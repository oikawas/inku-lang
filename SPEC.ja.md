# inku — DDL (Drawing Description Language) — SPEC

**Version: v1.92.0**

この文書は inku / DDL 仕様の日本語正本である。英語公開版は
[`SPEC.md`](SPEC.md) として、この文書の意図に基づき再構成・翻訳する。

**日本語版と英語版は節ごとに対応させる。**
仕様変更は本書を先に更新し、同じ内容を `SPEC.md` へ反映する。

## このドキュメントの位置づけ

**inku** は、DDL（Drawing Description Language）のリファレンス実装プロジェクトである。DDLは言語仕様、inkuはその実装全般の呼称である。

本書は**設計指針、言語設計、現行の主要契約**を記録する。通常の開発では短い入口である [`PROJECT_CONTEXT.ja.md`](PROJECT_CONTEXT.ja.md) を先に読み、必要な節だけ本書で確認する。時系列の実装・設計記録は [`CHANGELOG.ja.md`](CHANGELOG.ja.md) に分離されている。

### プロジェクト名「inku」について

- **ink** の日本語読み「インク」から
- 記述の物質そのものを名前とする——DDLが「記述は作品」というコンセプトであることと構造的に示している
- 墨（sumi）との連想：書道・墨絵の世界観、筆致に現れる「墨の濃淡」と呼応
- `-lang` サフィックスで言語プロジェクトとして位置づける（rust-lang, go-lang 等と並ぶ）

### エコシステム命名規約

派生プロジェクトは `inku-` プレフィックスで統一する：

- `inku-core` — Rustで実装された共通core。Rendererはserverの現行runtimeで使用し、Typed Compilerは受入済み・runtime未接続の基盤として保持する
- `inku-saijiki` — 語彙辞書、最小限かつ必要十分を目指す
- `inku-plugin` — 描画拡張 plugin、語彙自体は拡張されない、一種のマクロセット
- `inku-web` — コンテナベースのWeb UI 実装
- `inku-android` — Android 実装、シングルユーザー専用、カメラ機能が付属
- `inku-cli` — コマンドラインツール

---

## 1. コアコンセプト

### 1.1 「視覚的な短歌を書く言語」

DDLは単にグラフィックを記述する言語ではなく、**視覚的な短歌を書く言語**として位置づける。

`inku` はその参照実装であり、通常の意味での描画プログラムではない。**書かれた短い記述こそが持続する作品であり、typed document が共有の意味を保ち、そこから得た Score を SVG として一度演奏する**。同じ Score は同じ演奏契約を各hostが共有し、揺らぎは記述や意味を変えず演奏時にだけ現れる。

三つの規制の柱：

| アイディアの基 | inku が参考にしたこと |
|---|---|
| **Sol LeWitt の指示書** | 記述そのものが作品であるという思想。記述とドローイングの役割分離|
| **盆栽** | 無制限の語彙/スペックは、描き手を制約する。限られた選択肢が、よりよい創造を生む |
| **短歌** | ターゲットにした文章、意味を多く含みかつ依拠する伝統があるもの |

### 1.2 設計の根本姿勢

- **主張しない、提示する** — 作者の感情や解釈を、直接的に作品に侵入させない（運び手であることは否定しない）
- **短い記述こそが本質** — 長い記述は主張に傾く。短さが本質の提示を可能にする
- **型が自我を削ぐ** — 定型・制約があるからこそ、本質が浮かび上がる

### 1.3 起源

- 2026年4月2日、東京都現代美術館「ソル・ルウィット オープン・ストラクチャー」展
- 作者が文章で体験してきた「精神のフォグが削ぎ落とされ、元からそこにあったものが見えてくる」体験を、絵画という別媒体で再現すること

---

## 2. 設計原則

1. **記述は人間が読める** — 自然言語と記述言語の中間に位置する
2. **揺らぎは仕様である** — LLMのアーキテクチャ的揺らぎをバグとして排除しない。揺らぎはミクロ（線の震え・滲み）とマクロ（構図・配置）の二つのスケールを持ち、どちらも演奏（Renderer）で実現される（Section 13.8 / 14.4）
3. **感情語彙を排除する** — 「美しく」ではなく、数値と物理素材の語彙で記述
4. **固定した大きさを持たない** — 大きさ、位置は基準辺に対する相対位置で示される。Pixelの絶対値は持たない。サイズはスケール可能で、壁にも画面にも適用可能。**縦横比も固定しない** — 画面の縦横比は作品世界を規定する制約であって、記述が持つ寸法ではない
5. **出力は静止画** — 動かさない。見る人が動く。**⚠ 「面がどう在るか」は静止画の状態であって時間の経過ではない**（2026-08-12 作者裁定）。塗り・質感を語彙に持つときは**状態の名詞**で持つ（動詞の「塗る」ではなく名詞の「塗り」）。**動詞で持つと本原則と §3.1 の「配置する動作を中心とする」の両方に衝突する** —— `描く` が v1.92 で剪定されたのと同じ理由による
6. **文章を正規化されたDDLへ変換し、Typed Compilerで検証する設計を採る** — 入力は自由にすることが可能だが、DDLには明確な形式とルールがある。完全な自由形式はユーザーを圧倒する。適度な構造が創造を助ける。Typed Compiler基盤は受入済みだが現行runtimeには未接続であり、現在の生成経路は §12 に記す
7. **エンジンは後戻りしない** — 版木を彫り進めるように、描画エンジンは一方向にしか進まない。過去の版をシステムとして保持せず、選び直せるようにもしない。**残るのは刷り上がった作品（保存済み SVG）であって、彫る前の版木ではない**（§2.1）

### 2.1 演奏の版・同一性・保存

決定的な層だけが版を持つ。Stage 1 と Stage 2 の LLM 層は同じ入力でも揺らぐため、版ではなく実際に送信した prompt の digest を来歴として記録する。`render_engine_version` は同じ Score と seed の演奏結果が変わるとき、または演奏できる語彙が増えるときに上げる。語や道具の改名だけでは上げず、参照記録の更新もそれだけでは要求しない。`ddl_engine_version` は決定的変換の出力が変わるときに加え、`Instruction` のフィールド宣言順が変わるときにも上げる。宣言順を変えるときは移すfieldだけでなく席を譲るfieldも測る。`ddl_version` は文法または語彙が追加・変更・廃止されるとき、Score の `version` はschema構造が変わるときに上げる。`ddl_version` と `ddl_engine_version` は1から数える。`MODEL_CONFIG_VERSION` は計測値・推奨度・選択可否が変わるときに上げ、同じidの保存済みcatalogへ組み込みmetadataを反映する。`APP_VERSION` は `web/APP_VERSION` を唯一の正本とし、UI、`/api/info` の `version`、CLIが同じ値を読む。`server/pyproject.toml` の配布版はrelease tag時だけ更新する。`web/BUILD_NUMBER` はUI変更でも進む共有連番で、同一性には含めない。現在の値は実装と保存済み作品が正本である。新しい版の値、理由、結果は[変更履歴](CHANGELOG.ja.md)だけへ記録する。[描画エンジンの版史](docs/spec/render-engine-history.ja.md)は既存の版記録を保存するhistorical recordであり、新しい節を追加しない。

版と同一性 ID は別の名前空間である。作品エディション ID は `rh3` で、`score`、`render_seed`、render engine の ID / 版、`render_color_catalog_id` から決まる。`render_build_number` と Score側の `vary_seed` は同一性に含めない。保存済み `rh2` はlegacyとして保持し、再計算も `rh3` との比較もしない。

保存済みの参照コーパスは、凍結した版の比較記録として保持する。凍結済み版の出力は更新せず、既存のcase IDも保持する。全体の移行実装が完了した明示的なcheckpointでは、一度だけ全件を更新し、前版との差をmanifestに記録する。途中のengine版上げ、DDL版上げ、または改名だけでは、参照コーパスの全件更新・現行版directoryの作成・generatorや手動比較の実行を義務にしない。変更のリスクに応じて局所的な確認を選ぶ。描画の保存記録はSVG、DDLの保存記録はDDLテキストまたはJSONの形式を維持する。

SVGへ出す小数は `MASTER_GRID_DECIMALS` が定めるmaster gridに従い、固定小数6桁を保つ。過去engineを選択して再演奏する機構は持たず、再演奏は常に最新engineで行う。過去の版を再現する作品は保存済みSVGを返す。版史の経緯と測定値は同文書のhistorical recordとして保持する。

記録されたengine版は来歴であり、再描画の入力にはしない。現在の版と異なる場合はUIで知らせる。DDLの再解釈も常に最新の処理を使い、新しいエディションを作る。保存済みSVG・Score・seed・エディションIDはそのまま保持する。

PNGは正本SVGを写す派生出力であり、縮小してもSVGの材質・地のfilterを黙って落としてはならない。`feTurbulence` / `feDisplacementMap` / `feGaussianBlur`を省略する`cairosvg`は使わず、必要なラスタライザが無い場合は劣化したPNGへのfallbackではなく停止する。ServerとCLIは`shared/src/inku_analysis/rasterizer.py`のresvg経路、Androidは §12.14 の共有native raster APIを使う。これは旧版史に残るPNG規則と現在のhost接続をまとめたもので、描画の意味や実行経路を変更しない。

---

## 3. コアとエクステンションの分離

### 3.1 コアに入れるもの

語彙辞書は俳句の季語辞典にならって**歳時記**と呼ぶ。inku において歳時記は常時開いておくものではなく、必要なときに参照するものとする。

コア語彙は歳時記の 11 カテゴリと、あいだ（関係）で構成される。**語の正は実装の saijiki テーブル（v1.92 で単一情報源化）であり、機械生成の reference §1（`GET /api/reference` / `inku-cli reference`）が常に現行値を公開する。** 以下は概観で、語の追加・削除は reference を正とする。

| カテゴリ | 語彙（概観） |
|---|---|
| **かたち** | 円、楕円、三角、四角、線、弧、雲形 |
| **かたむき** | 水平、垂直、斜め、右上がり、右下がり、回転 |
| **てざわり** | 銀筆、鉛筆、ペン、ロットリング、クレヨン、チョーク、細筆、太筆、油彩、ビュラン、ドライポイント、コンピュータ |
| **つらなり** | 実線、破線、点線、一点鎖線 |
| **おもて** | 空、塗り、薄墨、粒、点、平行線、交差線、にじみ、アクアチント、濃い、薄い |
| **じ** | 紙、和紙、薄墨地、木炭地、カンバス、画用紙、メゾチント |
| **いろ** | 白、黒、青、赤、緑、灰、黄、橙、紫 |
| **ゆらぎ** | 細かく、大きく、ゆっくり、速く、揺れる、波打つ、震える、滲む |
| **ばしょ** | 上、下、中央、左端、右端、上端、下端、中心、隅 |
| **うごき** | 置く、並べる、引く、散らす、埋める、敷き詰める |
| **わりあい** | 縦長、横長、全幅、半幅、半円、上弦、下弦、三日月 |
| **あいだ** | 沿う、触れない、切る、間に、触れる、つながる |

`左上がり` / `left-rising` と `左下がり` / `left-falling` は、typed direct DDLとMacro参照で左右の意味を保つhidden markerである。現時点ではStage 1 promptと歳時記表示へ公開せず、既存の六つの表示語を変えない。

ペン・実線・空・黒は legacy Score / coerce と比較するための historical baseline であり、typed meaningへ挿入する既定値ではない。Visible DDL に該当 field が無ければ typed meaning は `unspecified` のままで、parser / semantic association は補わない。Lock検証済みviewからactual Scoreへ解決する現行subsetだけは、数値位置、またはverified Stage 1.5でdirect `Instruction { instruction_index }`へ解決済みの元`place:center`と、place actionを持つcount1のcircle / square / ellipse / cloudform / triangle / polygonについて、省略countを1、touchをpen、continuityをsolid、閉じた面を塗りとして解決する。色の省略は実際のwork paletteで解決したbackgroundとblack / whiteのOKLCH L差を比較し、大きい側（同差はblack）を選ぶ。明示値は項目ごとに優先し、この解決やeffective focusをsource meaningへ書き戻さない。旧Stop / OmitAndContinue入力は互換で受けるが、recoverableなfieldまたは実行単位の不成立は共通の局所回復としてtyped診断つきで省略し、残る描画を続ける。この規則は Renderer 内部の物理 fallbackや既存作品のread compatibilityを遡及変更しない。

図形の大小は歳時記語彙ではなく、typed DDL compilerが所有する有限の局所modifierである。現行classは`slightly_small` / `small` / `very_small` / `normal` / `slightly_large` / `large` / `very_large`の7つで、JAの普通・大小表現とENの`normal-sized`、`slightly` / `very`を含む対応表面をsource spanごと保持する。自由なdegree同義語やsource substring後処理へ広げない。

キャンバス形式は語彙でもpluginでもなく、shared core の `inku.canvas-format-registry.v1` が所有する resolved host option である。11形式は `square` / `golden` / `a4` / `b4` / `pillar` / `oban` / `wide` / `byobu` / `vertical` / `sd_monitor` / `hd_monitor` とし、visible DDL やmacro定義へ書かない（§19）。

**コアの性質**：
- 物理素材の語彙のみ（感情語ゼロ）
- 「描く動作」ではなく「配置する動作」を中心とする（盆栽で枝を「置く」感覚）
- Actionの語彙設計が特に重要：置く・並べる・埋める——これは提示の動詞
- **ゆらぎカテゴリは運動語彙のみ**：「細かく揺れる」「ゆっくり波打つ」は許容、「美しく揺れる」「激しく揺れる」は排除（詳細は Section 13）
- **あいだカテゴリは観察可能な関係のみ**：「沿う」「触れない」は外部から観察できる位置関係。「寄り添う」「呼応する」のような意図・擬人の語は排除（詳細は Section 14）。語彙（名詞）ではなく述語（統語）の追加であり、プラグイン原則1と矛盾しない
- **おもてカテゴリは面の在り方を言う状態の名詞のみ**（2026-08-12 作者裁定で新設）：つらなりが線の在り方（実線・破線・点線・一点鎖線）を言うのに対し、**おもては閉じた図形の内側がどう在るかを言う**。**動詞を入れない** —— 動詞の「塗る」ではなく名詞の「塗り」。行為の語は §2 原則 5 と「配置する動作を中心とする」の両方に衝突し、`描く` が剪定されたのと同じ理由で入らない。**質**（空・塗り・薄墨・粒・点・平行線・交差線・にじみ・アクアチント）と**濃さ**（濃い・薄い）の 2 次元を持ち、ゆらぎが振幅・周波数・質の 3 次元を持つのと同じ形。**⚠ 濃い／薄いは相対の語であって絶対の濃さではない** —— 同じ塗りでも道具によって濃さは大きく変わる（実測で原寸 1618px の平均輝度が 17.4〜131.1）。**⚠ 紙目は入らない**（面ではなく地の質で、`地:` が引き取る）。**⚠ 質のうち `粒`・`にじみ`・`薄墨` の 3 語は、線や弧に付いたときも落とさず、その痕の走り方として読む**（`粒` と `にじみ` は 2026-08-16 作者裁定・ddl engine 20 / render engine 37、`薄墨` は 2026-08-16 作者裁定・render engine 38）—— **この 3 語は内側の在り方ではなく痕の走り方を言うので、線が内側の代わりに持てるものだからである。****⚠ ただし 3 語の届く先は同じではない** —— **`粒` と `にじみ` は支持体の 2 量（吸い方・歯）を上げる**が、**`薄墨` は紙について何も言わない**（墨をどう溶いたかであって支持体の話ではない）ので、**太くて淡い帯として描く**（幅 3.0 倍・不透明度 0.35 倍）。**残る 6 語は従来どおり、直前の閉じた図形へ移すか、移せる先が無ければ落とす。****背景を埋める指示は面の話ではない**（`background` フィールドへ行く）
- **じカテゴリは支持体の名前のみ**（2026-08-15 新設・render engine 34）：**紙・和紙・薄墨地・木炭地・カンバス・画用紙・メゾチント の 7 語**で、`canvas.ground.material` の値になる。**おもてが閉じた図形の内側を言うのに対し、じはキャンバスそのものを言う** —— だから記述では「面: ...」ではなく「地: ...」の固定句で書く。**7 種は `<pattern>` のタイルとして敷かれ、`<filter>` を 1 つも使わないので、3 つの SVG profile が同じ地を出す。****費用の歯止めは要素数ではなく地の層のバイト数である**（24 KB）。
- **「ランダム」は記述者の入力としては禁止しない**。禁止されるのは Score / 正規化DDL の内部表現に無秩序を残すことであり、記述者が「ランダムに散らす」と書いた場合は Stage 1 が「画面全体に点々と」「ばらつく」「散らす」などの観察可能な配置へ解釈する。
- **コアの色語彙は9色**（白・黒・青・赤・緑・灰・黄・橙・紫）であり、記述者が書ける抽象色を表す。色カタログはこの9色の解決先を差し替える server-owned metadata で、語彙の拡張ではない。**黄・橙・紫は v2.9.11 で加わった** — カタログの `palette` には黄が12色あるのに実描画は0.6%で、**出口となる語が存在しなかった**（公称13.6%との差はそこから生まれていた）。3語は他の抽象色と同格であり、`color_hint` は依然として抽象色に収まらないニュアンスの置き場である。 **v2.9.12（render engine 17）から、9色は作品ごとに1回だけカタログの `palette` から決定的に割り当てられる** — 材料は `(render_seed, catalog_id, 抽象色)` の3つだけで、有彩6語は OKLCh の色相帯（CIELAB は青と紫を分離できない）、無彩3役は `map` 値と同じhexを予約してから明度の近い順に取る。背景も同じ割当を通り、`color_hint` は帯を指す語彙表としてだけ働く（ASCII は単語境界で照合する）。 **v2.9.14（render engine 18）から、13のカタログはそれぞれ9キーの `map` を持ち、その9キーはすべてそのカタログ自身の `palette` から選ばれる** — palette は無彩ちょうど3・有彩ちょうど7で6帯すべてを埋めるので、記述が求めた帯は最近傍の色ではなくその帯から答えられる。**1帯だけは意図して空にしてある** — `sea_stone` は紫を持たず、`blue` と同じ `Night Sea` が代役に立つ。**v2.11.11 から、保存済み作品を描き直すときの色の正本は作品自身が持つ記録である** — 描画要求が作品を名指せば（`/api/render-svg` と `/api/render-score` の `work_id`、CLI の `--from-work`）、サーバーはその行の `render_color_map` で描き、カタログの今日の定義を読まない。**したがって改名されたカタログも退役したカタログも描ける**（id の解決を通らないので 422 にならない）。記録を持たない古い作品は現行の定義へ落ち、そこでも 422 を出さない。作品を名指さない要求は従来どおりで、**退役したカタログidは既定へ落ちず何も返さないので、そのidを指定した描画は既定カタログで描かれる**。

**v1.92 で作者裁定により `描く` と `髪` を語彙から削除した。** v2.7.9 で**銀筆**（0.5px、手が引ける最も揺れない線）/ silverpoint と入れ替え。`hair` を記録した保存済み Score は読み込み時に `silverpoint` へ書き換えられ、seed 以外は変わらずに再演奏される。

**色カタログの命名と調整**: カタログ id は素材・光・技法に基づく名称を使用する。 — `ink_season`・`fresco_study`・`open_air_light`・`ink_porcelain`・`cool_material`・`dye_earth`・`vivid_material`・`weathered_heritage`・`sea_stone`・`moss_bark`・`neon_plate`・`lantern_dew`。カタログの `map` 値は 9 抽象色の意味を保たねばならず、より強い同一性の色は構造色を置き換えるのではなく `palette` に置く。Build 265 の見直しは `open_air_light`・`dye_earth`・`desert_mineral`（v2.9.14 で退役）を調整対象として残した — 暗い背景・高彩度のアクセント・紙や砂の色調が静かな記述を支配しうるため、記述ごとの例外へ分岐せず中核の明度と彩度で調整する。Build 266 でその 3 つの中核色を明るくした。カタログの `sub` は英語 UI の説明文、`sub_ja` が日本語 UI の説明文である。パレット色名は `name` を英語の正規ラベルとし `name_ja` を持ちうる。日本語 UI は `English（日本語）` の形で表示し、英語 UI は `name` だけを表示する。

**render JSON が記録する描画文脈**: 描画・構成・JSON タブ・保存済み作品 JSON は、実際に使われた `stage1_model` / `stage2_model` に加えて `render_build_number`・`render_color_profile`・`render_engine_id`・`render_engine_version`・`ddl_version`・`ddl_engine_version`・`render_canvas_aspect`・`render_hash`・`render_hash_short`・`render_color_catalog_id`・`render_color_catalog_name`・`render_color_catalog_sub`・`render_color_map`・`instruction_lang_requested`・`instruction_lang_resolved`・`ui_lang`・`render_seed` を含む。resource-awareなScore 0.10演奏はさらに`resource_execution`へ、Scoreから再計算した需要、予算超過で省略した原子単位と原因、target省略に伴うrelation省略を記録する。`ddl_version` と `ddl_engine_version` は、その絵を決めた DDL 層の版である。描画応答は必ず両方を積み、保存済み作品では版を記録する前に保存した古い行にだけ欠ける。抽象色と `palette:<name>` は SVG 描画に使った `#RRGGBB` へ展開して記録する。カタログの `map` / `swatches` / `palette` の全体は render JSON へ複製しない — 再演奏と監査に要る具体の記録は `render_color_map` だからである。`score.canvas` は楽譜レベルのキャンバス指示のままで、`render_canvas_aspect` はこの描画作品が実際に使ったキャンバス比を記録する。v2.13.14 から両者は食い違いうる — Stage 2 はどの紙のために組むのかを告げられ、そこで宣言した比は「構図が何のために組まれたか」の記録として残り、実際に演奏した紙は `render_canvas_aspect*` が持つ。それ以前に保存した作品は両方に要求比が入っている。描き直しは演奏した紙を作品の行から読むので、古い作品は以前とまったく同じに描き直る。新しいメタデータでは `render_canvas_aspect_id` が明示のキャンバス比識別子、`render_canvas_aspect_ratio` が実際に描画した幅／高さの比を数値で持つ。`render_canvas_aspect` は互換のために残り、古い記録は応答の中でそこから新しい id と比を導いて補える。

`背景を<抽象色>で埋める。` は面の指定ではなく、typed documentが所有する`background`を指定する有限構文である。sourceで明示した背景はhost contextより優先してScoreへ届ける。背景を省略した場合と複数背景が衝突した場合はcontext backgroundを使い、後者だけをtyped diagnosticとして残す。`埋める`は面または領域を密に満たし、`散らす`は要素を不規則に散布し、`敷き詰める`は図形を規則的・反復的に配置する。これらの意味を互いに読み替えない。typed fill planは全画面、既存named area、またはinlineの単一閉primitiveをtargetとして、同じ領域内の密な不規則配置とclip recipe、targetのsource owner、geometry、count provenanceを保持する。省略countは`ceil(A / d²)`で決め、明示countは保つ。群の混在countは明示分を引いた残りareaを省略種の平均`d²`で割り、ほぼ均等に配って余りをsource順に置き、各省略種を最低1とする。all-explicitは密度計算をしない。Macroは一つのmotifとしてbody、内部count、内側Transformを保ったreference footprintを使い、outer count、seed、material、instruction angle、performed relation移動からは影響を受けない。無面積/open target、numeric motif area、overflowは局所diagnosticで他描画を続ける。resource-aware compilerはこれをScore 0.10のcompact `fill_groups`へ保存し、個体座標を焼き込まず、ownerとnamespace内ordinal、count origin、target geometry、境界、sampling recipeを再演奏する。個数と図形はexactに保ち、procedural filter/patternによる個数近似は採用しない。filterは画材のappearanceだけに使える。Display / Editableはappearanceを適用してから境界clipし、Compatはfilterも`clip-path`も使わずgroup全体をbounded geometryへclipする。clip不能なら元sourceまたはcoordinated group全体を省略し、countの一部だけを残さず、独立した後続描画を続ける。`引く`はlineとarcを共通のgeometry、count、place resolverへ一度だけ配送する。source positionが未指定ならNoneのまま保ち、共通resolverは既存の揺らぎ幅を保つ中央領域`[0.39, 0.39, 0.61, 0.61]`から演奏時位置を選ぶ。明示位置と明示centerのStage 1.5 focusは優先する。`inku.geometry-resolution-policy.v1`はfill planを含むpayloadを保持し、現行digestは`5ce5ec570f913090bec92a9fc2802dfc7c322e866ed965a8486f52f17cb09a56`である。

位置省略の中央領域は、単体・Macro・まとまりで共有し、敷き詰めの配置領域にも同じ厳密値を使う。fillの対象領域省略は別の規則として画面全体を保つ。有効な地だけを指定した作品もScore／Planの描画内容であり、別の不成立な描画指示を省略した場合も、地と診断を保持する。

### 3.2 エクステンションとして分離するもの

- **Nature plugin**（例: 雨、葉、水、風）
- **bamboo拡張**などの具象語彙

**原則**: コアを汚さない。具象的・文化的な語彙はすべて拡張機能として追加可能な形で提供する。

---

## 4. プラグイン設計原則

本節のpluginは、`Nature.雨`のようなvisible qualified termから明示的に呼ぶ、data-onlyの**語彙マクロ**を意味する。外部code hookではない。Canvasはshared coreのhost option、Render Engine Packは描画coreの差し替えであり、この意味のpluginではない。

### 4.1 なぜプラグインを最初から設計するか

DDLではプラグイン機構を**後付けではなく最初から設計する**方針を採る。理由：

**コアの純度を守るため**
Nature plugin（雨・葉・水・風）のような具象語彙をコアに入れないと既に決めている。この判断は、プラグイン機構が最初から存在することが前提になる。

**コアとの境界を明確にするため**
何がコアで、何が拡張か。この線引きが後回しになると、線引き自体が曖昧になる。

### 4.2 Emacs Lisp の教訓

プラグインの自由度は諸刃の剣である。

**Emacs のような自由な拡張性の代償**
- コアとパッケージの境界が曖昧
- パッケージ同士が衝突する
- コア自体が拡張に引きずられて肥大化する
- 学習曲線が個人ごとにバラバラで、共通基盤としての性質が弱い

### 4.3 プラグイン設計原則（5つの原則）

**原則1: プラグインは語彙のマクロに限定する**
新しいプリミティブを追加できない。新しい構文を追加できない。既存のコア語彙の組み合わせに名前を付けるだけ。

**原則2: プラグインはコアを変更できない**
「置く」の意味を書き換えるプラグインは作れない。コアの語彙は不変。

**原則3: プラグインは明示的に参照される**
`Nature.雨` のように名前空間を持つ。素の語彙空間を汚さない。プラグインを使っているか否かが記述から明らかになる。

**原則4: プラグインは単独で完結する**
プラグインAがプラグインBに依存することを禁じる。依存関係の連鎖がないことで、導入・削除が独立できる。

**原則5: コアだけで書ける**
どんなプラグインも、コアmeaningだけで構成されたsemantic nodeへ展開できる。プラグインは省略記法であって、新機能ではない。

### 4.4 キャンバスと語彙マクロの所有境界

Canvasのcanonical ownerはshared coreの`inku.canvas-format-registry.v1`であり、語彙pluginやsystem pluginではない。Canvas selectionはresolved host optionとしてvisible DDL本文とMacroInvocation / MacroDefinitionの外に置く。同じDDLを異なるcanvasへ使え、選択が無いhost boundaryでは`square`をhost defaultにできるが、DDL compilerが`square`をsemantic factとして挿入する意味ではない。Hostが選択をScore / render context / historyへ運び、RendererがSVGの`width` / `height` / `viewBox`を解決する（§19）。

現行runtimeの`plugin_storage["canvas-aspect"]`、`canvas_aspect` request alias、保存済み`Score.canvas` / `render_canvas_aspect*`、system / user plugin directory、plugin status / enable toggleはlegacy互換操作として残る。これらは読み取りだけでなく、legacy plugin documentやenable状態の更新も行える。しかしそのことはsemantic authorityでも、`MacroDefinition`形式の新規authoring / loading APIでもない。これらのretirementとruntime / UI cutoverは後続Stepの責務で、本節は実装済みと偽装しない。Stage 2が現行互換経路でcanvasを受け取る場合もhost-resolved composition contextであり、visible DDL metadataではない。DDL sourceの座標、語、canonical meaningを書き換えない。

### 4.5 MacroDefinitionによる展開モデル

語彙pluginはコア語彙の組み合わせに名前を付けるdata-only macroである。Visible invocationは`Nature.雨`のような`Namespace.Heading`とし、definition version / canonical digest、document / compiler identity、source / generated provenanceはsidecar lockへ保存する。作者へDDL metadataとして書かせない。

全domainは一つのversioned `inku.macro-definition.v1`を使う。Tree / human / water等のdomain固有grammar、plugin別parser、plugin codeは作らない。Compilerはvisible invocationをlock解決し、closed typed parameterをbindingした後、attested composition seedとcaller-owned finite boundsでLLMなしにsemantic nodeへlate expansionし、通常のtyped loweringへ合流させる。Rendererはpluginを理解せず、後続の通常Scoreだけを受け取る。Description pathでStage 1へ渡せるのはbounded signature、parameter schema、short summaryだけであり、MacroDefinition本文やexpanded DDLをStage 1 / Stage 2 promptへ渡さない。Direct DDLのunknown / ambiguous qualified termをhidden LLM fallbackで補わず、明示errorにする。

同じ対象と明示指示へ一意に解決されたinlineとcontinuationは、文章の分割や照応の表面形から独立した同じcanonical meaningを持つ。したがって同じdrawing condition、policy / definition identity、attested seed、明示変奏なら、surface syntaxだけでmacro seed、focus、effective meaningを変えない。unknown、ambiguity、conflictを等価と推測せず、関係・順序・数量・属性・action・parameter、または真正の複数macro invocationを消さない。この規則は一般の文順交換やgraph isomorphismを保証しない。

宣言済みparameterへbindingされたmeaningは展開結果から読む。呼出し外側に残った属性はparameter bindingを再実装せずsource-owned診断とし、OmitAndContinueで未結合appearance fieldだけを省略した場合もMacroDefinition内の既存配色・touch・continuity・surfaceを保持する。未使用parameterは従来どおり受け入れ、parameter default / optionalや呼出し全体の新しい変換意味を追加しない。

この境界により、Rendererはcore meaningだけを知ればよく、pluginは新primitive・新syntax・core語義の変更を持ち込めない。Plugin間依存は許さず、導入と削除を独立させる。

### 4.6 Generic MacroDefinition v1

Anchorだけを含むTransformは、解決済みのAnchor全体の外接矩形中心を使う。一点だけならその点自身が中心になる。描画図形を含む場合は従来の描画図形全体の外接矩形中心を使い、Anchorは同じ変換に従う。

