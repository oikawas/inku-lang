# inku プロジェクトコンテキスト

**対象バージョン: v2.15.15 / Build 1091**

この文書は、開発者とAIが毎回 `SPEC.ja.md` 全文を読み直さずに作業を始めるための入口である。
設計判断の正本は `SPEC.ja.md` であり、この文書と食い違う場合は日本語仕様を優先する。

## 最初に読むもの

通常の作業では、次の順に必要な範囲だけ読む。

1. `AGENTS.md` がローカルに存在する場合は、開発・検証・デプロイ規則を確認する。
2. 本書で目的、構造、現在の契約を確認する。
3. `git status --short --branch` と直近の履歴で作業状態を確認する。
4. 変更対象に関係する `SPEC.ja.md` の節と実装ファイルだけを読む。
5. 歴史的経緯が必要な場合だけ `CHANGELOG.ja.md` を検索する。

全文確認が適するのは、初回参加、設計思想の再検討、複数領域にまたがる大規模変更、仕様矛盾の監査である。

## プロジェクトの目的

`inku` は DDL（Drawing Description Language）の参照実装である。
DDLは一般的な描画命令ではなく、「視覚的な短歌を書く言語」を目指す。

- 記述そのものを持続する作品として扱い、SVGは一回の演奏として扱う。
- 感情的な評価語ではなく、物理素材、配置、運動、観察可能な関係を書く。
- 短さと制約によって作者の主張を削ぎ、提示を中心にする。
- 既定の処理は再現可能にし、揺らぎはRendererの演奏とユーザーの明示操作に限定する。

短い記述はtyped semantic documentとして共有の意味を保ち、lock検証済みlowererが一度だけScoreへ解決する。SVGは同じScoreからの一度の演奏である。通常のServer／Web／Androidは、必要な最小版を選ぶresource-awareなcompact Scoreのcompile／演奏入口を持つ共有authoring pipelineを使う。旧作品の閲覧と保存済みScore／SVGの再演は維持し、旧作品からの変更は元を保った新しいvariationとして保存する。詳細な契約はSPECを正とする。

## 現行アーキテクチャ

```text
記述またはdirect DDL
  -> 共有Rust authoring state machine
  -> Stage 1: 記述から正規化DDLを生成（記述起点だけ）
  -> visible DDLをauthority・revisionと原子的にCAS保存
  -> typed compiler（known holeは自動検出して補完案を要求）
  -> 作者が補完案を承認した場合だけCAS保存
  -> typed Stage 1.5 + shared lowerer
  -> 必要な最小版のcompact Score（resource-aware基準は0.10、鏡写しを持つ場合だけ0.15）
  -> resource-aware Render Engine: SVG演奏
  -> raw Score・SVG・history authority linkを保存
```

- `server/`: FastAPIバックエンド。
API、認証、DB、共有pipelineのhost adapter、描画、系譜と旧作品の互換経路を持つ。
- `web/`: SvelteKit 2 / Svelte 5フロントエンド。
- `cli/`: 公開HTTP APIだけを使う `inku-cli`。
- `android/`: Kotlin / Jetpack Composeのhostと共有Rust pipeline／renderer binding。
詳細正本は `android/ANDROID_SPEC.ja.md`。
- `SPEC.ja.md`: 設計思想と現行契約の日本語正本。
- `SPEC.md`: 英語公開仕様。
- `CHANGELOG.ja.md` / `CHANGELOG.md`: 実装・設計変更の履歴。

### 共有Typed DDL基盤とcompact演奏core

共有Rust compilerは、日英の正規化DDLをtyped semantic documentとして解釈し、source provenance、canonical meaning、Macroの有限展開を保持する。compiler lockはsourceとprovenanceを照合し、lock検証済みmeaningだけが共通lowererへ進む。lowererは一度だけactual Scoreまたは反復のsymbolic Planへ解決し、recoverableな不成立はtyped diagnosticと局所省略で扱い、独立した描画を続ける。詳細な型、lock、recovery、geometry、relation、Macroの契約は[SPEC.ja.md](SPEC.ja.md)を正とする。

