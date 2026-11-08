"""Actual pinned registry/default dispatch/SDK; synthetic final HTTP/daemon only.

No live accounts, sockets, sidecars or provider inference. This is not canonical gateway
runtime or private-membership acceptance. Native RoutingIdentity/receiving runner fixtures
are explicitly synthetic; adapter code, SDK formatters and dispatch are actual imports.
"""
from contextlib import contextmanager
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import weakref

import pytest

sys.path.insert(0, os.environ.get("HERMES_UPSTREAM", str(Path(__file__).resolve().parents[2])))

from email_steward.security import Settings
from email_steward.gateways import native_access, CAPABILITIES
from cron_transport import CronTransport
from email_steward.service import Steward
from email_steward.store import Store
from email_steward.outbound import chunks


@pytest.fixture(autouse=True)
def forbid_real_network(monkeypatch):
    import socket
    attempts = []
    def deny(*args, **kwargs):
        import traceback
        attempts.append("".join(traceback.format_stack(limit=12)))
        raise AssertionError("Native qualification forbids real DNS/socket/network effects")
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    def bind_denied(sock, address):
        # urllib3 performs a loopback IPv6 availability probe at import. Refuse
        # it as unavailable without opening a socket endpoint or faking a transport.
        if address == ("::1", 0):
            raise OSError("Synthetic qualification disables IPv6 bind capability probe")
        return deny(sock, address)
    monkeypatch.setattr(socket.socket, "bind", bind_denied)
    monkeypatch.setattr(socket.socket, "listen", deny)
    yield
    assert not attempts, "\n".join(attempts)


class Response:
    status = 200
    ok = True
    content_type = "application/json"
    headers = {}
    def __init__(self, data): self.data = data
    async def json(self, **kwargs): return self.data
    async def text(self): return json.dumps(self.data)
    async def read(self): return json.dumps(self.data).encode()
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def release(self): pass
    async def wait_for_close(self): pass
    def raise_for_status(self): pass


@pytest.fixture
def route(tmp_path, monkeypatch):
    """Actual scoped PluginContext/PlatformRegistry; synthetic configured host/runner."""
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.plugins import PluginContext, PluginManager
    from hermes_cli.plugins_manifest import parse_manifest_file
    from gateway.config import PlatformConfig
    from gateway.session_identity import resolve_identity
    from gateway.platform_registry import platform_registry
    import gateway.run as run
    token = set_hermes_home_override(tmp_path)
    manager = PluginManager(scope_key=str(tmp_path))
    root = Path(os.environ.get("HERMES_UPSTREAM", Path(__file__).resolve().parents[2]))
    transports, calls = {}, []
    runner = SimpleNamespace(_authorization_adapter=lambda platform, profile: transports.get(platform.value),
        config=SimpleNamespace(multiplex_profiles=False), _primary_profile_name="custom",
        _owning_profile=lambda adapter, platform: (True, "custom"))
    monkeypatch.setattr(run, "_gateway_runner_ref", lambda: runner)
    def create(platform, target, *, chat_type="dm", thread=None, scope="", extra=None, parent=""):
        bundle = "wecom" if platform == "wecom_callback" else platform
        directory = root / "plugins/platforms" / bundle
        manifest = parse_manifest_file(directory / "plugin.yaml", directory, "bundled", "platforms")
        ctx = PluginContext(manifest, manager)
        module = importlib.import_module("plugins.platforms." + bundle + (".callback_adapter" if platform == "wecom_callback" else ".adapter"))
        importlib.import_module("plugins.platforms." + bundle).register(ctx)
        config = PlatformConfig(enabled=True, token="12345:" + "A" * 35,
            extra={"topic": target, "server": "https://synthetic.example.test", **(extra or {})})
        adapter = platform_registry.get(platform).adapter_factory(config)
        adapter._owner_profile = "custom"
        transports[platform] = adapter
        # Actual host YAML config parser is used by both preflight and entrypoint.
        import yaml
        (tmp_path / "config.yaml").write_text(yaml.safe_dump({"platforms": {platform: config.to_dict()}}))
        (tmp_path / "channel_directory.json").write_text(json.dumps({"platforms": {platform: [
            {"id": target, "name": "Synthetic exact destination", "type": chat_type}]}}))
        settings = Settings(home=tmp_path, profile="custom", owner="12345", platform=platform,
            destination=target, destination_type=chat_type, thread=thread, scope=scope, parent=parent,
            private_confirmed=True, account="custom:" + platform, transport_profile="custom",
            transport_home=str(tmp_path), grant_revision=1, timezone="UTC",
            route_context=json.dumps({k: str(config.extra[k]) for k in __import__("email_steward.gateways", fromlist=["CONTEXT_FIELDS"]).CONTEXT_FIELDS.get(platform, ())}))
        service = Steward(Store(tmp_path / (platform + "-state")), settings)
        service.current_settings()
        if CAPABILITIES[platform].mode == "interactive":
            source = adapter.build_source(target, chat_type=chat_type, user_id=settings.owner,
                thread_id=thread, scope_id=scope or None, parent_chat_id=parent or None)
            resolve_identity(source, runner=runner, adapter=adapter, transport_profile="custom", primary_home=tmp_path)
            service.guard(native_access(settings, source))
            create.source = source
        delivery = CronTransport(ctx, service, transports)
        return service, adapter, module, delivery
    create.transports = transports
    create.manager = manager
    yield create, calls, monkeypatch
    manager.unload()
    reset_hermes_home_override(token)


