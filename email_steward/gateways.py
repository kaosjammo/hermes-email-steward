"""Pinned native capabilities and authority. No transport SDK or network implementation."""
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from .errors import Error, invalid


@dataclass(frozen=True)
class Capability:
    mode: str
    types: tuple = ()
    threads: bool = False
    reason: str = "Explicit private grant and native activation required"


# Canonical core + bundled platforms at Hermes b63eb8bf. Not a plugin discovery allow-all.
CAPABILITIES = {
    **{p: Capability("internal", reason="Internal ingress/session surface; no private notification route")
       for p in ("a2a", "api_server", "local", "msgraph_webhook", "raft", "webhook")},
    "dingtalk": Capability("unsafe", reason="Default sender ignores chat_id in favour of static webhook"),
    "qqbot": Capability("unsafe", reason="Default sender probes different recipient scenes and can truncate"),
    "relay": Capability("experimental", reason="Authenticated connector capability grant not available here"),
    "email": Capability("restricted", reason="Host SMTP ignores refusal mapping and lacks notification provenance/intake-alias loop guard"),
    "irc": Capability("restricted", reason="Nick-only actor and writer-drain acknowledgement do not establish private recipient acceptance"),
    "simplex": Capability("restricted", reason="Daemon-local contact IDs omit receiving account proof; default text sender is fire-and-forget"),
    "ntfy": Capability("notification", ("topic",), reason="Host fabricates missing publish IDs; send outcome remains uncertain, never a complete receipt. Topic is not human identity."),
    "discord": Capability("interactive", ("dm", "group", "channel", "thread"), True),
    "telegram": Capability("notification", ("dm",), reason="Positive numeric private-chat route only; topics retry into parent and command source cannot exclude actor fallback"),
    "slack": Capability("interactive", ("dm", "group", "channel"), True),
    "matrix": Capability("interactive", ("dm", "group", "channel"), True),
    "buzz": Capability("interactive", ("dm", "group", "channel"), reason="Thread mode can discard root; flat route only"),
    "feishu": Capability("interactive", ("dm", "group")),
    "google_chat": Capability("interactive", ("dm",), reason="Thread fallback relocates messages; main-flow DM only, no stale thread/typing context"),
    "mattermost": Capability("interactive", ("dm", "group", "channel"), reason="Live reply failure flattens thread; flat route only"),
    "teams": Capability("interactive", ("dm", "group", "channel")),
    "line": Capability("interactive", ("dm", "group", "room"), reason="Postback absorption is blocked; host push drops its response/ID, so outcome remains uncertain"),
    "sms": Capability("interactive", ("dm",), reason="Signed provider phone identity; shared/reassigned numbers and push previews remain operator risks"),
    "signal": Capability("interactive", ("dm", "group"), reason="Host standalone loses RPC receipts/errors; notification outcome remains uncertain, never complete"),
    "photon": Capability("notification", ("dm", "group"), reason="Notification-only: native command source cannot distinguish a genuine actor from conversation fallback. Use granted Desktop/CLI management."),
    "bluebubbles": Capability("notification", ("dm", "group"), reason="Notification-only: native command source cannot distinguish a genuine actor from conversation fallback. Use granted Desktop/CLI management."),
    "wecom": Capability("interactive", ("dm",), reason="Groups require passive req_id and can fall back to a different proactive scene; DM only"),
    "wecom_callback": Capability("interactive", ("dm",), reason="Exactly one explicitly bound callback app required; ambiguous/multiple app fallback blocked"),
    "weixin": Capability("interactive", ("dm",), reason="No multiline splitting; host exposes a generated correlation ID, so outcome remains uncertain"),
    "whatsapp": Capability("restricted", reason="Default standalone bridge accepts missing session ownership; legacy bridge cannot prove receiving profile/account"),
    "whatsapp_cloud": Capability("interactive", ("dm",)),
    "yuanbao": Capability("interactive", ("dm",), reason="Live profile-owned active adapter required; DM only. Host ACK parser lacks provider-status validation; outcome remains uncertain"),
}

GRANT_FIELDS = ("platform", "owner", "destination", "destination_type", "thread", "parent",
    "scope", "account", "route_context", "transport_profile", "transport_home", "profile", "home", "private_confirmed", "host_config_version")

