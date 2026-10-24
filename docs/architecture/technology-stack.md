# Appendix: technology stack

This appendix gives one place to survey the languages, frameworks, main runtime components, and build/test tools that the current implementation uses directly. It follows the 2026-10-24 implementation baseline `086fbe3ea45dd0784b911a7599ef88f60b0c85dc` (v2.15.244 / Build 1320; macOS `1.1.5` / Build 13). This is not a complete list of transitive dependencies. Manifests and lock files remain canonical for versions; the numbers here are an architecture snapshot.

## Runtime components

| Component | Primary language | Framework / library | Responsibility | Canonical source |
|---|---|---|---|---|
| Browser UI | TypeScript, Svelte, HTML/CSS | Svelte 5, SvelteKit 2, CodeMirror 6 (the DDL editor) | SPA for descriptions, images, works, history, lineage, settings, and the view of shared-pipeline executions | `web/package.json`; `web/src/` |
| Web process | JavaScript (build output) | SvelteKit adapter-node, Node.js 22 | Static/UI serving and same-origin `/api` proxy | `web/Dockerfile`; `web/src/hooks.server.ts` |
| Server API | Python 3.12 | FastAPI, Pydantic, Uvicorn | HTTP API, authentication, the shared-pipeline host, the autonomous refinement runner, and operational status | `server/pyproject.toml`; `server/src/inku_server/api.py` |
| Server persistence | Python, SQL | SQLAlchemy 2, SQLite | Canonical schema, domain stores, variation authority, versioned migration, and backup | `server/src/inku_server/persistence/`; `persistence/` |
| Model access | Python / Kotlin / Swift | The Server's `httpx` (shared-pipeline provider effects; the colophon and the juxtaposition sentence choice through `vision_client.py`; the demo instruction; ChatGPT plan authorization and transfer), Android's `HttpURLConnection` and LiteRT-LM, and macOS's URLSession. The shared core's `provider_wire` writes the request bodies and reads the answers | The sketch, color catalog selection, the Stage 1 underdrawing, the composition reading, the laws stage, the color stage, known-hole completion, the color catalog choice, DDL writing and review for an image, the colophon, the juxtaposition, and on-device inference | `server/pyproject.toml`; `server/src/inku_server/pipeline_provider.py`; `server/src/inku_server/vision_client.py`; `core/crates/inku-pipeline/src/provider_wire.rs`; `android/app/build.gradle.kts`; `apple/Packages/InkuHost/Sources/InkuHost/ProviderTransport.swift` |
| Authoring pipeline core | Rust 2024 | `serde` / `serde_json`, `sha2`, `roxmltree`, `unicode-normalization` | Authoring state machine, effect protocol, authority transitions, prompt construction (including the composition, laws, color, and image stages), provider request bodies and answer reading, work identity, the rules of saved-work refinements, compile/render boundary | `core/crates/inku-pipeline/` |
| DDL compiler core | Rust 2024 | `serde` / `serde_json`, `sha2` | Typed compiler, Macros, Stage 1.5, Plan, resource selection, materialization, the underdrawing, and the saijiki asset | `core/crates/inku-ddl/` |
| Score core | Rust 2024 | `serde` / `serde_json`, `sha2` | Score types, canonical digest, compatibility reader, canvas registry, resource authority | `core/crates/inku-score/` |
| Render core | Rust 2024 | `serde` / `serde_json`, `kurbo`, `svgtypes`, `sha2` | Host-independent planning, geometry, marks, surfaces, and SVG | `core/crates/inku-render/` |
| Display core | Rust 2024 | Skia (`skia-safe`, SVG/WebP; feature `skia`), `roxmltree` | Draws saved or current SVG on screen so it looks as it does in the Web's Chrome; a work outside the support table is drawn with resvg | `core/crates/inku-display/` |
| GPU display process | Rust 2024 | Skia Graphite/Metal (feature `graphite`) | Draws the macOS app's zoomed windows in a separate process on Apple silicon | `core/crates/inku-display-gpu/` |
| Byte façade | Rust | UniFFI, Sudachi (`sudachi.rs`) | Pipeline entry points that pass only owned JSON byte buffers. Feature `display` adds the Skia display. On targets other than Android it counts the morae and syllables of a description with the Sudachi dictionary (macOS uses it) | `core/crates/inku-pipeline-uniffi/` |
| Python binding | Rust / Python | PyO3, maturin | Coarse CPython wheel boundary from the Server to the render core and the shared pipeline | `core/crates/inku-render-python/`; `server/Dockerfile` |
| Android binding | Rust / Kotlin | JNI, `resvg`, Skia (feature `display`) | Calls the shared pipeline, the render core, the SVG raster core, and the Skia display from Android | `core/crates/inku-render-android/`; `core/crates/inku-svg-raster/` |
| Android app | Kotlin, Gradle Kotlin DSL | Jetpack Compose, Room 2.8.4, KSP, AndroidX, CameraX | Device UI, the shared-pipeline host, Room history, provider/model management, and in-app capture | `android/app/build.gradle.kts`; `android/app/src/` |
| macOS app | Swift 6, SQL | SwiftUI, Observation, UniFFI, GRDB 7.11.1, system SQLite, URLSession, Keychain, CoreGraphics, WebKit (the 3D viewer) | Native UI, shared-pipeline host, persistence, providers, Skia screen display and zoomed windows, and export | `apple/Package.swift`; `apple/Packages/`; `apple/Sources/` |
| CLI | Python 3.12 | Standard HTTP client, Pillow, `inku-analysis` | Public HTTP API operations, batch, artifact save, and functional testing | `cli/pyproject.toml`; `cli/src/inku_cli/` |
| Shared analysis | Python 3.12 | `resvg-py`, Pillow | Read-only composition mirror, SVG raster/measurement, thumbnails | `shared/pyproject.toml`; `shared/src/inku_analysis/` |
| Distribution | Dockerfile, YAML | Docker Compose, GHCR, GitHub Actions | API/Web images, persistent volume, CI/release | `deploy/compose.yaml`; Dockerfiles; `.github/workflows/` |

