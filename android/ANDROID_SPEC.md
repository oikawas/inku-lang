# inku Android Implementation Notes

This directory is the Android workspace for the native standalone app and is
tracked by Git. Local-only artifacts, device IDs, downloaded models, logs, and
secrets must remain outside tracked files.

Last updated: 2026-07-23.

**Catch-up status**: Android sits at generation `1.48.0-android.1` with render engine
version `2`. The master web/server implementation is at v2.4.2 with engine 10. The port
proceeds in phases; see "2026-07-23 Catching Up With web/server v2, Phase 1" at the end
of this document.

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
- Reference compatibility tests at the SVG and render-metadata level.
  **Score-level parity started on 2026-07-23** (`ServerScoreParityTest.kt` checks the 15
  cases in `server/tests/fixtures/stage2/` plus exact `dh1` / `rh2` values; see the final
  section).
- Catching up with the web/server v2 generation (renderer engine 2 → 10, variation,
  plugins, lineage, tenkei). Only Phase 1 (Score schema / coerce / hash) is complete.

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
| Output of `server/src/inku_server/composer.py::_score_tool_schema()` | `android/app/src/main/java/app/inku/mobile/pipeline/ServerScoreSchemaJson.kt` | The Stage 2 tool schema JSON itself: primitive / weight / style enums, `additionalProperties: false`, and the arrangement, `at`, `relation`, and `surface` definitions. **Server schema changes land here first.** |
| `server/src/inku_server/db.py::render_hash_for_item` / `identity.py::description_hash` | `renderHash` / `descriptionHash` / `canonicalSeed` in `android/app/src/main/java/app/inku/mobile/pipeline/LocalFallbackPipeline.kt` | The eight `rh2` payload fields and the canonical-JSON rules, the `dh1` normalization rules, and integer coercion of seeds |

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
| `HistoryStrip.svelte` | Android removes the unused bottom history strip and consolidates history access into the history-grid tab and selected render controls. |
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

## 2026-05-07 Server Parity Fix Record

Server CLI and Android CLI comparisons from the same DDL showed that DDL
normalization was broadly aligned, while JSON Score and SVG output still
diverged. The main causes were Android-side differences in the Stage 2 user
message, Score tool schema, coerce chain, renderer seed/hash behavior, and
Android-only support layers.

This update treats the server implementation as the master for Android logic
that is not hardware-dependent:

- Stage 2 user messages now match `server/src/inku_server/composer.py`
  `_build_user_message()`. DDL input mode sends only the DDL when the original
  text and normalized DDL are identical.
- Stage 2 tool schema no longer uses the Android-only simplified schema.
  Android now uses `ServerScoreSchemaJson`, generated from the server
  `_score_tool_schema()`.
- Stage 2 Score repair reconnects the server `coerce_score()` stage order:
  material hint, variation hint, DDL coverage, color delivery, shape delivery,
  complex motif, composition diversity, structural duplicate repair, context
  energy, presence auxiliary repair, density governor, motion energy, and
  density budgets.
- Material and variation hints now use the same markers and defaults as the
  server `_with_material_hint()` and `_with_variation_hint()`.
- Android-only repairs that were not present in the server were removed,
  including treating `震える` as an extra motion-context trigger and adding an
  automatic membrane-haze support layer.
- Arrangement expansion, scatter/path/clustered placement, `preserve_space`
  margins, density radius, cluster axis/bend/jitter, and renderer seeding were
  aligned with `server/src/inku_server/renderer.py`.
- Renderer seeds are derived from an `Instruction.model_dump_json()` equivalent
  field order and default/null representation. Line variation uses the same
  seed source.
- Variation and material jitter signed hashes now follow the server SHA-256
  plus little-endian signed 64-bit behavior.

Verification:

- `gradle :app:compileDebugKotlin` succeeded.
- `gradle :app:assembleDebug` succeeded.
- The debug APK was reinstalled on Pixel 9 and headless DDL render comparison
  was rerun.
- Final check run:
  `/tmp/inku-headless/history-ddl5-after-final-parity-fix-20260507/history-ddl5-final-002`
  - `same_ddl: true`
  - `same_render_hash: false`
  - Remaining differences were identified mainly as LLM Stage 2 output
    variation in `variation.dimensions` and `arrangement.density`.

Future comparisons should classify same-Score drawing differences as renderer
porting issues. If the Score differs, compare Stage 2 model response, tool
schema, and the coerce chain against the server source in that order.

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

## 2026-05-07 Pixel 9 UI / Canvas Interaction Update

The Android draw tab UI was updated based on the Claude Design DDL4 S1 Compose
reference. As a mobile UI rule, horizontal scrolling is prohibited; choices,
chips, and menus must use wrapping rows or vertical layout instead.

UI requirements from this update:

- The draw tab prioritizes the S1 Compose writing flow: canvas, condition
  chips, prompt input, and normalized DDL should be easy to inspect in order.
- Controls and menus must not be overlaid on top of the artwork preview.
  - Star, render hash, and zoom controls are placed above the image.
  - Artwork / Prompt / JSON / SVG / PNG controls are placed below the image.
  - SVG / PNG expanded choices are shown inline below the image, not as
    popups covering the artwork.
- Tapping the image itself has no action.
- The image gesture surface is used only for pinch zoom and panning while
  zoomed.
- Existing buttons for tabs, settings, history, saijiki, model selection,
  color catalog selection, and related flows must always be wired to a
  transition or real action. Visual-only buttons are not acceptable.
- Japanese IME behavior must remain supported: input fields should keep the
  bring-into-view and IME padding behavior so focused fields are not hidden by
  the keyboard.

SVG / PNG sharing behavior:

- SVG / PNG / JSON sharing must not run heavy file generation on the main
  thread.
- PNG generation rasterizes SVG and encodes PNG on a background dispatcher,
  then opens the Android share sheet after completion.
- SVG export exposes profile choices with the same intent as the server/web
  implementation:
  - display SVG
  - editable SVG
  - compatible SVG
- PNG export exposes at least the server/web template Y-axis sizes:
  - 1080px
  - 2160px
  - 4320px
- Android uses the system share sheet instead of a browser download, but the
  user-facing SVG / PNG menu role should match the web version.

Verification:

- `gradle :app:compileDebugKotlin` succeeded.
- `gradle :app:assembleDebug` succeeded.
- The debug APK was installed and launched on Pixel 9.
- Screenshots confirmed that controls and menus are not overlaid on top of the
  artwork.
- PNG 1080px export opened the Android share sheet.
- logcat after PNG export did not show `FATAL EXCEPTION`, `ANR in`, or
  `Input dispatching timed out`.

## 2026-05-07 Explicit Android History Differences From Server/Web

The Android app remains a native single-user Pixel 9+ application whose
development master is the server/web implementation. However, management flows
that are unnecessary or too heavy for the mobile UI are intentionally removed
when specified here.

For the History screen, the following are explicit Android differences from the
server/web implementation:

- The trash feature is not exposed in the Android UI.
  - The History screen does not provide a Trash view switch.
  - It does not provide a button to move history entries to Trash.
  - It does not provide a restore-from-Trash button.
  - It does not provide a permanent-delete button.
  - It does not show confirmation dialogs for trash operations.
- The list layout is not exposed in the Android UI.
  - History uses the S4 History-style three-column thumbnail grid as the
    default and only layout.
  - The thumbnail/list layout toggle is not shown.
- Multi-select actions whose purpose was trash management are not exposed in
  the Android UI.
  - The select-all button is not shown.
  - History cards do not show checkboxes.
- The remaining History screen actions are limited to search, starred-only
  filtering, selecting a history item, Star / unstar for the selected item, and
  JSON sharing.

These removals are intentional Android-specific product differences, not
unfinished implementation gaps.

## 2026-05-07 LiteRT-LM MTP And Gemma 4 Re-Download Flow

The Android LiteRT-LM integration requires the GPU backend. It must not fall
back to CPU. For local Gemma 4 E2B / E4B execution, LiteRT-LM speculative
decoding / Multi-Token Prediction (MTP) is enabled.

