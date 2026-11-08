# Email Steward

Private Gmail triage for one owner, across up to four separately authorised Gmail accounts in one Hermes profile. A selected qualified native gateway controls obligations and rules; the native Hermes Desktop screen edits the same rule store. Suggested starter packs remain off until explicitly installed.

**Public-API release candidate.** Issue [#2](https://github.com/kaosjammo/hermes-email-steward/issues/2) tracks the usable public-API repair. Scheduled output now uses supported Hermes cron `deliver`; it is not indefinitely disabled. Qualification includes isolated released-host cron wiring; exact-candidate review and publication results are recorded on that issue. No Gmail send, reply draft, delete or unsubscribe action is implemented. Live Gmail/OAuth, real platform delivery, native Electron and mobile acceptance remain unverified.

## Fresh checkout and local checks

Use Python **3.14** on Linux with `venv` support for the pinned actual Hermes SDK qualification. The library declares Python 3.11–3.14 compatibility; this build does not claim a qualification run on each interpreter, and the pinned upstream supports 3.14 for new installations. The parser needs `libseccomp.so.2`, `qpdf`, Poppler (`pdftotext`, `pdftoppm`) and Tesseract with English language data in `/usr/bin` or `/bin`. Install those prerequisites using your machine's package manager before running extraction tests. [Extraction details and limits](docs/EXTRACTION.md) describe supported document variants, OCR and the kernel filter.

```bash
scripts/setup.sh
HERMES_UPSTREAM=/path/to/read-only/hermes-agent scripts/test.sh
TMPDIR="$PWD/.local/tmp" .local/backend/venv/bin/python scripts/validate_hermes.py --upstream /path/to/read-only/hermes-agent
scripts/package.sh
```

`setup.sh` creates `.local/backend/venv` and installs **tracked `requirements.lock`**, including build/test dependencies. It does not depend on a pre-existing task venv or alter Hermes' environment. All scratch, dependency cache and subprocess TMPDIR remain inside repository `.local/`. `ES_BOOTSTRAP_PYTHON` selects the initial interpreter. `ES_VENV_NAME=fresh-venv scripts/setup.sh` verifies installation into a second clean task venv. `ES_PYTHON=/absolute/path/to/prepared/python scripts/test.sh` selects a prepared interpreter; the default is the task venv. A missing interpreter produces an actionable setup error.

The native check copies the plugin into an isolated `.local/backend/native/home/plugins/email-steward`, sets isolated `HERMES_HOME`/`HERMES_RUNTIME_DIR`, and invokes the actual upstream validator and discovery from a different working directory. It never installs into the running Hermes profile. Current release qualification targets **Hermes v0.23.0**, commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`; the manifest requires `>=0.23.0`. The expanded native suite requires that released host; the native validation command must still be run for qualification. The GitHub workflow pins the same release; hosted CI is a separate acceptance gate.

`package.sh` builds a native plugin directory bundle, Python wheel and source distribution under `.local/backend/dist`. Build staging is `.local/backend/package-src`; it excludes `.local`, credentials, Git internals and dependency installations. The wheel supplies the Python library. Use the native directory bundle/source repository for the plugin's manifest, backend and Desktop assets together.

Some restricted execution sandboxes prevent Python's async thread wakeups, causing FastAPI tests to stall. This build's approved unrestricted synthetic runs are recorded separately from those timeouts. Do not treat a timeout as passing evidence.

Desktop component and browser tests have their own [tracked npm lock and scoped setup](tests/desktop/README.md). `node tests/desktop/setup.mjs --browser` installs only task-local dependencies and pinned Chromium; `node tests/desktop/run-browser.mjs` runs the actual backend behind the synthetic SDK fixture and stops its own host. Browser/Python overrides are documented; no personal cache or pre-existing venv is assumed.

## Synthetic demo

```bash
TMPDIR="$PWD/.local/tmp" .local/backend/venv/bin/python scripts/backend_fixture.py --port 8766
```

This loopback-only fixture serves the real REST router at `/api/plugins/email-steward`, backed by the real SQLite rule service, with two synthetic mailboxes and empty initial rules. It never reads Hermes configuration or selects Gmail transport. Its test middleware binds a **synthetic** trusted native principal and marks responses `X-Email-Steward-Fixture: synthetic-only`. It is an integration fixture, not a production authentication server. `create_app(state_root)` permits an isolated fixture state directory under `.local/`.

## Native install and owner setup

These are user-operated production setup instructions, **not actions executed by this build**. Install the native plugin directory using Hermes' plugin installation/enable workflow. Let Hermes PM admit the declared `fastapi>=0.133.1,<0.134` dependency; never use this development setup script to mutate a Hermes-managed environment. Include `plugin.yaml`, root `__init__.py`, `email_steward/`, `dashboard/` and `desktop/` together. Restart/reload the host as its plugin UI instructs.

The released host must load this trusted plugin in its owning profile process
so its CLI and typed Desktop identity are available. In that profile's
`config.yaml`, explicitly select `plugins.isolation: in_process` and include
`email-steward` in `plugins.enabled`; preserve other plugin settings. Hosted or
secondary-process mode cannot provide those contracts and fails closed.

Use an explicit profile selector for every setup, auth and scheduling command.
Replace `PROFILE` with its registered name, or `default` for the default/custom
root. For a custom root, launch with its own `HERMES_HOME` as well. Configure its
selected private Discord DM or owner-controlled restricted channel:

```bash
hermes -p PROFILE email-steward setup --platform discord --owner DISCORD_USER_ID --destination PRIVATE_CHAT_ID --type dm --account PROFILE:discord --transport-profile PROFILE --transport-home /absolute/owning/profile/home --confirm-private --desktop-subject uid:LOCAL_UID
```

For a restricted channel, use `--type channel` only after confirming its access controls. A channel name or loopback address alone never grants access. Desktop's normal local POSIX native bootstrap uses the exact `uid:<numeric uid>` subject; enter the actual local uid. Federated/native subjects can differ. [Security and supported host identities](docs/SECURITY.md) gives exact alternatives and fail-closed behaviour. Configure plugin settings under `plugins.entries.email-steward.settings`, with the schema declared in `plugin.yaml`.

After owner setup and mailbox connection, explicitly run `hermes -p PROFILE email-steward schedule-install` and check `hermes -p PROFILE cron status`. The owning scheduler must be running. [Scheduled delivery and recovery](docs/CRON.md) explains the generated script, exact private target, in-process owner-profile topology, configuration changes and uncertain outcomes. The one-minute cron job runs actual triage/brief/reminder production logic and Hermes delivers its stdout. Discovery does not activate it.

Optional `worker_enabled: true`, foreground `worker` and `poll-once` perform intake and queue output; they do not send independently. Threads capture the owning host context and reread current settings without private gateway scopes. Separate processes and actions share a file lock. Explicit local owner regrant revokes old queued authority/consent while retaining business state; changing profile home is refused.

## Gmail OAuth: separate account grants

Create your own Google Cloud OAuth **Desktop app** client with Gmail API enabled. Supply `EMAIL_STEWARD_GOOGLE_CLIENT_ID` and `EMAIL_STEWARD_GOOGLE_CLIENT_SECRET` through Hermes' supported profile secret configuration, **outside this repository**. Do not paste credentials into commands, chat, docs or evidence. Hermes owns PKCE sign-in, refresh locking and grant storage in the owning profile's private auth store. The plugin never reads or copies tokens.

There are four declared independent grant IDs. Sign in once per connected mailbox, selecting the intended Google account in each host-owned flow:

```bash
hermes -p PROFILE auth add email-steward:gmail-1
hermes -p PROFILE email-steward connect gmail-1 alex@example.test --name Personal
hermes -p PROFILE auth add email-steward:gmail-2
hermes -p PROFILE email-steward connect gmail-2 work@example.test --name Work
hermes -p PROFILE email-steward status
```

The example addresses are synthetic; replace them with your own during authorised setup. The supported capacity is **FOUR separately declared account OAuth slots: `gmail-1`…`gmail-4`**. Slots 3 and 4 work identically. Extending capacity requires additional manifest OAuth grant declarations, matching code/CLI slot allowlists, explicit new host-owned grants, and renewed plugin validation/account-isolation tests; account verification remains mandatory. There is no dynamic/unlimited grant or alternate auth system. Each request names its specific slot through `credentialed_provider_request`; its declared API host is only `gmail.googleapis.com`. `/users/{expected-address}/profile` must match the expected address at connect, every poll and each provider selection for item reads/mutations, Every resource URL also names the expected receiving address instead of users/me. Gmail then enforces account access on each request, so a slot change between the profile check and a read/effect is denied without reading or mutating the foreign mailbox. Distinct grants do not imply that choosing the same account twice creates a new mailbox. Duplicate addresses/slots are refused.

The declared `gmail.modify` scope permits label and Inbox location changes. Implementation calls only profile/history/message/thread/label reads, Triaged label creation, and label add/remove; it never changes `UNREAD` or calls Gmail send/draft/delete/trash endpoints. Sign-in and refresh remain host-owned. Use `hermes -p PROFILE auth status|refresh|logout email-steward:gmail-1` for the matching grant. No flow is launched by an unattended worker.

Connecting records the current Gmail history ID: older Inbox mail is excluded. An explicit bounded `historical` command can queue a date range of at most 31 days and 500 messages. History expiry or overflow pauses intake visibly and retains the checkpoint; it never silently skips forward. Use `recover-history MAILBOX AFTER_ISO LIMIT` to explicitly recover the bounded recent Inbox range and cut over to the current history head. The start must be within 31 days and the limit 1–500; an oversized scope fails without advancing anything. First use separate `historical` ranges if older mail also needs recovery. The recovery response states its cutover and exclusions. No automatic reset or inferred approval occurs.

## Native plaintext controls and model consent

Every `/email-steward` command requires the selected actual native source, off-wire receiving adapter, exact platform-qualified actor/chat/type/thread/scope and owning profile/home. The reduced model tool is public help only. Native Desktop and local CLI use their separate explicit grants. Reading or archiving does not complete an obligation.

```text
/email-steward help
/email-steward list
/email-steward inspect ax1
/email-steward inspect ax1 text
/email-steward inspect ax1 attachments
/email-steward done ax1
/email-steward archive ax1
/email-steward restore ax1
/email-steward snooze ax1 2026-11-06T11:00:00+11:00
/email-steward waiting ax1 2026-11-09T09:00:00+11:00
/email-steward remind ax1 2026-11-06T09:00:00+11:00
/email-steward rules
/email-steward packs
/email-steward pack-enable starter-action {"mailbox_id":null}
/email-steward brief
/email-steward health
/email-steward outbox
```

`rule-save JSON`, `rule-update ID JSON`, `rule-toggle ID JSON`, `preview JSON` and `correct REF JSON` use [the shared v1 schemas](docs/API.md). They call the same validator/store as Desktop. Stale versions return a conflict and current object; they never overwrite silently. `correct` with `always:false` changes one item and returns a proposed rule. `always:true` requires the explicit proposed/edited rule in the request. Pack installation is transactional and idempotent for each pack+mailbox/global scope; repeating it preserves edits and toggles. Preview writes nothing and calls no model. A sample's attachment safety is unassessed, so preview does not promise automatic archive.

Rules run first. Local conservative request/problem/uncertainty holds override unsafe FYI preferences. Without consent, unknown mail stays for review. For model judgement, read `/email-steward consent` first:

> Email Steward may transmit bounded email sender, subject, body and extracted attachment text to your configured Hermes model/provider for classification, summary and urgency. Mail is untrusted data. No tools are exposed and no email instructions are executed. Secrets are redacted on a best-effort basis. Summaries are sensitive local metadata. Rules run first. Hermes owns routing and may try its configured model/provider fallbacks. The plugin does not choose a separate service or change your routing. This SDK may not expose every attempted endpoint or fallback status; reported model/provider metadata is not a complete physical-attempt audit or a strict route guarantee. Renewed consent is required.

Explicitly approve with `/email-steward consent model-routing-v2`; disable with `/email-steward consent off`. Calls use `ctx.llm.complete_structured` with the host's configured model, a 45-second timeout and 700-output-token limit, with no model/provider/profile override or tools. Old model-content-v1 approval is insufficient for new model calls. SDK-reported provider/model/task metadata is retained in decision reasons and inspection, explicitly labelled incomplete: fallback status and endpoint/attempt history are unavailable. The plugin selects no fallback/provider/model override. Host routing failure leaves the message queued and health partial; host-managed fallback attempts may already have occurred.

## Briefs, references and recovery

Default brief times are 07:00, 11:00 and 20:00 in the configured user's timezone. An empty plugin `timezone` override inherits the owning Hermes profile's supported top-level `timezone` setting from its effective configuration. A valid explicit plugin IANA timezone overrides that profile value. If neither is configured, scheduling is refused until one is set; malformed values fail safely. The plugin never infers location, uses the server-local clock as a substitute, or changes global/profile configuration. Melbourne below is an explicit example only. For example:

```text
/email-steward schedule {"timezone":"Australia/Melbourne","briefs":["07:00","11:00","20:00"],"quiet_start":"22:00","quiet_end":"07:00","quiet_bypass":["danger","security"]}
```

DST uses local wall time. Repeated times send once per local-date slot; a nonexistent time moves forward across the DST gap. Catch-up is bounded to two days. Urgent alerts bypass quiet hours by default because no quiet hours are configured; with quiet hours, `danger` and `security` bypass by default. Explicit reminders notify at the next poll at/after the chosen time. Snooze restores Inbox/brief visibility at expiry without adding an unrequested notification. Done clears reminders, cancels queued unsent reminder deliveries and archives without changing read status. Gmail replies move unresolved items to Waiting and ask for a follow-up date; no universal delay is invented.

The operational target is detection, assessment and private delivery within five minutes, not guaranteed phone notification. Retries, dependency failure, processing backlog, late assessment, stale polling/reconciliation/heartbeat and uncertain delivery are visible. The worker polls durable message IDs before advancing checkpoints, processes up to 100 queued messages per cycle, and reconciles the ten oldest tracked conversations per account per cycle. Large backlogs can exceed the target and are reported. A brief says all-clear only when intake/processing/provider/delivery health is actually clear.

Permanent refs use first+last alphabetic local-part letters after Unicode NFKC+casefold, followed by a profile-global SQLite AUTOINCREMENT sequence. One letter repeats (`a` → `aa`); no letters uses `xx`. Account/thread uniqueness and the sequence handle prefix collisions. References survive category, archive and display-name changes and restart. Preserve the state database and its sequence when backing up/migrating. Digest aliases are immutable: `D<digest-id>:A1` resolves the original thread; an unqualified alias occurring in multiple digests is refused. Gmail links use the receiving account's encoded `authuser` address and thread id. Real multi-login browser targeting and native mobile-app opening still require live verification.

Outbox rows persist before stdout handoff. `handed_to_cron` and returned command text are not provider receipts. Observed delivery errors leave handoffs uncertain; a crash after durable handoff intent is not blindly retried. Latest job status is diagnostic, not an exact payload receipt. Inspect `/email-steward outbox` and the owning profile's cron history; `delivery-confirm ID` records explicit owner confirmation, while `delivery-retry ID` accepts duplicate risk under a still-current grant. Outstanding obligations survive output failures. See [cron semantics and limits](docs/CRON.md).

## Privacy and limits

Provider IDs, permanent refs, summaries/reasons, rules, lifecycle state, checkpoints, aliases and delivery history persist. Hermes also retains scheduled output/history under the owning profile. SQLite/state directories are owner-only (0700/0600); state is bound to its profile home and configured owner. Full bodies and attachment bytes/text are fetched transiently with explicit private profile scratch for parsers. No permanent mailbox replica is built.

Untrusted output is bounded, HTML/Markdown escaped, mentions disabled, authentication/credential-like content redacted, external/tracking links removed and Hermes media/file directives neutralised. Only generated account-specific Gmail links are added. Redaction and danger scanning are conservative and cannot guarantee detection of every secret or malicious format. A suspected dangerous attachment stops the attachment batch and queues a priority private warning for the cron route; unreadable/unsupported/truncated content holds automatic archive. Human-requested `done`/`archive` remains an explicit owner location choice.

See [security boundaries](docs/SECURITY.md), [backend implementation/evidence](docs/BACKEND.md), [R01–R10 acceptance map](docs/ACCEPTANCE.md), and [parser limits](docs/EXTRACTION.md). Independent exact-candidate review, real OAuth/account isolation, real private delivery, actual Desktop host and mobile/browser acceptance remain separate gates owned by the integrator/user.

## Repair-cycle safety behaviour

Automatic FYI archive applies only to the assessed message. It cannot remove Inbox from a newer unassessed reply. Superseded or legacy thread-wide automatic intents are cancelled; explicit owner Done/archive retains thread semantics. A retried automatic effect reads actual thread location and cannot replace successor obligation state. Final MIME, HTML and body/attachment joins budget inserted separators and mark discarded significance unreadable/review, preventing automatic archive. Each outbox effect rechecks the current private grant, destination and quiet policy; a revoked grant leaves uninvoked rows pending.

Rule-matched and consent-off messages use a bounded redacted extractive summary of the available request/substance and quote explicit deadline text. No calendar date, reminder interval or model call is inferred. Matched rules keep classification authority; raw bodies and full extracts remain transient. Model-enabled unknown items require renewed routing disclosure consent.

## Native route limits

Photon/BlueBubbles commands remain denied because the native bridge cannot prove a genuine actor rather than a conversation fallback. Notifications use the owner-created cron route. The old private adapter sender and its adapter-internals preflights have been removed; old direct-sender evidence does not qualify cron delivery. [Native route policy](docs/NATIVE-GATEWAYS.md) and [current qualification](https://github.com/kaosjammo/hermes-email-steward/issues/2) retain that distinction.

## Native presentation (ES-004)

The opt-in **Email rules** screen uses Hermes SDK controls, typography and theme colours. Rule conditions and a real match preview sit side by side on wide screens and stack on narrow ones. Rule order is available under an expandable control. A preview is required after each edit. Failed or conflicting saves require a server reload before another save; packs and one-off corrections keep their separate approvals. The screen still calls the same protected REST service and SQLite store as native commands.

Native commands return short replies directly and hand long replies to public call-bound `ctx.post_message` one bounded part at a time, with fresh grant checks. They stop on an unconfirmed part and report duplicate risk; full inspection output is not cached. Replies are plain-language summaries, after-state confirmations and explicit failure/uncertainty notices; machine tool and REST schemas are unchanged. Briefs and urgent alerts retain the permanent reference, substantive request, explicit deadline, warning and safe Gmail link. Long output splits at complete lines or words where possible, with bounded numbered parts. Credential-like values, unsafe links, mentions and transport directives remain neutralised; attachment/body inspection is transient. Gateway restrictions and provider-acceptance limits in [NATIVE-GATEWAYS.md](docs/NATIVE-GATEWAYS.md) still apply.

[Release-readiness acceptance](https://github.com/kaosjammo/hermes-email-steward/issues/2) tracks the current candidate. Earlier UI scores and approvals do not establish current rendered usability. Browser-hosted Desktop evidence is distinct from native Electron and live gateway/mobile acceptance.


## Installation risk disclosure

This draft can read mail and attachments from explicitly authorised Gmail accounts, call Google Gmail APIs, transmit bounded redacted email content to the configured Hermes model after consent, and hand bounded private notifications to the owner-configured Hermes cron delivery route. The Gmail modify scope permits label/Inbox changes. A profile-bound background poller runs only after explicit setup/enabling. Attachment extraction invokes bounded local parser/OCR subprocesses and uses private scratch; durable local SQLite state contains sensitive summaries, rules and delivery history. OAuth tokens and refresh remain host-owned; the plugin does not read credential stores. No telemetry or automatic self-update is implemented. Some native adapter integrations import undocumented Hermes modules; compatibility and scanner warnings need maintainer review. The synthetic test host is not a production authentication server.

The release compatibility target is Hermes v0.23.0 on Linux/Python 3.14, in the supported owner-profile topology described in [CRON.md](docs/CRON.md). Isolated installed-host synthetic wiring, package builds and focused checks have run. Independent release verdicts and exact published CI results are tracked separately on source issue #2. Historical development-SDK tests, failed builds and the original parked publication remain historical; current source issue #2 records the actual remaining gates.

### Publication privacy correction

An independent post-opening check found internal planning/approval provenance in the initial public technical addendum. The current source removes those identifiers, quoted approval provenance and private review paths, and describes the routing contract directly. The original public commit remains in Git history; this update does not claim historical erasure. No actual credential was identified by this finding.
