# inku Android 実装メモ

このディレクトリは、ネイティブ単体 Android アプリのワークスペースであり、Git 管理対象とする。
ローカル専用成果物、端末ID、ダウンロード済みモデル、ログ、秘密情報は追跡対象に含めない。

最終更新: 2026-07-24。

**追随状況**: Android は `2.0.0-android.1` / **render engine version `11`** の世代にある。
master の web/server は v2.4.8 / engine 11 で、**描画層は追いついている**。
Stage 1.5 展開層は Phase 3b まで移植済みで、3c〜3d が残っている。
差分の追随は段階的に行う（末尾の各 Phase 節を参照）。

## 更新ルール

- `ANDROID_SPEC.ja.md` を Android 仕様メモの正本とする。
- `ANDROID_SPEC.md` は英語版として、`ANDROID_SPEC.ja.md` の意図を保った翻訳・要約として更新する。
- Android 仕様を更新するときは、先に `ANDROID_SPEC.ja.md` を更新し、その後で `ANDROID_SPEC.md` を同期する。
- 英語版だけに存在する仕様・要件を追加してはならない。

## 確定事項

- Kotlin + Jetpack Compose によるネイティブ Android 実装。
- Room を正式な DB レイヤーとする。
- SQLite ファイルはアプリサンドボックス内に保持する。
- シングルユーザーの独立アプリケーションパッケージとする。
- デフォルト provider はローカルモデル provider とする。
- Web 参照実装との互換性のため、外部 provider も維持する:
  OpenAI、Claude、Gemini、NVIDIA NIM、Ollama、Intel OVMS。
- Android パイプラインは参照フローを維持する:
  description -> Stage 1 -> Stage 1.5 -> Stage 2 -> JSON Score -> SVG。
- JSON Score、render metadata、履歴 import/export、色カタログ、canvas aspect、SVG profile、
  render hash は Web 実装と互換にする。
- SVG 生成は Kotlin に移植する。端末上のサムネイルとメイン preview を安定させるため、
  保存済み JSON Score を直接描画する Compose Canvas preview 経路も持つ。
- Gemma 4 E2B を標準ローカルモデル、Gemma 4 E4B を高品質オプションとする。
- 初回起動時は、ライセンス同意後に選択されたローカルモデルをダウンロードする。
- 対象端末クラスは Pixel 9 以降とする。

## 現在の実装状態

Android ワークスペースには、namespace `app.inku.mobile` の build 可能な単体アプリがある。

実装済み:

- Kotlin、Jetpack Compose、Room、KSP を使う Gradle Android project。
- `MainActivity` と `InkuApplication`。
- アプリサンドボックス内の Room DB `inku.sqlite`。
- Room entity / DAO:
  - history items
  - app settings
  - model assets
  - provider settings
  - color catalogs
  - plugin settings
  - export templates
- 描画、バッチ実行、デモ実行、履歴選択、ローカル設定、モデル取得状態を扱う Repository / ViewModel 層。
- Gemma 4 E2B/E4B のローカルモデルカタログと取得状態管理:
  - 公式 LiteRT-LM Hugging Face `.litertlm` URL
  - SHA256 metadata
  - Room に保存するライセンス同意状態
  - アプリサンドボックス内への再開可能な `.part` download
  - progress bytes、total bytes、ready、failed、cancelled、interrupted、verifying states
  - 最終モデルファイル化前の SHA256 検証
  - 検証済みの完全な `.part` file からの復旧
  - 中断された in-progress download の `.part` file からの再開
  - app sandbox final storage under `files/models/`
- 決定的ローカル fallback pipeline:
  - natural language description -> normalized DDL
  - DDL -> JSON Score
  - JSON Score -> SVG
  - render hash / render metadata generation
- Android rendering は Web `/api/paint` と同じ論理 stage を辿る:
  Stage 1 interpretation、intermediate DDL expansion、Stage 2 Score composition、
  Score repair/coercion、SVG rendering、render hash generation、Room history persistence。
- Web/server 比較用 headless render execution:
  - exported `HeadlessRenderActivity`
  - adb から起動可能な run ID と prompt/model/catalog/canvas extras
  - app sandbox artifacts under `files/headless/<run_id>/`
  - `result.json`、`normalized.ddl`、`score.json`、`output.svg` の抽出
  - `INPUT_MODE=ddl` で Stage 1 を通さず、入力済み正規化DDLを Stage 2 以降へ直接流せる。
    LLM 出力の揺れを切り離し、DDL -> Score -> SVG の server 差分確認に使う。
  - server CLI も `inku-cli paint --input-mode ddl` を持ち、`/api/compose` 経由で
    DDL -> Score -> SVG を実行する。`--save-history` 指定時は `/api/history` へ保存する。
  - `inku-cli` 相当の local comparison runner として `android/scripts/headless_render_compare.sh`
  - 複数 prompt を連続比較し、retry と aggregate summary を作る
    `android/scripts/headless_batch_compare.sh`
  - `COMPARE_WEB=1` のとき、server-side generation は `inku-cli paint` で実行する。
    比較経路で `/api/paint` を直接叩いてはならない。
  - `android/scripts/headless_render_compare.sh` は server-side CLI 描画結果を後から通常履歴で参照できるよう、
    `CLI_SAVE_HISTORY=true` をデフォルトとし、`inku-cli paint --save-history` を付与する。
    `summary.json` と batch aggregate summary には server-side `history_id` を含める。
- LiteRT-LM は Stage 1 / Stage 2 のデフォルト local model provider として接続済み。
  provider は Room から選択済み Gemma 4 E2B/E4B `.litertlm` path を読み、
  model state が `ready` であることを確認し、cached LiteRT-LM `Engine` を初期化し、
  各 stage prompt を `Conversation` に送って返却 `Message` を text 化する。
  UI が device-side inference failure や timeout から復帰できるよう、request は bounded async flow と cancellation を使う。
- Stage 1 は、以前の Android summary prompt ではなく、Web 参照実装の
  `SYSTEM_PROMPT_PREFIX` と dynamic `EXAMPLE_POOL` selection algorithm を使う。
  Android 実装は `server/src/inku_server/interpreter.py` と同じ keyword-count rule で top 5 examples を選ぶ。
- Stage 1.5 は、日本語 DDL の Web `expand_intermediate_ddl` 経路を移植済み:
  placement-word sanitization、gray-background avoidance、static-center reframing、
  profile/tag selection、deterministic SHA-256 salted picks、
  structural/music/painting candidate selection、centered-layer limiting。
- Stage 2 は、Web 参照 `composer.py` の日本語 system prompt を、full conversion rules と key examples を含めて使う。
- LiteRT-LM provider が stage 実行できない場合、local path は Web fallback/coerce rules の Kotlin port に fallback する。
  Natural-language input は明示的な placement augmentation を含む normalized DDL へ保存されるため、
  Compose の `指示` field、`解釈（正規化DDL）` field、rendered Score、saved history が同じ user-visible flow で整合する。
- LiteRT-LM text response は DDL path に入る前に sanitize する。
  Gemma chat control token や、SQL-like text など明らかな non-DDL output は reject し、deterministic fallback に回す。
- Kotlin SVG renderer は current primitive subset を移植済み。
- Renderer は fallback path に必要な Web Score fields を扱う:
  `arrangement.color_cycle`、`arrangement.path`、clustered high-count groups、primitive `rotation`。
- 保存済み JSON Score 用 Native Compose preview renderer。
- Dark Compose UI は、Web-style workbench から Claude Design prototype ベースの Pixel 9 mobile-first layout へ移行中:
  - top application header
  - bottom navigation: Compose, History, Demo, Settings
  - Compose segmented mode: Write, Batch
  - selected canvas aspect を尊重しつつ、Pixel 9 で prompt と DDL path が届く bounded first-screen canvas card
  - canvas 下の prompt と DDL interpretation
  - local LLM work 中の layout jump を避ける fixed-height drawing CTA と in-place generating state / progress indicator
  - render sub-tabs: Artwork, Prompt, JSON
  - model、color catalog、canvas selection の explicit button rows
  - search/filter placeholders と two-column thumbnail cards を持つ dedicated History screen
  - overlay text badge ではなく accent border と corner marker による History selected-card affordance
- 選択中履歴 item の操作:
  - star / unstar
  - soft trash
  - Android `FileProvider` 経由の JSON share export
- 起動時、最新選択履歴 item を prompt、DDL、catalog、canvas settings へ復元する。
- Pixel 9 status bar / navigation bar safe-area handling。

未実装:

- background continuation、notification progress、metered-network policy、low-storage recovery を含む production-polished model download UX。
- 外部 provider execution。provider record は現時点では compatibility data structures として存在する。
- import/export、plugin management、advanced settings、user-management equivalents、admin/server-only web features の full web feature parity。
- Web-compatible JSON export からの import。
- SVG / render metadata レベルの reference compatibility tests。
  **Score レベルは 2026-07-23 に着手済み**（`ServerScoreParityTest.kt` が
  `server/tests/fixtures/stage2/` の 15 ケースと `dh1` / `rh2` の値一致を検証する。末尾の節を参照）。
- web/server v2 世代への追随（Renderer engine 2 → 10、変奏、プラグイン、系譜、添景）。
  Phase 1（Score schema / coerce / hash）のみ完了。

## 実機検証状態

最新の検証済み device class:

- Device: Pixel 9 connected by USB。
- APK: debug build from `android/app/build/outputs/apk/debug/app-debug.apk`。

実機確認済み:

- App installs and launches。
- launch 後 process は running のまま維持される。
- Draw action が新しい Room history item を作る。
- Batch-generated / single-draw history entries が `inku.sqlite` に永続化される。
- Latest checked history count: `4`。
- Latest checked render hash short: `6D8E`。
- Stored JSON Score と render metadata は JSON render tab から確認できる。
- Main preview と history thumbnails は device 上で JSON Score から render される。
- Star state update は Room に永続化され、選択中 history UI に反映される。
- JSON share export は app cache に `inku-<render_hash_short>.json` を書き、
  `FileProvider` 経由で Android share sheet を開く。
- Gemma 4 E2B/E4B model records は launch 時に Room へ seed される。
- Gemma 4 E2B license acceptance は `ready_to_download` として永続化される。
- 確認した logcat window では fatal Android runtime crash は観測されなかった。
- Headless Android render は Compose UI を開かずに完了した。
  確認 run は Stage 1 / Stage 2 に NVIDIA Gemma 4 31B を使い、
  artifacts を `/tmp/inku-headless/codex-headless-test3/` に出力し、
  render hash short `8097` を報告した。
- VPN 経由で local reference server の frontend port への web access を確認した。
  backend API port への direct CLI access はこの検証では応答待ちになったため、
  比較には frontend base URL 経由の `inku-cli` を使った。
- 最新の Android-vs-server comparison:
  - input: `青い背景に白い横線を三本引く`
  - Android device: Pixel 9 over USB
  - Stage 1: `nvidia:google/gemma-4-31b-it`
  - Stage 2: `nvidia:google/gemma-4-31b-it`
  - color catalog: `ink_porcelain`
  - canvas aspect: `square`
  - comparison runner: `android/scripts/headless_render_compare.sh`
  - server generation: VPN-reachable frontend URL に対する `inku-cli paint`
  - artifacts: `/tmp/inku-headless/codex-cli-compare-vpn2/`
- 比較は完了したが parity は未達:
  - Android render hash short: `8097`
  - server/inku-cli render hash short: `77FE`
  - `same_render_hash`: `false`
  - `same_ddl`: `false`
- その run で観測した parity gap:
  - Android normalized DDL は末尾 clause を重複した:
    `黒い細い斜め線を右上がりに三本並べる。細かく震える。`
  - server/inku-cli normalized DDL にはその duplicate clause がない。
  - Android Score は 3 instructions。
  - server/inku-cli Score は 4 instructions。`color_cycle` repair と white ellipse composition anchor を含む。
  - Android render metadata は `render_engine_version: 1`、server は `render_engine_version: 2`。
- 32文字の日本の四季テーマ指示を5件生成し、Android headless CLI 相当経路と
  server `inku-cli paint` の描画結果を比較した。
  - batch id: `season32-compare-003`
  - artifacts: `/tmp/inku-headless/season32-compare-003/`
  - prompt count: `5`
  - success count: `5`
  - error count: `0`
  - same render hash count: `0`
  - same DDL count: `1`
  - 入力は全て32文字で確認済み:
    - `春の雨に濡れた桜の影を白い余白へ淡く静かに散らす細い銀の線たちよ`
    - `夏の夜に光る海風を青い円と赤い点で遠く揺らす透明な波音として置く`
    - `秋の夕暮れに舞う落葉を金の線と黒い余白で斜めに重ねる細い影二本を`
    - `冬の朝に凍る池の息を白い弧と灰の点で静かに結ぶ細い影青く遠く残す`
    - `梅雨明けの雲間に虹の欠片を緑の弧と青い粒で軽く浮かべるそっと置く`
  - hash short comparison:
    - `season32-001`: Android `18E1`, server `FDCE`, DDL mismatch
    - `season32-002`: Android `5BF6`, server `CAA0`, DDL mismatch
    - `season32-003`: Android `588C`, server `E2BC`, DDL mismatch
    - `season32-004`: Android `2033`, server `2357`, DDL mismatch
    - `season32-005`: Android `E590`, server `5D2D`, DDL match
  - `season32-001` は自然言語からの数値抽出が Android と server で大きく異なった。
  - `season32-002` は DDL の意味は近いが、Android 側に `細筆` / `鉛筆` の material detail が追加された。
  - `season32-003` は Android 側で `二本数を二本並べる` という不自然な重複表現が出た。
  - `season32-004` は背景色、配置、個数、追加線の有無まで異なり、Stage 1/1.5 parity gap が大きい。
  - `season32-005` は DDL が一致したが render hash は不一致であり、renderer / metadata / SVG generation parity が未達である。

最新の local verification screenshot:

```text
/tmp/inku-android-workbench.png
```

## Data Source of Truth

Room database を local history / settings の source of truth とする。
Generated SVG、JSON export files、PNG files は derived artifacts とする。

重い user-visible export は Android Storage Access Framework を使う。
Internal model files と app-owned artifacts は app sandbox に置く。

## Compatibility Boundary

Android app は multi-user authentication を持たない。
Web user-scoped records は、1つの implicit local user に対応する。
User-management / admin-only features は、Android single-user equivalent として意味がある場合のみ local settings として表現する。
login や role handling は追加しない。

Server-only web features は、clear local single-user equivalent がない限り Android runtime から外す。

## Web/Server Master Policy

Android 版の開発 master は常に `web/` と `server/` の実装である。
Android 側は独立した native application package として実装するが、DDL interpretation、
Stage 1.5 expansion、Score coercion / repair、SVG rendering、history/render metadata の
behavioral source of truth は web/server 側とする。

今後 web/server 側を更新するときは、Android 側の追従可否を同じ変更単位で確認する。
Android 側の互換コードは server source の責務境界に対応するファイルへ分割し、
差分確認と移植漏れ検出を容易にする。

現在の renderer compatibility layout:

| server source | Android compatibility file | Responsibility |
| --- | --- | --- |
| `server/src/inku_server/renderer.py` / `_stroke_attrs`、dash、texture、blur | `android/app/src/main/java/app/inku/mobile/render/ServerRendererStyle.kt` | stroke/fill attributes、material weight style、texture filters、blur filters、hint opacity |
| `server/src/inku_server/renderer.py` / `_arc_path_d`、point generation、variation | `android/app/src/main/java/app/inku/mobile/render/ServerRendererGeometry.kt` | SVG geometry、arc sweep/large-arc rules、regular polygon points、triangle bbox points、variation path |
| `server/src/inku_server/renderer.py` / material outline helpers | `android/app/src/main/java/app/inku/mobile/render/ServerRendererMaterial.kt` | pencil/crayon/chalk/brush/rope outlines、specks、rope twists |
| `server/src/inku_server/renderer.py` / `render` and `_render_instruction` flow | `android/app/src/main/java/app/inku/mobile/render/DefaultSvgRenderer.kt` | Android SVG renderer orchestration、arrangement expansion、presence layer、metadata emission |