現行consumerの`transform`は回転、`scale_x` / `scale_y`、`translate_x` / `translate_y`を受け入れる。有限値だけを受け、負のscaleは反転、0は退化を表す。子図形のgeometryだけを、回転前の子図形全体の正確な外接矩形中心でscaleし、同じ中心で回転し、最後に平行移動する。translateはnormalized canvas軸の差分である。形状と間隔は変わるがstroke幅とgrain pitchは保つ。内側から外側へgeneral affineを合成し、配置が演奏時に決まる場合はその配置を確定してからbboxを求める。`group`は範囲・参照・ownerを運ぶ透明な構造であり、それ自体の配置・描画命令にはならない。

transformはCount1のactual Scoreとcompactな反復recipeの両方へ配送する。Score 0.5.0の`transform_groups`は範囲、回転、scale、translate、数値固定memberの元instruction indexを保持する。旧Score 0.4.0の回転だけのgroup、保存済み0.1.0／0.2.0／0.3.0、versionなしartifactは従来互換を保つ。空のgroup listはwireへ出ず、`surface_intensity`はScore 0.3.0以後で有効である。既定／legacy lowererはScore 0.9のまま、resource-aware入口だけがScore 0.10のresolved placement / repetition / fill recipeを出す。Score 0.8.0のdirect `placement_groups`は連続したsource順member範囲を一度だけ配置する。Macroは一つの配置memberとしてbodyの位置・内部count・Transform・Anchorと所有範囲を保ち、外側Macro反復は別の`repetition_groups`に保存するため、内外のcountとordinal namespaceは衝突しない。group単位の反復actionは、以下の個数規則でcompact recipeへ配送する。内部配置省略はbbox中心を揃える`overlap`、明示した「並べて置く」は既存wire値の`horizontal_source_order`、明示した「重ねて置く」は`overlap`、`散らす`と`敷き詰める`は`scatter`と`tile`である。group bbox中心をperformance seedで解決する一つのnamed regionへ移し、各memberのowner、count、seedと形を保つ。line-upの省略countは各member 1である。scatter / tileは明示countを保ち、合計8までの残りを省略したmemberへ均等配分し、余りはsource順で先の省略memberへ割り当てる。省略memberは最低1個とし、明示数と最低数だけで8を超える場合も減らさない。全省略も同じ規則で、9種類なら各1個になる。全明示なら合計8へ補わない。line-up / placeは省略memberだけ1とする。外部Connected、Touching / Along / Cutting、NotTouching / Betweenは、変形後の形・向き・namedまたは数値の配置authorityを保ったgroup全体の平行移動で成立を試みる。NotTouchingは既存gap、Betweenは先行二要素のbbox中心を使う既存recipeを保つ。不成立ならerrorを記録してrelationだけを外し、groupは元の変形後配置で描く。数値固定member、旧Stop入力、owner・元index・seed・失われた参照の規則は保持する。`compile_ddl_to_score_with_resources`と`render_with_resources`が共有coreの新入口であり、製品runtime / UI / API / 保存への切替は未完了である。

Anchorは線の接続先に使う非描画の基準点であり、`place`または`position_x` / `position_y`の組で位置を明示する。Anchorの`place:center`は画面中央（0.5, 0.5）で、Emitのfocus依存配置から推測しない。その他のnamed位置は既存の位置領域を使う。Score 0.6.0の`anchors`は描画instructionと別に保持し、`target_anchor_index`でConnectedの接続先になる。元の参照・owner・描画順・seedを保ち、包含Transformの移動・拡縮・回転へ一緒に従う。数値位置の固定と旧Stop入力の互換を維持するが、recoverableなrelation失敗はerrorを記録してrelationだけを外し、描画を止めない。位置のないAnchorを前後の図形や呼出し位置から補完しない。保存済みScore 0.1.0〜0.5.0とversionなしartifactは従来互換を保つ。

揺らぎparameterはasset category `variation`のまま、任意のclosed `dimension`（`amplitude` / `frequency` / `quality`）で候補を制限できる。例は`{"type":"semantic_ref","category":"variation","dimension":"amplitude"}`である。SemanticRefの`dimension`はvariation以外では禁止し、省略／Noneは旧category-only matchingとcanonical bytes / digestを保つ。Someはdefinition digestに含む。Flat Emitは`fluctuation_amplitude` / `fluctuation_frequency` / `fluctuation_quality`を使い、値は各dimensionに属する既存`SemanticRef { category: variation, id }`である。Field名は語義identityを変更しない。Definition、component `use`、binding、実行境界で同じ8語分類を検査する。

宣言parameterはすべて必須である。三parameterを宣言してcallerが一値だけならMissingCompatibleFact等のbinding errorとなる。一振幅parameterだけを宣言してEmitへ届けた場合は、§13.6の同じresolverが残る二slotを解決する。未宣言callerの推測overlay、generic variation一fieldからの三slot推測、parameter optional化は行わない。

`inku.macro-definition.v1`はclosed typed parameterと、definition-local `components`、共通operator `emit` / `use` / `group` / `anchor` / `relation` / bounded `repeat` / typed `transform` / deterministic bounded `vary`だけを持つ。任意code、I/O、無制限loop、recursion / component cycle、filesystem / network / clock / environment、外部macro依存、raw SVG / Score / renderer instructionの生成を許さない。Expansionはeffect-freeで、attested composition seedと明示boundsから決定的なsemantic nodeとsource / generated typed provenanceを返す。

正確な十進数は `{"expr":"exact_decimal","value":"0.240"}` のように記す閉じた型で、通常DDLと同じExactDecimalを使う。定義の元表記を保持し、canonical identityでは `0.240` と `0.24` を同じ値に正規化する。既存 `number` / `Number(f64)` の意味・定義bytesは変えず、f64からexact値を復元しない。Literal、宣言parameter、local、component、有限choicesはexact型を保つ。一般算術やexact値のrange / transformへの暗黙変換は追加しない。

Parameterは `{"type":"exact_decimal","dimension":"radius"}` のように宣言する。Optional dimensionは `radius` / `diameter` / `length` / `side` / `width` / `height` / `chord` / `sagitta` / `position_x` / `position_y` に限る。Callerの明示dimensionと値を一意かつ完全に束縛し、parameter名から意味を推測しない。Dimension省略はdimensionを持たない単独数値にだけ一致する。 同じclauseに通常primitiveとexact parameterを持つMacroが混在する場合は、既存の数値owner未対応境界を維持し、曖昧な割当として診断する。別clauseには影響しない。幅と高さ、弦長と矢高、XとYの複合factは全成分が同一呼出しへ束縛された場合だけ移管し、元keywordとdecimalの出典を保持する。

Flat Emitの同名fieldへexact値を渡す。`width`+`height`、`chord`+`sagitta`、`position_x`+`position_y`は両方が必要で、欠落・型不一致は診断する。数値位置はnamed `place`と別authorityで、両者を黙って上書きしない。寸法・位置は通常DDLと同じresolverへ届き、サイズ重複は診断付きで小さい候補を採る。Definition literalのownerは生成元のEmitであり、架空の原文spanを作らない。Count1/placeのactual Scoreと反復planを扱い、反復個体の生成は後続materializationに残す。

Actual Scoreへ届く現行finite consumerは、完成`emit`を一命令ずつ通常DDLと同じsemantic inputへprojectする。配置や変換を持たない`group`の入れ子も元の順序で巡回し、生成元ownerとlexical scopeで解決済みの参照IDを保持する。Group自身が新しい配置・座標変換・描画命令を作ることはない。`shape`は`line` / `circle` / `ellipse` / `cloudform` / `square` / `triangle` / `polygon` / `arc` / `point`、`movement`は明示`place`、`place`は`center`（exact generated focus target必須）または§18の明示`top` / `bottom` / 四辺 / `corner`を受け入れる。`color` / `touch` / `continuity` / `surface` / `angle`は同名categoryの既存IDを任意で持ち、省略時は通常lowererの同じdefaultを使う。Angleも同じresolverを使い、方向を持たないPointへの明示angleは拒否する。`thinness`は`fine` / `extra_fine`、`relative_scale`は`slightly_small` / `small` / `very_small` / `normal` / `slightly_large` / `large` / `very_large`のclosed core値を受け入れる。大小は通常DDLのnormal geometryと既存係数を一度だけ使い、明示`normal`も省略と区別する。`count`は省略または`Integer(1)`だけが現行Scoreへ届き、`Number(1.0)`を同一視しない。別key alias、raw Score field、f64からのdecimal meaning復元は行わない。

Macro headはsource instruction slot、source invocation ordinal、locked definition、expanded invocationをexact joinし、`place:center`だけは`MacroEmit { invocation_ordinal, expansion_path, generated_ordinal, field: place }`のeffective focusだけを使う。複数の完成Emitはその場の順序で通常命令列へ置換され、`use` / bounded `repeat` / `vary`由来という理由では拒否しない。出力命令はdirect source slotまたはgenerated provenanceへ順序どおり対応する。同じMacroの元の生成順で隣接するbound Emit間の`connected` / `touching`を、通常DDLと同じchecked relation規則で共有performerへ届け、元参照順とowner、numeric-fixed／named-movableの位置authorityを保つ。TouchingはLine / Arcの両端一致と既存Arc再構成を使い、明示relative scale（normal含む）・寸法・弦方向を固定する。`not_touching`と`between`も同じMacroの隣接bound Emitから通常DDLと同じchecked performerへ届く。NotTouchingは既存Medium gapを、Betweenはcurrentの直前Emitとさらに一つ前のEmitのbbox中心を使う既存recipeを保つ。named／noncenter位置はmovable、数値位置はfixedであり、位置authorityを上書きしない。Betweenの`from`は直前Emit、その一つ前を第二参照として両方のownerを保持する。`along` / `cutting`は両者がLineの隣接bound Emitから同じchecked performerへ届き、named位置はmovable、数値位置はfixedとして§14.4の方向・寸法規則を使う。隣接性はunbound Emitも含む元順序で判定し、省略されたfromまたはBetweenの二参照をsurvivorへ付け替えない。旧Stop / OmitAndContinue入力にかかわらず、不完全Emit、unknown key、category / type不一致、未結合caller fact、展開後の未対応Transform軸 / 位置のない`anchor` / 未対応`relation`は、確立済みの最小field・Emit・subtree・invocationを診断付きで省略して残るScoreを続ける。Group内も含め無関係なsiblingをsource / generated provenance順に残す。参照消失は元の依存先を保って関係だけを省略し、独立して描画可能なEmitを残す。参照を残存Emitへ付け替えない。未対応structural subtreeから子Emitだけを抜き出さず、未対応subtreeを跨いで隣接関係を作らない。未使用parameterと未参照Emit binding IDだけを理由に拒否しない。

DirectとMacroの反復planはConnected、Touching、Along、Cuttingのchecked relation intentを、検証済みの元targetと位置authorityのままsymbolicに保持する。これは個体materializationを意味しない。

Macroは意味解決後のinvocation順に実行する。照応だけのmentionは二度実行せず、後続macroの意味上の番号をずらさない。source occurrence ordinalはownershipとprovenanceのために別に保存する。原文の文章とリズム、source span、continuation edge / target、全binding、source / generated provenanceは保存・検証する。これらを含むfull compiler-lock digestはsource integrityのattestationであり、同じ意味の別表現どうしで一致する必要はない。source記録の差を意味選択へ混ぜず、source改変は拒否する。

旧`.inku-plugin.md`、`fires_on`、localized expansion template、旧Stage 1.5 / Stage 2 expanderは、新規pluginのsemantic canonとして退役した。Compatibility importerはapplication全体をerrorにせず`legacy_plugin_format` warningとper-macro `Imported | Omitted` outcomeを返す。旧作品は保存Score / expanded artifactを優先して表示し、旧expanderを恒久fallbackにしない。Artifact不足の`Omitted`をsilent partial renderや別図形へ変えない。

Shared Rust compiler foundationはparse / validate / identity / lock / binding / deterministic expansionに加え、上記finite Emit（配置を持たないGroup内を含む）を通常lowerer経由でactual Scoreへ届ける。ただしproduction runtime接続、package catalog、preview、legacy cutover、任意user package loaderは未完了である。後続package / catalog / preview実装はPLANの別Stepで扱う。`PLUGIN.md`は本節に従う現行authoring guideであり、未実装loaderやdirectory追加手順をauthorityとしてはならない。

Visible sourceの細さと大小は、同じdimensionの`SemanticRef` categoryを明示宣言したparameterへ、一意で完全なassignmentだけをbindingする。大小は既存のhead前修飾でqualified Macro headも認識する。Core由来の値はSaijiki asset metadataを持たず、元span / clause / atom / parameter / definitionへ結び、通常entity修飾として二重消費しない。Literal、外側parameter、definition-local component parameterの値はいずれも同じEmit fieldと通常lowererへ合流する。Missing / ambiguous bindingは既存上流error policy、未宣言caller factは既存lowering policyに従う。Bound parameterだけを新しいcontinuation predicateへ昇格せず、未宣言属性の自動overlay / fan-outを行わない。Source / owner integrity不良は両modeを停止する。

### 4.7 Render Engine との分離

語彙プラグインはコア語彙のマクロであり、描画コアそのものを差し替える仕組みではない。
描画コアは、より重い責務を持つ **Render Engine** として別扱いにする。

Render Engine は、`JSON Score + render options + server-owned color metadata` を受け取り、
`SVG + render metadata` を返す境界である。現行serverの`renderer.py`はdefault engineへのSVG-only互換facadeであり、
薄いadapterが検証済みScoreと解決済みoptionを1個のrequestにしてnative `inku_render` bindingを呼ぶ。

決定的な描画coreはRust crate `core/crates/inku-render`である。これはhost間で共有できるportability boundaryとして受け入れられているが、各hostのbindingとruntime cutoverは個別に確立する。現行server integration以外の実行経路を、このportability intentだけで稼働済みとは主張しない。

履歴、JSONタブ、CLI、ベンチマークが読む正規メタデータ形式は安定させる。`render_hash` は作品エディションIDで、SVG本文・入力文・正規化DDL・LLM応答本文は hash の主材料に含めない。

**現行形式は `rh3:<sha256>`（v2.4.5）。** 同一性は保存済み JSON Score・`render_seed`・`render_wild`・render engine の ID と版・`render_color_catalog_id` から決まる。**`render_build_number` と Score を作る側の seed（`composition_seed`。v2.8.0 までは `vary_seed`）は含めない。** build 番号は `web/BUILD_NUMBER` の中身で UI の変更でも採番されるため、**描画が 1 バイトも変わらないのにエディションIDが変わる**（偽の差分になる）。build 番号は来歴メタデータとして保持し、同一性の定義からは外す。作る側の seed は「Score が違えば ID も違う」ので冗長である。

> **旧形式 `rh2` の材料の鍵名は `vary_seed` のまま凍結する**（v2.8.0）。**同一性 ID の材料は名前ではない** — 鍵の文字を変えると保存済み作品の `rh2` が全部作り直しになる。値は改名後の `composition_seed` から取る。

**`render_wild` は engine 12 で材料に加えた。形式名は `rh3` のまま据え置く。** 材料が変わった以上は別の hash 空間になるが、**`render_engine_version` が同じ payload の中に入っている**ため、旧材料で計算された値は必ず `"11"` 以下を、新材料の値は必ず `"12"` 以上を含む。新旧が同じ値を持つことはありえないので、`rh4` を立てる必要はない。**この論法が成り立つのは engine 版を同時に上げたからであり、材料の追加だけを単独で行ってはならない。**

**`rh2`（v1.60〜v2.4.4）は legacy として保持し、再計算しない。** 保存済みの `rh2:` 行はそのままで、破壊的 migration は行わない（既存履歴の 64 桁 hex hash を legacy として残したときと同じ扱い）。**`rh2` と `rh3` は別の hash 空間であり、突き合わせて同一性を判定してはならない。** 起動時の backfill は `render_hash` が空の行にだけ `rh3` を書く。`render_hash_short`（末尾 4 桁）は形式によらず同じ。
外部任意コードをロードする仕組みは現時点では実装しない。まず内部境界とメタデータ記録を作り、
2つ目以降の実エンジンが必要になった段階で、配布形式・安全性・依存関係を設計する。

### 4.8 廃止

### 4.9 Reference vocabulary names

`Nature`、`Bamboo`は将来または説明用のreference vocabulary名である。現存するruntime-loaded package、install済みpackage、公式registry entryとは主張しない。将来reference definitionを提供する場合も、同じMacroDefinition v1 schemaと通常のlock / expansion境界に従い、plugin固有の実行経路を持たない。

### 4.10 名前空間の規約

プラグインは必ず名前空間を持つ。例:

```
Nature.雨
Human.目
Water.さざ波
```

これにより：
- プラグイン使用箇所が記述から明らかになる
- 同名語彙の衝突を防ぐ（Nature.雨 と Weather.雨 は別物として扱える）
- 将来のpackage / catalog実装では歳時記（Saijiki）を名前空間別に表示できる

### 4.11 自由度の境界

現行canonは「プラグインは語彙のマクロに限定する」である。自由度を広げるには別の作者裁定、schema / version、互換性設計が必要で、MacroDefinition v1へ暗黙に追加しない。

#### 「触れる」の形式の会計（v1.90.0）

- **得るもの:** 二つの弧が両端で接する木の葉形（vesica）のような閉じた有機的輪郭を、座標を楽譜へ凍結せず、位置・傾きの演奏揺らぎを保ったまま書ける。素描で現れた「閉じるがスタンプになる／変わるが割れる」という二律背反を、一つの観察可能な関係語で解消する。
- **失うもの:** あいだへ初めて端点一致という正確な拘束を入れる。既存の距離範囲を演奏が解決する緩い関係だけで構成された族の均質性は失われる。この対価は、閉形を書けない表現上の欠落より小さいと判断する。

将来この境界を変更するproposalが検証すべき問い：
- コアのプリミティブだけでどこまで意味のある表現ができるか
- プラグインを語彙マクロに限定しても、Nature や Bamboo のような具象世界を十分表現できるか
- 拡張のニーズが「マクロでは足りない」ことを示した場合、原則をどこまで緩めるか

**原則を緩める場合も、Emacs 化を避けるための明確な線引きを維持する**。自由度を増やすときは、その自由度が失わせるものを明示し、別のschema / versionと互換性境界を作者裁定してから判断する。

---

## 5. 三層パイプライン

```
記述（自然文）  →  正規化DDL  →  楽譜（JSON Score）  →  演奏（SVG）
人間が書く          Stage 1 が      Stage 2 が             Renderer が
                    解釈する         構造化する             描く
```

### 5.1 各層の役割

- **記述**: 人間の層。母語の自然文で書かれる。短歌的な短さを推奨。実行仕様の一段上に立つ詩歌的な層
- **正規化DDL**: Stage 1 が記述から書き起こす実行仕様（DDL を直接書く入口もある）。有効な語彙pluginはこの時点で`Namespace.Heading`のqualified termを含みうる。plugin展開がStage 1の直後にそれをコアDDLへ決定的に書き下し、Stage 1.5とStage 2はその展開後DDLを読む
- **JSON Score**: 中間の楽譜。言語非依存・機械可読
- **SVG**: 演奏の結果。一回性。記述は残り、出力は都度生まれ都度消える

**Stage 2 の tool schema は、プロパティの並び順ごと LLM へ渡る。** そのため**任意フィールドの充填率は
宣言位置に単調に従属する** — `Instruction` の `thinness` だけを 5 点振って測ると、先頭で **0%**、
14 番目（render engine 16 の宣言位置）で **18%**、19 番目で **48%**、22 番目で **83%**、末尾で **89%** だった
（異なり入力 25 件・同じ Stage 1 出力・同じ Stage 2 プロンプト・`nvidia:google/gemma-4-31b-it`。
全 5 群がそろった 21 件で対応をとった集計）。**先頭が 0% なので「意味の近い語の隣にあるのが悪い」のではない。
後ろにあるほど埋まる。** ゆえに**フィールドの宣言順は読みやすさの都合ではなく仕様である**。
順序を変えたときに版を上げる規則は本書 §2.1 が持つ。

**`thinness` は v2.9.33 で `surface` の直前へ移し、末尾は `surface` へ返した。**

**末尾の席は 1 つしかない。** `thinness` を末尾へ置いた v2.9.5〜v2.9.32 の間、`surface` は席を失って
搬送が **92% → 42%** へ落ち、**Stage 2 の出力そのものが半分に縮んだ**（出力トークン中央 172 → 94.5・
命令 2.45 → 1.43 個/回・`surface.opacity` は誰も書かないので既定値 0.28 が本番値になっていた。
168 本の実測・2026-08-02）。**「後ろにあるほど埋まる」は、後ろを譲った側が落ちることでもある。**
`thinness` 自身の搬送は 89% → 67% へ下がるが、**Score 全体を縮めない位置がここである**。

**`weight` の隣へ戻してはならない** — 語としては太さの隣だが、**位置のほうが仕様である**（隣では 3%）。
**`Instruction` の末尾は `surface` のために空けておく。** 新しい任意フィールドを末尾へ足すと同じ退行が起きる。

### 5.2 LeWittとの違い

LeWittの指示書は、実行可能な具体的指示そのものだった。inku でそれに相当するのは
**正規化DDL** であり、LeWitt が指示書を書いた地点に Stage 1 が立つ。

inku が LeWitt に足したものは二つある。

1. **記述者と実行者の一体化**: LeWitt は記述者（LeWitt）と実行者（職人）が
   分離していた。DDL では一人の人間の中で起きる（自分 ↔ LLM）。
2. **一段上の入力層**: 作者が書くのは指示書（正規化DDL）ではなく、その一段上の
   詩歌的な記述である。指示書は Stage 1 が代わりに書き起こす——作者は詩を書き、
   機械が LeWitt 流の指示に清書する。

内側から出たものが外側から返ってくる——その往復の中に、霧が払われる瞬間がある。

### 5.3 用語と層の対応表

UI の語彙ダイアログ（App Info「用語と層」）と同一内容であり、本表を単一の正本とする。

| 語 (ja) | 語 (en) | 対応する層・行為 |
|---|---|---|
| 記述 | Description | 作者が書く詩歌的な入力。作品の最上層（inku 固有。LeWitt に対応物なし）|
| 解釈 | Interpret | 記述を指示書へ読み解く Stage 1 の**行為** |
| 指示書（正規化DDL）| Instructions (Normalized DDL) | 解釈が生む実行仕様。**LeWitt の指示書に相当** |
| 楽譜（JSON Score）| Score (JSON Score) | 指示書を構造化した中間表現。決定的に保存される |
| 演奏（SVG）| Performance (SVG) | 楽譜を描く一回性の結果（＝draftsman の実現）|
| 詞書 | Headnote | 記述を作品の傍らに掲げ直したもの（短歌の詞書）|
| 読み取り | Reading | 言葉の読み直しから候補を作り直す操作（別の解釈）|

---

## 6. Base Language 問題

### 6.1 問題提起

日本語と英語（他の言語）でのDDLの扱いをどうするか。

### 6.2 方針（暫定）

**レイヤーごとに言語を分ける**：

| 層 | 言語 |
|---|---|
| DDLテキスト（人間が書く層） | 実装済みは日本語・英語。追加言語は Instruction Language Registry へのsupport実装後に受け付ける |
| JSON Score（機械が読む層） | 英語キーで統一 |
| LLM（変換層） | 登録済み言語の Stage 1 / Stage 2 prompt を使う |

### 6.3 設計上の根拠

JSONは「楽譜」であって「演奏」ではない。楽譜が国際記譜法で書かれていても、演奏家は自分の文化的背景で演奏する。同様に、記述は母語で、スコアは共通語で書ける。

「記述は自分の言葉でなければならない」という原則を守るため、DDLテキスト層は母語を許容する必要がある。短歌を英語で書くこともできるが、多くの人にとって母語の方が霧が払われやすい。

### 6.4 責任範囲の明確化（OSSとしての方針）

**作者（Shinichiro Oikawa）が責任を持つ範囲:**
- 日本語版DDL（Base Language として参照実装）
- 英語版DDL

**コミュニティに委ねる範囲:**
- 他言語版（中国語、韓国語、フランス語、その他）の実装
- 各言語固有の語彙拡張

**固定仕様として扱う範囲:**
- JSON Score は英語キーで統一（言語非依存の中間層）
- プリミティブ名、フィールド名は英語

### 6.5 UI表示言語と指示文言語

Web UI の表示言語と、ユーザーが入力する指示文の言語は別のメタデータとして扱う。記述タブでは指示文言語を事前選択させず、入力内容から自動判定する。日本語 UI で英語の指示を書く、または英語 UI で日本語の指示を書くことを許容する。

- `ui_lang` は画面表示・操作文言の言語であり、描画解釈の言語ではない
- `instruction_lang` はAPI互換性・再現・開発者診断のため `auto` / `ja` / `en` を持つが、通常の記述UIは常に `auto` を送る
- `auto` の場合、サーバーは入力文字列から日本語 / 英語を軽量判定し、Stage 1 / Stage 1.5 / Stage 2 に渡す言語を決める。文字・語彙から判定できない場合だけ `ui_lang` を既定値とする
- 解決結果は `instruction_lang_requested` / `instruction_lang_resolved` / `ui_lang` として `/api/paint`、`/api/compose`、履歴、JSONタブ、保存 artifact JSON に記録する
- これらの言語メタデータは監査・再現補助用であり、既存履歴の `render_hash` 互換性を壊さないため、現行の `render_hash` canonical payload には含めない
- 将来の他言語対応は、コア API を増やすのではなく、Instruction Language Registry に言語サポートを追加する形で拡張する

Instruction Language Registry は、各指示文言語について以下の境界をまとめる内部登録表である。

- 言語コード
- Stage 1 prompt
- Stage 2 prompt
- Stage 1.5 expander / filter
- Score coerce layer が使う言語別 marker セット

Score coerce layer の補修アルゴリズム本体は、JSON Score 構造に対する言語非依存の処理として共通化する。一方で、どの語が `motion` / `visual_event` / `hard_edge` / `dark field` などの抽象文脈を意味するかは言語依存であるため、`ja` / `en` の各 `InstructionLanguageSupport` が `coerce_markers` として所有する。

第三者がスペイン語などを追加する場合は、JSON Score schema や renderer を変更する前に、この registry に `es` などの言語サポートを追加する。追加言語は prompt / expander だけでなく、Score coerce layer 用の marker セットも持つ。既存の `ja` / `en` は従来の prompt と expander をそのまま登録し、coerce marker も言語別ファイルへ分離するため、言語固有語彙を共通コアへ混入させない。言語メタデータは `render_hash` の canonical payload に含めず、既存履歴やベンチマークのハッシュ参照を安定させる。

### 6.6 二言語並行開発の意義

日英の二言語で並行開発することは、お互いの描画結果を参照し、設計の質を上げるプロセスとして機能する：

同じ概念を日英で書いたとき、どちらかで自然でない表現が出たら、それはコアの言葉選びが偏っているサインである。両方で自然に書けるものだけがコアに残る。

**判断基準の例:**
- 「置く」⇔「place」——両方自然、コアに入れる
- 「佇む」⇔「stand still, but with presence」——英語だと一語にならない、コアではなく日本語版拡張として扱う

一言語だけで開発すると、気づかないうちに言語固有のバイアスがコアに入り込む。二言語あることで、言語非依存のコアと言語固有の拡張が自然に区別される。

### 6.7 英語の指示文経路

本節は運用面の記録であり、**英語経路が実際に何をしているか、それをどう測ったか**を残す。

Build 403〜427 で英語の指示文経路を構造的なルーティングの先へ広げた。日本語と英語は Stage 1 プロンプト・Stage 1.5 の展開／フィルタ挙動・Stage 2 プロンプト・coerce のマーカー集合について、それぞれ別の言語ファイルを持つようになった。JSON Score schema・renderer・色カタログ・補修アルゴリズムは共有したままである。したがって**言語固有の挙動は、プロンプト・展開器・マーカー・補修入力の境界に留めてある**。

英語経路は語ごとの翻訳を行うのではなく、**英語固有の言い回しを保つ**ように調整してある。`before`・`after`・`again and again`・`as if`・`at once` のような時間と関係の句、`diagonal`・`same beat`・`shifted` のような構図の手がかり、そして反射・霧・道・音・群れ・透明な出来事の語は、抽象的な視覚パラメータと焦点となる出来事の手がかりとして扱う。

Build 427 は、日英で対応する 30 組のプロンプトを同じ正方キャンバスと既定の色カタログで描き、ベンチマーク履歴を保存せずに確認した。熟練者の講評では英語経路は日本語に近い品質で、**英語は color resonance がやや高く、日本語は constraint adherence と visual event の存在感がやや強い**という差だった。英語に残るリスクは**整いすぎて出来事の瞬間が背景構造へ沈むこと**、日本語に残るリスクは**静かな詩的情景を、見える出来事を担えないほど小さな痕跡へ圧縮すること**である。今後の調整は、全体の密度を上げずに焦点となる出来事の大きさ・対比・周囲の反応を強める方向で行う。

---

## 7. UI設計方針

### 7.1 反復を前提とするUI

DDLは一回で完成させない。**記述→出力→推敲**の往復を設計の前提とする。

### 7.2 画面構成（概念）

現行の参照 UI は、記述入力と解釈結果、描画キャンバス、履歴、推敲を一つの制作面に置く。Stage 1 の正規化 DDL は描画完了を待たずに表示でき、保存済み作品からは DDL・Score・生成情報・系譜を辿れる。推敲は元作品との差分を派生 metadata と表示で示すが、プログラミングの diff を制作面の中心には置かない。

**表示の量は書き手が決める（v2.9.8）。** 画面に出す道具の数は、初めて開いた人には多すぎ、作り込む人には足りない。そこで表示範囲を 3 つのモードとして持ち、ログインユーザーごとにサーバー DB へ保存する。**シンプル**は必須のものと履歴（ユーザーメニュー・設定入口・単発の記述入力・描画操作・キャンバス・履歴）。**履歴を必須に含めるのは、描いた作品を見て失うだけの画面にしないためであり、作品を一枚もの（共有カード）として持ち出す口が履歴側とキャンバス側の 2 つとも履歴群に属するためである**（v2.13.9）。

**キャンバスのツールバーはどのモードでも残る** —— シンプルでは共有カードだけが並ぶ、**フル**は従来どおり全部、**カスタム**は必須に 7 つの表示群（まとめ描き・描画設定・指示書ツール・詳細ステータス・作品ツール・履歴・補助操作）を個別に足す。

**初めて作られたアカウントはシンプルから始まる。** モードが変えるのは表示層だけで、機能経路・履歴・保存データは変わらない — 隠れている道具もモードを戻せばそのまま動く。習熟度の呼び名（初心者 / 熟練者）は用いない。

**表示できない入力方式や作品タブを選んだままモードを変えたときは、単発入力またはキャンバスへ戻す。** **モードはレールのアイコンからも切り替えられ、アイコンは濃い横棒の本数でいまのモードを言う（シンプル 1・カスタム 2・フル 3）。メニューの並びもその順である**（v2.13.18）——**3 つのモードで同じ絵を出すアイコンは、どれが選ばれているかを言えない。**

