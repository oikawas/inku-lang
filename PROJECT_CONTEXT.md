# inku Project Context

**Target version: v2.9.25 / Build 822**

This is the starting point for developers and AI agents.
It avoids reloading the full specification for every task.
`SPEC.ja.md` remains the canonical design source; when this summary conflicts with it, follow the
Japanese specification.

## What to Read First

For ordinary work, read only what the task requires:

1.
If a local `AGENTS.md` exists, read it for development, verification, deployment, and security
rules.
2.
Read this file for the purpose, architecture, and current contracts.
3.
Inspect `git status --short --branch` and recent history.
4.
Read only the relevant sections of `SPEC.ja.md` or its public English adaptation, `SPEC.md`, plus
the implementation files being changed.
5.
Search `CHANGELOG.md` or the more detailed `CHANGELOG.ja.md` only when historical context matters.

A full specification read is appropriate for first-time onboarding, design-philosophy changes,
broad cross-cutting work, or a specification consistency audit.

## Purpose

`inku` is the reference implementation of DDL, the Drawing Description Language.
DDL is conceived as a language for writing visual tanka rather than as a conventional drawing
command language.

- The description is the durable work; an SVG is one performance.
- Authors write physical material, placement, motion, and observable relations rather than emotional judgments.
- Brevity and constraint reduce assertion and foreground presentation.
- The default path is reproducible.
Variation belongs to renderer performance and explicit user operations.

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

- DDL text may be written in the author's language.
JSON Score keys remain English.
- Keep Stage 1 interpretation separate from Stage 2 structuring.
- Stage 1.5 must not overwrite interpreted intent or accumulate fixed finished-work recipes.
- Coerce should shrink over time.
It must not inject a house style; invalid optional data should prefer drop-only handling.
- The same Score and seed reproduce the same work.
Do not add implicit time seeds or automatic variation counters.
- Keep `dh1` description identity, `rh3` work-edition identity (legacy `rh2` values are retained), history IDs, and lineage node IDs distinct.
- Lineage records explicit derivation operations only.
Never infer parentage from similarity, time, or matching hashes.
- Metrics, similarity, and vision reviews are diagnostic mirrors, not generation gates or automatic best-branch selectors.
- Plugins are validated declarative documents, expanded to core DDL immediately after Stage 1.
Stage 1.5, coerce, Score, replay, and rh2 do not depend on plugin content.
- The saijiki table (`server/src/inku_server/saijiki.py`, v1.92) is the source of truth for vocabulary.
The Stage 1 prompt vocabulary block, plugin closure markers, relation phrases, web Saijiki display,
and reference §1 are derived from it; vocabulary changes go through the table and its golden tests.
- Japanese and English behavior must stay aligned.
Do not introduce English-only requirements.
- **The engine does not go backwards** (SPEC "Design Principles", principle 9).
Past drawing engines are not kept in the system and no mechanism selects a version.
Replay always runs on the latest engine, and reproducing an edition as it was is **guaranteed by
returning the saved SVG**.
As in printmaking, the carving advances and the prints remain, but the block cannot be restored —
**which is why the reference corpus, a proof print, is pulled while a version is still current.**

## Current Product State

**This section describes only what exists now, in the present tense.**
The chronological record of what each version did lives in `CHANGELOG.ja.md` / `CHANGELOG.md`; this
document does not copy it.
To learn why something took its current shape, search the changelog by term, version, or Build number.

### Versions

| Subject | Value | Source of truth |
|---|---|---|
| Application | the "Target version" line at the top of this file | **the two files `web/APP_VERSION` and `web/BUILD_NUMBER`**. The UI, `/api/info` `version`, and the CLI all read them (the value is not copied here) |
| Render Engine | 20 | `server/src/inku_server/render_engines/default.py` |
| DDL | `ddl_version` 3 / `ddl_engine_version` 4 | `server/src/inku_server/layer_versions.py` |
| Android | `2.1.4-android.2` | `android/VERSION` (a namespace separate from web and server) |
| Python package | 2.7.2 | `server/pyproject.toml` (moves only on a product release) |

### Vocabulary

The Literals in `server/src/inku_server/schema.py` are canonical; the saijiki table (`saijiki.py`)
holds the mapping to Japanese terms.

- 8 primitives — `line` / `circle` / `ellipse` / `triangle` / `square` / `polygon` / `arc` / `cloudform`
- 4 line styles — `solid` / `dashed` / `dotted` / `dash_dot`
- 11 tools — `silverpoint` / `pencil` / `pen` / `rotring` / `crayon` / `chalk` / `brush_thin` / `brush_thick` / `burin` / `drypoint` / `computer`
- 2 thinness values — `fine` / `extra_fine` (an axis independent of the tool)
- 9 colors — `white` / `black` / `blue` / `red` / `green` / `gray` / `yellow` / `orange` / `purple`
- 9 surface textures, 5 surface directions, 6 ground materials

The saijiki table is a single source: the Stage 1 prompt vocabulary block, plugin closure markers,
relation phrases, the web Saijiki display, and reference §1 are all derived from it.
Vocabulary changes go through the table and its golden tests.

### Pipeline layers

