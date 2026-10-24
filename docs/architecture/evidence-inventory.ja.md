# 根拠インベントリ

## スナップショット

| 項目 | 値 |
|---|---|
| 作成日 | 2026-08-10（JST）、全面更新 2026-08-17、Web・core refactoring再照合 2026-08-24、SQLite persistence refactoring完了を再照合 2026-08-27、Typed DDL Step 8完了を再照合 2026-09-02、共有Rust pipeline cutover後の全面再照合 2026-09-25、2026-10-24までのcoreの更新を再照合 2026-10-24 |
| source branch / 実装commit | `main` / `086fbe3ea45dd0784b911a7599ef88f60b0c85dc`（本書更新前の実装baseline） |
| source状態 | 実装baselineではclean。2026-10-24の更新は文書だけで、実装を変えない |
| Project Context | `PROJECT_CONTEXT.ja.md`、対象 `v2.15.244 / Build 1320`（版の表は正本を名指す。残る古い記述は`known-differences.ja.md` F-14） |
| 日本語仕様 | `SPEC.ja.md`、文書版 `v1.92.0` |
| Web / app | `web/APP_VERSION` = `v2.15.244`、`web/BUILD_NUMBER` = `1320` |
| Render Engine | `default` / `93`（`core/crates/inku-render/src/lib.rs`）、core API `0.1.0` |
| DDL | `ddl_version=26` / `ddl_engine_version=71`（`server/src/inku_server/layer_versions.py`） |
| 共有pipeline binding | binding `1.1.0`、protocol `1.0.0`（`pipeline_candidate.py:PipelineBinding`が一致を要求） |
| Score | 新作はresource-awareなcompact 0.10を基準に、使う表現に応じた最小版（0.10〜0.22）。旧作品の0.1.0〜0.9.0とversionなしartifactは互換読取 |
| Android | `android/VERSION` = `2.1.4-android.105`、`android/BUILD_NUMBER` = `148446`、Room schema 14、共有Rust pipelineと同梱coreのRender Engine |
| macOS | `apple/VERSION` = `1.1.5`、`apple/BUILD_NUMBER` = `13`（Server／Webと別の採番）、GRDBの物理schema、UniFFIで共有Rust core |
| Server DB | migration registry version 5（`image_input_provenance`） |
| Server API | 135 route（`test_route_authorization.py`の`EXPECTED_ROUTE_COUNT`）、公開allowlist 5 path |

「公開可否」は、この表の記述をそのまま公開できるかを示す。環境変数は名前だけを扱い、値、資格情報、実DB、配備先固有の識別子は調査対象外とした。

## インベントリ

