# inku Android Implementation Notes

This directory is the Android workspace for the native standalone app and is
tracked by Git. Local-only artifacts, device IDs, downloaded models, logs, and
secrets must remain outside tracked files.

Last updated: 2026-08-25.

**Catch-up status**: Android sits at generation `2.1.4-android.64` with **render engine
`default / 41`** and **DDL engine version `20`**. Render identity comes from the packaged
`core/crates/inku-render/` library through JNI rather than a Kotlin compatibility literal;
`ReferenceCorpus.kt` declares the DDL reference version. The server also uses render engine `41`
and DDL engine `20`, so server and Android now share one Rust drawing implementation. The Stage 1.5 expander followed the staffage level being folded away on
2026-08-05 (see the 2026-08-05 section at the end of this document).

**The shared-Rust cutover is complete**: production Score-to-SVG/metadata calls
`core/crates/inku-render/` through one JNI request owned by `AndroidRenderHost`. Preview,
thumbnail, and PNG presentation rasterize saved/current SVG through the separate host-neutral
`core/crates/inku-svg-raster/` crate. Kotlin Engine 35 and AndroidSVG have been retired from
production, with no runtime fallback. Saved SVG, Room and Score schemas, DDL engine, and `rh3`
semantics are unchanged.

**Matching layer versions is not the same as a finished port.** The version number asserts that
drawing is identical; it says nothing about the UI, storage, or vocabulary. **The gaps that remain
are held by the issue ledger under the `android` area** — they are deliberately not copied here,
because a copy goes stale. The port proceeds in phases; see the phase sections at the end of this
document.

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
- Production Score-to-SVG rendering and performance metadata use the same
  `core/crates/inku-render/` in server and Android. Android calls the shared core
  through one native request boundary and does not keep a second canonical engine in Kotlin.
- Production paths including main preview, thumbnails, headless rendering,
  and DDL replay use SVG and metadata returned by Rust. Compose Canvas may remain a UI aid,
  but it does not mint a separate engine version or render identity.
- Saved SVGs are not rewritten during the cutover. Existing editions display their saved SVG;
  an explicit replay uses the latest Rust engine available at that time.
- The Rust engine cutover does not by itself expand into Room schema, persistence format,
  LLM providers, Stage 1 / 1.5 / 2, or coerce. Expanding the shared-core boundary requires a
  separate decision and contract.
- Gemma 4 E2B is the default local model. Gemma 4 E4B is a high-quality option.
- First launch downloads the selected local model after a license confirmation.
- Target device class is Pixel 9 or newer.

## Current Implementation Status

The Android workspace currently contains a buildable standalone application
package with namespace `app.inku.mobile`.

As of 2026-08-24, Android includes the Rust binding, Cargo/Gradle packaging, arm64 native library,
and Rust raster presentation. The list below records the post-cutover state.

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
- `AndroidRenderHost` serializes the coerced Score, resolved canvas and color map, catalog,
  profile, seeds, and `wild` into one canonical JSON request and calls shared Rust Engine 41
  through `NativeRenderBridge`.
- `inku-svg-raster` uses `resvg 0.48.0` to convert saved/current SVG into explicit
  premultiplied RGBA8 pixels with width, height, and stride. Android performs only the
  mechanical conversion to Bitmap backing-byte order.
- Main preview, history thumbnails, refinement preview, and PNG export use
  `RustArtworkRasterizer`. Its cache key includes SVG identity, target size, raster API, and
  options so ordinary recomposition does not rerasterize an unchanged work.
- Rust render and raster work runs on background coroutine dispatchers. There is no runtime
  renderer or rasterizer fallback.
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
- Android continues to own Kotlin Stage 1 / 1.5 / 2, Score coerce/repair, Room, and history.
  Shared Rust alone owns drawing geometry, materials, surfaces, strokes, and SVG serialization.
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
  - render sub-tabs: `Artwork`, `Prompt`, `Json`
  - explicit button rows for model, color catalog, and canvas selection
  - dedicated History screen with search/filter placeholders and two-column
    thumbnail cards
  - stronger History selected-card affordance using an accent border and
    corner marker instead of an overlaid text badge
- History operations for the selected item:
  - star / unstar
  - soft trash
  - JSON share export through Android `FileProvider`
- The normal Compose screen has a history thumbnail strip below the canvas. It reads only saved
  history values for selection, Star toggling, Stage 1/2 models, saved time, color-catalog ID,
  work hash, and canvas tooltips.
- A read-only generation-information sheet shows saved sketch, models and languages, seeds and
  variation, color catalog and color map, canvas, render hash and engine, creation time, and elapsed time.
- Lineage cards support editing saved DDL and Star toggling without changing the current focus when
  the action targets another card.
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

## Verified Device State

Latest verified device class:

- Device: Pixel 9 connected by USB.
- APK: debug build from `android/app/build/outputs/apk/debug/app-debug.apk`.

Verified on device:

- Five canonical Engine 41 cases match the server corpus byte for byte through the packaged
  `arm64-v8a` JNI library.
- Three current cases and one historical Engine 21 case match raw pixels, dimensions, stride, and
  SHA-256 at a 64-pixel target.
- Native identity reports default Engine `41`, renderer reference `11`, and core/raster API `0.1.0`.
- App installs and launches.
- Process remains running after launch.
- Draw action creates a new Room history item.
- Batch-generated and single-draw history entries persist in `inku.sqlite`.
- Latest checked history count: `4`.
- Latest checked render hash short: `6D8E`.
- Stored JSON Score and render metadata are visible through the JSON render tab.
- Main preview and history thumbnails rasterize saved canonical SVG through the shared Rust rasterizer.
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

The Android UI, host orchestration, and persistence use `web/` and `server/` as their reference.
The canonical drawing engine is the shared Rust core under `core/crates/inku-render/`, used by both
server and Android. Android remains a standalone native package: web/server stay authoritative for
DDL interpretation, Stage 1.5 expansion, Score coercion/repair, and history persistence, while the
Rust core is authoritative for SVG output and performance metadata.

Whenever web/server changes, the corresponding Android parity surface must be
checked in the same change unit. Android compatibility code is split along the
same responsibility boundaries as the server source so that future diffs are
easier to inspect and omissions are easier to catch.

Drawing-engine ownership and cutover boundary:

| Canonical source / current bridge | Android side | Responsibility |
| --- | --- | --- |
| `core/crates/inku-render/` | `AndroidRenderHost` → `NativeRenderBridge` → `inku-render-android` | Planning, geometry, marks, surfaces, layers, SVG emission, deterministic seeds, and performance metadata |
| `server/src/inku_server/render_engines/default/adapter.py` | Android host adapter | Thin host boundary that sends canonical Score and render options in one request and receives SVG plus metadata |
| `core/crates/inku-svg-raster/` | `RustArtworkRasterizer` | Presentation boundary from canonical SVG to host-neutral pixels; owns no Score, engine identity, or `rh3` semantics |

Cutover acceptance directly checks that single drawing, batch, demo, saved-Score replay, headless,
main preview, and thumbnail production paths reach Rust; engine ID/version comes from the Rust core;
and the same request yields matching SVG and engine metadata on the server host. Existing saved SVGs
are not regenerated.

The same policy applies to the pipeline. Changes in
`server/src/inku_server/interpreter.py`, `ddl_expander.py`, `coerce.py`, and
`schema.py` must be checked against the Android `pipeline/` package and
compatibility data models. Android-specific UI, Room, LiteRT-LM, and provider
routing can remain native, but user-visible DDL, Score, SVG, render metadata,
and history persistence behavior prioritize web/server parity.
The rendering cutover does not automatically move this Kotlin pipeline into Rust. Moving Stage 1,
Stage 1.5, Stage 2, or coerce into the shared core requires a separate contract that fixes the
boundary and persistence compatibility.

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
| `server/src/inku_server/db.py::render_hash_for_item` / `identity.py::description_hash` | `renderHash` / `descriptionHash` / `canonicalSeed` in `android/app/src/main/java/app/inku/mobile/pipeline/LocalFallbackPipeline.kt` | The `rh3` payload, canonical-JSON and `render_wild` normalization rules, `dh1` normalization, and integer coercion of seeds |

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
| SVG render engine | `core/crates/inku-render/` (the server calls it through `render_engines/default/adapter.py`) | `AndroidRenderHost` / `NativeRenderBridge` | Production sends one request to the same Rust core and reads engine identity and renderer reference from the same owner. |
| SVG raster presentation | `core/crates/inku-svg-raster/` | `RustArtworkRasterizer` / Bitmap and Compose | Rasterizes saved/current SVG without changing it. There is no AndroidSVG or Kotlin drawing fallback. |
| Render hash / metadata | `api.py::_render_hash` / render metadata assembly | `LocalFallbackPipeline.kt::renderHash` / renderer metadata | Match hash input fields, build number handling, engine id/version, catalog/canvas metadata. |
| History persistence | `api.py::_add_history_item` / `db.py::add_history_item` | `InkuRepository.kt::saveResult` / Room entities | Store the same user-visible data: input, DDL, Score, SVG, metadata, model IDs, catalog/canvas, hash, and timestamps. |
| Headless / CLI benchmark | `inku-cli paint --save-history` | `HeadlessRenderActivity.kt` / `android/scripts/headless_*` | Let both server and Android save history, and keep history_id, DDL, hash, and catalog in summaries. |

Saijiki parity is held by generation. The Android UI word groups are not copied
by hand: `server/scripts/gen_saijiki_kt.py` bakes `SaijikiGenerated.kt` out of
`saijiki.py` (10 categories and 73 words in each language) and the screen reads
that. `server/tests/test_saijiki_kt_is_current.py` keeps it fresh. Server Stage 1 is
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
| `CanvasPanel.svelte` | Ported for `artwork`/`prompt`/`score` tabs, star, hash copy, render metadata, zoom/pan controls, SVG share, and PNG share. |
| `OutputTabsContent.svelte` | Ported as prompt and JSON views from the saved Room history item. |
| `HistoryStrip.svelte` | Ported as a thumbnail strip below the Compose canvas, with selection, Star, model names, and saved-metadata tooltips. The history grid remains a separate entry point. |
| `HistoryManager.svelte` | Ported for thumbnails/list modes, search, starred filter, selection, trash, restore, and permanent delete. |
| `HistoryThumbnail.svelte` | Ported through `ArtworkPreview` in history tiles and list rows. |
| `ConfirmDialog.svelte` | Ported for DDL overwrite and destructive history operations. Non-history destructive settings confirmations remain in the parity test backlog. |
| `SettingsModal.svelte` | Ported for model selection, model connection settings, plugin setting, DB status, export templates, and misc settings. Server-only logs/output-save are represented as local-only equivalents. |
| `IncuMascot.svelte` / `YuragiMascot.svelte` | Ported as MascotWidget and IncuMascotView / YuragiMascotView with 5x5 pixel grid and animations in pure Kotlin / Compose Canvas. |

## Implementation Order

Completed or substantially implemented:

1. Project skeleton, Room schema, and compatibility data models.
2. Local settings, model download state placeholders, and provider abstraction.
3. Retired the Kotlin renderer through engine `35` and cut over to shared Rust Engine 41 plus Rust raster presentation.
4. Stage 1 / Stage 1.5 / Stage 2 pipeline shape with deterministic fallback.
5. Compose UI for single drawing, batch, demo, history, settings shell, render
   previews, prompt view, and JSON view.

Remaining next order:

1. Verify LiteRT-LM inference end to end on Pixel 9 with the downloaded Gemma 4
   E2B/E4B `.litertlm` model files and expose provider failures in the UI/log
   surface instead of silently falling back.
2. Harden model download UX with a foreground service or WorkManager,
   notifications, metered-network policy, and user-visible storage recovery.
3. Expand the JSON Score parser to cover the full web surface. Do not expand drawing algorithms in Kotlin.
4. Extend export compatibility from current single-item share export to full
   history import/export flows with Android Storage Access Framework.
