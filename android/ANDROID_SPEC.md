# inku Android Implementation Notes

This directory is the Android workspace for the native standalone app and is
tracked by Git. Local-only artifacts, device IDs, downloaded models, logs, and
secrets must remain outside tracked files.

Last updated: 2026-05-06.

## Specification Update Workflow

`ANDROID_SPEC.ja.md` is the canonical Android specification note.
`ANDROID_SPEC.md` is the maintained English version of the same intent.

When updating Android specifications:

1. Update `ANDROID_SPEC.ja.md` first.
2. Refresh `ANDROID_SPEC.md` as an English translation or public-facing
   adaptation of the Japanese source.
3. Do not introduce English-only Android requirements that are absent from
   `ANDROID_SPEC.ja.md`.

## Fixed Decisions

- Native Android implementation in Kotlin and Jetpack Compose.
- Room is the official database layer.
- SQLite is stored inside the application sandbox.
- Single-user standalone package.
- The local model provider is the default provider.
- External providers remain available for compatibility with the web reference:
  OpenAI, Claude, Gemini, NVIDIA NIM, Ollama, and Intel OVMS.
- The Android pipeline keeps the reference flow:
  description -> Stage 1 -> Stage 1.5 -> Stage 2 -> JSON Score -> SVG.
- JSON Score, render metadata, history import/export, color catalogs, canvas
  aspects, SVG profiles, and render hashes must remain compatible with the web
  implementation.
- SVG generation is ported to Kotlin. The app also has a native Compose Canvas
  preview path that renders stored JSON Score directly for reliable on-device
  thumbnails and main previews.
- Gemma 4 E2B is the default local model. Gemma 4 E4B is a high-quality option.
- First launch downloads the selected local model after a license confirmation.
- Target device class is Pixel 9 or newer.

## Current Implementation Status

The Android workspace currently contains a buildable standalone application
package with namespace `app.inku.mobile`.

Implemented:

- Gradle Android project with Kotlin, Jetpack Compose, Room, and KSP.
- `MainActivity` and `InkuApplication`.
- Room database named `inku.sqlite` in the app sandbox.
- Room entities and DAOs for:
  - history items
  - app settings
  - model assets
  - provider settings
  - color catalogs
  - plugin settings
  - export templates
- Repository and ViewModel layer for drawing, batch execution, demo execution,
  history selection, local settings, and placeholder model download state.
- Local model catalog and acquisition state management for Gemma 4 E2B/E4B:
  - official LiteRT-LM Hugging Face `.litertlm` URLs
  - SHA256 metadata
  - Room-backed license acceptance state
  - resumable `.part` downloads into the app sandbox
  - progress bytes, total bytes, ready, failed, cancelled, interrupted, and verifying states
  - SHA256 verification before finalizing the model file
  - recovery of a complete, already verified `.part` file without re-downloading
  - interrupted in-progress downloads are resumable from their `.part` files
  - app-sandbox final storage under `files/models/`
- Deterministic local fallback pipeline for:
  - natural language description to normalized DDL
  - DDL to JSON Score
  - JSON Score to SVG
  - render hash and render metadata generation
- Android rendering follows the same logical stages as the web `/api/paint`
  flow: Stage 1 interpretation, intermediate DDL expansion, Stage 2 Score
  composition, Score repair/coercion, SVG rendering, render-hash generation,
  and Room history persistence.
- Headless render execution for web/server comparison:
  - exported `HeadlessRenderActivity`
  - adb-startable run IDs and prompt/model/catalog/canvas extras
  - app-sandbox artifacts under `files/headless/<run_id>/`
  - extracted `result.json`, `normalized.ddl`, `score.json`, and `output.svg`
  - `INPUT_MODE=ddl` bypasses Stage 1 and sends an already-normalized DDL input
    directly through Stage 2 and later stages. This isolates LLM variance when
    comparing DDL -> Score -> SVG behavior against the server.
  - The server CLI also supports `inku-cli paint --input-mode ddl`, which calls
    `/api/compose` for DDL -> Score -> SVG and saves through `/api/history`
    when `--save-history` is set.
  - `android/scripts/headless_render_compare.sh` as an `inku-cli`-equivalent
    local comparison runner
  - `android/scripts/headless_batch_compare.sh` for multi-prompt comparison,
    retry, and aggregate summary generation
  - when `COMPARE_WEB=1`, server-side generation is executed through
    `inku-cli paint`; the script must not call `/api/paint` directly for the
    comparison path
  - `android/scripts/headless_render_compare.sh` defaults
    `CLI_SAVE_HISTORY=true` so server-side CLI drawings are run with
    `inku-cli paint --save-history` and can be reviewed later in normal server
    history. `summary.json` and the batch aggregate summary include the
    server-side `history_id`.