Implementation requirements:

- Set `ExperimentalFlags.enableSpeculativeDecoding = true` before initializing
  the LiteRT-LM Engine.
- Keep the backend as `Backend.GPU()`.
- If GPU initialization fails, stop drawing and surface the error to the user.
- Do not add CPU fallback.
- Engine initialization logs should make it possible to confirm the GPU backend
  and speculative decoding state.

Gemma 4 model download UI:

- The LiteRT-LM / Gemma E2B / E4B panel in Model Settings provides a
  `Re-download` action in addition to the existing license acceptance and
  download flow.
- `Re-download` deletes the finished `.litertlm` file and any interrupted
  `.part` file from the device, then downloads from the same Hugging Face URL
  from the beginning.
- Models whose license has not been accepted cannot be re-downloaded.
- Re-download is disabled while the model is queued, connecting, downloading,
  or verifying.
- Re-download progress uses the same Room `model_assets` state as normal
  downloads.

Model file handling:

- Gemma 4 LiteRT-LM files downloaded before 2026-05-05 may predate MTP support,
  so users must be able to refresh them with the `Re-download` action.
- As of 2026-05-07, the Hugging Face `x-linked-etag` values for E2B and E4B
  match the SHA-256 values stored by the Android implementation.
- Therefore the current policy keeps the same download URLs and SHA-256 values,
  and refreshes old on-device files by deleting and downloading them again from
  the same URLs.

Verification:

- `gradle :app:compileDebugKotlin` succeeded.
- `gradle :app:assembleDebug` succeeded.
- The debug APK was installed and launched on Pixel 9.

## 2026-05-08 Android-Specific Swipe History In Compose Preview

As an explicit Android difference from the server/web implementation, the
Compose screen lets users switch the currently displayed history item by
swiping directly on the rendered image.

- Swiping right on the rendered image moves one history item backward.
- Swiping left on the rendered image moves one history item forward.
- Tapping the image remains a no-op.
- Pinch-in / pinch-out zoom and panning while zoomed remain supported.
- While zoomed, image manipulation takes priority over history swiping.
- In normal view, history swipes are active only inside the displayed drawing
  image area.
- Short-term repeated history switching is throttled so one horizontal swipe
  does not jump across multiple history items.
- The ViewModel keeps the history summary list active from startup so swiping
  works immediately after the latest history item is restored at launch.

This gesture is an Android-specific mobile usability addition and is not a
server/web parity requirement.

Verification:

- `gradle :app:compileDebugKotlin` succeeded.
- `gradle :app:assembleDebug` succeeded.
- The debug APK was installed on Pixel 9, and left / right swipes on the
  Compose preview image were verified to switch history items.

## 2026-05-08 Android-Specific Unified Model Selection

The Android model-selection UI prioritizes mobile simplicity. It exposes a
single drawing-model choice instead of separate Stage 1 and Stage 2 selectors.

- The Compose model-selection dialog and Settings model-selection panel show
  one drawing-model selector, not separate Stage 1 / Stage 2 selectors.
- The Compose model-selection dialog prioritizes fast mobile selection and does
  not show explanatory text about preserving server/web-compatible metadata.
- The Compose model-selection dialog should stay compact, containing only the
  provider selector, model list, OK, and cancel controls required for the
  unified selection flow.
- When the user selects a model, Android writes the same model id to both
  `selectedModelId` and `selectedStage2ModelId`.
- Persisted settings keep the existing `model_selection.stage1_model` and
  `model_selection.stage2_model` fields so future per-stage options can be
  reintroduced without changing the storage shape.
- History DB records, JSON display, JSON export, and render metadata continue
  to include server/web-compatible `stage1_model` and `stage2_model` fields.
- Repository and pipeline calls continue to receive `stage1ModelId` and
  `stage2ModelId`; Android passes the unified UI selection to both arguments.
- If old settings contain different Stage 1 and Stage 2 values, Android
  normalizes the UI selection on restore by preferring the Stage 1 value.

This is an Android UI-specific difference. It does not change the
server-compatible storage format or history metadata.

## 2026-05-08 Android-Specific Presentation View

On Android, double-tapping the drawing image opens a presentation view.

- Presentation view hides the app UI around the drawing and expands the image
  area to the full screen.
- The drawing is centered, and its scale is automatically chosen as the largest
  size that still keeps the entire image visible.
- Android determines the displayed drawing's real aspect ratio from the SVG
  `viewBox`, or from SVG `width` / `height` when no viewBox is available.
  Only when SVG dimensions cannot be read does Android fall back to the saved
  history `canvas_aspect` resolved through `CanvasAspects`.
- Landscape canvases are rotated 90 or 270 degrees on Pixel 9 portrait screens
  so the artwork's long edge always aligns with the screen's long edge.
- While presentation view is active, Android detects the device's physical
  up/down orientation and dynamically adjusts the artwork's visual up direction
  to match. For landscape artwork, long-edge alignment takes precedence, so the
  rendered rotation remains either 90 or 270 degrees.
- The presentation-view margin background follows the displayed SVG's
  background `rect fill`, treating that fill as the drawing's dominant
  background color.
- If the drawing background is white-ish, the margin background switches to the
  Android dark-mode background.
- If the drawing background is black-ish, the margin background switches to the
  Android light-mode background.
- For non-white and non-black drawing backgrounds, Android classifies the
  extracted drawing background by luminance.
- Non-white/non-black light backgrounds use the Android dark-mode background as
  the margin color, and dark backgrounds use the Android light-mode background.
- While presentation view is active, pinch and pan transforms are disabled.
  Double-tapping returns to the normal view.
- In presentation view, double-tap and left/right swipes are active across the
  whole presentation surface, including margins outside the displayed artwork.
- Presentation-view left/right swipes are interpreted relative to the current
  physical device orientation. Even though `MainActivity` remains portrait
  locked, holding the device sideways or upside down changes which screen-axis
  movement counts as device-relative left or right.
- In presentation view, a right swipe advances one history item and a left
  swipe moves back one item. This intentionally reverses the normal image-area
  swipe mapping to favor fullscreen viewing/page-turn behavior on Android.
- Matching the server/web `CanvasPanel.svelte` presentation controls, Android
  shows a control strip at the bottom of presentation view. The strip provides
  the same user-facing roles: move one history item backward, jump to the latest
  history item, move one history item forward, show current position / total
  count, star / unstar, toggle instruction captions, and close presentation
  view.
- Instruction captions use the displayed history item's original user input,
  not the internally expanded Stage 1 prompt. Captions are overlaid near the
  lower part of the presentation surface with horizontal margins.
- The caption toggle is disabled when there is no original instruction text to
  display.
- Normal pinch zoom, pan, and left/right history swipes remain available outside
  presentation view.

This is an Android-only mobile viewing behavior. It does not change history DB
records, SVG/PNG export output, or render metadata.

## 2026-05-08 Render Metadata Canvas Ratio

As a shared server/android metadata change, render metadata now includes
`render_canvas_aspect_id` and `render_canvas_aspect_ratio` in addition to the
existing `render_canvas_aspect` field.

- `render_canvas_aspect` remains for compatibility.
- `render_canvas_aspect_id` is the explicit canvas aspect identifier and is
  included in new Android render metadata, JSON display, and headless results.
- `render_canvas_aspect_ratio` is the actual rendered canvas width/height ratio,
  such as `square=1.0`, `oban=0.666666...`, and `wide=2.35`.
- Android render-hash calculation includes `render_canvas_aspect_id` and
  `render_canvas_aspect_ratio`, matching the server metadata contract.
- For old Android history entries without the new fields, the UI derives them
  from the saved `canvas_aspect` / `render_canvas_aspect` value.

Ratio source:

- On the server, `render_canvas_aspect_ratio` is calculated from `ratio_w` /
  `ratio_h` in the system `canvas_aspect` plugin definition.
- On Android, the migrated `CanvasAspects` table is the only source for canvas
  ratio values, and the ratio is calculated as `ratioW / ratioH` for the same
  aspect identifier.
