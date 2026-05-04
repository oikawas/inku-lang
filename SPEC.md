# inku — Drawing Description Language Specification

**Version: v1.39**
**Canonical source:** [SPEC.ja.md](SPEC.ja.md)

This document is the official English specification for public review, contest
submission, and non-Japanese readers.  It is adapted from `SPEC.ja.md`, which is
the canonical source because the author works in Japanese.  When the
specification changes, update `SPEC.ja.md` first, then refresh this English
version.

---

## 1. What inku Is

`inku` is the reference implementation of DDL, the Drawing Description
Language.  DDL is a compact language for writing visual instructions that can be
interpreted by LLMs and rendered as abstract SVG drawings.

inku is not a drawing program in the usual sense.  It treats the written
description as the durable work, and the rendered SVG as one performance of that
work.  The same description may be rendered again later, with controlled
variation, while preserving the underlying score.

The project stands at the intersection of three traditions:

- Sol LeWitt's instruction-based art, where the instruction itself is part of
  the artwork.
- Bonsai, where constraint, scale, and material focus expression rather than
  reducing it.
- Tanka, where a fixed form makes presentation more important than assertion.

The name `inku` comes from the Japanese reading of "ink".  It also points to
the material nature of writing and to the sumi-ink world that informs the visual
palette.

---

## 2. Core Idea

DDL is designed as a language for writing visual tanka.

The author writes a short description.  The system interprets it into a
controlled DDL vocabulary, expands it through deterministic filters, structures
it as JSON, and renders it as SVG.

```text
description -> normalized DDL -> expanded DDL -> JSON Score -> SVG
human          Stage 1          Stage 1.5      Stage 2       Renderer
```

The description remains readable by humans.  The JSON Score remains structured
enough for machines.  The SVG is a performance.

Variation is intentional.  DDL does not attempt to eliminate all model or
renderer variation.  It uses variation as part of the medium, while keeping the
score, schema, and renderer boundaries explicit.

---

## 3. Design Principles

1. Descriptions must remain human-readable.
2. Variation is part of the specification, not a bug.
3. Emotional adjectives are excluded from core vocabulary.
4. Physical, spatial, material, and motion words are preferred.
5. Coordinates are normalized ratios, not fixed pixels.
6. Output is still image SVG; the viewer moves, not the image.
7. The input language is constrained enough to support iteration.
8. Optional concrete worlds belong in plugins, not the core language.

DDL avoids words such as "beautifully" or "powerfully" in the core.  The system
should express such ideas through visible choices: number, placement, material,
line behavior, color, weight, and negative space.

---

## 4. Pipeline

### Stage 1: Interpretation

Stage 1 reads the user's natural-language description and produces normalized
DDL.  Its job is semantic.  It may choose a more visually effective
interpretation when the input is ambiguous, but it should remain within the
core vocabulary and preserve important user intent.

Stage 1 also carries tone, atmosphere, and context into the DDL when possible.
It should not simply extract nouns.  A quiet sentence, a ceremonial sentence,
and a turbulent sentence should lead to different density, focus, motion, and
material choices.

### Stage 1.5: Deterministic Expansion Filter

Stage 1.5 sits between natural interpretation and strict JSON generation.  It
is deterministic and rule-guided.  It expands sparse DDL into richer visual
possibilities by selectively applying:

- mathematical and geometric laws
- spatial paths and non-central focus
- scene-tone palette choices
- music-derived structures such as counterpoint, canon, and harmonic ratios
- painting and material techniques such as perspective, chiaroscuro, drawing,
  pointillism, watercolor, oil-paint layering, patchwork, fresco, and sumi ink
- abstracted natural or material forms using the current primitive vocabulary

The filter must be selective.  It should not pack every technique into every
image.  It chooses a small number of relevant techniques based on the sentence's
context, emotional tone, and implied scale.

### Stage 2: Structuring

