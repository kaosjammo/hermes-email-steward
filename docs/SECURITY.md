# Backend authority and privacy boundary

The production plugin uses the owning Hermes profile's configuration and local state. Client request JSON and headers cannot choose an owner, profile, provider slot, private destination or authorisation flag. The synthetic fixture app deliberately supplies a test principal; it never composes a real Gmail provider and is never loaded by native plugin registration.

## Supported HTTP identity

This implementation was checked against upstream Hermes `b63eb8bf5a7a09e33b6d63077ec4e7df7361780b`, with the actual sources at:

- `hermes_cli/dashboard_auth/native_http.py::authenticate_native_http`: the host redeems a one-request private ticket, verifies served profile/capabilities and attaches `request.state.native_http_principal`.
- `gateway/runtime_bootstrap.py::TicketStore`: native-http grants contain `profile_id`, `subject`, `purpose`, `capabilities`, `scope`, `instance_id` and a restart flag. `gateway/control_socket.py::_posix_peer_subject` derives local POSIX subjects as `uid:<peer uid>` after same-user socket/home checks. The plugin does not redeem/recreate tickets itself.
- `hermes_cli/dashboard_auth/middleware.py`: the host verifies a provider login and attaches a typed `Session` to `request.state.session`.
- `hermes_cli/web_server.py::_has_valid_session_token`: the host compares its configured Desktop/dashboard session token. The Desktop SDK's REST bridge supplies host authentication; custom plugin headers are not required.

With `private_confirmed: true`, a nonblank configured platform-qualified `owner` and exact private `destination`/`destination_type`, HTTP access additionally needs one of these explicit profile settings:

| Setting | Required verified host identity |
| --- | --- |
| `desktop_subject: "uid:1000"` (example uid only) | Native principal `subject` exactly matches, `profile_id` equals this resolved profile home, `purpose == "native-http"`, `scope == "profile"`, and capabilities exactly `{"http:owner"}`. No wildcard or arbitrary dictionary from request JSON is accepted. |
| `desktop_session_user`, `desktop_session_provider`, `desktop_session_issuer` | Actual upstream `Session` instance with exactly matching `user_id`, `provider`, `issuer` and future `expires_at`. Email/display name/org are not used as identity. Missing issuer is explicitly represented by an empty configured string. |
| `desktop_local_token: true` | The real host `_has_valid_session_token(request)` must verify the credential on that request. `request.state.token_authenticated` alone and generic service-token principals do not grant access. This option explicitly delegates this profile's plugin to the host's single-owner token. |

All settings default to no Desktop grant. Anonymous loopback, `X-Owner`, body fields, guessed private channel names, truthy strings such as `"false"`, foreign profiles, expired sessions, unsupported host identity types and broader-purpose grants fail closed. API error responses contain safe messages, not traces, credential values or raw mail.

The real upstream request-state seam is trusted because the host authenticates and attaches it; HTTP callers cannot assign Python request attributes. Tests bind a **synthetic trusted host principal** in their app middleware, exactly as required by the shared contract. Production routes do not install that middleware. Source code running inside a trusted host process can alter process state, which lies outside this HTTP boundary.

Current qualification supports Hermes' in-process native backend identity path. Hosted-plugin IPC identity transformations are not qualified; a host mode that forwards only an auth boolean is refused. The actual validator reports its generic host-isolation compatibility assessment, which is not evidence that the plugin's owner identity survives every hosted deployment. Private-core identity imports produce validator warnings and may require requalification on upstream changes; unsupported changes fail closed rather than accepting an anonymous fallback.

## Native gateways, CLI and background authority

See [the ES-002 contract](NATIVE-GATEWAYS.md). Actual SessionSource plus off-wire RoutingIdentity and receiving adapter bind the selected platform, human actor, chat/type/thread/parent, native tenant/account context and profile/home. Reconstructed/serialized sources, inferred/relay routes and the reduced model-tool bridge cannot supply private authority. The tool accepts command only and provides public help; plaintext native commands retain the shared backend.

The local operator CLI explicitly grants one destination and allocates a durable monotonic revision before configuration writes. Private confirmation is disabled until setup completes. A deliberate regrant can transfer ownership inside the same profile; it does not migrate state across homes. All old queues/approvals/consent are invalidated. Native interactive routes need an actual-source command attestation under the current generation before private notifications. DM labels are not membership proof; the operator remains responsible for destination privacy.

Background scope remains the host-owned profile runtime scope. The supported user config version token conservatively revokes work on ANY user-layer config edit, including unrelated settings and switch-away/back. The next native command reattests the new grant; prior pending/uncertain work is never rerouted. Already in-flight native requests cannot be recalled. This is not a universal hidden SDK retry veto.

