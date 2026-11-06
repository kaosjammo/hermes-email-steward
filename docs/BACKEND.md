> Historical synthetic engineering notes. These results refer to earlier internal candidates, not acceptance of this unfinished public snapshot. Current status: https://github.com/kaosjammo/hermes-email-steward/issues/1

# Backend implementation and evidence

Current controller clarification: [SCOPE-ADDENDUM.md](SCOPE-ADDENDUM.md). Initial-build receipts below remain historical; cycle-1 evidence and fresh closing review are separate.

The backend is a collection of small Python modules around one SQLite metadata store. `api.create_router` and `chat.Chat` both invoke `service.Steward`; `rules.RuleStore` supplies the single validator, compare-and-swap store, previews and pack installation. `worker.Worker.tick` is the production intake/scheduler/outbox entrypoint used by native background polling and CLI. The synthetic fixture app uses the exact same router/service/store with explicitly synthetic providers and a trusted test principal.

## Native integration

Root `__init__.py` loads the package relatively inside Hermes' per-profile plugin namespace. `email_steward.plugin.register` registers `/email-steward`, the `email_steward` model tool and `hermes email-steward`. Background start is opt-in through `worker_enabled`; it uses `spawn_context_thread` and the host-owned full profile runtime scope on each iteration, binding home/secrets/terminal policy without reading credential values in plugin code. CLI setup/connect does not borrow another profile. `dashboard/plugin_api.py` loads its own installed copy by location, so discovery does not depend on the source checkout being cwd or an editable install. There is no dashboard UI or second rule state.

Gmail uses the actual `credentialed_provider_request` host helper and declared per-account OAuth IDs. The host attaches/refreshed credentials are never exposed to plugin code. The optional configured-model adapter uses `ctx.llm.complete_structured`; provider, model, agent and profile overrides/tools are absent. The native notification adapter uses the actual `send_message_tool` entrypoint also used by `hermes send`, not the deliberately unregistered `send_message` model tool.

Capacity is FOUR separately declared OAuth slots (`gmail-1`…`gmail-4`). More accounts require manifest grant declarations, matching code/CLI allowlists, explicit host-owned authorisation and renewed validation/isolation tests; no dynamic alternate auth system is assumed.

Timezone defaults inherit the effective owning profile's top-level `timezone`, with an optional explicit plugin override. Empty/unconfigured scheduling is refused and malformed values fail validation. No global config changes or location inference occur.

The real upstream validator's private-core import warnings are retained. Identity/session/local-token seams are inspected against the pinned source and fail closed; their future compatibility and host-isolation identity forwarding are explicit limits in `SECURITY.md`. The generic validator host-ready assessment does not replace actual hosted identity qualification.

## State and recovery

`Store` opens private metadata SQLite with `BEGIN IMMEDIATE`; an independent `flock` serialises external provider effects, intake, worker and owner actions across threads/processes. All network work occurs outside SQLite write transactions. Accounts keep history checkpoints and health. Jobs keep account/message IDs, attempts, retry times and payload-free errors. Items keep account/thread refs, redacted metadata/decisions and independent obligation/archive/reminder state. Rules/packs use the same tables across surfaces. Digest aliases and outbox identities are immutable. Full message and attachment content is never written as a cache.

Poll queue insertion and checkpoint advancement are atomic. Processing labels an incoming message `Triaged` before recording success; a crash can replay an idempotent label write. Archive/restore intents persist before their external effect and retry. Done clears future reminders and cancels queued unsent reminder rows. New substantive messages update/reopen the original conversation ref. Pending model/provider work, stale polls/reconciliation/heartbeat and delivery uncertainty are visible through health and briefs.

Connect establishes a new-only baseline. `historical` queues an explicit bounded date window without changing intake checkpoint. `recover-history` explicitly queues the bounded recent Inbox scope and changes checkpoint to a profile-verified current head, together; oversize/failure leaves the old checkpoint. Neither runs automatically. Date scopes are limited to 31 days and 500 messages; larger history is handled in deliberately selected windows.

