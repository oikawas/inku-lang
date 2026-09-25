# Appendix: technology stack

This appendix gives one place to survey the languages, frameworks, main runtime components, and build/test tools that the current implementation uses directly. It covers the implementation baseline `46f17da8c5b438511f9bd915395763262b55fb72` of 2026-09-25 and is not a complete list of transitive dependencies. Manifests and lock files remain canonical for versions; the numbers here are an architecture snapshot.

## Runtime components

| Component | Primary language | Framework / library | Responsibility | Canonical source |
|---|---|---|---|---|
| Browser UI | TypeScript, Svelte, HTML/CSS | Svelte 5, SvelteKit 2 | SPA for descriptions, works, history, lineage, settings, and the view of shared-pipeline executions | `web/package.json`; `web/src/` |
| Web process | JavaScript (build output) | SvelteKit adapter-node, Node.js 22 | Static/UI serving and same-origin `/api` proxy | `web/Dockerfile`; `web/src/hooks.server.ts` |
| Server API | Python 3.12 | FastAPI, Pydantic, Uvicorn | HTTP API, authentication, the shared-pipeline host, and operational status | `server/pyproject.toml`; `server/src/inku_server/api.py` |
| Server persistence | Python, SQL | SQLAlchemy 2, SQLite | Canonical schema, domain stores, variation authority, versioned migration, and backup | `server/src/inku_server/persistence/`; `persistence/` |
| Model access | Python / Kotlin | `httpx` (shared-pipeline provider effects), OpenAI SDK and Anthropic SDK (colophon, demo, Vision), OpenAI-compatible / Gemini HTTP, LiteRT-LM | The sketch, color catalog selection, the Stage 1 underdrawing, known-hole completion, and on-device inference | `server/pyproject.toml`; `server/src/inku_server/pipeline_provider.py`; `android/app/build.gradle.kts` |
| Authoring pipeline core | Rust 2024 | `serde` / `serde_json`, `sha2` | Authoring state machine, effect protocol, authority transitions, prompt construction, compile/render boundary | `core/crates/inku-pipeline/` |
| DDL compiler core | Rust 2024 | `serde` / `serde_json`, `sha2` | Typed compiler, Macros, Stage 1.5, Plan, resource selection, materialization, the underdrawing, and the saijiki asset | `core/crates/inku-ddl/` |
| Score core | Rust 2024 | `serde` / `serde_json`, `sha2` | Score types, canonical digest, compatibility reader, canvas registry, resource authority | `core/crates/inku-score/` |
| Render core | Rust 2024 | `serde` / `serde_json`, `kurbo`, `svgtypes`, `sha2` | Host-independent planning, geometry, marks, surfaces, and SVG | `core/crates/inku-render/` |
| Byte façade | Rust | UniFFI | Pipeline entry points that pass only owned JSON byte buffers | `core/crates/inku-pipeline-uniffi/` |
| Python binding | Rust / Python | PyO3, maturin | Coarse CPython wheel boundary from the Server to the render core and the shared pipeline | `core/crates/inku-render-python/`; `server/Dockerfile` |
| Android binding | Rust / Kotlin | JNI, `resvg` | Calls the shared pipeline, the render core, and the SVG raster core from Android | `core/crates/inku-render-android/`; `core/crates/inku-svg-raster/` |
| Android app | Kotlin, Gradle Kotlin DSL | Jetpack Compose, Room 2.8.4, KSP, AndroidX | Device UI, the shared-pipeline host, Room history, and provider/model management | `android/app/build.gradle.kts`; `android/app/src/` |
| CLI | Python 3.12 | Standard HTTP client, Pillow, `inku-analysis` | Public HTTP API operations, batch, artifact save, and functional testing | `cli/pyproject.toml`; `cli/src/inku_cli/` |
| Shared analysis | Python 3.12 | `resvg-py`, Pillow | Read-only composition mirror, SVG raster/measurement, thumbnails | `shared/pyproject.toml`; `shared/src/inku_analysis/` |
| Distribution | Dockerfile, YAML | Docker Compose, GHCR, GitHub Actions | API/Web images, persistent volume, CI/release | `deploy/compose.yaml`; Dockerfiles; `.github/workflows/` |

## Languages and formats

