"""Profile-bound runtime composition. No provider calls or worker start on import."""
from pathlib import Path
import hashlib
import json

from .errors import Error
from .security import Settings
from .service import Steward
from .store import Store
from .judgement import HermesModel


def settings_from_host(ctx=None):
    from hermes_constants import get_hermes_home
    from hermes_cli.profiles import get_active_profile_name
    from hermes_cli.config import load_config_readonly
    home = get_hermes_home().resolve()
    # Top-level `timezone` is the supported effective profile configuration source
    # (hermes_time.py/config_defaults.py). No inferred location or server-local fallback.
    config = load_config_readonly() or {}
    if ctx is not None:
        read = ctx.get_config
    else:
        entry = config.get("plugins", {}).get("entries", {}).get("email-steward", {})
        settings = entry.get("settings", entry.get("config", {}))
        read = lambda key, default=None: settings.get(key, default)
    names = {"owner", "destination", "destination_type", "private_confirmed", "desktop_subject",
        "desktop_session_user", "desktop_session_provider", "desktop_session_issuer", "desktop_local_token",
        "timezone", "briefs", "quiet_start", "quiet_end", "quiet_bypass", "important_contacts", "poll_seconds",
        "platform", "thread", "parent", "scope", "account", "route_context", "transport_profile", "transport_home", "grant_revision"}
    defaults = Settings(home=home, profile=get_active_profile_name())
    values = {key: read(key, getattr(defaults, key)) for key in names}
    if values["thread"] == "":
        values["thread"] = None
    if values["timezone"] == "":
        values["timezone"] = config.get("timezone", "")
    for key in ("briefs", "quiet_bypass", "important_contacts"):
        values[key] = tuple(values[key])
    # A supported backend token detects unobserved switch-away/back writes too.
    # Conservatively any user-layer edit revokes queued authority. No config watcher,
    # private history, global mutation or additional host permission API is needed.
    from hermes_cli.config_backend import config_version_or_none
    version = config_version_or_none(home / "config.yaml")
    epoch = hashlib.sha256(json.dumps(version, default=str).encode()).hexdigest()
    return Settings(home=home, profile=get_active_profile_name(), host_config_version=epoch, **values)


def service_from_host(ctx=None):
    settings = settings_from_host(ctx)
    store = Store(settings.home / "plugin-data" / "email-steward")
    if ctx is None:
        # REST never needs the model, so no ambient active agent lookup occurs here.
        return Steward(store, settings, settings_reader=lambda: settings_from_host())
    return Steward(store, settings, model=HermesModel(ctx), settings_reader=lambda: settings_from_host(ctx))
