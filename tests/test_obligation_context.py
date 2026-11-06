"""Cycle 2: actual worker/store/inspection/brief and real host-helper HTTP wire."""
import json
import os
from pathlib import Path
import socket

import pytest
from repair_wire import AccountWire, compose
from email_steward.service import Steward
from email_steward.store import Store
from email_steward.worker import Worker

REQUEST = "Please approve disputed renewal by Friday at 17:00."


@pytest.fixture
def env(tmp_path, monkeypatch, request):
    network = []
    def deny(*args, **kwargs):
        network.append(True)
        raise AssertionError("Only synthetic HTTP transport is authorised")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    wire = AccountWire()
    with wire.stack():
        s, a, w, d = compose(tmp_path)
        s.enable_pack(a, "starter-info", {"mailbox_id": None})
        def add(ident, body, received, subject="Receipt"):
            wire.add(ident, "t", body, subject)
            wire.boxes["A"]["messages"][ident]["internalDate"] = str(int(received * 1000))
        def fresh():
            service = Steward(Store(s.store.root), s.settings, model=s.model)
            return service, Worker(service, d)
        yield wire, s, a, w, d, add, fresh
        assert network == []
        assert wire.foreign() == []
        if os.environ.get("ES_CONTEXT_EVIDENCE"):
            root = Path(os.environ["ES_CONTEXT_EVIDENCE"])
            root.mkdir(parents=True, exist_ok=True)
            (root / (request.node.name.replace("/", "_") + ".json")).write_text(json.dumps({
                "case": request.node.name, "network_attempts": len(network), "items": s.store.items(),
                "jobs": s.store.rows("SELECT * FROM jobs"), "wire": wire.calls,
                "briefs": s.store.rows("SELECT text FROM outbox WHERE category='brief'")}, indent=2) + "\n")


def context(s, a, w, expected="m2", phrase="disputed renewal", deadline="Friday"):
    item = s.store.items()[0]
    assert item["reference"] == "ax1" and item["classification"] == "needs_action"
    assert item["latest_message"] == expected
    assert phrase in item["summary"] and deadline in item["deadline"]
    assert phrase in s.inspect(a, item["reference"], text=True)["text"]
    w.brief(1300, key="context-" + str(item["version"]))
    brief = s.store.rows("SELECT text FROM outbox WHERE category='brief'")[-1]["text"]
    assert phrase in brief and deadline in brief and "17:00" in brief
    return item


@pytest.mark.parametrize("ids", [("m1", "m2"), ("z-old", "a-new")])
def test_batch_uses_provider_chronology_not_opaque_id_order(env, ids):
    wire, s, a, w, d, add, fresh = env
    add(ids[0], "Harmless receipt", 1000)
    add(ids[1], REQUEST, 1001, "Reply")
    w.tick(1100)
    context(s, a, w, ids[1])
    assert all(j["status"] == "done" for j in s.store.rows("SELECT * FROM jobs"))
    for m in wire.boxes["A"]["messages"].values():
        assert "Label_A" in m["labelIds"] and "UNREAD" in m["labelIds"]
    assert "INBOX" in wire.boxes["A"]["messages"][ids[1]]["labelIds"]


@pytest.mark.parametrize("older", ["Harmless receipt", "Please review the obsolete quote today."])
def test_after_triaged_failure_restart_retry_preserves_newer_context(env, older):
    wire, s, a, w, d, add, fresh = env
    add("m1", older, 1000)
    add("m2", REQUEST, 1001, "Reply")
    hit = []
    def once(point):
        if point == "after_triaged" and not hit:
            hit.append(True)
            raise RuntimeError("Synthetic interrupted old assessment")
    w.crash = once
    w.tick(1100)
    before = context(s, a, w)
    s, w = fresh()
    w.tick(1200)
    after = context(s, a, w)
    for key in ("summary", "deadline", "reason", "holds", "urgent", "urgent_category", "latest_message", "received"):
        assert after[key] == before[key], key
    w.tick(1250)  # Repeated recovery is idempotent.
    context(s, a, w)
    assert all(j["status"] == "done" for j in s.store.rows("SELECT * FROM jobs"))
    assert all("Label_A" in m["labelIds"] for m in wire.boxes["A"]["messages"].values())