5. Complete destructive confirmations for every non-history settings operation
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
- Controls and menus must not be overlaid on top of the work preview.
  - Star, render hash, and zoom controls are placed above the image.
  - `Artwork` / `Prompt` / `Json` / SVG / PNG controls are placed below the image.
  - SVG / PNG expanded choices are shown inline below the image, not as
    popups covering the work.
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
  work.
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
  so the work's long edge always aligns with the screen's long edge.
- While presentation view is active, Android detects the device's physical
  up/down orientation and dynamically adjusts the work's visual up direction
  to match. For a landscape work, long-edge alignment takes precedence, so the
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
  whole presentation surface, including margins outside the displayed work.
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
- Under the 2026-08-24 author ruling, Room v1–9 is intentionally reset once for
  this transition only. Before starting the normal Room singleton, a reset
  coordinator classifies `inku.sqlite`; only the v1–9 allowlist closes open
  handles, removes the database and its journals through the Android database
  API, and removes the derived `files/thumbnails` tree. Old rows are not
  migrated, exported, or retained. The existing bootstrap owner then starts a
  fresh v10 database normally. A missing or zero-byte DB creates fresh v10,
  while an existing v10 DB opens normally without deletion. Downloaded model
  files under `files/models/` are outside SQLite and are not deleted by this
  reset. Version 11 or later, non-empty version 0, and unreadable SQLite DBs
  fail closed without changing database, thumbnail, or model bytes, and show
  only a safety explanation and retry. Retry repeats classification only; it
  never clears or deletes. Schema changes after v10 require an explicit Room
  migration or a new author ruling, and no generic destructive fallback is
  used.
- Local model downloads carry `ModelDownloadSpec.maxDownloadBytes`, and
  downloads are aborted both when `Content-Length` is too large and when the
  streamed byte count exceeds the limit.
- History thumbnail decoding is allowed only for canonical paths under
  `files/thumbnails`, preventing unexpected file decoding if the DB is damaged.
- Compose work-preview and history-thumbnail caches are limited by estimated
  bitmap bytes rather than entry count.
- Android build number increments only for package-producing tasks such as APK,
  bundle, and install tasks. Avoid running assemble/install for checks that need
  a clean worktree.

## 2026-05-10 Android Performance Optimizations

The Android app implements the following optimizations to improve Pixel 9
history browsing, work previews, and first local-model render latency.

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
  thumbnail columns. No destructive migration was used for this historical v2
  change.
- Main work previews in Compose and History reuse bitmap output through an
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
  handled by `MIGRATION_2_3`; no destructive migration was used for this
  historical v3 change.
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

## 2026-07-25 render engine 12 Catch-up Phase 4b′ (Material Outline Layer Re-implementation & Exact Parity Verification)

In accordance with contract `antigravity-android-engine12.md` §9, re-implemented the material outline layer (`<polyline class="material-outline">`) and added exact string parity assertions for `points` and `stroke-dasharray`.

### Implementation & Parity Fixes
1. **`ServerRendererMaterial.kt` Direct Port Fixes**:
   - Fixed redundant `scale` multiplication in `outlineOffsetPx` to match `_outline_offset_px`.
   - Formatted seed in `hash01` as `${seed.toULong()}:$salt:$i` (unsigned uint64 decimal representation).
   - Unified `variedDashPattern` (3 decimal places) and `scaleDash` (`fmt` 6 decimal places) formats with Python implementation.
2. **`DefaultSvgRenderer.kt` Pipeline Fixes**:
   - Passed normalized 64-bit uint64 seed (`seedLong`) derived via `seedForInstruction` to `ServerRendererMaterial.lineGroup` via `instructionSeed`.
   - Bound `materialCenterline` to `centerline` (varied centerline) when `ins.variation` is present.
3. **Exact String Parity Tests (`DefaultSvgRendererPhase2fTest.kt`)**:
   - Added `testMaterialOutlinePointsAndDashArrayExactParity` verifying exact string parity (`assertEquals`) of `points` and `stroke-dasharray` against reference SVGs for `02_line_brush`, `09_line_white`, `14_region_then_relation`, and `15_line_brush_wild`.
4. **Mutation Sensitivity Verification**:
   - Verified that adding a `1e-6` perturbation (`0.003500001`) to `outlineOffsetPx` floor causes `testMaterialOutlinePointsAndDashArrayExactParity` to FAIL.

### Verification Results
- All 68 unit tests PASS 100% (`PASS 68 / Failures 0 / Errors 0 / Skipped 0`).
- `android/BUILD_NUMBER` is **`148088`**.
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

## 2026-07-23 web/server v2 Alignment Phase 2d (Line Expressive Rendering `stroke-engine-v1`)

In accordance with contract `antigravity-android-phase2-renderer.md` §8, non-`rotring` `primitive == "line"` rendering was routed to `ServerStrokeEngine.synthesizeStroke`, emitting `<g class="stroke-engine-v1 controls-N events-M">` containing variable-width outline `<path>` elements (`rotring` lines remain geometric `<line>` / `<polyline>`).

### Implementation & Seed Calculation Synchronization

1. **Expressive `line` Rendering in `DefaultSvgRenderer.kt`**:
   - Delegates non-`rotring` line rendering to `renderHandStroke` to construct `stroke-engine-v1` groups.
   - For lines with variation (`needsPathVariation`), the first `synthesizeStroke` pass (39 samples) determines the group `class` attribute (`controls-39 events-M`), while the second `synthesizeStroke` pass (`centerline.size` samples) provides per-sample widths to `outlineForCenterline` for the variable-width band.
2. **Key & Seed Parity with Python `_seed_for_instruction`**:
   - `serverInstructionJson` matches Python Pydantic `model_dump(mode="json")` exact key order, `from_` key alias, `variation` filtering (`null` for lines without variation), and default `null` fields (`center`, `radius`, `at`, `relation`, `surface`, etc.).
   - Appends `:render:{renderSeed}` and interprets SHA-256 digest bytes as Little-Endian Unsigned 64-bit integer (`ULong`).
3. **64-bit Seed Formatting & Variation Hash Repairs**:
   - `ServerStrokeEngine.kt` `unitHash` formats `$seed` as unsigned 64-bit string (`seed.toULong().toString()`), matching Python's `f"{seed}:{label}:{index}"`.
   - `ServerRendererGeometry.kt` replaces 32-bit truncation `seedToInt` with `seedToLong`, maintaining 64-bit seed values across `hash01`, `signedHash`, `sampleOffset`, and `xorSeed` (`seed ^ 0x9E37`).

### Verification

`DefaultSvgRendererPhase2dTest.kt` was created to perform exact parity validation against server reference SVG fixtures:

- `02_line_brush.svg`: `stroke-engine-v1 controls-39 events-2` class attribute and `path d` coordinate string **match reference SVG exactly**.
- `09_line_white.svg`: `stroke-engine-v1 controls-39 events-0` class attribute and varied centerline band `path d` coordinate string **match reference SVG exactly**.
- `05_circle_rotring.svg` (Rotring Verification): Does not create `stroke-engine-v1` group and renders geometric `<line>` correctly.

`gradle :app:testDebugUnitTest --rerun-tasks` (all 28 tests) and `gradle :app:assembleDebug` succeed.
`android/BUILD_NUMBER` incremented to `148075`. `android/VERSION` remains `1.48.0-android.1`.

## 2026-07-23 web/server v2 Alignment Phase 2e (Closed Shape Expressive Outline `contour-stroke-v1`)

In accordance with contract `antigravity-android-phase2-renderer.md` §8, closed shape primitives (`circle`, `ellipse`, `square`, `triangle`, `polygon`) with non-`rotring` weights were migrated to single-stroke ring bands (`contour-stroke-v1` with `fill-rule="evenodd"` 2-subpath `<path>`). `rotring` shapes maintain their original geometric elements.

### Implementation & Seed Calculation Synchronization

1. **64-bit Seed Truncation Elimination**:
   - Completely removed `seedToInt` (32-bit truncation) across `ServerRendererGeometry.kt`, `ServerRendererMaterial.kt`, and `DefaultSvgRenderer.kt`, preserving 64-bit seed values (`Long` representing unsigned 64-bit bit patterns) throughout.
   - Added parity test in `ServerRendererGeometryTest.kt` verifying `renderer_seed_range.json` reference values (`stroke_engine_unit`, `renderer_hash01`, `renderer_hash_to_unit`, `instruction_seed`), proving 100% deterministic seed calculation matching Python server.
2. **`contour-stroke-v1` Band Generation in `DefaultSvgRenderer.kt`**:
   - Non-`rotring` closed shapes use `usesHandStroke(weight)` (`weight != "rotring" && weight in GRAMMARS`) to synthesize `contour-stroke-v1` bands.
   - Non-varied shapes sample contours based on `strokeSampleCount`.
   - Varied shapes sample contours based on `segmentCount` and apply per-edge seeds (`seed + (i + 1) * 7919`) and representative dimension amplitude `amp` for polygons.
   - Base shape elements update `fill` and `stroke` according to `region_fill` (`false` if `surface` specified), scaling `stroke-width` by 0.42 for non-`solid` styles.
   - `drypoint` shapes render burr polygons using per-sample normals `centerlineNormals`.

### Verification

`DefaultSvgRendererPhase2eTest.kt` and `ServerRendererGeometryTest.kt` were created and expanded to validate structural and exact string parity against reference server SVGs:

- `01_circle_pen.svg`, `07_circle_wave.svg`, `08_circle_perlin.svg`: `contour-stroke-v1` class attribute and `<path d="...">` coordinate strings **match reference SVGs exactly**.
- `05_circle_rotring.svg`: Does not create `contour-stroke-v1` band and renders plain `<circle>`.
- `03_square_filled.svg`, `06_surface_hatch.svg`: `contour-stroke-v1` class attributes match reference SVGs.

`gradle :app:testDebugUnitTest --rerun-tasks` (all 35 tests) and `gradle :app:assembleDebug` succeed.
`android/BUILD_NUMBER` incremented to `148076`. `android/VERSION` remains `1.48.0-android.1`.

## 2026-07-23 web/server v2 Alignment Phase 2f (Surface Texture & Hatch `surface-stroke-v1` + Arc `arc-stroke-v1` Full Parity)

In accordance with contract `antigravity-android-phase2-renderer.md` §8, full Android rendering synchronization for surface textures / hatches (`surface-stroke-v1`) and arc strokes (`arc-stroke-v1`) was completed.

### Implementation Details

1. **Surface Texture & Hatch Rendering (`renderSurfaceVectors`)**:
   - Renders hatch lines and stipple groups when `surface` is specified, applying `class="surface-stroke-v1 hatch-spacing-..."` directly to child elements (`<path>` or `<line>`).
   - For non-`rotring` weights (`pencil`, `pen`, `marker`, `crayon`, etc.), converts hatch segments to hand-drawn strokes (`hatchStroke`) via `ServerStrokeEngine.synthesizeAlong` and outputs them using `contourStrokePath`.
   - Implemented shape-specific scanline intersection algorithms (`surfaceScanlineSegments`) for `circle`, `ellipse`, `square`, `triangle`, `polygon`, `arc`, and `cloudform` bounding boxes and scanline clips.
2. **Arc Expressive Stroke Rendering (`renderArcHandStroke`)**:
   - Generates expressive hand strokes (`arc-stroke-v1`) for `arc` primitives, emitting intent lines (`polyline` / `path`) and outline band paths (`contourStrokePath`) in exact sequence.
   - Fully synchronized `arcPointsWithVariation` endpoint pinning contract (`basePoints[0]` and `basePoints[last]` pinned, parameterized via `i / last`).
3. **Material Outline Profile (`ServerRendererMaterial.kt`)**:
   - Added `class="material-outline"` to `circleOutline`, `ellipseOutline`, `rectOutline`, and `arcOutline` elements, aligning with Python `s1` material intensity level (`offsetGain = 2.8`, `opacityGain = 1.8`, `offsetFloor = 0.0035 * unit`, `opacityFloor = 0.50`).
4. **Seed & Field Serialization Alignment**:
   - Strictly aligned with Pydantic JSON field aliases: `serverInstructionJson` uses `"from_"` (matching Python `model_dump(mode="json")`), while `surfaceSeed` uses `"from"` (matching `model_dump_json(by_alias=True)`).
   - `synthesizeAlong` pins open stroke endpoints (`samples[0]` and `samples[last]`) to `points[0]` / `points[last]` when `closed = false`.

