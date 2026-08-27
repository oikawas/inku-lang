# Appendix: technology stack

This appendix provides one view of the languages, frameworks, major components,
and build/test tools directly used by the current implementation. It describes
implementation baseline `8c39e5f5aac0fb15c5ca0f859587b4b7eb7367ab` on
2026-08-27, not every transitive dependency. Manifests and lock files remain
canonical; versions here are an architecture snapshot.

## Runtime components

| Component | Primary languages | Frameworks / libraries | Responsibility | Canonical evidence |
|---|---|---|---|---|
| Browser UI | TypeScript, Svelte, HTML/CSS | Svelte 5, SvelteKit 2 | SPA for descriptions, works, history, lineage, and settings | `web/package.json`; `web/src/` |
| Web process | JavaScript build output | SvelteKit adapter-node, Node.js 22 | UI/static serving and same-origin `/api` proxy | `web/Dockerfile`; `web/src/hooks.server.ts` |
| Server API | Python 3.12 | FastAPI, Pydantic, Uvicorn | HTTP API, authentication, pipeline orchestration, operations status | `server/pyproject.toml`; `server/src/inku_server/api.py` |
| Server persistence | Python, SQL | SQLAlchemy 2, SQLite | Canonical schema, domain stores, versioned migration, and backup | `server/src/inku_server/persistence/`; `persistence/` |
| Model access | Python / Kotlin | OpenAI SDK, Anthropic SDK, OpenAI-compatible HTTP, LiteRT-LM | Stages 0.5 / 1 / 2 and on-device inference | `server/pyproject.toml`; `server/src/inku_server/model_settings.py`; `android/app/build.gradle.kts` |
| Render core | Rust 2024 | `serde` / `serde_json` | Host-neutral planning, geometry, marks, surfaces, and SVG | `core/crates/inku-render/` |
| Python render binding | Rust / Python | PyO3, maturin | Coarse one-call CPython wheel boundary from Server to core | `core/crates/inku-render-python/`; `server/Dockerfile` |
| Android render/raster binding | Rust / Kotlin | JNI, `resvg` | Calls shared render and SVG-raster cores from Android | `core/crates/inku-render-android/`; `core/crates/inku-svg-raster/` |
| Android app | Kotlin, Gradle Kotlin DSL | Jetpack Compose, Room 2.8.4, KSP, AndroidX | Device UI, local pipeline, Room history, provider/model management | `android/app/build.gradle.kts`; `android/app/src/` |
| CLI | Python 3.12 | Standard HTTP client, Pillow, `inku-analysis` | Public API control, batch, artifact saving, functional checks | `cli/pyproject.toml`; `cli/src/inku_cli/` |
| Shared analysis | Python 3.12 | `resvg-py`, Pillow | Read-only composition mirrors and SVG raster/measurement | `shared/pyproject.toml`; `shared/src/inku_analysis/` |
| Distribution | Dockerfile, YAML | Docker Compose, GHCR, GitHub Actions | API/Web images, persistent volume, CI, and release | `deploy/compose.yaml`; Dockerfiles; `.github/workflows/` |

## Languages and description formats

| Language / format | Main locations | Boundary role |
|---|---|---|
| Python | `server/`, `cli/`, `shared/` | API, provider integration, persistence, CLI, analysis |
| TypeScript / JavaScript | `web/` | Svelte components, browser state, Node runtime, unit tests |
| Kotlin / Kotlin DSL | `android/` | Android production code, Compose UI, Gradle build |
| Rust | `core/` | Shared render engine, CPython/JNI bindings, SVG raster |
| SQL / SQLite DDL | `persistence/`, Server migration, Room exports | Portable logical constraints, physical schemas, migration verification |
| HTML / CSS / Svelte markup | `web/src/` | Browser presentation |
| Markdown / Mermaid | `SPEC*`, `docs/`, manuals, plugin documents | Product contracts, architecture, diagrams, declarative plugins |
| JSON | Score, API, trace, portable contract, fixtures | Structured data boundary among hosts |
| TOML / YAML / KTS | Python/Rust/Android/CI manifests | Dependencies, builds, and workflows |
| Shell | `scripts/`, `no-git-sync/scripts/` | Guarded build, check, and deployment entry points |

## Frameworks and major direct dependencies

### Server / CLI / shared

- FastAPI `>=0.141.1`, Pydantic `>=2.13.4`, and Uvicorn `>=0.52.1`.
- SQLAlchemy `>=2.0.51`. SQLite is the only Server backend; a PostgreSQL
  adapter is not a current support surface.
- OpenAI `>=2.52.0`, Anthropic `>=0.120.2`, and Pillow `>=12.3.0`.
- Python packages use `uv_build`; locking and synchronization use `uv`.

### Web

- Svelte `^5.55.2`, SvelteKit `^2.57.0`, Vite `^8.0.7`, and TypeScript
  `^6.0.2`.
- `@sveltejs/adapter-node` emits the Node bundle. The distribution runtime is
  Node.js 22.
- Browser-side rendering is the boundary: `+layout.ts` sets `ssr = false`.

### Rust / native

- Rust `1.95`, edition 2024. The workspace contains four crates:
  `inku-render`, `inku-render-python`, `inku-render-android`, and
  `inku-svg-raster`.
- PyO3 `0.29.2` provides the CPython 3.12 abi3 wheel, `jni` `0.21.1` the
  direct Android boundary, and `resvg` `0.48.0` host-neutral raster
  presentation.
- The native core contains no host SDK, database, network, or provider client.

### Android

- Android Gradle Plugin 8.9.1, Kotlin 2.3.0, JVM toolchain 21, compile/target
  SDK 36, and minimum SDK 35.
- Jetpack Compose, Material 3, Lifecycle/ViewModel, Room 2.8.4, and KSP.
- LiteRT-LM 0.11.0 provides on-device model execution. NDK 29 builds the
  shared Rust library for arm64-v8a.

## Build, test, and quality gates

| Area | Build / package | Primary checks |
|---|---|---|
| Server / CLI / shared | `uv`, `uv_build`, CPython wheel | pytest, Ruff, portable persistence verifier |
| Web | npm, Vite, adapter-node | Node test runner, `svelte-check`, i18n/model lint |
| Rust | pinned rustup/Cargo, maturin | `cargo test`, fmt, clippy, wheel/import smoke |
| Android | Gradle, KSP, Room schema export, NDK | JVM unit, Compose/Room instrumentation, native parity |
| Documentation | Markdown, Mermaid, JSON | bilingual checker, link/path checks, portable mapping check |
| Distribution | Docker Buildx, Compose, GitHub Actions | multi-architecture image build, health, release gate |

## Deliberate non-sharing

- Server and Android share the Rust render core and logical portable
  persistence meaning, not a database file, ORM/DAO, or UI framework.
- Web and CLI use only the public HTTP API and do not import Server Python
  modules at runtime.
- A future iOS adapter remains possible, but Swift, SwiftUI, and an iOS
  database framework are not part of the current stack.
- PostgreSQL compatibility and historical Render Engine runtimes are not part
  of the current architecture.