**設定ダイアログにも同じ考えの 2 モードを置く（v2.13.18）。** `標準`は日々使う設定だけを出し、`詳細`は`プラグイン`・`制限値`・`未読語台帳`・`その他（サーバー）`の 4 タブを加える。**タブの名前は 1 つのモジュールが持ち、タブバーと本文の番人が同じ表を読む** ——**バーが隠して番人が許すと本文へ届かない箱ができ、逆だと押しても何も起きないボタンが残る。**選択はブラウザに残り、サーバーの保存データは変わらない。

### 7.3 LLM Model Inspection

推敲のモデル比較では、利用可能な LLM を明示的に選び、同じ作品から生じる Stage 1 / Stage 2 の差を見る。特定のモデル名を現行契約として固定せず、実使用モデルと出力差を記録する。

### 7.4 inst. box のデザイン

**基本方針: IntelliSenseの逆を行く**

IntelliSenseは「書く前に候補を出す」ことで間違いを減らすツール。DDLでは逆に、**書き手の迷いの中に創作の瞬間がある**と考える。「置く」と書こうとして一瞬手が止まるその静止の中に、「並べる、の方が近い」という気づきが生まれる。補完候補が次々出ると、思考が候補に引っ張られて内側を見る隙がなくなる。

**採用する設計**

1. **白紙の記述エリア**: 書くときは何も出さない。短歌の原稿用紙に近い純度
2. **歳時記（Saijiki）として語彙辞書を別配置**: 記述者が能動的に参照しに行く
3. **書いた後に解釈フィードバック**: 正規化 DDL と解釈差を描画後に確認する（詳細は7.6）
4. **記述者のための書き込みは、記述ではない**: **行頭の連番**（`1. ` `01. ` `０１．` `１　` `12）` `3:`）と
**角括弧で囲んだコメント**（`[疎  紀友則 / 古今和歌集（春下）]`。半角 `[]` と全角 `［］`）は、
**作品には原文のまま保存し、描画のどの層にも渡さない**（**Stage 0.5 を含む**）。
記述エリアとバッチの入力欄は、その範囲の**文字の背景を灰色**にして「これは描かれない」と示す。
**切るのはサーバー側 1 か所**（`description_labels.py`）なので、web・CLI・Android のどの経路でも同じに効く。
数字が番号と見なされるのは**区切り記号か全角空白が続くときだけ**で、`2026年` や `3本の線` は記述として残る。
**閉じていない `[` も記述**である（行末まで飲み込ませない）

**却下した設計**

| 設計 | 却下理由 |
|---|---|
| IntelliSense風の自動補完 | 創作の静止時間を奪う。手続き的すぎる |
| 常時表示の選択肢一覧 | 「外側を見る → 内側から引き出す」順序を強制する。創作の順序と逆 |

**設計の根拠**

短歌を書くとき季語一覧を常に見ながら書く人はいない。自分の中から湧いてきた言葉を書いて、後で季語を確認する。**内側から出る → 外側で確認**の順序が正しい。

### 7.5 歳時記（Saijiki）

DDLの語彙辞書は **Saijiki** と呼ぶ。英語版でもこの名称を維持する。

**名称選定の根拠**

- 俳句の国際化により英語圏でも既にある程度認知されている
- 日本発のコンセプトであることを明示できる
- 英語話者にとっては "Saijiki" というボタンを開く行為自体が、異文化の視点で語彙を見る体験になる

**カテゴリ構造**

歳時記は 12 カテゴリ（かたち・かたむき・てざわり・つらなり・**おもて**・**じ**・いろ・ゆらぎ・ばしょ・うごき・わりあい・あいだ）に、ロード済みプラグインの名前空間付き語を加えて表示する。語彙の現行値は §3.1 の表と reference §1 を正とし、web の歳時記表示も同じ saijiki テーブルから配信される（v1.92: `GET /api/saijiki` + バンドル内蔵スナップショットの同期ストア）。

カテゴリ名はひらがなを採用する。漢字は硬い。ひらがなは記述の敷居を下げる。英語版カテゴリ名は forms / angles / touches / continuity / **surfaces** / **grounds** / colors / movements / places / motions / proportions / relations とする。

**配置方針**

- 記述エリアには表示しない
- UI上のボタン（[Saijiki]）から能動的に開く
- 書くときは閉じている、迷ったときだけ開く

歳時記ドロワーは閲覧専用とする（v1.98）。語彙チップのクリックは挿入ではなくプレビュー表示であり、語の挿入は DDL エディタダイアログ内のインライン歳時記でのみ行う（ロード済みプラグインの名前空間付き語も同所に表示する）。開閉トグルはキャンバス下部ツールバーに置く。

### 7.6 解釈フィードバック（Interpretation Feedback）

現行のフィードバックは、書き手の原文に対する採点ではなく、変換結果の観察面である。正規化 DDL、互換経路で展開された場合の展開後 DDL、プラグイン警告、制限値の注記、解釈差を表示する。Stage 1 の結果はストリームで先に届きうるが、早く表示されることは正しさの判定ではない。

語単位の確信度、墨色による色分け、インライン英 gloss は現行機能ではなく、現在契約に含めない。読めなかった語やフォールバックは、実際に保存・返却される警告と metadata で区別する。

書き手は「自分の書いた言葉」と「LLMの解釈」のズレを見ることができる。このズレ自体が、次の記述を書く材料になる。

- 「LLMが『静かに置く』と読んだなら、次は『置く』と書けばいい」
- 「いや、『佇ませる』の方が自分の意図に近い。LLMが読めなかったということは、まだ見えていない何かがある」

どちらの反応も創作的である。**ズレが思考を生む**。

### 7.7 差分の可視化（記述の推敲過程）

7.2で言及した「新旧の差分を色で可視化」の原則：

- プログラミングのdiffではなく、**文章を削ぎ落とすプロセスの可視化**として設計する
- 変更・追加が視覚的にわかる
- 推敲の痕跡として残る

7.6の解釈フィードバックと組み合わせることで、記述者は「自分が書き換えた部分」と「LLMが読み取った度合い」の両方を一画面で確認できる。

### 7.8 参照 Web アプリケーション

本節は**参照インターフェースが実際に何を提供しているか**の記録である。概念ではなく運用の面を持つ。

Web実装では、`+page.svelte`をroute composition shellとし、route lifecycle、画面構成、history／lineageのcross-owner action、短い表示用projectionとowner配線を保持する。Session、単一作品、Batch、Demo、履歴／系譜、Canvas viewport、推敲、Settingsはrouteごとに1個のownerが可変stateと非同期identityを持つ。1回のPaint、履歴保存／再演、推敲候補の計画と適用は、解決済みinputと名前付きcapabilityだけを受けるstateless operationへ分ける。CanvasとSettingsのfocused viewは表示とlocal draftを所有するが、domain state、transport、request serialization、追加のawait境界を複製しない。作品を切り替えた後に古い非同期結果が戻っても、runまたはtarget identityが一致しない結果は現在画面へ適用しない。

短い英語のタブ・ボタン・ラベルは `docs/i18n/glossary.md` の対応表と `web/src/lib/i18n/GLOSSARY.md` の文体規則に従う（2026-08-17 に対応表を前者へ統合した）。後者の規則を `npm run lint:i18n`（v2.7.1）が強制する。iPad 級の幅では Canvas のタブと、表示中の モデル／色／キャンバス／作成時刻のメタデータが 2 行へ折り返し、左パネルは作品メタデータを切り落とさずビューポートに合わせて伸縮する。

Web アプリが現行の参照インターフェースである。v1.72 で推敲とモデル比較を一級の制作面にした。`推敲` タブはタッチ・配置・読み取り・色カタログ・変奏（§12.13）の変更をラジオ選択として提供する — **1 回の推敲で選べる介入はちょうど 1 つ**であり、系譜の各辺は 1 つの原因に帰属できる。

変奏を選ぶとそのラジオの直下に強度（控えめ／中庸／大胆、既定は中庸）が現れる。候補 1 案はサーバー採番の新しい seed を 1 つ、4 案は 4 つ使う。変奏のための独立した節やボタンは置かない。選んだ推敲要素はブラウザが記憶する。

読み取りは上流の介入 1 つで、下流の配置とタッチは再生成される。候補 1 案または 4 案は選ばれた要素だけを振り、同じ選択・保存の手順を使い、2 列のグリッド（1 案なら全幅）でダイアログに収まる大きさで表示する。**ただしタッチは、利用者が「タッチへ託す言葉」を入力して 1 案だけ生成する。同じ言葉は同じタッチ seed になるため、4 案は提供しない。**

選んだ推敲候補の保存は、自動でスターを付けずに通常の履歴へ入れる。保存操作は未保存・保存中・保存済みを区別し、保存済みの候補は二度保存できない。候補生成中は他の生成・描画操作を止め、3 秒後に共有の停止操作を出す（要求の中断で裏打ちする）。進捗の文言は実際に行っている作業を名指しする。読み取り候補は画像のホバーで正規化 DDL を出す。

描画 seed と変奏 seed は独立した JavaScript 安全な乱整数で、初回生成から候補・履歴・再演まで持ち回る。タッチ候補は利用者が託した言葉から seed を決める。表示の描画は、正本の構図座標を変えずにタッチ seed の変化を見せる。

色カタログの推敲は DDL・Score・キャンバス・配置 seed・描画 seed を固定したまま親と異なるカタログを当て、4 案は可能なかぎり異なるカタログを使う。色以外のすべての推敲は、次回描画の操作ではなく**表示中の親作品の実効カタログとキャンバスを継承する**。色の辺は `catalog_change` を使い、前後のカタログ ID を記録する。

キャプションの表示可否はユーザーごとに永続する。前後の移動は推敲の中で開いている 調整／モデル比較 のサブビューを保ったまま対象作品だけを変える。

調整候補は**生成元の作品が所有する一時状態**であり、履歴・系譜・近傍・移動から作品を明示的に選ぶか、新しい生成や DDL 描画を始めると消える。調整とモデル比較を行き来しただけでは消えない。対象が変わると、対象が所有するモデル比較結果・読み取り差分・再演エラー・中間系譜の通知・系譜取得状態も戻る。実行中のモデル比較は中断し、系譜要求は最新のものだけが表示を更新できる。

Web UI は直接的な操作ラベルを保ち、仕様の側は音楽のメタファーを保つ — 演奏は「タッチ」、構成は「配置」、解釈は「読み取り」として表示する。モデル比較は Canvas 側の `推敲` タブの中に `調整` と並ぶサブビューとして置き、judge 値を表示しない。3 つのモードを持つ — `Stage 1/2 共通`・`Stage 1 固定 + Stage 2 比較`・`Stage 1 比較 + Stage 2 固定`。共通モードは選んだ各モデルを両段に使う。固定モードは固定側に 1 つ、比較側に最大 4 つを選ぶ。禁止されるのは**対象作品が使った Stage 1/2 の組み合わせちょうど 1 つだけ**で、対象が使ったモデルでも固定側との組み合わせが異なれば選べる。禁止された選択は浮動ツールチップが説明する。モデルは常に明示的に選ばれ、未選択の代替モデルを走らせることはない。対象を変えると古い比較結果を消し、実行中の比較を中断する。保存した比較結果は実際に使った Stage 1・Stage 2 のモデルを記録し、採用またはスター付きで履歴へ入れられる。

系譜カードの作品メニューは、見出し「作品編集」の下にこの順で提供する — 描画パラメータの編集、記述を編集、指示書を編集、写生の区切りを変える、使用モデル変更、AI自動推敲プロセス。DDL直接生成作品では、記述を編集・写生の区切りを変える・使用モデル変更を出さない。描画パラメータの編集と使用モデル変更は、選んだカードを対象に対応する既存の推敲サブビューを開き、比較のロジックを複製しない。記述と指示書の編集は選んだ作品から初期化したダイアログを開き、描画は `description_edit` または `ddl_edit` の子を保存し、系譜へ戻り、最新の子とその祖先へ焦点を当てる。ダイアログを閉じると元の系譜ビューへ戻り、通常のトップレベルの推敲タブはパネル配置を保つ。旧「手動推敲」モーダルにメニュー項目は無い。

主要な UI 領域:

- **App rail**: 開閉トグル・ユーザーメニュー・プロフィール・設定・言語とテーマの操作を持つ小さなナビゲーション
- **入力パネル**: 描画・バッチ・デモの各モード
- **DDL 表示／編集**: 描画の流れには読み取り専用の正規化 DDL を表示し、語のハイライト、展開後 DDL の表示、`DDL から描画`を備える。編集は行番号・インライン歳時記・短い構文ガイドを持つ DDL 編集ダイアログで行う
- **Canvas パネル**: SVG 表示・ズーム・パン・出力タブ・ステータスバー・書き出しボタン
- **履歴ストリップ**: 最近の作品・ホバーのメタデータ・スター印・ページング。**サムネイルの下に添える情報は読み手が選ぶ** —— 世代・モデル・engine バージョン・ファイル容量から最大 2 つで、**0 個も選択可能**（何も選ばなければ絵だけが並ぶ）
- **履歴マネージャ**: 大きな履歴ビュー・ゴミ箱・復元・完全削除・スターのフィルタ・**共有のみのフィルタ**・作品ごとの共有。共有ダイアログは宛先と権限（読み取り／書き込み）を選び、いま誰に渡っているかを一覧する。**他人から共有された作品には印を出す** —— 人が選んで消す画面なので、印が無いと他人の作品が自分のものと同じ見た目で並ぶ。**宛先は自分と同じ組織グループの人を名前で選べ**、候補を取れない利用者は id を直接入力する（全員の名簿は開かない）
- **設定モーダル**: モデル・色カタログ・DB 状態・プラグイン状態・書き出しテンプレート・ユーザー・テーマ

ステータスバーは現在の描画文脈を表示する — Stage 1 モデル／Stage 2 モデル／色カタログ／キャンバス比／現在の履歴項目のスター状態／SVG・PNG の書き出し操作。

履歴の表示では、モデル・カタログ・キャンバスの値は取れるかぎり履歴項目から取る。編集中は現在の選択から取る。Canvas パネルのヘッダは選んだ作品の色カタログ・キャンバス・作成時刻も表示する。入力パネルの色カタログボタンは現在選ばれているカタログ名を表示し、長い名前は省略記号で切る。

設定モーダルの「その他」タブは**履歴選択時の挙動**の操作を持つ。履歴項目を選んだときに UI の現在のキャンバス比と色カタログをその項目の値へ更新するか、現在の UI の選択を保つかを、それぞれ独立に選べる。この設定は UI の選択状態にしか効かない — 保存済みの履歴 SVG は保存されたまま表示され、描き直されない。

同じタブが**履歴ストリップに添える事実**の選択も持つ。世代・モデル・engine バージョン・ファイル容量の 4 つから**最大 2 つ**を選び、選んだ順ではなく**宣言順**で出す。**「何も選ばない」は既定への差し戻しではなく、保存される答えである** — したがって**未回答（列を持たない口座）と空の選択は別物として扱う**。3 つ目を選ぼうとすると、既存の選択を追い出さずに拒み、上限を画面で示す。**ファイル容量はサーバーが保存済みの作品について報告する量**であり、ブラウザが受け取った SVG を数えたものではない — 帯を埋める一覧は絵を運ばないので、受け取ったものを数えるとすべての作品が 0 と報告される。

Canvas パネルは鑑賞向けの操作も持つ。描画タブの全画面アイコンはプレゼンテーションモードを開き、現在の SVG を最大化して、履歴の移動・最新項目・スター切替・指示キャプション切替・閉じるの小さな操作バーを出す。Escape で閉じる。描画タブのキャプションアイコンは指示キャプションを切り替える。横書きのキャプションは、通常の Canvas ビューでは描画タブに対して左右 10% の余白を取り、そのタブの内側で切り取られる。プレゼンテーションモードではウィンドウに対して左右 10% の余白を取る。日本語を含む詞書きには、両画面の操作バーに「横書き／縦書き」の選択を表示する。縦書きは上から下・右から左に読み、改行と強調表現を保持する。長い縦書きの詞書きは枠内でスクロールできる。初期値は横書き・左で、日本語を含まない文章は選択値を保持したまま横書きで表示する。設定モーダルの「その他」にある「詞書きの表示位置」で左／右を選び、縦書きの配置と横書きの文字揃えに適用する。**キャプションが表示するのは利用者に向けた元の指示文であって、内部で補強された Stage 1 プロンプトではない** — 感情ヒントやシステムプロンプトの素材をプレゼンテーションのキャプションから締め出すためである。

履歴 DB は、Web UI・`inku-cli`・Android のヘッドレス CLI・その他の API クライアントが保存した描画の正本であり続ける。Web UI は、ログイン中の利用者が最新の非フィルタ履歴を見ているあいだ、最新の通常履歴ページを定期的に読み直す。ブラウザウィンドウが焦点を取り戻したときや、隠れていたタブが見えるようになったときにも読み直す。これにより CLI が保存した描画が手動の再読込なしに履歴ストリップへ現れ、現在選ばれている履歴項目はまだ在るかぎり保たれる。**スターのみの履歴・検索結果・古い履歴ページを見ているあいだ、また履歴要求が実行中のあいだは、UI が履歴を自動で置き換えることはない。**

PNG 書き出しの選択肢は、設定モーダルの書き出しタブでユーザーごとのテンプレートとして管理する。各テンプレートは名前・説明・y 軸の高さ（ピクセル）を持つ。既定のテンプレートは `PNG 1080px`・`PNG 2160px`・`PNG 4320px`（保存済みの旧既定 `1024px` / `2048px` は自動で置き換わり、利用者が手を入れたテンプレートは保たれる）。ステータスバーの PNG メニューはこれらのテンプレートから生成し、書き出しの幅は現在のキャンバス比から計算する。

履歴管理の「アニメーション」は、2作品以上の選択時に出力モーダルを開く。設定の書き出しタブ「複数作品のアニメーション」の値を初期値として、形式（APNG／GIF）、切り替えパターン、表示秒数、解像度と任意の高さを今回の出力用に変更できる。対応ブラウザでは保存先パス指定ボタンからフォルダを選択でき、「保存」を押すと選択作品を古い順で書き出す。モーダル内の設定・保存先の変更は既定設定に保存しない。保存先の指定がない場合は既存の保存先設定に従い、フォルダ選択に非対応のブラウザではブラウザのダウンロード設定を使う。今回指定したフォルダへの保存失敗はモーダル内に表示し、別の保存先へ自動で切り替えない。

系譜タブの「アニメーションを書き出す」も、2作品以上のチェック時に同じ出力モーダルを開く。ボタンを押した時点でチェックされている作品を対象として保持し、古い順に書き出す。チェックされていない祖先や現在表示中の作品は自動で追加しない。

---

## 8. 選択のコストと創造のバランス

### 8.1 問題

「たいていの人にとって選択はコスト」だが、「創造は選択の連続」でもある。DDLはこのバランスをどう取るか。

### 8.2 方針

**軸1: 選択の粒度**
- ユーザーに委ねるのは**粗い選択（意図のレベル）**
- 細かい選択（パラメータ）はLLMと揺らぎに委ねる

**軸2: 選択のタイミング**
- 事前選択（記述を書く）を最小化
- 事後選択（複数の出力から選ぶ）を中心にする
- 比較対象がある選択はコストが低い

### 8.3 具体設計への含意

記述後に複数バリエーションを同時生成し、ユーザーが選ぶ or 記述を変える or 再生成する。「白紙から作る」ではなく「並んだものを見る」に選択コストを下げる。

### 8.4 事後選択の実体化 — 二段の再生成（v1.52）

再生成は二段に分かれる。どちらも既定の決定性を壊さず、明示操作でのみ変わる。

| 段 | 名称 | 変わるもの | コスト |
|---|---|---|---|
| 演奏 | 別の演奏 | performance seed による領域・関係・配置位相の解決（§13.8 / §14.4） | LLM 呼び出しなし（再レンダリングのみ） |
| 構図 | 別の構図 | composition seed による Stage 1.5 の焦点選択と、作者が明示したかたむきの具体角度選択・隅の四候補選択（§12.11 / §18） | Stage 2 の1回（保存済み正規化 DDL は不変） |

別の構図が選び直すのは閉じた六つの焦点候補と、記述にかたむきがあるときの具体角度である。Stage 1.5 transformation自体はfocus-onlyを保ち、角度の数値化はStage 2 consumerが同じ`composition_seed`から行う。構図族、技法、色、タッチ、relation、要素数を発明・再選択してはならない。別の演奏と明示変奏は確定した角度を保つ。明示変奏は、強度（小・中・大）と variation seed が揃ったときだけ焦点軸を動かし、不完全な指定は変奏なしとして扱う。記述、正規化 DDL、明示属性は変えない。

この二段が §8.2 の「事後選択を中心にする」の実体である。分散の広い生成系では外れも増えるが、外れの処理は governor による事前の平均化ではなく、並んだものから選ぶという人間の行為に委ねる。選ぶことは記述を推敲することと並ぶ創作の一部である。品質の最終判定もこの事後選択に属し、judge metric は受け入れゲートではなく回帰検知の参考値として扱う。

**UIラベル方針**: SPEC と内部設計では、記述 → 楽譜 → 演奏という音楽メタファーを維持する。一方、主要な操作ボタンでは、初めて触るユーザーが押した結果を予測しやすいように、メタファー語を直感的な操作語へ置き換える。UI上では `演奏` を `タッチ`、`構図` を `配置`、`解釈` を `読み取り` として扱う。現在画像から候補を作って選ぶ操作は Canvas 側の `推敲` タブに集約する。

系譜の各辺を単一の介入として説明可能にするため、推敲要素はタッチ・配置・読み取り・色カタログ・変奏（§12.13）の5種類から一度に1種類だけを選択する。変奏を選択したときだけ強度（小・中・大、既定は中）をラジオ直下に表示し、1案は新規seed 1つ、4案は新規seed 4つの候補を生成する（独立した変奏セクションと専用ボタンは持たない）。タッチでは利用者が託す言葉から同じ seed が決まるため、1案だけを生成する。

推敲要素の選択は前回値をブラウザに記憶する。UIはラジオ式の排他的選択とし、単一選択である旨を明記する。読み取りは一つの上流介入として扱い、その結果として配置とタッチを下流工程で再生成する。

1案または4案は、選択した同一要素だけを変えた候補として生成し、候補は2列（1案のみ全幅1列）でダイアログ内に収めて表示し、選択したものだけを通常履歴へ保存し、保存だけではスターを付けない。タッチは 1 案だけである。保存操作は未保存・保存中・保存済みの3状態を区別し、保存済み候補は再保存できない。

候補生成中は他の生成・描画操作を禁止し、開始3秒後から共通デザインの停止ボタンでAPI要求を中断できる。進行表示は実際の生成対象を示す。読み取りを含む候補は画像hoverで正規化DDLを表示する。

`render_seed` / `composition_seed` はJavaScript safe integer範囲の独立乱数とし、初回生成時から履歴・候補・再生へ引き継ぐ。タッチ候補は利用者が託す言葉から render seed を決め、同じScoreの配置を維持しながら表示上の質感を変える。

色カタログ変更は親作品のDDL・Score・キャンバス・配置seed・render seedを固定し、現在とは異なるcatalog IDだけを適用する。4案では可能な限り異なるカタログを使う。色以外の推敲は、次の描画設定ではなく親作品の実使用カタログとキャンバスを継承する。色変更は系譜の `catalog_change` として変更前後のcatalog IDを記録する。

詞書の表示状態、横書き／縦書き、左／右の選択はユーザー設定としてDBへ保存し、通常表示とプレゼンテーションモードで共有する。推敲タブ内の調整／モデル比較で前後の作品へ移動するときはサブタブ文脈を維持し、対象作品だけを切り替える。

調整候補は生成元の作品に属する一時状態であり、履歴・系譜・近い作品・前後移動から作品を明示選択した場合、または新規生成・DDL描画へ進んだ場合は破棄する。調整／モデル比較のサブタブ切替だけでは候補を破棄しない。対象作品の変更時は、調整候補に加えてモデル比較結果、読み取り差分、再現描画エラー、系譜の中間作品通知と取得状態も同じ対象依存状態として初期化する。進行中のモデル比較は中断し、系譜取得は最新要求だけを反映する。

モデル比較は Canvas 側の `推敲` タブ内に `調整` と並ぶサブタブとして配置し、judge値を表示しない。比較モードは `Stage 1/2共通`、`Stage 1固定 + Stage 2比較`、`Stage 1比較 + Stage 2固定` の3種類とする。共通モードでは選択モデルを両Stageに使う。固定モードでは固定側を1モデル、比較側を最大4モデル選ぶ。対象作品と同一のStage 1/2組み合わせだけを禁止し、禁止理由をfloating tooltipで示す。対象作品のモデルでも、固定側との組み合わせが対象作品と異なる場合は比較側で選択できる。比較対象はユーザーが明示的に選び、未選択モデルをfallback実行しない。対象作品変更時は古い比較結果をクリアし、進行中の比較要求も中断する。結果カードは実際に使用したStage 1/2モデルを記録し、採用またはスター付きで履歴へ保存できる。

通常生成のStage 1 / Stage 2はLLM処理として扱い、画像入力を読む処理はVisionとして別のユーザーモデル設定を持つ。モデル選択ダイアログは `Stage 1/2`・`Stage 1`・`Stage 2`・`Vision` を分け、管理者のモデル設定も各モデルのLLM/Vision用途を明示する。`GET /api/models` は旧CLI向けのLLM `catalog` を維持しつつ、`llm_catalog` と `vision_catalog` を返す。奥書は、通常のVision既定値から初期化される奥書専用モデル選択をユーザーごとに保存し、次に奥書を開いたとき復元する。APIまたはCLIの明示モデル指定は互換性のため優先する。

各モデルは、用途（LLM/Vision）、用途別の5段階推奨度（v1.98 で LLM 用と Vision 用に分離。旧単一値は読み取り互換のみ）、日英の評価コメント、実測値に基づく速度区分と速度ラベルを持てる。**推奨度は用途に加えて段でも分かれる** — 段ごとに測ったモデルは Stage 1 用と Stage 2 用の値を持ち、これは用途の値を置き換えるのではなく狭める。段の値を持たないモデルは両段とも用途の値を読むので、通しで測ったモデルの表示は変わらない。

管理者はモデル設定でこれらを編集し、設定時とユーザーのモデル選択時にはマウスオーバーで確認できる。**段ごとに測ったモデルのマウスオーバーは推奨度を 2 行に分けて示し、通しで測ったモデルは 1 行のままとする** — 通しの値を 2 行に複製すると、行っていない計測があるように見えるためである。Vision は段で分けない。

速度は計測時点の観測値を示す診断情報であり、恒久的な性能保証や生成品質の受け入れゲートにはしない。**接続先は速度を開発者モードでのみ示すよう指定できる（v2.9.5・v2.9.8）** — 実行環境が一台の観測に依存しており、リリースが約束できる値ではない接続先がそうである。この隠蔽は表示層だけで行い、保存内容と実行するモデルは変えない。

モデル一覧の表示順は、提供終了（EOL）を末尾、次にその場の用途と段の推奨度降順、同点はラベル昇順とする（v1.98）。Stage 1/2 共通の選択では二つの段の低い方を用いる。提供終了モデルは選択不可の印を付けてカタログに残置し、削除しない（過去作品のモデル参照を保全する）。

**選択不可の理由は 2 つある — 提供終了と、提供元の有料プランを要すること（v2.9.8）。** 後者は提供元の一覧に現れない（一覧には載るが叩くと拒否される）ため、**一覧を取り直しても印を外さない**。提供終了は一覧が反映するので取り直しで外れる。この違いは、印の出所が一覧か実測かの違いである。サーバーは EOL モデルへのリクエストを拒否せず、プロバイダ由来の失敗を種別（モデル提供終了・認証・流量制限・その他）として分類し説明表示する。

通常生成だけでなく、画像入力を扱わないバッチは現在のStage 1/2を表示し、Visionを含まないモデル選択ダイアログを開く。デモは指示文生成用LLMと描画用Stage 1/2を別々に選択し、奥書はVision一覧を接続先別カードで選ぶ。これらのカードでも同じ評価メタデータをマウスオーバー表示し、ツールチップはテーマに依存しない高コントラスト配色とする。

系譜カードの作品メニューは、見出し「作品を編集する」の下に、描画要素、記述、DDL、モデル、AIに自律推敲させる、ゴミ箱への移動をこの順で提供する（項目名は対象語のみに短縮する）。比較系の2操作が開くダイアログのタイトルは「描画要素を編集」「モデルを編集」とする。記述編集とDDL編集は選択作品の内容を入れたモーダルダイアログで開き、描画結果をそれぞれ `description_edit` / `ddl_edit` の子作品として保存する。描画後は系譜表示へ戻り、最新の子作品をfocus nodeとして祖先とともに自動表示する。二つの比較操作は選択カードを対象作品として既存の推敲サブビューをモーダルダイアログで開き、独立した比較実装を持たない。ダイアログを閉じると元の系譜表示へ戻り、上部の通常推敲タブは従来のパネル表示を維持する。旧手動推敲モーダルへの入口は提供しない。ゴミ箱操作は他の比較操作と視覚的に区別し、操作結果を明示する高コントラスト表示とする。

---

## 9. 「最初の一筆」の設計

### 9.1 要件

- インスピレーションを最初の一筆にできること
- その一筆が十分に満足の行くフィードバックを生むこと
- 偶然性が高すぎず、補完が行きすぎず、しかし単なるトレースでもないこと

### 9.2 出力のバランス

各Stageの補完、エラー訂正のバランスの重要性。

```
偶然性が高すぎる    →  自分の意図が見えない  →  やる気をなくす
補完しすぎる        →  自分が作った感がない  →  意義を見出せない
単なるトレース      →  DDLである必要がない   →  意義を見出せない
```

バランスが正しい位置にあるとき：**自分が書いた言葉が、予想より少しだけ賢く実現される**。その「少しだけ」が続きを書きたくさせる。

記述欄は短歌的な短さを支えるため、非強制の長さ目安だけを持つ。（boxに中を表示はするが強制ではない）日本語では31字前後、英語では12語前後をひとつの目安とするが、入力は一切ブロックしない。長い記述を否定する文言や評価表示は出さず、数字のカウンタと淡い濃度変化だけで、型の存在を静かに示す。

### 9.3 最初の一行

「何を描くか」ではなく「何が心に留まっているのか」を書くもの。そこからLLMが、DDLを引き出す。

---

## 10. 品質・エラー対策

### 10.1 典型的なエラー

1. トークンが長すぎる（入力の問題）
2. 生成されたJSONにエラー（変換の問題）
3. 指示に相当する描画処理が生成できない（表現の問題）

すべて「記述とスキーマの距離」から来ている。記述がスキーマから遠いほど、LLMの解釈が必要になり、失敗確率が上がる。

### 10.2 制約のレイヤー

| レイヤー | 対策 |
|---|---|
| Layer 1: 入力制約 | 記述の語彙・文法・長さを制限 |
| Layer 2: 変換制約 | システムプロンプトでスキーマ厳守を指示、Few-shot examples |
| Layer 3: 出力制約 | Sanitizerで JSON エラーを自動修復 |

### 10.3 制約設計の本質

