"""Production cron handoff contracts. Fixtures never select a real mailbox."""
import json
from dataclasses import replace

import pytest

from email_steward.errors import Error
from test_backend import env


class CronContext:
    def __init__(self, home):
        self.home = home
        self.jobs = []
        self.calls = []

    def dispatch_tool(self, name, args):
        assert name == "cronjob_manage"
        self.calls.append(dict(args))
        if args["action"] == "create":
            job = {**args, "job_id": "synthetic-cron", "enabled": False}
            self.jobs.append(job)
            return json.dumps({"success": True, "job_id": job["job_id"]})
        if args["action"] == "resume":
            self.jobs[0]["enabled"] = True
            return json.dumps({"success": True})
        if args["action"] == "remove":
            self.jobs = [j for j in self.jobs if j["job_id"] != args["job_id"]]
            return json.dumps({"success": True})
        assert args["action"] == "list"
        return json.dumps({"success": True, "jobs": self.jobs})


def test_owner_schedule_produces_real_urgent_and_reminder_content_without_send_receipt(env, monkeypatch):
    from email_steward.cron_delivery import install_schedule, cron_tick
    service, _, provider, _, access, _ = env
    ctx = CronContext(service.settings.home)
    monkeypatch.setattr("email_steward.cron_delivery.prepare_tools", lambda: None)
    binding = install_schedule(ctx, service)
    assert ctx.jobs[0]["no_agent"] is True
    assert ctx.jobs[0]["deliver"] == "discord:67890"
    assert ctx.jobs[0]["attach_to_session"] is False
    assert ctx.jobs[0]["enabled"] is True
    provider.add("alert", subject="Security alert", body="Suspicious sign-in. Please review today.")
    output = cron_tick(ctx, service, binding["key"], service.settings.home, now=1000)
    assert "Suspicious sign-in" in output and "https://mail.google.com/" in output
    rows = service.store.rows("SELECT * FROM outbox")
    assert rows and all(row["state"] == "handed_to_cron" for row in rows)
    assert not any(row["state"] in {"sent", "accepted"} for row in rows)
    assert cron_tick(ctx, service, binding["key"], service.settings.home, now=1001) == ""
    item = service.store.item("ax1")
    item.update(reminder_at=1002, schedule_grant=service.store.active_grant)
    service.store.put_item(service.store.account("gmail-1"), item["thread_id"], item)
    ctx.jobs[0].update(last_run_at="synthetic-completed", last_status="delivery_failed",
                       last_delivery_error="Synthetic transport failure")
    output = cron_tick(ctx, service, binding["key"], service.settings.home, now=1003)
    assert "Reminder" in output and "Suspicious sign-in" in output
    assert service.store.item("ax1")["classification"] == "needs_action"
    assert service.store.item("ax1")["reminder_at"] is None
    assert all(row["state"] not in {"sent", "accepted"} for row in service.store.rows("SELECT * FROM outbox"))


@pytest.mark.parametrize("change", ["destination", "profile", "home", "binding", "job-target", "job-disabled"])
def test_cron_refuses_changed_authority_before_any_provider_call(env, monkeypatch, change):
    from email_steward.cron_delivery import install_schedule, cron_tick
    service, _, provider, _, _, _ = env
    ctx = CronContext(service.settings.home)
    monkeypatch.setattr("email_steward.cron_delivery.prepare_tools", lambda: None)
    binding = install_schedule(ctx, service)
    key, home = binding["key"], service.settings.home
    if change == "destination":
        service.settings = replace(service.settings, destination="99999")
    elif change == "profile":
        service.settings = replace(service.settings, profile="foreign")
    elif change == "home":
        home = home / "foreign"
    elif change == "binding":
        key = "foreign"
    elif change == "job-target":
        ctx.jobs[0]["deliver"] = "discord:99999"
    else:
        ctx.jobs[0]["enabled"] = False
    def forbidden(*args):
        raise AssertionError("Provider must not be selected on denied cron authority")
    service.provider_factory = forbidden
    with pytest.raises(Error):
        cron_tick(ctx, service, key, home, now=1000)


def test_explicit_schedule_replacement_preserves_history_and_blocks_old_grant(env, monkeypatch):
    from email_steward.cron_delivery import install_schedule, cron_tick
    service = env[0]
    ctx = CronContext(service.settings.home)
    monkeypatch.setattr("email_steward.cron_delivery.prepare_tools", lambda: None)
    old = install_schedule(ctx, service)
    service.store.outbox("historical", 1, "Old destination summary")
    service.settings = replace(service.settings, destination="99999")
    with pytest.raises(Error):
        install_schedule(ctx, service)
    fresh = install_schedule(ctx, service, replace_existing=True)
    assert fresh["key"] != old["key"] and len(ctx.jobs) == 1
    assert ctx.jobs[0]["deliver"] == "discord:99999"
    assert cron_tick(ctx, service, fresh["key"], service.settings.home, now=2) == ""
    assert service.store.rows("SELECT state FROM outbox WHERE id='historical'") == [{"state": "blocked"}]


@pytest.mark.parametrize("field,value", [("deliver", "discord:99999"), ("schedule", "every 5m"), ("name", "Other purpose")])
def test_schedule_replacement_refuses_an_operator_edited_job(env, monkeypatch, field, value):
    from email_steward.cron_delivery import install_schedule
    service = env[0]
    ctx = CronContext(service.settings.home)
    monkeypatch.setattr("email_steward.cron_delivery.prepare_tools", lambda: None)
    old = install_schedule(ctx, service)
    ctx.jobs[0][field] = value
    with pytest.raises(Error):
        install_schedule(ctx, service, replace_existing=True)
    assert service.store.meta("cron_binding") == old
    assert not any(call["action"] == "remove" for call in ctx.calls)


@pytest.mark.parametrize("change", ["grant", "job", "quiet"])
def test_authority_is_rechecked_after_selection_before_export(env, monkeypatch, change):
    from email_steward.cron_delivery import install_schedule, cron_tick
    service = env[0]
    ctx = CronContext(service.settings.home)
    monkeypatch.setattr("email_steward.cron_delivery.prepare_tools", lambda: None)
    binding = install_schedule(ctx, service)
    service.store.outbox("selected", 1, "Private queued text", category="brief")
    original = service.store.rows
    def rows(sql, args=()):
        found = original(sql, args)
        if "ORDER BY CASE" in sql:
            if change == "grant":
                service.settings = replace(service.settings, private_confirmed=False)
            elif change == "job":
                ctx.jobs[0]["deliver"] = "discord:99999"
            else:
                service.settings = replace(service.settings, quiet_start="00:00", quiet_end="23:59")
        return found
    monkeypatch.setattr(service.store, "rows", rows)
    if change == "quiet":
        assert cron_tick(ctx, service, binding["key"], service.settings.home, now=2) == ""
    else:
        with pytest.raises(Error):
            cron_tick(ctx, service, binding["key"], service.settings.home, now=2)
    assert original("SELECT state FROM outbox WHERE id='selected'") == [{"state":"pending"}]
    assert not service.store.meta("cron_last_handoff")