`DefaultSvgRenderer.kt` には orchestration を残し、server-derived details は
`ServerRendererStyle.kt` / `ServerRendererGeometry.kt` / `ServerRendererMaterial.kt` に置く。
server `renderer.py` に変更が入った場合は、まず上表の該当ファイルを更新対象として確認する。

同じ方針を pipeline でも維持する。`server/src/inku_server/interpreter.py`、
`ddl_expander.py`、`coerce.py`、`schema.py` の変更は、Android の
`pipeline/` package と compatibility data model へ対応づけて確認する。
Android 固有の UI / Room / LiteRT-LM / provider routing は native implementation としてよいが、
生成される DDL、Score、SVG、render metadata、history persistence の user-visible behavior は
web/server との parity を優先する。

現在の pipeline compatibility layout:

| server source | Android compatibility file | Responsibility |
| --- | --- | --- |
| `server/src/inku_server/interpreter.py` / Stage 1 model text cleanup and usable DDL guard | `android/app/src/main/java/app/inku/mobile/pipeline/ServerDdlText.kt` | model output cleanup、Stage 1 DDL normalization、number-noise repair、clause dedupe、drawable vocabulary guard |
| `server/src/inku_server/ddl_expander.py` | `android/app/src/main/java/app/inku/mobile/pipeline/WebDdlExpander.kt` | Stage 1.5 DDL expansion and sensory / structural marker insertion |
| `server/src/inku_server/coerce.py` / `PRIMITIVE_SPECS`、field coercion、post-coerce | `android/app/src/main/java/app/inku/mobile/pipeline/ServerScoreCoercer.kt` | Stage 2 instruction の primitive field repair、fallback field selection、arc angle repair |
| `server/src/inku_server/coerce.py` / semantic marker helpers、presence inference、color/layout/material/radius detection | `android/app/src/main/java/app/inku/mobile/pipeline/ServerScoreSemantics.kt` | context marker detection、quiet-density / motion / colorful context 判定、presence inference、visible color/background、DDL hint helpers |
| `server/src/inku_server/composer.py` and `coerce.py` / fallback score synthesis | `android/app/src/main/java/app/inku/mobile/pipeline/ServerFallbackComposer.kt` | provider failure / unusable Stage 2 output 時の fallback DDL、fallback instruction、arrangement synthesis |
| `server/src/inku_server/coerce.py` / DDL coverage、shape/color/motif/composition repair factories | `android/app/src/main/java/app/inku/mobile/pipeline/ServerScoreRepairFactory.kt` | drawable clause extraction、clause primitive/color mapping、coverage instruction、shape/motif repair instruction factories |
| `server/src/inku_server/coerce.py` / semantic repair order and Android-local orchestration | `android/app/src/main/java/app/inku/mobile/pipeline/LocalFallbackPipeline.kt` | Score coercion orchestration、dedupe、DDL coverage、color/shape/motif/composition/context/motion/presence/density repair order、fallback Score construction、Stage 1/2 provider fallback control |
| `server/src/inku_server/schema.py` / Stage 2 tool contract and provider tool-call responses | `android/app/src/main/java/app/inku/mobile/pipeline/WebScoreTool.kt` | Stage 2 submit_score schema、Stage 2 JSON extraction、tool_calls / arguments unwrap、renderable instructions guard |
| `server/src/inku_server/composer.py::_score_tool_schema()` の生成結果 | `android/app/src/main/java/app/inku/mobile/pipeline/ServerScoreSchemaJson.kt` | Stage 2 tool schema の JSON 本体。primitive / weight / style の列挙、`additionalProperties: false`、arrangement・`at`・`relation`・`surface` の定義。**server schema の変更はまずここへ反映する** |
| `server/src/inku_server/db.py::render_hash_for_item` / `identity.py::description_hash` | `android/app/src/main/java/app/inku/mobile/pipeline/LocalFallbackPipeline.kt` の `renderHash` / `descriptionHash` / `canonicalSeed` | `rh2` payload の 8 項目と canonical JSON 規則、`dh1` の正規化規則、seed の整数化 |

指示から描画までの function-level parity table:

| Flow step | server master | Android port | Parity rule / current work item |
| --- | --- | --- | --- |
| UI prompt input | `web/src/lib/components/InputPanel.svelte` / `DdlEditor.svelte` | `ui/InkuApp.kt` / `ui/InkuViewModel.kt` | mobile-native UI でよいが、prompt、DDL、auto-repair、model/catalog/canvas state は同一 flow に保存する。 |
| Paint API orchestration | `api.py::api_paint` | `data/InkuRepository.kt::paint` / `pipeline/LocalFallbackPipeline.kt::paint` | Stage 1、Stage 1.5、Stage 2、coerce、render、hash、history save の順序を一致させる。 |
| Stage 1 model call | `interpreter.py::interpret_detail` / `_build_system_prompt` | `LocalFallbackPipeline.kt` + `WebDdlSpec.kt` | system prompt、example selection、model output cleanup、fallback control を server に合わせる。 |
| Stage 1 text cleanup | `interpreter.py` cleanup / usable DDL checks | `ServerDdlText.kt` | DDL guard、number-noise repair、clause dedupe、drawable vocabulary guard を関数単位で比較する。 |
| Stage 1.5 expansion | `ddl_expander.py::expand_intermediate_ddl` | `WebDdlExpander.kt` | sensory / structural markers、filter candidates、density and placement insertion を server 更新単位で追従する。 |
| Stage 2 model call | `composer.py::compose` / `_compose_*` | `LocalFallbackPipeline.kt` / provider clients | prompt、tool schema、retry / fallback criteria、timeout policy を server と比較する。 |
| Stage 2 tool schema | `schema.py::Score` / `Instruction` / `composer.py` tool schema | `WebScoreTool.kt` | JSON schema、tool_calls unwrap、arguments unwrap、renderable instruction guard を一致させる。 |
| Score primitive field coerce | `coerce.py::PRIMITIVE_SPECS` / `POST_COERCE` | `ServerScoreCoercer.kt` | primitive required fields、fallback fields、default values、arc angle repair を一致させる。 |
| Score semantic coerce | `coerce.py` marker helpers | `ServerScoreSemantics.kt` | material、color、variation、presence、density、motion marker を server の marker set と戻り値へ合わせる。 |
| DDL coverage repair | `coerce.py::_ddl_clauses` / `_primitive_from_clause` / `_fallback_instruction_from_clause` | `ServerScoreRepairFactory.kt` | clause extraction、primitive selection、coverage instruction defaults を一致させる。`円` / `circle` は server と同じく coverage repair では `ellipse` へ寄せる。 |
| Fallback Score synthesis | `api.py` fallback helpers / `coerce.py::_fallback_instruction_from_clause` | `ServerFallbackComposer.kt` | provider failure / unusable Stage 2 output 時の primitive、geometry、arrangement defaults を server に合わせる。 |
| Repair order | `coerce.py::coerce_score` | `LocalFallbackPipeline.kt` | visible color、dedupe、coverage、shape/color/motif/composition/context/motion/presence/density の順序を比較し、Android 固有順序を残さない。 |
| SVG render engine | `render_engines/default.py` / `renderer.py::render` / `_render_instruction` | `DefaultSvgRenderer.kt` / `ServerRenderer*.kt` | instruction expansion、arrangement placement、material outline、filters、metadata を renderer table と合わせる。 |
| Render hash / metadata | `api.py::_render_hash` / render metadata assembly | `LocalFallbackPipeline.kt::renderHash` / renderer metadata | hash input fields、build number handling、engine id/version、catalog/canvas metadata を一致させる。 |
| History persistence | `api.py::_add_history_item` / `db.py::add_history_item` | `InkuRepository.kt::saveResult` / Room entities | saved input、DDL、Score、SVG、metadata、model IDs、catalog/canvas、hash、timestamps を同じ user-visible data として保持する。 |
| Headless / CLI benchmark | `inku-cli paint --save-history` | `HeadlessRenderActivity.kt` / `android/scripts/headless_*` | server/android とも履歴保存可能にし、summary に history_id、DDL、hash、catalog を残す。 |

Saijiki parity は category-by-category で確認する。Android UI の word groups は
`web/src/lib/saijiki.ts` / `web/src/lib/i18n/ja.ts` と一致させる。server Stage 1 は
`interpreter.py` の saijiki list と allowed action verbs を参照する。Web UI が exposed していない
`描く` は Android UI でも独立 word としては出さず、DDL / model output に現れた場合のみ pipeline で扱う。
Score coercion / fallback / repair では、`katachi` を primitive、`tezawari` を weight、
`tsuranari` を style、`iro` を visible color、`yuragi` を variation、`basho` を center / position、
`ugoki` を arrangement、`katamuki` を rotation / line endpoints、`wariai` を size / arc angle /
line span へ反映する。LLM output が欠落または揺れた場合も、Stage 1.5 後の DDL に含まれる
Saijiki words を `ServerScoreCoercer.kt`、`ServerScoreSemantics.kt`、
`ServerFallbackComposer.kt`、`ServerScoreRepairFactory.kt` で補完し、server `composer.py` /
`coerce.py` の visible behavior へ寄せる。

## Web Component Porting Matrix

`web/src/lib/components/` 配下の全 Web component を Android port の検討対象とする。
Android 実装は mobile-native layout を使ってよいが、button action、state transition、persistence target は、
local single-user equivalent と明記されたものを除き、Web component と一致させる。

| Web component | Android status |
| --- | --- |
| `AppRail.svelte` | top header と bottom navigation に対応。Settings と app state entry point は可視のまま維持する。 |
| `AuthPanel.svelte` | local single-user equivalent。Login UI は出さず、local user は admin-equivalent settings access を持つ。 |
| `ProfileModal.svelte` | local single-user equivalent。Account/password editing は意図的に表示しない。 |
| `InputPanel.svelte` | Compose mode tabs、prompt input、canvas/catalog/model buttons、clear/draw action、batch/demo panels に移植。 |
| `PaintButton.svelte` | primary draw buttons に移植。 |
| `StopButton.svelte` | cancellable jobs backed active draw/batch/demo stop action に移植。 |
| `BatchPanel.svelte` | local batch text execution、progress message、selected latest result、Room history save として移植。 |
| `DemoPanel.svelte` | one-shot local demo generation として移植。Interval loop parity 用 persisted local settings は予定。 |
| `CanvasAspectPlugin.svelte` | Canvas settings panel と plugin enable flag の Room settings 永続化として移植。 |
| `ColorCatalogModal.svelte` | cancel/confirm semantics を持つ color catalog selection panel として移植。 |
| `DdlEditor.svelte` / `DdlEditPanel.svelte` | inline DDL editor、editor dialog、auto-repair toggle、Stage 2 replay、stop action として移植。 |
| `SaijikiInline.svelte` | 同じ word groups を使う inline Saijiki panel として移植。 |
| `SaijikiDrawer.svelte` | Android では inline Saijiki panel が mobile equivalent。drawer layout は使わない。 |
| `CanvasPanel.svelte` | artwork/prompt/score tabs、star、hash copy、render metadata、zoom/pan controls、SVG share、PNG share として移植。 |
| `OutputTabsContent.svelte` | saved Room history item からの prompt / JSON views として移植。 |
| `HistoryStrip.svelte` | Android 版では未使用の下部履歴ストリップを廃止し、履歴タブのグリッド表示と描画パネルの選択中結果操作に集約。 |
| `HistoryManager.svelte` | thumbnails/list modes、search、starred filter、selection、trash、restore、permanent delete として移植。 |
| `HistoryThumbnail.svelte` | history tiles / list rows の `ArtworkPreview` 経由で移植。 |
| `ConfirmDialog.svelte` | DDL overwrite と destructive history operations に移植。Non-history destructive settings confirmations は parity test backlog。 |
| `SettingsModal.svelte` | model selection、model connection settings、plugin setting、DB status、export templates、misc settings に移植。Server-only logs/output-save は local-only equivalents として表現。 |
| `KiwiMascot.svelte` | visibility setting として表現。Android progress indicator は native Material progress を使う。 |

## 実装順序

完了または概ね実装済み:

1. Project skeleton、Room schema、compatibility data models。
2. Local settings、model download state placeholders、provider abstraction。
3. current SVG primitive subset の Kotlin renderer port。
4. Deterministic fallback を含む Stage 1 / Stage 1.5 / Stage 2 pipeline shape。
5. Single drawing、batch、demo、history、settings shell、render previews、prompt view、JSON view の Compose UI。

次の残作業:

1. Pixel 9 上で、downloaded Gemma 4 E2B/E4B `.litertlm` model files を使った LiteRT-LM inference を end-to-end verify し、
   provider failure を silent fallback ではなく UI/log surface に出す。
2. foreground service または WorkManager、notifications、metered-network policy、user-visible storage recovery で model download UX を harden する。
3. Kotlin renderer と JSON Score parser を full web primitive / style surface まで拡張する。
4. 現在の single-item share export から、Android Storage Access Framework を使う full history import/export flows へ export compatibility を拡張する。
5. reference web JSON / SVG / render metadata fixture に対する automated compatibility tests を追加する。
6. Non-history settings operation の destructive confirmation を完了し、Android UI state transition の automated parity coverage を追加する。

## 2026-05-07 Server Parity 修正記録

同一 DDL から描画した server CLI / Android CLI の比較で、DDL 正規化までは概ね一致していた一方、JSON Score と SVG 描画結果に差が残っていた。
調査の結果、主因は Android 側に残っていた server と異なる Stage 2 入力、Score tool schema、coerce chain、renderer seed/hash、独自補助レイヤーだった。

今回の修正で、Android のハードウェア非依存ロジックは原則として server 実装を master とし、以下を server source に合わせた。

- Stage 2 user message は `server/src/inku_server/composer.py` の `_build_user_message()` と同じ形式にする。
  `originalText` と DDL が同一の DDL 入力では、余計な `[原文]` block を付けず DDL のみを送る。
- Stage 2 tool schema は Android 独自の簡略 schema を廃止し、server の `_score_tool_schema()` から生成した `ServerScoreSchemaJson` を使用する。
- Stage 2 後の Score 補正は `server/src/inku_server/coerce.py` の `coerce_score()` の段階構成に合わせる。
  `material_hint`、`variation_hint`、DDL coverage、color delivery、shape delivery、complex motif、composition diversity、structural duplicate、context energy、presence auxiliary、density governor、motion energy、density budget を通常フローへ接続する。
- `material_hint` / `variation_hint` は server の `_with_material_hint()` / `_with_variation_hint()` と同じ marker と default variation を使う。
- server にない Android 独自補修として入っていた、`震える` を motion context として扱う追加条件と、membrane haze 補助レイヤー自動追加は削除する。
- renderer の arrangement 展開、scatter / path / clustered 配置、`preserve_space` margin、density radius、cluster axis / bend / jitter は `server/src/inku_server/renderer.py` に合わせる。
- renderer seed は `Instruction.model_dump_json()` 相当の field order と default/null 表現から作り、line variation の seed も同じ seed source を使う。
- variation / material jitter の signed hash は server の `_hash_to_unit()` と同じ SHA-256 + little-endian signed 64-bit 由来にする。

検証:

- `gradle :app:compileDebugKotlin` 成功。
- `gradle :app:assembleDebug` 成功。
- Pixel 9 へ debug APK を再インストールして headless DDL render comparison を実行。
- 最終確認 run: `/tmp/inku-headless/history-ddl5-after-final-parity-fix-20260507/history-ddl5-final-002`
  - `same_ddl: true`
  - `same_render_hash: false`
  - 残差は主に LLM Stage 2 出力揺れによる `variation.dimensions` と `arrangement.density` の差として確認した。

今後の比較で同一 Score からの描画差が出た場合は、renderer の Kotlin 実装差分として扱う。
Score 自体が異なる場合は、Stage 2 model response、tool schema、coerce chain の順に server source と照合する。

## 2026-05-07 Renderer Parity 追加修正記録

同一 Score を入力にした server CLI / Android headless renderer の PNG 比較で、DDL 正規化や Score 生成を介さない純 renderer 差分を切り分けた。
この比較では server 側の `inku-cli render-score` と Android 側の `HeadlessRenderActivity input_mode=score` を使用し、過去履歴から選んだ 5 件の Score を同一入力として描画した。