Stage 2 converts normalized and expanded DDL into JSON Score.  Its job is
structural, not poetic.  It must preserve DDL elements such as color, material,
movement, arrangement path, rotation, and canvas.  If an element exists in DDL,
Stage 2 should either encode it or fail clearly.

When Stage 2 cannot return usable instructions because of timeout, empty output,
or transient model failure, the server may produce a deterministic fallback
Score.  This fallback is still expected to preserve the DDL's visible essentials:
quantity, placement path, material words, palette tone, and enough shape variety
to remain reviewable.

### Renderer: Performance

The renderer converts JSON Score into SVG.  It owns visual realization:

- coordinate normalization
- material-specific line and contour treatment
- motion and wobble realization
- primitive expansion
- SVG filters and texture effects
- canvas aspect handling

The renderer is allowed to produce controlled variation, but it must preserve
the JSON Score's intent.

SVG export has three profiles:

- `display`: the default server-rendered SVG used for web display, history,
  PNG generation, and artifact rebuilds.
- `editable`: generated on demand from JSON Score and server-owned color catalog
  metadata, with stable ASCII IDs and layer-like groups for Illustrator and
  Affinity editing.
- `compat`: generated on demand from JSON Score and server-owned color catalog
  metadata, avoiding filters and clip paths for broader SVG compatibility.

The DB stores only the `display` SVG in `history.svg`.  Editable and compatible
SVG files are regenerated at download time rather than stored as additional DB
payloads.

---

## 5. Core Vocabulary

The vocabulary dictionary is called Saijiki, following the haiku term for a
seasonal word dictionary.  In inku, Saijiki is consulted rather than kept open
at all times.

Current core categories include:

| English | Japanese | Examples |
| --- | --- | --- |
| shape | かたち | circle, ellipse, triangle, square, line, arc |
| touch / material | てざわり | pen, pencil, rotring, fine brush, thick brush, crayon, chalk, rope |
| line continuity | つらなり | solid, dashed, dotted, dot-dashed |
| motion | うごき | place, align, scatter, fill, tremble, undulate |
| place | ばしょ | top, bottom, edge, corner, near, across |
| angle | かたむき | horizontal, vertical, diagonal, rotated |
| proportion | わりあい | tall, wide, half, quarter, crescent |
| color | いろ | white, black, blue, red, green, gray |

Colors in JSON Score are abstract color names.  Rendering resolves them through
the selected color catalog.  The server is the source of truth for color
catalog definitions and exposes them through `/api/color-catalogs`; clients
select a `catalog_id` rather than owning their own catalog tables.  When user
instructions include color nuance, the system may preserve `color_hint` so
Stage 2 and rendering can resolve the best catalog color without losing intent.
The default catalog is a neutral baseline, not a cultural default.  Additional
catalog ids use material-, light-, and technique-based names to avoid presenting
a country, ethnicity, food, festival, empire, or tourism marker as a complete
palette identity: `ink_season`, `fresco_study`, `open_air_light`,
`ink_porcelain`, `cool_material`, `dye_earth`, `desert_mineral`,
`vivid_material`, `weathered_heritage`, and `sea_stone`.
Catalog `map` values must preserve the meaning of the abstract colors
`white / black / blue / red / green / gray`; stronger identity colors belong in
`palette` rather than replacing structural colors.  The Build 265 review leaves
`open_air_light`, `dye_earth`, and `desert_mineral` as known tuning targets:
their dark backgrounds, high-chroma accents, or paper/sand tones can dominate
quiet prompts, so future tuning should adjust core brightness and saturation
instead of branching into prompt-specific exceptions.
Build 266 lightens those three catalogs' core colors to reduce background and
dark-color dominance.  Catalog `sub` remains the English UI description, while
`sub_ja` carries the Japanese UI description.  Palette color names use `name` as
the English canonical label and may include `name_ja`; the Japanese UI displays
those entries as `English（日本語）`, while the English UI displays `name` only.