- JSON display, history records, headless results, and render hashes must use
  the definition value that corresponds to the selected
  `render_canvas_aspect_id`.
- If old history records or external inputs do not contain the ratio value,
  Android derives it from the saved identifier using the same definition table.
- Android must not append independent canvas ratio values that are not present
  in the server plugin definition.

## 2026-05-08 Canvas Selection Entry Point In The Drawing Panel

On Android, the drawing panel exposes canvas selection from the zoom-control row
above the image preview.

- The canvas button is placed immediately to the right of the zoom-percentage
  display.
- The button label uses the selected canvas name and shortens long names so the
  drawing panel remains usable on Pixel 9 width.
- Pressing the button opens the canvas-size selection dialog.
- Selecting a canvas saves the setting and closes the dialog.
- This entry point is available from both Compose and Batch drawing panels and
  updates the `canvas_aspect` setting.
- Server/web has no standalone Canvas settings tab. Canvas aspect selection is
  performed from the input panel `CanvasAspectPlugin`.
- Android removes `Settings > Canvas` and consolidates canvas selection into
  drawing / writing screen buttons that open the shared selection dialog.
- The server/web plugin enable/disable setting is a server operations and plugin
  management feature and is not migrated to the single-user Android app.

## 2026-05-09 Color Catalog Selection Entry Point

Android aligns color catalog selection with the server/web `InputPanel` and
`ColorCatalogModal` flow by opening a shared dialog from the writing / drawing
screen buttons instead of the Settings menu.

- Server/web has no standalone Color Catalog settings tab.
- Android removes `Settings > Color Catalog`.
- The color catalog selection dialog remains available from the writing /
  drawing screen color catalog button.
- `color_catalog` persistence, history DB records, render metadata, JSON
  display, and render hash behavior are unchanged.
- The setting that controls whether history selection applies the history color
  catalog remains under Display settings, matching the server/web behavior.

## 2026-05-08 Model Settings Provider UI

The Android model settings panel follows the server/web model-provider settings
shape by rendering each service as an independent provider panel.

- English section headings such as `AI SERVICE CONNECTIONS` are not shown.
- Each provider panel shows `変更` on the right side of the panel title. It opens
  the service-name edit dialog. The body does not repeat a `サービス名` label or
  duplicate value.
- Connection type is selected from a dropdown. Android uses the server
  `openai_compatible`, `anthropic`, and `gemini` kinds and adds the
  Android-specific `litert-lm` kind.
- `Base URL` is shown as a read-only row with an adjacent `編集` button that
  opens a URL edit dialog.
- `APIキー` follows the server/web state transition: when a key is already set,
  Android does not show the stored key and exposes a single `削除` button; when
  no key is set, the same action slot becomes `追加` and opens the new-key dialog.
- The panel shows the models published to the user and provides a `モデル選択`
  button that opens the model picker.
- The model picker follows the server/web flow with model-list fetch, select all,
  clear all, search, checkbox model rows, and save / cancel actions.
- The model-list fetch button retrieves the latest model list from the selected
  provider service and reflects it in the publishable model candidates.
- Fetch-in-progress and fetch-result status is shown at the bottom of the model
  picker dialog.
- The model search field requests an ASCII-oriented keyboard because model ids
  are generally searched in Latin characters.
- After fetching a model list, Android follows the server/web selection rule:
  only models that existed before the fetch and were already selected remain
  selected; newly fetched candidates are not auto-selected.
- Fetched model candidates are stored separately from the models published to
  the user. The drawing model picker shows only saved published models and must
  not include unselected fetched candidates.
- If an old Android build stored the initial candidate list as published models,
  startup normalization removes that migration artifact only when the saved list
  exactly matches a known legacy default candidate list.
- The bottom row of each provider panel contains `サービス削除` and `保存`.
- Because Android is single-user, published models from this panel are reflected
  directly in the drawing model choices available to that user.
- The LiteRT-LM download-cancel button is not shown in the model settings panel.

## 2026-05-08 Demo Panel S3 Layout And Random Color Catalog

The Android Demo panel follows the DDL4 `S3 — Demo` layout for the content below
the image preview: status, generated prompt, seed phrase, demo settings, and
start / stop action.

- Header elements above the image preview, such as the S3 `inku` label, are not
  migrated because Android keeps its existing navigation structure.
- After demo start, Android runs the same conceptual loop as the server/web
  client: generate instruction, render, wait for the configured interval, and
  repeat.
- The model used for demo instruction generation follows Android's main model
  selection. The Demo panel does not show a separate prompt-generation model
  settings area.
- Demo rendering keeps random color catalog selection always enabled as an
  Android-specific behavior. The Demo settings panel does not show a control for
  this option, and Android chooses a random color catalog immediately before
  each `repository.paint` call.
- The interval row is displayed in `-`, `xx sec`, `+` order.
- Double-tapping the image enters presentation mode. Demo rendering continues in
  presentation mode, and the bottom-right corner shows the remaining display
  time for the current image.
- LLM status text says `指示文生成/Stage1/2共通` to show that Android's single
  model selection is shared by instruction generation, Stage 1, and Stage 2.
- Even if an older `demo_random_color_catalog` setting exists, Android restores
  Demo random color catalog behavior as always enabled.
- The seed phrase and interval are also saved as demo settings and restored on
  restart.
- Demo renders continue to use the existing Android behavior of saving to normal
  history, with a `[demo] ` prefix in the saved input.

## 2026-05-08 Drawing Panel SVG / PNG Export Menus

The Android drawing panel follows the server/web `CanvasPanel` export behavior
by making the `SVG` and `PNG` controls menu buttons rather than direct actions.

- The SVG button is labeled `SVG ▾` and opens a menu.
- The SVG menu contains `表示用SVG`, `編集用SVG`, and `汎用SVG`.
- `表示用SVG` exports through the Android share sheet with `svg_profile=display`.
- `編集用SVG` exports with `svg_profile=editable` and includes metadata and ids
  for vector editing.
- `汎用SVG` exports with `svg_profile=compat`.
- The SVG menu includes a help entry, matching the server/web intent of making
  each SVG format's purpose visible.
- The PNG button is labeled `PNG ▾` and opens a menu.
- The PNG menu is populated from Room `export_templates` instead of hard-coded
  size rows.
- The default templates match server/web: `PNG 1080px`, `PNG 2160px`, and
  `PNG 4320px`.
- Each PNG menu row shows the template name and description. The selected
  template's `height_px` is used as the PNG output Y-axis pixel size.
- Selecting an SVG or PNG item opens the Android share sheet. History DB,
  render metadata, and render hash are unchanged.
- The older Android UI that expanded export choices as horizontally arranged
  chips is no longer used.
- `Settings > Output Files` is removed because server/web has no equivalent
  user-facing settings tab and Android does not maintain separate file-save
  settings for it.
- SVG / PNG / JSON sharing remains available from the drawing panel menus. PNG
  background and PNG template management are consolidated under
  `Settings > Export`.
- The server/web `server_misc` output auto-save setting is a server operations
  feature and is not migrated to the single-user Android app.

## 2026-05-09 Android Version / Build Management

The Android app has Android-specific version and build metadata that is
separate from the web/server `web/BUILD_NUMBER`.

- `android/VERSION` is the source of truth for Android `versionName`.
- `android/BUILD_NUMBER` is the source of truth for Android `versionCode` and
  the in-app build number. It is managed as a monotonically increasing integer.
- `android/app/build.gradle.kts` reads both files instead of hard-coding
  `versionName` or `versionCode`.
- The initial v1.48-generation Android values are
  `versionName=1.48.0-android.1` and `versionCode=148001`.
- Every `assemble*`, `bundle*`, or `install*` Android app build task increments
  `android/BUILD_NUMBER` by 1 during Gradle configuration. The incremented
  value is used by that same build as both `versionCode` and
  `BuildConfig.BUILD_NUMBER`.