調査の結果、差分は SVG 文字列ハッシュの不一致ではなく、実際の PNG 上でも確認できる rendering behavior の差だった。
Android 側のハードウェアに依存しない描画処理は server 実装を master とし、以下を `server/src/inku_server/renderer.py` / `server/src/inku_server/color_catalogs.py` に合わせて修正した。

- renderer hash / noise:
  - `hash01` は server の `struct.unpack("<I", digest[:4]) / 0xFFFFFFFF` と同じ little-endian unsigned 32-bit にする。
  - signed hash は server の `struct.unpack("<q", digest[:8]) / 2**63` と同じ little-endian signed 64-bit にする。
  - smooth noise は `hash01 * 2 - 1` ではなく server の `_hash_to_unit()` 相当を使う。
- color catalog / color resolution:
  - render 用 color map は基本 6 色だけでなく `palette:<name>` entries も含める。
  - `color_hint` と palette label / hue hint から最終色を再解決する `_resolve_color()` 相当を Android に移植する。
  - `material inferred from DDL: ...` などの hint 文字列に含まれる token も、現行 server と同じ scoring rule で扱う。
- color cycle:
  - `arrangement.color_cycle` 展開時は server の `_apply_color_cycle()` と同じく、色選択に関係する hint を落とし、描画効果に関わる hint だけを残す。
  - `count == 1` の arrangement でも color cycle を適用する。
- arrangement effect hint:
  - `_shift()` 相当のタイミングで `density=<value>`、`fade=<value>`、`preserve_space` を `color_hint` に追記し、透明度制御に反映する。
- coordinate conversion:
  - server の `_px()` は 0..1 clamp を行わず、キャンバス外へ伸びた geometry は clip-path に任せる。
  - Android でも `px()` の clamp を削除し、配置展開後の line / shape が server と同じ座標で描かれるようにする。
- blur / texture:
  - `quality=pink` の blur は stroke attrs へ直接入れず、server と同じく描画 element/group に後段で filter として適用する。
  - material texture filter と blur filter の責務を分ける。
- SVG stroke defaults:
  - server が明示していない `stroke-linejoin="round"` の Android 常時付与を削除する。

検証:

- `gradle :app:compileDebugKotlin` 成功。
- `gradle :app:assembleDebug` 成功。
- Pixel 9 へ debug APK を再インストールして、同一 Score 5 件の server / Android PNG 比較を再実行。
- 最終確認 run: `/tmp/inku-headless/score-render-server-vs-android-after-linejoin-fix-20260507`

最終 PNG 差分:

| run | mean absolute difference | RMS difference | note |
| --- | ---: | ---: | --- |
| score-render-001 | 0.0% | 0.0% | PNG 上は一致。 |
| score-render-002 | 0.0487% | 0.9241% | 極小差分が残る。 |
| score-render-003 | 0.0033% | 0.0965% | 実質一致に近い。 |
| score-render-004 | 0.1387% | 1.4994% | 残差最大。次回は material / filter rasterization と shape outline を優先確認する。 |
| score-render-005 | 0.0137% | 0.2947% | 実質一致に近い。 |

関連 commit:

- `0999489 fix: align android renderer hashes with server`
- `0a61e66 fix: align android renderer style with server`
- `3871dd5 fix: match server stroke join defaults`

今後の renderer parity 作業では、まず同一 Score 入力で PNG 差分を確認し、Score が同一でない場合のみ Stage 2 / coerce chain 側へ戻る。
同一 Score で残る差分は、SVG element 属性、filter 注入位置、material outline、SVG rasterizer 差の順に server source と比較する。

## Local Commit Record

- `f34852b feat: add android headless render comparison`
  - Android headless render entry point と adb-driven comparison script を追加。
  - OpenAI-compatible provider routing、encrypted local provider API key storage、
    web-compatible Stage 1 / Stage 1.5 / Stage 2 prompt and tool support を追加。
  - Web DDL expander port の Android-side tests を追加。
  - Pixel 9 UI、model/provider selection、batch/history/settings flows、renderer support を Android parity checkpoint として更新。
  - `gradle :app:compileDebugKotlin` と `bash -n android/scripts/headless_render_compare.sh` で確認。

この commit は local-only artifacts、具体的な device IDs、local server addresses、downloaded models、API keys を意図的に含めない。
無関係な `manual/` files は untracked のまま残した。

## Build And Deployment Notes

repository workspace からの既知の debug build command:

```sh
cd android
GRADLE_USER_HOME=/tmp/inku-gradle-home JAVA_HOME=/Applications/Android\ Studio.app/Contents/jbr/Contents/Home gradle :app:assembleDebug
```

USB deployment commands は local environment の target device serial を使う。
具体的な local device ID を commit してはならない。

```sh
adb -s "$ANDROID_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s "$ANDROID_SERIAL" shell am force-stop app.inku.mobile
adb -s "$ANDROID_SERIAL" shell am start -n app.inku.mobile/.MainActivity
```

Room は WAL を使う。接続中 debug device から database を確認するときは、
main database と WAL files をまとめて pull する。

```sh
adb -s "$ANDROID_SERIAL" exec-out run-as app.inku.mobile cat databases/inku.sqlite > /tmp/inku-android.sqlite
adb -s "$ANDROID_SERIAL" exec-out run-as app.inku.mobile cat databases/inku.sqlite-wal > /tmp/inku-android.sqlite-wal
adb -s "$ANDROID_SERIAL" exec-out run-as app.inku.mobile cat databases/inku.sqlite-shm > /tmp/inku-android.sqlite-shm
```

## 2026-05-07 Pixel 9 UI / Canvas 操作更新

Claude Design DDL4 の S1 Compose（記述）案を参考に、Android 版の描画タブ UI を更新した。
ただし、モバイル UI 方針として横スクロールは使用禁止とし、すべての選択肢・チップ・メニューは折り返し表示または縦方向の配置で構成する。

今回の更新での UI 要件:

- 描画タブの主表示は S1 Compose（記述）を優先し、キャンバス、条件チップ、指示入力、正規化 DDL の順に自然に確認できる構成にする。
- 画像プレビュー上にボタンやメニューを重ねない。
  - star / render hash / zoom 操作は画像の上側へ配置する。
  - 描画 / Prompt / JSON / SVG / PNG の操作は画像の下側へ配置する。
  - SVG / PNG の展開メニューも画像上へ被せず、画像下のインライン選択肢として表示する。
- 画像本体のタップは no action とする。
- 画像本体のジェスチャは、ピンチイン / ピンチアウトによる zoom と、zoom 時の pan のみに使う。
- 既存のタブ、設定、履歴、歳時記、モデル選択、色カタログ選択などのボタンは、見た目だけでなく必ず遷移先または実処理へ接続する。
- 日本語 IME 表示時に入力欄が隠れないよう、入力欄は bring-into-view / IME padding 前提の実装を維持する。

SVG / PNG 共有の挙動:

- SVG / PNG / JSON の共有は、重いファイル生成処理を main thread で実行しない。
- PNG 生成は SVG rasterize と PNG encode を background dispatcher で実行し、完了後に Android share sheet を開く。
- SVG は server / web 版と同じ利用意図を持つ profile 選択を提供する。
  - 表示用 SVG
  - 編集用 SVG
  - 汎用 SVG
- PNG は server / web 版の保存テンプレートに合わせ、少なくとも以下の Y 軸サイズを提供する。
  - 1080px
  - 2160px
  - 4320px
- Android 版ではブラウザ download ではなく Android の share sheet を使うが、ユーザー操作上は Web 版の SVG / PNG メニューと同じ役割を持つ。

実機確認:

- `gradle :app:compileDebugKotlin` 成功。
- `gradle :app:assembleDebug` 成功。
- Pixel 9 へ debug APK を install し、起動を確認。
- スクリーンショットで、画像上に操作ボタンやメニューが重なっていないことを確認。
- PNG 1080px export を実行し、Android share sheet が表示されることを確認。
- PNG export 実行後の logcat で `FATAL EXCEPTION`、`ANR in`、`Input dispatching timed out` が出ていないことを確認。

## 2026-05-07 Android 履歴画面の明示的な server/web 差分

Android 版は Pixel 9 以上を想定したシングルユーザー用ネイティブアプリであり、server/web 版を開発上の master としながらも、モバイル操作で不要または重い管理導線は明示的に削除する。

今回、履歴画面について以下を server/web 版からの明示的な差分として定義する。

- ごみ箱機能は Android UI では提供しない。
  - 履歴画面に Trash / ごみ箱の表示切替を置かない。
  - 履歴を Trash へ移動するボタンを置かない。
  - Trash からの復元ボタンを置かない。
  - 履歴の完全削除ボタンを置かない。
  - ごみ箱操作の確認ダイアログを出さない。
- 履歴画面のリスト表示は Android UI では提供しない。
  - 履歴表示は S4 History（履歴）に寄せた 3 列サムネイルグリッドを標準かつ唯一の表示形式とする。
  - サムネイル / リストの表示切替ボタンを置かない。
- ごみ箱削除を前提にした一括選択操作は Android UI では提供しない。
  - 全選択ボタンを置かない。
  - 各履歴カードのチェックボックス表示を置かない。
- 履歴画面に残す操作は、検索、星付きフィルタ、履歴選択、選択中履歴の Star / Star 解除、JSON 共有に限定する。

この削除は未実装ではなく、Android 版のモバイル UI とシングルユーザー前提に基づく意図的な仕様差分である。

## 2026-05-07 LiteRT-LM MTP と Gemma 4 再取得導線

Android 版の LiteRT-LM は GPU backend を必須とし、CPU fallback は行わない。
Gemma 4 E2B / E4B のローカル実行では、LiteRT-LM の speculative decoding / Multi-Token Prediction (MTP) を有効化する。

実装要件:

- LiteRT-LM Engine 初期化前に `ExperimentalFlags.enableSpeculativeDecoding = true` を設定する。
- backend は `Backend.GPU()` のままとする。
- GPU 初期化に失敗した場合は描画を継続せず、ユーザーへエラーを返す。
- CPU fallback を入れてはいけない。
- Engine 初期化 log には GPU backend と speculative decoding 有効状態を確認できる情報を出す。

Gemma 4 モデル取得 UI:

- モデル設定の LiteRT-LM / Gemma E2B / E4B パネルに、既存のライセンス同意 / ダウンロード導線とは別に `再取得` ボタンを用意する。
- `再取得` は、端末内の完成済み `.litertlm` と中断中の `.part` を削除し、同じ Hugging Face URL から最初から取得し直す。
- ライセンス未同意のモデルでは `再取得` を実行できない。
- 取得中、接続中、検証中など busy 状態では `再取得` を実行できない。
- 再取得中の進捗は通常ダウンロードと同じ Room の `model_assets` 状態で管理する。

モデルファイルに関する扱い:

- 2026-05-05 より前に取得した Gemma 4 LiteRT-LM ファイルは MTP 対応前の可能性があるため、ユーザーは `再取得` で最新ファイルに更新できる必要がある。
- 2026-05-07 時点で、E2B / E4B の Hugging Face `x-linked-etag` は Android 実装に保持している SHA-256 と一致している。
- そのため、現時点では download URL と SHA-256 を変更せず、端末内の古いファイルを破棄して同じ URL から取り直す方針とする。

確認:

- `gradle :app:compileDebugKotlin` 成功。
- `gradle :app:assembleDebug` 成功。
- Pixel 9 へ debug APK を install し、起動を確認。

## 2026-05-08 記述パネル描画表示の Android 固有履歴スワイプ

Android 版の記述パネルでは、モバイル操作に合わせた server/web 版との明示的な差分として、描画画像そのものへの左右スワイプで表示中の履歴を切り替えられる。

- 描画画像上の右スワイプは、履歴を 1 件前へ戻す。
- 描画画像上の左スワイプは、履歴を 1 件後へ進める。
- 画像タップには操作を割り当てない。
- ピンチイン / ピンチアウトによるズームと、ズーム時のパン操作は維持する。
- ズーム中は履歴スワイプより画像操作を優先する。
- 通常表示時の履歴スワイプは描画画像の表示範囲内だけを対象とする。
- 1 回の横スワイプで複数履歴へ連続移動しないよう、短時間の連続履歴送りを抑制する。
- アプリ起動時に最新履歴を復元した直後でも履歴一覧を参照できるよう、ViewModel は履歴一覧を起動時から保持する。

この操作は Android 版の片手操作性とモバイル履歴確認のための追加仕様であり、server/web 版との parity 対象ではない。

確認:

- `gradle :app:compileDebugKotlin` 成功。
- `gradle :app:assembleDebug` 成功。
- Pixel 9 へ debug APK を install し、記述パネルの描画画像上で左スワイプ / 右スワイプによる履歴切替を確認。

## 2026-05-08 Android 固有のモデル選択一本化

Android 版のモデル選択 UI は、モバイル操作の単純化を優先し、Stage 1 / Stage 2 を別々に選ばせず単一の「描画モデル」選択として扱う。

- 記述画面のモデル選択ダイアログ、設定画面のモデル選択パネルは、Stage 1 / Stage 2 個別選択ではなく 1 つのモデル選択を表示する。
- 記述画面のモデル選択ダイアログは、モバイルでの即時選択を優先し、server/web 互換メタデータ維持に関する説明文を表示しない。
- 記述画面のモデル選択ダイアログは、単一選択に必要な provider / model list / OK / cancel に絞ったコンパクトなサイズにする。
- ユーザーがモデルを選択した場合、Android 内部状態では `selectedModelId` と `selectedStage2ModelId` の両方へ同じ model id を設定する。
- 設定保存は将来の個別オプション復活に備え、従来通り `model_selection.stage1_model` と `model_selection.stage2_model` を保持する。
- 履歴 DB、JSON 表示、JSON export、render metadata の `stage1_model` / `stage2_model` は server/web 互換のため維持する。
- Repository / pipeline の引数も `stage1ModelId` / `stage2ModelId` を維持し、Android UI の単一選択値を両方へ渡す。
- 既存設定に Stage 1 / Stage 2 の異なる値が残っている場合、Android UI 復元時は Stage 1 側を優先して単一選択へ正規化する。

この仕様は Android UI の独自差分であり、サーバー互換の保存形式と履歴メタデータを変更するものではない。

## 2026-05-08 Android 固有のプレゼンテーション表示

Android 版では、描画画像をダブルタップするとプレゼンテーション表示へ移行する。

- プレゼンテーション表示中は、描画画像以外のアプリ内 UI を非表示にし、画像表示領域を画面全体へ広げる。
- 画像は画面中央に配置し、拡大率は画像全体が切れずに表示される最大サイズへ自動調整する。
- 表示中 SVG の `viewBox`、または `width` / `height` から画像の実縦横比を判定する。
  取得できない場合のみ、保存済み履歴の `canvas_aspect` を `CanvasAspects` 定義で解決する。
- 横長キャンバスの画像は、Pixel 9 の縦画面に合わせて 90 度または 270 度回転し、画の長辺がスクリーンの長辺方向へ必ず揃うように表示する。
- プレゼンテーション表示中は、端末の物理的な上下向きを検出し、画像の上方向を端末の向きに合わせて動的に補正する。
  ただし横長画像では長辺合わせを優先し、回転角は 90 度または 270 度のどちらかに保つ。
- プレゼンテーション表示の余白背景は、表示中 SVG の背景 `rect fill` を画像の支配的な背景色として扱い、それに合わせて変更する。
- 画像背景色が白系の場合は、余白背景を Android ダークモード背景へ切り替える。
- 画像背景色が黒系の場合は、余白背景を Android ライトモード背景へ切り替える。
- 白 / 黒以外の背景色では、抽出した画像背景色の輝度で明暗を判定する。
- 白 / 黒以外でも明色の場合は Android ダークモード背景、暗色の場合は Android ライトモード背景を余白背景に使用する。
- プレゼンテーション表示中は、ピンチ / パンによる拡大移動を行わず、ダブルタップで通常表示へ戻る。
- プレゼンテーション表示中のダブルタップと左右スワイプは、画像の表示範囲内だけでなく、余白を含むプレゼンテーション画面全体で有効とする。
- プレゼンテーション表示中の左右スワイプは、端末の現在向きに合わせて判定する。
  Activity は portrait 固定のままでも、端末を横向き / 上下反転で持った場合は、物理端末基準の左右として履歴移動方向を解釈する。
