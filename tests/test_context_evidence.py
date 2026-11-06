"""Substance, independent activity warnings and on-request targets, real wire/service."""
import base64
from dataclasses import replace

import pytest
from test_obligation_context import env, REQUEST
from email_steward.judgement import CONSENT


def brief_now(s, w, key):
    digest = w.brief(1300, key=key)
    return "\n".join(x["text"] for x in s.store.rows("SELECT text FROM outbox WHERE id LIKE ?", ("brief:" + digest + ":%",)))


@pytest.mark.parametrize("subject,body,attachment", [
    ("Receipt", "Harmless receipt", True),
    ("Re: Please approve renewal", "Harmless receipt", False),
    ("Re: Renewal", "Thanks for the update.", False),
    ("Re: Review required", "Thank you for your reply and review.", False),
    ("Re: Approval", "Acknowledged. Much appreciated.", False),
    ("Re: Renewal", "No problem, thanks for clarifying the deadline.", False),
    ("Re: Renewal", "Noted the Friday deadline. Thanks for your review.", False),
])
def test_followup_category_cannot_erase_substance_or_hide_current_review(env, subject, body, attachment):
    wire, s, a, w, d, add, fresh = env
    add("request", REQUEST, 1000, "Question")
    w.tick(1100)
    before = s.store.item("ax1")
    add("followup", body, 1002, subject)
    if attachment:
        wire.boxes["A"]["messages"]["followup"]["payload"]["parts"] = [{
            "filename": "statement.unknown", "mimeType": "application/octet-stream",
            "body": {"data": base64.urlsafe_b64encode(b"inert unsupported synthetic document").decode(), "size": 36}}]
    s, w = fresh()
    w.tick(1200)
    item = s.store.item("ax1")
    for key in ("classification", "summary", "deadline", "reason", "urgent", "urgent_category", "latest_message", "received"):
        assert item[key] == before[key], key
    assert set(before["holds"]).issubset(item["holds"])
    assert item["activity_message"] == "followup"
    text = brief_now(s, w, "current-only")
    assert "disputed renewal" in text and "Friday" in text and "17:00" in text
    assert subject in text and "review" in text.casefold()
    assert "disputed renewal" in s.inspect(a, "ax1", text=True)["text"]
    note = s.inspect(a, "ax1")["activity_review"]
    assert note["message_id"] == "followup" and note["classification"] != "fyi"
    if attachment:
        assert item["attachment_status"] == "unsupported"
        assert note["attachment_status"] == "unsupported" and "unsupported" in text
        inspected = s.inspect(a, "ax1", attachments=True)
        assert inspected["extracts"][0]["status"] == "unsupported"
        add("ack", "Thanks for your reply.", 1003, "Re: Update")
        w.tick(1250)
        assert "unsupported" in brief_now(s, w, "warning-still-pending")
    assert all(x["status"] == "done" for x in s.store.rows("SELECT * FROM jobs"))
    assert all("Label_A" in m["labelIds"] and "UNREAD" in m["labelIds"] for m in wire.boxes["A"]["messages"].values())
    assert not any(c["method"] == "POST" and "INBOX" in (c["body"] or {}).get("removeLabelIds", []) for c in wire.calls)


