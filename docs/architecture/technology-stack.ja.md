# 付録：技術スタック

この付録は、現行実装が直接使う言語、framework、主要component、build/test toolを1か所で俯瞰する。2026-10-24の実装baseline `086fbe3ea45dd0784b911a7599ef88f60b0c85dc`（v2.15.244 / Build 1320、macOS `1.1.5` / Build 13）に合わせた。transitive dependencyの完全な一覧ではない。版の正本は各manifestとlock fileであり、本書の数字はarchitecture snapshotである。

## 実行component

| Component | 主言語 | Framework / library | 責任 | 正本 |
|---|---|---|---|---|
| Browser UI | TypeScript、Svelte、HTML/CSS | Svelte 5、SvelteKit 2、CodeMirror 6（DDLエディタ） | 記述、画像、作品、履歴、系譜、設定、共有pipeline実行のview | `web/package.json`; `web/src/` |
| Web process | JavaScript（build output） | SvelteKit adapter-node、Node.js 22 | static/UI配信とsame-origin `/api` proxy | `web/Dockerfile`; `web/src/hooks.server.ts` |
| Server API | Python 3.12 | FastAPI、Pydantic、Uvicorn | HTTP API、認証、共有pipelineのhost、AI自動推敲のrunner、運用status | `server/pyproject.toml`; `server/src/inku_server/api.py` |
| Server persistence | Python、SQL | SQLAlchemy 2、SQLite | 正本schema、domain store、variation authority、versioned migration、backup | `server/src/inku_server/persistence/`; `persistence/` |
| Model access | Python / Kotlin / Swift | Serverの`httpx`（共有pipelineのprovider effect、奥書と取り合わせの一文選びは`vision_client.py`、デモの指示文、ChatGPTプランの認可と送信）、Androidの`HttpURLConnection`とLiteRT-LM、macOSのURLSession。要求本文と答えの読みは共有coreの`provider_wire`が作る | 写生、色カタログ選択、Stage 1下絵、構図の読み、法則の段、配色の段、known-hole補完、画像からの色カタログ選び・DDLの書き・見比べ、奥書、取り合わせ、端末内推論 | `server/pyproject.toml`; `server/src/inku_server/pipeline_provider.py`; `server/src/inku_server/vision_client.py`; `core/crates/inku-pipeline/src/provider_wire.rs`; `android/app/build.gradle.kts`; `apple/Packages/InkuHost/Sources/InkuHost/ProviderTransport.swift` |
| Authoring pipeline core | Rust 2024 | `serde` / `serde_json`、`sha2`、`roxmltree`、`unicode-normalization` | authoring state machine、effect protocol、authority遷移、prompt構築（構図・法則・配色・画像の段を含む）、providerへの要求本文と答えの読み、作品の同一性、保存作品の推敲の規則、compile／render境界 | `core/crates/inku-pipeline/` |
| DDL compiler core | Rust 2024 | `serde` / `serde_json`、`sha2` | typed compiler、Macro、Stage 1.5、Plan、資源選択、materialize、下絵、歳時記asset | `core/crates/inku-ddl/` |
| Score core | Rust 2024 | `serde` / `serde_json`、`sha2` | Score型、canonical digest、互換reader、canvas registry、資源authority | `core/crates/inku-score/` |
| Render core | Rust 2024 | `serde` / `serde_json`、`kurbo`、`svgtypes`、`sha2` | host非依存のplanning、geometry、mark、surface、SVG | `core/crates/inku-render/` |
| Display core | Rust 2024 | Skia（`skia-safe`、SVG／WebP。feature `skia`）、`roxmltree` | 保存済み／現行SVGをWebのChromeと同じ見え方で画面に描く。照合表の外の作品はresvg | `core/crates/inku-display/` |
| GPU display process | Rust 2024 | Skia Graphite／Metal（feature `graphite`） | macOSの拡大の窓をApple siliconの別processで描く | `core/crates/inku-display-gpu/` |
| Byte facade | Rust | UniFFI、Sudachi（`sudachi.rs`） | 所有したJSON byte bufferだけを受け渡すpipeline入口。feature `display`でSkia表示を含める。Android以外の対象では記述の音数・音節をSudachiの辞書で数える（macOSが使う） | `core/crates/inku-pipeline-uniffi/` |
| Python binding | Rust / Python | PyO3、maturin | Serverからrender coreと共有pipelineへの粗いCPython wheel境界 | `core/crates/inku-render-python/`; `server/Dockerfile` |
| Android binding | Rust / Kotlin | JNI、`resvg`、Skia（feature `display`） | Androidから共有pipeline、render core、SVG raster core、Skia表示を呼ぶ | `core/crates/inku-render-android/`; `core/crates/inku-svg-raster/` |
| Android app | Kotlin、Gradle Kotlin DSL | Jetpack Compose、Room 2.8.4、KSP、AndroidX、CameraX | 端末UI、共有pipelineのhost、Room履歴、provider/model管理、アプリ内の撮影 | `android/app/build.gradle.kts`; `android/app/src/` |
| macOS app | Swift 6、SQL | SwiftUI、Observation、UniFFI、GRDB 7.11.1、system SQLite、URLSession、Keychain、CoreGraphics、WebKit（3Dビューア） | native UI、共有pipeline host、保存、provider、Skiaの画面表示と拡大の窓、書き出し | `apple/Package.swift`; `apple/Packages/`; `apple/Sources/` |
| CLI | Python 3.12 | 標準HTTP client、Pillow、`inku-analysis` | 公開HTTP API操作、batch、artifact保存、機能検査 | `cli/pyproject.toml`; `cli/src/inku_cli/` |
| Shared analysis | Python 3.12 | `resvg-py`、Pillow | read-only composition mirror、SVG raster/measurement、thumbnail | `shared/pyproject.toml`; `shared/src/inku_analysis/` |
| Distribution | Dockerfile、YAML | Docker Compose、GHCR、GitHub Actions | API/Web image、persistent volume、CI/release | `deploy/compose.yaml`; Dockerfiles; `.github/workflows/` |

