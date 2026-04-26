# inku — DDL (Drawing Description Language) — SPEC

**Version: v1.4**

---

## このドキュメントの位置づけ

**inku** は、DDL（Drawing Description Language）の参照実装プロジェクトである。DDLは言語仕様、inkuはその実装を指す。

本書は**設計哲学と言語設計の方針**を記録する。実装の前提となる思想を明文化することが目的。実装状態の詳細は別途 SPEC_v1.md 等で管理する。

### プロジェクト名「inku」について

- **ink** の日本語読み「インク」から
- 記述の物質そのものを名前とする——DDLが「記述は作品」というコンセプトであることと構造的に一致する
- 墨（sumi）との連想：書道・墨絵の世界観、色パレットの「墨の濃淡」と呼応
- `-lang` サフィックスで言語プロジェクトとして位置づける（rust-lang, go-lang 等と並ぶ）

### エコシステム命名規約

派生プロジェクトは `inku-` プレフィックスで統一する：

- `inku-core` — コアライブラリ
- `inku-saijiki` — 語彙辞書
- `inku-nature` — Nature plugin
- `inku-web` — Web UI 実装
- `inku-android` — Android 実装
- `inku-cli` — コマンドラインツール

---

## 1. コアコンセプト

### 1.1 「視覚的な短歌を書く言語」

DDLは絵を記述する言語ではなく、**視覚的な短歌を書く言語**として位置づける。

三つの伝統の交点に立つ：

| 伝統 | DDLへの寄与 |
|---|---|
| Sol LeWitt の指示書 | 記述そのものが作品であるという思想 |
| 盆栽 | 制約は制限ではなく凝縮である |
| 短歌 | 主張せず提示する。型が自我を削ぐ |

### 1.2 設計の根本姿勢

- **主張しない、提示する** — 作者の感情や解釈を作品に侵入させない
- **短い記述こそが本質** — 長い記述は主張に傾く。短さが提示を可能にする
- **型が自我を削ぐ** — 定型・制約があるからこそ、本質が浮かび上がる

### 1.3 起源

- 2026年4月2日、東京都現代美術館「ソル・ルウィット オープン・ストラクチャー」展
- 作者が文章で体験してきた「精神のフォグが削ぎ落とされ、元からそこにあったものが見えてくる」体験を、絵画という別媒体で再現すること

---

## 2. 設計原則（確定事項）

1. **記述は人間が読める** — 自然言語と記述言語の中間に位置する
2. **揺らぎは仕様である** — LLMのアーキテクチャ的揺らぎをバグとして排除しない
3. **感情語彙を排除する** — 「美しく」ではなく、数値と物理素材の語彙で記述
4. **キャンバスを持たない** — 座標系は 0.0〜1.0 の比率。壁にも画面にも適用可能
5. **出力は静止画** — 動かさない。見る人が動く
6. **入力は制約付きDSL寄り** — 完全な自由形式はユーザーを圧倒する。適度な構造が創造を助ける

---

## 3. コアとエクステンションの分離

### 3.1 コアに入れるもの

| カテゴリ | 語彙 |
|---|---|
| **Color** | 白、黒、青、赤、緑、灰 |
| **Canvas** | 正方形（Option: A4, B4, Letter） |
| **Action** | 置く、描く、並べる、埋める、塗りつぶす |
| **Pen** | ペン、筆太、筆細、ロトリング、クレヨン |
| **Line** | 直線、波線、ひっかき、ドット |
| **Object** | 線、円、だ円、三角、四角 |
| **Location** | 上下左右、斜、回転、ランダム |
| **つらなり (Continuity)** | 実線、破線、点線、一点鎖線 |
| **ゆらぎ (Movement)** | 細かく、大きく、ゆっくり、速く、揺れる、波打つ、震える、滲む、ばらつく |

**コアの性質**：
- 物理素材の語彙のみ（感情語ゼロ）
- 「描く動作」ではなく「配置する動作」を中心とする（盆栽で枝を「置く」感覚）
- Actionの語彙設計が特に重要：置く・並べる・埋める——これは提示の動詞
- **ゆらぎカテゴリは運動語彙のみ**：「細かく揺れる」「ゆっくり波打つ」は許容、「美しく揺れる」「激しく揺れる」は排除（詳細は Section 13）

### 3.2 エクステンションとして分離するもの

- **Nature plugin**（例: 雨、葉、水、風）
- **bamboo拡張**などの具象語彙

**原則**: コアを汚さない。具象的・文化的な語彙はすべて拡張機能として追加可能な形で提供する。

---

## 4. プラグイン設計原則

### 4.1 なぜプラグインを最初から設計するか

DDLではプラグイン機構を**後付けではなく最初から設計する**方針を採る。理由：

**コアの純度を守るため**
Nature plugin（雨・葉・水・風）のような具象語彙をコアに入れないと既に決めている。この判断は、プラグイン機構が最初から存在することが前提になる。プラグインが後付けだと、「とりあえずコアに入れておいて、後で分離する」という妥協が生まれる。

**拡張の作法を先に決めるため**
他言語版をコミュニティに委ねる方針も、プラグインの作法が定義されていて初めて成立する。「自由に拡張してください」だけでは、各実装がバラバラになる。

**コアとの境界を明確にするため**
何がコアで、何が拡張か。この線引きが後回しになると、線引き自体が曖昧になる。

### 4.2 Emacs Lisp の教訓と Go の姿勢

プラグインの自由度は諸刃の剣である。

**Emacs の拡張性の代償**
- コアとパッケージの境界が曖昧
- パッケージ同士が衝突する
- コア自体が拡張に引きずられて肥大化する
- 学習曲線が個人ごとにバラバラで、共通基盤としての性質が弱い

**Go の対極的姿勢**
- 言語機能を意図的に少なく保つ
- マクロもメタプログラミングもない
- 「一つのやり方」を強制することで、他人のコードが読める

DDLが短歌を目指すなら、**Go 寄りの姿勢**が合う。短歌に「私だけの文法」はない。共通の型があるから、個人の表現が成立する。

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
どんなプラグインも、コア語彙で書いた記述に「展開」できる。プラグインは省略記法であって、新機能ではない。

### 4.4 プラグインの展開モデル

プラグインは「コア語彙の組み合わせに名前を付けたもの」として定義される。

例:
```
Nature.雨  →  短い線を上から下に多数散らす
           = 「細い、縦の短い線を、上半分の領域に、散らす」
             （コア語彙: 細線、縦、短、上半分、散らす）
```

プラグインは展開可能である。つまり、プラグインを使った記述は、コアだけで書いた記述に機械的に変換できる。これにより：

- レンダラーはコアだけを知っていればいい
- プラグインのバグがレンダリングを壊さない
- 他言語への移植時、コアだけ移植すれば動く
- プラグイン同士が衝突しない

### 4.5 盆栽との対応

この設計は盆栽の比喩と一致する。盆栽は新しい植物を発明しない。既存の植物の組み合わせと配置で世界を作る。プラグインも同じ性質を持つべきである。

新機能を足すのではなく、既存の組み合わせに名前を与える。それがプラグインの役割。

### 4.6 公式 Reference Plugins

「公式」と「非公式」のプラグインを分ける問題への DDL の姿勢：

**方針: 公式 reference plugins を数個だけ用意する**

Nature、Bamboo など、数個の公式プラグインを「プラグインの書き方の手本」として提供する。それ以外はユーザーが自由に作れるが、公式レジストリは持たない。

**利点:**
- プラグインの作法が手本で示される
- 公式レビューの負担を避けられる
- ユーザーは参考実装を読んで自分のプラグインを書ける
- コアチームはコアに集中できる

### 4.7 名前空間の規約

プラグインは必ず名前空間を持つ。例:

```
Nature.雨
Nature.風
Bamboo.竹
Seasons.桜
```

これにより：
- プラグイン使用箇所が記述から明らかになる
- 同名語彙の衝突を防ぐ（Nature.雨 と Weather.雨 は別物として扱える）
- 歳時記（Saijiki）でもプラグイン別にカテゴリを分けて表示できる

### 4.8 自由度に関する最終判断の留保

上記の原則は「プラグインは語彙のマクロに限定する」を強く推している。しかし、**最終的な自由度の範囲は、実装とテストを経て決める**。

検証すべき問い：
- コアのプリミティブだけでどこまで意味のある表現ができるか
- プラグインを語彙マクロに限定しても、Nature や Bamboo のような具象世界を十分表現できるか
- 拡張のニーズが「マクロでは足りない」ことを示した場合、原則をどこまで緩めるか

**原則を緩める場合も、Emacs 化を避けるための明確な線引きを維持する**。自由度を増やすときは、その自由度が失わせるものを明示した上で判断する。

---

## 5. 三層パイプライン

```
記述（DDL テキスト）  →  楽譜（JSON Score）  →  演奏（SVG）
人間が書く               LLMが解釈する           Renderer が描く
```

### 5.1 各層の役割

- **DDLテキスト**: 人間の層。母語で書かれる。短歌的な短さを推奨
- **JSON Score**: 中間の楽譜。言語非依存・機械可読
- **SVG**: 演奏の結果。一回性。記述は残り、出力は都度生まれ都度消える