## Languages and formats

| Language / format | Main locations | Boundary role |
|---|---|---|
| Python | `server/`, `cli/`, `shared/` | API, pipeline host, provider transport, persistence, CLI, and analysis |
| TypeScript / JavaScript | `web/` | Svelte components, browser state, Node runtime, and unit tests |
| Kotlin / Kotlin DSL | `android/` | Android production code, Compose UI, pipeline host, and Gradle build |
| Swift | `apple/` | Apple native UI, pipeline host, provider transport, GRDB persistence, OS lifecycle |
| Rust | `core/` | Shared authoring pipeline, typed compiler, Score types, render engine, SVG raster, Skia screen display, and CPython/JNI/UniFFI bindings |
| SQL / SQLite DDL | `persistence/`, Server migration, Room export | Portable logical constraints, physical schemas, and migration verification |
| HTML / CSS / Svelte markup | `web/src/` | Browser presentation |
| Markdown / Mermaid | `SPEC*`, `docs/`, manuals, plugin documents | Product contracts, architecture, diagrams, and plugin documents |
| JSON | Score, API, pipeline envelopes and snapshots, saijiki and underdrawing assets, portable contract, fixtures | Structured data boundary between hosts |
| TOML / YAML / KTS | Python/Rust/Android/CI manifests | Dependencies, builds, and workflow settings |
| Shell | `scripts/` | Product build and check entry points. Private operation entry points are in the internal repository. |

## Frameworks and key direct dependencies

### Server / CLI / shared

- FastAPI `>=0.141.1`, Pydantic `>=2.13.4`, and Uvicorn `>=0.52.1`.
- SQLAlchemy `>=2.0.51`. The Server backend is SQLite only; a PostgreSQL adapter is not part of the current support surface. The distributed image pins SQLite to Ubuntu 22.04's `libsqlite3` (3.37.2) and rebuilds only CPython's `_sqlite3` module against its headers (`server/runtime/sqlite.json`).
- `httpx` `>=0.28.1` (provider transport for the shared pipeline), `cryptography` `>=50.0.0`, `PyJWT[crypto]` `>=2.10.1` (ChatGPT plan authorization), `python-dotenv` `>=1.2.2`, Pillow `>=12.3.0`, and `sudachipy` `>=0.6.10` with `sudachidict-small` (the morae and syllables of a description).
- The native wheel (`inku-render-python`) stays out of the Server package's dependency graph and is injected only for image builds and checks.
- `uv_build` builds Python packages; `uv` manages lock and sync.

### Web

- Svelte `^5.55.2`, SvelteKit `^2.57.0`, Vite `^8.0.7`, and TypeScript `^6.0.2`.
- CodeMirror 6 (`@codemirror/state`, `view`, `commands`, `autocomplete`) carries the DDL editor and its completion-range display.
- `@sveltejs/adapter-node` produces the Node bundle. The distributed image runs Node.js 22.
- Browser-side rendering is the boundary; `+layout.ts` sets `ssr = false`.

### Rust / native