制約を厳しくすればエラーは減るが表現の自由度も下がる。制約を緩くすれば表現は豊かになるがエラーが増える。
DDLの制約設計は**「どこまでをシステムが保証し、どこからをLLMの揺らぎに委ねるか」の境界線を引くこと**である。

### 10.4 補修と無発明

coerce は記述と typed meaning に明示された内容を Score へ届けるための限定的な delivery / safety 境界である。新しいアクセント、近接反応、消失痕、視覚的事件、構図の支点、relation、色、形を発明しない。

無効値や解決不能な関係は、意味を推測して補わず、警告付きの drop、明示的な failure、または読み取り互換の経路として区別する。補修を品質の底上げや発火率の floor に使わず、同じ定型部品が現れる経路を作らない。

Lock検証済みStage 1.5からactual Scoreへ下ろす共有境界は、旧StopとOmitAndContinueの入力を受けるが、recoverableな意味エラーでは同じ局所回復を使う。元meaningを削らずexecution projectionだけを縮め、appearance field、source instruction、Macro Emit / subtree / invocation、Ground、coordinated group、relation instructionの実際の省略単位をsource / generated ownerとspan付き診断へ残す。recoverableなrelation失敗はerrorを記録してrelationだけを外し、描画可能なmemberとgroupを残す。全単位が省略された場合と、owner / focus joinまたはhost contextの整合性が壊れた場合は停止する。どの入力もLLM、推測、clamp、index再圧縮によるrelation再解決を使わない。


---

## 11. テスト戦略

### 11.1 評価軸の分離

| 機械判定 | 人間（またはLLM）判定 |
|---|---|
| JSONがvalidか | 意図を反映しているか |
| 全primitiveが実装済みか | 芸術的に面白いか |
| トークン長が範囲内か | 揺らぎが適切か |
| レンダリングが完了するか | — |

CLI の judge metric（`visual_event`、`negative_space_pressure`、`motion_energy` など）は、急な品質崩壊や実装回帰を見つけるための診断値である。Build 448 で JP #23 のように低い `visual_event` と高い人間評価が乖離する例を確認したため、これらの指標を最終的な作品評価や受け入れゲートとして再調整しない。品質の最終判断は §8 の事後選択、すなわち人間が並んだ作品から選ぶ行為に属する。

### 11.2 評価の層

品質は複数の層で評価する。

- API・DB・schema・composer・interpreter・renderer・決定的フォールバック挙動のバックエンドテスト
- フロントエンドの Svelte check と本番ビルド
- CLI によるベンチマーク生成
- 保存されたベンチマーク要約とコンタクトシート
- 生成された SVG / PNG の目視確認
- 不正・曖昧・感情的・会話的・矛盾した指示によるストレステスト

### 11.3 ベンチマークが見るもの

- Stage 1 が入力の文脈を丸ごと保つか
- Stage 1.5 が明示意味を保ち、焦点以外を発明しないか
- Stage 2 が DDL 要素をすべて JSON Score へ運ぶか
- 決定的フォールバックが講評に足る量の DDL 内容を保つか
- renderer が DDL の特徴を可視にするか
- 出力に十分な余白・揺らぎ・芸術的な焦点があるか

現行の render core 調整は、CLI ベンチマーク要約の作品ごとに明示の品質指標を記録する — `constraint_adherence`・`negative_space_pressure`・`motion_energy`・`color_resonance`・`visual_event`・`figurative_risk`。これらの judge metric は退行センサーであって、最終的な受け入れゲートでも人間の選択の代替でもない。Build 448 で機械採点と人間の講評の乖離（とくに JP #23）を確認したので、好みの作品を高く出すために指標を再調整してはならない。フォールバックの使用・サーバーのハードタイムアウト・モチーフのヒント・存在数・色の痕跡・構図マーカーは別に記録する。待ち行列や再試行の時間は診断専用で、主要な品質指標としては扱わない — 無料の推論エンドポイントは外部の待ち行列の挙動に支配されうるからである。

NVIDIA の無料 API を試すときの所要時間も同じく運用メタデータとして扱い、芸術的な品質の信号としては扱わない。待ち行列の遅延はサービスの混雑を示しうるが、成功した作品を美的・構造的な講評から除外する理由にはならない。

**現在の実装状況の棚卸しは 2026-07-28 に [実装状況](docs/spec/implementation-status.ja.md) へ移した**（2026-08-02 から日英の対で維持し、日本語が正本である）。

### 11.4 テスト計画の履歴

完了済みの PoC、初期自動テスト計画、モデル名、着手順は [CHANGELOG.ja.md](CHANGELOG.ja.md) と [公開履歴アーカイブ](docs/history/changelog-v0.1-v1.71.ja.md) に置く。現行の検査層と受け入れ境界は §11.1〜§11.3 を正とする。


---

## 12. 二段階変換アーキテクチャ

現行パイプラインは、任意の Stage 0.5、Stage 1 の有限 typed normalization、決定的な Stage 1.5、Stage 2 の閉じた Score 化、Renderer の演奏から成る。本章は現在の各段の authority と互換境界を記す。

### 12.1 二段階変換の採用

DDLの変換パイプラインは**二段階変換**を採用する。一段階変換は採用しない。

```
ユーザー記述
    ↓ 第一段階：解釈
正規化DDL（コア語彙のみで表現された中間表現）
    ↓ 第二段階：構造化
JSON Score
    ↓
SVG
```

### 12.2 一段階変換を採用しない理由

記述とDDL生成の間に、明確な切断面を作ることで、想定外の記述からの想定外の意味の流入（例：「美しい」のニュアンスが、JSON生成時にengineに影響を与える）を、構造的に抑止する。

また、現在のLLMの性能要件を考慮して、LLMに渡す仕事を1種類とすることで、精度を向上する。

**仕事1: 解釈（意味論的）**
自由な自然言語の曖昧な表現を、DDLの語彙空間にマッピングする

**仕事2: 構造化（構文論的）**
primitive、region、weight、variation などのフィールドを持つ、スキーマに合致するJSONを生成する

この二つは求められる能力が根本的に異なる：
- 解釈は**創造的・連想的**な能力
- 構造化は**機械的・規則遵守的**な能力

一つのプロンプトで両方を高水準で要求すると、どちらも中途半端になる。特にコーナーケースでは、解釈の難しさが構造化エラーを誘発する（解釈に迷ったLLMがJSON形式も崩す連鎖）。

既存のテストからも、一段階変換ではコーナーケースを実装しきれないことが観察されている。

### 12.3 DDLコンセプトとの整合性

二段階変換は、DDLの哲学と構造的に一致する。

SPEC Section 5 の三層パイプラインに二段階変換を組み込むと：

```
記述（母語・自由な言葉）
  ↓ 第一段階：解釈
正規化DDL（コア語彙のみ）          ← ここが「霧が払われる瞬間」の実体
  ↓ 第二段階：構造化
楽譜（JSON Score）
  ↓
演奏（SVG）
```

「記述 → 正規化DDL」の段階こそが、記述者自身に自分の意図を可視化させる場面である。「佇ませる」のような曖昧な言葉が、「中心付近に、細い線で、わずかに揺らぎを与えて置く」のようなコア語彙に分解される。この分解が記述者にフィードバックされることで、自分が何を書いたかが初めて見える。

短歌で言えば、自分が書いた一首を他者が読み解いてくれる感覚に近い。読み解きと自分の意図のズレが、次の記述を生む。

### 12.4 正規化DDLの形式

第一段階の出力である「正規化DDL」の形式は、以下の設計方針で決定する。

**方針: 自然文のリズムを保ちつつ、コア語彙に限定する**

```
正規化DDL（例、実コーパス形式）:

  中心に鉛筆の細い線をひとつ置く。線は細かく揺れる。
```

Typed DDL compilerでは、この例の第二文は第二のdrawable entityを作らない。`は` / `が`、または意味同等の英語determinerを伴うcanonical headが、一意な先行entityを再導入するとき、後続predicateを同じentity / instructionへ結ぶsource-preserving continuation edgeとなる。Target候補がない、複数ある、clause境界が不明瞭である、またはunknown / conflictを含む場合はtyped issueとしてfail closedし、first / nearest / lastで推測しない。

Continuationはreintroduced head、subject marker / determiner、predicateの正確なsource spanとclause provenanceを保存する一方、canonical semantic bytesにはlocalized surfaceを含めない。Headとmarkerはcontinuation syntax、predicateの明示modifier / actionはtargetのstructured fieldとしてそれぞれexactly once配送され、元のquantity、position、relation、Ground、MacroInvocationを作り直さない。既存relationの`previous_one` / `previous_two`は明示relation edgeのtargetであり、このmarked-subject continuation targetとは別である。これはJSON Scoreより前のvisible typed semantic graphである。後節にあるJSON Score例はこのgraphそのものではなく、Score / Rendererへのloweringとdefault裁定はStep 10 gateの責務であり、本規則はそれらを開始しない。

たとえば`赤い円を中心に置く。`と`円を中心に置く。円は赤い。`は、同じ対象と明示指示へ一意に解決されるなら同じsource-independent canonical meaningを持つ。前者のinlineと後者のcontinuationのsource span、rhythm、continuation edge / target、binding、provenanceはそれぞれ保存され、full compiler-lock attestationは一致しなくてよい。

**却下した選択肢:**

| 形式 | 却下理由 |
|---|---|
| 完全自然文（「中心付近に、細い線を、わずかな揺らぎで置く」） | 第二段階で再度「解釈」の余地が残る |
| 構造化リスト（YAMLライク） | コードっぽく見える。記述の楽しさを削ぐ。似たようなグラフィック記述言語が存在する |
| 関数呼び出し風（`置く(対象=線, 位置=中心)`） | コードに近すぎる |
| 分離修飾行（「揺らぎ: 小」を独立行で書く初期案） | 実装では採用されなかった。運動語彙は「線は細かく揺れる。」のようにインラインの文として書く（fixture コーパスが正）。例外は面・地の質感で、「面: ...」「地: ...」の固定句だけが行として分離される |

**採用形式の特徴:**
- 自然文のリズム（短歌的な読み心地）
- 語彙はコアに限定（「置く」「細い」「中心」など）
- 運動語彙はインラインの文、面・地の質感のみ「面:／地:」の固定句で分離
- 日本語版と英語版でフォーマットの構造を共通化
- **記述者の目に触れる前提で設計する**（解釈フィードバックUIで表示される）
- Stage 1が記述から素材を解釈した場合は、その選択をvisible normalized DDLへ明記する。入力が明示した素材は保持する
- 記述者がdirect DDLを書いた場合、または生成DDLを編集した場合は、てざわり等の省略を許容してtyped meaningを`unspecified`のまま保持する。Texture / context、primitive type、語順、現行Score defaultからhidden推測または挿入しない
- 図形の大小は普通 / 小さい / 大きいと弱・標準・強を組み合わせた有限7classの局所modifierとして記し、明示normalと省略を区別する。数値geometryとqualitative sizeの併記、unknown degree、曖昧なownerはtyped conflict / issueにする
- ビュランとドライポイントはvisible DDLが明示した場合だけexplicitとなる。Stage 1 few-shotの品質方針とdirect DDL compiler semanticsを混同しない
- 現行actual Score lowererは、数値位置、またはverified Stage 1.5のdirect instruction ownerへ解決済みの元`place:center`と、place actionを持つcount1 circle / square / ellipse / cloudformだけで、作者裁定済みのnormal geometry・大小倍率・描画属性省略をresolutionとして適用する。Named経路は寸法を保ったままeffective focusを`at.region`へ置く。旧Stop / OmitAndContinue入力にかかわらず、recoverableな対象外意味やpalette context不足は独立fieldまたはtyped実行単位だけを省略して残存Scoreと診断を返す。両modeとも元meaningを変更せず、このRust経路は製品runtimeにはまだ接続しない

### 12.5 モデル分割

段階ごとに異なるモデルを使える。**現行実装は Stage 別のモデル選択制**であり、ユーザー・管理者が Stage 1 / Stage 2 / Vision の各用途にモデルを設定できる（§8.4 のモデル設定・モデル比較、`/api/models` の llm/vision カタログ）。

初期設計時の想定（Stage 1 = 高能力モデル、Stage 2 = 軽量モデル）は方針として維持される:

- 解釈（Stage 1）は連想的・創造的でニュアンス理解が必要、構造化（Stage 2）は入力が制限されるため軽量モデルでも安定する
- 「モデル選択そのものが創造的変数」という原則と、実用的なコスト構造を両立する

### 12.6 第一段階（解釈）の設計

Stage 1 は自由記述を、書き手が観察・編集できる正規化 DDL へ有限に写す。原文の明示要素・数量・色・素材・関係を保ち、隠れた視覚要素や「美しい」解釈を追加しない。語彙、閉じた schema、制限値、出典をプロンプト lock として渡し、出力はその lock の内側だけを使う。これは I-640 で同期した有限 typed normalization 契約であり、特定のモデル名やモデル階級を正本にしない。

### 12.7 第二段階（構造化）の設計

Stage 2 は effective DDL / typed meaning を閉じた JSON Score schema へ構造化する。色、素材、数量、運動、配置 path、回転、canvas、明示 relation を保ち、届かない明示要素は黙って別の意味へ変えず失敗として扱う。語彙と relation の対応は Saijiki と typed lowering の正本から導出し、履歴上の prompt sketch を現行契約にはしない。

Lock検証済みtyped経路では、Stage 2 consumerの失敗方針をStop（既定）またはOmitAndContinueとして明示する。Continueは届かない意味をScore fieldへ変換せず、execution projectionからtyped単位を省略し、残った命令と元owner順序を返す。結果は完全成功、省略付き成功、停止を区別する。

作者が明示したかたむきは、元meaningとtag付き`composition_seed`、logical occurrence、angle identityに束縛した共通resolverで、direct instructionとflat Macro Emitから一度だけ`Score.rotation`へ届く。Stage 2はeffective focus、variation seed、render seed、source spellingをこの選択へ混ぜない。

### 12.8 エラー回復戦略

各 LLM 段は、空・短すぎる・schema 不適合の応答に対して理由を明示した再試行を一度だけ行う。再試行後も使えない場合は別モデルへ切り替えず、決定的フォールバックで有限に完了するか、明示的に失敗する。フォールバックは DDL の明示要素を配達するための互換経路であって、新しい内容を補う経路ではない。

応答と保存履歴は Stage ごとのフォールバック理由、使用モデル、provider failure の分類を保持し、UI は発生した層を示す。`interpret_fallback` / `compose_fallback` は理由、`"none"`、欄導入前の未記録を区別する。印のある親から推敲するときは実行前に一度確認し、既存作品へ遡及して値を書かない。

Runtime未接続のshared compiler consumerでは、StopとOmitAndContinueはLLM fallbackではなく同じverified inputへ適用する決定的な実行方針である。Continueはappearance fieldを既存defaultへ戻せる場合だけfield単位で省略し、成立しないinstruction / Emit / call / structural subtree、Ground、group、relationをそれぞれのtyped単位で省略する。整合性不良は両modeで停止し、全省略を空の新作成功として扱わない。

### 12.9 実装史の所在

逆順実装、初期 prompt、完了済み Phase の記録は [CHANGELOG.ja.md](CHANGELOG.ja.md) と [公開履歴アーカイブ](docs/history/changelog-v0.1-v1.71.ja.md) に置く。本節は新しい実装順序を開始しない。

### 12.10 レイテンシ対策

`POST /api/paint/stream` は `sketch`（写生層が動いた場合）、`stage1`、`score`、`done` の順に有限な進行を知らせる。`stage1` は正規化 DDL と診断 metadata を先に表示でき、`done` は通常応答を返す。保存済み作品の「別の構図」と「DDL から描画」は保存済み DDL から再開し、Stage 1 を呼び直さない。独立した Stage 1 キャッシュや将来の並列化を現行契約には含めない。

### 12.11 中間フィルタ（Stage 1.5）

Stage 1.5 は LLM を使わない決定的な typed transformation である。入力は lock 検証済みの `CanonicalReady` typed meaning とし、自由 prose は受け取らない。出力は Stage 2 が読む effective DDL / typed meaning である。

- 原文、正規化 DDL、元の typed meaning、effective meaning、source / generated provenance を別々に保ち、元の意味や明示属性を上書きしない
- 新しい sentence、entity、relation、technique、color、touch、primitive、content を発明しない
- `place:center` だけを閉じた六つの焦点候補の一つへ写す。その他の place と明示属性はそのまま通す
- verified viewをactual Scoreへ下ろすときは、direct `Instruction { instruction_index }`は元のtyped instructionと同じindexのinstructionだけを所有する。direct coordinated groupはその規則を変えず、別の`placement_groups`範囲としてmemberを配送する。`GroupPredicate` / `MacroEmit`を同じindexのownerとせず、数値位置をfocus targetにせず、元centerを仮の`0.5,0.5`へ書き換えない
- baseline のfocus選択はlockで検証されたpre-expansion meaning digest、expanded meaning digest、attested optional `composition_seed`に束縛する。seedの不在と`Some(0)`の存在は別であり、full compiler-lock digestはsource integrityのattestationであってfocus材料ではない
- 明示noncenter placeはfocus targetへ加えず、Stage 2が§18の領域へ解決する。隅の四候補選択も構図側の責務で、元meaningとattested optional seedおよび元logical occurrenceを使う。
- 明示angleは元のtyped meaningのまま通し、center-only target集合や変奏軸へ追加しない。具体角度はStage 2が同じverified pre / expanded meaning、tag付きoptional `composition_seed`、directの元logical ordinal、またはMacroのsemantic ordinal / expansion path / generated ordinalから選ぶ
- Stage 1.5の入力を切り離す前に、実際のvisible DDLのUTF-8 bytes、semantic source occurrenceに残る言語証跡、未使用分を含む全macro sidecarの三項、実行macroのresolved / binding / semantic head identityをcompiler lockと照合する。SourceOccurrenceがない入力へ新しい言語条件を課さず、未使用sidecarにresolutionや実行を要求しない。Sourceとprovenanceは入場時のintegrity証拠であり、meaningやfocusの材料ではない
- 明示変奏は amplitude（`small` / `medium` / `large`）と `variation_seed` がともにある場合だけ完全であり、焦点だけを動かす。不完全な指定は変奏なしとする
- output の canonical bytes、schema identity、digest、provenance は同じ意味を再現し、別 schema の bytes を同じ identity と偽らない

sealed Rust Stage 1.5 v5 のtyped foundationとR1 / R2 / D1、direct instructionのnormal / explicit geometry、finite flat Macro Emit、および両者へ共通の局所回復error policyはactual Scoreまで実装済みだがruntimeには未接続である。`compile_ddl_to_score` facadeは元の`NormalizedDdlDocument`を一度だけcompileし、そのsource / state / lock / issuesを保持する。旧StopとContinueの入力は、同じcompilationのtyped owner / dependencyに従うsealed projectionを使う。回復可能な上流hole / conflictは確立済みの局所単位を省略して独立命令を届け、描画単位の全省略はstoppedとする。Canonical pre-meaningでは成功済みmacro outputを元binding / source ordinal / semantic ordinal / seed / provenanceのexact subsetとして再利用し、再seed・再展開しない。NonCanonical pre-expansion projectionでは省略単位を先に確定した後、一度だけseedを導出して展開し、local failure後のretry drawを行わない。Global budgetおよびsource / lock / owner / definition / provenance整合性不良は両modeを止める。Public Stage 1.5 APIは`CanonicalReady`専用のままで、任意のmutable compilationを回復しない。D1のmeaning / seed / focus、source ordinal欠番、generated provenanceは保ち、寸法規則の追加はgeometry policy digestへ記録し、Score 0.2.0で新しい月形を表す。現行Python経路のcoerceやLLM fallbackが置換済みとはみなさない。Runtime / UI / API / 保存接続は後続の責務である。

このruntime未接続subsetは、directとflat Macro Emitのangleをcircle / ellipse / cloudform / square / triangle / polygonのactual `Score.rotation`まで共有lowererで配達する。Squareもdirectとflat Macro Emitで同じangle resolverを通り、numeric配置だけは回転した宣言矩形をmust-fitし、named focusはmust-fitを追加しない。この到達はwhole Step 10の完了ではない。

同じruntime未接続subsetは有限な二段階のthinnessをdirectとflat Macro Emitからactual
`Instruction.thinness`へ届け、明示宣言した細さ・大小parameterも§4.6の経路へbindingする。
この到達だけでwhole Step 10を完了とはしない。


全幅・半幅はキャンバスの横幅の100%・50%を回転前の寸法へ適用する。線は長さ、開弧は弦の長さ、閉じた図形は基準輪郭の横幅、雲形は宣言幅を使い、元の形と縦横比を保つ。回転後の横占有幅や筆致の外縁から再計測せず、端への接触や位置移動を追加しない。通常DDLと宣言済みflat Macro Emitの`proportion_width_extent`は共通の寸法解決を通る。

半円は上へ膨らむ半円の開弧、上弦は右、下弦は左へ膨らむ半円の開弧とする。三日月は歳時記の細い月形の閉じた塗り面であり、一本の開弧に置き換えない。Score 0.2.0の`primitive: arc`、`arc_form: crescent`と`center`・`size`がその輪郭を表す。月形の基準は歳時記の三本の三次Bezier曲線で、寸法は曲線の実際の境界に基づく。省略された`arc_form`は従来の開弧の意味とcanonical bytesを保ち、保存済みScore 0.1.0を読み続ける。三日月の位置・回転・境界は共通rendererへ渡す。端点を要求するconnected/touchingへ閉じた三日月を渡すと不適合を診断する。

大きさの指定が重なるときは、原文の全候補を保持し、各候補を独立に物理寸法へ解決して小さい幅を採用する。明示寸法が形を指定する場合はその縦横比を一度だけ拡縮し、相対サイズを二重に掛けない。同じ大きさの重複もエラーとして示す。`ConflictingSizeSpecifications`は候補寸法と採用寸法を持ち、処置`Recovered`はStop/Continueの両方でその図形を描くことを表す。この例外は重複サイズだけであり、形の不整合、未対応属性、source/lockの整合性不良を回復可能にしない。これは共通compilerからScoreと診断までの接続であり、現行のPython生成経路やUIへの置換を意味しない。

### 12.12 添景と互換記録

現行生成に添景レベルはない。Stage 1.5 と coerce は記述にない要素を足さず、明示内容を配達する限定修復だけを行う。明示angleの数値解決も新しい添景や視覚要素を足す処理ではなく、元のtyped identityを既存`rotation`へ配達する処理である。過去作品の `history.tenkei` と API の `tenkei` は読み取り互換のため残るが、新しい作品の生成契約には作用しない。導入・廃止の経緯と件数は [CHANGELOG.ja.md](CHANGELOG.ja.md) と [公開履歴アーカイブ](docs/history/changelog-v1.72-v2.4.ja.md) に置く。

### 12.13 変奏（Stage 1.5）

構図の同一性はattested optional `composition_seed`とlockで検証されたpre-expansion meaning・expanded meaningが担う。full compiler-lock digestはsource integrityを検証するattestationであり、同じmeaningの別表現へ同一lockを要求しない。「別の構図」は保存済み正規化 DDL を再利用し、閉じた六つの候補から焦点を選び直し、明示angleがあれば同じidentity材料から具体角度も、明示cornerがあれば専用domainで隅も選び直す。現行入力に `vary_seed` はない。

明示変奏は amplitude（小・中・大）と `variation_seed` の組である。両方が揃った場合だけ焦点を動かし、同じlock検証済みmeaning、attested composition seed、amplitude、variation seedは同じeffective meaningを得る。構図族、色、タッチ、技法、relation、要素数は動かさない。

Score と描画同一性の現行 domain は `rh3` である。`rh2` は保存済み作品を読むための legacy domain であり、新規生成の current identity として書かない。七軸から一軸へ畳んだ履歴は [CHANGELOG.ja.md](CHANGELOG.ja.md) に置く。

### 12.14 Renderer が持つもの

本節は運用面の記録である。**揺らぎが演奏される層としての renderer という概念は §13.8 が持つ**。ここに書くのは、その層の実装が実際に何を抱えているかである。

renderer は JSON Score を SVG へ変換する。視覚的な実体化を持つ。

- 座標の正規化
- 素材ごとの線と輪郭の扱い
- 運動と揺れの実体化
- primitive の展開
- SVG フィルターとテクスチャ効果
- キャンバス比の扱い

現行の標準実装は共有Rust rendererであり、platform-independentなRust crate `core/crates/inku-render`が演奏の正本である。PythonはScore schemaとcoerceの正本、host側canvas/profileの解決、fresh seedの発行、engine registryを所有する。薄い`render_engines/default/adapter.py`は、検証済みScoreと解決済みoptionを1個の正規JSON requestへまとめ、独立した`inku-render-python` CPython wheelを1回だけ呼び、SVGとmetadataを一緒に受け取る。AndroidはKotlin hostでcoerce済みScore、canvas、色map、profile、seedを解決し、薄い`inku-render-android` JNIを同じ粗いrequestで呼ぶ。`renderer.py`はSVGだけを必要とする既存Server callerの互換facadeであり、第二の描画実装ではない。

Rust core内では、host-neutralなrequest/output型と粗い`render`境界から、決定的seed、performance planning、arrangement／placement／relation、純粋な幾何、mark／stroke／surface／support、ground／presence layer／palette、SVG documentへ一方向に依存する。host SDKやPython runtimeへ依存せず、engine identityとrenderer-owned referenceもcoreが持つ。Engine 40のPython実装やruntime fallbackは持たず、過去のEngine 40 corpusは履歴根拠としてのみ保持する。この境界はServerの出力意味論を固定したままAndroidと将来のclientへ同じcoreを渡すportability boundaryである。Android bindingはEngine 42で統合済みであり、Android固有のKotlin rendererへfallbackしない。

SVGからpixelへのpresentationはRender Engineと別の`core/crates/inku-svg-raster` APIが所有する。Androidのmain preview、履歴thumbnail、refinement preview、PNG exportは、保存済みまたは生成直後のcanonical SVGをresource非依存のpremultiplied RGBA8へ変換する。このraster APIの変更は、それ自体ではRender Engineの版を変えず、保存SVGや`rh3`の意味も変えない。

renderer は制御された揺らぎを生んでよいが、**JSON Score の意図は保たねばならない**。各描画は `render_seed` を持ちうる。同じ seed を与えれば再演は再現し、正本の Score は動かない。演奏の 2 つのスケールと render engine の版史は §13.8 と §13.11 にある。

**人・顔・動物・群れのモチーフは、文字どおりの対象としては描かない。** Stage 2 と coerce 層がそれらを `Score.presence` へ変換する — presence の種別・強度・重心・対称性・視線の圧・群れの挙動・輪郭密度である。renderer は presence を、かすかな弧・縁へ寄った焦点・非対称な間隔・輪郭密度の圧として実体化する。棒人間・頭と胴の対・翼や尾の印・同一の楕円の輪といった**固定のシルエットは避ける**。

primitive 語彙は多角形の語のために `polygon` を持つ。五角形や六角形の primitive を個別に足すことはしない — 多角形の意図は `polygon` と `sides=5-8` で表す。運動のエネルギーは、単に個数や密度を増やすのではなく、軌跡・回転・斜めの配置・波の経路・非対称で扱う。

Score の coerce 層は、明示内容のScore schemaへの配送と安全だけを担う。invalid relationの警告付きdropなど有限の処理はしてよいが、visual event、composition anchor、density floor、accent shapeを足してはならない。Rendererの揺らぎは`render_seed`に束縛され、canonical Scoreを変えない。

SVG の書き出しは 3 つのプロファイルを持つ。

- `display`: 既定のサーバー描画 SVG。Web 表示・履歴・PNG 生成・作品の再構築に使う
- `editable`: JSON Score とサーバー所有の色カタログメタデータから要求に応じて生成する。SVG-native editor での編集に向け、安定した ASCII の ID とレイヤー相当のグループを持つ。non-computer の solid fill は実体の base fill と standard SVG filter のむらを保つ
- `compat`: 同じく要求に応じて生成し、定義済みportable subsetに制限する。filter と clip-path を使わない filter-free flat vector fallback で、広い互換性のため一部表現を単純化することがある。Computerはcontour path内のbase field、grille、黒いscanlineを保ち、Oilはclipした幅拡張を使わず既存のfilter-freeなpaint passで形とintensityを保つ。Display / Editableとのpixel一致は約束しない

DB が保存するのは `history.svg` の `display` SVG だけである。編集可能 SVG と互換 SVG は、DB の追加ペイロードとして保存するのではなく**ダウンロード時に生成し直す**。

### 12.15 写生層（Stage 0.5、v2.9.38）

記述と Stage 1 のあいだに置く**任意の層**である。短歌のように密度の高い記述は、Stage 1 が
一度に噛み砕けない。そこで記述を**物の言葉へ写した自然文（写生文）**に変えてから後段へ渡す。

写生文は**記述の代わりに 3 つの消費者へ届く** — Stage 1・プラグイン展開（発動の判断）・Stage 1.5。
**Stage 2 と coerce へは届かない**（v2.9.41）。**この 2 つが読むのは DDL だけ**である —
設計図が出来たあとの層に散文を見せると、散文に遡れる追加と DDL への配達が区別できなくなる。
**プラグインの種（何枚・何本を決める材料）は記述**であって写生文ではない。同じ記述なら、
写生文が変わっても解決される数は変わらない。
**記述そのものは保存と表示に残る。** 作品は作者が書いたものであって、層が書いたものではない。

この段落はcutover前のlegacy runtimeとその歴史的な説明である。新typed pipelineのmacro意味規範とfocus seed sourceは§4.5と§12.11に従い、原文や写生文をtyped macro seed sourceへ戻さない。

**背景の番人を 1 つ撤去した**（v2.9.41）。「利用者が機械生成のプランを記述欄に貼った」ことを
見抜く判定は、判じていたのが**文字列の出自**だったので、記述が coerce へ届かなくなると
判ずる素性が残らない。残すと本番の DDL の普通の形に誤爆する — **本番の濃色 604 件で
54 件が白へ落ち、撤去後は 1 件**である。

**区切りの大きさ（`sketch_grain`）は 2 値**で、`fine`（細かく区切る・既定）と
`coarse`（大きく区切る）を描画のたびに選ぶ。総量ではなく刻み方だけが違う。
区切りを変えて描き直すと、系譜に `sketch_grain_change` の辺が付く（同じ区切りなら再演である）。

**層が落ちたときは記述がそのまま Stage 1 へ流れ、描画は完走する。** 失敗した回を写生文として
記録しない。保存済みの作品は、保存された写生文から描き直す（層を呼び直さない）。

**層が何をしたかは作品に記録される**（`sketch_state`、v2.9.43）。写生文が無いことは
**4 つの別々の出来事**を意味しうるので、状態を分けて書き留める — `fine` / `coarse`（走って
その区切りで写生文を作った）・**`fallback`（走ったが落ちた）**・`off`（使えたが呼び手が
通さないことを選んだ）・`not_applicable`（この経路は層を呼ばない）。
**`NULL` はこの記録より前に描かれた作品だけを指し、「切」の同義ではない。**
既定値を持たず、遡及して埋めることもしない — 埋めれば、層が在る前に描かれたという
唯一の事実が失われる。**状態を名指す関数は 1 つで、保存する経路も応答もそこを通る。**