### Verification

Created and expanded `DefaultSvgRendererPhase2fTest.kt` to validate structural and exact string parity against 10 reference server SVGs:

- **Reference SVG Parity**: All 10 reference SVGs (`01_circle_pen.svg`, `03_square_filled.svg`, `04_arc_crayon.svg`, `05_circle_rotring.svg`, `06_surface_hatch.svg`, `07_circle_wave.svg`, `08_circle_perlin.svg`, `10_arc_wave.svg`, etc.) match 100% in structure (element count, order, `class` attributes) and `<path d="...">` coordinate strings.
- `gradle :app:testDebugUnitTest --rerun-tasks` (all 44 unit tests) passes 100%.
- `gradle :app:assembleDebug` succeeds, incrementing `android/BUILD_NUMBER` to `148077`. `android/VERSION` remains `1.48.0-android.1`.

## 2026-07-23 web/server v2 Alignment Phase 2g (Cloudform Contour, Touching Reconstruction, Region/Relation Ordering & 2f Remediation)

In accordance with contract `antigravity-android-phase2-renderer.md` §8, the final Phase 2 stage (Phase 2g) covering cloudform contour generation, minor-arc reconstruction for `touching`, region/relation resolution ordering, and 2f leftover remediations was completed.

### Implementation & Remediation Details

1. **2f Leftover Remediation (⓪)**:
   - Replaced 11 invalid color catalog ID references (`"sumi"`, `"sumi_traditional"`) in test code with valid `"default"`, verifying all tests pass.
   - Documented decision on unknown catalog IDs: retained deterministic fallback to `"default"` via `ColorCatalogs.get()` to preserve Android native application stability and robust UI rendering.
   - Corrected 2f section documentation errors in `ANDROID_SPEC.ja.md` and `ANDROID_SPEC.md` regarding reference SVG enumeration, structural vs path coordinate parity distinctions, engine 10 arrival, and `2.0.0-android.1` version numbering.
2. **Cloudform Contour Generation (`ServerRendererGeometry.kt`)**:
   - Ported `generateCloudformContour`, `sampleClosedCatmullRom`, 1/f harmonic bases, 49-point closed Bezier curves, and self-intersection / curvature / clearance bounding constraints from `cloudform.py`.
3. **`touching` Reconstruction & Performance Resolution Order (`DefaultSvgRenderer.kt`)**:
   - Integrated `resolvePerformanceScore` into `DefaultSvgRenderer` preprocessing pipeline, enforcing region placement (`resolveAtRegion`) prior to relation resolution (`resolveRelation`: `touching`, `along`, `cutting`, `between`, `not_touching`) to match server v1.94 ordering.
   - Synchronized contact-preserving minor arc reconstruction via `minorArcDelta` and `arcFromEndpointsAndSagitta`.

### Verification

XML test result aggregation (`app/build/test-results/testDebugUnitTest/*.xml`) confirms all 45 unit tests pass 100% (including all 10 reference SVG structural/class parity checks, non-band rotring behavior, and cloudform determinism).
`render_engine_version` remains `"10"`.
`gradle :app:assembleDebug` succeeds, incrementing `android/BUILD_NUMBER` to `148078`. `android/VERSION` remains `2.0.0-android.1`.

## 2026-07-23 web/server v2 Alignment Phase 2g′ (Cloudform, Arc Geometry Flags, Touching Sagitta & Reference SVG Parity)

In accordance with contract `antigravity-android-phase2-renderer.md` §8 Phase 2g′, parity alignment between Python reference implementation (`renderer_cloudform_and_relations.json` and reference SVGs 11–14: `11_cloudform_pencil.svg`, `12_cloudform_rotring.svg`, `13_touching_arcs.svg`, `14_region_then_relation.svg`) and the Android rendering engine was executed.

### Implementation & Parity Details

1. **Minor Arc Geometry Alignment (`ServerRendererGeometry.kt`)**:
   - Synchronized `arcPathD` formula with Python server `renderer.py:3493-3504` (`minorArcDelta` and `sweep = 0` if `delta > 0.0` else `1`).
   - Consolidated `energyLateral` lookup to `GRAMMARS[weight]` constant table.
2. **Hand Stroke, ID Hierarchy & `touching` Orientation (`DefaultSvgRenderer.kt`)**:
   - Fixed Y-coordinate subtraction sign (`cy - r * sin(rad)`) in `performedArcSagitta` and `canvasEndpointGeometry` for screen coordinates, resolving `touching` arc curvature inversion.
   - Appended `<path class="cloudform contour-v1 stroke-engine-touch" ...>` attributes for `cloudform` primitives.
   - Emitted top-level `<g id="instruction_...">` and `<g id="mark_...">` hierarchy when `svgProfile == "editable"`.
3. **Test Infrastructure (`ServerRendererCloudformAndRelationsTest.kt`)**:
   - Updated regex pattern `d="([^"]+)"` to `\bd="([^"]+)"` to eliminate false attribute matches on `<metadata id="...">`.
   - Injected `render_seed` into `score` object in `renderFromIndexEntry`.

### Verification

All 54 unit tests pass 100% via `gradle :app:testDebugUnitTest --rerun-tasks`.
`gradle :app:assembleDebug` succeeds, incrementing `android/BUILD_NUMBER` to `148079`. `android/VERSION` remains `2.0.0-android.1`.

## 2026-07-24 web/server v2 Alignment Phase 2g″ (Cloudform Normal Direction Sign, Test Tolerance Tightening & 2g′ Doc Correction)

In accordance with contract `antigravity-android-phase2-renderer.md` §8 Phase 2g″ (Remanded Revision), the cloudform contour normal vector sign condition was fixed, and test tolerances were tightened to exact requirements.

### Implementation & Remediation Details

1. **Cloudform Normal Direction Sign Fix (`ServerRendererGeometry.kt:881`)**:
   - Inverted the normal direction reversal condition from `if (nx * towardCenterX + ny * towardCenterY > 0)` to `if (nx * towardCenterX + ny * towardCenterY < 0)` (matching `server/cloudform.py:229`). This fixed waist displacements to deform inward (waist/concave) rather than expanding outward (convex).
2. **`DefaultSvgRenderer` Cloudform Seed Derivation (`DefaultSvgRenderer.kt:327`)**:
   - Updated `performanceSeed` argument in `generateCloudformContour` from `renderSeed` directly to `seedForInstruction(ins, renderSeed)`.
3. **Test Tightening & Negative Failure Proof (`ServerRendererCloudformAndRelationsTest.kt`)**:
   - Removed `0.05` tolerance in `testCloudformContourParity`, enforcing `1e-9` point tolerance and exact `<path d>` string equality across all 14 cases.
   - Added exact `<path d>` equality checks for `11_cloudform_pencil.svg` and `12_cloudform_rotring.svg` in `testReferenceSvgParity11To14`.
   - Verified that prior to the sign fix, the tightened assertions failed as expected on `testCloudformContourParity` (hair-plain Point 11: `expected:<0.531388453> but was:<0.53138964464791>`) and `testReferenceSvgParity11To14` (`11_cloudform_pencil` path d mismatch).
4. **Documentation Correction**:
   - Corrected SVG filenames (`11_cloudform_pencil.svg`, `12_cloudform_rotring.svg`, `14_region_then_relation.svg`) and parity scope descriptions in the Phase 2g′ section.

### Verification

- `render_engine_version` remains `"10"`.
- XML test aggregation (`app/build/test-results/testDebugUnitTest/*.xml`) confirms 54 unit tests across 12 files pass 100%.
- `gradle :app:assembleDebug` incremented `android/BUILD_NUMBER` to `148080`. `android/VERSION` remains `2.0.0-android.1`.

## 2026-07-24 web/server v2 Alignment Phase 3a (Stage 1.5 Expander Core, Profile, Composition Family & Deterministic Selection)

In accordance with contract `antigravity-android-phase3-expander.md` §8 Phase 3a, the Stage 1.5 DDL expander core (`_expand_ja` / `_expand_en`), filter profiles, dynamic focus replacement, category planning, candidate selection, and composition family application were ported to Android.

### Implementation & Parity Details

1. **Expander Core & Filter Profiles (`WebDdlExpander.kt`)**:
   - Expanded parameter signature for `expandIntermediateDdl` to accept future Phase 3b/3c/3d parameters (`tenkei`, `focus`, `variationAmplitude`, `variationSeed`, `variationReport`, `enablePlugins`, `pluginInstructionsPresent`).
   - Ported deterministic profile resolution (`_profile_ja` / `_profile_en`) for `intensity`, `tags`, and `mode`.
   - Replaced static center keywords in DDL (`画面中央`, `near the center`, etc.) with hash-derived focus ids (`_reframe_static_center_ja` / `_reframe_static_center_en`).
2. **Deterministic Candidate Selection & Hash Parity**:
   - Implemented Python `_seed`-compatible SHA-256 Big-Endian 64-bit unsigned integer (`ULong`) hashing function.
   - Fixed 64-bit unsigned integer string formatting using `java.lang.Long.toUnsignedString` for `varySeed` to prevent values >= 2^63 from printing negative values.
   - Synchronized category counts (`_category_plan`, `_cap_category_plan`), deterministic selection (`_select_category`, `_category_pool`, `_pick`), and composition family text rewrite (`_apply_composition_family_ja`, `_apply_composition_family_en`).
3. **Phase 3a Corpus Test Infrastructure (`WebDdlExpanderPhase3aTest.kt`)**:
   - Dynamically loaded reference corpus `ddl_expand.json` and verified exact string equality (`assertEquals`) for the 7 Phase 3a corpus cases (`A-base-ja`, `A-base-en`, `B-context-differs`, `B-context-none`, `B-vary-seed-0`, `B-vary-seed-12345`, `B-vary-seed-9223372036854775809`).

### Verification

- `render_engine_version` remains `"10"`.
- XML test aggregation (`app/build/test-results/testDebugUnitTest/*.xml`) confirms 58 unit tests across 13 files pass 100%.
- `gradle :app:assembleDebug` succeeded, incrementing `android/BUILD_NUMBER` to `148081`. `android/VERSION` remains `2.0.0-android.1`.









## 2026-07-24 web/server v2.4.8 Alignment Phase 2h (Master Grid, Render Engine 11)

Following the contract `antigravity-android-phase2h-master-grid.md`, Android now writes
every number on the **master grid** that web/server declared at engine 11: six decimal
places, fixed. **No geometry changed. Only the places that turn a number into a string.**

### Implementation

1. **Declaring the grid (`ServerRendererGeometry.kt`)**:
   - `MASTER_GRID_DECIMALS = 6` as a constant; `fmt` moves from `"%.3f"` to
     `"%.${MASTER_GRID_DECIMALS}f"` with an explicit `Locale.US`. **Trailing zeros are kept.**
   - `-0.000000` collapses to `0.000000`, matching the signed-zero case that
     `master_grid.py` handles explicitly on the server.
2. **Removing the duplicate (`DefaultSvgRenderer.kt`)**:
   - `fmt3` was an identical second implementation and is gone. **A duplicate lets a
     missed call site pass in silence.**
   - `class="hatch-spacing-%.3f"` stays at three digits: it is an identifier, not a
     coordinate (same as `renderer.py:2190`).
3. **Forcing the grid at one point (`DefaultSvgRenderer.kt`)**:
   - `applyMasterGrid` runs once over the assembled SVG, mirroring
     `renderer.py::_apply_master_grid`, with the same three exempt attributes
     (`version` / `class` / `id`).
   - **Kotlin's `Double.toString()` emits exponent forms such as `1.0E-5`** when a value
     is interpolated directly, so without this pass those numbers would sit off the grid.
4. **Stroke coordinates (`ServerStrokeEngine.kt`)**: `formatCoord` drops
   `BigDecimal.setScale(3, HALF_EVEN)` in favour of `ServerRendererGeometry.fmt`, so
   `path d` lands on the same grid.
