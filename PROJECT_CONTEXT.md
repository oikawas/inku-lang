# inku Project Context

**Target version: v2.13.47 / Build 975**

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
  -> Stage 0.5: sketch from life (optional; rewrites the description as prose naming things)
  -> Stage 1: interpretation
  -> normalized DDL (which may contain namespaced plugin words)
  -> declarative plugin expansion: deterministic writing-down to core DDL
  -> Stage 1.5: deterministic expansion and relation assignment
  -> Stage 2: JSON Score
  -> coerce / validation: boundary handling with a drop-only preference
  -> Render Engine: SVG performance
  -> history and work lineage
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
- A redraw runs under the limits the work was drawn under.
Today's settings are used only for a work whose row recorded no limits, and the answer says which of the two drew it.
A request may lower a limit but never raise one.
The ceiling belongs to the administrator, not to the caller placing the order.
- A raised ceiling reaches the page.
No place keeps a shipping number written into it, and the bands and the cap on cluster count are held as ratios of the setting.
A ceiling that does not reach the page is a second ceiling the administrator cannot see.
- The number on a ceiling says what it weighs.
What is counted is marks; what reaches a reader is a file.
The conversion comes from the per-mark cost the server measured, with no copy of it kept in the browser.
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
| Render Engine | 41 | `core/crates/inku-render/src/lib.rs` |
| DDL | `ddl_version` 3 / `ddl_engine_version` 20 | `server/src/inku_server/layer_versions.py` |
| Android | `2.1.4-android.63` | `android/VERSION` (a namespace separate from web and server) |
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
The saijiki holds ten categories, and `おもて` / surfaces (eleven words) says how the inside of a
closed shape is (ddl-engine 15) — the counterpart to continuity, which says how a line is, with
state nouns rather than actions. A surface attached to an instruction that encloses nothing is moved
by coerce to the closed shape before it, and dropped where there is none. **The two words 粒 (grain)
and にじみ (bleed) are the exception and stay on the line or arc they landed on** (ddl-engine 20):
they say how the mark runs rather than how an inside is, which is what a line has instead of an
inside.

### Pipeline layers