def test_newer_informational_followup_preserves_open_substance_and_inspection(env):
    wire, s, a, w, d, add, fresh = env
    add("m2", REQUEST, 1000, "Reply")
    w.tick(1100)
    before = context(s, a, w)
    add("m3", "Harmless receipt", 1001)
    w.tick(1200)
    after = context(s, a, w)
    assert all(after[k] == before[k] for k in ("summary", "deadline", "holds", "reason", "urgent"))
    assert after["activity_message"] == "m3" and after["activity_received"] == 1001
    assert all(j["status"] == "done" for j in s.store.rows("SELECT * FROM jobs"))
    assert "Label_A" in wire.boxes["A"]["messages"]["m3"]["labelIds"]


@pytest.mark.parametrize("action", ["done", "snooze", "waiting", "remind", "archive", "restore", "correct"])
def test_older_action_retry_cannot_undo_newer_owner_transition(env, action):
    wire, s, a, w, d, add, fresh = env
    add("m1", "Please review obsolete quote today.", 1000)
    add("m2", REQUEST, 1001, "Reply")
    hit = []
    def fail(point):
        if point == "after_triaged" and not hit:
            hit.append(True)
            raise RuntimeError("Synthetic old job interruption")
    w.crash = fail
    w.tick(1100)
    item = s.store.items()[0]
    import time
    due = time.time() + 3600
    if action == "correct":
        s.correct(a, item["reference"], {"version": item["version"], "classification": "needs_review", "always": False})
    else:
        s.action(a, item["reference"], action, at=due if action in {"snooze", "waiting", "remind"} else None)
    before = s.store.items()[0]
    # A manual provider move makes the older job eligible again, even after Done.
    for m in wire.boxes["A"]["messages"].values():
        m["labelIds"] = sorted(set(m["labelIds"]) | {"INBOX"})
    s, w = fresh()
    w.tick(1200)
    after = s.store.items()[0]
    for key in ("classification", "summary", "deadline", "reason", "latest_message", "snooze_until", "reminder_at"):
        assert after[key] == before[key], (action, key)
    assert all(j["status"] == "done" for j in s.store.rows("SELECT * FROM jobs"))
    assert len([x for x in d.sent if x[1].startswith("urgent:")]) == 0
    assert "disputed renewal" in s.inspect(a, after["reference"], text=True)["text"]


@pytest.mark.parametrize("kind", ["action", "review"])
def test_genuine_new_substantive_reply_updates_or_reopens_context(env, kind):
    wire, s, a, w, d, add, fresh = env
    add("m2", REQUEST, 1000)
    w.tick(1100)
    s.action(a, "ax1", "done")
    assert s.store.item("ax1")["classification"] == "done"
    body = "Please approve replacement agreement by Friday at 17:00." if kind == "action" else "Maybe uncertain significance about replacement agreement."
    add("new", body, 1002, "Reply" if kind == "action" else "Notice")
    s, w = fresh()
    w.tick(1200)
    item = s.store.item("ax1")
    assert item["classification"] == ("needs_action" if kind == "action" else "needs_review")
    assert item["latest_message"] == "new" and "replacement agreement" in item["summary"]
    assert not item["archived"] and item["reminder_at"] is None
    assert "replacement agreement" in s.inspect(a, "ax1", text=True)["text"]


