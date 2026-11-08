"""Accepted cycle-1 regressions through real production/helper boundaries."""
from dataclasses import replace
import json
from unittest.mock import patch

import pytest
from repair_wire import AccountWire, compose, SOURCE
from email_steward.errors import Error
from email_steward.gmail import Attachment
from email_steward.judgement import CONSENT


@pytest.fixture
def wire_env(tmp_path):
    wire = AccountWire()
    with wire.stack():
        yield (wire, *compose(tmp_path))


def attempt(operation):
    try:
        return operation()
    except Error:
        return None  # Provider denial is expected; never count foreign success.


@pytest.mark.parametrize("operation", ["inspect", "effect"])
def test_grant_flip_after_profile_cannot_read_or_mutate_foreign_account(wire_env, operation):
    wire, service, access, worker, delivery = wire_env
    wire.add("m1", "t1", "Please respond", "Request")
    worker.tick(1100)
    ref = service.items(access)[0]["reference"]
    wire.add("m1", "t1", "Foreign synthetic private content", box="B")
    before = list(wire.boxes["B"]["messages"]["m1"]["labelIds"])
    wire.calls.clear()
    def flip(request, path):
        if path == "/profile":
            wire.active, wire.after = "B", None
    wire.after = flip
    result = attempt(lambda: service.inspect(access, ref, text=True) if operation == "inspect" else service.action(access, ref, "archive"))
    assert wire.foreign() == []
    assert "Foreign synthetic private content" not in str(result)
    assert wire.boxes["B"]["messages"]["m1"]["labelIds"] == before
    assert any(c["denied"] for c in wire.calls)


def test_label_cache_cannot_cross_a_grant_flip_between_lookup_and_modify(wire_env):
    wire, service, access, worker, delivery = wire_env
    wire.add("m1", "t1")
    wire.add("m1", "t1", box="B")
    wire.boxes["B"]["labels"].append({"id": "Label_A", "name": "Unrelated B label"})
    worker._poll(service.store.account("gmail-1"), 1100)
    def flip(request, path):
        if path == "/labels":
            wire.active, wire.after = "B", None
    wire.after = flip
    attempt(lambda: worker._process(service.store.rows("SELECT * FROM jobs")[0], 1100))
    assert wire.foreign() == []
    assert wire.boxes["B"]["messages"]["m1"]["labelIds"] == ["INBOX", "UNREAD"]
    assert service.store.rows("SELECT * FROM messages") == []


def test_foreign_history_never_commits_ids_or_checkpoint_even_without_collision(wire_env):
    wire, service, access, worker, delivery = wire_env
    wire.add("B-only", "B-thread", box="B")
    profiles = wire.profiles
    def flip(request, path):
        if path == "/profile" and wire.profiles == profiles + 2:
            wire.active, wire.after = "B", None
    wire.after = flip
    worker.tick(1100)
    assert service.store.rows("SELECT * FROM jobs") == []
    assert service.store.account("gmail-1")["checkpoint"] == "0"
    assert wire.foreign() == []


@pytest.mark.parametrize("resource", ["history", "list", "attachment", "thread", "labels"])
def test_all_resource_paths_deny_foreign_bearer_at_provider_boundary(wire_env, resource):
    wire, service, access, worker, delivery = wire_env
    wire.add("same", "t", box="B")
    provider = service.provider(service.store.account("gmail-1"))
    wire.active, wire.calls = "B", []
    operations = {"history": lambda: provider.changes("0"), "list": lambda: provider.historical(0, 2000, 10),
        "attachment": lambda: provider.call("GET", "/messages/same/attachments/a"),
        "thread": lambda: provider.thread_state("t"), "labels": provider.triaged_label}
    attempt(operations[resource])
    assert wire.foreign() == []
    assert wire.calls and all(c["denied"] and c["user"] == "alex@example.test" for c in wire.calls)