- Compile-only verification tasks such as `compileDebugKotlin` do not increment
  `android/BUILD_NUMBER`.
- Update `android/VERSION` when Android follows a new server/spec generation or
  when DB schema, history JSON, render metadata, or export compatibility
  changes.
- The Settings menu includes a Version Information panel showing
  `versionName`, `versionCode`, build number, build type, application id,
  source spec, and render engine version.
- Version/build metadata must not contain API keys, device IDs, local server
  details, or personal environment paths.

## 2026-05-09 Model Settings Panel Cleanup

The Android Model Settings panel now treats connection kind as a creation-time
service property.

- Existing service panels no longer show or edit `接続形式`.
- Existing service kind remains stored as `provider.kind` and is preserved when
  saving service name, Base URL, API key, or published models.
- The per-service `保存` button is removed because it only saved connection
  kind changes.
- The service-add button is shown at the end of the provider list. Its dialog
  collects service id, service name, connection kind, Base URL, and API key.
- `有効` / `無効` status text is removed from provider panels because it only
  reflected DB `isEnabled`, not a live connection check.
- The `サービス削除` button is compact and right-aligned at the bottom of each
  provider panel.

## 2026-05-09 Mobile Vocabulary Editing UI For DDL Dialog

The Android DDL edit dialog has a mobile-specific vocabulary editing UI so that
users can edit DDL directly while referencing saijiki terms on a limited screen.
This is an intentional Android difference from the server/web UI.

- Saijiki terms in the DDL body are shown as chip-like highlights with
  category-specific colors. The body remains dense and readable, with minimal
  padding and only slight corner rounding.
- The inline highlight color and candidate chip color use the same category
  color so terms in the body and vocabulary candidates are visually linked.
- Body taps do not rely on Android-side coordinate estimation. After Compose
  `BasicTextField` resolves the caret position, Android converts that caret to
  a vocabulary selection when it lands inside a saijiki term. This avoids offset
  drift caused by wrapping, IME, scrolling, or font-size changes.
- The selected term is shown explicitly above the body box and in the material
  bar, making it clear that tapping a candidate will replace that term.
- Candidate taps replace the selected range when a term is selected. If no term
  is selected, the candidate is inserted at the current caret position.
- When a term is selected, the candidate row prioritizes alternative terms from
  the same saijiki category. The selected term itself is excluded, and terms
  already present in the body follow without duplicates.
- When the material panel is opened, the selected term's category is moved to
  the top and labeled as alternative candidates.
- This UI affects only Android editing ergonomics. It must not change
  server/web-compatible DDL, Score, SVG, history persistence, or JSON metadata.

## 2026-05-09 Compose Auto-Repair State And IME Return Flow

The Android compose screen defines the following mobile-specific input-state
behavior.

- The `補正` button controls whether DDL auto-repair / Stage-1.5-style DDL
  expansion is allowed.
- New installs default `補正` to OFF.
- The `補正` state is saved in Room setting `ddl_auto_repair` and restored after
  app restart.
- When `補正` is OFF, Android does not run `expandIntermediateDdl()` after Stage
  1 or during DDL-to-render execution, so Android does not append additional
  phrases to the displayed DDL.
- When `補正` is ON, Android uses the server/web-compatible DDL expansion and
  repair path.
- The compose-screen `新規作成` action clears both the prompt and interpreted
  DDL, and resets `ddlEditedAfterGeneration` to false.
- When the IME opens, focused input fields retry `bringIntoView()` at multiple
  timings instead of relying on a single focus-time scroll. This keeps input
  areas visible after Japanese IME candidate rows or keyboard height changes.
- When drawing finishes, Android clears input focus, hides the IME, and scrolls
  the compose screen back to the image area.

## 2026-05-09 Pixel 9 Landscape Safe Canvas

As an Android-specific canvas option, Android adds
`pixel9_landscape_safe` for Pixel 9 landscape display.

- The measured Pixel 9 physical display is `1080 x 2424 px` in portrait,
  `2424 x 1080 px` in landscape, with density `420 dpi` and density scale
  `2.625`.
- The camera hole is centered at the portrait top edge and becomes a side-edge
  avoidance area in landscape. The measured display cutout is
  `Rect(485, 0 - 595, 173)` in portrait coordinates, so the landscape side
  intrusion is about `173 px`.
- To avoid the camera hole and rounded corners with comfortable room, this
  canvas assumes about `240 px` side margin on both landscape sides.
- The usable landscape area is `2424 - 240 * 2 = 1944 px` by `1080 px`, so the
  largest practical safe ratio is `1944:1080 = 1.8`.
- Android represents this as the simple `9:5` ratio:
  `id=pixel9_landscape_safe`, `label=Pixel 9 Landscape Safe`, `ratioW=9.0`,
  and `ratioH=5.0`.
- This is an Android-only display optimization and does not exist in the
  server/web canvas aspect plugin. History, JSON, render metadata, and render
  hashes still record it through the standard `render_canvas_aspect_id` and
  `render_canvas_aspect_ratio` fields.

## 2026-05-09 Demo Settings Panel

On Android, demo seed phrase editing is removed from the main Demo screen and
moved to `Settings > Demo Settings`.

- The main Demo screen focuses on the image, status, generated prompt,
  start/stop action, and display interval.
- `Settings > Demo Settings` allows editing the seed phrase and display
  interval.
- The seed phrase is saved in Room setting `demo_seed_phrase` and restored after
  app restart.
- After Demo starts, each render cycle sends the seed phrase to the currently
  selected main LLM and displays that response in the `生成された指示文` box.
- The LLM response shown in `生成された指示文` is used directly as the normal
  prompt for Stage 1 DDL generation, Stage 2 Score generation, and rendering.
- The older Android implementation that assembled demo prompts from fixed local
  templates is no longer used.
- Demo rendering always uses the Android-specific `pixel9_landscape_safe`
  canvas aspect and does not follow the canvas selected on the normal Compose
  screen.
- Demo rendering always picks a random color catalog for each render cycle and
  does not follow the color catalog selected on the normal Compose screen.
- The metadata shown at the bottom of the Demo screen displays the actual color
  catalog name used for that render cycle. When showing an existing history item
  after app startup, the display name is resolved from the color catalog ID saved
  in history.
- The `Canvas` metadata on the Demo screen shows the user-facing
  `CanvasAspects` label instead of the internal ID. `pixel9_landscape_safe` is
  displayed as `Pixel 9 Landscape Safe`.
- The default seed phrase is:

```text
世界の人と動物、自然と都市を主題として96文字の短文を作って。感情豊かに、季節や、人生と人のつながり、人生、世代、神。色々な観点から。
```

- A `デフォルト値に戻す` button restores the seed phrase to that default after
  editing.

## 2026-05-10 LiteRT-LM 0.11.0 Pinning And Performance Logs

The Android LiteRT-LM path manages its dependency version and runtime logs
explicitly to improve benchmark reproducibility and investigation quality.

- The LiteRT-LM Android dependency must not use `latest.release`; it is pinned
  to `com.google.ai.edge.litertlm:litertlm-android:0.11.0`.
- Stage 1 / Stage 2 system prompts are not concatenated into the user prompt.
  They are passed through LiteRT-LM `ConversationConfig(systemInstruction=...)`.
- `Conversation.sendMessageAsync()` receives only the stage user prompt. This
  avoids duplicate prompt wrapping and follows the LiteRT-LM conversation API.
- The existing policy remains unchanged: GPU backend is required, CPU fallback
  is not allowed, and speculative decoding / MTP is enabled.
- The LiteRT-LM provider emits the following `InkuPerf` log events:
  - `litert_request_start`: `model_id`, `prompt_chars`, `system_chars`,
    `max_tokens`, and `engine_max_tokens`
  - `litert_engine_init`: `model_id`, `backend`, `speculative_decoding`,
    `engine_init_ms`, and `max_tokens`
  - `litert_request_done`: `model_id`, `elapsed_ms`, and `output_chars`