- プレゼンテーション表示中は、右スワイプで履歴を 1 件後へ進め、左スワイプで履歴を 1 件前へ戻す。
  これは通常表示時の画像内スワイプ方向とは逆であり、全画面鑑賞時のページ送り感覚を優先する Android 固有仕様とする。
- server/web 版 `CanvasPanel.svelte` の presentation controls に合わせ、プレゼンテーション表示の下部に操作コントロールを表示する。
  Android 版でも、履歴を 1 件前へ戻す、最新履歴へ移動する、履歴を 1 件後へ進める、現在位置 / 全件数の枚数表示、Star / Star 解除、指示文字幕表示切替、終了を同じ役割の操作として提供する。
- 指示文字幕は、Stage 1 送信用に拡張された内部 prompt ではなく、表示中履歴のユーザー入力原文を使う。
  字幕は画像表示の下部に重ね、プレゼンテーション画面内で左右余白を持つ表示とする。
- 字幕表示ボタンは、表示できる指示文原文がない場合は無効化する。
- 通常表示時のピンチ拡大、パン、左右スワイプによる履歴切替は維持する。

この挙動はモバイル閲覧用の Android 独自 UI であり、履歴 DB、SVG/PNG 書き出し、render metadata の内容は変更しない。

## 2026-05-08 Render metadata のキャンバス比率値

server/android 共通仕様として、render metadata に従来の `render_canvas_aspect` に加えて `render_canvas_aspect_id` と `render_canvas_aspect_ratio` を追加する。

- `render_canvas_aspect` は互換性のため従来通り保持する。
- `render_canvas_aspect_id` は明示的なキャンバス比率識別子であり、Android の新規 render metadata / JSON 表示 / headless result に含める。
- `render_canvas_aspect_ratio` は実際にレンダリングされたキャンバスの幅÷高さの数値であり、例として `square=1.0`、`oban=0.666666...`、`wide=2.35` を記録する。
- Android の render hash 計算は、server と同じく `render_canvas_aspect_id` と `render_canvas_aspect_ratio` を含める。
- 旧履歴で新フィールドが存在しない場合、表示時は保存済みの `canvas_aspect` / `render_canvas_aspect` から補完する。

比率値の取得元:

- server 版では、system plugin の `canvas_aspect` 定義にある `ratio_w` / `ratio_h` から `render_canvas_aspect_ratio` を算出する。
- Android 版では、server の `canvas_aspect` 定義を移植した `CanvasAspects` を唯一の取得元とし、同じ識別子から `ratioW / ratioH` を算出する。
- JSON、履歴、headless result、render hash に記録する比率値は、描画時に実際に選択された `render_canvas_aspect_id` に対応する定義値から作る。
- 旧履歴や外部入力で比率値が欠落している場合も、保存済み識別子から同じ定義を使って補完する。
- Android 側で、plugin 定義に存在しない独自のキャンバス比率値を後付けしてはならない。

## 2026-05-08 描画パネルのキャンバス選択導線

Android 版の描画パネルでは、モバイル操作に合わせ、画像表示の右上にあるズーム操作行へキャンバス選択ボタンを配置する。

- キャンバスボタンはズーム率表示の右隣に置く。
- ボタン表示は選択中キャンバスの名前とし、長い名前は描画パネル内に収まるよう短縮する。
- ボタン押下でキャンバスサイズ選択ダイアログを表示する。
- キャンバスを選択した時点で設定を保存し、ダイアログを閉じる。
- この導線は記述 / バッチの描画パネルから使用でき、`canvas_aspect` 設定を更新する。
- server/web 版には独立した「キャンバス」設定タブはなく、キャンバス比率の選択は入力パネルの `CanvasAspectPlugin` から行う。
- Android 版でも `設定 > キャンバス` は廃止し、キャンバス選択は描画 / 記述画面のボタンと共通の選択ダイアログに集約する。
- server/web 版のプラグイン有効 / 無効設定はサーバー運用・プラグイン管理機能であり、シングルユーザー Android 版には移植しない。

## 2026-05-09 色カタログ選択導線

Android 版では、server/web 版 `InputPanel` と `ColorCatalogModal` に合わせ、色カタログ選択を設定メニューではなく記述 / 描画画面のボタンから開く共通ダイアログへ集約する。

- server/web 版には独立した「色カタログ」設定タブはない。
- `設定 > 色カタログ` は廃止する。
- 色カタログ選択ダイアログは維持し、記述 / 描画画面の色カタログボタンから開く。
- `color_catalog` の保存、履歴 DB、render metadata、JSON 表示、render hash の扱いは変更しない。
- 履歴選択時に履歴の色カタログを反映するかどうかの設定は、server/web 版と同じく表示設定側に残す。

## 2026-05-08 モデル設定パネルの接続先 UI

Android 版のモデル設定パネルは、server/web 版のモデル接続先設定に合わせ、各サービスを独立した接続先パネルとして表示する。

- `AI SERVICE CONNECTIONS` などの英字セクション見出しは表示しない。
- 各サービスパネルでは、パネル名の右側に `変更` ボタンを表示し、サービス名変更ダイアログを開く。本文側に `サービス名` ラベルと値は重複表示しない。
- 接続形式はドロップダウン選択とし、server と同じ `openai_compatible`、`anthropic`、`gemini` に Android 固有の `litert-lm` を追加する。
- `Base URL` は表示専用行とし、横の `編集` ボタンから URL 変更ダイアログを開く。
- `APIキー` は server/web 版と同じ状態遷移に寄せ、設定済みの場合は入力欄を表示せず単一ボタンを `削除` とし、未設定の場合は単一ボタンを `追加` として新しいキーを設定できる。
- ユーザーに公開するモデルを表示し、横の `モデル選択` ボタンからモデル選択ダイアログを開く。
- モデル選択ダイアログは、server/web 版と同じくモデル一覧取得、全選択、全解除、検索、チェック式モデル一覧、保存 / キャンセルを持つ。
- モデル一覧取得ボタンは、接続先サービスから最新のモデル一覧を取得し、公開モデル候補へ反映する。
- モデル一覧取得中および取得結果のステータスは、ダイアログ下部に表示する。
- モデル検索入力欄は、モデルID検索に合わせて英数字入力を優先するキーボード設定にする。
- モデル一覧取得後の選択状態は server/web 版に準拠し、既存候補かつ取得前に選択済みだったモデルだけを選択済みとして維持し、新規候補は自動選択しない。
- モデル一覧取得で得た候補リストは、ユーザーに公開するモデルの保存値とは分離して保持する。描画画面のモデル選択には、公開済みとして保存されたモデルだけを表示し、未選択の取得候補を混入させない。
- 旧 Android 実装で初期候補リストが公開済みモデルとして保存されていた場合、既知の初期候補リストと完全一致する行だけを起動時に正規化し、移植時の初期値混入を取り除く。
- 各サービスパネルの最下段には `サービス削除` と `保存` を配置する。
- Android 版ではユーザー管理を持たないため、このパネルで設定した公開モデルは単一ユーザーが描画モデルとして選択できるモデル一覧へ反映される。
- LiteRT-LM の取得中断ボタンはモデル設定パネルには表示しない。

## 2026-05-08 デモパネルの S3 レイアウトとランダム色カタログ

Android 版のデモパネルは、Claude Design DDL4 の `S3 — Demo（デモ）` を基準に、画像表示以降の構成を `状態表示`、`生成された指示文`、`シードフレーズ`、`デモ設定`、`開始 / 停止` の順に配置する。

- 画面上部から画像までのヘッダー要素は Android 既存ナビゲーションに従い、S3 の `inku` ラベル等は移植対象外とする。
- デモ開始後は、server/web 版と同じく `指示生成 → 描画 → 表示間隔待機` のループとして動作する。
- 指示文生成に使用するモデルは Android のメインモデル選択に従う。デモパネル内に指示文生成モデル専用の設定エリアは表示しない。
- デモ描画ではランダム色カタログを Android 独自仕様として常時オンにし、デモ設定パネルにオプション行は表示しない。各描画サイクルで `repository.paint` へ渡す色カタログを都度ランダムに選ぶ。
- 表示間隔行は `-`、`xx秒`、`+` の順で表示する。
- 画像のダブルタップでプレゼンテーションモードへ移行した場合もデモ描画は継続し、画面右下に現在画像の残り表示時間を表示する。
- LLM 状態表示は、Android の単一モデル選択が指示文生成 / Stage 1 / Stage 2 に共通適用されることを示すため、`指示文生成/Stage1/2共通` と表示する。
- 旧設定で `demo_random_color_catalog` が保存されていても、デモでは常時オンとして復元する。
- シードフレーズと表示間隔もデモ設定として保存し、再起動後に復元する。
- デモ履歴は既存 Android 実装に合わせて通常履歴へ保存し、入力履歴には `[demo] ` prefix を付ける。

## 2026-05-08 描画パネルの SVG / PNG エクスポートメニュー

Android 版の描画パネルでは、server/web 版 `CanvasPanel` の SVG / PNG エクスポート操作に合わせ、`SVG` ボタンと `PNG` ボタンを単発アクションではなくメニュー形式にする。

- `SVG` ボタンは `SVG ▾` と表示し、押下でメニューを開く。
- SVG メニューには `表示用SVG`、`編集用SVG`、`汎用SVG` を表示する。
- `表示用SVG` は `svg_profile=display` として共有シートへ渡す。
- `編集用SVG` は `svg_profile=editable` として共有シートへ渡し、編集用途のメタデータと ID を含める。
- `汎用SVG` は `svg_profile=compat` として共有シートへ渡す。
- SVG メニューには server/web 版と同じ意図でヘルプ導線を置き、各形式の用途を確認できるようにする。
- `PNG` ボタンは `PNG ▾` と表示し、押下でメニューを開く。
- PNG メニューは固定値を直書きせず、Room に保存された `export_templates` を表示する。
- 初期テンプレートは server/web 版と同じ `PNG 1080px`、`PNG 2160px`、`PNG 4320px` とする。
- PNG メニューの各項目はテンプレート名と説明を表示し、選択したテンプレートの `height_px` を PNG 生成の Y 軸ピクセル数として使用する。
- SVG / PNG の選択後は Android の共有シートを開く。履歴 DB、render metadata、render hash は変更しない。
- 旧 Android 実装のように、ボタン押下後にチップを横並び展開する UI は使用しない。
- `設定 > 出力ファイル` は server/web 版に同等の設定タブがなく、Android 側でも固有の保存設定を持たないため廃止する。
- SVG / PNG / JSON の共有機能は描画パネルの各メニューから実行し、PNG 背景と PNG テンプレート管理は `設定 > エクスポート` に集約する。
- server/web 版の `server_misc` にある出力ファイル自動保存設定はサーバー運用機能であり、シングルユーザー Android 版には移植しない。

## 2026-05-09 Android version / build 管理

Android 版は web/server の `web/BUILD_NUMBER` とは独立した Android 用 version / build を持つ。

- `android/VERSION` を Android `versionName` の正本とする。
- `android/BUILD_NUMBER` を Android `versionCode` とアプリ内 build number の正本とし、単調増加する整数として管理する。
- `android/app/build.gradle.kts` は `versionName` / `versionCode` を直書きせず、上記2ファイルから読み込む。
- v1.48 世代の初期値は `versionName=1.48.0-android.1`、`versionCode=148001` とする。
- `assemble*` / `bundle*` / `install*` の Android アプリ build タスクを実行するたびに、Gradle が `android/BUILD_NUMBER` を 1 増やし、その増えた値を同じ build の `versionCode` と `BuildConfig.BUILD_NUMBER` に使う。
- `compileDebugKotlin` などのコンパイル確認タスクでは `android/BUILD_NUMBER` を増やさない。
- server/spec 世代への追従、DB schema、履歴 JSON、render metadata、export 互換性に影響する変更では、`android/VERSION` も更新する。
- 設定メニューには `バージョン情報` パネルを置き、`versionName`、`versionCode`、build number、build type、application id、source spec、render engine version を表示する。
- version / build metadata には API キー、端末 ID、ローカルサーバー情報、個人環境パスを含めない。

## 2026-05-09 モデル設定パネルの追加整理

Android 版のモデル設定パネルは、接続形式をサービス追加時にのみ設定する。

- 既存サービスパネルから `接続形式` の表示とドロップダウンを削除する。
- 既存サービスの接続形式は `provider.kind` として保持し、サービス名、Base URL、APIキー、公開モデルの保存時にも変更しない。
- 接続形式の変更保存だけを担っていた各サービスパネル下部の `保存` ボタンは削除する。
- サービス追加ボタンを接続先一覧の末尾に表示し、追加ダイアログでサービスID、サービス名、接続形式、Base URL、APIキーを入力する。
- 各サービスパネルの `有効` / `無効` 表示は、接続確認結果ではなく DB の `isEnabled` 表示にすぎないため UI から削除する。
- `サービス削除` ボタンは小型化し、各パネル下部の右側へ配置する。

## 2026-05-09 DDL 編集ダイアログのモバイル語彙編集 UI

Android 版の DDL 編集ダイアログは、限られた画面サイズで歳時記語を参照しながら DDL を直接編集するため、server/web 版とは異なるモバイル専用の語彙編集 UI を持つ。

- DDL 本文中の歳時記語は、カテゴリごとの色を持つチップ風ハイライトとして表示する。本文の視認性を優先し、余白は最小限、角丸はわずかに留める。
- ハイライト色と候補チップの色は同じカテゴリ色を使い、本文中の語と候補一覧の関係を視覚的に揃える。
- 本文タップ時は自前の座標推定ではなく、Compose `BasicTextField` が確定したキャレット位置をもとに、その位置が歳時記語の内側なら語選択へ変換する。これにより折り返し、IME、スクロール、フォントサイズ変更によるタップ位置ずれを避ける。
- 選択中の語は本文ボックス上部と素材バーに明示表示し、候補タップでその語を置換する状態であることを示す。
- 候補タップ時は、語が選択されている場合は選択範囲を置換し、選択語がない場合は現在キャレット位置へ挿入する。
- 語が選択されている場合、候補列は選択語と同じ歳時記カテゴリの代替候補を先頭に表示する。選択語自身は候補から除外し、本文に出現済みの語はその後ろへ重複なしで続ける。
- 素材パネルを開いた場合も、選択語と同じカテゴリを最上段に並べ替え、カテゴリ名には代替候補であることを示す。
- この UI は Android 独自の編集体験であり、DDL、Score、SVG、履歴保存、JSON メタデータの server/web 互換性には影響させない。

## 2026-05-09 記述画面の補正状態と IME 復帰

Android 版の記述画面では、モバイル入力中の状態管理として以下を仕様化する。

- `補正` ボタンは DDL 自動補正 / Stage 1.5 相当の DDL 拡張を許可する状態を表す。
- 新規インストール時の `補正` は OFF をデフォルトとする。
- `補正` のON/OFFは Room 設定 `ddl_auto_repair` に保存し、アプリ再起動後も復元する。
- `補正` が OFF のとき、Stage 1 後および DDL から描画時に `expandIntermediateDdl()` を実行せず、表示される DDL に Android 側で追加フレーズを付与しない。
- `補正` が ON のときのみ、server/web 互換の DDL 拡張・補正経路を使う。
- 記述画面の `新規作成` は指示文だけでなく解釈DDLも同時にクリアし、`ddlEditedAfterGeneration` を false に戻す。
- IME 表示時は、フォーカス直後の単発スクロールではなく複数タイミングで `bringIntoView()` を再試行し、日本語IMEの候補欄やキーボード高さ変化後も入力領域が見えるようにする。
- 描画完了時は入力フォーカスを解除してIMEを閉じ、記述画面のスクロール位置を画像エリアへ戻す。

## 2026-05-09 Pixel 9 Landscape Safe キャンバス

Android 独自仕様として、Pixel 9 実機の横向き表示に合わせた `pixel9_landscape_safe` キャンバス比率を追加する。

