# Known differences and unknowns

## Specification and implementation differences

### F-01 Render Engine version (resolved during the review)

- At the start of the review, `PROJECT_CONTEXT.ja.md` named Render Engine 28 while the implementation was 29.
- Public commit `8b4d43cc` then updated the document to 29, matching `render_engines/default.py` and `server/reference/render-engine-29/manifest.json`.
- Result: **resolved**. The documentation snapshot follows the updated commit.

### F-02 Android specification-note versions (recurred)

- The header was synchronized with the implementation of the time on 2026-08-24, but the current header (last updated 2026-09-25) names `2.1.4-android.80`, render engine `67`, DDL engine version `20`, and a Server `ddl_engine_version` of 21.
- The implementation is Render Engine `68` (`core/crates/inku-render/src/lib.rs`) and `ddl_engine_version` `47` (`layer_versions.py`), and Android uses the same shared Rust pipeline.
- Result: **the version numbers are stale**. Engine identity is read from the packaged native library rather than a Kotlin product constant, so this is a documentation difference, not a runtime behavior difference.

### F-03 Android external-provider execution

- The "not implemented" section of the Android specification note lists external provider execution as not implemented and calls provider records compatibility data structures.
- Current `RoutingModelProvider` resolves enabled providers and connects to `GeminiModelProvider` and `OpenAiCompatibleProvider`. `SingleAttemptModelEffectProvider` sends shared-pipeline provider effects to them. The first half of the same note also describes the request conditions for Gemini and OpenAI-compatible providers.
- Result: **the "not implemented" section is stale**. An Anthropic-specific protocol implementation was not found, so parity across every provider is not claimed.

### F-04 Long historical Stage 1.5 description (resolved)

- In the earlier snapshot, `SPEC.ja.md` §12.11 described an old design that added mathematical, musical, and painterly candidates.
- The current §12.11 is rewritten as a typed transformation that takes only `CanonicalReady` typed meaning and changes only focus and explicit variation.
- Result: **resolved**.

### F-05 Stale statements in the Project Context

