"""Owner-created script-only cron delivery through public Hermes contracts.

The plugin emits bounded text; Hermes owns transport and its delivery history.
Emission is a handoff, never a provider or human receipt.
"""
import hashlib
import json
from pathlib import Path
import time
import uuid

from .errors import Error
from .gateways import fingerprint, native_target
from .scheduling import quiet
from .store import private_dir
from .worker import Worker

# Leave room below the host's 4000-character non-chunking transport limit for
# its normal header/footer. Further parts stay durable for the following tick.
MAX_BATCH_BYTES = 3000
FOOTER = "Email Steward · handed to Hermes cron; delivery confirmation is host-owned."


def prepare_tools():
    from tools.registry import discover_builtin_tools, registry
    if registry.get_entry("cronjob_manage") is None:
        discover_builtin_tools()


def cron_call(ctx, **args):
    prepare_tools()
    result = ctx.dispatch_tool("cronjob_manage", args)
    if isinstance(result, str):
        result = json.loads(result)
    if not isinstance(result, dict) or result.get("success") is not True:
        raise Error("cron_unavailable", "Hermes cron operation failed; inspect the owning profile's cron status.", 503)
    return result


def current_job(ctx, binding):
    result = cron_call(ctx, action="list", include_disabled=True)
    jobs = [j for j in result.get("jobs", []) if j.get("job_id") == binding["job_id"]]
    if len(jobs) != 1:
        raise Error("cron_binding", "The owner-created Email Steward cron job is missing.", 403)
    return jobs[0]


def wrapper(home, profile, key):
    # main is Hermes' public console entrypoint. Explicit profile selection avoids
    # startup following the root's sticky active_profile to another owner's home.
    selector = "default" if profile == "custom" else profile
    arguments = ["hermes", "-p", selector, "email-steward", "cron-tick",
                 "--home", str(home), "--binding", key]
    return f'''# Owner-generated Email Steward cron entrypoint. Contains no credentials.
import contextlib, io, json, os, sys
os.environ["HERMES_HOME"] = {str(home)!r}
sys.argv = {arguments!r}
output, diagnostics = io.StringIO(), io.StringIO()
status = 0
try:
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(diagnostics):
        from hermes_cli.main import main
        status = main() or 0
except SystemExit as exc:
    status = exc.code or 0
except BaseException:
    status = 1
records = []
if status == 0:
    for line in output.getvalue().splitlines():
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if (isinstance(value, dict) and set(value) == {{"binding", "cron_output"}}
                and value["binding"] == {key!r} and isinstance(value["cron_output"], str)):
            records.append(value["cron_output"])
if status != 0 or len(records) != 1 or len(records[0].encode()) > {MAX_BATCH_BYTES}:
    print("Email Steward scheduled run failed. Pending work is retained; inspect owner health and cron status.")
    raise SystemExit(1)
if records[0]:
    print(records[0], flush=True)
'''


def install_schedule(ctx, service, *, replace_existing=False):
    """Called only by the explicit local owner CLI; discovery never schedules work."""
    settings = service.current_settings()
    settings.require_schedule()
    target = native_target(settings)
    if replace_existing:
        remove_owned_schedule(ctx, service)
    with service.store.operation():
        previous = service.store.meta("cron_binding")
        if previous:
            # Do not overwrite or replace an operator's existing/edited schedule.
            job = current_job(ctx, previous)
            check_binding(service, previous, job, previous["key"], settings.home)
            return previous
        key = uuid.uuid4().hex
        directory = private_dir(settings.home / "scripts")
        path = directory / ("email-steward-" + key + ".py")
        code = wrapper(settings.home, settings.profile, key)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(code)
        path.chmod(0o600)
        result = cron_call(ctx, action="create", schedule="every 1m", name="Email Steward",
                           script=path.name, no_agent=True, deliver=target,
                           attach_to_session=False, paused=True,
                           paused_reason="Email Steward is verifying its explicit owner binding")
        binding = {"key": key, "job_id": result["job_id"], "home": str(settings.home),
                   "profile": settings.profile, "fingerprint": fingerprint(settings),
                   "grant": list(service.store.active_grant), "deliver": target,
                   "script": str(path), "script_sha256": hashlib.sha256(code.encode()).hexdigest()}
        job = current_job(ctx, binding)
        binding.update(schedule=job.get("schedule"), name=job.get("name"))
        service.store.set_meta("cron_binding", binding)
        check_binding(service, binding, job, key, settings.home, allow_paused=True)
        cron_call(ctx, action="resume", job_id=binding["job_id"])
        check_binding(service, binding, current_job(ctx, binding), key, settings.home)
        return binding


def remove_owned_schedule(ctx, service):
    """Explicit local-operator replacement only; never touch an edited/foreign job."""
    settings = service.current_settings()
    with service.store.operation():
        binding = service.store.meta("cron_binding")
        if not binding:
            return
        job = current_job(ctx, binding)
        path = Path(binding["script"])
        if (binding["home"] != str(settings.home) or path.parent.resolve() != (settings.home / "scripts").resolve()
                or path.name != "email-steward-" + binding["key"] + ".py"
                or path.is_symlink() or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != binding["script_sha256"]
                or job.get("script") != path.name or job.get("deliver") != binding["deliver"]
                or job.get("no_agent") is not True or job.get("attach_to_session") is not False
                or job.get("schedule") != binding["schedule"] or job.get("name") != binding["name"]):
            raise Error("cron_binding", "The existing cron job was edited; reconcile it through Hermes cron before replacing it.", 403)
        cron_call(ctx, action="remove", job_id=binding["job_id"])
        service.store.set_meta("cron_binding", None)
        path.unlink()