| Language / format | Main locations | Boundary role |
|---|---|---|
| Python | `server/`, `cli/`, `shared/` | API, pipeline host, provider transport, persistence, CLI, and analysis |
| TypeScript / JavaScript | `web/` | Svelte components, browser state, Node runtime, and unit tests |
| Kotlin / Kotlin DSL | `android/` | Android production code, Compose UI, pipeline host, and Gradle build |
| Rust | `core/` | Shared authoring pipeline, typed compiler, Score types, render engine, CPython/JNI bindings, and SVG raster |
| SQL / SQLite DDL | `persistence/`, Server migration, Room export | Portable logical constraints, physical schemas, and migration verification |
| HTML / CSS / Svelte markup | `web/src/` | Browser presentation |
| Markdown / Mermaid | `SPEC*`, `docs/`, manuals, plugin documents | Product contracts, architecture, diagrams, and plugin documents |
| JSON | Score, API, pipeline envelopes and snapshots, saijiki and underdrawing assets, portable contract, fixtures | Structured data boundary between hosts |
| TOML / YAML / KTS | Python/Rust/Android/CI manifests | Dependencies, builds, and workflow settings |
| Shell | `scripts/` | Product build and check entry points. Private operation entry points are in the internal repository. |

## Frameworks and key direct dependencies

### Server / CLI / shared

- FastAPI `>=0.141.1`, Pydantic `>=2.13.4`, and Uvicorn `>=0.52.1`.
- SQLAlchemy `>=2.0.51`. The Server backend is SQLite only; a PostgreSQL adapter is not part of the current support surface.
- `httpx` `>=0.28.1` (provider transport for the shared pipeline), OpenAI `>=2.52.0`, Anthropic `>=0.120.2`, `cryptography` `>=50.0.0`, `python-dotenv` `>=1.2.2`, and Pillow `>=12.3.0`.
- The native wheel (`inku-render-python`) stays out of the Server package's dependency graph and is injected only for image builds and checks.
- `uv_build` builds Python packages; `uv` manages lock and sync.

### Web

- Svelte `^5.55.2`, SvelteKit `^2.57.0`, Vite `^8.0.7`, and TypeScript `^6.0.2`.
- `@sveltejs/adapter-node` produces the Node bundle. The distributed image runs Node.js 22.
- Browser-side rendering is the boundary; `+layout.ts` sets `ssr = false`.

### Rust / native

- Rust `1.95`, edition 2024. The workspace consists of five host-neutral crates — `inku-score`, `inku-ddl`, `inku-pipeline`, `inku-render`, and `inku-svg-raster` — and three binding crates: `inku-pipeline-uniffi`, `inku-render-python`, and `inku-render-android`.
- UniFFI `0.32.0` provides the pipeline's byte façade, PyO3 `0.29.2` the CPython 3.12 abi3 wheel, `jni` `0.21.1` direct Android JNI, `resvg` `0.48.1` host-neutral raster presentation, `kurbo` `0.13.1` and `svgtypes` `0.16.1` fill-boundary clipping and path handling, and `sha2` `0.11.0` digests.
- The native core has no host SDK, DB, network, or provider client.

### Android

- Android Gradle Plugin 8.9.1, Kotlin 2.3.0, JVM toolchain 21, compile/target SDK 36, and min SDK 35.
- Jetpack Compose (BOM 2026.04.01), Material 3, Lifecycle/ViewModel, Room 2.8.4, and KSP.
- LiteRT-LM 0.11.0 runs device models. The shared Rust library is built for arm64-v8a with NDK 29.

## Build, test, and quality gates

| Area | Build / package | Main checks |
|---|---|---|
| Server / CLI / shared | `uv`, `uv_build`, CPython wheel | pytest, Ruff, portable persistence verifier |
| Web | npm, Vite, adapter-node | Node test runner, `svelte-check`, i18n/model lint |
| Rust | pinned rustup/Cargo, maturin, UniFFI | `cargo test`, fmt, clippy, wheel/import smoke, matching binding and protocol versions |
| Android | Gradle, KSP, Room schema export, NDK | JVM units, Compose/Room instrumentation, device acceptance of the shared pipeline, native parity |
| Documentation | Markdown, Mermaid, JSON | Bilingual checker, link/path checks, portable mapping checks |
| Distribution | Docker Buildx, Compose, GitHub Actions | Multi-architecture image build, health, release gates |

## Intentional non-sharing

- The Server and Android share the Rust core (authoring pipeline, typed compiler, Score types, render, raster) and the logical meaning of portable persistence; they do not share DB files, ORM/DAO code, UI frameworks, or provider transport.
- Web and the CLI use only the public HTTP API and do not import Server Python modules at runtime.
- A future iOS adapter is designable, but Swift, SwiftUI, and an iOS DB framework are not part of the current stack.
- A PostgreSQL compatibility layer, past Render Engine runtimes, and the old Python/Kotlin Stage 1, Stage 1.5, Stage 2, and coerce are not part of the current architecture.
