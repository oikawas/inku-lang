# inku — Drawing Description Language Specification

**Version: v1.52**
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

The UI display language and the instruction language are separate concerns.
Users may run the Japanese UI while writing English instructions, or use the
English UI while writing Japanese instructions.  API requests use
`instruction_lang` (`auto`, `ja`, or `en`) for interpretation and `ui_lang` for
display context.  When `instruction_lang` is `auto`, the server lightly detects
Japanese or English from the input text and passes the resolved language to
Stage 1, Stage 1.5, Stage 2, and demo-instruction generation.  Render metadata
records `instruction_lang_requested`, `instruction_lang_resolved`, and
`ui_lang` for audit and replay context.  These language metadata fields are not
part of the current canonical `render_hash` payload, so existing history hashes
and benchmark references remain stable.

Instruction-language implementation is organized through an internal
Instruction Language Registry.  Each registered language owns its language code,
Stage 1 prompt, Stage 2 prompt, Stage 1.5 expander/filter entry point, and
the language-specific marker set used by the Score coerce layer.
Japanese and English are registered by binding the existing prompts and
expanders without changing their text or behavior, while their coerce marker
sets live in separate language files.  The coerce algorithms remain common
because they operate on language-independent JSON Score structure; language
differences belong in the marker sets that map words such as motion,
visual-event, hard-edge, or dark-field cues to those shared repair policies.  A
third-party language such as Spanish should be added first as a new registry
entry with prompts, expander behavior, and coerce markers, keeping JSON Score
schema, renderer behavior, and color catalogs separate unless the new language
demonstrably needs a core extension.

Builds 403-427 extend the English instruction path beyond structural routing.
Japanese and English now live in separate language files for Stage 1 prompts,
Stage 1.5 expansion/filter behavior, Stage 2 prompts, and coerce marker sets.
They still share the same JSON Score schema, renderer, color catalogs, and
repair algorithms.  Language-specific behavior is therefore kept at the prompt,
expander, marker, and repair-input boundary.

The English path is tuned to preserve English-specific phrasing instead of
performing word-by-word translation.  Temporal and relational phrases such as
`before`, `after`, `again and again`, `as if`, and `at once`, along with
composition cues such as `diagonal`, `same beat`, `shifted`, reflection, fog,
road, sound, flock, and transparent-event language, are treated as cues for
abstract visual parameters and focal events.

Build 427 was checked with 30 Japanese/English equivalent prompt pairs rendered
with the same square canvas and default color catalog, without saving benchmark
history.  Expert review found the English path close to Japanese quality:
English tended to score slightly higher on color resonance, while Japanese
remained slightly stronger on constraint adherence and visual-event presence.
The remaining English risk is becoming too orderly and letting the event moment
sink into background structure.  The remaining Japanese risk is compressing
quiet poetic scenes into marks that are too small to carry a visible event.
Future tuning should strengthen focal-event size, contrast, and neighboring
reactions without increasing overall density.

---

## 3. Design Principles

1. Descriptions must remain human-readable.
2. Variation is part of the specification, not a bug. It exists at two scales: micro variation in line wobble, blur, grain, and texture; and macro variation in composition and placement resolved by the renderer.
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
image.  It now favors composition-family selection and relation attachment over
fixed finished recipes.  The maintained composition families include diagonal
bands, vertical rhythm, horizontal strata, radial or concentric structures,
one-sided focus, central stillness, retreat to the edge, and dispersal.  Focus
points are represented as regions, not hard-coded coordinates.  Techniques such
as counterpoint, pointillist backgrounds, perspective lines, and canon-like
repetition should primarily become relations on existing instructions; separate
fixed auxiliary layers are used only when relation encoding cannot carry the
intent.

### Stage 2: Structuring

Stage 2 converts normalized and expanded DDL into JSON Score.  Its job is
structural, not poetic.  It must preserve DDL elements such as color, material,
movement, arrangement path, rotation, and canvas.  If an element exists in DDL,
Stage 2 should either encode it or fail clearly.