- Rust `1.95.0`, edition 2024. The workspace has ten crates: six host-neutral crates — `inku-score`, `inku-ddl`, `inku-pipeline`, `inku-render`, `inku-svg-raster`, and `inku-display` — and four binding/host crates: `inku-pipeline-uniffi`, `inku-render-python`, `inku-render-android`, and `inku-display-gpu`.
- UniFFI `0.32.0` provides the pipeline's byte façade, PyO3 `0.29.2` the CPython 3.12 abi3 wheel, `jni` `0.21.1` direct Android JNI, `resvg` `0.48.1` host-neutral raster presentation, `kurbo` `0.13.1` and `svgtypes` `0.16.1` fill-boundary clipping and path handling, `sha2` `0.11.0` digests, `roxmltree` `0.21.1` SVG reading, and `unicode-normalization` `0.1.25` string normalization.
- Skia is `skia-safe` `=0.153.3`, which only a displaying host enables through a feature. Android's and macOS's CPU display use the published prebuilt binaries (Android's includes Ganesh and Vulkan, but the display draws on CPU raster surfaces and never creates a GPU context); macOS's Graphite/Metal uses a copy built once by `scripts/skia-graphite-binaries.sh`. Both are checked against SHA-256 digests (`skia-binaries.sha256`). The Server build and CI's Rust workspace checks (`cargo test --workspace`) leave Skia out; CI's Android native gate (`checkRustNative`) builds the JNI library with `display` from the verified Android prebuilt.
- The host-neutral crates have no host SDK, DB, network, or provider client. `provider_wire` only writes request bodies and reads answers; the host sends them.

### Android

- Android Gradle Plugin 8.9.1, Kotlin 2.3.0, JVM toolchain 21, compile/target SDK 36, and min SDK 35.
- Jetpack Compose (BOM 2026.04.01), Material 3, Lifecycle/ViewModel, Room 2.8.4, KSP, and CameraX 1.6.2 (in-app capture).
- LiteRT-LM 0.17.1 runs device models. The shared Rust library (a JNI library that includes render, raster, and the Skia display) is built for arm64-v8a with NDK 29.

### macOS

- Swift tools 6.1; the minimum OS is macOS 14/iOS 17. It uses SwiftUI and Observation, GRDB 7.11.1 with system SQLite, and URLSession and Keychain.
- The shared Rust is embedded as a UniFFI XCFramework (feature `display` includes the Skia display), and `inku-display-gpu` is built for arm64 and shipped in the app's `Contents/MacOS/`.
- For description counts, Sudachi small, the reading settings, and CMUdict are hash-verified and copied into InkuHost's resources; the 3D viewer the Web registers is copied unchanged into InkuUI's resources and opened with WebKit.

## Build, test, and quality gates

XcodeGen/Xcode build an arm64/x86_64 Universal macOS app, and the distributed
app is a dmg signed with Developer ID and notarized (versions in `apple/VERSION`
and `apple/BUILD_NUMBER`). Rust is packaged as platform-specific XCFramework
slices. iOS has the shared packages and initial Rust artifacts, with app screens
and camera integration still pending. Python, uv, and Node.js are needed only at
build time, to generate resources from Server-owned source and prepare the fixed
dictionaries, and are not embedded in the app. See the
[build guide and current scope](../../apple/README.md).

| Area | Build / package | Main checks |
|---|---|---|
| Server / CLI / shared | `uv`, `uv_build`, CPython wheel | pytest, Ruff, portable persistence verifier |
| Web | npm, Vite, adapter-node | Node test runner, `svelte-check`, i18n/model lint |
| Rust | pinned rustup/Cargo, maturin, UniFFI | `cargo test`, fmt, clippy, wheel/import smoke, matching binding and protocol versions. Tests that include Skia (`--features skia`, `graphite`) run on macOS |
| Android | Gradle, KSP, Room schema export, NDK | JVM units, Compose/Room instrumentation, device acceptance of the shared pipeline, native parity, Skia display comparison (instrumentation) |
| Swift | SwiftPM, XcodeGen, Xcode, UniFFI/XCFramework | Change-specific core/host/DB checks, AppCheck (including the Skia display and zoomed windows), Universal linking, native UI |
| Documentation | Markdown, Mermaid, JSON | Bilingual checker, link/path checks, portable mapping checks |
| Distribution | Docker Buildx, Compose, GitHub Actions | Multi-architecture image build, health, release gates |

## Intentional non-sharing

- Server, Android, and Swift share the Rust core (authoring pipeline, typed compiler, Score types, render, raster, and provider request bodies and answer reading; Android and macOS also share the Skia screen display) and the logical meaning of portable persistence; they do not share DB files, ORM/DAO code, UI frameworks, or provider transport (the sending).
- Web and the CLI use only the public HTTP API and do not import Server Python modules at runtime.
- Swift, SwiftUI, and GRDB are part of the current stack as the macOS app. iPad/iPhone UI, camera, and real-device acceptance remain unfinished.
- A PostgreSQL compatibility layer, past Render Engine runtimes, and the old Python/Kotlin Stage 1, Stage 1.5, Stage 2, and coerce are not part of the current architecture.
