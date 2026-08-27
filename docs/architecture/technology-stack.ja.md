# 付録：技術スタック

この付録は、現行実装が直接使う言語、framework、主要component、build/test toolを1か所で俯瞰する。2026-08-27の実装baseline `8c39e5f5aac0fb15c5ca0f859587b4b7eb7367ab`を対象とし、transitive dependencyの完全な一覧ではない。版の正本は各manifestとlock fileであり、本書の数字はarchitecture snapshotである。

## 実行component

| Component | 主言語 | Framework / library | 責任 | 正本 |
|---|---|---|---|---|
| Browser UI | TypeScript、Svelte、HTML/CSS | Svelte 5、SvelteKit 2 | 記述、作品、履歴、系譜、設定のSPA | `web/package.json`; `web/src/` |
| Web process | JavaScript（build output） | SvelteKit adapter-node、Node.js 22 | static/UI配信とsame-origin `/api` proxy | `web/Dockerfile`; `web/src/hooks.server.ts` |
| Server API | Python 3.12 | FastAPI、Pydantic、Uvicorn | HTTP API、認証、pipeline統率、運用status | `server/pyproject.toml`; `server/src/inku_server/api.py` |
| Server persistence | Python、SQL | SQLAlchemy 2、SQLite | 正本schema、domain store、versioned migration、backup | `server/src/inku_server/persistence/`; `persistence/` |
| Model access | Python / Kotlin | OpenAI SDK、Anthropic SDK、OpenAI-compatible HTTP、LiteRT-LM | Stage 0.5 / 1 / 2と端末内推論 | `server/pyproject.toml`; `server/src/inku_server/model_settings.py`; `android/app/build.gradle.kts` |
| Render core | Rust 2024 | `serde` / `serde_json` | host非依存のplanning、geometry、mark、surface、SVG | `core/crates/inku-render/` |
| Python render binding | Rust / Python | PyO3、maturin | Serverからcoreへの粗い1-call CPython wheel境界 | `core/crates/inku-render-python/`; `server/Dockerfile` |
| Android render/raster binding | Rust / Kotlin | JNI、`resvg` | Androidから共有render coreとSVG raster coreを呼ぶ | `core/crates/inku-render-android/`; `core/crates/inku-svg-raster/` |
| Android app | Kotlin、Gradle Kotlin DSL | Jetpack Compose、Room 2.8.4、KSP、AndroidX | 端末UI、local pipeline、Room履歴、provider/model管理 | `android/app/build.gradle.kts`; `android/app/src/` |
| CLI | Python 3.12 | 標準HTTP client、Pillow、`inku-analysis` | 公開HTTP API操作、batch、artifact保存、機能検査 | `cli/pyproject.toml`; `cli/src/inku_cli/` |
| Shared analysis | Python 3.12 | `resvg-py`、Pillow | read-only composition mirror、SVG raster/measurement | `shared/pyproject.toml`; `shared/src/inku_analysis/` |
| Distribution | Dockerfile、YAML | Docker Compose、GHCR、GitHub Actions | API/Web image、persistent volume、CI/release | `deploy/compose.yaml`; Dockerfiles; `.github/workflows/` |

## 言語と記述形式

| 言語／形式 | 主な使用場所 | 境界上の役割 |
|---|---|---|
| Python | `server/`, `cli/`, `shared/` | API、provider統合、persistence、CLI、analysis |
| TypeScript / JavaScript | `web/` | Svelte component、browser state、Node runtime、unit test |
| Kotlin / Kotlin DSL | `android/` | Android production code、Compose UI、Gradle build |
| Rust | `core/` | 共有render engine、CPython/JNI binding、SVG raster |
| SQL / SQLite DDL | `persistence/`, Server migration、Room export | portable論理制約、物理schema、migration検証 |
| HTML / CSS / Svelte markup | `web/src/` | browser presentation |
| Markdown / Mermaid | `SPEC*`, `docs/`, manual、plugin document | 製品契約、architecture、図、宣言的plugin |
| JSON | Score、API、trace、portable contract、fixture | host間の構造化data境界 |
| TOML / YAML / KTS | Python/Rust/Android/CI manifest | dependency、build、workflow設定 |
| Shell | `scripts/`, `no-git-sync/scripts/` | build、検査、配備のguard付きentry point |

## Frameworkと主要direct dependency

### Server / CLI / shared

- FastAPI `>=0.141.1`、Pydantic `>=2.13.4`、Uvicorn `>=0.52.1`。
- SQLAlchemy `>=2.0.51`。Server backendはSQLiteだけで、PostgreSQL adapterは現行support surfaceに含まれない。
- OpenAI `>=2.52.0`、Anthropic `>=0.120.2`、Pillow `>=12.3.0`。
- `uv_build`でPython packageをbuildし、`uv` lock/syncを使う。

### Web

- Svelte `^5.55.2`、SvelteKit `^2.57.0`、Vite `^8.0.7`、TypeScript `^6.0.2`。
- `@sveltejs/adapter-node`でNode用bundleを作る。配布imageのruntimeはNode.js 22。
- browser-side renderingを境界とし、`+layout.ts`で`ssr = false`を設定する。

### Rust / native

- Rust `1.95`、edition 2024。workspaceは`inku-render`、`inku-render-python`、`inku-render-android`、`inku-svg-raster`の4 crate。
- PyO3 `0.29.2`はCPython 3.12 abi3 wheel、`jni` `0.21.1`はAndroid direct JNI、`resvg` `0.48.0`はhost-neutral raster presentationを担う。
- native coreはhost SDK、DB、network、provider clientを持たない。

### Android

- Android Gradle Plugin 8.9.1、Kotlin 2.3.0、JVM toolchain 21、compile/target SDK 36、min SDK 35。
- Jetpack Compose、Material 3、Lifecycle/ViewModel、Room 2.8.4とKSPを使う。
- LiteRT-LM 0.11.0は端末内model実行を担う。共有Rust libraryはarm64-v8a向けにNDK 29でbuildする。

## Build・test・quality gate

| 対象 | Build / package | 主な検査 |
|---|---|---|
| Server / CLI / shared | `uv`, `uv_build`, CPython wheel | pytest、Ruff、portable persistence verifier |
| Web | npm、Vite、adapter-node | Node test runner、`svelte-check`、i18n/model lint |
| Rust | pinned rustup/Cargo、maturin | `cargo test`、fmt、clippy、wheel/import smoke |
| Android | Gradle、KSP、Room schema export、NDK | JVM unit、Compose/Room instrumentation、native parity |
| Documentation | Markdown、Mermaid、JSON | bilingual checker、link/path検査、portable mapping検査 |
| Distribution | Docker Buildx、Compose、GitHub Actions | multi-arch image build、health、release gate |

## 意図した非共有

- ServerとAndroidが共有するのはRust render coreとportable persistenceの論理意味であり、DB file、ORM/DAO、UI frameworkは共有しない。
- WebとCLIは公開HTTP APIだけを使い、ServerのPython moduleをruntime importしない。
- 将来iOS adapterは設計可能だが、Swift、SwiftUI、iOS DB frameworkは現行stackに含まれない。
- PostgreSQL互換層と過去Render Engine runtimeは現行architectureに含まれない。