Adjectives, motion words, and texture words modify the primitive that the DDL
already names.  Stage 2 must not add unrequested support lines, support shapes,
or differently colored instructions merely because the DDL says "trembling",
"swaying", "blurring", "thick", "thin", or a similar modifier.  The server also
applies a narrow deterministic contract guard for single-primitive DDL with
motion or texture modifiers: it keeps only instructions matching the requested
primitive and explicit color, drops unrequested auxiliary marks, and applies
the missing motion as variation on the requested primitive when possible.  The
guard is intentionally not applied to multi-motif DDL.

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
the JSON Score's intent.  Renderer performance has two scales: micro variation
(line wobble, blur, grain, material texture) and macro variation (seeded
resolution of regions and relations).  Each render may carry a `render_seed`;
providing the same seed makes replay reproducible while leaving the canonical
Score stable.

inku exposes this as the first half of two-step regeneration: **another
performance** rerenders the same JSON Score with a new explicit performance
seed. It does not call an LLM and does not change the interpretation or Score.

Human, face, animal, and group motifs are not drawn as literal objects.  Stage 2
and the coercion layer convert them into `Score.presence`: presence kind,
intensity, center of gravity, symmetry, gaze pressure, group behavior, and
contour density.  The renderer realizes presence as faint arcs, edge-biased
focus, asymmetric spacing, and contour-density pressure.  It avoids fixed
silhouettes such as stick figures, head/body pairs, wing/tail marks, or rings
of identical ellipses.

The primitive vocabulary includes `polygon` for polygonal language.  Individual
pentagon or hexagon primitives are not added; polygonal intent is represented
with `polygon` and `sides=5-8`.  Motion energy is handled by trajectory,
rotation, diagonal placement, wave paths, and asymmetry rather than simply
increasing count or density.

The score coercion layer also contains rendering-core quality repairs used by
the current default engine.  These repairs are deliberately generic rather than
prompt-specific, and must not become a visible system fingerprint.  Quiet, mist, memory, shadow, and neon-blur contexts apply
density and negative-space governors so vertical lines, particles, large filled
shapes, or background surfaces do not overwhelm the work.  Motion words that
arrive without an effective trajectory can receive a small directional motion
floor, and requested colors that appear only in a color cycle may be promoted to
a primary stroke so the color intent remains visible.  Visual events are
distributed across available vocabulary: when a scene lacks angular anchors,
the repair may add a small `polygon`; when repeated lines dominate, it shapes
the existing line group with syncopated spacing, preserved negative space,
directional fading, and slight endpoint gaps instead of increasing density.

Repair parts such as focal reactions, angular pulses, vanishing traces, and
rhythm offsets are measured by marker phrase in CLI analysis. Their firing rate
is monitored, but no new governor or floor may force them into every sample.
When such a part is necessary, fixed coordinates and fixed shape parameters are
resolved from the event anchor and input hash so repeated works do not reveal a
constant inserted component. Focal adjacent reactions are limited to isolated
visual events where omitting the reaction would weaken the subject.

The rendering core is exposed internally through a RenderEngine contract.  A
render engine receives JSON Score, render options, and server-owned color
metadata, then returns SVG plus render metadata.  The current `renderer.py`
implementation is wrapped as the static `default` engine.  inku does not load
arbitrary external engine code yet; this boundary exists so future engine packs
can be introduced without changing the API, history, JSON tab, CLI, or
benchmark metadata contracts.

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
| relations | あいだ | along, not touching, cutting, between |
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
compose, the JSON tab, and saved artifact JSON include the resolved
`stage1_model` / `stage2_model` that were actually used, plus
`render_build_number`, `render_color_profile`, `render_engine_id`,
`render_engine_version`, `render_canvas_aspect`, `render_hash`,
`render_hash_short`, `render_color_catalog_id`, `render_color_catalog_name`,
`render_color_catalog_sub`, `render_color_map`,
`instruction_lang_requested`, `instruction_lang_resolved`, `ui_lang`, and `render_seed`, where
abstract colors and `palette:<name>` entries are expanded to the exact
`#RRGGBB` codes used for SVG rendering.  The current engine metadata is
`render_engine_id: "default"` and
`render_engine_version: "1"`.  The full catalog `map` / `swatches` / `palette`
snapshot is not duplicated in render JSON because `render_color_map` is the
concrete color record needed for replay and audit.
`render_hash` is a 64-character SHA-256 hex hash of the rendered content and
server-owned render metadata.  `render_hash_short` is the four-character
uppercase suffix used for UI and CLI references.
Instruction-language metadata and `render_seed` are retained in JSON and history.
They are excluded from the current canonical Score payload; the rendered SVG and
server-owned render metadata still identify the concrete artifact for audit and
replay context.
`score.canvas` remains the score-level canvas instruction, while
`render_canvas_aspect` records the canvas aspect actually used for this rendered
artifact.  In normal server-generated output they match, but both are retained
so render metadata remains visible even when old records or imported Scores are
inspected.
`render_canvas_aspect_id` is the explicit canvas aspect identifier for new
metadata, and `render_canvas_aspect_ratio` records the actual rendered
width/height ratio as a number.  `render_canvas_aspect` remains for
compatibility; old records can be backfilled in responses by deriving the new id
and ratio from it.

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
- `at.region`: optional normalized placement region `[x0,y0,x1,y1]` resolved by the renderer seed
- `relation`: optional observable relation to the previous instruction: `along`, `not_touching`, `cutting`, or `between`