def test_batched_reply_is_assessed_triaged_and_urgent_on_same_reference(wire_env):
    wire, service, access, worker, delivery = wire_env
    service.enable_pack(access, "starter-info", {"mailbox_id": None})
    wire.add("m1", "t", "Harmless receipt")
    wire.add("m2", "t", "Please approve the disputed charge today", "Re: Receipt")
    worker.tick(1100)
    worker.tick(1200)
    item = service.store.item(service.items(access)[0]["reference"])
    assert item["classification"] == "needs_action" and item["latest_message"] == "m2"
    assert not item["archived"] and item["reference"] == "ax1"
    assert all(row["status"] == "done" for row in service.store.rows("SELECT status FROM jobs"))
    assert "Label_A" in wire.boxes["A"]["messages"]["m2"]["labelIds"]
    assert "INBOX" in wire.boxes["A"]["messages"]["m2"]["labelIds"]
    assert all("UNREAD" in m["labelIds"] for m in wire.boxes["A"]["messages"].values())
    assert any(ident.startswith("urgent:") for _, ident, _ in delivery.sent)


def test_stale_automatic_effect_retry_cannot_archive_new_arrival_or_rewrite_successor(wire_env):
    wire, service, access, worker, delivery = wire_env
    service.enable_pack(access, "starter-info", {"mailbox_id": None})
    wire.add("m1", "t", "Harmless receipt")
    original = service.retry_effects
    with patch.object(service, "retry_effects", lambda: None):
        worker.tick(1100)
    assert service.store.rows("SELECT * FROM effects WHERE status='pending'")
    wire.add("m2", "t", "Please approve today", "Reply")
    original()  # Retry of old m1 effect before newer message is even queued.
    assert "INBOX" in wire.boxes["A"]["messages"]["m2"]["labelIds"]
    worker.tick(1200)
    item = service.store.item(service.items(access)[0]["reference"])
    assert item["latest_message"] == "m2" and item["classification"] == "needs_action" and not item["archived"]
    # Another old intent cannot overwrite the successor's state on recovery.
    service.store.execute("UPDATE effects SET status='pending'")
    original()
    assert service.store.item(item["reference"])["classification"] == "needs_action"
    assert not service.store.item(item["reference"])["archived"]


