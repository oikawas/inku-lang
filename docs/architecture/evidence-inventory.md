# Evidence inventory

## Snapshot

| Subject | Value |
|---|---|
| Date | 2026-08-10 (JST) |
| Public branch / commit | `main` / `dfa7b25569c10f45fe504fdb39be1335eebb9e87` |
| Public uncommitted changes | None at the refreshed snapshot |
| Project Context | `PROJECT_CONTEXT.ja.md`, target `v2.11.18 / Build 874` |
| Japanese specification | `SPEC.ja.md`, document version `v1.92.0` |
| Web / app | `web/APP_VERSION` = `v2.11.18`; `web/BUILD_NUMBER` = `874` |
| Render Engine | implementation `default / 29` |
| DDL | `ddl_version=3`; `ddl_engine_version=11` |
| Android | `android/VERSION` = `2.1.4-android.22`; implementation reports Render Engine `26` |

Environment-variable names may appear, but values, credentials, production DB contents, and deployment-specific identifiers were outside the investigation.

## Inventory

| ID | Element or boundary | Responsibility | Implementation evidence | Specification evidence | Confidence |
|---|---|---|---|---|---|
| SYS-USER | Author | Starts descriptions, explicit derivations, settings, and export | `web/src/routes/+page.svelte`; `cli/src/inku_cli/cli.py`; `android/app/src/main/java/app/inku/mobile/ui/InkuApp.kt` | `SPEC.ja.md` §7, §23 | Confirmed |
| SYS-WEB | Web frontend | SvelteKit UI, same-origin API proxy, browser state | `+page.svelte`; `web/src/hooks.server.ts`; `web/package.json` | §7, §21 | Confirmed |
| SYS-CLI | CLI | Public HTTP API client and functional-test instrument | `cli/src/inku_cli/cli.py` (`ApiClient`, parser); no Server runtime import | §23 | Confirmed |
| SYS-ANDROID | Android | Separate Kotlin pipeline and Room history | `InkuRepository`; `LocalFallbackPipeline`; `DefaultSvgRenderer`; `InkuDatabase` | `android/ANDROID_SPEC.ja.md` | Confirmed |
| SYS-API | FastAPI app | Middleware, lifespan, and router assembly | `server/src/inku_server/api.py` (`app`, `_lifespan`, `include_router`) | §22; Project Context | Confirmed |
| SYS-LLM | LLM providers | External inference for Stages 0.5, 1, and 2 | `model_settings.py`; `interpreter.py`; `composer.py` | §12.5–12.8 | Confirmed |
| SYS-DB | Server DB | Canonical history, lineage, users, sessions, and settings | `db.py` (`HistoryRow`, `add_item`) | §21–22 | Confirmed |
| SYS-FILES | Work-file area | Optional description, DDL, JSON, SVG, and PNG derivatives | `api_core/rendering.py` (`_save_output_files`, `_submit_history_artifact_save`) | §21 | Confirmed |
| SYS-LOG | Log area | stdout and rotating application file | `logging_setup.py:configure_logging` | §21 | Confirmed |
| SYS-BACKUP | DB backup area | SQLite replicas and manual/scheduled generations | `db.py:create_db_backup`, `ensure_scheduled_db_backup` | §22 | Confirmed |
| API-ROUTERS | Router set | 10 groups and 82 endpoints | `api_core/routers/{public,auth,me,plugins,settings,users,history,lineage,render,feedback}.py`; `test_route_authorization.py` | Project Context | Confirmed |
| API-AUTH | Authentication and authorization | Bearer/cookie sessions, role guards, six public paths | `api_core/deps.py`; `routers/auth.py`; `test_route_authorization.py` | §22 | Confirmed |
| API-LIMIT | Capacity boundaries | Body, request, render, Stage, and file-queue limits | `security.py`; `api_core/state.py`; `render.py:_run_with_hard_timeout` | §22 | Confirmed |
| PIPE-SKETCH | Stage 0.5 Sketch from life | Optional natural-language observation and state record | `sketch.py`; `render.py:_resolved_sketch`; `SketchDetail` | §12.15; Project Context | Confirmed |
| PIPE-S1 | Stage 1 interpretation | Description to Instructions (normalized DDL) | `interpreter.py:interpret_detail`, `_build_system_prompt_parts` | §12.1, §12.6 | Confirmed |
| PIPE-PLUGIN | Declarative plugin | Deterministic writing-down into core DDL and optional instructions | `plugins/document_format.py`; `render.py:_call_compose_detail` | §4.4–4.7 | Confirmed |
| PIPE-S15 | Stage 1.5 | Deterministic focus rewrite and explicit variation | `ddl_expander.py:expand_intermediate_ddl`, `_expand_ja`, `_expand_en` | §12.11–12.13, §14.5 | Confirmed |
| PIPE-S2 | Stage 2 | DDL to JSON Score through a schema tool | `composer.py:compose`, `_score_tool_schema`; `schema.py:Score` | §12.7 | Confirmed |
| PIPE-COERCE | Coerce/validation | Drop invalid values, deliver requests, enforce ceilings, and retain one explicitly named abstract color | `coerce/__init__.py`; `coerce/normalize.py`; `coerce/compose.py` | §10, §12.12, §14.6 | Confirmed |
| PIPE-RENDER | Render Engine | JSON Score and seeds to SVG and performance metadata | `render_engines/default.py:DefaultRenderEngine`; `renderer.py:render` | §12.14, §13.8 | Confirmed |
| PIPE-HISTORY | History persistence | Store Server Paint outputs in the DB | `render.py:_paint_events`; `rendering.py:_add_history_item`; `db.py:add_item` | §21 | Confirmed |
| DATA-DH1 | `dh1` | Identity of a normalized description | `identity.py:description_hash` | Project Context | Confirmed |
| DATA-RH3 | `rh3` | Edition identity from Score, render seed, Wild, engine, and color catalog | `db.py:render_hash_for_item`; `test_render_hash.py` | Project Context | Confirmed |
| DATA-RH2 | Legacy `rh2` | Compatibility with the older edition hash | `db.py:_legacy_render_hash_for_item`; `test_render_hash.py` | Project Context | Confirmed |
| DATA-LINEAGE | Lineage nodes and edges | Connect only an explicit parent and derivation kind | `LineageNodeRow`; `LineageEdgeRow`; `db.py:add_item`; `test_lineage_acceptance.py` | §21; Project Context | Confirmed |
| DATA-SAIJIKI | Saijiki | Vocabulary source for prompts, markers, relation literals, display, and references | `saijiki.py`; `test_saijiki_golden.py` | Project Context | Confirmed |
| WEB-FEATURES | Web feature modules | Separate batch, export, catalog, inspection, Wild, and related state | `web/src/lib/features/<name>/` | Project Context | Confirmed |
| WEB-REGISTRY | Three settings registries | Collect local storage, user settings, and render payload fields | `persisted-settings.ts`; `user-settings.ts`; `render-payload.ts` | Project Context | Confirmed |
| WEB-I18N | UI language and tokens | Japanese/English UI, English glossary, and CSS tokens | `web/src/lib/i18n/*`; `GLOSSARY.md`; `+page.svelte` | §6–7 | Confirmed |
| OPS-COMPOSE | Compose distribution | API/Web services and persistent volume | `compose.yaml`; Server and Web Dockerfiles | §22 | Confirmed |
| TEST-SERVER | Server checks | pytest, API surface, authorization, and route ownership | `server/tests`; `test_api_surface.py`; `test_route_authorization.py` | §11; Project Context | Confirmed |
| TEST-CORPUS | Frozen corpora | Rebuild and compare 588 Render Engine 34 cases and 49 DDL Engine 19 cases | `server/reference/render-engine-34/manifest.json`; `ddl-engine-19/manifest.json`; workflow | §11, §22 | Confirmed |
| TEST-ANDROID | Android reference | Pin Server-version fixtures with manifests | `android/app/src/test/resources/server_reference/`; `test_android_reference_fixtures_are_current.py` | Android specification | Confirmed |
| TEST-WEBCLI | Web/CLI checks | Svelte checks/unit/lint and CLI pytest | `web/package.json`; Web tests; `cli/tests/test_cli.py` | Project Context | Confirmed |
| CI-GATES | Current CI | Corpus rebuild, Android design preview, and release-tag container build | `.github/workflows/reference-corpus.yml`; `release.yml` | §11, §22 | Confirmed |

## Confidence

- **Confirmed**: Direct evidence exists in an entry point, call site, schema, or test.
- **Specification**: Present in the specification but not confirmed in the current implementation.
- **Inferred**: Derived from multiple static sources, with the reason stated nearby.
- **Unknown**: Requires measurement or deployment information not examined here.
