"""Actual public Hermes LLM recovery; only physical client callbacks are synthetic.

Retains the original review's proven host route boundary. It never replaces
PluginContext/PluginLlm/call_llm/resolution/recovery or performs real inference.
"""
from dataclasses import replace
import inspect
import json
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

import pytest

SOURCE = Path(os.environ.get("ES_REPAIR_SOURCE", Path(__file__).resolve().parents[1]))
UPSTREAM = Path(os.environ.get("HERMES_UPSTREAM", Path(__file__).resolve().parents[2]))
sys.path[:0] = [str(SOURCE), str(UPSTREAM)]
from email_steward.judgement import HermesModel, CONSENT, DISCLOSURE
from email_steward.errors import Error
from email_steward.security import Settings, Access
from email_steward.store import Store
from email_steward.service import Steward
from email_steward.worker import Worker
from email_steward.synthetic import SyntheticGmail, SyntheticDelivery

SAMPLE = {"sender": "fixture@example.test", "subject": "Synthetic ambiguous message",
          "body": "Synthetic confidential email content marker alpha"}
DECISION = dict(classification="needs_review", archive=False, urgent=False,
                summary="Synthetic configured assessment", reason="Synthetic uncertainty", deadline=None)


def test_actual_adapter_grounded_quote_updates_existing_context(actual_host, monkeypatch):
    host = actual_host
    host.primary_failure = False
    host.provider.add("old", thread="t", received=1000, body="Please approve disputed renewal by Friday at 17:00.")
    host.worker.tick(1100)
    host.service.consent(host.access, "model-routing-v2")
    for key, value in {"classification":"needs_action", "summary":"Reconsider allocation", "reason":"New allocation issue", "context_evidence":"allocation changed materially"}.items():
        monkeypatch.setitem(DECISION, key, value)
    host.provider.add("new", thread="t", received=1002, body="The allocation changed materially.")
    host.worker.tick(1200)
    item = host.service.store.items()[0]
    assert item["latest_message"] == "new" and item["context_source"] == "model_quote"
    assert item["model_routing"]["reported_model"] == "primary-fixture-model"
    assert [x["route"] for x in host.physical] == ["primary"]


