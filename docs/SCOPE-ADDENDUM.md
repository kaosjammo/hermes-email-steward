# Controller source correction and R03 clarification, 05/11/2026

This is a sourced correction to the generated specification, recorded during
accepted repair cycle 1 (consumed 1 of 5, remaining 4). It does not erase the
original requirements, frozen commits, independent findings or receipts.

The controller recovered the primary consolidated approved brief in session
`20261105_164203_4eae4239`, anchored DB message **406273**, followed by Q31A and
Mike's final approval in Discord **1567789836864200745**. Its exact model wording:

> Use rules first, then the user’s configured Hermes model. No mandatory additional AI service.

The generated R03/prompt incorrectly strengthened that into an absolute
pre-transmission/no-host-fallback requirement. The controller explicitly owns
that specification error; the stronger wording was not Mike's instruction.
The original text remains in REQUIREMENTS.md with this clarification linked.

The approved implementation uses the supported configured-model API. Hermes
owns its existing routing and may try user-configured model/provider fallbacks.
The plugin does not select another service, change global routing, request
provider/model/profile override grants, monkeypatch the host or extend core.
Explicit current user/task restrictions on models/providers remain binding.

Independent A-006 observations are valid: the real old public PluginContext /
PluginLlm / auxiliary client can attempt a configured fallback after failure,
including a same-model alternate endpoint whose default public result lacks a
complete fallback marker. Primary failure with no configured fallback fails
safely. At this pin the supported public call has no per-call no-fallback flag.
The sealed addendum and raw probes remain read-only under
`.local/reviews/initial-a/model-fallback/`.

A-006 is accepted as an **Important accuracy/consent defect**, rather than an
authorisation to implement unsupported strict routing. The prior disclosure
and failure message falsely promised no substitution/attempt. Before model
content can flow again, the owner must accept **model-routing-v2**, which
discloses host-managed fallbacks and incomplete endpoint/attempt visibility.
Old **model-content-v1** approval is not sufficient
for a new model call; revoked/missing consent also causes zero model calls.
Rules and bounded local extractive brief content remain model-free.

The adapter consumes only public result `provider`, `model` and `audit.task`,
and labels them **SDK-reported metadata**. Durable reasons/inspection include
that bounded information and explicitly say fallback status and physical
endpoint/attempt history are unavailable. No inference that the reported
provider/model proves a unique endpoint or no fallback is permitted. Public
task slots require registration and can be separately operator-routed; this
plugin retains the default main-model path rather than introducing another
route or claiming task metadata supplies a complete attempt audit.

Failure leaves processing pending and reports that host-managed fallback may
already have been attempted. Post-response metadata is not pre-transmission
prevention. Strict host routing can be an optional future host capability; it
is neither implemented nor a new blocker imposed on this build.

The six original Important findings and Minor sdist omission remain unchanged;
ES-B-001 duplicates A-002. A-006 is separately tracked within this same cycle.
Fresh independent exact-successor closing reviews must judge this clarified
primary contract and the preserved observations. Live model quality and all
previously unrun provider/native/full-host gates remain UNRUN.
