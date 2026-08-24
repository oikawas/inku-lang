# Known differences and unknowns

## Specification and implementation differences

### F-01 Render Engine version — resolved during the original review

- At the beginning of the original review, `PROJECT_CONTEXT.ja.md` named Render Engine 28 while implementation was 29.
- Public commit `8b4d43cc` aligned Project Context with `render_engines/default.py` and `server/reference/render-engine-29/manifest.json`.
- Status: resolved. The current architecture baseline is later still.

### F-02 Android specification snapshot — resolved

- The former snapshot disagreed with implementation on the Android and Render Engine versions.
- On 2026-08-24 the opening was aligned to `2.1.4-android.63`, shared Rust Engine 41, and DDL Engine 20.
- Status: resolved. Engine identity now comes from the packaged native library rather than a Kotlin product constant.

### F-03 Android external-provider execution

- The Android specification says external-provider execution is not implemented.
- Current `RoutingModelProvider` resolves an enabled provider and calls `OpenAiCompatibleProvider.generate` / `fetchModels`; `InkuRepository` uses that router for Stage 1, Stage 2, and demo paths.
- Status: stale for the OpenAI-compatible path. No equivalent claim is made for provider-specific Anthropic or Gemini protocols.

### F-04 Long older Stage 1.5 account

- `SPEC.ja.md` §12.11 describes the older mathematical, musical, and painterly candidate additions.
- §12.12 overrides that design; current code reframes focus and adds no sentence of its own.
- Status: not a current implementation mismatch, but easy to misread when §12.11 is read alone.

## Terms that need context

- “The Renderer is non-deterministic” and “different SVG from the same Score” in the specification describe different render seeds. The implementation contract is: same JSON Score + same render seed + same performance conditions reproduce the same work.
- `SPEC.ja.md` document version `v1.92.0` and app `v2.13.47` are separate namespaces, not a mismatch.

## Concentrated responsibilities

### C-01 `web/src/routes/+page.svelte`

Session, current-work submit/replay/stop, Batch/Demo asynchronous lifecycles, refinement orchestration and target identity, Settings administration slices, and the largest Canvas/Settings views now have route-instance or focused owners. The page retains route lifecycle, modal/view state, component wiring, history/lineage cross-owner actions, and short presentation projections. It remains a composition seam, but it is no longer the canonical writer for those high-change workflows.

Its remaining line count alone does not demonstrate an ownership violation. Another split is warranted only when one change reason crosses multiple owners, mutable state is duplicated, or an asynchronous failure boundary moves back into the page.

### C-02 `server/src/inku_server/db.py`

One module holds schema, migration, auth, settings, backup, history, lineage, and search. Transactions are explicit, but responsibility is concentrated.

### C-03 `api_core/routers/render.py`

Request/response models, provider failures, fallback, Stage orchestration, trace, and history handoff meet in one router module.

## Not confirmed from source

- Deployed processes, DB backend, queue utilization, and actual backup/log/output settings
- Current provider reachability, model availability, and latency
- Whether the Redis rate limiter is active in a deployment
- Current Compose state and volume persistence
- Executable Mermaid validation; no existing CLI was available in the original review

## Specification-only diagram content

Every major node and edge in this set has public implementation evidence. The diagrams do not claim a current deployment topology.

## Follow-up questions

1. Should the opening Android snapshot and external-provider statement be aligned with current code?
2. Should the remaining route-shell/history-lineage coordination, DB module, or render router be the next concentration reviewed by change reason?
3. Should the Android JVM tests move into CI? The Server, CLI, Web, and document gates entered CI with `checks.yml` (ledger I-192).

These questions are not copied automatically into `PROJECT_CONTEXT.ja.md` or `SPEC.ja.md`.