Render JSON produced by the server records the concrete render context.  Paint,
compose, and saved artifact JSON include the resolved `stage1_model` /
`stage2_model` that were actually used, plus `render_build_number`,
`render_color_profile`, `render_color_catalog_id`, `render_color_catalog_name`,
`render_color_catalog_sub`, and `render_color_map`, where abstract colors and
`palette:<name>` entries are expanded to the exact `#RRGGBB` codes used for SVG
rendering.  The full catalog `map` / `swatches` / `palette` snapshot is not
duplicated in render JSON because `render_color_map` is the concrete color
record needed for replay and audit.

---

## 6. JSON Score

JSON Score is the machine-readable score produced by Stage 2.  It is not the
final artwork; it is the structure that the renderer performs.

Important score concepts:

- `canvas`: selected canvas aspect identifier, such as `square` or `golden`
- `instructions`: ordered drawing instructions
- primitive fields: line, circle, ellipse, triangle, square, arc, and related data
- `weight`: material / tool quality
- `variation`: visible wobble, blur, tremble, or motion behavior
- `arrangement`: count, distribution, paths, grouping, density, fade, and color cycles
- `rotation`: shape-level or group-level orientation
- `color_hint`: optional hint used when resolving catalog colors

Large repetitions should prefer group behavior over literal overload.  Dense
clusters use `arrangement.density`, `cluster_count`, `fade`, and
`preserve_space` so that negative space remains part of the composition.

Current scene-tone palette behavior uses abstract colors only:

- spring, flowers, buds, and warm light lean toward red / green / white
- water, night, moon, rain, mist, and cold air lean toward blue / white / gray
- forest, leaves, grass, moss, and fragrance lean toward green / white / gray

Nuance that cannot be represented by the six abstract colors is retained in
`color_hint` for catalog-based rendering.

The system treats the DB history record as the source of truth.  SVG, JSON
files, PNG files, and other artifacts are derived outputs.

---

## 7. Canvas Model

Coordinates remain normalized from `0.0` to `1.0`.  Canvas aspect changes do not
change DDL coordinates.

The built-in `canvas-aspect` plugin currently supports:

| Category | ID | Ratio | Purpose |
| --- | --- | --- | --- |
| Basic | `square` | 1:1 | default ordered canvas |
| Standard | `golden` | 1.618:1 | golden-ratio rectangle |
| Modern | `a4` | 1:1.414 | root rectangle / print standard |
| Modern | `b4` | 1:1.414 | root rectangle / print standard |
| Classic JP | `pillar` | 1:5 | Japanese pillar-picture format |
| Ukiyoe | `oban` | 2:3 | ukiyo-e oban proportion |
| Cinema | `wide` | 2.35:1 | cinematic panorama |
| Classic JP | `byobu` | 2.2:1 | Japanese folding screen format based on one half of a six-panel pair |
| Mobile | `vertical` | 9:16 | smartphone vertical format |

The selected aspect is stored per user in plugin storage and passed to
`/api/paint`, `/api/compose`, and history saving.  It is also written into
`Score.canvas`, so history and JSON display show which aspect produced a work.

The renderer uses the selected aspect to determine SVG `width`, `height`, and
`viewBox`.  Circle and arc radii are based on the shorter side to avoid
accidental stretching.

---

## 8. Plugin Model

Plugins separate the core language from optional extensions.  The first
reference plugin is `canvas-aspect`, which uses the canvas-size hook.

Plugin principles:

1. Plugins should not rewrite core vocabulary.
2. Plugins should expose a narrow, explicit option surface.
3. Plugin state is stored per user in DB-backed plugin storage.
4. Plugin code should be isolated from the main UI where possible.
5. Plugin behavior should be documented in [PLUGIN.md](PLUGIN.md).

