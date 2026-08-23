# Client boundaries

## Different responsibilities

```mermaid
flowchart TB
    USER["Author"]
    WEB["Web\nSvelteKit UI"]
    CLI["CLI\nHTTP client + bench instrument"]
    ANDROID["Android\nseparate pipeline + renderer"]
    API["Public Server HTTP API"]
    SERVER_PIPE["Server pipeline"]
    ANDROID_PIPE["Android Kotlin pipeline"]
    ROOM[("Room DB")]

    USER --> WEB
    USER --> CLI
    USER --> ANDROID
    WEB -->|"HTTP"| API
    CLI -->|"HTTP only"| API
    API --> SERVER_PIPE
    ANDROID --> ANDROID_PIPE
    ANDROID_PIPE --> ROOM
    SERVER_PIPE -.->|"later port from canonical Server behavior"| ANDROID_PIPE
```

Web is the reference UI for Server works. The CLI measures the public API. Android performs every stage on-device as a separate implementation. No ordinary Android path to the Server pipeline was confirmed.

## Web internals

```mermaid
flowchart LR
    PAGE["+page.svelte\nscreen orchestration"]
    COMPONENTS["components/\ninput, canvas, history, lineage, settings"]
    FEATURES["features/<name>/\nbatch, export, catalog, inspection, Wild"]
    RUN["features/run/current-work.ts\none Paint request, stream, and saved-work projection"]
    LINEAGE_STATE["features/history/lineage-state.svelte.ts\nroute-instance lineage queries + nearby works"]
    HISTORY_STATE["features/history/browsing-state.svelte.ts\nroute-instance strip queries, paging, filters, refresh, and manager coordination"]
    HISTORY_MUTATIONS["features/history/mutations.ts\nroute-instance mark and lifecycle mutation coordination"]
    HISTORY_WORK["features/history/{save,replay,current-work,lineage-actions}.ts\nsave, replay, current-work, and lineage-action coordination"]
    CANVAS_VIEWPORT["features/canvas/viewport-state.svelte.ts\nroute-instance zoom, fit, pan, and pointer/keyboard interactions"]
    REFINE_SESSION["features/canvas/refinement-session.svelte.ts\nroute-instance busy, cancellation, fan-out progress, and candidate selection"]
    HISTORY_MANAGER["historyManagerState.svelte.ts\nmanager query, cache, and measured page size"]
    SETTINGS["features/settings/state.svelte.ts\nroute-instance Settings shell + Server / model-provider / user-group administration"]
    SETTINGS_MODAL["SettingsModal.svelte\nSettings shell view"]
    USER_ADMIN_VIEW["features/settings/UserAdministrationSettings.svelte\nuser/group focused view"]
    DATABASE_VIEW["features/settings/DatabaseAdministrationSettings.svelte\ndatabase/backup focused view"]
    LIMITS_VIEW["features/settings/RenderLimitsSettings.svelte\nrender-limits focused view"]
    RUNTIME_VIEW["features/settings/ServerRuntimeSettings.svelte\nserver-runtime focused view"]
    TRANSPORT["transport/api-fetch.ts\nauthenticated HTTP transport"]
    PERSIST["persisted-settings.ts"]
    USERSET["user-settings.ts"]
    PAYLOAD["render-payload.ts"]
    LOCAL[("localStorage")]
    INDEXED[("IndexedDB / browser folder handle")]
    API["Server API"]

    PAGE --> COMPONENTS
    PAGE --> FEATURES
    PAGE -->|"resolved defaults + named capabilities"| RUN
    PAGE -->|"create owner + wire current focus/actions"| LINEAGE_STATE
    RUN -->|"loadNearby capability"| LINEAGE_STATE
    PAGE -->|"create owner + wire current work/notices"| HISTORY_STATE
    HISTORY_STATE -->|"construct exactly one"| HISTORY_MANAGER
    PAGE -->|"create owner + wire current-canvas capability"| HISTORY_MUTATIONS
    COMPONENTS -->|"named mutation actions"| HISTORY_MUTATIONS
    HISTORY_MUTATIONS -->|"strip/trash/manager projections"| HISTORY_STATE
    HISTORY_MUTATIONS -->|"mark projections + focused-query refresh"| LINEAGE_STATE
    PAGE -->|"resolved defaults + route UI/Canvas application"| HISTORY_WORK
    COMPONENTS -->|"named replay/focus/lineage actions"| HISTORY_WORK
    HISTORY_WORK -->|"listing reconciliation"| HISTORY_STATE
    HISTORY_WORK -->|"note projection"| HISTORY_MUTATIONS
    HISTORY_WORK -->|"focus/query refresh"| LINEAGE_STATE
    PAGE -->|"create per-route owner + global shortcut gate"| CANVAS_VIEWPORT
    COMPONENTS -->|"typed CanvasViewport"| CANVAS_VIEWPORT
    PAGE -->|"candidate generation, save, and Canvas application"| REFINE_SESSION
    COMPONENTS -->|"typed RefinementSession"| REFINE_SESSION
    PAGE -->|"create factory + wire external dependencies"| SETTINGS
    PAGE --> SETTINGS_MODAL
    SETTINGS_MODAL -->|"SettingsController"| SETTINGS
    SETTINGS_MODAL -->|"session display and input props"| USER_ADMIN_VIEW
    SETTINGS -->|"userAdministration submodel"| USER_ADMIN_VIEW
    SETTINGS_MODAL -->|"database/db_backup slices"| DATABASE_VIEW
    SETTINGS -->|"named database operations"| DATABASE_VIEW
    SETTINGS_MODAL -->|"render_limits slice"| LIMITS_VIEW
    SETTINGS -->|"named limits operations"| LIMITS_VIEW
    SETTINGS_MODAL -->|"output_save/render_concurrency slices"| RUNTIME_VIEW
    SETTINGS -->|"named runtime operations"| RUNTIME_VIEW
    SETTINGS -->|"named settings and administration operations"| TRANSPORT
    RUN -->|"Paint stream + unread-word feedback"| TRANSPORT
    LINEAGE_STATE -->|"lineage + neighbor queries"| TRANSPORT
    LINEAGE_STATE -->|"graph/loading/error + nearby works"| COMPONENTS
    HISTORY_STATE -->|"strip/trash queries + external state probe"| TRANSPORT
    HISTORY_MUTATIONS -->|"mark PATCH + lifecycle POST"| TRANSPORT
    HISTORY_WORK -->|"history save + replay + promote/note"| TRANSPORT
    HISTORY_STATE -->|"strip selection/paging/filter state"| COMPONENTS
    HISTORY_MANAGER -->|"manager state"| COMPONENTS
    TRANSPORT --> API
    FEATURES -->|"load registration"| PERSIST
    FEATURES -->|"model_settings slice"| USERSET
    FEATURES -->|"request slice"| PAYLOAD
    PERSIST --> LOCAL
    USERSET -->|"PATCH /api/auth/me/settings"| API
    PAYLOAD -->|"Paint / compose / render payload"| API
    FEATURES -->|"export target"| INDEXED
    COMPONENTS -->|"history / lineage / export API"| API
```

