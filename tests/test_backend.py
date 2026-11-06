"""Synthetic production-entrypoint regressions; never uses a real mailbox."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import json
import os
import time

import pytest
from fastapi import FastAPI
import asyncio
import httpx

from email_steward.api import create_router
from email_steward.security import Settings, discord_access
from email_steward.service import Steward
from email_steward.store import Store
from email_steward.worker import Worker
from email_steward.errors import Error
from email_steward.synthetic import SyntheticGmail, SyntheticModel, SyntheticDelivery


@pytest.fixture
def env(tmp_path):
    settings = Settings(home=tmp_path, profile="synthetic", owner="12345", destination="67890",
                        destination_type="dm", private_confirmed=True,
                        desktop_subject="desktop:synthetic", timezone="Australia/Melbourne")
    provider, delivery, model = SyntheticGmail(), SyntheticDelivery(), SyntheticModel()
    store = Store(tmp_path / "email-steward")
    service = Steward(store, settings, lambda account: provider, model)
    from test_gateways import native_source
    source, transport = native_source(settings)
    # Keep the synthetic receiving transport alive for this fixture.
    source._fixture_transport = transport
    access = discord_access(settings, source)
    service.connect(access, "gmail-1", "alex@example.test", "Synthetic personal")
    return service, Worker(service, delivery), provider, delivery, access, source


def rule(**changes):
    return dict(name="Invoices", enabled=True, mailbox_id=None, priority=100,
                conditions=[dict(field="subject", operator="contains", value="invoice")],
                actions=dict(classification="fyi", archive=True), **changes)


def client_for(service, principal=True, boolean=False):
    app = FastAPI()
    if principal or boolean:
        @app.middleware("http")
        async def trusted_fixture(request, call_next):
            if principal:
                request.state.native_http_principal = dict(profile_id=str(service.settings.home),
                    subject="desktop:synthetic", purpose="native-http", scope="profile",
                    capabilities=frozenset({"http:owner"}))
            if boolean:
                request.state.token_authenticated = True
            return await call_next(request)
    app.include_router(create_router(lambda: service), prefix="/api/plugins/email-steward")
    class Client:
        def request(self, method, path, **kwargs):
            async def send():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://synthetic") as client:
                    return await client.request(method, path, **kwargs)
            return asyncio.run(send())
        def get(self, path, **kwargs): return self.request("GET", path, **kwargs)
        def post(self, path, **kwargs): return self.request("POST", path, **kwargs)
        def put(self, path, **kwargs): return self.request("PUT", path, **kwargs)
    return Client()


def test_rest_discord_parity_conflicts_and_preview(env):
    s, w, p, d, a, _ = env
    api = client_for(s)
    base = "/api/plugins/email-steward"
    created = api.post(base + "/rules", json=rule())
    assert created.status_code == 201, created.text
    saved = created.json()["rule"]
    assert s.rules(a) == [saved]
    update = api.put(base + "/rules/" + saved["id"], json={**rule(), "version": 1})
    assert update.json()["rule"]["version"] == 2
    conflict = api.post(base + "/rules/" + saved["id"] + "/toggle", json={"version": 1, "enabled": False})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["current"]["version"] == 2
    preview = api.post(base + "/rules/preview", json={"rule": rule(), "sample": {
        "mailbox_id": "gmail-1", "sender": "billing@example.test", "subject": "invoice", "body": "Payment failed. Please respond today."}})
    assert preview.status_code == 200
    assert preview.json()["matched"] and not preview.json()["archive"] and preview.json()["holds"]
    assert len(s.rules(a)) == 1
    assert api.post(base + "/rules", json={**rule(), "owner": "owner"}).status_code == 422
    assert api.post(base + "/rules", json={**rule(), "mailbox_id": "foreign"}).status_code == 422
    for scope in (None, "gmail-1"):
        r = api.post(base + "/packs/starter-action/enable", json={"mailbox_id": scope})
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()["rules"]]
        assert [x["id"] for x in api.post(base + "/packs/starter-action/enable", json={"mailbox_id": scope}).json()["rules"]] == ids


def test_owner_auth_fails_closed(env):
    s, w, p, d, a, src = env
    path = "/api/plugins/email-steward/rules"
    for client in (client_for(s, False), client_for(s, False, True)):
        assert client.get(path, headers={"X-Owner": "owner"}).status_code == 401
    for key, val in (("user_id", "intruder"), ("chat_id", "public"), ("chat_type", "channel"), ("profile", "other"), ("is_bot", True)):
        from gateway.session_identity import replace_source
        fake = replace_source(src, **{key: val})
        with pytest.raises(Error):
            discord_access(s.settings, fake)


def test_worker_baseline_archive_holds_retry_and_lifecycle(env):
    s, w, p, d, a, _ = env
    p.add("old", thread="old", subject="old", historical=True)
    s.save_rule(a, rule())
    p.add("m1", thread="same", subject="Invoice", body="Payment failed. Please respond today.", unread=True)
    p.fail_modify = 1
    w.tick(now=1000)
    assert not d.sent or "All clear" not in str(d.sent)
    w.tick(now=1100)
    items = s.items(a)
    assert len(items) == 1
    item = items[0]
    assert item["classification"] == "needs_action" and not item["archived"]
    assert p.messages["m1"]["unread"] and "Triaged" in p.messages["m1"]["labels"]
    w.tick(now=1200)
    assert len(s.items(a)) == 1
    s.action(a, item["reference"], "done")
    assert s.items(a)[0]["classification"] == "done"
    assert p.messages["m1"]["unread"] and "INBOX" not in p.messages["m1"]["labels"]
    p.add("m2", thread="same", subject="Re: invoice", body="Can you confirm today?")
    w.tick(now=1300)
    assert s.items(a)[0]["reference"] == item["reference"]
    assert s.items(a)[0]["classification"] == "needs_action"


def test_alias_account_isolation_and_restart(env):
    s, w, p, d, a, _ = env
    p.add("m1", thread="one", body="Please respond")
    w.tick(now=1000)
    first = s.items(a)[0]
    digest1 = w.brief(1000, key="first")
    p.add("m2", thread="two", body="Please respond")
    w.tick(now=1100)
    digest2 = w.brief(1100, key="second")
    assert s.store.resolve(digest1 + ":A1") == first["reference"]
    with pytest.raises(Error, match="ambiguous"):
        s.store.resolve("A1")
    assert s.store.resolve(digest2 + ":A1")
    assert "authuser=alex%40example.test" in first["link"]
    other = SyntheticGmail(address="az@example.test")
    s.provider_factory = lambda account: p if account["id"] == "gmail-1" else other
    s.connect(a, "gmail-2", "az@example.test", "Other synthetic")
    other.add("m1", thread="one", body="Please respond")
    w.tick(now=1200)
    refs = [i["reference"] for i in s.items(a)]
    assert len(refs) == len(set(refs)) == 3
    assert Store(s.store.root).resolve(digest1 + ":A1") == first["reference"]


def test_concurrent_ticks_and_action_do_not_duplicate(env):
    s, w, p, d, a, _ = env
    p.add("m", thread="t", body="Please respond")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: w.tick(now=1000), range(4)))
    assert len(s.items(a)) == 1
    item = s.items(a)[0]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: s.action(a, item["reference"], "done"), range(3)))
    assert s.items(a)[0]["classification"] == "done"


def test_reauthorised_oauth_slot_cannot_read_or_mutate_old_account_items(env):
    s, w, p, d, a, _ = env
    p.add("same-id", thread="same-thread", body="Please respond")
    w.tick(now=1000)
    item = s.items(a)[0]
    before = list(p.modifications)
    # A slot can be reauthorised between polls; even a colliding provider ID
    # must not let an old item read/change the newly selected mailbox.
    p.address = "another@example.test"
    operations = [lambda: s.action(a, item["reference"], "archive"),
                  lambda: s.inspect(a, item["reference"], text=True),
                  lambda: s.preview(a, {"rule": rule(), "reference": item["reference"]})]
    for operation in operations:
        with pytest.raises(Error, match="mailbox|Mailbox|grant|Grant|account|Account"):
            operation()
    assert p.modifications == before
    assert not s.items(a)[0]["archived"]
    assert len([m for m in p.modifications if m[1] == "Triaged"]) == 1