Plugin implementation is split into system and user directories.  Each plugin
owns its own directory.  The built-in `canvas-aspect` plugin lives under
`server/src/inku_server/plugins/system/canvas_aspect/` on the backend and
`web/src/lib/plugins/system/canvas-aspect/` in the frontend.  User plugin
directories are reserved for future local or third-party plugin loading.

The next likely plugin family is nature primitives or phenomena, such as
leaves, wind, rain, or water.  Such plugins must define whether they extend
Stage 2, JSON Score, renderer behavior, or only a deterministic vocabulary
expansion.

---

## 9. Web Application

The web app is the current reference interface.

Major UI areas:

- App rail: compact navigation, user menu, profile, settings, language and
  theme controls
- Input panel: single drawing, batch drawing, and demo modes
- DDL editor: editable normalized DDL embedded in the single drawing flow, with
  Saijiki word highlighting and an expanded dialog editor
- Canvas panel: SVG display, zoom, pan, output tabs, status bar, export buttons
- History strip: recent works, hover metadata, star markers, pagination
- History manager: larger history view, trash, restore, permanent delete, star filter
- Settings modal: models, color catalogs, DB status, plugin status, export
  templates, users, theme

The status bar displays the current render context:

- Stage 1 model
- Stage 2 model
- color catalog
- canvas aspect
- star state for the current history item
- SVG / PNG export controls

For history display, model, catalog, and canvas values come from the history
item when available.  For active editing, they come from the current selections.

PNG export options are managed as per-user templates in the settings modal's
export tab.  Each template has a name, description, and y-axis height in pixels.
The default templates are `PNG 1024px` and `PNG 2048px`.  The status bar PNG
menu is generated from these templates, and export width is computed from the
current canvas aspect ratio.

---

## 10. Modes

### Single Drawing

The user writes one instruction and runs the full pipeline.  The resulting DDL
can be edited directly.  Replaying from DDL skips Stage 1 and calls Stage 2 /
renderer again.

The normalized DDL appears as an interpretation box under the single drawing
input.  The box supports two editing paths:

- direct inline editing in the highlighted interpretation box
- the `Saijiki` button opens the side drawer for vocabulary reference and word
  insertion at the current caret position
- the `DDL editing` button opens a larger dialog with line numbers, a
  two-column Saijiki vocabulary panel, and a short DDL syntax guide

The same `Draw from DDL` action is also available below the interpretation box
for quick replay without opening the dialog.  The dialog itself does not start
drawing, so drawing actions remain concentrated in the main single-drawing
panel.

If the user edits DDL directly and then presses the normal `draw` button, inku
warns that the DDL edit will be lost.  The choices are `cancel`, `OK`, and
`draw from DDL`.  `OK` reruns Stage 1 from the natural-language prompt, while
`draw from DDL` preserves the edited DDL and runs Stage 2 / rendering only.

DDL replay shows elapsed time, token information, a stop button, and the kiwi
progress mascot.  Stopping replay aborts the active `/api/compose` request.
During single drawing and DDL replay, the single tab shows a running effect and
the batch/demo start actions are suppressed.

During single drawing and DDL replay, the progress bar can show a kiwi mascot.
The kiwi faces left, walks slowly, pecks with a long beak, sniffs, blinks,
occasionally opens its beak during a quick dash, and sometimes curls into a
"kiwi ball".  In the curled state it keeps its head, body, and beak visible,
stays in place for more than six seconds, closes its eye, and gently nods its
head.  The legs are anchored at fixed body positions so the feet move without
the leg roots drifting.

### Batch Drawing

The batch panel accepts multiple instruction lines.  During execution, the
active line is highlighted and the current DDL interpretation is displayed
read-only.  Batch execution keeps failure reports until the next batch run, and
stores batch prompt history per user.

Batch mode can optionally choose a random server color catalog for each render.
The selected catalog is sent as `catalog_id` to `/api/paint`, and history records
store the catalog that was actually used.

The batch mascot is a small crab that walks slowly during progress, moves its
claws, watches the process, and occasionally dives under a water surface while
bubbles rise.