## Web state and persistence

| Owner | Examples | Boundary |
|---|---|---|
| Component/page memory | Current result, output tab, replay modal/loading, and application of current work to Canvas | Lost on reload; not Server-canonical. A stateless history feature builds the field projection from a history item |
| Stateless run feature | One Paint request, stream progress, and immediate saved-work projection | `runCurrentWork` receives resolved defaults and named capabilities; outer loops, route state, and AbortControllers stay with the page |
| Route-instance lineage query owner | Lineage graph/loading/error, stale-response identity, branch/overview merge, and nearby works | One `LineageQueryState` per route; query state is not copied into a history action module or the page |
| Route-instance history browsing owner | Strip items/count/offset/selection, filters, paging/resize, stale-response identity, trash summary, external refresh, mark projections, and manager coordination | One `HistoryBrowsingState` per route constructs exactly one existing `HistoryManagerState`; manager request/cache/page-size semantics are not copied |
| Route-instance history mutation coordinator | Optimistic star/revision/share mutations and bulk trash/restore/permanent-delete coordination | One `HistoryMutations` per route; it duplicates no state and sends only named projections to the browsing/lineage owners and the page-owned current canvas |
| Stateless history work operations | Save-oriented history payload, saved-work replay, history-to-current-work projection, and saved-child/promote/note coordination | `save.ts`, `replay.ts`, `current-work.ts`, and `lineage-actions.ts` receive only typed inputs and named capabilities; route UI, AbortControllers, and Canvas application stay with the page |
| Route-instance Canvas viewport owner | Zoom, measured fit zoom, pan, pointer capture, and keyboard zoom/pan | One `CanvasViewportState` per route; `CanvasPanel` receives the typed owner, while the page wires only global-shortcut eligibility and `fit()` requests when work changes |
| Route-instance refinement session owner | Single/grid/save busy state, elapsed/tokens, fan-out slots, AbortController, and candidate selection | One `RefinementSessionState` per route; only the active controller commits progress/errors/finish, and `CanvasPanel` sends cancel/toggle to the typed owner. Candidate requests, saves, and Canvas application stay with the page |
| Route-instance feature owner | Settings dialog visibility, tab and detail level; Server and model-provider administration; user/group lists, status, and operations | One `createSettingsController` per route; focused views receive only their required `userAdministration`, `database`/`db_backup`, `render_limits`, or `output_save`/`render_concurrency` slices and named operations |
| Focused component memory | Unsaved API keys, account forms and passwords, and user/group selection | Kept only by the component that renders the input: account drafts in `UserAdministrationSettings.svelte`, API-key drafts in `SettingsModal.svelte` |
| localStorage | UI language, Settings detail level, Wild, batch retry, result log, export and orientation settings | Browser-local |
| IndexedDB | File System Access folder handle | Needs structured clone, outside localStorage |
| User Server settings | Catalog and model-inspection `model_settings` slices | Per login user through `user-settings.ts` |
| Render payload | Catalog, Wild, and related request fields | Contributors grouped by request kind in `render-payload.ts` |
| Server DB | History, SVG, Score, lineage | A client does not choose trusted SVG content |

