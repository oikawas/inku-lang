# Client boundaries

## 三clientの責任差

```mermaid
flowchart TB
    USER["利用者"]
    WEB["Web\nSvelteKit UI"]
    CLI["CLI\nHTTP client + bench補助"]
    ANDROID["Android\n別pipeline + renderer"]
    API["Server公開HTTP API"]
    SERVER_PIPE["Server pipeline"]
    ANDROID_PIPE["Android Kotlin pipeline"]
    ROOM[("Room DB")]

    USER --> WEB
    USER --> CLI
    USER --> ANDROID
    WEB -->|"HTTP"| API
    CLI -->|"HTTPのみ"| API
    API --> SERVER_PIPE
    ANDROID --> ANDROID_PIPE
    ANDROID_PIPE --> ROOM
    SERVER_PIPE -.->|"正本として後追い移植"| ANDROID_PIPE
```

Webはserver作品を操作する参照UI、CLIはserverの公開APIを測るclient、Androidは端末内で全段を動かす別実装である。Androidがserver APIを通常pipelineとして呼ぶ関係は確認できない。

## Web内部

```mermaid
flowchart LR
    PAGE["+page.svelte\n画面orchestration"]
    COMPONENTS["components/\n入力・canvas・history・lineage・settings"]
    FEATURES["features/<name>/\nbatch/export/catalog/inspection/wild等"]
    PERSIST["persisted-settings.ts"]
    USERSET["user-settings.ts"]
    PAYLOAD["render-payload.ts"]
    LOCAL[("localStorage")]
    INDEXED[("IndexedDB / browser folder handle")]
    API["Server API"]

    PAGE --> COMPONENTS
    PAGE --> FEATURES
    FEATURES -->|"load registration"| PERSIST
    FEATURES -->|"model_settings slice"| USERSET
    FEATURES -->|"request slice"| PAYLOAD
    PERSIST --> LOCAL
    USERSET -->|"PATCH /api/auth/me/settings"| API
    PAYLOAD -->|"paint/compose/render payload"| API
    FEATURES -->|"export target"| INDEXED
    COMPONENTS -->|"history/lineage/export API"| API
```

## Webの状態と永続化

| 所有者 | 例 | 境界 |
|---|---|---|
| component/page memory | 描画中のresult、tab、history選択、lineage graph | reloadで消える。server正本ではない |
| localStorage | UI language、wild、batch retry、result log、export設定、表示向き | browser-local |
| IndexedDB | File System Access APIのfolder handle | structured cloneが必要でlocalStorage外 |
| user server settings | catalog、model inspection等の`model_settings` slice | login user単位、`user-settings.ts`で集約 |
| render payload | catalog/wild等のrequest field | `render-payload.ts`のkind別contributor |
| server DB | 履歴、SVG、Score、系譜 | clientが信頼済みSVGを決めない |

`+page.svelte` は依然大きなorchestratorだが、UI componentとfeature stateは分離されている。主要表示は記述入力、canvas/refine/lineage、batch、demo、history manager、settingsで構成される。

## CLI境界

- `ApiClient` は `urllib.request` で `/api/*` と `/health` だけを扱う。
- runtime codeは `inku_server` をimportしない。`inku_analysis` はrasterize/analysis用の共有packageで、server pipelineを迂回するものではない。
- `paint` / `batch` の自然文modeは `/api/paint`、DDL modeは `/api/compose`、保存時は `/api/history` を利用する。
- 機能試験の送信者として `test_cli_sender_census.py` に検査される。CLI testがserver sourceを読む箇所はテスト上の契約照合であり、製品runtime依存ではない。

## Android境界

- `InkuRepository` → `LocalFallbackPipeline` → `DefaultSvgRenderer` → Roomという端末内flow。
- `RoutingModelProvider` はlocal LiteRT-LMとOpenAI-compatible remote providerを選ぶ。
- `CompatibilityConstants.renderEngineVersion` は35。Serverの38とは別版である。
- serverの条件式・schema・seed・参照fixtureを後追い移植する。数字が同じでも自動的な同一実装ではない。

## i18nとUI token

| 正本 | 実装 |
|---|---|
| 日本語/英語UI pack | `web/src/lib/i18n/ja.ts`, `en.ts`, `types.ts` |
| 英語UI用語 | `docs/i18n/glossary.md`（対応表）、`web/src/lib/i18n/GLOSSARY.md`（規則）、`npm run lint:i18n` |
| 歳時記表示 | login後の`GET /api/saijiki`でserver tableからhydrate |
| button寸法・action/accent色 | `web/src/routes/+page.svelte`の`:root` token |

## 根拠対応

`SYS-WEB`, `SYS-CLI`, `SYS-ANDROID`, `WEB-FEATURES`, `WEB-REGISTRY`, `WEB-I18N`。主要pathは図中に記載した。