## 言語と記述形式

| 言語／形式 | 主な使用場所 | 境界上の役割 |
|---|---|---|
| Python | `server/`, `cli/`, `shared/` | API、pipeline host、provider通信、persistence、CLI、analysis |
| TypeScript / JavaScript | `web/` | Svelte component、browser state、Node runtime、unit test |
| Kotlin / Kotlin DSL | `android/` | Android production code、Compose UI、pipeline host、Gradle build |
| Swift | `apple/` | Apple native UI、pipeline host、provider通信、GRDB保存、OS lifecycle |
| Rust | `core/` | 共有authoring pipeline、typed compiler、Score型、render engine、SVG raster、Skiaの画面表示、CPython/JNI/UniFFI binding |
| SQL / SQLite DDL | `persistence/`, Server migration、Room export | portable論理制約、物理schema、migration検証 |
| HTML / CSS / Svelte markup | `web/src/` | browser presentation |
| Markdown / Mermaid | `SPEC*`, `docs/`, manual、plugin document | 製品契約、architecture、図、plugin文書 |
| JSON | Score、API、pipeline envelopeとsnapshot、歳時記・下絵asset、portable contract、fixture | host間の構造化data境界 |
| TOML / YAML / KTS | Python/Rust/Android/CI manifest | dependency、build、workflow設定 |
| Shell | `scripts/` | 製品の build と検査の entry point。非公開運用 entry point は internal repository にある。 |

## Frameworkと主要direct dependency

### Server / CLI / shared

- FastAPI `>=0.141.1`、Pydantic `>=2.13.4`、Uvicorn `>=0.52.1`。
- SQLAlchemy `>=2.0.51`。Server backendはSQLiteだけで、PostgreSQL adapterは現行support surfaceに含まれない。配布imageのSQLiteはUbuntu 22.04の`libsqlite3`（3.37.2）に固定し、CPythonの`_sqlite3`だけをそのheaderで作り直す（`server/runtime/sqlite.json`）。
- `httpx` `>=0.28.1`（共有pipelineのprovider transport）、`cryptography` `>=50.0.0`、`PyJWT[crypto]` `>=2.10.1`（ChatGPTプランの認可）、`python-dotenv` `>=1.2.2`、Pillow `>=12.3.0`、`sudachipy` `>=0.6.10`と`sudachidict-small`（記述の音数・音節）。
- native wheel（`inku-render-python`）はServer packageの依存graphに入れず、image buildと検査の時だけ注入する。
- `uv_build`でPython packageをbuildし、`uv` lock/syncを使う。

### Web

- Svelte `^5.55.2`、SvelteKit `^2.57.0`、Vite `^8.0.7`、TypeScript `^6.0.2`。
- CodeMirror 6（`@codemirror/state`、`view`、`commands`、`autocomplete`）はDDLエディタと補完の範囲の表示を担う。
- `@sveltejs/adapter-node`でNode用bundleを作る。配布imageのruntimeはNode.js 22。
- browser-side renderingを境界とし、`+layout.ts`で`ssr = false`を設定する。

### Rust / native

