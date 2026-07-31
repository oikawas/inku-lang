# inku 英語 UI 用語辞書（正本）

**UI の文字列を足す・変える前に、必ずこの文書を引くこと。** 英語は日本語の直訳ではなく、
美術・版画・音楽・genart の英語圏の術語に対応させてある。辞書を引かずに訳語を発明すると、
一語二義（同じ英語が二つの概念を指す）と混線（interpretation / reading / performance / variation）が起きる。

この文書の規則は **`web/scripts/i18n-lint.mjs` が機械で検査する**。文面と検査は一対で、
片方を変えたら同じ commit でもう片方も変える。

```sh
cd web
npm run lint:i18n          # 用語・禁止語・文体の検査
npm run lint:i18n -- --list # 許容例外として何を通したかも出す
npm run check              # 型と鍵の欠落（LangPack）
```

出典: `no-git-sync/fable5/co-work/inkuenterminology.md`（Fable の翻訳辞書）と
`no-git-sync/fable5/claude_code/tasks/en-terminology.md`（2026-07-25 の作者裁定）。
適用の記録は `en-terminology-result.md`、全 788 文字列の対応表は `en-terminology-inventory.md`。

---

## 0. 三行で

1. **日本語が正本。** 英語だけを直す。日本語の文言・語順・句読点を「ついでに」直さない。
2. **一語一義。** 同じ概念に二つの英語を当てない。特に §2 の 6 語。
3. **工房の語で書く。** generate / prompt / create / image / AI-powered / magic は使わない（§5）。

---

## 1. 英語表示は 4 系統ある

`en.ts` だけ直すと、コンポーネント側に旧語彙が残る。**新しい文字列を足すときも 4 系統のどれに置くかを決める**。

| # | 系統 | 場所 | 件数（2026-07-25） |
|---|---|---|---|
| 1 | i18n パック | `web/src/lib/i18n/en.ts`（型は `types.ts` の `LangPack`。`ja.ts` と鍵は完全一致） | 641 項目 |
| 2 | コンポーネント内の三項式 | `isJapanese ? '…' : '…'`（`CanvasPanel` / `LineagePanel` / `InputPanel` / `HistoryStrip` ほか） | 132 箇所 |
| 3 | `getLang()` 分岐 | `getLang() === 'ja' ? '…' : '…'`（`+page.svelte` ほか。改行を挟む形も 1 件ある） | 15 箇所 |
| 4 | 日英併記ラベル | コンポーネントのテキストノードにある `日本語 / English`。英語側だけを lint する | 17 箇所（2026-07-31） |

**新規は原則 系統 1（`en.ts`）に置く。** 系統 2・3 は既存分だけ。系統 4 はモデル情報カードの
日英同時表示を保つ場合に限る。鍵を足したら `ja.ts` にも同じ鍵を足す
（`npm run check` が鍵の欠落を error にする）。

---

## 2. コア用語辞書（層とパイプライン）

