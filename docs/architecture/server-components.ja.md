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
    RENDERING["api_core/rendering.py"]
    REGISTRY["render_engines/__init__.py\ncurrent_render_engine()"]
    HOST["render_engines/host.py / profiles.py / seeds.py\nhost所有のrequest準備"]
    DEFAULT_INIT["render_engines/default/__init__.py"]
    ADAPTER["default/adapter.py\n薄い1-call native adapter"]
    BINDING["inku-render-python\nCPython wheel境界"]
    CORE["inku-render Rust core\nplanning / geometry / marks / SVG / metadata"]
    REFERENCE["reference.py\n実装reference"]
    RENDERER["renderer.py\nSVG-only互換facade"]
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
    RENDERING --> REGISTRY
    RENDERING --> HOST
    REGISTRY --> DEFAULT_INIT
    DEFAULT_INIT --> ADAPTER
    ADAPTER --> HOST
    ADAPTER --> BINDING
    BINDING --> CORE
    REFERENCE --> BINDING
    RENDERER -->|"render() → current engine .svg"| REGISTRY
    RENDERING --> DB
    RENDERING -->|"PNG rasterize"| ANALYSIS
```

正規経路は `api_core/rendering.py → render_engines` registry → `default/adapter.py` → 独立した `inku-render-python` wheel → platform-independentな `inku-render` core である。adapterはhost所有のcanvas/profileを解決し、正規requestを1回serializeして、SVGとmetadataを1回のcallで受け取る。`renderer.py` はSVG-only互換facadeとして残り、同じregistryへ委譲する。

Stage 6でPython Engine 40の統率、planning、mark、surface、layer、SVG emission、stroke moduleを削除した。`default/` に残るのはpackage exportと薄いRust adapterだけである。`/api/reference` も第二のPython実装をimportせず、renderer所有の表をnative coreから読む。Androidはまだ履歴上のKotlin rendererを使っており、このRust coreの採用は次のportability boundaryである。

## Rust core内部

```mermaid
flowchart LR
    PYBIND["inku-render-python\nJSON decode・CPython変換だけ"]
    PUBLIC["lib.rs / types.rs / reference.rs\nengine identity・host-neutral型・reference"]
    RENDER["render.rs\n粗いrequest/output境界・SVG統率・metadata"]
    PLAN["performance.rs / planning.rs / arrangement.rs\nplacement.rs / group.rs\nScore-level演奏・関係・反復配置"]
    GEOMETRY["geometry.rs / arc.rs / cloudform.rs / contact.rs\n純粋な点・輪郭・接触幾何"]
    MATERIAL["marks.rs / mark_paths.rs / stroke.rs / fills.rs\nsurfaces.rs / surface_geometry.rs / support.rs / materials.rs\n画材・線・面・紙との接触"]
    CANVAS["ground.rs / ground_patterns.rs / layers.rs / palette.rs\n支持体・presence・色割当"]
    SVG["svg.rs\n小さいdocument tree・境界で1回serialize"]
    DETERMINISM["determinism.rs\nhash・seed payload・scalar noise"]

    PYBIND --> PUBLIC
    PYBIND --> RENDER
    RENDER --> PUBLIC
    RENDER --> PLAN
    RENDER --> MATERIAL
    RENDER --> CANVAS
    RENDER --> SVG
    PLAN --> GEOMETRY
    MATERIAL --> GEOMETRY
    PLAN --> DETERMINISM
    GEOMETRY --> DETERMINISM
    MATERIAL --> DETERMINISM
    CANVAS --> DETERMINISM
    MATERIAL --> SVG
    CANVAS --> SVG
```

`types.rs`はPython schemaの代替ではなく、検証・coerce済みの正規Scoreと解決済みhost optionだけを受ける。`render.rs`が唯一の全体統率で、planningは作品レベルの演奏と配置、geometryは副作用のない点列計算、material群はmark／stroke／surfaceとsupportの相互作用、canvas群はground／presence／palette、`svg.rs`は小さいdocument treeと最終serializeを所有する。`determinism.rs`は横断的に使われるがhost entropyは作らない。CPython bindingはこの公開面を粗く呼ぶだけで、内部moduleごとのPython往復やhost SDK依存を入れない。

## Router分類

| Router | endpoint数 | 主責任 | default guard |
|---|---:|---|---|
| `public` | 10 | health、info、catalog、models、saijiki、reference、prompts、demo | なし。`/health` と `/api/info` 以外は個別guard |
| `auth` | 4 | auth config、login/logout | なし。login以外は個別guard |
| `me` | 13 | profile、user settings、各user storage | `_current_user` |
| `plugins` | 8 | plugin閲覧・検証・CRUD・enable | `_current_user`、変更はadmin |
| `settings` | 16 | server-wide settings、backup | `_admin_user` |
| `users` | 8 | user/group管理 | `_user_manager` |
| `history` | 18 | 履歴、SVG、thumbnail、mark、trash、共有、artifact再作成 | `_current_user` |
| `lineage` | 8 | lineage graph/group、promote、colophon | `_current_user` |
| `render` | 8 | variation、compose、interpret、render、paint、vision | `_current_user` |
| `feedback` | 3 | unread words | `_current_user` |

合計96。公開allowlistは `/health`、`/api/info`、`/api/auth/login` の3 pathである（`test_route_authorization.py`）。ログインに要らないものは残さない、が基準である。

**⚠ この表の件数は手で写したもので、赤くする検査は無い**（allowlistの3 pathだけが検査に載っている）。件数の正本は `test_route_authorization.py` の `EXPECTED_ROUTE_COUNT` である。

## 主要flow

- `/api/paint` と `/api/paint/stream` は同じ `_paint_events` generatorを消費する。streamだけ層の完了を先行eventとして返す（`sketch`・`stage1`・`score` の3つ。`sketch` は写生層が動いた回だけ）。**先行eventが1つでも出た後の失敗は、HTTPではなく本文の `error` eventで届く。**
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
