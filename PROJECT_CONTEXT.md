# inku Project Context

**Target version: v1.96.0 / Build 606**

This is the starting point for developers and AI agents. It avoids reloading the full specification for every task. `SPEC.ja.md` remains the canonical design source; when this summary conflicts with it, follow the Japanese specification.

## What to Read First

For ordinary work, read only what the task requires:

1. If a local `AGENTS.md` exists, read it for development, verification, deployment, and security rules.
2. Read this file for the purpose, architecture, and current contracts.
3. Inspect `git status --short --branch` and recent history.
4. Read only the relevant sections of `SPEC.ja.md` or its public English adaptation, `SPEC.md`, plus the implementation files being changed.
5. Search `CHANGELOG.md` or the more detailed `CHANGELOG.ja.md` only when historical context matters.

A full specification read is appropriate for first-time onboarding, design-philosophy changes, broad cross-cutting work, or a specification consistency audit.

## Purpose

`inku` is the reference implementation of DDL, the Drawing Description Language. DDL is conceived as a language for writing visual tanka rather than as a conventional drawing command language.

- The description is the durable work; an SVG is one performance.
- Authors write physical material, placement, motion, and observable relations rather than emotional judgments.
- Brevity and constraint reduce assertion and foreground presentation.
- The default path is reproducible. Variation belongs to renderer performance and explicit user operations.

## Current Architecture

```text
instruction
  -> Stage 1: interpretation
  -> normalized DDL (which may contain namespaced plugin words)
  -> declarative plugin expansion: deterministic writing-down to core DDL
  -> Stage 1.5: deterministic expansion and relation assignment
  -> Stage 2: JSON Score
  -> coerce / validation: boundary handling with a drop-only preference
  -> Render Engine: SVG performance
  -> history and artwork lineage
```

- `server/`: FastAPI backend for APIs, authentication, DB access, interpretation, composition, coercion, rendering, and lineage.
- `web/`: SvelteKit 2 / Svelte 5 frontend.
- `cli/`: `inku-cli`, which operates only through the public HTTP API.
- `android/`: separate Kotlin / Jetpack Compose implementation; `android/ANDROID_SPEC.ja.md` is its detailed canonical specification.
- `SPEC.ja.md`: canonical Japanese design and behavior specification.
- `SPEC.md`: maintained public English adaptation.
- `CHANGELOG.ja.md` / `CHANGELOG.md`: chronological design and implementation history.

## Contracts That Must Remain Intact

- DDL text may be written in the author's language. JSON Score keys remain English.
- Keep Stage 1 interpretation separate from Stage 2 structuring.
- Stage 1.5 must not overwrite interpreted intent or accumulate fixed finished-work recipes.
- Coerce should shrink over time. It must not inject a house style; invalid optional data should prefer drop-only handling.
- The same Score and seed reproduce the same work. Do not add implicit time seeds or automatic variation counters.
- Keep `dh1` description identity, `rh2` work-edition identity, history IDs, and lineage node IDs distinct.
- Lineage records explicit derivation operations only. Never infer parentage from similarity, time, or matching hashes.
- Metrics, similarity, and vision reviews are diagnostic mirrors, not generation gates or automatic best-branch selectors.
- Plugins are validated declarative documents, expanded to core DDL immediately after Stage 1. Stage 1.5, coerce, Score, replay, and rh2 do not depend on plugin content.
- The saijiki table (`server/src/inku_server/saijiki.py`, v1.92) is the source of truth for vocabulary. The Stage 1 prompt vocabulary block, plugin closure markers, relation phrases, web Saijiki display, and reference §1 are derived from it; vocabulary changes go through the table and its golden tests.
- Japanese and English behavior must stay aligned. Do not introduce English-only requirements.

## Current Product State

As of v1.89, the authenticated web application includes:

- automatic Japanese/English instruction detection and per-stage model/language comparison;
- color catalogs, canvas aspects, and reproducible touch/layout/reading refinement;
- user-scoped history, stars, comments, trash, search, and lineage grouping;
- explicit lineage nodes and edges, including intermediate works hidden from regular history;
- autonomous AI refinement, drawing-element/model/language comparison, lineage Okugaki, and generation/prompt/JSON inspection;
- a public-API CLI with administration and benchmark support;
- a `default` Render Engine behind an internal boundary for future Engine Packs.

In v1.90.0, Build 586 formalized `touching`, Build 587 unified relation geometry in transform-composed canvas coordinates, and Build 588 removed duplicate touching assignment. Build 589 adds validated `.inku-plugin.md` documents and a deterministic expansion layer immediately after Stage 1. Explicit qualified terms and `fires_on` nouns that are stated subjects may fire; metaphors and unknown objects may not. Validation rejects recursion, expansion beyond 48 instructions, fixed-coordinate repetition, external references, and namespace collisions. Provenance is ordinary history metadata, while Score, canonical artwork data, rh2, and replay remain independent of plugin documents. Build 590 adds a general boundary preventing Stage 1.5 from appending auxiliary shapes and Score from retaining instructions beyond the explicit numeric-region count after structural expansion. The boundary caps instruction count, while arrangement-driven visible multiplicity remains model-dependent between Mistral and Qwen. Build 591 extends the declarative plugin format to v2, accepting `member` composites, `note:` comment lines, a `bottom band` and a computed diagonal band, load-time rejection of unknown region keys (removing the silent fallback), English repetition units with unit-preserving singulars, `anchor ... at N to M spots` nested repetition, and longest-match `fires_on` resolution at a position. Score, coerce, and rh2 are unchanged, and Nature.leaves v0.3.0 passes `plugin validate`.

