# Known differences and unknowns

## Specification and implementation differences

### F-01 Render Engine version (resolved during the review)

- At the start of the review, `PROJECT_CONTEXT.ja.md` named Render Engine 28 while the implementation was 29.
- Public commit `8b4d43cc` then updated the document to 29, matching `render_engines/default.py` and `server/reference/render-engine-29/manifest.json`.
- Result: **resolved**. The documentation snapshot follows the updated commit.

### F-02 Android specification-note versions (recurred)

- The header was synchronized with the implementation of the time on 2026-08-24, but the current header (last updated 2026-09-25) names `2.1.4-android.80`, render engine `67`, DDL engine version `20`, and a Server `ddl_engine_version` of 21.
- The implementation is Render Engine `68` (`core/crates/inku-render/src/lib.rs`) and `ddl_engine_version` `47` (`layer_versions.py`), and Android uses the same shared Rust pipeline.
- Result: **the version numbers are stale**. Engine identity is read from the packaged native library rather than a Kotlin product constant, so this is a documentation difference, not a runtime behavior difference. Handed to the Android owner on 2026-09-25.

### F-03 Android external-provider execution

- The "not implemented" section of the Android specification note lists external provider execution as not implemented and calls provider records compatibility data structures.
- Current `RoutingModelProvider` resolves enabled providers and connects to `GeminiModelProvider` and `OpenAiCompatibleProvider`. `SingleAttemptModelEffectProvider` sends shared-pipeline provider effects to them. The first half of the same note also describes the request conditions for Gemini and OpenAI-compatible providers.
- Result: **the "not implemented" section is stale**. An Anthropic-specific protocol implementation was not found, so parity across every provider is not claimed. Handed to the Android owner on 2026-09-25.

### F-04 Long historical Stage 1.5 description (resolved)

- In the earlier snapshot, `SPEC.ja.md` §12.11 described an old design that added mathematical, musical, and painterly candidates.
- The current §12.11 is rewritten as a typed transformation that takes only `CanonicalReady` typed meaning and changes only focus and explicit variation.
- Result: **resolved**.

### F-05 Stale statements in the Project Context (resolved)

- In the earlier snapshot, `PROJECT_CONTEXT.ja.md` was older than the implementation in its version table (Render Engine 66, DDL 11 / 45, Android `2.1.4-android.78`), its android section (render engine 42, DDL engine 20, the Android host owning Stage 1 / 1.5 / 2 and coerce), its test surfaces (CI enforcing `render-engine-42` and `ddl-engine-20`), its deterministic layers (`coerce/`, `ddl_expander.py`), the RAW trace, and the vocabulary's source of truth (`schema.py`).
- Both language editions were brought up to date on 2026-09-25.
- Result: **resolved**.

### F-06 Route-count test constants (resolved)

- `EXPECTED_ROUTE_COUNT` in `test_route_authorization.py` was still 95 and counted neither the eleven `/api/pipeline/*` routes added on 2026-09-13 (`2ad24df9`) nor the removal of `/api/prompts` on 2026-09-14 (`03bbd686`). `tests/data/api-surface-baseline.json` was also from before those changes.
- On 2026-09-25 the constant became 105, and the baseline was regenerated from the live app (105 operations, 160 schemas). `test_route_authorization.py` passes in an environment with the native wheel.
- Result: **resolved**.

### F-07 Gate for label-only descriptions (resolved)

- The cutover deleted the old `description_labels.py`, so leading numbers and bracketed comments reached Stage 1, the sketch, and color catalog selection as written, and a label-only description was no longer refused with 400 (a mismatch with `SPEC.ja.md` §12.16).
- On 2026-09-25 `description_labels.py` returned, and `PipelineService.start` (every description-origin path) and regeneration from a description cut labels only from the text handed to the core. The work keeps the description as written, and a label-only description is refused with 400.
- Result: **resolved**. Android never had the cut; this gate sits at the Server boundary.

### F-08 Stream progress events (resolved)

- After the cutover, the compatibility stream returned the final result as a single `done` line (a mismatch with `SPEC.ja.md` §12.10).
- On 2026-09-25 it returned to re-reading the execution and emitting `sketch` (when the sketch ran), `stage1`, `score`, and `done` in order. A refusal before the first event arrives as its HTTP status, and a failure after it (including an approval wait for a completion proposal) as an in-band `error` event. Token counts are null because the shared pipeline does not count them.
- Result: **resolved**.

### F-09 Stale descriptive text inside the implementation (resolved)

- `core/crates/inku-pipeline/README.md` (the number of effect tags, the candidate API not switching the runtime, and more), the docstring of `persistence/variation_authority.py`, and "runtime-disconnected" in `inku-ddl` doc comments remained after the shared pipeline became the normal runtime.
- They were corrected on 2026-09-25. The earlier snapshot's point about `inku-score` calling the raw Score JSON Schema Python-owned was withdrawn, because `score.schema.json` is still an artifact checked against Python's `Score`.
- Result: **resolved**.

### F-10 Leftover Stage executor (resolved)

- The Stage executor configured by `INKU_STAGE_WORKERS` / `INKU_STAGE_QUEUE_LIMIT` had no submitter, and `stage_execution` in `/api/settings/status` showed a pool nothing used and counters that never moved. `SPEC.ja.md` §22 and SETUP also described the executor.
- On 2026-09-25 the executor was removed, and `stage_execution` now reports the shared pipeline worker pool (`workers` is `max_workers`, `queue_limit` is `max_retained_runs`) and the counts of provider effects. The response schema did not change (it is one of the schemas frozen since before permission groups). SPEC §22 and SETUP were revised too.
- Result: **resolved**.

### F-11 Reference corpus for Android device acceptance

- `prepareRustParityAssets` and `NativeRenderDeviceTest` stage a few cases from `server/reference/render-engine-41` onto the device and compare SVG bytes. The test also asserts that `NativeRenderBridge.renderEngineVersion()` is `"41"`, and the path filter in `android-native.yml` names `render-engine-41`.
- The packaged library's Render Engine is 68, so the assertion cannot hold, and the expected SVGs are Engine 41 bytes with no guarantee of matching the current engine.
- Result: **inferred that device acceptance fails** (not run on a device). Fixing it needs changes such as generating the expected SVGs with the same commit's host core at build time, plus acceptance on the Pixel 9, so it was handed to the Android owner on 2026-09-25.

### F-12 Fake provider in the hole-completion API test

- The fake provider in `server/tests/test_pipeline_api.py::test_managed_api_persists_approved_patch_reload_and_legacy_fork` reads `base_source_digest` and similar fields from the hole-completion request body to answer it.
- The current hole-completion prompt (`inku.visible-ddl-hole-completion-prompt.v3`) does not pass digests or byte positions to the provider (`SPEC.md` §12.7.1). The test also fails at the commit before the fixes (`f910a11e`) with `KeyError: 'base_source_digest'`.
- Result: **the test has not followed prompt v3**. This update does not change it.

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
- Current results of Android device acceptance (F-11).
- How the Mermaid diagrams actually display. All 44 diagrams in this set were parsed with the mermaid 11 parser, but their display on GitHub or Gitea was not checked.

## Specification-only parts

All major nodes and edges have public-source implementation evidence. No node represents live deployment state.

## Follow-up questions

1. The Android specification note (F-02, F-03) and the reference corpus for device acceptance (F-11) await the Android owner's fix and acceptance.
2. Should the hole-completion API test (F-12) be brought to the request and response shape of hole-completion prompt v3?

These are not changes made by this review, so they were not copied into the ledger automatically.