5. **Cloudform contours (`ServerRendererGeometry.kt`)**: `closedCatmullRomPath` keeps a
   local three-digit format because **the server quantises there too**
   (`cloudform.py:134,143`); `applyMasterGrid` then pads it to six. Writing six digits
   directly here would diverge from the server by one digit.
6. **Version claim**: `render_engine_version` moves from `"10"` to `"11"`.

### Verification

- Counting `app/build/test-results/testDebugUnitTest/*.xml` by hand: **61 tests,
  0 failures, 0 errors** (58 baseline + 3 discriminating). All 12 tests that were red at
  the start are green, and **not one of their assertions was rewritten**.
- **Each discriminating test was shown to fail under a targeted perturbation**:
  (1) `MASTER_GRID_DECIMALS` 6 -> 5 fails `testEveryEmittedNumberSitsOnMasterGrid`;
  (2) gridding integers as well fails `testIntegersRemainIntegers`;
  (3) dropping `Locale.US` fails `testLocaleIndependence`.
- **Formatting fidelity measured**: `String.format(Locale.US, "%.6f", v)` was compared
  against `BigDecimal(v).setScale(6, HALF_EVEN)` — which is what Python's `f"{v:.6f}"`
  means — over two million random values in 0..1000, with **zero mismatches**. Within
  that range the JVM formatter does not diverge from Python.
- `android/VERSION` stays `2.0.0-android.1` and `android/BUILD_NUMBER` stays `148081`.
  Only `android/` changed; server, web, cli and shared are untouched.

## 2026-07-24 web/server v2 Alignment Phase 3b (Stage 1.5 Variation Alignment)

In accordance with contract `antigravity-android-phase3-expander.md` §8 Phase 3b, the Stage 1.5 variation feature (`build_variation_plan`, `_variation_ranked_axes`, `_variation_base_offset`, `_shift_*`, `_apply_count_axes`, `_variation_moved_axes`, `_resolve_focus_id`) was fully ported to Android.

### Implementation & Parity Details

1. **Variation Structure & Constants (`WebDdlExpander.kt`)**:
   - Ported `VariationPlan` data class, amplitude ranks (`small`, `medium`, `large`), 7 axes (`type_swap`, `count`, `touch`, `focus`, `color`, `composition`, `type_family`), tier definitions, and amplitude axis range mappings.
   - Deterministic plan generation implemented via `buildVariationPlan`, `variationRankedAxes`, and `variationBaseOffset`.
2. **Unsigned 64-bit Hash Key Consistency**:
   - Standardized seed string key generation (e.g. `$amplitude:${java.lang.Long.toUnsignedString(seed)}`) using `java.lang.Long.toUnsignedString` to prevent unsigned 64-bit integers >= 2^63 from printing negative values and causing key misalignment.
3. **Effective Variation Plan & Decision Point Shifts**:
   - Ported `effectiveVariationPlan` to dynamically verify actual output string diffs and fall back or shift axes deterministically.
   - Applied shifts at decision points (`AXIS_COLOR`, `AXIS_TOUCH`, `AXIS_COMPOSITION`, `AXIS_TYPE_SWAP`, `AXIS_COUNT`, `AXIS_TYPE_FAMILY`, `AXIS_FOCUS`) via `shiftChoice`, `shiftCategoryCount`, `shiftCategoryFamily`, and `resolveFocusId`.
4. **Dynamic `variation_report` Generation**:
   - Implemented `variationMovedAxes` to record only axes that caused visible output changes, populating `moved_axes` and `resolved_focus` in `variationReport`.
5. **Phase 3b Corpus Test Suite (`WebDdlExpanderPhase3bTest.kt`)**:
   - Automated testing against 16 Phase 3b corpus cases (`A-variation-*` 8 cases, `B-variation-*` 3 cases, `B-focus-*` 5 cases) in `ddl_expand.json`, verifying exact output string matching (`assertEquals`) and `variation_report` parity.

### Verification

- `render_engine_version` remains `"11"`.
- XML test aggregation (`app/build/test-results/testDebugUnitTest/*.xml`) confirms 62 unit tests pass 100% (0 failures, 0 errors).
- `gradle :app:assembleDebug` succeeded, incrementing `android/BUILD_NUMBER` to `148082`. `android/VERSION` remains `2.0.0-android.1`.


## 2026-07-25 web/server v2 Catch-up Phase 3d (Built-in Nature Plugin Expansion)

Per contract `antigravity-android-phase3-expander.md` §8 Phase 3d, the built-in nature
plugin expansion (`Nature.風` / `Nature.うねり` / `Nature.無風` and the English spellings
`wind` / `undulation` / `stillness` / `calm`) was ported to Android.

### Implementation Details

1. **Nature Plugin Regex and Term Extraction (`WebDdlExpander.kt`)**:
   - Defined `NATURE_PLUGIN_RE` (`Nature.(風|うねり|無風|wind|undulation|stillness|calm)`) and
     `naturePluginTerms`, which deterministically maps the matched keywords onto the category
     tag set `"wind"`, `"undulation"`, `"stillness"`.
2. **Sentence Removal and Macro Composition**:
   - `dropNaturePluginSentences` removes every sentence matching `NATURE_PLUGIN_RE` and
     recomposes the remainder with the language-appropriate terminator handling (`joinSentences`).
   - `applyNaturePluginMacros` deterministically inserts the natural-language macro that
     corresponds to the extracted tags and the language.
3. **Wiring into the Expansion Entry Point**:
   - `expandIntermediateDdl` calls `applyNaturePluginMacros` at its head (right after `sanitized`
     is produced), expanding only when `enablePlugins=true` and passing the text through untouched
     when it is `false`. This matches the server order
     (sanitize → avoid gray background → nature macros).
4. **Phase 3d Corpus Tests (`WebDdlExpanderPhase3dTest.kt`)**:
   - Verified exact output string equality (`assertEquals`) against the three Phase 3d cases of the
     reference corpus `ddl_expand.json` (`A-plugin-enabled`, `B-plugin-instructions-present`,
     `A-plugin-disabled`).
   - Added `testNaturePluginMacroSensitivityToAvoidTautology`, which asserts that the output for
     `A-plugin-enabled` changes when `enablePlugins=false`, so the corpus test cannot pass vacuously.

### Verification

- `render_engine_version` remains `"11"`; this phase is Stage 1.5 and does not touch the drawing layer.
- XML test aggregation (`app/build/test-results/testDebugUnitTest/*.xml`) confirms 64 unit tests pass
  (62 existing + 2 new), 0 failures, 0 errors, 0 skipped.
- `gradle :app:assembleDebug` succeeded, incrementing `android/BUILD_NUMBER` to `148083`.
  `android/VERSION` remains `2.0.0-android.1`.

## 2026-07-25 render engine 12 Catch-up Phase 4a (De-regularization of `ServerStrokeEngine`)

Per contract `antigravity-android-engine12.md` §4a, the de-regularization of `ServerStrokeEngine.kt` (envelope replacement, addition of `gesture` to `ToolGrammar`, centerline gesture synthesis, length-based correction events, addition of `wild` parameter) and `ServerStrokeEngineTest.kt` parity updates were completed.

### Implementation Details

1. **ToolGrammar & Tool Extensions (`ServerStrokeEngine.kt`)**:
   - Added 10th field `gesture: Double` to `ToolGrammar` and updated all 10 tool grammars with engine 12 values.
   - Defined `WILD_GAIN = 3.5` and `GESTURE_EDGE = 0.16`.
2. **De-regularization Primitive Functions**:
   - `smoothNoiseSalted`: 4th hash noise stream using explicit salt and frequency parameters.
   - `edgeWindow`: Raised-cosine endpoint window (replacing fixed central sine bulge `max(0, sin(pi t))`).
   - `swell`: Low-frequency modulation of maximum width position.
   - `gestureWave`: Low-frequency 2D centerline wander wave.
3. **Stroke Synthesis Updates (`synthesizeStroke`, `synthesizeAlong`)**:
   - Added `wild: Boolean = false` to `synthesizeStroke` to scale `gestureAmp`.
   - Replaced envelope with `edgeWindow(t) * swell(t, seed)` (`synthesizeAlong` closed loops use `swell(t, seed)`).
   - Changed `correction` event amplitude perturbation from sample index modulo `i % 5` to length-based `correction-kick` hash.
4. **Unit Tests & Mutation Verification (`ServerStrokeEngineTest.kt`)**:
   - Updated parity tests (`testPrimitivesParity`, `testSynthesizeStrokeParity`, `testSynthesizeAlongParity`) for engine 12 primitive samples, constants, and `wild` option.
   - Added `testWildPairingDivergenceAndIdentity` to verify `rotring` identity and `pencil` divergence under `wild`.
   - Verified mutation response: introducing `1e-6` offset to `swell` causes all 3 target parity tests to fail as expected.

### Verification

- `render_engine_version` remains `"11"` (to be bumped to `"12"` at the final commit of 4c).
- XML test aggregation (`app/build/test-results/testDebugUnitTest/*.xml`) confirms 64 out of 65 unit tests pass, 1 failure (SVG structure parity, resolved in 4b), 0 skipped. `ServerStrokeEngineTest` passes 5/5 (100%).
- Changes restricted to `android/`.

## 2026-07-25 render engine 12 Catch-up Phase 4b (Material Outline Layer Port & Full Parity)

Per contract `antigravity-android-engine12.md` §4b, the material outline layer (replacing `<line>` elements with `<polyline class="material-outline">`, gesture centerline tracking, variable dasharray generation, wandering offset, non-uniform specks) was fully ported to the Android renderer.

### Implementation Details

1. **Material Outline Layer Extensions (`ServerRendererMaterial.kt`)**:
   - Ported `valueNoise1d` (1D value noise) and `hash01` (SHA-256 4-byte uint) random stream generators.
   - Implemented `offsetPolyline` (tracking gestured centerline) and `variedDashPattern` (spanning line without repeating cadence).
   - Migrated straight line texture rendering from 3 `<line>` elements to 3 `<polyline class="material-outline">` elements.
2. **Renderer Wiring (`DefaultSvgRenderer.kt`)**:
   - Connected `materialCenterline` (gestured stroke samples) from `renderHandStroke` to `ServerRendererMaterial.lineGroup`.
   - Maintained `rotring` (`05_circle_rotring`) and cloudforms (`11_cloudform_pencil`, `12_cloudform_rotring`) as clean geometric primitives, maintaining byte-level identity.
3. **Full Parity for Reference SVG Test Suite**:
   - All 11 reference SVG tests that failed at baseline (including `testAllReferenceSvgStructureParity` and `testReferenceSvgParity11To14`) returned to 100% green.
   - Verified `class="material-outline"` appears strictly on `<polyline>` elements and never on `<line>` elements.

### Verification

- `render_engine_version` remains `"11"` (to be bumped to `"12"` at 4c final commit).
- XML test aggregation (`app/build/test-results/testDebugUnitTest/*.xml`) confirms 65 out of 65 unit tests pass (100% PASS / 0 failures / 0 errors / 0 skipped).
- `gradle :app:assembleDebug` succeeded, incrementing `android/BUILD_NUMBER` to `148085`.

## 2026-07-25 render engine 12 Catch-up Phase 4c (Wild Wiring & Engine Version 12 Promotion)

Per contract `antigravity-android-engine12.md` §4c, the `wild` flag wiring (`line` primitive only) and `render_engine_version` promotion to `"12"` were completed.

### Implementation Details

1. **`wild` Flag Pipeline Wiring (`DefaultSvgRenderer.kt`)**:
   - Read `render_wild` / `wild` from `score` JSON and wired it through `renderInstruction` → `renderHandStroke` → `ServerStrokeEngine.synthesizeStroke(..., wild = wild)`.
   - Scoped strictly to `line` primitives, ensuring closed contours, hatches, and arcs remain unaffected.
2. **`render_engine_version` Promotion**:
   - Promoted `render_engine_version` in `DefaultSvgRenderer.kt` metadata from `"11"` to **`"12"`**.