現在のlowererは背景の有限構文とsource優先のbackground、line / arcの`引く`、位置省略（sourceではNone、演奏時は中央領域から選ぶ）、明示位置、既存のsurface / Ground、有限のgeometryとrelationを共有してScoreへ届ける。新作品は表現に必要な最小Score版を選び、resource-awareなcompact wireは0.10を基準とする。source owner、namespaceごとのordinal、placement／repetition／fill group、fill targetと境界、Macroの内外の反復をrecipeとして保存する。演奏時にrecipeからsamplingし、個体座標を保存しない。解決済みの個数・図形を正確に保ち、資源超過は個体生成前に当該sourceまたはcoordinated placement全体を診断付きで省略して、独立した後続を続ける。旧Score 0.9は旧作品の互換読取用に維持する。

`compile_ddl_to_score_with_resources`と`render_with_resources`が共通coreの入口であり、通常Webと既存のinterpret／compose／paint APIも同じpipeline serviceを使う。Provider transportはcoreが要求したactionごとに一度だけ呼び、再試行判断をcoreに残す。CanvasのIDと整数比は共有coreの11形式を正本とする。新しい6資源上限はlogical objects 4096、template nodes 128、anchor instances 4096、transform instances 4096、placement instances 64、fill instances 64である。既存4上限、管理者のauthority、旧作品に保存済みのbudgetを維持し、超過した配置だけを省略して後続を続ける。

通常WebとAPIは共有Rustのauthoring serviceを使う。系譜編集は選択したhistoryのownerと保存contextを引き継ぎ、元作品を保持する。Active DDLのsource変更はCASとauthority lockを保ち、設定変更は親関係を持つ新しいvariationへ進む。履歴は当該revisionの診断を復元し、古い形式や壊れたsidecarでも保存DDL／Score／SVGの表示を継続する。実装の時系列は[CHANGELOG.ja.md](CHANGELOG.ja.md)、現在の契約はSPECを参照する。

## 守るべき設計契約

- DDLテキストは母語で書ける。
JSON Scoreのキーは英語で統一する。
- 記述起点のStage 1はvisible normalized DDLだけを生成し、Scoreの意味を決めない。
- 共有compiler／lowererは可視DDLと検証済みmeaningを正とし、typed Stage 1.5は入力の意味を上書きしない。
- 旧Stage 2／coerceは互換経路としてのみ残し、新作品のsemantic authorityにしない。
局所回復は新しい様式を注入せず、最小のfieldまたは実行単位を診断付きで省略する。
- 同一Scoreと同一seedは同じ作品を再現する。
暗黙の時刻seedや自動varyを導入しない。
- 描き直しは、その作品が描かれた上限で走る。
上限の記録を持たない作品でだけ今日の設定を使い、応答はどちらで描いたかを名乗る。
注文書は上限を下げられるが上げられない。
上限は管理者のものであって、注文する側が外せるものではない。
- 上げた上限は紙まで届く。
出荷時の数字を直に書いた場所を残さず、帯も群の数の上端も設定に対する比で持つ。
届かない上限は、管理者に見えないもう一つの上限である。
- 上限の数字は、それが何メガバイトかを名乗る。
数えているのは墨の本数で、閲覧者に届くのはファイルだからである。
換算はサーバーが測った 1 本あたりのバイトから引き、ブラウザに写しを持たない。
- `dh1`（記述同一性）、`rh3`（作品エディション。
旧 `rh2` は legacy として保持）、履歴ID、系譜node IDを混同しない。
- 系譜は明示された派生操作だけを記録し、類似度、時刻、hash一致から親子関係を推測しない。
- 品質指標、類似度、Vision所見は監査の鏡であり、生成ゲートや「最良枝」の自動選択に接続しない。
- 言語上のmacroはdomain別codeや個別文法を足さず、一つの汎用`MacroDefinition`形式で
  記述する。保存済みMacro定義と旧作品のScore／SVGは互換性を保ち、新作の意味は共有compilerが決定する。