この層は感情語を出してはならない（設計原則 3・7、§13.3）。写生文が名指すのは物と、その配置と、
その状態である。**したがって正規化 DDL に意味語が現れないことは、搬送の失敗ではなく設計である** —
「夜」は「背景を黒で埋める」として運ばれる。搬送を語の一致で測る検査は、この翻訳を喪失と読む。

### 12.16 記述は作品の出自である（v2.9.44）

記述は記録ではない。**プラグインが発火するか・Stage 1.5 が何を文脈に読むか・プラグインの種・
指示文の言語の 4 つを動かす。** したがって**その DDL を生んでいない文字列を記述の席へ座らせない** —
作者が打った本文が記述であり、記述を後から貼り替える経路を入口は持たない。
既存作品の記述を上書きして描き直す操作（推敲）は別の操作であって、出自の差し替えではない。

ここで述べるprose-driven plugin発動、記述seed、Stage 1.5 contextはcutover前legacy runtimeの説明に限る。新typed pipelineの意味とseedの規範は§4.5と§12.11であり、この説明は原文や写生文をtyped macro seed sourceへ復活させない。

**削ると何も残らない記述は受け付けない。** 行頭の連番と角括弧のコメントは記述者のもので
描画のものではない（v2.9.40）が、**切った結果が空になる記述**は、後段に空文字から主題を
作らせる。描く 3 経路（`/api/interpret`・`/api/paint`・`/api/paint/stream`）はこれを 400 で断り、
**空白だけの記述は 422 で断る**。**判定は 2 条件である** — 生の記述が空であることは別の検証が
既に断っており、切った結果だけを見ると**札を 1 つも持たない文に「札だけです」と答えてしまう**。

**指示書を描く経路（`/api/compose`）はこの番人を持たない。** DDL で書き起こした作品には
記述が無く、記述の無い指示書を描くことがその経路の目的だからである。**記述の鍵は空文字ではなく
欠落として扱う。**

**入口の門番は、描画が読む文字列を読む。** 記述欄の長さ目安は入力をブロックしないが（§7.1）、
**送信は切った後の文字列で判ずる** — 端から端まで札だけの記述は送れない。これは第二の規則ではなく、
描画が使う規則を扉へ移したものである。

---

共通Rustの`plan_verified_stage15[_with_policy]`は、verified Stage 1.5と既存のhost canvas / palette contextから、通常instructionと宣言済みflat Macro Emitに同じobject-size / placement resolverを使う。省略をsourceへ書き戻さず、`line-up` / `scatter` / `tile`の数量省略は解決結果だけで8、`place`は従来の1とする。明示正整数1..u32::MAXを保ち、zero・範囲外・不明・競合・定性的数量や必須Macro引数の欠落を8へ変えない。

Object sizeの基準はcanvas短辺で、count・cell・密度に依存しない。実planはline / circle / ellipse / square / triangle / polygon / arc / cloudform / pointの9shapeへ届く。Normalは幅または直径6/25、ellipse / cloudformの高さは幅の3/5、arcの矢高3/50、pointの直径3/250。既存の全大小倍率とshape固有anchorを保ち、thinnessを外形sizeにしない。例えばlarge circleの直径9/25は4個でも8個でも同じで、重なりを許す。Numeric geometryは元のexact decimal / Rational、basis、dimension、provenanceを保持する。

形状制約はprimitive identityと別のoptional meaningである。正三角形はtriangle、正方形 / 正四角形はsquare、五〜八角形はpolygonを保ち、core-head continuationにも制約と元出典を運ぶ。制約不在の旧canonical / source bytesへnull fieldを加えない。通常三角は上頂点・下底の二等辺でnormal幅=高さ=6/25。正三角は一辺sから高さs√3/2を求め、planにはexact sideと固定規則を保持し、irrationalな高さを有限decimalへ偽装しない。通常四角は既定1:1、WidthHeightを明示すれば既存square wireの独立幅高さへ届く。正方形は等辺を要求する。多角形は正多角形で省略5辺、明示5〜8辺、Radius / Diameterは外接円の寸法である。辺数は図形個数と区別する。

縦長 / 縦に長い / 細長いはtall、横長 / 横に長いはwideとしてtriangle / square / ellipse / cloudformの共有consumerへ届く。数値寸法省略時は長辺6/25×size係数、短辺はその半分。明示WidthHeightは保持して縦横の大小関係を照合し、不一致、regularとの併記、範囲外の辺数は元instruction / Emitの説明付き停止・省略となる。日英の有限構文で「横に長い四角形」「一辺0.24の正三角形」「六角形」、`wide rectangle` / `equilateral triangle`等を扱う。三角・四角のsemantic anchorは物理bbox中心で、Scoreではtop-left＋sizeへ変換する。Polygonはcenter / radius / sidesへ写し、numericの回転後頂点boundsを最後のgeometry境界で確認する。Namedは既存regionとclipping方針を保つ。通常DDLと宣言済みflat Emitは同じresolverを使い、place / count1はactual Score、反復は個体を作らないReady planへ届く。

非Gridのdomainはcanvasの各軸の物理長さで、群の重心をsemantic anchorへ置く。方向省略のline-upは横一列で、幅Wをn分したcellの中央、同じ縦中央に置く式を保持する。TileはW>=Hならcolumns=min(n,max(1,ceil(sqrt(n*W/H))))、rows=ceil(n/columns)、H>Wなら同じ式を長辺のrowsへ適用しcolumns=ceil(n/rows)とする。行優先でn個だけを満たし、rows / columns / cell寸法 / filled countを解決する。Numeric anchorへはfilled prefixのexact重心を平行移動し、named Gridは元region内に置いて重心補正しない。Scatterは矩形のX/Y一様samplingと群の重心をanchorへ移すrecipeだけを持ち、既存performance seedと元owner / instance ordinalを後続materializationへ要求する。Composition seedの代用、乱数実行、fit縮小、個数変更、反発や最小間隔の追加は行わない。例えば1200×800 / 800×1200のnormal circle直径は共に192、4個のline-up間隔は300 / 200、8個のtileは4列2行 / 2列4行である。

配置方向はoptionalなinstruction / Emitの`layout_direction`が所有し、entityの`angle`と独立する。「中央に、横線を縦に三本並べる。」「中央に、斜めの線を横に三本並べる。」と英語のaction-prefix / shape adjective / direction adverbを同じtyped入口で扱う。日本語の「に」のphrase証拠、英語の既存angle rowのadverb形で役割を分ける。Compiler専用parser aliasはprompt・display・legacy markerを変えない。Single-head continuationの方向も元entityへmergeし、競合は停止する。Field不在のcanonical / provenance bytesは保ち、存在時だけ意味と完全な出典を含める。

Line-upだけが方向を配置へ届ける。省略は従来の横一列、明示horizontalは同じ式でも元の明示identityを保持する。t=(i+1/2)/n-1/2としてanchorからのoffsetはhorizontal=(tW,0)、vertical=(0,tH)、rising=(ts,-ts)、falling=(ts,ts)、s=min(W,H)である。Y下向きの物理座標で斜めは45度とし、長方形の対角線へ引き伸ばさない。Bare diagonalはattestされたoptional composition seed（NoneとSome(0)を区別）、元pre / expanded meaning、元logical occurrenceを専用layout-direction roleでframeして二軸から選ぶ。Shape angleの選択scheme・size・countは変えず、focus / variation / render seedやsource spellingを方向選択へ使わない。Pointにも方向は届くがPoint自身のangleは拒否する。Place / Scatter / Tile、group / relationの新方向、rotated等の未対応方向は元instruction / Emit単位で停止・省略し、全省略は両mode停止する。既存Score入口も新fieldを捨てて成功しない。

Planは一instruction / 一Emitにつき一件で、exact count、解決済み寸法・外観・angle・位置・layout式とsource / generated originを持つ。count比例の配列・個体geometry・Score命令複製は作らない。旧Stop / Continue入力にかかわらず、recoverableなblockingは既存のtyped owner / span / 理由 / 実処置を保つ最小fieldまたは実行単位の省略として扱い、残るplanを返す。全省略をReadyにせず、未対応field・relation・coordinationを黙って捨てない。resource-aware materializerはこのPlanをScore 0.10の再演可能なrecipeへ写し、個体配列を作る前にhard policyとcallerが明示許可したoperational budgetの双方で需要を検査する。現行出荷値はprimitive mark合計400、展開後Score templateごとのprimitive mark 240、resolved count 2000、drawable template 64であり、countをclampしない。`logical_objects`、`template_nodes`、`anchor_instances`、`transform_instances`、`placement_instances`、`fill_instances`の追加6次元は明示accountingを持つが、新しい出荷既定値を導入しない。超過した一sourceまたはcoordinated placement全体を個体化前に省略して診断し、独立した後続を続ける。保存Scoreはauthorityのsnapshotを持つが需要の自己申告は持たず、再演時にrecipeから再計算する。既存Score wire / lowering outcome / compiler executionの成功意味とScore 0.9のdefault / legacy互換は変わらない。同じ`inku.geometry-resolution-policy.v1`がこの解決をattestする。製品runtime / UI / API / 保存cutoverとnative受入は未完了である。

## 13. 揺らぎの設計

### 13.1 揺らぎとランダム性の区別

揺らぎ（sway）は単なるランダム性ではない。

- **ランダム性**: 無秩序。何が起きるか予測できない
- **揺らぎ**: 秩序の中の微細な変動。核となる意図は保たれたまま、表面が動く

盆栽の枝の曲がりは揺らぎ。完全にランダムに生えた木ではなく、職人が基本形を決めて、そこから自然が細部を動かしている。短歌の朗詠も揺らぎ。五七五七七という型は変わらないが、声の抑揚・間・呼吸で毎回違う。

DDLの揺らぎは、この意味での揺らぎである。

### 13.2 揺らぎが担う三つの役割

**役割1: 作家の介入を最小化する**
数値・運動語彙だけの揺らぎは、感情や意図を持たない。「偶然」が作家の代わりに最終決定をする。LeWittが指示書を書いた後、職人の手に委ねたのと同じ構造。

**役割2: 出力の一回性を保証する**
同じ記述から毎回違うものが生まれる。記述は残り、出力は消える。この構造が「演奏」というメタファーを実体化する。

**役割3: 見る人の空間を作る**
完全に機械的な出力は、完成している。揺らぎがあると、見る人がその揺らぎを「意味あるもの」として読む余地が生まれる。ロスコの色面が完全なフラットではなく微妙な動きを持っているのと同じ。

### 13.3 感情語彙と運動語彙の区別

揺らぎに関する記述では、**感情語彙と運動語彙を厳密に区別する**。

**運動語彙（許容する）:**
```
細かく揺れる、ゆっくり波打つ、ばらつく、かすかに震える、ぶれる、滲む
```
これらは物理的な運動の描写。外部から観察可能な振る舞い。作品そのものではなく、作品の振る舞いの記述。

**感情語彙（排除する）:**
```
美しく揺れる、繊細に揺れる、優雅に揺れる、大胆に揺れる、激しく揺れる
```
これらは書き手の主観的評価。作品への介入。DDLの「感情語彙を排除する」原則に反する。

**境界（LLMの解釈に委ねる）:**
```
わずかに、少し（程度表現だが感情に寄る）
```

短歌でも、「美しい花」は主観だが、「風に揺れる花」は観察。DDL もこの区別を有限な Stage 1 の typed normalization 境界で扱い、特定モデルの能力を契約にはしない。

### 13.4 揺らぎの三層構造

揺らぎは三つの層から生まれる。優先順位は **プラグイン > 運動語彙 > 素材固有**。

```
[素材固有の揺らぎ]（常にあり・記述者は意識しない）
  pencil, brush, chalk などが持つ自然な揺らぎ

  ↓ 記述者が指定すると上書きされる

[運動語彙による揺らぎ指定]（記述者が書ける）
  細かく、ゆっくり、ばらつく、震える
  
  ↓ プラグインが明示されるとさらに上書きされる

[Nature plugin による現象起因の揺らぎ]（明示的に呼び出す）
  Nature.風、Nature.うねり
```

この三層は、盆栽の発想と一致する：
- **素材**（樹種）には自然な性質がある
- **職人の手**が入る（運動語彙）
- **環境要因**（風、季節）が重なる（プラグイン）

**太さは揺らぎではなく寸法である**（engine 16、v2.9.3）。素材固有の揺らぎを `weight` が内包するのと
同じ層に太さは属さない。道具は太さを既定として持つが、太さそのものは記述者が独立に書ける寸法であり、
**三層（素材固有・運動語彙・Nature プラグイン）の対象外**である。細い側にのみ段階があり、
太い側の語彙は持たない。`Instruction.thinness`（`fine` / `extra_fine`）がこれを運ぶ。
**三層に例外を作るのではなく、太さを三層の外に置く**という整理である。

Visible DDLの有限表記は、Fineが日本語`細い` / 英語`thin`、ExtraFineが日本語`ごく細い` /
英語`extra-fine`である。Runtime未接続のshared compilerはこの二段階をsource表記から独立した
typed identityとして保持し、対応範囲のdirect instructionとflat Macro Emitから共通lowererを通して
既存`Instruction.thinness`へ届ける。未指定は`None`のままで、太い段階や自由なdegree同義語を補わない。

なお **`thinness` は歳時記の語ではない**（2026-07-29 作者裁定）。Stage 1 は太さ語を読んで
正規化DDL へ書くが、§3.1 の語彙表と歳時記の表示には現れない。

#### 暴れる（engine 12、到達範囲は engine 14）

**三層とは別に、演奏そのものの上限を外すスイッチを一つ置く。** UI では「暴れる」。

- **作品全体に一つ**。ストロークごとでも道具ごとでもない。
  **engine 12 では線プリミティブにしか届いていなかった**（円・楕円・三角・四角・多角形・弧・塗り・ハッチは
  ON でも出力がバイト一致した）。**engine 14 で輪郭・弧・塗り・ハッチへ届かせ、位置づけと実装を一致させた**
- **外すのは振幅の上限と自己交差の禁止だけ**。端点の固定と決定性は ON でも保つ。
  同じ Score・同じ seed・同じ状態なら、何度描いても同じ SVG が出る
- **記録して再現する**。`render_seed` の隣に `render_wild` として保存し、
  エディション ID（`rh3`）の材料に含める。**同じ Score を暴れさせた版と暴れさせない版は別の作品である**
- **道具の癖に掛かる倍率であって、癖を作るものではない**。揺れ項が 0 の道具（`rotring`）は
  暴れさせても動かない。**機械には暴れる余地がない**

**これは変奏（Stage 1.5）とは層が違う。** 変奏は楽譜を書き換える決定的な工程で、
暴れるは楽譜を変えずに演奏の幅を変える Renderer 層のノブである（層の責任は本書 §12、版の扱いは §2.1 に記す）。

### 13.5 weight による揺らぎの質

揺らぎには「量」だけでなく「質」がある。DDLでは、weight（素材）が揺らぎの質を暗黙に決める：

| weight | 揺らぎの質 | 特性 |
|---|---|---|
| silverpoint | almost_none | ほぼ揺らぎなし（正確）。手の道具でもっとも細く（0.5px）、もっとも揺れない線。※v1.92 に `hair` の名で語彙から削剪したが、v2.7.9 で銀筆と改名して語彙へ戻した。保存済み Score の `hair` は読み込み時に `silverpoint` へ置換する |
| pencil | perlin_fine | パーリン寄り（手の連続性）、薄い副線、微細な粒 |
| pen | perlin_minimal | わずかなパーリン。基準となる標準線 |
| rotring | almost_none | 均一幅、角端、硬い製図線 |
| crayon | rubbed_noise | 擦れ、短い破線、粒状の欠け |
| chalk | perlin_plus_noise | パーリン + 粉っぽいかすれ、blur |
| brush_thin | perlin_strong | 細い筆跡、副線、濃淡 |
| brush_thick | pressure_blur | 太い筆圧、擦れ副線、軽い blur |
| oil_paint | viscous_ridges | 油彩。絵具の残る太い筆跡、選択色から作る明暗の刷毛筋、塗り面に重なる筆跡で厚塗りを表す |
| burin | almost_none | 硬く確実な彫線。丸端、texture filter なし |
| drypoint | burr_noise | まくれ（バー）による滲み・かすれ。専用の burr 処理 |
| computer | periodic_quantized | 揺れを持つが**誤差なく反復する**。整数周期の正弦と格子への丸め。材質は標本化の残り（[版史](docs/spec/render-engine-history.ja.md) の「engine 13」） |

数値特性（stroke 幅・不透明度・dasharray・filter 有無）の正は reference §6 とする。

#### 道具別の塗りと濃淡

閉じた塗りは、選んだ道具の質感を持つ。Score 0.3.0以後の`surface_intensity`は`normal`（省略時）／`dense`／`faint`で、通常の値はwire出力へ追加しない。保存済みScore 0.1.0／0.2.0／0.3.0は元の版を保持して読み書きする。通常DDLとMacroは同じ濃淡を共通lowererから渡し、反復planも個体生成前のappearanceへ保持する。濃淡だけを変えて、選択色のidentity、図形や筆跡を決めるseedを変えない。

| 道具 | 塗りの表現 |
|---|---|
| 銀筆・鉛筆 | 銀筆は細かく静かな銀の痕。鉛筆は芯を寝かせた幅広い擦り跡で、濃いほど余白を減らす。薄いは重なりの黒みを抑える |
| ペン・ロットリング | ペンはわずかなインクのむら、ロットリングは均一で硬い製図インク |
| チョーク・クレヨン | チョークは粉と紙の隙間。クレヨンは蝋の擦れを持ち、チョークより面を覆う |
| 太筆・細筆 | 筆の墨の濃淡と擦れ。通常も十分に濃く、濃いはさらに濃くする |
| ビュラン・ドライポイント | ビュランはシャープで制御された彫線。ドライポイントは柔らかく毛羽立つ黒い線。彫線の並びは規則性を崩す |
| 油彩 | 幅広い筆跡と同色の明暗による刷毛筋。濃いは筋を強めて座標を軽量化し、薄いは筆跡の絵具を透かす |
| コンピュータ | 縦RGB帯、黒いインターレース走査線、淡い光のにじみでCRTを表す。濃いは明度を下げ、薄いは明度を上げる |

粒子や線は小さな共有pattern／mask／filterで表し、油彩はfilterを使わずpathで表す。油彩の塗り幅と間隔は基準の3倍、内部筋の明暗差は通常0.6／濃い1.05／薄い0.6、濃いの座標簡略化は短辺1000当たり許容差0.25（拡幅前）、薄いの各筆跡opacityは0.54とする。下地と輪郭を拡幅しない。Compatはfilterを持たない近似表現であり、Displayと同一画像とはしない。

Typed DDLの濃淡接続はsolidな閉じた塗りを対象とし、非solidなtexture、塗りのない線・弧、Pointの明示surfaceは既存の未対応診断を維持する。Scoreの描画能力と、typed DDLの意味が接続済みの範囲を混同しない。アプリのtyped runtime／UI／save全面接続は後続工程である。

**揺らぎのノイズ種別:**
- **ホワイトノイズ**: 各点独立・相関なし・ギザギザ
- **パーリンノイズ**: 連続的・隣接点が似る・滑らかな波
- **1/f揺らぎ（ピンクノイズ）**: 自然界に多い・人間が「自然」と感じる

手描きの線は手の慣性から連続性を持つため、パーリンノイズ寄りが自然。


### 13.6 運動語彙のカテゴリ

Saijiki（歳時記）に「ゆらぎ（movements）」カテゴリを追加する。

**日本語版「ゆらぎ」:**

| 次元 | 語彙 |
|---|---|
| 振幅 | 細かく、大きく |
| 周波数 | 速く、ゆっくり |
| 質 | 揺れる、波打つ、震える、滲む |

**⚠ ゆらぎの `滲む` と おもて の `にじみ` は別のものである**（2026-08-12 作者裁定）。
ゆらぎの `滲む` は**線そのものが震えて滲む**振る舞い、おもての `にじみ` は**塗った面の縁が広がる**状態。
**動詞と名詞で品詞が分かれる。**

**英語版「movements」:**

| Dimension | Vocabulary |
|---|---|
| amplitude | fine, large |
| frequency | quickly, slowly |
| quality | swaying, undulating, trembling, blurring |

配置のばらつきは ゆらぎ ではなく、うごき（散らす）と arrangement（layout / path / jitter）が担う。

Runtime未接続のshared compilerでは、通常DDLと宣言済みflat Macroが一つのresolverを通る。`fine` / `large`はFine / Broad、`slowly` / `quickly`はSlow / High、`swaying` / `trembling`はPerlin、`undulating`はWave、`blurring`はPinkへ写す。三slotが全て無ければ`Instruction.variation=None`、一つ以上あれば不足する振幅／周波数／質だけをMedium / Medium / Perlinで補う。明示値が優先し、三次元は独立である。`trembling`からFineやHighを推測しない。Sourceやtyped meaningへdefaultを注入せず、既存geometry-resolution-policyのauthor-resolved omissionがこの共通定義をattestする。

### 13.7 Nature plugin による現象の揺らぎ

`Nature.風` などの名前空間付き語は、`inku.macro-definition.v1` の閉じた typed parameter、bounded repeat、typed transform、deterministic bounded vary から core meaning を emit する概念例である。definition は raw Score field、renderer 命令、noise algorithm を直接書かず、source / generated provenance と compiler lock に従う。

MacroDefinition v1 の schema と展開 primitive は受け入れ済みだが、runtime loader、公式 registry、インストール済み Nature package はまだ接続されていない。v1.70 の hard-coded Nature 展開は legacy compatibility であり、新規 semantic canon や恒久 fallback ではない。保存済み Score / expanded artifact を優先し、欠落を別図形へ黙って変えない。

### 13.8 Renderer での揺らぎ生成

揺らぎの乱数生成は **Renderer 層**で行う。JSON Score では行わない。

**設計の根拠:**

| 層 | 役割 | 決定性 |
|---|---|---|
| DDLテキスト | 記述（母語） | 決定的 |
| 正規化DDL | 解釈（コア語彙） | 決定的 |
| JSON Score | 楽譜（構造化指示） | 決定的 |
| **Renderer** | **演奏（揺らぎを実現）** | **非決定的** |
| SVG | 出力（一回性） | 都度生成 |

JSON Score は「楽譜」であり、演奏そのものは含まない。楽譜には揺らぎの「指示」（amplitude, frequency, quality）は含まれるが、具体的な乱数値は含まれない。これにより：

- 同じ JSON Score から Replay すると、毎回違う SVG が生まれる（既存のAndroidアプリの機能）
- JSON Score がアーカイブとして意味を持つ
- 揺らぎのシード値を変えれば同じ楽譜から複数の演奏が生まれる

**演奏の自由度は二スケールある（v1.51）:**

| スケール | 実体 | 記述箇所 |
|---|---|---|
| ミクロ | 線の震え、滲み、粒、擦れ | §13.9 variation |
| マクロ | 関係・領域として記された配置の演奏時解決 | §14.4 逐次解決 |

楽譜は「前の線に触れない、狭い間隔で」と関係を記し、演奏がその都度の位置を決める。これにより「同じ楽譜から毎回違う演奏」が、数px級の震えではなく構図レベルで成立する。従来の実装はミクロのみを実現しており、マクロの揺らぎがどの層にも割り当てられていなかった。これが出力の均質化（Build 436 で観測）の一次原因である。

**敷き詰め演奏の三層（v1.75）:** 書き手が「敷き詰める」と明示した `layout="grid"` は、(1) performance seed 由来の決定的 hash によるセル内位置の微小ずれ、(2) 各要素で位相が異なる既存 `variation`、(3) pencil / brush / chalk 等の既存 weight 素材固有の揺らぎ、の三層で演奏する。同一 Score + 同一 render seed は bit 同一であり、seed が変わると秩序を保ったまま手の差が変わる。grid は全面反復そのものが書き手の意図なので、scatter 用の偏り・fade・cluster・preserve-space・数量代表化を適用しない。

**支持体の抵抗（v2.9.16 / render engine 19）:** 揺らぎは道具の側だけにあるのではない。**絵画で地が持つ役割は、描く手に抵抗することである** — 吸い込む地では線が滲み、弾く地では掠れる。engine 18 まで地と描画は独立に合成されるだけで出会っておらず、`canvas.ground` は保存作品の 1.7%・凍結 SVG の 0% にしか無いので、地の側に条件を置いても届かない。engine 19 は**すべての作品に既定の支持体を置く**。**紙は 1 種の定数で、吸う（`absorb`）/ 弾く（`tooth`）のどちらを受けるかは道具の側の性質**である（brush は吸われて膨らみ、crayon / pencil / chalk は弾かれる。`rotring` と `computer` は機械なので紙に触れない）。**弾かれた側では墨を置かない** — 幅を細めても最も細い道具ではアンチエイリアスに沈むので、掠れは「線が細くなる」ことではなく「白が残る」こととして作る。**切れ目は同じ `path` の subpath になるので、要素は 1 つも増えない**（§13.4 の三層は素材・運動語彙・現象の三つだが、支持体はそのどれでもなく、**演奏の最後に道具が出会う相手**として掛かる）。


### 13.9 JSON Score の variation スキーマ

JSON Score の `variation` フィールドは、次元ごとに分離した構造を持つ。

```json
{
  "variation": {
    "amplitude": "fine",
    "frequency": "high",
    "quality": "perlin",
    "dimensions": ["position_y"]
  }
}
```

| フィールド | 値 | 説明 |
|---|---|---|
| `amplitude` | `fine` / `medium` / `broad` | 振幅（運動語彙由来） |
| `frequency` | `slow` / `medium` / `high` | 周波数（運動語彙由来） |
| `quality` | `none` / `white` / `perlin` / `pink` / `wave` | 明示運動語彙から解決するノイズ種別。素材固有の演奏は独立 |
| `dimensions` | `[position_x, position_y, angle, length, rotation, radius]` | どの次元を揺らすか。`thickness` は v2.7.2 で退役した（宣言だけで Renderer が読まなかった） |

**記述者はこの構造を直接書かない**。運動語彙・weight・プラグインの組み合わせから、第二段階の構造化層が生成する。

現行実装では、線の揺らぎは Renderer で polyline 化して表現する。振幅は**その痕の線幅に対する倍率**で `fine=0.35` / `medium=0.6` / `broad=2.0` とする（render engine 28。v2.1.0〜engine 27 は図形の代表寸法に対する比率 0.025 / 0.08 / 0.18 で、それ以前は 1000px キャンバス基準の絶対 px 7 / 12 / 30）。**揺らぎは道具が紙に当たって生じるものなので、物差しは図形ではなく痕の太さである** —— 代表寸法で測ると、同じ 8% が筆では見えず細い鉛筆では別の線になった。代表寸法の 0.40 というクランプは、自分の痕より小さい図形のための安全弁として残る。

`quality` の使い分けは以下を基本とする。

- `perlin`: 「震える」「細かく揺れる」などの微細で不規則な線の揺らぎ
- `wave`: 「ゆっくり揺れる」「波打つ」などの低周期で読み取りやすいうねり
- `pink`: 「滲む」などの境界のぼかし
- `white`: 粗いノイズ的なばらつき

Shared compilerの明示揺らぎは常に`dimensions=["position_x","position_y"]`を使う。Lineは既存の直交方向、Arcとcircle / ellipse / square / cloudform / triangle / polygonは既存の内外方向のconsumerで演奏する。短線threshold、noise、seed、geometry、位置、angle、thinness、material、関係端点の契約を変更しない。Pointと未対応shapeへの明示variationは拒否する。Stage 1.5のfocus-only変奏とは別である。

スキーマレベルでは variation は保持するが、DDLテキスト層のインターフェースからは見えない。プラグインや素材を実装する人だけがこの次元を扱う。

### 13.10 JSON Score の arrangement path

`arrangement` は本数・個数だけでなく、連なり方と軌跡を保持する。

```json
{
  "arrangement": {
    "count": 21,
    "layout": "scatter",
    "path": "wave",
    "margin": 0.12
  }
}
```

| フィールド | 値 | 説明 |
|---|---|---|
| `layout` | `horizontal` / `vertical` / `radial` / `scatter` / `grid` | 基本配置。`grid` は明示された敷き詰め |
| `path` | `none` / `diagonal` / `wave` / `top_to_bottom` / `left_to_right` / `right_half` | 配置軌跡 |
| `rows` / `cols` | 1〜64 または省略 | grid の行列数。両方明示時は `rows×cols` を優先 |
| `jitter` | 0.0〜1.0（既定0.12） | grid セル内の決定的な位置ずれ |

対応関係:

- 「波打つ軌跡に沿って」→ `layout="scatter"`, `path="wave"`
- 「斜めの帯」→ `path="diagonal"`
- 「上から下へ散らす」→ `layout="vertical"`, `path="top_to_bottom"`
- 「左から右へ」「横に」→ `layout="horizontal"`, `path="left_to_right"`
- 「右半分」→ `path="right_half"`
- 「放射状」「同心円状」→ `layout="radial"`
- 「敷き詰める」「格子状に敷く」→ `layout="grid"`（この明示語がある場合だけ。count の上限は layout に関わらず一律 2000）

#### 群れがどこへ置かれるか（render engine 20）

**layout が決めるのは散らばりの形であって、群れの置き場所ではない。**
展開された群れは**その instruction が述べた座標（アンカー）へ重心を合わせて**置かれ、
枠 **[0.02, 0.98]** からはみ出す分は**軸ごと・方向ごとに、はみ出したぶんだけ**縮めて収める
（相似形で群れ全体を縮めたり、枠へ丸めて印を積み上げたりはしない）。
`radial` の `center` は回転中心であり、**省略時はアンカーの周りを回る**（キャンバス中央ではない）。
**例外は `at.region` を持つ `grid` 1 つ** — 格子は述べられた領域を敷き詰めるので、
群れをアンカーへ寄せずにその領域に留まる。
engine 19 まではどの layout も置き場所を seed から決めており、
**展開後の印の 77.8% が宣言座標を参照していなかった**。

#### 明示された個数の扱い（v2.7.6）

Canonical meaningでは、記述に明示された個数をlosslessなsymbolic intentとして保持する。Step 11のpure ceiling preflightを、展開、配列確保、またはその他のO(count) materializationより前に適用する。`u32::MAX`等の巨大な値もclampや代表数へのsilent rewriteをせず、拒否時のallocation / materializationは0である。

以下は既存Score / coerce経路のcompatibility behaviorを記録したもので、上のsymbolic intentを再定義しない。Step 11 cutover前のruntime状態を新規semantic canonと取り違えない。

| 要求 | 扱い |
|---|---|
| **240 未満** | **literal。要求値をそのまま `arrangement.count` に使う** |
| **240 以上** | 代表化。`count` を 80〜120 とし、`density` / `cluster_count` / `fade` / `preserve_space` で群の見え方を保つ |

