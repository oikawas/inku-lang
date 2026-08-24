# システムコンテキスト

WebとCLIはserverのHTTP APIを利用する。Androidは同じserverを薄いclientとして呼ぶのではなく、端末内に別のDDL pipeline、renderer、Room DBを持つ。Server DBがserver作品の正本であり、作品ファイル領域は任意の派生保存である。

```mermaid
flowchart LR
    SYS_USER["利用者"]
    SYS_WEB["Web / SvelteKit\nroute shell + feature owners"]
    SYS_CLI["inku-cli"]
    SYS_ANDROID["Android別実装"]
    SYS_API["inku server / FastAPI"]
    SYS_CORE["共有Rust Engine 41\n粗いnative 1-call境界"]
    SYS_LLM["外部・ローカル LLM provider"]
    SYS_DB[("Server DB / 正本")]
    SYS_FILES[("作品ファイル / 任意の派生")]
    ANDROID_DB[("端末Room DB / Android正本")]

    SYS_USER -->|"画面操作・記述"| SYS_WEB
    SYS_USER -->|"command・prompt"| SYS_CLI
    SYS_USER -->|"端末操作・記述"| SYS_ANDROID
    SYS_WEB -->|"same-origin HTTP API"| SYS_API
    SYS_CLI -->|"公開HTTP API"| SYS_API
    SYS_API -->|"検証済みScore + 解決済みoption"| SYS_CORE
    SYS_API -->|"Stage呼出し"| SYS_LLM
    SYS_API -->|"履歴・設定・session"| SYS_DB
    SYS_API -->|"SVG/JSON/DDL/PNG生成"| SYS_FILES
    SYS_ANDROID -->|"対応provider呼出し"| SYS_LLM
    SYS_ANDROID -->|"履歴・設定・系譜"| ANDROID_DB
```

Web内部では `+page.svelte` がroute lifecycle、画面構成、owner配線を担い、Session・Work・Batch・Demo・Refinement・Settings・history/lineage・viewportをroute-instance ownerへ分離する。1回のPaintやrefinement処理はstateless operation、CanvasとSettingsの表示はfocused viewが所有する。Server内部では薄いPython adapterが独立wheelを1回呼び、platform-independentなRust coreがEngine 41のplanning、geometry、mark、surface、layer、SVG、metadataを所有する。詳細なcanonical owner図は `client-boundaries.ja.md`、Rust module図は`server-components.ja.md`が持つ。

## 外部境界と信頼境界

| 境界 | 契約 | 根拠 |
|---|---|---|
| Browser → Web | UI状態はroute-instance feature owner、localStorage・IndexedDB・File System Accessはbrowser側 | `+page.svelte`; `features/session/state.svelte.ts`; `features/work/state.svelte.ts`; `features/canvas/refinement-coordinator.svelte.ts`; `features/export/save-target.ts` |
| Web → API | developmentはVite proxy、配布時はSvelteKit hook proxy | `vite.config.ts`; `web/src/hooks.server.ts` |
| CLI → API | `urllib`によるHTTPのみ。Server内部packageをimportしない | `cli/src/inku_cli/cli.py` |
| API → provider | provider/modelを解決後、Anthropic/Gemini/OpenAI互換へ接続 | `model_settings.py`; `interpreter.py`; `composer.py` |
| API → Rust core | 検証済みScoreと解決済みhost optionを1個のJSON requestで渡し、SVGとmetadataを一緒に受け取る | `render_engines/default/adapter.py`; `inku-render-python`; `core/crates/inku-render` |
| API → DB | server生成の履歴、系譜、設定、認証状態を保存 | `db.py`; `rendering.py` |
| API → files | DB保存と独立したbest-effort queue。満杯時はfileだけskip | `api_core/state.py`; `rendering.py:_submit_history_artifact_save` |
| Android | serverとは別のtrust/storage boundary | `InkuRepository`; `InkuDatabase`; `LocalFallbackPipeline` |

## ノード／edge根拠

| 図要素 | Evidence ID | 主な根拠 |
|---|---|---|
| 利用者/Web/CLI/Android | `SYS-USER`, `SYS-WEB`, `SYS-CLI`, `SYS-ANDROID` | 各entry pointとUI/parser |
| FastAPI/provider | `SYS-API`, `SYS-LLM` | `api.py`, `model_settings.py` |
| Rust render core | `PIPE-RENDER` | `default/adapter.py`, `inku-render-python`, `inku-render` |
| Server DB/files | `SYS-DB`, `SYS-FILES` | `db.py`, `rendering.py` |
| Android Room | `SYS-ANDROID` | `data/db/InkuDatabase.kt` |