- LiteRT-LM is wired as the default local model provider for Stage 1 and Stage
  2. The provider reads the selected Gemma 4 E2B/E4B `.litertlm` file path from
  Room, verifies that the model is in the `ready` state, initializes a cached
  LiteRT-LM `Engine`, sends each stage prompt through a `Conversation`, and
  renders the returned `Message` into text. Requests use a bounded async flow
  with cancellation so the UI can return to the deterministic local fallback if
  device-side inference fails or exceeds the current timeout.
- Stage 1 now uses the web reference `SYSTEM_PROMPT_PREFIX` and dynamic
  `EXAMPLE_POOL` selection algorithm instead of the earlier Android summary
  prompt. The Android implementation selects the top five matching examples
  using the same keyword-count rule as `server/src/inku_server/interpreter.py`.
- Stage 1.5 now ports the web `expand_intermediate_ddl` path for Japanese DDL:
  placement-word sanitization, gray-background avoidance, static-center
  reframing, profile/tag selection, deterministic SHA-256 salted picks,
  structural/music/painting candidate selection, and centered-layer limiting.
- Stage 2 now uses the web reference `composer.py` Japanese system prompt
  verbatim, including the full conversion rules and key examples.
- If the LiteRT-LM provider cannot run for a stage, the local path falls back to
  the deterministic Kotlin port of the web fallback/coerce rules. Natural-
  language input is preserved into normalized DDL with explicit placement
  augmentation, so the Compose `指示` field, `解釈（正規化DDL）` field, rendered
  Score, and saved history remain aligned in the same user-visible flow.
- LiteRT-LM text responses are sanitized before entering the DDL path. Gemma
  chat control tokens and clearly non-DDL outputs such as SQL-like text are
  rejected and routed to the deterministic fallback.
- Kotlin SVG renderer port for the current primitive subset.
- Renderer support includes the web Score fields needed by the fallback path:
  `arrangement.color_cycle`, `arrangement.path`, clustered high-count groups,
  and primitive `rotation`.
- Native Compose preview renderer for stored JSON Score.
- Dark Compose UI in transition from the web-style workbench to a Pixel 9
  mobile-first layout based on the Claude Design prototype:
  - top application header
  - bottom navigation: Compose, History, Demo, Settings
  - Compose segmented mode: Write, Batch
  - bounded first-screen canvas card that respects the selected canvas aspect
    while keeping the prompt and DDL path reachable on Pixel 9
  - prompt and DDL interpretation below the canvas
  - fixed-height drawing CTAs with an in-place generating state and progress
    indicator, avoiding layout jumps during local LLM work
  - render sub-tabs: Artwork, Prompt, JSON
  - explicit button rows for model, color catalog, and canvas selection
  - dedicated History screen with search/filter placeholders and two-column
    thumbnail cards
  - stronger History selected-card affordance using an accent border and
    corner marker instead of an overlaid text badge
- History operations for the selected item:
  - star / unstar
  - soft trash
  - JSON share export through Android `FileProvider`
- Startup restoration of the latest selected history item into prompt, DDL,
  catalog, and canvas settings.
- Pixel 9 status bar and navigation bar safe-area handling.

Not implemented yet:
- Production-polished model download UX, including background continuation,
  notification progress, metered-network policy, and low-storage recovery.
- External provider execution. Provider records exist only as compatibility
  data structures at this stage.
- Full web feature parity for import/export, plugin management, advanced
  settings, user-management equivalents, and admin/server-only web features.
- Import from web-compatible JSON exports.
- Reference compatibility tests against exported web JSON fixtures.

## Verified Device State

Latest verified device class:

- Device: Pixel 9 connected by USB.
- APK: debug build from `android/app/build/outputs/apk/debug/app-debug.apk`.