# Only PUBLIC account/server identifiers. No tokens, passwords, secret files or general
# object introspection. Empty means the profile's unique native slot plus native scope/ID.
CONTEXT_FIELDS = {
    "ntfy": ("server",), "signal": ("account", "http_url"), "mattermost": ("url",),
    "bluebubbles": ("server_url",), "wecom": ("bot_id", "websocket_url"), "weixin": ("account_id", "base_url"),
    "sms": ("account_sid", "from_number"), "whatsapp_cloud": ("phone_number_id",),
    "teams": ("client_id",), "feishu": ("app_id",), "google_chat": ("project_id",),
    "photon": ("project_id",), "whatsapp": ("bridge_port",),
    "wecom_callback": ("corp_id", "agent_id"), "yuanbao": ("app_id",), "buzz": ("cli_path", "relay_url"),
    "matrix": ("homeserver", "user_id"),
}

DEPENDENCIES = {
    "discord": ("discord", "aiohttp"), "telegram": ("telegram",),
    "slack": ("slack_sdk", "slack_bolt", "aiohttp"), "matrix": ("mautrix", "aiohttp"),
    "feishu": ("lark_oapi",), "google_chat": ("google.auth", "googleapiclient", "google.cloud.pubsub_v1", "google_auth_httplib2", "httplib2"),
    "teams": ("microsoft_teams.apps", "aiohttp"), "line": ("aiohttp",), "mattermost": ("aiohttp",),
    "sms": ("aiohttp",), "signal": ("aiohttp", "wcwidth"), "ntfy": ("httpx",),
    "bluebubbles": ("httpx", "aiohttp"), "photon": ("httpx", "aiohttp"),
    "wecom": ("aiohttp",), "weixin": ("aiohttp", "cryptography"),
    "whatsapp": ("aiohttp",), "whatsapp_cloud": ("aiohttp", "httpx"),
    "wecom_callback": ("aiohttp", "httpx", "cryptography"), "yuanbao": ("websockets",),
}


def missing_dependencies(platform):
    missing = []
    for module in DEPENDENCIES.get(platform, ()):
        try:
            present = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError, AttributeError):
            present = False
        if not present:
            missing.append(module)
    return missing


def context(settings):
    try:
        value = json.loads(settings.route_context)
    except (TypeError, ValueError):
        raise invalid("route_context must be a JSON object of the required public identifiers") from None
    if (not isinstance(value, dict) or set(value) != set(CONTEXT_FIELDS.get(settings.platform, ()))
            or any(not isinstance(v, str) or not 1 <= len(v) <= 512
                   or any(ord(c) < 33 or unicodedata.category(c) == "Cf" for c in v) for v in value.values())):
        raise invalid("Supply exactly the platform's required public route_context fields; no credentials")
    for key, item in value.items():
        if key in {"url", "server", "homeserver", "http_url", "server_url", "websocket_url", "base_url", "relay_url"}:
            try:
                parsed = urlsplit(item)
            except ValueError:
                raise invalid("Invalid public server URL") from None
            if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise invalid("Public server URLs must not contain credentials, query secrets or fragments")
        elif key == "cli_path":
            if not Path(item).is_absolute():
                raise invalid("Select an explicit absolute native CLI path")
        elif any(c in item for c in "/\\") or ".." in item:
            raise invalid("Public account identifiers cannot be paths")
    return value