Large repetitions should prefer group behavior over literal overload.  Dense
clusters use `arrangement.density`, `cluster_count`, `fade`, and
`preserve_space` so that negative space remains part of the composition.

Current scene-tone palette behavior uses abstract colors only:

- spring, flowers, buds, and warm light lean toward red / green / white
- water, night, moon, rain, mist, and cold air lean toward blue / white / gray
- forest, leaves, grass, moss, and fragrance lean toward green / white / gray

Nuance that cannot be represented by the six abstract colors is retained in
`color_hint` for catalog-based rendering.

Relations are sequential.  `along`, `not_touching`, and `cutting` refer to the
immediately previous instruction; `between` refers to the previous two.  There
are no arbitrary ids, forward references, or repair governors for relations.
Invalid relations are dropped silently by validation or coercion, and the
instruction is rendered as an ordinary instruction.  The coerce layer may remove
invalid relations but must not add new ones.

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
The canvas panel header also shows the selected work's color catalog, canvas,
and creation time.  The color catalog button in the input panel displays the
currently selected catalog name and truncates long names with an ellipsis.

The settings modal's "other" tab includes history-selection behavior controls.
Users can choose independently whether selecting a history item updates the UI's
current canvas aspect and color catalog to the history item's values, or keeps
the current UI selections.  This setting affects only the UI selection state;
the saved history SVG is displayed as stored and is not re-rendered.

The canvas panel also supports viewing-oriented controls.  A fullscreen icon in
the drawing tab opens presentation mode, which maximizes the current SVG and
shows a compact control bar for history navigation, latest item, star toggle,
instruction caption toggle, and close.  Escape closes presentation mode.  A
caption icon in the drawing tab toggles an instruction caption.  In normal
canvas view, the caption uses 10% left and right margins relative to the drawing
tab and is clipped inside that tab.  In presentation mode, the caption uses 10%
left and right margins relative to the window.  Captions display the original
user-facing instruction text, not the internally augmented Stage 1 prompt; this
keeps emotion-hint or system prompt material out of presentation captions.

The history DB remains the source of truth for renders saved by the web UI,
`inku-cli`, Android headless CLI, and other API clients.  The web UI periodically
refreshes the latest normal history page while the signed-in user is viewing the
latest non-filtered history.  It also refreshes when the browser window regains
focus or a hidden tab becomes visible.  This allows CLI-saved renders to appear
in the history strip without a manual reload, while preserving the currently
selected history item when it is still present.  The UI does not auto-replace
history while the user is viewing starred-only history, search results, older
history pages, or while a history request is already in flight.

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
- the `auto repair` checkbox controls whether the server applies deterministic
  JSON Score repair after Stage 2. It is enabled by default. When disabled,
  Stage 2 output is rendered without the broader `coerce_score()` repair pass,
  while hard contract guards may still remove instructions that violate the
  requested primitive/color contract.

The same `Draw from DDL` action is also available below the interpretation box
for quick replay without opening the dialog.  The dialog itself does not start
drawing, so drawing actions remain concentrated in the main single-drawing
panel.

If the user edits DDL directly and then presses the normal `draw` button, inku
warns that the DDL edit will be lost.  The choices are `cancel`, `OK`, and
`draw from DDL`.  `OK` reruns Stage 1 from the natural-language prompt, while
`draw from DDL` preserves the edited DDL and runs Stage 2 / rendering only.
The natural-language prompt is not reinterpreted by `Draw from DDL`.

