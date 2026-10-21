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

The eight effect tags are `select_description_catalog`, `generate_sketch`,
`generate_normalized_ddl`, `read_composition`, `choose_laws`, `choose_colors`,
`commit_visible_normalized_ddl`, and `complete_visible_ddl_holes`.
`generate_sketch` runs only when the start or a
regeneration asks for a sketch; its failure continues Stage 1 with the
description alone. `read_composition` runs only when the configuration's
`composition` sets `read`: it asks how the settled Stage 1 plan is composed, and
the core places the layers whose place the description does not state on ranges
of the thirds grid before the commit. With `read` false the default reading
places them without a request; without `composition` Stage 1 is committed as it
printed it. `choose_laws` runs only when the configuration has `laws` and the plan
was composed: a reader chooses laws of placement, size, arrangement and hand and
the cards (C1 to C6: sparse and dense, patterns, polyrhythm, motif and variation,
jo-ha-kyu, shin-gyo-so) for the composed layers, and the core applies them to the
composed document's Score and prints the layers they change in numbers (a numeric
point, the ends of a row or a line, a numeric range, a numeric size, a numeric
angle) before the commit; a moved line is printed by its ends, cut where the
canvas cuts it, a grid as a numeric range the core tiles, a layer a progression or
beat groups open as one sentence per mark, a layer a card rebuilds as one
sentence per instruction, and a pair whose marks turn as its two marks. An
arranged layer's marks are fitted to their spacing, but a layer that would shrink
below the floor keeps its size. The printed document is compiled as the run
compiles it before it is committed. An answer the core refuses is asked again
with that answer and the reason as a new action within the same budget, also
when a mark it places at a numeric point does not lie wholly on the canvas;
from the third request on, the request also lists the reasons the answers
before it were refused with. A layer a refused answer named with the
description's words as one whose count the description writes keeps that count
in the answers after it. An arc's sagitta is printed at most half its
printed chord. `choose_colors`
runs only when the configuration has `colors`, once the laws stage ends for a
composed plan (also when the laws fell back or the run has none): a reader
chooses color laws among the eighteen (B11, B13, B14, B16 to B20, C7 to C9, D1
to D7) for the work, their number not fixed, shown its layers as the core estimates them drawn
(each layer's drawn contrast and chroma and the colors it would not be seen in,
from the renderer's editable SVG) and its paints' places on Itten's wheel. The
core keeps the colors the description states, plugged-in layers and the
ground, recolors a layer the laws stage colored (aerial perspective, a pattern)
only in colors that keep its law, checks the laws of lightness by the drawn
lightness and D2 once every law is applied, fades only a layer of three marks
or more, refuses an answer that changes nothing, and where a law leaves the
colors to the tool takes the combination that recolors the main layer, then the
most harmonious one. It prints the layers the colors change (a color, colors in turn
or shifting, a fade, a handling, a numeric size, a kasane's lower colors before
the layer) and compiles the printed document as the run compiles it before it
is committed; the record of the laws follows the sentences printed again. A run
that applies its laws keeps their basis in its snapshot (`laws_basis`: the
composed document, the digest of the committed document, the answer), which a
host saves with the work. The start `saved_laws` runs the laws stage from a
saved work (the AI refinement's laws move): `laws_entry` reads the composed
document the work keeps, or the DDL of a work without laws, back as the plan it
was printed from, the run checks that the plan compiles to the same Score, asks
for the laws with the refinement's direction (laws left out, the cards, the
author's sentence), keeps the work's own lines where the laws changed nothing,
and commits as a DDL edit; it stops with a reason rather than commit its base.
Each result echoes action ID, attempt, and request
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
| Composition reading exhausted or rejected | Place the layers from the default reading and commit; a plan that cannot be composed is committed as Stage 1 printed it |
| Laws answer refused by the core's rules | Request the laws again with the original message, the refused answer as written (not one too long to read) and the reason, and from the third request on the reasons the answers before it were refused with, using a new logical action within the same laws `max_attempts` and `total_timeout_ms` budget |
| Laws answer whose printed mark at a numeric point leaves the canvas | Request the laws again with the reason that names the layer and its laws, within the same budget |
| Laws exhausted, or a laws document that compiles to no Score or to more diagnostics or omissions than the composed document | Commit the composed document as the composition printed it (`laws_fallback`) |
| The laws stage from a saved work cannot start, is exhausted, or prints a document that fails its check | Fail with the reason (`laws_basis_stale`, `laws_without_basis`, `not_faithful`, `no_law`, `laws_refused`, `laws_compile`, `laws_unavailable` and the others of SPEC §12.6.4); never commit the base unchanged |
| Colors answer refused by the core's rules (its schema, a law it cannot take, a color not seen when drawn) | Request the colors again with the original message and the reason, using a new logical action within the same colors `max_attempts` and `total_timeout_ms` budget |
| Colors exhausted, no law the work can take as the main one, or a colors document that does not compile to the colors chosen or compiles to more diagnostics or omissions than the document the laws left | Commit the document the laws left (`colors_fallback`) |
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
The model returns a closed-typed underdrawing; the core prints it as visible DDL,
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
