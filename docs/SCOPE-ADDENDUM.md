# Model routing and consent boundary

Email Steward runs rules first, then optionally uses the user's configured Hermes model. It does not require a separate AI service.

## Host-owned routing

The implementation uses the supported configured-model API. Hermes owns routing and may try user-configured model/provider fallbacks. The plugin does not select another service, change global routing, request provider/model/profile override grants, monkeypatch the host or extend core. Explicit current operator/task restrictions on models and providers remain binding.

The tested public PluginContext/PluginLlm path can attempt a configured fallback after a primary failure, including an alternate endpoint whose public result does not expose a complete fallback marker. Primary failure without a configured fallback fails safely. The tested public call has no per-call no-fallback flag. This is not a guarantee that email content reached only one endpoint.

## Renewed consent

Before email content can be sent for model judgement, the owner must accept **model-routing-v2**. That disclosure covers host-managed fallbacks and incomplete endpoint/attempt visibility. Old **model-content-v1** approval is insufficient for a new model call. Missing or revoked consent causes zero new plugin model calls. Rules and bounded local extractive summaries remain model-free.

## Audit limits

The adapter consumes public result `provider`, `model` and `audit.task` fields and labels them **SDK-reported metadata**. Durable reasons and inspection show that bounded information while stating that fallback status and physical endpoint/attempt history are unavailable. Reported provider/model values do not prove a unique endpoint or absence of fallback.

Public task slots require registration and may be separately operator-routed. This plugin retains the default main-model path rather than inventing another route or claiming that task metadata supplies a complete attempt audit.

Failure leaves processing pending and warns that host-managed fallback may already have been attempted. Post-response metadata is not pre-transmission prevention. A strict host routing control is not implemented here. Live model quality, physical routing and provider/native/full-host acceptance remain unverified.

Internal approval/conversation identifiers and private review locations are intentionally not part of this public technical contract. An earlier public source commit contained planning provenance; this document corrects the current source without claiming that public Git history has been purged.