def check_binding(service, binding, job, key, home, *, allow_paused=False):
    settings = service.current_settings()
    path = Path(binding["script"])
    if (key != binding["key"] or Path(home).resolve() != settings.home
            or binding["home"] != str(settings.home) or binding["profile"] != settings.profile
            or binding["fingerprint"] != fingerprint(settings)
            or tuple(binding["grant"]) != service.store.active_grant
            or job.get("deliver") != binding["deliver"] or native_target(settings) != binding["deliver"]
            or job.get("script") != path.name or job.get("no_agent") is not True
            or job.get("attach_to_session") is not False
            or job.get("schedule") != binding["schedule"] or job.get("name") != binding["name"]
            or not allow_paused and job.get("enabled") is not True
            or path.is_symlink() or not path.is_file()
            or path.parent.resolve() != (settings.home / "scripts").resolve()
            or hashlib.sha256(path.read_bytes()).hexdigest() != binding["script_sha256"]):
        raise Error("cron_binding", "Scheduled owner/profile/destination authority changed; reconcile the schedule locally.", 403)
    return settings


def cron_tick(ctx, service, key, home, *, now=None):
    now = time.time() if now is None else now
    binding = service.store.meta("cron_binding")
    if not binding:
        raise Error("cron_binding", "Explicit owner schedule setup is required.", 403)
    job = current_job(ctx, binding)
    check_binding(service, binding, job, key, home)
    observation = service.store.meta("cron_host_observation", {})
    if (job.get("last_delivery_error") and job.get("last_run_at")
            and job.get("last_run_at") != observation.get("last_failure_observed")):
        # A failed/partial host send may already have delivered some text. Keep
        # the most recent handoff uncertain; owner confirmation/retry is explicit.
        latest = service.store.meta("cron_last_handoff", {})
        with service.store.transaction() as db:
            for ident in latest.get("ids", []):
                db.execute("UPDATE outbox SET state='uncertain',error=? WHERE id=? AND state='handed_to_cron'",
                    ("Host delivery failure observed after handoff; exact payload outcome unknown", ident))
        observation["last_failure_observed"] = job["last_run_at"]
    # Latest-run metadata is diagnostic, not an exact payload receipt. Never
    # promote a handoff to sent/accepted from last_status=ok or a timestamp.
    service.store.set_meta("cron_host_observation", {
        "observed": now, "last_run_at": job.get("last_run_at"),
        "last_status": job.get("last_status"),
        "delivery_error": bool(job.get("last_delivery_error")),
        "delivery_unverified": bool(job.get("last_delivery_unverified")),
        "last_failure_observed": observation.get("last_failure_observed")})
    Worker(service, None).tick(now)
    with service.store.operation():
        settings = check_binding(service, binding, current_job(ctx, binding), key, home)
        selected, size = [], len((FOOTER + "\n\nEmail Steward scheduled output\n\n").encode())
        rows = service.store.rows("SELECT * FROM outbox WHERE state IN ('pending','retry') AND next_try<=? "
            "ORDER BY CASE WHEN category IN ('danger','security','reminder') THEN 0 ELSE 1 END,rowid LIMIT 100", (now,))
        for row in rows:
            if (row["grant_generation"], row["grant_fingerprint"]) != service.store.active_grant:
                service.store.execute("UPDATE outbox SET state='blocked',error='Historical grant revoked; no reroute' WHERE id=?", (row["id"],))
                continue
            if quiet(settings, now, row["category"]):
                continue
            addition = len(row["text"].encode()) + 2
            if size + addition > MAX_BATCH_BYTES:
                break
            selected.append(row)
            size += addition
        # Re-read public host configuration and the job after selection. Owner
        # grants, cron edits and quiet hours can change during a slow intake run.
        # Never export text selected under an authority that has since changed.
        settings = check_binding(service, binding, current_job(ctx, binding), key, home)
        selected = [row for row in selected if not quiet(settings, now, row["category"])]
        if not selected:
            return ""
        text = "Email Steward scheduled output\n\n" + "\n\n".join(r["text"] for r in selected) + "\n\n" + FOOTER
        attempt = uuid.uuid4().hex
        with service.store.transaction() as db:
            for row in selected:
                db.execute("UPDATE outbox SET state='handed_to_cron',attempts=attempts+1,error=? WHERE id=?",
                           ("Handoff " + attempt + "; host delivery unconfirmed", row["id"]))
            from .store import dump
            record = {
                "job_id": binding["job_id"], "ids": [r["id"] for r in selected], "at": now,
                "sha256": hashlib.sha256(text.encode()).hexdigest(), "bytes": len(text.encode()),
                "prior_host_run": job.get("last_run_at"), "grant": list(service.store.active_grant)}
            db.execute("INSERT INTO meta VALUES(?,?)", ("cron_handoff:" + attempt, dump(record)))
            db.execute("INSERT INTO meta VALUES('cron_last_handoff',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dump(record),))
        return text