閾値の既定 240 は `max_expanded_per_instruction` の既定に合わせてある。閾値だけを 300 へ上げると 241〜299 が「literal と規定されているのに coerce が 240 で切る」構造的に守れない帯になるので、**正規化が両者の整合を強制する**（v2.10.0）。**記述が述べた数は、その構成の閾値まではそのまま描かれる** — 既定では「二百三十三本」は 233 本描かれる。**閾値は制限値の設定であり、値を動かせば「そのまま描かれる」帯も動く。どの値で描いたかは作品に記録される**（`history.render_limits`）ので、設定が版と同じ資格で再現性を担う。**描き直しは作品に記録された値で走り、記録の無い作品でだけ今日の設定へ落ちる。どちらで描いたかは応答が名乗る**（v2.13.30）。注文書は 1 枚のあいだ上限を下げられるが上げられない —— 要素ごとに現行の設定で抑えられる。

**述べ方が「だけ／のみ」でなくても、個数は述べたとおりに描かれる（v2.11.20・ddl-engine 11／v2.12.1・ddl-engine 12 で帯を広げた）。**
それ以前は「三つ**だけ**」の形だけが数を守り、「円を三つ並べる」のように普通に述べた数は下流の推測に上書きされていた。
**効かせる先は、その節に対応する群がちょうど 1 つに決まるときに限る** ——
節から作った（図形・色・太さ）の三つ組を持つ群が 1 つならその群、三つ組が当たらないときは同じ図形の群が 1 つならその群、
**候補が複数か 0 なら何もしない。曖昧なまま押し付けると、別の節が述べた数を壊すからである。**
**効く帯は literal の閾値そのものから来る**（既定では 239 まで。閾値は `max_expanded_per_instruction` に
合わせて正規化されるので、設定を動かせば帯も動く）。**同じ境目に 2 つ目の名前を与えない** ——
別の定数として書くと、片方だけが動いたときに誰も気づかないからである。
**閾値以上は代表化の領分で、この枝は 1 件も触らない。**
**強制した数が命令ごとの上限か作品全体の上限を越えるときは、切り詰めずに強制しない** ——
この枝は予算より後に走るので越えた分を誰も削らず、切り詰めれば**述べた数でも代表数でもない中途半端な数**が絵に出る。
**届かないなら手を出さないほうが、記述に対して正直である。**

**どの読み手も同じ数え方をする（v2.13.10・ddl-engine 14）。** 個数を読む口は複数あるが、読み方は 1 つである。

- **記述の言語が判定を決める。** 数字の近くに CJK があると個数を落とす除外は、**本文が日本語のときだけ**効く。
  英語の本文に書かれた `12` は、隣にプラグイン語の漢字があっても 12 である（それ以前は落ちていた）。
  **言語は coerce の呼び手 5 つすべてが渡す。**
- **参照の句が個数を述べていないときだけ、その文まで広げて読む。** 句が述べていれば文は上書きしない。
- **参照の句の中の助数詞なしの算用数字は個数である**（`緑のNature.下草を50散らす。` は 50）。
  **句の外の裸の数字も、同じ文の中なら読む** —— ただし下の除外は広げた先でも効く。
- **軸を名指す語のそばの数は読まない**（方向・向き・種類・層・行・列・度・回・倍・割と、英語の相当語）。
  `四つの方向` の 4 も `30度` の 30 も個数ではない。**索引の数も読まない**（`member 2` の 2 は「どれか」であって「いくつか」ではない）。
- **小数と分数は個数ではない**（`0.11 の半径` の 0.11）。

**この規則は Android の移植にも同じ形で入っている** —— 手書きの漢数字表は消え、期待値は server の実測から生成する。

**静けさ・膜・記憶系の文脈で密度を抑える処理は、明示された個数の群には適用しない。** 静けさは場面の読みであり、書かれた数は読みではない。個数が指定されていない群に対してのみ働く。大きさを整える処理（象徴形・単独形・意図しない塗り）は、いくつを触るものではないので従来どおり働く。

**複数群の literal 合計が 400（`max_expanded_primitives` の既定）を超える場合は、要求値の大きい群から順に代表化へ倒し、合計が 400 以下になった時点で止める。小さい群を先に削らない。** 数えられる数と数えられない数は別物であり、比例縮小は数えられる側を先に壊す。全群を代表化しても超える場合だけ、大きい群が一つの上限を分け合う。

**総量と命令数には、layout に答えない天井が coerce の最後に置かれている。** 上の代表化は密度の読みであり、`grid` を意図的に免除する（穴の空いた格子は格子ではない）。**その免除は「間引き」には正しく「天井」には誤りなので、天井は grid を含めて数える** — 描かれる印の数は `count` ではなく `rows × cols` で数え、超過分は比を保ったまま小さい格子へ落とす。命令の本数にも上限（既定 64）がある。**本番の最大は 27 なので、実在の作品はどれも触られない。**天井が縛るのは、検証だけを通り抜けた要求である。**この天井は決定的な層に在り、プロンプトの「1〜5 命令」というお願いに依存しない。**

`path` が `none` の場合は従来どおり `layout` だけで配置する。`path` が指定された場合、Renderer は決定的な hash と連番を使い、同じ JSON Score から同じ軌跡配置を再現する。

### 13.11 記述例と展開

記述例：

```
細かく揺れるペンシルの破線が3本、画面を横切る
```

**第一段階（解釈）の出力（正規化DDL、実コーパス形式）:**

```
鉛筆の破線の横線を縦に三本並べる。線は細かく揺れる。
```

**第二段階（構造化）の出力（JSON Score、抜粋）:**

```json
{
  "instructions": [
    {
      "primitive": "line",
      "style": "dashed",
      "from": [0.0, 0.33],
      "to": [1.0, 0.33],
      "weight": "pencil",
      "variation": {
        "amplitude": "fine",
        "frequency": "medium",
        "quality": "perlin",
        "dimensions": ["position_x", "position_y"]
      }
    }
  ]
}
```

**Renderer:**

JSON Scoreを受け取り、`variation`情報から実際の揺らぎ関数（Perlin、Fine振幅、Medium周波数、既存の線に直交する演奏）を選んでSVGを生成する。同じScoreと同じrender seedは同じ演奏になる。この複数本の記述例は概念例であり、shared compilerのcount1 deliveryが反復allocationまで実装済みという意味ではない。

v1.99 で揺らぎの演奏対象を線に加えて弧・閉図形（円・楕円・三角・四角・多角形）へ拡張した。発火条件は quality ∈ {perlin, wave, white} かつ dimensions が position_x / position_y / radius のいずれかを含む場合（line と対称、radius は図形の自然軸）。閉図形は継ぎ目が連続する周期ノイズで輪郭を演奏し、多角形系は辺ごとに演奏して角を固定、弧は両端点を完全固定して touching の接点契約を維持する。pink（滲み）と quality=none の経路は不変。この変更で同一 Score + 同一 seed の演奏結果が変わるため、render engine version を 5 へ更新した（過去作品の再演奏は見た目が変わりうるが、保存済み SVG は不変）。

v2.0.5 で wave 品質の揺らぎに演奏 seed 由来の位相を導入した（従来は位相固定の正弦波で、seed を変えても波形が同一だった）。位相は seed から決定的に導出し、整数周波数による閉輪郭の自動閉合・弧の端点固定・多角形の角固定は維持される。あわせて材質輪郭（pencil / crayon / chalk 等の輪郭とspeck）も演奏 seed に追随させた。演奏 seed 未指定時は従来とバイト一致。同一 Score + 同一 seed の演奏結果が変わるため render engine version を 6 へ更新した。

v2.1.0 でレンダリングの px 絶対値を比例系へ全面改修した。揺らぎ振幅語彙（fine / medium / broad）の意味を 1000px キャンバス基準の絶対 px（7 / 12 / 30px）から**図形の代表寸法に対する比率**（0.025 / 0.08 / 0.18）へ変更した。代表寸法は circle / polygon / arc = 半径、ellipse = 半径の相乗平均、square / triangle / cloudform = 短辺の 1/2、line = 線長。小さな図形は細かく、大きな図形は大きく揺れる。滲み（pink）の stdDeviation も同様に比率化（0.009 / 0.03 / 0.07）。輪郭の分割数とストロークの標本数は固定値（80 / 49）から長さ比例（クランプ付き）へ変更した。材質層（線幅・dasharray・質感 filter・材質輪郭・speck）と display filter は `canvas.unit` 相対化し、`unit=1000` では従来と一致する（speck 個数の周長比例化と stroke 標本数の長さ比例化を除く）。あわせて作者キャリブレーションにより材質輪郭と speck の強度を下限方式で引き上げた（強度段 s1: 輪郭 offset / opacity と speck opacity / 個数に下限を設定、質感 filter は据え置き）。材質輪郭には `class="material-outline"` を付与し、主線と機械的に区別できるようにした。同一 Score + 同一 seed の演奏結果が変わるため render engine version を 7 へ更新した。

v2.2.0 で閉図形（circle / ellipse / square / triangle / polygon）の輪郭を手描きストローク（筆致エンジン）で描くようにした。`stroke_engine` に任意中心線へのストローク合成 `synthesize_along` を追加し（道具文法は line 用と同一、追従目標だけを差し替え。意図の歩幅をフィードフォワードし、ばねには残差だけを担わせる積分器で曲率による半径方向の歪みを排除）、輪郭は外周・内周 2 サブパスの塗り帯（`class="contour-stroke-v1"`、fill-rule evenodd）として描く。角は理想位置に固定して筆の継ぎ目とし、角のない閉輪郭は継ぎ目を線形ランプで閉合させる。対象 weight は rotring を除く手描き系全種（rotring は幾何輪郭のまま）。帯の中心線は変奏を演奏した後の輪郭で、材質輪郭・speck は帯と併存する。破線・点線は線種そのものが記述なので、細めた幾何輪郭を残す。本体要素は幾何のまま維持され（実線では `stroke="none"` で塗りのみ）、bbox・touching 契約は不変。line と弧の出力は v2.1 とバイト一致（弧のストローク化は touching 検査の弧抽出器の再設計を伴うため次契約へ）。同一 Score + 同一 seed の演奏結果が変わるため render engine version を 8 へ更新した。

v2.3.0 で閉図形の塗りを領域 fill から**素材の筆致で内側を埋めるストローク塗り**へ変更し、`filled` の意味論を復権した（`True` = 素材の筆致で内部を埋める / `False` = 輪郭のみ。従来は閉図形が `filled` に関わらず常に塗りつぶされる死にフィールドだった）。

塗りは走査線と閉輪郭の交点を対で取り、内部区間 1 つ = 1 筆として `synthesize_along` に通す（clipPath 不要。凹形 cloudform も交点対のまま扱え、端点は交点から線幅の半分だけ内側へ寄るので縁が輪郭に揃う）。群は `class="fill-stroke-v1"`。走査角は演奏 seed 由来（0〜180° 一様）で図形ごとに変わり、間隔は `max(線幅 × 1.5, canvas.unit × 0.012)` に ±12% のジッタ。完全被覆は狙わず紙目（隙間）を残す。

rotring は領域 fill を維持し（`True` = ベタ塗り / `False` = 輪郭のみ）、走査線 3 本未満の微小図形は領域 fill に縮退する。`surface` 指定時は素材塗りを出さない（塗り = 素材の既定の埋め方、`surface` = 明示的な版表現）。

**`surface.texture="grain"` は道具文法で作った有限の粒を `<pattern>` tile に定義し、閉輪郭そのものを carrier path として `fill` から反復参照する。** 粒の論理数は density と固定tileだけで決まり、面積はその定義を何度繰り返すかだけを決める。`filter`・`clipPath` は加えないので、3つのSVG profile は同じ grain 構造を出す。

**⚠ v2.13.20（ddl engine 18）で 1 つ例外ができた** —— `surface.texture="solid"` は「素材の既定の埋め方」そのものを言う値なので、**版表現の層ではなく塗りの層へ行く**。おもての質 9 語がすべて `surface.texture` の値になり、塗りだけが `filled` へ行く非対称が消えた（`filled` は残り、coerce の枝が `solid` と `filled=true` を両方向に導出する）。あわせて surface の hatch / crosshatch を幾何直線から筆致の帯（`class="surface-stroke-v1"`）へ差し替え（中心線・角度・間隔・本数は不変、rotring は幾何直線のまま）、演奏されない variation を seed key から除外して不活性な variation の有無で演奏バイトが変わらないようにした（primitive 別の不活性判定。cloudform は輪郭生成器が quality / amplitude / frequency を常に消費するため不活性なのは dimensions のみ）。同一 Score + 同一 seed の演奏結果が変わるため render engine version を 9 へ更新した。

**⚠ v2.13.24（render engine 35）で hatch / crosshatch の行は輪郭で切られるようになった** —— 塗りと同じ交点の機構を通すので、行は図形の中だけに残り、凹形では区間ごとに 1 本ずつ描いて空洞をまたがず、輪郭と交わらない行は 1 本も描かない。`clipPath` は使わないので `compat` でも同じ形に収まる。**切る前の層は動かない** —— 角度・間隔・`spacing_gradient`・1 行ごとの揺らぎはそのままで、間隔クラスの値も前の版と同じである（減るのは輪郭の外に出ていた行の本数だけ）。

v2.3.1 で弧（arc）も手描きストロークの帯（`class="arc-stroke-v1"`）で演奏するようにし、v2.2.0 で残されていた最後の対象外を解消した。対象 weight は rotring を除く手描き系全種（rotring と非手描き weight は幾何の弧のまま）。帯の中心線は変奏を演奏した後の弧で、両端は意図値に固定される。**幾何の弧は不可視の意図要素（`stroke="none"`）として残し**、touching（接点契約）の検査は描画 SVG からこの意図弧を読み戻して座標で担保する（弧抽出器は無改変。帯は `M..L..Z` の塗りポリゴンで弧コマンドを持たないため二重計上されない）。**接点端も taper のまま**とする（ストローク合成の envelope は両端でゼロへ収束する。接点契約は意図弧が座標で担保するため、帯は自由端と同じく端で柔らかく消えてよい。葉の先端・付け根は柔らかく消える見た目になる）。破線・点線は意図弧そのものを細い破線 / 点線で可視化する（線種は記述なので読めるまま残す。line・閉図形と対称）。drypoint は演奏後の中心線に沿って burr を出し、材質輪郭・speck は帯と併存する。同一 Score + 同一 seed の演奏結果が変わるため render engine version を 10 へ更新した。

---

## 14. 関係（あいだ）の設計

### 14.1 なぜ関係か

短歌の表現力は語彙の豊富さではなく、語と語の関係の装置——縁語、掛詞、切れ、句跨り——から生まれる。三十一音という型の中で無限が成立するのは、要素間の関係が意味を運ぶからである。

LeWitt の Wall Drawing も同様である。語彙は線と少数の色という inku より貧しい集合だが、指示文の大半は関係の記述で占められている（触れない線、円の内側、左辺の中点から右上隅へ向けて、など）。鑑賞者が読み取るのも個々の線ではなく、線と線の間に生じる密度の勾配・緊張・間である。

現行の JSON Score は、順序付き instruction に明示的な逐次 relation を持つ。relation は記述者の DDL または明示 macro emit に由来し、独立した部品を Stage 1.5 の固定技法レシピで結び直すものではない。

関係の語彙は、コアに名詞を足すのではなく述語（統語）を足す拡張である。「型が自我を削ぐ」原則とはむしろ相性が良い——関係の文法は書き手に構成の判断を強いる型であって、自由の放縦ではない。プラグイン原則1（語彙のマクロに限定）、Go 的抑制のいずれとも矛盾しない。

### 14.2 観察可能な関係語彙

§13.3 の感情語彙/運動語彙の区別を、関係に延長する。物理的・外部観察可能な関係のみをコアに許す。

**関係語彙は次の6語に限定する:**

| 語彙（日） | 語彙（英） | 意味 | relation.type |
|---|---|---|---|
| 沿う | along | 直前要素の軌跡・方向に沿って配置する | `along` |
| 触れない | not touching | 直前要素に接近するが接触しない | `not_touching` |
| 切る | cutting | 直前要素を横切り、視覚的な断絶を作る（短歌の「切れ」に相当） | `cutting` |
| 間に | between | 直前の2要素の間の領域に置く | `between` |
| 触れる | touching | 直前要素に接触する。両端点を一致させて閉形を構成する | `touching` |
| つながる | connected | current始端を直前要素の終端へ合わせ、両方の形を変えずに接続する | `connected` |

**排除する語**: 寄り添う、応える、対話する、呼応する——意図・擬人の語であり、外部から観察できない。

v1.52 クローズ時点では、JSON Score の `relation` は正規化DDL中に明示的な previous-object 句がある場合に限る。日本語では `前の線に沿って` / `前の形に触れない` / `前の線を切る` / `前の二つの間に`、英語では `along the previous line` / `not touching the previous shape` / `cutting the previous line` / `between the previous two` を固定句とする。`touching` は日本語の `前の線に触れる` / `前の弧に両端で触れる`、英語の `touching the previous line` / `touching the previous arc at both ends` が接触を明示する場合に限り使い、自発付与しない。`connected` は `前の形につながる` / `connected to the previous shape` だけを固定句とし、短表記や未検証のprior primitive typeを断定する別句をaliasにしない。自然文由来の「周囲」「同じ拍子」「先行/遅れ」「近く/遠く」は relation ではなく、position / path / rotation / spacing で表す。

**第二段候補（実測後に判断）**: 重なる、離す、同じ向きに、逆向きに、〜より細く。現行語で表現の不足が実測で示されてから追加する。片端接続の`つながる (connected)`は独立した表現価値と有限なLine / Arc / Point endpoint familyを確定してから導入した。

### 14.3 JSON Score スキーマ

instruction に任意フィールド `relation` を追加する。

```json
{
  "primitive": "arc",
  "weight": "brush_thin",
  "relation": {
    "type": "not_touching",
    "gap": "narrow"
  }
}
```

| フィールド | 値 | 説明 |
|---|---|---|
| `type` | `along` / `not_touching` / `cutting` / `between` / `touching` / `connected` | 関係の種類 |
| `gap` | `narrow` / `medium` / `wide` | 距離の目安。具体値は演奏が解決する |
| `target_instruction_index` | 0以上のScore index | checked `connected` / `touching` / `along` / `cutting`が参照する正確な先行Score instruction。旧relationでは省略 |
| `position_authority` | `named_movable` / `numeric_fixed` | checked currentの位置authority |
| `touching_constraints` | `dimensions_fixed` / `direction_fixed`のboolean組 | typed `touching`の明示寸法・向きの固定条件。省略normalとは区別し、旧Scoreでは省略 |

**参照先は常に「直前の instruction」とする（暗黙 prev 参照）。** `between` のみ直前の2要素を参照する。id による任意参照は導入しない。理由:

- 幻覚参照・循環参照・前方参照が構造的に発生しない
- 軽量モデル（Stage 2）が参照解決という新しい認知負荷を負わない。relation は素通しコピーで済む
- LeWitt の職人の手順（先に描いた線を見て、次の線を置く）と一致する

id 参照が必要になった場合も、その必要が実測で示されてから第二段として検討する。

### 14.4 逐次解決と演奏（マクロ揺らぎ）

関係の解決は Renderer が演奏時に行う。Renderer は制約ソルバを持たない。instruction を順に処理し、直前要素の**確定した**位置・輪郭を参照して次を配置する（逐次解決）。

- `not_touching, gap=narrow` → 直前要素の輪郭から一定レンジ内の距離・方位を、演奏ごとの乱数で決める
- `along` → 直前要素の軌跡に沿う帯領域内で、位置・位相を演奏ごとに決める
- `cutting` → 直前要素と交差する角度・交点を、レンジ内で演奏ごとに決める
- `between` → 直前2要素の間の領域内で決める
- `touching` → line / arc だけに適用し、直前の line / arc の演奏実現後の両端点へ当該要素の両端点を一致させる
- `connected` → Line / Arc / Pointに適用し、currentのcanonical始端（Pointはcenter）をpriorのcanonical終端（Pointはcenter）へ平行移動する。prior、寸法、曲率、rotationは変えない

現行のtyped Along / Cutting描画はCount1のactual Scoreを対象とする。Macroの反復CompositionPlanは共通のrelation intentを保持するが、反復個体の演奏は後続materializationで扱う。Typed Alongではcurrentと直前要素がともに線で、currentの方向が未指定なら、その方向を直前の線と平行に揃える。明示された方向・寸法・数値位置は保持する。Typed Cuttingも、共通resolverが決めた通常寸法または明示寸法を保持し、専用のランダム長に置き換えない。明示方向は交差角の演奏より優先する。通常DDLとMacroは同じ意味を使う。旧metadata-free Scoreの関係処理は互換用に保持し、Typed DDL本番pipeline／UI／saveの全面接続とは区別する。

`touching` で当該要素が弧なら、直前要素の確定端点を P1, P2、弦長を `c=|P2-P1|`、当該弧の演奏後の符号付き矢高を `b` とし、`r=c²/(8|b|)+|b|/2` で劣弧を再構成する。中心は弦の中点から膨らみと反対側へ `r-|b|` だけ置き、掃引角は必ず180°未満とする。直前要素が弧なら膨らみ側はその反対側を既定とする。劣弧の符号・掃引規約はRendererのSVG弧描画と一つの実装を共有する。variationと筆致は端点を固定し、中間区間だけへ作用する。閉形、端点のない直前要素、退化した弦・矢高ではrelationをdropし、座標推定による修復やgovernorは行わない。

端点・接線・矢高の検証は、祖先groupのrotation等を含むすべての描画変換を合成したキャンバス座標系で行う。

関係は相対指定であるため、参照先の位置が動けば連なる要素すべてが動く。これにより「関係（=楽譜に記された秩序）は保たれたまま、構図が毎回変わる」というマクロの揺らぎが成立する。§13.1 の定義——秩序の中の変動——が、線の震えから構図スケールへ、原理を変えずに拡張される。

region（`at`）と relation を両方持つ instruction（プラグイン member 由来の双弧など）は、region 配置を先に適用した後で relation を解決する（v1.94）。touching では直前要素の演奏後端点が位置を確定するため、region は連鎖の起点・情報として扱われる。

typed compilerは、通常direct隣接instructionの正確な日英full literalと、同じflat Macro expansion内の隣接bound Emit間に明示されたrelationから、`connected`を同じScore consumerへ運ぶ。元Score index、dependency slot、owner、focus、seedを保つ。named位置はmovable、numeric位置はfixedであり、named region解決後に接続に必要な平行移動だけを適用して再clampしない。numericは既存physical geometry精度で必要deltaがzeroなら成功し、非zeroなら明示conflictにする。

recoverable なrelation失敗は、旧Stop入力を含むどのmodeでもSVG全体を止めない。失敗したrelationだけをerrorとして記録して外し、current instructionまたはMacro Emit、その所属group、後続dependencyは元の変形後配置と元Score index / owner / seedのまま描く。参照先をnearest survivorへ付け替えず、複数の移動要求が競合するときは一つを恣意的に優先せず元配置を保ち、その配置で成立しないrelationだけを外す。全描画単位の省略、source / lock / owner / exact Score joinのintegrity失敗、または描画対象が残らない場合は両mode停止する。旧5 relationのwarning / wire挙動は維持する。これはdirect shared/native経路であり、typed DDL本番pipeline、UI、設定保存cutoverの完了を主張しない。

validator / coerce で判明するinvalid relationは従来どおりwarningを記録してdropし、relationを発明しない。checked performerでのみ判明するrecoverableな不成立はerrorを記録し、そのrelationだけをdropする。instruction、所属group、後続dependencyは元の変形後配置で描画を続ける。grid layoutがrelationを消費する場合などwarning-classの失敗はstructured warningを記録する。一方、prior boundsの不足やcanonical-silentな退化幾何のfallbackは警告なしでrelationをdropする。

Engine 45のtyped `touching`も通常directと同flat Macroの隣接bound Emitから同じchecked performerへ届く。日英の四full literalは、有限宣言に書かれたLine / Arc対象を元のPreviousOneと照合し、型が違えばcanonical成功へ進まない。Macroは実際のtyped Emitを確認し、literalのnoun条件を作らない。Line / Arcだけが成功対象で、先行を変えずに両端を一致させ、Arcは上記と同じ劣弧再構成を使う。明示numeric geometryまたはrelative scale（normalのfactor 1も含む）は寸法を固定し、明示angleはcanonical両端順による弦方向を固定する。省略normalはTouchingに合わせて変わりうる。Numeric位置はanchor固定かつ最終geometryの既存must-fitを保ち、named focusはmovable/clippingのままとする。不一致はtyped conflictとなる。

typed Touchingにも上のrelation recoveryと元dependency / owner / drawing ordinal規則を適用する。不成立ならTouchingだけをerrorとして外し、current、同じgroup、後続dependencyを元の変形後配置で描く。新metadataのない旧Touchingには上記legacyの再構成・warning・dropを保ち、Connectedも変えない。typed本番pipeline / UI / 保存設定cutoverとwhole Step10の完了は含まない。

### 14.5 relation の owner

relation は記述者が Stage 1 または direct typed DDL で明示した場合、または明示 macro definition が emit した場合だけ Score に入る。Stage 1.5 は relation を追加・変更せず、coerce は invalid relation を警告付きで drop できるだけである。

### 14.6 制約と禁止事項

1. relation は 1 instruction につき最大 1 つとする
2. 解決不能な relation を座標推定や governor で修復しない
3. Stage 1.5 と coerce は relation を発明しない
4. 使用率、type 分布、drop 率は監査の鏡であり、発火率の floor や生成制御へ接続しない

### 14.7 歳時記への表示

歳時記の「あいだ」カテゴリは、関係の語彙が単なる幾何指定ではなく、余白と緊張を書くための語であることを示す。表示例: 「沿う」「触れない」「切る」「間に」「触れる」「つながる」。

---

### 14.9 雲形の設計（v1.89.1）

#### 14.9.1 なぜ雲形か

> 窓の外の雲は、二度と同じ形をしていない。それでも人は飽きずに見る。作品を、窓の外を見るように見てもらうこと——雲形はそのための形である。

円や四角は定義から来る。雲形には定義がない。ならば輪郭は誰が決めるのか——**演奏が決める**。楽譜には過程のパラメータ(揺らぎの性質・大きさ・素材)だけが記され、Renderer が performance seed から輪郭を生成する。同じ楽譜から、毎回違う雲が生まれる。

「記述は永続し、演奏は一回性」は、これまで配置と筆致に働いてきた。雲形はこの原理を形そのものに及ぼす。円は揺らいでも円だが、雲形は揺らぎの実現値がそのまま同一性である。

雲形は雲の模写ではない。名は雲形定規に倣う——不規則曲線の**族**を指す造形語であり、気象の雲ではない。大和絵の霞、料紙の州浜、墨流し——日本の造形は、不定形を恣意ではなく「不規則さの文法を持つ型」として様式化してきた。雲形はその系譜に立つ。LeWitt の "lines not straight, not touching" が否定形と過程で線を定義したように、雲形は過程で面を定義する。

#### 14.9.2 生成過程(輪郭は演奏が決める)

輪郭は二段の決定的合成で生成する。すべて performance seed 従属であり、同一 seed は同一輪郭を再現する。

1. **基底閉曲線**: 半径関数 r(θ) に周回連続な多オクターブ 1/f 信号を乗せた閉曲線。低周波成分が少数の大きなローブ(「大きく波打つ」)、高周波成分が細かな凹凸(「細かく揺れる」)を作る。ゆらぎ語彙がオクターブ配分に写像される
2. **法線変位**: 基底曲線の弧長に沿った第二の周期信号で法線方向に変位させ、入り江・くびれ(州浜的な凹部)を作る。変位振幅は局所半径・曲率に対して幾何学的に制限し、自己交差を構造的に防ぐ(これは governor ではなく、既存「安全な描画」と同種の幾何保証である)

輪郭のエッジ品質は筆致エンジン(道具文法)が担う——鉛筆の雲形とロットリングの雲形は別物である。内部は surface(wash / stipple / hatch 等)が満たす。`mode: carve` と組み合わせれば、黒地から不定形の光を彫り出せる。出力はベジェ当てはめを経て点数予算に従う。

#### 14.9.3 既存語彙との合成(修飾語を新設しない)

雲形が受け取る修飾はすべて既存語彙で表す:

- **ゆらぎ** → 輪郭のオクターブ配分(細かく / 大きく / 波打つ / 震える / 滲む)
- **わりあい** → 縦横比(縦長の雲形 / 横長・全幅の雲形——霞の帯はこれで書ける)
- **てざわり** → 輪郭の筆致(道具文法)
- **surface / いろ** → 内部の質感と色
- **あいだ** → 関係(雲形は「前の形」として参照可能。逐次解決は確定輪郭の bbox / 輪郭線に対して働く)
- **ばしょ / うごき** → 配置(散らされた複数の雲形は、それぞれ別の輪郭を持つ)

#### 14.9.4 選択規則(逃げ場にしない)

雲形は「分からないときの近似」ではない。制約による凝縮を守るため:

1. Stage 1 が雲形を選べるのは、(a) 記述に「雲形」/ "cloudform" が明示されている場合、または (b) 指示対象そのものが無定形である場合(雲、煙、霞、染み、島影、水たまり 等)に限る
2. 未知・不明瞭な対象は従来どおり既存図形で近似する。雲形を fallback にしない
3. Stage 1.5・coerce は雲形を注入・追加できない(§10.4 の適用)
4. 雲形の使用率・文脈はモチーフ台帳(洗練の会計)で鏡として監視する。governor・floor は設けない

#### 14.9.5 決定性と識別

輪郭生成は performance seed からの決定的導出であり、新しい乱数源・新しい hash 入力を追加しない。現行 `rh3` の算出 domain は不変で、保存済み `rh2` は legacy として再計算しない。楽譜(JSON Score)は雲形の過程パラメータのみを保持し、輪郭座標を保存しない——輪郭は演奏の実現値である。


#### 14.9.6 形式の会計

- **得るもの**: 定義によらない形。揺らぎが装飾ではなく形の本体そのものである最初のかたち。見る人の投影を誘う輪郭(設計原則5「動くのは見る人」が最も強く働く)
- **失うもの**: 「かたち=定義可能な図形」という語彙の均質性。解釈に迷った際の逃げ場になる危険(→ §14.9.4 で封じる)

雲形を含む現行描画の identity domain は `rh3` である。保存済み `rh2` は読み取り互換の legacy domain として再計算しない。

## 15. 開発方針

### 15.1 開発軸

**メイン軸**: Web UI（ブラウザ）+ Python FastAPI + LLM プロバイダ（Stage 別選択制、§12.5）
- 理由: 開発速度、デモのしやすさ、将来性
- 開発は Mac 上で行い、負荷の掛かる試験は配備先のテスト専用コンテナで回す（§22）

**補完軸**: ネイティブ Android アプリ（Pixel 9 で検証）+ LiteRT-LM（Gemma 4 E2B / E4B）
- server を正本とする後追い移植で、render engine の版を追随させる（現況は `android/ANDROID_SPEC.ja.md`）
- 「ローカルLLMでも動く」差別化ポイントとして保持
- Androidアプリの版は `android/VERSION` が独立に持つ