### 5.2 LeWittとの違い

LeWittの指示書は記述者と実行者が分離していた（LeWitt ↔ 職人）。
DDLでは一人の人間の中で起きる（自分 ↔ LLM）。
内側から出たものが外側から返ってくる——その往復の中に、霧が払われる瞬間がある。

---

## 6. Base Language 問題

### 6.1 問題提起

日本語と英語（他の言語）でのDDLの扱いをどうするか。

### 6.2 方針（暫定）

**レイヤーごとに言語を分ける**：

| 層 | 言語 |
|---|---|
| DDLテキスト（人間が書く層） | 母語（日本語・英語・他） |
| JSON Score（機械が読む層） | 英語キーで統一 |
| LLM（変換層） | 多言語理解 |

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

### 6.5 二言語並行開発の意義

日英の二言語で並行開発することは、設計の質を上げる装置として機能する：

同じ概念を日英で書いたとき、どちらかで自然でない表現が出たら、それはコアの言葉選びが偏っているサインである。両方で自然に書けるものだけがコアに残る。

**判断基準の例:**
- 「置く」⇔「place」——両方自然、コアに入れる
- 「佇む」⇔「stand still, but with presence」——英語だと一語にならない、コアではなく日本語版拡張として扱う

一言語だけで開発すると、気づかないうちに言語固有のバイアスがコアに入り込む。二言語あることで、言語非依存のコアと言語固有の拡張が自然に区別される。

---

## 7. UI設計方針

### 7.1 反復を前提とするUI

DDLは一回で完成させない。**記述→出力→また記述**の往復を設計の前提とする。

### 7.2 画面構成（概念）

**Phase 1: Initial (inst Generation)**
```
[描画エリア]
    ↓
[inst入力エリア]  ← 最初のアイデアを書く
    ↓
[DRAW ボタン]
```

**Phase 2: Next (inst Generation)**
```
[Prev. inst の出力]  [Next inst の出力]
      ↓                    ↓
[前の記述を表示]      [新しい記述を書く]
                          ↓
                     [DRAW ボタン]
```

新旧の差分は色で可視化する（変更・追加が視覚的にわかる）。これは**推敲の痕跡**として設計する。プログラミングのdiffではなく、文章を削ぎ落とすプロセスの可視化。

### 7.3 LLM Model Inspection

複数のLLMモデル（例: Gemma 4 と Opus 4.7）を横並びで比較できるビュー。同じ記述を異なるモデルに渡し、出力の違いを見る。「モデル選択そのものが創造的変数」という原則を可視化する。

### 7.4 inst. box のデザイン

**基本方針: IntelliSenseの逆を行く**

IntelliSenseは「書く前に候補を出す」ことで間違いを減らすツール。DDLでは逆に、**書き手の迷いの中に創作の瞬間がある**と考える。「置く」と書こうとして一瞬手が止まるその静止の中に、「並べる、の方が近い」という気づきが生まれる。補完候補が次々出ると、思考が候補に引っ張られて内側を見る隙がなくなる。

**採用する設計**

1. **白紙の記述エリア**: 書くときは何も出さない。短歌の原稿用紙に近い純度
2. **歳時記（Saijiki）として語彙辞書を別配置**: 記述者が能動的に参照しに行く
3. **書いた後に解釈フィードバック**: 書いた語に解釈の度合いが色で付く（詳細は7.6）

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
- 翻訳不可能な言葉を残すこと自体が、DDLの「言語への敬意」と一致する
- 英語話者にとっては "Saijiki" というボタンを開く行為自体が、異文化の視点で語彙を見る体験になる

**カテゴリ構造（日本語版）**

ひらがなを採用する。漢字は硬い。ひらがなは記述の敷居を下げる。

| カテゴリ | 語彙例 |
|---|---|
| かたち | 円、三角、四角、線、弧 |
| てざわり | ペン、筆、クレヨン、チョーク、縄 |
| うごき | 置く、並べる、埋める、散らす |
| ばしょ | 上、下、中心、端、隅 |

**カテゴリ構造（英語版）**

| Category | Vocabulary |
|---|---|
| forms | circle, triangle, square, line, arc |
| touches | pen, brush, crayon, chalk, rope |
| motions | place, align, fill, scatter |
| places | top, bottom, center, edge, corner |

**配置方針**

- 記述エリアには表示しない
- UI上のボタン（[Saijiki]）から能動的に開く
- 書くときは閉じている、迷ったときだけ開く
- 歳時記が「見る」ものではなく「見に行く」ものになるように設計する

### 7.6 解釈フィードバック（Interpretation Feedback）

DRAW を押した後、記述した文字列に**解釈の度合いを示す色**が付く。

**設計思想**

- IntelliSenseが「書く前」に候補を出すのに対し、これは「書いた後」にフィードバックする
- 短歌で書いた後に師匠が朱を入れる感覚に近い。ただし**訂正ではなく、どう読まれたかの提示**
- メッセージは「LLMはこう読みました」であって「正しい／間違っている」ではない

**色の表現（案）**

墨の濃淡で表現する。主張の強い色は避ける。書道の感覚。

| 状態 | 表現 |
|---|---|
| 確実に解釈された語 | 濃い墨色 |
| 曖昧に解釈された語 | 薄い墨色 |
| 解釈されなかった語 | ほぼ透明（うっすら） |

拡張語彙（Nature plugin等）を使った場合は、墨色とは別の柔らかい色（例: 薄い朱）で表現する候補もある。

**設計上の注意点**

- 色が「評価」にならないようにする。記述者が萎縮すると創作が止まる
- 「解釈できなかった」ではなく「LLMが確信を持てなかった」と表現する。原因を書き手ではなくLLM側の限界として提示する
- 色の意味を UI 上で明示的に説明する

**発展形: 解釈のズレの表示**

書いた語の横に、LLMがどう解釈したかを小さく併記する：

```
佇ませる [place with stillness]
```

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

---

## 9. 「最初の一筆」の設計

### 9.1 要件

- インスピレーションを最初の一筆にできること
- その一筆が十分に満足の行くフィードバックを生むこと
- 偶然性が高すぎず、補完が行きすぎず、しかし単なるトレースでもないこと

### 9.2 針のバランス

```
偶然性が高すぎる    →  自分の意図が見えない  →  やる気をなくす
補完しすぎる        →  自分が作った感がない  →  意義を見出せない
単なるトレース      →  DDLである必要がない   →  意義を見出せない
```

針が正しい位置にあるとき：**自分が書いた言葉が、予想より少しだけ賢く実現される**。その「少しだけ」が続きを書きたくさせる。

### 9.3 最初の一行

「何を描くか」ではなく「何が気になっているか」を書くもの。そこからLLMが引き出す。

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

---

## 11. テスト戦略

### 11.1 評価軸の分離

| 機械判定 | 人間（またはLLM）判定 |
|---|---|
| JSONがvalidか | 意図を反映しているか |
| 全primitiveが実装済みか | 芸術的に面白いか |
| トークン長が範囲内か | 揺らぎが適切か |
| レンダリングが完了するか | — |

### 11.2 テストケースの自動生成

Opus 4.7 にテスト指示を生成させる。
軸：
- **難易度**: 単純 → line複数 → 複数primitive → 抽象概念 → 詩的表現
- **種類**: 幾何学的 → 具象的 → 感情的 → 詩的

生成されたテストケース自体がDDLの語彙の探索にもなる。

### 11.3 自動テストパイプライン

```
テスト指示セット（自動生成）
    ↓
composer（DDL → JSON）
    ↓ 機械判定: valid / token / primitive
renderer（JSON → SVG）
    ↓ 機械判定: 生成成功 / 描画要素数
結果ログ（指示 / JSON / SVG / エラー種別 / 生成時間）
```

ログビューアはユーザー向け描画ツールと同じUI基盤で兼用可能。

### 11.4 着手順

1. 小さなテストセットを手動で作る（10〜20件、難易度・種類をバラけさせる）
2. 自動実行スクリプトを作る（結果をJSONログに保存）
3. Opus 4.7 でテストケースを拡張生成する（100件規模に）
4. ログビューアを作る（SVGを並べて目視確認できる）

---

## 12. Opus 4.7 の役割と二段階変換アーキテクチャ

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

一段階変換では、LLMが同時に二つの異なる仕事をすることになる：

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
正規化DDL（例）:

  中心に 細い線を ひとつ 置く
  揺らぎ: 小
