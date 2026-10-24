# システムコンテキスト

WebとCLIはserverのHTTP APIを利用する。AndroidとmacOSはserverを経由せず、端末内のhostから同じ共有Rust coreを呼び（AndroidはKotlinからJNI、macOSはSwiftからUniFFI）、自身のDB（Room、GRDB）へ保存する。記述（Server・Webでは画像も）から可視DDL、Score、SVGまでの意味の判断と、保存作品の推敲の規則は、ServerでもAndroidでもmacOSでも共有Rust coreが所有する。Python／Kotlin／Swift hostが担うのはprovider通信、原子的な保存、UI、host固有の設定解決である。Server DBがserver作品の正本であり、作品ファイル領域は任意の派生保存である。

```mermaid
flowchart LR
    SYS_USER["利用者"]
    SYS_WEB["Web / SvelteKit\nroute shell + feature owners"]
    SYS_CLI["inku-cli"]
    SYS_ANDROID["Android host\nKotlin UI + Room"]
    SYS_MACOS["macOS host\nSwiftUI + GRDB"]
    SYS_API["inku server / FastAPI\npipeline host"]
    SYS_CORE["共有Rust core\npipeline + typed compiler + Render Engine 93"]
    SYS_RASTER["inku-svg-raster / inku-display\nSVG → pixel presentation（resvg・Skia）"]
    SYS_LLM["外部・ローカル LLM provider"]
    SYS_DB[("Server DB / 正本")]
    SYS_FILES[("作品ファイル / 任意の派生")]
    ANDROID_DB[("端末Room DB / Android正本")]
    MACOS_DB[("端末GRDB / macOS正本")]

    SYS_USER -->|"画面操作・記述・画像・DDL・補完案の承認"| SYS_WEB
    SYS_USER -->|"command・prompt・画像"| SYS_CLI
    SYS_USER -->|"端末操作・記述・DDL"| SYS_ANDROID
    SYS_USER -->|"端末操作・記述・DDL"| SYS_MACOS
    SYS_WEB -->|"same-origin HTTP API"| SYS_API
    SYS_CLI -->|"公開HTTP API"| SYS_API
    SYS_API -->|"snapshot + input envelope\n(native wheel)"| SYS_CORE
    SYS_ANDROID -->|"snapshot + input envelope\n(JNI)"| SYS_CORE
    SYS_MACOS -->|"snapshot + input envelope\n(UniFFI)"| SYS_CORE
    SYS_ANDROID -->|"保存済み／現行SVG"| SYS_RASTER
    SYS_MACOS -->|"保存済み／現行SVG"| SYS_RASTER
    SYS_API -->|"coreが要求したeffectを1回ずつ"| SYS_LLM
    SYS_ANDROID -->|"coreが要求したeffectを1回ずつ"| SYS_LLM
    SYS_MACOS -->|"coreが要求したeffectを1回ずつ"| SYS_LLM
    SYS_API -->|"履歴・authority・実行snapshot・設定・session"| SYS_DB
    SYS_API -->|"SVG/JSON/DDL/PNG生成"| SYS_FILES
    SYS_ANDROID -->|"履歴・authority・実行snapshot・系譜"| ANDROID_DB
    SYS_MACOS -->|"履歴・authority・実行snapshot・系譜"| MACOS_DB
```

共有Rust coreは6つのhost非依存crate（`inku-score`、`inku-ddl`、`inku-pipeline`、`inku-render`、`inku-svg-raster`、`inku-display`）と4つのbinding／host用crate（`inku-pipeline-uniffi`、`inku-render-python`、`inku-render-android`、`inku-display-gpu`）から成る。authoring state machine（`inku-pipeline`）はsnapshotとinputを受け、次のsnapshot、進行event、最大1個のeffectを返す。hostはそのeffect（LLM呼出し、可視DDLのCAS保存、画像の実行の見比べの画）を1回だけ実行し、identityを保った結果を返す。providerへの要求本文と答えの読みもcoreが持ち（`provider_wire`）、hostは鍵とHTTPだけを持つ。再試行、fallback、authority遷移、compileの契機はcoreが決める。typed compiler（`inku-ddl`）が可視DDLをScoreへ一度だけ下ろし、Render Engine（`inku-render`）がSVGを演奏する。AndroidとmacOSの画面表示はSkia（`inku-display`。macOSの拡大の窓は別processの`inku-display-gpu`）、thumbnailとPNGはraster crate（resvg）を通り、pixelは派生presentationとしてUIへ渡る。

Web内部では`+page.svelte`がroute lifecycle、画面構成、owner配線を担い、Session・Work・Batch・Demo・Refinement・Settings・history/lineage・viewportをroute-instance ownerへ分離する。共有pipelineの実行（DDL編集、補完案の承認、記述からのfork）は`features/pipeline/`のcontrollerが保存済み状態を読んで表示し、作者の操作だけをServerへ渡す。詳細なcanonical owner図は`client-boundaries.ja.md`、Server内部とRust crate図は`server-components.ja.md`が持つ。

## 外部境界と信頼境界