One poll processes up to 100 pending messages and reconciles ten oldest tracked conversations per account. Timing uses elapsed monotonic time as well as the wall-clock base so processing itself can reveal a missed five-minute target. The limit is an operational target, not a notification guarantee. A stopped process cannot announce its own failure; subsequent health checks/restart briefs report stale timestamps.

## Reproducible command inventory

All commands run from the standalone repository and bind `TMPDIR=$PWD/.local/tmp`. Dependency installations went through approved task-scoped escalation, using only `.local/backend` venv/cache. Tests involving Python async thread wakeups were separately approved outside the restrictive sandbox after preserving its stalls. Synthetic HTTP servers bind only loopback and use synthetic mail. Upstream and installed Hermes remain read-only.

```bash
scripts/setup.sh
ES_VENV_NAME=fresh-venv scripts/setup.sh
ES_PYTHON="$PWD/.local/backend/fresh-venv/bin/python" scripts/test.sh
TMPDIR="$PWD/.local/tmp" .local/backend/fresh-venv/bin/python scripts/validate_hermes.py --upstream "$PWD/.."
ES_PYTHON="$PWD/.local/backend/fresh-venv/bin/python" scripts/package.sh
```

The fresh setup creates a new venv from `requirements.lock`, then `pip check`; it does not reuse the pre-existing task venv. `package.sh` stages public source inside `.local/backend` and creates a native plugin directory tarball, sdist and wheel. CI config pins checkout/setup actions and the upstream SDK, installs the documented Linux parser prerequisites and runs only this package. CI has not been executed remotely.

## Evidence ledger

Evidence is ignored local build output, not a published artefact or independent review. Full command argv/results are recorded in `final-commands.json` after the final local runs. Initial and intermediate failures are retained rather than overwritten.

| Evidence under `.local/evidence/backend/` | Actual result and meaning |
| --- | --- |
| `01-initial-red.txt` | Exit 2: production API module absent at the start. Pytest initially inherited the outer root; attempted outside-cache writes were refused. Local pytest root/cache configuration was added before further runs. |
| `02-first-executable.txt`, `03-diagnostic.txt` | Async thread wakeup stalls in the restrictive sandbox; stopped with exit 130 after diagnostic capture. These are not passing tests. |
| `04-asgi.txt`, `05-sandbox-timeout.txt` | Sandbox ASGI thread wakeup stalls, timeout exit 124. |
| `06-synthetic-run.txt` | Exit 0: first five backend entrypoint tests outside the restrictive sandbox. |
| `07-safety-red.txt` | Exit 0 despite the early filename: twenty then-current backend/safety tests passed. The filename is retained accurately here, not claimed as RED. |
| `08-invariant-red.txt` | Exit 1: six genuine failures—four malformed-rule 503 cases, truthy-string private confirmation, display-name important-contact urgency. |
| `09-invariant-green.txt` | Exit 1 despite filename: root relative plugin import conflicted with pytest's package import. Preserved as a failure. Entry import was made lazy without changing native semantics. |
| `10-invariant-green.txt` | Exit 0: 36 backend/worker/boundary tests passed after those fixes. |
| `11-native-validation.txt` | Exit 0: actual copied-plugin manifest/capability validation and discovery from outside the source cwd; tool/slash/CLI/router and four OAuth declarations present. Optional upstream tool imports warn about absent requests in the minimal SDK test env. |
| `12-transport-native.txt` | Exit 0: five real Gmail-adapter/synthetic HTTP and actual Hermes session/model adapter tests. |
| `13-owner-binding-red.txt` | Exit 1: changing configured owner could inherit old profile metadata; fixed with durable home+owner binding. |
| `14-backend-green.txt` | Exit 0: 43 backend/transport/native tests passed after owner binding/concurrency changes. |
| `15-native-outbound-red.txt` | Exit 1: dispatching the intentionally unregistered `send_message` tool did not send. Fixed to use the actual host send helper. |
| `16-full-green.txt` | Exit 0: 59 then-current Python tests, including the real extraction/OCR suite, passed. |
| `17-reminder-red.txt` | Exit 1: an already queued reminder survived Done. Fixed by cancelling pending/retry reminder rows transactionally with Done. |
| `18-fresh-setup.txt` | Exit 0: separate clean task venv installed tracked lock and passed `pip check`. |
| `19-presentation-red.txt` | Exit 1: hostile subject retained a Hermes `MEDIA:` file directive. Fixed by neutralising directives and untrusted file separators. |
| `20-final-tests.txt` | Exit 0: 62 tests passed in the separate fresh venv before the timezone contract regression was added. |
| `21-final-native.txt`, `22-package-build.txt`, `23-wheel-install.txt` | Exit 0: then-current native discovery/validation, native bundle/sdist/wheel builds and offline wheel target install. |
| `24-installed-wheel.txt` | Exit 1: the first smoke script constructed incomplete OOXML; the parser correctly reported unreadable. The fixture was replaced by the real fixture generator without weakening assertions. |
| `25-timezone-red.txt` → `26-timezone-green.txt` | Exit 1 (six failures) → exit 0 (seven tests): actual effective-profile timezone inheritance, non-Melbourne next brief, explicit override, malformed and unset config. |
| `27-installed-wheel-green.txt` | Exit 0: installed wheel ran actual DOCX through the real worker, without a source-tree cache or durable full content. |
| `28-final-tests.txt`–`32-final-wheel-smoke.txt` | Exit 0 for all five commands: final fresh-venv suite, actual isolated native discovery/validation, package build, offline wheel install and real DOCX worker smoke. `final-commands.json` records exact argv/exits and elapsed time. |