```

**却下した選択肢:**

| 形式 | 却下理由 |
|---|---|
| 完全自然文（「中心付近に、細い線を、わずかな揺らぎで置く」） | 第二段階で再度「解釈」の余地が残る |
| 構造化リスト（YAMLライク） | コードっぽく見える。記述の楽しさを削ぐ |
| 関数呼び出し風（`置く(対象=線, 位置=中心)`） | コードに近すぎる |

**採用形式の特徴:**
- 自然文のリズム（短歌的な読み心地）
- 語彙はコアに限定（「置く」「細い」「中心」など）
- 修飾情報（揺らぎなど）を明示的に分離
- 日本語版と英語版でフォーマットの構造を共通化
- **記述者の目に触れる前提で設計する**（解釈フィードバックUIで表示される）

### 12.5 モデル分割

段階ごとに異なるモデルを使う：

| 段階 | モデル | 理由 |
|---|---|---|
| 第一段階（解釈） | **Claude Opus 4.7** | 豊かな解釈・盆栽や短歌のニュアンス理解が必要 |
| 第二段階（構造化） | **Claude Haiku 4.5 or ローカルLLM** | 機械的変換なので軽量モデルで十分 |

**利点:**
- コストの高い Opus は一回だけ使う
- 第二段階は入力が制限されているので、軽量モデルでも安定する
- 「モデル選択そのものが創造的変数」という原則を維持しつつ、実用的なコスト構造

### 12.6 第一段階（解釈）の設計

**Opus 4.7 が担うこと:**
1. 自由な記述の意味を読み取る（「佇ませる」→「静かに中心に置く」）
2. 盆栽の感性、短歌のリズムを理解して正規化する
3. 曖昧さに対して「最も美しい」解釈を選ぶ
4. 揺らぎの度合いを記述の雰囲気から決める（「ひっそりと」→揺らぎ小）

これはOpusの**芸術的な解釈能力**を最大限活かす設計である。軽量モデルには難しい、ニュアンスの読み取りをOpusに任せる。

**プロンプト設計の方針:**
- コア語彙のリストを明示
- Saijiki（歳時記）のカテゴリ構造を共有
- 「美しく解釈する」ことを明示的に求める
- Few-shot examples で「曖昧な記述 → 正規化DDL」の例を示す

### 12.7 第二段階（構造化）の設計

**軽量モデルが担うこと:**
- 正規化DDL を JSON Score に機械的に変換する
- スキーマ遵守を最優先する
- 創造的判断は不要（第一段階で済んでいる）

**プロンプト設計の方針:**

```
あなたは、正規化DDLをJSON Scoreに変換する関数です。
入力は以下のコア語彙のみを含みます:

かたち: 円、三角、四角、線、弧
てざわり: ペン、筆、クレヨン、チョーク、縄
うごき: 置く、並べる、埋める、散らす
ばしょ: 上、下、中心、端、隅
太さ: 細、中、太
揺らぎ: 小、中、大

各語彙はJSON Scoreの以下のフィールドに対応します:
...（マッピング表）

入力をパースし、スキーマに従ってJSONを出力してください。
```

入力が制限されているので、このプロンプトはほぼ決定的な変換関数として機能する。

### 12.8 エラー回復戦略

二段階化により、エラー回復が段階ごとに設計できる：

**第一段階でのエラー:**
- Opusが正規化できなかった語がある → 「この語は理解できませんでした」とUIで表示
- 解釈フィードバック（Section 7.6）の「薄い色」や「透明」として視覚化
- **記述者にフィードバックするだけで、処理を止めない**

**第二段階でのエラー:**
1. Sanitizer（既存のKotlin/Python実装）でJSON修復を試みる
2. 修復不可ならエラーを含めたプロンプトでリトライ（最大3回）
3. それでもダメな場合、Opus 4.7 でフォールバック（コストはかかるがほぼ必ず成功する）

### 12.9 実装順序（逆順実装）

**パイプラインの後段から実装する**方針を採る。

**Step 1: 第二段階を先に作る**
- 正規化DDL（入力） → JSON Score（出力）の変換を実装
- 入力は最初は手書きで作る（10〜20個の正規化DDL例）
- 第二段階が安定すれば、パイプラインの後半が固まる

**Step 2: 第一段階を作る**
- ユーザー記述 → 正規化DDL
- Opus 4.7 でプロンプト設計
- 第二段階に繋げる

**Step 3: UI・解釈フィードバック・仕上げ**
- Web UIで両段階の出力を表示
- 解釈フィードバック実装
- サンプル記述集を用意

**逆順実装の根拠:**
第二段階が安定していないと、第一段階のデバッグが難しくなる。入力側から作ると、出力側の不安定さに振り回される。下流から固めていくことで、各段階のデバッグが独立できる。

### 12.10 レイテンシ対策

二段階化によるレイテンシ倍増への対策：

**対策A: 段階的UI表示**
第一段階の結果（正規化DDL）を先にUIに表示する。ユーザーは正規化DDLを見ながら、第二段階（描画）の完了を待つ。体感レイテンシが下がる。

**対策B: キャッシュ**
同じ記述からは同じ正規化DDLが生成される前提で、第一段階の結果をキャッシュする。揺らぎは第二段階以降で入れる。

**対策C: 並列化（将来的）**
複数バリエーション生成時、第二段階を並列実行する。

---

## 13. 揺らぎの設計

### 13.1 揺らぎとランダム性の区別

揺らぎ（variation）は単なるランダム性ではない。

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

短歌でも、「美しい花」は主観だが、「風に揺れる花」は観察。DDLもこの区別で判断する。第一段階（Opus 4.7）の解釈能力がこの境界判定を担う。

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
  Nature.風、Nature.さざ波
```

この三層は、盆栽の発想と一致する：
- **素材**（樹種）には自然な性質がある
- **職人の手**が入る（運動語彙）
- **環境要因**（風、季節）が重なる（プラグイン）

### 13.5 weight による揺らぎの質

揺らぎには「量」だけでなく「質」がある。DDLでは、weight（素材）が揺らぎの質を暗黙に決める：

| weight | 揺らぎの質 | 特性 |
|---|---|---|
| hair | almost_none | ほぼ揺らぎなし（正確） |
| pencil | perlin_fine | パーリン寄り（手の連続性） |
| pen | perlin_minimal | わずかなパーリン |
| chalk | perlin_plus_noise | パーリン + ざらつき |
| brush | perlin_strong | 強いパーリン + 太さのバラつき |
| rope | slow_wave | 大きな波、ゆっくりした揺らぎ |

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
| 配置 | ばらつく、散らばる |

**英語版「movements」:**

| Dimension | Vocabulary |
|---|---|
| amplitude | fine, broad |
| frequency | quick, slow |
| quality | wobble, undulate, tremble, blur |
| placement | scatter, disperse |

### 13.7 Nature plugin による現象の揺らぎ

自然現象の揺らぎは Nature plugin として提供する。記述者は揺らぎのパラメータを書くのではなく、**現象を呼び出す**。

**基本形:**

```
ペンで直線を 中心に 置く
Nature.風を 通す
```

または：

```
筆で円を 並べる
Nature.さざ波を かける
```

「風を通す」「さざ波をかける」は動詞として自然現象を記述に織り込める。短歌の読み心地に近い。

**代表的な Nature plugins（参考実装候補）:**

- `Nature.風`: 横方向のゆるやかな波
- `Nature.さざ波`: 細かい波形の重畳
- `Nature.揺れ`: 中心軸周りの微小回転
- `Nature.震え`: 高周波の小さな揺動
- `Nature.無風`: 揺らぎを抑制（素材固有揺らぎも消す）

**マクロ展開の例:**

```
Nature.風 の展開（概念）:
  全ての線と形に対して
  水平方向の緩やかな波
  振幅: 描画対象サイズの 2-5%
  周波数: 画面幅あたり 1-2 周期
  形状: パーリンノイズ
```

展開は第二段階の構造化層で処理される。プラグイン原則に従い、コアのメカニズムは変更しない。

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

### 13.9 JSON Score の variation スキーマ

JSON Score の `variation` フィールドは、次元ごとに分離した構造を持つ。

```json
{
  "variation": {
    "amplitude": "fine",
    "frequency": "high",
    "quality": "perlin",
    "dimensions": ["position_y", "thickness"]
  }
}
```

| フィールド | 値 | 説明 |
|---|---|---|
| `amplitude` | `fine` / `medium` / `broad` | 振幅（運動語彙由来） |
| `frequency` | `slow` / `medium` / `high` | 周波数（運動語彙由来） |
| `quality` | `none` / `white` / `perlin` / `pink` / `wave` | ノイズ種別（weight由来） |
| `dimensions` | `[position_x, position_y, angle, length, thickness, ...]` | どの次元を揺らすか |

**記述者はこの構造を直接書かない**。運動語彙・weight・プラグインの組み合わせから、第二段階の構造化層が生成する。

スキーマレベルでは variation は保持するが、DDLテキスト層のインターフェースからは見えない。プラグインや素材を実装する人だけがこの次元を扱う。

### 13.10 記述例と展開

記述例：

```
細かく揺れるペンシルの破線が3本、画面を横切る
```

**第一段階（Opus 4.7）の出力（正規化DDL）:**

```
ペンシルで 破線を 横に 3本 置く
揺れ: 細かい
```