- **Stage 1 (interpretation)** — detects the language of the instruction and produces normalized DDL.
The prompt is assembled from the saijiki table and holds no fixed vocabulary string of its own.
- **Plugin expansion** — writes a validated `.inku-plugin.md` down into core DDL deterministically,
immediately after Stage 1.
Only a `fires_on` term that is namespace-qualified or named as an explicit subject fires; it never
widens to metaphor or unknown subjects.
- **Stage 1.5** — deterministic expansion and relation assignment.
It carries variation (three strengths) and a tenkei level (`none` / `sparse` / `auto`), both stored
per work.
- **Stage 2** — Score construction as JSON.
The fill rate of an optional field **depends on its declaration order** in the tool schema; fields
declared last are filled more often.
- **coerce** — split into `normalize` and `compose`.
Invalid values prefer drop-only handling, and no house style is injected.
- **Render Engine 20** — the SVG performance.
It carries closed-shape outlines and fills, arcs, the material layer, ground resistance, and master
grid quantization of coordinates.

A RAW trace exists for observation (`include_trace` on `/api/paint` and `/api/compose`, default
false).
It returns each layer's intermediate product in one response without changing the Score, branching,
or call counts, and without persisting anything.

### web (SvelteKit 2 / Svelte 5)

An authenticated single-page application with description, work, batch, demo, and lineage tabs.

- Description entry and reproducible refinement (touch, placement, reading), plus AI autonomous
refinement and variation
- 13 color catalogs (`color_catalogs.py`; every catalog carries all 9 colors), canvas ratios, tenkei
level, and display mode
- Per-user history, stars, comments, trash, search, lineage groups, and explicit lineage nodes and edges
- Model, language, and drawing-element comparison; generation-info, prompt, and JSON inspectors; the
colophon
- SVG, PNG, and animation export
- A Japanese and English UI.
`web/src/lib/i18n/GLOSSARY.md` is canonical for English terminology and `npm run lint:i18n` enforces it.

UI dimensions come from the `:root` tokens in `+page.svelte` (`--btn-sm-*`) and colors from
`--action-*` and `--accent*`; literal px values and literal colors are treated as regressions.

### server (FastAPI)

- The 80 endpoints live in the ten files under `server/src/inku_server/api_core/routers/` (`auth`,
`feedback`, `history`, `lineage`, `me`, `plugins`, `public`, `render`, `settings`, `users`).
Shared definitions live in `api_core/{state,models,deps,common,rendering}.py`.
- `api.py` holds only the `app` assembly, `_lifespan`, middleware, startup calls, and `include_router`
lines.
**Dependencies run one way — `api.py` → routers → shared** — and no router imports `api.py`.
- Authorization is enforced both by per-route guards and by router-level default dependencies.
Every endpoint except the six on the public allowlist sits behind a guard.
- The LLM layer reaches both Anthropic and OpenAI-compatible local or cloud backends, and the product
can be started without a single API key.
Model reference resolution follows three rules — explicit qualification, sole ownership, then the
stage default — and never guesses.

### cli

`inku-cli` uses only the public HTTP API.
It carries drawing, history, plugin, reference-dump, administrative, and benchmark commands, and does
not import server internals.

### android

A separate implementation in Kotlin, Jetpack Compose, and Room that runs the whole pipeline on the
device.
`android/ANDROID_SPEC.ja.md` is canonical for its detail.
**It follows server as the source of truth and server design is never bent to match Android.**
It can lag at any time, so an Android version number must not be read as the server version.

### Verification surfaces

- **`server/tests`** — pytest, including route-authorization coverage (walking the live `app.routes`),
API-surface identity (compared against `tests/data/api-surface-baseline.json`), and route-body
location (counting `route.endpoint.__module__`).
- **Frozen reference corpora** — proof prints per version under `server/reference/`.
`render-engine-20` (525 cases) and `ddl-engine-4` (33 cases) are current, and CI enforces
byte-identical regeneration.
- **`cli/tests`** — pytest.
- **`npm run check`**, **`lint:i18n`**, **`lint:models`**, **`lint:recommendations`** — web types,
terminology, and model resolution.
- **`scripts/check_docs.py`** — internal references in public documents.

The **deterministic layers** are `coerce/`, `ddl_expander.py`, `renderer.py`, `stroke_engine.py`,
`schema.py`, `saijiki.py`, and `language_support/{ja,en}.py`.
Touching any of them requires running the frozen-corpus comparison.

**CI runs only the frozen-corpus regeneration.**
Neither pytest, ruff, nor `npm run check` runs in CI, so **a regression the corpora do not observe is
not stopped by anything automatic.**

### On open issues

**Unresolved issues and undecided questions are not recorded here.**
Anything written here freezes at the moment it is written, so a stale claim survives its own fix.
A separate developer-facing register holds them, with state.

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
- For Web behavior or UI changes, increment `web/BUILD_NUMBER`.
When the application generation changes, also update the Web `APP_VERSION`.
- **Do not stack per-version paragraphs in "Current Product State".**
The changelog holds what each version did, so this document keeps present-tense statements and
rewrites the parts that changed.
Appending a paragraph at every release turns this file into a second changelog and it stops working
as an entry point.
- **Do not record unresolved issues or undecided questions here.**
A statement here freezes when written, so it survives its own fix.
Track issues where they can carry state.