def test_final_mime_join_truncation_is_visible_and_holds_archive(wire_env):
    import base64
    wire, service, access, worker, delivery = wire_env
    service.enable_pack(access, "starter-info", {"mailbox_id": None})
    wire.add("m1", "t")
    message = wire.boxes["A"]["messages"]["m1"]
    chunks = ["x" * 320 for _ in range(99)] + ["x" * 285 + "Please approve today"]
    chunks[0] += chunks.pop(1)
    assert sum(map(len, chunks)) <= 32000 < len("\n".join(chunks))
    message["payload"] = {"mimeType": "multipart/mixed", "headers": message["payload"]["headers"],
        "parts": [{"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(c.encode()).decode()}} for c in chunks]}
    worker.tick(1100)
    item = service.store.item(service.items(access)[0]["reference"])
    assert item["attachment_status"] == "unreadable" and item["classification"] == "needs_review"
    assert not item["archived"] and "INBOX" in message["labelIds"]
    assert not any(c["method"] == "POST" and "INBOX" in c["body"].get("removeLabelIds", []) for c in wire.calls)


def test_body_attachment_join_cannot_discard_content_without_hold(wire_env):
    from email_steward.extraction import Extraction
    wire, service, access, worker, delivery = wire_env
    service.enable_pack(access, "starter-info", {"mailbox_id": None})
    wire.add("m1", "t", "x" * 31999)
    provider = service.provider(service.store.account("gmail-1"))
    fetch = provider.fetch
    def attachments(ident):
        message = fetch(ident)
        message.attachments = [Attachment("synthetic.txt", "", 1, lambda: b"x")]
        return message
    provider.fetch = attachments
    service.provider_factory = lambda _: provider
    worker.extractor = lambda *args, **kwargs: Extraction("ok", "?")
    worker.tick(1100)
    item = service.store.item(service.items(access)[0]["reference"])
    assert item["attachment_status"] == "unreadable" and not item["archived"]


def cron_env(wire_env, monkeypatch):
    from email_steward.cron_delivery import install_schedule
    from test_cron_delivery import CronContext
    wire, service, access, worker, delivery = wire_env
    service.settings = replace(service.settings, destination="67890")
    service.current_settings()
    ctx = CronContext(service.settings.home)
    monkeypatch.setattr("email_steward.cron_delivery.prepare_tools", lambda: None)
    binding = install_schedule(ctx, service)
    for number in range(1, 6):
        service.store.outbox(str(number), 1, "Synthetic summary " + str(number) + " " + "x" * 600)
    return service, ctx, binding


def test_current_private_grant_is_checked_before_each_cron_handoff(wire_env, monkeypatch):
    from email_steward.cron_delivery import cron_tick
    service, ctx, binding = cron_env(wire_env, monkeypatch)
    first = cron_tick(ctx, service, binding["key"], service.settings.home, now=1100)
    assert "Synthetic summary 1" in first and "Synthetic summary 5" not in first
    before = service.store.rows("SELECT id,state FROM outbox")
    assert any(row["state"] == "handed_to_cron" for row in before)
    assert any(row["id"] == "5" and row["state"] == "pending" for row in before)
    service.settings = replace(service.settings, private_confirmed=False)
    with pytest.raises(Error):
        cron_tick(ctx, service, binding["key"], service.settings.home, now=1101)
    assert service.store.rows("SELECT id,state FROM outbox") == before
    assert not service.store.rows("SELECT id FROM outbox WHERE state IN ('sent','accepted')")


@pytest.mark.parametrize("change", ["quiet", "destination"])
def test_each_handoff_uses_current_quiet_and_destination_policy(wire_env, monkeypatch, change):
    from email_steward.cron_delivery import cron_tick, install_schedule
    service, ctx, binding = cron_env(wire_env, monkeypatch)
    first = cron_tick(ctx, service, binding["key"], service.settings.home, now=1100)
    assert "Synthetic summary 5" not in first
    if change == "quiet":
        service.settings = replace(service.settings, quiet_start="00:00", quiet_end="01:00")
        assert cron_tick(ctx, service, binding["key"], service.settings.home, now=1101) == ""
        assert service.store.rows("SELECT state FROM outbox WHERE id='5'") == [{"state": "pending"}]
    else:
        service.settings = replace(service.settings, destination="99999")
        with pytest.raises(Error):
            cron_tick(ctx, service, binding["key"], service.settings.home, now=1101)
        fresh = install_schedule(ctx, service, replace_existing=True)
        assert cron_tick(ctx, service, fresh["key"], service.settings.home, now=1102) == ""
        assert service.store.rows("SELECT state FROM outbox WHERE id='5'") == [{"state": "blocked"}]
    assert not service.store.rows("SELECT id FROM outbox WHERE state IN ('sent','accepted')")


@pytest.mark.parametrize("matched,consented", [(True, False), (True, True), (False, False)])
def test_brief_conveys_body_only_request_and_explicit_deadline_without_model(wire_env, matched, consented):
    wire, service, access, worker, delivery = wire_env
    if matched:
        service.enable_pack(access, "starter-action", {"mailbox_id": None})
    if consented:
        service.consent(access, CONSENT)
    wire.add("m1", "t", "Please approve the contract renewal by Friday at 17:00.", "Quick question")
    worker.tick(1100)
    worker.brief(1110, key="concrete-brief")
    item = service.store.item(service.items(access)[0]["reference"])
    text = "\n".join(r["text"] for r in service.store.rows("SELECT text FROM outbox WHERE category='brief'"))
    assert item["classification"] == "needs_action"
    assert "contract renewal" in text.casefold() and "Friday" in text and "17:00" in text
    assert item["deadline"] and "Friday" in item["deadline"] and "17:00" in item["deadline"]
    assert service.model.calls == []
    assert len(item["summary"]) <= 500
