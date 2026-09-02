# Current implementation status

**What the reference implementation actually carries today.** Split out of `SPEC.md` §15 on
2026-07-28: an inventory of what is built is not a specification of what the language is, and
it was the single largest section standing between a reader and the concepts.

**Both languages.** By the author's ruling of 2026-08-02 this file corresponds to
[`implementation-status.ja.md`](implementation-status.ja.md) section for section. Japanese is the
canonical source; this replaces the 2026-07-28 ruling under which the inventory was English only.

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
- progress mascot chosen in settings from two, `Incu` and `Yuragi`; single
  drawing, DDL replay, batch, and demo all share the selected one
- integrated DDL interpretation editor with Saijiki drawer, expanded dialog,
  token/time display, and cancellable `/api/compose` replay
- shared-Rust `inku-ddl` compiler foundation that preserves visible normalized DDL with source
  spans and reaches a typed semantic document, generic macro locking/binding/finite expansion,
  ownership conservation, and fail-closed diagnostics; accepted, but not connected to product runtime
- scene-tone color strategy, richer fallback Scores, sensory visibility
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

History records carry a server-side `render_hash`. New records use the `rh2:<sha256>` edition-id semantics from the render metadata section: saved Score plus explicit render conditions, not SVG text. Legacy 64-character hashes remain display-compatible. History APIs, paint/compose responses, the JSON tab, and saved artifact JSON expose both `render_hash` and the four-character uppercase `render_hash_short` for human reference.  The
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
History-manager thumbnails do not open an enlarged hover preview, keeping the grid and selection interaction stable.
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
OpenAI-compatible API, and Ollama Cloud. Admin users can
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
variables are treated as initial values. A model reference is resolved in three
steps and never by guesswork: an explicit provider prefix wins
(`openai:...`, `anthropic:...`, `gemini:...`, `nvidia:...`, `ollama:...`,
`ollama-cloud:...`); otherwise, if *exactly one* configured provider
lists that model ID, that provider is used; otherwise the stage's configured
provider is used. Because a provider ID cannot contain a colon, the first colon
is the only possible split point, so a model ID may carry any number of them
(`qwen3.5:4b-q4_K_M`). A model ID offered by two providers — `gpt-oss:20b` is
offered by both Ollama and Ollama Cloud — is deliberately *not* decided by the
second step. The earlier fallbacks (a slash meaning NVIDIA, a `gemini-` prefix,
and a catch-all provider) are gone: a bare string that no catalog lists now goes
to the stage's provider instead of silently to one that answered `/health` long
after it had stopped serving models. That provider, Intel OVMS, was withdrawn
altogether on 2026-07-30; a withdrawn provider is dropped from stored settings on
read, is offered nowhere, and raises rather than accepting a connection, while its
model ids stay readable so works made on it are still named.
Wherever a model is named on screen — the running indicator, the work's Stage 1
and Stage 2 lines, the history table, the lineage node details — it is named as
`<provider> / <model>`, because a model id alone does not say where it runs and,
with `gpt-oss:20b` served by two providers, is not even unique. The model picker
is the exception: its cards already sit under a provider heading.
The web UI normalizes model IDs sent to `/api/paint`, `/api/interpret`, and
`/api/compose` by combining the selected provider with the selected model, for
example `openai:gpt-5.2`. Stored per-user model choices are provider/model
pairs; the older single qualified string is still accepted on read and split
into a pair. Demo prompt generation uses the same provider resolution path for
OpenAI API Platform, Claude API, Gemini API, NVIDIA NIM, Ollama, and Ollama
Cloud. Ollama Cloud declares its own concurrency ceiling, which the
server enforces per provider rather than exposing as a setting.
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

### v1.52 (2026-07-04)

Version 1.52 materializes post-selection through two explicit regeneration
paths. `render_seed` supports another performance without an LLM call.
`composition_seed` supports another composition by mixing an explicit counter into the
Stage 1.5 selection seed while preserving the default rule that the same input
produces the same expansion. The vary path changes composition-family, focus,
and technique selection; it does not intentionally change Stage 1
interpretation.

Version 1.52 also forbids repair parts from becoming a system fingerprint. CLI
diversity analysis now reports marker-based repair-part counts and sample
rates. Coerce repair parts use input-derived placement and shape variation
instead of fixed coordinates, and adjacent focal reactions fire only for
isolated visual events.

Build 442 verification confirmed that the `composition_seed` path is implemented
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

Build 445 generalized the Build 444 low-score fixes into DDL coverage handling
for small dots, circles, and ellipses. English DDL sentence splitting is now
more precise, `circle` and `ellipse` are no longer collapsed into one fallback
shape, and `radius` / `半径` plus small-mark coverage such as `small dot` is kept
as a compact, low-density foreground mark with outward fade and preserved
negative space. This is a shape, size, and spacing correction in the existing
coerce fallback path, not a new marker vocabulary or global governor.