The drawing tab also exposes two explicit regeneration actions. **Another
performance** keeps the same Score and asks only the renderer for a new
performance seed. **Another composition** keeps the user-facing text as the
identity of the work but increments a `vary_seed` for Stage 1.5 selection, so
composition family, focus, and technique candidates can change without making
the default path nondeterministic. The same text plus the same `vary_seed` and
`render_seed` is reproducible from metadata.

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

In the color catalog dialog, clicking outside the dialog confirms the current
selection exactly like the save/confirm action. The cancel button still restores
the selection snapshot from when the dialog was opened.

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

Server-side output artifact saving is an admin-managed, server-wide setting.
The settings dialog includes an admin-only "other (server)" tab for:

- enabling or disabling automatic drawing file artifact saving
- setting the output folder as an absolute server path
- selecting the automatic PNG artifact size, either 1080px or 2160px

The server stores these values in `app_settings.output_save_settings` as
`enabled`, `output_dir`, and `png_size`.  `INKU_OUTPUT_DIR` and
`INKU_OUTPUT_PNG_SIZE` provide initial values; if unset, the defaults are
`~/.local/share/inku/outputs` and 2160px.  The API endpoint
`PUT /api/settings/output-save` is admin-only, accepts only absolute output
paths, and restricts PNG size to 1080 or 2160.

Disabling automatic artifact saving does not disable DB history saving.  The
history DB remains the source of truth, and only derived files such as SVG,
JSON, input text, normalized DDL, and PNG artifacts are skipped.  When enabled,
artifact files remain grouped by user and date under
`<output_dir>/<user_id>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history-id>...`.

The "other (server)" tab shows save worker and queue settings, save statistics,
and the PNG artifact size.  Save workers are concurrent file-save jobs; the
queue is the maximum number of pending artifact save jobs.  If the queue is
full, the server preserves DB history and skips only artifact file saving.

Server log retention is also an admin-managed, server-wide setting.  The
settings dialog includes an admin-only "log retention" tab for enabling or
disabling application log retention, setting the retention period in days,
choosing a daily / weekly / monthly rotation interval, and enabling compression
for rotated logs.  The default policy is enabled, rotates daily, keeps 90 days,
and compresses rotated logs.

The server stores this policy in `app_settings.log_retention_settings` as
`enabled`, `retention_days`, `rotate`, and `compress`.  `INKU_LOG_RETENTION_DAYS`
and `INKU_LOG_ROTATE` provide initial values.  `GET /api/settings/status`
returns the current policy with generated `logrotate` and `systemd` drop-in
previews for `inku-server` and `inku-api`; `PUT /api/settings/log-retention` is
admin-only and updates the stored policy.  Applying those generated files to the
host OS remains an operational task that requires server privileges.

The generated systemd preview uses
`StandardOutput=journal+append:/var/log/inku/<service>.log` and the matching
`StandardError` value so operators can follow logs through both
`journalctl -fu <service>` and retained file logs.  `inku-api` and `inku-server`
also print startup banners wrapped in 60-character `=` borders; the banners
include the service role, application version, build number, build date, mode,
listen host/port, runtime / platform, and log destination.  The API banner
includes the active render engine ID and version.  The API and web UI use
different emoji sets that match their roles.

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

Concurrent drawing requests are bounded at the application layer. Stage 1 and
Stage 2 LLM calls share a bounded executor controlled by `INKU_STAGE_WORKERS`
and `INKU_STAGE_QUEUE_LIMIT`. If capacity cannot be acquired, or if a stage
exceeds its hard timeout, the request follows the same deterministic fallback
path used for stage hard timeouts. Timed-out LLM calls may continue in their
underlying Python thread until the provider call returns, so their capacity slot
is retained until that worker actually finishes. This prevents timed-out
provider calls from creating an unbounded backlog.

Per-user drawing counters are updated with a single database-side atomic
increment so simultaneous `/api/paint` requests for the same user do not lose
generation counts. History listing, retrieval, starring, trashing, restoring,
and deletion remain scoped by `user_id` so drawing history does not mix across
users. Admin status responses include `stage_execution` with Stage worker count,
queue limit, and submitted/completed/failed/timed_out/rejected counters.

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