### 15.2 完了済み Phase の所在

PoC と初期機能の完了記録は [CHANGELOG.ja.md](CHANGELOG.ja.md) と [公開履歴アーカイブ](docs/history/changelog-v0.1-v1.71.ja.md) に置く。

### 15.3 現行開発の境界

現在の実装状況は [実装状況](docs/spec/implementation-status.ja.md) に記す。描画 engine の新しい変更は [CHANGELOG.ja.md](CHANGELOG.ja.md)、既存の版記録は次の版史に置く。本節は新しい実装 Phase を定義しない。

**engine の版ごとの記録は 2026-07-28 に [render engine の版史](docs/spec/render-engine-history.ja.md) へ移した。**
版史は過去の記録として保持する。現行の版・同一性・参照コーパス・保存とPNGの規則は本書 §2.1、新しい変更履歴は [CHANGELOG.ja.md](CHANGELOG.ja.md) を参照する。

## 16. ライセンス

**MIT License** （Copyright 2026 Shinichiro Oikawa）

- 「誰でも使える」コンセプトと一致する
- プロジェクトの広がりを優先する
- 将来的にデュアルライセンスへの移行は可能

---

## 17. 残件と検討事項

公開仕様は残件一覧や運用手順を持たない。実装済み範囲は [実装状況](docs/spec/implementation-status.ja.md)、設計・実装の経緯は [CHANGELOG.ja.md](CHANGELOG.ja.md)、既存の描画層の版記録は [版史](docs/spec/render-engine-history.ja.md) に保持する。


---

## 18. JSON Score

明示揺らぎは§13.6の三次元resolverから既存`Instruction.variation`へ届く。Scoreのdeserialize default（Medium / Medium / None）は従来どおりであり、sourceの一slot以上から解決するdefaultと区別する。作者は内部Variation JSONを自然DDLへ直接書かない。

明示named位置は通常DDLと宣言済みflat Macroの共通geometry consumerで次の`at.region`へ解決する。
値はcanvas各軸0..1のsemantic anchor領域であり、図形全体を収める範囲ではない。

| place identity | 領域 [x0,y0,x1,y1] |
|---|---|
| top | [0,0,1,1/3] |
| bottom | [0,2/3,1,1] |
| left_edge | [0,0,1/10,1] |
| right_edge | [9/10,0,1,1] |
| top_edge | [0,0,1,1/10] |
| bottom_edge | [0,9/10,1,1] |
| corner | 左上[0,0,1/5,1/5]、右上[4/5,0,1,1/5]、左下[0,4/5,1/5,1]、右下[4/5,4/5,1,1]の一つ |

Center / middleは元のcanonical centerとexact ownerの六focusを保つ。四辺は狭い帯であり固定点ではない。
隅はStage 2が`inku.score-place-selection.v1`専用domainで選ぶ。Verified original pre / expanded meaning
digest、NoneとSome(0)を区別するtag付きcomposition seed、directの元logical ordinalまたはMacroのsemantic
ordinal / expansion path / generated ordinalをframeし、SHA-256先頭byteのmodulo 4を左上・右上・左下・右下へ写す。
四択なので異なる構図seedでも同じ隅になり得る。選んだ隅をsource / canonical meaning / provenanceへ書き戻さず、
隅内のanchorは既存Rendererのrender seedが選ぶ。別の演奏・明示変奏は隅を変えない。
Tableはpolicyの有理数定義から最後にだけScore f64へ変換する。Policy IDは同じでも内容digestは変わり、
semantic schemaの新versionを意味しない。未指定位置は補わず、named/numeric conflict、numeric must-fitを保つ。
Noncenterとrelationの未対応境界は広げず、relationを黙って落とさない。このdeliveryはruntime / UI / 保存へ未接続で、whole Step10の完了ではない。

JSON Score は Stage 2 が生む機械可読の楽譜である。**最終的な作品ではない** — renderer が演奏する構造である。

楽譜の主要な概念:

- `canvas`: 選ばれたキャンバス比の識別子（`square`・`golden` など）
- `instructions`: 順序を持つ描画命令
- primitive のフィールド: canonical exact 9であるline・circle・ellipse・triangle・square・polygon・arc・point・cloudformと関連する処理データ。PointはCircleとは別のidentityを持つ丸いfilled markである。`rectangle`は10番目のprimitiveではなく、別の作者裁定とschema / versionなしに追加しない
- `weight`: 素材／道具の質
- `variation`: 目に見える揺れ・にじみ・震え・運動の挙動
- `arrangement`: 個数・分布・経路・グループ化・密度・減衰・色循環
- `rotation`: 形レベルまたはグループレベルの向き
- `color_hint`: カタログ色を解決するときの任意のヒントと、renderer が絵の性格として読む記述マーカー
- `note`: 任意の、機械が書く処理注記。**描画には決して届かない** — 演奏 seed の許可リストの外に在り、Stage 2 には決して出力しないよう指示してある。coerce と API は診断をここへ記録する。診断が色の記述と取り違えられないようにするためである。**これは処理が走った順の履歴であり、最終的な Score や絵の現状を要約する欄ではない。** 後続処理が先行診断の結果を覆した場合も両方残りうるため、`note` の一節だけを現在の色・形・配置の証拠にしてはならない。**宣言順は 2 番目に置いてある** — 任意フィールドの充填率は宣言順の末尾へ向かって上がるからである
- `at.region`: 任意の正規化された配置領域 `[x0,y0,x1,y1]`。renderer の seed が解決する
- `relation`: 直前の命令に対する任意の観察可能な関係 — `along`・`not_touching`・`cutting`・`between`・`touching`。触れる関係は両端点を固定する

**記述が明示した個数は、その後のいかなる読み取りより優先する。** Canonical meaningは値をlosslessなsymbolic intentとして保持する。Step 11のpure ceiling preflightは、展開、配列確保、またはその他のO(count) materializationより前に走る。`u32::MAX`等もclampや代表数へのsilent rewriteをせず、拒否時のallocation / materializationは0である。現行runtimeに残る閾値と代表化はcompatibility behaviorであり、canonical countを別の値へ変えるsemantic authorityではない。

**大きさには三つのauthorityがある。** `unspecified`、`explicit qualitative`、`explicit numeric geometry`を混同しない。現行subsetでは、allocationを持たないcount1のcircle / square / ellipse / cloudform / triangle / polygonについて、normalのdiameter / side / widthをcanvas短辺の`6/25`（0.24）、ellipse / cloudformのheightをwidthの`3/5`とする。Lineのnormal lengthとArcのnormal chordも`6/25`で、Arcのsagittaはchordの`1/4`、Pointのnormal diameterは`3/250`（0.012）である。Finite relative factorはsmall側がweak / standard / strong=`3/4` / `1/2` / `3/8`、large側が`5/4` / `3/2` / `7/4`、normalが`1`で、通常geometryへexact rationalとして一度だけ掛ける。Lineはlength、Arcはchordとsagittaを相似に、Pointはdiameterを拡縮する。既存`small`はstandard-smallであり、`普通の大きさ`というexplicit normalはunspecifiedへ畳まない。Explicit numeric geometryはqualitative sizeで変更せず、両方の併記はconflictにする。このsubset外のunspecified normalは未裁定であり、自由なdegree同義語やhidden LLMで補わない。

Explicit numeric geometryはdimension、basis、canonical base-10 coefficient / scale、source spelling provenanceを保持する。Scoreの`f64`へ変換するのは一つのdeterministic lowering boundaryだけで、silent clamp / rescaleをしない。過去のcircle `0.038` / ellipse `0.06×0.032`という固定寸法 calibration は現役candidateではなく、context前のcandidateはsymbolic size intentを保持する。値と経緯は CHANGELOG に置く。

Sizeとpositionを解決するcanonical policyの単一ownerは`inku-ddl`で、そのidentity / digestは`inku.geometry-resolution-policy.v1`である。Compiler lockはこのidentity / digestを参照・attestし、`ddl_engine_version`はactivation metadataに限定する。`size_rule_version`や二重ownerを作らない。

同じpolicyは明示angleも所有する。`horizontal=0`、`vertical=90`、`diagonal`は`45 / 135 / 225 / 315`、`rising` / `falling`はそれぞれ整数度`[-37,-23]` / `[23,37]`、`left_rising` / `left_falling`は`[203,217]` / `[143,157]`、`rotated`は各45度境界から5度を超えて離れた整数度を有限一様に選ぶ。SHA-256のangle専用domainへ、lock検証済みoriginal pre / expanded meaning digest、tag付きoptional `composition_seed`、logical occurrence、angle identityをframeして選ぶ。同じmeaningのinline / continuationは同じ選択になり、真の別occurrenceは別keyを持つ。effective focus、variation seed、render seed、raw source bytes、full-lock digestは材料にしない。

CircleとPointの回転extentは同じ半径、ellipseは理想楕円、cloudformとsquareは宣言width / heightの矩形envelope、LineとArcは最終的な有限端点・弧を使う。数値配置では短辺単位の宣言寸法を物理空間で回してcanvas各軸へ戻し、回転後extentだけをmust-fit判定する。回転前bboxで先に拒否せず、位置移動、縮小、count削減、別角度retryを行わない。Named focusは従来どおりmust-fitを追加せず寸法と`at.region`を保つ。Line / Arc / Squareのangleはdirectとflat Macro Emitの両方で同じresolverを通って`Score.rotation`へ届く。丸いPointの明示angleはunsupportedであり、別の回転形へ読み替えない。

同じpolicyがeffective focusを`at.region`へ写す六値も所有する: `upper_right=[0.60,0.18,0.82,0.40]`、`upper_left=[0.18,0.18,0.40,0.40]`、`lower_right=[0.60,0.60,0.82,0.82]`、`lower_left=[0.18,0.60,0.40,0.82]`、`upper_edge=[0.39,0.07,0.61,0.29]`、`right_half=[0.61,0.39,0.83,0.61]`である。既存4 closed shapeのNamed Score instructionは`center` / `position`を持たず、解決済みの`radius` / `size`と`at.region`を持つ。Line / Arc / Pointは有限な基準geometryとsemantic anchorに加えて`at.region`を持ち、Rendererがそのanchorをregionへ移す。数値positionだけはanchorのunit intervalとshape extentのmust-fitを検査する。Named経路はregionをshape-safe範囲と交差させず、寸法の縮小、fit目的の再配置・再抽選、空intersection停止を行わない。

作者A裁定では見切れを許す。Rendererが行うregion extentの短辺換算、performance seedによるanchor選択、基準点のunit-interval clamp（squareのtop-leftを含む）はそのままである。したがって座標補正が一切ない、またはshape全体が常に紙内に収まるという保証ではない。Engine 42では、point座標はcanvas各軸の正規化座標、size / radius / gapはcanvas短辺単位という既存wireを保ったまま、square / triangleのsemantic center、移動、回転pivot、performed bounds、relation、composite offset、arrangement fitを一つの物理短辺座標族で計算して各軸へ戻す。Engine 43ではLineの端点中点、Arcの弦中点、Pointの中心をsemantic anchorとする。Typed Arcは既存optional `position`へ弦中点を運び、field不在の旧Score Arcは円中心anchor・回転を保つ。Canvasを渡さない公開helperは従来の正規化座標互換を保つ。

現行subsetでは、省略countだけを1として解決し、zero / repeated / qualitative countはmaterializeしない。Touch省略はpen、continuity省略はsolid、closed surface省略は塗りで、明示emptyは塗らず明示solidは同じ既存fill経路へ届く。色省略には、Rendererの既存`work_color_assignment` / `resolve_color`と同じ実background / black / whiteのRGB・OKLCH L観測を明示contextとして要求する。`inku-ddl`の単一policyがbackgroundとの差の大きいblack / whiteを選び、同差はblackとする。明示色はpalette contextを要求せず、その色を保つ。各instructionの明示値は独立に優先する。旧Stop入力は互換で受けるが、recoverableなrelation意味エラーを全停止には使わない。OmitAndContinueはunsupportedなcolor / touch / continuity / surface quality / intensityを独立fieldとして省略し、実際に使ったcontrast color / pen / solid / fill、または保持した明示qualityを診断する。それ以外はsource instruction、Macro Emit / structural subtree / invocation、Ground、coordinated groupの最小成立単位で省略する。relationは不成立ならerrorとしてrelationだけを外し、図形とgroupを元の変形後配置で残す。Relationのprevious-one / twoは元source indexの意味を保持し、省略後の圧縮indexへ付け替えない。Lowering resultは使ったcanvas / background / resolved palette contextとgeometry policy digest、mode、outcome、gap、owner / span / dispositionを保持するが、元のsemantic document / canonical meaning / provenanceへdefaultやfocusを挿入しない。

静けさ・膜・記憶の場面のために繰り返しを間引く**静けさの密度 governor は、個数が明示されたグループには効かない** — 静けさは場面の読み取りであり、明示された数は読み取りではないからである。文字どおりのグループが合わせて `max_expanded_primitives`（既定 400）を超えるときは、最大のものから順に代表表現へ移し、次のものが譲る前に予算を測り直す。**読み手が数えられたはずの小さなグループは文字どおりのまま残る。**

Line / Arcはnormal appearanceで非fill、PointはCircleとは別identityの丸いfillになる。Pointの明示surface / variationは未裁定のためtyped unsupportedである。

場面の色調の規則は、いまのところ抽象色だけから選ぶ。

- 春・花・芽・暖かい光 → 赤／緑／白へ寄る
- 水・夜・月・雨・霧・冷たい空気 → 青／白／灰へ寄る
- 森・葉・草・苔・香り → 緑／白／灰へ寄る

9 つの抽象色（§3.1）では表せないニュアンスは、カタログに基づく描画のために `color_hint` へ残す。

**関係は逐次である。** `along`・`not_touching`・`cutting`・`touching` は直前の 1 命令を指し、`between` は直前の 2 命令を指す。**任意の id も前方参照も、関係のための補修 governor も無い。** 妥当でない関係は検証または coerce が警告を記録して落とし、命令は関係なしで通常どおり描画される。**coerce 層は妥当でない関係を取り除いてよいが、新しい関係を足してはならない。** JSON Score の `relation` は正規化 DDL の明示的な「前の対象」の句のために予約されている — `前の線に沿って` / `along the previous line`、`前の形に触れない` / `not touching the previous shape`、`前の線を切る` / `cutting the previous line`、`前の二つの間に` / `between the previous two`、そして明示の接触句 `前の線に触れる` / `touching the previous line` と `前の弧に両端で触れる` / `touching the previous arc at both ends`。**触れる関係が自発的に足されることはない。** 自然言語の近さ・律動・前後・近い・遠いは、関係ではなく位置・経路・回転・間隔で表す。

領域（`at`）と関係の両方を持つ命令（プラグインの member による双弧など）は、まず領域で置かれ、次に関係で解決される（v1.94）。触れる関係では**直前の命令の端点が最終位置を決める**ので、領域は連鎖の起点の情報として働く。演奏時に初めて解決不能と分かった関係は落とす。grid layoutがrelationを消費する場合などwarning-classの失敗はstructured warningを記録するが、prior boundsの不足やcanonical-silentな退化幾何のfallbackは警告なしでrelationを落とす。

`touching` では、現在と直前の命令がともに line か arc でなければならない。renderer は直前の命令の**演奏された端点**を取り、現在の端点をそこへ固定する。弦長 `c`・符号つきの演奏された矢高 `b` の弧については `r=c²/(8|b|)+|b|/2` で劣弧を再構成する。中心は膨らみの反対側に在り、直前が弧であれば新しい弧は既定で反対側へ膨らむ。劣弧の巻き方向は SVG の弧描画と同じ共有の約束に従う。揺らぎと筆致の演奏は両端点を固定したまま内部にだけ働く。閉じた形と端点を持たない対象は、警告を記録して**落とすだけ**で拒否する。演奏された幾何が退化した場合も描画時に関係を落とす — **座標の補修も governor も導入しない。**

端点・接線・矢高の検証は、祖先グループの回転を含むすべての描画変換を合成したあとの**キャンバス座標で**行う。

この 5 つ目の関係は、かつての緩い距離制約の一様な族を、**1 つの厳密な端点制約と引き換えにした**。その代わり、演奏された座標を Score へ凍結させることなく、二弧の葉のような閉じた有機的輪郭を書けるようになった。保留中の `continuing` 候補はこの版の外に在り、cloudform の面と地の表現が改善されてから再検討する。

システムは **DB の履歴レコードを正本として扱う。** SVG・JSON ファイル・PNG ファイルその他の作品は派生出力である。

---

## 19. キャンバスモデル

Canvas selectionはvisible DDLやmacroの意味ではなく、shared coreの`inku.canvas-format-registry.v1`から解決するhost optionである。同じDDLを異なるcanvasへ使え、DDL sourceの座標・語・canonical meaningは変わらない。Registryの形式と正の整数比は次の11組を正とする。

| ID | 比（width / height） |
| --- | ---: |
| `square` | `1 / 1` |
| `golden` | `809 / 500` |
| `a4` | `500 / 707` |
| `b4` | `500 / 707` |
| `pillar` | `1 / 5` |
| `oban` | `2 / 3` |
| `wide` | `47 / 20` |
| `byobu` | `11 / 5` |
| `vertical` | `9 / 16` |
| `sd_monitor` | `4 / 3` |
| `hd_monitor` | `16 / 9` |

選択が無いhost boundaryでは`square`をhost defaultにできるが、DDL compilerが`square`をsemantic factとして挿入する意味ではない。Hostがresolved selectionをScore / render context / historyへ運び、RendererがSVGの`width` / `height` / `viewBox`を決める。Stage 2が現行互換経路でcanvasを受け取る場合も、これはhost-resolved composition contextであってvisible DDL metadataではない。

現行runtimeの`plugin_storage["canvas-aspect"]`、`canvas_aspect` request alias、保存済み`Score.canvas` / `render_canvas_aspect*`、system / user plugin directory、plugin status / enable toggleはread compatibilityとして残る。これらは新規plugin authoring modelではない。Retirementとruntime / UI cutoverは後続Stepが所有し、本節は完了済みと主張しない。現行UIで比を変えたときは描画表示を消してplaceholderへ切り替えるが、表示中作品はlineage contextとして保持し、次の保存作品は`canvas_aspect_change`の子として記録できる。

Position座標は`0.0`から`1.0`の正規化のままで、Xはcanvas幅、Yはcanvas高さの割合である。左上は`(0.0,0.0)`、右下は`(1.0,1.0)`、exact centerは`(0.5,0.5)`とする。Named center、qualitative region、exact numeric coordinateは別authorityで、exact coordinateをStage 1.5のfocus targetにせず、silent move / clamp / snapしない。Boundary anchorの妥当性と、shape extentがcanvasからclipする診断は別に扱う。

Direct typed DDLは、JAの`半径N` / `直径N` / `幅N、高さN` / `一辺N`と`画面の横X、縦Yの位置`、対応するENの有限構造、および日英の有限7class size modifierを受け入れる。小数は元のspellingとsource spanをprovenanceに残し、意味では符号付きbase-10係数とscaleへ正規化する。Lock検証済みStage 1.5 v5 viewとhostが明示したcanvas / backgroundを入口とし、color省略時だけ対応するresolved palette contextも要求する。数値位置、またはverified direct instructionの元`place:center`と、place actionが解決済みのcircle、ellipse、cloudform、square、triangle、polygonの独立instruction群は、明示numeric geometryまたは現行normal / qualitative geometryと、省略count=1 / pen / solid / fill / contrast colorをactual `Score`へ変換できる。`none` / `solid` / surface省略の既存fillを保ったまま、`wash` / `grain` / `stipple` / `hatch` / `crosshatch` / `bleed` / `aquatint`は既存Rendererの`SurfaceSpec`へ、検証済みの`paper` / `washi` / `ink_wash` / `charcoal_ground` / `canvas` / `drawing_paper` / `mezzotint`はhost解決済みaspectを持つ`Canvas::Spec`の既存`CanvasGroundSpec`へ届く。数値のtexture / material defaultやseedをcompilerは作らない。solidな閉じた塗りのSurface intensityは道具別のnormal／dense／faintへ届く。非solid・Pointの明示surface等のrecoverableな未対応組合せは、旧Stop / OmitAndContinue入力にかかわらず最小fieldまたは実行単位を診断付きで省略し、残るScoreを返す。Groundだけも描画内容であり、Groundを残す場合も元の省略診断を保つ。整合性不良または全省略はstoppedである。このRust経路はruntimeにはまだ接続しない。

痕のisotropic size、円・弧の半径、`radial`の環、`at.region`の広がり、clusterの帯、pathの交差軸のずれは、そのallocationまたはcanvas短辺を基準に画素へ直す。Circleをaspect-correctに保ち、ellipseは記述したaspectを保つ。置き場所・region中心・cluster中心は幅と高さに比例し、pathの進行量（`margin` / `span`）と`arrangement.margin`は各軸の割合を保つ。この決定は§18の単一`inku.geometry-resolution-policy.v1` ownerに従う。

Direct typed DDLのfinite geometryには、JAの`長さN` / `弦長N、矢高N`と対応するEN `length N` / `chord N, sagitta N`も含む。Line / Arc / Pointは既存4 closed shapeと同じactual Score lowererへ入り、Pointは既存`半径N` / `直径N`を使う。JA `点`は独立noun headならPointであり、別の明確な形状headを修飾する同一phraseでは既存stipple surfaceのままである。

### 数値の解像度（マスターグリッド）

Renderer の共有`format_number`境界は数値を小数第6位で丸め、`-0.0`を`0`に正規化し、末尾の0と不要な小数点を取り除く。したがって書式は固定小数ではなく、出力値は最大6桁の小数部を持ち、整数としても書かれうる。現行仕様は数値の丸めを定めるが、固定幅の文字列表現や`-?\d+\.\d{6}`の一致を保証しない。

**小数第6位で丸める精度は維持し、書き出す量を減らすために下げない。** 座標や質感フィルタの数値精度を下げることは、末尾の0を除いて同じ値を短く表記することとは異なり、描画結果を変えうる。過去の精度比較の測定値は [CHANGELOG.ja.md](CHANGELOG.ja.md) に記録する。

---

## 20. モード

Runtime未接続のtyped compilerで揺らぎが不成立なら、旧Stop / Continue入力にかかわらず元instruction／malformed Emit／未宣言caller invocationを既存単位で診断付きに省略し、残るScoreを返す。元owner、理由、実処置を保ち、揺らぎを新しいfield-level回復単位へ広げない。Integrity不良または描画対象ゼロは停止である。製品runtime、UI、保存経路への接続は未完了である。

### 単一描画

記述者は指示を 1 つ書き、パイプライン全体を走らせる。得られた DDL は読み取り専用の解釈ボックスで確認し、DDL 編集ダイアログで直接編集できる。DDL からの再演は Stage 1 を飛ばし、Stage 2 と renderer をもう一度呼ぶ。

正規化 DDL は単一描画の入力の下に**読み取り専用の解釈ボックス**として現れる。

- v1.98 から Canvas のツールバーに置かれた `歳時記` トグルは、サイドドロワーを**閲覧専用の語彙リファレンス**として開く — 語のチップを押すと挿入ではなくプレビューが出る
- `DDL 編集` ボタンは、行番号・2 列の歳時記語彙パネル・短い DDL 構文ガイドを持つ大きなダイアログを開く。v1.98 から**語の挿入はこのダイアログのインライン歳時記だけで起きる**。ここは読み込まれたプラグインの語彙も並べる
- `自動補修` は設定から切り替える。既定は有効。無効にすると Stage 2 の出力は広い `coerce_score()` の補修を通さずに描画されるが、**要求された primitive／色の契約に反する命令は、硬い契約ガードが取り除くことがある**

同じ `DDL から描画` の操作は解釈ボックスの下にもあり、ダイアログを開かずに素早く再演できる。候補の metadata は、当てはまるところで render、composition、variation、interpretation の seed を示す。DDL 編集ダイアログの `描画` は、編集した DDL を保って Stage 2 と renderer だけを走らせ、自然言語の記述を解釈し直さない。

描画タブは明示の再生成操作を 2 つ出す。**別の演奏**は同じ Score を保ち、renderer にだけ新しい演奏 seed を求める。**別の構図**は保存済み正規化 DDL を保って `composition_seed` を進め、Stage 1.5 の閉じた六つの候補から焦点を選び直し、明示angleがあればStage 2で具体角度も、明示cornerがあれば隅も選び直す。構図族、技法、色、タッチ、relation、要素数は変えない。同じlock検証済みmeaningとattested `composition_seed`なら同じeffective meaningと角度・隅を再現する。別の演奏と明示変奏は確定角度と隅を保つ。保存済みScore / expanded artifactを優先し、原文を保存し、silent backfillを行わず、恒久的なold/new runtime switchを作らない。semantic schema / identityは変更bytesを旧identityと偽らない。D1の実装到達は§12.11のtyped v5からresource-awareなScore 0.10演奏coreまで接続したが、製品host runtime / UI / API / 保存への切替は未完了である。

v1.98 から単一描画は `POST /api/paint/stream`（NDJSON）を呼ぶ。解釈が終わった時点で `stage1` イベントを出し（正規化 DDL・使ったモデル・トークン数・所要時間・フォールバックの旗）、Stage 2 と描画が続くあいだ UI は解釈を見せられる。最後の `done` イベントは従来と同じ `PaintResponse` を運ぶ。`POST /api/paint` は同じロジックの包みとして応答の形を変えずに残るので、**CLI と Android に変更は要らない**。

v2.13.39 から合図は 4 つになった。写生層が動いた回は `sketch` が `stage1` より前に出て（粒度・フォールバックの旗・トークン数・写生に掛かった時間）、Stage 2 と coerce が終わって Score が確定した時点で `score` が出る（命令数・使ったモデル・トークン数・所要）。**段階表示はこの 4 つの合図で切り替わり、次の層を推測して先に出すことをやめた。**写生文と Score の本体はイベントに載せない（`done` が既に運んでいる）。**`stage1` の `elapsed_ms` は写生を含んだままである** — 内訳は `sketch` の `elapsed_ms` を引けば出る。**⚠ 最初のイベントが `sketch` になったため、写生層が動いた要求では Stage 1 の失敗が HTTP 502 ではなく本文の `{"event":"error","status":502}` で届く**（写生 off の回は 502 のまま）。「最初のイベントより前の失敗は HTTP、後の失敗は本文」という規則そのものは変わっていない。

DDL の再演は所要時間・トークン情報・停止ボタン・進捗マスコットを見せる。再演の停止は実行中の `/api/compose` 要求を中断する。単一描画と DDL 再演のあいだ、単一タブは実行中の効果を出し、バッチ／デモの開始操作は抑止される。

単一描画・DDL 再演・バッチ・デモの進捗表示には、**設定で選んだマスコットが 1 体**出る。選べるのは `Incu` と `Yuragi` の 2 体で、既定は `Incu`。名前は固有名詞なので翻訳しない。`Incu` は 5×5 の画素で組んだ立方体で、15 秒に 1 回ゆっくり回る。`Yuragi` は蟹で、左の鋏を 11 秒ごと、右の鋏を 8 秒ごとに持ち上げて挨拶する。切り替えは設定ダイアログで行う。**画面ごとに違うマスコットが出ることはない。**

### バッチ描画

バッチパネルは複数行の指示を受け取る。実行中は現在の行をハイライトし、現在の DDL 解釈を読み取り専用で表示する。バッチ実行は次のバッチ実行まで失敗レポートを保ち、バッチ指示の履歴をユーザーごとに保存する。**履歴は 50 件まで保つ（v2.13.21・それ以前は 20 件）。上限を持つのはサーバーであり、読み出しと書き込みの両方で切る。**一覧はウインドウの高さの半分を天井とし、入りきらないときはスクロールする。

**途中で終わったバッチは、止まったところから続けられる（v2.13.21）。** 再開は**まだ作品になっていない行だけ**を、**元の記述の行番号のまま**描く。「最後に描いた行の次から全部」ではない —— 途中で失敗した行があると、その後ろの描画済みを描き直すからである。再開の可否は、**最新のバッチ作品が最新の保存済み記述の最終行かどうか**で決まり、照合は**行番号と記述の両方**で行う（番号だけでは、記述を短くしたあとに無関係な実行を「未完」と読む）。再開時の条件（モデル・色カタログ・写生・暴れる・キャンバス）は**最後に描かれた作品の記録**から読み、**記録の無い条件は作らない** —— 記録の欠落は「その設定が off だった」ではなく「その記録より古い」ことを意味するので、既定値を作ると別の条件で再開することになる。

各行を読ませてサーバーに色カタログを選ばせる選択は、**バッチ専用ではなく色カタログの選択そのもの**である（下記）。**v2.9.39 までバッチはこれを自前のチェックボックスで持ち、v2.9.22 まではブラウザ側でカタログを乱択していた。**

色カタログのダイアログは、13 のカタログの**上に「記述から自動選択」を 1 つ置く**。これは色を持たない選択で、選ぶと描画のたびにサーバーが記述を読んでカタログを決める（`catalog_mode` を `auto` にし、`catalog_id` には **モデルに届かないときや存在しないカタログを名指ししたときにサーバーが保つフォールバック**として既定カタログを運ぶ）。履歴レコードは実際に使われたカタログを保存するので、**推敲と描き直しは自動選択を引き継がず、その作品のカタログで描く**。**履歴レコードは、解決後のカタログに加えて「どう指定したか」（`catalog_mode`）も保存する（v2.13.21）** —— 解決後の id だけでは、そのときに自動選択を頼んだのかカタログを名指ししたのかが読めないためである。**これを読むのはバッチの再開だけで、自動選択を頼んだ実行は自動選択のまま続く。**推敲と描き直しの振る舞いは変えない。**この記録より古い作品は値を持たず、値が無いことは「自動選択ではなかった」ではなく「記録されていない」を意味する。**

**カタログの選択はユーザーごとにサーバーへ保存する**（`model_settings.color_catalog_id`）。描画にはセッションが要るので、ブラウザ単位の値は「別のユーザーの選択」にしかならない。保存できるのは現存するカタログか `auto` だけで、引退した id は既定へ落ちる。

ダイアログの外を押すと保存／確定の操作とまったく同じく現在の選択が確定する。取り消しボタンは従来どおり、開いた時点の選択のスナップショットへ戻す。

### デモ描画

デモモードは種となる語句から指示を繰り返し生成し、描画し、設定された間隔だけ待ち、また繰り返す。デモの設定はユーザーごとに保存する。**デモの結果は既定では保存しない** — 記述者は現在の描画を明示的に履歴へ保存できる。

デモも同じ選択で描く。ステータスバーは、現在のカタログ選択だけでなく**描画結果が報告したカタログ**を反映する。**v2.9.39 までデモはユーザーごとのデモ設定に自前の `catalog_mode` を持ち、v2.9.22 までは乱択だった。**

`/api/paint` は `catalog_mode` を `fixed`・`auto`・`random` のいずれかで受け取る。`fixed` は `catalog_id` をそのまま使い、`auto` は記述を読み、`random` は `catalog_id` 以外のカタログを引く。**`random` は推敲に属する** — その「別のカタログ」は 1 つの記述を違う色で見るために在り、記述を読ませれば毎回同じカタログに落ち着いてしまう。`catalog_mode` を省いた要求は `fixed` として振る舞う。このフィールドは v2.9.22 で真偽値の `random_color_catalog` を置き換えた。