- The version table in `PROJECT_CONTEXT.ja.md` names Render Engine `66`, DDL `ddl_version` 11 / `ddl_engine_version` 45, and Android `2.1.4-android.78`. The implementation is 68, 13 / 47, and `2.1.4-android.80`.
- Its android section says "Android and the Server use the same shared Rust render engine `42`, and Android's DDL engine is `20`" and "the Android host still owns Stage 1 / 1.5 / 2, Score coerce, Room, history, and `rh3` identity", while Android has moved to the shared Rust pipeline (the document's "pipeline layers" section describes the current state).
- Its test-surface section names the active corpora as `render-engine-42` (610 cases) and `ddl-engine-20` (49 cases) and says "CI enforces byte identity of regeneration". The latest frozen records are Render Engine 66 (620 cases) and DDL engine 45 (3 cases), and the corpus comparison is a manual-dispatch workflow (`server/reference/README.md` states the policy of neither generating nor comparing outside an explicit checkpoint).
- Its list of deterministic layers still includes the deleted `coerce/` (only observation compatibility remains) and `ddl_expander.py`, and it still describes a "RAW trace (`include_trace`)". The current compatibility projection does not pass `include_trace` to the pipeline and returns no trace.
- Its vocabulary section names `schema.py` and `saijiki.py` as the source of truth, while its own design-contract section and the implementation name the shared core's `saijiki-v1.json`.
- Result: **part of the Project Context is older than the implementation**. This documentation follows the implementation and the SPEC and reference README that agree with it.

### F-06 Route-count test constants

- A static count gives 105: 94 endpoints in the ten routers and 11 in `/api/pipeline`.
- `EXPECTED_ROUTE_COUNT` in `test_route_authorization.py` is 95, and its comment records neither the addition of `/api/pipeline/*` nor the removal of `/api/prompts`. `tests/data/api-surface-baseline.json` also has 95 operations, contains the retired `/api/prompts`, and contains none of `/api/pipeline/*`.
- `/api/pipeline/*` arrived on 2026-09-13 (`2ad24df9`) and `/api/prompts` was removed on 2026-09-14 (`03bbd686`).
- Result: **inferred that the test constant and baseline disagree with the current routes**. App import failed in this review's environment for lack of the native wheel, so the live routes were not counted and that test was not run.

### F-07 Gate for label-only descriptions

- `SPEC.ja.md` §12.16 says the three drawing routes (`/api/interpret`, `/api/paint`, `/api/paint/stream`) reject with 400 a description that becomes empty after leading numbers and bracketed notes are stripped, and reject whitespace-only input with 422.
- The current Server has no stripping implementation (the old `description_labels.py`), and the description goes to the shared pipeline unchanged. Only the 422 whitespace check remains in `PaintRequest`. Web decides whether a description may be sent through `description-labels.ts`, whose comment still names the deleted Server file as the source of truth.
- Result: **specification and implementation differ**. A label-only description sent from a client other than Web (such as the CLI) is not answered with the specified 400.

### F-08 Stream progress events

- `SPEC.ja.md` §12.10 says `POST /api/paint/stream` reports progress in the order `sketch`, `stage1`, `score`, `done`.
- The current compatibility stream returns the final result as one `done` line after the shared-pipeline execution settles. An approval wait for a completion proposal arrives as a 409 before the stream starts. Web shows progress by re-reading the `/api/pipeline` view.
- Result: **specification and implementation differ**.

### F-09 Stale descriptive text inside the implementation

- `core/crates/inku-pipeline/README.md` says "there are four effect tags", "the candidate API does not switch the existing runtime", and "the existing runtime prompt is unchanged". The implementation has five effects, adding `generate_sketch`, and the shared pipeline is the normal runtime.
- The module docstring of `persistence/variation_authority.py` says "the ordinary Server runtime does not import or install these tables", while `pipeline_runtime.py` uses it as the store of the normal service.
- Doc comments in several `inku-ddl` modules (`compiler_lock.rs`, `composition_plan.rs`, `document.rs`, `macro_definition.rs`, `score_lowering.rs`, and others) still say "runtime-disconnected". `inku-score/src/types.rs` says "Python remains the schema authority".
- Result: **differences in descriptive text**, not in behavior.

### F-10 Leftover Stage executor

- `api_core/state.py` creates a Stage executor and slots from `INKU_STAGE_WORKERS` / `INKU_STAGE_QUEUE_LIMIT`, and `/api/settings/status` returns its counters.
- No current code submits a job to this executor. LLM effects run in the thread pool of `PipelineService`.
- Result: **only the status display remains**. The values shown do not represent the current LLM workload.

### F-11 Reference corpus for Android device acceptance

- `prepareRustParityAssets` and `NativeRenderDeviceTest` stage a few cases from `server/reference/render-engine-41` onto the device and compare SVG bytes. The path filter in `android-native.yml` also names `render-engine-41`.
- The current Render Engine is 68, and the latest frozen corpus is 66.
- Result: **unknown**. This review did not confirm whether the staged cases produce the same bytes under Engine 68.

## Terms that need care across documents

- SPEC phrases such as "the Renderer is nondeterministic" and "different SVG from the same Score" describe performances with different render seeds. The Project Context and implementation contract is "the same Score + same seed + same drawing conditions produce the same work"; this documentation uses the latter for reproducibility.
- `SPEC.ja.md` document version `v1.92.0` and app version `v2.15.28` are separate namespaces and are not treated as a mismatch.
- "Stage 2" meant, in the old implementation, the LLM stage that wrote a Score from DDL; now it means the LLM stage that only produces visible patch proposals for known holes. The shared Rust lowerer structures the Score.
- "Coerce" survives only in the context of older-Score compatibility (`coerce_saved_score`) and saved observation records (`coerce/observability.py`); it is not a generation stage for new works.
- "Sketch" means different things for the old Stage 0.5 (a layer that passed a sketch downstream in place of the description) and the current optional effect (supplementing place and light beside the description). The `fine` / `coarse` records of older works belong to the former.

## Possible concentration points

### C-01 `web/src/routes/+page.svelte`

Session, current-work submit/replay/stop, Batch/Demo asynchronous lifecycles, refinement orchestration and target identity, Settings administration slices, the largest Canvas/Settings views, and the shared-pipeline execution view now have route-instance or focused owners. The page keeps route lifecycle, modal/view state, component wiring, history/lineage cross-owner actions, the hand-off from DDL editing to the pipeline, and short display projections. It remains a composition seam, but it is no longer the canonical writer for high-change workflows.

Remaining line count alone does not show an ownership violation. Consider another split only when one reason for change crosses several owners, mutable state is duplicated, or an asynchronous failure boundary returns to the page.

### C-02 `server/src/inku_server/db.py`

The current `db.py` is the public compatibility and composition façade. Schema declaration, versioned startup, legacy-column coordination, baseline callbacks, backup, auth, settings, history, lineage, search, and variation authority have implementation owners under `persistence/`; the façade composes live dependencies and delegates existing import names.

Remaining line count or compatibility re-exports alone do not show an ownership violation. Future reductions should target only wrappers proven to have zero readers and should not remove public imports or call-time composition for line-count reasons.

### C-03 Large modules in the shared core

The old concentration in `api_core/routers/render.py` dissolved with the cutover; the router now holds only the compatibility projection and the entry for replaying older Scores. The crossing point for changes has moved into the shared core. `inku-ddl/src/score_lowering.rs` (about 7,800 lines), `semantic_association.rs` and `compiler_lock.rs` (about 4,600 lines each), and `inku-pipeline/src/machine.rs` (about 2,000 lines) are large, and on the Server side `pipeline_product.py:ProductPipelineEffects` holds four host responsibilities — preparation, provider, save, and replay — in one class.

Line count alone does not show an ownership violation. Consider a split only when independent reasons for change collide in the same module.

## Not confirmed from implementation

- Deployed processes, DB backend, queue utilization, and actual backup/log/output settings were not inspected because secrets and live environments were out of scope.
- External LLM provider reachability, model availability, and latency were not measured; only static routing was checked.
- Whether the Redis rate limiter is active in deployment is unknown because `INKU_REDIS_URL` values were not read.
- Compose runtime health and volume persistence were not started; only configuration was checked.
- The live app's route count. The review environment had no native wheel and app import failed, so the count comes from a static count of declarations (F-06).
- Current results of Android device acceptance (F-11).
- How the Mermaid diagrams actually display. All 44 diagrams in this set were parsed with the mermaid 11 parser, but their display on GitHub or Gitea was not checked.

## Specification-only parts

All major nodes and edges have public-source implementation evidence. No node represents live deployment state.

## Follow-up questions

1. Should the stale statements in the Project Context (F-05) and the Android specification note (F-02, F-03) be updated to match the current implementation?
2. Should the route-count test constant and the API surface baseline (F-06) be aligned with the current routes?
3. For the label-only gate (F-07) and stream progress events (F-08), should the SPEC follow the implementation, or the implementation return to the SPEC?
4. How should the unused Stage executor (F-10) and the reference corpus for Android device acceptance (F-11) be handled?

These are not changes made by this review, so they were not copied into the ledger automatically.