The Build 445 JP/EN 30+30 full benchmark
(`cli/out/jp-en-30-equivalent-445/{jp,en}/`) completed 60/60. JP #27 and JP #28
still hit stage2 timeouts on the final server-timeout retry and used saved
fallback results, so fallback was 2/60. Repair parts remained accepted:
`adjacent_reaction` 8/60 (13.3%), `angular_pulse` 0/60, and
`vanishing_trace` 2/60 (3.3%). Quality averages were `visual_event` 80.43,
`negative_space_pressure` 91.47, `motion_energy` 93.73,
`constraint_adherence` 94.17, `color_resonance` 96.83, and
`figurative_risk` 1.33. Against the Build 441 guard baseline,
`negative_space_pressure`, `motion_energy`, and `constraint_adherence` are back
within the allowed -5 window, but `visual_event` is still below the required
threshold (`80.43` versus `93.0`). The remaining v1.52 work is now concentrated
on restoring semantic eventfulness for low rows such as JP #02 (`visual_event`
40) and JP #21 / EN #04 / EN #20 / EN #21 (`visual_event` 48).

Build 446 / 446-2 addresses those sticky low-event rows by strengthening only
existing instructions and arrangement metadata. Compact dot, circle, and ellipse
coverage can now be treated as a compact focal visual event in an event context.
Existing focal events receive an opposing arrangement center, color cycle,
preserved negative space, low density, and outward fade so that they read as
compositional counterweights. For inherited-memory scenes, an existing support
instruction can carry an inherited-memory trace instead of adding a new repair
part. This is not a new drawing primitive or global floor; it is a placement,
color-cycle, and semantic-hint correction on existing elements.

The Build 446-2 JP/EN 30+30 full benchmark
(`cli/out/jp-en-30-equivalent-446-2/{jp,en}/`) completed 60/60. JP #09 still
used a fallback result after the final stage2-timeout retry, so fallback was
1/60. Quality averages were `visual_event` 92.85,
`negative_space_pressure` 94.30, `motion_energy` 96.95,
`constraint_adherence` 95.50, and `color_resonance` 99.75, satisfying the
Build 441 -5 regression guard. Repair fingerprints also remain accepted:
`adjacent_reaction` 13/60 (21.7%), `angular_pulse` 0/60, and
`vanishing_trace` 1/60 (1.7%). The inherited-memory arc that fable5 identified
as a possible successor fingerprint is now measured as `inherited_memory_arc`;
it appeared in 4/60 samples (6.7%).

The remaining risk is relation drop rate. Build 446-2 measured JP 15/53
(28.3%), EN 22/51 (43.1%), and 37/104 combined (35.6%), above the 20% reference
used by fable5. v1.52 keeps relation validation drop-only: coerce must not
repair or complete relations. If this rate is treated as blocking, mitigation
should be limited to Stage 2 prompt guidance that emits relations only when they
are safe in output order and omits them when uncertain.

Build 447 treated relation drop rate as blocking and strengthened the Stage 2
prompt. Ordinary placement language such as along a diagonal band, along an
undulating trace, riverbank, and roadside must not become relation; `between`
requires two immediately previous outline instructions; and uncertain cases
must omit relation. The Build 447 JP/EN 30+30 benchmark still measured JP 13/55,
EN 4/29, and 17/84 combined dropped relations, or 20.2%, just over the 20%
reference used by fable5.

Build 448 adds a Stage 2 output gate that keeps relation only when the
normalized DDL literally contains one of the fixed previous-object phrases:
`前の線に沿って` / `along the previous line`, `前の形に触れない` / `not
touching the previous shape`, `前の線を切る` / `cutting the previous line`, or
`前の二つの間に` / `between the previous two`. Natural-language-derived ideas
such as around, same beat, ahead/behind, not touched, near, and far are expressed
with position, path, rotation, and spacing instead. Coerce remains drop-only for
relations and still does not repair or complete them.

The Build 448 JP/EN 30+30 full benchmark
(`cli/out/jp-en-30-equivalent-448/{jp,en}/`) completed 60/60. JP #01 still used
a fallback result after the final stage2-timeout retry, so fallback was 1/60.
Combined quality averages were `visual_event` 92.40,
`negative_space_pressure` 95.87, `motion_energy` 97.77,
`constraint_adherence` 92.00, and `color_resonance` 99.27, satisfying the Build
441 -5 regression guard. Repair fingerprints also remain accepted:
`adjacent_reaction` 14/60 (23.3%), `angular_pulse` 0/60, `vanishing_trace` 2/60
(3.3%), and `inherited_memory_arc` 4/60 (6.7%). Relation drop improved to JP
1/6 (16.7%), EN 0/2, and 1/8 combined (12.5%), below the blocking 20% reference.
The relation sample rate is intentionally low on the natural-language fable set
because relation is again reserved for fixed previous-object phrases. Version
1.52 is therefore accepted for vary, repair-fingerprint suppression, the quality
guard, and the relation-drop blocking item.


