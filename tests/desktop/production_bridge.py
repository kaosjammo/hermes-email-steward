"""Task-owned synthetic host wrapping the ACTUAL router/service/SQLite store.

This is not upstream host authentication acceptance. Trusted middleware injects
only the synthetic fixture principal, outside the production plugin's UI.
"""
import json
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from email_steward.api import create_router
from email_steward.rules import FIELDS
from email_steward.security import Settings, Access
from email_steward.service import Steward
from email_steward.store import Store
from email_steward.synthetic import SyntheticGmail

home = ROOT / ".local" / "desktop" / "production-state"
service = None
client = None
denied = False
providers = {}


def compose(reset=False):
    global service, client, access, providers
    if client:
        client.close()
    if reset and home.exists():
        shutil.rmtree(home)
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    settings = Settings(home=home.resolve(), profile="desktop-synthetic", owner="fixture-owner",
                        destination="fixture-private", private_confirmed=True,
                        desktop_subject="desktop:ui-fixture")
    providers = {"gmail-1": SyntheticGmail("alex@example.test"), "gmail-2": SyntheticGmail("sam@example.test")}
    service = Steward(Store(home / "email-steward"), settings, lambda account: providers[account["id"]])
    source = SimpleNamespace(platform="discord", user_id=settings.owner, chat_id=settings.destination,
                             chat_type="dm", profile=settings.profile, is_bot=False)
    access = Access(settings.home, settings.owner, "synthetic-local-seed")
    for ident, provider in providers.items():
        if not any(a["id"] == ident for a in service.store.accounts()):
            service.connect(access, ident, provider.address, "Personal" if ident == "gmail-1" else "Work")
    providers["gmail-1"].add("ui-message", subject="Invoice check", body="Please check invoice.")
    if not service.store.items():
        service.store.put_item(service.store.account("gmail-1"), "ui-message", dict(
            sender="synthetic@example.test", subject="Invoice check", summary="Please check invoice.",
            classification="needs_review", reason="Attachment significance needs review.",
            rule_id=None, archived=False, attachment_status="unreadable", latest_message="ui-message",
            changed=time.time(), link=""))
    app = FastAPI()

    @app.middleware("http")
    async def trusted_fixture(request, call_next):
        if not denied:
            request.state.native_http_principal = dict(subject="desktop:ui-fixture", purpose="native-http",
                scope="profile", profile_id=str(settings.home), capabilities=frozenset({"http:owner"}))
        return await call_next(request)

    app.include_router(create_router(lambda: service), prefix="/api/plugins/email-steward")
    client = TestClient(app)


compose()
for line in sys.stdin:
    try:
        command = json.loads(line)
        op = command.get("op", "request")
        if op == "reset":
            compose(True)
            result = {"status": 200, "body": {"reset": True}}
        elif op == "restart":
            compose()
            result = {"status": 200, "body": {"restarted": True}}
        elif op == "conflict":
            rules = service.rules(access)
            if rules:
                rule = rules[0]
                service.save_rule(access, {**{k: rule[k] for k in FIELDS}, "name": "Changed elsewhere", "version": rule["version"]}, rule["id"])
            result = {"status": 200, "body": {"changed": True}}
        else:
            denied = command.get("denied", False)
            response = client.request(command.get("method", "GET"), "/api/plugins/email-steward" + command["path"],
                                      **({"json": command["body"]} if command.get("body") is not None else {}))
            result = {"status": response.status_code, "body": response.json()}
    except Exception as exc:
        result = {"status": 500, "body": {"error": {"code": "bridge_failure", "message": str(exc)}}}
    print(json.dumps(result), flush=True)
client.close()