**第二段階（軽量モデル）の出力（JSON Score、抜粋）:**

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
        "frequency": "high",
        "quality": "perlin",
        "dimensions": ["position_y"]
      }
    }
  ]
}
```

**Renderer:**

JSON Score を受け取り、`variation` 情報から実際の揺らぎ関数（パーリンノイズ、細かい振幅、高い周波数、y軸方向）を選んで SVG を生成する。Replay のたびに異なる乱数値で演奏される。

---

## 14. 開発方針

### 14.1 開発軸

**メイン軸**: Web UI（ブラウザ）+ Python FastAPI + Opus 4.7 API
- 理由: 開発速度、デモのしやすさ、将来性
- テスト・イテレーションは Mac 上で実施

**補完軸**: Android アプリ（Pixel 9）+ Gemma 4 E2B-IT
- E2E 動作確認済み
- 「ローカルLLMでも動く」差別化ポイントとして保持
- 追加開発は最小限

### 14.2 Phase 1（PoC 完成）

- [ ] FastAPI サーバー構築（`/compose` エンドポイント）
- [ ] Opus 4.7 API 接続（既存 `composer.py` を流用・更新）
- [ ] SVG レンダラー確認（既存 `renderer.py` 流用）
- [ ] Web UI 実装（記述エリア + SVG表示 + 反復UI）
- [ ] DDLテキスト・JSON Score・SVG のトリプル表示

### 14.3 Phase 2（品質向上）

- [ ] 複数バリエーション同時生成
- [ ] SVG ダウンロード機能
- [ ] サンプル DDL テキスト集
- [ ] LLM比較ビュー（Gemma vs Opus）

---

## 15. ライセンス

**MIT License** （Copyright 2026 Shinichiro Oikawa）

- 「誰でも使える」コンセプトと一致する
- プロジェクトの広がりを優先する
- 将来的にデュアルライセンスへの移行は可能

---

## 16. 残件と検討事項

v0.8 時点で **E2E パイプライン (自由記述 → 解釈 → Score → SVG) はブラウザで稼働**している。以下は今後の拡張 / 品質向上タスク。

### A. Renderer (実装優先)

| 項目 | 状態 | 備考 |
|---|---|---|
| line 揺らぎ | 実装済 (v0.8) | 80 segments polyline、perlin/wave/pink/white |
| circle 揺らぎ | 未実装 | 円周 polygon 化 → radius or 位置の揺らぎ注入 |
| ellipse 揺らぎ | 未実装 | circle と同様 (rx/ry 方向別揺らぎ可能) |
| triangle 揺らぎ | 未実装 | 3 辺それぞれ polyline に展開 |
| square 揺らぎ | 未実装 | 4 辺それぞれ polyline に展開 |
| arc 揺らぎ | 未実装 | path を N 分割して radius 揺らぎ |
| `thickness` dimension | 未対応 | stroke-width を segment 毎に変化 (1 line = 複数 path 必要) |
| `angle` / `rotation` / `length` dimension | 未対応 | 線の端点位置に作用する軸 |
| 揺らぎの視覚品質 | MVP 水準 | 鉛筆 / 筆の物理的リアリズムは未着手 (SPEC §13.5) |

### B. Stage 2 composer (精度改善)

- qwen-api の fixture 合格率 9/15、残 6 件の改善案:
  - center/position 混同の対比例を EXAMPLE_POOL 形式で追加
  - 複数命令並列用の例を追加
- Anthropic Haiku 4.5 path の fidelity 測定 (ベースライン比較)
- Gemma3-4B 対応: tool parameters 用の flat schema 生成ヘルパ (`_flatten_schema_for_tool()`)
- tolerance `±0.05` の妥当性 (複数 LLM 横断比較で再調整)

### C. Stage 1 interpreter

- EXAMPLE_POOL に arc 例 (弧を使う詩句 → `弧を引く` 等) 追加、弧出力を誘導
- Stage 1 → Stage 2 の E2E 汎化試験 (interpret 結果が composer を通るか)
- SPEC §2 原則5 違反動詞の混入率測定 (v0.7 強化 + v1.0 属性保持強化後の再評価)
- Anthropic Opus 4.7 path の測定 (作者感による解釈品質比較)
- 学習モードの生成サンプル品質評価 (style ローテーションの多様性実測)

### D. Web UI / 体験 (SPEC §7 未消化)

- **Prev/Next 並置の二枚鑑賞** — 現状は単枚差替え、SPEC §7.7 は並置を想定
- **LLM Model Inspection** — Stage 2 を複数モデルで同時実行し結果を横並べ比較するビュー
- 履歴 item 個別削除 (× ボタン) / export・import JSON
- **解釈のズレ併記** (7.6 発展) — 別解釈を並べて提示
- **差分の色分けルール** (7.2/7.7) — 前回との変更・追加・削除を色分け
- **記述エリアのサイズ制限** (短歌的「型」として文字数ガイド)
- 解釈フィードバック色パレットの確定 (v0.6 で `墨の濃淡` 採用、朱色追加要否)
- サンプル記述集 (SPEC §14.3 Phase 2)

### E. テスト / CI / 運用

- GitHub Actions 等の CI 未設定 (全テスト pentala 手動実行)
- LLM fixture テストを夜間バッチ化、model × fixture 行列で記録
- latency / token usage メトリクス収集
- LLM hallucination エラー回復 (SPEC §12.8) 未実装

### F. 仕様 / エコシステム (長期)

- **Nature plugin** — 風 / さざ波 / 葉などの現象起因揺らぎ (SPEC §13.7)
- **エクステンション機構** — プラグイン読込、名前空間 (SPEC §4)
- **Saijiki 辞書の配信形式** — `web/src/lib/saijiki.ts` 内ハードコード中、将来的に `inku-saijiki` パッケージ
- **Base Language** — 英語版 Saijiki + 英語 prompt (SPEC §5)
- **短歌的制約の強化** — 文字数カウント、句跨ぎの扱い
- **リーダーボード / 作品保存** — ユーザーごとの作品コレクション (P2P or 集約サーバー)

### G. 既に解消済 (参考)

- ~~arc primitive の角度フィールド仕様~~ → v0.7 で解消 (現 v0.8 付録参照)
- ~~Renderer 揺らぎの基本実装~~ → v0.8 で line に実装
- ~~Opus 4.7 API の利用方針 (二段階 vs 一段階)~~ → v0.3 二段階確定
- ~~LLM モデル選択の UI~~ → v0.7 で dropdown + localStorage
- ~~qwen3 thinking 可視化~~ → v0.7 で実装
- ~~NVIDIA NIM プロバイダー追加 + モデル per-stage 選択~~ → v0.9 で実装
- ~~本数・個数の arrangement 展開 (JSON サイズ問題)~~ → v0.9 で実装
- ~~プロンプト無限増殖問題~~ → v0.9 で schema-as-spec + EXAMPLE_POOL により構造的に解決
- ~~大量オブジェクト描画 (100本・200個)~~ → v1.0 で count 上限 500 + scatter hash 化
- ~~scatter 固定10点問題~~ → v1.0 で SHA-256 hash ベースに変更、N 個任意対応
- ~~line from/to 省略時のレンダーエラー~~ → v1.0 で layout から推定補完 + fallback
- ~~Stage 1 属性脱落問題 (色・素材・方向の省略)~~ → v1.0 で属性保持セクション + EXAMPLE_POOL 強化
- ~~履歴の localStorage 上限・永続化~~ → v1.0 でサーバーサイド無制限保存 + ページネーション
- ~~render failed: 必須フィールド欠損エラー~~ → v1.1 で coerce.py (PRIMITIVE_SPECS テーブル駆動) により事前補修
- ~~非 Saijiki 語の展開 (固定辞書の限界)~~ → v1.1 で LLM 意味理解 + SYSTEM_PROMPT_PREFIX 展開原則に転換
- ~~背景色の固定 (white のみ)~~ → v1.1 で Score.background フィールド追加
- ~~大量配置時の単色制約~~ → v1.1 で Arrangement.color_cycle 追加
- ~~Stage 2 がユーザーの元の記述を参照できない~~ → v1.1 で original_text パス・スルー実装
- ~~比率・形状の語彙不足 (縦長/横長/月形等)~~ → v1.2 で Saijiki わりあいカテゴリ追加
- ~~演奏中に何をしているか分からない~~ → v1.2 で 2 コール方式 + ステージラベル表示
- ~~1 記述ずつしか処理できない~~ → v1.2 でバッチ記述モード追加
- ~~学習モードの複雑さ~~ → v1.2 で廃止 (実験的機能として trainer.py は残置)

---

## 付録: 既存ファイル構成

```
inku-lang/                         # github.com/oikawas/inku-lang
├── README.md                      # プロジェクト紹介（英語）
├── README.ja.md                   # プロジェクト紹介（日本語）
├── LICENSE                        # MIT License
├── SPEC.md                        # 本書（設計哲学・言語設計）
├── CLAUDE.md                      # Claude Code 用コンテキスト (gitignore)
├── server/                        # Python バックエンド (uv管理)
│   ├── pyproject.toml             # inku-server 0.1.0
│   ├── uv.lock
│   ├── .env.example               # ANTHROPIC_API_KEY 雛形
│   ├── src/inku_server/
│   │   ├── __init__.py
│   │   ├── schema.py              # JSON Score Pydantic モデル
│   │   ├── renderer.py            # Score → SVG (svgwrite)
│   │   ├── composer.py            # 正規化DDL → Score (Haiku 4.5)
│   │   └── coerce.py              # Score 構造補修 (PRIMITIVE_SPECS テーブル駆動)
│   └── tests/
│       ├── conftest.py            # dotenv 読込
│       ├── test_renderer.py       # 10 cases
│       ├── test_composer.py       # 15 fixture + 厳密比較
│       ├── test_interpreter.py    # 5 smoke cases (Saijiki 語彙検査)
│       ├── test_api.py            # FastAPI TestClient 8 cases
│       └── fixtures/stage2/       # 正規化DDL ↔ Score ペア
│           └── {01..15}/{input.txt,expected.json}
└── web/                           # SvelteKit 2 + Svelte 5 + TS (inku-web 0.1.0)
    ├── package.json
    ├── svelte.config.js
    ├── vite.config.ts             # /api → 127.0.0.1:8100 proxy
    ├── src/
    │   ├── app.html
    │   ├── lib/
    │   │   ├── saijiki.ts         # 歳時記辞書 (7 カテゴリ)
    │   │   ├── highlight.ts       # 墨濃淡トークナイザ (Saijiki/感情/地)
    │   │   └── models.ts          # 選択可能な LLM 一覧と既定
    │   └── routes/
    │       ├── +layout.svelte
    │       └── +page.svelte       # モード / モデル選択 / Saijiki / 履歴 / 思考 UI
    └── static/
