"""ES-002 production grant/outbox boundaries; all accounts and final transports synthetic."""
from dataclasses import replace
import json
import sys
import os
from pathlib import Path
from types import SimpleNamespace
import weakref

import pytest

sys.path.insert(0, os.environ.get("HERMES_UPSTREAM", str(Path(__file__).resolve().parents[2])))

from email_steward.security import Settings, Access
from email_steward.service import Steward
from email_steward.store import Store
from email_steward.synthetic import SyntheticDelivery
from email_steward.worker import Worker
from email_steward.errors import Error


def configured(home, **changes):
    return Settings(home=home, profile="synthetic", owner="12345", destination="67890",
        private_confirmed=True, timezone="UTC", platform="discord", grant_revision=1,
        account="synthetic:discord", transport_profile="synthetic", transport_home=str(home.resolve()), **changes)


def compose(home):
    current = [configured(home)]
    s = Steward(Store(home / "data"), current[0], settings_reader=lambda: current[0])
    s.current_settings()
    return s, current


def native_source(settings):
    from gateway.config import Platform
    from gateway.session import SessionSource
    from gateway.session_identity import RoutingIdentity
    adapter = SimpleNamespace(platform=Platform(settings.platform), _owner_profile=settings.profile)
    # weakref-capable synthetic final receiving transport; actual identity/source classes.
    class Transport: pass
    transport = Transport()
    transport.__dict__.update(adapter.__dict__)
    transport.config = SimpleNamespace(extra={})
    source = SessionSource(platform=transport.platform, chat_id=settings.destination, user_id=settings.owner,
        chat_type=settings.destination_type, thread_id=settings.thread, scope_id=settings.scope or None,
        parent_chat_id=settings.parent or None, profile=settings.profile)
    source._identity = RoutingIdentity(settings.profile, settings.profile, settings.home, settings.home,
        transport=weakref.ref(transport))
    return source, transport


def test_inventory_is_closed_and_all_internal_routes_deny(tmp_path):
    from email_steward.gateways import CAPABILITIES, validate
    assert len(CAPABILITIES) == 33
    for platform, cap in {**CAPABILITIES, "external-unknown": SimpleNamespace(mode="unknown")}.items():
        if cap.mode not in {"interactive", "notification"}:
            with pytest.raises(Error):
                validate(replace(configured(tmp_path), platform=platform))


def test_actual_offwire_identity_required_and_namespace_collisions_denied(tmp_path):
    from email_steward.gateways import native_access
    settings = configured(tmp_path)
    source, transport = native_source(settings)
    assert native_access(settings, source).surface == "discord"
    for change in ({"platform": "slack"}, {"scope_id": "other"}, {"chat_id": "other"},
                   {"user_id": None}, {"is_bot": True}, {"thread_id": "foreign"},
                   {"parent_chat_id": "foreign"}, {"profile_route_rejected": True},
                   {"delivered_via_upstream_relay": True}):
        from gateway.session_identity import replace_source
        with pytest.raises(Error): native_access(settings, replace_source(source, **change))
    clone = type(source).from_dict(source.to_dict())
    with pytest.raises(Error): native_access(settings, clone)
    source._identity = replace(source._identity, runtime_home=tmp_path / "other")
    with pytest.raises(Error): native_access(settings, source)


@pytest.mark.parametrize("field,value", [("platform", "telegram"), ("owner", "other"),
    ("destination", "99999"), ("destination_type", "group"), ("thread", "555"),
    ("scope", "other"), ("parent", "other")])
def test_changed_grant_blocks_old_rows_without_reroute(tmp_path, field, value):
    s, current = compose(tmp_path)
    s.store.outbox("old", 1, "Synthetic private notification")
    current[0] = replace(current[0], **{field: value, "grant_revision": 2,
        **({"account": "synthetic:telegram"} if field == "platform" else {}),
        **({"scope": "synthetic-guild"} if field == "destination_type" else {})})
    d = SyntheticDelivery()
    Worker(s, d).flush(2)
    assert d.sent == []
    row = s.store.rows("SELECT * FROM outbox")[0]
    assert row["state"] == "blocked" and row["attempts"] == 0


def test_away_and_back_does_not_revive_queued_authority(tmp_path):
    s, current = compose(tmp_path)
    s.store.outbox("old", 1, "Synthetic private notification")
    original = current[0]
    current[0] = replace(original, destination="99999", grant_revision=2)
    s.current_settings()
    current[0] = replace(original, grant_revision=3)
    s.current_settings()
    d = SyntheticDelivery()
    Worker(s, d).flush(2)
    assert not d.sent and s.store.rows("SELECT state FROM outbox")[0]["state"] == "blocked"


