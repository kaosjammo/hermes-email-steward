"""Adopted independent runtime regressions; all providers and delivery are synthetic."""
import sys
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from test_backend import env
from test_cron_delivery import CronContext
from email_steward.cron_delivery import install_schedule, cron_tick, MAX_BATCH_BYTES
from email_steward.chat import Chat
from email_steward.worker import Worker
from email_steward.store import Store
from email_steward.service import Steward


def setup(service, monkeypatch):
    ctx = CronContext(service.settings.home)
    monkeypatch.setattr('email_steward.cron_delivery.prepare_tools', lambda: None)
    binding = install_schedule(ctx, service)
    return ctx, binding


def test_large_multibyte_backlog_completes_across_restart_without_replay(env, monkeypatch):
    service = env[0]
    service.settings = replace(service.settings, briefs=())
    ctx, binding = setup(service, monkeypatch)
    service.store.outbox('large', 1, 'ax1 Synthetic statement\n' + '🙂' * 5000 + ' END-SYNTHETIC-CONTENT')
    expected = service.store.rows('SELECT id,text FROM outbox ORDER BY rowid')
    assert len(expected) > 10
    outputs = []
    for now in range(2, 40):
        # Re-open durable state as a fresh worker would on every CLI invocation.
        fresh = Steward(Store(service.store.root), service.settings, service.provider_factory, service.model)
        fresh.current_settings()
        output = cron_tick(ctx, fresh, binding['key'], service.settings.home, now=now)
        if not output:
            break
        assert len(output.encode()) <= MAX_BATCH_BYTES
        outputs.append(output)
    assert len(outputs) > 2
    assert 'END-SYNTHETIC-CONTENT' in outputs[-1]
    assert all(r['state'] == 'handed_to_cron' and r['attempts'] == 1
               for r in service.store.rows('SELECT * FROM outbox'))
    assert len(service.store.rows("SELECT * FROM meta WHERE key LIKE 'cron_handoff:%'")) == len(outputs)
    assert not service.store.rows("SELECT * FROM outbox WHERE state IN ('sent','accepted','pending','retry')")


def test_provider_failure_retains_pending_job_then_recovers_without_reprocessing(env, monkeypatch):
    service, _, provider, _, access, _ = env
    service.settings = replace(service.settings, briefs=())
    ctx, binding = setup(service, monkeypatch)
    provider.add('new', subject='Security alert', body='Suspicious sign-in. Please review today.')
    provider.fail_modify = 1
    cron_tick(ctx, service, binding['key'], service.settings.home, now=1000)
    assert service.store.rows("SELECT * FROM jobs WHERE status='pending'")
    assert Worker(service, None).health(1000)
    cron_tick(ctx, service, binding['key'], service.settings.home, now=1100)
    assert not service.store.rows("SELECT * FROM jobs WHERE status='pending'")
    assert service.store.item('ax1')['classification'] == 'needs_action'
    count = len(service.store.rows('SELECT * FROM outbox'))
    assert cron_tick(ctx, service, binding['key'], service.settings.home, now=1200) == ''
    assert len(service.store.rows('SELECT * FROM outbox')) == count


def test_failure_uncertain_and_explicit_retry_preserves_obligation(env, monkeypatch):
    service, _, provider, _, _, source = env
    service.settings = replace(service.settings, briefs=())
    ctx, binding = setup(service, monkeypatch)
    provider.add('new', subject='Security alert', body='Suspicious sign-in. Please review today.')
    output = cron_tick(ctx, service, binding['key'], service.settings.home, now=1000)
    assert output
    ident = service.store.meta('cron_last_handoff')['ids'][0]
    ctx.jobs[0].update(last_delivery_error='Synthetic refusal', last_run_at='run-1')
    assert cron_tick(ctx, service, binding['key'], service.settings.home, now=1100) == ''
    assert service.store.rows('SELECT state FROM outbox WHERE id=?', (ident,))[0]['state'] == 'uncertain'
    assert service.store.item('ax1')['classification'] == 'needs_action'
    chat = Chat(lambda: service, lambda s: Worker(s, None))
    result = chat.run('delivery-retry ' + ident, source=source)
    assert result.get('duplicate_risk_acknowledged') is True, result
    assert cron_tick(ctx, service, binding['key'], service.settings.home, now=1200)
    assert cron_tick(ctx, service, binding['key'], service.settings.home, now=1201) == ''
    assert service.store.item('ax1')['classification'] == 'needs_action'


