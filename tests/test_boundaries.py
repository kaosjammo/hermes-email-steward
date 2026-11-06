"""Malformed inputs and native ownership grants must fail closed through actual routes."""
from dataclasses import replace
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from email_steward.errors import Error
from email_steward.security import Settings, desktop_access
from test_backend import env, rule, client_for


@pytest.mark.parametrize("patch", [
    {"actions": {"classification": [], "archive": False}},
    {"mailbox_id": []},
    {"conditions": [{"field": [], "operator": "contains", "value": "x"}]},
    {"conditions": [{"field": "body", "operator": [], "value": "x"}]},
    {"conditions": [None]},
    {"enabled": "false"},
    {"priority": True},
])
def test_malformed_rules_are_validation_errors(env, patch):
    api = client_for(env[0])
    result = api.post("/api/plugins/email-steward/rules", json={**rule(), **patch})
    assert result.status_code == 422, result.text
    assert result.json()["error"]["code"] == "validation_error"


def test_config_never_accepts_truthy_strings_as_private_confirmation(env):
    with pytest.raises(Error):
        replace(env[0].settings, private_confirmed="false").require_private()


def test_revoked_private_grant_refuses_delivery_and_backend(env):
    s, w, p, d, a, _ = env
    s.settings = replace(s.settings, private_confirmed=False)
    assert client_for(s).get("/api/plugins/email-steward/rules").status_code == 403
    with pytest.raises(Error):
        w.tick(now=1000)
    assert not d.sent


@pytest.mark.parametrize("patch", [
    {"profile_id": "/synthetic/foreign-profile"}, {"subject": "another-desktop"},
    {"purpose": "native-profile-create"}, {"capabilities": {"profiles:create"}}, {"scope": "host"},
])
def test_native_grant_exact_profile_subject_and_capabilities(env, patch):
    settings = env[0].settings
    principal = dict(profile_id=str(settings.home), subject=settings.desktop_subject,
                     purpose="native-http", scope="profile", capabilities={"http:owner"})
    request = SimpleNamespace(state=SimpleNamespace(native_http_principal={**principal, **patch}))
    with pytest.raises(Error):
        desktop_access(settings, request)


def test_important_contact_display_name_is_assessed_contextually(env):
    s, w, p, d, a, _ = env
    s.settings = replace(s.settings, important_contacts=("synthetic@example.test",))
    original = p.fetch
    def fetch(ident):
        message = original(ident)
        message.sender = "Important Person <synthetic@example.test>"
        return message
    p.fetch = fetch
    p.add("m", body="Please approve this", received=995)
    w.tick(now=1000)
    assert any(x[1].startswith("urgent:") for x in d.sent)


def test_archive_hold_for_oversized_attachment_is_not_downgraded_by_later_ok(env):
    s, w, p, d, a, _ = env
    from email_steward.gmail import Attachment
    from scripts.extraction_fixtures import office
    raw = office("docx", "Synthetic informational text")
    s.save_rule(a, rule())
    p.add("m", subject="Invoice", attachments=[Attachment("big.pdf", "", 17 * 1024 * 1024, lambda: b""),
          Attachment("small.docx", "", len(raw), lambda: raw)])
    w.tick(now=1000)
    assert s.items(a)[0]["attachment_status"] == "unreadable"
    assert not s.items(a)[0]["archived"]


def test_changing_profile_owner_cannot_inherit_existing_mail_metadata(env):
    s, w, p, d, a, _ = env
    s.settings = replace(s.settings, owner="new-owner")
    with pytest.raises(Error, match="owner"):
        w.tick(now=1000)
    assert client_for(s).get("/api/plugins/email-steward/items").status_code == 403