- The pipeline emits the following `InkuPerf` log events:
  - `paint_start` / `paint_done`: selected models, prompt length, catalog,
    canvas, total elapsed time, and render hash
  - `stage1_start` / `stage1_done` / `stage1_failed`
  - `stage2_start` / `stage2_done` / `stage2_failed`
  - `stage2_invalid`: why the first Stage 2 output was retried, response
    length, whether `instructions` existed, and a short preview
  - `render_start` / `render_done`
- LiteRT-LM Stage 2 system prompts explicitly forbid whitespace inside JSON
  numbers because Gemma can emit malformed values such as `0. 0`, `0. 01`,
  or `50 0`.
- Stage 2 JSON ingestion tries strict parsing, JSON object substring parsing,
  and parsing after LiteRT-LM numeric-whitespace repair. If `org.json` accepts
  malformed numbers as strings, keys and string values are trimmed, only
  number-like strings are normalized back to `Int` / `Long` / `Double`, and
  whitespace/newline corruption inside keys is normalized to schema-compatible
  snake_case.
- These logs are for performance investigation only. They must not change the
  server/web-compatible history JSON, Score, SVG, or render metadata formats.
- `engine_init_ms`, `stage1_ms`, `stage2_ms`, `render_ms`, `model_id`, and
  `prompt_chars` are collected from adb logcat and may be saved under
  `no-git-sync/perf-logs/` when needed. Performance logs under `no-git-sync`
  are not tracked by git.

As of 2026-05-10, Pixel 9 device measurements with the same prompt,
`ink_season`, `pixel9_landscape_safe`, GPU backend, and MTP enabled show:

- E2B: `engine_init_ms=6741`, `stage1_ms=18422`, `stage2_ms=89507`,
  `render_ms=13`, total `107956ms`. Stage 2 retried.
- E4B: the first run, `perf-litert-e4b-003`, exited during Stage 1 engine
  initialization. The rerun, `perf-litert-e4b-004`, completed with
  `engine_init_ms=12011`, `stage1_ms=29937`, `stage2_ms=41931`,
  `render_ms=47`, total `71933ms`. Stage 2 retried.
- `ConversationConfig(systemInstruction=...)` reduces user-side `prompt_chars`
  to about 31 for Stage 1 and 132 for Stage 2, but the system prompt is still
  passed separately. Total latency therefore remains strongly affected by model
  output length and retry behavior.
- With Stage 1 prompt optimization enabled, E2B, and the same prompt,
  `perf-litert-e2b-opt-002` produced malformed Stage 2 JSON on the first pass:
  numeric whitespace such as `0. 0`, `0. 01`, and `50 0` caused
  `stage2_invalid reason=json_extract_failed` and triggered retry.
- After adding the numeric-whitespace prohibition to the prompt and the JSON
  ingestion repair path, the same condition in `perf-litert-e2b-opt-004`
  completed without retry: `engine_init_ms=3644`, `stage1_ms=10223`,
  `stage2_ms=28124`, total `38466ms`, render hash short `DCB9`.
- The same prompt was also run through server-side `inku-cli paint` with
  `nvidia:google/gemma-4-31b-it`, `ink_season`, and server-supported canvas
  `wide` as `server-stage2-retry-001`. The server result had
  `compose_retry_count=0`, `compose_retry_reasons=[]`,
  `compose_fallback_used=false`, `elapsed_stage2_ms=26060`, and
  `tokens_out_stage2=351`; no server-side Stage 2 retry occurred.
- Therefore the observed retry is treated as a localized Android LiteRT-LM /
  Gemma E2B free-text JSON output issue, not a shared server Stage 2 contract
  issue. The repair remains in the provider-independent Score ingestion layer
  so it also protects against equivalent malformed JSON from other providers.

## 2026-05-10 LiteRT-LM Stage 1 Prompt Optimization Option

As an Android-specific feature, the `Settings > Model Settings > LiteRT-LM`
panel provides a `プロンプト最適化` checkbox.

- The setting is saved in Room `app_settings` as
  `litert_stage1_prompt_optimization` and restored after app restart.
- The default is OFF.
- Even when enabled, it applies only when the Stage 1 model starts with
  `local-litert-lm:`. It must not affect non-local providers such as OpenAI,
  Claude, Gemini, NVIDIA, Ollama, or OVMS.
- When enabled, Stage 1 uses a LiteRT-LM-specific compressed system prompt
  instead of the large web/server Stage 1 prompt, passed through
  `ConversationConfig(systemInstruction=...)`.
- The compressed Stage 1 prompt keeps the following contract:
  - output only normalized DDL text
  - preserve Saijiki vocabulary, attribute retention, concrete counts,
    explicit placement, random-word prohibition, no forced true circles for
    dots/particles/stars/rain/snow/sand/petals, no concrete human/face/animal
    rendering, background contrast preservation, and gray-background
    prohibition
  - include only a small number of Stage 1 examples selected for the input to
    reduce prompt size
- DDL, Score, SVG, history JSON, and render metadata persistence formats are
  unchanged.
- Headless rendering also reads this setting. If the CLI/ADB extra
  `litert_stage1_prompt_optimization` is provided, that value takes precedence.
- Unit tests verify that the compressed prompt is substantially shorter than
  the normal Stage 1 prompt and that key fixture example outputs remain
  aligned.

## 2026-05-10 Prompt Tab Display And LiteRT-LM Compressed Prompts

The `Prompt` tab in the draw screen and history screen generally follows the
server/web `/api/prompts` display behavior.

- For non-LiteRT-LM renders, Android does not persist the exact system prompt
  string used at render time in the history DB. At display time, it reconstructs
  the current normal Android Stage 1 / Stage 2 system prompts.
- This normal display path does not branch the Stage 2 prompt by history model
  kind and does not reselect Stage 1 examples from the input text. Like the
  server/web `OutputTabsContent`, it displays the normal Stage 1 input, Stage 1
  system, Stage 2 input, and Stage 2 system sections.
- As an Android-specific behavior, a history item whose `stage1_model` or
  `stage2_model` starts with `local-litert-lm:` is treated as a LiteRT-LM
  render, and the `Prompt` tab displays LiteRT-LM prompts.
- For LiteRT-LM renders, the Stage 2 system prompt always displays the
  LiteRT-LM-specific compressed Stage 2 prompt.
- For LiteRT-LM renders, the Stage 1 system prompt reflects the current
  `litert_stage1_prompt_optimization` setting at display time. If enabled, the
  LiteRT-LM-specific compressed Stage 1 prompt is displayed; if disabled, the
  normal Stage 1 system prompt is displayed.
- This is an Android-specific display difference only. It must not change DDL,
  Score, SVG, history JSON, render metadata, or render hash persistence formats.

## 2026-05-10 Stability And Security Hardening

The Android app implements the following stability and local-data protection
rules.

- `HeadlessRenderActivity` remains externally launchable in debug builds because
  Android development and external verification require it. In release builds,
  a manifest placeholder sets it to `exported=false`, so normal distribution
  builds cannot be launched by other apps.
- Debug builds keep `HeadlessRenderActivity` externally launchable, but the
  activity does not proceed to rendering unless the caller passes the debug-only
  random token stored in app-internal `files/headless-auth-token` as either the
  `auth_token` or `headless_auth_token` extra.
- `app.inku.mobile.permission.HEADLESS_RENDER` is declared as a signature
  permission for `HeadlessRenderActivity`. Release builds attach this
  permission to the activity.
- Headless `run_id` accepts only `[A-Za-z0-9._-]{1,80}` and the canonical output
  path must remain under `files/headless/<run_id>`.
- Headless `text_file` must not read arbitrary filesystem paths. Input may be
  passed directly through the `text` extra, or by using
  `app:headless-inputs/<file>` to read only from the app-internal dedicated
  input directory.
- Headless input is limited to 250,000 characters. `text_file` input is read
  with an explicit limit instead of using unbounded `readText()`.
- Headless artifacts remain under `files/headless`. At launch, old runs are
  pruned to at most 50 run directories and at most 7 days of retention.