- **Stage 0.5 (sketch from life)** — an optional layer that rewrites the description as plain prose
naming things. Its granularity is chosen per draw from two values, `fine` (many short sentences,
the default) and `coarse` (fewer, longer ones).
**The prose stands in for the description at three consumers**
(Stage 1, the plugin expansion's firing decision, and Stage 1.5).
**Stage 2 and coerce read the DDL alone.** The plugin's seed -- what decides how many -- is the description.
The description itself is kept for saving and display, and when the layer fails it goes to Stage 1 unchanged.
**What the layer did is recorded on the work** (`sketch_state`, one of `fine`, `coarse`, `fallback`,
`off`, `not_applicable`). **A run that fell over, a run the author switched off, and a route that
never calls the layer are recorded separately.** `NULL` means only one thing: the work was drawn
before the column existed.
**A run where interpretation or composition fell back is recorded the same way** (`interpret_fallback`
and `compose_fallback`). **The composition field holds three states**: a reason, `"none"` (it did not
fall back), and no record at all.
**Refining from a marked work as the lineage parent asks once before it runs.**
- **Stage 1 (interpretation)** — detects the language of the instruction and produces normalized DDL.
The prompt is assembled from the saijiki table and holds no fixed vocabulary string of its own.
- **Plugin expansion** — writes a validated `.inku-plugin.md` down into core DDL deterministically,
immediately after Stage 1.
Only a `fires_on` term that is namespace-qualified or named as an explicit subject fires; it never
widens to metaphor or unknown subjects.
**What a plugin hands over is one unit, and a count stated in the phrase naming it says how many of
those units to place** (what one unit becomes is settled by the plugin document's declaration and the
seed; the body does not reach inside it). The count is read by `counts.py`, shared with coerce.
**When the stated number times one unit exceeds a budget, the single unit stands and the decline is
recorded rather than trimmed to fit.**
- **Stage 1.5** — deterministic expansion and relation assignment.
It carries variation (three strengths), stored per work. **One axis moves — the focus — and this
layer adds no sentence the description did not ask for.**
- **Stage 2** — Score construction as JSON.
The fill rate of an optional field **depends on its declaration order** in the tool schema; fields
declared last are filled more often.
**It is told which paper it composes for** (v2.13.14). What it may fit to the paper is size and
placement, never the number of marks. **What it declares stays in `Score.canvas` and may disagree
with the aspect actually performed on.**
- **coerce** — split into `normalize` and `compose`.
Invalid values prefer drop-only handling, and no house style is injected.
**The words this layer judges a description with are declared in one place**, `COERCE_MARKERS` in
`language_support/{ja,en}.py` (72 systems, 693 distinct words).
**No matching literal is written into a branch of `coerce/`** — the one exception is a string this
layer wrote itself and a later branch reads back (a `note`). Tests hold both halves.
**When the description names exactly one abstract color, the color cycle folds to that one color**
(background clauses do not count, and a polychrome phrase or a cycle without the named color is left
alone).
**An even split is a distribution the description never stated, so it is taken back rather than delivered.**
**A count stated in plain words reaches the group its clause describes, but only when
exactly one group answers to that clause** (an ambiguous pairing is left alone). It is a branch of its
own, separate from the "only" path and carrying its own note wording, so attribution stays countable.
**The band it covers comes from the limits threshold** — it reaches the counts the configuration calls
literal (up to 239 by default) and leaves everything at or above the threshold to representation.
**The boundary is not given a second name.**
**When the forced count would exceed the per-instruction or whole-work budget, it is not forced rather
than trimmed** — a trimmed count is neither the number stated nor the represented one.
- **Render Engine 41** — the SVG performance, owned by the shared Rust core and called through one thin Python adapter.
**A sheet called by name changes how the brush runs**: each of the seven grounds carries its own
absorbency and tooth, and those values reach the stroke synthesizer, so the same description leaves
a different mark on washi than on canvas. `面: 粒` and `面: にじみ` on a line or an arc are read as
that one instruction working the sheet harder (capped at 3.0x), rather than as a surface that landed
on a shape with no inside.
A surface texture (hatch, crosshatch) has each row clipped at its ends to the outline, so it stays
inside the shape that carries it. The clipping happens in the coordinates before anything is drawn,
so a profile that uses no filters keeps the same shape, and the angle, spacing, and density gradient
are exactly what they were before the clipping.
A wash lays each sweep as wide as the pitch or wider, so no paper is left between two sweeps: it
reads as a field rather than as stripes. Each sweep is correspondingly lighter, and the ink a reader
sees is the composite of the overlapping layers.
The ground is one of seven supports you can name (paper, washi, ink-wash ground, charcoal ground, canvas, drawing paper, mezzotint), tiled as a `<pattern>`.
**No filter is used at all, so all three profiles emit exactly the same ground.**
A mark's extents become pixels through the canvas's short edge, so the same description draws the same shape on any aspect (placement still scales with width and height).
The layer that arranges marks follows the same rule: a `radial` ring's radius, an `at.region`'s extent, a cluster's band, and the cross-axis spread of a `path` all become pixels through the short edge.
A region's centre and a cluster's centre stay proportional, so "upper right" is the upper right of any canvas.
How much of the paper a group uses along its own line (`margin` and `span`) is not a shape and is untouched.
It carries closed-shape outlines and fills, arcs, the material layer, ground resistance, and master
grid quantization of coordinates.
Each member of a group holds a size (±35%) and a turn (±27°) of its own.
The wander's amplitude is a multiple of **that tool's stroke width** (0.35 / 0.6 / 2.0) rather than of
the figure's size, the tool's tone takes its offset from the **performed ink** rather than the intended
geometry, and the fray comes from a contact field standing for the paper's tooth rather than a dash table.
**The lengths that contact reads sit on the same six-decimal grid the SVG writes, so the same Score
counts the same number of teeth whatever machine draws it.**
**A fill sits on an underlay that holds the field as a real element, and what sits on top splits at
coverage 0.2 into scan lines and rubbings.**

A RAW trace exists for observation (`include_trace` on `/api/paint` and `/api/compose`, default
false).
It returns each layer's intermediate product in one response without changing the Score, branching,
or call counts, and without persisting anything.

### web (SvelteKit 2 / Svelte 5)

An authenticated single-page application with description, work, batch, demo, and lineage tabs.
**The screen is drawn by the browser** (`export const ssr = false` in `+layout.ts`).
**Until it is built, the curtain in `app.html` is what shows** — the ground colour and the word
`inku`, painted from inline CSS alone, so it waits on no external resource. **It is dismissed by one
CSS rule as well: `app.html` holds no `<script>`.**
Per-feature settings hold reactive state directly at module level in `.svelte.ts`, so drawing on the
server could mix one person's state across requests. The boundary is stated as a setting.
**On a server started with `INKU_SINGLE_USER`, one person is settled on and signed in automatically,
so the sign-in screen never appears and the sign-out control is hidden** (the multi-user machinery stays
in place).

- Description entry and reproducible refinement (touch, placement, reading), plus AI autonomous
refinement and variation. A leading number and a bracketed comment stay in the stored work, reach
no layer of the drawing, and are greyed in the editors
- 13 color catalogs (`color_catalogs.py`; every catalog carries all 9 colors) plus "from the
description", canvas ratios, and display mode. The catalog selection is stored per
user on the server
- **The canonical colors for redrawing a stored work are the `render_color_map` the work recorded.**
When a request names a work (`work_id`), the server draws from that row and never reads today's
definition of the catalog. **A renamed catalog and a retired one both draw**, and an older work with
no record falls back to the current definition. The catalog name is shown under its current name,
with a note when it is retired or when the work holds no record of its colors
- Per-user history, stars, revision marks, share marks, comments, trash, search, lineage groups, and
explicit lineage nodes and edges.
The three marks are independent: filtering on them together shows only the works that carry them all.
A listing shows **images baked from the stored SVGs**, kept in a derived `thumbs.db` beside the
canonical database. Baking happens after saving and never runs the engine, so the picture stays
the one the work was drawn with; works not baked yet are drawn from their SVG.
How many run at once is entered by an administrator, since the machine is not asked for its core
count -- in a container the host's is the wrong answer.
The rasterizing runs in child processes -- the rasterizer holds the GIL, so threads would sit
on one core -- while the writing stays in the parent, and one work that cannot be baked does
not stop the rest.
**When the bake is small, the texture of marks drawn in a row with one tool is folded into a
single run before rasterizing.**
That cuts how many times the filter is applied and raises the area it covers, so **it only pays
while the width is small.**
The door that rasterizes reads the width and decides; it is not a flag the callers pass, because
a flag any caller could forget is one some caller would.
**The stored SVG is never folded** -- the fold happens only at bake time, so neither the identity
of the picture nor the engine version moves
- Per-work sharing.
A recipient and a permission (`read` or `write`) are chosen one work at a time, and a shared work
carries a mark in the list.
Recipients can be picked by name among the members of your own organisation group; the full roster
stays closed.
A lineage may cross owners, so a node you cannot read appears as a card with its content withheld,
and deleted is told apart from private in words
- A share mark aimed at a group. The work itself says "this group may read me".
**It is visible only when the read bit (`for_share`) and the destination (`share_group_id`) are both
there**: the bit alone is a permission with no destination, the destination alone is one nobody
opened.
Raising the bit without naming a group fills in the owner's own organisation group, and only an
administrator may name another.
Dropping it leaves the destination, so raising it again returns to the same recipients.
**What widens is reading only; writing does not move**
- Model, language, and drawing-element comparison; generation-info, prompt, and JSON inspectors; the
colophon
- SVG, PNG, and animation export, plus a shareable one-sheet card (drawing, headnote, seed, and seal
composed into one image, in a square and a portrait layout; the server bakes it with a bundled font,
so the same characters appear on any machine).
One code path drops every file, and it can write to a folder the user picked (browsers with the File
System Access API; the rest fall back to the browser default)
- A Japanese and English UI.
**English terminology is canonical in two places**: `docs/i18n/glossary.md` holds the term-by-term correspondence (gathered on 2026-08-17 from the web table and two local notes), and `web/src/lib/i18n/GLOSSARY.md` holds the style rules, the forbidden and restricted words, and the pairing with the machine checks. **`npm run lint:i18n` enforces them over the web display strings, and `server/scripts/check_docs.py` enforces them over the English public documents**.

UI dimensions come from the `:root` tokens in `+page.svelte` (`--btn-sm-*`) and colors from
`--action-*` and `--accent*`; literal px values and literal colors are treated as regressions.
**The base, hover, disabled, and `ghost-active` rules of the shared button class (`ghost-btn`) live as
one global rule each in `+page.svelte`.** Under Svelte's scoping, writing the class name does not reach
a rule that lives elsewhere, so **restating the base inside a component is duplication, not sharing.**

A feature's settings stay inside `web/src/lib/features/<name>/`.
Storing them in localStorage, persisting them on the server and putting them on the render request
are collected by **three registries that name no feature at all**
(`persisted-settings.ts`, `user-settings.ts`, `render-payload.ts`),
so adding one setting moves no line of `+page.svelte`.

### server (FastAPI)

- The 96 endpoints live in the ten files under `server/src/inku_server/api_core/routers/` (`auth`,
`feedback`, `history`, `lineage`, `me`, `plugins`, `public`, `render`, `settings`, `users`).
The count is owned by `EXPECTED_ROUTE_COUNT` in `server/tests/test_route_authorization.py`.
Shared definitions live in `api_core/{state,models,deps,common,rendering}.py`.
- `api.py` holds only the `app` assembly, `_lifespan`, middleware, startup calls, and `include_router`
lines.
**Dependencies run one way — `api.py` → routers → shared** — and no router imports `api.py`.
- Authorization is enforced by router-level default dependencies.
Every endpoint except the three on the public allowlist (`/health`, `/api/info`, `/api/auth/login`)
sits behind a guard. **Every entry on that list has to give a reason that was measured** (narrowed
from six in v2.13.26; ledger I-086).
**A per-route `Depends` remains in only two cases: when the body uses the `actor` value, and when the
route imposes a stronger guard than the router default (the seven admin-only routes in `plugins`).**
**Restating the router's own guard as a parameter is a second enforcement point, not defence in depth.**
What a guard asks is membership in a permission group (`admins`, `leaders`, `users`), and one member
may hold several. The test lives in a single predicate; the `role` column that remains on the user row
is a mirror derived from those memberships and is read by no decision. Memberships are assigned through
the existing user APIs. The organisation group is a separate thing, one per member, independent of permission.
- **What a member may do** (the permission group) and **what a member may see** (the visibility scope)
are separate axes, and both run through a single predicate.
The default scope gives `admins` everything, `leaders` their own organisation and `users` their own
works, and a per-work ACL and the group-aimed flag the work carries itself add to it.
**The paths written in raw SQL run through the same predicate** — when full-text search is left out,
it shows up not as "too much is visible" but as "it goes missing when you search".
- The LLM layer reaches both Anthropic and OpenAI-compatible local or cloud backends, and the product
can be started without a single API key.
Model reference resolution follows three rules — explicit qualification, sole ownership, then the
stage default — and never guesses.

### cli

`inku-cli` uses only the public HTTP API.
It carries drawing, history, plugin, reference-dump, administrative, and benchmark commands, and does
not import server internals.
**Feature tests run through this CLI.**
When a flag does not exist yet, it is implemented in the CLI first and tested there.
**An unnamed key is not an error — it is filled with a default — so request fields are counted per
sender** (`server/tests/test_cli_sender_census.py`).
**The path that counts raster measurements counts the image it was handed, at the width it was
handed.** The width is decided by the burning step, not the counting step, so that path declares no
width or scale flag.

### android

A separate implementation in Kotlin, Jetpack Compose, and Room that runs the whole pipeline on the
device.
`android/ANDROID_SPEC.ja.md` is canonical for its detail.
**It follows server as the source of truth and server design is never bent to match Android.**
It can lag at any time, so an Android version number must not be read as the server version.
Its interface is bilingual and the language is chosen in the settings screen (default `ja`).
A Kotlin language pack holds the wording; `server/scripts/gen_saijiki_kt.py` generates the saijiki
vocabulary.
Android currently declares render engine `35` and DDL engine `20`. The server declares render
engine `40` and DDL engine `20`, so the deterministic DDL repairs are current while the drawing
layer is five versions behind.

### Verification surfaces

- **`server/tests`** — pytest, including route-authorization coverage (walking the live routes
through `fastapi.routing.iter_route_contexts`; **reading `app.routes` directly yields nothing from
fastapi 0.141 onward**), API-surface identity (compared against
`tests/data/api-surface-baseline.json`), and route-body location (counting
`route.endpoint.__module__`).
- **Frozen reference corpora** — proof prints per version under `server/reference/`.
`render-engine-41` (610 cases) and `ddl-engine-20` (49 cases) are current, and CI enforces
byte-identical regeneration.
- **The Android reference corpus** — `android/app/src/test/resources/server_reference/` is filed the
same way. The port reads the directory for the version it declares, so **raising the server engine
adds a directory rather than reddening the port**. Older versions cannot be rebaked, so each one is
held by its own `manifest.json` of names and digests.
- **`cli/tests`** — pytest.
- **`npm run check`**, **`lint:i18n`**, **`lint:models`**, **`lint:recommendations`** — web types,
terminology, and model resolution.
- **`npm run test:unit`** — unit tests over web's pure functions (Node's `node:test`; no new
dependency).
- **`scripts/check_docs.py`** — internal references in public documents, the heading shape of each Japanese/English pair, and the **forbidden words on the English side** (the four words of `GLOSSARY.md` §5-1; a backticked span is an identifier and is skipped).

