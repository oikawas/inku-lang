# Server components

## API面

`api.py` はprocess-wideな組立てを持ち、endpoint本体は10 routerへ分かれる。router-level default dependencyと個別dependencyの両方が認可を作る。`test_route_module_split.py` はlive routeの`endpoint.__module__`を検査し、endpointが`api.py`へ戻る退行を防ぐ。

```mermaid
flowchart TD
    API_PY["api.py\napp / lifespan / middleware"]
    PUB["public router"]
    AUTH["auth router"]
    ME["me router"]
    PLUGINS["plugins router"]
    SETTINGS["settings router"]
    USERS["users router"]
    HISTORY["history router"]
    LINEAGE["lineage router"]
    RENDER["render router"]
    FEEDBACK["feedback router"]
    DEPS["api_core/deps.py\nsession・role guards"]
    SHARED["api_core state/models/common/rendering"]
    DB["db.py"]

    API_PY -->|"include_router"| PUB
    API_PY -->|"include_router"| AUTH
    API_PY -->|"include_router"| ME
    API_PY -->|"include_router"| PLUGINS
    API_PY -->|"include_router"| SETTINGS
    API_PY -->|"include_router"| USERS
    API_PY -->|"include_router"| HISTORY
    API_PY -->|"include_router"| LINEAGE
    API_PY -->|"include_router"| RENDER
    API_PY -->|"include_router"| FEEDBACK
    AUTH --> DEPS
    ME --> DEPS
    PLUGINS --> DEPS
    SETTINGS --> DEPS
    USERS --> DEPS
    HISTORY --> DEPS
    LINEAGE --> DEPS
    RENDER --> DEPS
    FEEDBACK --> DEPS
    PUB --> SHARED
    RENDER --> SHARED
    HISTORY --> SHARED
    SHARED --> DB
```

依存方向は `api.py → routers → api_core共有module / domain module` である。`server/src/inku_server/api_core/routers/` から `inku_server.api` へのimport検索は0件だった。

## 処理面

```mermaid
flowchart LR
    RENDER_ROUTER["render router"]
    SKETCH["sketch.py"]
    INTERPRETER["interpreter.py"]
    PLUGIN_DOC["plugins/document_format.py"]
    EXPANDER["ddl_expander.py"]
    COMPOSER["composer.py"]
    SCHEMA["schema.py"]
    COERCE["coerce/"]
    ENGINE["render_engines/default.py"]
    RENDERER["renderer.py + stroke_engine.py"]
    RENDERING["api_core/rendering.py"]
    DB["db.py"]
    ANALYSIS["shared/inku_analysis"]

    RENDER_ROUTER --> SKETCH
    RENDER_ROUTER --> INTERPRETER
    RENDER_ROUTER --> PLUGIN_DOC
    RENDER_ROUTER --> EXPANDER
    RENDER_ROUTER --> COMPOSER
    COMPOSER --> SCHEMA
    RENDER_ROUTER --> COERCE
    COERCE --> SCHEMA
    RENDER_ROUTER --> RENDERING
    RENDERING --> ENGINE
    ENGINE --> RENDERER
    RENDERING --> DB
    RENDERING -->|"PNG rasterize"| ANALYSIS
```

## Router分類

| Router | endpoint数 | 主責任 | default guard |
|---|---:|---|---|
| `public` | 9 | health、info、catalog、models、saijiki、reference、prompts、demo | なし。一部routeは認証 |
| `auth` | 4 | auth config、login/logout | なし。更新/logoutは個別guard |
| `me` | 12 | profile、user settings、各user storage | `_current_user` |
| `plugins` | 8 | plugin閲覧・検証・CRUD・enable | `_current_user`、変更はadmin |
| `settings` | 10 | server-wide settings、backup | `_admin_user` |
| `users` | 8 | user/group管理 | `_user_manager` |
| `history` | 12 | 履歴、SVG、mark、trash、artifact再作成 | `_current_user` |
| `lineage` | 8 | lineage graph/group、promote、colophon | `_current_user` |
| `render` | 8 | variation、compose、interpret、render、paint、vision | `_current_user` |
| `feedback` | 3 | unread words | `_current_user` |

合計82。公開allowlistは `/health`、`/api/info`、`/api/auth/login` の3 pathである（`test_route_authorization.py`）。ログインに要らないものは残さない、が基準である。

## 主要flow

- `/api/paint` と `/api/paint/stream` は同じ `_paint_events` generatorを消費する。streamだけStage 1完了を先行eventとして返す。
- `/api/compose` はStage 1を通らず、受け取ったDDLからplugin → Stage 1.5 → Stage 2 → coerce → renderへ進む。
- provider/modelはrequest指定、userのStage設定、provider catalogを `provider_for_model` / `_resolved_stage_model` で解決する。
- `api_core/rendering.py` がScore/renderとhistory/file保存の継ぎ目である。

## 根拠対応

| 図要素 | Evidence ID | 根拠 |
|---|---|---|
| app/router/deps | `SYS-API`, `API-ROUTERS`, `API-AUTH` | `api.py`, `api_core/routers`, `deps.py` |
| pipeline components | `PIPE-*` | `render.py:_call_compose_detail`, `_paint_events` |
| persistence | `PIPE-HISTORY`, `SYS-FILES` | `rendering.py`, `db.py` |
| shared rasterizer | `SYS-FILES` | `shared/src/inku_analysis/rasterizer.py` |