`inku-cli paint` and `inku-cli batch` support `--input-mode paint|ddl`.
The default `paint` mode sends natural-language input to `/api/paint` and runs
the full Stage 1 -> Stage 1.5 -> Stage 2 -> render pipeline.  `--input-mode ddl`
treats the input text as already-normalized DDL, skips Stage 1, and sends it to
`/api/compose`.  When `--input-mode ddl --save-history` is used, the CLI saves
the compose result through `POST /api/history` so the output appears in normal
server history.  `/api/compose` returns the effective DDL after Stage 1.5
expansion, and CLI output/history use that effective DDL for DDL-to-render
benchmark parity.
The CLI sends instruction language through `--instruction-lang auto|ja|en`.
`auto` is the default and lets the server resolve Japanese or English from the
input text.  `--ui-lang` may be supplied as display-context metadata, but it
does not control interpretation.

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

Current render-core tuning records explicit artwork-quality metrics in CLI
benchmark summaries: `constraint_adherence`, `negative_space_pressure`,
`motion_energy`, `color_resonance`, `visual_event`, and `figurative_risk`.
Fallback use, server hard timeouts, motif hints, presence counts, color traces,
and compositional markers are recorded separately.  Queue or retry duration is
diagnostic only and is not treated as a primary quality metric, because free
inference endpoints can be dominated by external queue behavior.

For NVIDIA free API testing, elapsed time is treated as operational metadata,
not as an artistic quality signal.  Queue delays can indicate service pressure,
but they do not exclude a successful work from aesthetic or structural review.

---

## 15. Current Implementation Status

The reference implementation currently includes:

- FastAPI backend
- SvelteKit frontend
- native Android app
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
- CLI DDL input mode for DDL-to-render parity: `inku-cli paint --input-mode ddl`
  and `batch --input-mode ddl` call `/api/compose` directly and save through
  `/api/history` when `--save-history` is set
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

The Android app is a Kotlin + Jetpack Compose native package with Room/SQLite
as its local data layer.  It is a single-user application package rather than a
multi-user server client.  Server/web remains the development master for DDL
interpretation, Stage 1.5 expansion, Score repair, SVG rendering, history
metadata, canvas aspect values, and render hash semantics.  Android-specific UI
decisions are allowed only when they are explicit mobile equivalents or
documented omissions.

Android local LLM support uses LiteRT-LM with Gemma 4 E2B as the standard local
model and Gemma 4 E4B as the higher-quality option.  Model license acceptance,
download state, re-download, checksum validation, and model file paths are
stored in Room.  The LiteRT-LM GPU backend is required; CPU fallback is not part
of the Android behavior.

Android simplifies model selection to one drawing model for instruction
generation, Stage 1, and Stage 2, while preserving server-compatible
`stage1_model` and `stage2_model` fields in settings, JSON display, exported
JSON, history records, and render metadata.  The Model Settings page exposes
provider panels for adding services, editing service names and base URLs,
adding or deleting API keys, fetching provider model lists, and choosing
published models.  Connection kind is set when a service is created and is not
edited from existing service panels.  Fetched candidate models are stored
separately from the published models shown in the drawing model picker.

The Android drawing view provides mobile-specific controls: pinch zoom, pan,
left/right image swipes for history navigation, and double-tap presentation
mode.  Presentation mode hides other UI, centers the image, rotates landscape
canvases for portrait phones, and chooses the surrounding background from the
rendered image background.  White-background images use the dark app
background; black-background images use a light background.

The Android history view intentionally differs from the server/web UI.  It uses
a three-column thumbnail grid and omits trash, list view, bulk selection, user
management, DB administration, plugin administration, and server log controls
because the Android package is single-user and mobile-first.

Android SVG/PNG export follows the server/web `CanvasPanel` intent.  SVG export
is a menu with display, editable, and compatibility profiles.  PNG export is a
menu backed by Room `export_templates`, with `1080px`, `2160px`, and `4320px`
Y-axis defaults.  Android opens the platform share sheet instead of browser
downloads.

Android render metadata includes `render_canvas_aspect_id` and
`render_canvas_aspect_ratio`, derived from the same canvas aspect definitions
ported from the server/web system plugin.  Android headless render and
comparison tooling can run without the Compose UI and is used with the server
CLI `--input-mode ddl` flow to compare DDL-to-render and Score-to-render
parity.

Android versioning is independent of the web build number.  `android/VERSION`
is the source for Android `versionName`, and `android/BUILD_NUMBER` is the
source for Android `versionCode`.  For the v1.48 generation, the Android values
start at `1.48.0-android.1` and `148001`.  The Android Settings menu exposes
version details including version name, version code, build type, application
id, source spec generation, and render engine version.

