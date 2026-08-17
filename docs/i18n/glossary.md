# inku 日英用語対応表（正本） / Japanese–English Glossary

**日本語が正本で、英語は日本語の直訳ではなく、美術・版画・音楽・生成芸術の英語圏で通用する術語に対応させる。**
違和感のない・慣用に沿った語を選び、同じ概念に二つの英語を当てない（一語一義）。
工房の語で書き、工学と宣伝の語（generate / prompt / create / image / AI-powered / magic）を避ける。

- **本表が inku の日英訳語対応の正本である**（2026-08-17 統合）。それまで対応表は
  `web/src/lib/i18n/GLOSSARY.md` §2–§3 と、2026-08-09（Android 言語パック）・2026-08-10
  （公開アーキテクチャ文書）の 2 枚の私家版ノートに分かれていた。三者の行はすべて本表へ移した。
- **文体規則・禁止語と制限語・機械検査（`web/scripts/i18n-lint.mjs`）との対**は、引き続き
  `web/src/lib/i18n/GLOSSARY.md` が正本である。訳語を引くのは本表、書き方の規則を引くのはあちら。
- **対象外**: 歳時記の語彙（正本は `server/src/inku_server/saijiki.py`。`sumi` / `washi` は DDL の語彙値）、
  JSON Score の鍵・API フィールド名・DB 列名・`rh3` 等の識別子（表示層の語で動かさない）。
- **★印**は、裁定待ちだった対応を 2026-08-17 に上記方針の適用で確定させた行である。

列の読み方: 「用法」は品詞と使いどころ、「退けた訳・注」は使ってはいけない訳とその理由。
**「lint 固定」とある英語は `i18n-lint.mjs` が一字一句を強制する。**

---

## 1. 核 — 記述から刷りまで

| 日本語（正本） | 英語 | 用法 | 退けた訳・注 |
|---|---|---|---|
| 記述 | **description** | 名詞。動詞は write | ~~prompt~~（思想に反する） |
| 解釈（Stage 1） | **interpretation** / **interpret** | 名詞／動詞 | ~~reading~~（読み取りと混線する） |
| 指示書（正規化DDL） | **instructions** | **常に複数形**。初出は "Instructions (normalized DDL)" | ~~instruction~~（単数）、~~spec~~ |
| 楽譜 | **score**（固有表記は **JSON Score**） | 名詞 | — |
| 演奏 | **performance** / **perform** | 名詞／動詞 | ~~rendering~~（技術文脈のみ） |
| 作品 | **work**（複数 works） | 名詞 | ~~artwork~~（**禁止**）、~~image~~ |
| エディション／刷り | **edition** / **impression** | 名詞。`rh3` は edition ID、個々の SVG は an impression | — |
| 版木・版 | **block** / **state** | 版画の文脈のみ。engine の版数は **engine version** | — |
| 起点（新規作成） | **origin**（動作は **New**） | 名詞。系譜の根の札も origin | ~~Root~~（graph の語。web の旧表示は 2026-08-17 実測で解消済み） |
| 読み取り（言葉の読み直し） | **reading** | 名詞 | ~~interpretation~~ |
| 写生（Stage 0.5） | **Sketch from life** | 名詞句。**短縮形 `Sketch` を単独で使わない**（2026-08-03 作者裁定 D-1）。英語版 Stage 1 プロンプトが `sketch` を weight の語（淡い鉛筆の筆致）に使っており、単独だと一語二義になる | ~~Sketch~~（単独）、~~sketching~~、~~drawing from life~~ |
| 区切りの大きさ | **grain** | 名詞。写生の操作子の見出し語 | ~~granularity~~（工学的）、~~segmentation~~ |
| 細かく区切る／大きく区切る | **Fine** / **Coarse** | 形容詞。**grain の値としてのみ**。揺らぎの振幅の `fine` / `broad` とは別の軸 | ~~Small / Large~~（量に読める） |

## 2. パイプラインの層と判定