| 日本語（正本） | 英語 | 品詞・用法 | 使ってはいけない訳 |
|---|---|---|---|
| 記述 | **description** | 名詞。動詞は write | ~~prompt~~（思想に反する） |
| 解釈（Stage 1） | **interpretation** / **interpret** | 名詞／動詞 | ~~reading~~（読み取りと混線する） |
| 指示書（正規化DDL） | **instructions** | **常に複数形**。初出は "Instructions (normalized DDL)" | ~~instruction~~（単数）、~~spec~~ |
| 楽譜 | **score**（固有表記は **JSON Score**） | 名詞 | — |
| 演奏 | **performance** / **perform** | 名詞／動詞 | ~~rendering~~（技術文脈のみ・§5） |
| 演奏する（主動作ボタン） | **Paint** | 動詞。API `/api/paint` と一致 | ~~Generate~~, ~~Create~~, ~~Draw~~（ボタン語として） |
| 読み取り（言葉の読み直し） | **reading** | 名詞 | ~~interpretation~~ |
| 揺らぎ | **sway** | 名詞 | ~~fluctuation~~（計測器）、~~jitter~~（信号） |
| 添景 | **staffage** | 名詞。tooltip に "minor accompanying elements" を添える | ~~decoration~~, ~~props~~ |
| 歳時記 | **Saijiki** | 固有名詞・大文字 | ~~almanac~~ 単独 |
| 詞書 | **headnote** | 名詞。語彙ダイアログでのみ "kotobagaki" の注記可 | ~~caption~~, ~~Kotobagaki~~（ラベルとして） |
| 奥書 | **colophon** | 名詞。**CLI サブコマンドと API パスも `colophon`**（§6 の例外・v2.8.0） | ~~Okugaki~~（ローマ字残しは不採用） |
| 系譜 | **lineage** | 名詞 | — |
| 系譜全体図 | **lineage map**（ボタンは **Map**） | 名詞句 | ~~Overview~~ |
| 世代 | **generation**（略 **Gen.**） | 名詞。**世代の意味のときだけ generation を使ってよい** | — |
| 推敲 | **refinement** / **refine** | 名詞／動詞 | ~~revision~~（事務的）、~~iteration~~（工学的） |
| AI 自律推敲 | **autonomous refinement** | 名詞句。**AI を頭に付けない** | ~~AI refinement~~, ~~AI-powered~~ |
| 変奏 | **variation** | 名詞。**変奏（Stage 1.5 の振り）だけに使う** | 推敲の候補は **option** |
| 候補・案 | **option** / **candidate** | 名詞 | ~~variation~~（変奏と衝突） |
| 色カタログ | **color catalog** | 名詞。inku 固有概念 | ~~palette~~（**禁止**） |
| 作品 | **work**（複数 works） | 名詞 | ~~artwork~~（**禁止**）、~~image~~ |
| 配置・構図 | **composition** | 名詞。五操作でも provenance でも同語 | ~~layout~~（UI 文中） |
| エディション／刷り | **edition** / **impression** | 名詞。`rh3` は edition ID、個々の SVG は an impression | — |
| 版木・版 | **block** / **state** | 版画の文脈のみ。engine の版数は **engine version** | — |
| 暴れる | **Wild** | トグルラベル。実装名 `WILD_GAIN` と一致 | ~~Unleashed~~ |
| 生成情報 | **provenance** | 名詞。モデル・seed・版数のドロワー | ~~Generation Info~~ |
| 履歴 | **history** | 名詞 | — |
| ごみ箱 | **trash** | 名詞 | — |
| 起点（新規作成） | **origin**（動作は **New**） | 名詞 | — |
| 記録なし | **not recorded** | 状態表示。値を推測しない契約の表示 | ~~unknown~~（別状態。`historyVersionUnknown` は「不明」の訳として別に存在する） |
| UIモード | **UI mode**（**Simple UI / Full UI / Custom UI**） | 表示構成の固定プリセットとユーザー別設定 | ~~Beginner / Expert~~（習熟度の評価にしない） |

### 2-1. 道具（てざわり）の名

てざわりの語そのものは `saijiki.py` が正本で、UI へは `/api/saijiki` からハイドレートされる（§6）。
ここに載せるのは、**UI が自前の文字列として書いている**もの — 語プレビューの例文と感情語ヒント — に限る。

| 日本語（正本） | 英語 | 品詞・用法 | 使ってはいけない訳 |
|---|---|---|---|
| 銀筆 | **silverpoint** | 名詞。Score の `weight` 値と同綴りで、小文字のまま文中に置く | ~~hair~~（2026-07-27 に改名。画材として存在しない語だった）、~~silver pen~~, ~~metalpoint~~ |

---

## 3. 五つの推敲操作と変奏の強度（**固定値。lint が一致を強制する**）

「何を引き直し、何を保つか」が名前だけで対比できるよう、**Another + 名詞**で統一する。
変奏だけは音楽術語 Variation を単独で使う。**ボタン幅が厳しくても名詞を省略しない**（折り返す）。

| 日本語（正本） | 英語ラベル | ツールチップの型 |
|---|---|---|
| 言葉でタッチを変える | **Another performance** | "Same interpretation, same composition — only the performance sways…" |
| 配置を変える | **Another composition** | "Same reading of your words — Stage 2 redraws…" |
| 読み取りを変える | **Another reading** | "Your sentence stays. The words are read anew…" |
| 色カタログを変える | **Another catalog** | "Same performance — colors re-translated through a different catalog…" |
| 変奏 | **Variation** | "Shakes the expansion layer (Stage 1.5) at a chosen amplitude…" |

