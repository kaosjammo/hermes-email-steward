> Current delivery uses the owner-created Hermes cron route in [CRON.md](CRON.md). Native commands return short text or post bounded parts through public call-bound `ctx.post_message`. The private adapter sender described in the historical implementation/evidence below has been removed. Its SDK/preflight results are not current cron qualification, and private adapter-attribute checks are no longer a plugin contract. Current exact-candidate and platform qualification is tracked in [source issue #2](https://github.com/kaosjammo/hermes-email-steward/issues/2).

# ES-002 requirements and acceptance addendum

This historical addendum records earlier native gateway boundaries; it does not establish current cron or live-delivery acceptance.
It supplements ES-001 and does not replace its Gmail, obligation, extraction, privacy, Desktop or configured
Hermes model contracts. Repair-3 predecessor and budget are recorded in
[ES-002](https://github.com/kaosjammo/hermes-email-steward/issues/1). Original requirements/history remain intact.

## Product boundary

One shared service/store, one explicitly selected private native destination, one qualified
owner. No broadcasts, transport SDK stacks, separate rule store, implicit home/name resolution,
cross-platform forwarding, automatic gateway activation or Gmail correspondence. Unknown
third-party platforms fail closed. Native means pinned core plus bundled platform plugins;
internal, unsafe, experimental, missing-dependency and live-activation states are explicit.

The operator grants canonical platform, exact native destination, optional exact thread/topic
(none means none), actual chat type, platform-qualified owner, tenant/account/transport scope,
receiving profile/home and runtime profile/home. Only necessary public identifiers and opaque
host references are stored. Explicit private-destination confirmation is necessary; a DM label
does not prove membership or exclude forwarding, push previews or shared devices.

Inbound authority uses actual host SessionSource and off-wire RoutingIdentity/receiving adapter
provenance. Bots, anonymous/fallback actors, rejected/inferred routing, wrong platform, owner,
scope, account, parent, type, thread or profile/home are denied. The model tool remains
command-only with additionalProperties=false; a reduced bridge lacking that evidence cannot
mutate state. Actual-source plaintext `/email-steward` remains the common command baseline.
Native Desktop HTTP/session grants remain separate and unchanged.

Outbound uses the existing host-owned send_message registry/default dispatch, with exact route
roundtrip and native account/type consistency. No plugin-selected SDK sender, model-facing
cross-platform send tool, host monkeypatch or upstream/global changes. Known destination/type/
thread fallbacks are blocked. Email, ntfy and IRC have no human command authority merely by
having a transport. Email notification-only activation additionally requires demonstrable
self/intake-alias and automated echo protection; otherwise that route remains restricted.

Every plugin-owned durable row/chunk and explicit retry revalidates a fresh full grant and
monotonic generation. Grant changes invalidate old authority, including switch-away/back,
without rerouting pending/uncertain history or resetting Gmail/business state. Legacy Discord
settings/no-thread work migrate only where provable; ambiguous old bindings are quarantined.
An already accepted/in-flight host request cannot be recalled. Ordinary trusted same-recipient
host retries do not imply a universal per-network-effect permission hook.

Bounded plain-text chunks must fit the final dialect/encoded budget without silent truncation,
retain stable references and trusted generated Gmail links, and neutralise content directives,
mentions, formatting, controls/bidi, header injection and target overrides. Provider acceptance
is not human delivery/read. Skipped/no-op/partial/malformed/unconfirmed/ambiguous outcomes are
not complete; possible effects remain uncertain and require explicit duplicate-risk controls.

## Acceptance checks

| ID | Required executable boundary |
|---|---|
| G01 | Reconciled data-driven inventory of all 33 canonical native surfaces; unknown and internal routes make zero transport calls. |
| G02 | Explicit single grant setup/status; full platform/account/scope/profile/home identity and collision negatives. |
| G03 | Actual native plaintext command lifecycle; weak/anonymous/bot/reduced-tool authority denied; Desktop grants unchanged. |
| G04 | Actual native parser, registry and default dispatch at synthetic final transport seam; exact target/type/thread/account, no hidden recipient fallback. |
| G05 | Durable chunk/row generation, revocation, switch-away/back, explicit retry and narrow legacy migration; uncertain history retained. |
| G06 | Hostile text and encoded/dialect budgets through actual rendered host payloads; no directive/mention execution or silent loss. |
| G07 | Honest accepted/queued/blocked/uncertain handling of no-op, malformed, partial and timeout results; no blind retry. |
| G08 | Notification-only/unsafe/experimental/dependency limitations and email echo/intake restrictions are explicit, with zero-call negatives. |
| G09 | Full ES-001 regressions, including repair-3 obligation context/legacy owner fences, unchanged model-routing-v2 and extraction/privacy. |
| G10 | Native validation, dependency consistency, bundle/sdist/wheel/member checks, offline installed-artifact smoke, hashes and clean local commit. |

Local synthetic final transport proof is distinct from live gateway auth/private membership,
provider delivery/read, mobile, native Electron, canonical gateway lifecycle and hosted CI.
Those activation gates remain UNRUN unless independently executed under new authority.
The final capability matrix records exactly which actual source/SDK/dispatch ran and which
lowest transport boundary was synthetic. Reused UI/parser/model receipts retain their original
input scope and are not rebound to changed backend bytes. Parent alone declares readiness.

## Operator setup and operational limits

Run `hermes email-steward capabilities` for canonical names, required public context fields and missing Python dependencies. Select the owning profile explicitly; `--account PROFILE:PLATFORM`, `--transport-profile PROFILE` and `--transport-home ABSOLUTE_HOME` must match that runtime. `--scope` is the actual workspace/tenant/guild/server where required; `--thread` and `--parent` must exactly match the observed native source (omitting thread means none). Supply required public account/server values in `--route-context '{"field":"value"}'`; never tokens or credentials. URLs reject credentials/query/fragment. Setup does not activate any platform.

Use the README Discord example, substituting a supported canonical platform and its exact native identifiers. A host-authenticated `/email-steward help` in the selected conversation establishes interactive route attestation. Changed config, including unrelated user-layer edits, conservatively changes generation and requires reattestation and renewed model-routing-v2 content consent. Explicit local operator regrant may transfer the same profile's business state to a new owner; it is not an ordinary remote command. Unbound legacy rows are blocked, sending rows stay uncertain, and old bound rows retain their origin descriptor. No historical queue is copied to a new grant.

Plaintext commands share one parser/service. Responses use transient bounded chunks; explicit full-text/attachment inspection is never retained in outbox. Only receipt metadata survives; repeat a command explicitly if a reply is incomplete. A route with uncertain host receipts stops after the first uncertain chunk; large replies on that route may be incomplete and require Desktop/CLI inspection. No silent complete-delivery claim or automatic retry is made. Mentions/control/bidi/media/header syntax and formatting are neutralised; only trusted generated Gmail links retain URL syntax. Weixin line breaks become spaces to prevent its automatic chatty-line split.

## Capability and local executed boundary matrix

All rows require separate live activation/private membership/provider/mobile acceptance, currently UNRUN. Interactive means the shared plaintext source path is admitted only with exact off-wire identity and current attestation. Python dependency availability is reported dynamically; Buzz additionally needs its configured native executable/relay (actual CLI/daemon UNRUN). Shared/reassigned phone numbers, forwarded mail, shared devices and push previews remain privacy limitations. Email is deliberately restricted: current host SMTP/refusal and notification provenance do not establish the required safe notification boundary; this does not authorise Gmail correspondence.

| Canonical platform | Mode | Local native boundary / restriction | Public context |
|---|---|---|---|
| a2a | internal | Zero native send calls: Internal ingress/session surface; no private notification route | Profile native slot + observed scope |
| api_server | internal | Zero native send calls: Internal ingress/session surface; no private notification route | Profile native slot + observed scope |
| bluebubbles | notification | Actual adapter HTTPX; synthetic HTTP; exact GUID, notification-only actor fallback; no bridge started | server_url |
| buzz | interactive | Actual native CLI argv/receipt parser; synthetic subprocess boundary only; real executable UNRUN | cli_path, relay_url |
| dingtalk | unsafe | Zero native send calls: Default sender ignores chat_id in favour of static webhook | Profile native slot + observed scope |
| discord | interactive | Actual Discord REST/default sender; synthetic aiohttp HTTP | Profile native slot + observed scope |
| email | restricted | Zero native send calls: Host SMTP ignores refusal mapping and lacks notification provenance/intake-alias loop guard | Profile native slot + observed scope |
| feishu | interactive | Actual Lark SDK; synthetic requests HTTP | app_id |
| google_chat | interactive | Actual discovery client; synthetic httplib2; flat DM only | project_id |
| irc | restricted | Zero native send calls: Nick-only actor and writer-drain acknowledgement do not establish private recipient acceptance | Profile native slot + observed scope |
| line | interactive | Actual push sender; synthetic aiohttp; no ID => uncertain | Profile native slot + observed scope |
| local | internal | Zero native send calls: Internal ingress/session surface; no private notification route | Profile native slot + observed scope |
| matrix | interactive | Actual mautrix SDK; synthetic HTTPAPI; E2EE UNRUN | homeserver, user_id |
| mattermost | interactive | Actual v4 sender; synthetic aiohttp; flat only | url |
| msgraph_webhook | internal | Zero native send calls: Internal ingress/session surface; no private notification route | Profile native slot + observed scope |
| ntfy | notification | Actual live publish/default sender; server must match current grant/config before each effect; missing ID fabrication => uncertain | server |
| photon | notification | Actual adapter HTTPX; synthetic HTTP; notification-only, native actor fallback; no bridge started | project_id |
| qqbot | unsafe | Zero native send calls: Default sender probes different recipient scenes and can truncate | Profile native slot + observed scope |
| raft | internal | Zero native send calls: Internal ingress/session surface; no private notification route | Profile native slot + observed scope |
| relay | experimental | Zero native send calls: Authenticated connector capability grant not available here | Profile native slot + observed scope |
| signal | interactive | Actual standalone RPC/formatter; synthetic HTTPX; lost receipt => uncertain | account, http_url |
| simplex | restricted | Zero native send calls: Daemon-local contact IDs omit receiving account proof; default text sender is fire-and-forget | Profile native slot + observed scope |
| slack | interactive | Actual Bolt/WebClient/live unique team map; synthetic aiohttp | Profile native slot + observed scope |
| sms | interactive | Actual Twilio form sender; synthetic aiohttp; queued != human delivery | account_sid, from_number |
| teams | interactive | Actual Teams SDK initialise without listener; synthetic HTTPX | client_id |
| telegram | notification | Actual PTB SDK; synthetic HTTPXRequest; positive private ID only | Profile native slot + observed scope |
| webhook | internal | Zero native send calls: Internal ingress/session surface; no private notification route | Profile native slot + observed scope |
| wecom | interactive | Actual queue/correlation; synthetic final WebSocket; uncertain | bot_id, websocket_url |
| wecom_callback | interactive | Actual callback SDK + HTTPX; synthetic token/send HTTP; one app only | corp_id, agent_id |
| weixin | interactive | Actual adapter; synthetic aiohttp; generated ID => uncertain | account_id, base_url |
| whatsapp | restricted | Zero native send calls: Default standalone bridge accepts missing session ownership; legacy bridge cannot prove receiving profile/account | bridge_port |
| whatsapp_cloud | interactive | Actual adapter HTTPX; synthetic HTTP; bound phone-number ID | phone_number_id |
| yuanbao | interactive | Actual binary encoder/connection; synthetic WebSocket ACK; uncertain | app_id |

Executed identities and final results are recorded in BUILD-HANDOFF and the ES-002 evidence receipts. The matrix describes exercised local boundaries, not live provider success. No SDK import was fabricated to hide a missing dependency.

## Repair 4 boundary correction

Independent review found that Photon and BlueBubbles parsers fill a missing actor from conversation metadata. The public native command bridge cannot distinguish genuine/fallback values, so both are intentionally **notification-only**, including when an actor is present. No raw message/client attribute is promoted to authority. Explicit selected notifications retain exact account/server/route checks; management denials explain the limit. Other qualified platforms retain shared plaintext commands. Existing Desktop rule management and local operator setup/status/worker remain available; full plaintext lifecycle requires an interactive supported destination.

ntfy now requires a live adapter whose captured server exactly matches the current public server grant AND fresh host config. Missing or stale live route blocks before native invocation; standalone ntfy without a provable live adapter is conservatively held. Its topic continues to be explicitly supplied by the host default sender. Reconfiguring the server cannot send newly queued current-generation work through an old connection. Already-in-flight calls remain ordinary host behaviour; following plugin-owned rows/chunks stop on revocation/mismatch. The immediate server-context sibling checks retain their existing adapter/config comparisons; no transport or upstream rewrite was made.

Computed current policy counts (from CAPABILITIES): {"experimental": 1, "interactive": 16, "internal": 6, "notification": 4, "restricted": 4, "unsafe": 2} across 33 canonical surfaces. These modes describe admission, not live activation or human membership. All live gates remain UNRUN. Repair4 leaves one accepted dispatch remaining.