- App backup is disabled. The database, history, provider settings, encrypted
  API keys, local model state, and headless outputs are excluded from cloud
  backup and device transfer.
- Remote provider Base URLs must use HTTPS, except for device-local loopback
  HTTP (`localhost`, `127.0.0.1`, or `::1`). This preserves local Ollama / OVMS
  verification while preventing plaintext prompt/API-key transmission to LAN or
  external HTTP endpoints. This validation is performed both when saving a
  provider setting and when opening a request.
- Remote provider HTTP error bodies are redacted before display. Bearer tokens,
  NVIDIA API keys, OpenAI keys, Google API keys, and values that look like
  `api_key`, `authorization`, or `token` are hidden.
- Remote provider HTTP response bodies are not read without limit. Successful
  responses are capped at 2,000,000 characters; error responses are capped at
  16,384 characters and are truncated for display. `HttpURLConnection` is always
  disconnected in `finally`.
- Headless results and remote-provider error display share redaction for API
  keys, Bearer tokens, and internal device data paths.
- The LiteRT-LM provider exposes an explicit `close()` and closes the cached
  Engine when the ViewModel is destroyed and after headless rendering finishes.
  ViewModel destruction must not block the UI thread with `runBlocking`; close
  runs on the Application-scope IO coroutine.
- Draw, DDL render, batch, and demo jobs carry a run id so stale completion or
  failure callbacks from older jobs cannot overwrite the current drawing state.
- Batch execution is limited to 100 items. Inputs above 100 non-empty lines are
  rejected before execution.
- Demo execution is limited to 100 cycles per start and stops when the limit is
  reached.
- Room DB stores history, provider settings, and API-key-related user data, so
  destructive migration is prohibited. Schema changes must add explicit Room
  migrations.
- Local model downloads carry `ModelDownloadSpec.maxDownloadBytes`, and
  downloads are aborted both when `Content-Length` is too large and when the
  streamed byte count exceeds the limit.
- History thumbnail decoding is allowed only for canonical paths under
  `files/thumbnails`, preventing unexpected file decoding if the DB is damaged.
- Compose artwork and history-thumbnail caches are limited by estimated bitmap
  bytes rather than entry count.
- Android build number increments only for package-producing tasks such as APK,
  bundle, and install tasks. Avoid running assemble/install for checks that need
  a clean worktree.

## 2026-05-10 Android Performance Optimizations

The Android app implements the following optimizations to improve Pixel 9
history browsing, artwork previews, and first local-model render latency.

- The history grid loads a `HistoryListItem` DTO and does not select
  `display_svg`, `expanded_ddl`, `score_json`, or `render_metadata_json` for
  list rendering.
- Operations that need the full history payload, such as detail selection,
  replay, JSON display, or Prompt display, lazily load `HistoryItemEntity` by
  history id.
- History thumbnails are persisted at render-save time as 384px WebP files in
  app-internal storage. Room `history_items` stores `thumbnail_path`,
  `thumbnail_width`, and `thumbnail_height`.
- Existing history rows without thumbnails are backfilled at startup, up to 100
  rows per startup pass.
- This schema change uses Room version 2 and `MIGRATION_1_2` to add the three
  thumbnail columns. Destructive migration remains prohibited.
- Main artwork previews in Compose and History reuse bitmap output through an
  `LruCache` keyed by history item, display size, and presentation rotation,
  instead of re-rendering SVG on every recomposition.
- The renderer hot path avoids unnecessary JSON stringify/parse deep copies
  while applying colors. This must not change the server/web-compatible meaning
  of Score, SVG, render metadata, or render hash.
- When a selected LiteRT-LM model is already downloaded and in `ready` state,
  Android attempts a background Engine warmup after settings restore, model
  selection, and model download completion.
  - Warmup is only a latency optimization. It does not change render success
    semantics or the GPU-required/no-CPU-fallback policy.
  - A warmed Engine is reused by the normal render path.
- Settings restore loads `app_settings` in one pass instead of issuing many
  sequential `getSetting()` calls during startup.
- PNG share/export is capped at 4320px height and an estimated 128MB bitmap
  allocation. Oversized exports fail before bitmap creation to avoid OOM.
- These changes are Android-internal performance optimizations. They must not
  change DDL, Score, SVG, history JSON, render metadata, or render hash
  compatibility with server/web.

## 2026-05-10 Android Performance Optimizations, Phase 2

The Android app implements the following additional performance improvements.

- Room DB is upgraded to version 3 and adds composite history indexes for
  `trashed, created_at` and `starred, trashed, created_at`. The schema change is
  handled by `MIGRATION_2_3`; destructive migration remains prohibited.
- `HistoryListItem` exposes a precomputed lower-case search string so history
  filtering does not rebuild and lowercase the same fields on every query
  change.
- The history Flow is no longer collected at the app root for every tab. It is
  collected only while the History tab is displayed, reducing unnecessary
  compose work during Compose, Demo, and Settings interactions.
- Render save writes the history row first and schedules 384px WebP thumbnail
  generation on a repository IO coroutine. The history list updates after the
  thumbnail columns are written.
- Startup thumbnail backfill runs in small batches of 8 rows with spacing,
  instead of rendering up to 100 thumbnails in one burst.
- Renderer and pipeline hot paths replace several `JSONObject(item.toString())`
  stringify/parse deep copies with top-level JSON object copy helpers. This
  must not change server/web-compatible Score semantics.
- LiteRT-LM streaming response merging uses `StringBuilder` to reduce repeated
  string copies for long Stage 2 outputs.
- Stage 1 system prompt generation has small LRU caches for both the normal
  prompt and the LiteRT-LM compressed prompt, avoiding repeated example
  selection and large string reconstruction for equivalent inputs.
- Model settings UI parses published model IDs through a small LRU cache, so
  identical `publishedModelsJson` values are not reparsed repeatedly.
- PNG export displays a progress indicator and status text so large PNG exports
  do not appear unresponsive.
- These are Android-internal performance optimizations. They do not change
  saved DDL, Score, SVG, history JSON, render metadata, or render hash
  compatibility.

## 2026-07-23 Catching Up With web/server v2, Phase 1 (Score schema / coerce / hash parity)

Android is at generation `1.48.0-android.1` with render engine version `2`, while the
master web/server implementation has reached v2.4.2 and engine 10. The gap corresponds to
`### v1.49` through `### v2.4.2` in `CHANGELOG.ja.md` and includes a change of method in
the drawing core (absolute px replaced by proportional units; closed-shape outlines,
fills, and arcs redrawn as hand strokes) as well as the additions of variation, plugins,
lineage, and tenkei.

The catch-up proceeds in phases. **Phase 1 is limited to letting the Score carry the new
information; it does not touch how anything is drawn.**

Author's rulings (2026-07-23):

- The drawing core (Score schema / coerce, then the renderer) comes first; lineage and UI
  follow.
- **`render_engine_version` keeps reporting `"2"` until engine 10 is reached.** Reporting
  an intermediate value mid-port would change `render_hash`, breaking history
  compatibility and the meaning of the work edition ID.
- Parity between server and Android is required only up to visual equivalence for now;
  byte-identical SVG is a decision to make once parity tests exist. **The Score (JSON) and
  the hashes, however, must match structurally and by value.**
- `android/VERSION` moves to the `2.x` series when engine 10 is reached; until then it
  stays `1.48.0-android.1`.

### Ported in Phase 1

- **Stage 2 tool schema** (`ServerScoreSchemaJson.kt`): `cloudform` added to the
  primitives; `burin` and `drypoint` added to the weights and `rope` removed; `mode`
  (`additive` / `carve`), `carve_depth`, `at` (a placement region resolved at render
  time), `relation` (`along` / `not_touching` / `cutting` / `between` / `touching`, with
  `contact: both_ends`), and `surface` added to instructions; `layout="grid"` with `rows`,
  `cols`, and `jitter` added to arrangements, with the count ceiling raised to 2000 for
  grids; `canvas` now accepts `{aspect, ground}` as well as an ID string.