```

`server/src/inku_server/`:
- `schema.py` — Pydantic Score モデル (Arrangement.count 上限 1000、background/color_cycle/filled フィールド追加)
- `renderer.py` — Score → SVG (svgwrite)、揺らぎ生成、arrangement 展開、scatter hash 散布、閉形状自動塗りつぶし
- `interpreter.py` — Stage 1: 自由記述 → 正規化DDL (EXAMPLE_POOL 38件、k=5 動的選択、非 Saijiki 語展開・わりあいルール)
- `composer.py` — Stage 2: 正規化DDL → Score (backend dispatch、original_text パス・スルー、わりあいマッピング例)
- `coerce.py` — Score 構造補修レイヤー (PRIMITIVE_SPECS テーブル駆動、generic coerce loop)
- `api.py` — FastAPI: `/api/compose`/`/api/interpret`/`/api/history`/`/api/paint`/`/health`
- `trainer.py` — コーパス生成ユーティリティ (学習モード API は v1.2 で廃止)

**開発環境 (ローカル運用手順は `LOCAL_WORK.md` を参照、未コミット)**

**別リポジトリ / 別 PoC**:
- `ddl/` — 初期 Python PoC (Android 補完軸のベース、Web版は server/ に移行)
- `android/` — Android 実装 (SPEC_v1.md 参照、E2E 動作確認済)

---

## 変更履歴

### v1.4 (2026-04-26)
SPEC.mdの内容精査。

### v1.3 (2026-04-26)

**Saijiki スナップショット + トークン表示 + ダウンロード + i18n**

#### Saijiki スナップショット

特定時点のシステムプロンプト状態を名前付きで保存・呼び出す機能を追加。

- **`server/src/inku_server/snapshots.py` 新規作成**
  - `create_snapshot(name, stage1_prefix, stage2_prompt)` → UUID + タイムスタンプ付きで保存
  - ストレージ: `/tmp/inku-saijiki-snapshots.json` (env var `INKU_SNAPSHOTS_FILE`)
  - `list_snapshots()` / `get_snapshot(id)` / `delete_snapshot(id)` の CRUD
- **API エンドポイント追加**
  - `GET /api/saijiki/snapshots` → `list[SnapshotMeta]`
  - `POST /api/saijiki/snapshots` → スナップショット作成
  - `DELETE /api/saijiki/snapshots/{id}` → 削除
- **スナップショット適用**: `InterpretRequest` / `ComposeRequest` / `PaintRequest` に `snapshot_id` フィールド追加。推論時に一致するスナップショットのプロンプトを上書き
- **設計**: Stage 1 はプレフィックス (`SYSTEM_PROMPT_PREFIX`) のみ保存し、EXAMPLE_POOL の動的例選択は引き続きリアルタイム動作。スナップショットはプレフィックスの変更のみをキャプチャ
- **Web UI**: スナップショットパネル (折り畳み式) を歳時記エリアに追加。現在設定表示・名前入力・保存・削除・選択適用

#### トークン数トラッキング

LLM の消費トークンを処理中に表示し履歴にも記録。

- **`interpreter.py`**: `interpret_detail()` が `(ddl, thinking, tokens_in, tokens_out)` の 4-tuple を返すように変更
  - Anthropic: `resp.usage.input_tokens / output_tokens`
  - OpenAI/OVMS: `resp.usage.prompt_tokens / completion_tokens`
  - いずれも `getattr` で安全取得 (未対応モデルは `None`)
- **`composer.py`**: `compose()` が `(Score, tokens_in, tokens_out)` の 3-tuple を返すように変更
- **`api.py`**: `InterpretResponse` / `ComposeResponse` / `PaintResponse` に `tokens_in / tokens_out` フィールド追加
- **Web UI**: 処理中の「構造化中…」ラベルにトークン数をリアルタイム表示。履歴サムネイルに `{in}→{out}tok` 表示

#### ダウンロード機能

完成した作品を SVG および複数解像度の PNG で保存可能に。

- **SVG ダウンロード**: `<desc>` タグに元の記述テキストを埋め込んで出力。`svgWithDesc()` 関数で `<svg ...>` の直後に挿入
- **PNG ダウンロード**: 4 解像度 (1080 / 2160 / 1024 / 2048px) をブラウザ Canvas API で変換
  - SVG に `width` / `height` 属性を注入し `Image` に描画 → Canvas → `toBlob('image/png')` → `<a>` 要素でダウンロード
  - Canvas 背景は白 (`#ffffff`) でプリフィル (透過 PNG にならないよう)
- **UI**: キャンバス下部にダウンロードバーを追加。`↓ SVG` ボタン + `PNG:` ラベル + `1080 / 2160 / 1024 / 2048` ボタン

#### 履歴: モデル名・トークン数表示

- 履歴サムネイルに Stage 2 使用モデルの短縮名 (`shortModel()`) を表示
- `Iteration` 型に `tokens_in / tokens_out` フィールド追加
- `HistoryPostBody` にも `tokens_in / tokens_out` を追加してサーバー側履歴にも記録

#### ハッカソン関連テキスト削除

UI 全体からハッカソン関連の記述を削除。

#### i18n — 日英言語パック

UI の日本語 / 英語切り替えを実装。将来の多言語対応を設計から内包。

- **`web/src/lib/i18n/types.ts`**: `LangPack` インターフェース定義
  - 単純文字列フィールドと関数フィールド (`batchCount(n)`, `stageStructuring(tok)`, `tokenSummary(...)` 等) を混在
- **`web/src/lib/i18n/ja.ts`** / **`en.ts`**: 日本語・英語パックを個別ファイルで管理
- **`web/src/lib/i18n/index.svelte.ts`**: Svelte 5 `$state` ベースの言語ストア
  - `t()` 関数でアクティブパックを返す (テンプレート内 `t().key` で全文字列を参照)
  - `setLang(code)` + `localStorage` 永続化
  - 新言語追加: `types.ts` にパック実装 + `PACKS` に登録するだけ
- **`+page.svelte`**: 全ハードコード文字列を `t().xxx` に置き換え。`$derived.by(() => t().tokenSummary(...))` パターンで複合 derived を実装
- **ヘッダー**: 言語切り替えボタン (`日本語` / `English`) をヘッダー右上に配置

---

### v1.2 (2026-04-25)

**バッチモード + 演奏ステージ可視化 + 学習モード廃止 + わりあい語彙追加**

#### バッチ記述モード

- 入力欄に「記述 / バッチ」タブを追加
- バッチタブ: 改行区切りで複数の記述を入力、左端に行番号を自動表示
- 順次処理: 演奏中は「N / M 番目を演奏中…」と表示、停止ボタンで中断可能
- 各結果を履歴に保存し、最後の結果がキャンバスに残る

#### 演奏中ステージ可視化

- フロントエンドの処理方式を `/api/paint` 1 コール → `/api/interpret` + `/api/compose` の 2 コール方式に変更
- 演奏中に「解釈中…」「構造化中…」をステージラベルとして経過秒と並べてリアルタイム表示
- `ComposeRequest` に `original_text` フィールド追加 (Stage 2 が元の記述を参照して属性補完に活用)

#### 学習モード廃止

- Web UI の学習モードパネルを削除
- `GET /api/train`・`GET /api/train/stats`・`DELETE /api/train` エンドポイントを削除
- 起動時の EXAMPLE_POOL 注入ルーティングも削除 (`trainer.py` は実験的ユーティリティとして残置)

#### Web UI 改善

- 出力タブ順変更: 演奏 → プロンプト → 楽譜 (旧: 演奏→楽譜→プロンプト)
- プロンプト表示領域拡大: ユーザー入力 max-height 160px、システムプロンプト 400px、外枠 680px
- 履歴に `stage1_model` / `stage2_model` を記録 (サムネイルの title で確認可)

