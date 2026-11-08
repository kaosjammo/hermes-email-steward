"""Run the installed released-host scheduler with synthetic provider and capture adapter.

Standalone qualification helper, never loaded by production plugin registration.
Run with the task-owned released-host interpreter. No network/listener is used.
"""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tarfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--profile", default="default", choices=["default", "steward-test"])
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    base, runtime = root / "home", root / "runtime"
    base.mkdir()
    (base / "config.yaml").write_text("timezone: UTC\n")
    # The host deliberately normalizes nested homes beneath its native root.
    # Refuse before CLI startup instead of risking PM state outside this task.
    from hermes_constants import get_default_hermes_root
    if get_default_hermes_root(home=base).resolve() != base.resolve():
        raise SystemExit("Qualification home resolves outside its isolated root; choose a task directory outside the native Hermes data root.")
    foreign = base / "profiles/foreign"
    foreign.mkdir(parents=True)
    (foreign / "config.yaml").write_text("timezone: UTC\n")
    (base / "active_profile").write_text("foreign\n")
    home = base if args.profile == "default" else base / "profiles" / args.profile
    plugin = home / "plugins/email-steward"
    if args.bundle:
        with tarfile.open(args.bundle) as archive:
            archive.extractall(root / "unpacked", filter="data")
        shutil.copytree(root / "unpacked/email-steward", plugin)
    else:
        plugin.mkdir(parents=True)
        for name in ("email_steward", "dashboard", "desktop"):
            shutil.copytree(source / name, plugin / name, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("plugin.yaml", "__init__.py", "pyproject.toml"):
            shutil.copyfile(source / name, plugin / name)
    fixture = home / "plugins/synthetic-mail-fixture"
    fixture.mkdir()
    shutil.copyfile(source / "tests/repair_wire.py", fixture / "wire_fixture.py")
    (fixture / "plugin.yaml").write_text("name: synthetic-mail-fixture\nversion: 1.0.0\nmanifest_version: 2\napi_version: 1\nkind: standalone\ndescription: Isolated synthetic qualification only\n")
    (fixture / "__init__.py").write_text('''
def register(ctx):
    import atexit, json, os, socket
    from pathlib import Path
    from unittest.mock import patch
    from hermes_constants import get_hermes_home
    home = get_hermes_home()
    os.environ['ES_REPAIR_SOURCE'] = str(home / 'plugins/email-steward')
    from .wire_fixture import AccountWire
    from hermes_cli import plugin_oauth as oauth
    import httpx
    wire = AccountWire()
    path = home / 'synthetic-mail.json'
    wire.boxes = json.loads(path.read_text())
    original = httpx.Client
    transport = httpx.MockTransport(wire.handle)
    patches = [patch.object(oauth, '_read_grant', wire.grant),
               patch.object(httpx, 'Client', lambda *a, **kw: original(*a, transport=transport, **kw))]
    for item in patches: item.start()
    def save():
        path.write_text(json.dumps(wire.boxes))
        with (home / 'synthetic-provider-calls.jsonl').open('a') as stream:
            stream.write(json.dumps(wire.calls) + '\\n')
    atexit.register(save)
    def deny(*args, **kw):
        raise AssertionError('Synthetic cron qualification forbids real network')
    socket.getaddrinfo = deny
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
''')
    clock = datetime.now(timezone.utc).strftime("%H:%M")
    (home / "config.yaml").write_text("timezone: UTC\nplugins:\n  enabled: [email-steward, synthetic-mail-fixture]\n  isolation: in_process\n  load_timeout_seconds: 0\n  entries:\n    email-steward:\n      settings:\n        briefs: [\"" + clock + "\"]\n")
    boxes = {key: {"address": address, "history": 0, "messages": {}, "events": [],
                   "labels": [{"id": "Label_" + key, "name": "Triaged"}]}
             for key, address in (("A", "alex@example.test"), ("B", "other@example.test"))}
    mail = home / "synthetic-mail.json"
    mail.write_text(json.dumps(boxes))
    empty = root / "empty-bundled"
    empty.mkdir()
    scratch = root / "tmp"
    scratch.mkdir(mode=0o700)
    env = {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
           "TMPDIR": str(scratch), "HERMES_HOME": str(home), "HERMES_RUNTIME_DIR": str(runtime),
           "HERMES_BUNDLED_PLUGINS": str(empty), "PYTHONDONTWRITEBYTECODE": "1"}
    os.environ.clear()
    os.environ.update(env)
    commands = []
    def cli(*arguments):
        argv = [sys.executable, "-m", "hermes_cli.main", "-p", args.profile, "email-steward", *arguments]
        result = subprocess.run(argv, env=env, cwd=root, capture_output=True, text=True, timeout=60)
        commands.append({"argv": argv, "cwd": str(root), "exit": result.returncode})
        (root / "COMMANDS.json").write_text(json.dumps(commands, indent=2))
        (root / (arguments[0] + ".log")).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout
    cli("setup", "--platform", "discord", "--owner", "12345", "--destination", "67890", "--type", "dm",
        "--account", args.profile + ":discord", "--transport-profile", args.profile, "--transport-home", str(home),
        "--confirm-private", "--desktop-subject", "uid:synthetic", "--timezone", "UTC")
    cli("connect", "gmail-1", "alex@example.test")
    boxes = json.loads(mail.read_text())
    body = "Suspicious sign-in. Please review today."
    boxes["A"].update(history=1, events=[[1, "synthetic-new"]], messages={"synthetic-new": {
        "id": "synthetic-new", "threadId": "synthetic-thread", "internalDate": str(int(time.time() * 1000)),
        "labelIds": ["INBOX", "UNREAD"], "payload": {"mimeType": "text/plain", "headers": [
            {"name": "From", "value": "security@example.test"}, {"name": "Subject", "value": "Security alert"}],
            "body": {"data": base64.urlsafe_b64encode(body.encode()).decode(), "size": len(body)}}}})
    mail.write_text(json.dumps(boxes))
    cli("schedule-install")
    from hermes_constants import get_hermes_home
    assert get_hermes_home().resolve() == home
    from gateway.config import Platform, PlatformConfig
    from gateway.platforms.base import BasePlatformAdapter, SendResult
    from cron import scheduler
    from cron.jobs import list_jobs, trigger_job, get_job
    from cron.executions import list_executions
    from hermes_cli.plugins import PluginContext, PluginManager
    from hermes_cli.plugins_manifest import parse_manifest_file
    import plugins.platforms.discord
    platform_root = Path(plugins.platforms.discord.__file__).parent
    manager = PluginManager(scope_key=str(home))
    plugins.platforms.discord.register(PluginContext(
        parse_manifest_file(platform_root / "plugin.yaml", platform_root, "bundled", "platforms"), manager))
    class Capture(BasePlatformAdapter):
        def __init__(self):
            super().__init__(PlatformConfig(enabled=True), Platform.DISCORD)
            self.captured = []
            self.fail = False
        async def connect(self, **kw): raise AssertionError("No live adapter activation")
        async def disconnect(self): pass
        async def get_chat_info(self, chat_id): return {"name": "Synthetic", "type": "dm"}
        async def send(self, chat_id, content, reply_to=None, metadata=None):
            if self.fail:
                return SendResult(False, error="Synthetic capture refusal", retryable=False)
            self.captured.append({"chat_id": chat_id, "text": content, "metadata": metadata})
            return SendResult(True, message_id="synthetic-capture-" + str(len(self.captured)))
    capture = Capture()
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    job = list_jobs()[0]
    try:
        trigger_job(job["id"])
        assert scheduler.tick(verbose=False, adapters={Platform.DISCORD: capture}, loop=loop, sync=True) == 1
        text = "\n".join(item["text"] for item in capture.captured)
        assert "Suspicious sign-in" in text and "https://mail.google.com/" in text, text
        assert "Email Steward brief" in text and "A1" in text, text
        assert all(item["chat_id"] == "67890" for item in capture.captured)
        sys.path.insert(0, str(plugin))
        from email_steward.runtime import service_from_host
        from email_steward.security import Access
        service = service_from_host(PluginContext(
            parse_manifest_file(plugin / "plugin.yaml", plugin, "user", ""), manager))
        access = Access(home, "12345", "local-operator-cli")
        service.action(access, "ax1", "remind", at=time.time() + 1)
        time.sleep(1.1)
        trigger_job(job["id"])
        assert scheduler.tick(verbose=False, adapters={Platform.DISCORD: capture}, loop=loop, sync=True) == 1
        assert "Reminder" in capture.captured[-1]["text"]
        assert service.store.item("ax1")["reminder_at"] is None
        assert service.store.item("ax1")["classification"] == "needs_action"
        count = len(capture.captured)
        trigger_job(job["id"])
        assert scheduler.tick(verbose=False, adapters={Platform.DISCORD: capture}, loop=loop, sync=True) == 1
        assert len(capture.captured) == count, "A repeated run must not replay the handoff"
        service.action(access, "ax1", "remind", at=time.time() + 1)
        time.sleep(1.1)
        capture.fail = True
        trigger_job(job["id"])
        assert scheduler.tick(verbose=False, adapters={Platform.DISCORD: capture}, loop=loop, sync=True) == 1
        assert get_job(job["id"])["last_status"] == "delivery_failed"
        capture.fail = False
        trigger_job(job["id"])
        assert scheduler.tick(verbose=False, adapters={Platform.DISCORD: capture}, loop=loop, sync=True) == 1
        assert len(capture.captured) == count, "An uncertain failed handoff must not replay automatically"
        assert service.store.rows("SELECT id FROM outbox WHERE state='uncertain'")
        assert not service.store.rows("SELECT id FROM outbox WHERE state IN ('sent','accepted')")
        assert (base / "active_profile").read_text().strip() == "foreign"
        assert not list(foreign.rglob("email-steward*")), "The sticky foreign profile must remain untouched"
        result = {"profile": args.profile, "bundle_sha256": hashlib.sha256(args.bundle.read_bytes()).hexdigest() if args.bundle else None,
                  "sticky_foreign_profile_untouched": True, "host_python": sys.executable, "home": str(home), "job": get_job(job["id"]),
                  "executions": list_executions(job_id=job["id"]), "captured": capture.captured,
                  "commands": commands, "plugin_files": {
                      str(path.relative_to(plugin)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in sorted(plugin.rglob("*")) if path.is_file() and "__pycache__" not in path.parts},
                  "kind": "released-host production scheduler/script/CLI with synthetic OAuth grant/HTTP and capture adapter"}
        (root / "RESULT.json").write_text(json.dumps(result, indent=2))
        print(json.dumps({"result": str(root / "RESULT.json"), "captures": count, "repeat_replay": False}))
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()
        manager.unload()


if __name__ == "__main__":
    main()