Backend-owned tests are `test_backend.py`, `test_boundaries.py`, `test_worker_safety.py`, `test_gmail_transport.py`, `test_native.py` and `test_timezone.py`. They exercise real application/API/action/worker entrypoints, a synthetic HTTP Gmail server, actual SDK session context/identity types and the real local parser. Parser-only tests remain extraction-lane owned; Desktop tests remain UI-lane owned.

No overall review verdict, freeze, commit or remote action is issued by this implementation lane. Live Gmail OAuth, real private Discord delivery, actual Desktop host/browser/mobile behaviour and user model acceptance remain UNRUN. The parent integrates all lanes and owns final exact-candidate independent review.

## Accepted repair cycle 1

Gmail clients require an expected receiving address and use it in every resource URL. Provider-enforced addressing survives per-request host credential changes; profile checks alone are not the boundary. Automatic archive intents store the assessed message ID and use message modify; stale or legacy thread-wide automatic intents cancel instead of touching a newer obligation. Explicit owner archive/Done stays thread-scoped. Final body transforms/joins carry a review hold on truncation. Outbox sends recheck current private/destination/quiet policy per effect. Rule-matched and consent-off briefs carry bounded extractive substance and quoted explicit deadlines, never inferred dates or automatic reminders.

The supported configured-model API may use user-owned host fallback routing. New model-routing-v2 consent discloses that behaviour and limited endpoint/attempt visibility; old approval is not reused. Public SDK provider/model/audit.task metadata is labelled as reported, persisted in decisions/reasons, and not claimed as physical-route proof. No route override, new auxiliary slot, private host patch or global routing change is used. Failures remain pending with honest error text.

Host dependencies now align to pinned upstream [web]: FastAPI 0.133.1, Starlette 1.9.0, Uvicorn 0.54.0 and python-multipart 0.0.32. The new private repair venv installed the real distributions together with the plugin bounded declaration and passed actual version/import checks and pip check. PM keeps exact core pins and inherits upstream overrides; no web override/forced downgrade is required for this set. This is the actual web/SDK qualification subset, not a claim that every Hermes optional extra was installed as a union. Hosted CI remains UNRUN; its Python target now matches the pinned SDK runtime (3.14). Old qualification venvs/archives were not changed.

## Cycle 2 conversation context