- Rust `1.95.0`、edition 2024。workspaceは10 crateで、`inku-score`、`inku-ddl`、`inku-pipeline`、`inku-render`、`inku-svg-raster`、`inku-display`のhost非依存6 crateと、`inku-pipeline-uniffi`、`inku-render-python`、`inku-render-android`、`inku-display-gpu`のbinding／host用4 crateから成る。
- UniFFI `0.32.0`はpipelineのbyte facade、PyO3 `0.29.2`はCPython 3.12 abi3 wheel、`jni` `0.21.1`はAndroid direct JNI、`resvg` `0.48.1`はhost-neutral raster presentation、`kurbo` `0.13.1`と`svgtypes` `0.16.1`は塗りの境界clipとpath処理、`sha2` `0.11.0`はdigest、`roxmltree` `0.21.1`はSVGの読み、`unicode-normalization` `0.1.25`は文字列の正規化を担う。
- Skiaは`skia-safe` `=0.153.3`で、表示するhostだけがfeatureで入れる。AndroidとmacOSのCPU表示は公開の事前ビルド（AndroidのものはGanesh・Vulkanを含むが、表示はCPUのraster surfaceで描き、GPU contextを作らない）、macOSのGraphite／Metalは`scripts/skia-graphite-binaries.sh`で一度組んだ写しを使い、どちらもSHA-256を照合する（`skia-binaries.sha256`）。Serverのbuildと、CIのRust workspace検査（`cargo test --workspace`）はSkiaを入れない。CIのAndroid native gate（`checkRustNative`）は、照合したAndroidの事前ビルドで`display`入りのJNI libraryを組む。
- host非依存のcrateはhost SDK、DB、network、provider clientを持たない。`provider_wire`は要求本文を作り答えを読むだけで、送信はhostが行う。

### Android

- Android Gradle Plugin 8.9.1、Kotlin 2.3.0、JVM toolchain 21、compile/target SDK 36、min SDK 35。
- Jetpack Compose（BOM 2026.04.01）、Material 3、Lifecycle/ViewModel、Room 2.8.4とKSP、CameraX 1.6.2（アプリ内の撮影）を使う。
- LiteRT-LM 0.17.1は端末内model実行を担う。共有Rust library（render・raster・Skia表示を含むJNI library）はarm64-v8a向けにNDK 29でbuildする。

### macOS

- Swift tools 6.1、最低OSはmacOS 14／iOS 17。SwiftUIとObservation、GRDB 7.11.1とsystem SQLite、URLSessionとKeychainを使う。
- 共通RustはUniFFIのXCFramework（feature `display`でSkia表示を含む）として組み込み、`inku-display-gpu`はarm64で組んでアプリの`Contents/MacOS/`へ同梱する。
- 記述の音数はSudachi small・読み設定・CMUdictをhash検証してInkuHostのresourceへ写し、Webが登録した3DビューアはそのままInkuUIのresourceへ写してWebKitで開く。

## Build・test・quality gate

macOSアプリはarm64／x86_64 Universal appをXcodeGen／Xcodeで作り、配布物はDeveloper ID署名と公証を受けたdmgである（版は`apple/VERSION`と`apple/BUILD_NUMBER`）。Rustはplatform別XCFrameworkへpackagingする。iOSは共通packageと初期Rust artifactまでで、アプリ画面とcameraは後続。Python・uv・Node.jsは、Server正本からresourceを生成し固定辞書を用意するbuild時だけ必要で、アプリに組み込まない。[build手順と現在の範囲](../../apple/README.ja.md)を参照。

| 対象 | Build / package | 主な検査 |
|---|---|---|
| Server / CLI / shared | `uv`, `uv_build`, CPython wheel | pytest、Ruff、portable persistence verifier |
| Web | npm、Vite、adapter-node | Node test runner、`svelte-check`、i18n/model lint |
| Rust | pinned rustup/Cargo、maturin、UniFFI | `cargo test`、fmt、clippy、wheel/import smoke、binding・protocol版の一致。Skiaを含む試験（`--features skia`、`graphite`）はmacOSで走らせる |
| Android | Gradle、KSP、Room schema export、NDK | JVM unit、Compose/Room instrumentation、共有pipelineの端末受入、native parity、Skia表示の照合（instrumentation） |
| Swift | SwiftPM、XcodeGen、Xcode、UniFFI／XCFramework | 変更に必要なcore・host・DB境界確認、AppCheck（Skia表示と拡大の窓を含む）、Universal link、native画面 |
| Documentation | Markdown、Mermaid、JSON | bilingual checker、link/path検査、portable mapping検査 |
| Distribution | Docker Buildx、Compose、GitHub Actions | multi-arch image build、health、release gate |

## 意図した非共有

- Server・Android・Swiftが共有するのはRust core（authoring pipeline、typed compiler、Score型、render、raster、providerへの要求本文と答えの読み。AndroidとmacOSはSkiaの画面表示も）とportable persistenceの論理意味であり、DB file、ORM/DAO、UI framework、provider transport（送信）は共有しない。
- WebとCLIは公開HTTP APIだけを使い、ServerのPython moduleをruntime importしない。
- Swift／SwiftUI／GRDBはmacOSアプリとして現行stackに含む。iPad／iPhoneアプリのUI・camera・実機受入は未完了である。
- PostgreSQL互換層、過去Render Engine runtime、旧Python / KotlinのStage 1・Stage 1.5・Stage 2・coerceは現行architectureに含まれない。