Provider/action work uses a process-safe lock shared by workers and owner actions. SQLite `BEGIN IMMEDIATE` protects atomic checkpoints, queue insertion, rule CAS, pack installation, correction+approved rule and outbox identity. No network operation occurs while a SQLite write transaction is held. A connected slot's `/profile` address is verified every poll. Message IDs, threads and mutation intents always carry their account identity.

## Outbound notifications and untrusted mail

Native notifications call `tools.send_message_tool.send_message_tool`, the same host-owned entrypoint used by `hermes send`. Upstream intentionally does **not** register `send_message` as a model tool. It retains the host's relay/adapter policy. The plugin supplies only its configured exact native destination and its sanitised text; no mail-controlled destination, attachment path, API verb or model/tool instruction is accepted. Live adapter delivery remains UNRUN.

Sender/subject/summary/reason/extract output passes bounded secret/link redaction and HTML/Markdown escaping. Mentions become inactive fullwidth `＠`; mail-controlled media directives and local file path separators are neutralised so the outbound helper cannot interpret them as file uploads. Only generated account-specific Gmail links bypass generic external-link removal. A model prompt marks mail as untrusted data, exposes no tools, bounds input/output/time, and runs only after durable explicit content-disclosure consent. No plugin-selected fallback/model/provider override is requested. Under renewed model-routing-v2 consent, the host may try its existing configured fallbacks; the SDK may not expose every endpoint or attempt. SDK-reported metadata is retained with that limitation, never treated as a complete route audit. Prior model-content-v1 consent does not enable new model calls. Host routing errors leave jobs pending and briefs partial. See SCOPE-ADDENDUM.md for the primary-source correction.

Secrets can have arbitrary formats; these filters are conservative, not proof that all sensitive material is recognised. Summaries and rules remain sensitive. Keep state, profile backups and private deliveries owner-controlled. No durable full body or attachment cache exists. Parsers receive only bounded bytes and explicit 0700 profile scratch; see `EXTRACTION.md` for effective resource/kernel controls and their limits.

## Timezone and scheduling configuration

The supported Hermes profile source is the top-level `timezone` field in the effective `load_config_readonly()` configuration, as used by upstream `hermes_time.py` and declared in `config_defaults.py`. Empty plugin override inherits that value; a non-empty valid plugin IANA override wins. No configured timezone means scheduling fails with an actionable error, while rules remain usable. Malformed profile/plugin values are validation errors, with no Melbourne/server-local/location inference or global config mutation. Tests exercise America/New_York inheritance and next brief, London/Tokyo overrides, invalid types/zones and missing configuration.

## Crash and delivery semantics

Gmail label additions/removals are idempotent and never touch `UNREAD`. Queue/checkpoint changes commit together; successfully processed IDs are unique per account. Provider mutation intents survive a crash and retry. Digest mappings are immutable and ambiguous unqualified aliases refuse action. Done cancels future and queued unsent reminder notifications.

A host send success is recorded as sent. If sending began but success was not durably recorded, the outbox becomes uncertain and is not blindly retried. Owner confirmation or explicit duplicate-risk retry is available through private commands. This preserves uncertainty instead of claiming exactly-once network delivery. Failed/late/uncertain work prevents empty all-clear claims.

## Repair-cycle boundary corrections

All Gmail resource URLs name the verified expected receiving account; host credential re-resolution cannot turn users/me into a different mailbox. The provider enforces the explicit user address, including history/checkpoints, attachment fetches and cached label use. Preflight remains a useful check but is not the request binding. Automatic archive is message-scoped and stale automatic decisions are cancelled, preserving newer reply eligibility and current obligation/location state. Final content joins account for separators and transformations; discarded significance holds archive. Every outbox effect uses the current owner/profile/private grant, destination and quiet policy immediately before invocation; known uninvoked sends stay pending on revocation.

## Accepted repair 4

ES002-A-001: Photon/BlueBubbles are notification-only because genuine/fallback actor provenance is indistinguishable at the supported bridge. ES002-A-002: each ntfy effect requires the actual live server to match fresh config and the full selected grant; stale/missing live route blocks before native/HTTP calls. ES002-B-001: registered lifecycle tests now use bounded future dates and assert real Waiting/snooze/reminder/location/Done/cancellation state and error absence. No scheduling bound changed. See NATIVE-GATEWAYS.md and the local ES-002 ticket for computed policy counts and exact review contributions. Ledger cap5/consumed4/remaining1. Original R2-A-001/002 closed independently for 7ee421d; successor regressions and fresh independent closing assessment remain required.