def route_context_matches(settings, config, adapter):
    """Compare supported actual host public fields at admission/effect; never infer an account."""
    expected = context(settings)
    if not expected:
        return True
    extra = config.extra
    values = {k: str(extra.get(k, "")) for k in expected}
    attrs = {
        "ntfy": {"server": "_server"},
        "signal": {"account": "account", "http_url": "http_url"},
        "bluebubbles": {"server_url": "server_url"}, "weixin": {"account_id": "_account_id", "base_url": "_base_url"},
        "teams": {"client_id": "_client_id"}, "photon": {"project_id": "_project_id"},
        "whatsapp": {"bridge_port": "_bridge_port"},
        "wecom": {"bot_id": "_bot_id", "websocket_url": "_ws_url"},
        "whatsapp_cloud": {"phone_number_id": "_phone_number_id"},
        "yuanbao": {"app_id": "_app_key"}, "buzz": {"cli_path": "cli_path", "relay_url": "relay_url"},
        "matrix": {"homeserver": "_homeserver", "user_id": "_user_id"},
    }
    if settings.platform in attrs:
        if adapter is None:
            return False
        values = {key: str(getattr(adapter, attr, "")) for key, attr in attrs[settings.platform].items()}
        if any(str(extra.get(key, "")) != value for key, value in expected.items()):
            return False
    if settings.platform == "sms":
        from agent.secret_scope import get_secret
        values = {"account_sid": get_secret("TWILIO_ACCOUNT_SID", ""), "from_number": get_secret("TWILIO_PHONE_NUMBER", "")}
    if settings.platform == "wecom_callback":
        apps = getattr(adapter, "_apps", ()) if adapter is not None else ()
        if len(apps) != 1:
            return False
        values = {key: str(apps[0].get(key, "")) for key in expected}
        if values != expected:
            return False
        # Re-evaluate the fresh config too; the default sender must never choose a
        # first/legacy app from a different configuration than the receiving adapter.
        configured = adapter._normalize_apps(extra)
        return len(configured) == 1 and all(str(configured[0].get(k, "")) == v for k, v in expected.items())
    return values == expected


def capability(platform):
    if platform not in CAPABILITIES:
        raise Error("unsupported_platform", "Unknown external platform is not authorised.", 403)
    return CAPABILITIES[platform]


def binding(settings):
    return {key: str(getattr(settings, key)) if key in {"home", "transport_home"} else getattr(settings, key)
            for key in GRANT_FIELDS}


