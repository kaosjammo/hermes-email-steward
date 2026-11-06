# Email Steward shared API, v1

Status: initial implementation contract, 05/11/2026. Plugin id `email-steward`.
Desktop calls only `ctx.rest(path, {method, body})`, scoped by the SDK to
`/api/plugins/email-steward`. Qualified native gateways call the same Python service, validator
and SQLite rule store. Desktop has no second rule store. All examples are synthetic.

## Identity and errors

There are **no owner/user/profile fields accepted as authority in a body or
header supplied by the plugin UI**. Desktop uses the authenticated Hermes host
session, explicitly enabled for the owning profile and matched to its configured
Desktop principal. The backend must verify the actual upstream trusted request
identity (native principal or verified session), never trust an arbitrary
`X-Owner` header or a caller-supplied `request.state` boolean. The authenticated
single-owner local Desktop token may be explicitly authorised in profile
configuration; anonymous loopback alone is insufficient. Unsupported/absent host
identity fails closed. Tests bind a synthetic trusted host principal in the test
app, exercising the same service guard. Backend implementation documents precise
supported host identity/config fields; if a contract adjustment is necessary,
coordinate with the integration owner before changing this file.

Upstream identity readback: native HTTP middleware stamps a redeemed grant in
`request.state.native_http_principal`; the owner grant names `profile_id`,
`subject`, `purpose: native-http`, `capabilities: {http:owner}` and profile
scope. Match the profile and explicitly granted subject; a principal for
profile creation/registry access does not qualify. Verified dashboard
`request.state.session` exposes `user_id`, `provider`, `issuer`, `expires_at`;
match the configured tuple and reject expiry. Local Desktop session-token mode
must revalidate the request with the host's real token verifier and require its
explicit profile grant. `token_authenticated: true` by itself never qualifies.
The UI sends no identity fields, custom owner headers or plugin-stored secrets.

Native commands derive authority from actual Hermes SessionSource plus off-wire RoutingIdentity/receiving adapter. ES-002 requires the selected platform-qualified owner, exact private chat/type/thread/parent, native scope/account and profile/home. Reduced model-tool context cannot prove this and provides public help only. Merely naming a private channel is not a grant: local setup explicitly confirms privacy. All inspection, rule changes, previews, aliases and actions share the same service guards. Background work binds the owning profile. REST v1 schemas and Desktop grants remain unchanged; see NATIVE-GATEWAYS.md.

Every response is JSON. Successful GETs return the objects below; successful
mutations return `{ "rule": Rule }`, pack enable returns `{ "rules": [Rule] }`.
Errors use HTTP 400/401/403/404/409/422/503 with
`{ "error": { "code": "validation_error", "message": "...", "fields": {"name":"..."} } }`.
`fields` may be absent. Stale writes return 409 with code `version_conflict`
and `current: Rule` inside `error`. Never return traces, credentials or raw mail
in errors. Unknown JSON fields are rejected. No destructive/send actions exist.

## Mailboxes, rules and packs

`GET /mailboxes` → `{ "mailboxes": [{"id":"mailbox-1","address":"alex@example.test","display_name":"Personal"}] }`.
IDs are opaque account identities, not sender addresses. Unknown mailbox scopes
are validation errors. `mailbox_id: null` means global within this profile only.

`GET /rules` → `{ "rules": [Rule] }`, ordered priority descending, then id.

```json
{
  "id": "rule-1", "version": 1, "name": "Invoices to review",
  "enabled": true, "mailbox_id": null, "priority": 100,
  "conditions": [{"field":"subject","operator":"contains","value":"invoice"}],
  "actions": {"classification":"needs_review","archive":false},
  "pack_id": null
}
```