- **Unknown fields are rejected**: following the server change that added
  `ConfigDict(extra="forbid")` to every Pydantic schema (v1.86.1), every object in the
  schema carries `additionalProperties: false`, and `ServerScoreCoercer` holds the set of
  permitted instruction keys and drops anything outside it. That set matches the
  `Instruction` fields in the server's `schema.py`.
- **Coercion**: normalization for `surface` and `relation` (defaults, range clamping, and
  keeping `contact` only for `touching`), clamping of grid `rows` / `cols` (1-64) and
  `jitter` (0.0-1.0), and required-field repair for `cloudform`.
- **Vocabulary detection** (`ServerScoreSemantics.kt`): `burin` and `drypoint` added to
  weight detection, the removed `rope` dropped, and `cloudform` treated as a shape with a
  `center` and a `size`.
- **Hashes** (`LocalFallbackPipeline.kt`):
  - `dh1` (description identity) follows `identity.py`: NFC normalization, `\r\n` and `\r`
    folded to `\n`, surrounding whitespace stripped, then `"dh1:" + sha256(...)`.
  - `render_hash` is redefined as `rh2`. The payload holds the same eight fields as the
    server's `db.render_hash_for_item` — `version`, `score`, `render_seed`, `vary_seed`,
    `render_build_number`, `render_engine_id`, `render_engine_version`, and
    `render_color_catalog_id` — and the result is `"rh2:" + sha256(canonical_json)`, where
    canonical JSON means sorted keys, `(",", ":")` separators, and no ASCII escaping.
  - **Seed canonicalization**: the server passes `render_seed` and `vary_seed` through
    `_canonical_seed`, which coerces them to integers before hashing, so the string
    `"12345"` and the number `12345` produce the same hash. Android now has an equivalent
    `canonicalSeed`.

### Not ported in Phase 1 (Phase 2 onward)

The Score accepts and preserves the fields above, but **the renderer does not draw them**.
The following belong to Phase 2 and later:

- `surface` texture rendering and `canvas.ground` ground rendering
- grid (tiling) cell expansion
- `cloudform` contour generation (1/f base curve plus a 49-point closed Bezier)
- the `carve` subtractive compositing order (ground → additive → carve → plate tone)
- minor-arc reconstruction for `touching`, and the region/relation resolution order
  (including the double-arc fix from v1.94)
- the proportional-unit rework (engine 7) and the stroke work that follows (engines 8, 9,
  and 10)

### Verification

`app/src/test/java/app/inku/mobile/pipeline/ServerScoreParityTest.kt` was added.

- **The repair path**: the 15 cases from `server/tests/fixtures/stage2/` are carried in
  with their origin noted, and each is fed to `ServerScoreCoercer` as **the kind of
  unpolished Score an LLM emits** — numbers as strings, `position` used in place of
  `center`, unknown fields mixed in — and the result is checked against the fixture's
  `expected.json`. The comparison covers `center`, `position`, `from`, `to`, `radius`,
  `size`, `style`, `weight`, `color`, and `variation` as well as `primitive`, and
  multi-instruction fixtures are checked in full.
- **Hash values**: pinned against values measured on the server.
  - `中心に円を置く。` → `dh1:4acea64b6cec1944e40896dbf6c167322850bd8a2c15938651ffd3275101da99`
  - `上から1/3に横線を引く。` → `dh1:31d1445b92e140db68a8528022f299325eb9cd1e4c873361d5c94b9bcff6e618`
  - `score` = a centered circle of radius 0.1, `render_seed` = `"12345"` (given as a
    string), `vary_seed` = null, `render_build_number` = `"689"`, `render_engine_id` =
    `"default"`, `render_engine_version` = `"2"`, `render_color_catalog_id` =
    `"sumi_traditional"` → `rh2:b96d71a1af99a98373fd47b093b12bd836f9af33a0da0546a1312fdc253adb99`
    (short `DB99`)

    Passing the seed as a string and still matching is what confirms `canonicalSeed` works.

`gradle :app:testDebugUnitTest` passes all 11 tests and `gradle :app:assembleDebug`
succeeds. `android/BUILD_NUMBER` is `148069`; `android/VERSION` remains
`1.48.0-android.1`.

## 2026-07-23 web/server v2 Alignment Phase 2a (Geometry Variation & Wave Phase Seed Tracking)

In accordance with contract `antigravity-android-phase2-renderer.md` §4/§5, Phase 2a of the renderer alignment was completed.
`render_engine_version` remains `"2"` as decreed in ruling 1.

### Scope Ported

- **Geometry Variation (`ServerRendererGeometry.kt`)**:
  - `wavePhase(seed: Int)`: `_hash01(0, seed, "wave-phase") * 2 * Math.PI` derives the noise phase nonlinearly from `seed` when `wave` quality is requested.
  - `periodicValueNoise1D`: Added periodic noise helper for closed contours ($t \in [0, 1)$) to ensure seamless boundary loop continuity.
  - `variedCirclePoints`, `variedEllipsePoints`, `variedPolygonPoints`, `variedArcPathD`:
    Applies variation noise according to `quality` (`wave`, `perlin`, `pink`, `white`) and `dimensions` (`position_x`, `position_y`, `radius`) for circle, ellipse, polygon, rect, and arc primitives.
- **Material Seed Dependency (`ServerRendererMaterial.kt`)**:
  - `seedToInt` normalizes `render_seed` to ensure 100% deterministic output for material lines and powder specks.
- **Renderer Integration (`DefaultSvgRenderer.kt`)**:
  - Evaluates `variation` presence for `circle`, `ellipse`, `square`, `triangle`, `polygon`, and `arc`, outputting distorted `<polygon points="...">` or `<path d="...">` elements accordingly.

### Verification

`app/src/test/java/app/inku/mobile/render/ServerRendererGeometryTest.kt` was added.

- **Wave Phase Seed Dependency**: Verified that seeds 111 and 222 yield distinct wave phases and sample offsets, while identical seeds yield 100% deterministic points.
- **Geometry Distortion & Determinism**: Verified that circle, arc, and polygon variations distort accurately and reproduce identically for identical seeds.

`gradle :app:testDebugUnitTest` (all 15 tests) and `gradle :app:assembleDebug` succeed.
`android/BUILD_NUMBER` is `148070`; `android/VERSION` remains `1.48.0-android.1`.

## 2026-07-23 web/server v2 Alignment Phase 2a′ (Exact Server Alignment of Variation Primitives)

In accordance with contract `antigravity-android-phase2-renderer.md` §8, Phase 2a′ exact alignment of variation primitives (`_hash01`, `_hash_to_unit`) was completed.

### Explicit Separation & Specification of Two Hash Functions

1. **`_hash01(i, seed, salt)`**:
   - String format is **`"{seed}:{salt}:{i}"`** (yielding `"{seed}::{i}"` when `salt` is empty).
   - Extracts the first 4 bytes of SHA-256 digest as a little-endian unsigned 32-bit integer, divided by `0xFFFFFFFF` (4294967295) to produce a float in $[0.0, 1.0]$. Used for `wavePhase` etc.
2. **`_hash_to_unit(i, seed)`**:
   - Has a completely independent arithmetic structure from `_hash01`. String format is **`"{seed}:{i}"`** (no salt).
   - Extracts the first 8 bytes of SHA-256 digest as a little-endian **signed 64-bit integer** (`Long`), divided by $2^{63}$ (`9223372036854775808.0`) to produce a float in $[-1.0, 1.0]$.
   - Used as the foundation for `valueNoise1D` (Perlin lattice) and `white` noise.

### Verification

Added `testReferencePrimitivesExactParity` to `ServerRendererGeometryTest.kt` to assert against `renderer_variation_primitives.json`.

- All items for `wave_phase` (3 cases), `hash01` (6 cases), `hash_to_unit` (5 cases, including negative $i$), `value_noise_1d` (5 cases), `periodic_value_noise_1d` (5 cases), `sample_offset` (36 samples), and `sample_offset_periodic` (36 samples) match server measured values 100% within **tolerance 1e-9**.

