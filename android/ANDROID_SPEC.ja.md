# inku Android 実装メモ

このディレクトリは、ネイティブ単体 Android アプリのワークスペースであり、Git 管理対象とする。
ローカル専用成果物、端末ID、ダウンロード済みモデル、ログ、秘密情報は追跡対象に含めない。

最終更新: 2026-05-06。

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
- exported web JSON fixture に対する reference compatibility tests。

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
| `HistoryStrip.svelte` | history tab と selected render controls 経由で移植。 |
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
