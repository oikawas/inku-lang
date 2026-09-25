# 付録：技術スタック

この付録は、現行実装が直接使う言語、framework、主要component、build/test toolを1か所で俯瞰する。2026-09-25の実装baseline `46f17da8c5b438511f9bd915395763262b55fb72`を対象とし、transitive dependencyの完全な一覧ではない。版の正本は各manifestとlock fileであり、本書の数字はarchitecture snapshotである。

## 実行component

| Component | 主言語 | Framework / library | 責任 | 正本 |
|---|---|---|---|---|
| Browser UI | TypeScript、Svelte、HTML/CSS | Svelte 5、SvelteKit 2 | 記述、作品、履歴、系譜、設定、共有pipeline実行のview | `web/package.json`; `web/src/` |
| Web process | JavaScript（build output） | SvelteKit adapter-node、Node.js 22 | static/UI配信とsame-origin `/api` proxy | `web/Dockerfile`; `web/src/hooks.server.ts` |
| Server API | Python 3.12 | FastAPI、Pydantic、Uvicorn | HTTP API、認証、共有pipelineのhost、運用status | `server/pyproject.toml`; `server/src/inku_server/api.py` |
| Server persistence | Python、SQL | SQLAlchemy 2、SQLite | 正本schema、domain store、variation authority、versioned migration、backup | `server/src/inku_server/persistence/`; `persistence/` |
| Model access | Python / Kotlin | `httpx`（共有pipelineのprovider effect）、OpenAI SDK・Anthropic SDK（奥書・デモ・Vision）、OpenAI-compatible / Gemini HTTP、LiteRT-LM | 写生、色カタログ選択、Stage 1作品計画、known-hole補完、端末内推論 | `server/pyproject.toml`; `server/src/inku_server/pipeline_provider.py`; `android/app/build.gradle.kts` |
| Authoring pipeline core | Rust 2024 | `serde` / `serde_json`、`sha2` | authoring state machine、effect protocol、authority遷移、prompt構築、compile／render境界 | `core/crates/inku-pipeline/` |
| DDL compiler core | Rust 2024 | `serde` / `serde_json`、`sha2` | typed compiler、Macro、Stage 1.5、Plan、資源選択、materialize、作品計画、歳時記asset | `core/crates/inku-ddl/` |
| Score core | Rust 2024 | `serde` / `serde_json`、`sha2` | Score型、canonical digest、互換reader、canvas registry、資源authority | `core/crates/inku-score/` |
| Render core | Rust 2024 | `serde` / `serde_json`、`kurbo`、`svgtypes`、`sha2` | host非依存のplanning、geometry、mark、surface、SVG | `core/crates/inku-render/` |
| Byte facade | Rust | UniFFI | 所有したJSON byte bufferだけを受け渡すpipeline入口 | `core/crates/inku-pipeline-uniffi/` |
| Python binding | Rust / Python | PyO3、maturin | Serverからrender coreと共有pipelineへの粗いCPython wheel境界 | `core/crates/inku-render-python/`; `server/Dockerfile` |
| Android binding | Rust / Kotlin | JNI、`resvg` | Androidから共有pipeline、render core、SVG raster coreを呼ぶ | `core/crates/inku-render-android/`; `core/crates/inku-svg-raster/` |
| Android app | Kotlin、Gradle Kotlin DSL | Jetpack Compose、Room 2.8.4、KSP、AndroidX | 端末UI、共有pipelineのhost、Room履歴、provider/model管理 | `android/app/build.gradle.kts`; `android/app/src/` |
| CLI | Python 3.12 | 標準HTTP client、Pillow、`inku-analysis` | 公開HTTP API操作、batch、artifact保存、機能検査 | `cli/pyproject.toml`; `cli/src/inku_cli/` |
| Shared analysis | Python 3.12 | `resvg-py`、Pillow | read-only composition mirror、SVG raster/measurement、thumbnail | `shared/pyproject.toml`; `shared/src/inku_analysis/` |
| Distribution | Dockerfile、YAML | Docker Compose、GHCR、GitHub Actions | API/Web image、persistent volume、CI/release | `deploy/compose.yaml`; Dockerfiles; `.github/workflows/` |

## 言語と記述形式

