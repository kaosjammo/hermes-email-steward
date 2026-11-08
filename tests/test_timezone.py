"""Configured profile timezone inheritance; no location or process-local fallback."""
from datetime import datetime
from pathlib import Path
import os
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from email_steward.errors import Error
from email_steward.runtime import settings_from_host
from email_steward.scheduling import due_slots


@pytest.fixture
def host(tmp_path, monkeypatch):
    upstream = Path(os.environ.get("HERMES_UPSTREAM", Path(__file__).resolve().parents[2]))
    if not (upstream / "hermes_constants.py").exists():
        pytest.skip("read-only Hermes SDK required for effective profile config test")
    monkeypatch.syspath_prepend(str(upstream))
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    import hermes_cli.config
    config = {"timezone": "America/New_York"}
    monkeypatch.setattr(hermes_cli.config, "load_config_readonly", lambda: config)
    token = set_hermes_home_override(str(tmp_path))
    try:
        yield config
    finally:
        reset_hermes_home_override(token)


def test_profile_timezone_inherited_and_next_brief_is_not_melbourne(host):
    settings = settings_from_host()
    assert settings.timezone == "America/New_York"
    zone = ZoneInfo("America/New_York")
    before = datetime(2026, 11, 5, 6, 59, tzinfo=zone).timestamp()
    after = datetime(2026, 11, 5, 7, 1, tzinfo=zone).timestamp()
    slots = due_slots(settings, before, after)
    assert len(slots) == 1 and ":07:00" in slots[0][1]
    assert datetime.fromtimestamp(slots[0][0], zone).hour == 7


def test_explicit_plugin_timezone_overrides_profile_for_ctx_and_rest(host):
    host["plugins"] = {"entries": {"email-steward": {"settings": {"timezone": "Europe/London"}}}}
    assert settings_from_host().timezone == "Europe/London"
    ctx = SimpleNamespace(profile_name="custom", get_config=lambda key, default=None: "Asia/Tokyo" if key == "timezone" else default)
    settings = settings_from_host(ctx)
    assert settings.timezone == "Asia/Tokyo"
    zone = ZoneInfo("Asia/Tokyo")
    slots = due_slots(settings, datetime(2026, 11, 5, 6, tzinfo=zone).timestamp(), datetime(2026, 11, 5, 8, tzinfo=zone).timestamp())
    assert len(slots) == 1 and datetime.fromtimestamp(slots[0][0], zone).hour == 7


@pytest.mark.parametrize("timezone", ["Unknown/Invalid", 42, None, {"zone": "UTC"}])
def test_malformed_profile_timezone_refuses_scheduling_without_fallback(host, timezone):
    host["timezone"] = timezone
    with pytest.raises(Error):
        settings_from_host()


def test_unconfigured_timezone_requires_explicit_configuration_before_scheduling(host):
    host["timezone"] = ""
    settings = settings_from_host()
    assert settings.timezone == ""
    with pytest.raises(Error, match="timezone"):
        due_slots(settings, 1000, 1100)