- 語彙の正本は共有Rustの`core/crates/inku-ddl/assets/saijiki-v1.json`である。共有Stage 1 promptはそのprojectionを使い、Serverの表示表・Web／Android歳時記・referenceも同じ語彙へ揃える。
- 日本語と英語の挙動を揃え、英語だけの要件を追加しない。
- **エンジンは後戻りしない**（SPEC.ja §15.8）。
過去の描画エンジンをシステムとして保持せず、版を選び直す機構も作らない。
Replay は常に最新で行い、当時のエディションの再現は**保存済み SVG の返却で担保する**。
版画と同じで、彫りは進み刷りは残るが版木は戻せない。
**だから現役のうちに参照コーパス（＝校正刷り）を取る。
**

## 現在の製品状態

**本節は「いま何が在るか」だけを現在形で書く。**
どの版で何をしたかという時系列の記録は `CHANGELOG.ja.md` が持ち、本書はそれを写さない。
なぜその形になったかを知りたいときは `CHANGELOG.ja.md` を該当語・版・Build 番号で検索する。

### 版

| 対象 | 値 | 正本 |
|---|---|---|
| アプリ | 本書冒頭の「対象バージョン」 | **`web/APP_VERSION` と `web/BUILD_NUMBER` の 2 ファイル**。UI・`/api/info` の `version`・CLI はすべてここを読む（値をここに写さない） |
| Render Engine | 66 | `core/crates/inku-render/src/lib.rs` |
| DDL | `ddl_version` 11 / `ddl_engine_version` 45 | `server/src/inku_server/layer_versions.py` |
| Android | `2.1.4-android.78` | `android/VERSION`（web / server とは別の名前空間） |
| Python パッケージ | 2.7.2 | `server/pyproject.toml`（**製品リリースのときだけ動く**） |

### 語彙

正本は `server/src/inku_server/schema.py` の Literal で、日本語の語との対応は saijiki テーブル（`saijiki.py`）が持つ。

- 図形 9 — `line` / `circle` / `ellipse` / `triangle` / `square` / `polygon` / `arc` / `point` / `cloudform`
- 線種 4 — `solid` / `dashed` / `dotted` / `dash_dot`
- 道具 11 — `silverpoint` / `pencil` / `pen` / `rotring` / `crayon` / `chalk` / `brush_thin` / `brush_thick` / `burin` / `drypoint` / `computer`
- 細さ 2 — `fine` / `extra_fine`（道具から独立した太さの軸）
- 色 9 — `white` / `black` / `blue` / `red` / `green` / `gray` / `yellow` / `orange` / `purple`
- 面の質感 9・面の向き 5・地の素材 7

saijiki テーブルは単一の情報源で、Stage 1 プロンプトの語彙ブロック・プラグインの閉包マーカー・relation の固定句・web の歳時記表示・reference §1 をそこから導出する。
語彙の変更はテーブルと golden test を経由する。
歳時記は 10 カテゴリで、`おもて`（11 語）が閉じた図形の内側の在り方を言う（ddl-engine 15）。
つらなりが線の在り方を言うのと対になる軸で、語は状態の名詞であって動作ではない。
面の指定が閉じていない命令に付いたときは、共有compiler／lowererが対応する閉図形へ届け、成立する先が無ければ診断付きで省略する。
**ただし `粒` と `にじみ` の 2 語は例外で、線や弧の上にそのまま残る**（ddl-engine 20）——
この 2 語は内側の在り方ではなく痕の走り方を言うので、線が内側の代わりに持てるものだからである。

### パイプラインの各層