History records carry a server-side `render_hash`: a 64-character SHA-256 hex
hash of the rendered content and render metadata.  History APIs, paint/compose
responses, the JSON tab, and saved artifact JSON expose both `render_hash` and
the four-character uppercase `render_hash_short` for human reference.  The
history manager shows the short hash without changing the thumbnail layout;
clicking it copies the full hash.  The status bar also shows the current
render's short hash beside the star action and copies the full hash when
clicked.  After the web UI saves a render through the history API, it replaces
the active result hash with the DB history record's hash so the value shown
immediately after rendering matches the value shown when the same work is later
selected from history.  The CLI can resolve hash suffixes, reject ambiguous
short matches, and export selected or ranged history items for benchmark review.
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
profile, render engine, canvas aspect, and color catalog fields, followed by the
`score` payload.
When a history item is reopened, the JSON tab displays the saved `stage1_model`
and `stage2_model` from that history record.
Paint, compose, history records, the JSON tab, and saved artifact JSON also
include render engine metadata.  `render_engine_id` identifies the rendering
core that performed the JSON Score, and `render_engine_version` identifies that
engine's contract version.  These fields are included in the canonical
`render_hash` payload so two works rendered with different engines remain
traceable even when their input Score is otherwise similar.
The settings dialog includes an admin-only Model Settings tab.  It stores the
default Stage 1 / Stage 2 provider and model plus per-provider base URL and API
key settings in server app settings.  The supported connection targets are
OpenAI API Platform, Claude API, Gemini API, NVIDIA NIM, Ollama's
OpenAI-compatible API, and Intel OVMS's OpenAI-compatible API. Admin users can
add and remove connection services from the model settings tab. Added services
carry a service ID, display name, connection kind (`openai_compatible`,
`anthropic`, or `gemini`), base URL, and optional initial API key. The add
service dialog saves the new service to the server immediately when Add is
pressed, so service panels do not include a redundant whole-panel save button.
Model lists are fetched later through each service's model-list fetch action
instead of being typed manually when the service is created.
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
distinguishes preserving, replacing, and clearing a provider key. Provider API
keys are stored in the DB in encrypted `enc:v1:` form. The server uses
`INKU_SECRET_KEY` when set, otherwise `INKU_SECRET_KEY_FILE` or
`~/.local/share/inku/secret.key` as a local key file. Existing plaintext keys
remain readable for compatibility and are migrated to encrypted storage on the
next save. The Model Settings tab shows this rule next to the AI service
connections heading: API keys are encrypted in the DB, are never displayed
again, and keys configured through environment
variables are treated as initial values. LLM calls
resolve provider-prefixed model IDs such as
`openai:...`, `anthropic:...`, `gemini:...`, `nvidia:...`, `ollama:...`, and
`ovms:...`, while keeping compatibility for older NVIDIA slash IDs and local
OVMS model IDs.
The web UI normalizes model IDs sent to `/api/paint`, `/api/interpret`, and
`/api/compose` by combining the selected provider with the selected model, for
example `openai:gpt-5.2`. If an API request still sends a bare model ID and it
matches the current user's configured Stage 1 or Stage 2 model, the server
qualifies it with that user's configured provider before dispatching. Demo
prompt generation uses the same provider resolution path for OpenAI API
Platform, Claude API, Gemini API, NVIDIA NIM, Ollama, and Intel OVMS.
LLM server connection settings are global admin-managed settings.  Each user's
Stage 1 / Stage 2 provider and model selection is stored separately in
`user_accounts.model_settings`, saved from the model selection dialog through
`/api/auth/me/settings`, and restored on login.  Admin users can also toggle
which models are visible to users for each provider. Published-model selection
is handled in a separate dialog that also contains model-list fetch, search,
select-all, and clear-all controls. Checkbox changes inside that dialog are
drafted locally and are sent to the server only when Save is pressed; Cancel or
clicking outside the dialog discards them. The main settings tab summarizes
only the currently published models. `GET /api/models` returns only published
models for signed-in users, and the model selection dialog uses that filtered
catalog.
The status-bar PNG export templates default to Y-axis heights of `1080px`,
`2160px`, and `4320px`. Older saved defaults of `1024px` and `2048px` are
automatically replaced by the new defaults, while user-customized templates are
preserved. The Japanese UI labels this dimension as `Y軸` / `Y軸の高さ`.

