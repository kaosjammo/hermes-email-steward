> Historical synthetic engineering notes. These results refer to earlier internal candidates, not acceptance of this unfinished public snapshot. Current status: https://github.com/kaosjammo/hermes-email-steward/issues/1

# R01–R10 implementation and qualification map

**Current status: accepted repair 3, consumed 3/5, remaining 2; locally qualified, parent combined-candidate acceptance pending.** Cycle 2 closing verdicts were A NOT_READY / B scoped PASS, combined NOT_READY for R2-A-001/002. The sourced model-routing-v2 authority remains unchanged. Earlier receipts are historical, not rebound to new backend bytes. Gateway expansion is now ES-002 implementation scope; parent will review the eventual combined candidate and alone declare readiness.

This map describes implementation and locally executed evidence, not an independent review verdict or live-readiness claim. The parent owns final integration, source freeze, issue updates and independent review. The parser and Desktop lanes retain their own acceptance evidence.

## Historical cycle 1 qualification

The current repair candidate addresses A-001–A-006, ES-B-002 and Minor
ES-B-003. ES-B-001 duplicates A-002. The six original Important defects plus
A-006's separately accepted disclosure/consent defect are tracked in
[BUILD-HANDOFF.md](BUILD-HANDOFF.md#accepted-repair-cycle-1-successor).
Initial review verdicts and controller reproductions remain unchanged.

All executable source, tests and dependency declarations were hash-bound to a
fresh isolated copy before the aggregate. That copy passed **104 Python tests**,
**7 component tests**, **1 environment test**, **18 actual-API browser checks**,
**10 actual upstream renderer/SDK checks**, and **5 actual token-verifier checks**.
Actual copied-plugin validation/discovery, real installed host-web/plugin
dependency compatibility, bundle/sdist/wheel builds, offline wheel installation
and installed-wheel real DOCX processing exited 0. Detailed logs, manifests,
screenshots and failure history are under `.local/evidence/repair-1/`.
Only handoff/acceptance/issue documentation changes follow these source-bound
runs; final artifacts are rebuilt from the successor archive.

| Requirement | Additional repaired boundary and regression |
| --- | --- |
| R01, R02, R04, R08 | All Gmail URLs use the verified receiving address; actual host helper plus synthetic HTTP bearer retargeting proves provider denial with zero foreign resource successes, effects or checkpoint commits |
| R02, R05 | Automatic archive is assessed-message scoped; batched and stale retries preserve newer reply eligibility, obligation, urgency, reference and unread state; explicit owner thread actions remain |
| R03 | Useful bounded redacted local request/deadline summaries for matched and consent-off mail; actual public host routing under renewed v2 consent; missing, revoked and old consent make zero model calls |
| R06 | Current owner/profile/private grant, destination and quiet policy checked separately before each native send; revoked second send remains pending with zero forbidden invocation |
| R07 | Final MIME and body/attachment joins account for separators; discarded content produces visible unreadable/review hold and no automatic archive |
| R09 | Same production API/store under corrected host dependencies; synthetic-control browser and actual upstream SDK flows rerun on the repaired source |
| R10 | FastAPI bound aligns with pinned host web extra; new locked private environment, actual imports/registration/API and included sdist Desktop guide |

This is builder-executed qualification, **not successor independent acceptance**.
Native Electron, canonical gateway/background lifecycle, real session redemption,
profile switching, broader actual-host state/error/narrow/conflict flows, live
Gmail/OAuth/Discord/browser/mobile/model quality and hosted CI remain **UNRUN**.
The earlier tables below describe the historical initial candidate.

## Historical initial integration qualification, 05/11/2026

All implementation writers are terminal and their reports joined. Lead initial
stabilisation additionally repaired installed-parser temp paths, model-tool
thread projection, account-slot reauthorisation on item reads/effects, and the
compact FYI brief grouping. Actual RED failures and subsequent GREEN outputs
remain under `.local/evidence/integration/` and extraction evidence. Review
repair dispatches consumed **0**; this is implementation qualification only.

| Layer | Final local evidence | Scope |
| --- | --- | --- |
| Python production API/action/worker/parser/native protocol | `10-final-python.txt`: 74 passed, exit 0 | Real local extraction/OCR and actual SDK context types; synthetic Gmail/HTTP/delivery/model inputs |
| Desktop dependency/setup | `desktop-scoped-setup-approved.txt`: tracked lock npm ci, exit 0; `04-pinned-browser-install.txt`: task-local pinned Chromium, exit 0 | Fresh tracked manifest/lock, no personal-cache dependency; initial sandbox EPERM preserved |
| Desktop component/environment interactions | `desktop-components-portable.txt`: 7 passed; `desktop-environment-tests.txt`: 2 passed; exits 0 | Real React/query, synthetic SDK controls/host atoms |
| Browser full UI state matrix | `11-sealed-browser.txt`: 18 checks, exit 0; `desktop-sealed/` receipts and 14 PNGs | Actual final router/service/SQLite; synthetic SDK/identity/provider; sandboxed task-local Chromium |
| Actual upstream browser Desktop renderer/SDK | `.local/real-desktop-host/reruns/sealed-source/qualification.json`: 10 checks, 15 API calls, zero page errors, exit 0 | Unchanged supported `build:webapp`, real disk ESM loader/components/registry/profile-aware ctx.rest; synthetic surrounding shell RPC/auth grant and Gmail |
| Actual upstream token verifier | Same rerun `identity-protocol.json`: 5/5, exit 0 | Production API/security plus real host verifier; newly minted synthetic host token, explicit profile grant; no full middleware/ticket-redemption claim |
| Native validation/discovery and distribution | `12-native-final.txt`, `13-final-package.txt`, `14-wheel-install.txt`, `15-wheel-smoke.txt`: all exits 0 | Actual copied-plugin discovery outside repo cwd; native bundle/sdist/wheel; fresh offline wheel target and newly processed real DOCX through actual Worker, synthetic Gmail |

The 25-file executed actual-renderer candidate manifest equals the current source
after the runs (`runtime-binding-cleanup.json`: no drift). The original host
owner's earlier snapshot remains separately retained and is not rebound to the
changed source. Recorded task hosts are stopped, ports closed, browser commands
joined and own T3 tab closed. Upstream baseline remains
`b63eb8bf5a7a09e33b6d63077ec4e7df7361780b`; the qualified Webapp source hash is
`ecbde7c1424efda3bc466c33c0747faf54280667bb68b0053e24f954210d34b5`.

Actual renderer evidence closes the local SDK core-flow gap, while native
Electron, canonical gateway/background lifecycle, real auth redemption/profile
switching, actual-host broader state/error/narrow/conflict flows, live Gmail and
Discord delivery, Google browser account/mobile links, model quality and hosted
CI remain **UNRUN**. Synthetic narrow rendering is not Gmail mobile acceptance.

| Requirement | Backend implementation | Executable local evidence | Remaining external gate |
| --- | --- | --- | --- |
| R01 individual/multiple Gmail accounts/private controls | Native manifest/register, separate declared `gmail-1`…`gmail-4` grants, verified mailbox profile, owner/private guards, common Desktop/Discord service | `test_gmail_transport` runs two accounts through real Gmail adapter + synthetic HTTP server; `test_backend`/`test_native` exercise guards; actual isolated Hermes discovery registers tool/slash/CLI/router | Real OAuth consent, two distinct real accounts and private Discord adapter delivery UNRUN |
| R02 new-only intake/durable state | Connect history baseline, atomic queue+checkpoint, unique account/message IDs, separate obligations/location/Triaged/read state, durable mutation intents, scoped historical/recovery commands | Real HTTP baseline test excludes older message; worker crash cases before/after queue, after label/processing; retry, mixed-account failure and explicit bounded recovery tests | Real history retention, Gmail pagination/rate limits and manual provider changes UNRUN |
| R03 rules/consented judgement | Same casefold AND validator/service/store for all surfaces; explicit pack installation; body/substance/uncertainty holds; `ctx.llm.complete_structured` only after content consent; corrections suggest rules, `always` requires explicit rule | REST+chat parity, conflict and pack-scope tests; real DOCX request content overrides FYI; consent/model-failure tests; adapter test checks bounded redaction and absence of model/provider overrides/tools | Live configured-model quality, account-specific business judgement and user consent UNRUN |
| R04 references/aliases/links | Account/thread uniqueness, NFKC/casefold local-part first+last letters, profile-global AUTOINCREMENT suffix, immutable digest mappings, ambiguous alias refusal, encoded account Gmail URL | Restart/account/prefix/alias tests and real HTTP two-account isolation | Browser Google multi-login `authuser` and native mobile opening UNRUN |
| R05 lifecycle | Done/archive/restore separate from read; snooze expiry restore; explicit reminders; Waiting/sent detection; manual archive retains obligation; one-off/always correction | Worker/action concurrency, manual archive, sent replies, snooze/reminder/done tests; queued reminder cancellation RED→GREEN; public REST/chat correction tests | Real Gmail sent/thread/location timing UNRUN |
| R06 scheduling/urgent/private delivery | Timezone/DST slots, schedule overrides, quiet/bypass, due reminders, immediate per-message urgent delivery, private persistent outbox; late/stale/pending/uncertain health prevents all-clear | DST gap/fold and quiet tests; durable slot dedupe; crash-after-send uncertainty; real native outbound helper dispatch with synthetic final send; private destination and revoked grant tests | Actual Discord delivery/reconciliation, phone notifications and live five-minute operation UNRUN |
| R07 attachments | Real extraction API, private profile scratch, batch stop on danger, immediate warning, unresolved/truncation holds, only requested extract presentation | Parser lane's real format/OCR/kernel tests; worker uses real dangerous PDF, DOCX and broken/legacy files; batch second loader never called; SQLite contains no full raw/extracted payload markers | Recognition of every malicious file is not guaranteed; live provider attachment fetch/OCR quality UNRUN |
| R08 privacy/profiles | Owner-only SQLite/lock/scratch, durable home+owner binding, profile-bound worker context, no durable raw bodies; redaction/escaping/no active mentions/media directives | Permissions, owner-change isolation RED→GREEN, real bound Hermes source context, private principal rejection, transient-text assertions | Production filesystem/backups/host-process trust and real secret-format coverage require owner verification |
| R09 Desktop/shared rules | Protected REST exact v1 router; no second rule store; atomic CAS; scope-aware idempotent packs; validated preview without model/write; item correction | Real FastAPI REST exercised with trusted synthetic native principal, malformed JSON/schema negatives, foreign/missing grants, version-conflict current object and chat parity. `scripts/backend_fixture.py` supplies durable synthetic backend for UI owner | Parent/Desktop lane owns rendered UI/native host interaction evidence. Backend tests alone do not establish it |
| R10 runnable package/docs/qualification | Fresh-checkout locked task setup, reproducible test runner, source+wheel+native bundle builds, actual copied-plugin validation/discovery outside cwd, scoped CI | `.local/evidence/backend` and `.local/evidence/integration` contain commands/results and genuine initial/invariant failures; `scripts/setup.sh`, `test.sh`, `validate_hermes.py`, `package.sh`, portable Desktop setup/runner | Hosted CI and final independent review UNRUN; source identity/freeze recorded in BUILD-HANDOFF; no push/PR/live install authorised |

The provider-visible label is exactly `Triaged`; adding it does not resolve obligations, archive, or change read/unread. Successful processing is recorded only after that label operation succeeds. Replayed idempotent provider writes after a crash are possible, while message IDs/alerts/digest mappings remain deduplicated locally.

Network delivery cannot honestly be qualified exactly once: the supported host send surface has no idempotency key or post-crash receipt lookup. Uncertain rows require private owner reconciliation or explicit duplicate-risk retry. A two-day bounded brief catch-up avoids unlimited old deliveries; unresolved obligations remain in subsequent briefs. Intake history overflow/expiry never silently advances. Explicit `recover-history` states the bounded recovery scope and current-history cutover.

No live Gmail access, credentials, real private mail, existing independent triage automation, running Hermes installation, external repository creation, push, PR or deployment was used. Backend evidence is source/local/synthetic unless explicitly described as actual upstream discovery or real local parser execution.

## Cycle 2 current qualification

Consumed **2/5, remaining 3**; fresh independent successor acceptance pending.
R1-A-001 and controller later-FYI extension are repaired at production Worker/
Store/brief/inspection/REST boundaries. R02–R06 preserve unresolved substance,
meaningful text target, chronology and explicit owner/Sent transitions while
finishing each eligible message. ES-R1-B-001 fixes R10 actual sdist inventory.

Stable aggregate **123 passed**, copied independent wire **18 passed**, copied
controller later-FYI **1 passed**, Desktop component/environment **7/1 passed**,
native discovery/compatible dependency checks/package/installed artifact smoke
exits0, recorded under `.local/evidence/repair-2/`. BUILD-HANDOFF.md contains
exact provenance and preserved RED/setup history. The existing concurrency test
now explicitly dates its intended newer reply; its assertions are unchanged.
Prior closed boundaries reran; sourced routing-v2 policy remains byte-identical.

Unchanged renderer/SDK/visual/parser/model analysis is explicitly reused after
hash verification. Historical screenshots are not current changed-backend proof.
Current protected REST/wire/worker tests supply that proof. The earlier R01–R10
mapping remains an implementation guide within its stated historical evidence
scope; all live/native/full-host/mobile/CI gates and security limits remain UNRUN
or bounded as listed in the current handoff. Parent alone declares readiness.

## Repair 3 current qualification (pre-expansion)

R2-A-001: content-source evidence now differs from final category. The unresolved
request/deadline/reason/urgency and text/extract target coexist with current
activity review, independent model attribution and conservative attachment holds.
Acknowledgements/inherited subjects do not erase the action; genuine body, real
attachment, approved body-rule and grounded consented model evidence still update.
Actual briefs, inspection and protected REST reference preview are exercised.

R2-A-002: actual repair1 production seeds old JSON/SQLite in one process; successor
opens it in another. Done, repeated Done, correction, Waiting, snooze, reminder and
archive survive stale queued work without stale urgent/archive, while ordinary
items remain unfenced and genuine arrivals after the compatibility fence reopen.
No queue/history deletion or blanket migration. The fixed old correction marker
is compatibility-only; new model text cannot impersonate owner authority.

Final fresh-copy aggregate **149 passed / zero skipped**, actual old archive
explicitly provided. Original wire18, residual21, component7/environment1 file,
native/dependency/package/install affected smoke exits0, recorded under
`.local/evidence/repair-3/`. Prior red/failing outputs and staged source/package
remain separately retained. Model-routing-v2 disclosure/consent constants and
sourced authority are unchanged; actual public model adapter/recovery is rerun.

This is builder qualification, not final acceptance. Gateway expansion is future
ES-002 and is not implemented here; parent will bind eventual combined-candidate
review/readiness, reusing unchanged proof. All historical local/live/native/full-
host/mobile/CI limitations persist. **3/5 consumed, 2 remaining**, no budget reset.

## ES-002 current contract

The gateway-neutral grant, shared plaintext command and host delivery path supersede the historical Discord/session-projection descriptions above. See [NATIVE-GATEWAYS.md](NATIVE-GATEWAYS.md) for G01–G10, platform restrictions, config-wide conservative invalidation and actual synthetic native boundaries. Model-routing-v2 and R01–R10 business requirements remain unchanged. Historical repair budget (inactive); original residual closing review remains pending.

## ES-002 exact-copy builder qualification — 06/11/2026

Feature implementation on the same branch/owner; repair budget cap5/consumed3/remaining2 unchanged. Qualified source copy `.local/evidence/es-002/attempt-02/candidate/` passed 201 Python tests with no skips (aggregate-01, exit0), including both original obligation/legacy fence families, model consent/routing, extraction, OAuth, outbox and protected REST. Native gate/grant focused suite52 passed; actual SDK registry/default dispatch tests use explicitly synthetic final HTTP/WebSocket/process seams. Real CLI/daemon/live gateways remain UNRUN. Seven React component checks and environment checks passed; unchanged renderer/browser screenshots are reused only within their original byte scope.

Native validation/discovery exit0 retains inspected private-core seam warnings. Build, actual host dependency union, exact installed lock/pip consistency, bundle/sdist member checks and offline wheel+sdist install exit0. Both installed artifacts passed real DOCX plus unsupported-followup/current review/old request/inspection/Done, actual old-production SQLite seed and new substantive reopen smoke. Commands/log SHA256s are in unique JSON receipts. Final doc-only package/member/install checks and exact final head/tree/inventory/artifact hashes are indexed by `final-seal.json`. No executable drift from the aggregate is permitted. Preserved predecessor77 and prior repair3 evidence210 hashes match.

G01–G10 map: inventory/zero-call negatives (`test_gateways`, `test_native_gateways`); setup/source/context/collisions/plaintext (`test_native_gateways`); generation/ABA/chunks/legacy history (`test_gateways`, `test_repair_cycle1`); dialect/receipts actual native payloads (`test_native_gateways`); original R01–R10 and legacy residuals (complete201 aggregate); distributions/host dependencies (`test_distribution`, install smokes). Platform limits and concrete executed seams are in NATIVE-GATEWAYS.md.

No new child or gateway process was started; test subprocesses are joined. No external action occurred. Parent must freeze and run TWO fresh independent combined reviews; R2-A-001/002 remain pending those closing assessments. No PR-ready/overall review PASS or issue closure is claimed.

## Accepted repair 4

ES002-A-001: Photon/BlueBubbles are notification-only because genuine/fallback actor provenance is indistinguishable at the supported bridge. ES002-A-002: each ntfy effect requires the actual live server to match fresh config and the full selected grant; stale/missing live route blocks before native/HTTP calls. ES002-B-001: registered lifecycle tests now use bounded future dates and assert real Waiting/snooze/reminder/location/Done/cancellation state and error absence. No scheduling bound changed. See NATIVE-GATEWAYS.md and the local ES-002 ticket for computed policy counts and exact review contributions. Ledger cap5/consumed4/remaining1. Original R2-A-001/002 closed independently for 7ee421d; successor regressions and fresh independent closing assessment remain required.

Repair4 local qualification: 212 Python tests/no skips; components7/environment2; native registration/discovery,93 exact installed dependency pins plus host contract/pip consistency, native bundle/sdist/wheel and offline installed real-format/legacy smokes all exit0. Per-finding zero-effect and positive controls are in tests/test_gateway_admission.py and strengthened tests/test_native_gateways.py. Final exact-source/artifact/command index: `.local/evidence/repair-4/final-seal.json`. This is builder evidence only; fresh independent successor assessment is pending.


## ES-004 native UI and gateway presentation goal

The original R01–R10 and sourced model-routing-v2 contract remain unchanged. See [ES-004](https://github.com/kaosjammo/hermes-email-steward/issues/1) for the eight-part design rubric and independent per-reviewer >=9.5/PASS criterion. Four historical engineering repairs are preserved; the scoped design loop is UNCAPPED, not a reset of that history. No council scores or design acceptance yet.

Round1 builder evidence:215 Python tests/no skips;7 component and2 environment tests; actual native registration/dependency and package checks;33 actual upstream browser-renderer interactions with31 screenshots across explicitly preserved partial runs/continuations;157 native gateway assertions over22 captured scenarios. Synthetic host identity/provider/final transport seams remain explicit. Gateway copy tests exercise command after-state, redaction, urgent/brief substance and safe bounded chunks. Existing owner/fence/OAuth/obligation/extraction/model/private-route suites remain in the aggregate. New images are bound to executed source hashes, not relabelled historical screenshots. Final package/member/offline install receipts and exact source identity are indexed in the round seal. Three fresh independent reviewers and parent readback remain required; live/native/hosted limitations above are not waived.