- **共有authoring state machine** — 通常Server／WebとAndroidは、version付きsnapshotへcommandを適用する同じ共有Rust coreを使う。Androidの通常UIは`InkuRepository`、`AndroidWorkPipeline`、JNIを通る。Coreは次snapshot、進行event、最大1件のtyped effectを返す。
- **Host effect** — Python／Kotlin hostは、coreが要求したStage 1またはknown-hole補完のprovider呼出し、もしくはvisible DDLのCAS保存を一度だけ実行し、identityを保ったresultを返す。再試行、authority遷移、次のeffectはcoreが決め、hostは別の意味分岐を持たない。
- **Visible DDLとauthority** — 記述起点だけがStage 1を使ってvisible normalized DDLを作る。Direct DDLと作者が承認した補完patchは同じCAS保存境界へ入り、保存acknowledgment後のexact bytesだけを再parseする。Description authorityはsource bytesを変更する最初の作者確定後にDDL authorityへ単調にlockする。
- **Typed compiler／Stage 1.5／lowerer** — compiler lockでsource、provenance、Macro definitionを検証し、bounded Macro expansionとfocus-onlyのtyped Stage 1.5を経てactual Scoreまたはcompact recipeへ一度だけ下ろす。Known holeだけが補完候補となり、holeなしではStage 2 LLMを呼ばない。Recoverableな不成立は最小のfieldまたは実行単位を診断付きで省略し、独立した後続を保つ。
- **Scoreと資源** — lowererは表現に必要な最小Score版を選ぶ。Resource-awareなcompact基準は0.10で、鏡写しrelationを持つ作品だけが0.15を必要とする。保存済みpolicyから需要を再計算し、超過した一sourceまたはcoordinated placement全体を個体化前に省略する。
- **互換境界** — 旧作品は保存済みScore／SVGと保存時contextで表示・再演する。新しい作品の意味は共有Rustが決定する。AndroidのカメラDDLも共有語彙を使い、履歴表示は保存情報に基づく。記録されていないpromptを旧実装から再構成しない。
- **Render Engine 66** — 共有Rust coreが所有し、Serverの薄いPython adapterとAndroidの薄いJNI adapterが同じ1 requestで呼ぶSVGの演奏。
Androidのmain preview、thumbnail、PNG exportはcanonicalな保存済み／現行SVGを別crate
`inku-svg-raster`（`resvg`）でpixel化する。pixelは派生presentationであり、保存の正本はSVGのままである。
**名前で呼んだ支持体は筆の走り方を変える** —— 地の 7 種はそれぞれ吸い方と歯の強さを持ち、
その値が筆の合成へ渡るので、同じ記述でも和紙とカンバスでは痕が違う形で出る。
`面: 粒` と `面: にじみ` は線や弧に付いたとき、その 1 命令だけ紙を強く働かせる指示として読まれ（上限 3.0 倍）、
面を持てない図形に落ちてきた面の語ではなくなる。
面の質感（平行線・交差線）は行の両端を輪郭で切るので、それを持つ図形の中だけに残る。
切るのは描く前の座標計算なので、フィルタを使わない profile でも同じ形に収まり、
角度・間隔・濃さの傾きは切る前と 1 つも変わらない。
薄墨は掃きの幅が間隔と同じかそれより広いので、掃きと掃きのあいだに紙が残らない面になる
（縞ではない）。1 本ずつの濃さはそのぶん薄く、重なって出る濃さが読み手の見る濃さである。
地は名前で呼べる 7 つの支持体（紙・和紙・薄墨地・木炭地・カンバス・画用紙・メゾチント）で、
**`<pattern>` のタイルとして敷く。フィルタは 1 つも使わないので、3 つの profile がまったく同じ地を出す。**
痕の寸法はキャンバスの短辺で画素へ直すので、同じ記述はどの縦横比でも同じ形の痕を描く（置き場所は従来どおり幅と高さに比例する）。
痕を並べる層も同じ規則に従い、`radial` の環の半径と `at.region` の広がり、まとまり（クラスタ）の帯と道筋（`path`）の交差軸のずれを短辺で画素へ直す。
領域の中心とまとまりの中心は比例のままなので、「右上」はどの比でも右上である。
道筋が自分の線に沿って紙をどれだけ使うか（`margin` と `span`）は形ではないので触っていない。
群の成員は一人ひとりが自分の大きさ（±35%）と傾き（±27°）を持つ。
揺らぎの振幅は図形の大きさではなく**その道具の線幅**で決まり（fine 0.35 / medium 0.6 / broad 2.0 倍）、
道具のトーン（材質輪郭）は意図した幾何ではなく**演奏された墨**からオフセットを取る。
掠れは dash 表ではなく紙の目を表す接触の場が決める。
**接触が読む長さは SVG が書くのと同じ小数 6 桁の格子に載るので、
同じ Score は機械が変わっても同じ数の紙目を数える。**
閉図形の輪郭と塗り、弧、材質層、地の抵抗、マスターグリッドによる座標の量子化を持つ。
**塗りは面を実体で持つ下地の上に載り、上に載るものは被覆率 0.2 で走査線と擦りの痕に分かれる。**

