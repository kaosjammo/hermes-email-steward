# Scheduled delivery through Hermes cron

Email Steward uses Hermes **v0.23.0 or later**, with the owner profile served in
`plugins.isolation: in_process` mode. This is an explicit owner configuration
choice. Hosted/secondary-process plugin mode skips registered CLI commands and does
not forward a typed owner identity to dashboard backends; those topologies are
refused rather than authorising a request from an admission boolean.

Install the complete native plugin directory, finish the private owner setup and
connect the intended Gmail slots as described in the README. Configure an IANA
timezone. Hermes owns OAuth sign-in and refresh; no unattended sign-in occurs.

Then explicitly enable the production schedule in that profile:

```bash
hermes -p PROFILE email-steward schedule-install
hermes -p PROFILE cron status
hermes -p PROFILE cron list --all
```

Replace `PROFILE` with the registered profile name; use `default` for the default
root. Custom exported roots also use an explicit default selector and verify
their resolved home. This command creates one private Python wrapper beneath
the owning home's `scripts/` and one recurring, script-only cron job. It verifies
the owner/profile/grant, wrapper and exact `platform:destination[:thread]`
delivery target before enabling the job. Discovery alone creates no job.

The owning Hermes scheduler must be running. The job runs every minute and
invokes the registered production `cron-tick` operation through the public
Hermes CLI entrypoint. It performs actual intake, triage, due reminders,
reconciliation and configured briefs. Its bounded stdout is delivered by
Hermes cron. It does not ask a model to interpret a slash command or use the
public-help-only model bridge.

The outer cron job uses `no_agent`; the plugin's classifier can still use the
configured Hermes model after explicit model-content consent. Rules-first and
consent-off processing remain available. Optional background/foreground intake
workers only queue output; they never send it independently. A cron schedule is
the production delivery route.

## Changes and recovery

The schedule binds the exact private grant and configuration generation. A
changed/revoked grant, home, wrapper or job fails closed. After an intentional
owner/settings change, explicitly replace the plugin's verified job:

```bash
hermes -p PROFILE email-steward schedule-install --replace
```

Replacement verifies ownership of the original job and script. It refuses an
operator-edited job rather than overwriting it. Historical outbox rows retain
their old grant and are never rerouted to the new destination. Review old
reminders and explicitly rearm them under the new grant when appropriate.

Each run emits a bounded batch, with urgent/reminder rows ahead of brief
continuations. Remaining parts stay durable for later ticks; large backlogs can
delay a complete brief. Quiet policy is checked before handoff. Host wrapping,
transport limits and scheduler health still apply.

`handed_to_cron` means the plugin recorded an output attempt, **not** that a
provider or person received it. Host latest-run status is diagnostic and cannot
prove which exact payload arrived. Observed delivery errors leave the latest
handoff uncertain. A crash between recording and emitting is also ambiguous;
the same batch is not replayed automatically. Outstanding action/review state
survives, and future scheduled briefs still include unresolved obligations.

Inspect `/email-steward health`, `/email-steward outbox`, and the owning profile's
cron status/history. After checking the private destination, `delivery-confirm
ID` records explicit owner confirmation. `delivery-retry ID` accepts duplicate
risk and requeues only under its still-current grant. Neither operation grants
a historical row a new destination.

Hermes stores cron output/history locally as well as the plugin's sensitive
summary/outbox metadata. Protect those profile files and backups. Message
bodies and full attachment extracts requested through native commands remain
transient; that does not make scheduled summaries nonpersistent.

Revocation is checked immediately before stdout handoff. The public cron route
does not provide an atomic plugin-to-host final-send revocation or an exact
per-payload receipt API; already in-flight host work can finish. The requested
[owner-configured outbound API](https://github.com/NousResearch/hermes-agent/issues/151105)
would provide a stronger host-owned capability boundary. Current usability
does not depend on that future API.

## Qualification boundary

The isolated released-host probe exercises the actual scheduler, generated
script, installed plugin CLI, host credential helper, Gmail/service logic and
capture adapter. Grants, Gmail HTTP and the final adapter are synthetic. It
covers substantive briefs/alerts, due reminders, repeated ticks and delivery
failure/uncertainty. It does not establish live Gmail/OAuth, platform delivery,
phone notification, native Electron or human receipt. Complete candidate,
package, frontend and independent-review gates remain separate.