変奏の強度 小／中／大 = **Subtle / Moderate / Sweeping**（2026-07-25 作者裁定）。

> **`Moderate` は変奏の強度に予約されている。** 速度の表示に使わない（コストは
> `Very fast (no LLM)` / `Medium (Stage 2 LLM and API)` / `Slow (LLM and API)`）。

tooltip の型: 一文目に「何が起きるか」、二文目に「何が保たれるか」。一〜二文で止める。

---

## 4. 文体規則

1. **Sentence case。** ラベル・ボタン・見出しはすべて先頭のみ大文字（"Another reading"。"Another Reading" としない）。
   固有名詞の例外は **Saijiki / inku / JSON Score / DDL** と製品名・技術トークン（API, DB, SVG, PNG, Stage 1 …）のみ。
   **`inku` は文頭でも小文字。**
2. **三点リーダは `…`（U+2026）一文字。** `...` を書かない。進行形 + `…` は進行中表示だけに使う。
3. **感嘆符を使わない。** 宣伝語（magic, amazing, AI-powered）も使わない。
4. **数値・単位・seed・hash・識別子は日英で同一。** 翻訳しない（`{render}` のような置換トークンも動かさない）。
5. **エラーは一行目を平叙文にする。** 技術情報は後段へ畳む。例: "The interpreter did not answer in time, so a stock set of instructions was performed."
6. **段階表示は工房の語で。** "Interpreting your words…" / "Writing the score…" / "Performing…"（"Generating…" と書かない）。
7. **語彙ダイアログ（App Info）は §2 の対訳表と一致させる。**

---

## 5. 禁止語と、許容される例外

**「grep 残存ゼロ」を目標にしない。** 正当な用法まで消える。lint は**キー単位の許容例外**で判定する。

### 5-1. どこにも書いてはいけない語

`palette` / `artwork` / `fluctuation` / `jitter` / `AI-powered` / `magic` / `okugaki`(ローマ字)

### 5-2. 決められた場所にだけ許される語（lint の `RESTRICTED`）

| 語 | 許される意味 | 許容キー（これ以外は error） |
|---|---|---|
| `generat*` | **世代**の意味、または PNG/SVG のファイル生成という技術文脈 | `aiRefineVisionModeHint` / `aiRefineDirectionRandomHint` / `aiRefineGensLabel` / `settingsDbBackupMaxGenerations` / `okugakiDescription` / `okugakiBranchConfirm` / `okugakiProgress` / `svgExportDisplayUse` / `svgExportEditableFeature` / `svgExportCompatFeature` / `provenanceLabelGeneration` / `provenanceHintGeneration`（生成情報ドロワーの**世代**の行） / `historyGenerationTitle`（履歴管理の作品パネルの**世代番号**） / `settingsDbBackupListGeneration` / `settingsDbBackupEstimatedDiskHint`（DB バックアップの**保存世代**） |
| `prompt` | **LLM プロンプトそのもの**の表示 | `tabPrompts` / `tooltipCanvasTabPrompts` / `promptStage1System` / `promptStage2System` / `CanvasPanel` の provenance 説明文 / `provenanceLabelStage1PromptDigest` / `provenanceLabelStage1PromptBaseDigest` / `provenanceLabelStage2PromptDigest` と対応する `provenanceHint*`（プロンプト digest の行。digest はプロンプトそのものの指紋なので description では言い換えられない） |
| `creat*` | **完了・日時・肩書き** | `appInfoCreatorTitle` / `settingsDbBackupRunDone` / `bootstrapAdminNote` / `historyCreatedAtHeader` / `Created`（列見出し） |
| `image` | **Vision が実際に画像を見る**文脈、またはInfoの作者指定文で心にある像を指す用法 | `appInfoConceptBody` / `modelSelectionVisionHint` / `aiRefineVisionModeHint` / `aiRefineVisionReading` / `aiRefineVisionSourceError` |
| `render*` | **サーバー側の技術設定・DB フィールド名・置換トークン** | `canvasSeedSummary`(`{render}`) / `settingsRenderConcurrency*`(5 件) / `historyReplayMissingSeed`(`render_seed`) / `replayComparisonTitle`(Renderer) |
| `kotobagaki` | 語彙ダイアログの**注記としての一度だけ** | `appInfoVocabRows` |
| `Moderate` | **変奏の強度・中** | `variationMedium` / `variationTooltipLarge` |