観測用に RAW trace がある（`/api/paint` と `/api/compose` の `include_trace`、既定 false）。
各層の中間生成物を 1 応答に持ち帰るだけで、Score・分岐・回数を変えず DB へも保存しない。

### web（SvelteKit 2 / Svelte 5）

認証付きの単一ページアプリで、記述・作品・バッチ・デモ・系譜の各タブを持つ。
**画面はブラウザが描く**（`+layout.ts` の `export const ssr = false`）。
**組み上がるまでのあいだは `app.html` の幕が出る** —— 地の色と `inku` の 1 語を inline の CSS だけで塗るので、
外部リソースを 1 本も待たない。**消えるのも CSS 規則 1 本で、`app.html` は `<script>` を 1 つも持たない。**
機能ごとの設定は `.svelte.ts` のモジュール直下に反応状態を置く流儀なので、
サーバー側で描くと利用者の状態が要求をまたいで混ざりうる。境界は設定として明示してある。
**`INKU_SINGLE_USER` を立てたサーバーでは利用者が 1 人に定まり自動的にログイン済みになるので、
ログイン画面は現れず、ログアウトの導線も隠れる**（マルチユーザー機構はそのまま残る）。

- 記述の入力と再現可能な推敲（タッチ・配置・読み取り）、AI による自律推敲と変奏。
行頭の連番と角括弧のコメントは作品に残るが描画のどの層にも渡らず、入力欄では背景が灰色になる
- 色カタログ 13 本（`color_catalogs.py`。全カタログが 9 色すべてを持つ）と「記述から自動選択」、
キャンバス比率、表示モードの選択。カタログの選択はユーザーごとにサーバーへ保存する
- **保存済み作品を描き直すときの色の正本は、作品自身が記録した `render_color_map` である。**
描画要求が作品を名指せば（`work_id`）サーバーはその行の色で描き、カタログの今日の定義を読まない。
**改名されたカタログも退役したカタログも描け**、記録を持たない古い作品は現行の定義へ落ちる。
名札は現行名で出し、退役しているものと記録を持たないものにはその旨を添える
- ユーザー別の履歴、スター、推敲マーク、共有の印、コメント、ゴミ箱、検索、系譜グループ、明示的な lineage node / edge。
3 つの印は独立していて、併せて絞ると全部を持つ作品だけが出る。
一覧が並べるのは**保存済み SVG を焼いた画像**で、焼き先は正本 DB の隣の派生専用 `thumbs.db`。
焼くのは保存の後で、engine は動かさないので絵は当時のまま。まだ焼けていない作品は SVG で描く。
焼く仕事は子プロセスへ出す（ラスタライザは GIL を手放さないので、スレッドでは 1 コアに固まる）。
**小さく焼くときは、同じ道具で続けて引かれた痕の質感を塊 1 つへ畳んでから焼く。**
掛かる回数は減るが掛かる面積は増えるので、**得になるのは幅が小さいあいだだけ**である。
判断は焼く側の入口が幅を見て下し、呼ぶ側の旗にはしない（旗は忘れられる）。
**保存する SVG は畳まない。** 畳むのは焼くときだけなので、絵の同一性も engine の版も動かない。
何本出すかは管理者が設定に入れる —— コア数は機械に訊かない（コンテナでは母機の数が答えにならない）。
書き込みは親が行い、1 枚が焼けなくても残りは焼かれる
- 作品ごとの共有。相手と権限（`read` / `write`）を作品 1 件ずつ選べ、
共有された作品には一覧で分かる印が付く。宛先は自分と同じ組織グループの人を名前で選べる
（全員の名簿は開かない）。系譜は持ち主をまたぐので、読めない節点は本文を伏せた札として出て、
削除済みと非公開を別の語で区別する
- グループ宛の共有の印。作品が自分で「このグループなら読んでよい」と言う。
**読み取りビット（`for_share`）と宛先（`share_group_id`）の 2 つが揃ったときだけ**見え、
ビットだけは宛先の無い許可、宛先だけは誰も開いていない宛先である。
宛先を省いて立てると所有者の組織グループが入り、他組織を名指せるのは管理者だけ。
下ろしても宛先は残るので、立て直せば同じ相手へ戻る。**広がるのは読み取りだけで、書き込みは動かない**
- モデル・言語・描画要素の比較、生成情報／プロンプト／JSON のインスペクタ、奥書（colophon）
- 作品の SVG / PNG / アニメーション書き出しと、一枚ものの共有カード（絵・詞書・seed・刻印を 1 枚に組み、
正方形と縦長の 2 版面。サーバーが同梱フォントで焼くので、どの機械でも同じ文字が出る）。
落とし口は 1 本で、利用者が選んだフォルダへ書ける（File System Access API を持つブラウザのみ。
持たないブラウザはブラウザ既定へ落ちる）
- 日英の UI。**英語の用語は 2 つに分かれて正本を持つ** —— **訳語の対応表は `docs/i18n/glossary.md`**（2026-08-17 に web の表と私家版ノート 2 枚を統合した）、**文体規則・禁止語と制限語・機械検査との対は `web/src/lib/i18n/GLOSSARY.md`**。**web の表示文字列は `npm run lint:i18n` が、公開文書の英語は `server/scripts/check_docs.py` が**強制する