The **deterministic layers** are `coerce/`, `ddl_expander.py`, `core/crates/inku-render/`, the native
request boundary, `render_engines/default/`, `renderer.py`, `schema.py`, `saijiki.py`, and
`language_support/{ja,en}.py`. An output-affecting change requires the frozen-corpus comparison;
a host-only change proven not to alter the native request or output uses proportionate direct checks.
Within rendering, the Rust core owns planning, geometry, marks, surfaces, layers, SVG emission,
deterministic seed derivation, and performance metadata. Python owns only the registry, thin adapter,
SVG-only compatibility facade, and fresh host entropy.

**CI runs two workflows.**
`reference-corpus` re-bakes the frozen corpora and requires byte-identical output; `checks` runs
**server (ruff and pytest), cli (ruff and pytest), web (`npm run check`, `test:unit`, `lint:i18n`),
and the published documents (`check_docs.py`).**

**⚠ Some surfaces are still outside it.**
**(1) paths that need a key** — the thirty tests that call NVIDIA NIM skip without one;
**(2) local-only material** — nine tests that use `cli/bench/leaf`, and one that wants `cairosvg`;
**(3) two comparisons against bytes baked on darwin** — the Android reference fixtures and the
platform-stability pair test, **which read the Linux bake as a defect and are deselected there**;
**(4) the Android JVM tests**, for which `checks.yml` simply has no job — its four are `server`,
`cli`, `web` and `docs` (**⚠ corrected 2026-08-16: the previous reason, "there is no gradle
wrapper", was false** — `android/gradlew` and `android/gradle/wrapper/` are tracked. Android is not
entirely absent from CI either: `reference-corpus.yml` carries an `android-design-preview` job);
**(5) the operational scripts under `no-git-sync/`**, which git does not track.
**The population is not the same as a full local run.**

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

- Update `SPEC.ja.md` first for a specification change, then carry **the same content, section for section**, into `SPEC.md`. Neither language may hold a section the other lacks (the author's ruling of 2026-08-02; **Japanese remains canonical**). `server/scripts/check_docs.py` is the only gate on this and must be run before merging. The same gate also reads the forbidden words on the English side (a backticked identifier is not checked).
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