| 言語／形式 | 主な使用場所 | 境界上の役割 |
|---|---|---|
| Python | `server/`, `cli/`, `shared/` | API、pipeline host、provider通信、persistence、CLI、analysis |
| TypeScript / JavaScript | `web/` | Svelte component、browser state、Node runtime、unit test |
| Kotlin / Kotlin DSL | `android/` | Android production code、Compose UI、pipeline host、Gradle build |
| Rust | `core/` | 共有authoring pipeline、typed compiler、Score型、render engine、CPython/JNI binding、SVG raster |
| SQL / SQLite DDL | `persistence/`, Server migration、Room export | portable論理制約、物理schema、migration検証 |
| HTML / CSS / Svelte markup | `web/src/` | browser presentation |
| Markdown / Mermaid | `SPEC*`, `docs/`, manual、plugin document | 製品契約、architecture、図、plugin文書 |
| JSON | Score、API、pipeline envelopeとsnapshot、歳時記・作品計画asset、portable contract、fixture | host間の構造化data境界 |
| TOML / YAML / KTS | Python/Rust/Android/CI manifest | dependency、build、workflow設定 |
| Shell | `scripts/` | 製品の build と検査の entry point。非公開運用 entry point は internal repository にある。 |

## Frameworkと主要direct dependency

### Server / CLI / shared

- FastAPI `>=0.141.1`、Pydantic `>=2.13.4`、Uvicorn `>=0.52.1`。
- SQLAlchemy `>=2.0.51`。Server backendはSQLiteだけで、PostgreSQL adapterは現行support surfaceに含まれない。
- `httpx` `>=0.28.1`（共有pipelineのprovider transport）、OpenAI `>=2.52.0`、Anthropic `>=0.120.2`、`cryptography` `>=50.0.0`、`python-dotenv` `>=1.2.2`、Pillow `>=12.3.0`。
- native wheel（`inku-render-python`）はServer packageの依存graphに入れず、image buildと検査の時だけ注入する。
- `uv_build`でPython packageをbuildし、`uv` lock/syncを使う。

### Web

- Svelte `^5.55.2`、SvelteKit `^2.57.0`、Vite `^8.0.7`、TypeScript `^6.0.2`。
- `@sveltejs/adapter-node`でNode用bundleを作る。配布imageのruntimeはNode.js 22。
- browser-side renderingを境界とし、`+layout.ts`で`ssr = false`を設定する。

### Rust / native

- Rust `1.95`、edition 2024。workspaceは`inku-score`、`inku-ddl`、`inku-pipeline`、`inku-render`、`inku-svg-raster`のhost非依存5 crateと、`inku-pipeline-uniffi`、`inku-render-python`、`inku-render-android`のbinding 3 crateから成る。
- UniFFI `0.32.0`はpipelineのbyte facade、PyO3 `0.29.2`はCPython 3.12 abi3 wheel、`jni` `0.21.1`はAndroid direct JNI、`resvg` `0.48.1`はhost-neutral raster presentation、`kurbo` `0.13.1`と`svgtypes` `0.16.1`は塗りの境界clipとpath処理、`sha2` `0.11.0`はdigestを担う。
- native coreはhost SDK、DB、network、provider clientを持たない。

### Android

- Android Gradle Plugin 8.9.1、Kotlin 2.3.0、JVM toolchain 21、compile/target SDK 36、min SDK 35。
- Jetpack Compose（BOM 2026.04.01）、Material 3、Lifecycle/ViewModel、Room 2.8.4とKSPを使う。
- LiteRT-LM 0.11.0は端末内model実行を担う。共有Rust libraryはarm64-v8a向けにNDK 29でbuildする。

## Build・test・quality gate

| 対象 | Build / package | 主な検査 |
|---|---|---|
| Server / CLI / shared | `uv`, `uv_build`, CPython wheel | pytest、Ruff、portable persistence verifier |
| Web | npm、Vite、adapter-node | Node test runner、`svelte-check`、i18n/model lint |
| Rust | pinned rustup/Cargo、maturin、UniFFI | `cargo test`、fmt、clippy、wheel/import smoke、binding・protocol版の一致 |
| Android | Gradle、KSP、Room schema export、NDK | JVM unit、Compose/Room instrumentation、共有pipelineの端末受入、native parity |
| Documentation | Markdown、Mermaid、JSON | bilingual checker、link/path検査、portable mapping検査 |
| Distribution | Docker Buildx、Compose、GitHub Actions | multi-arch image build、health、release gate |

## 意図した非共有

- ServerとAndroidが共有するのはRust core（authoring pipeline、typed compiler、Score型、render、raster）とportable persistenceの論理意味であり、DB file、ORM/DAO、UI framework、provider transportは共有しない。
- WebとCLIは公開HTTP APIだけを使い、ServerのPython moduleをruntime importしない。
- 将来iOS adapterは設計可能だが、Swift、SwiftUI、iOS DB frameworkは現行stackに含まれない。
- PostgreSQL互換層、過去Render Engine runtime、旧Python / KotlinのStage 1・Stage 1.5・Stage 2・coerceは現行architectureに含まれない。