UI の寸法は `+page.svelte` の `:root` のトークン（`--btn-sm-*`）が、色は `--action-*` と `--accent*` が正本で、px と色の直書きは退行として扱う。
**共通のボタンクラス（`ghost-btn`）の基底・hover・disabled・`ghost-active` は `+page.svelte` のグローバル規則 各 1 本が持つ。**
Svelte のスコープではクラス名を書いても他所の規則が届かないので、
**コンポーネント側に基底を書き直すことは、共通化ではなく複製である。**

機能ごとの設定は `web/src/lib/features/<name>/` に閉じる。
localStorage への保存・server への永続・描画要求への同梱は、
**機能を 1 つも名指ししない 3 つの登録簿**（`persisted-settings.ts` / `user-settings.ts` / `render-payload.ts`）が集めるので、
設定を 1 本足しても `+page.svelte` は 1 行も動かない。

### server（FastAPI）

- エンドポイント 96 本は `server/src/inku_server/api_core/routers/` の 10 ファイルに在る（`auth` `feedback` `history` `lineage` `me` `plugins` `public` `render` `settings` `users`）。本数の正本は `server/tests/test_route_authorization.py` の `EXPECTED_ROUTE_COUNT` である。
共有される定義は `api_core/{state,models,deps,common,rendering}.py` に置く。
- `api.py` が持つのは `app` の組み立て・`_lifespan`・ミドルウェア・起動時の呼び出し・`include_router` だけである。
**依存の向きは `api.py` → routers → 共有の一方向**で、router から `api.py` を import しない。
- 認可の強制点は router 単位の既定依存である。
公開許可リストに載る 3 本（`/health`・`/api/info`・`/api/auth/login`）を除き、すべてガードの下に在る。
**一覧に載る各項目は、測った理由を持たねばならない**（v2.13.26 で 6 本から 3 本へ絞った。[I-086]）。
**ルート単位の `Depends` が残るのは 2 つの場合だけで、本体が `actor` の値を使うときと、
router 既定より強いガード（`plugins` の管理者限定 7 本）を課すときである。**
**router 既定と同じガードを引数へ書き直すことは、二重の強制点であって多重の防御ではない。**
ガードが尋ねるのは権限グループ（`admins` / `leaders` / `users`）への所属で、1 人が複数に属せる。
判定の入口は述語 1 本に集めてあり、利用者行に残る `role` 列は所属から導出した写しで、どの判定も読まない。
所属の割り当ては既存のユーザー API が扱う。組織グループは別の実体で、1 人 1 つのまま権限とは独立に動く。
- **何ができるか**（権限グループ）と**何が見えるか**（可視範囲）は別の軸で、
どちらも述語 1 本を通る。既定の見える範囲は `admins` が全部・`leaders` が自分の組織・`users` が自分の作品で、
そこへ作品ごとの ACL と、作品が自分で言うグループ宛の旗が足す。**生の SQL で書かれた経路も同じ述語を通す** ——
全文検索が漏れると、現れ方は「見えすぎる」ではなく「検索したときだけ見えない」になる。
- LLM は Anthropic とローカル／クラウドの OpenAI 互換の各 provider へ繋がる。ローカル Ollama は別途導入・起動・モデル取得・接続・段への割り当てを行う構成で、製品全体を API キーや認証設定なしで利用できるという保証ではない。Vision は画像入力に対応するモデルを別途設定した場合に同じ互換経路を使えるが、検証済みローカルカタログには標準 Vision モデルを持たない。
モデル参照の解決は明示修飾 → 一意所有 → 段の既定の 3 段規則で、推測をしない。

