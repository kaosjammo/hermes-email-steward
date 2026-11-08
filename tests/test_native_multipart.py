"""Actual released public command/post-message path, with a synthetic final adapter."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import threading

from test_backend import env
from test_native import upstream


def test_registered_command_posts_every_part_through_public_host_context(env, upstream, monkeypatch):
    from gateway.config import PlatformConfig
    from gateway.platforms.base import SendResult
    from gateway.plugin_messages import bind_live_source
    from gateway.session import build_session_key
    from gateway.session_context import set_session_vars, clear_session_vars
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.plugins import PluginContext, PluginManager, get_plugin_command_handler
    from hermes_cli.plugins_manifest import parse_manifest_file
    from plugins.platforms.discord.adapter import DiscordAdapter
    from email_steward.worker import Worker
    import email_steward.plugin as product
    import hermes_cli.plugins as plugins
    import gateway.run as gateway

    service, _, provider, _, _, source = env
    marker = "REGISTERED-NATIVE-TAIL-MUST-ARRIVE"
    provider.add("body", body="Please review. " + "ordinary " * 1000 + marker)
    Worker(service, None).tick(1000)
    captured = []
    class Capture(DiscordAdapter):
        async def send(self, chat_id, content, reply_to=None, metadata=None):
            assert chat_id == service.settings.destination
            assert metadata['_interim_send'] is True
            parts = self.truncate_message(self.format_message(content), self.MAX_MESSAGE_LENGTH)
            assert len(parts) <= self.MAX_SPLIT_MESSAGES
            captured.extend(self._cap_split_chunks(parts))
            return SendResult(True, message_id="synthetic-" + str(len(captured)))
    adapter = Capture(PlatformConfig(enabled=True))
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    key = build_session_key(source)
    runner = SimpleNamespace(_running=True, _gateway_loop=loop,
        session_store=SimpleNamespace(lookup_by_session_key=lambda _: None),
        _session_key_for_source=build_session_key,
        _plugin_messaging_session_owned=lambda session_key, plugin_home, plugin_id:
            session_key == key and Path(plugin_home).resolve() == service.settings.home and plugin_id == 'email-steward',
        _delivery_adapter_for=lambda actual_source: adapter if actual_source is source else None,
        _thread_metadata_for_source=lambda _: {})
    token = set_hermes_home_override(service.settings.home)
    manager = PluginManager(scope_key=str(service.settings.home))
    root = Path(__file__).resolve().parents[1]
    ctx = PluginContext(parse_manifest_file(root/'plugin.yaml', root, 'project', ''), manager)
    monkeypatch.setattr(product, 'service_from_host', lambda ctx: service)
    monkeypatch.setattr(plugins, '_ensure_plugins_discovered', lambda **kw: manager)
    monkeypatch.setattr(gateway, '_gateway_runner_ref', lambda: runner)
    session_tokens = set_session_vars(platform='discord', user_id=service.settings.owner,
        chat_id=service.settings.destination, chat_type='dm', profile=service.settings.profile, session_key=key)
    try:
        product.register(ctx)
        handler = get_plugin_command_handler('email-steward')
        with bind_live_source(source):
            reply = handler('inspect ax1 text', source=source)
        assert len(captured) > adapter.MAX_SPLIT_MESSAGES
        assert marker in '\n'.join(captured)
        assert 'reply parts' in reply and 'host-owned' in reply
        assert marker not in reply
        assert not service.store.rows("SELECT id FROM outbox WHERE category='command'")
        assert marker.encode() not in service.store.path.read_bytes()
        # The same public method refuses without a calling-session context.
        clear_session_vars(session_tokens)
        session_tokens = None
        before = list(captured)
        refused = ctx.post_message('This must not leave an unbound call')
        assert refused.ok is False and refused.error == 'no_conversation'
        assert captured == before
    finally:
        if session_tokens is not None: clear_session_vars(session_tokens)
        manager.unload()
        reset_hermes_home_override(token)
        asyncio.run_coroutine_threadsafe(loop.shutdown_default_executor(), loop).result(5)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()