#### Saijiki わりあいカテゴリ追加

- 新カテゴリ `わりあい (proportions)`: 縦長・横長・全幅・半幅・半円・上弦・下弦・三日月
- Stage 1 `SYSTEM_PROMPT_PREFIX` に `# わりあい` ルールセクション追加 (縦横比・線長・月形→角度の変換原則)
- Stage 2 `SYSTEM_PROMPT` にわりあい JSON マッピング例 7 件追加
- `EXAMPLE_POOL` に 8 件追加 (縦横比 2・線長 2・弧月 4)
- `saijiki.ts` に `わりあい` カテゴリを追加

---

### v1.1 (2026-04-25)

**coerce レイヤー + 背景色 + 配色サイクル + 塗りつぶし + 非 Saijiki 語展開 + UI 改善**

#### coerce.py — テーブル駆動の構造補修レイヤー (新規)

LLM が必須フィールドを省略した Score を renderer に渡す前に自動補修する `coerce.py` を新規作成。

- **設計原則**: primitive 個別の if/elif を書かない。`FieldSpec` dataclass + `PRIMITIVE_SPECS` テーブルで要件を宣言し、汎用ループで適用。新 primitive 追加 = テーブルにエントリ追記のみ
- **`FieldSpec`**: `name / default / fallbacks (cross-field 代替) / coerce (型正規化関数)` を宣言
- **`PRIMITIVE_SPECS`**: 6 primitive (line/circle/ellipse/arc/square/triangle) の必須フィールド仕様
  - fallback 例: circle の `center` 欠損時は `position` を代用
  - 型正規化: `_as_coord / _as_positive_float / _as_positive_size / _as_float`
- **`POST_COERCE`**: cross-field 制約 (arc の `angle_start == angle_end` → +270° 補正)
- **`api.py`**: `/api/compose` / `/api/paint` 両エンドポイントで `render()` 前に `coerce_score()` を呼び出し

#### 閉じた形状の自動塗りつぶし

- `_CLOSED_SHAPES = frozenset({"circle", "ellipse", "square", "triangle"})`
- `_stroke_attrs()`: `do_fill = ins.primitive in _CLOSED_SHAPES or ins.filled` — 閉形状は色指定で自動塗りつぶし
- `Instruction.filled: bool = False` フィールドを schema.py に追加 (明示的塗りつぶし指定)

#### 背景色 (Score.background)

- `Score.background: Color = "white"` フィールド追加
- `renderer.render()`: `COLOR_MAP.get(score.background, BACKGROUND)` でキャンバス全体を背景色で塗りつぶし
- Stage 2 プロンプトに background ルール追加

#### 配色サイクル (Arrangement.color_cycle)

- `Arrangement.color_cycle: list[Color]` フィールド追加 (デフォルト空 = 全要素同色)
- `_apply_color_cycle(items, cycle)`: arrangement 展開後に `i % len(cycle)` で色を上書き
- 全 layout (horizontal / vertical / radial / scatter) で適用

#### count 上限 1000 へ拡張

- `Arrangement.count` 上限 500 → 1000、`_clamp_count` validator も更新
- composer.py / interpreter.py のプロンプト記述も同様に更新

#### Stage 2: original_text パス・スルー

- `compose(ddl, *, original_text=None)` に引数追加
- `_build_user_message(ddl, original_text)`: 原文と正規化DDL が異なる場合 `[原文]…[正規化DDL]…` 形式でユーザーメッセージを構成
- `/api/paint` で `req.text` を Stage 2 に渡すよう改善 → LLM が元の記述の意図をより正確に反映

#### 非 Saijiki 語の LLM 意味展開

- Stage 1 `SYSTEM_PROMPT_PREFIX` に `# 非 Saijiki 語の展開` セクションを追加
  - 展開の四つの切り口: 形状 / 質感 / 構造 / 動作→配置
  - 例: 月→円、霧→楕円(滲む)、森→縦線を複数、散る→ランダムに散らす
- 固定辞書アプローチ (`expansion.py`) を削除 — LLM の意味理解に委ねる方針に転換
- EXAMPLE_POOL に自然現象・詩的語彙の例 9 件追加 (太陽、星空、水平線+月、山並み、森、雪、炎、都市、花びら)

#### Web UI 改善

- **タブ切り替え**: 演奏 / 楽譜 / プロンプト の 3 タブ (旧: 垂直展開)。新しい結果が来ると自動的に「演奏」タブに戻る
- **ビルド番号**: `vite.config.ts` に `.build-number` ファイルベースのインクリメント機構を追加。ヘッダー左上に `#N` 表示
- **接続先 / モデル ラベル**: 「接続先：」「モデル：」を明記
- **プロンプト表示順**: Stage1ユーザー入力 → Stage1システム → Stage2ユーザー入力 → Stage2システム (文脈順)

---

### v1.0 (2026-04-25)

**大量描画対応 + Renderer 堅牢化 + Stage 1 属性保持強化 + 学習モード + サーバーサイド履歴**

#### 大量オブジェクト描画 (count 上限 500)

「100本の線」「200個の円」を実際に描画できるようアルゴリズムを改良。

- **schema.py**: `Arrangement.count` 上限 50 → 500、`_clamp_count` validator も同様
- **renderer.py**: 固定10点 `_SCATTER_POSITIONS` を廃止。`_scatter_pos(i, seed, margin)` を追加
  - SHA-256 hash ベースの決定的ランダム座標生成 — N 個任意対応
  - 同一 Score → 同一 SVG の決定性を維持 (seed = instruction の hash)
- **interpreter.py**: 「100本・200個 → 30程度に丸める」規則を撤廃、具体的な数はそのまま通す
- **composer.py**: count 上限説明を 50 → 500 に更新

#### Renderer: line from/to 省略時の fallback

LLM が arrangement 付き line を生成するとき `from`/`to` を省略するケースがあり `render failed` エラーが発生していた問題を修正。

- `_ensure_line_coords(ins)` を追加: layout から方向を推定してデフォルト座標を補完
  - `layout="vertical"` → 横線 (`[0.0, 0.5]`→`[1.0, 0.5]`)
  - その他 (`horizontal` / `scatter` / `radial`) → 縦線 (`[0.5, 0.0]`→`[0.5, 1.0]`)
- `_expand_arrangement` 入口で呼び出し (arrangement 展開前に補完)
- `_render_instruction` でも arrangement なし line に同様の fallback を適用 (raise を除去)

#### Stage 1 属性保持強化

記述の解釈時に色・素材・方向・揺らぎが脱落する問題を構造的に修正。

- **`# 属性保持 — 脱落禁止` セクション追加**
  - 「感情語の除去だけが正規化であり、属性の省略は誤り」を明示
  - いろ / てざわり / 太さ / 方向・ばしょ / ゆらぎ / 配置パターン の保持を個別明記
- **数量表現ルール更新**: 「色・素材・方向とともに 1 文に」収める例を追加
- **EXAMPLE_POOL**: 12件 → 21件 (+7件)
  - 追加例: クレヨン+色+数量、鉛筆+細さ、震える複数線、右半分+色+数量、300本のクレヨン、地平線構成、チョーク+滲み
- **k: 3 → 5** — 複合属性入力での例参照数を増加

#### 学習モード (SSE ストリーム)

コーパスを自動拡張するバックグラウンド学習機能を追加。

- **`trainer.py` 新規作成**
  - `VARIATION_STYLES` (5スタイル): 詩的・口語・抽象・自然現象・擬音語をローテーション
  - `generate_sample(style_idx, model)`: 指定スタイルで記述サンプルを LLM 生成
  - `run_one_iteration(style_idx, model)`: 生成 → `interpret_detail` → EXAMPLE_POOL 追加
  - `add_learned_example(input, ddl)`: EXAMPLE_POOL へ追記 + `INKU_LEARNED_FILE` に永続化
  - `load_learned_examples()`: 起動時に永続化済みコーパスを EXAMPLE_POOL へ注入
  - `clear_learned_examples()`: auto エントリのみ削除、static 例は保持
  - backend dispatch: interpreter.py と同じ anthropic / nvidia / ovms ルーティング
- **`api.py` 追加エンドポイント**
  - `GET /api/train?n=&model=` → SSE ストリーム (`progress` / `result` / `error` / `done` イベント)
  - `GET /api/train/stats` → `{"learned_count": N}`
  - `DELETE /api/train` → コーパスクリア
  - `asyncio.to_thread` で sync LLM 呼び出しを非同期化
  - `request.is_disconnected()` でクライアント切断を検出してループを停止
- **Web UI** (学習モードパネル)
  - 折り畳み式パネル、イテレーション数入力、モデル選択
  - リアルタイム進捗バー (shimmer アニメーション)、ログ表示
  - 停止ボタン → EventSource close → サーバーループも次イテレーション前に停止
  - `onMount` で初期 `learned_count` を取得

#### サーバーサイド履歴 (無制限・ページネーション)

localStorage の容量制限を解消し、セッション跨ぎの履歴を実現。

