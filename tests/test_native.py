"""Actual read-only Hermes SDK context and model contract checks."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import time

import pytest

from email_steward.chat import Chat
from email_steward.judgement import HermesModel
from email_steward.security import desktop_access
from test_backend import env


@pytest.fixture
def upstream():
    root = Path(os.environ.get("HERMES_UPSTREAM", Path(__file__).resolve().parents[2]))
    if not (root / "hermes_constants.py").is_file():
        pytest.skip("Hermes upstream SDK not present; run scripts/validate_hermes.py with --upstream")
    sys.path.insert(0, str(root))
    try:
        yield root
    finally:
        sys.path.remove(str(root))


def test_real_session_context_owner_derived_never_tool_args(env, upstream):
    from gateway.session_context import set_session_vars, clear_session_vars
    s, w, p, d, a, source = env
    chat = Chat(lambda: s, lambda _: w)
    assert "error" in json.loads(chat.tool({"command": "list"}))
    tokens = set_session_vars(platform="discord", user_id="owner", chat_id="private", chat_type="dm", profile="synthetic", session_key="synthetic-session")
    try:
        assert json.loads(chat.tool({"command": "list"}))["error"]["code"] == "forbidden"  # ES-002: reduced bridge cannot prove off-wire principal
        assert chat.run("list", source=source) == {"items": []}
        assert "error" in json.loads(chat.tool({"command": "list", "owner": "owner"}))
        set_session_vars(platform="discord", user_id="intruder", chat_id="private", chat_type="dm", profile="synthetic", session_key="synthetic-session")
        assert "error" in json.loads(chat.tool({"command": "list"}))
    finally:
        clear_session_vars(tokens)


def test_verified_upstream_session_exact_identity_expiry_and_type(env, upstream):
    from hermes_cli.dashboard_auth.base import Session
    from dataclasses import replace
    s = env[0]
    settings = replace(s.settings, desktop_subject="", desktop_session_user="u", desktop_session_provider="synthetic", desktop_session_issuer="fixture")
    session = Session("u", "synthetic@example.test", "Synthetic", "", "synthetic", int(time.time()) + 60, "", "", issuer="fixture")
    req = SimpleNamespace(state=SimpleNamespace(session=session))
    assert desktop_access(settings, req).surface == "desktop-session"
    for foreign in (replace(session, user_id="foreign"), replace(session, issuer="other"), replace(session, expires_at=0), SimpleNamespace(**session.__dict__)):
        with pytest.raises(Exception):
            desktop_access(settings, SimpleNamespace(state=SimpleNamespace(session=foreign)))


def test_configured_model_adapter_no_override_no_tools_and_bounded_redacted_input():
    calls = []
    def complete_structured(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(parsed={"classification": "needs_review", "archive": False, "urgent": False, "summary": "Synthetic", "reason": "Synthetic"})
    model = HermesModel(SimpleNamespace(llm=SimpleNamespace(complete_structured=complete_structured)))
    assert model.judge({"sender": "a@example.test", "subject": "OTP 123456", "body": "X" * 60000})["classification"] == "needs_review"
    call = calls[0]
    assert not {"provider", "model", "agent_id", "profile", "tools"} & set(call)
    assert "123456" not in str(call) and len(call["input"][0]["text"]) < 34000
    assert call["timeout"] == 45 and call["max_tokens"] == 700


def test_model_tool_preserves_restricted_channel_thread_boundary(env, upstream):
    from dataclasses import replace
    from gateway.session_context import set_session_vars, clear_session_vars
    service, worker, *_ = env
    service.settings = replace(service.settings, destination_type="channel")
    chat = Chat(lambda: service, lambda _: worker)
    tokens = set_session_vars(platform="discord", user_id="owner", chat_id="private",
        chat_type="channel", thread_id="unapproved-thread", profile="synthetic",
        session_key="synthetic-thread-session")
    try:
        result = json.loads(chat.tool({"command": "list"}))
        assert result.get("error", {}).get("code") == "forbidden"
    finally:
        clear_session_vars(tokens)


def test_native_delivery_blocks_unattested_host_route_before_send(env, upstream, monkeypatch):
    from email_steward.plugin import HermesDelivery
    from tools import send_message_tool as outbound
    captured = []
    monkeypatch.setattr(outbound, "_handle_send", lambda args: captured.append(args))
    assert HermesDelivery(None, env[0].store).send(env[0].settings, "Synthetic private alert", "synthetic-id") == "blocked"
    assert captured == []