v1.92.0 (Build 592) restructures the Saijiki. A single table (`saijiki.py`) now derives the Stage 1 prompt vocabulary block, the plugin closure markers, the relation phrases, reference §1, and the web Saijiki display (`GET /api/saijiki` plus a snapshot-seeded synchronous store). Pre-restructuring prompts are frozen as golden fixtures so any assembly drift beyond the approved pruning fails tests. The words 描く (draw) and 髪 / hair were pruned from the vocabulary by the author's decision (the Score `Weight` enum keeps `hair` for replay compatibility), 彫る (carve) was removed from the web display, and the static Nature entries are frozen until their declarative migration.

v1.93 (Build 593) adds the RAW trace option. `include_trace` (default false) on `/api/paint` and `/api/compose` returns each layer's intermediate output in a single response; it is observation-only, changes no Score/render/branch/count, and is never persisted (the entry point for the intent-audit harness). A bench-dedicated container environment (api 8101 / web 5174, dedicated volume, version-frozen images) now runs alongside the bare-metal deployment on the development server; operational details live in the local `AGENTS.md`.

v1.94.0 (Build 594–599) is web-UI-only cleanup that touches neither the drawing machinery nor the server. A read-only "current selection" (model, color catalog, canvas; interpretation/rendering labels when the stages differ; full model names) moved into the input tab below the instruction and buttons. The canvas status bar drops the model/catalog/canvas display in favor of a render-hash button (last four digits) that copies the full hash on click. The left panel (input, batch, demo) is collapsible to the left, and the canvas artwork supports mouse-wheel zoom. Vision models are organized by purpose: the model chosen in AI autonomous refinement persists as `vision_model` and the okugaki model as `okugaki_model`, and the Vision tab is dropped from the model dialog opened from the input tab (vision is used only for readings and refinement observation, never for generation). Bottom history thumbnails show the Stage 1 short name with a Stage 1 / Stage 2 full-name tooltip, the state badge is removed (kept in the tooltip), and English labels use "Gen." Button styling and placement were aligned (new-root matches the "new" button, the hash button matches the other status-bar buttons, the Latest button moved left, the input tab is model-then-catalog order), and the refinement/okugaki model-picker tooltip is `position: fixed` to avoid scroll-container clipping. "Move to trash" was removed from the lineage artwork card menu (the header bulk-trash stays).

Build 600 fixes an instruction carrying both a region (`at`) and a relation losing its relation silently during region placement, so touching resolution was never reached. Region placement now runs first and relation resolution follows; plugin-member double arcs (leaf forms) perform as designed as endpoint-pinned opposing minor arcs (intent-audit finding F-1). Relations unresolvable only at performance time drop with a recorded warning per §14.4. The rh2 contract and Score schema are unchanged.

v1.95 (Builds 601–604) is a second web-UI phase; server, Score, and rh2 are unchanged. Comparison dialogs became single-view, the standalone refine tab was removed, the instruction tab was restructured (read-only normalized DDL, a shared DDL editor dialog, DDL-origin works identified by `display_label='DDL'` with instruction-based actions hidden), the Drawing tab became Artwork with a generation badge, and autonomous-refinement UX was polished. Build 600 also added deterministic transcription of expansion-layer pair members into Score instructions (style-sentence consumption, merging past coerce) plus the inspection-only `carriage_warnings` mirror, making vocabulary carriage model-independent so model choice purely widens expression.

v1.96 (Builds 605–606) introduced the user-selectable scenery level `tenkei` (none / sparse / auto, default auto), mapped deterministically onto all three layers (Stage 1 norm sections plus a pure-invocation bypass, Stage 1.5 pool reduction, a coerce insertion budget) with no post-hoc thinning governor and no effect on rh2. It also restored the §4.6 Stage 1.5 addition guard that Build 600 pair transcription had bypassed, implemented the user plugin management API (content read, create, overwrite, delete, enable/disable persisted in `.plugin-state.json`) with its settings UI, and attached `lineage_generation` to lineage responses. UI phase 3 replaced the mascot with the inku cube, unified the abortable generation-status element across dialogs, redesigned language comparison as direct Stage 1 × Stage 2 combinations, and single-sourced model metadata.

## Where to Look for a Change

| Change area | Primary references |
|---|---|
| Language philosophy, vocabulary, variation, relations | `SPEC.ja.md` §§1–14 or the corresponding `SPEC.md` sections |
| Web UI, refinement, comparison | `SPEC.ja.md` §§7–8 and `web/src/` |
| Score, interpretation, composition, rendering | `SPEC.ja.md` §§5 and 12–14; `server/src/inku_server/` |
| History, lineage, Okugaki | refinement accounting and Okugaki sections; related API and DB code |
| Operations and verification | local `AGENTS.md`, `compose.yaml`, and component READMEs |
| Historical rationale | search `CHANGELOG.ja.md` or `CHANGELOG.md` by term, version, or Build number |

## Documentation Update Rules

- Update `SPEC.ja.md` first for a specification change, then adapt the same intent into `SPEC.md`.
- When current architecture or a major contract changes, update both project-context files.
- Update `CHANGELOG.ja.md` first for release/Build history, then reflect publicly relevant content in `CHANGELOG.md`.
- Keep current contracts in the specification and chronological implementation detail in the changelog.
- For Web behavior or UI changes, increment `web/BUILD_NUMBER`. When the application generation changes, also update the Web `APP_VERSION`.