Verified on device:

- App installs and launches.
- Process remains running after launch.
- Draw action creates a new Room history item.
- Batch-generated and single-draw history entries persist in `inku.sqlite`.
- Latest checked history count: `4`.
- Latest checked render hash short: `6D8E`.
- Stored JSON Score and render metadata are visible through the JSON render tab.
- Main preview and history thumbnails render from JSON Score on device.
- Star state updates are persisted to Room and reflected back into the selected
  history UI.
- JSON share export writes `inku-<render_hash_short>.json` into the app cache
  and opens the Android share sheet through `FileProvider`.
- Gemma 4 E2B/E4B model records are seeded into Room on launch.
- Gemma 4 E2B license acceptance persists as `ready_to_download`.
- No fatal Android runtime crash was observed in the checked logcat window.
- Headless Android render completed without opening the Compose UI. The checked
  run used NVIDIA Gemma 4 31B for Stage 1 and Stage 2, produced artifacts under
  `/tmp/inku-headless/codex-headless-test3/`, and reported render hash short
  `8097`.
- VPN connectivity to the local reference server was verified for web access
  through the frontend port. Direct CLI access to the backend API port waited
  without a response in this test, so the comparison used `inku-cli` through the
  frontend base URL.
- The latest Android-vs-server comparison was run with:
  - input: `青い背景に白い横線を三本引く`
  - Android device: Pixel 9 over USB
  - Stage 1: `nvidia:google/gemma-4-31b-it`
  - Stage 2: `nvidia:google/gemma-4-31b-it`
  - color catalog: `ink_porcelain`
  - canvas aspect: `square`
  - comparison runner: `android/scripts/headless_render_compare.sh`
  - server generation: `inku-cli paint` against the VPN-reachable frontend URL
  - artifacts: `/tmp/inku-headless/codex-cli-compare-vpn2/`
- The comparison completed, but parity was not achieved:
  - Android render hash short: `8097`
  - server/inku-cli render hash short: `77FE`
  - `same_render_hash`: `false`
  - `same_ddl`: `false`
- Observed parity gaps from that run:
  - Android normalized DDL duplicated the final clause:
    `黒い細い斜め線を右上がりに三本並べる。細かく震える。`
  - server/inku-cli normalized DDL did not contain that duplicate clause.
  - Android Score had 3 instructions.
  - server/inku-cli Score had 4 instructions, including a `color_cycle` repair
    and a white ellipse composition anchor.
  - Android render metadata reported `render_engine_version: 1`; the server
    reported `render_engine_version: 2`.
- A five-prompt comparison was run using generated 32-character Japanese
  seasonal instructions, Android headless CLI-equivalent rendering, and server
  `inku-cli paint`.
  - batch id: `season32-compare-003`
  - artifacts: `/tmp/inku-headless/season32-compare-003/`
  - prompt count: `5`
  - success count: `5`
  - error count: `0`
  - same render hash count: `0`
  - same DDL count: `1`
  - all input prompts were verified as 32 characters:
    - `春の雨に濡れた桜の影を白い余白へ淡く静かに散らす細い銀の線たちよ`
    - `夏の夜に光る海風を青い円と赤い点で遠く揺らす透明な波音として置く`
    - `秋の夕暮れに舞う落葉を金の線と黒い余白で斜めに重ねる細い影二本を`
    - `冬の朝に凍る池の息を白い弧と灰の点で静かに結ぶ細い影青く遠く残す`
    - `梅雨明けの雲間に虹の欠片を緑の弧と青い粒で軽く浮かべるそっと置く`
  - hash short comparison:
    - `season32-001`: Android `18E1`, server `FDCE`, DDL mismatch
    - `season32-002`: Android `5BF6`, server `CAA0`, DDL mismatch
    - `season32-003`: Android `588C`, server `E2BC`, DDL mismatch
    - `season32-004`: Android `2033`, server `2357`, DDL mismatch
    - `season32-005`: Android `E590`, server `5D2D`, DDL match
  - `season32-001` showed large Android/server divergence in numeric
    extraction from natural language.
  - `season32-002` was semantically close, but Android added material details
    such as `細筆` and `鉛筆`.
  - `season32-003` produced the unnatural Android phrase `二本数を二本並べる`.
  - `season32-004` diverged in background color, placement, count, and whether
    an additional line was added, showing a large Stage 1/1.5 parity gap.
  - `season32-005` matched DDL but still produced a different render hash,
    leaving renderer / metadata / SVG generation parity unresolved.