### Demo Drawing

Demo mode repeatedly generates an instruction from a seed phrase, renders it,
waits for the configured interval, and repeats.  Demo settings are stored per
user.  Demo results are not saved by default; the user can explicitly save a
current render to history.

Demo mode can also choose a random server color catalog for each render.  This
option is part of the per-user demo settings.  The status bar reflects the
catalog reported by the render result, not only the current global catalog
selection.

While demo is running, history interaction is restricted where it could confuse
context.

---

## 11. History and Data Integrity

History is stored in the server DB.  The DB record is the source of truth for:

- original input
- normalized DDL
- JSON Score
- SVG rendered by the server
- model metadata
- color catalog
- timing and token metadata
- star state
- trash state

The web UI does not send client-generated SVG back as trusted history content.
`/api/paint` generates and saves server-side history directly.  Compatibility
history endpoints re-render from JSON Score instead of trusting SVG sent by the
client.

For SVG download, the web UI exposes Display, Editable, and Compat variants.
Display downloads the stored SVG.  Editable and Compat call server render
endpoints so past history can benefit from the current export structure without
duplicating SVG blobs in the DB.

The CLI `paint` and `batch` commands also accept
`--svg-profile display|editable|compat` for saved SVG files.

---

## 12. Security and Operations

The web app includes authentication, user roles, sessions, per-user settings,
user profile editing, and user management.  Passwords are stored as salted
PBKDF2-SHA256 hashes.

The app rail user menu opens a profile dialog for the signed-in user.  The
dialog can update the user's email address and password through
`PATCH /api/auth/me/profile`.  Password changes require the current password,
and the endpoint is separate from admin user-management APIs.

Settings visibility is role-aware.  DB settings and user management are visible
only to the `admin` role.  The plugins tab is visible to all signed-in users,
but plugin setting changes and plugin-storage update APIs are restricted to
`admin`.

The DB settings tab also shows the current DB file size when the backend is a
SQLite file database.  Admin users can configure DB replica backups with an
interval in days and a maximum number of automatic generations.  The defaults
are seven days and four generations.  Scheduled backups are created when the
settings status endpoint is loaded after the interval has elapsed.  Manual
backups can be created immediately and are stored separately from the automatic
generation limit.  File-replica backups are reported as unavailable for
non-SQLite DB backends.

Operational details for the author's local server are intentionally not part of
this public specification.  They belong in untracked local documents such as
`AGENTS.md`, `LOCAL_WORK.md`, and `no-git-sync/`.

The application is developed on macOS and verified on the deployment host after
rsync-based sync and service restart.  Git is used for source history, not as a
file exchange mechanism with the local server.

---

## 13. CLI

`inku-cli` is a command-line client for controlling the inku server through the
API.  Its initial purpose is to support automated prompt/image generation,
quality review, and feedback loops for tuning Stage 1, Stage 1.5, Stage 2, and
renderer behavior.

CLI configuration is local and editable.  It stores base URL, provider/model
selection, and timeout values outside the server DB.

`inku-cli batch` can write a benchmark summary JSON file.  When an output
directory is used, the default summary path is `analysis-summary.json` in that
directory.  The summary includes all successful samples and review groupings for
fallback, slow, and normal samples.  Slow samples are diagnostic only; successful
drawings remain part of quality review even when the free inference endpoint was
queued.

Benchmark summaries also include diagnostic traces used for tuning:

- `color_trace`, including requested colors, colors present in the Score,
  missing requested colors, warnings, and negated color markers.
- `negated_color_markers`, so phrases such as "not green" or Japanese
  equivalents such as `緑には寄せず` do not incorrectly count as missing green.
- `score_motif_hint_counts` and `score_motif_hint_lines` for compound motif
  repairs such as `leaf_cluster`, `paper_shard`, `ripple_knot`, and
  `mountain_sign`.