Mutable fields are exactly `name`, `enabled`, `mailbox_id`, `priority`,
`conditions`, `actions`. `name`: 1–100 nonblank characters. `enabled`: boolean.
`priority`: integer −1000…1000. `conditions`: 1–20 AND clauses; field is
`sender`, `subject` or `body`; operator is `contains` or `equals`; value is
1–500 characters. Matching uses Unicode casefold; no executable expressions or
regular expressions. `actions.classification` is `needs_action`, `fyi`, or
`needs_review`; `actions.archive` is boolean, allowed only with `fyi`.
Rules express classification/archive preference, never bypass danger,
unreadable-significance or substance/uncertainty holds. First eligible matching
rule wins; explanation identifies rule and matched conditions. `pack_id` is
server assigned provenance, never client writable. No rule triggers send/delete.

`POST /rules` body is the mutable fields above (all required). Explicit Save is
approval of this rule. Returns 201 `{ "rule": Rule }` with server id/version.

`PUT /rules/{id}` body is all mutable fields plus `version` (the last read
version). Atomic compare-and-swap increments version. Returns 200. No upsert.

`POST /rules/{id}/toggle` body `{ "version": 1, "enabled": false }` uses
identical conflict handling. No implicit overwrite after conflict; reload/review.

`GET /packs` → `{ "packs": [{"id":"starter-action","name":"Direct requests",
"description":"Questions and requests stay visible.","enabled":false,
"rules":[{"name":"...","enabled":true,"mailbox_id":null,"priority":0,
"conditions":[{"field":"body","operator":"contains","value":"please"}],
"actions":{"classification":"needs_action","archive":false}}]}] }`.
Required suggested packs cover direct requests, informational items and review
uncertainty. Nothing is enabled automatically. Pack `enabled` means already
installed, not all member rules are currently switched on.

`POST /packs/{id}/enable` body `{ "mailbox_id": null }` explicitly approves
creating that pack's rules at the requested scope; transactional/idempotent for
the same pack+scope. Repeating does not reset edits/toggles. GET packs may expose
`enabled_scopes: [null, "mailbox-1"]` to describe installed scopes precisely.

## Preview and corrections

`POST /rules/preview` body:

```json
{
  "rule": {"name":"Try invoice","enabled":true,"mailbox_id":null,"priority":100,
    "conditions":[{"field":"subject","operator":"contains","value":"invoice"}],
    "actions":{"classification":"needs_review","archive":false}},
  "sample": {"mailbox_id":"mailbox-1","sender":"billing@example.test",
    "subject":"Your invoice","body":"Please check this invoice."}
}
```

Alternative to `sample`: `reference: "ax1"` fetches relevant transient text for
an authorised existing item. Exactly one of sample/reference is required; sample
body ≤32,000 characters, subject ≤1000, sender ≤320. Unsaved rule is validated
with the same validator as Save. Preview never writes rules/items/provider or
calls a model. Response:
`{ "matched": true, "explanation": "...", "classification":"needs_review",
"archive":false, "holds":[] }`. `holds` contains warnings when archive would
be blocked; returned archive is the safe effective preference. Preview must not
imply a rule alone assesses attachment safety or guarantees future mail action.

`GET /items` → `{ "items": [Item] }` is a compact authorised view for explaining
and correcting outcomes; Desktop may omit this view while native plaintext commands expose it.
`Item` includes `reference`, `mailbox_id`, `sender`, `subject`, `summary`,
`classification`, `reason`, `rule_id` (nullable), `version`, `archived`,
`attachment_status`, `link`; no durable raw body/attachment content.

`POST /items/{reference}/correct` body
`{ "version": 1, "classification":"needs_action", "always":false }`.
One-off correction changes this item and returns
`{ "item": Item, "suggested_rule": MutableRule }` for explicit user review;
it does not silently create a rule. Optional `rule: MutableRule` with
`always:true` is explicit reusable-rule approval, validated/persisted by the
same rule service. `always:true` without an explicit rule is invalid. A rule
editor may present the returned suggestion and save it using POST /rules.
The response also includes `applied_rule: Rule | null`: the actual saved rule
for an explicitly approved reusable correction, otherwise null. This additive
presentation metadata lets every surface acknowledge the persisted outcome;
it grants no new authority and does not replace `always:true` plus a valid rule.