The latest local verification screenshot was written to:

```text
/tmp/inku-android-workbench.png
```

## Data Source of Truth

The Room database is the source of truth for local history and settings.
Generated SVG, JSON export files, and PNG files are derived artifacts.

Heavy user-visible exports should use Android's Storage Access Framework.
Internal model files and app-owned artifacts live in the app sandbox.

## Compatibility Boundary

The Android app has no multi-user authentication. Web user-scoped records map to
one implicit local user. User-management and admin-only features should be
represented as local settings where they still make sense, but they should not
add login or role handling.

Server-only web features are kept out of the Android runtime unless they have a
clear local single-user equivalent.

## Web/Server Master Policy

The Android port always treats the `web/` and `server/` implementations as the
development master. Android is still a standalone native application package,
but the behavioral source of truth for DDL interpretation, Stage 1.5 expansion,
Score coercion/repair, SVG rendering, and history/render metadata is the
web/server implementation.

Whenever web/server changes, the corresponding Android parity surface must be
checked in the same change unit. Android compatibility code is split along the
same responsibility boundaries as the server source so that future diffs are
easier to inspect and omissions are easier to catch.

Current renderer compatibility layout:

| server source | Android compatibility file | Responsibility |
| --- | --- | --- |
| `server/src/inku_server/renderer.py` / `_stroke_attrs`, dash, texture, blur | `android/app/src/main/java/app/inku/mobile/render/ServerRendererStyle.kt` | Stroke/fill attributes, material weight style, texture filters, blur filters, hint opacity |
| `server/src/inku_server/renderer.py` / `_arc_path_d`, point generation, variation | `android/app/src/main/java/app/inku/mobile/render/ServerRendererGeometry.kt` | SVG geometry, arc sweep/large-arc rules, regular polygon points, triangle bbox points, variation paths |
| `server/src/inku_server/renderer.py` / material outline helpers | `android/app/src/main/java/app/inku/mobile/render/ServerRendererMaterial.kt` | Pencil/crayon/chalk/brush/rope outlines, specks, rope twists |
| `server/src/inku_server/renderer.py` / `render` and `_render_instruction` flow | `android/app/src/main/java/app/inku/mobile/render/DefaultSvgRenderer.kt` | Android SVG renderer orchestration, arrangement expansion, presence layer, metadata emission |

`DefaultSvgRenderer.kt` keeps orchestration only. Server-derived details belong
in `ServerRendererStyle.kt`, `ServerRendererGeometry.kt`, and
`ServerRendererMaterial.kt`. When server `renderer.py` changes, those files are
the first Android update targets.

The same policy applies to the pipeline. Changes in
`server/src/inku_server/interpreter.py`, `ddl_expander.py`, `coerce.py`, and
`schema.py` must be checked against the Android `pipeline/` package and
compatibility data models. Android-specific UI, Room, LiteRT-LM, and provider
routing can remain native, but user-visible DDL, Score, SVG, render metadata,
and history persistence behavior prioritize web/server parity.

Current pipeline compatibility layout:

| server source | Android compatibility file | Responsibility |
| --- | --- | --- |
| `server/src/inku_server/interpreter.py` / Stage 1 model text cleanup and usable DDL guard | `android/app/src/main/java/app/inku/mobile/pipeline/ServerDdlText.kt` | Model output cleanup, Stage 1 DDL normalization, number-noise repair, clause dedupe, drawable vocabulary guard |
| `server/src/inku_server/ddl_expander.py` | `android/app/src/main/java/app/inku/mobile/pipeline/WebDdlExpander.kt` | Stage 1.5 DDL expansion and sensory/structural marker insertion |
| `server/src/inku_server/coerce.py` / `PRIMITIVE_SPECS`, field coercion, post-coerce | `android/app/src/main/java/app/inku/mobile/pipeline/ServerScoreCoercer.kt` | Stage 2 instruction primitive field repair, fallback field selection, arc angle repair |
| `server/src/inku_server/coerce.py` / semantic marker helpers, presence inference, color/layout/material/radius detection | `android/app/src/main/java/app/inku/mobile/pipeline/ServerScoreSemantics.kt` | Context marker detection, quiet-density/motion/colorful context checks, presence inference, visible color/background, DDL hint helpers |
| `server/src/inku_server/composer.py` and `coerce.py` / fallback score synthesis | `android/app/src/main/java/app/inku/mobile/pipeline/ServerFallbackComposer.kt` | Fallback DDL, fallback instruction, and arrangement synthesis after provider failure or unusable Stage 2 output |
| `server/src/inku_server/coerce.py` / DDL coverage, shape/color/motif/composition repair factories | `android/app/src/main/java/app/inku/mobile/pipeline/ServerScoreRepairFactory.kt` | Drawable clause extraction, clause primitive/color mapping, coverage instruction, shape/motif repair instruction factories |
| `server/src/inku_server/coerce.py` / semantic repair order and Android-local orchestration | `android/app/src/main/java/app/inku/mobile/pipeline/LocalFallbackPipeline.kt` | Score coercion orchestration, dedupe, DDL coverage, color/shape/motif/composition/context/motion/presence/density repair order, fallback Score construction, Stage 1/2 provider fallback control |
| `server/src/inku_server/schema.py` / Stage 2 tool contract and provider tool-call responses | `android/app/src/main/java/app/inku/mobile/pipeline/WebScoreTool.kt` | Stage 2 `submit_score` schema, Stage 2 JSON extraction, tool_calls/arguments unwrap, renderable instructions guard |

Function-level parity table from prompt to rendering:

| Flow step | server master | Android port | Parity rule / current work item |
| --- | --- | --- | --- |
| UI prompt input | `web/src/lib/components/InputPanel.svelte` / `DdlEditor.svelte` | `ui/InkuApp.kt` / `ui/InkuViewModel.kt` | Mobile-native UI is acceptable, but prompt, DDL, auto-repair, model/catalog/canvas state must stay in the same saved flow. |
| Paint API orchestration | `api.py::api_paint` | `data/InkuRepository.kt::paint` / `pipeline/LocalFallbackPipeline.kt::paint` | Keep the order: Stage 1, Stage 1.5, Stage 2, coerce, render, hash, history save. |
| Stage 1 model call | `interpreter.py::interpret_detail` / `_build_system_prompt` | `LocalFallbackPipeline.kt` + `WebDdlSpec.kt` | Match the system prompt, example selection, model output cleanup, and fallback control. |
| Stage 1 text cleanup | `interpreter.py` cleanup / usable DDL checks | `ServerDdlText.kt` | Compare DDL guard, number-noise repair, clause dedupe, and drawable vocabulary guard function by function. |
| Stage 1.5 expansion | `ddl_expander.py::expand_intermediate_ddl` | `WebDdlExpander.kt` | Track sensory/structural markers, filter candidates, density, and placement insertion with server updates. |
| Stage 2 model call | `composer.py::compose` / `_compose_*` | `LocalFallbackPipeline.kt` / provider clients | Compare prompt, tool schema, retry/fallback criteria, and timeout policy. |
| Stage 2 tool schema | `schema.py::Score` / `Instruction` / `composer.py` tool schema | `WebScoreTool.kt` | Match JSON schema, tool_calls unwrap, arguments unwrap, and renderable instruction guard. |
| Score primitive field coerce | `coerce.py::PRIMITIVE_SPECS` / `POST_COERCE` | `ServerScoreCoercer.kt` | Match primitive required fields, fallback fields, default values, and arc angle repair. |
| Score semantic coerce | `coerce.py` marker helpers | `ServerScoreSemantics.kt` | Align material, color, variation, presence, density, and motion marker sets and return values. |
| DDL coverage repair | `coerce.py::_ddl_clauses` / `_primitive_from_clause` / `_fallback_instruction_from_clause` | `ServerScoreRepairFactory.kt` | Match clause extraction, primitive selection, and coverage instruction defaults. `円` / `circle` follows server behavior and becomes `ellipse` in coverage repair. |
| Fallback Score synthesis | `api.py` fallback helpers / `coerce.py::_fallback_instruction_from_clause` | `ServerFallbackComposer.kt` | Match primitive, geometry, and arrangement defaults after provider failure or unusable Stage 2 output. |
| Repair order | `coerce.py::coerce_score` | `LocalFallbackPipeline.kt` | Compare visible color, dedupe, coverage, shape/color/motif/composition/context/motion/presence/density order and remove Android-only ordering. |
| SVG render engine | `render_engines/default.py` / `renderer.py::render` / `_render_instruction` | `DefaultSvgRenderer.kt` / `ServerRenderer*.kt` | Match instruction expansion, arrangement placement, material outlines, filters, and metadata. |
| Render hash / metadata | `api.py::_render_hash` / render metadata assembly | `LocalFallbackPipeline.kt::renderHash` / renderer metadata | Match hash input fields, build number handling, engine id/version, catalog/canvas metadata. |
| History persistence | `api.py::_add_history_item` / `db.py::add_history_item` | `InkuRepository.kt::saveResult` / Room entities | Store the same user-visible data: input, DDL, Score, SVG, metadata, model IDs, catalog/canvas, hash, and timestamps. |
| Headless / CLI benchmark | `inku-cli paint --save-history` | `HeadlessRenderActivity.kt` / `android/scripts/headless_*` | Let both server and Android save history, and keep history_id, DDL, hash, and catalog in summaries. |