| 日本語（正本） | 英語 | 用法 | 退けた訳・注 |
|---|---|---|---|
| 演奏する（主動作ボタン） | **Paint** | 動詞・**lint 固定**。API `/api/paint` と一致 | ~~Generate~~、~~Create~~、~~Draw~~（ボタン語として） |
| 純粋呼出し（プラグイン語だけの入力） | **pure invocation** | 名詞句。Stage 1 を飛ばして転写する判定の名 | — |
| 転写・書き下し（プラグイン展開） | **writing-down** / **transcription** | 名詞。宣言的プラグイン文書の決定的展開。転写された instruction は transcribed instruction | ~~expansion~~ 単独（Stage 1.5 の展開と紛れる文脈では避ける） |
| 解釈フォールバック（Stage 1 が落ちた） | **Interpretation fallback** | 名詞句。**層を名指す**ため作曲側と対で使う | ~~Stage 1 fallback~~（UI で段番号を主語にしない） |
| 作曲フォールバック（Stage 2 が落ちた） | **Score fallback** | 名詞句。印の文言と生成情報の見出し | ~~Composition fallback~~（`composition` は配置・構図の語で `composition_seed` と紛れる）、~~Stage 2 fallback~~ |
| ★ 要求配達（coerce の配達契約） | **request delivery** / **deliver requests** | 固有の保守用語。記述で明示された色・形・個数・主題を Score へ届ける coerce の責務 | ~~preserving explicit requests~~（形が揃わない）。毎回の言い換えはしない |
| 天井（強制上限） | **ceiling**（強調は **hard ceiling**） | 名詞。coerce の最後に 1 回だけ当たる上限 | ~~cap~~・~~quota~~ |
| drop-only 優先 | **drop-only preference** | 名詞句。不正値を補正せず落とす設計傾向 | — |
| 演奏可能な Score | **performable Score** | 名詞句。coerce 後に Render Engine へ渡せる状態 | ~~renderable~~（技術文脈では可） |
| ★ 作品として引き直す | **new performance** | 名詞句。保存 Score からの別演奏（"Stored SVG and a new performance"） | 芸術文脈は performance、技術文脈だけ render、と分ける従来規則の適用 |
| ★ 同条件で再実行 | **replay** | 名詞／動詞。履歴の再現描画 | — |
| ★ 描画（技術操作） | **render** | 動詞・名詞。API・関数・engine の技術文脈のみ（`render-score`・Render Engine・`renderer.py`） | UI の芸術文脈では使わない |
| ★ ラスタ化（SVG→PNG） | **rasterize** | 動詞。PNG は SVG の派生物 | ~~convert~~ |
| 描画エンジン | **Render engine** | 名詞句。版数は **engine version** | ~~Drawing engine~~ |
| 鏡（検査のみの記録） | **mirror** | 名詞。生成を分岐させない観測（`carriage_warnings` など） | ~~gate~~（門は合否を持つ別概念） |
| 点呼（送り手の検査） | **roll call** | 名詞。全 sender が値を送っていることの検査 | — |
| 実況（stream の途中経過） | **commentary** | 名詞。`sketch` / `stage1` / `score` event の総称 | ~~progress~~ 単独 |

## 3. 推敲・変奏・系譜

| 日本語（正本） | 英語 | 用法 | 退けた訳・注 |
|---|---|---|---|
| 推敲 | **refinement** / **refine** | 名詞／動詞 | ~~revision~~（事務的）、~~iteration~~（工学的） |
| 言葉でタッチを変える | **Another performance** | **lint 固定**。五操作は Another + 名詞で統一 | — |
| 配置を変える | **Another composition** | **lint 固定** | — |
| 読み取りを変える | **Another reading** | **lint 固定** | — |
| 色カタログを変える | **Another catalog** | **lint 固定** | — |
| 変奏 | **Variation** | **lint 固定**。音楽術語を単独で。**変奏（Stage 1.5 の振り）だけに使う** | 推敲の候補は **option** |
| 変奏の強度 小／中／大 | **Subtle / Moderate / Sweeping** | **lint 固定**（2026-07-25 作者裁定）。`Moderate` は変奏の強度に予約 | 速度表示に使わない |
| 候補・案 | **option** / **candidate** | 名詞 | ~~variation~~（変奏と衝突） |
| AI 自律推敲 | **autonomous refinement** | 名詞句。**AI を頭に付けない** | ~~AI refinement~~、~~AI-powered~~ |
| 配置・構図 | **composition** | 名詞。五操作でも provenance でも同語 | ~~layout~~（UI 文中） |
| 系譜 | **lineage** | 名詞 | — |
| 系譜全体図 | **lineage map**（ボタンは **Map**） | 名詞句 | ~~Overview~~ |
| 世代 | **generation**（略 **Gen.**） | 名詞。**世代の意味のときだけ generation を使ってよい** | — |
| 派生種別 | **derivation kind** | 名詞。DB/API 識別子 `derivation_kind` と一致 | — |
| 経年（派生種別） | **Age** | 名詞。系譜の辺の札 | ~~Aging~~（進行形は工程に読める）、~~Patina~~（比喩を増やす） |
| 外部の種（派生種別） | **External seed** | 名詞句。`seed` は Score の語として既出 | ~~Foreign seed~~ |
| 破調（派生種別） | **Hacho** | ローマ字が正しい英語表記（`renga` と同じ扱い） | ~~Broken meter~~、~~Irregularity~~ |
| 連歌の付句（派生種別） | **Renga reply** | 付句は返した句なので reply | ~~Renga tsukeku~~（ローマ字 2 語）、~~Linked verse~~ |
| 奥書 | **colophon** | 名詞。**CLI サブコマンドと API パスも `colophon`**（v2.8.0） | ~~Okugaki~~（ローマ字残しは不採用。DB テーブル名・保存済み設定の鍵は凍結で残る） |
| 詞書 | **headnote** | 名詞 | ~~caption~~、~~Kotobagaki~~（ラベルとして） |

