# 根拠インベントリ

## スナップショット

| 項目 | 値 |
|---|---|
| 作成日 | 2026-08-10（JST）、全面更新 2026-08-17、renderer境界更新 2026-08-22 |
| 公開側 branch / commit | `main` / `88506e0e10ffa38fdeeac3f74dfe1c5f07b3e37c` |
| 公開側の未コミット変更 | なし（更新後snapshot確認時） |
| Project Context | `PROJECT_CONTEXT.ja.md`、対象 `v2.13.47 / Build 937` |
| 日本語仕様 | `SPEC.ja.md`、文書版 `v1.92.0` |
| Web / app | `web/APP_VERSION` = `v2.13.47`、`web/BUILD_NUMBER` = `946` |
| Render Engine | 実装 `default` / `40` |
| DDL | `ddl_version=3` / `ddl_engine_version=20` |
| Android | `android/VERSION` = `2.1.4-android.47`、実装が名乗る Render Engine `35` |

「公開可否」は、この表の記述をそのまま公開できるかを示す。環境変数は名前だけを扱い、値、資格情報、実DB、配備先固有の識別子は調査対象外とした。

## インベントリ

| ID | 要素／境界 | 責任 | 実装上の根拠 | 仕様上の根拠 | 信頼度 | 公開可否 |
|---|---|---|---|---|---|---|
| SYS-USER | 利用者 | 記述、明示的な派生、設定、書き出しを開始する | `web/src/routes/+page.svelte`; `cli/src/inku_cli/cli.py`; `android/app/src/main/java/app/inku/mobile/ui/InkuApp.kt` | `SPEC.ja.md` §7, §23 | 確認済み | 公開可 |
| SYS-WEB | Web frontend | SvelteKit UI、同一origin API proxy、ブラウザ状態 | `web/src/routes/+page.svelte`; `web/src/hooks.server.ts`; `web/package.json` | §7, §21 | 確認済み | 公開可 |
| SYS-CLI | CLI | 公開HTTP APIクライアント、機能試験とベンチ補助 | `cli/src/inku_cli/cli.py` (`ApiClient`, parser); server内部importなし | §23 | 確認済み | 公開可 |
| SYS-ANDROID | Android | Kotlinによる端末内の別パイプライン、Room履歴 | `InkuRepository`, `LocalFallbackPipeline`, `DefaultSvgRenderer`, `InkuDatabase` | `android/ANDROID_SPEC.ja.md` | 確認済み | 公開可 |
| SYS-API | FastAPI app | middleware、lifespan、router組立て | `server/src/inku_server/api.py` (`app`, `_lifespan`, `include_router`) | §22; Project Context「server」 | 確認済み | 公開可 |
| SYS-LLM | LLM providers | Stage 0.5/1/2等の外部推論 | `model_settings.py` (`provider_for_model`, `connection_for`); `interpreter.py`; `composer.py` | §12.5–12.8 | 確認済み | 抽象化すれば可 |
| SYS-DB | Server DB | 履歴、系譜、利用者、session、設定の正本 | `db.py` (`HistoryRow`ほか、`add_item`) | §21–22 | 確認済み | 公開可 |
| SYS-FILES | 作品ファイル領域 | SVG/JSON/DDL/入力/PNGの任意派生保存 | `api_core/rendering.py` (`_save_output_files`, `_submit_history_artifact_save`) | §21 | 確認済み | 抽象化すれば可 |
| SYS-LOG | ログ領域 | stdoutとアプリ内ローテーションファイル | `logging_setup.py` (`configure_logging`) | §21 | 確認済み | 抽象化すれば可 |
| SYS-BACKUP | DBバックアップ領域 | SQLite replica、自動/手動世代 | `db.py` (`create_db_backup`, `ensure_scheduled_db_backup`) | §22 | 確認済み | 抽象化すれば可 |
| API-ROUTERS | Router群 | 10分類、96 endpoint（件数の正本は `test_route_authorization.py` の `EXPECTED_ROUTE_COUNT`） | `api_core/routers/{public,auth,me,plugins,settings,users,history,lineage,render,feedback}.py`; `test_route_authorization.py` | Project Context「server」 | 確認済み | 公開可 |
| API-AUTH | 認証・認可 | Bearer/cookie session、role guard、公開3経路 | `api_core/deps.py`; `routers/auth.py`; `test_route_authorization.py` | §22 | 確認済み | 公開可 |
| API-LIMIT | 容量境界 | body、request、render、Stage、保存queueの上限 | `security.py`; `api_core/state.py`; `render.py:_run_with_hard_timeout` | §22 | 確認済み | 公開可 |
| PIPE-LIMITS | 描画量の上限 | 展開primitive数・命令数・個数読み取りの上限を1箇所で定義し、request単位で解決して作品へ記録 | `limits.py` (`Limits`, `DEFAULT_LIMITS`); `render.py:_limits_for_render` | Project Context「設計契約」 | 確認済み | 公開可 |
| PIPE-SKETCH | Stage 0.5 写生 | 任意の自然文写生と状態記録 | `sketch.py`; `render.py:_resolved_sketch`; `SketchDetail` | §12.15; Project Context「パイプライン」 | 確認済み | 公開可 |
| PIPE-S1 | Stage 1 解釈 | 記述から正規化DDL | `interpreter.py:interpret_detail`, `_build_system_prompt_parts` | §12.1, §12.6 | 確認済み | 公開可 |
| PIPE-PLUGIN | 宣言的プラグイン | 検証済み文書をcore DDL/instructionへ決定的展開 | `plugins/document_format.py` (`PluginDocumentManager`, `expand_plugin_ddl`); `render.py:_call_compose_detail` | §4.4–4.7 | 確認済み | 公開可 |
| PIPE-S15 | Stage 1.5 | 決定的な焦点書換えと明示変奏 | `ddl_expander.py:expand_intermediate_ddl`, `_expand_ja`, `_expand_en` | §12.11–12.13, §14.5 | 確認済み | 公開可 |
| PIPE-S2 | Stage 2 | DDLからJSON Score、schema tool利用 | `composer.py:compose`, `_score_tool_schema`; `schema.py:Score` | §12.7 | 確認済み | 公開可 |
| PIPE-COERCE | coerce/validation | 不正値drop、要求配達、天井、描画可能性確保 | `coerce/__init__.py:coerce_score`; `coerce/normalize.py`; `coerce/compose.py` | §10, §12.12, §14.6 | 確認済み | 公開可 |
| PIPE-RENDER | Render Engine | ScoreとseedからSVGと描画metadata | `render_engines/__init__.py:current_render_engine`; `render_engines/default/adapter.py:DefaultRenderEngine`; `render_engines/default/engine.py:render_result`; `renderer.py:render`（SVG-only互換facade） | §12.14, §13.8 | 確認済み | 公開可 |
| PIPE-HISTORY | 履歴保存 | `/api/paint`のserver生成物をDBへ保存 | `render.py:_paint_events`; `rendering.py:_add_history_item`; `db.py:add_item` | §21 | 確認済み | 公開可 |
| DATA-DH1 | `dh1` | 正規化した記述の同一性 | `identity.py:description_hash` | Project Context「設計契約」 | 確認済み | 公開可 |
| DATA-RH3 | `rh3` | Score、render seed、wild、engine、色カタログによるedition同一性 | `db.py:render_hash_for_item`; `test_render_hash.py` | Project Context「設計契約」 | 確認済み | 公開可 |
| DATA-RH2 | legacy `rh2` | 旧edition hashの互換保持 | `db.py:_legacy_render_hash_for_item`; `test_render_hash.py` | Project Context「設計契約」 | 確認済み | 公開可 |
| DATA-LINEAGE | 系譜node/edge | 明示された親とderivation kindだけをedge化 | `LineageNodeRow`, `LineageEdgeRow`, `db.py:add_item`; `test_lineage_acceptance.py` | §21、Project Context「設計契約」 | 確認済み | 公開可 |
| DATA-SAIJIKI | 歳時記 | prompt、marker、relation、Web表示、referenceの語彙正本 | `saijiki.py` (`SAIJIKI`, `prompt_block`, `display_categories`); `test_saijiki_golden.py` | Project Context「語彙」 | 確認済み | 公開可 |
| DATA-FALLBACK | fallbackの記録 | 各層のfallbackを列として保存（Stage 1 = `interpret_fallback`、Stage 2 = `compose_fallback`、写生 = `sketch_state`）。記録なし（列導入前の作品）とfallbackでないを区別する | `db.py:HistoryRow`; `web/src/lib/composeFallback.ts` | Project Context「設計契約」 | 確認済み | 公開可 |
| WEB-FEATURES | Web feature modules | batch、export、catalog、inspection、wild、Settings管理、1回のPaint run、lineage query、history browsingを分離 | `web/src/lib/features/<name>/` | Project Context「web」 | 確認済み | 公開可 |
| WEB-REGISTRY | 3設定登録簿 | localStorage、user settings、render payloadを集約 | `persisted-settings.ts`; `user-settings.ts`; `render-payload.ts` | Project Context「web」 | 確認済み | 公開可 |
| WEB-I18N | UI語彙・token | 日英UI、英語用語集、CSS token | `web/src/lib/i18n/*`; `GLOSSARY.md`; `+page.svelte` `:root` | §6–7 | 確認済み | 公開可 |
| OPS-COMPOSE | Compose配布 | API/Webの2 serviceと永続volume | `compose.yaml`; `server/Dockerfile`; `web/Dockerfile` | §22 | 確認済み | 抽象化すれば可 |
| TEST-SERVER | Server検査 | pytest、API surface、認可、route所在 | `server/tests`; `test_api_surface.py`; `test_route_authorization.py` | §11; Project Context「検査面」 | 確認済み | 公開可 |
| TEST-CORPUS | 凍結コーパス | render 40の610件、DDL 20の49件を再生成照合 | `server/reference/render-engine-40/manifest.json`; `ddl-engine-20/manifest.json`; workflow | §11, §22 | 確認済み | 公開可 |
| TEST-ANDROID | Android参照 | server版ごとのfixtureをmanifest固定 | `android/app/src/test/resources/server_reference/`; `server/tests/test_android_reference_fixtures_are_current.py` | Android仕様メモ | 確認済み | 公開可 |
| TEST-WEBCLI | Web/CLI検査 | Svelte check/unit/lint、CLI pytest | `web/package.json`; `web/src/**/*.test.ts`; `cli/tests/test_cli.py` | Project Context「検査面」 | 確認済み | 公開可 |
| CI-GATES | 現在のCI | server/cli lint+pytest、web check+unit+lint:i18n、docs検査、corpus・Android design preview再生成、tag時image build | `.github/workflows/checks.yml`; `reference-corpus.yml`; `release.yml` | §11, §22 | 確認済み | 公開可 |

## 信頼度の読み方

- **確認済み**: entry point、呼び出し、schema、testのいずれかで直接確認した。
- **仕様のみ**: 仕様にあるが、現行実装で対応を確認できない。
- **実装から推定**: 複数の静的根拠から推定した。推定理由を本文に添える。
- **未確認**: 実測または秘密情報が必要で、今回の境界では確認していない。
