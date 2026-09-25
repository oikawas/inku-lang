# Shared authoring pipeline

This crate owns authoring decisions. Hosts perform the requested provider or
storage effect and return its result; they do not retry, select a fallback,
modify DDL, or reconstruct compiler decisions independently.

The ordinary Server/Web and Android runtimes use this crate through
`inku-pipeline-uniffi`; there is no other runtime path for new works.

## Byte boundary

`inku-pipeline-uniffi` exports `step(snapshot_bytes, input_envelope_bytes)` and
`version_report()`. Both arguments to `step` and its result are owned byte buffers
containing UTF-8 JSON. An empty snapshot starts an execution. Every successful
reply contains the complete next snapshot; the host serializes calls for that
execution and retains that snapshot for its next call.

An input uses the following envelope. `payload` is a `PipelineInput` variant
with its additional integer `version: 1` field.

```json
{
  "protocol": "inku.pipeline",
  "version": "1.0.0",
  "kind": "input",
  "execution_id": "new",
  "message_id": "host-message-id",
  "sequence": "0",
  "payload": {"tag": "cancel", "version": 1}
}
```

The example shows the envelope shape; the first input must be `start`, not
`cancel`. A start supplies variation identity, an authoring nonce, resolved host
options, explicit resource and envelope limits, retry policies, definitions and
their separate localized summaries, and the authoring authority sidecar. It
selects either direct DDL or description input. Later inputs echo the assigned
execution identity and increment the previous sequence exactly once. Seeds,
revisions, and ordinals use canonical unsigned decimal strings.

Successful output has `kind: "output"` and
`payload: {"tag": "step_result", "version": 1, "result": ...}`. The result
contains `snapshot`, ordered output-only `events`, and optional `rendered` data.
Errors have `kind: "error"` and
`payload: {"tag": "error", "version": 1, "code": ...}`; their correlation
fields are null. The host associates them with the synchronous call and retains
its previous snapshot. Unknown protocol versions, tags, semantic fields, stale
results, and malformed exact integers are rejected before state mutation.

The initial configuration declares `envelope_limits`; subsequent calls retain
those values in the snapshot. Hosts must also enforce their transport byte cap
before allocating ABI buffers. Snapshots are trusted host state with consistency
digests, not authenticated bearer tokens for an untrusted client.

## Effects and commit authority

The five effect tags are `select_description_catalog`, `generate_sketch`,
`generate_normalized_ddl`, `commit_visible_normalized_ddl`, and
`complete_visible_ddl_holes`. `generate_sketch` runs only when the start or a
regeneration asks for a sketch; its failure continues Stage 1 with the
description alone. Each result echoes action ID, attempt, and request
digest. Retries preserve the logical action ID and increase its attempt; a new
action receives a new identity. Corrective Stage 1 normalization is a new action
because compiler feedback changes its payload and request digest. The host
enforces the supplied delay and timeout and reports elapsed time including its
provider attempt, but not a delay already accounted for by the core.

| Result | Core decision |
| --- | --- |
| Temporary transport, timeout, rate limit, or response schema failure | Retry within the explicit attempt and total-time budget |
| Compiler rejection of an uncommitted core-generated Stage 1 candidate | Request complete DDL again from the same Stage 1 with the original description, rejected DDL, and bounded reason/span diagnostics with corresponding exact source excerpts, using a new logical action within the same Stage 1 `max_attempts` and `total_timeout_ms` budget |
| Provider rejection or any other semantic validation failure | No retry |
| Catalog selection exhausted or rejected | Resolve `default`, record `auto_fallback_default`, then construct Stage 1 |
| Stage 1 exhausted or rejected | Fail without a new semantic artifact |
| Hole completion exhausted or rejected | Keep committed DDL and require user editing |
| Host commit failure | Fail and retain the last acknowledged document and authority |
| Cancellation | Invalidate the outstanding action; later results are stale |

The corrective Stage 1 path uses the same model and response schema and returns
a complete replacement DDL. The rejected candidate is not committed as the
visible document or as a work; it remains only in request context retained for
durable execution replay. This path does not apply to direct or already accepted
author DDL, or to Macro expansion budget or integrity failures after the source
already has canonical pre-expansion meaning. Provider-reported generic semantic
failure and hole-patch validation are also terminal. The host does not repair DDL
or decide to retry, and the correction does not relax the compiler, reduce counts,
patch Score, or delegate hidden meaning changes to a later LLM.

`commit_visible_normalized_ddl` carries the exact visible document, its digest,
and an authority proposal with an expected revision. The host makes these bytes
visible and durably commits the document and authority in one compare-and-set
transaction. It acknowledges the document digest, new revision, and authority
digest only after success. The core then reparses the acknowledged document and
compiles its Score. It never releases a new Score before that acknowledgment.
Host adapters must make commit effects idempotent by action identity so that a
lost acknowledgment can be recovered without a second revision mutation.

The first committed user DDL change locks description authority monotonically
within that variation. Undoing the text does not unlock it. Origin remains a
separate immutable sidecar field. `legacy_unknown` requires a compatibility
decision; neither origin nor authority is inferred from old text. Starting from
a description after a lock requires a new variation owned by the host.

## Known-hole completion and rendering

Description generation must finish as visible DDL without deferred holes.
After a visible commit is acknowledged, an `IncompleteKnownHole` parse starts
a bounded completion request automatically, without a separate user operation.
No hole means no Stage 2 LLM call; unknowns, conflicts, and integrity failures
are not sent for completion. `complete_holes` remains an optional retry command.
The request carries compiler-reported source ranges and locks. The provider
returns a constrained source patch, never a Score. A valid proposal
emits its visible base and candidate, then waits for `approve_patch`. Approval
revalidates the base revision and patch before requesting the same atomic
commit. Declining the proposal leaves committed DDL unchanged. Declines and
exhausted failures do not automatically repeat the request on that revision.
A newly committed source is parsed again; an approved subset patch may leave
other known holes that enter the same bounded completion path.

Stage 1 receives bounded macro signatures, parameter schemas, and localized
summaries. It receives no definition bodies or expanded DDL. The typed prompt
edition preserves the distinct meanings of fill, scatter, tile, and background.
The model returns a closed-typed work plan; the core prints it as visible DDL,
and only that DDL reaches the compiler.

`render` is an explicit input after a committed compilation has a Score. Its
strict options carry exact seeds and resolved rendering values. The adapter
checks compiler options, canvas registry and geometry, catalog, palette, Score
digest, and resource authority before calling the existing renderer. Resource
and relation recovery remains the compiler/renderer's existing local recovery.
The pipeline does not invent shipping values for new resource dimensions.

`replay::replay` applies a recorded typed input/result sequence through the same
state machine. Events are observations and cannot drive transitions. A transcript
that includes `render` invokes the renderer and requires a permitted rendering
environment; pure authoring replay does not generate images.