def test_native_body_is_transient_even_when_long(env):
    service, _, provider, _, access, source = env
    marker = 'SYNTHETIC-TRANSIENT-END-OF-LONG-BODY'
    provider.add('body', subject='Synthetic request', body='Please review. ' + 'ordinary ' * 500 + marker)
    Worker(service, None).tick(1000)
    posted = []
    chat = Chat(lambda: service, lambda s: Worker(s, None),
                post_message=lambda text: posted.append(text) or SimpleNamespace(ok=True))
    reply = chat.command('inspect ax1 text', source=source)
    assert marker in '\n'.join([*posted, reply])
    assert not service.store.rows("SELECT * FROM outbox WHERE category='command'")
    assert marker.encode() not in service.store.path.read_bytes()


def test_manual_brief_cannot_be_exported_by_concurrent_cron(env, monkeypatch):
    service, _, provider, _, _, source = env
    service.settings = replace(service.settings, briefs=())
    ctx, binding = setup(service, monkeypatch)
    provider.add('new', subject='Review', body='Please approve the synthetic proposal today.')
    Worker(service, None).tick(1000)
    # Drain unrelated urgent output before the manual brief.
    cron_tick(ctx, service, binding['key'], service.settings.home, now=1001)
    import email_steward.replies as replies
    original = replies.command_reply
    exported = []
    def interleave(*args, **kwargs):
        exported.append(cron_tick(ctx, service, binding['key'], service.settings.home, now=1002))
        return original(*args, **kwargs)
    monkeypatch.setattr(replies, 'command_reply', interleave)
    reply = Chat(lambda: service, lambda s: Worker(s, None)).command('brief', source=source)
    assert 'Email Steward brief' in reply
    assert not exported[0], 'Manual brief was also exported through cron: ' + exported[0]


def test_long_native_reply_survives_released_discord_response_cap(env):
    from gateway.config import PlatformConfig
    from plugins.platforms.discord.adapter import DiscordAdapter
    from email_steward.gmail import Attachment
    from scripts.extraction_fixtures import office
    service, _, provider, _, _, source = env
    marker = 'SYNTHETIC-END-MUST-REACH-OWNER'
    first = office('docx', 'Please review. ' + 'ordinary ' * 850)
    last = office('docx', 'ordinary ' * 850 + marker)
    provider.add('long', subject='Synthetic long request', body='Please review the attachments.',
                 attachments=[Attachment('first.docx', '', len(first), lambda: first),
                              Attachment('last.docx', '', len(last), lambda: last)])
    Worker(service, None).tick(1000)
    posted = []
    reply = Chat(lambda: service, lambda s: Worker(s, None),
        post_message=lambda text: posted.append(text) or SimpleNamespace(ok=True)).command('inspect ax1 attachments', source=source)
    assert marker in '\n'.join([*posted, reply])
    adapter = DiscordAdapter(PlatformConfig(enabled=True))
    from gateway.plugin_messages import _fit
    # The public host clamps each posted message; its normal returned response
    # is formatted/split/capped independently. The triggering reply still spans
    # more than the eight-message cap when combined, but no single call does.
    assert len(posted) > adapter.MAX_SPLIT_MESSAGES
    delivered = []
    for response in [*posted, reply]:
        assert _fit(adapter, service.settings.destination, response) == response
        chunks = adapter.truncate_message(adapter.format_message(response), adapter.MAX_MESSAGE_LENGTH)
        assert len(chunks) <= adapter.MAX_SPLIT_MESSAGES
        delivered.extend(adapter._cap_split_chunks(chunks))
    assert marker in '\n'.join(delivered)
    assert not service.store.rows("SELECT id FROM outbox WHERE category='command'")
    assert marker.encode() not in service.store.path.read_bytes()