- `math_balance_markers` and `math_balance_marker_lines` for detected
  compositional markers such as radial Fibonacci counts, golden-like centers,
  rule-of-thirds-like centers, and counterweight-like opposite placements.

`inku-cli contact-sheet` builds a PNG contact sheet from a directory of PNG
outputs, making benchmark review less dependent on manual image assembly.

---

## 14. Testing and Evaluation

The project evaluates quality through several layers:

- backend tests for API, DB, schema, composer, interpreter, renderer, and
  deterministic fallback behavior
- frontend Svelte check and production build
- CLI-based benchmark generation
- saved benchmark summaries and contact sheets
- visual review of generated SVG/PNG output
- stress tests using invalid, ambiguous, emotional, conversational, and
  contradictory instructions

Benchmarks focus on:

- whether Stage 1 preserves the whole input context
- whether Stage 1.5 expands without overpacking techniques
- whether Stage 2 preserves all DDL elements in JSON Score
- whether deterministic fallback keeps enough DDL content to be reviewable
- whether the renderer makes DDL features visible
- whether the output has enough negative space, variation, and artistic focus

For NVIDIA free API testing, elapsed time is treated as operational metadata,
not as an artistic quality signal.  Queue delays can indicate service pressure,
but they do not exclude a successful work from aesthetic or structural review.

---

## 15. Current Implementation Status

The reference implementation currently includes:

- FastAPI backend
- SvelteKit frontend
- authenticated users and admin user management
- signed-in user profile editing
- role-aware settings visibility
- DB file size display and SQLite backup settings
- DB-backed history
- star and trash history management
- batch rendering
- demo rendering
- model/provider selection
- color catalog selection
- dark mode
- plugin storage, system/user plugin directories, and `canvas-aspect`
- SVG export and template-based PNG export
- CLI client foundation, benchmark summary output, and contact sheet generation
- CLI history export by render hash for benchmark review contact sheets,
  per-item JSON, and summary JSON
- CLI version/build reporting and server-owned color catalog lookup
- CLI benchmark diagnostics for color delivery, negated colors, motif hint
  arrival, and mathematical balance marker sample lines
- shared kiwi progress mascot for single drawing and DDL replay
- integrated DDL interpretation editor with Saijiki drawer, expanded dialog,
  token/time display, and cancellable `/api/compose` replay
- scene-tone palette strategy, richer fallback Scores, sensory visibility
  safeguards, and broader primitive use within the current schema
- renderer material effects, wobble, rotation, arrangement paths, density/fade,
  and canvas aspect support