## Extraction boundary (owned by extraction lane)

`extract(data: bytes, filename: str, content_type: str = '', *, scratch_root:
Path | None = None) -> Extraction`, with `status` one of `ok`, `dangerous`,
`unreadable`, `unsupported`, plus `text: str` and `reason: str`. Caller stops
the remaining attachment batch at dangerous, sends an urgent warning, and holds
automatic archive for every unresolved significance state. Temporary extraction
is bounded/cleaned; no durable full body/attachment cache. All test scratch lives
inside repo `.local/` with TMPDIR bound there; no real data or live mutation.

## Running the real service in the isolated UI test host

The implemented Python factory is
`email_steward.api.create_router(service_factory) -> APIRouter`; mount it on a
task-owned FastAPI app at `/api/plugins/email-steward`. The unified native
package exposes `dashboard/plugin_api.py:router`, composed with
`email_steward.runtime.service_from_host`. Do not use that production composition
to access a real profile during this build.

Synthetic integration uses the actual service/store/validator and explicitly
labelled synthetic Gmail/model adapters. Imports and construction:

```python
from email_steward.api import create_router
from email_steward.security import Settings, discord_access
from email_steward.service import Steward
from email_steward.store import Store
from email_steward.synthetic import SyntheticGmail, SyntheticModel

settings = Settings(home=private_synthetic_home, profile="synthetic",
    owner="owner", destination="private", destination_type="dm",
    private_confirmed=True, desktop_subject="desktop:synthetic")
provider = SyntheticGmail()
service = Steward(Store(settings.home / "email-steward"), settings,
    lambda account: provider, SyntheticModel())
# A synthetic trusted SessionSource-like object, used on the server only:
source = type("Source", (), dict(platform="discord", user_id="owner",
    chat_id="private", chat_type="dm", profile="synthetic", is_bot=False))()
service.connect(discord_access(settings, source), "gmail-1",
    "alex@example.test", "Synthetic personal")
app.include_router(create_router(lambda: service),
    prefix="/api/plugins/email-steward")
```

`private_synthetic_home` must be an absolute task-owned private directory under
`.local/`, not a real Hermes home. Only synthetic test-host middleware stamps
`request.state.native_http_principal = {"profile_id": str(settings.home.resolve()),
"subject": "desktop:synthetic", "purpose": "native-http", "scope": "profile",
"capabilities": frozenset({"http:owner"})}`. This test identity never belongs in
client JSON/headers and is not production authentication. See
`tests/test_backend.py::client_for` for the executable test binding. Keep this
host on its own loopback port; no unrelated listeners or shared state changes.

Production configuration lives under `plugins.entries.email-steward.settings`:
`owner`, `destination`, `destination_type`, `private_confirmed`, and explicit
Desktop grant `desktop_subject` OR the three-field tuple
`desktop_session_user`, `desktop_session_provider`, `desktop_session_issuer`
OR `desktop_local_token: true` (off by default; actual host token is revalidated).
Operational settings are `timezone`, `briefs`, `quiet_start`, `quiet_end`,
`quiet_bypass`, `important_contacts`, `poll_seconds`. No UI setting is an
authentication substitute. OAuth account slots are independently declared
host-owned grants `gmail-1` through `gmail-4`; connection verifies Gmail `/profile`
address against the requested receiving account. This build never starts OAuth.

## Repair3 inspection semantics (REST rule schema unchanged)

Reference preview and on-request text use the retained unresolved request. A
pending activity attachment warning contributes a preview hold. Service/chat
inspection can additionally return activity_review: a bounded redacted note with
message_id, received, subject, summary, reason, classification, attachment_status,
holds and optional SDK-reported model_routing. On-request attachment extracts cover
both relevant messages when different, labelled by message ID/subject and bounded
to 20 total; danger stops the entire extraction. The text target remains the request. This adds
no client authority, UI store, new rule field or REST endpoint. Briefs explicitly
label the latest activity and additional review, preserving original action text.