### v1.60 (2026-07-07)

Version 1.60 moves the project from quality-loop closure to a one-person playable 1.0 candidate: another person should be able to set up inku from the README, write a visual tanka, consult Saijiki, read interpretation feedback, choose with vary, save, and replay a result.

- `render_hash` is redefined as an `rh2:<sha256>` work-edition identifier computed from the saved JSON Score, `render_seed`, `composition_seed` (the rh2 payload keeps the frozen key name `vary_seed`), `render_build_number`, `render_color_catalog_id`, and render-engine metadata. SVG text, input text, normalized DDL, and raw LLM responses are excluded. Existing 64-character hashes remain legacy display-compatible values.
- History now stores `composition_seed`, and the history manager can replay a saved Score with its saved seed.
- The input panel shows approximate post-processing interpretation feedback using ink-density shading. This does not change the Stage 1 schema or prompt.
- The canvas displays the input text as a caption by default, treating the relation between words and image as part of the work.
- The English and Japanese READMEs now include Quick Start setup, provider/API-key guidance, two-stage regeneration, the six-color Saijiki constraint, and history replay.
- Final gallery selection is deferred to v1.70 or later. Version 1.60 is complete once the candidates are recorded; selecting works for publication belongs to the next evaluation and release cycle.
- Phase E sparse-output handling adopts the E-2 policy: use the existing `visual_event` / `negative_space_pressure` metrics and visual review only, without adding a dedicated metric or marker. Sparse outputs are not a blocking implementation target for v1.60.

### v1.70 (2026-07-08)

Version 1.70 implements the aesthetic-selection phase: it keeps judge metrics out of the acceptance gate and instead makes form, post-selection, and comparison visible in the product.

- The language/spec alignment pass clarifies that writer-facing words such as random scattering remain valid input, while unordered randomness is forbidden only as an internal Score representation. The core color vocabulary remains six abstract writer-facing colors; color catalogs are server-owned resolution metadata, not vocabulary expansion.
- The writing surface now carries only a quiet, non-blocking length hint: roughly 31 Japanese characters or roughly 12 English words.
- Saijiki relation entries keep poetic headings while examples show the reachable fixed previous-object phrases. Stage 1 only normalizes explicitly written element relationships into relation phrases; place or scene words such as riverbank-style "along" are not relation predicates.
- Post-selection is now concrete: a variation grid can produce four default candidates, optionally include a fresh interpretation candidate, allow multiple selections, and save selected works to history. Starred history items may carry a short optional note explaining the choice.
- Explicit interpretation variation records `interpretation_seed` and displays a normalized-DDL diff. Reproduction is anchored in the saved DDL/Score rather than in replaying the LLM nondeterministic text output.
- The `Nature` reference vocabulary plugin adds `Nature.wind`, `Nature.undulation`, and `Nature.stillness` as deterministic Stage 1.5 macros. The explicit `Nature.` namespace is required; plain natural-language words do not trigger the plugin. The implementation uses existing DDL/Score variation and arrangement only, so no new primitive, Score field, or coerce rule is added.
- Saijiki shows Nature plugin terms in a separate plugin category with distinct, subdued styling.
- The comparison area shows previous/current renders side by side, a subdued prompt diff, and an LLM Model Inspection view for two Stage 1 models. It is a viewing tool, not a judge surface, and displays no judge values.
- Localized tooltips were added to the main action controls, including the four-candidate grid, interpretation variation, save selected, model comparison, and DDL auto-repair controls. Tooltip text follows the main UI language switch.
- The left app rail no longer expands on mouse hover. Its width is controlled by an explicit top-left expand/collapse toggle, so the working area can remain stable while editing.
- Build 458 was verified on pentala for D-1/D-2; screenshots are stored under `no-git-sync/screen-cap/` and the local verification note is recorded in `cli/tune_bench.md`.

### v1.71 (2026-07-08)

- Added `instruction.surface` and `canvas.ground` to JSON Score for object-surface and canvas-ground texture.
- Added renderer support for display, editable, and compat texture profiles, including texture metadata and deterministic seed handling.
- Updated Stage 1 and Stage 2 prompts so texture words become score attributes instead of hidden helper shapes.
- Preserved backward compatibility: existing scores without surface or ground render as before.
- Expanded Svelte tooltip coverage across AppRail icons, Input panel tabs/buttons, and Canvas panel controls (zoom, vary, downloads, navigation) to improve usability.

---
