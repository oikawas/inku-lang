# Change impact map

## Change areas and checks

| Change area | Contract | Main code | Direct checks | Frozen corpus or output | Additional gate |
|---|---|---|---|---|---|
| Saijiki vocabulary | `SPEC.ja.md` §6, §12–14; one vocabulary source | `saijiki.py`, `schema.py`, language support | Saijiki golden/reference/API/Kotlin-current tests | DDL corpus; Web/Android snapshots | Docs and Web terminology |
| Schema declaration order | Delivery rate of optional Stage 2 fields | `schema.py`, `composer._score_tool_schema` | `test_thinness_declaration_position.py` | Corpus does not test this model behavior | Dedicated check required |
| Stage 0.5 | Alternate description consumer and `sketch_state` | `sketch.py`, render router, client senders | Stage 0.5, state, sender-census, Web tests | Outside DDL/render corpora | Client census; history migration |
| Plugin document | Core writing-down immediately after Stage 1 | `plugins/document_format.py`, render router | Plugin format/v2 tests | DDL `A-plugin-*` cases | CRUD/auth and reference dump |
| Stage 1.5 | No semantic overwrite; focus; explicit variation | `ddl_expander.py`, language support | Expander, variation, staffage-fold tests | DDL Engine corpus | `check_frozen_corpora.py` |
| Coerce | Drop/repair, request delivery, ceilings, one named abstract color | `coerce/normalize.py`, `compose.py`, `__init__.py` | Coerce, limit, relation, and named-color tests | DDL Engine corpus | `check_frozen_corpora.py` |
| Renderer/strokes | Same Score+seed; forward-only engine | `renderer.py`, `stroke_engine.py`, `render_engines/default.py` | Renderer contracts and platform stability | 553 Render Engine 30 cases | Version bump; rebuild twice; Linux CI |
| Identity/history | `dh1`, `rh3`, legacy `rh2`, DB canonical data | `identity.py`, `db.py`, rendering/history router | Hash, integrity, lineage acceptance | Android parity fixtures | Migration and stored-row compatibility |
| API route/model | 82 routes, six public paths, response shape | `api.py`, `api_core/*` | Route auth, module split, API baseline | None | Web/CLI/Android sender census |
| Web settings feature | Three registries and local/user/payload boundaries | `web/src/lib/features/*`, `+page.svelte` | Registry unit tests and route-source contracts | None | `npm run check`, unit and relevant lint |
| English Web text | Japanese/English terms and tokens | `i18n/*`, components | Type/check | None | `lint:i18n`; docs check when relevant |
| CLI flag/API field | Public HTTP only; help/manual move together | `cli.py`, CLI docs/manual | CLI tests and sender census | Bench output is separate | Functional test through CLI |
| Android port | One-to-one port of Server decisions; Room schema | Kotlin pipeline/render/data | JVM, manifest parity, device checks as needed | Android Server-reference directories | Preserve device data |
| Docker/runtime | Two services, persistent volume, health | Compose, Dockerfiles, lockfiles | Build, health, persistence | Container output | Milestone Compose verification |

## CI and local gates

```mermaid
flowchart LR
    CHANGE["Change"]
    CI_CORPUS["CI: rebuild render/DDL corpora"]
    CI_PREVIEW["CI: rebuild Android design preview"]
    LOCAL_SERVER["Local: pytest + ruff"]
    LOCAL_WEB["Local: check + unit + lint"]
    LOCAL_CLI["Local: CLI pytest + functional test"]
    LOCAL_ANDROID["Local: Gradle JVM / device when needed"]
    RELEASE["Tag: container build and publication"]

    CHANGE --> CI_CORPUS
    CHANGE --> CI_PREVIEW
    CHANGE -.->|"not in current CI"| LOCAL_SERVER
    CHANGE -.->|"not in current CI"| LOCAL_WEB
    CHANGE -.->|"not in current CI"| LOCAL_CLI
    CHANGE -.->|"not in current CI"| LOCAL_ANDROID
    CHANGE -->|"release tag"| RELEASE
```

On ordinary pushes and pull requests, current workflows rebuild the frozen render/DDL corpora and Android design preview. They do not run pytest, ruff, Svelte checks, Web units/lint, CLI pytest, or Android unit tests.

## Special rule for deterministic layers

The deterministic-layer list for `server/scripts/check_frozen_corpora.py` is `coerce/`, `ddl_expander.py`, `renderer.py`, `stroke_engine.py`, `schema.py`, `saijiki.py`, and `language_support/{ja,en}.py`. Reference tests that only compare stored files do not replace running the rebuild.

## Evidence map

Evidence: `TEST-SERVER`, `TEST-CORPUS`, `TEST-ANDROID`, `TEST-WEBCLI`, `CI-GATES`.