- Pixel 9 実機の物理解像度は縦向き `1080 x 2424 px`、横向き `2424 x 1080 px`、density `420 dpi`、density scale `2.625`。
- カメラホールは portrait 上端中央にあり、landscape では左右端側の回避対象になる。実機の display cutout は portrait 座標で `Rect(485, 0 - 595, 173)` であり、landscape では片側へ約 `173 px` 食い込む。
- カメラホールと丸角を十分に避けるため、landscape 横幅 `2424 px` に対して左右それぞれ `240 px` 程度の安全マージンを想定する。
- 有効表示領域は `2424 - 240 * 2 = 1944 px`、高さ `1080 px` なので、最大化に近い安全比率は `1944:1080 = 1.8`。
- 実装上のキャンバス比率は簡潔な `9:5` とし、`CanvasAspects` では `id=pixel9_landscape_safe`、`label=Pixel 9 Landscape Safe`、`ratioW=9.0`、`ratioH=5.0` とする。
- この比率は Android 独自の表示最適化であり、server/web の canvas aspect plugin には存在しない。履歴、JSON、render metadata、render hash には通常の `render_canvas_aspect_id` / `render_canvas_aspect_ratio` として記録する。

## 2026-05-09 デモ設定パネル

Android 版では、デモ画面のシードフレーズ編集を画面本体から外し、`設定 > デモ設定` に移動する。

- デモ画面本体は画像、状態、生成された指示文、開始 / 停止、表示間隔の確認に集中させる。
- `設定 > デモ設定` では、シードフレーズと表示間隔を編集できる。
- シードフレーズは Room 設定 `demo_seed_phrase` に保存し、アプリ再起動後に復元する。
- デモ開始後、各描画サイクルではシードフレーズを現在選択中のメインLLMへ投入し、その回答を `生成された指示文` box に表示する。
- `生成された指示文` box に表示したLLM回答を、そのまま通常の指示文として Stage 1 DDL生成、Stage 2 Score生成、描画へ接続する。
- デモ用の固定テンプレートから指示文を組み立てる旧Android実装は使用しない。
- デモ描画で使用するキャンバス比率は Android 独自の `pixel9_landscape_safe` 固定とし、通常の記述画面で選択中のキャンバス設定には従わない。
- デモ描画の色カタログは常に各描画サイクルごとにランダム選択し、通常の記述画面で選択中の色カタログ設定には従わない。
- デモ画面下部のメタ情報では、`Color` にその描画サイクルで実際に使用した色カタログ名を表示する。起動直後など既存履歴を表示している場合は履歴に保存された色カタログIDから表示名を解決する。
- デモ画面下部の `Canvas` は内部IDではなく、`CanvasAspects` のユーザー向け表示名を表示する。`pixel9_landscape_safe` は `Pixel 9 Landscape Safe` と表示する。
- シードフレーズの既定値は以下とする。

```text
世界の人と動物、自然と都市を主題として96文字の短文を作って。感情豊かに、季節や、人生と人のつながり、人生、世代、神。色々な観点から。
```

- `デフォルト値に戻す` ボタンを置き、編集後でも上記の既定値へ戻せるようにする。

## 2026-05-10 LiteRT-LM 0.11.0 固定と性能計測ログ

Android 版の LiteRT-LM 実行は、比較再現性と調査容易性を優先し、依存バージョンと実行時ログを明示的に管理する。

- LiteRT-LM Android dependency は `latest.release` を使用せず、`com.google.ai.edge.litertlm:litertlm-android:0.11.0` に固定する。
- Stage 1 / Stage 2 の system prompt は user prompt に連結せず、LiteRT-LM の `ConversationConfig(systemInstruction=...)` として渡す。
- `Conversation.sendMessageAsync()` には各 stage の user prompt のみを渡す。これにより prompt 包装の重複を避け、LiteRT-LM 公式 API の会話モデルに合わせる。
- GPU backend 必須、CPU fallback なし、speculative decoding / MTP 有効の方針は維持する。
- LiteRT-LM provider は `InkuPerf` log tag で以下を出力する。
  - `litert_request_start`: `model_id`、`prompt_chars`、`system_chars`、`max_tokens`、`engine_max_tokens`
  - `litert_engine_init`: `model_id`、`backend`、`speculative_decoding`、`engine_init_ms`、`max_tokens`
  - `litert_request_done`: `model_id`、`elapsed_ms`、`output_chars`
- pipeline は `InkuPerf` log tag で以下を出力する。
  - `paint_start` / `paint_done`: 選択 model、prompt length、catalog、canvas、total elapsed、render hash
  - `stage1_start` / `stage1_done` / `stage1_failed`
  - `stage2_start` / `stage2_done` / `stage2_failed`
  - `stage2_invalid`: 初回 Stage 2 出力が retry へ回った理由、response length、instructions 有無、短い preview
  - `render_start` / `render_done`
- LiteRT-LM Stage 2 では、Gemma が `0. 0`、`0. 01`、`50 0` のように JSON 数値の内部へ空白を混入させることがあるため、Stage 2 system prompt に数値内部空白の禁止例を明記する。
- Stage 2 JSON 取り込み側では、strict parse、JSON object substring parse、LiteRT-LM 数値空白補修後 parse の順に試行する。さらに `org.json` が壊れた数値を文字列として受けた場合も、key と文字列 value を trim し、数値に見える文字列だけを `Int` / `Long` / `Double` へ正規化する。key 内の改行・空白崩れは schema 互換の snake_case へ正規化する。
- これらのログは performance investigation 用であり、履歴 JSON、Score、SVG、render metadata の server/web 互換形式を変更しない。
- `engine_init_ms`、`stage1_ms`、`stage2_ms`、`render_ms`、`model_id`、`prompt_chars` は adb logcat から収集し、必要に応じて `no-git-sync/perf-logs/` に保存する。`no-git-sync` 配下の計測ログは git 管理対象外とする。

2026-05-10 時点の Pixel 9 実機計測では、同一指示文、`ink_season`、`pixel9_landscape_safe`、GPU backend、MTP 有効で以下を確認した。

- E2B: `engine_init_ms=6741`、`stage1_ms=18422`、`stage2_ms=89507`、`render_ms=13`、total `107956ms`。Stage 2 は再投入が発生した。
- E4B: 初回 `perf-litert-e4b-003` は Stage 1 engine init 中に process 終了。再実行 `perf-litert-e4b-004` は `engine_init_ms=12011`、`stage1_ms=29937`、`stage2_ms=41931`、`render_ms=47`、total `71933ms`。Stage 2 は再投入が発生した。
- `ConversationConfig(systemInstruction=...)` 化により user prompt 側の `prompt_chars` は Stage 1 で 31、Stage 2 で 132 程度まで短縮されるが、system prompt は別枠で渡るため、総処理時間の改善は model output と retry の有無に強く依存する。
- Stage 1 prompt 最適化 ON、E2B、同一指示文で `perf-litert-e2b-opt-002` を実行したところ、初回 Stage 2 出力は `0. 0`、`0. 01`、`50 0` のような数値内部空白を含む JSON で、`stage2_invalid reason=json_extract_failed` により retry へ回った。
- 数値内部空白禁止 prompt と JSON 取り込み補修を追加後、同一条件の `perf-litert-e2b-opt-004` は retry なしで完了した。実測は `engine_init_ms=3644`、`stage1_ms=10223`、`stage2_ms=28124`、total `38466ms`、render hash short `DCB9`。
- 同じ指示文を server 側 `inku-cli paint` で `nvidia:google/gemma-4-31b-it`、`ink_season`、server 有効 canvas `wide` にて実行した `server-stage2-retry-001` では、`compose_retry_count=0`、`compose_retry_reasons=[]`、`compose_fallback_used=false`、`elapsed_stage2_ms=26060`、`tokens_out_stage2=351` であり、server 側 Stage 2 retry は発生しなかった。
- 以上から、今回観測した retry は server 共通の Stage 2 仕様問題ではなく、Android LiteRT-LM / Gemma E2B の自由テキスト JSON 出力が壊れる局所問題として扱う。ただし JSON 補修は provider 非依存の Score 取り込み層に置くため、他 provider が同種の壊れた JSON を返した場合にも防御的に有効とする。

## 2026-05-10 LiteRT-LM Stage 1 プロンプト最適化オプション

Android 独自仕様として、`設定 > モデル設定 > LiteRT-LM` パネルに `プロンプト最適化` チェックボックスを追加する。

- 設定値は Room `app_settings` の `litert_stage1_prompt_optimization` に保存し、再起動後に復元する。
- デフォルトは OFF とする。
- ON の場合でも、対象は Stage 1 model が `local-litert-lm:` のときだけとする。OpenAI / Claude / Gemini / NVIDIA / Ollama / OVMS などの非ローカル provider には影響させない。
- ON の場合、Stage 1 system prompt は web/server 版の巨大な Stage 1 prompt ではなく、LiteRT-LM 専用の圧縮版を `ConversationConfig(systemInstruction=...)` に渡す。
- 圧縮版 Stage 1 prompt は、以下の契約を維持する。
  - 正規化DDL本文のみを出力する。
  - Saijiki 語彙、属性保持、数量具体化、配置明示、ランダム禁止、点/粒/星/雨/雪/砂/花びらの真円固定禁止、人/顔/動物の非具象化、背景コントラスト保持、灰背景禁止を保持する。
  - 入力に近い Stage 1 変換例を少数だけ選び、prompt size を抑える。
- DDL、Score、SVG、履歴 JSON、render metadata の保存形式は変更しない。
- headless render でも同設定を参照する。CLI/ADB extras の `litert_stage1_prompt_optimization` が指定された場合は、その値を優先する。
- 圧縮版 prompt の導入にあたり、通常 Stage 1 prompt より十分短いことと、主要 fixture の変換例出力が一致することを unit test で確認する。

## 2026-05-10 Prompt タブ表示と LiteRT-LM 圧縮 prompt 表示

描画画面 / 履歴画面の `Prompt` タブは、原則として server/web 版の `/api/prompts` 表示に合わせる。

- 非 LiteRT-LM 描画では、履歴の保存時点の system prompt 文字列を DB に保存せず、表示時点の Android 実装が持つ通常の Stage 1 / Stage 2 system prompt を再構成して表示する。
- この通常表示では、履歴の model 種別による Stage 2 prompt 分岐や、入力文に応じた Stage 1 example 再選択を行わない。server/web の `OutputTabsContent` と同様に、通常の Stage 1 input、Stage 1 system、Stage 2 input、Stage 2 system を表示する。
- Android 独自仕様として、`stage1_model` または `stage2_model` が `local-litert-lm:` で始まる履歴は LiteRT-LM 描画として扱い、`Prompt` タブに LiteRT-LM 用 prompt を表示する。
- LiteRT-LM 描画の Stage 2 system prompt は、常に LiteRT-LM 専用の圧縮版 Stage 2 prompt を表示する。
- LiteRT-LM 描画の Stage 1 system prompt は、表示時点の `litert_stage1_prompt_optimization` 設定を反映する。ON の場合は LiteRT-LM 専用の圧縮版 Stage 1 prompt を表示し、OFF の場合は通常 Stage 1 system prompt を表示する。
- この仕様は Android の表示上の独自差分であり、DDL、Score、SVG、履歴 JSON、render metadata、render hash の保存形式は変更しない。

## 2026-05-10 安定性・セキュリティ強化

Android 版の安定性とローカルデータ保護のため、以下を実装する。

- `HeadlessRenderActivity` は Android 開発・外部検証に必須のため、debug build では `exported=true` を維持する。一方、release build では manifest placeholder により `exported=false` とし、通常配布版では外部アプリから起動できないようにする。
- debug build の `HeadlessRenderActivity` は外部起動可能性を維持するが、アプリ内部領域 `files/headless-auth-token` に生成した debug 専用ランダム token を `auth_token` または `headless_auth_token` extra として渡さない限り、描画処理へ進まない。
- `HeadlessRenderActivity` 用に `app.inku.mobile.permission.HEADLESS_RENDER` を signature permission として定義する。release build ではこの permission を activity に設定する。
- headless `run_id` は `[A-Za-z0-9._-]{1,80}` のみ許可し、出力先 canonical path が `files/headless/<run_id>` 配下であることを検証する。
- headless `text_file` は任意ファイルパスを許可しない。`text` extra 直接指定、または `app:headless-inputs/<file>` 形式でアプリ内部の専用入力ディレクトリ配下だけを読む。
- headless 入力は最大 250,000 文字に制限する。`text_file` も全量 `readText()` で読むのではなく、上限を超えた時点で拒否する。
- headless 出力 artifact は `files/headless` 配下に限定し、最大 50 run、または 7 日を超えた古い run を起動時に削除する。
- アプリバックアップは無効化する。DB、履歴、provider 設定、暗号化済み API key、ローカルモデル状態、headless 出力を cloud backup / device transfer の対象にしない。
- remote provider の Base URL は HTTPS、または端末内 loopback (`localhost` / `127.0.0.1` / `::1`) の HTTP のみ許可する。Ollama / OVMS のローカル検証用途は維持し、LAN / 外部 HTTP への prompt・API key 平文送信は許可しない。この検証は保存時と使用時の両方で行う。
- remote provider の HTTP エラー本文は UI 表示前に redaction し、Bearer token、NVIDIA API key、OpenAI key、Google API key、`api_key` / `authorization` / `token` らしき値を伏せる。
- remote provider の HTTP response body は無制限に読み込まない。成功応答は最大 2,000,000 文字、エラー応答は最大 16,384 文字まで読み、超過時は拒否または切り詰めて表示する。`HttpURLConnection` は成功・失敗に関わらず `disconnect()` する。
- headless result と remote provider error display には共通 redaction を適用し、API key、Bearer token、端末内データパスをそのまま表示・保存しない。
- LiteRT-LM provider は明示的な `close()` を持ち、ViewModel 破棄時および headless render 完了時に cached Engine を閉じる。ViewModel 破棄時の close は UI thread を `runBlocking` で止めず、Application scope の IO coroutine で実行する。
- 描画、DDL描画、バッチ、デモは run id を持ち、古い Job の完了・失敗通知が新しい描画状態を上書きしないようにする。
- バッチ実行は最大 100 件までとする。100 件を超える入力は実行前に拒否する。
- デモ実行は開始 1 回あたり最大 100 サイクルまでとし、上限到達時に停止する。
- Room DB は履歴、provider 設定、API key 関連のユーザーデータを保持するため、破壊的 migration を使わない。schema 変更時は明示的な Room migration を追加する。
- ローカルモデル download は `ModelDownloadSpec.maxDownloadBytes` を持ち、Content-Length 判明時と stream 中の両方で上限を超える download を中断する。
- 履歴サムネイルの decode は `files/thumbnails` 配下の canonical path のみ許可する。DB破損や想定外 path による任意ファイル decode を避ける。
- Compose の artwork / history thumbnail cache は entry 数ではなく推定 bitmap byte 数で制限する。
- Android build number は APK / bundle / install など package 生成系 task のみで increment する。clean な作業ツリーが必要な確認では assemble/install を不用意に実行しない。

## 2026-05-10 Android 性能最適化

Android 版は Pixel 9 実機での履歴表示、描画 preview、ローカルモデル初回実行の体感速度を改善するため、以下を実装する。

- 履歴一覧は `HistoryListItem` DTO で取得し、一覧表示に不要な `display_svg`、`expanded_ddl`、`score_json`、`render_metadata_json` を SELECT しない。
- 履歴詳細、再描画、JSON / Prompt 表示など完全な履歴内容が必要な操作では、履歴 ID から `HistoryItemEntity` を遅延取得する。
- 履歴サムネイルは描画保存時に 384px の WebP としてアプリ内部領域へ永続化し、Room `history_items` に `thumbnail_path`、`thumbnail_width`、`thumbnail_height` を保存する。
- 既存履歴でサムネイルが存在しないものは、起動時に最大 100 件までバックフィルする。
- この DB schema 変更は Room version 2 とし、`MIGRATION_1_2` で上記 3 列を追加する。破壊的 migration は使わない。
- 記述 / 履歴のメイン描画 preview は SVG を毎 recomposition で再描画せず、表示サイズと回転状態を key にした `LruCache` 上の bitmap を再利用する。
- Renderer の hot path では、色適用時の不要な JSON stringify / parse deep copy を避ける。ただし server/web 互換の Score、SVG、render metadata、render hash の意味は変更しない。
- LiteRT-LM モデルが選択され、かつ取得済み `ready` の場合、設定復元後、モデル選択後、モデル取得完了後に background で Engine warmup を試行する。
  - warmup は初回描画待ちを短縮するための先読みであり、描画の成功判定や GPU 必須方針を変更しない。
  - warmup で初期化済みの Engine は通常描画時に再利用する。