| 境界 | 契約 | 根拠 |
|---|---|---|
| Browser → Web | UI状態はroute-instance feature owner、localStorage・IndexedDB・File System Accessはbrowser側 | `+page.svelte`; `features/session/state.svelte.ts`; `features/work/state.svelte.ts`; `features/canvas/refinement-coordinator.svelte.ts`; `features/export/save-target.ts` |
| Web → API | developmentはVite proxy、配布時はSvelteKit hook proxy。clientはsnapshot、authority sidecar、effect結果、資源policyを送れない | `vite.config.ts`; `web/src/hooks.server.ts`; `pipeline_candidate.py`（module docstring） |
| CLI → API | `urllib`によるHTTPのみ。Server内部packageをimportしない | `cli/src/inku_cli/cli.py` |
| API → Rust core | 信頼済みconfigとsnapshotを所有したbyte bufferで渡し、次snapshotと演奏結果を受け取る。binding版とprotocol版の一致を起動時に要求する | `pipeline_candidate.py:PipelineBinding`; `inku-render-python`; `inku-pipeline-uniffi` |
| API → provider | model参照を解決後、coreが要求したeffectをtransport 1回で実行し、再試行しない。要求本文と答えの読みは共有coreの`provider_wire`が作る。画像の実行ではrunのメモリにある画像を参照どおりに添える | `pipeline_provider.py:SingleAttemptProvider`; `model_settings.py`; `provider_wire.rs`; `pipeline_images.py` |
| Android → Rust core | 同じbyte protocolをJNIで渡す。新しい演奏はcoreのrender入力、保存済みScoreの再演は復元した資源policyの下で`renderSaved`を使う（端末専用の旧9:5形式だけ`AndroidRenderHost`） | `SharedPipelineHost.kt`; `NativePipelineBridge.kt`; `AndroidWorkPipeline.kt`; `inku-render-android` |
| Android SVG → raster／表示 | canonical SVGとtarget geometryを渡し、明示的なpremultiplied RGBA8/strideを受け取る。通常表示はSkia（`inku-display`）、thumbnailとPNGはresvg | `RustArtworkRasterizer.kt`; `AndroidDisplayRenderer.kt`; `core/crates/inku-svg-raster`; `core/crates/inku-display` |
| macOS → Rust core | 同じbyte protocolをUniFFIで渡す。作品の同一性、保存作品の推敲の規則、AI自動推敲、providerの要求本文も同じcoreを呼ぶ。Server APIは呼ばない | `PipelineHost.swift`; `apple/Packages/InkuCore/`; `inku-pipeline-uniffi` |
| macOS表示 | 通常表示はSkia（`inku-display`）。拡大の窓はApple siliconで`inku-display-gpu`の別process（Skia Graphite）が描き、GPU driverがそのprocessを終わらせてもアプリは落ちない | `DisplayComposite.swift`; `core/crates/inku-display-gpu` |
| API → DB | 可視DDLとauthorityのCAS、action ACK、実行snapshot、server生成の履歴、系譜、設定、認証状態を保存 | `persistence/variation_authority.py`; `db.py`; `pipeline_product.py:save_result` |
| API → files | DB保存と独立したbest-effort queue。満杯時はfileだけskip | `api_core/state.py`; `rendering.py:_submit_history_artifact_save` |
| Android | serverとは別のtrust/storage boundary。意味判断・描画・`dh1`／`rh3`の計算は共有Rust、Room・provider設定はhost所有 | `InkuRepository`; `InkuDatabase`; `RoomSharedPipelineStore`; `AndroidWorkPipeline` |
| macOS | serverとも端末とも別のtrust/storage boundary。意味判断・描画・同一性は共有Rust、GRDB・provider設定・Keychainはhost所有 | `apple/Packages/InkuPersistence/`; `ProviderTransport.swift`; `PipelineHost.swift` |

## ノード／edge根拠

| 図要素 | Evidence ID | 主な根拠 |
|---|---|---|
| 利用者/Web/CLI/Android | `SYS-USER`, `SYS-WEB`, `SYS-CLI`, `SYS-ANDROID` | 各entry pointとUI/parser |
| FastAPI/provider | `SYS-API`, `PIPE-HOST`, `SYS-LLM` | `api.py`, `pipeline_runtime.py`, `pipeline_provider.py` |
| 共有Rust core | `SYS-CORE`, `PIPE-MACHINE`, `PIPE-TYPED-DDL`, `PIPE-RENDER`, `PIPE-WIRE`, `PIPE-REFINE` | `core/Cargo.toml`, `inku-pipeline`, `inku-ddl`, `inku-render` |
| raster／表示 | `PIPE-RASTER`, `PIPE-DISPLAY` | `inku-svg-raster`, `inku-display`, `inku-display-gpu`, `RustArtworkRasterizer.kt` |
| Server DB/files | `SYS-DB`, `DATA-AUTHORITY`, `SYS-FILES` | `db.py`, `variation_authority.py`, `rendering.py` |
| Android Room | `SYS-ANDROID` | `data/db/InkuDatabase.kt`, `RoomSharedPipelineStore.kt` |
| macOS GRDB | `SYS-MACOS` | `apple/Packages/InkuPersistence/`, `PipelineHost.swift` |