@pytest.fixture
def actual_host(tmp_path, monkeypatch, request):
    from agent import auxiliary_client as ac
    from hermes_cli.plugins import PluginContext, PluginManifest, PluginManager
    from hermes_cli import config
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_RUNTIME_DIR", str(tmp_path / "runtime"))
    state = SimpleNamespace(physical=[], clients=[], network=[], primary_failure=True, backup_failure=False)
    def deny(*args, **kwargs):
        state.network.append("FORBIDDEN")
        raise AssertionError("No real socket/DNS/inference is authorised")
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket, "create_connection", deny)

    def configure(*, backup=True, same_model=False):
        data = {"model": {"provider": "custom", "default": "primary-fixture-model",
            "base_url": "https://primary.invalid/v1", "api_key": "no-key-required"},
            "auxiliary": {"transient_retries": 0}, "plugins": {"enabled": [], "isolation": "in_process"}}
        if backup:
            data["fallback_providers"] = [{"provider": "custom", "model": "primary-fixture-model" if same_model else "alternate-fixture-model",
                "base_url": "https://alternate.invalid/v1", "api_key": "no-key-required"}]
        (tmp_path / "config.yaml").write_text(json.dumps(data))
        config._LOAD_CONFIG_CACHE.clear()
        config._RAW_CONFIG_CACHE.clear()
        ac._client_cache.clear()
        ac._reset_aux_unhealthy_cache()

    def client_factory(*, api_key, base_url, **ignored):
        assert api_key == "no-key-required"
        assert base_url in {"https://primary.invalid/v1", "https://alternate.invalid/v1"}
        state.clients.append(base_url)
        def create(**kwargs):
            route = "primary" if base_url == "https://primary.invalid/v1" else "alternate"
            state.physical.append(dict(route=route, model=kwargs["model"], tools=bool(kwargs.get("tools")),
                synthetic_content=SAMPLE["body"] in json.dumps(kwargs["messages"])))
            if (route == "primary" and state.primary_failure) or (route == "alternate" and state.backup_failure):
                raise ConnectionError("synthetic connection refused")
            return SimpleNamespace(model=kwargs["model"], choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps(DECISION), tool_calls=None), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30))
        return SimpleNamespace(base_url=base_url, api_key=api_key, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(ac, "_create_openai_client", client_factory)
    configure()
    manager = PluginManager()
    manager._discovered = True
    ctx = PluginContext(PluginManifest(name="email-steward", key="email-steward", source="synthetic-test"), manager)
    assert Path(inspect.getfile(type(ctx.llm))).resolve() == UPSTREAM.resolve() / "agent/plugin_llm.py"
    assert Path(inspect.getfile(HermesModel)).resolve() == SOURCE.resolve() / "email_steward/judgement.py"
    state.model, state.configure, state.ctx = HermesModel(ctx), configure, ctx
    settings = Settings(home=tmp_path, profile="synthetic-routing", owner="owner", destination="private",
                        private_confirmed=True, timezone="UTC")
    provider = SyntheticGmail()
    service = Steward(Store(tmp_path / "state"), settings, lambda _: provider, state.model)
    access = Access(settings.home, settings.owner, "synthetic-owner")
    service.connect(access, "gmail-1", provider.address, "Synthetic")
    state.service, state.access, state.provider = service, access, provider
    state.worker = Worker(service, SyntheticDelivery())
    try:
        yield state
    finally:
        ac._client_cache.clear()
        config._LOAD_CONFIG_CACHE.clear()
        config._RAW_CONFIG_CACHE.clear()
        assert state.network == []
        assert all(not c["tools"] for c in state.physical)
        if os.environ.get("ES_MODEL_EVIDENCE"):
            import re
            output = Path(os.environ["ES_MODEL_EVIDENCE"])
            output.mkdir(parents=True, exist_ok=True, mode=0o700)
            name = re.sub(r"[^A-Za-z0-9_-]", "_", request.node.name)
            (output / (name + ".json")).write_text(json.dumps({"case": request.node.name,
                "adapter_source": str(SOURCE / "email_steward/judgement.py"),
                "actual_sdk": str(UPSTREAM / "agent/plugin_llm.py"),
                "actual_recovery": str(UPSTREAM / "agent/auxiliary_client.py"),
                "physical_callbacks": state.physical, "network_attempts": len(state.network),
                "real_provider_calls": 0}, indent=2) + "\n")


def test_primary_success_exposes_bounded_public_metadata(actual_host):
    host = actual_host
    host.primary_failure = False
    result = host.model.judge(SAMPLE)
    assert [c["route"] for c in host.physical] == ["primary"]
    assert result.get("model_routing", {}).get("reported_model") == "primary-fixture-model"
    assert result["model_routing"]["fallback_status"] == "not exposed"


@pytest.mark.parametrize("same_model", [False, True])
def test_renewed_consent_host_fallback_is_reported_without_endpoint_claims(actual_host, same_model):
    host = actual_host
    host.configure(same_model=same_model)
    host.service.consent(host.access, "model-routing-v2")
    host.provider.add("m", subject=SAMPLE["subject"], body=SAMPLE["body"])
    host.worker.tick(1100)
    assert [c["route"] for c in host.physical] == ["primary", "alternate"]
    assert all(c["synthetic_content"] for c in host.physical)
    item = host.service.store.items()[0]
    reported = "primary-fixture-model" if same_model else "alternate-fixture-model"
    assert item["model_routing"]["reported_model"] == reported
    assert item["model_routing"]["reported_provider"] == "custom"
    assert item["model_routing"]["fallback_status"] == "not exposed"
    assert reported in host.service.inspect(host.access, item["reference"])["item"]["reason"]
    assert "endpoint/attempt history unavailable" in item["reason"]
    assert "https://alternate.invalid" not in str(item)
    assert "configured model/provider fallbacks" in DISCLOSURE


def test_no_configured_fallback_primary_failure_is_pending_and_honest(actual_host):
    host = actual_host
    host.configure(backup=False)
    host.service.consent(host.access, "model-routing-v2")
    host.provider.add("m", body=SAMPLE["body"])
    host.worker.tick(1100)
    assert [c["route"] for c in host.physical] == ["primary"]
    assert host.service.store.rows("SELECT status FROM jobs")[0]["status"] == "pending"
    assert host.worker.health(1100)
    assert host.service.items(host.access) == []


def test_exhausted_routes_error_does_not_deny_actual_fallback_attempts(actual_host):
    host = actual_host
    host.backup_failure = True
    with pytest.raises(Error) as caught:
        host.model.judge(SAMPLE)
    assert [c["route"] for c in host.physical] == ["primary", "alternate"]
    message = caught.value.body["error"]["message"]
    assert "No fallback was used" not in message
    assert "fallback attempts may have occurred" in message


@pytest.mark.parametrize("consent", ["model-content-v1", "", "off"])
def test_old_missing_or_revoked_consent_never_calls_actual_host_model(actual_host, consent):
    host = actual_host
    host.primary_failure = False
    host.service.store.set_meta("model_consent", consent)
    host.provider.add("m", body=SAMPLE["body"])
    host.worker.tick(1100)
    assert host.physical == [] and host.clients == []
    assert host.service.items(host.access)[0]["classification"] == "needs_review"


def test_rule_match_remains_model_free_even_with_renewed_consent(actual_host):
    host = actual_host
    host.service.consent(host.access, "model-routing-v2")
    host.service.enable_pack(host.access, "starter-action", {"mailbox_id": None})
    host.provider.add("m", body="Please approve the renewal by Friday at 17:00.")
    host.worker.tick(1100)
    assert host.physical == [] and host.clients == []
    assert host.service.items(host.access)[0]["classification"] == "needs_action"
