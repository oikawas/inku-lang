# Server components

## API surface

`api.py` owns process-wide assembly; endpoint bodies live in ten routers. Router defaults and endpoint dependencies both contribute authorization. `test_route_module_split.py` checks live `endpoint.__module__` values so endpoint ownership cannot drift back into `api.py` unnoticed.

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
    DEPS["api_core/deps.py\nsession and role guards"]
    SHARED["api_core state / models / common / rendering"]
    DB["db.py\ncompatibility / composition facade"]

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

The dependency direction is `api.py → routers → shared api_core/domain modules`. A search under `server/src/inku_server/api_core/routers/` found no import from `inku_server.api`.

## Processing surface

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
    HOST["render_engines/host.py / profiles.py / seeds.py\nhost-owned request preparation"]
    DEFAULT_INIT["render_engines/default/__init__.py"]
    ADAPTER["default/adapter.py\nthin one-call native adapter"]
    BINDING["inku-render-python\nCPython wheel boundary"]
    CORE["inku-render Rust core\nplanning / geometry / marks / SVG / metadata"]
    REFERENCE["reference.py\nimplementation reference"]
    RENDERER["renderer.py\nSVG-only compatibility facade"]
    DB["db.py\ncompatibility / composition facade"]
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
    RENDERING -->|"PNG rasterization"| ANALYSIS
```

The canonical path is `api_core/rendering.py → render_engines` registry → `default/adapter.py` → the independent `inku-render-python` wheel → the platform-independent `inku-render` core. The adapter resolves host-owned canvas/profile data, serializes one canonical request, and receives SVG plus metadata in one call. `renderer.py` remains the SVG-only compatibility facade and delegates through the same registry.

Stage 6 removed the Python Engine 40 orchestration, planning, mark, surface, layer, SVG-emission, and stroke modules. `default/` now contains only its package export and the thin Rust adapter. `/api/reference` obtains renderer-owned tables from the native core instead of importing a second Python implementation. Android now calls the same core through the thin `inku-render-android` JNI adapter. Its SVG presentation uses the separate `inku-svg-raster` crate; this boundary does not change the Server's existing PNG raster path.

## Persistence surface

```mermaid
flowchart TD
    CALLERS["routers / services / tests"]
    FACADE["db.py\ncompatibility and composition"]
    STARTUP["config / engine / schema\nmigrations / legacy_schema\ninvariants / backup"]
    SECURITY["access / accounts / groups\nsessions / identities"]
    PRODUCT["settings / history / search\nlineage / okugaki / feedback"]
    SQLITE[("canonical SQLite")]

    CALLERS --> FACADE
    FACADE --> STARTUP
    FACADE --> SECURITY
    FACADE --> PRODUCT
    STARTUP --> SQLITE
    SECURITY --> SQLITE
    PRODUCT --> SQLITE
```

`db.py` is the public compatibility facade that avoids rewriting every caller
at once and the composition seam that supplies call-time dependencies.
`persistence/schema.py` owns the ORM schema; `config.py` and `engine.py` own
SQLite-only configuration and connection PRAGMAs; `migrations.py` owns the
versioned registry and startup decision; and `backup.py` plus `invariants.py`
own snapshots and the data-loss guard. Domain CRUD and queries belong to
modules separated by their reasons to change.

No direct SQL, transaction, migration Session, metadata-create, commit, or
flush implementation owner remains in `db.py`. Compatibility re-exports and
thin delegates are intentional. Only a wrapper with proven-zero readers is
removed; keeping new persistence behavior out of the facade matters more than
reducing its line count.

## Rust core internals

```mermaid
flowchart LR
    PYBIND["inku-render-python\nJSON decoding and CPython conversion only"]
    PUBLIC["lib.rs / types.rs / reference.rs\nengine identity, host-neutral types, and reference"]
    RENDER["render.rs\ncoarse request/output boundary, SVG orchestration, and metadata"]
    PLAN["performance.rs / planning.rs / arrangement.rs\nplacement.rs / group.rs\nScore-level performance, relations, and repeated placement"]
    GEOMETRY["geometry.rs / arc.rs / cloudform.rs / contact.rs\npure point, contour, and contact geometry"]
    MATERIAL["marks.rs / mark_paths.rs / stroke.rs / fills.rs\nsurfaces.rs / surface_geometry.rs / support.rs / materials.rs\ntools, strokes, surfaces, and support contact"]
    CANVAS["ground.rs / ground_patterns.rs / layers.rs / color-assignment module\nsupport ground, presence, and color assignment"]
    SVG["svg.rs\nsmall document tree serialized once at the boundary"]
    DETERMINISM["determinism.rs\nhashes, seed payloads, and scalar noise"]

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

`types.rs` does not replace the Python schema; it receives only the canonical Score after validation/coercion and resolved host options. `render.rs` is the sole whole-render orchestrator. Planning owns work-level performance and placement, geometry owns side-effect-free point calculations, the material group owns marks/strokes/surfaces and their interaction with the support, the canvas group (`ground.rs`, `ground_patterns.rs`, `layers.rs`, and `palette.rs`) owns ground/presence/color assignment, and `svg.rs` owns the small document tree and final serialization. `determinism.rs` is shared across groups but never creates host entropy. The CPython binding calls this public surface coarsely, with no per-module Python round trips or host-SDK dependency in the core.

## Router groups

| Router | Endpoints | Main responsibility | Default guard |
|---|---:|---|---|
| `public` | 10 | Health, info, catalogs, models, Saijiki, references, prompts, demo | None; every route but `/health` and `/api/info` adds its own guard |
| `auth` | 4 | Auth configuration, login/logout | None; every route but login adds its own guard |
| `me` | 13 | Profile, user settings, user storage | `_current_user` |
| `plugins` | 8 | Browse, validate, CRUD, enable plugins | `_current_user`; admin for changes |
| `settings` | 16 | Server-wide settings and backup | `_admin_user` |
| `users` | 8 | User/group management | `_user_manager` |
| `history` | 18 | History, SVG, thumbnails, mark, trash, sharing, derivative rebuild | `_current_user` |
| `lineage` | 8 | Lineage graph/group, promote, colophon | `_current_user` |
| `render` | 8 | Variation, compose, interpret, render, Paint, vision | `_current_user` |
| `feedback` | 3 | Unread words | `_current_user` |

Total: 96. The three-path public allowlist is `/health`, `/api/info`, and `/api/auth/login` (`test_route_authorization.py`). The rule is that nothing logging in does not need stays on it.

**⚠ The counts in this table are copied by hand, and no gate reddens for them** (only the three allowlist paths are held by a check). The canonical count is `EXPECTED_ROUTE_COUNT` in `test_route_authorization.py`.

## Main flows

- `/api/paint` and `/api/paint/stream` consume the same `_paint_events` iterator; only the stream emits the layer-completion events early (`sketch`, `stage1`, `score`; `sketch` only on requests where that layer ran). **Once any early event has been written, a failure arrives as an `error` event in the body rather than as an HTTP status.**
- `/api/compose` starts from supplied DDL and proceeds through plugin → Stage 1.5 → Stage 2 → coerce → performance.
- `provider_for_model` and `_resolved_stage_model` resolve request, user settings, and provider catalog choices.
- `api_core/rendering.py` joins Score/performance to history and optional work-file persistence.

## Evidence map

Evidence: `SYS-API`, `API-ROUTERS`, `API-AUTH`, `PIPE-*`, `PIPE-HISTORY`, `SYS-DB`, `DATA-MIGRATION`, `SYS-FILES`.
