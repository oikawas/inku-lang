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

The body may use `emit`, `use`, `group`, `anchor`, `relation`, bounded `repeat`,
typed `transform`, and deterministic bounded `vary`; `components` are local to
the same definition. A definition cannot contain arbitrary code, I/O,
filesystem, network, clock, or environment access, recursion or component
cycles, external macro dependencies, raw SVG or Score data, Renderer
instructions, or plugin-specific parsers, grammars, or renderers.

This is the smallest accepted definition:

```json
{
  "schema": "inku.macro-definition.v1",
  "namespace": "Example",
  "heading": "QuietMark",
  "version": "1.0.0",
  "parameters": {},
  "components": {},
  "body": []
}
```

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
`square`, `polygon`, `arc`, and `cloudform`. Geometry is resolved only by the
single `inku-ddl` owner identified as `inku.geometry-resolution-policy.v1`;
plugins cannot add another owner or a ninth primitive. Exact counts remain
lossless symbolic intent until the Step 11 pure ceiling passes before any
O(count) allocation or materialization.

## Current Implementation Status

The shared Rust compiler foundation can parse, validate, identify, lock, bind,
and deterministically expand MacroDefinition v1 values. Production runtime
integration, an installable package catalog, preview, legacy cutover, and a
general user-package loader are not complete. This guide therefore does not
claim that arbitrary packages can currently be installed or loaded.

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