| ID | 要素／境界 | 責任 | 実装上の根拠 | 仕様上の根拠 | 信頼度 | 公開可否 |
|---|---|---|---|---|---|---|
| SYS-USER | 利用者 | 記述、画像（Server・Webの画像タブ）、direct DDL、補完案の承認、明示的な派生（推敲とAI自動推敲を含む）、設定、書き出しを開始する | `web/src/routes/+page.svelte`; `cli/src/inku_cli/cli.py`; `android/app/src/main/java/app/inku/mobile/ui/InkuApp.kt`; `apple/Sources/InkuMac/` | `SPEC.ja.md` §7, §12.6.6, §12.7.1, §23 | 確認済み | 公開可 |
| SYS-WEB | Web frontend | SvelteKit UI、同一origin API proxy、ブラウザ状態、共有pipeline実行の表示と作者操作の転送 | `web/src/routes/+page.svelte`; `web/src/hooks.server.ts`; `web/src/lib/features/pipeline/`; `web/package.json` | §7, §12.7.1, §21 | 確認済み | 公開可 |
| SYS-CLI | CLI | 公開HTTP APIクライアント、機能試験とベンチ補助。画像から描く`paint --image`は`/api/pipeline/images`と`/api/pipeline/variations`を使う | `cli/src/inku_cli/cli.py` (`ApiClient`, parser); server内部importなし | §23 | 確認済み | 公開可 |
| SYS-ANDROID | Android | Kotlin/Compose UI、Room履歴、provider transport、共有Rust pipeline・renderer・raster・Skia表示へのJNI host | `InkuRepository`; `AndroidWorkPipeline`; `SharedPipelineHost`; `NativePipelineBridge`; `SingleAttemptModelEffectProvider`; `AndroidRenderHost`; `RustArtworkRasterizer`; `AndroidDisplayRenderer`; `NativeDisplayBridge`; `InkuDatabase` | `android/ANDROID_SPEC.ja.md`; `SPEC.ja.md` §12.7.1 | 確認済み | 公開可 |
| SYS-MACOS | macOS | SwiftUIのUI、GRDB履歴、provider transport、UniFFIで共有Rust pipeline・renderer・raster・Skia表示へ繋ぐhost。Server APIは呼ばない。拡大の窓はApple siliconで別processのSkia Graphiteが描く | `apple/Sources/InkuMac/`; `apple/Packages/InkuHost/Sources/InkuHost/{PipelineHost,ProviderTransport}.swift`; `apple/Packages/InkuCore/`; `apple/Packages/InkuPersistence/`; `core/crates/inku-display-gpu` | `apple/SWIFT_SPEC.ja.md`; `SPEC.ja.md` §12.7.1 | 確認済み | 公開可 |
| SYS-API | FastAPI app | middleware、lifespan、用途別routerと共有pipeline routerの組立て | `server/src/inku_server/api.py` (`app`, `_lifespan`, `include_router`, `pipeline_router`, `register_pipeline_errors`) | §22; Project Context「server」 | 確認済み | 公開可 |
| SYS-CORE | 共有Rust core | Score型、typed DDL compiler、authoring state machine、Render Engine、SVG raster、Skiaの画面表示をhost非依存に所有する | `core/Cargo.toml`（10 crate）; `core/crates/{inku-score,inku-ddl,inku-pipeline,inku-render,inku-svg-raster,inku-display}` | §12.7.1, §12.14 | 確認済み | 公開可 |
| SYS-LLM | LLM providers | 写生、色カタログ選択、Stage 1下絵、構図の読み、法則の段、配色の段、known-hole補完、画像からの色カタログ選び・DDLの書き・見比べ、取り合わせの一文選び、奥書の外部推論 | `pipeline_provider.py` (`SingleAttemptProvider`, `resolved_stage_model`); `model_settings.py`; `vision_client.py`; 共有core `provider_wire.rs`; Android `RoutingModelProvider` | §12.5–12.8 | 確認済み | 抽象化すれば可 |
| SYS-DB | Server DB | SQLite正本とdomain persistence。`db.py`は互換・composition façade | `persistence/{config,engine,schema,access,accounts,groups,sessions,identities,settings,history,search,lineage,okugaki,feedback,variation_authority}.py`; `provider_observation.py`; `db.py` | §21–22 | 確認済み | 公開可 |
| SYS-FILES | 作品ファイル領域 | SVG/JSON/DDL/入力/PNGの任意派生保存 | `api_core/rendering.py` (`_submit_history_artifact_save`); `pipeline_product.py:save_result`からのjob投入 | §21 | 確認済み | 抽象化すれば可 |
| SYS-LOG | ログ領域 | stdoutとアプリ内ローテーションファイル。compiler結果は診断の件数と安全な投影だけを記録する | `logging_setup.py` (`configure_logging`); `pipeline_product.py` (`pipeline_compiler_outcome`) | §21 | 確認済み | 抽象化すれば可 |
| SYS-BACKUP | DBバックアップ領域 | migration・手動・定時で共有するWAL-safe SQLite snapshotと世代管理 | `persistence/backup.py`; `db.py`の薄いdelegate | §22 | 確認済み | 抽象化すれば可 |
| DATA-MIGRATION | Server schema lifecycle | SQLite-only事前検証、versioned registry（v1 legacy baseline → v2 共有pipeline sidecar → v3 provider観測 → v4 単一のDDL本文 → v5 画像入力の記録）、allowlisted legacy fingerprint、単一writer移行、PK/canonical history byte invariant、fail-closed | `persistence/{config,engine,migrations,legacy_schema,invariants,backup}.py`; portable persistence tests | §22 | 確認済み | 公開可 |
| API-ROUTERS | Router群 | 用途別の13 router moduleと`/api/pipeline`の共有pipeline router。135 endpoint（件数の正本は`test_route_authorization.py`の`EXPECTED_ROUTE_COUNT`。router別は`server-components.ja.md`） | `api_core/routers/{public,auth,me,plugins,settings,users,history,lineage,render,feedback,description,chatgpt,autonomous}.py`; `pipeline_api.py:pipeline_router` | Project Context「server」 | 確認済み | 公開可 |
| API-AUTH | 認証・認可 | Bearer/cookie session、role guard、理由付きの公開allowlist 5 path。管理者でないleaderは自分のユーザーグループの利用者だけを管理する。共有pipeline routerは`_current_user`を所有者として全操作へ渡す | `api_core/deps.py`; `routers/auth.py`; `routers/users.py`; `api.py`（`pipeline_router(_pipeline_service, _current_user, ...)`）; `test_route_authorization.py`; `test_a_leader_keeps_members_in_their_group.py` | §22 | 確認済み | 公開可 |
| API-LIMIT | 容量境界 | body、request、render、pipeline worker・保持run・effect段数、envelope byte、保存queue、画像の受取（32 MiB、所有者ごとの一時ID、待機15分）の上限 | `security.py`; `api_core/state.py`; `pipeline_api.py:PipelineService`; `pipeline_defaults.py` (`host_limits`, `envelope_limits`); `pipeline_images.py` | §12.6.6, §22 | 確認済み | 公開可 |
| PIPE-HOST | Server pipeline host | 信頼済みconfig・provider・保存effectを共有coreへ供給し、実行snapshotを直列化して保存する。画像の実行では受け取った画像をrunのメモリに置き、見比べの画を描く。意味分岐を持たない | `pipeline_runtime.py`; `pipeline_api.py:PipelineService`; `pipeline_candidate.py` (`PipelineBinding`, `CandidateExecution`); `pipeline_product.py:ProductPipelineEffects`; `pipeline_settings.py`; `pipeline_defaults.py`; `pipeline_compat.py`; `pipeline_images.py` | §12.6.6, §12.7.1 | 確認済み | 公開可 |
| PIPE-MACHINE | 共有authoring state machine | snapshot + input envelope → 次snapshot + event + 最大1 effect。retry、fallback、authority遷移、compile契機を決める。入力は記述・direct DDL・画像・保存作品からの法則の手の4つ | `core/crates/inku-pipeline/src/{machine,machine/image,protocol,authority,prompts,core_boundary,hole_completion,replay,byte_envelope}.rs`; `inku-pipeline-uniffi` (`step`) | §12.7.1, §12.8 | 確認済み | 公開可 |
| PIPE-LIMITS | 資源authority | hard policyとoperational budget（既存4上限 + 新6上限）を解決し、作品へ保存し、個体化前に需要を検査する | `pipeline_defaults.py` (`ADDITIONAL_RESOURCE_LIMITS`); `limits.py` (`Limits`, `DEFAULT_LIMITS`); `pipeline_settings.py`; `inku-score/src/score_resources.rs`; `api_core/rendering.py:_limits_for_render`（再演） | §12.16後段、Project Context「設計契約」 | 確認済み | 公開可 |
| PIPE-SKETCH | 写生 | 作者が選んだときだけStage 1前に場所と光を補う。失敗しても描画を止めない | `inku-pipeline/src/prompts.rs:build_sketch_prompt`; `machine.rs:finish_sketch`; `sketch.py`（保存済み状態の型だけ） | §12.6.1 | 確認済み | 公開可 |
| PIPE-CATALOG | 色カタログ自動選択 | `catalog_mode=auto`のときだけ記述からカタログを選び、失敗時は`default`へ落とす | `prompts.rs:build_catalog_selection_prompt`; `machine.rs:select_catalog`; `pipeline_product.py:prepare` | §12.7.1 | 確認済み | 公開可 |
| PIPE-S1 | Stage 1 下絵 | 記述から閉じた型の下絵JSONを受け、可視DDLへ決定的に印字する。compiler不受理時は有限予算内で再正規化し、尽きたら描画可能な残部だけを採用候補にする | `prompts.rs` (`build_stage1_prompt_with_sketch`, `parse_stage1_response`); `inku-ddl/src/work_plan.rs` (`normalize_work_plan`, `print_work_plan`); `machine.rs` (`correct_stage1`, `residual_execution_preflight`) | §12.6, §12.8 | 確認済み | 公開可 |
| PIPE-COMPOSITION | 構図の読み | Stage 1の下絵の後に、記述が置き場所を言わない層の置き場所を記述から読み（`read_composition`、prompt `inku.composition-reading-prompt.v4`）、紙が見せられる値だけを数の範囲で印字する。保存作品の別の構図は可視DDLだけから読み直す | `inku-pipeline/src/{composition_reading,composition,recompose}.rs`; `routers/render.py`（`/api/composition/ranges`） | §12.6.2, §12.6.3 | 確認済み | 公開可 |
| PIPE-LAWS | 法則の段 | 構図の後に、読み手が選んだ絵画・意匠・音楽の法則を当て、変えた層だけを数の形で印字し直してからcommitする（`choose_laws`、prompt `inku.laws-prompt.v1`）。保存作品からの法則の手（入力`SavedLaws`）と、作品に残す法則の記録（`laws_layers`・`laws_basis`）を持つ | `inku-pipeline/src/{laws,laws_entry,laws_record}.rs`; `inku-ddl/src/work_plan.rs`（数の印字） | §12.6.4 | 確認済み | 公開可 |
| PIPE-COLORS | 配色の段 | 法則の段の後に、色の法則から作品の配色を選び、描いた見え方（rendererの編集用SVGから層ごとに見積もる）で地から見えない色や法則の成り立たない色を選び直す（`choose_colors`、prompt `inku.colors-prompt.v1`）。Serverの記述起点の既定（2026-10-20） | `inku-pipeline/src/{colors,appearance}.rs` | §12.6.5 | 確認済み | 公開可 |
| PIPE-CANVAS | 画面比の宣言とはめ込み | 新しいDDLの1文目に組んだ比を宣言し（DDL 26）、Scoreの`canvas.declared_ratio`に入れる。宣言は命令・文番号・種の材料にならない。宣言と違う比の紙では、hostの`canvas_fit`で比を保って紙の中央にはめ込む（render engine 93）。保存作品のはめ込みは保存Scoreを版を変えずに描き直す | `inku-ddl/src/canvas_ratio.rs`; `inku-pipeline/src/{core_boundary,saved_variants}.rs`（`fit_render`）; `inku-render`（`CanvasSize.bleed`） | §19 | 確認済み | 公開可 |
| PIPE-TYPED-DDL | Typed DDL compiler | 可視DDLのsource span、typed semantic document、汎用Macroのlock/binding/有限展開、compiler lock（4状態）、曖昧さのfail-closed診断。形の無い文は、抱える穴が無ければ範囲つきの止める診断で名指して省く（DDL engine 71） | `inku-ddl/src/{document,parser,clause,numeric_range,semantic_association,semantic_instruction,semantic_document,macro_resolution,macro_parameter_binding,macro_expansion,compiler_lock}.rs` (`compile_typed_ddl`) | §4.4–4.6, §12.4, §12.7 | 確認済み | 公開可 |
| PIPE-HOLE | known-hole補完（Stage 2） | 保存済みDDLのknown holeと、作品の控え（A3）と比べて言葉だけを直した範囲を、範囲限定のpatch候補として要求し、作者承認後にCAS保存する。Scoreを出力しない | `machine.rs` (`complete_holes`, `hole_response`); `hole_completion.rs`; `completion_ranges.rs`; `inku-ddl/src/{visible_patch,completion_record}.rs`; `prompts.rs:build_hole_completion_prompt` | §12.7, §12.7.1 | 確認済み | 公開可 |
| PIPE-IMAGE | 画像から書く作品 | 記述の代わりに画像から始め（入力`Image`）、VisionのモデルがDDLを直接書く。compilerの所見で一度だけ聞き直し、hostが描いた画と元の画像を見比べて一度直す（`select_image_catalog`・`write_image_ddl`・`draw_image_review`・`review_image_ddl`）。画像はcoreに入らず、参照（形式・画素数・SHA-256・バイト数）だけを持つ | `inku-pipeline/src/{image_ddl,machine/image}.rs`; `provider_wire.rs`（画像の部品）; `pipeline_images.py`（Serverの受取と見比べの画） | §12.6.6 | 確認済み | 公開可 |
| PIPE-WIRE | providerへの要求本文と答えの読み | OpenAI Responses・OpenAI互換chat・Anthropic Messages・Geminiの要求本文、schema変換、画像の部品、答えの読み、ChatGPTプランの要求とSSEの読み・失敗の分類を共有coreが持つ（`inku.provider-wire.v1`）。hostは鍵・HTTP・流量・観測だけを持つ | `inku-pipeline/src/provider_wire.rs`; `provider_wire/chatgpt.rs`; `pipeline_provider.py`; Android `providerWire`（JNI）; macOS `ProviderTransport.swift` | §12.5 | 確認済み | 公開可 |
| PIPE-REFINE | 保存作品の推敲の規則 | てざわり・支持体・配色の候補と差し替え（`inku.saved-variants.v1`）、取り合わせ（`inku.juxtaposition.v1`）、AI自動推敲の手番・親子の見える差・辺の記録（`inku.autonomous-refine.v1`）を共有coreが持ち、Server・Android・macOSが同じ規則を呼ぶ。AI自動推敲のrunはServerが進める | `inku-pipeline/src/{saved_variants,retouch,juxtaposition,autonomous_refine}.rs`; `autonomous_refine.py`; `routers/autonomous.py` | §7.8; 自律推敲の方式 | 確認済み | 公開可 |
| PIPE-MACRO | MacroDefinition | 汎用Macro定義、同梱`Nature.leaves`、新作用catalogの解決。旧Markdown pluginは警告付きで省略し、本文を再解釈しない | `inku-ddl/src/macro_definition.rs`; `NATURE_LEAVES_V1_JSON`; `inku-pipeline-uniffi/src/macro_catalog.rs`; `macro_catalog.py`; `plugins/document_format.py`（有効化の取っ手） | §4.5–4.6 | 確認済み | 公開可 |
| PIPE-S15 | Typed Stage 1.5 | `CanonicalReady`のmeaningだけを受け、入力を検証してeffective meaningの同一性を固定する（焦点と明示変奏は外した） | `inku-ddl/src/stage15_transform.rs` (`transform_stage15`); `compiler_execution.rs:prepare_stage15_execution` | §12.11, §12.13 | 確認済み | 公開可 |
| PIPE-LOWER | Plan・資源選択・materialize | verified effective meaningを一度だけsymbolic Planへ下ろし、資源を選び、compact Score recipeへ写す。局所省略を診断に残す | `inku-ddl/src/{compiler_execution,composition_plan,plan_resources,score_materialization,score_lowering}.rs` (`compile_ddl_to_score_with_resources`) | §12.7, §12.16後段, §18 | 確認済み | 公開可 |
| PIPE-COMPAT | 旧Score互換 | 0.10未満の保存済み・外部Scoreだけに構造的な既定、fill表記の橋渡し、解決不能relationの除去、記録上限を当てる。DDLや記述を受けない | `saved_score_compat.py:coerce_saved_score`; `coerce/observability.py`; `inku-score/src/compatibility.rs` | §12.14, §18 | 確認済み | 公開可 |
| PIPE-RENDER | Render Engine | Score、seed、解決済みhost option、資源authorityからSVGと描画metadataを作る。compact Scoreはtyped performance、旧Scoreは従来のchecked performanceを通る | `inku-pipeline/src/core_boundary.rs` (`render_delivery`, `render_saved_score`); `inku-render/src/render.rs` (`render`, `render_with_resources`); `checked_performance.rs`; `typed_performance.rs`; `render_engines/default/adapter.py`（旧Score経路）; `inku-render-python`; `inku-render-android` | §12.14, §13.8 | 確認済み | 公開可 |
| PIPE-RASTER | SVG raster presentation | 保存済み／生成直後のcanonical SVGをresource非依存のpremultiplied RGBA8へ変換し、pixel format・寸法・strideを明示する。thumbnailとPNG書き出しはここを使う | `core/crates/inku-svg-raster`; `NativeRenderBridge`; `RustArtworkRasterizer` | §12.14; Android仕様 | 確認済み | 公開可 |
| PIPE-DISPLAY | 画面表示 | 保存済み／現行SVGを、WebのChromeと同じ見え方でSkiaに描く（照合表の外の作品はresvg）。AndroidとmacOSの通常表示が使い、macOSの拡大の窓はApple siliconで別processのSkia Graphiteが描く。保存SVGとcoreの演奏は変えない | `core/crates/inku-display`; `core/crates/inku-display-gpu`; `inku-pipeline-uniffi`・`inku-render-android`の`display` feature; Android `AndroidDisplayRenderer`; macOS `DisplayComposite.swift` | Android仕様; Swift仕様 | 確認済み | 公開可 |
| PIPE-3D | 実験的な3D表示の入力 | 保存作品から実験的な3D表示へ渡す入力（`inku.ddl3d.v1`）を共有coreが組む | `inku-pipeline/src/ddl3d.rs`; `web/src/lib/features/experimental-3d/` | Android仕様; Swift仕様 | 確認済み | 公開可 |
| PIPE-HISTORY | 履歴保存 | 共有pipelineの演奏をhistory rowへ保存し、authority revisionとfork用sidecarをlinkする | `pipeline_product.py:save_result`; `db.py:add_item` façade; `persistence/history.py`; `VariationAuthorityStore.link_history` | §12.7.1, §21 | 確認済み | 公開可 |
| DATA-AUTHORITY | Variation authority | origin・authority・revisionのCAS、action ACKの冪等性、実行snapshot、history link sidecar | `inku-pipeline/src/authority.rs`; `persistence/variation_authority.py` (`VariationAuthorityStore`); `persistence/schema.py`（`variation_authority`, `variation_authority_actions`, `pipeline_candidate_executions`, `pipeline_history_links`） | §12.7.1 | 確認済み | 公開可 |
| DATA-DH1 | `dh1` | 正規化した記述の同一性 | `identity.py:description_hash` | Project Context「設計契約」 | 確認済み | 公開可 |
| DATA-RH3 | `rh3` | Score、render seed、wild、engine、色カタログによるedition同一性 | `db.py:render_hash_for_item`; `test_render_hash.py` | Project Context「設計契約」 | 確認済み | 公開可 |
| DATA-RH2 | legacy `rh2` | 旧edition hashの互換保持 | `db.py:_legacy_render_hash_for_item`; `test_render_hash.py` | Project Context「設計契約」 | 確認済み | 公開可 |
| DATA-LINEAGE | 系譜node/edge | 明示された親とderivation kindだけをedge化。AI自動推敲の子は辺に手の記録（`ai_move`）を持つ | `LineageNodeRow`, `LineageEdgeRow`, `db.py:add_item`; `autonomous_refine.py`; `test_lineage_acceptance.py` | §21、Project Context「設計契約」 | 確認済み | 公開可 |
| DATA-SAIJIKI | 歳時記 | 語彙の正本は共有coreのasset。Stage 1 projection、Serverの表示表、Web／Android歳時記、referenceがそこから導出する | `core/crates/inku-ddl/assets/saijiki-v2.json`; `inku-ddl/src/saijiki.rs`; `saijiki.py`; `test_saijiki_api.py`; `test_saijiki_kt_is_current.py` | Project Context「語彙」 | 確認済み | 公開可 |
| DATA-FALLBACK | 層ごとの結果の記録 | 新作は写生を`sketch_state`、provider失敗を実行context、compiler結果と4診断をhistory link sidecar v2へ残す。sidecarは補完の控え（`completion_ranges`）と法則の記録（`laws_layers`・`laws_basis`）も持つ。旧列`interpret_fallback` / `compose_fallback`は旧作品の表示のためだけに残る | `pipeline_product.py` (`provider_for`, `save_result`); `variation_authority.py:history_pipeline_diagnostics`; `db.py:HistoryRow`; `web/src/lib/composeFallback.ts` | §12.7.1, §12.8 | 確認済み | 公開可 |
| DATA-IMAGE | 画像入力の記録 | 画像から書いた作品は、来歴（`image_provenance`）とcoreの記録（`image_ddl`。画像のbytesは持たない）をhistory rowに保存し、`input`・`source_text`は空にする。画像そのものはrunのメモリにだけ置く | `persistence/schema.py`（`HistoryRow.image_provenance`・`image_ddl`）; `persistence/migrations.py`（v5）; `pipeline_images.py` | §12.6.6, §22 | 確認済み | 公開可 |
| WEB-FEATURES | Web feature modules | route shellから分離したSession・Work（画像タブを含む）・Batch・Demo・Refinement・Settings・history/lineage・viewport・pipeline owner、AI自動推敲・取り合わせ・実験的3D、stateless operation、focused Canvas/Settings view | `web/src/routes/+page.svelte`; `web/src/lib/features/{session,work,batch,demo,run,history,canvas,settings,pipeline,autonomous,juxtaposition,experimental-3d}/`; `web/src/lib/components/{CanvasPanel,SettingsModal,DdlEditorDialog,PipelineStatus,InputPanel}.svelte`; ownership tests | §7.8、Project Context「web」 | 確認済み | 公開可 |
| WEB-REGISTRY | 3設定登録簿 | localStorage、user settings、render payloadを集約 | `persisted-settings.ts`; `user-settings.ts`; `render-payload.ts` | Project Context「web」 | 確認済み | 公開可 |
| WEB-I18N | UI語彙・token | 日英UI、英語用語集、CSS token | `web/src/lib/i18n/*`; `GLOSSARY.md`; `+page.svelte` `:root` | §6–7 | 確認済み | 公開可 |
| OPS-COMPOSE | Compose配布 | API/Webの2 serviceと永続volume | `compose.yaml`; `deploy/compose.yaml`; `server/Dockerfile`; `web/Dockerfile` | §22 | 確認済み | 抽象化すれば可 |
| TEST-SERVER | Server検査 | pytest、API surface、認可、route所在、共有pipeline hostとauthority store | `server/tests`; `test_api_surface.py`; `test_route_authorization.py`; `test_pipeline_{api,candidate,compat,product,provider}.py`; `test_persistence_variation_authority.py` | §11; Project Context「検査面」 | 確認済み | 公開可 |
| TEST-CORE | 共有Rust検査 | crateごとのunit/integration test。authoring flowはnative rendererを呼ばない代表flowで検査する | `core/crates/inku-ddl/tests/`; `core/crates/inku-render/tests/`; `core/crates/inku-score/tests/`; `inku-pipeline/src/focused_flow.rs` | §11 | 確認済み | 公開可 |
| TEST-CORPUS | 凍結コーパス | 明示的な全更新checkpointだけで新しい版のdirectoryを作る。最新の凍結はRender Engine 66の620件とDDL engine 45の3件（共有Rust pipeline）。DDL engine 1–26は退役した展開・coerce・plugin層の履歴記録 | `server/reference/render-engine-66/manifest.json`; `ddl-engine-45/manifest.json`; `server/reference/README.md`; `reference-corpus.yml` | §11, §22 | 確認済み | 公開可 |
| TEST-ANDROID | Android受入 | 共有pipelineのhost JVM testと端末受入。同梱libraryのSVG・engine identity・renderer referenceを、build時に同じcommitのhost coreが作る期待値と照合し、raw pixelも照合する（凍結corpusはScore入力とraster入力だけに使う） | `SharedPipelineHostTest`; `AndroidSharedPipelineTest`; `SharedPipelineDeviceAcceptanceTest`; `NativeRenderDeviceTest`; `generateRustParityExpected`; `prepareRustParityAssets`; `inku-render-android/examples/render-parity-expected.rs` | Android仕様 | 確認済み | 公開可 |
| TEST-WEBCLI | Web/CLI検査 | Svelte check/unit/lint、CLI pytest | `web/package.json`; `web/src/**/*.test.ts`; `cli/tests/test_cli.py` | Project Context「検査面」 | 確認済み | 公開可 |
| CI-GATES | 現在のCI | server/cli lint+pytest（Rust toolchain guardを含む）、web check+unit+lint:i18n、bilingual docsとportable persistence verifier、共有Rust / raster / JNI / Android hostのpath-scoped native gate、手動dispatchだけのcorpus比較とimage build確認 | `.github/workflows/checks.yml`; `android-native.yml`; `reference-corpus.yml`; `release.yml` | §11, §22; Android仕様 | 確認済み | 公開可 |

## 退役したID

2026-09-14のcutoverで、次のIDが指していたPython層は新作経路から外れた。過去の文書やCHANGELOGから辿れるよう、IDと後継を残す。

| 旧ID | 旧実装 | 後継 |
|---|---|---|
| PIPE-PLUGIN | `plugins/document_format.py:expand_plugin_ddl`による散文起点の決定的展開 | PIPE-MACRO |
| PIPE-S2 | `composer.py:compose`によるLLMのScore化 | PIPE-HOLE（known holeだけのpatch候補）とPIPE-LOWER |
| PIPE-COERCE | `coerce/`の配達・統治・天井 | PIPE-LOWER（新作）とPIPE-COMPAT（旧Score） |

## 信頼度の読み方

- **確認済み**: entry point、呼び出し、schema、testのいずれかで直接確認した。
- **仕様のみ**: 仕様にあるが、現行実装で対応を確認できない。
- **実装から推定**: 複数の静的根拠から推定した。推定理由を本文に添える。
- **未確認**: 実測または秘密情報が必要で、今回の境界では確認していない。