def test_quiet_boundary_crossed_during_intake_blocks_final_handoff(env, monkeypatch):
    from datetime import datetime, timezone
    import email_steward.cron_delivery as cron
    service = env[0]
    service.settings = replace(service.settings, timezone='UTC', briefs=(), quiet_start='23:00', quiet_end='07:00')
    ctx, binding = setup(service, monkeypatch)
    start = datetime(2026, 11, 8, 22, 59, 59, tzinfo=timezone.utc).timestamp()
    clock = [start]
    service.store.outbox('ordinary-brief', start - 1, 'Private ordinary brief', category='brief')
    class SlowIntake:
        def __init__(self, *args): pass
        def tick(self, now):
            assert now == start
            clock[0] = start + 2
    monkeypatch.setattr(cron, 'Worker', SlowIntake)
    monkeypatch.setattr(cron.time, 'time', lambda: clock[0])
    # Exercise the real production default, which takes time.time() at entry.
    output = cron.cron_tick(ctx, service, binding['key'], service.settings.home)
    assert output == '', 'Handoff used pre-intake time after quiet hours began: ' + output
    assert service.store.rows("SELECT state FROM outbox WHERE id='ordinary-brief'") == [{'state':'pending'}]


@pytest.mark.parametrize("stop", ["unconfirmed", "revoked"])
def test_multipart_reply_stops_without_caching_or_replaying_body(env, stop):
    service, _, provider, _, _, source = env
    marker = "SYNTHETIC-TAIL-MUST-BE-WITHHELD"
    provider.add("body", body="Please review. " + "ordinary " * 900 + marker)
    Worker(service, None).tick(1000)
    posted = []
    def post(text):
        posted.append(text)
        if stop == "revoked":
            service.settings = replace(service.settings, private_confirmed=False)
            return SimpleNamespace(ok=True)
        return SimpleNamespace(ok=False, pending=True)
    reply = Chat(lambda: service, lambda s: Worker(s, None), post_message=post).command("inspect ax1 text", source=source)
    assert len(posted) == 1 and marker not in posted[0] and marker not in reply
    assert "repeating may duplicate" in reply
    assert not service.store.rows("SELECT id FROM outbox WHERE category='command'")
    assert marker.encode() not in service.store.path.read_bytes()


def test_interrupted_native_brief_stays_reserved_until_explicit_owner_retry(env, monkeypatch):
    service, _, provider, _, _, source = env
    service.settings = replace(service.settings, briefs=())
    ctx, binding = setup(service, monkeypatch)
    provider.add("new", body="Please approve the synthetic proposal today.")
    Worker(service, None).tick(1000)
    cron_tick(ctx, service, binding['key'], service.settings.home, now=1001)
    import email_steward.replies as replies
    original = replies.command_reply
    def interrupted(*args): raise RuntimeError("Synthetic interruption before export")
    monkeypatch.setattr(replies, "command_reply", interrupted)
    chat = Chat(lambda: service, lambda s: Worker(s, None))
    with pytest.raises(RuntimeError): chat.command("brief", source=source)
    rows = service.store.rows("SELECT * FROM outbox WHERE state='reserved_native'")
    assert rows and all(row['attempts'] == 0 for row in rows)
    assert cron_tick(ctx, service, binding['key'], service.settings.home, now=1002) == ''
    assert any('uncertainty' in issue for issue in Worker(service, None).health(1002))
    monkeypatch.setattr(replies, "command_reply", original)
    result = chat.run("delivery-retry " + rows[0]['id'], source=source)
    assert result['duplicate_risk_acknowledged'] is True
    assert "Email Steward brief" in cron_tick(ctx, service, binding['key'], service.settings.home, now=1003)
