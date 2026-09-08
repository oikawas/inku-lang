# inku Vocabulary Plugin Authoring Guide

In inku, a plugin is a data-only vocabulary macro. A visible qualified term
such as `Nature.雨` invokes one versioned `inku.macro-definition.v1` definition,
which expands into ordinary typed core meaning. A plugin is not executable
code, a parser extension, or a renderer hook.

Canvas selection is a host option owned by
`inku.canvas-format-registry.v1`, not a plugin. A Render Engine Pack is a
separate replacement for the drawing core. The normative plugin boundary is
[SPEC §4](SPEC.md#4-plugin-model).

## Definition Format

Declared flat Emits with `movement` set to `line_up`, `scatter`, or `tile` reach the same object-size / placement resolver as ordinary DDL through the verified Stage 1.5 plan API. Omitted Emit count resolves to eight; explicit positive integers through u32::MAX remain exact. Missing required parameters and invalid types never receive that default. Size uses the canvas short edge independently of count, preserving existing normal sizes, size factors, appearance, and angle for seven shapes. Optional `layout_direction` requires an existing `angle` category SemanticRef and expands literals or declared parameter / local references. It is separate from shape `angle` and delivers horizontal, vertical, or physical 45-degree rows only to line_up. Omission and explicit horizontal retain distinct identities; bare diagonal chooses two axes using original meaning, attested optional composition seed, and original occurrence under a dedicated role. Unsupported actions / identities such as rotated and undeclared caller direction stop or omit the original execution unit. Multiple parameters in the same category are not disambiguated by names. Plans also retain tile from physical aspect or a scatter recipe requiring a later performance seed, together with generated owners, bindings, and provenance. They add no undeclared caller overlay or fan-out. Stop / Continue retain field / Emit / invocation omission units. Ready plan does not mean an instance array, Score, or drawing succeeded. The existing field-absent place / count-one Score path remains; the Score entrance cannot silently discard an Emit direction. Unsupported geometry, whole Step10, Step11, and runtime integration remain incomplete.

A definition has exactly these top-level fields:

- `schema`: exactly `inku.macro-definition.v1`
- `namespace` and `heading`: together form the visible
  `Namespace.Heading` name
- `version`: the definition version locked with its canonical digest
- `parameters`: a closed map of typed input schemas
- `components`: definition-local reusable components
- `body`: the bounded, data-only statement list

Parameter schemas are closed to `number`, `integer`, `boolean`, fixed-length
`list`, and `semantic_ref`. Expressions are closed to typed number, integer,
boolean, list, parameter, local, and semantic-reference forms. Unknown fields,
types, expressions, operators, and semantic references are rejected.

Declare sway with, for example, `{"type":"semantic_ref","category":"variation","dimension":"amplitude"}`.
The optional `dimension` is closed to `amplitude`, `frequency`, or `quality`, and is allowed only
for category variation. Omitted / None preserves legacy category-only matching and canonical
bytes / digest; a specified constraint participates in the digest. Parameter names do not imply dimensions.

Flat Emit keys are `fluctuation_amplitude`, `fluctuation_frequency`, and `fluctuation_quality`;
their expression category stays `variation`. The respective IDs are `fine` / `large`,
`slowly` / `quickly`, and `swaying` / `trembling` / `undulating` / `blurring`.
Definition-local `use` shares the classification, and deferred actual values are checked at
execution boundaries. Mapping, missing-slot defaults, and supported shapes follow ordinary DDL in SPEC §13.6.

Three declared parameters require three caller values; supplying only one is a binding error.
Declaring only an amplitude parameter and delivering its Emit field yields Medium frequency
and Perlin quality. All three slots absent means no variation. Invalid values do not become None:
undeclared callers keep invocation diagnostics and malformed Emits keep Emit diagnostics and omission units.
This remains disconnected from runtime / UI / saves and does not ask authors to write internal Variation JSON.

The body may use `emit`, `use`, `group`, `anchor`, `relation`, bounded `repeat`,
typed `transform`, and deterministic bounded `vary`; `components` are local to
the same definition. A definition cannot contain arbitrary code, I/O,
filesystem, network, clock, or environment access, recursion or component
cycles, external macro dependencies, raw SVG or Score data, Renderer
instructions, or plugin-specific parsers, grammars, or renderers.

This small definition reaches the current runtime-disconnected Score lowerer:

```json
{
  "schema": "inku.macro-definition.v1",
  "namespace": "Example",
  "heading": "QuietCircle",
  "version": "1.0.0",
  "parameters": {},
  "components": {},
  "body": [
    {
      "op": "emit",
      "binding": null,
      "fields": {
        "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
        "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
        "place": {"expr": "semantic_ref", "category": "place", "id": "center"},
        "color": {"expr": "semantic_ref", "category": "color", "id": "black"}
      }
    }
  ]
}
```

Each complete flat Emit becomes one ordinary Score instruction. A sequence of
complete Emits keeps its order, including Emits already flattened through
`use`, bounded `repeat`, or `vary`. The current consumer accepts `shape`
(`line`, `circle`, `ellipse`, `cloudform`, `square`, `arc`, or `point`), explicit
`movement:place`, explicit `place` (center, top, bottom, the four edges, or corner), and optional same-category `color`,
`touch`, `continuity`, `surface`, `angle`, `thinness`, and `relative_scale`. Thinness is a closed
core category outside Saijiki: only `thinness:fine` and
`thinness:extra_fine` are accepted, and both use the same lowerer as ordinary DDL.
The other closed core category, `relative_scale`, accepts `slightly_small`, `small`,
`very_small`, `normal`, `slightly_large`, `large`, and `very_large`. It uses ordinary
normal geometry and the existing factor exactly once, keeping explicit normal distinct from omission.
Angle uses the same seeded resolver as ordinary DDL and reaches
`Score.rotation` for every supported shape whose orientation is visible,
including line, arc, and square. Point rejects an explicit angle because its
round mark has no authored orientation.
Existing fill behavior for omitted, `none`,
and `solid` surface remains; the seven positive surface qualities use the same
existing `SurfaceSpec` defaults as ordinary DDL. A Macro does not author a
document Ground. A verified document-owned Ground reaches the same lowerer as a
`CanvasGroundSpec` with the host-resolved aspect. Omitted drawing attributes and
normal count-one geometry use the same defaults as ordinary DDL.

An explicit `connected` or `touching` relation may join only two adjacent bound flat Emits in
the same expansion, with exact center placement on both Emits. It preserves Emit order and generated ownership and uses
the same checked Score performer as ordinary DDL. A missing, nonadjacent, or
omitted `from` omits the complete `to` Emit under OmitAndContinue; it never
retargets to the last surviving Emit. Touching accepts Line / Arc, matches both endpoints,
and shares the ordinary Arc reconstruction. Explicit dimensions, relative scale (including normal), and chord direction remain
fixed; omitted normal may adjust. Macro relations check actual typed Emits without creating
a literal noun condition. Other relation kinds and structural
relation placement remain unsupported by this consumer.

Stop is the default. Under Stop, incomplete Emits, unknown keys, mismatched
value types or categories, unbound caller facts, repeated outer counts, and
expanded `group`, `transform`, `anchor`, or unsupported `relation` nodes stop the entire
Score. Under explicit OmitAndContinue, a supported appearance problem omits
only that field and uses the ordinary default; an invalid flat Emit omits that
Emit; and an unsupported structural node omits its whole subtree without
extracting child Emits. Invalid outer placement, size, count, relation, or other
caller meaning omits the invocation. Unrelated flat siblings retain source and
generated-provenance order. Diagnostics identify source or generated ownership,
spans, invocation, expansion path, generated ordinal, field key, and the actual
omission unit. If no drawing target remains, the result is stopped.

Place literals and explicitly declared `{"type":"semantic_ref","category":"place"}` parameters
use the same regions in SPEC §18. Only center requires an exact generated focus join.
Stage 2 selects a corner from attested meaning, composition seed, and original occurrence; the Renderer
chooses its anchor within that corner. Coordinates never enter source or provenance. Noncenter relations
remain unsupported, and no implicit caller overlay or omitted-place default is added.

Meaning bound through declared parameters is read from the expanded Emit. An
unbound caller appearance field does not fan out or override generated values;
OmitAndContinue drops that caller field and preserves the definition's color,
touch, continuity, or surface. An unused parameter or an unreferenced Emit
binding ID does not fail merely for being unused. The finite consumer recognizes
only an omitted count or an integer count of one; it never treats a
floating-point `1.0` as that integer. The current authoring schema does not
expose `count` as an Emit field, so a Score-ready definition currently omits it
and receives normal count-one.

An angle written on the Macro caller is unbound caller meaning. It does not fan
out to or override angles authored by individual Emits.

Thinness and size bind only parameters explicitly declared with
`{"type":"semantic_ref","category":"thinness"}` or the `relative_scale` category.
For example, `thin normal-sized Draw.Mark` supplies these two finite facts when
`Draw.Mark` declares one parameter for each category. Size uses the existing
modifier-before-head syntax. An Emit reads the named parameter through
`{"expr":"parameter","name":"scale"}` in its `relative_scale` field.
The assignment must be unique and complete. Each core fact retains its original
source owner and has no Saijiki asset metadata; ordinary entity modifiers do not
consume it again. Literal and definition-local component values use the same fields.
Missing or ambiguous binding follows the upstream error policy; undeclared caller
facts retain existing lowering diagnostics. There is no automatic overlay or fan-out,
and a bound parameter alone does not become a continuation predicate.

## Resolution, Expansion, and LLM Boundary

The compiler resolves an explicit qualified invocation against a sidecar lock.
The lock attests the definition name, version, canonical digest, document and
compiler identity, and the source and generated provenance needed to reproduce
the expansion. Expansion binds typed parameters and uses the attested
composition seed plus caller-owned finite bounds. It is effect-free and
deterministic, and its output rejoins ordinary typed lowering.

For a Description request, Stage 1 may receive only a bounded signature,
parameter schema, and short summary. It never receives the definition body or
expanded DDL. Direct DDL with an unknown or ambiguous qualified term fails
explicitly; it does not trigger a hidden LLM fallback.

## Geometry and Count Boundary

Macros emit typed core meaning rather than final geometry. Size has three
distinct authorities: unspecified, explicit qualitative, and explicit numeric
geometry. Explicit normal is not unspecified. Position likewise distinguishes
named center, a qualitative region, and an exact numeric coordinate. On a
non-square canvas, X is a fraction of width and Y of height; isotropic size uses
its allocation or the short side, so circles remain circular and ellipse aspect
is preserved. `(0.0,0.0)` is top-left, `(1.0,1.0)` is bottom-right, and
`(0.5,0.5)` is exact center.

The exact canonical primitive set is `line`, `circle`, `ellipse`, `triangle`,
`square`, `polygon`, `arc`, `point`, and `cloudform`. Line accepts exact
`length`, arc accepts exact `chord` plus `sagitta`, and point reuses exact
`radius` or `diameter`. Geometry is resolved only by the
single `inku-ddl` owner identified as `inku.geometry-resolution-policy.v1`;
plugins cannot add another owner or a tenth primitive. Exact counts remain
lossless symbolic intent until the Step 11 pure ceiling passes before any
O(count) allocation or materialization.

## Current Implementation Status

The shared Rust compiler foundation can parse, validate, identify, lock, bind,
and deterministically expand MacroDefinition v1 values. Its finite flat Emit
subset also reaches an actual Score through the same lowerer used by ordinary
DDL, with shared Stop / OmitAndContinue outcomes and typed omission diagnostics.
The compile-once facade retains the original document, compiler state, lock, and
issues. Explicit Continue can omit typed upstream holes, conflicts, and dependent
units in a sealed execution projection while preserving independent instructions.
Canonical macro output reuses its original seed, semantic ordinal, and generated
provenance without expansion retry. Missing or duplicate execution owners, focus
joins, global budgets, and integrity failures stop both modes. The public Stage 1.5
API remains strict. The Score wire, canonical meaning, seed, focus, geometry policy,
and generated provenance are unchanged. Production runtime integration, UI / API /
persistence selection, an installable package catalog, preview, legacy cutover, and
a general user-package loader are not complete.
This guide therefore does not claim that arbitrary packages can currently be
installed or loaded or that legacy coerce / LLM fallback has been replaced.

`Nature` and `Bamboo` are future or explanatory reference-vocabulary names,
not installed packages or entries in an official registry. The v1.70
hard-coded Nature expansion and legacy `.inku-plugin.md` / `fires_on` fixtures
are not the current authoring format.

The current `plugin_storage["canvas-aspect"]`, `canvas_aspect` request alias,
system/user plugin directories, and plugin status or enable controls are
compatibility surfaces while retirement remains unfinished. They are not an
authoring or loading API for vocabulary macros.

A compatibility importer reports `legacy_plugin_format` and returns a
per-macro `Imported` or `Omitted` outcome. Existing works prefer their stored
Score or expanded artifact. An omitted macro without such an artifact must not
silently render partially, fall back to the old expander forever, or become a
different figure.
