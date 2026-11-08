"""SDK qualification bridge: real plugin cron handoff -> real host delivery.

This is test scaffolding, not a plugin sender. The registered CLI/script/tick
path is qualified separately by cron_host_probe.py against an installed host.
All adapters and final provider/network leaves in these tests are synthetic.
"""
import asyncio

from email_steward.cron_delivery import install_schedule, cron_tick, current_job
from email_steward.gateways import fingerprint
from email_steward.errors import Error


class CronTransport:
    def __init__(self, ctx, service, adapters):
        self.ctx, self.service, self.adapters = ctx, service, adapters
        self.binding = install_schedule(ctx, service)
        self._fixture_receipts = []

    def send(self, settings, text, ident):
        try:
            if fingerprint(settings) != fingerprint(self.service.current_settings()):
                return "blocked"
            self.service.store.outbox("probe:" + ident, 1, text)
            output = cron_tick(self.ctx, self.service, self.binding["key"], settings.home, now=2)
            if not output:
                return "blocked"
            self.last_output = output
        except Error:
            return "blocked"
        from cron import scheduler
        from model_tools import _run_async
        from gateway.config import Platform
        async def current_loop():
            return asyncio.get_running_loop()
        job = {"id": self.binding["job_id"], "name": "Synthetic SDK qualification",
               "deliver": self.binding["deliver"], "attach_to_session": False}
        error = scheduler._deliver_result(job, output,
            adapters={Platform(name): adapter for name, adapter in self.adapters.items()},
            loop=_run_async(current_loop()))
        observed = current_job(self.ctx, self.binding)
        self._fixture_receipts.append({"error": error, "unverified": observed.get("last_delivery_unverified")})
        assert error is None, error  # SDK qualification must exercise a successful host route.
        assert not self.service.store.rows("SELECT id FROM outbox WHERE state IN ('sent','accepted')")
        return "handed_to_cron"  # Host success never promotes the plugin's output receipt.