- 設定復元は `app_settings` を一括取得し、起動時に多数の `getSetting()` を逐次発行しない。
- PNG 共有 / 書き出しは最大高さ 4320px、推定 bitmap メモリ 128MB までに制限する。超過時はエラーとして扱い、巨大 bitmap 生成による OOM を避ける。
- これらの変更は Android 内部の性能最適化であり、DDL、Score、SVG、履歴 JSON、render metadata、render hash の server/web 互換形式は変更しない。

## 2026-05-10 Android 性能最適化 第2段

Android 版は追加の性能改善として、以下を実装する。

- Room DB を version 3 に上げ、履歴一覧で使う `trashed, created_at` と `starred, trashed, created_at` の複合 index を追加する。migration は `MIGRATION_2_3` で行い、破壊的 migration は使わない。
- `HistoryListItem` は検索用の lower-case 連結文字列を生成済み property として持ち、履歴検索入力ごとの全文連結・lowercaseを避ける。
- 履歴 Flow はトップレベルで常時 collect せず、履歴タブ表示時にのみ collect する。これにより記述 / デモ / 設定操作時の履歴リスト更新による不要な compose work を減らす。
- 描画保存時は履歴本体を先に保存し、384px WebP thumbnail 生成は repository 内の IO coroutine で非同期実行する。thumbnail列更新後に履歴一覧へ反映する。
- 起動時の既存履歴 thumbnail backfill は一度に100件処理せず、8件ずつ少量バッチで間隔を空けて実行する。
- Renderer / pipeline の hot path では、`JSONObject(item.toString())` による stringify / parse deep copy を top-level copy helper に置き換える。server/web 互換の Score 意味論は変更しない。
- LiteRT-LM streaming response の結合は `StringBuilder` ベースにし、Stage 2 の長い出力で文字列コピーを減らす。
- Stage 1 system prompt 生成は通常版 / LiteRT-LM圧縮版とも小さなLRU cacheを持ち、同一・近似入力での例選択と巨大文字列再構成を抑える。
- モデル設定 UI の公開モデルID parse は小さなLRU cacheを通し、同じ `publishedModelsJson` の再parseを避ける。
- PNG export 中は progress indicator と状態メッセージを表示する。大きなPNG出力時にUIが無反応に見えないようにする。
- Compose の artwork / history thumbnail cache は引き続き推定bitmap byte数で制限し、今回の追加変更でも保存形式・render hash・履歴JSONの互換性は変更しない。

## 2026-07-23 web/server v2 追随 Phase 1（Score schema / coerce / hash parity）

Android 版は `1.48.0-android.1` / render engine version `2` の世代にあり、master である
web/server は v2.4.2 / engine 10 に達している。差分は `CHANGELOG.ja.md` の
`### v1.49` 〜 `### v2.4.2` に対応し、描画コアの方式転換（絶対 px から比例系への改修、
閉図形輪郭・塗り・弧の手描きストローク化）と、変奏・プラグイン・系譜・添景の追加を含む。

追随は段階的に行う。**Phase 1 は「Score が新しい情報を運べるところまで」に限定し、
描き方（Renderer）には触れない。**

作者裁定（2026-07-23）:

- 描画コア（Score schema / coerce → Renderer）を優先し、系譜・UI は後続とする。
- **`render_engine_version` は engine 10 に到達するまで `"2"` を申告し続ける。**
  部分移植の途中で中間の値を名乗ると `render_hash` が変わり、履歴の互換と
  作品エディション ID の意味が壊れるため。
- server と Android の一致条件は当面「視覚的に同等」までとし、SVG のバイト一致は
  parity テスト整備後に判断する。ただし **Score（JSON）とハッシュは構造・値の一致を求める。**
- `android/VERSION` は engine 10 到達時に `2.x` 系へ上げる。それまで `1.48.0-android.1` を維持する。

### Phase 1 で移植した範囲

- **Stage 2 tool schema**（`ServerScoreSchemaJson.kt`）: primitive に `cloudform` を追加。
  weight に `burin` / `drypoint` を追加し `rope` を削除。instruction に `mode`（`additive` / `carve`）、
  `carve_depth`、`at`（演奏時配置領域）、`relation`（`along` / `not_touching` / `cutting` /
  `between` / `touching` と `contact: both_ends`）、`surface`（面の質感）を追加。
  arrangement に `layout="grid"` と `rows` / `cols` / `jitter` を追加し、count 上限を
  grid のとき 2000 とする。canvas は ID 文字列に加えて `{aspect, ground}` を受理する。
- **未知フィールドの拒否**: server が全 Pydantic スキーマへ `ConfigDict(extra="forbid")` を
  入れた変更（v1.86.1）に追随し、schema の全オブジェクトへ `additionalProperties: false` を
  付与した。`ServerScoreCoercer` は instruction の許可キー集合を持ち、範囲外のキーを除去する。
  許可キー集合は server `schema.py` の `Instruction` フィールドと一致させる。
- **Coercion**: `surface` と `relation` の正規化（既定値・範囲クランプ・`touching` のときのみ
  `contact` を残す）、grid の `rows` / `cols`（1-64）と `jitter`（0.0-1.0）のクランプ、
  `cloudform` の必須フィールド補修を追加した。
- **語彙判定**（`ServerScoreSemantics.kt`）: 「ビュラン」/ `burin`、「ドライポイント」/ `drypoint` を
  weight 判定へ追加し、削除済みの「縄」/ `rope` を落とした。`cloudform` は `center` と `size` を
  持つ図形として扱う。
- **ハッシュ体系**（`LocalFallbackPipeline.kt`）:
  - `dh1`（記述同一性）を `identity.py` と同じ規則で算出する。NFC 正規化 → `\r\n` と `\r` を
    `\n` へ → 前後の空白を除去 → `"dh1:" + sha256(...)`。
  - `render_hash` を `rh2` へ再定義した。payload は server `db.render_hash_for_item` と同じ
    `version` / `score` / `render_seed` / `vary_seed` / `render_build_number` /
    `render_engine_id` / `render_engine_version` / `render_color_catalog_id` の 8 項目とし、
    `"rh2:" + sha256(canonical_json)` を返す。canonical JSON は
    `sort_keys=True` / `separators=(",", ":")` / `ensure_ascii=False` 相当とする。
  - **seed の正規化**: server は `_canonical_seed` で `render_seed` / `vary_seed` を整数化して
    から payload に入れる。したがって文字列 `"12345"` と数値 `12345` は同じハッシュになる。
    Android にも `canonicalSeed` を置き、同じ正規化を行う。

### Phase 1 で移植していない範囲（Phase 2 以降）

Score は上記フィールドを受理・保持するが、**Renderer は描かない**。以下は Phase 2 以降で扱う。

- `surface` の質感描画、`canvas.ground` の地の描画
- grid（敷き詰め）のセル展開
- `cloudform` の輪郭生成（1/f 基底曲線 + 49 点閉 Bezier）
- `carve` の減算合成順序（ground → additive → carve → plate tone）
- `touching` の劣弧再構成と region / relation の解決順序（v1.94 の双弧修正を含む）
- 比例系改修（engine 7）以降のストローク化一式（engine 8 / 9 / 10）

### 検証

`app/src/test/java/app/inku/mobile/pipeline/ServerScoreParityTest.kt` を追加した。

- **Score の修復経路**: `server/tests/fixtures/stage2/` の 15 ケースを出所付きで取り込み、
  **LLM が吐きうる未整形の Score**（数値が文字列、`center` の別名 `position`、未知フィールドの
  混入）を入力として `ServerScoreCoercer` を通し、結果が fixture の `expected.json` と
  一致することを検証する。`primitive` だけでなく `center` / `position` / `from` / `to` /
  `radius` / `size` / `style` / `weight` / `color` / `variation` を照合し、
  複数命令の fixture は全命令を対象とする。
- **ハッシュの値一致**: server 実測値を固定値として検証する。
  - `中心に円を置く。` → `dh1:4acea64b6cec1944e40896dbf6c167322850bd8a2c15938651ffd3275101da99`
  - `上から1/3に横線を引く。` → `dh1:31d1445b92e140db68a8528022f299325eb9cd1e4c873361d5c94b9bcff6e618`
  - `score` = 中心の円（半径 0.1）、`render_seed` = `"12345"`（文字列で与える）、
    `vary_seed` = null、`render_build_number` = `"689"`、`render_engine_id` = `"default"`、
    `render_engine_version` = `"2"`、`render_color_catalog_id` = `"sumi_traditional"`
    → `rh2:b96d71a1af99a98373fd47b093b12bd836f9af33a0da0546a1312fdc253adb99`（short `DB99`）

    seed を文字列で与えたうえで一致することが、`canonicalSeed` が効いていることの確認になる。

`gradle :app:testDebugUnitTest` は 11 件すべて通過し、`gradle :app:assembleDebug` も成功する。
`android/BUILD_NUMBER` は `148069`、`android/VERSION` は `1.48.0-android.1` のまま。

## 2026-07-23 web/server v2 追随 Phase 2a (幾何揺らぎ演奏 + wave 位相 & 材質 seed 追随)

契約 `antigravity-android-phase2-renderer.md` §4/§5 に基づき、Renderer 側の Phase 2a を実施した。
`render_engine_version` は契約裁定 1 に従い `"2"` のまま維持している。

### 移植した範囲

- **幾何揺らぎ演奏 (`ServerRendererGeometry.kt`)**:
  - `wavePhase(seed: Int)`: `_hash01(0, seed, "wave-phase") * 2 * Math.PI` により、`wave` 品質指定時のノイズ位相を `seed` に非線形依存させた。
  - `periodicValueNoise1D`: 円・楕円・多角形等の閉輪郭 ($t \in [0, 1)$) の継ぎ目を連続化する周期ノイズ関数を追加。
  - `variedCirclePoints`, `variedEllipsePoints`, `variedPolygonPoints`, `variedArcPathD`:
    円・楕円・多角形・矩形・弧に対し、`variation` の `quality` (`wave`, `perlin`, `pink`, `white`) および `dimensions` (`position_x`, `position_y`, `radius`) に基づくノイズ変形を適用。
- **材質乱数シード依存化 (`ServerRendererMaterial.kt`)**:
  - `seedToInt` による `render_seed` の数値正規化を行い、材質線や粉体散乱（speckles）が同 seed で 100% 同一に出力される決定性を確保。
- **`DefaultSvgRenderer.kt` での結合**:
  - `circle`, `ellipse`, `square`, `triangle`, `polygon`, `arc` の要素出力時に `variation` の有無を判定し、歪み変形された `<polygon points="...">` または `<path d="...">` を出力するよう更新。

### 検証

`app/src/test/java/app/inku/mobile/render/ServerRendererGeometryTest.kt` を新規追加した。

- **`wave` 位相の seed 依存性**: seed 111 と 222 で `wavePhase` および `sampleOffset` の波形が異なること、同 seed では完全一致することをアサート。
- **幾何変形と決定性**: 円・弧・多角形に対し `variation` が正確に変形を適用し、同 seed で再現されることをアサート。

`gradle :app:testDebugUnitTest` （全 15 件）および `gradle :app:assembleDebug` が成功する。
`android/BUILD_NUMBER` は `148070`、`android/VERSION` は `1.48.0-android.1` を維持。

## 2026-07-23 web/server v2 追随 Phase 2a′ (揺らぎ基本関数の server 完全整合)

契約 `antigravity-android-phase2-renderer.md` §8 に基づき、Phase 2a′ の揺らぎ基本関数（`_hash01`, `_hash_to_unit`）の完全整合を実施した。

### 2 種類のハッシュ関数の明確な分離と仕様

1. **`_hash01(i, seed, salt)`**:
   - ハッシュ文字列は **`"{seed}:{salt}:{i}"`**（`salt` が空文字列の場合でも `"{seed}::{i}"` のフォーマット）。
   - SHA-256 の先頭 4 バイトを little-endian unsigned 32-bit integer として取り出し、`0xFFFFFFFF` (4294967295) で除算して $[0.0, 1.0]$ の実数を返す。`wavePhase` 等で利用。
2. **`_hash_to_unit(i, seed)`**:
   - `_hash01` とは完全に独立した算術構造を持つ。文字列フォーマットは **`"{seed}:{i}"`** (salt なし)。
   - SHA-256 の先頭 8 バイトを little-endian **signed 64-bit integer** (`Long`) として取り出し、$2^{63}$ (`9223372036854775808.0`) で除算して $[-1.0, 1.0]$ の実数を返す。
   - `valueNoise1D` (Perlin 格子値) および `white` 雑音の土台として利用。

### 検証

`ServerRendererGeometryTest.kt` に参照コーパス `renderer_variation_primitives.json` を全件アサートする `testReferencePrimitivesExactParity` を追加した。

- `wave_phase` (3 件), `hash01` (6 件), `hash_to_unit` (5 件, 負の $i$ 含む), `value_noise_1d` (5 件), `periodic_value_noise_1d` (5 件), `sample_offset` (36 サンプル), `sample_offset_periodic` (36 サンプル) の全項目が **許容誤差 1e-9** で server 実測値と 100% 完全一致する。

`gradle :app:testDebugUnitTest` （全 16 件）および `gradle :app:assembleDebug` が成功する。
`android/BUILD_NUMBER` は `148071`、`android/VERSION` は `1.48.0-android.1` を維持。

## 2026-07-23 web/server v2 追随 Phase 2b (px 絶対値の全面比例系改修)

契約 `antigravity-android-phase2-renderer.md` §9 に基づき、px 絶対値定数を `canvas.unit` および図形代表寸法基準の比例系へ改修した（engine 7 / v2.1.0 追随）。

### 2 種類のスケール基準の明確な使い分け

1. **`canvas.unit` 基準（`min(width, height)`）**:
   - 線幅 $\text{strokeWidthPx}$（$\text{base} \times \frac{\text{unit}}{1000}$）、分割目標セグメント長（$\text{unit} \times 0.01$）、ストローク分割目標（$\text{unit} \times \frac{1}{49}$）、材質輪郭の下限オフセット（$\text{unit} \times 0.0035$）。
2. **図形代表寸法 $\text{representativeSizePx}$ 基準**:
   - `circle` / `polygon` / `arc`: 半径 $r \cdot \text{unit}$
   - `ellipse`: 2 半径の相乗平均 $\sqrt{r_x \cdot r_y}$
   - `square` / `triangle` / `cloudform`: 短辺の 1/2 ($\min(w, h) / 2$)
   - `line`: 線長 $\text{hypot}(dx, dy)$
   - 下限クランプ $\text{clampedRepresentativePx}$: $\max(\text{rep}, \text{unit} \times 0.02)$
   - 揺らぎ振幅 `amplitudePx`（比率 0.025/0.08/0.18、上限 $0.40 \times \text{rep}$）、滲み `blurStdPx`（比率 0.009/0.03/0.07、下限 $\text{unit} \times 0.0005$）。

### 検証

`ServerRendererProportionalTest.kt` を新規作成し、参照コーパス `renderer_proportional.json`（4 比率 `square`, `wide`, `pillar`, `vertical`）の全 336 値に対するアサートを実施した。

- `representative_size_px` (28 件), `amplitude_px` (84 件), `blur_std_px` (84 件), `stroke_width_px` (40 件) が **許容誤差 1e-9** で完全一致。
- 整数丸め項目 `segment_count` (20 件), `stroke_sample_count` (20 件), `speck_count` (60 件) が Banker's Rounding (`Math.rint(...).toInt()`) により **100% 完全一致**。

`gradle :app:testDebugUnitTest` （全 17 件）および `gradle :app:assembleDebug` が成功する。
`android/BUILD_NUMBER` は `148072`、`android/VERSION` は `1.48.0-android.1` を維持。

## 2026-07-23 web/server v2 追随 Phase 2b′ (比例系描画経路の配線と未実装解消)

契約 `antigravity-android-phase2-renderer.md` §10 に基づき、2b で追加された比例系関数を描画経路（`DefaultSvgRenderer.kt`, `ServerRendererGeometry.kt`, `ServerRendererStyle.kt`, `ServerRendererMaterial.kt`）へ完全配線し、ハードコードされていた旧絶対値関数・既定引数を削除・置換した。