系譜の辺の札（web `derivation.ts` の写し。**正本は実装**で、本表は 2026-08-17 に写した）:
タッチ = Touch ／ 構図 = Layout ／ 色 = Color ／ 解釈 = Reading ／ モデル = Model ／ 言語 = Language ／
DDL編集 = DDL edit ／ 記述編集 = Description edit ／ 再描画 = Replay ／ キャンバス変更 = Canvas change ／
変奏 = Variation ／ 写生の区切り = Sketch grain。
**注**: 辺の札は 1 語の短札という別の register で、`Layout` / `Color` は §3 の
composition / color catalog と食い違って見える（→ §8）。

## 4. 画面の語

| 日本語（正本） | 英語 | 用法 | 退けた訳・注 |
|---|---|---|---|
| 履歴 | **history** | 名詞 | — |
| ごみ箱 | **trash** | 名詞 | — |
| 生成情報 | **provenance** | 名詞。モデル・seed・版数のドロワー | ~~Generation Info~~ |
| 記録なし | **not recorded** | 状態表示。値を推測しない契約の表示 | ~~unknown~~（調査の「未確認」は別概念 → §5） |
| UIモード | **UI mode**（**Simple UI / Full UI / Custom UI**） | 表示構成のプリセットと個人設定 | ~~Beginner / Expert~~（習熟度の評価にしない） |
| 権限グループ | **Permission groups** | 名詞・**常に複数形**。1 人が複数を持てる（v2.12.0） | ~~Role~~（判定から消えた語）、~~Access level~~ |
| 管理者（グループ名） | **Administrators** | 権限グループ `admins` の表示形・複数形 | ~~Admin~~（旧 role の表示語）、~~Administrator~~（単数） |
| リーダー（グループ名） | **Leaders** | 権限グループ `leaders` の表示形 | ~~Group lead~~、~~Manager~~ |
| ユーザー（グループ名） | **Users** | 権限グループ `users` の表示形 | ~~User~~（単数）、~~Member~~ |
| ユーザーグループ | **user group** | 組織のまとまり・1 人 1 つ。**権限とは独立** | ~~permission group~~（別の実体） |
| 暴れる | **Wild** | トグルラベル・**lint 固定**。実装名 `WILD_GAIN` と一致 | ~~Unleashed~~ |
| 筆致制限 | **Stroke limit** | 暴れるトグルの見出し語 | ~~Brush limit~~ |
| 制限値 | **Limits** | 設定タブ名。一枚が持てる墨の数を決める数の組 | ~~Caps~~・~~Quotas~~・~~Thresholds~~ |
| 描画表現（設定カード） | **Stroke** | 見出し語。筆致制限・暴れると同じ軸 | — |
| 脱・規則化（カード副題） | **Letting the stroke off its rules** | 句 | ~~Derandomization~~（逆の意味）、~~Unruled~~ |
| 素材（歳時記語を開く操作子） | **Materials** | 名詞 | — |
| プロンプト最適化 | **Instruction optimization** | 名詞句。`prompt` が禁止なので指示書側の語で言い直す | ~~Prompt optimization~~ |
| 調整（比較 3 面の 1 つ） | **Adjust** | 見出し語。他は Model / Language | — |
| Stage 1/2 共通（比較モード） | **Stage 1/2 shared** | 名詞句。他は `Stage 1 fixed + Stage 2 compared` / `Stage 1 compared + Stage 2 fixed` | — |
| 説明（テンプレートの注記） | **Details** | 名詞。**`Description` は記述に予約** | ~~Description~~ |
| 履歴の値／現在値を維持 | **The history's value** / **Keep the current value** | 履歴選択の 2 択 | — |
| （推奨しない） | **(not recommended)** | 括弧付きの付記。**メニューの選択肢の隣にだけ** | ~~deprecated~~（廃止に読める）、~~legacy~~ |
| SVG オブジェクト数／SVG 点数 | **SVG objects** / **SVG points** | 生成情報の重さの行。数え方の正本は `$lib/svgWeight` | ~~elements~~・~~nodes~~（DOM の量に読める）、~~vertices~~ |
| 揺らぎ | **sway** | 名詞 | ~~fluctuation~~（計測器）、~~jitter~~（信号） |
| 添景 | **staffage** | 名詞。v2.11.0 で軸ごと畳んだ（記録の表示にのみ残る） | ~~decoration~~、~~props~~ |
| 銀筆 | **silverpoint** | 名詞。Score の `weight` 値と同綴り・小文字 | ~~hair~~（画材として存在しない語だった）、~~metalpoint~~ |
| 歳時記 | **Saijiki** | 固有名詞・大文字。カテゴリ鍵のローマ字（`katachi` ほか）は正しい英語表記 | ~~almanac~~ 単独 |