def test_sent_barrier_and_informational_mail_preserve_waiting_context(env):
    wire, s, a, w, d, add, fresh = env
    add("m2", REQUEST, 1000)
    w.tick(1100)
    add("sent", "Owner's synthetic reply", 1002, "Re: Reply")
    wire.boxes["A"]["messages"]["sent"]["labelIds"] = ["SENT"]
    w.tick(1150)
    assert s.store.item("ax1")["classification"] == "waiting"
    add("late-old", "Please review obsolete quote today.", 1001, "Old reply")
    add("info", "Harmless receipt", 1003)
    w.tick(1200)
    item = s.store.item("ax1")
    assert item["classification"] == "waiting" and item["latest_message"] == "m2"
    assert "disputed renewal" in item["summary"] and "Friday" in item["deadline"]
    add("response", "Please approve replacement agreement by Friday at 17:00.", 1004)
    w.tick(1250)
    assert s.store.item("ax1")["latest_message"] == "response"
    assert s.store.item("ax1")["classification"] == "needs_action"


def test_newer_fyi_processed_first_does_not_resolve_older_unassessed_request(env):
    wire, s, a, w, d, add, fresh = env
    add("z-request", REQUEST, 1000)
    add("a-receipt", "Harmless receipt", 1001)
    w.tick(1100)
    context(s, a, w, "z-request")
    assert s.store.item("ax1")["activity_received"] == 1001


def test_done_fences_already_queued_work_even_if_it_has_a_later_provider_date(env):
    wire, s, a, w, d, add, fresh = env
    add("a-pending", "Please review queued quote today.", 1003)
    add("m2", REQUEST, 1001)
    hit = []
    def fail(point):
        if point == "after_triaged" and not hit:
            hit.append(True)
            raise RuntimeError("Synthetic queued work interruption")
    w.crash = fail
    w.tick(1100)
    s.action(a, "ax1", "done")
    for m in wire.boxes["A"]["messages"].values():
        m["labelIds"] = sorted(set(m["labelIds"]) | {"INBOX"})
    s, w = fresh()
    w.tick(1200)
    item = s.store.item("ax1")
    assert item["classification"] == "done" and item["latest_message"] == "m2"
    assert "Friday" in item["deadline"]
    assert all(j["status"] == "done" for j in s.store.rows("SELECT * FROM jobs"))
    assert not any(ident.startswith("urgent:") for _, ident, _ in d.sent)


def test_equal_date_new_arrival_can_reopen_done_but_cannot_replace_open_context(env):
    wire, s, a, w, d, add, fresh = env
    add("m2", REQUEST, 1000)
    w.tick(1100)
    add("old-tie", "Please review another quote today.", 1000)
    w.tick(1120)
    context(s, a, w)
    s.action(a, "ax1", "done")
    add("new-tie", "Please approve replacement agreement by Friday at 17:00.", 1000)
    w.tick(1200)
    context(s, a, w, "new-tie", "replacement agreement")


def test_shared_rest_preview_and_correction_use_preserved_request_context(env):
    from dataclasses import replace
    from test_backend import client_for
    wire, s, a, w, d, add, fresh = env
    s.settings = replace(s.settings, desktop_subject="desktop:synthetic")
    add("m2", REQUEST, 1000)
    w.tick(1100)
    add("m3", "Harmless receipt", 1001)
    w.tick(1200)
    client = client_for(s)
    rule = dict(name="Request context", enabled=True, priority=100, mailbox_id=None,
                conditions=[dict(field="body", operator="contains", value="disputed renewal")],
                actions=dict(classification="needs_review", archive=False))
    response = client.post("/api/plugins/email-steward/rules/preview", json={"rule": rule, "reference": "ax1"})
    assert response.status_code == 200 and response.json()["matched"] is True
    item = s.store.item("ax1")
    response = client.post("/api/plugins/email-steward/items/ax1/correct", json={
        "version": item["version"], "classification": "needs_review", "always": False})
    assert response.status_code == 200, response.text
    assert s.store.item("ax1")["latest_message"] == "m2"
    assert s.store.item("ax1")["owner_received"] == 1001
    assert "disputed renewal" in s.inspect(a, "ax1", text=True)["text"]