3. **Discriminating Pair Tests (`DefaultSvgRendererPhase2fTest.kt`)**:
   - Added `testWildPairingDivergenceAndIdentity`.
   - Verified that `15_line_brush_wild` diverges from `02_line_brush` (`assertNotEquals`), while `16_circle_pen_wild` maintains **exact byte identity** with `01_circle_pen` (`assertEquals`).

### Verification

- XML test aggregation (`app/build/test-results/testDebugUnitTest/*.xml`) confirms 66 out of 66 unit tests pass (100% PASS / 0 failures / 0 errors / 0 skipped).
- `gradle :app:assembleDebug` succeeded, incrementing `android/BUILD_NUMBER` to `148086`.

## 2026-07-25 render engine 12 Catch-up Phase 4d (rh3 Migration, Room Database & UI Integration)

Per contract `antigravity-android-engine12.md` §4d, the edition ID migration to `rh3`, Room schema extension, and UI toggle integration were completed.

### Implementation Details

1. **Edition ID Migration to `rh3` (`LocalFallbackPipeline.kt`)**:
   - Updated `renderHash` method to `rh3` format.
   - Standardized payload to 7 keys in ascending order (`render_color_catalog_id`, `render_engine_id`, `render_engine_version`, `render_seed`, `render_wild`, `score`, `version`).
   - Verified zero occurrences of `rh2` in the codebase via `grep_search`.
2. **`rh3` Fixed Reference Parity Tests (`ServerScoreParityTest.kt`)**:
   - Updated `testRenderHashParity` to assert all 4 reference expectation strings specified in §3.5:
     - `render_wild` unset: `rh3:44cf760dc769c1e04ea8187d602120401c29cdea58d6a3bcc08ea428179e9694`
     - `render_wild = false`: `rh3:44cf760dc769c1e04ea8187d602120401c29cdea58d6a3bcc08ea428179e9694`
     - `render_wild = true`: `rh3:842f46d67af6a696001f90ccd29367a8b65888cd8ea922e67ecb4d82f7c139e2`
     - `render_wild = false` / engine `"11"`: `rh3:d1b1c9e25a031429e931ae6d8575dbda538bb78e8862a7ace337d2077799e8b6`
3. **Room Schema Extension & Migration (`HistoryItemEntity.kt`, `InkuDatabase.kt`)**:
   - Added `renderWild: Boolean? = null` column to `HistoryItemEntity`.
   - Bumped `InkuDatabase` to `version = 4` and registered `MIGRATION_3_4` (`ALTER TABLE history_items ADD COLUMN render_wild INTEGER`).
4. **UI Toggle Integration (`InkuViewModel.kt`, `InkuApp.kt`)**:
   - Added `renderWild: Boolean = false` state and `setRenderWild` handler to `InkuViewModel`.
   - Added "暴れる（演奏上限の解除） / Wild (unleashed performance)" toggle switch (default OFF) in settings panel.

### Verification

- XML test aggregation (`app/build/test-results/testDebugUnitTest/*.xml`) confirms 66 out of 66 unit tests pass (100% PASS / 0 failures / 0 errors / 0 skipped).
- `gradle :app:assembleDebug` succeeded, incrementing `android/BUILD_NUMBER` to `148087`.

## 2026-07-25 render engine 12 Catch-up Stage 4b′ (re-porting the material outline layer, and exact-match verification of `points` / `stroke-dasharray`)

In accordance with contract `antigravity-android-engine12.md` §9, completed the re-porting of the rejected material outline layer (`<polyline class="material-outline">`) and the exact string comparison tests for the `points` coordinate sequence and the `stroke-dasharray` dash values.

### Implementation and catch-up detail

1. **Straight port and bug fixes in `ServerRendererMaterial.kt`**:
   - Removed the `scale` that was applied twice inside `outlineOffsetPx`, matching the `_outline_offset_px` formula exactly.
   - Corrected the seed stringification in `hash01` to `${seed.toULong()}:$salt:$i` (unsigned uint64, decimal representation).
   - Unified the formatting of `variedDashPattern` (3 decimal places) and `scaleDash` (`fmt`, 6 decimal places) with the Python implementation.
2. **Seed and path propagation fixes in `DefaultSvgRenderer.kt`**:
   - In `renderHandStroke` and `materialLineGroup`, propagated the normalized 64-bit uint64 seed (`seedLong`) derived from `seedForInstruction` as the `instructionSeed` parameter.
   - When a `variation` (tremor or wave) is present, bound the `centerline` (the waved centre line) to `materialCenterline`.
3. **Added exact-match comparison tests for `points` and `stroke-dasharray` (`DefaultSvgRendererPhase2fTest.kt`)**:
   - Added `testMaterialOutlinePointsAndDashArrayExactParity`.
   - For the four cases `02_line_brush`, `09_line_white`, `14_region_then_relation` and `15_line_brush_wild`, verified with `assertEquals` that the `points` coordinate string and the `stroke-dasharray` array of `<polyline class="material-outline">` match the reference SVG exactly.
4. **Mutation testing (discriminating power)**:
   - Confirmed that perturbing the `floor` coefficient `0.0035` in `outlineOffsetPx` by `1e-6` (to `0.003500001`) does make `testMaterialOutlinePointsAndDashArrayExactParity` **FAIL**.

### Verification

- Self-aggregation of `app/build/test-results/testDebugUnitTest/*.xml` shows all 68 unit tests passing (**PASS 68 / Failures 0 / Errors 0 / Skipped 0**).
- `android/BUILD_NUMBER` incremented to **`148088`**.

## 2026-07-26 render engine 14 Catch-up Stage 5a/5b/5c/5d (stroke_engine terms, grid quantization, raster bleed, performed outline, touch vocabulary alignment)

In accordance with contract `antigravity-android-engine14.md`, completed Android implementation catch-up for render engine 14, `rh3` hash verification, and Saijiki touch vocabulary alignment (10 terms).

### Implementation & Adaptation Details

1. **`stroke_engine` Jitter Terms & Grid Quantization (§5a)**:
   - Added `WILD_JITTER_GAIN = 1.35` and `WILD_QUANTIZE_STEP = 0.018` in `ServerStrokeEngine.kt`.
   - Implemented wild jitter amplification and grid quantization (`step = 0.018`) when `wild = true`.
2. **`renderer` Grid, Raster Bleed, & Performed Outline (§5b)**:
   - Defined `gridStepPx` and `RASTER_BLEED_OPACITY = 0.45` in `DefaultSvgRenderer.kt`, adding `<rect class="raster-bleed">` grid background rendering.
   - Added `offsetPerformedPath` and `performedOutline` to `ServerRendererMaterial.kt`, outputting `<path class="performed-outline">` from `renderContourHandStroke` / `renderArcHandStroke` when `wild = true`.
3. **Full Propagation of `wild` Flag & Bump `render_engine_version` to `"14"` (§5c)**:
   - Bumped `render_engine_version` default to `"14"` in `DefaultSvgRenderer.kt` and `LocalFallbackPipeline.kt`.
   - Propagated `wild` flag across contour, fill, arc, and surface vector rendering calls.
4. **Saijiki Touch Display Vocabulary (10 terms) Alignment & `rh3` Hash Verification (§5d)**:
   - Synchronized `saijikiGroups` "てざわり" in `InkuApp.kt` to exactly 10 canonical terms (pencil, pen, rotring, crayon, chalk, thin brush, thick brush, burin, drypoint, computer).
   - Added `computer` weight support in `ServerScoreSchemaJson.kt`, `ServerScoreCoercer.kt`, `ServerScoreSemantics.kt`, and `WebDdlSpec.kt`. Retained `hair` for backward compatibility playback, while completely removing `rope` (`縄`).
   - Verified `rh3` hashes for engine `"14"` in `ServerScoreParityTest.kt`:
     - `render_wild` unset / engine `"14"`: `rh3:49909b323b19dd6931ebe4c417050793671b26fbf0ecfa458b360c9b760b379b`
     - `render_wild = true` / engine `"14"`: `rh3:2e344afb5426b5418763add9a6c23adae3361fb33a74382821fc11c804cc98b0`
     - `render_wild = false` / engine `"12"`: `rh3:44cf760dc769c1e04ea8187d602120401c29cdea58d6a3bcc08ea428179e9694`

### Verification Results

- All 71 unit tests passed cleanly via `gradle :app:testDebugUnitTest` (**PASS 71 / Failures 0 / Errors 0 / Skipped 0**).

## 2026-08-05 Catch-up for the limits becoming settings, Stage 5 (v2.10.0 / android `2.1.4-android.7`)

The bare `240` that `clusterCount()` carried in `LocalFallbackPipeline.kt` now points at a named
constant, **`LITERAL_COUNT_THRESHOLD`**.

- **It was deliberately not pointed at `MAX_EXPANDED_PER_INSTRUCTION`.** Both are 240 at the
  defaults, but they are **different fields on the server** (`literal_count_threshold` and
  `max_expanded_per_instruction`), and aiming at one would assert an identity that does not exist.
- **The `120` and `500` in the same function stay bare.** The `120` equals the server's
  `represented_count_max` but is not the same rule. **Being the same number does not make it the
  same rule.**
- **Android has no settings UI for this.** The on-device pipeline has no settings route, so the
  limits run at their defaults, and it neither sends nor reads the server's `render_limits` — a
  decision, not an omission.
- The server's own `_cluster_count` still carries a bare 240 / 500 / 120 (**[I-136]**). **Android
  went first here, so on this one point the two sides have different shapes.**

### Verification Results

- `gradle :app:compileDebugKotlin` **BUILD SUCCESSFUL** (zero `^e: ` lines).
  **No visual check was made on the Pixel 9.**

## 2026-08-05 A caller that writes to the lineage tables ([I-068] / v2.10.0 / android `2.1.4-android.8`)

The node and edge tables had been ported, but **nothing on the save path ever wrote to them**.
`InkuRepository.saveResult` now writes **one node per save** and **one edge only when a derivation
was declared**.

- **`LineagePlanner.kt` (new) is the pure function that decides what to write**, copied one
  condition at a time from `db.py:2030-2138`. **The decision is made before any row is created, so a
  refusal leaves no history row either.**
- **Three things were added only to copy the conditions**: ① `isTruthy` (Python truthiness; `or {}`
  turns an empty list into `{}`); ② a save that declares a parent but no kind is refused as
  **`invalid lineage derivation kind`**, not as "a parent is required"; ③ `canonicalJson` (the
  recursion of `sort_keys=True`, separators without spaces, `ensure_ascii=False`, and sorting by
  **code point**).
- **The write is node then edge in one transaction** (SQLite's foreign key requires the child node
  first — the same order as the server).
- **The derivation kinds now match the server's sixteen** (they were eleven, in declaration order).
  **The list is read out of the baked fixture.**
