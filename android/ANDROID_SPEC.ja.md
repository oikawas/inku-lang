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