### cli

`inku-cli` は公開 HTTP API だけを使う。
描画・履歴・プラグイン・参照 dump・管理コマンド・ベンチマーク補助を持ち、server の内部モジュールを import しない。
**機能テストは変更した挙動を所有するsurfaceを通す。** CLI/APIの描画flowは`inku-cli`、
WebまたはAndroidのUIは各UI、backend contractはfocused API checkで検査する。
要求されたCLI workflowに必要な旗が無いときだけ、まずCLIに実装してからテストする。
**送らない鍵はエラーにならず既定で埋まるので、リクエストのフィールドは送り手ごとに数える**
（`server/tests/test_cli_sender_census.py`）。
**ラスタの判定量を数える経路は、渡された画像をその幅のまま数える。**
幅を決めるのは焼く段であって数える段ではないので、幅・尺度の旗を持たない。

### android

Kotlin / Jetpack Compose / Room による別実装で、端末内でパイプライン全段を回す。
詳細の正本は `android/ANDROID_SPEC.ja.md`。
**server を正本として後から追随する形であり、server の設計を Android に合わせて曲げない。**
追随の遅れは常にありうるので、Android の版数と server の版数を同じものとして読まない。
UI は日英で、切替は設定画面から行う（既定は `ja`）。
画面の文言は Kotlin の言語パックが、歳時記の語彙は `server/scripts/gen_saijiki_kt.py` の生成物が持つ。
現行AndroidとServerは同じ共有Rust render engine `42`を使い、AndroidのDDL engineは`20`である。
Android固有のKotlin描画engineとAndroidSVG artwork pathはretire済みで、runtime fallbackは無い。
Stage 1 / 1.5 / 2、Score coerce、Room、履歴、`rh3` identityは引き続きAndroid hostが所有する。

### 検査面

- **`server/tests`** — pytest。ルート認可の網羅（生きたルートを `fastapi.routing.iter_route_contexts` で歩く。**`app.routes` を直に読むと fastapi 0.141 以降は 1 本も取れない**）、API 表面の同一性（`tests/data/api-surface-baseline.json` と照合）、ルート本体の所在（`route.endpoint.__module__` を数える）を含む。
- **凍結された参照コーパス** — `server/reference/` に版ごとの校正刷りを置く。
現役は `render-engine-42`（610 件）と `ddl-engine-20`（49 件）で、再生成のバイト一致を CI が強制する。
- **Android の参照材料** — `android/app/src/test/resources/server_reference/` はDDL、Score、coerce、履歴互換だけを保持する。
描画の正本は`server/reference/render-engine-42/`と共有Rust coreであり、Androidへ版別SVG corpusを複製しない。
端末受入はcanonical manifestから選んだ少数のrequestをtest assetへ生成し、同梱JNIのSVG byteとraw pixelを直接照合する。
- **`cli/tests`** — pytest。
- **`npm run check`** と **`lint:i18n`** / **`lint:models`** / **`lint:recommendations`** — web の型と用語とモデル解決。
- **`npm run test:unit`** — web の純関数の単体テスト（Node の `node:test`。依存を足していない）。
- **`scripts/check_docs.py`** — 公開文書の内部参照と、日英の見出し形状と、**英語側の禁止語**（`GLOSSARY.md` §5-1 の 4 語。バックティックの中は識別子として除く）。