デモの実行中は、文脈を混乱させうるところで履歴の操作を制限する。

---

## 21. 履歴とデータの完全性

履歴はサーバーの DB に保存する。**DB のレコードが正本である**もの:

- 元の入力
- 入力側の正規化 DDL（Stage 1 の `ddl`）と、Stage 1.5 の実効 DDL（`expanded_ddl`、Stage 2 の入力）
- JSON Score
- サーバーが描画した SVG
- モデルのメタデータ
- 色カタログ
- 時間とトークンのメタデータ
- スター状態
- ゴミ箱状態

**Web UI はクライアントが生成した SVG を、信頼できる履歴の中身としては送り返さない。** `/api/paint` がサーバー側で履歴を生成して直接保存する。互換のための履歴エンドポイントは、クライアントが送った SVG を信じるのではなく **JSON Score から描画し直す**。

SVG のダウンロードでは、Web UI は Display・Editable・Compat の 3 つを出す。Display は保存済みの SVG を落とす。Editable と Compat はサーバーの描画エンドポイントを呼ぶので、**DB に SVG の塊を重複させることなく**、過去の履歴も現在の書き出し構造の恩恵を受けられる。

CLI の `paint` と `batch` も、保存する SVG ファイルのために `--svg-profile display|editable|compat` を受け取る。

**サーバー側の作品ファイル保存は、管理者が管理するサーバー全体の設定である。** 設定ダイアログは管理者だけに見える「その他（サーバー）」タブを持ち、次を扱う。

- 描画ファイルの自動保存の有効化・無効化
- 出力フォルダをサーバーの絶対パスとして設定
- 自動 PNG のサイズを 1080px か 2160px から選択

サーバーはこれらを `app_settings.output_save_settings` に `enabled`・`output_dir`・`png_size` として保存する。`INKU_OUTPUT_DIR` と `INKU_OUTPUT_PNG_SIZE` が初期値を与え、未設定なら既定は `~/.local/share/inku/outputs` と 2160px。API の `PUT /api/settings/output-save` は管理者専用で、絶対パスだけを受け取り、PNG サイズを 1080 か 2160 に制限する。

**自動保存を切っても DB の履歴保存は切れない。** 履歴 DB は正本のままで、SVG・JSON・入力テキスト・正規化 DDL・PNG といった派生ファイルだけが飛ばされる。有効なとき、作品ファイルはユーザーと日付でまとめて `<output_dir>/<user_id>/YYYY-MM-DD/YYYYMMDD_HHMMSS_<history-id>...` の下に置かれる。

「その他（サーバー）」タブは保存ワーカーとキューの設定・保存の統計・PNG のサイズを示す。保存ワーカーは並行するファイル保存ジョブ、キューは保留中の保存ジョブの上限である。**キューが満杯なら、サーバーは DB の履歴を守り、作品ファイルの保存だけを飛ばす。**

**サーバーログの保持も管理者が管理するサーバー全体の設定である。** 設定ダイアログは管理者専用の「ログ保持」タブを持ち、アプリケーションログの保持の有効化・無効化、保持日数、日次／週次／月次のローテーション間隔、ローテーション済みログの圧縮を扱う。既定の方針は有効・日次ローテーション・90 日保持・圧縮あり。

サーバーはこの方針を `app_settings.log_retention_settings` に `enabled`・`retention_days`・`rotate`・`compress` として保存する。`INKU_LOG_RETENTION_DAYS` と `INKU_LOG_ROTATE` が初期値を与える。`PUT /api/settings/log-retention` は管理者専用で、保存された方針を更新する。

**この方針を実行するのはアプリケーション自身である。** サーバーはログファイルを `INKU_LOG_DIR`（既定は `~/.local/share/inku/logs`、コンテナ配布版のイメージは `/data/logs`）へ書き、保存日数ぶんの世代を保ち、圧縮が有効なら回転済みを gzip にし、古い世代を自分で削除する。`GET /api/settings/status` は現在の方針を、**書き出し先といまあるファイルの一覧**とともに返す。**ホスト OS へ当てる生成ファイルは無い。** これは DB バックアップの方針と同じ形であり、**プラットフォームが実行する方針は systemd も logrotate も持たないコンテナ配布版で同じにならない**ため、こちらへ揃えた。

**同じ行は標準出力にも出続ける**ので、運用者は `journalctl -fu <service>` とコンテナの `docker logs` をこれまでどおり使える。コンテナ配布版では、daemon が標準出力から集めるぶんの上限を `compose.yaml` の `logging` が持つ。`inku-api` と `inku-server` は 60 文字の `=` で囲んだ起動バナーも出す。バナーはサービスの役割・アプリケーション版数・Build 番号・ビルド日・モード・待ち受けのホストとポート・実行環境／プラットフォーム・ログの出力先を含む。API のバナーは有効な render engine の ID と版数を含む。API と Web UI は役割に合った異なる絵文字の組を使う。

---

## 22. セキュリティと運用

Web アプリは認証・権限グループ・作品の可視範囲と共有・セッション・ユーザーごとの設定・プロフィール編集・ユーザー管理を含む。**パスワードは salt 付き PBKDF2-SHA256 のハッシュで保存する。**

**権限グループ（v2.12.0）。** 何ができるかは、利用者が属する権限グループが決める。グループは **`admins`・`leaders`・`users` の 3 つに固定**し、利用者が増やせるようにはしない —— 増やしたくなる需要は作品単位の共有であり、それは可視範囲の側が担う。**1 人は複数の権限グループに属せる**（多対多）。**判定の入口は述語 1 本に集める** —— 分岐を散らすと、可視範囲を書くときに漏れが出る。**利用者行の `role` 列は残すが、どの判定も読まない。**残す理由はバックアップからの復元で、列を落とすと本版より後に取った DB が本版より前の版で開かなくなる。**列は所属から機械が導出した写しとして書き続け、人は書かない**（手で写した値を検査で凍らせると、正本が動いた翌日から緑のままずれを守る）。**起動時の移行は 1 対 1 かつ冪等**とし、旧 `admin` を `admins`、`group_lead` を `leaders`、`user` を `users` へ写す。**「管理者は同時にリーダーでもある」と読み替えない** —— 読み替えると、移行が広げた所属と人が意図して広げた所属を、あとから区別できなくなる。**組織グループは別の実体で、1 人 1 つのまま**、権限グループとは独立に判定する。

**可視範囲と作品ごとの共有（v2.12.2）。** 何ができるか（権限グループ）と何が見えるかは別の軸である。**既定の見える範囲は所属が決める** —— `admins` は全部、`leaders` は自分の組織、`users` は自分の作品。そこへ**作品ごとの ACL が足す**。ACL の 1 行は**（作品・宛先の種類・宛先）の 3 つ組**で、権限は `read` と `write` の 2 つ。3 つ組にするのは、**同じ相手に対して作品ごとに違う権限を与えられるようにするため**である。**ACL は id だけを保存し、名前を 1 つも持たない** —— 利用者名も組織名も、変えれば共有はそのまま追従する。**判定はすべて可視述語 1 本を通す。生の SQL で書かれた経路も同じ述語を通す** —— 全文検索の経路が漏れると、**現れ方は「見えすぎる」ではなく「検索したときだけ見えない」**になるので、見えるようになる向きの検査では捕まらない。**書き込みの拒否は 403 ではなく 404 と「0 件」で表明する** —— 403 は「その作品は在る」と教えてしまう。**設定に ACL は無い**（個人設定は本人のみ、グローバル設定は `admins` のみ）。

**作品が自分で言うグループ宛の共有（v2.13.36）。** 可視範囲の 3 つ目の入口である。**束で示したい相手が居るとき、ACL は 1 行ずつ書くしかない** —— 実際、本番の `history_acl` は今日まで 0 行である。**形は Linux のファイルシステムに寄せる** —— 所有者は `user_id`、グループは `share_group_id`、読み取りビットは `for_share`。**world に当たるものは作らない**（作者裁定・2026-08-17。「誰でも読める」は組織の外へ出す判断なので、旗のついでに入れてよいものではない）。**見えるのはビットが立ち、かつグループが一致するときだけ**である —— ビットだけは宛先の無い許可、グループだけは誰も開いていない宛先で、**どちらも単独では権限を意味しない。****宛先を省いて立てると所有者の組織グループが入る**（新しいファイルが作った人のグループを取るのと同じ）。**他組織を名指せるのは `admins` だけ**で、非 admin には 403 を返す。**ただしその 403 は名指したときにだけ掛かる** —— `chmod g+r` はグループの変更権を要求しないので、一度開いた作品を開き直すのに管理者権限を要求すると、**宛先を選んだ本人がそれを繰り返せなくなる**。**ビットを下ろしても宛先は残す** —— `chmod g-r` はグループを忘れない。消すと、次にビットが上がったときに黙って別の相手へ向き直る。**旗が広げるのは読み取りだけで、`_writable_by` は動かさない。****系譜の節点と辺は付いてくるが、奥書は付いてこない** —— 旗の節を ACL と同じ枝（作品 id を渡す呼び出し）へ置いたためで、`list_okugaki` は作品 id を渡していない唯一の呼び出しである。**判定は ACL と同じく可視述語 1 本を通し、生の SQL の経路も同じ節を持つ。**

**系譜は持ち主をまたぐ（v2.12.2）。** 読める他人の作品を親にでき、根の id を継ぐので、**1 つの群が 2 人にまたがり、見える節点の数は見る人によって違う**。**読めない節点は本文を伏せて出し**、`deleted`（削除済み）と `not_permitted`（非公開）を**別の語で区別する** —— どちらも空の点線カードとして描かれるので、**札が無いと「もう無い」と「持ち主に頼めばよい」を見分けられない**。**辺の可視は子に従う。その帰結として、親の所有者も派生を見られない** —— 例外を作れば、親に従わせる案が退けられた理由がそのまま親の側で復活する。**共有された作品の奥書は、他人が書いたものも読める** —— 奥書を「作品への注釈」と読むためである。

**単独利用モード（v2.11.19）。** 個人が自分の機械で使うとき、共有サーバーのための入口の手続きは過剰である。`INKU_SINGLE_USER` を立てたサーバーは、利用者を 1 人に定めて自動的にログイン済みとして扱う。**マルチユーザーの機構は取り除かない。既定の所在を分けるだけである** —— コードの既定は off とし、すでに動いている配備が版を上げただけで無防備にならないようにする。配布物の既定は on とし、起動してブラウザを開けばそのまま書ける状態にする。単独の利用者は初回に最も古い管理者として解決し、その結果を利用者の id で書き留める。**名前ではなく id で指すのは、改名しても指す先が変わらないためであり、利用者行ではなく設定へ書き留めるのは、単独の利用者が構造的に 1 人しか居ないようにするためである。**書き留めた値は DB の中にあるので、バックアップとともに退避され、ともに戻る。管理者が 1 人も居ない DB では単独利用モードは働かず、要求は拒まれたままとする。**単独利用モードでも、パスワードの変更とユーザー管理は隠さない** —— 配布物の既定では利用者のパスワードが誰も知らない値になるため、そこが単独の運用から通常の運用へ戻る唯一の道である。サーバーは単独利用モードであるかどうかを、版とビルド番号を返すのと同じ公開の応答で伝える。

App rail のユーザーメニューは、ログイン中の利用者のプロフィールダイアログを開く。ダイアログは `PATCH /api/auth/me/profile` を通じてメールアドレスとパスワードを更新できる。**パスワードの変更は現在のパスワードを要求し**、このエンドポイントは管理者のユーザー管理 API とは別である。

設定の可視性は権限グループに応じる。**DB 設定とユーザー管理は `admins` グループに属する利用者にだけ見える。** プラグインタブはログイン中の全利用者に見えるが、**プラグイン設定の変更とプラグインストレージの更新 API は `admins` に制限する。**

Serverの正本永続化はSQLAlchemy上のSQLiteだけを使う。`INKU_DB_URL`と派生thumbnail DB設定はSQLite URLだけを受け付け、両方を検証してからどちらのengineも作る。非SQLite URLを拒否したあと空の既定DBへ黙って切り替えることはしない。Server SQLAlchemy/SQLiteとAndroid Room/SQLiteはそれぞれ自身の物理schemaを持ち、将来iOS adapterを作る場合も同じ論理契約へ別の物理mappingを持つ。同じDB file、table名、column配置を共有するという意味ではない。論理契約とhost mappingの正本は[`persistence/README.md`](persistence/README.md)と[`persistence/contract.json`](persistence/contract.json)である。Server専用の認証・管理tableと端末専用のprovider・model・cache tableはhost extensionであってparity gapではない。このmappingは保存済みSVG、Score、hash、NULLの意味を変えない。

Serverのschema lifecycleはversion付きmigration registryが所有する。fresh DBはschemaとregistryを同じ単一writer transactionで作る。registryを持つDBは版とchecksumを検証して通常起動し、旧schema用の全件repair scanを毎回は行わない。registry導入前のDBは、明示的に登録されたschema fingerprintと完全なFTS状態だけを受け入れる。未知のfingerprint、部分的なFTS、未来のregistry版、checksum不一致は、schemaやrowを変更する前にfail closedする。

受け入れた旧DBを変更する前には、SQLite Backup APIでWALを含む読取可能なsnapshotを作る。その後に`BEGIN IMMEDIATE`相当の単一writer境界を取り、migration前後で各tableのprimary-key identityと、履歴の`id`・`input`・`score`・`svg`のcanonical byteをstreaming digestで照合する。`PRAGMA quick_check`とforeign-key検査も必須で、どれかが失敗すればtransactionをrollbackし、検証済みsnapshotを回復判断のため保持する。手動・定時backupも同じSQLite-native snapshot ownerを使い、WALを無視するmain fileだけのcopyへfallbackしない。

`server/src/inku_server/db.py`は既存importとcall shapeを保つ互換・composition façadeである。物理schema、設定、engine、migration、invariant、backup、および認証・設定・履歴・検索・系譜などのdomain persistence ownerは`server/src/inku_server/persistence/`に分かれる。façadeの残存行数だけを理由に再分割せず、新しい永続化処理は対応するownerへ置く。

Androidはこの論理契約を共有するがServer DBを開かない。Room v1–9からv10への移行では、通常のRoom singletonを開く前にv1–9だけを明示的に削除し、DB本体・journal・派生thumbnailを捨ててfresh v10を作る。SQLite外のdownload済みmodel fileは残す。既存v10は保持し、v11以上、non-empty v0、読めないDBはbyteを変更せずfail closedする。v10以後にgeneric destructive fallbackは設けず、明示的なRoom migrationまたは新しい作者裁定を要する。

DB 設定タブは現在のSQLite DBファイルサイズも示す。管理者はDBのレプリカバックアップを、日数の間隔・時刻・自動世代の最大数で設定できる。既定は7日・03:00・4世代。手動バックアップは即座に作れ、自動世代の上限とは別に保存される。backupとrestoreはSQLite file boundaryを使う。

**間隔がどの日かを決め、時刻がその日のいつかを決める。** 次の期限は**最後に取ったバックアップから**導き、スケジューラがたまたま目を覚ました瞬間からは導かない。夜遅くに取ったバックアップが後続を引きずらないためである。

定時バックアップは、アプリケーションの lifespan が所有する常駐スケジューラが取る。1 分に 1 回、期限かどうかを尋ねる。`INKU_DB_BACKUP_SCHEDULER=0` で外せる。**1 分の刻みは意図して粗い** — 期限がループ自身の周期ではなく最後のバックアップから来るので、目覚めが遅れてもコピーは 1 つ遅れるだけで飛ばされない。**設定状態のエンドポイントを読んでもバックアップは作られない。** v2.9.7 まではそのエンドポイントが唯一の引き金で、間隔 N 日は実際には「N 日が過ぎたあと管理者が次にパネルを開いたとき」を意味し、しかもパネルを更新しただけでレプリカが書かれることも意味していた。**どちらの性質も無くなった。**

設定状態の応答は、バックアップがいま何を占めているかも報告する — 保持されている各ファイルの世代・種別・時刻・サイズである。**世代 1 が最新の自動バックアップ**で、番号が最も大きいものが次に間引かれる。**手動バックアップは決して間引かれないので世代番号を持たない。** 一覧は 50 行で止まるが、**報告される総数と総サイズはすべてのファイルを覆う**ので、打ち切りが使用量を過小に見せることはない。

並行する描画要求はアプリケーション層で上限を持つ。Stage 1 と Stage 2 の LLM 呼び出しは `INKU_STAGE_WORKERS` と `INKU_STAGE_QUEUE_LIMIT` が制御する有界の executor を共有する。容量を取れないとき、または段が硬いタイムアウトを超えたときは、段の硬いタイムアウトと同じ決定的フォールバック経路をたどる。**タイムアウトした LLM 呼び出しは、プロバイダの呼び出しが返るまで下地の Python スレッドで走り続けうる**ので、そのワーカーが実際に終わるまで容量の枠は保たれる。タイムアウトしたプロバイダ呼び出しが無限の滞留を作らないようにするためである。

ユーザーごとの描画カウンタは**データベース側の単一のアトミック加算**で更新するので、同じ利用者の `/api/paint` が同時に来ても生成回数を落とさない。履歴の一覧・取得・スター・ゴミ箱・復元・削除はいずれも可視述語で範囲を切る。**v2.12.2 まで範囲は `user_id` の一致だけだった**が、いまは所属由来の既定スコープと作品ごとの ACL がそこへ足す。**それでも通り道は 1 本のままで、範囲を持たない経路は無い。**管理者向けの状態応答は `stage_execution` として Stage のワーカー数・キュー上限・submitted / completed / failed / timed_out / rejected のカウンタを含む。

**作者のローカルサーバー固有の運用詳細は、意図してこの公開仕様に含めない。** それらは製品 repository 外の private internal documentation に集約する。

アプリケーションは macOS で開発する。**負荷が継続する試験——試験一式の全走、摂動の全走、参照コーパスの焼き直し、ラスタ化、ベンチのラン、移植の JVM 試験——は配備先ホストのテスト専用コンテナで回す**（**試験の器は用途ごとに分かれる**）（手順は `AGENTS.md`）。実装物は従来どおり rsync で同期し、systemd サービスを再起動して配備先ホストで確認する。本番の Docker Compose イメージは、通常のソース変更ごとに作り直すのではなく、リリース候補などの節目で確認する。**テスト専用コンテナとリリースのイメージは別物である** —— リリースのイメージは試験の依存を持たないので（`uv sync --frozen --no-dev`）、試験の器は同じ土台に dev 依存を足した別のイメージになる。**測定について言えるのは「リリースと同じ土台の上で測っている」までで、「リリースと同一の環境で測っている」ではない。****凍結物（参照コーパス・移植の参照 fixture）は、リリースが走るのと同じ Linux で焼く** —— macOS の libm と glibc は sin/cos/hypot で 1 ULP 食い違い、量子化の網の外に在る値はそこで割れる。**Git はソースの履歴のために使うのであって、ローカルサーバーとのファイル交換の手段としては使わない。**

**engine の版ごとの記録は 2026-07-28 に [render engine の版史](docs/spec/render-engine-history.ja.md) へ移した。**
リリース版史は過去の記録として保持する。現行の版・同一性・参照コーパス・保存とPNGの規則は本書 §2.1、新しい変更履歴は [CHANGELOG.ja.md](CHANGELOG.ja.md) を参照する。

---

## 23. CLI

`inku-cli` は API を通じて inku サーバーを操作するコマンドラインクライアントである。当初の目的は、Stage 1・Stage 1.5・Stage 2・renderer の挙動を調整するための、自動の記述／画像生成・品質講評・フィードバックループを支えることにある。

CLI の設定はローカルで編集可能である。ベース URL・プロバイダとモデルの選択・タイムアウト値を**サーバー DB の外に**保持する。

`inku-cli paint` と `inku-cli batch` は `--input-mode paint|ddl` に対応する。既定の `paint` モードは自然言語の入力を `/api/paint` へ送り、Stage 1 → Stage 1.5 → Stage 2 → 描画のパイプライン全体を走らせる。`--input-mode ddl` は入力テキストを**既に正規化された DDL** として扱い、Stage 1 を飛ばして `/api/compose` へ送る。`--input-mode ddl --save-history` を使うと、CLI は compose の結果を `POST /api/history` で保存するので、出力は通常のサーバー履歴に現れる。`/api/compose` は Stage 1.5 の展開後の**実効 DDL** を返し、CLI の出力と履歴はその実効 DDL を使う — DDL から描画までのベンチマークの対応を保つためである。

CLI は指示文の言語を `--instruction-lang auto|ja|en` で送る。既定の `auto` はサーバーに入力テキストから日本語か英語かを解決させる。`--ui-lang` は表示文脈のメタデータとして与えてよいが、**解釈は制御しない**。

`inku-cli batch` はベンチマーク要約の JSON ファイルを書ける。出力ディレクトリを使うとき、既定の要約のパスはそのディレクトリの `analysis-summary.json` である。要約は成功したすべての標本と、フォールバック・遅い・通常の標本の講評用のまとまりを含む。**遅い標本は診断専用である** — 無料の推論エンドポイントが待ち行列に入っていたとしても、成功した描画は品質講評の一部であり続ける。

ベンチマーク要約は、調整に使う診断のトレースも含む。

- `color_trace` — 要求された色・Score に在る色・欠けている要求色・警告・否定された色マーカー
- `negated_color_markers` — 「not green」や `緑には寄せず` のような句が、緑の欠落として誤って数えられないようにする
- `score_motif_hint_counts` と `score_motif_hint_lines` — `leaf_cluster`・`paper_shard`・`ripple_knot`・`mountain_sign` のような複合モチーフの補修のため
- `math_balance_markers` と `math_balance_marker_lines` — 放射状のフィボナッチ数・黄金比に近い中心・三分割に近い中心・釣り合いを取る対向配置といった、検出された構図マーカーのため

`inku-cli contact-sheet` は PNG 出力のディレクトリから PNG のコンタクトシートを作り、ベンチマークの講評が手作業の画像組みに頼らずに済むようにする。

---

## 24. 正本の所在

**`SPEC.ja.md` が正本である。** `SPEC.md` は維持される英語公開版である。

仕様を更新するとき:

1. `SPEC.ja.md` を先に更新する。
2. 英語の `SPEC.md` を、**同じ内容を節ごとに**運ぶよう改める。**どちらの言語も、他方に無い節を持ってはならない**（2026-08-02 作者裁定）。
3. **省略しない。** かつての作法は英語の文言を簡潔に保つよう求めていたが、その指示は撤回した — 正本より黙って少なく語るファイルを生んだからである。
4. 日本語の元に無い、英語だけの挙動を持ち込まない。
5. 現行契約は仕様へ、時系列の実装の詳細は変更履歴へ置く。
6. `server/scripts/check_docs.py` が両ファイルの見出し形状の一致を見る。**これがこの規則の唯一のゲートであり**、ドキュメントの変更をマージする前に必ず走らせる。
7. 同じゲートが、**英語側の禁止語**（`web/src/lib/i18n/GLOSSARY.md` §5-1 の `artwork` / `palette` / `AI-powered` / `magic`）も見る。**バックティックで囲まれた span は識別子とみなして検査しない** — コードの enum 名やフィールド名は、英語の散文の中でも実物の綴りのまま残すのが正しい。凍った記録である `CHANGELOG.md` と `docs/history/changelog-*.md` は、宣言された除外である。

---

## 付録: リポジトリ構成（概観）

```
inku-lang/                 # github.com/oikawas/inku-lang
├── SPEC.ja.md / SPEC.md               # 仕様（日本語正本 / 英語公開版）
├── PROJECT_CONTEXT.ja.md / .md        # 開発者・AI 向けの短い入口
├── CHANGELOG.ja.md / .md              # 時系列の実装・設計記録
├── README.ja.md / README.md           # プロジェクト紹介
├── server/                            # FastAPI バックエンド (inku_server, uv 管理)
├── web/                               # SvelteKit 2 + Svelte 5 フロントエンド
├── cli/                               # inku-cli (HTTP API クライアント、uv 管理)
├── shared/                            # server と CLI が共有する解析パッケージ (inku_analysis)
├── core/                              # 共有 Rust core（DDL compiler / render engine / score / SVG raster）
├── persistence/                       # Server と Android が共有する論理 SQLite 永続化契約
├── docs/                              # 公開文書（architecture / spec / guide / history / i18n）
├── manual/ja|en/                      # 利用者マニュアル（日英 7 対）
└── android/                           # ネイティブ Android 実装（正本: android/ANDROID_SPEC.ja.md）
```

モジュール構成・API 経路・CLI サブコマンド・語彙定数の**現行値は本書に列挙しない**。次を正とする:

- 語彙・定型句・マーカー・領域・weight 特性・検証閾値: **reference dump**（`GET /api/reference` / `inku-cli reference --md`。実装テーブルの機械生成鏡）
- API 経路: `server/src/inku_server/api_core/routers/`（FastAPI ルート定義 10 本）と
  `server/src/inku_server/api.py`（`app` の組み立て・ミドルウェア・`include_router`）
- CLI サブコマンド: `inku-cli --help` および `manual/ja/cli-reference-for-ai.md`
- 各パッケージの内部構成: `PROJECT_CONTEXT.ja.md` の「現在の製品状態」（**パッケージ README への委譲は 2026-08-02 にやめた**。`server/README.md` は空・`web/README.md` は SvelteKit の雛形・`cli/README.md` は使い方と `--help` の写しで、3 つとも内部構成を書いていなかった）

初期 Python PoC の `ddl/` ディレクトリ（Android 補完軸のベース）は役目を終えて木から消えた。実装は `server/` が引き継いでいる。

---

## 洗練の契約

洗練は分岐・語・部品・規則を無自覚に増やさず、削減または維持の理由を CHANGELOG に残す。類似特徴、モチーフ頻度、Vision 所見、coerce 発火率は観察の鏡であり、既定生成、抑制、受け入れ、品質関数へ自動接続しない。系譜は明示された派生 edge だけを根拠とし、類似性から推測しない。

通常生成の指示言語は入力から自動判定する。保存済みの Stage 別言語と `language_variation` metadata は読み取り・再現互換のため残るが、言語比較 UI は現行機能ではない。版・Build ごとの導入、削減、UI 変更、会計記録は [CHANGELOG.ja.md](CHANGELOG.ja.md) と [公開履歴アーカイブ](docs/history/changelog-v1.72-v2.4.ja.md) に置く。

## 自律推敲の方式

系譜の「AIに自律推敲させる」は、世代数を1〜10に限定した反復操作であり、最終作品の判定は人間が行う。ユーザーは実行前に次の方式を選ぶ。

- `ランダムな自動推敲`: 有効にした読み取り・色カタログ・配置・タッチ・変奏から世代ごとの変動対象をランダムに選ぶ。Visionは使用しない。方向性テキストは読み取り世代の描画テキストにだけ反映されるため、その条件をランダム方式のUIに明示する。
- `AI Visionによる自動推敲`: ユーザーがVisionモデルを接続先別一覧から明示選択する。選んだモデルは、その実行中、Stage 1・Stage 2の生成とVisionの助言のいずれにも使うが、三つの役割と各promptは分けたままにする。各世代の保存画像をサーバーでPNG化し、元の指示、ユーザーの方向性、許可された推敲要素とともにVisionへ渡す。Visionは見える事実、次に試す一つの方向、許可範囲内の変動対象を返し、その助言を次世代生成へ渡す。

どちらの方式でも変奏（§12.13）を有効な推敲要素に含められる（有効要素の上限は5）。変奏を有効にしたときだけ強度（小・中・大、既定は中）の選択を表示し、選んだ強度は実行中の全変奏世代に適用される。seedはサーバーが採番する。

Vision方式は有限の助言ループだが、品質最適化や自動受け入れではない。Visionは点数・順位・合否・称賛・否定を返さず、生成済み世代を棄却しない。途中世代を`lineage_only`、最終世代を通常履歴として全世代を系譜へ保存する。使用方式、Visionモデル、観察、次に試す方向は派生metadataへ記録し、モーダルにも最新所見を表示する。モデルは実行ごとに切り替えられるが、一回の実行中は固定する。最終的な保存・昇格・スター付与・採否は人間だけが行う。

## 奥書（系譜の朗読）の設計

奥書は、系譜の一本の枝（rootから表示作品）に添える、AIの一人称による読みである。判定、要約、推薦ではなく、作品と作品のあいだに何が見えるようになったかを観察語彙で記し、推敲という時間を鑑賞可能にする。事実の層はlineage node/edgeが担い、奥書は「私にはこう見える」「私はこう読んだ」という限定された解釈だけを加える。

- 世代ごとの記述は必ずrootから逐次生成し、世代iの入力には世代0〜iだけを含める。後の世代を先の世代の意味や成功として語る目的論を、注意書きだけでなく入力構造で遮断する。選ばれなかった枝も回り道や失敗として扱わない。
- 入力はderivation kindとmetadata、各作品の詞書、前後作品をサーバーでPNG化したサムネイル対、既存の特徴鏡が読む構図族・primitive・色・密度・角度・配置pathの差分である。新しい品質尺度は作らない。画像は観察に必要な範囲へ縮小し、単体512px、比較対768×384pxを上限とする。
- 同一モデル・言語・prefix・画像hashで成功した世代所見は短時間だけサーバー内にキャッシュできる。途中タイムアウト後の同一再実行では完了済み所見を再利用するが、異なるモデル、作品、prefixへ流用しない。全世代を一要求へまとめて後世代を先の所見へ露出させる最適化は禁止する。
- 結びの不変量はLLMに発見させず、全世代の特徴鏡と保持Score要素の共通集合から決定的に計算する。LLMはその機械抽出結果だけを一人称で言語化し、因果や作者の意図を加えない。
- 「良い」「美しい」「成功」「洗練」等の日英評価語と数値評価はwarning-onlyの語彙検査対象とする。検出しても自動修正、再生成、保存拒否は行わない。
- 署名は本文生成とは別にサーバーが読み手モデルと日付から機械付与する。言語はUIまたはCLIの明示設定に従う。
- 奥書は対象lineage node、読んだ時点のnode ID列、モデル、日時、言語、本文、warning、事実シートを本人スコープの不変レコードとして追記する。更新APIと編集UIは持たず、削除だけを許す。同じ枝を別モデルや別日に読めば古い順に連なる。Idempotency-Keyは同じ読みの二重保存を防ぐ。
- 奥書は dh1、現行 rh3、legacy rh2、生成、変奏、推敲候補、受け入れ、品質関数、枝推薦へ接続しない。系譜タブの「奥書を読む」または`inku-cli colophon`からだけ明示実行し、`--dry-run`は保存せず標準出力する。

---

## 変更履歴

時系列の実装・設計記録は [CHANGELOG.ja.md](CHANGELOG.ja.md) へ分離した。現在の入口は [PROJECT_CONTEXT.ja.md](PROJECT_CONTEXT.ja.md) を参照する。