**新しく例外を足すときは、`i18n-lint.mjs` の該当リストとこの表を同じ commit で更新する。**
例外に足す前に、まず訳語を変えられないかを考えること。

---

## 6. 触ってはいけない経路

| パス | 理由 |
|---|---|
| `server/src/inku_server/saijiki.py` の `surface_en` / `name_en` | **英語版 DDL の語彙仕様**。`prompt_block("en")` から Stage 1 プロンプトへ流入し、golden fixture `server/tests/fixtures/prompts/stage1_prefix_en.golden.txt` が固定している。UI 表示の都合で変えない |
| `web/src/lib/saijiki.ts` / `saijiki.generated.ts` | 歳時記語とカテゴリ名の**表示経路**。中身は `/api/saijiki` からハイドレートされる server 由来の語 |
| `web/src/lib/i18n/ja.ts` | 日本語正本 |
| 三項式・`getLang()` 分岐の**日本語側リテラル** | 同上 |
| JSON Score の鍵 / API フィールド名 / SVG の class 名 / DB カラム名 / `rh3` 等の識別子 | 表示層の改修で識別子を動かさない |

**例外が 2 つある（どちらも同じ理由・同じ方針）。**

**例外その一 — 奥書（2026-07-27 作者裁定、v2.8.0 で実施）。**
**打鍵する名前は英語の術語で付ける**という先例（`paint` / `refine` / `lineage` が
辞書語と一致している。辞書 :55 は「API `/api/paint` と一致」と明記する）に対し、
**`okugaki` だけがローマ字で残っていた**ため、**CLI サブコマンド名と API パスを
`colophon` へ移した**。エイリアスは残していない（互換が切れるので minor 採番）。

**それでも動かさないもの**: DB のテーブル名・列名（`okugaki` テーブル）、
`model_settings` の `okugaki_model`（**保存済みユーザー設定**）、
モジュール名 `okugaki.py`、i18n の鍵 `okugaki*`。
**鍵名のローマ字は本来なら通例であり、禁じているのは表示に出る語である。**
ただし変奏については**辞書を完全に通すという作者裁定（2026-07-27）**により、
**鍵まで `hensou*` → `variation*` へ揃えた**（v2.8.0）。

**変奏では衝突が逆向きだった** — 辞書は `variation` を変奏だけに予約している
（候補は `option`）のに、実装では**本物の変奏がローマ字 `hensou`** で、
**変奏でない 4 種が `*_variation`** を名乗っていた。`touch_variation` → `touch_change`、
`model_variation` → `model_comparison`、`layout_variation` → `layout_change`、
`language_variation` → `language_comparison` とし、`hensou` → `variation` を戻した。
**`vary_seed` は変奏ですらなく Stage 1.5 の構図 seed** なので `composition_seed` にした。

> **hash と同一性 ID の材料は名前ではない。凍結する。**
> rh2 payload の鍵 `vary_seed` と `ddl_expander` の salt `#hensou` / `#vary` は動かしていない。
> **新旧の対応は `no-git-sync/opus5/name_convantion/RENAMES.md` に記録がある。**

**例外その二 — 添景（2026-07-27 作者裁定「奥書と同じ方針で」、v2.8.0 で実施）。**
辞書は 添景 = **staffage** と定めており（:58）、**web は既にその語で表示していた**。
ローマ字が残っていたのは**打鍵する側 1 箇所だけ** — CLI の旗 `--tenkei` である。
**`--staffage` へ移し、エイリアスは残していない**（奥書と同じ）。
help の文言も第三の語 `scenery` から `staffage` へ揃えた。

**それでも動かさないもの**: API の要求・応答フィールド `tenkei`（server 27 箇所）、
DB 列 `history.tenkei`、`tenkei_for_node()` 等の内部識別子、web の `tenkei.ts` と i18n 鍵。
**鍵名のローマ字は通例**という上の規則がそのまま効く。
番人は CLI 側に 2 つ置いた（`--tenkei` が `SystemExit` になること／
**旗の一覧そのものに `tenkei` を含むものが無いこと**。名指しの一覧は穴を残すため）。