### v1.52 (2026-07-04)

Version 1.52 materializes post-selection through two explicit regeneration
paths. `render_seed` supports another performance without an LLM call.
`vary_seed` supports another composition by mixing an explicit counter into the
Stage 1.5 selection seed while preserving the default rule that the same input
produces the same expansion. The vary path changes composition-family, focus,
and technique selection; it does not intentionally change Stage 1
interpretation.

Version 1.52 also forbids repair parts from becoming a system fingerprint. CLI
diversity analysis now reports marker-based repair-part counts and sample
rates. Coerce repair parts use input-derived placement and shape variation
instead of fixed coordinates, and adjacent focal reactions fire only for
isolated visual events.

Build 442 verification confirmed that the `vary_seed` path is implemented
through the API, CLI, and web UI. A 5-prompt x 5-vary run succeeded 25/25 with
no fallback, and JP/EN 30-sample repair-part measurement reduced
`adjacent_reaction` from 56/60 to 14/60.

Build 442 did not satisfy the benchmark acceptance gate. `angular_pulse`
remained at 14/60, `vanishing_trace` rose from 21/60 to 26/60, and average
`visual_event` fell from the Build 441 baseline of 93.0 to 77.8.

Build 443 tightened `vanishing_trace` so it requires both a disappearance
context and a trace subject such as footprints, breath, outlines, figures, or
circles. It also changed the generic `visual_event` fallback from a small
angular pulse to an input-derived compact mark. The JP/EN 30+30 benchmark then
reported `adjacent_reaction` at 11/60, `angular_pulse` at 0/60, and
`vanishing_trace` at 2/60, satisfying the repair-fingerprint gate. Average
`visual_event` remained 77.93 and `negative_space_pressure` remained 88.97, so
the Build 441 quality-regression guard is still not satisfied. Version 1.52
should therefore be read as complete for feature delivery and repair-fingerprint
suppression, with low-quality sample investigation still remaining.

Build 444 targeted the remaining low-quality samples without adding a new
global floor. The generic compact visual event now carries a color cycle and an
input-derived opposing center; a `brief_arrival_departure` event type covers
temporary arrival-and-leaving moments; and the existing doubled-river-road and
tilted-room-drop recipes now carry color cycling and opposing placement. The
targeted benchmark recovered EN #06 to `visual_event` 98 /
`negative_space_pressure` 100, EN #27 to 70 / 76 on a single rerun, and JP #28
to 76 / 86.

The Build 444 JP/EN 30+30 full benchmark
(`cli/out/jp-en-30-equivalent-444/{jp,en}/`) completed 60/60 with no fallback.
Repair parts remained within the v1.52 fingerprint gate:
`adjacent_reaction` 10/60 (16.7%), `angular_pulse` 0/60, and
`vanishing_trace` 2/60 (3.3%). The quality averages were `visual_event` 79.90,
`negative_space_pressure` 89.97, `motion_energy` 94.57, and
`constraint_adherence` 93.33. Compared with the Build 441 guard baseline
(`visual_event` 93.0, `negative_space_pressure` 96.23, `motion_energy` 97.7,
`constraint_adherence` 86.0), `visual_event` and
`negative_space_pressure` still miss the within-5 regression guard. The current
v1.52 status is therefore: Phase A-D implementation, measurement, vary, and
repair-fingerprint acceptance are complete, but the quality-regression guard is
not yet accepted. Further work should inspect low-scoring rows such as EN #21
(`visual_event` 40 / `negative_space_pressure` 26), JP #23
(`negative_space_pressure` 42), and JP #02/#03 (`visual_event` 48), and improve
existing recipe placement, color cycling, and opposing relationships rather
than adding marker vocabulary or a new governor.

### v1.51 (2026-07-02)

Version 1.51 adds the relation system, called `aida` in Japanese, and assigns
variation to both micro and macro scales.  JSON Score instructions may now carry
`at.region` for renderer-resolved placement and `relation` for observable
relationships to previous instructions: `along`, `not_touching`, `cutting`, and
`between`.  Renderer performances record `render_seed` so macro placement can
vary between performances while remaining reproducible when a seed is provided.

Stage 1.5 is redirected away from fixed finished recipes and toward
composition-family selection plus relation attachment.  Invalid relations are
dropped rather than repaired, and the coerce layer is forbidden from adding
relations.

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
