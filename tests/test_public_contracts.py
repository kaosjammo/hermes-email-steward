"""Public command and dashboard contracts, with synthetic owner state only."""
from dataclasses import replace
import time
from types import SimpleNamespace

import pytest

from email_steward.chat import Chat
from email_steward.errors import Error
from email_steward.security import desktop_access
from test_backend import env
from test_native import upstream


def test_native_command_returns_content_to_host_without_background_send(env):
    service, worker, _, delivery, _, source = env
    result = Chat(lambda: service, lambda _: worker).command("rules", source=source)
    assert "Email rules" in result and "No rules yet" in result
    assert delivery.sent == []
    assert service.store.rows("SELECT * FROM outbox WHERE category='command'") == []


def test_dashboard_session_cannot_authorise_a_different_runtime_home(env, upstream, monkeypatch):
    from hermes_cli.dashboard_auth.base import Session
    import hermes_constants
    service = env[0]
    settings = replace(service.settings, desktop_subject="", desktop_session_user="owner",
                       desktop_session_provider="fixture", desktop_session_issuer="fixture-issuer")
    session = Session("owner", "owner@example.test", "Owner", "", "fixture",
                      int(time.time()) + 60, "", "", issuer="fixture-issuer")
    request = SimpleNamespace(state=SimpleNamespace(session=session))
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: settings.home)
    assert desktop_access(settings, request).surface == "desktop-session"
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: settings.home / "foreign")
    with pytest.raises(Error):
        desktop_access(settings, request)


def test_context_threads_keep_their_own_profile_and_plugin_settings(tmp_path, upstream):
    from agent.memory_provider import spawn_context_thread
    from hermes_constants import get_hermes_home, set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.plugins import PluginContext, PluginManager
    from hermes_cli.plugins_manifest import parse_manifest_file
    from email_steward.plugin import bound_home
    from pathlib import Path
    import threading
    import yaml

    root = Path(__file__).resolve().parents[1]
    manifest = parse_manifest_file(root / "plugin.yaml", root, "project", "")
    barrier = threading.Barrier(3)
    observed, failures, threads = [], [], []
    for name, owner in (("one", "111"), ("two", "222")):
        home = tmp_path / name
        home.mkdir()
        (home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"entries": {
            "email-steward": {"settings": {"owner": owner}}}}}))
        token = set_hermes_home_override(str(home))
        try:
            ctx = PluginContext(manifest, PluginManager(scope_key=str(home)))
            def run(home=home, owner=owner, ctx=ctx):
                try:
                    barrier.wait(timeout=10)
                    with bound_home(home):
                        observed.append((get_hermes_home().resolve(), ctx.get_config("owner")))
                    with pytest.raises(Error):
                        with bound_home(home / "foreign"):
                            pass
                except BaseException as exc:
                    failures.append(exc)
            thread = spawn_context_thread(run, name="steward-profile-test-" + name)
            thread.start()
            threads.append(thread)
        finally:
            reset_hermes_home_override(token)
    barrier.wait(timeout=10)
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert not failures, failures
    assert set(observed) == {(tmp_path / "one", "111"), (tmp_path / "two", "222")}


@pytest.mark.parametrize("variant,expected", [
    ("owner", 200), ("unauthenticated", 401), ("unknown-token", 401),
    ("wrong-owner", 401), ("wrong-issuer", 401), ("expired", 401),
    ("wrong-home", 401), ("boolean-only", 401)])
def test_actual_dashboard_session_gate_and_plugin_owner_route(env, upstream, monkeypatch, variant, expected):
    import asyncio
    import httpx
    from fastapi import FastAPI
    from hermes_cli.dashboard_auth import DashboardAuthProvider, Session, register_provider
    from hermes_cli.dashboard_auth.registry import restore_registration
    from hermes_cli.dashboard_auth.middleware import gated_auth_middleware
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from email_steward.api import create_router

    service = env[0]
    service.settings = replace(service.settings, desktop_subject="", desktop_session_user="owner",
        desktop_session_provider="steward-synthetic-gate", desktop_session_issuer="synthetic-issuer")
    class Provider(DashboardAuthProvider):
        name, display_name, interactive_login = "steward-synthetic-gate", "Synthetic", False
        def start_login(self, **kw): raise AssertionError("No external login")
        def complete_login(self, **kw): raise AssertionError("No external login")
        def refresh_session(self, **kw): raise AssertionError("No refresh")
        def revoke_session(self, **kw): raise AssertionError("No revoke")
        def verify_session(self, *, access_token):
            if access_token != "synthetic-owner-token": return None
            return Session("foreign" if variant == "wrong-owner" else "owner", "owner@example.test",
                "Owner", "", self.name, int(time.time()) + (-10 if variant == "expired" else 60),
                "", "", issuer="foreign" if variant == "wrong-issuer" else "synthetic-issuer")
    provider = Provider()
    token = set_hermes_home_override(service.settings.home / "foreign" if variant == "wrong-home" else service.settings.home)
    scope = str(service.settings.home / "foreign" if variant == "wrong-home" else service.settings.home)
    register_provider(provider, scope=scope)
    app = FastAPI()
    app.state.auth_required = True
    app.middleware("http")(gated_auth_middleware)
    if variant == "boolean-only":
        @app.middleware("http")
        async def bool_fixture(request, call_next):
            request.state.token_authenticated = True
            return await call_next(request)
    app.include_router(create_router(lambda: service), prefix="/api/plugins/email-steward")
    headers = {} if variant in {"unauthenticated", "boolean-only"} else {
        "Authorization": "Bearer " + ("unknown-token" if variant == "unknown-token" else "synthetic-owner-token")}
    async def query():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://synthetic") as client:
            from test_backend import rule
            read = await client.get("/api/plugins/email-steward/rules", headers=headers)
            write = await client.post("/api/plugins/email-steward/rules", headers=headers, json=rule())
            return read, write
    try:
        response, mutation = asyncio.run(query())
        assert response.status_code == expected, response.text
        assert mutation.status_code == (201 if expected == 200 else expected), mutation.text
        assert len(service.rule_store.list()) == (1 if expected == 200 else 0)
        assert not service.store.rows("SELECT id FROM outbox")
    finally:
        assert restore_registration(provider.name, provider, None, scope=scope)
        reset_hermes_home_override(token)