def test_durable_chunks_bound_bytes_and_stop_on_revocation(tmp_path):
    s, current = compose(tmp_path)
    text = "ax1 " + "🙂" * 1200 + " END-OF-CONTENT"
    s.store.outbox("long", 1, text)
    rows = s.store.rows("SELECT * FROM outbox ORDER BY rowid")
    assert len(rows) > 1 and all(len(r["text"].encode()) <= 900 for r in rows)
    assert "END-OF-CONTENT" in rows[-1]["text"]
    class Revoking:
        calls = []
        def send(self, settings, text, ident):
            self.calls.append(ident)
            current[0] = replace(current[0], private_confirmed=False)
            return "accepted"
    d = Revoking()
    Worker(s, d).flush(2)
    assert len(d.calls) == 1
    assert s.store.rows("SELECT state FROM outbox ORDER BY rowid")[0]["state"] == "accepted"
    assert all(r["attempts"] == 0 for r in s.store.rows("SELECT attempts FROM outbox WHERE state!='accepted'"))


def test_unbound_legacy_rows_are_quarantined_sending_retains_uncertainty(tmp_path):
    store = Store(tmp_path / "data")
    store.execute("INSERT INTO outbox(id,created,text,category,state) VALUES('old',1,'synthetic','brief','pending')")
    store.execute("INSERT INTO outbox(id,created,text,category,state) VALUES('inflight',1,'synthetic','brief','sending')")
    s = Steward(store, configured(tmp_path))
    d = SyntheticDelivery()
    Worker(s, d).flush(2)
    assert not d.sent
    assert {r["id"]: r["state"] for r in store.rows("SELECT id,state FROM outbox")} == {"old": "blocked", "inflight": "uncertain"}


@pytest.mark.parametrize('failure', ['privacy', 'reader', 'home'])
def test_observed_revocation_cannot_revive_old_grant(tmp_path, failure):
    s, current = compose(tmp_path)
    s.store.outbox('old', 1, 'Synthetic')
    old = current[0]
    if failure == 'reader':
        s.settings_reader = lambda: (_ for _ in ()).throw(ValueError('synthetic config error'))
    else:
        current[0] = replace(old, **({'private_confirmed':False} if failure == 'privacy' else {'home':tmp_path/'other'}))
    with pytest.raises(Exception): s.current_settings()
    current[0] = old
    s.settings_reader = lambda: current[0]
    s.current_settings()
    d = SyntheticDelivery()
    Worker(s,d).flush(2)
    assert not d.sent
    assert s.store.rows('SELECT state,attempts FROM outbox')[0] == {'state':'blocked','attempts':0}
    assert s.store.meta('gateway_grant:1')['binding']['destination'] == old.destination


def test_native_host_config_aba_invalidates_even_unrelated_edits(tmp_path):
    import yaml
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from email_steward.runtime import settings_from_host
    token = set_hermes_home_override(tmp_path)
    path = tmp_path / 'config.yaml'
    config = {'timezone':'UTC','plugins':{'entries':{'email-steward':{'settings':{
        'owner':'12345','destination':'67890','private_confirmed':True}}}}}
    try:
        path.write_text(yaml.safe_dump(config))
        original = settings_from_host()
        s = Steward(Store(tmp_path/'data'), original, settings_reader=settings_from_host)
        s.current_settings(); s.store.outbox('old', 1, 'Synthetic')
        config['unrelated_synthetic_setting'] = 'changed'
        path.write_text(yaml.safe_dump(config))
        del config['unrelated_synthetic_setting']
        path.write_text(yaml.safe_dump(config))
        assert settings_from_host().host_config_version != original.host_config_version
        d = SyntheticDelivery(); Worker(s,d).flush(2)
        assert not d.sent and s.store.rows('SELECT state FROM outbox')[0]['state'] == 'blocked'
    finally:
        reset_hermes_home_override(token)


def test_receipts_partial_and_payload_tail_are_not_silently_complete():
    from email_steward.outbound import receipt, chunks
    for value in ({'success':True}, {'success':True,'message_id':'ok'},
                  {'success':True,'message_id':'123','partial':True},
                  {'success':True,'message_id':'123','platform':'foreign'},
                  {'success':True,'message_id':'123','chat_id':'foreign'},
                  {'success':True,'skipped':True}, {'success':False,'message_id':'123'}):
        assert receipt(value,'discord','67890') != 'accepted'
    link = 'https://mail.google.com/mail/u/alex@example.test/#all/abc123'
    text = 'ax123 D0123456789ab '+link+' '+'界'*2000+' END-SENTINEL'
    parts = chunks(text, (link,))
    assert all(len(p.encode()) <=900 for p in parts)
    assert sum(link in p for p in parts) == 1 and parts[-1].endswith('END-SENTINEL')
    assert all('ax123' in p for p in parts)