- **`api.py`**: `_history: list[dict]` をメモリ保持 + `_HISTORY_FILE` (既定 `/tmp/inku-history.json`) に永続化
- エンドポイント: `GET /api/history?offset=&limit=` (新着順)、`POST /api/history`、`DELETE /api/history`
- **Web UI**: `HISTORY_PAGE_SIZE=10`、`← 新` / `旧 →` ページナビ、全件数表示

#### UI 改善

- **歳時記ボタン**: ヘッダー → 記述エリア右上 (`<div class="input-header">`) に移動
- **Saijiki トークン色**: `#111` → `#2c3e91` (青) でインライン表示

---

### v0.9 (2026-04-25)

**プロンプト非線形化 + NVIDIA NIM 対応 + arrangement 実装**

#### プロンプト設計の構造改善 (主要変更)

機能追加でプロンプトが際限なく長くなる問題を、MT (機械翻訳) のスペック / コーパス分離原則を援用して構造的に解決。

- **schema.py を仕様の正典 (Source of Truth) に**
  - 全フィールドに日本語 ↔ 値マッピングを含む `description` を付与
  - LLM はツールスキーマの description を直接参照 → SYSTEM_PROMPT にフィールド説明を繰り返す必要がなくなる
  - 新プリミティブ追加 = スキーマ更新のみ。SYSTEM_PROMPT は変えない

- **composer.py: SYSTEM_PROMPT を手順のみに削減**
  - 3,942 chars → 1,072 chars (-73%)
  - 変換例は最重要パターン 4 件に絞る (残りはスキーマ description が補う)

- **interpreter.py: EXAMPLE_POOL + 動的例選択**
  - `EXAMPLE_POOL`: `{keywords, input, output}` タプルのリスト (現在 12 件)
  - `_select_examples(text, k=3)`: 入力とのキーワード一致数でスコアリングし上位 k 件を選択
  - `_build_system_prompt(text)`: PREFIX + 選択された k 件を推論ごとに構築
  - 例を何件追加してもプロンプト長は固定 (PREFIX + 3 件)
  - SYSTEM_PROMPT モジュール変数はプレフィックスのみを公開 (`/api/prompts` 互換)

- **レイテンシ効果**: 322.7s → 21.5s (同一出力、NVIDIA Gemma 4 31B、15x 高速化)

#### NVIDIA NIM プロバイダー追加

- `google/gemma-4-31b-it` を第一・第二段階の既定モデルに設定
- モデル ID による自動ルーティング:
  - `anthropic:<model>` プレフィックス → Anthropic API
  - `/` を含む ID → NVIDIA NIM (`https://integrate.api.nvidia.com/v1`)
  - その他 → OVMS (ローカル OpenAI 互換)
- UI: プロバイダー選択 (NVIDIA NIM / Anthropic / ローカル) + モデル選択の 2 段 dropdown、localStorage 永続化
- `web/src/lib/models.ts` に `PROVIDER_GROUPS` 構造を追加
- NVIDIA_API_KEY は `no-git-sync/.env` + systemd `EnvironmentFile=` で管理

#### arrangement フィールド (本数・個数の JSON サイズ問題)

N 個の instruction を展開すると JSON が N 倍になる問題を解決。Renderer 側で展開することで JSON は常に O(1)。

- **schema.py**: `Arrangement` モデル追加 (`count` / `layout` / `margin` / `center` / `radius`)
- **renderer.py**: `_anchor()` / `_shift()` / `_expand_arrangement()` — Renderer 側で N 個に展開
  - layout: `horizontal` / `vertical` / `radial` / `scatter` (決定的ランダム散布)
  - `count=1` は展開せず単体返却。`ge=2` → `ge=1` に変更 (バリデーションエラー防止)
- **interpreter.py EXAMPLE_POOL**: 数量表現を 1 文でまとめる例、ランダム配置例を収録
- **composer.py**: arrangement 使用を SYSTEM_PROMPT で強制、複数 instruction 生成を禁止

#### UI 改善

- 正規化DDL タブ削除 (常に自由記述モード = `/api/paint`)
- 履歴サムネイルに経過秒数を表示 (`Iteration` に `elapsed_ms` 追加)
- `GET /api/prompts` エンドポイント追加 → 出力欄「プロンプト (デバッグ)」パネルで Stage 1 / 2 のシステムプロンプトと実際の入力を表示
- キャンバス背景色を白に変更 (`#f7f5ef` → `#ffffff`)
- 推論中ライブタイマー + 完了後「解釈 Xs + 構造化 Ys = Zs」内訳表示

---

### v0.8 (2026-04-24)

**Renderer 揺らぎ実装 + arc primitive**

- **line の variation を Renderer で生成** (SPEC §13.8 の核心)
  - 80 セグメントの polyline に変換、SHA-256(model_dump_json) でシード
  - quality 4 種: `wave` (sin), `perlin` (smoothstep 1D value noise), `pink` (2 オクターブ合成), `white` (per-segment hash)
  - amplitude: fine=4px / medium=12px / broad=30px (1000px canvas 上)
  - frequency: slow=2 / medium=6 / high=14 cycles/線長
  - dimensions 適用: `position_x` / `position_y` 単独は該軸揺らぎ、両方指定は線に垂直方向揺らぎ
  - 決定的: 同一 Score → byte 一致 SVG (test 保証)
- **arc primitive 本実装**
  - Schema: `angle_start` / `angle_end` (度、0°=東、CCW 正)
  - Renderer: `<path d="M ... A r r 0 large sweep x y">` で弧描画
  - large-arc-flag: `(end-start) % 360 > 180`、sweep-flag: `end > start` で 0 (CCW)
  - Composer prompt に 弧 行追加、1/4円 / 半円 の角度例
- **新規 test 7件** (arc quarter / half / missing-angles、variation perlin / wave / deterministic / quality=none)

### v0.7 (2026-04-24)

**LLM 多モデル対応 + Stage 1 静止画強化 + thinking 可視化**

- **LLM モデル: UI から切替可能に**
  - `POST /api/compose`: `model` フィールド
  - `POST /api/interpret`: `model` フィールド
  - `POST /api/paint`: `stage1_model` / `stage2_model` フィールド
  - `compose()` / `interpret_detail()` に `model` キーワード引数追加、未指定時は env 既定
  - UI (モード切替下に `解釈` / `構造化` dropdown、localStorage 永続化): Qwen2.5-7B / Qwen3-8B / Gemma3-4B / Gemma3-12B

- **既定モデル**
  - Stage 1: `qwen3-api` (Qwen3-8B)
  - Stage 2: `qwen-api` (Qwen2.5-7B)
  - Gemma3-12B は 15 fixture に 6 時間要、実用外 (選択肢には残す)
  - Gemma3-4B は Score full schema + tool_choice 組合せで破綻 (bracket 出力異常、空白クォート連鎖)、prompt + schema 簡略化で動作するが品質は未検証

- **Stage 1 system prompt: 静止画原則 強化 (SPEC §2 原則5)**
  - 禁止動詞: 動く / 動かす / 広がる / 広げる / 流れる / 伸びる / 昇る / 落ちる / 散る / 沈む / 塗る
  - 使える動作動詞: 置く / 並べる / 引く / 描く / 散らす / 埋める
  - 動的→静的 言い換え 5 例 (月が昇る→右上に円、花が散る→細かい点を散らす 等)

- **Qwen3 thinking 可視化**
  - `interpret_detail()` が `(ddl, thinking)` tuple を返す
  - `include_thinking=True` で `/no_think` を外し、`<think>…</think>` 内容を分離保持
  - `POST /api/interpret`, `/api/paint` に `include_thinking` request フィールド、`thinking` response フィールド
  - UI: Stage 1 が qwen3 系のとき「思考を表示」checkbox、結果パネルに faded amber 色の `<details>` で内部思考表示 (作者の思考プロセス可視化)

### v0.6 (2026-04-23)

**Phase 1 完了 — E2E パイプライン稼働 + UI 反復支援**

- **LLM バックエンド 二系統併存**
  - Stage 2 (composer): `qwen-api` (Qwen2.5-7B) 既定、Anthropic Haiku 4.5 併用可能
  - Stage 1 (interpreter): `qwen3-api` (Qwen3-8B) 既定、Anthropic Opus 4.7 併用可能
  - 切替: 環境変数 `INKU_LLM_BACKEND=openai|anthropic`
  - OVMS (`http://127.0.0.1:18000/v3`) は OpenAI 互換、API key=`none`
  - qwen3-api は `/no_think` prefix で thinking トレースを抑制して使用
  - tool_use は Anthropic ネイティブ、OpenAI 側は `<tool_call>` タグが content に埋め込まれるので正規表現で抽出

- **Stage 1 interpreter 実装**
  - `server/src/inku_server/interpreter.py`
  - 入力: 自由な自然言語、出力: Saijiki 語彙のみを使う短い日本語 (正規化DDL)
  - system prompt に 4 few-shot (感情語→物理語 置換、画面座標比率)
  - 5 ケース smoke test 全通過 (4 は prompt 内例と重複、memorize 傾向あり)