Saijiki parity is checked category by category. Android UI word groups must
match `web/src/lib/saijiki.ts` and `web/src/lib/i18n/ja.ts`. Server Stage 1 is
checked against the saijiki list and allowed action verbs in `interpreter.py`.
The verb `draw` / `描く`, which is not exposed by the web UI, is not exposed as
an independent Android word either; it is handled only when it appears in DDL or
model output. Score coercion, fallback, and repair map `katachi` to primitives,
`tezawari` to weights, `tsuranari` to styles, `iro` to visible colors,
`yuragi` to variation, `basho` to center/position, `ugoki` to arrangement,
`katamuki` to rotation/line endpoints, and `wariai` to size, arc angle, and line
span. Even when LLM output is incomplete or variable, saijiki words in the
post-Stage-1.5 DDL are repaired through `ServerScoreCoercer.kt`,
`ServerScoreSemantics.kt`, `ServerFallbackComposer.kt`, and
`ServerScoreRepairFactory.kt` so Android behavior tracks server `composer.py`
and `coerce.py`.

## Web Component Porting Matrix

All web components under `web/src/lib/components/` are considered for the
Android port. The Android implementation may use mobile-native layout, but the
button action, state transition, and persistence target must match the web
component unless marked as a local single-user equivalent.

| Web component | Android status |
| --- | --- |
| `AppRail.svelte` | Mapped to top header and bottom navigation. Settings and app state entry points remain visible. |
| `AuthPanel.svelte` | Local single-user equivalent. No login UI; the local user has admin-equivalent settings access. |
| `ProfileModal.svelte` | Local single-user equivalent. Account/password editing is intentionally not shown. |
| `InputPanel.svelte` | Ported to Compose mode tabs, prompt input, canvas/catalog/model buttons, clear/draw action, batch and demo panels. |
| `PaintButton.svelte` | Ported to primary draw buttons. |
| `StopButton.svelte` | Ported to active draw/batch/demo stop action backed by cancellable jobs. |
| `BatchPanel.svelte` | Ported as local batch text execution, progress message, selected latest result, Room history save. |
| `DemoPanel.svelte` | Ported as one-shot local demo generation with persisted local settings planned for interval loop parity. |
| `CanvasAspectPlugin.svelte` | Ported as the Canvas settings panel and plugin enable flag persisted to Room settings. |
| `ColorCatalogModal.svelte` | Ported as the color catalog selection panel with cancel/confirm semantics. |
| `DdlEditor.svelte` / `DdlEditPanel.svelte` | Ported as inline DDL editor, editor dialog, auto-repair toggle, Stage 2 replay, and stop action. |
| `SaijikiInline.svelte` | Ported as the inline Saijiki panel using the same word groups. |
| `SaijikiDrawer.svelte` | Mobile equivalent is the inline Saijiki panel; drawer layout is not used on Android. |
| `CanvasPanel.svelte` | Ported for artwork/prompt/score tabs, star, hash copy, render metadata, zoom/pan controls, SVG share, and PNG share. |
| `OutputTabsContent.svelte` | Ported as prompt and JSON views from the saved Room history item. |
| `HistoryStrip.svelte` | Ported through the history tab and selected render controls. |
| `HistoryManager.svelte` | Ported for thumbnails/list modes, search, starred filter, selection, trash, restore, and permanent delete. |
| `HistoryThumbnail.svelte` | Ported through `ArtworkPreview` in history tiles and list rows. |
| `ConfirmDialog.svelte` | Ported for DDL overwrite and destructive history operations. Non-history destructive settings confirmations remain in the parity test backlog. |
| `SettingsModal.svelte` | Ported for model selection, model connection settings, plugin setting, DB status, export templates, and misc settings. Server-only logs/output-save are represented as local-only equivalents. |
| `KiwiMascot.svelte` | Represented by persisted visibility setting; the Android progress indicator uses native Material progress. |