**決定的な層**は`coerce/`・`ddl_expander.py`・`core/crates/inku-render/`・`core/crates/inku-svg-raster/`・native request境界・`render_engines/default/`・`renderer.py`・`schema.py`・`saijiki.py`・`language_support/{ja,en}.py`である。出力へ影響する変更では凍結corpusを照合し、native request/outputを変えないと証明したhost-only変更は比例した直接検査を使う。描画内部ではRust coreがplanning、geometry、mark、surface、layer、SVG emission、決定的seed派生、演奏metadataを所有する。raster crateはSVGから明示pixelを作るpresentationだけを所有する。PythonとAndroidが所有するのはhost adapter、解決済み入力、保存／identityとUI固有変換である。

**CI は 3 本の workflow を回す。**
`reference-corpus` が凍結コーパスの再生成を照合し、`checks` が
**server（ruff と pytest）・cli（ruff と pytest）・web（`npm run check`・`test:unit`・`lint:i18n`）・
公開文書（`check_docs.py`）**を回す。`android-native` は共有Rust core / raster / JNI / Android hostの
変更だけで起動し、Rust 1.95、NDK 29、`arm64-v8a` native library、境界のhost JVM testを検査する。

**⚠ CI が見ていないものは残っている。**
**① 鍵の要る経路**（NVIDIA NIM を叩く 30 件は鍵が無いので skip する）、
**② ローカル専用の材料**（`cli/bench/leaf` を使う 9 件と `cairosvg` の 1 件）、
**③端末instrumentation**（canonical SVG byte / raw pixel照合は、同梱JNIを使うPixel 9受入であり、
host CIでは代替しない）、
**④Androidの全JVM suite**（CIは共有native境界に関係するfocused testだけを回す。全走はlocal gateである）、
**⑤ internal repository の運用スクリプト**（製品 repository 外で管理し、CI の入力にしない）。
**手元の全走とは母集団が違う。**

### 残っている課題について

**未解決の課題・未裁定の事項は本書に書かない。**
本書へ書くと、書かれた時点で凍って以後だれも見直さないため、直っても古い記述が残る。
開発者向けの台帳が別に在り、そちらが状態を持つ。

## 変更時の確認先

| 変更領域 | 主に読むもの |
|---|---|
| 言語思想・語彙・揺らぎ・関係 | `SPEC.ja.md` §1–14 |
| Web UI・推敲・比較 | `SPEC.ja.md` §7–8、`web/src/` |
| Score・解釈・構成・描画 | `SPEC.ja.md` §5、§12–14、`server/src/inku_server/` |
| 履歴・系譜・奥書 | `SPEC.ja.md` の洗練の会計／奥書、関連API・DB |
| 運用・検証 | ローカルの `AGENTS.md`、`compose.yaml`、各README |
| 過去の判断理由 | `CHANGELOG.ja.md` を該当語・版・Build番号で検索 |

## 文書更新規則

- 仕様変更は `SPEC.ja.md` を先に更新し、**同じ内容を節ごとに** `SPEC.md` へ反映する。
片方にしか無い節は置かない（2026-08-02 裁定。**正本が日本語である点は変わらない**）。
`server/scripts/check_docs.py` が見出し形状の一致を見る唯一のゲートで、マージ前に走らせる。
同じゲートが英語側の禁止語も見る（バックティックで囲んだ識別子は対象外）。
- 現行アーキテクチャ、重要契約、runtime接続状態が実際に変わるときだけ、日英の本書を更新する。Stepの完了・停止・次Stepへの移行だけでは更新を要求しない。
- リリース／Buildの履歴は `CHANGELOG.ja.md` を先に更新し、公開上必要な内容を `CHANGELOG.md` に反映する。
- 実装だけの細部を仕様本文へ無制限に積み増さない。
現行契約は仕様、時系列の記録は変更履歴へ置く。
- Webの挙動またはUI変更では `web/BUILD_NUMBER` を更新する。
アプリ世代変更時はWebの `APP_VERSION` も揃える。
- **本書の「現在の製品状態」には版ごとの段落を積まない。**
版で何をしたかは `CHANGELOG.ja.md` が持つので、本書は現在形の記述だけを保ち、変わった箇所を書き換える。
採番のたびに段落を足すと、本書は変更履歴の二枚目になり、入口として読めなくなる。
- **未解決の課題・未裁定の事項を本書に書かない。**
本書の記述は書かれた時点で凍り、直っても古い記述が残る。
課題は状態を持てる台帳で管理する。
