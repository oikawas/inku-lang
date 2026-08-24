# Change impact map

## 変更領域と検査

| 変更領域 | 仕様・契約 | 主code | 直接test | 参照corpus / 生成物 | 追加確認 |
|---|---|---|---|---|---|
| saijiki語彙 | `SPEC.ja.md` §6, §12–14、語彙single source | `saijiki.py`, `schema.py`, language support | `test_saijiki_golden.py`, `test_reference.py`, `test_saijiki_api.py`, `test_saijiki_kt_is_current.py` | DDL corpus、Web/Android生成snapshot | docs check、Web i18n |
| schema宣言順 | Stage 2 optional field搬送率 | `schema.py`, `composer._score_tool_schema` | `test_thinness_declaration_position.py` | corpusはこのLLM搬送特性を検査しない | 専用test必須 |
| Stage 0.5 | 記述の代替消費者と`sketch_state` | `sketch.py`, `render.py`, Web/CLI/Android sender | `test_stage05_sketch.py`, `test_sketch_state.py`, `test_cli_sender_census.py`, Web sketch test | DDL/render corpus外 | client census、履歴migration |
| plugin文書 | Stage 1直後のcore writing-down | `plugins/document_format.py`, router | plugin format/v2 tests | DDL corpus `A-plugin-*` | plugin CRUD/auth、reference dump |
| Stage 1.5 | 意味非上書き、焦点、明示変奏 | `ddl_expander.py`, language support | expander、variation、staffage fold tests | DDL engine corpus | `check_frozen_corpora.py` |
| coerce | drop/repair、要求配達、hard ceiling、単一の名指し抽象色 | `coerce/normalize.py`, `coerce/compose.py`, `coerce/__init__.py` | composer/coerce/limits/relation tests | DDL engine corpus | `check_frozen_corpora.py` |
| render core/stroke | 同一Score+seed+解決済みoption、engine前進、粗いnative 1-call境界 | `core/crates/inku-render`; `inku-render-python`; `default/adapter.py`; `renderer.py`互換facade | Rust workspace test、adapter/facade契約、reference API、same-version platform sample | 現行Engine 41の610件、Engine 40は履歴保持 | version裁定、出力変更時2回再生成、pinned wheelとLinux CI |
| identity/history | `dh1`, `rh3`, legacy `rh2`, DB正本 | `identity.py`, `db.py`, rendering/history router | hash、integrity、lineage acceptance | Android parity fixtures | migrationと既存row互換 |
| API route/model | 96 route、公開3、response shape | `api.py`, `api_core/*` | route auth、module split、API surface baseline | なし | Web/CLI/Android sender census |
| Web route/workflow | ownerはrouteごとに1個、stale resultを現作品へ適用しない、stateless Paint operation | `+page.svelte`; `features/session/state.svelte.ts`; `features/work/state.svelte.ts`; `features/{batch,demo}/state.svelte.ts`; `features/run/current-work.ts`; `features/canvas/refinement-coordinator.svelte.ts` | route composition、current-work、Batch/Demo、refinement ownership test | なし | targeted unit、`npm run check`、`npm run build` |
| Web Canvas/history/refinement | history/lineage/viewportのsingle owner、target identity、focused Canvas view | `features/history/*`; `features/canvas/*`; `components/CanvasPanel.svelte` | history state/action、viewport、refinement、focused-view test | なし | targeted unit、`npm run check`、`npm run build` |
| Web Settings | aggregateが4 sliceを各1回生成、secretとdraftをfocused view外へ複製しない、3 registry境界 | `features/settings/*`; `components/SettingsModal.svelte`; `persisted-settings.ts`; `user-settings.ts`; `render-payload.ts` | Settings ownership/slice/focused-view、registry unit test | なし | targeted unit、`npm run check`、`npm run build`; 表示語変更時は`lint:i18n` |
| Web表示語 | 日英語彙、token | `i18n/*`, component | type/check | なし | `lint:i18n`、必要ならdocs check |
| CLI flag/API field | 公開HTTPのみ、help/manual同時更新 | `cli.py`, CLI README/manual | `cli/tests/test_cli.py`, sender census | bench artifactは別 | CLI経由機能試験 |
| Android移植 | server判定の1対1移植、Room schema | Kotlin pipeline/render/data | JVM tests、manifest parity、必要時instrumentation | Android server_reference版dir | device data backup規則、実機データを消さない |
| Docker/runtime | 2 service、persistent volume、health | compose/Dockerfiles/lockfiles | build/health/persistence | container image | milestone Compose検証 |

## CIとlocal gate

```mermaid
flowchart LR
    CHANGE["変更"]
    CI_SERVER["CI: server ruff + pytest"]
    CI_CLI["CI: CLI ruff + pytest"]
    CI_WEB["CI: web check + unit + lint:i18n"]
    CI_DOCS["CI: check_docs.py"]
    CI_CORPUS["CI: render/DDL corpus再生成"]
    CI_PREVIEW["CI: Android design preview再生成"]
    LOCAL_ANDROID["Local: Gradle JVM / 必要時実機"]
    RELEASE["Tag: container image build/publish"]

    CHANGE --> CI_SERVER
    CHANGE --> CI_CLI
    CHANGE --> CI_WEB
    CHANGE --> CI_DOCS
    CHANGE --> CI_CORPUS
    CHANGE --> CI_PREVIEW
    CHANGE -.->|"CIでは未実行"| LOCAL_ANDROID
    CHANGE -->|"release tag"| RELEASE
```

現行CIは通常push/PRで、server（ruff + pytest）、CLI（ruff + pytest）、Web（svelte-check + unit + lint:i18n）、公開文書（`check_docs.py`）、凍結render/DDL corpus再生成、Android design preview再生成を実行する（`checks.yml` は台帳I-192で追加）。AndroidのJVM/instrumentationテストはworkflow上に無く、local検証が必要である。

## 決定的層の特別規則

`coerce/`、`ddl_expander.py`、`core/crates/inku-render/`、native request境界、`render_engines/default/`、`renderer.py`、`schema.py`、`saijiki.py`、`language_support/` は決定的層である。Render Engine出力へ影響しうる変更では現行凍結corpusを再生成する。pytestのreference testは凍結fileとmanifestを読むだけの部分があり、generator再実行の代用にならない。native request/outputを変えないと証明したhost-only変更は、比例した直接検査とbounded same-version byte sampleを使う。

Rustのunit/ownership testだけでは描画同一性を証明しない。出力へ影響するcore変更では直接testに加えてRender Engine corpusを再生成し、portable algorithmとserialize後のbyte identityを同時に確認する。native binding変更ではさらに、pinned wheel build、import、engine identity、該当Linux runtime gateを行う。

## 根拠対応

`TEST-SERVER`, `TEST-CORPUS`, `TEST-ANDROID`, `TEST-WEBCLI`, `CI-GATES`。workflowと各package manifest/testを一次根拠とした。
