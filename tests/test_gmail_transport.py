"""Synthetic loopback Gmail REST server, driven through the real Gmail adapter and worker."""
import base64
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from threading import Thread
from urllib.parse import urlsplit, parse_qs, unquote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from email_steward.errors import Error
from email_steward.gmail import Gmail
from email_steward.security import Access, Settings
from email_steward.service import Steward
from email_steward.store import Store
from email_steward.synthetic import SyntheticDelivery, SyntheticModel
from email_steward.worker import Worker


def wire_message(ident, thread, body="Synthetic informative content", *, unread=True, inbox=True, subject="Receipt"):
    labels = (["INBOX"] if inbox else []) + (["UNREAD"] if unread else [])
    return dict(id=ident, threadId=thread, internalDate="1000000", labelIds=labels, payload={
        "mimeType": "text/plain", "headers": [{"name": "From", "value": "billing@example.test"}, {"name": "Subject", "value": subject}],
        "body": {"data": base64.urlsafe_b64encode(body.encode()).decode(), "size": len(body)}})


@contextmanager
def synthetic_server():
    state = {slot: {"address": address, "history": 0, "messages": {}, "events": [], "labels": [], "requests": []}
             for slot, address in (("gmail-1", "alex@example.test"), ("gmail-2", "work@example.test"))}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return
        def do_GET(self):
            self.handle_json("GET")
        def do_POST(self):
            self.handle_json("POST")
        def handle_json(self, method):
            slot = self.headers["X-Synthetic-Grant"]
            assert slot in state
            account = state[slot]
            path = urlsplit(self.path)
            user, _, tail = path.path.removeprefix("/gmail/v1/users/").partition("/")
            suffix = "/" + tail
            query = parse_qs(path.query)
            size = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(size)) if size else None
            account["requests"].append((method, suffix, query, body))
            if unquote(user).casefold() != account["address"].casefold():
                self.send_response(403)
                self.end_headers()
                return
            result = {}
            if suffix == "/profile":
                result = {"emailAddress": account["address"], "historyId": str(account["history"])}
            elif suffix == "/history":
                start = int(query["startHistoryId"][0])
                result = {"historyId": str(account["history"]), "history": [
                    {"id": str(n), "messagesAdded": [{"message": {"id": ident}}]} for n, ident in account["events"] if n > start]}
            elif suffix == "/labels" and method == "GET":
                result = {"labels": account["labels"]}
            elif suffix == "/labels" and method == "POST":
                result = {"id": "Label_Triaged", "name": body["name"]}
                account["labels"].append(result)
            elif suffix.startswith("/messages/"):
                ident = suffix.split("/")[2]
                result = account["messages"][ident]
                if suffix.endswith("/modify"):
                    labels = set(result["labelIds"])
                    labels.update(body["addLabelIds"])
                    labels.difference_update(body["removeLabelIds"])
                    result["labelIds"] = sorted(labels)
            elif suffix.startswith("/threads/"):
                thread = suffix.split("/")[2]
                messages = [m for m in account["messages"].values() if m["threadId"] == thread]
                if suffix.endswith("/modify"):
                    for message in messages:
                        labels = set(message["labelIds"])
                        labels.update(body["addLabelIds"])
                        labels.difference_update(body["removeLabelIds"])
                        message["labelIds"] = sorted(labels)
                result = {"id": thread, "messages": messages}
            raw = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    class Response:
        def __init__(self, status, body):
            self.status, self.body = status, body
        def json(self): return json.loads(self.body)
    def request(slot, method, url, *, json=None, timeout=20):
        parts = urlsplit(url)
        assert parts.scheme == "https" and parts.netloc == "gmail.googleapis.com"
        target = f"http://127.0.0.1:{server.server_port}" + parts.path + ("?" + parts.query if parts.query else "")
        import json as serializer
        req = Request(target, data=serializer.dumps(json).encode() if json is not None else None, method=method,
                      headers={"X-Synthetic-Grant": slot, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=timeout) as response:
                return Response(response.status, response.read())
        except HTTPError as error:
            return Response(error.code, error.read())
    try:
        yield state, request
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_two_grants_real_http_baseline_triaged_archive_restore_unread_and_no_forbidden_calls(tmp_path):
    with synthetic_server() as (state, request):
        settings = Settings(home=tmp_path, profile="synthetic", owner="owner", destination="private", private_confirmed=True, timezone="UTC")
        s = Steward(Store(tmp_path / "state"), settings, lambda account: Gmail(account["grant_id"], request, expected_address=account["address"]), SyntheticModel())
        a = Access(settings.home, settings.owner, "synthetic-owner")
        state["gmail-1"]["messages"]["old"] = wire_message("old", "old")
        state["gmail-1"]["history"] = 1
        state["gmail-1"]["events"].append((1, "old"))
        s.connect(a, "gmail-1", "alex@example.test", "Synthetic personal")
        s.connect(a, "gmail-2", "work@example.test", "Synthetic work")
        s.enable_pack(a, "starter-info", {"mailbox_id": None})
        for slot in state:
            state[slot]["history"] += 1
            state[slot]["messages"]["new"] = wire_message("new", "shared-thread")
            state[slot]["events"].append((state[slot]["history"], "new"))
        d = SyntheticDelivery()
        Worker(s, d).tick(now=1100)
        assert len(s.items(a)) == 2
        for slot in state:
            labels = state[slot]["messages"]["new"]["labelIds"]
            assert "UNREAD" in labels and "INBOX" not in labels and "Label_Triaged" in labels
        assert "Label_Triaged" not in state["gmail-1"]["messages"]["old"]["labelIds"]
        item = next(i for i in s.items(a) if i["mailbox_id"] == "gmail-2")
        s.action(a, item["reference"], "restore")
        assert "INBOX" in state["gmail-2"]["messages"]["new"]["labelIds"]
        assert "INBOX" not in state["gmail-1"]["messages"]["new"]["labelIds"]
        for account in state.values():
            for method, path, query, body in account["requests"]:
                assert not any(x in path for x in ("/send", "/drafts", "/trash", "/delete"))
                if body and path.endswith("/modify"):
                    assert "UNREAD" not in body["addLabelIds"] + body["removeLabelIds"]


def test_wrong_account_refuses_connect_and_changed_grant_pauses_worker(tmp_path):
    with synthetic_server() as (state, request):
        settings = Settings(home=tmp_path, profile="synthetic", owner="o", destination="p", private_confirmed=True, timezone="UTC")
        s = Steward(Store(tmp_path / "state"), settings, lambda account: Gmail(account["grant_id"], request, expected_address=account["address"]))
        a = Access(settings.home, "o", "synthetic")
        with pytest.raises(Error) as denial:
            s.connect(a, "gmail-2", "alex@example.test", "Wrong")
        assert denial.value.body["error"]["code"] == "account_access_denied"
        assert not s.store.accounts()
        s.connect(a, "gmail-1", "alex@example.test", "Right")
        state["gmail-1"]["address"] = "replaced@example.test"
        Worker(s, SyntheticDelivery()).tick(now=1000)
        assert s.store.account("gmail-1")["last_error"]


def test_real_transport_refuses_item_reads_and_effects_after_slot_reauthorisation(tmp_path):
    with synthetic_server() as (state, request):
        settings = Settings(home=tmp_path, profile="synthetic", owner="o", destination="p",
                            private_confirmed=True, timezone="UTC")
        service = Steward(Store(tmp_path / "state"), settings,
                          lambda account: Gmail(account["grant_id"], request, expected_address=account["address"]))
        access = Access(settings.home, "o", "synthetic")
        service.connect(access, "gmail-1", "alex@example.test", "Original")
        account = state["gmail-1"]
        account["history"] = 1
        account["events"].append((1, "same-id"))
        account["messages"]["same-id"] = wire_message("same-id", "same-thread", "Please respond")
        Worker(service, SyntheticDelivery()).tick(now=1100)
        item = service.items(access)[0]
        account["address"] = "new-owner@example.test"
        before = len(account["requests"])
        for operation in (lambda: service.inspect(access, item["reference"], text=True),
                          lambda: service.action(access, item["reference"], "archive")):
            with pytest.raises(Error) as denial:
                operation()
            assert denial.value.body["error"]["code"] == "account_access_denied"
        assert account["requests"][before:]
        assert all(method == "GET" and path == "/profile"
                   for method, path, _, _ in account["requests"][before:])
        assert "INBOX" in account["messages"]["same-id"]["labelIds"]