`+page.svelte` remains the screen orchestrator, while `features/run/current-work.ts` owns one Paint request, its NDJSON progress, and the immediate nearby-history, saved-lineage, generation-count, and unread-word effects. The page resolves its current settings and supplies narrow named capabilities; it retains the current result, outer submit/replay/batch/demo/refinement loops, stale-result decisions, and AbortController ownership.

Stage 5A places lineage and nearby-work query state in one route-instance `LineageQueryState`. It owns request identity, loading/error, graph replacement, branch/overview merge, reset invalidation, and same-history neighbor deduplication. `runCurrentWork` receives its `loadNearby` method directly.

Stage 5B places history browsing in one route-instance `HistoryBrowsingState`. It owns strip and trash queries, paging, selection synchronization, filters, resize alignment, stale-response identity, external-save refresh, save/run listing refresh, and mark projections. It constructs exactly one existing `HistoryManagerState` and seeds or refreshes that owner without duplicating its request suppression, cache, or measured page-size rules. The page supplies current-work and browser-lifecycle capabilities.

Stage 5C makes `HistoryMutations` own optimistic star/revision/share PATCH and rollback, plus bulk trash/restore/permanent-delete POST and refresh ordering. It duplicates no mutable state: named projections go to `HistoryBrowsingState` and `LineageQueryState`, while current-canvas reseating returns through a page capability.