## 5. 文書・調査の語

| 日本語（正本） | 英語 | 用法 | 退けた訳・注 |
|---|---|---|---|
| ★ 利用者・作者 | **author** / **user** | **作品を作る主体・文書の人物ノードは author、認証・権限・DB の技術文脈は user**（`user_id`・user group 等の実装語と一致させる）。演奏 = performance / 技術 = render と同じ「芸術文脈と配管の語を分ける」規則の適用 | どちらか 1 語への統一は退けた（芸術の主体に user は冷たく、認証の主体に author は不正確） |
| 正本 | **canonical**（データは canonical data） | 形容詞。DB・Git・日本語仕様に共通 | ~~source of truth~~（説明文でのみ） |
| 派生物 | **derivative** | 名詞。作品ファイル・PNG・再生成物 | — |
| 根拠 | **evidence** | 名詞。Evidence ID・evidence inventory | — |
| 確認済み（信頼度） | **Confirmed** | 実装・test の直接根拠あり | — |
| 仕様のみ（信頼度） | **Specification** | 仕様にはあるが現行実装で未確認 | — |
| 推定（信頼度） | **Inferred** | 複数の静的根拠から推定 | — |
| 未確認（信頼度） | **Unknown** | 配備実測等を行っていない調査状態。**履歴表示の「記録なし = not recorded」とは別概念**で、この意味に限り許す | — |
| 既知の差異 | **known differences** | 名詞句。仕様差・実装差・未確認の記録 | — |

## 6. 禁止語と制限語

どこにも書いてはいけない語: `palette` / `artwork` / `fluctuation` / `jitter` / `AI-powered` / `magic` / `okugaki`（ローマ字）。
決められた場所にだけ許される語（`generat*` / `prompt` / `creat*` / `image` / `render*` ほか）の許容キー一覧と
機械検査の中身は、`web/src/lib/i18n/GLOSSARY.md` §5・§8 が正本である。
バックティックで囲んだ識別子は禁止の対象外（識別子は識別子のまま残す。「grep 残存ゼロ」を目標にしない）。

## 7. 本表の運用

1. **日本語を先に書く。** 概念を本表で引き、あれば必ずその英語を使う。
2. 表に無い概念は、方針（美術の慣用・一語一義・工房の語・ローマ字を増やさない・静かな文体）で決め、
   **決めた語と退けた候補を本表へ追記する**（辞書に無い語を黙って使わない）。
3. 文体（Sentence case・`…`・感嘆符なし）と禁止語・制限語は `web/src/lib/i18n/GLOSSARY.md` §4–§5 を当てる。
4. **語そのものの新設・変更（五操作の名前・強度の名前・コア用語の差し替え）は作者裁定が要る。**
   ★印の行は 2026-08-17 の方針適用で確定させたもので、裁定はいつでも上書きできる。
5. 統合前の 2 枚の私家版ノート（2026-08-09 Android・2026-08-10 アーキテクチャ）は役目を終え、記録として残る。

## 8. 既知の食い違い

- **系譜の辺の札** — web 実装は `layout_change` に "Layout"、`catalog_change` に "Color" を出す。
  本表の 配置 = composition・色カタログ = color catalog とは別の 1 語短札の register で、
  実装の写しとして §3 に記録した。**揃えるかどうかは裁定事項**。
- **日本語 UI 側の揺れ** — 「キャンセル」と「取消」、「デモ」と「デモ表示」が併存し、英語はどちらも
  Cancel / Demo の 1 語に落ちている。日本語を揃えるかどうかは裁定事項（日本語を「ついでに」直さない規則のため据え置き）。
- **日本語 UI の旧語彙**（生成・画像）と `manual/en/` の制限語の残りは、
  `web/src/lib/i18n/GLOSSARY.md` §9 の記録のとおり（本表の対象は訳語の対応で、適用の進捗はあちらが持つ）。