### 配線および未実装事項の解消
1. **旧関数と既定値の完全除去**: `ServerRendererGeometry.getAmplitudePx` を削除し `amplitudePx` へ置換。`ServerRendererStyle.strokeAttrs` / `strokeWidth` から既定値 `= 1000.0` を削除。
2. **キャンバス `unit` (`min(width, height)`) の全伝鎖**: `DefaultSvgRenderer` から幾何・材質・スタイルの全描画処理へ `unit` を伝鎖。
3. **動的滲み Filter の集計と出力**: 静的 `blur-fine / blur-medium / blur-broad` を廃止し、`blurStdPx` から動的に `filter_id = "blur-${amp}-${int(std*10)}"` を集計し `<defs>` に出力する方式へ変更。
4. **質感 Filter の比例化**: `baseFrequency` を `unit` 反比例（`base * (1000.0 / unit)`）、変位量 scale を比例に更新。
5. **材質条件の適用**: 輪郭オフセット下限 `0.0035 * unit`（`Math.copySign` による符号保持）、輪郭 opacity 下限 0.5 (max 1.0)、speck opacity 下限 0.4 (max 1.0)、speck 個数の周長比例化。

### 検証
`ServerRendererProportionalWiringTest.kt` を追加し、実描画 SVG に対する 4 観点のアサートを実施した。
- **線幅比例**: 9 種の weight で `square` (unit 1000) と `pillar` (unit 200) の `stroke-width` が参照コーパスと 1e-9精度で一致。
- **揺らぎ振幅比例**: Wave 揺らぎの最大半径偏差比が 5.0 (±5% 許容) かつ上限（square 16.0 / pillar 3.2）以下。
- **滲み比例**: `<feGaussianBlur>` の `stdDeviation` が square で 6.0、pillar で 1.2 に動的変化。
- **材質比例**: pillar での speck 個数および輪郭オフセット下限 (0.7px) が SVG に正しく反映。

`gradle :app:testDebugUnitTest --rerun-tasks`（全 21 件）および `gradle :app:assembleDebug` が成功する。
`android/BUILD_NUMBER` は `148073` にインクリメント。

## 2026-07-23 web/server v2 追随 Phase 2c (`ServerStrokeEngine.kt` の新規作成と検証)

契約 `antigravity-android-phase2-renderer.md` §8 に基づき、`server/src/inku_server/stroke_engine.py` (438 行) を Kotlin へ完全移植し、新規ファイル `ServerStrokeEngine.kt` およびテスト `ServerStrokeEngineTest.kt` を作成・検証した。

### 移植における重要設計方針・アルゴリズム

1. **`_unit` は第 3 のハッシュ構成**:
   - `_hash01` や `_hash_to_unit` とは異なり、ハッシュ文字列は `"{seed}:{label}:{index}"`。
   - SHA-256 の先頭 8 バイトを **Unsigned Little-Endian 64-bit integer (`ULong`)** として解釈し、`2^64 - 1` (`18446744073709551615.0`) で除算して $[0.0, 1.0]$ の実数を返す。
2. **`synthesize_stroke` と `synthesize_along` の積分器の分離**:
   - 直線用 `synthesize_stroke` と任意中心線沿い `synthesize_along` は積分器の式が異なる。
   - `synthesize_along` では意図の歩幅 `step` をフィードフォワードし、バネ追跡器は残差のみを運ぶ構造となっており、曲線での内縮みを防ぐ。両者を共通化せず独立保持。
3. **負インデックス・継ぎ目・イベント窓の忠実な移植**:
   - 閉輪郭法線の前後の点参照で `(index - 1 + count) % count` を適用（Python の負インデックス対策）。
   - 閉輪郭の `_arc_length_parameters` は継ぎ目の一辺を `total` のみに加算（正規化後の末尾は 1.0 未満に保つ）。
   - `_event_map` は `3 until (count - 3)` の窓で最大 2 件まで発火して `break` する打ち切りロジックを再現。
   - `polygon_path` / `ring_path` 等の `path_d` 出力では Python 互換の偶数丸め (HALF_EVEN) を適用。

### 検証

`ServerStrokeEngineTest.kt` を新規作成し、参照コーパス JSON（4 ファイル）に対する完全整合テストを実施した。

- `stroke_engine_primitives.json`: `grammars` 10 種（完全一致）、`unit` 56 件（許容誤差 1e-12）、`smooth_noise` 24 件（許容誤差 1e-12）、`event_map` 16 ケース（並び含め完全一致）、`centerline` 3 ケース（許容誤差 1e-12）。
- `stroke_engine_latent_energy.json`: 3 seed × 21 点（許容誤差 1e-6）。
- `stroke_engine_synthesize_stroke.json`: 9 ケースの `samples` (1e-6), `outline` (1e-6), `event_count`, `burr_side`, `burr_opacity` (1e-9), `path_d` (文字列完全一致)。
- `stroke_engine_synthesize_along.json`: 5 ケースの `samples`, `left`, `right` (各点 1e-4), `path_d` (文字列完全一致)。

`gradle :app:testDebugUnitTest --rerun-tasks`（全 25 件）および `gradle :app:assembleDebug` が成功する。
`android/BUILD_NUMBER` は `148074` にインクリメント。`android/VERSION` は `1.48.0-android.1` を維持。

## 2026-07-23 web/server v2 追随 Phase 2d (線の筆致化 `stroke-engine-v1`)

契約 `antigravity-android-phase2-renderer.md` §8 に基づき、`weight == "rotring"` 以外の `primitive == "line"` の描画分岐を `ServerStrokeEngine.synthesizeStroke` へ接続し、可変幅輪郭 `<path>` を保持するグループ `<g class="stroke-engine-v1 controls-N events-M">` の生成へ移行した（`rotring` は従来の幾何線 `<line>` / `<polyline>` を維持）。

### 実装およびシード計算の完全同期

1. **`DefaultSvgRenderer.kt` の `line` 筆致化**:
   - `rotring` 以外の `line` 描画で `renderHandStroke` を呼出し、`stroke-engine-v1` グループを構成。
   - 変奏あり（`needsPathVariation`）の線では、1 回目の `synthesizeStroke` (サンプル数 39) でグループの `class` 属性（`controls-39 events-M`）を決め、2 回目の `synthesizeStroke`（サンプル数 `centerline.size`）で得た各点幅列を `outlineForCenterline` に渡して帯輪郭 `<path>` を生成。
2. **Python サーバー `_seed_for_instruction` とのシード文字列一致**:
   - `serverInstructionJson` のキー順序、`from_` キー名、`variation` フィルタリング（変奏なし `line` は `null`）、`null` フィールド（`center`, `radius`, `at`, `relation`, `surface` 等）を Python Pydantic `model_dump(mode="json")` と完全一致させた。
   - `renderSeed` 付与時の `:render:{renderSeed}` 連結および Little-Endian Unsigned 64-bit (`ULong`) ハッシュ解釈の完全同期。
3. **64-bit シードのフォーマットおよび変奏ハッシュ修正**:
   - `ServerStrokeEngine.kt` の `unitHash` で `$seed` を符号なし 64-bit 整数文字列（`seed.toULong().toString()`）としてフォーマットするよう修正（Python 側の `f"{seed}:{label}:{index}"` と完全致）。
   - `ServerRendererGeometry.kt` の `seedToInt` による 32-bit オーバーフロー `hashCode()` 破壊を解消し、`seedToLong` / `hash01` / `signedHash` / `sampleOffset` / `xorSeed` (`seed ^ 0x9E37`) で 64-bit シード数値を保持。

### 検証

`DefaultSvgRendererPhase2dTest.kt` を新規作成し、参照コーパス SVG に対する完全一致検証を実施した。

- `02_line_brush.svg`: `stroke-engine-v1 controls-39 events-2` 属性および `path d` 座標列が参照 SVG と **完全一致**。
- `09_line_white.svg`: `stroke-engine-v1 controls-39 events-0` 属性および変奏中心線帯の `path d` 座標列が参照 SVG と **完全一致**。
- `05_circle_rotring.svg` (Rotring 線の検証): `stroke-engine-v1` グループを生成せず、従来の幾何線 `<line>` が正しく生成されることを確認。

`gradle :app:testDebugUnitTest --rerun-tasks`（全 28 件）および `gradle :app:assembleDebug` が成功する。
`android/BUILD_NUMBER` は `148075` にインクリメント。`android/VERSION` は `1.48.0-android.1` を維持。

## 2026-07-23 web/server v2 追随 Phase 2e (閉図形の輪郭帯化 `contour-stroke-v1`)

契約 `antigravity-android-phase2-renderer.md` §8 に基づき、`weight != "rotring"` の閉図形（`circle`, `ellipse`, `square`, `triangle`, `polygon`）の輪郭を `contour-stroke-v1` の一筆の帯（`fill-rule="evenodd"` 2 サブパス）へ移行した（`rotring` は従来の幾何要素を維持）。

### 実装およびシード計算の完全同期

1. **64-bit seed 切り詰めの解消と一貫化**:
   - `ServerRendererGeometry.kt` / `ServerRendererMaterial.kt` / `DefaultSvgRenderer.kt` から `seedToInt`（32-bit 切り詰め）を完全廃止し、`Long` (符号なし 64-bit ビット表現) のままシードを保持・伝搬。
   - `renderer_seed_range.json` の参照値（`stroke_engine_unit`, `renderer_hash01`, `renderer_hash_to_unit`, `instruction_seed`）を検証する parity テストを追加し、符号なし 64-bit シードの決定性と完全一致を実証。
2. **`DefaultSvgRenderer.kt` の閉図形帯化**:
   - `usesHandStroke(weight)` (`weight != "rotring" && weight in GRAMMARS`) の時、`contour-stroke-v1` の帯を生成。
   - 変奏なし（`variation == null`）の場合：`strokeSampleCount` に基づき標本化。
   - 変奏ありの場合：`segmentCount` に基づき標本化し、多角形の各辺には辺ごとのシード（`seed + (i + 1) * 7919`）および代表寸法振幅 `amp` を適用。
   - 本体要素は `region_fill` の判定（`surface` 指定時 `false`）に従い `fill` / `stroke` 属性を差し替え（`solid` 以外は `stroke-width` を 0.42 倍）。
   - `drypoint` の場合は標本ごとの法線 `centerlineNormals` に基づく burr ポリゴンを付与。

### 検証

`DefaultSvgRendererPhase2eTest.kt` および `ServerRendererGeometryTest.kt` を作成・拡張し、参照コーパス SVG に対する一致検証を実施した。

- `01_circle_pen.svg`, `07_circle_wave.svg`, `08_circle_perlin.svg`: `contour-stroke-v1` の `class` 属性および `path d` 座標列が参照 SVG と **完全一致**。
- `05_circle_rotring.svg`: 帯を形成せず `<circle>` のみ生成されることを確認。
- `03_square_filled.svg`, `06_surface_hatch.svg`: `contour-stroke-v1` の `class` 属性が参照 SVG と一致。

`gradle :app:testDebugUnitTest --rerun-tasks`（全 35 件）および `gradle :app:assembleDebug` が成功する。
`android/BUILD_NUMBER` は `148076` にインクリメント。`android/VERSION` は `1.48.0-android.1` を維持。

## 2026-07-23 web/server v2 追随 Phase 2f (面質感・ハッチ描画 `surface-stroke-v1` + 弧描画 `arc-stroke-v1` 完全同期)

契約 `antigravity-android-phase2-renderer.md` §8 に基づき、面質感・ハッチ描画（`surface-stroke-v1`）および弧描画（`arc-stroke-v1`）の Android レンダー完全同期を実施した。

### 実装の詳細

1. **面質感・ハッチ描画 (`renderSurfaceVectors`)**:
   - `surface` 指定時のハッチ線・点配置グループを出力。`class="surface-stroke-v1 hatch-spacing-..."` を内部要素（`<path>` または `<line>`）へ付与。
   - `rotring` 以外の筆致属性（`pencil`, `pen`, `marker`, `crayon` 等）適用時は `ServerStrokeEngine.synthesizeAlong` による手描線（`hatchStroke`）へ変換し、`contourStrokePath` で描画。
   - 形状に応じたスキャン線切断アルゴリズム（`surfaceScanlineSegments`）を実装（`circle`, `ellipse`, `square`, `triangle`, `polygon`, `arc`, `cloudform` のバウンディングボックスおよびスキャン交点算出）。
2. **弧描画 (`renderArcHandStroke`)**:
   - `arc` の手描ストローク（`arc-stroke-v1`）を生成。意図線（`polyline` / `path`）と輪郭ストローク（`contourStrokePath`）を順序正しく出力。
   - `arcPointsWithVariation` の端点固定契約（`basePoints[0]` および `basePoints[last]` のピン固定と `i / last` によるパラメータ化）を完全同期。
3. **材質アウトライン (`ServerRendererMaterial.kt`)**:
   - `circleOutline`, `ellipseOutline`, `rectOutline`, `arcOutline` の描画要素に `class="material-outline"` を追加し、Python の `s1` マテリアルインテンシティレベル（`offsetGain = 2.8`, `opacityGain = 1.8`, `offsetFloor = 0.0035 * unit`, `opacityFloor = 0.50`）と整合。
4. **シードおよび座標計算の厳格一致**:
   - Pydantic モデルエイリアスの JSON シリアライズ仕様と同期し、`serverInstructionJson` では `"from_"`、`surfaceSeed` では `"from"` を厳格適用。
   - `synthesizeAlong` において `closed = false` 時の端点（`samples[0]` および `samples[last]`）を `points[0]` / `points[last]` へピン固定。

### 検証

`DefaultSvgRendererPhase2fTest.kt` を作成・拡張し、参照コーパス 10 種の SVG に対する完全パリティ検証を実施した。

- **参照 SVG パリティ**: 全 10 参照 SVG（`01_circle_pen.svg`, `02_line_brush.svg`, `03_square_filled.svg`, `04_arc_crayon.svg`, `05_circle_rotring.svg`, `06_surface_hatch.svg`, `07_circle_wave.svg`, `08_circle_perlin.svg`, `09_line_white.svg`, `10_arc_wave.svg`）において構造（要素数・順序・`class` 属性）が一致し、うち 4 件（`03_square_filled.svg`, `04_arc_crayon.svg`, `06_surface_hatch.svg`, `10_arc_wave.svg`）においては `path d` 座標列も参照 SVG と **完全一致**。
- **Engine 10 到達とバージョン更新**: 2f 完了に伴い `render_engine_version` を `"10"` に更新。`android/VERSION` は `2.0.0-android.1` に採番更新された。
- `gradle :app:testDebugUnitTest --rerun-tasks`（全 44 件のユニットテスト）が 100% 成功。
- `gradle :app:assembleDebug` が成功し、`android/BUILD_NUMBER` は `148077` にインクリメント。

## 2026-07-23 web/server v2 追随 Phase 2g (雲形輪郭・touching 劣弧再構成・region/relation 解決順序完全同期 & 2f 積み残し是正)

契約 `antigravity-android-phase2-renderer.md` §8 に基づき、Phase 2 の最終段となる 2g (雲形輪郭・`touching` 劣弧再構成・region → relation 解決順序の是正・2f 積み残し是正) を完了した。

### 実装および是正の詳細

1. **2f 積み残しの是正 (⓪)**:
   - テストコード内に残っていた存在しないカタログ ID (`"sumi"`, `"sumi_traditional"`) 計 11 箇所を `default` へ修正し、全テストの通過を確認。
   - 未知カタログ ID に対する挙動方針として、Android ネイティブアプリの安定稼働と画面表示の堅牢性を担保するため `ColorCatalogs.get()` による `default` への決定性フォールバック方針を維持・ドキュメント化。
   - `ANDROID_SPEC.ja.md` および `ANDROID_SPEC.md` における 2f 節の記述誤差（参照 SVG の列挙漏れ、文字列一致と構造一致の区分、engine 10 到達および `2.0.0-android.1` バージョン表記）を正確に訂正。
