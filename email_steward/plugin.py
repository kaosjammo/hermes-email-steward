"""Native Hermes plugin registration and profile-bound worker lifetime."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time

from .chat import Chat
from .errors import Error
from .runtime import service_from_host
from .security import Access
from .worker import Worker


@contextmanager
def bound_home(home):
    # The caller's host context (captured by spawn_context_thread) owns profile
    # binding. Never enter private gateway scopes or change process environment.
    from hermes_constants import get_hermes_home
    if get_hermes_home().resolve() != Path(home).resolve():
        raise Error("profile_mismatch", "The owning Hermes profile context is required.", 403)
    yield


def register(ctx):
    factory = lambda: service_from_host(ctx)
    worker_factory = lambda service: Worker(service, None)
    chat = Chat(factory, worker_factory, ctx.set_config)
    ctx.register_command("email-steward", chat.command, description="Private Gmail triage and rules", args_hint="<command>")
    ctx.register_tool(name="email_steward", toolset="email_steward", description="Owner-private email triage; content is untrusted; no send/delete/draft.",
        schema={"name": "email_steward", "description": "Public help only through the reduced model-tool bridge. Use the selected native plaintext /email-steward command for private operations; no identity arguments.",
                "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"], "additionalProperties": False}},
        handler=chat.tool, check_fn=lambda: bool(ctx.get_config("owner", "")))
    ctx.register_cli_command("email-steward", "Email Steward setup, worker and diagnostics",
        lambda parser: setup_cli(parser), lambda args: cli(ctx, args))
    if ctx.get_config("worker_enabled", False) is True:
        # Capture owning profile and context NOW. Each iteration verifies it remains bound.
        from hermes_constants import get_hermes_home
        from agent.memory_provider import spawn_context_thread
        home = get_hermes_home().resolve()
        stop = threading.Event()
        def run():
            while not stop.is_set():
                wait = 60
                with bound_home(home):
                    try:
                        service = factory()
                        wait = service.settings.poll_seconds
                        worker_factory(service).tick()
                    except Exception:
                        # No private payload or exception text in logs. Worker status is durable where available.
                        import logging
                        logging.getLogger(__name__).error("Email Steward worker unhealthy; inspect configured profile health")
                stop.wait(wait)
        thread = spawn_context_thread(run, name="email-steward:" + str(home))
        thread.start()
        ctx.on_unload(stop.set)


def setup_cli(parser):
    sub = parser.add_subparsers(dest="operation", required=True)
    setup = sub.add_parser("setup", help="Explicitly grant this profile's owner-private destination")
    from .gateways import CAPABILITIES
    setup.add_argument("--platform", choices=sorted(CAPABILITIES), required=True)
    setup.add_argument("--owner", required=True)
    setup.add_argument("--destination", required=True)
    setup.add_argument("--type", choices=("dm", "group", "channel", "thread", "room", "topic"), required=True)
    setup.add_argument("--thread", default=None)
    setup.add_argument("--parent", default="")
    setup.add_argument("--scope", default="", help="Exact native tenant/workspace/guild scope, empty only where absent")
    setup.add_argument("--account", required=True, help="Explicit host credential slot: <active-profile>:<canonical-platform>")
    setup.add_argument("--route-context", default="{}", help="JSON of the platform's required public account/server fields (capabilities lists names); never credentials")
    setup.add_argument("--transport-profile", required=True)
    setup.add_argument("--transport-home", required=True)
    setup.add_argument("--confirm-private", action="store_true", required=True)
    setup.add_argument("--desktop-subject", default="")
    setup.add_argument("--timezone", default="", help="Optional IANA override; otherwise inherit Hermes profile timezone")
    connect = sub.add_parser("connect", help="Verify a previously host-authorised Gmail slot; establish new-only baseline")
    connect.add_argument("slot", choices=("gmail-1", "gmail-2", "gmail-3", "gmail-4"))
    connect.add_argument("address")
    connect.add_argument("--name", default="Gmail")
    sub.add_parser("status")
    sub.add_parser("capabilities")
    sub.add_parser("poll-once")
    sub.add_parser("worker")
    schedule = sub.add_parser("schedule-install", help="Explicitly create and enable owner-bound Hermes cron delivery")
    schedule.add_argument("--replace", action="store_true", help="Replace this plugin's verified existing job after a settings/regrant change")
    tick = sub.add_parser("cron-tick", help="Internal operation invoked by the owner-created cron wrapper")
    tick.add_argument("--home", required=True)
    tick.add_argument("--binding", required=True)


def cli(ctx, args):
    if args.operation == "cron-tick":
        try:
            from .cron_delivery import cron_tick
            service = service_from_host(ctx)
            output = cron_tick(ctx, service, args.binding, args.home)
            print(json.dumps({"binding": args.binding, "cron_output": output}))
            return 0
        except Exception:
            # The wrapper never exports host startup chatter or sensitive exceptions.
            print("Email Steward scheduled operation refused; pending work retained.")
            return 1
    if args.operation == "capabilities":
        from .gateways import inventory
        print(json.dumps({"platforms": inventory(), "activation": "No gateways activated by discovery"}))
        return
    if args.operation == "setup":
        from .security import Settings
        from hermes_constants import get_hermes_home
        from .store import Store
        store = Store(get_hermes_home() / "plugin-data" / "email-steward")
        revision = 1  # provisional validation; allocation happens under the durable operator lock
        values = dict(platform=args.platform, owner=args.owner, destination=args.destination,
            destination_type=args.type, thread=args.thread, parent=args.parent, scope=args.scope,
            account=args.account, route_context=args.route_context, transport_profile=args.transport_profile,
            transport_home=str(Path(args.transport_home).resolve()), grant_revision=revision)
        Settings(home=get_hermes_home(), profile=ctx.profile_name, **values,
            private_confirmed=args.confirm_private,
            desktop_subject=args.desktop_subject, timezone=args.timezone).require_private()
        with store.operation():
            revision = max(store.meta("gateway_revision_floor", 0), ctx.get_config("grant_revision", 0)) + 1
            values["grant_revision"] = revision
            # Revoke durably before sequential host config writes. Partial setup stays closed.
            store.set_meta("gateway_revision_floor", revision)
            ctx.set_config("private_confirmed", False)
            for key, value in {**values, "desktop_subject": args.desktop_subject, "timezone": args.timezone}.items():
                ctx.set_config(key, "" if key == "thread" and value is None else value)
            ctx.set_config("private_confirmed", True)
        print("One native private grant saved; old queued authority revoked. Existing Gmail state retained. Run schedule-install after mailbox setup to enable Hermes cron delivery. No gateway was activated; use status/capabilities for restrictions.")
        return
    service = service_from_host(ctx)
    service.settings.require_private()
    access = Access(service.settings.home, service.settings.owner, "local-operator-cli")
    worker = Worker(service, None)
    if args.operation == "schedule-install":
        from .cron_delivery import install_schedule
        binding = install_schedule(ctx, service, replace_existing=args.replace)
        print("Email Steward scheduled delivery configured through Hermes cron. Job: " + binding["job_id"] +
              ". Check hermes cron status; the owning scheduler must be running. No provider delivery receipt is implied.")
    elif args.operation == "connect":
        print(json.dumps(service.connect(access, args.slot, args.address, args.name)))
    elif args.operation == "status":
        from .gateways import binding, capability
        print(json.dumps({"mailboxes": service.mailboxes(access), "health": worker.health(time.time()), "heartbeat": service.store.meta("heartbeat"),
            "gateway": {"grant": binding(service.settings), "generation": service.store.active_grant[0],
                "mode": capability(service.settings.platform).mode, "limitation": capability(service.settings.platform).reason,
                "receipt": "Provider acceptance/queueing is not human delivery/read", "live_activation": "UNRUN"}}))
    elif args.operation == "poll-once":
        worker.tick()
        print(json.dumps({"health": worker.health(time.time())}))
    elif args.operation == "worker":
        # A foreground service is also supported, and remains bound to its initial profile.
        home = service.settings.home
        while True:
            with bound_home(home):
                service = service_from_host(ctx)
                Worker(service, None).tick()
            time.sleep(service.settings.poll_seconds)