- **Two things the server has and Android does not**: the `history_visibility` column (the judgment
  is ported, but **only the `normal` path is reachable on the device**) and a `user_id` column on the
  lineage tables (**one device, one user**, so the server's same-user condition has no counterpart).

### Not yet wired (for whoever touches this next)

**The UI call sites were not wired to pass a parent.** The three entry points on `InkuRepository`
merely have the `LineageDeclaration` parameter; `InkuViewModel` and `InkuApp` still call with the
default. **On a real device today a node is written every time and no edge is ever written.** There
is no UI that shows lineage either.

### Verification Results

- **JVM unit 143 / 0 failures** (38 classes) and **instrumented 21 / 0 failures** (Pixel 9; no
  emulator).
- **All five perturbations aimed at production code, and no stage came out at zero.**
  **Under P2 (cut the wiring) all 143 JVM tests stayed green** and only five instrumented tests went
  red — **a suite of pure functions cannot be the acceptance for a save path.**


## 2026-08-05 The staffage level folded away ([I-139] / android `2.1.4-android.8`, unchanged)

Following the contract `android-folds-away-the-staffage-level.md`, the staffage level
(tenkei) that the server **folded away as an axis** in v2.11.0 (`05c62206`) is gone from
Android too. **The server is the source of truth and Android is the port**, so what was
carried across is not the same *result* but the same *judgement*.

### What was dropped

- **`WebDdlExpander.kt`** — the `tenkei` parameter and the nine conditions counted in
  section 2.2 of the contract. `expandJa` / `expandEn` now **resolve the focus, return
  `reframeStaticCenter*`, and stop.** Focus is the only variation axis left; the six
  others (type swap, count, touch, colour, composition family, type family) and the
  structural / musical / painterly candidate sentences they wrote are gone.
  `contextText` and `varySeed` **remain as parameters but no longer move the output**
  (the server keeps them the same way).
- **`InkuPipeline.kt` / `LocalFallbackPipeline.kt` / `InkuRepository.kt`** —
  `PaintRequest.tenkei` and its hand-off, plus the three signatures of `paint`,
  `interpret` and `composeFromDdl`. **The parameter was removed, not pinned to a default.**
- **`InkuApp.kt` / `InkuViewModel.kt` / `data/model/Tenkei.kt`** — the picker and its
  state. `Tenkei.kt` was deleted outright.

**Android never had a stored column or a wire field for `tenkei`**, so nothing corresponds
to the server-side ruling that keeps the DB column and shows it on old works in developer
mode. No column and no screen were added for the port.

### What was not dropped

**Whatever the server kept was kept.** `DdlFilterProfile`, `DdlFilterCandidate` and `pick`
have no caller after the fold, but the server still carries `_FilterProfile`,
`_FilterCandidate` and `_pick`, so the shapes match. **The client does not decide that its
own way is better.**

### Verification Results

- **JVM unit 156 / 0 failures** (37 classes, 0 skipped). The starting point was 143 with 4
  red. The arithmetic is **143 − 3 (staffage-only tests deleted) + 16 (gates T-1..T-7) = 156**.
- **Instrumented 20 / 0 failures** (Pixel 9; no emulator). One staffage test was removed
  from the starting 21.
- **The six tests named in section 1.3 of the contract were re-pointed, not deleted.** Each
  now asserts something that is true after the fold and false before it, and says so in its name.
- **All 30 reference cases match exactly — but that is a regenerated record, not a property
  test.** The re-bake left only **14 distinct outputs (47%)**, so a port that ignored its
  input would go green on 16 of the 30. **The discrimination is carried by T-2**, the focus control.


## 2026-08-06 The run's colour catalogue is decided in one place ([I-103] / android `2.1.4-android.9`)

**Five places decided which catalogue a run used** — the draw, DDL, demo, batch and
repeated-run paths each read `InkuUiState.selectedCatalogId` on their own. That is why
**the acceptance that shipped with [I-081]** (the removal of the demo path's random pick)
**held nothing**: it asserted against a **private helper of the test's own** that returned the
same field, so **putting the random pick back into production code left all 118 tests green**
([I-103]).

**This follows the server** (§2-4). There, a paint resolves its catalogue through
`_resolved_paint_catalog_id` (`api_core/routers/render.py`) called **once**, and the acceptance
**drives the real `/api/paint` with only `_ask_model` replaced**. Both halves were copied.

### The decider

- **`data/model/CatalogSelection.kt` (new)** — `resolvedCatalogIdForRun` is the one decider, and
  the five call sites in `InkuViewModel` go through it. **The now-unused `kotlin.random.Random`
  import went with them.**
- **One difference from the server is kept**: given an id that is not in the list, **the server
  answers 422 while this client falls back to the default catalogue**, so a setting saved by an
  older build cannot stop the app from drawing. **This is an Android-specific circumstance
  (backward compatibility of stored settings), not a client-side invention.**
- **The server's three modes (`fixed`, `auto`, `random`) do not exist here** — the catalogue is
  the setting, and the demo path's random pick was removed in [I-081]. The KDoc records that
  **should a mode arrive, it belongs inside this function** rather than at a call site.

### Acceptance

- **`ColorCatalogSelectionDeterminismTest`** now drives `resolvedCatalogIdForRun` instead of a
  helper of its own.
- **`CatalogSelectionWiringTest` (new, instrumented)** drives the draw, DDL, demo, batch and
  repeated-run paths **on the device against a real repository**, and **reads the catalogue back
  out of what was saved**. The model provider echoes the prompt it is given: what the server gets
  by monkeypatching a module, this client gets by taking the collaborator as an argument.
- **⚠ Four of the five call sites are covered** — **the draw path's `interpret` argument reaches
  nothing but a log line**, so perturbing it changes no drawing at all (**an argument with no
  consumption point is invisible to any test**; see [I-142]).

### Results

- **JVM unit 159 / 0 failures** (37 classes), from a baseline of 156.
- **Instrumented 25 / 0 failures** (physical Pixel 9), from a baseline of 20.


## 2026-08-06 Seeing that the description travels untouched ([I-134] / android `2.1.4-android.10`)

**[I-114]** removed the `emotionHint` concatenated onto `description`, **but nothing watched the
removal**. **No JVM unit test constructs an `InkuRepository`** (it needs a context and a
database), so **putting the concatenation back into production code turned only 0 of 136 tests
red** (measured 2026-08-05).

### Where it is observable

`description` and `originalText` leave as two fields of one `PaintRequest`, but **they surface in
different places**.

- **`description` becomes the Stage 1 prompt itself** — `LocalFallbackPipeline` sets
  `prompt = request.description` and **wraps it in no template**, so the assertion can be
  **exact equality against the recorded prompt**.
- **`originalText` travels through `PaintResult.originalInput` into
  `history_items.originalInput`.**

### The gate (`DescriptionPassthroughTest`, instrumented)

A **real Room database and a real `InkuRepository`**, with **only the model replaced** — matching
the server, whose description gates are written to run **through the routes, not through the
predicates**.

| | Entry point | What it reads |
|---|---|---|
| T-1 | `paint` | the Stage 1 prompt |
| T-2 | `interpret` | the Stage 1 prompt and **the returned `originalInput`** |
| T-3 | `paint` | the stored `originalInput` |
| T-4 | `composeFromDdl` | the stored `originalInput` |
| T-5 | `renderFromScore` | the stored `originalInput` and `normalizedDdl` |
| T-6 | `paint` × 2 | **the other way round** — two descriptions arrive as two texts, so a constant cannot pass |

### One gate was deliberately not placed

**`composeFromDdl`'s `description` is not gated.** That entry point **takes the DDL as its own
argument and reads `request.description` nowhere**, so **any assertion about it would be green
whatever the repository did** (the shape of **[I-142]**: an argument with no consumption point).
Its `originalText` is observable and T-4 covers it.

### Discriminating power, measured by perturbation

**Four entry points × two fields = eight enforcement points, each perturbed on its own.**

| Enforcement point perturbed | Red |
|---|---|
| `paint.description` | **2** (T-1, T-6) |
| `paint.originalText` | **2** (T-3, T-6) |
| `interpret.description` | **1** (T-2) |
| `interpret.originalText` | **1** (T-2) |
| `composeFromDdl.description` | **0** (no consumption point, as above) |
| `composeFromDdl.originalText` | **1** (T-4) |
| `renderFromScore.description` | **1** (T-5) |
| `renderFromScore.originalText` | **1** (T-5) |

**⚠ `interpret.originalText` was zero at first** — that entry point saves nothing, so the field
surfaces **only in what it returns**. **The perturbation that hit nothing is what exposed the gap
in the acceptance**, and T-2 was extended to cover it.

### Results

- **Instrumented 31 / 0 failures** (physical Pixel 9, from 25).
- **JVM unit 159 / 0 failures** (37 classes, unchanged). **No production code changed.**

## 2026-08-08 The sketch layer (Stage 0.5) reaches the client ([I-138] series 5/5 / android `2.1.4-android.16`)

**The layer that rewrites a description into "the language of things" before Stage 1 reads it is now
on the client too.** The last of the five-part series, ported under the rule that **the server is
canonical and the client is where it is carried to** (development conventions §2-4).

### There are two normalisation functions with the same name

**This is the easiest thing to get wrong in this port.** The server and the web client each hold a
function of **the same name with different behaviour**.

| Function | Origin | On unknown or missing | Role |
|---|---|---|---|
| `normalize_sketch_grain` | server `sketch.py:43` | **`fine`** (rounds to the default) | resolves the grain that was **requested** |
| `normalizeSketchGrain` | web `sketch.ts:82` | **`null`** | reads the grain a stored work **recorded** |

**The port gives them different names** — `Sketches.normalizeGrain` (the server one) and
`Sketches.recordedGrainOf` (the web one). **Comparison against a parent uses the latter. Using the
former inverts both answers.**

| Parent's `sketch_grain` | Control | `recordedGrainOf` (chosen) | `normalizeGrain` (wrong) |
|---|---|---|---|
| `null` (a work older than the column) | `Off` | `null` vs `null` → **replay** | `fine` vs `null` → **grain change** |
| `null` (a work older than the column) | `Fine` | `null` vs `fine` → **grain change** | `fine` vs `fine` → **replay** |

**A work older than the column is not "a work drawn at the default" — it is a work drawn before
there was a grain to record.** `off` carries no grain either, so **absence equals absence, and
redrawing with the layer switched off stays a replay.**

### The sixth state is the absence of a value, not `off`

There are five recorded states (the server's `sketch_state`), but **an empty column carries a sixth
meaning**. `MIGRATION_7_8` **backfills nothing** — backfilling would turn **a work drawn before the
layer into a work drawn with the layer switched off**.

### A fallback row records no sketch prose (**author's ruling 2026-08-08, matching the server**)

The contract asked that a fallback run leave `sketch_text` non-empty, but **the server writes
neither `sketch_text` nor `sketch_grain` on a fallback row** (`render.py:1917-1922`). **What a
fallback carries is the description itself**, and writing that into the sketch column would make
**a work that never passed through the layer indistinguishable from one that did.** **An empty
column with only the state set to `fallback` is the whole reason the state column exists.**

### Sketching is non-deterministic, and reproduction means sending it again

`SketchFromLife.call` **passes no seed**. There is therefore **no test asserting that the same
description and grain sketch the same way twice.** Reproduction works **not by sketching again but
by sending the stored `sketch_text` again** — a redraw whose description and grain both stand still
carries the parent's sketch prose.

### The temperature still diverges from the server ([I-159])

**The sketch layer was set to the server's 0.3, but Android's Stage 1 is 0.2 and Stage 2 is 0.1.**
**That divergence predates the sketch layer** and was not touched here. **It is recorded as pending
a ruling on [I-159].**

## 2026-08-08 Waiting for the write before the close ([I-150] / android `2.1.4-android.17`)

### What was broken

**A save hands the thumbnail write to `thumbnailScope` and does not wait for it.**
`InkuRepository.close()` was one line, `thumbnailScope.cancel()`.
**`cancel()` requests cancellation; it does not wait for it.** A write already inside
`updateThumbnail` keeps running, so when the caller closes the database next,
**the database disappears from under the write.**

**The throw lands on the background coroutine rather than on the caller.** It is therefore
**not recorded as a failing test: the process dies and the remaining tests never run.**
**This shape arrives as "the rest did not run", not as "one test is red",** so it is invisible
unless the XML is counted. **Five of twelve runs were truncated.**

### The fix — join, then tear down

```kotlin
suspend fun close() {
    thumbnailScope.coroutineContext.job.children.toList().joinAll()
    thumbnailScope.cancel()
    localLiteRtProvider.close()
}
```

**⚠ Not `cancelAndJoin`.** Cancelling first abandons the write, so the thumbnail never lands and
**no assertable property is left, which means no gate can be placed.** Joining first means that by
the time `close()` returns, the write is on disk and nothing holds the database.

### Four classes only closed the repository asynchronously

**Twelve** instrumented classes build an `InkuRepository`. **Four**
(`CatalogSelectionWiringTest`, `LineageDeclarationWiringTest`, `LineageScreenTest`,
`SketchLineageWiringTest`) closed it only through
`store.clear()` → `onCleared` → `applicationScope.launch { repository.close() }`,
**and leaned on `delay(500)`.** They now close it directly. **The sleep stays**, because it also
guards the other work the view model starts; for the thumbnail it is now a belt rather than the
guarantee.

### Two gates, on two different surfaces

| T | Surface | What it watches |
|---|---|---|
| T-1 | Instrumented (Pixel 9 hardware) | Save, `close()`, and the row already carries `thumbnail_path`. **A contrast asserts that the save alone does not write it** — without it the assertion would hold vacuously if the save ever finished the thumbnail itself |
| T-2 | The server's pytest | Every `database.close()` is covered by an earlier `repository.close()`. **Stated as a running count rather than as adjacency**, because one class still keeps a settle between the two and the settle is not what is being asserted |

**T-2 lives on the server side because pytest runs in every acceptance cycle while Gradle runs only
in the cycles that touch `android/`.** Four tests already read the Kotlin sources from pytest. It
skips on a missing `android/` (the tree is absent on the deployed server).

### The shipping app never closes the database

**`database.close()` is called only from the instrumented tests.** This is therefore a defect in the
test scaffolding rather than something a user can see; in production the worst case is one lost
thumbnail write as the app goes away. **The production code was still changed, because a `close()`
that does not wait is claiming something untrue.**
---

## 2026-08-08 Naming what the app draws with (UI redesign, stage A / android `2.1.4-android.18`)

**The app can now name its drawing materials by what they are for, not by their value.** Not one
pixel moved.

### Every literal lived in one file

Before the move, the materials **sat as literals inside `ui/InkuApp.kt`** — colours in **89 places
(57 values)**, `.dp` in **429 places (54 values)**, `.sp` in **8 places (5 values)**. Across 5,773
lines, none of those 526 numbers carried the name of a role. `Color(0xFF34302B)` appears four times
as the hairline around a card, and **nowhere said so.**

**The other 68 files held zero literals of all three kinds.** Not because the discipline held, but
because **only one file drew screens.**

### Three files under `ui/theme/`

| file | what it holds |
|---|---|
| `Color.kt` | `InkuColors` (9 roles) plus **65 tokens naming the 57 values by their use** |
| `Dimens.kt` | **new**. The **53 dp values** except `0.dp` (plus 3 aliases) |
| `Type.kt` | The **5 hand-set sp values**, and a record of which M3 steps the screens use |

**Colours are named for their role** — `CardHairline`, not `Ink34302B` — the rule the web side
follows with `--action-bg` / `--accent`. **Two roles that share an ARGB were given two names**
(`background` and `PresentationDarkBackground` are both `0xFF11100F`, but they are **two decisions
that only currently agree**). That is why there are 65 tokens rather than 57: **gaining is normal,
losing is the regression.**

### No value moved

The 53 dp values are not on a 4dp grid — **22 of them sit off it**. **The pull to tidy them is
real, and was not acted on.** If stage A and stage B (the navigation work) both move pixels in the
same round, **there is no way to tell which one moved them** — the same reason the engine versions
are kept on a single line. Pulling the values onto a grid belongs to stage B, where the screens get
rebuilt anyway.

### Zero gets no token

**"No padding" is not a measurement.** The **20** occurrences of `PaddingValues(0.dp)` stay literal,
and **that is the only exception.** (Counting them has a trap: `grep -c '0\.dp'` also matches the
tail of `10.dp` and `20.dp`, which in this file returns 68 false hits against 20 real ones. **Match
the whole literal.**)

### The gates live in the server's pytest

**The extraction happens once; literals come back every round.** Each new screen makes writing
`12.dp` on the spot faster than looking up `Dimens.spaceXl`. **With nothing guarding it, a token
layer is at its most consistent on the day it is built.**

The six checks (T-4..T-9) are in `server/tests/test_android_names_what_it_draws_with.py`. **The
server's pytest runs in every acceptance round; Gradle only runs in rounds that touch `android/`.**
Following the four existing precedents, they skip on the absence of the `android/` **directory**.

**T-7 freezes the zero across every Kotlin file outside `theme/`.** If T-4..T-6 watched only
`InkuApp.kt`, **a round that built a new screen in a new file would sail straight through** — a hole
shaped like guarding one file instead of guarding the rule.

### What goes to Claude Design

`android/design/gen_design_preview.py` reads the three Kotlin token files and bakes
`design/preview/*.html`. **It parses source and needs neither Gradle nor the Android SDK** — **a
generator CI cannot run defeats the point of baking the files at all**, since a check nobody runs
reports a stale preview as green. Each page carries an `@dsCard` marker on its first line, and a
third job in `reference-corpus.yml` **requires byte identity**.

**T-8 is a regenerated record, not a check of a property.** It says nothing about whether the tokens
are right. **That is why it sits paired with T-4..T-7** — one side holds "literals do not come
back", the other holds "the Claude Design copy does not go stale". **Neither one alone is enough.**

## 2026-08-08 Putting the work first (UI redesign, stage B / android `2.1.4-android.19`)

**The work sat in the fourth band of the screen.** The first held model and condition chips, the
second magnification, the third the switch tabs — **seeing what you had drawn always took a scroll.**
Stage A gave the values names; **this stage uses those names to rebuild the layout and the
wayfinding.** Judgement stays server-conformant; what moved is placement and wayfinding.

### Three families

| Family | What | Where |
|---|---|---|
| **Work information** | hash, favourite, lineage, the drawing / Prompt / JSON switch, the way into full screen | around the canvas |
| **Drawing settings** | model, sketch from life, canvas ratio, color catalog, the description/batch switch | one place, directly above the description |
| **Export** | three SVG profiles, PNG template, template editing | one entry → bottom sheet |

**There were three ways into the model selector.** Separate composables each opened the same screen,
so every one of them landed in the same place. **A count of entry points is not a count of choices** —
they were folded into one.

**⚠ `DDL` was not added to the work-information switch.** The contract's family table listed
"drawing / Prompt / JSON / DDL", but DDL is readable from the `interpretation` field and the DDL
editor. **A fourth tab would be adding vocabulary**, so whether to add it is left as a ruling.

### The mascot became a state display

**The condition for showing it is web's `RunStatus` condition — "something is running"** (a single
drawing, a batch, the demo, the DDL editor, the lineage). When nothing runs, the row disappears
entirely. **Choosing the mascot (Incu / Yuragi) stays in settings** — that is a preference, not a
state display.

**`uiMode` (full / simple) means something different now.** The only differences used to be the
mascot and a duplicated chip row, and **this stage removes both, so the distinction was empty.**
Simple now folds away `interpretation` (the DDL field and drawing from DDL). **The contract did not
specify this; it is the implementation's judgement.**

### Viewing gathers in the full-screen view

Pinch 0.25×–10×, pan, double tap to toggle fit ⇄ actual size, back key to leave, and a button in the
top-right corner as the way in. **Zoom in the normal view was removed, condition and all** — vertical
scrolling and a one-finger drag were competing for the same gesture.

**Swipe direction is unified as right = previous, left = next.** Only the full-screen view had it
reversed, so **the same finger movement meant two different things in two states of one screen.**

**Double tap computes "actual size" from the work itself** (SVG `viewBox` width ÷ the width actually
drawn), dropping to 2.0× when the work is already at or beyond actual size — **a double tap that does
nothing reads as broken.**

### The main action sits above the IME

While the description has focus, **Paint is pinned directly above the IME** and the description field
moves upward. **Nothing is bound to the IME action key** — in Japanese input the return key confirms
a conversion, so **the drawing would start on a keystroke meant to confirm text.**

### ⚠ "Visible above the IME" cannot be measured under instrumentation

The contract wrote T-11 as "while the IME is up, Paint **is displayed**". **That form never went
green.**

| What was measured | Result |
|---|---|
| `ComponentActivity` + `setContent { InkuApp() }` | the bar sits at **y=2269** in a 2424px window (behind the keyboard) |
| switching to the shipping `MainActivity` | **same y=2269** |
| waiting on the IME inset via `ViewCompat.getRootWindowInsets` | **same y=2269** |

**Compose pins window insets to 0 while instrumented** (the mechanism that makes tests
deterministic), so `imePadding()` lifts nothing. **The gate stayed red whether the perturbation was
applied or not** — it was measuring the test host, not the product.

**The re-seated form** (author's ruling) is three claims: **① the main action exists exactly once
② it sits outside the scroll ③ the bottom bar has yielded its place.** All three hold with a 0 inset,
and all three fail when the focus wiring is cut. **That it clears the keyboard is evidenced by a
screenshot from the real device** — what instrumentation cannot measure is not restated in a form
instrumentation can and then called settled.

**Two facts that occur only under instrumentation came out of this** (both left as comments in the
test): **a work arriving on the canvas takes focus away from the description**, and **focus travels
through the ViewModel's flow into composition, so `waitForIdle` does not wait for it.**

### Dimensions and type

**Three heights** (56 / 40 / 32), **two corner radii** (card 16dp and pill), **four spacing steps**
(4 / 8 / 16 / 24), **smallest type 12sp**. `Dimens` goes from **56 `Dp` declarations to 41**, and
**literals off the 4dp grid from 22 to 0** (the 1dp hairline is the one exception). **Cross-family
borrowing was undone** as well (`radiusCard = spaceXxl` and friends now carry their own values).

**⚠ Folding the declarations does not fold the call sites.** With the radii apparently reduced to
two, 18 call sites still passed `RoundedCornerShape(Dimens.spaceXs)` and 16 more `(Dimens.spaceM)`,
so **there were really four (4 / 8 / 16 / pill)**. **The gate was extended to count call sites** —
**a check that reads only the token list waves through every way of not using the tokens.**

### Items still carrying no gate

**Where the back key goes, the 48dp touch target, spacing being exactly four steps, and the canvas
being topmost** have **no T in the contract and no observation point in this stage** (they were
confirmed by eye). **The spacing claim can be seated as "the `Dimens` spacing family holds four
values"** — today's T-7 goes no further than the grid.

## 2026-08-22 Representation bands follow device-local integer ratios (android `2.1.4-android.47`, [I-271])

`LocalFallbackPipeline` now computes density boundaries as `3/2` and `2/3` of the representation maximum, and cluster boundaries as `25/6`, `2/1`, and `1/1`. Cluster bands also use integer scaling from the shipping maximum of 120. With the shipping 80–120 pair, density boundaries remain 180/80 and cluster boundaries and values remain 500/240/120 and 9/7/5/3.

Android does not transport server settings, so this stage provides only the deterministic calculation seam for device-local limits. The server's fixed 24-marks-per-cluster cap was excluded by the 2026-08-22 author ruling because it changes shipping output for counts 73–119 from 3 to 4/5. No server-setting synchronization, UI, persistence, network, or API path was added.

## 2026-08-23 Showing each refinement candidate's turn (android `2.1.4-android.48`, [I-348])

While four refinement candidates are being generated, one row keeps a lane for each candidate: completed candidates show a check, the current candidate shows the mascot opposite the selected one, and candidates not yet started show a middle dot. Numbers one through four stay in fixed positions. Android generates candidates sequentially, so only one mascot moves at a time; the row does not imply that Web's parallel fan-out was ported. The row is absent for a single candidate and whenever generation is not busy.

The display is derived only from the existing `refinementCount`, `refinementCandidates.size`, and `refinementBusy` values. No ViewModel, repository, pipeline, rendering, persistence, server, Web, or shared path changed.

## 2026-08-23 Keeping history beside the canvas (android `2.1.4-android.49`, [I-349])

The ordinary Compose screen now places a horizontal strip of existing history thumbnails directly below the canvas. A selection ring marks the current work, taps use the existing history-selection path, and changing the selected work scrolls the strip to its position. The strip is absent with no history, in presentation/full-screen, or when controls are hidden; selection is disabled while drawing or refining.

Only the thumbnail-selection route from Web's `HistoryStrip` is adapted. Android's existing History screen, search, and starred filter remain canonical. No ViewModel, repository, Room query or schema, history count or ordering, replay generation, or persistence changed.

## 2026-08-23 Naming the model in the history strip (android `2.1.4-android.50`, [I-350])

Each history-strip thumbnail now carries the Stage 1 model name already present in its saved summary. The provider prefix is removed and long names use the existing fourteen-character compact rule. Old history with a null or blank model omits the label row entirely instead of reserving empty space.

The I-349 selection ring, tap behavior, scrolling to the selected work, interaction lock during drawing or refinement, and history order are unchanged. No new producer or summary field was added, and no ViewModel, repository, Room query or schema, pipeline, rendering, persistence, server, Web, or shared path changed.

## 2026-08-23 Removing order-dependent guesses from model routing (android `2.1.4-android.51`, [I-351])

A model provider is now resolved in three steps: an explicit prefix naming a configured provider, exact ownership by exactly one enabled provider, then the default-local provider. If multiple providers publish the same model, or none owns it, routing no longer chooses the first list entry and proceeds to default-local. Disabled providers do not count as owners; an explicit prefix naming a disabled provider keeps that identity and stops before execution instead of redirecting elsewhere.

Prefix-like unknown words and colons inside model IDs remain unchanged. OpenAI-compatible requests remove only their own leading provider prefix. No per-stage provider setting, `ModelRequest`, provider catalog, Room schema or migration, pipeline, rendering, persistence, server, Web, or shared path changed.

## 2026-08-23 Starring a work directly in the history strip (android `2.1.4-android.52`, [I-354])

Each thumbnail in the ordinary Compose history strip now has a `★` or `☆` control at its upper-right corner for starring or unstarring the work in place. The Star control is a separate tap target from selecting the thumbnail, so starring does not replace the work shown on the canvas. The existing drawing and refinement lock disables both actions.

The UI uses only the existing `HistoryListItem.starred` state and `toggleStar(HistoryListItem)` action. I-349's selection ring, tap, scrolling, and visibility rules and I-350's model label are preserved. No new state producer, ViewModel action, repository or DAO query, Room schema or migration, persistence, pipeline, rendering, server, Web, or shared path changed.

## 2026-08-23 Copying the visible Prompt or JSON (android `2.1.4-android.53`, [I-355])

The Prompt and JSON tabs on the ordinary Compose screen and the existing Canvas panel now have a `Copy` control. Prompt copies the complete Stage 1 and Stage 2 input and system-prompt text shown on screen; JSON copies the complete rendered-information text shown on screen. Display and clipboard share the same computed string, and no control appears for the `Artwork` tab or with no selected work.

The UI uses only the existing `LocalClipboardManager` and `renderPromptText` or `renderJsonText`. Tab switching, body text, hash copying, export, and canvas messages are preserved. No new ViewModel state or action, producer, generation rule, repository or DAO query, Room schema or migration, persistence, pipeline, rendering, server, Web, or shared path changed.

## 2026-08-23 Reading saved provenance (android `2.1.4-android.54`, [I-356])

The ordinary Compose screen and the existing Canvas panel can now open a read-only `Provenance` sheet for the selected work. Saved sketch state, Stage 1 and Stage 2 models and languages, seeds and variation, color catalog, canvas, render hash and engine, creation time, and elapsed time are arranged under Sketch from life, Interpretation, Performance, Identity, and Run. Null, blank, or malformed render metadata is shown as `—` without crashing the sheet.

The sheet reads only the existing `HistoryItemEntity` and `renderMetadataJson`. Generation, derivation, comments, batch data, and tokens have no current Android producer and were not added. No ViewModel state or action, repository or DAO query, Room schema or migration, persistence, lineage fetch, token collection, SVG analysis, pipeline, rendering, server, Web, or shared path changed.

## 2026-08-23 Showing the color map saved on the work (android `2.1.4-android.55`, [I-357])

The Performance section of the Provenance sheet now includes a `Color map` row. It shows each color word, the code saved in the work's `render_color_map`, and a swatch for that code, ordered by color word. The row is absent when the map is missing or empty or the metadata is malformed. An invalid code falls back to a neutral swatch while its saved string remains visible.

The UI uses only the existing `workColorSnapshot(renderMetadataJson)` and never recalculates the assignment from the current color catalog. No producer, color-code rewrite or normalization, ViewModel state or action, repository or DAO query, Room schema or migration, persistence, SVG analysis, pipeline, rendering, server, Web, or shared path changed.

## 2026-08-23 Showing the color-catalog name saved on the work (android `2.1.4-android.56`, [I-358])

The existing `Color catalog` row in the Provenance sheet now shows a non-blank catalog name from a valid saved color snapshot together with the ID from that same snapshot as `saved name (catalog-id)`. It keeps the prior ID-only display when the name is missing or blank, the snapshot is absent, the map is empty, or the metadata is malformed, and it does not duplicate equal names and IDs.

The UI uses only the existing `workColorSnapshot(renderMetadataJson)` and does not consult current `ColorCatalogs` or a rename table. It does not show `catalogSub`, preserving the Web decision that removed the fixed tagline. No producer, ViewModel state or action, repository or DAO query, Room schema or migration, persistence, pipeline, rendering, server, Web, or shared path changed.

## 2026-08-23 Inspecting both saved models from the history strip (android `2.1.4-android.57`, [I-359])

Long-pressing or pointer-hovering the existing compact Stage 1 label in the ordinary Compose history strip now shows the work's saved Stage 1 and Stage 2 model IDs, including provider prefixes, in a two-line tooltip. A missing Stage 2 value is shown as `—`; a work with no Stage 1 value retains the prior behavior of having neither a label row nor a tooltip target.

The visible fourteen-character Stage 1 label, thumbnail dimensions, work selection, Star control, selected-position scrolling, and interaction lock during drawing or refinement are preserved. The UI uses only the existing `HistoryListItem` and Material tooltip; no new state, model resolver, repository or DAO query, Room schema or migration, pipeline, rendering, server, Web, or shared path changed.

## 2026-08-23 Showing saved time and color-catalog ID in the history-strip tooltip (android `2.1.4-android.58`, [I-360])

I-359's model tooltip now also shows the work's saved time and saved color-catalog ID. The timestamp uses the same ISO-8601 UTC representation as the Provenance sheet and the existing `Created` and `Color catalog` labels. A non-positive or unconvertible timestamp or a blank catalog ID is shown as `—`.

The UI reads only the existing `HistoryListItem.createdAt` and `colorCatalogId` and never looks up a name from the current color-catalog list. I-359's complete model IDs, missing-Stage-2 marker, no-Stage-1 omission, fourteen-character visible label, thumbnail dimensions, work selection, Star, scrolling, and interaction lock are preserved. No new state, repository or DAO query, Room schema or migration, pipeline, rendering, server, Web, or shared path changed.

## 2026-08-23 Showing the work hash and canvas in the history-strip tooltip (android `2.1.4-android.59`, [I-361])

I-360's model tooltip now also shows the work's saved short render hash under the existing `Provenance hash` label with the established `F` prefix and its saved `canvasAspect` under the existing `Canvas` label. A blank value is shown as `—`.

The UI reads only the existing `HistoryListItem.renderHashShort` and `canvasAspect`. It neither loads the full item nor recalculates from current canvas options. I-360's model IDs, saved time, color-catalog ID, no-Stage-1 omission, fourteen-character visible label, thumbnail dimensions, work selection, Star, scrolling, and interaction lock are preserved. No new state, repository or DAO query, Room schema or migration, pipeline, rendering, server, Web, or shared path changed.

## 2026-08-23 Wiring the VersionInfoPanel instrumentation test to product compatibility constants (android `2.1.4-android.60`, [I-318])

`VersionInfoPanelTest` now builds its expected render-engine text from the same `CompatibilityConstants.renderEngineId` and `renderEngineVersion` used by the product instead of retaining the stale literal `default 26`. The test now checks that VersionInfoPanel is wired to the product compatibility values; it no longer independently freezes the current engine number.

No production Kotlin, visible text, Gradle dependency, runner, Espresso stub, persistence format, Room, pipeline, rendering, server, Web, or shared path changed. The first instrumentation attempt failed before the Compose hierarchy because the device screen was off behind the keyguard, so private task I-362 added a read-only display preflight. After unlock, fail-first failed only on the old literal; the same one test passed after implementation and at the branch tip. Every run used the APK-retention flag and a database evacuation, preserving two history rows, two lineage rows, schema version 9, and 1,239 thumbnails. I-064 remains unchanged and open.

## 2026-08-23 Toggling a work Star in place from the history grid (android `2.1.4-android.61`, [I-363])

Every work card in the history screen now keeps a visible `★` or `☆` control at its upper right, reflecting the saved Star state. Tapping that control calls only the existing `toggleStar(HistoryListItem)` path and does not select the card. Existing card taps, long-press Star toggling, selection rings, thumbnails, work titles, search, Star-only filtering, ordering, and counts are preserved.

The change uses only the existing `HistoryListItem.starred`, toggle action, and `HistoryBadge`. It adds no state producer, ViewModel action, repository or DAO query, Room schema or migration, i18n, pipeline, rendering, server, Web, or shared path. The focused JVM test failed before production editing only on the two unresolved references to the planned helper, then passed during implementation and at the branch tip.

## 2026-08-24 Editing saved DDL from a lineage card (android `2.1.4-android.62`, [I-364])

Every lineage card with a normal work now has the existing `DDL edit` action after Elements and before Model. The action can target a card other than the current focus and opens the existing editor with that work's saved `normalizedDdl`. Drawing the edit uses the existing `drawFromDdl` and `ddl_edit` save path, keeps the Lineage tab, then reloads the graph focused on the saved child. Tombstones have no action.

No new editor, producer, repository or DAO query, Room schema or migration, persistence format, i18n, LLM processing, pipeline, rendering, server, Web, or shared path was added. One focused device test covers the card action, editor seed value, `ddl_edit` edge, and child refocus. The test removes only the thumbnail for the render hash it creates after closing the repository; the final evacuation preserved two history rows, two lineage rows, schema version 9, and 1,239 thumbnails.

## 2026-08-24 Toggling a work Star in place from a lineage card (android `2.1.4-android.63`, [I-365])

Every lineage card with a normal work now keeps a visible `★` or `☆` control at the upper right of its thumbnail. The control is a separate tap target from card selection, so starring or unstarring a non-focused card does not change the selected work or lineage focus. Tombstones have no control.

The UI uses only the existing `HistoryItemEntity.starred`, `toggleStar(HistoryItemEntity)`, Star persistence, lineage reload, and `HistoryBadge`. Reloading the graph after persistence updates the same card under the same focus. Existing card taps, thumbnails, generation and state labels, and Elements, DDL, Model, and Language actions are preserved. No new producer, repository or DAO query, Room schema or migration, persistence format, i18n, pipeline, rendering, server, Web, or shared path changed.

## 2026-08-24 Shared Rust drawing engine and raster presentation cutover complete (I-369)

Android stopped following engine versions with its own Kotlin drawing engine and connected the same
`core/crates/inku-render/` used by the server to production rendering. The coarse
`inku-render-android` JNI boundary returns Engine 41 SVG plus metadata in one call, and engine
identity, API versions, and renderer reference come from the same Rust owner.

The separate `inku-svg-raster` crate uses `resvg 0.48.0` to present current and historical SVG as
pixels. Preview, thumbnail, refinement, and PNG export consume canonical saved SVG and never
implicitly replay Score. Kotlin Engine 35, AndroidSVG, and renderer-only corpus/tests were removed.
On Pixel 9, five Engine 41 cases matched SVG bytes, three current plus one historical case matched
host raw-pixel digests, and known color/alpha/stride mapping passed. Score 0.1.0, DDL Engine 20,
Room schema, saved format, `rh3`, app version, and BUILD_NUMBER did not change.

## 2026-08-25 Keeping inku visible in the Pixel 9 launcher with the Web icon (android `2.1.4-android.64`, [I-373])

The ordinary `.MainActivity` retains its existing `MAIN` and `LAUNCHER` entry. inku was absent from the Pixel 9 app list because the package was not installed, so this change adds no activity alias, boot receiver, or persistent service.

The former brush-and-eye launcher design is replaced by the same black, gray, red, green, and blue pixel-grid mark used by Web `favicon-192.png`. The adaptive icon uses a transparent foreground over the Web light background `#f5f3ef`; all five legacy and round density assets use the same mark.

Build 148107 was installed normally on the Pixel 9. User 0 reports the package installed with `hidden=false` and `suspended=false`; launcher resolution returns `app.inku.mobile/.MainActivity`, and a cold start succeeds. The Pixel Launcher app list shows the `inku` label with the new pixel-grid icon. No uninstall, data clear, or instrumentation was performed.