@pytest.mark.parametrize("evidence", ["body", "body_after_ack", "body_with_comma", "attachment", "rule", "model"])
def test_new_grounded_content_updates_context_without_changing_routing_policy(env, evidence):
    from scripts.extraction_fixtures import office
    wire, s, a, w, d, add, fresh = env
    add("request", REQUEST, 1000, "Question")
    w.tick(1100)
    replacement = "Please approve replacement agreement by Monday at 17:00."
    body = replacement if evidence == "body" else ("Thanks for your review. " + replacement if evidence == "body_after_ack" else "The allocation changed materially.")
    if evidence == "body_with_comma":
        body = "Noted the prior Friday deadline. Please approve replacement agreement by Monday, 17:00."
    if evidence == "rule":
        s.save_rule(a, dict(name="Content rule", enabled=True, mailbox_id=None, priority=1000,
            conditions=[dict(field="body", operator="contains", value="allocation changed")],
            actions=dict(classification="needs_review", archive=False)))
    if evidence == "model":
        s.consent(a, CONSENT)
        def judge(sample):
            s.model.calls.append(sample)
            return dict(classification="needs_action", archive=False, urgent=False,
                summary="Reconsider the revised allocation.", reason="Consented synthetic judgement.",
                context_evidence="allocation changed materially", model_routing={"reported_provider":"fixture", "reported_model":"configured", "reported_task":"auto"})
        s.model.judge = judge
    add("new", body, 1002, "Notice")
    if evidence == "attachment":
        raw = office("docx", replacement)
        wire.boxes["A"]["messages"]["new"]["payload"]["parts"] = [{"filename":"decision.docx", "mimeType":"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "body":{"data":base64.urlsafe_b64encode(raw).decode(),"size":len(raw)}}]
    w.tick(1200)
    item = s.store.item("ax1")
    assert item["latest_message"] == "new" and item["classification"] in {"needs_action", "needs_review"}
    assert item["context_source"] in {"body", "rule_body", "model_quote"}
    if evidence in {"body", "body_after_ack", "body_with_comma", "attachment"}:
        assert "replacement agreement" in brief_now(s, w, "replacement") and "Monday" in item["deadline"] and "17:00" in item["deadline"]
    if evidence != "model":
        assert s.model.calls == []


def test_subject_only_rule_and_ungrounded_model_do_not_replace_live_attribution(env):
    wire, s, a, w, d, add, fresh = env
    add("request", REQUEST, 1000, "Question")
    w.tick(1100)
    before = s.store.item("ax1")
    s.save_rule(a, dict(name="Subject rule", enabled=True, mailbox_id=None, priority=1000,
        conditions=[dict(field="subject", operator="contains", value="approval")],
        actions=dict(classification="needs_action", archive=False)))
    add("subject", "Thanks for the update.", 1002, "Re: Approval")
    w.tick(1200)
    assert s.store.item("ax1")["latest_message"] == "request"
    s.consent(a, CONSENT)
    s.model.judge = lambda sample: dict(classification="needs_review", archive=False, urgent=False,
        summary="Check acknowledgement", reason="Synthetic alternate assessment", context_evidence="invented not in message",
        model_routing={"reported_provider":"second-fixture", "reported_model":"configured", "reported_task":"auto"})
    add("model", "Acknowledged, much appreciated.", 1003, "Notice")
    w.tick(1250)
    item = s.store.item("ax1")
    assert item["latest_message"] == "request" and item["reason"] == before["reason"]
    assert item.get("model_routing") == before.get("model_routing")
    assert s.inspect(a, "ax1")["activity_review"]["model_routing"]["reported_provider"] == "second-fixture"


def test_rest_reference_preview_keeps_live_request_while_inspection_surfaces_review(env):
    from test_backend import client_for
    wire, s, a, w, d, add, fresh = env
    s.settings = replace(s.settings, desktop_subject="desktop:synthetic")
    add("request", REQUEST, 1000, "Question");w.tick(1100)
    add("ack", "Thanks for the update.", 1002, "Re: Please approve renewal")
    wire.boxes["A"]["messages"]["ack"]["payload"]["parts"] = [{"filename":"statement.unknown", "mimeType":"application/octet-stream", "body":{"data":base64.urlsafe_b64encode(b"inert unsupported text").decode(),"size":21}}]
    w.tick(1200)
    rule = dict(name="Live request", enabled=True, mailbox_id=None, priority=100,
        conditions=[dict(field="body",operator="contains",value="disputed renewal")],
        actions=dict(classification="needs_review",archive=False))
    response = client_for(s).post("/api/plugins/email-steward/rules/preview", json={"rule":rule,"reference":"ax1"})
    assert response.status_code == 200 and response.json()["matched"]
    assert "Attachment significance unresolved: unsupported" in response.json()["holds"]
    assert s.inspect(a,"ax1")["activity_review"]["message_id"] == "ack"


def test_new_model_reason_cannot_impersonate_legacy_owner_marker(env):
    wire, s, a, w, d, add, fresh = env
    s.consent(a, CONSENT)
    s.model.judge = lambda sample: dict(classification="needs_review", archive=False, urgent=False,
        summary="New model uncertainty", reason="Explicit owner correction.")
    add("model", "Novel synthetic content.", 1000, "Notice")
    w.tick(1100)
    w.tick(1200)
    assert "owner_queue" not in s.store.item("ax1")


def test_retained_attachment_request_and_current_unsupported_extract_are_both_inspectable(env):
    from scripts.extraction_fixtures import office
    wire, s, a, w, d, add, fresh = env
    raw = office("docx", REQUEST)
    add("request", "Attachment enclosed.", 1000, "Notice")
    wire.boxes["A"]["messages"]["request"]["payload"]["parts"] = [{"filename":"decision.docx", "mimeType":"application/octet-stream", "body":{"data":base64.urlsafe_b64encode(raw).decode(),"size":len(raw)}}]
    w.tick(1100)
    add("ack", "Thanks for the update.", 1002, "Receipt")
    wire.boxes["A"]["messages"]["ack"]["payload"]["parts"] = [{"filename":"statement.unknown", "mimeType":"application/octet-stream", "body":{"data":base64.urlsafe_b64encode(b"inert unsupported text").decode(),"size":21}}]
    w.tick(1200)
    extracts = s.inspect(a, "ax1", attachments=True)["extracts"]
    assert any(x["message_id"] == "request" and "disputed renewal" in x["text"] and x["status"] == "ok" for x in extracts)
    assert any(x["message_id"] == "ack" and x["status"] == "unsupported" for x in extracts)
    assert "Friday" in brief_now(s,w,"both-contexts")