Stage 5D assigns four stateless modules the save-oriented `POST /api/history` payload and listing reconciliation, saved-work replay request and version comparison, typed history-item-to-current-work projection, and saved-child/promote/note coordination across existing owners. The page supplies resolved browser preferences, localized messages, and route-target identity. It retains modal/tab/loading state, AbortControllers, Svelte assignments, Canvas application and late-SVG handling, and draw/refinement actions launched from lineage. History modules do not copy state from `HistoryBrowsingState`, `HistoryMutations`, or `LineageQueryState`.

Stage 6A makes one route-instance `CanvasViewportState` own zoom, fit zoom, pan, drag origins, pointer capture, and keyboard mapping. `CanvasPanel` receives the typed owner instead of individual state and callback props, and passes ResizeObserver measurements plus wheel and pointer events to named operations. The page retains the global shortcut gate that excludes inputs and modals, plus composition calls that return the viewport to fit when the work or result changes. Refinement, variations, the current result, and Canvas markup do not move in this Stage.

Stage 6B makes one route-instance `RefinementSessionState` own single/grid/save busy state, elapsed and token totals, fan-out waiting/running/done progress, cancellation identity, status, and candidate selection. A target reset aborts and invalidates the active controller, so late callbacks cannot write into a replacement session. `CanvasPanel` receives the typed owner instead of individual session props. Candidate endpoints and planning, history saves, Canvas application, fallback confirmation, target-context versioning, and single-redraw result mapping stay with the page.

The Settings shell, Server administration, model-provider administration, and user/group administration state machines are owned by the route-instance `features/settings/state.svelte.ts`. The page wires the signed-in actor, session/user-settings refresh, external per-tab loaders, drawing-time model-catalog loader, and render-concurrency setter into the factory. Login/logout, the canonical current actor, and drawing-time model selection stay on the page. `SettingsModal.svelte` receives one `SettingsController` as the Settings shell. The user/group tab passes only the narrow `userAdministration` submodel and required session props to `UserAdministrationSettings.svelte`; account-form/password drafts stay in that input view, while API-key drafts stay in the modal. The database/backup tab passes only `database`/`db_backup` to `DatabaseAdministrationSettings.svelte`, the render-limits tab only `render_limits` to `RenderLimitsSettings.svelte`, and the server-runtime tab only `output_save`/`render_concurrency` to `ServerRuntimeSettings.svelte`, each with required named operations. Status and operation ownership stays in the route-instance feature owner. The owner never copies a secret from an operation argument into state, confirmation, or error output.

## CLI boundary

- `ApiClient` uses `urllib.request` for `/api/*` and `/health`.
- Runtime code does not import `inku_server`. Shared `inku_analysis` is used for rasterization/analysis, not to bypass the Server pipeline.
- Natural-language `paint`/`batch` uses `/api/paint`; DDL mode uses `/api/compose`; history persistence uses `/api/history`.
- `test_cli_sender_census.py` treats the CLI as the functional sender.

## Android boundary

- Flow: `InkuRepository` → `LocalFallbackPipeline` → `DefaultSvgRenderer` → Room.
- `RoutingModelProvider` selects local LiteRT-LM or an OpenAI-compatible remote provider.
- `CompatibilityConstants.renderEngineVersion` is 35; Server is 38.
- Server conditions, schema, seeds, and reference fixtures are ported later. Matching numbers would not by themselves prove identical implementations.

## Language and UI sources

| Source | Implementation |
|---|---|
| Japanese/English UI packs | `web/src/lib/i18n/ja.ts`, `en.ts`, `types.ts` |
| English terminology | `docs/i18n/glossary.md` (correspondence table); `web/src/lib/i18n/GLOSSARY.md` (rules); `npm run lint:i18n` |
| Saijiki display | `GET /api/saijiki` after login |
| Button dimensions and action/accent tokens | `:root` in `web/src/routes/+page.svelte` |

## Evidence map

Evidence: `SYS-WEB`, `SYS-CLI`, `SYS-ANDROID`, `WEB-FEATURES`, `WEB-REGISTRY`, `WEB-I18N`.