## Implementation Order

Completed or substantially implemented:

1. Project skeleton, Room schema, and compatibility data models.
2. Local settings, model download state placeholders, and provider abstraction.
3. Kotlin renderer port for the current SVG primitive subset.
4. Stage 1 / Stage 1.5 / Stage 2 pipeline shape with deterministic fallback.
5. Compose UI for single drawing, batch, demo, history, settings shell, render
   previews, prompt view, and JSON view.

Remaining next order:

1. Verify LiteRT-LM inference end to end on Pixel 9 with the downloaded Gemma 4
   E2B/E4B `.litertlm` model files and expose provider failures in the UI/log
   surface instead of silently falling back.
2. Harden model download UX with a foreground service or WorkManager,
   notifications, metered-network policy, and user-visible storage recovery.
3. Expand the Kotlin renderer and JSON Score parser to cover the full web
   primitive and style surface.
4. Extend export compatibility from current single-item share export to full
   history import/export flows with Android Storage Access Framework.
5. Add automated compatibility tests against reference web JSON and SVG/render
   metadata fixtures.
6. Complete destructive confirmations for every non-history settings operation
   and add automated parity coverage for the Android UI state transitions.

## Local Commit Record

- `f34852b feat: add android headless render comparison`
  - Added the Android headless render entry point and adb-driven comparison
    script.
  - Added OpenAI-compatible provider routing, encrypted local provider API key
    storage, and web-compatible Stage 1 / Stage 1.5 / Stage 2 prompt and tool
    support.
  - Added Android-side tests for the web DDL expander port.
  - Updated the Pixel 9 UI, model/provider selection, batch/history/settings
    flows, and renderer support as part of the same Android parity checkpoint.
  - Verified with `gradle :app:compileDebugKotlin` and
    `bash -n android/scripts/headless_render_compare.sh`.

The commit intentionally excludes local-only artifacts, concrete device IDs,
local server addresses, downloaded models, and API keys. Unrelated `manual/`
files were left untracked.

## Build And Deployment Notes

Known working debug build command from the repository workspace:

```sh
cd android
GRADLE_USER_HOME=/tmp/inku-gradle-home JAVA_HOME=/Applications/Android\ Studio.app/Contents/jbr/Contents/Home gradle :app:assembleDebug
```

USB deployment commands use the target device serial from the local environment.
Do not commit concrete local device IDs:

```sh
adb -s "$ANDROID_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s "$ANDROID_SERIAL" shell am force-stop app.inku.mobile
adb -s "$ANDROID_SERIAL" shell am start -n app.inku.mobile/.MainActivity
```

Room uses WAL. When inspecting the database from the connected debug device,
pull the main database and WAL files together:

```sh
adb -s "$ANDROID_SERIAL" exec-out run-as app.inku.mobile cat databases/inku.sqlite > /tmp/inku-android.sqlite
adb -s "$ANDROID_SERIAL" exec-out run-as app.inku.mobile cat databases/inku.sqlite-wal > /tmp/inku-android.sqlite-wal
adb -s "$ANDROID_SERIAL" exec-out run-as app.inku.mobile cat databases/inku.sqlite-shm > /tmp/inku-android.sqlite-shm
```