def test_actual_discord_rest_default_dispatch_and_hostile_payload(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("discord", "67890")
    import aiohttp
    async def request(self, method, url, **kwargs):
        calls.append((method, str(url), kwargs))
        return Response({"id": "67890", "type": 1} if method == "GET" else {"id": "999999", "channel_id": "67890"})
    monkeypatch.setattr(aiohttp.ClientSession, "_request", request)
    hostile = '@everyone <@12345> MEDIA:/etc/passwd [[as_document]] **x**\u202e\x00\nBcc: victim@example.test\nax1'
    parts = chunks(hostile)
    assert delivery.send(s.settings, parts[0], "test") == "handed_to_cron"
    posts = [c for c in calls if c[0] == "POST"]
    assert len(posts) == 1 and posts[0][1].endswith("/channels/67890/messages")
    payload = posts[0][2]["json"]
    assert all(x not in payload["content"] for x in ("@everyone", "<@", "MEDIA:/", "[[as_document]]", "\u202e", "\x00", "Bcc:"))
    assert "\nax1\n" in payload["content"]
    assert "handed to Hermes cron" in payload["content"]


def test_actual_telegram_sdk_flat_route_no_topic_fallback(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("telegram", "67890")
    from telegram.request import HTTPXRequest
    async def do_request(self, url, method, request_data=None, **kwargs):
        data = request_data.json_parameters if request_data else {}
        calls.append((url, data))
        result = ({"id": 12345, "is_bot": True, "first_name": "Synthetic", "username": "synthetic_bot"}
            if url.endswith("getMe") else {"message_id": 12, "date": 1, "chat": {"id": 67890, "type": "private"}, "text": "synthetic"})
        return 200, json.dumps({"ok": True, "result": result}).encode()
    monkeypatch.setattr(HTTPXRequest, "do_request", do_request)
    assert delivery.send(s.settings, chunks("ax1 *message* 🙂")[0], "test") == "handed_to_cron"
    sends = [x for x in calls if x[0].endswith("sendMessage")]
    assert len(sends) == 1 and str(sends[0][1]["chat_id"]) == "67890"
    assert "message_thread_id" not in sends[0][1]
    before = len(calls)
    assert delivery.send(replace(s.settings, thread="12"), "synthetic", "topic") == "blocked"
    assert len(calls) == before


def test_actual_slack_live_sdk_exact_workspace_and_thread(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("slack", "D123456789", scope="T12345", thread="123.456")
    from slack_sdk.web.async_client import AsyncWebClient
    import aiohttp
    client = AsyncWebClient(token="xoxb-synthetic", retry_handlers=[])
    from slack_bolt.async_app import AsyncApp
    adapter._app = AsyncApp(client=client, signing_secret="synthetic")
    adapter._team_clients = {"T12345": client}
    adapter._channel_team = {"D123456789": "T12345"}
    adapter._channel_teams = {"D123456789": {"T12345"}}
    async def request(self, method, url, **kwargs):
        calls.append((method, str(url), kwargs))
        response = Response({"ok": True, "ts": "123.999", "channel": "D123456789"})
        response.headers = {"Content-Type": "application/json;charset=utf-8"}
        return response
    monkeypatch.setattr(aiohttp.ClientSession, "_request", request)
    assert delivery.send(s.settings, chunks("ax1 @channel *request* Friday")[0], "slack") == "handed_to_cron"
    posts = [c for c in calls if c[1].endswith("chat.postMessage")]
    assert len(posts) == 1
    payload = posts[0][2]["json"]
    assert payload["channel"] == "D123456789" and payload["thread_ts"] == "123.456"
    assert "@channel" not in payload["text"] and "ax1" in payload["text"]
    before = len(calls)
    s.settings = replace(s.settings, scope="FOREIGN", grant_revision=2)
    assert delivery.send(s.settings, "synthetic", "collision") == "blocked"
    assert len(calls) == before


def test_actual_matrix_mautrix_sdk_exact_room_and_root(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("matrix", "!synthetic:example.test", scope="example.test",
        thread="$root:example.test", parent="!synthetic:example.test",
        extra={"homeserver": "https://example.test", "user_id": "@synthetic:example.test"})
    from mautrix.client import Client
    from mautrix.api import HTTPAPI
    # Actual SDK construction has no authenticated connection or sidecar startup.
    import asyncio
    async def make_client():
        return Client(mxid="@synthetic:example.test", base_url="https://example.test", token="synthetic")
    loop = asyncio.Runner()
    adapter._client = loop.run(make_client())
    async def request(self, method, path, content=None, **kwargs):
        calls.append((str(method), str(path), content))
        return {"event_id": "$receipt:example.test"}
    monkeypatch.setattr(HTTPAPI, "request", request)
    assert delivery.send(s.settings, chunks("ax1 **body** @room 🙂")[0], "matrix") == "handed_to_cron"
    from urllib.parse import unquote
    assert len(calls) == 1 and "rooms/!synthetic:example.test/send/m.room.message" in unquote(calls[0][1])
    payload = calls[0][2]
    assert payload["m.relates_to"]["event_id"] == "$root:example.test"
    assert payload["m.relates_to"]["rel_type"] == "m.thread"
    assert "@room" not in payload["body"] and "ax1" in payload["body"]
    loop.run(adapter._client.api.session.close())
    loop.close()


def test_actual_line_standalone_push_and_revoked_grant_guard(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("line", "U" + "1" * 32,
        extra={"channel_access_token": "synthetic", "channel_secret": "synthetic"})
    import aiohttp
    async def request(self, method, url, **kwargs):
        calls.append((str(url), kwargs))
        return Response({})
    monkeypatch.setattr(aiohttp.ClientSession, "_request", request)
    revoked = replace(s.settings, private_confirmed=False)
    assert delivery.send(revoked, "ax1 synthetic", "held") == "blocked" and calls == []
    create.transports.pop("line")  # exercise the actual host standalone default when live is absent
    assert delivery.send(s.settings, "ax1 synthetic", "line") == "handed_to_cron"
    assert len(calls) == 1 and calls[0][0].endswith("/message/push")
    payload = calls[0][1]["json"]
    assert payload["to"] == s.settings.destination and len(payload["messages"]) == 1
    assert "ax1 synthetic" in payload["messages"][0]["text"] and "handed to Hermes cron" in payload["messages"][0]["text"]


def test_actual_mattermost_standalone_server_and_target(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("mattermost", "a" * 26,
        extra={"url": "https://mattermost.example.test"})
    create.transports.pop("mattermost")
    import aiohttp
    async def request(self, method, url, **kwargs):
        calls.append((str(url), kwargs))
        return Response({"id": "synthetic-post"})
    monkeypatch.setattr(aiohttp.ClientSession, "_request", request)
    assert delivery.send(s.settings, "ax1 synthetic", "mattermost") == "handed_to_cron"
    assert len(calls) == 1 and calls[0][0] == "https://mattermost.example.test/api/v4/posts"
    assert calls[0][1]["json"]["channel_id"] == s.settings.destination
    assert "root_id" not in calls[0][1]["json"]


def test_actual_signal_daemon_envelope_and_account_collision(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("signal", "+15550001111",
        extra={"account": "+15550002222", "http_url": "https://signal.example.test"})
    import httpx
    async def handle(self, request):
        payload = json.loads(request.content)
        calls.append((payload["method"], payload["params"]))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"],
            "result": {"timestamp": 1790000000000, "results": [{"type": "SUCCESS"}]}})
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    assert delivery.send(s.settings, chunks("ax1 **request** @all")[0], "signal") == "handed_to_cron"
    sends = [c for c in calls if c[0] == "send"]
    assert len(sends) == 1 and sends[0][1]["account"] == "+15550002222"
    assert sends[0][1]["recipient"] == ["+15550001111"]
    assert "@all" not in sends[0][1]["message"]
    before = len(calls)
    s.settings = replace(s.settings, route_context=json.dumps({"account": "+15550003333", "http_url": "https://signal.example.test"}), grant_revision=2)
    assert delivery.send(s.settings, "synthetic", "wrong-account") == "blocked"
    assert len(calls) == before


def test_actual_whatsapp_cloud_http_exact_phone_account(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("whatsapp_cloud", "15550001111",
        extra={"phone_number_id": "public-number-id", "access_token": "synthetic"})
    import httpx
    adapter._http_client = httpx.AsyncClient()
    async def handle(self, request):
        calls.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.synthetic"}]})
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    assert delivery.send(s.settings, "ax1 synthetic", "cloud") == "handed_to_cron"
    assert len(calls) == 1 and calls[0].url.path.endswith("/public-number-id/messages")
    payload = json.loads(calls[0].content)
    assert payload["to"] == "15550001111" and payload["recipient_type"] == "individual"
    assert delivery.last_output in payload["text"]["body"]
    import asyncio
    asyncio.run(adapter._http_client.aclose())
    adapter._http_client = None


def test_actual_sms_form_and_provider_queued_receipt(route):
    create, calls, monkeypatch = route
    for key, value in {"TWILIO_ACCOUNT_SID": "ACsynthetic", "TWILIO_PHONE_NUMBER": "+15550002222", "TWILIO_AUTH_TOKEN": "synthetic"}.items():
        monkeypatch.setenv(key, value)
    s, adapter, module, delivery = create("sms", "+15550001111",
        extra={"account_sid": "ACsynthetic", "from_number": "+15550002222"})
    import aiohttp
    async def request(self, method, url, **kwargs):
        calls.append((str(url), kwargs))
        return Response({"sid": "SMsynthetic", "status": "queued"})
    monkeypatch.setattr(aiohttp.ClientSession, "_request", request)
    assert delivery.send(s.settings, "ax1 synthetic", "sms") == "handed_to_cron"
    assert len(calls) == 1 and "/Accounts/ACsynthetic/Messages.json" in calls[0][0]
    from urllib.parse import parse_qs
    form = parse_qs(calls[0][1]["data"]()._value.decode())  # actual aiohttp form encoder
    assert form["To"] == ["+15550001111"] and form["From"] == ["+15550002222"]
    assert len(form["Body"]) == 1 and delivery.last_output in form["Body"][0]


@pytest.mark.parametrize("platform,target,extra,receipt_data,path", [
    ("bluebubbles", "iMessage;-;+15550001111", {"server_url": "https://blue.example.test", "password": "synthetic"},
        {"status": 200, "data": {"guid": "synthetic-guid"}}, "/api/v1/message/text"),
    ("photon", "iMessage;-;+15550001111", {"project_id": "synthetic-project"},
        {"ok": True, "messageId": "synthetic-message"}, "/send"),
])
def test_actual_native_bridge_payload_no_sidecar_started(route, platform, target, extra, receipt_data, path):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create(platform, target, extra=extra)
    import httpx
    client = httpx.AsyncClient()
    if platform == "bluebubbles":
        adapter.client = client
    else:
        adapter._http_client = client
        adapter._sidecar_bind, adapter._sidecar_port, adapter._sidecar_token = "127.0.0.1", 1, "synthetic"
    async def handle(self, request):
        calls.append(request)
        return httpx.Response(200, json=receipt_data)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    body = chunks("ax1 paragraph one\n\nparagraph two @everyone")[0]
    assert delivery.send(s.settings, body, platform) == "handed_to_cron"
    assert len(calls) == (5 if platform == "bluebubbles" else 1)
    assert all(request.url.path == path for request in calls)
    payloads = [json.loads(request.content) for request in calls]
    assert all(payload["chatGuid" if platform == "bluebubbles" else "spaceId"] == target for payload in payloads)
    text = "\n\n".join(payload["message" if platform == "bluebubbles" else "text"] for payload in payloads)
    assert delivery.last_output in text and text.count("paragraph two ＠everyone") == 1
    assert "@everyone" not in text
    import asyncio
    asyncio.run(client.aclose())


def test_actual_wecom_request_correlation_and_uncertain_ack(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("wecom", "synthetic-user",
        extra={"bot_id": "public-bot", "secret": "synthetic", "websocket_url": "wss://wecom.example.test/ws"})
    class SyntheticWebSocket:
        closed = False
        async def send_json(self, payload):
            calls.append(json.loads(json.dumps(payload)))
            adapter._pending_responses[payload["headers"]["req_id"]].set_result(
                {"headers": payload["headers"], "errcode": 0, "errmsg": "ok"})
        async def close(self): self.closed = True
    adapter._ws = SyntheticWebSocket()  # final socket seam; no connection or listener is started
    assert delivery.send(s.settings, "ax1 synthetic", "wecom") == "handed_to_cron"
    assert len(calls) == 1 and calls[0]["body"]["chatid"] == "synthetic-user"
    assert calls[0]["cmd"] == module.APP_CMD_SEND
    from model_tools import _run_async
    _run_async(adapter.disconnect())


def test_actual_feishu_lark_sdk_message_request(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("feishu", "oc_synthetic",
        extra={"app_id": "cli_synthetic", "app_secret": "synthetic"})
    import requests
    def send(self, request, **kwargs):
        calls.append(request)
        data = ({"code": 0, "tenant_access_token": "synthetic-token", "expire": 3600}
            if "/auth/" in request.url else {"code": 0, "data": {"message_id": "om_synthetic"}})
        response = requests.Response()
        response.status_code, response._content = 200, json.dumps(data).encode()
        response.headers["Content-Type"] = "application/json"
        return response
    monkeypatch.setattr(requests.Session, "send", send)
    assert delivery.send(s.settings, "ax1 synthetic", "feishu") == "handed_to_cron"
    messages = [r for r in calls if "/im/v1/messages" in r.url]
    assert len(messages) == 1
    payload = json.loads(messages[0].body)
    assert payload["receive_id"] == "oc_synthetic" and "chat_id" in messages[0].url
    assert "ax1 synthetic" in payload["content"]


def test_actual_google_chat_discovery_sdk_flat_dm_and_stale_context_guard(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("google_chat", "spaces/synthetic", extra={"project_id": "synthetic-project"})
    assert module._load_google_modules()
    from google.auth.credentials import AnonymousCredentials
    from googleapiclient.discovery import build
    import httplib2
    adapter._credentials = AnonymousCredentials()
    adapter._chat_api = build("chat", "v1", credentials=adapter._credentials, static_discovery=True, cache_discovery=False)
    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        calls.append((str(uri), method, body))
        return httplib2.Response({"status": "200", "content-type": "application/json"}), json.dumps({
            "name": "spaces/synthetic/messages/receipt"}).encode()
    monkeypatch.setattr(httplib2.Http, "request", request)
    assert delivery.send(s.settings, "ax1 synthetic", "google") == "handed_to_cron"
    assert len(calls) == 1 and "/spaces/synthetic/messages" in calls[0][0]
    assert delivery.last_output in json.loads(calls[0][2])["text"]
    before = len(calls)
    s.settings = replace(s.settings, thread="spaces/synthetic/threads/foreign", grant_revision=2)
    assert delivery.send(s.settings, "synthetic", "thread") == "blocked"
    assert len(calls) == before


def test_actual_teams_sdk_initialize_without_listener_and_exact_conversation(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("teams", "19:synthetic@thread.v2", scope="synthetic-tenant",
        extra={"client_id": "synthetic-app", "tenant_id": "synthetic-tenant"})
    # Supported host lazy binder, already-installed actual SDK. No installer is permitted.
    import pm
    monkeypatch.setattr(pm, "ensure_import", lambda *a, **k: (_ for _ in ()).throw(AssertionError("No lazy installs")))
    assert module.check_teams_requirements()
    import aiohttp.web
    import jwt, time
    fake_token = jwt.encode({"appid": "synthetic-app", "tid": "synthetic-tenant", "exp": int(time.time()) + 3600},
        "synthetic-test-key-not-a-real-credential", algorithm="HS256")
    async def token(*args, **kwargs): return fake_token
    adapter._app = module.App(client_id="synthetic-app", tenant_id="synthetic-tenant", token=token,
        http_server_adapter=module._AiohttpBridgeAdapter(aiohttp.web.Application()))
    from model_tools import _run_async
    _run_async(adapter._app.initialize())  # public SDK explicitly initializes without starting a listener
    import httpx
    async def handle(self, request):
        calls.append(request)
        return httpx.Response(200, json={"id": "synthetic-activity"})
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    assert delivery.send(s.settings, "ax1 synthetic", "teams") == "handed_to_cron", delivery._fixture_receipts
    assert len(calls) == 1 and calls[0].url.path == "/teams/v3/conversations/19:synthetic@thread.v2/activities"
    assert delivery.last_output in json.loads(calls[0].content)["text"]


def test_actual_ntfy_http_notification_does_not_grant_commands(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create("ntfy", "synthetic-private", chat_type="topic")
    import httpx
    adapter._http_client = httpx.AsyncClient()
    async def handle(self, request):
        calls.append(request)
        return httpx.Response(200, json={"id": "synthetic-receipt"})
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    assert delivery.send(s.settings, "ax1 bounded plain notification", "test") == "handed_to_cron"
    assert len(calls) == 1 and calls[0].url.path == "/synthetic-private"
    assert delivery.last_output.encode() in calls[0].content
    from gateway.session import SessionSource
    with pytest.raises(Exception): native_access(s.settings, SessionSource(adapter.platform, s.settings.destination, user_id=s.settings.owner))
    import asyncio
    asyncio.run(adapter._http_client.aclose())
    adapter._http_client = None


@pytest.mark.parametrize("platform", [p for p, c in CAPABILITIES.items() if c.mode not in {"interactive", "notification"}])
def test_unsupported_surface_never_enters_native_dispatch(route, platform):
    create, calls, monkeypatch = route
    from tools import send_message_tool as host
    invoked = []
    monkeypatch.setattr(host, "send_message_tool", lambda args: invoked.append(args))
    # No adapter or optional SDK import is fabricated for a denied platform.
    settings = Settings(home=Path(os.environ["HERMES_HOME"]), profile="custom", owner="owner", platform=platform,
        destination="synthetic", private_confirmed=True)
    from email_steward.gateways import validate
    with pytest.raises(Exception):
        validate(settings)
    assert invoked == [] and calls == []


def test_actual_wecom_callback_single_app_and_exact_recipient(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create('wecom_callback', 'synthetic-corp:12345',
        extra={'corp_id':'synthetic-corp', 'agent_id':'7', 'corp_secret':'synthetic-only'})
    import httpx
    adapter._http_client = httpx.AsyncClient()
    async def handle(self, request):
        calls.append(request)
        return httpx.Response(200, json=({'errcode':0, 'access_token':'synthetic-token', 'expires_in':7200}
            if request.method == 'GET' else {'errcode':0, 'msgid':'synthetic-callback-receipt'}))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', handle)
    try:
        assert delivery.send(s.settings, chunks('ax1 @all synthetic')[0], 'callback') == 'handed_to_cron', delivery._fixture_receipts
        posts = [c for c in calls if c.method == 'POST']
        assert len(posts) == 1
        body = json.loads(posts[0].content)
        assert body['touser'] == '12345' and body['agentid'] == 7 and '@all' not in body['text']['content']
        before = len(calls)
        s.settings = replace(s.settings, route_context=json.dumps({'corp_id':'foreign','agent_id':'7'}), grant_revision=2)
        assert delivery.send(s.settings, 'ax1', 'changed') == 'blocked' and len(calls) == before
    finally:
        from model_tools import _run_async
        _run_async(adapter._http_client.aclose())


def test_actual_weixin_exact_account_and_recipient_correlation_not_receipt(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create('weixin', 'synthetic-user',
        extra={'account_id':'synthetic-account', 'base_url':'https://synthetic.example.test', 'split_multiline_messages':False})
    import aiohttp
    async def request(self, method, url, **kwargs):
        calls.append((method, str(url), kwargs))
        return Response({'ret':0})
    monkeypatch.setattr(aiohttp.ClientSession, '_request', request)
    assert delivery.send(s.settings, chunks('ax1 first\nsecond')[0], 'weixin') == 'handed_to_cron', delivery._fixture_receipts
    assert len(calls) == 1
    body = json.loads(calls[0][2]['data'])
    assert body['msg']['to_user_id'] == 'synthetic-user'
    assert 'ax1 first' in body['msg']['item_list'][0]['text_item']['text']
    assert 'second' in body['msg']['item_list'][0]['text_item']['text']
    s.settings = replace(s.settings, route_context=json.dumps({'account_id':'foreign','base_url':'https://synthetic.example.test'}), grant_revision=2)
    assert delivery.send(s.settings, 'ax1', 'foreign') == 'blocked' and len(calls) == 1


def test_actual_yuanbao_binary_dm_and_ambiguous_ack(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create('yuanbao', 'direct:12345', extra={'app_id':'synthetic-app', 'app_secret':'synthetic-only'})
    class Socket:
        async def send(self, data):
            frame = module.decode_conn_msg(data)
            calls.append(frame)
            # Actual connection parser resolves this response but does not validate provider status.
            adapter._connection._pending_acks[frame['head']['msg_id']].set_result({'head':frame['head']})
    adapter._connection._ws = Socket()
    type(adapter).set_active(adapter)
    try:
        assert delivery.send(s.settings, chunks('ax1 @all bounded')[0], 'yuanbao') == 'handed_to_cron', delivery._fixture_receipts
        assert len(calls) == 1
        # Actual binary frame carries a single explicit recipient and neutralised text.
        assert b'12345' in calls[0]['data'] and '＠all'.encode() in calls[0]['data']
        s.settings = replace(s.settings, route_context=json.dumps({'app_id':'foreign'}), grant_revision=2)
        assert delivery.send(s.settings, 'ax1', 'inactive') == 'blocked' and len(calls) == 1
    finally:
        type(adapter).set_active(None)
        adapter._connection._ws = None


def test_actual_buzz_cli_dispatch_synthetic_process_boundary(route, tmp_path):
    create, calls, monkeypatch = route
    path = tmp_path / 'synthetic-cli-placeholder'
    path.write_text('Not an installed CLI; final process boundary is synthetic.')
    s, adapter, module, delivery = create('buzz', 'synthetic-channel', extra={
        'cli_path':str(path), 'relay_url':'wss://synthetic.example.test', 'private_key':'1'*64})
    import asyncio
    class Process:
        returncode = 0
        async def communicate(self, content):
            calls[-1]['content'] = content.decode()
            return json.dumps({'accepted':True, 'event_id':'synthetic-event'}).encode(), b''
    async def execute(*argv, **kwargs):
        calls.append({'argv':argv, 'relay':kwargs['env']['BUZZ_RELAY_URL']})
        return Process()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', execute)
    assert delivery.send(s.settings, chunks('ax1 @all MEDIA:/etc/passwd')[0], 'buzz') == 'handed_to_cron', delivery._fixture_receipts
    assert len(calls) == 1
    assert calls[0]['argv'][1:] == ('messages','send','--channel','synthetic-channel','--content','-')
    assert calls[0]['relay'] == 'wss://synthetic.example.test' and '@all' not in calls[0]['content']


def test_native_registered_plaintext_lifecycle_and_transient_inspection(route):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create('discord','67890')
    from email_steward.synthetic import SyntheticGmail
    from email_steward.worker import Worker
    from email_steward.chat import Chat
    from hermes_cli.plugins import PluginContext
    from hermes_cli.plugins_manifest import parse_manifest_file
    from hermes_cli.plugin_command_dispatch import invoke_plugin_command
    from gateway.session_identity import replace_source
    import aiohttp
    provider = SyntheticGmail(); s.provider_factory = lambda account:provider
    access = native_access(s.settings,create.source)
    s.connect(access,'gmail-1','alex@example.test','Synthetic')
    provider.add('m1',subject='Renewal',body='Please approve disputed renewal by Friday at 17:00. PRIVATE-INSPECTION-ONLY',received=1)
    worker=Worker(s,delivery)
    async def request(self, method, url, **kwargs):
        if method == 'POST': calls.append(kwargs['json']['content'])
        return Response({'id':'67890','type':1} if method=='GET' else {'id':'999999'})
    monkeypatch.setattr(aiohttp.ClientSession,'_request',request)
    worker.tick(2)
    ref=s.store.items()[0]['reference']
    root=Path(__file__).resolve().parents[1]
    ctx=PluginContext(parse_manifest_file(root/'plugin.yaml',root,'project',''),create.manager)
    import email_steward.plugin as plugin
    monkeypatch.setattr(plugin, 'service_from_host', lambda _: s)
    plugin.register(ctx)
    handler=create.manager._plugin_commands['email-steward']['handler']
    import time
    from datetime import datetime, timezone
    now = int(time.time())
    due, wake = now + 3600, now + 7200
    iso = lambda epoch: datetime.fromtimestamp(epoch, timezone.utc).isoformat()
    replies = []
    def command(text):
        before = len(calls)
        result = invoke_plugin_command(handler, text, source=create.source)
        assert result and 'Details:' not in result, (text, result)
        assert len(calls) == before
        replies.append(result)
    for text in ('list', 'rules', 'packs', f'inspect {ref} text'):
        command(text)
    command(f'waiting {ref} {iso(due)}')
    assert s.store.item(ref)['classification'] == 'waiting' and s.store.item(ref)['reminder_at'] == due
    command(f'snooze {ref} {iso(wake)}')
    assert s.store.item(ref)['snooze_until'] == wake and 'INBOX' not in provider.messages['m1']['labels']
    command(f'remind {ref} {iso(due)}')
    assert s.store.item(ref)['reminder_at'] == due
    command(f'restore {ref}')
    assert 'INBOX' in provider.messages['m1']['labels'] and s.store.item(ref)['classification'] == 'waiting'
    command(f'archive {ref}')
    assert 'INBOX' not in provider.messages['m1']['labels'] and s.store.item(ref)['classification'] == 'waiting'
    s.store.outbox(f'reminder:{ref}:queued', now, 'Synthetic pending reminder', 'reminder')
    command(f'done {ref}')
    item = s.store.item(ref)
    assert item['classification'] == 'done' and item['reminder_at'] is None and item['snooze_until'] is None
    assert s.store.rows("SELECT state FROM outbox WHERE id=?", (f'reminder:{ref}:queued',))[0]['state'] == 'cancelled'
    assert provider.messages['m1']['unread'] and 'Triaged' in provider.messages['m1']['labels']
    assert any('PRIVATE-INSPECTION-ONLY' in p for p in replies)
    assert all('PRIVATE-INSPECTION-ONLY' not in row['text'] for row in s.store.rows('SELECT text FROM outbox'))
    before=len(calls)
    denied=invoke_plugin_command(handler,'list',source=replace_source(create.source,user_id='foreign'))
    assert 'forbidden' in denied and len(calls)==before


def test_actual_cli_setup_monotonic_regrant_and_partial_failure(route, capsys):
    create, calls, monkeypatch = route
    s, adapter, module, delivery = create('discord','67890')
    import argparse
    from email_steward.plugin import setup_cli, cli
    from email_steward.runtime import settings_from_host
    from hermes_cli.plugins import PluginContext
    from hermes_cli.plugins_manifest import parse_manifest_file
    root=Path(__file__).resolve().parents[1]
    ctx=PluginContext(parse_manifest_file(root/'plugin.yaml',root,'project',''),create.manager)
    parser=argparse.ArgumentParser(); setup_cli(parser)
    args=parser.parse_args(['setup','--platform','discord','--owner','12345','--destination','67890',
        '--type','dm','--account','custom:discord','--transport-profile','custom','--transport-home',str(s.settings.home),
        '--confirm-private','--timezone','UTC'])
    cli(ctx,args); first=settings_from_host(ctx); assert first.grant_revision==1
    cli(ctx,args); assert settings_from_host(ctx).grant_revision==2
    writer=ctx.set_config
    def fail(key,value):
        if key=='destination': raise RuntimeError('Synthetic interrupted host config write')
        writer(key,value)
    monkeypatch.setattr(ctx,'set_config',fail)
    with pytest.raises(RuntimeError): cli(ctx,args)
    assert settings_from_host(ctx).private_confirmed is False
    assert Store(s.settings.home/'plugin-data/email-steward').meta('gateway_revision_floor')==3
    assert calls==[]