- **API エンドポイント 拡張**
  - `POST /api/interpret`: 自由記述 → 正規化DDL
  - `POST /api/paint`: 自由記述 → 正規化DDL → Score → SVG (フルパイプライン)
  - 既存 `POST /api/compose`, `GET /health` は維持
  - FastAPI 既定 port を `8000 → 8100` へ変更 (pentala 上で 8000 が他サービスと衝突)
  - 起動時 env: `INKU_SERVER_HOST`, `INKU_SERVER_PORT` で上書き可

- **Stage 2 fidelity 記録 (qwen-api strict モード)**
  - 15 fixture 中 9 通過、残り 6 件の典型的な失敗:
    - center (円/楕円) と position (三角/四角) の混同
    - 「中央」指示時の bbox 左上補正未実施
    - 複数命令並列時の field 一括誤適用
  - tool_use API 経由で JSON 構造エラー (`]` vs `}` 誤閉じ等) は解消
  - Haiku 4.5 移行で改善見込みだが、ローカル LLM で回る事実を優先

- **Web UI: モード切替 + Saijiki 参照 + 反復履歴**
  - タブ: 自由記述 / 正規化DDL (それぞれ /api/paint と /api/compose に繋ぐ)
  - 自由記述モード: 解釈結果 (正規化DDL) を左カラム下部に常時表示
  - 歳時記ドロワー: 右スライドイン、7 カテゴリ (かたち/てざわり/つらなり/いろ/ゆらぎ/ばしょ/うごき)、chip クリックで textarea の caret 位置に挿入
  - Saijiki 辞書は `web/src/lib/saijiki.ts` に分離
  - 反復履歴: in-memory、最大 20 件、`◀ N/M ▶` 移動ボタンで input/output/DDL を過去状態に復元
  - サムネイル列: 履歴 2 件以上で下段に 96px 方形ミニチュア SVG を横並べ、クリックで jump

- **運用 / 非公開メモ**
  - `LOCAL_WORK.md` に同期フロー・起動手順・トラブルシュートを集約 (gitignore 済)
  - Mac は SSH tunnel or `http://pentala:5173` でブラウザアクセス、コード編集のみ
  - dev server は pentala 上で nohup 常駐 (`/tmp/inku-server.log`, `/tmp/inku-web.log`)

### v0.5 (2026-04-23)

**Phase 1 続き — FastAPI + Web クライアント 立ち上げ**

- **FastAPI エンドポイント**
  - `POST /api/compose`: `{ddl}` → `{score, svg}` (Stage 2 composer → Renderer を縦結合)
  - `GET /health`: liveness (`{ok: true}`)
  - CORS: `http://localhost:*` / `127.0.0.1:*` 許可 (regex ベース)
  - エラーハンドリング: composer 失敗 502, render 失敗 500, 入力不正 422
  - エントリポイント: `uv run inku-server` で `uvicorn` が `127.0.0.1:8000` reload 起動
  - テスト: `TestClient` + `monkeypatch` で composer バイパス、API キー不要で 5 cases pass

- **SvelteKit Web クライアント (`web/`)**
  - SvelteKit 2.57 + Svelte 5.55 (runes モード) + Vite 8 + TypeScript
  - 単一ルート `/`: 記述 textarea + 演奏 (SVG インライン表示) + 楽譜 (JSON Score collapsible)
  - Vite dev proxy: `/api` → `http://127.0.0.1:8000` (CORS 回避)
  - スタイル: Renderer パレットと整合 (背景 #f7f5ef, 墨 #111)、和文フォント優先
  - 名前: `inku-web` v0.1.0
  - svelte-check: 0 error, 0 warning

- **ホスト構成**
  - server + web ともに pentala (Ubuntu 22.04.5) で常時起動
  - Mac はブラウザクライアント専用 (SSH tunnel `-L 5173 -L 8000`)
  - Node.js 22.22.2 (NodeSource apt、システム PATH)、Python 3.10.12 + uv

- **次段階への布石**
  - `/api/compose` は Stage 2 のみ。Stage 1 (Opus 解釈) エンドポイントは未実装
  - 解釈フィードバック (書後色付け)、Saijiki 参照窓、Prev/Next 並置は UI 未着手
  - Renderer の揺らぎ (perlin/wave) 実装も未着手 (fixture 11/15 が variation 指定)

### v0.4 (2026-04-23)

**Phase 1 実装着手 — Server バックエンドの骨格形成**

- **リポジトリ構成**
  - `inku-lang` リポジトリを GitHub (`github.com/oikawas/inku-lang`) に作成
  - 開発フロー: `pentala` (Ubuntu 22.04.5) 中心開発 + Mac git sync
  - `server/` と `web/` の2スロット構成。`server/` 先行実装

- **Python プロジェクト: inku-server 0.1.0**
  - パッケージマネージャ: `uv` (0.11.7) + src-layout
  - 依存: anthropic, fastapi, pydantic v2, svgwrite, uvicorn, python-dotenv
  - dev: pytest, ruff
  - Python 3.10+

- **JSON Score schema (Pydantic v2 実装)**
  - `extra="forbid"` で未知フィールド拒否、schema 厳密化
  - `populate_by_name=True` + alias で予約語回避 (`from` → `from_`)
  - Primitive: `line | circle | ellipse | triangle | square | arc`
  - Weight 9種、Color 6種、LineStyle 4種、Variation 4フィールド (amplitude/frequency/quality/dimensions)
  - `Score.model_json_schema()` を Anthropic tool input_schema にそのまま渡せる形

- **Renderer MVP (svgwrite, 1000x1000 viewBox)**
  - 実装済 primitive: line, circle, ellipse, triangle (等辺二等辺), square (矩形)
  - 座標変換: `0.0-1.0` 比率 × `CANVAS_PX=1000` で px 化
  - weight → `stroke-width` マッピング (hair 0.5 〜 rope 10.0)
  - color → HEX パレット (黒=#111111, 青=#2c3e91, 赤=#a2342a, 緑=#2f6b3a, 灰=#888888, 白=#ffffff)
  - style → `stroke-dasharray` (solid=なし, dashed=12,8, dotted=2,6, dash_dot=12,6,2,6)
  - 背景色: `#f7f5ef` (墨が映える薄黄、和紙を想起)
  - 未実装: arc (schema に角度フィールド未定義)、variation の実際の波形生成

- **Stage 2 composer (正規化DDL → JSON Score)**
  - モデル: `claude-haiku-4-5-20251001` via Anthropic tool_use
  - `submit_score` ツールを定義し `tool_choice` で強制呼び出し
  - system prompt に Saijiki 歳時記マッピング + 座標系 + 出力ルールを圧縮記述
  - `Score.model_json_schema()` を tool input_schema に直接注入

- **正規化DDL Fixture 15ケース**
  - `server/tests/fixtures/stage2/{01..15}/` に input.txt + expected.json ペア
  - 網羅: 全5 primitive、全4 style、weight 複数 (pencil/pen/brush_thick)、color 全6、variation 2種 (fine+perlin, broad+wave)、複数命令 (3円並列)

- **テスト**
  - `test_renderer.py`: 10 cases, pytest 全 pass
  - `test_composer.py`: 15 fixture parametrize + tool schema validation
  - Integration は `ANTHROPIC_API_KEY` 有時のみ実行 (`pytest.mark.skipif`)
  - `conftest.py` で `.env` 自動読込 (python-dotenv)

- **二段階変換アーキテクチャの確定**
  - v0.3 で方針化、v0.4 で Stage 2 (Haiku 4.5) を先行実装 (逆順実装)
  - Stage 1 (Opus 4.7 解釈) は未着手
  - `/api/compose` FastAPI 実装は次 phase

### v0.3 (2026-04-21)

- inku-langとしての全体設計の開始
- プロジェクト名を `inku` (inku-lang) として確定
- Section 4「プラグイン設計原則」を新規追加（Emacs Lisp 化を避ける5原則）
- Section 12「Opus 4.7 の役割」を「二段階変換アーキテクチャ」として大幅書き換え
- Section 13「揺らぎの設計」を新規追加（感情語彙と運動語彙の区別、三層構造）
- Section 3「コアに入れるもの」に「つらなり」「ゆらぎ」カテゴリを追加
- Section 5「Base Language 問題」に責任範囲の明確化（日英は作者、他言語はコミュニティ）
- Section 7「UI設計方針」に Saijiki（歳時記）、解釈フィードバック、書後色付けを追加
- Section 6「コアとエクステンションの分離」の方針を整理

### v0.2 (2026-04-14)

- 最初のプロトタイプとして、コンセプトしたものが動作可能かを簡単にクライアントでテスト
- Android 実装状態を記録（SPEC_v1.md に分離）
- LiteRT-LM 0.10.0 API 調査・実装
- Pixel 9 での E2E 動作確認

### v0.1 (2026-04-02)

- 初期コンセプト（東京都現代美術館「ソル・ルウィット オープン・ストラクチャー」展にて構想）
- 三層パイプライン（記述 → 楽譜 → 演奏）の設計
- JSON Schema v0.1 の策定
- DDL_concept.md として初期ドキュメントを記録

---

## 起源

構想: 2026年4月2日、東京都現代美術館「ソル・ルウィット オープン・ストラクチャー」展