History records carry a server-side `render_hash`: a 64-character SHA-256 hex
hash of the rendered content and render metadata.  History APIs also expose a
four-character uppercase short hash for human reference.  The history manager
shows the short hash without changing the thumbnail layout; clicking it copies
the full hash.  The CLI can resolve hash suffixes, reject ambiguous short
matches, and export selected or ranged history items for benchmark review.
The history manager opens at 80% of the current viewport, leaving 10% margins
on each side, and thumbnail cards show the prompt preview above a compact
star/hash/action row.
Prompt previews omit a leading numeric marker such as `#12`, and the compact
thumbnail controls keep visible contrast in both light and dark modes.
History manager pagination tracks overlapping fetches so the loading indicator
is cleared when the final request completes.
Thumbnail pagination measures the actual dialog thumbnail area and dynamically
uses only the number of items that fit without a thumbnail scrollbar.
The thumbnail star action is isolated from card selection, and page sizing uses
measured card height to reduce unused space at the bottom of the dialog.
The thumbnail action row places the star at the lower left, shows hash labels
without `#`, and aligns hash button typography with the delete action.
Starred thumbnails keep an explicit highlighted star state in dark mode.
The thumbnail hover tooltip includes a larger image preview above the metadata.
The history manager header is compressed into two rows: title/view/count/pager
on the first row and selection/filter/search controls on the second row.
When thumbnail page size is recalculated from measured card dimensions, the
current page number is preserved instead of jumping back to the first page.
Per-item delete actions in the history manager use a compact trash icon button
instead of a text label.
The JSON tab, paint responses, history records, and saved artifact JSON include
the resolved `stage1_model` / `stage2_model` used by the server.
Current color management is intentionally limited to sRGB. The JSON tab,
paint/compose responses, history records, and saved artifact JSON include
`render_color_profile: { id: "srgb", name: "sRGB IEC61966-2.1", standard:
"IEC 61966-2-1:1999" }`. Adobe RGB and other wide-gamut profiles remain future
extension candidates and are not implemented in the current renderer.
The JSON tab displays render metadata first, including model, build, color
profile, and color catalog fields, followed by the `score` payload.
When a history item is reopened, the JSON tab displays the saved `stage1_model`
and `stage2_model` from that history record.
The settings dialog includes an admin-only Model Settings tab.  It stores the
default Stage 1 / Stage 2 provider and model plus per-provider base URL and API
key settings in server app settings.  The supported connection targets are
OpenAI API Platform, Claude API, Gemini API, NVIDIA NIM, Ollama's
OpenAI-compatible API, and Intel OVMS's OpenAI-compatible API. Admin users can
add and remove connection services from the model settings tab. Added services
carry a service ID, display name, connection kind (`openai_compatible`,
`anthropic`, or `gemini`), base URL, and optional initial API key. Model lists
are fetched later through each service's model-list fetch action instead of
being typed manually when the service is created.
The service ID is the stable internal key used for DB connection settings,
Stage 1 / Stage 2 provider references, API provider dispatch, and duplicate
protection, so it is not editable after creation. The user-facing service name
can be edited later.
Each service panel can fetch its model list through the server. The server uses
the saved base URL and API key to call the provider-specific models API and
saves the returned model list back into that service definition without sending
raw API keys to the browser. Fetch success or error messages are shown at the
bottom of the published-model picker dialog.
Raw API keys are kept server-side only. The UI uses
`GET /api/settings/models` only to know whether a key is configured. Raw keys
are never returned to the browser; when a key is already configured, the input
shows "keep saved key" and is read-only. Entering a new key for an unset
service changes that service action to save the key. `PUT /api/settings/models`
distinguishes preserving, replacing, and clearing a provider key. LLM calls
resolve provider-prefixed model IDs such as
`openai:...`, `anthropic:...`, `gemini:...`, `nvidia:...`, `ollama:...`, and
`ovms:...`, while keeping compatibility for older NVIDIA slash IDs and local
OVMS model IDs.
LLM server connection settings are global admin-managed settings.  Each user's
Stage 1 / Stage 2 provider and model selection is stored separately in
`user_accounts.model_settings`, saved from the model selection dialog through
`/api/auth/me/settings`, and restored on login.  Admin users can also toggle
which models are visible to users for each provider. Published-model selection
is handled in a separate dialog that also contains model-list fetch, select-all,
and clear-all controls. The main settings tab summarizes only the currently
published models. `GET /api/models` returns only published models for signed-in
users, and the model selection dialog uses that filtered catalog.

Detailed implementation history remains in the canonical Japanese spec.

---

## 16. Licensing

The intended license direction is:

- core DDL specification: permissive license such as CC0 or MIT
- reference implementation: MIT or Apache-2.0
- Saijiki vocabulary data: CC BY or CC BY-SA, if community contribution begins

The language should remain reusable by other implementations while preserving
the reference implementation as one concrete path.

---

## 17. Source of Truth

`SPEC.ja.md` is canonical.  This file is the maintained English public version.

When updating the specification:

1. Update `SPEC.ja.md` first.
2. Refresh this English `SPEC.md` to reflect the same intent.
3. Keep public English wording concise and readable.
4. Do not introduce English-only behavior that is absent from the Japanese
   source.