> **歳時記のローマ字は別扱いである。** `/api/saijiki` と歳時記のカテゴリ鍵 9 個
> （`katachi` / `katamuki` / `tezawari` / `tsuranari` / `iro` / `yuragi` / `basho` / `ugoki` / `wariai`）は
> **辞書が 歳時記 = `Saijiki`（固有名詞・大文字）と定めているとおりで、ローマ字が正しい英語表記**である。
> `renga` / `hacho` も同じ扱い。**`sumi` / `washi` は識別子ではなく DDL の語彙値**
> （`sumi` は `black` の同義語として `ink` / `obsidian` / `黒` と並ぶ、記述者が書く語）。

**判断規則**: 変えようとしている文字列が Stage 1/2 プロンプト・Score・テスト fixture に届いているなら、
**直さずに作者へ報告する**（歳時記カテゴリ名が先例）。

---

## 7. 新しい UI 文字列を足すときの手順

1. **日本語を先に書く**（`ja.ts` に鍵を足す）。日本語が正本。
2. **§2 の表で概念を引く。** 表にある概念なら、英語はそこにある語を使う。
3. **表に無い概念なら、原典 §1 の五原則で決める**（メタファーを貫く／直訳より役割／ローマ字を増やさない／静かな文体／一語一義）。
   **決めた語と退けた候補を §2 の表に追記する**（辞書に無い語を黙って使わない）。
4. **§4 の文体規則を当てる**（Sentence case、`…`、感嘆符なし）。
5. `npm run lint:i18n` と `npm run check` を通す。
6. 語そのものの新設・変更（五操作の名前、強度の名前、コア用語の差し替え）は**作者裁定が要る**。
   実装セッションの判断で決めない。

---

## 8. 検査が何を見ているか

`web/scripts/i18n-lint.mjs`（error は 1 件でも exit 1）:

1. `en.ts` と `ja.ts` の**鍵集合が完全一致**すること
2. §3 の固定ラベル（五操作・強度・`Paint`・`Wild`）が**一字一句その語**であること
3. §5-1 の禁止語が**どこにも無い**こと
4. §5-2 の制限語が**許容キー以外に無い**こと
5. `...`（三点）と感嘆符が無いこと
6. ラベル（文末記号を含まない短い文字列）の **Title Case 疑い**（warning）

`npm run check`（svelte-check）は `LangPack` の鍵欠落を error にする。**用語の質は見ない。**

日本語を動かしていないことは、必要なら指紋で確かめられる（`LC_ALL=C` を省かないこと）:

```sh
md5 -q web/src/lib/i18n/ja.ts
grep -rh -o "isJapanese ? '[^']*'" web/src | LC_ALL=C sort | md5
grep -rhE -o "getLang\(\) === 'ja' \? '[^']*'" web/src | LC_ALL=C sort | md5
```

---

## 9. まだ揃っていないもの（既知の食い違い）

- **README.md（英語）・SPEC.md・`manual/en/` は旧語彙のまま。** ただし**禁止語はもう残っていない**
  （2026-07-31 実測: `artwork` / `Okugaki` / `Unleashed` / `Generation Info` は 3 文書とも **0 件**。
  旧記載の「`artwork` 53 件」等は古い）。残るのは **`SPEC.md` の `palette` 10 件**で、
  これはカタログのフィールド名＝コード識別子である。**動いていないのは概念語のほう**で、
  `manual/en/` は generate 13 / generation 25 / create 14 / image 9 に対し perform 7。
  ドキュメント側の追随は別作業。
- **本辞書は英語表示文字列の正本であって、日本語の正本ではない**（`lint:i18n` が見るのは `en.ts` だけ）。
  **日本語 UI は旧語彙のまま**である（2026-07-31 実測: `ja.ts` に 生成 29 / 画像 7。
  `manualRefineGenerateButton` は ja「生成する」/ en "Refine"、`historyImageHeader` は ja「画像」/ en "Work"）。
  **`README.ja.md` と `manual/ja/` が 生成・画像 を使うのは、その日本語画面を正しく書き写しているから**である
  （台帳 [I-004]・2026-07-31 作者裁定で据え置き）。**日本語側を先に動かすなら UI から**。
- **履歴ゼロの空状態文言**（原典 §5 の "Nothing here yet. …"）に対応する鍵が UI に無い。足すなら鍵ごと新設する。
- `stage1Label` / `stage2Label` はどのコンポーネントからも参照されていない（死に鍵）。