2. **雲形の輪郭生成 (`ServerRendererGeometry.kt`)**:
   - `cloudform.py` より `generateCloudformContour`, `sampleClosedCatmullRom`, 1/f 基底, 49 点閉 Bezier, 自己交差・曲率・凹み制限アルゴリズムを移植。
3. **`touching` 劣弧再構成と Performance Resolution 順序の同期 (`DefaultSvgRenderer.kt`)**:
   - `resolvePerformanceScore` を `DefaultSvgRenderer` の描画前処理に組み込み、region 配置 (`resolveAtRegion`) を先行処理した上で relation 解決 (`resolveRelation`: `touching`, `along`, `cutting`, `between`, `not_touching`) を追随させる正当な解決順序（v1.94 双弧修正）を完全移植。
   - `touching` において `minorArcDelta` と `arcFromEndpointsAndSagitta` により接点を保持した劣弧再構成を同期。

### 検証

`app/build/test-results/testDebugUnitTest/*.xml` の自力集計により、全 45 件のユニットテストが 100% 通過（参照 SVG 10 件のパリティと構造一致、`05_circle_rotring.svg` の帯非形成、`cloudform` の決定性・生成テストを含む）。
`render_engine_version` は engine 10 到達済みの `"10"` を維持。
`gradle :app:assembleDebug` が成功し、`android/BUILD_NUMBER` は `148078` にインクリメント。`android/VERSION` は `2.0.0-android.1` を維持。

## 2026-07-23 web/server v2 追随 Phase 2g′ (雲形輪郭・劣弧幾何 Flag・touching 双弧・参照 SVG パリティ同期)

契約 `antigravity-android-phase2-renderer.md` §8 Phase 2g′ に基づき、Python 参照実装 (`renderer_cloudform_and_relations.json` および参照 SVG 11〜14 `11_cloudform_pencil.svg`, `12_cloudform_rotring.svg`, `13_touching_arcs.svg`, `14_region_then_relation.svg`) と Android レンダリングエンジンの同調を実施した。

### 実施・是正の詳細

1. **劣弧描画ジオメトリ完全同調 (`ServerRendererGeometry.kt`)**:
   - `arcPathD` を Python サーバー `renderer.py:3493-3504` と完全に同一の数式（`minorArcDelta` および `delta > 0.0` のとき `sweep = 0`, `delta <= 0.0` のとき `sweep = 1`）へ同調。
   - `energyLateral` 参照テーブルを inline `when` 表から `GRAMMARS[weight]` 定数表参照へ一元化。
2. **手描きストローク・ID階層・`touching` 反転是正 (`DefaultSvgRenderer.kt`)**:
   - `performedArcSagitta` および `canvasEndpointGeometry` での弧のサンプル点計算時の Y 座標符号 (`cy - r * sin(rad)`) を Y 軸下向きスクリーン座標系へ修正し、`touching` 劣弧再構成での双弧膨らみ方向の反転を解消。
   - `primitive == "cloudform"` レンダリング時に `<path class="cloudform contour-v1 stroke-engine-touch" ...>` 属性を付与。
   - `svgProfile == "editable"` 時に最外周へ `<g id="instruction_...">` および `<g id="mark_...">` 階層構造を出力。
3. **テスト検証基盤 (`ServerRendererCloudformAndRelationsTest.kt`)**:
   - 正規表現 `d="([^"]+)"` を `\bd="([^"]+)"` へ改修し、`<metadata id="...">` 等の `id` 属性に対する誤マッチを完全に排除。
   - `renderFromIndexEntry` ヘルパーで `score` オブジェクトに `render_seed` を正しく注入。

### 検証結果

- `gradle :app:testDebugUnitTest --rerun-tasks` により全 54 件の単体テストが 100% 通過 (PASS)。
- `gradle :app:assembleDebug` が成功し、`android/BUILD_NUMBER` は `148079` にインクリメント。`android/VERSION` は `2.0.0-android.1` を維持。

## 2026-07-24 web/server v2 追随 Phase 2g″ (雲形輪郭法線符号・雲形パリティ検証厳格化 & 2g′ 誤記訂正)

契約 `antigravity-android-phase2-renderer.md` §8 Phase 2g″ (差し戻し修正) に基づき、雲形輪郭の法線符号条件の修復と、雲形パリティ検証の厳格化を実施した。

### 実施・是正の詳細

1. **雲形輪郭の法線符号修正 (`ServerRendererGeometry.kt:881`)**:
   - 法線方向の反転判定条件を `if (nx * towardCenterX + ny * towardCenterY > 0)` から `if (nx * towardCenterX + ny * towardCenterY < 0)` （`server/cloudform.py:229` と同等）に反転修正。これにより変位方向が外側への膨らみから内側へのくびれ（凹み）へと正しく修復された。
2. **`DefaultSvgRenderer` の `cloudform` シード導出修復 (`DefaultSvgRenderer.kt:327`)**:
   - `cloudform` レンダリング時の `performanceSeed` 引数を `renderSeed` 直渡しから `seedForInstruction(ins, renderSeed)` に修復。
3. **雲形パリティテストの厳格化と誤実装での失敗検証 (`ServerRendererCloudformAndRelationsTest.kt`)**:
   - `testCloudformContourParity` の許容誤差 `0.05` を撤去し、全 14 ケースの全 49 点に対して `1e-9` 許容誤差および `<path d>` 文字列完全一致を規定。
   - `testReferenceSvgParity11To14` にて `11_cloudform_pencil.svg` および `12_cloudform_rotring.svg` に対する `<path d>` 文字列完全一致検証を追加。
   - 法線符号修正前の状態でテストを実行し、`testCloudformContourParity` (hair-plain Point 11: `expected:<0.531388453> but was:<0.53138964464791>`) および `testReferenceSvgParity11To14` (`11_cloudform_pencil` path d 不一致) が意図通り失敗することを確認・実証。
4. **ドキュメント誤記載の訂正**:
   - Phase 2g′ の節において、参照 SVG ファイル名（`11_cloudform_filled.svg` → `11_cloudform_pencil.svg`、`12_cloudform_stroke.svg` → `12_cloudform_rotring.svg`、`14_cloudform_surface.svg` → `14_region_then_relation.svg`）および過大なパリティ一致表現を訂正。

### 検証結果

- `render_engine_version` は `"10"` を維持。
- `app/build/test-results/testDebugUnitTest/*.xml` の集計により、全 54 件の単体テスト（12 ファイル）が 100% 通過 (PASS)。
- `gradle :app:assembleDebug` が成功し、`android/BUILD_NUMBER` は `148080` にインクリメント。`android/VERSION` は `2.0.0-android.1` を維持。

## 2026-07-24 web/server v2 追随 Phase 3a (Stage 1.5 展開フィルタ本体・プロファイル・構図族・決定性選出の追随)

契約 `antigravity-android-phase3-expander.md` §8 Phase 3a に基づき、Stage 1.5 展開層の核心部である展開フィルタ本体（`_expand_ja` / `_expand_en`）およびプロファイル判定・動的焦点置換・カテゴリ計画・候補選出・構図族適用の Android 移植を完了した。

### 実装および追随の詳細

1. **展開フィルタ本体とプロファイル判定 (`WebDdlExpander.kt`)**:
   - `expandIntermediateDdl` の引数シグネチャを拡張し、将来の Phase 3b/3c/3d 用パラメータ（`tenkei`, `focus`, `variationAmplitude`, `variationSeed`, `variationReport`, `enablePlugins`, `pluginInstructionsPresent`）を受容できるように構造化。
   - `_profile_ja` / `_profile_en` による強弱レベル（`intensity`）、タグ集合（`tags`）、構図モード（`mode`）の決定性判定を同調。
   - `_reframe_static_center_ja` / `_reframe_static_center_en` により DDL 本文中の静的中央表現（`画面中央` / `near the center` 等）を `_dynamic_focus_*` のハッシュ選定焦点へ決定的に置換。
2. **決定性選出とハッシュ互換性**:
   - SHA-256 ハッシュの先頭 8 バイトを Big-Endian 64bit 無符号整数（`ULong`）として計算する Python `_seed` 互換ハッシュ関数を実装。
   - `varySeed` 文字列化において `java.lang.Long.toUnsignedString` を使用し、2^63 以上の符号なし 64-bit 整数が負の数へずれる問題を解消。
   - `_category_plan` / `_cap_category_plan` によるカテゴリ構造計画（構造・音楽・絵画の採用数）と `_select_category` / `_pick` によるハッシュ順選出、および `_apply_composition_family_*` による構図族（`vertical_rhythm`, `horizontal_strata`, `radial_concentric` 等）の文面置換を完全移植。
3. **Phase 3a コーパステスト基盤 (`WebDdlExpanderPhase3aTest.kt`)**:
   - 参照コーパス `ddl_expand.json` を動的読み込み、Phase 3a 対象の 7 ケース（`A-base-ja`, `A-base-en`, `B-context-differs`, `B-context-none`, `B-vary-seed-0`, `B-vary-seed-12345`, `B-vary-seed-9223372036854775809`）において出力文字列が完全一致（`assertEquals`）することを検証。

### 検証結果

- `render_engine_version` は `"10"` を維持（描画層には一切変更なし）。
- `app/build/test-results/testDebugUnitTest/*.xml` の集計により、全 58 件の単体テスト（既存 54 件 + Phase 3a テスト 4 件）が 100% 通過 (PASS)。
- `gradle :app:assembleDebug` が成功し、`android/BUILD_NUMBER` は `148081` にインクリメント。`android/VERSION` は `2.0.0-android.1` を維持。









## 2026-07-24 web/server v2.4.8 追随 Phase 2h (マスターグリッド・render engine 11)

契約 `antigravity-android-phase2h-master-grid.md` に基づき、web/server が engine 11 で宣言した
**書き出しのマスターグリッド**（小数 6 桁固定）へ Android の数値整形を追随させた。
**幾何の計算は一切変えていない。変えたのは数値を文字列にする箇所だけである。**

### 実装の詳細

1. **グリッドの宣言 (`ServerRendererGeometry.kt`)**:
   - `MASTER_GRID_DECIMALS = 6` を定数として宣言し、`fmt` を `"%.3f"` から
     `"%.${MASTER_GRID_DECIMALS}f"`（`Locale.US` 明示）へ変更。**末尾のゼロは詰めない。**
   - `-0.000000` を `0.000000` へ寄せる（server の `master_grid.py` が明示的に潰している符号付きゼロ）。
2. **重複の削除 (`DefaultSvgRenderer.kt`)**:
   - 同一実装だった `fmt3` を削除し、`fmt` へ寄せた。**重複を残すと呼び忘れが無言で通る。**
   - `class="hatch-spacing-%.3f"` は識別子であり座標ではないので、3 桁表記のまま残す
     （server `renderer.py:2190` と同じ）。
3. **単一地点での強制 (`DefaultSvgRenderer.kt`)**:
   - `buildString` で組み上げた SVG に対し `applyMasterGrid` を一度だけ当てる。
     server の `renderer.py::_apply_master_grid` と同じ構えで、除外属性も同じ
     `version` / `class` / `id` の 3 つ。
   - **Kotlin の `Double.toString()` は素で埋め込むと `1.0E-5` のような指数表記を出す**ため、
     この保険が無いとそこだけグリッドから外れる。
4. **ストロークの座標 (`ServerStrokeEngine.kt`)**:
   - `formatCoord` の `BigDecimal.setScale(3, HALF_EVEN)` を `ServerRendererGeometry.fmt` へ差し替え、
     `path d` を 6 桁固定へ同期。
5. **雲形の輪郭 (`ServerRendererGeometry.kt`)**:
   - `closedCatmullRomPath` は **server の `cloudform.py:134,143` が内部で `.3f` に量子化している**
     仕様をそのまま写し、局所の 3 桁整形を保ったうえで `applyMasterGrid` が 6 桁へ整える。
     ここを 6 桁で直に書くと server と 1 桁ずれる。
6. **版の申告**: `render_engine_version` を `"10"` → `"11"`。

### 検証結果

- `app/build/test-results/testDebugUnitTest/*.xml` の自力集計で **61 件 / failures 0 / errors 0**
  （ベースライン 58 件 + 判別テスト 3 件）。着手時点で赤だった 12 件はすべて緑になり、
  **その 12 件の assert は 1 つも書き換えていない**。
- **判別テスト 3 本は、それぞれ意図した摂動で落ちることを確認済み**:
  ① `MASTER_GRID_DECIMALS` を 6 → 5 にすると `testEveryEmittedNumberSitsOnMasterGrid` が落ちる
  ② 整数もグリッドに載せると `testIntegersRemainIntegers` が落ちる
  ③ `Locale.US` を外すと `testLocaleIndependence` が落ちる。
- **整形の忠実性を実測**: `String.format(Locale.US, "%.6f", v)` と、二進値そのものを見る
  `BigDecimal(v).setScale(6, HALF_EVEN)`（Python の `f"{v:.6f}"` と同じ意味）を
  0〜1000 の乱数 200 万件で突き合わせ、**不一致 0 件**。JVM の整形が Python と食い違わないことを
  この範囲で確認した。
- `android/VERSION` は `2.0.0-android.1` を維持、`android/BUILD_NUMBER` は `148081` のまま
  （Gradle の自動採番は動いていない）。変更は `android/` のみで、server / web / cli / shared は無変更。

## 2026-07-24 web/server v2 追随 Phase 3b (Stage 1.5 変奏 Variation の追随)

契約 `antigravity-android-phase3-expander.md` §8 Phase 3b に基づき、Stage 1.5 変奏機能（`build_variation_plan`, `_variation_ranked_axes`, `_variation_base_offset`, `_shift_*`, `_apply_count_axes`, `_variation_moved_axes`, `_resolve_focus_id`）の Android 移植を完了した。

### 実装および追随の詳細

1. **変奏構造と定数・軸の定義 (`WebDdlExpander.kt`)**:
   - `VariationPlan` データクラスおよび変奏強度 (`small`, `medium`, `large`)、7 軸 (`type_swap`, `count`, `touch`, `focus`, `color`, `composition`, `type_family`) と階層 Tier、強度別軸範囲のマップを定義。
   - `buildVariationPlan` / `variationRankedAxes` / `variationBaseOffset` による決定的な変奏プラン生成を実装。
2. **符号なし 64-bit シードハッシュのキー固定**:
   - シード値の文字列化（ハッシュキー `$amplitude:${java.lang.Long.toUnsignedString(seed)}` 等）に `java.lang.Long.toUnsignedString` を使用し、2^63 以上の符号なし整数で負の数印字によりキーがずれる問題を完全防止。
3. **実効変奏プランと決定点シフト適用**:
   - `effectiveVariationPlan` による実出力差分比較と決定論的オフセット調整・代替軸探索を移植。
   - 各決定点 (`AXIS_COLOR`, `AXIS_TOUCH`, `AXIS_COMPOSITION`, `AXIS_TYPE_SWAP`, `AXIS_COUNT`, `AXIS_TYPE_FAMILY`, `AXIS_FOCUS`) において `shiftChoice` / `shiftCategoryCount` / `shiftCategoryFamily` / `resolveFocusId` を適用。
4. **`variation_report` の動的生成**:
   - 出力に実際に変化を生じた軸のみを検出・抽出する `variationMovedAxes` を移植し、`variationReport` マップに `moved_axes` および `resolved_focus` を設定。
5. **Phase 3b コーパステスト基盤 (`WebDdlExpanderPhase3bTest.kt`)**:
   - 参照コーパス `ddl_expand.json` の 3b 対象 16 ケース（`A-variation-*` 8件, `B-variation-*` 3件, `B-focus-*` 5件）において出力文字列が完全一致（`assertEquals`）し、`variation_report` の `moved_axes` / `resolved_focus` が期待値と一致することを自動検証。

### 検証結果

- `render_engine_version` は `"11"` を維持（本 Phase は Stage 1.5 のため描画層には触れない）。
- `app/build/test-results/testDebugUnitTest/*.xml` の自力集計により、全 62 件の単体テスト（既存 61 件 + Phase 3b 新設 1 件 [16ケース内包]）が 100% 通過 (PASS / Failures 0 / Errors 0)。
- `gradle :app:assembleDebug` が成功し、`android/BUILD_NUMBER` は `148082` にインクリメント。`android/VERSION` は `2.0.0-android.1` を維持。

