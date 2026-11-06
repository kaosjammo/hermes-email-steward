"""Authority comes from host transport state plus operator profile configuration."""
from dataclasses import dataclass, field
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from .errors import Error, invalid


@dataclass(frozen=True)
class Settings:
    home: Path
    profile: str
    owner: str = ""
    destination: str = ""
    destination_type: str = "dm"
    private_confirmed: bool = False
    desktop_subject: str = ""
    desktop_session_user: str = ""
    desktop_session_provider: str = ""
    desktop_session_issuer: str = ""
    desktop_local_token: bool = False
    model_consent: str = ""
    timezone: str = ""
    briefs: tuple[str, ...] = ("07:00", "11:00", "20:00")
    quiet_start: str = ""
    quiet_end: str = ""
    quiet_bypass: tuple[str, ...] = ("danger", "security")
    important_contacts: tuple[str, ...] = ()
    poll_seconds: int = 60
    platform: str = "discord"
    thread: str | None = None
    parent: str = ""
    scope: str = ""
    account: str = ""
    transport_profile: str = ""
    transport_home: str = ""
    grant_revision: int = 0
    route_context: str = "{}"
    host_config_version: str = ""

    def __post_init__(self):
        object.__setattr__(self, "home", Path(self.home).resolve())
        for key in ("owner", "destination", "destination_type", "desktop_subject", "desktop_session_user", "desktop_session_provider", "desktop_session_issuer", "timezone", "platform", "parent", "scope", "account", "transport_profile", "transport_home", "host_config_version"):
            if not isinstance(getattr(self, key), str):
                raise invalid("Identity and timezone configuration must be strings")
        if type(self.poll_seconds) is not int:
            raise invalid("poll_seconds must be an integer")
        if type(self.grant_revision) is not int or self.grant_revision < 0:
            raise invalid("grant_revision must be a nonnegative integer")
        if not isinstance(self.route_context, str) or len(self.route_context) > 4096:
            raise invalid("route_context must be a bounded JSON string containing public identifiers")
        try:
            import json
            object.__setattr__(self, "route_context", json.dumps(json.loads(self.route_context), sort_keys=True, separators=(",", ":")))
        except (TypeError, ValueError):
            raise invalid("route_context must be valid JSON") from None
        if self.thread is not None and (not isinstance(self.thread, str) or not self.thread):
            raise invalid("thread must be an exact identifier or null")
        for key in ("briefs", "quiet_bypass", "important_contacts"):
            value = getattr(self, key)
            if not isinstance(value, (list, tuple)) or len(value) > 24 or any(not isinstance(v, str) for v in value):
                raise invalid("Schedule/contact configuration must be bounded lists of strings")
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except (KeyError, ValueError):
                raise invalid("Configure a valid IANA timezone", timezone="Unknown timezone") from None
        if not 15 <= self.poll_seconds <= 240:
            raise invalid("poll_seconds must be 15–240")
        for value in (*self.briefs, self.quiet_start, self.quiet_end):
            if value:
                clock_minutes(value)
        if bool(self.quiet_start) != bool(self.quiet_end):
            raise invalid("quiet hours need both start and end")

    def require_schedule(self):
        if not self.timezone:
            raise invalid("Configure the Hermes profile timezone or an explicit Email Steward timezone before scheduling", timezone="Timezone is required")

    def require_private(self):
        if (not self.owner or not self.destination or self.private_confirmed is not True
                or self.destination_type not in {"dm", "group", "channel", "thread", "room", "topic"}):
            raise Error("private_destination_required", "Configure and explicitly confirm the owner's private destination.", 403)
        if self.grant_revision or self.platform != "discord":
            from .gateways import validate
            validate(self)


def clock_minutes(value):
    try:
        h, m = value.split(":")
        if len(h) != 2 or len(m) != 2 or not (0 <= int(h) < 24 and 0 <= int(m) < 60):
            raise ValueError
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        raise invalid("Use HH:MM local time") from None


@dataclass(frozen=True)
class Access:
    home: Path
    owner: str
    surface: str
    grant: str = ""
    revision: int = 0


def require_access(settings, access):
    settings.require_private()
    if not isinstance(access, Access) or access.home != settings.home or access.owner != settings.owner:
        raise Error("forbidden", "Owner access for this profile is required.", 403)
    if access.grant:
        from .gateways import fingerprint
        if access.grant != fingerprint(settings) or access.revision != settings.grant_revision:
            raise Error("grant_revoked", "The selected native grant changed; repeat from its current authorised source.", 403)


def discord_access(settings, source):
    # Compatibility import name only; no weaker legacy principal admission.
    from .gateways import native_access
    return native_access(settings, source)


def desktop_access(settings, request):
    settings.require_private()
    grant = getattr(request.state, "native_http_principal", None)
    if isinstance(grant, dict) and settings.desktop_subject:
        if (grant.get("subject") == settings.desktop_subject and grant.get("purpose") == "native-http"
                and grant.get("scope") == "profile" and grant.get("profile_id") == str(settings.home)
                and set(grant.get("capabilities", ())) == {"http:owner"}):
            return Access(settings.home, settings.owner, "desktop-native")
    session = getattr(request.state, "session", None)
    if session is not None and settings.desktop_session_user and settings.desktop_session_provider:
        from hermes_cli.dashboard_auth.base import Session
        if (isinstance(session, Session) and session.user_id == settings.desktop_session_user
                and session.provider == settings.desktop_session_provider
                and session.issuer == settings.desktop_session_issuer and session.expires_at > time.time()):
            return Access(settings.home, settings.owner, "desktop-session")
    if settings.desktop_local_token is True:
        # Verify the actual host credential anew. A request.state boolean is never authority.
        from hermes_cli.web_server import _has_valid_session_token
        if _has_valid_session_token(request):
            return Access(settings.home, settings.owner, "desktop-token")
    raise Error("unauthenticated", "An explicitly granted verified Hermes host identity is required.", 401)