`gradle :app:testDebugUnitTest` (all 16 tests) and `gradle :app:assembleDebug` succeed.
`android/BUILD_NUMBER` is `148071`; `android/VERSION` remains `1.48.0-android.1`.

## 2026-07-23 web/server v2 Alignment Phase 2b (Full Proportional Scale Rework of px Constants)

In accordance with contract `antigravity-android-phase2-renderer.md` §9, absolute px constants were refactored into a proportional scaling system based on `canvas.unit` and shape representative sizes (aligning with engine 7 / v2.1.0).

### Explicit Differentiation of Scaling Systems

1. **`canvas.unit` System (`min(width, height)`)**:
   - Stroke width $\text{strokeWidthPx}$ ($\text{base} \times \frac{\text{unit}}{1000}$), segment target length ($\text{unit} \times 0.01$), stroke sample target ($\text{unit} \times \frac{1}{49}$), and material outline offset floor ($\text{unit} \times 0.0035$).
2. **Shape Representative Size $\text{representativeSizePx}$ System**:
   - `circle` / `polygon` / `arc`: Radius $r \cdot \text{unit}$
   - `ellipse`: Geometric mean of 2 radii $\sqrt{r_x \cdot r_y}$
   - `square` / `triangle` / `cloudform`: Half of short side ($\min(w, h) / 2$)
   - `line`: Line length $\text{hypot}(dx, dy)$
   - Lower clamp $\text{clampedRepresentativePx}$: $\max(\text{rep}, \text{unit} \times 0.02)$
   - Variation amplitude `amplitudePx` (ratios 0.025/0.08/0.18, max $0.40 \times \text{rep}$), blur std `blurStdPx` (ratios 0.009/0.03/0.07, min $\text{unit} \times 0.0005$).

### Verification

Added `ServerRendererProportionalTest.kt` to assert against `renderer_proportional.json` across 4 aspect ratios (`square`, `wide`, `pillar`, `vertical`).

- `representative_size_px` (28 cases), `amplitude_px` (84 cases), `blur_std_px` (84 cases), and `stroke_width_px` (40 cases) match 100% within **tolerance 1e-9**.
- Integer rounding items `segment_count` (20 cases), `stroke_sample_count` (20 cases), and `speck_count` (60 cases) match 100% via Banker's Rounding (`Math.rint(...).toInt()`).

`gradle :app:testDebugUnitTest` (all 17 tests) and `gradle :app:assembleDebug` succeed.
`android/BUILD_NUMBER` is `148072`; `android/VERSION` remains `1.48.0-android.1`.

## 2026-07-23 web/server v2 Alignment Phase 2b′ (Wiring Proportional Scale to Render Pipeline & Resolving Unimplemented Items)

In accordance with contract `antigravity-android-phase2-renderer.md` §10, proportional scale functions added in 2b were fully wired into the rendering pipeline (`DefaultSvgRenderer.kt`, `ServerRendererGeometry.kt`, `ServerRendererStyle.kt`, `ServerRendererMaterial.kt`), removing all hardcoded legacy absolute functions and default parameters.

### Wiring & Resolution of Unimplemented Requirements
1. **Complete Removal of Legacy Functions & Defaults**: Removed `ServerRendererGeometry.getAmplitudePx` in favor of `amplitudePx`. Removed default parameter `= 1000.0` from `ServerRendererStyle.strokeAttrs` and `strokeWidth`.
2. **Full Propagation of Canvas `unit` (`min(width, height)`)**: Threaded `unit` down from `DefaultSvgRenderer` to all geometry, material, and style calls.
3. **Dynamic Blur Filter Aggregation**: Replaced static `blur-fine / blur-medium / blur-broad` with dynamic `filter_id = "blur-${amp}-${int(std*10)}"` aggregation computed from `blurStdPx` and outputted to `<defs>`.
4. **Proportional Texture Filters**: Updated `baseFrequency` to be inversely proportional to `unit` (`base * (1000.0 / unit)`) and displacement scale to be proportional to `unit`.
5. **Material Constraints**: Applied material outline offset floor `0.0035 * unit` (preserving sign via `Math.copySign`), outline opacity floor 0.5 (capped at 1.0), speck opacity floor 0.4 (capped at 1.0), and perimeter-proportional speck counts.

### Verification
Added `ServerRendererProportionalWiringTest.kt` to assert rendered SVG output across 4 dimensions:
- **Stroke Width Scaling**: 9 weights across `square` (unit 1000) and `pillar` (unit 200) match reference fixture `stroke_width_px` within 1e-9 tolerance.
- **Variation Amplitude Scaling**: Wave variation radius deviation ratio between square and pillar equals 5.0 (±5% tolerance) and remains within upper bounds (16.0 for square / 3.2 for pillar).
- **Blur Scaling**: `<feGaussianBlur>` `stdDeviation` dynamically scales (6.0 for square / 1.2 for pillar).
- **Material Scaling**: Speck counts and outline offset floor (0.7px for pillar) are accurately reflected in rendered SVG elements.

`gradle :app:testDebugUnitTest --rerun-tasks` (all 21 tests) and `gradle :app:assembleDebug` succeed.
`android/BUILD_NUMBER` incremented to `148073`.

## 2026-07-23 web/server v2 Alignment Phase 2c (Creation of `ServerStrokeEngine.kt` & Verification)

In accordance with contract `antigravity-android-phase2-renderer.md` §8, `server/src/inku_server/stroke_engine.py` (438 lines) was fully ported to Kotlin as new file `ServerStrokeEngine.kt` and verified with `ServerStrokeEngineTest.kt`.

### Key Design Rationale & Algorithm Details

1. **`_unit` Hash Construction**:
   - Distinct from `_hash01` and `_hash_to_unit`, the hash format string is **`"{seed}:{label}:{index}"`**.
   - Extracts the first 8 bytes of SHA-256 as an **Unsigned Little-Endian 64-bit integer (`ULong`)**, divided by `2^64 - 1` (`18446744073709551615.0`) to produce a float in $[0.0, 1.0]$.
2. **Separation of Integrators in `synthesize_stroke` and `synthesize_along`**:
   - `synthesize_stroke` (straight line) and `synthesize_along` (arbitrary centerline) use different integration formulas.
   - `synthesize_along` feeds forward the intended step vector (`step`), leaving the spring tracker to carry only the residual deviation to prevent radial shrinkage on curves. The two integrators are kept strictly separate.
3. **Negative Indexing, Seam Ramping & Event Window**:
   - Centerline normal calculations handle negative indices via `(index - 1 + count) % count` for closed contours.
   - `_arc_length_parameters` includes the seam segment in `total` for closed loops but not in `running`, ensuring `parameters.last() < 1.0`.
   - `_event_map` scans window `3 until (count - 3)` and caps at 2 events max via early `break`.
   - `polygon_path` / `ring_path` path generation applies Python-compatible HALF_EVEN rounding.

### Verification

`ServerStrokeEngineTest.kt` was created to perform exact parity testing against 4 server reference JSON fixtures:

- `stroke_engine_primitives.json`: `grammars` (10 weights exact match), `unit` (56 cases, 1e-12 tolerance), `smooth_noise` (24 cases, 1e-12 tolerance), `event_map` (16 cases exact match), `centerline` (3 cases, 1e-12 tolerance).
- `stroke_engine_latent_energy.json`: 3 seeds × 21 samples (1e-6 tolerance).
- `stroke_engine_synthesize_stroke.json`: 9 cases for `samples` (1e-6), `outline` (1e-6), `event_count`, `burr_side`, `burr_opacity` (1e-9), and `path_d` (exact string match).
- `stroke_engine_synthesize_along.json`: 5 cases for `samples`, `left`, `right` (1e-4 tolerance), and `path_d` (exact string match).

`gradle :app:testDebugUnitTest --rerun-tasks` (all 25 tests) and `gradle :app:assembleDebug` succeed.
`android/BUILD_NUMBER` incremented to `148074`. `android/VERSION` remains `1.48.0-android.1`.