def fingerprint(settings):
    return hashlib.sha256(json.dumps(binding(settings), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(settings):
    cap = capability(settings.platform)
    if cap.mode not in {"interactive", "notification"}:
        raise Error("unsupported_route", cap.reason, 403)
    if not settings.grant_revision and (settings.platform != "discord" or settings.thread is not None
            or settings.destination_type not in {"dm", "channel"}):
        raise Error("setup_required", "Legacy migration is Discord/no-thread only; explicitly select a new versioned native grant.", 403)
    if settings.destination_type not in cap.types or (settings.thread and not cap.threads):
        raise Error("unsupported_route", "This exact chat type/thread has no safe native route. " + cap.reason, 403)
    if settings.thread is not None and (not settings.thread or not isinstance(settings.thread, str)):
        raise invalid("Thread must be an exact native identifier or null")
    if settings.grant_revision:
        if (settings.transport_profile != settings.profile or settings.transport_home != str(settings.home)
                or settings.account != settings.profile + ":" + settings.platform):
            raise Error("grant_scope", "Select the owning profile's exact native credential slot; cross-profile transport forwarding is refused.", 403)
        context(settings)
    for key in ("owner", "destination", "scope", "account", "parent", "thread"):
        value = getattr(settings, key)
        if value is not None and (not isinstance(value, str) or len(value) > 512
                or any(ord(c) < 33 or ord(c) == 127 or unicodedata.category(c) == "Cf" for c in value)):
            raise invalid("Use bounded native identifiers without whitespace or control characters")
    target = settings.destination
    if settings.owner.casefold() in {"unknown", "anonymous", "system", "bot", "none", "null"}:
        raise invalid("Anonymous/service fallback identities cannot own Email Steward")
    if (settings.platform in {"slack", "matrix", "teams"}
            or settings.platform == "discord" and settings.destination_type in {"channel", "thread"}) and not settings.scope:
        raise invalid("This platform/chat requires its exact native tenant/workspace/server/guild scope")
    if target.lower() in {"home", "default"} or target.startswith(("@", "#")) and settings.platform != "matrix":
        raise invalid("Select an exact native destination, never a display name or Home")
    if settings.platform in {"discord", "telegram", "whatsapp_cloud"} and not re.fullmatch(r"-?\d+", target):
        raise invalid("This gateway requires an exact numeric conversation identifier")
    if settings.platform == "telegram" and not target.isdigit():
        raise invalid("Select a positive exact Telegram private-chat ID; group/type ambiguity is unsupported")
    if settings.platform == "slack" and not re.fullmatch(r"[DCG][A-Z0-9]{8,}", target):
        raise invalid("Use an exact Slack conversation ID, not a user/name target")
    if settings.platform == "whatsapp" and target.endswith(("@broadcast", "@newsletter")):
        raise invalid("Broadcast/newsletter destinations are forbidden")
    if settings.platform == "bluebubbles" and (target.count(";") < 2 or target.split(";", 1)[0] not in {"iMessage", "SMS", "RCS"}):
        raise invalid("Use the observed exact BlueBubbles chat GUID; handle-to-new-chat fallback is forbidden")
    if settings.platform == "wecom_callback" and (target != context(settings)["corp_id"] + ":" + settings.owner
            or any(c in settings.owner for c in "|:;/*") or settings.owner.casefold() == "@all"):
        raise invalid("Select exactly one corp-qualified human callback user, never a recipient list")
    if settings.platform == "yuanbao" and target != "direct:" + settings.owner:
        raise invalid("Select the owner's exact Yuanbao direct conversation")
    if settings.platform == "feishu" and not target.startswith("oc_"):
        raise invalid("Use the exact observed Feishu chat ID, not an alias/user-to-new-DM target")
    if settings.platform == "signal" and target.startswith("group:") != (settings.destination_type == "group"):
        raise invalid("Signal group/DM target must match the explicitly selected chat type")
    if settings.platform == "weixin" and target == "filehelper":
        raise invalid("filehelper is not an owner-private conversation grant")
    if settings.platform == "ntfy" and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", target):
        raise invalid("Select one exact ntfy topic, without URL/path/header syntax")
    return cap


def native_target(settings):
    validate(settings)
    ref = settings.destination + (":" + settings.thread if settings.thread else "")
    return settings.platform + ":" + ref


def native_access(settings, source):
    """Only actual off-wire receiving identity, never reconstructed model-tool environment."""
    from .security import Access
    from gateway.session import SessionSource
    from gateway.session_identity import identity_of
    settings.require_private()
    cap = validate(settings)
    if cap.mode != "interactive":
        raise Error("principal_unavailable", cap.reason + " Private native commands are unavailable; use granted Desktop/CLI management.", 403)
    identity = identity_of(source)
    platform = getattr(getattr(source, "platform", None), "value", None)
    adapter = identity.adapter() if identity else None
    if (not isinstance(source, SessionSource) or cap.mode != "interactive" or platform != settings.platform
            or source.is_bot or not source.user_id or source.user_id != settings.owner
            or source.chat_id != settings.destination or source.chat_type != settings.destination_type
            or source.thread_id != settings.thread or source.parent_chat_id != (settings.parent or None)
            or (source.scope_id or "") != settings.scope or source.profile_route_rejected
            or source.profile not in {None, settings.profile}
            or source.delivered_via_upstream_relay or source.detached_route
            or identity is None or identity.transport_inferred or adapter is None
            or identity.runtime_home.resolve() != settings.home or identity.runtime_profile != settings.profile
            or identity.authorization_home.resolve() != Path(settings.transport_home or settings.home).resolve()
            or identity.transport_profile != (settings.transport_profile or settings.profile)
            or getattr(getattr(adapter, "platform", None), "value", None) != settings.platform
            or (getattr(adapter, "_owner_profile", None) or settings.profile) != settings.profile):
        raise Error("forbidden", "Use the selected platform-qualified owner's exact private native source and receiving profile.", 403)
    if settings.grant_revision and not route_context_matches(settings, adapter.config, adapter):
        raise Error("account_mismatch", "The native receiving transport's public account/server context changed.", 403)
    return Access(settings.home, settings.owner, settings.platform, fingerprint(settings), settings.grant_revision)


def inventory():
    return [{"platform": p, "mode": c.mode, "chat_types": list(c.types), "threads": c.threads,
             "public_context_fields": list(CONTEXT_FIELDS.get(p, ())),
             "missing_dependencies": missing_dependencies(p),
             "limitation": c.reason, "live_activation": "UNRUN"} for p, c in sorted(CAPABILITIES.items())]
