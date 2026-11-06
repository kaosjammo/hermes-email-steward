"""Synthetic HTTP + grant store; actual Hermes OAuth/helper and Gmail/service run.

Based on the independently reported A-001 wire boundary. No actual credential,
mailbox, inference or external HTTP is used. A real provider rejects an explicit
user address that the bearer cannot access; this fixture models that refusal.
"""
import base64
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import unquote

SOURCE = Path(os.environ.get("ES_REPAIR_SOURCE", Path(__file__).resolve().parents[1]))
UPSTREAM = Path(os.environ.get("HERMES_UPSTREAM", Path(__file__).resolve().parents[2]))
sys.path[:0] = [str(SOURCE), str(UPSTREAM)]
import httpx
from hermes_cli import plugin_provider_requests as host, plugin_oauth as oauth
from email_steward.security import Settings, Access
from email_steward.service import Steward
from email_steward.store import Store
from email_steward.worker import Worker
from email_steward.synthetic import SyntheticDelivery, SyntheticModel


def wire(ident, thread, body="Synthetic informational text", subject="Receipt"):
    return dict(id=ident, threadId=thread, internalDate="1000000", labelIds=["INBOX", "UNREAD"], payload={
        "mimeType": "text/plain", "headers": [{"name": "From", "value": "billing@example.test"},
        {"name": "Subject", "value": subject}], "body": {"data": base64.urlsafe_b64encode(body.encode()).decode(), "size": len(body)}})


class AccountWire:
    def __init__(self):
        self.active, self.calls, self.profiles = "A", [], 0
        self.after = None
        self.boxes = {key: dict(address=address, history=0, messages={}, events=[],
            labels=[{"id": "Label_" + key, "name": "Triaged"}])
            for key, address in [("A", "alex@example.test"), ("B", "other@example.test")]}
        self.spec = oauth._declared_clients(SOURCE)[0]

    def grant(self, key):
        assert key.endswith(":gmail-1")
        return dict(access_token="synthetic-" + self.active, fingerprint=self.spec.fingerprint)

    def add(self, ident, thread="thread", body="Informational content", subject="Receipt", box="A"):
        account = self.boxes[box]
        account["history"] += 1
        account["events"].append((account["history"], ident))
        account["messages"][ident] = wire(ident, thread, body, subject)

    def handle(self, request):
        key = request.headers["authorization"].removeprefix("Bearer synthetic-")
        assert key in self.boxes
        box = self.boxes[key]
        user, _, tail = request.url.path.removeprefix("/gmail/v1/users/").partition("/")
        user, path = unquote(user), "/" + tail
        denied = user not in {"me", box["address"]}
        body = json.loads(request.content) if request.content else None
        self.calls.append(dict(mailbox=key, user=user, method=request.method, path=path, body=body, denied=denied))
        if denied:
            return httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED"}})
        result = {}
        if path == "/profile":
            self.profiles += 1
            result = {"emailAddress": box["address"], "historyId": str(box["history"])}
        elif path == "/history":
            start = int(request.url.params["startHistoryId"])
            result = {"historyId": str(box["history"]), "history": [{"id": str(n),
                "messagesAdded": [{"message": {"id": ident}}]} for n, ident in box["events"] if n > start]}
        elif path == "/labels":
            result = {"labels": box["labels"]}
        elif path == "/messages":
            result = {"messages": [{"id": ident} for ident in box["messages"]]}
        elif path.startswith("/messages/"):
            ident = path.split("/")[2]
            if ident not in box["messages"]:
                return httpx.Response(404, json={"error": "synthetic not found"})
            result = box["messages"][ident]
            if path.endswith("/modify"):
                labels = set(result["labelIds"])
                labels.update(body["addLabelIds"])
                labels.difference_update(body["removeLabelIds"])
                result["labelIds"] = sorted(labels)
            elif "/attachments/" in path:
                result = {"data": base64.urlsafe_b64encode(b"synthetic attachment").decode()}
        elif path.startswith("/threads/"):
            thread = path.split("/")[2]
            messages = [m for m in box["messages"].values() if m["threadId"] == thread]
            if path.endswith("/modify"):
                for message in messages:
                    labels = set(message["labelIds"])
                    labels.update(body["addLabelIds"])
                    labels.difference_update(body["removeLabelIds"])
                    message["labelIds"] = sorted(labels)
            result = {"messages": messages}
        else:
            raise AssertionError("Unexpected synthetic wire route " + path)
        if self.after:
            self.after(request, path)
        return httpx.Response(200, json=result)

    def stack(self):
        stack, original = ExitStack(), httpx.Client
        transport = httpx.MockTransport(self.handle)
        stack.enter_context(patch.object(host, "_calling_plugin_dir", lambda: SOURCE))
        stack.enter_context(patch.object(oauth, "_read_grant", self.grant))
        stack.enter_context(patch.object(httpx, "Client", lambda *a, **kw: original(*a, transport=transport, **kw)))
        return stack

    def foreign(self):
        return [c for c in self.calls if c["mailbox"] == "B" and not c["denied"] and c["path"] != "/profile"]


def compose(home):
    settings = Settings(home=home, profile="synthetic-repair", owner="owner", destination="private",
                        private_confirmed=True, timezone="UTC")
    service = Steward(Store(home / "state"), settings, model=SyntheticModel())
    access = Access(settings.home, settings.owner, "synthetic-owner")
    service.connect(access, "gmail-1", "alex@example.test", "Synthetic A")
    delivery = SyntheticDelivery()
    return service, access, Worker(service, delivery), delivery