Each eligible message is still assessed, Triaged and durably completed. The item
keeps the meaningful unresolved context in its existing summary/deadline/reason/
holds/urgency/received/latest_message fields. On-demand inspection and reference
preview fetch that message, not a later informational receipt. Separate bounded
activity_message/activity_received scalars record the latest assessed arrival.
Gmail internalDate orders substantive context; older or equal-date open contexts
are retained conservatively rather than sorted by opaque message IDs. A previously
unassessed request may upgrade FYI even if an informational receipt is newer.

Explicit owner actions/corrections record an owner_received provider-date floor
and owner_queue durable job-rowid fence. Already queued work cannot undo that
transition; jobs are retained, so these rowids remain stable. A newly queued
substantive message may reopen Done, including an equal-date arrival after the
queue fence. Sent dates fence earlier incoming work while retaining Waiting.
Informational mail preserves open/Done context and explicit snooze/reminder state.
Only a newly accepted context can create automatic archive or assessed urgent
effects; independent attachment danger warnings remain immediate. No body cache,
assessment-history framework, new routing policy or REST payload field is added.

## Repair 3: content evidence, pending activity and existing owner state

Context replacement uses typed context_source evidence from current body/extracted
text, an approved matching body rule, or a bounded quote returned by the consented
configured model and verified against current content. Final category and inherited
subject alone are not evidence of a new obligation. A small conservative clause
recogniser excludes acknowledgement/quoted-line preambles; it is not perfect NLP.
Original continuations preserve explicit deadline punctuation/times. The optional
model context_evidence quote is transient, never stored; only its source enum is.
No model route, consent version, provider override or extra service is introduced.

When current activity needs review without replacing the live request, a single
bounded activity_review record holds its message pointer, redacted summary/reason,
classification, attachment status/holds and separately attributed reported model
metadata. The highest unresolved attachment severity survives later acknowledgements.
Latest activity subject is separate. Public attachment status/holds conservatively
include the pending warning; existing request summary/deadline/reason/urgency and
text target remain. Real briefs expose both; on-request attachments cover the request and review
messages (20 total, labelled by message) while text/reference preview retain the request. Done clears this pending
review record; these heuristics are not malware clearance or a message-history store.

Before intake/retry and before repeated Done, a SQLite transaction initialises
missing owner fences for genuinely controlled existing records: Done/Waiting,
explicit timing fields, persisted non-automatic owner effects or the old format's
exact author-written correction marker. That final marker is a narrowly scoped
compatibility sentinel only when the new context_source field is absent; a new
model reason cannot confer owner authority. Ordinary items are not blanket-fenced.
Queue rowids/date floors persist idempotently, preserving existing Sent authority.
Only stale automatic intents are cancelled; jobs/history/triage and explicit owner
intents remain. New owner operations carry a typed owner_controlled marker.

The real compatibility regression launches actual repair1 production to seed its
old JSON/database, exits, then opens the SAME database in a separate successor
process. Set ES_LEGACY_SOURCE to an exact local archive of
3efca2b3f3831f1d45cd06c4647a4bf5555893f7 for this gate. For example:

```bash
mkdir -p .local/backend/repair-3-legacy-source .local/tmp
export TMPDIR="$PWD/.local/tmp"
git archive 3efca2b3f3831f1d45cd06c4647a4bf5555893f7 | tar -x -C .local/backend/repair-3-legacy-source
ES_LEGACY_SOURCE="$PWD/.local/backend/repair-3-legacy-source" scripts/test.sh
```

Without that explicit archive, the eight production-upgrade tests are reported
SKIPPED, never counted as compatibility qualification. Repair3's full local
aggregate supplies it, with zero skipped gates. No old environment or live state
is migrated during the build; all persisted compatibility fixtures are synthetic.

## ES-002 current contract

The gateway-neutral grant, shared plaintext command and host delivery path supersede the historical Discord/session-projection descriptions above. See [NATIVE-GATEWAYS.md](NATIVE-GATEWAYS.md) for G01–G10, platform restrictions, config-wide conservative invalidation and actual synthetic native boundaries. Model-routing-v2 and R01–R10 business requirements remain unchanged. Historical repair budget (inactive); original residual closing review remains pending.
