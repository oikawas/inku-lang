# 凍結: 作曲が落ちた作品にも印が付き、その作品を親に選ぶときは一度だけ尋ねる（[I-292]）

**この文書は、製品コードを 1 行も書く前に commit で凍らせる**（実行規約 §2-8）。
ここに書いた数字を、実装のあとで書き換えない。実測との差は完了レポートに書く。

- **エージェント**: Opus 5（`claude-opus-5[1m]`）／ 契約 `a-work-drawn-by-a-fallback-says-so.md`
  ／ 枝 `feat/a-work-drawn-by-a-fallback-says-so` ／ 起点 `0f6478c9`
- **測った木**: `/Users/oikawas/projects/ddl-server-work`
  （`git status --porcelain` の出力が空・`git merge-base HEAD main` = `0f6478c9`）
- **版**: v2.13.37 / Build 924 / render engine 38 / ddl engine 20

---

## 0. 走行中に受けた裁定（2026-08-17・作者）

**契約 段 2 は「送り手は web と cli の 2 つ」と書いているが、着手前の実測でこれは主経路を外していた。**

| 実測した事実 | 現物 |
|---|---|
| 描いた作品を保存する**主経路は server 自身** | `render.py:2074`〜`:2121` が `save_history` のとき `_add_history_item` を呼ぶ |
| **`interpret_fallback` を書いているのも server** | `render.py:2081` |
| **web が `interpret_fallback` を POST に積む行** | **0 件**（`web/src` 全体） |
| **cli が積む行** | **0 件**（payload 生成部） |
| `POST /api/history` の送り手（＝契約が名指す 2 つ） | web `+page.svelte:4463`（再保存）／ cli `cli.py:2174`（`compose` 経路）。**ほかに web の demo 保存 `:4489` と cli の `refine save` `cli.py:3408` がある** |

**➡ 作者裁定: 「server も書く —— Stage 1 とまったく同じ形にします。」**
したがって **段 1 に 1 条項を足す**（`render.py` の paint 経路が自分で `compose_fallback` を書く）。
**受入を 1 つ足し（T-242）、摂動を 1 本足す（P-12）。**
**⚠ この 1 条項と T-242 / P-12 だけが契約の文面に無い。ほかは契約どおり。**

---

## 1. 着手前の満点（**コードを 1 行も書く前**）

### 1-1. server 全走（pentala のテスト専用コンテナ）

```
cd /Users/oikawas/projects/ddl-server-work
/Users/oikawas/projects/ddl-server/no-git-sync/scripts/testbox.sh --sync --exclusive --server
```

| passed | skipped | 測った機械 |
|---|---|---|
| **3435** | **31** | **container:ddl-server**（`full-run-records.tsv` に自動で 1 行入った） |

**契約 §0 の記録（3435 / 31）と一致した。**
**⚠ Mac で測れば 3434 / 32 になる**（F-1 が darwin で skip する）。**本書の数字はすべてコンテナのもの。**

### 1-2. web / cli（Mac）

| 面 | コマンド | 実測 |
|---|---|---|
| web 単体 | `npm run test:unit` | **tests 449 / pass 449 / fail 0 / skipped 0** |
| web 型・a11y | `npm run check` | **268 FILES / 0 ERRORS / 2 WARNINGS / 2 FILES_WITH_PROBLEMS** |
| web 語彙 | `npm run lint:i18n` | **1078 English strings / 48 allowed exceptions / 0 warnings / 0 errors** |
| cli | `make test-cli` | **237 passed**（warnings 50 は Pillow の Deprecation） |

**既知の a11y 2 件の在処を実測した** —— `AIRefineModal.svelte:192` と `ManualRefineModal.svelte:80`。
**契約 §6 の記述と一致する**（引き継ぎ文書の古い行ではなく契約が正しかった）。

### 1-3. 道連れになるメタゲート

**web の suite に 2 本ある**（契約 §4 の予告どおり。実測で在処を特定した）——
どちらも `web/src/lib/the-navigation-buttons-agree-on-which-way-is-newer.test.ts`:

| 名前 | 何をするか | 道連れの条件 |
|---|---|---|
| **T-15**（`:321`） | **自分以外の全 `.test.ts` を子プロセスで走らせ、`fail == 0` を主張**（`pass >= 191`） | **web の検査が 1 本でも赤くなれば必ず赤くなる** |
| **T-16**（`:366`） | `scripts/i18n-lint.mjs` を回し、warnings / errors が 0 であることを主張 | **`lint:i18n` が赤くなったときだけ** |

**⚠ 新しい検査ファイルは `web/src/lib/` に置くので T-15 の子走行に含まれる**（`walk(join(WEB,'src'))`）。
**T-15 の `BASELINE = 191` は `pass >= BASELINE` なので、検査が増えても赤くならない。**

**server 側にテストの総本数を主張する検査は 0 件**（`server/tests/*.py` を舐めて確認した）。
**cli 側にも 0 件。**したがって **道連れの「+1」は web にしか起きない。**

---

## 2. 着手前に測った、契約に無い事実

### 2-1. 推敲の呼び出し点（契約 §6 が「実装が数え直せ」と書いた数）

**発行側は「6 ＋ 5 ＝ 11 か所」と数えた。**起点 `0f6478c9` で数え直した実測は下記。

**`derivationKind` / `derivation_kind` をリテラルで立てる箇所 = 11**（発行側は 6 と数えていた）:

| 行 | 値 | 発行側が数えたか |
|---|---|---|
| `+page.svelte:4900` | `'description_edit'` | **数えていない** |
| `+page.svelte:4925` | `'sketch_grain_change'` | **数えていない** |
| `+page.svelte:4994` | `'ddl_edit'` | **数えていない** |
| `+page.svelte:5584` | `'touch_change'` | 数えた |
| `+page.svelte:5613` | `'layout_change'` | **数えていない** |
| `+page.svelte:5659` | `'reinterpretation'` | **数えていない** |
| `+page.svelte:5790` | `'touch_change'` | 数えた |
| `+page.svelte:5819` | `'layout_change'` | 数えた |
| `+page.svelte:5838` | `'reinterpretation'` | 数えた |
| `+page.svelte:5890` | `'catalog_change'` | 数えた |
| `+page.svelte:5927` | `'variation'` | 数えた |

**値を先へ渡す口 = 8**（発行側は 5 と数えていた）:
`:3274`（paint stream の本体）・`:3695`（`submitDerivationKind`）・`:4013`（`replayKind`）・
`:4466`（POST /api/history の本体）・`:5254`・`:5526`・`:6120`・`:6456`。

**➡ 実装が数えた全数は 11 ＋ 8 ＝ 19 か所**（型宣言 `:3144` と `pushHistory` の引数宣言 `:4454` を除く）。

**⚠ ただし「推敲を実行する動作」はこの 19 ではない。**リテラルの 11 は 5 本の候補生成器を含み、
それは `generateVariationCandidates`（`:5969`）1 つから出る。**動作で数えると 8 つ**である:

| # | 動作 | 親の出どころ |
|---|---|---|
| 1 | `varyPerformance`（`:5548`） | `ensureVisibleLineageParentId()` |
| 2 | `varyComposition`（`:5602`） | 同上 |
| 3 | `varyInterpretation`（`:5645`） | 同上 |
| 4 | `generateVariationCandidates`（`:5969`） | `currentLineageParentId()`（候補 5 種の親） |
| 5 | `drawLineageDescriptionEdit`（`:4892`） | `node.history` |
| 6 | `drawLineageSketchGrain`（`:4915`） | `node.history` |
| 7 | `drawLineageDdlEdit`（`:4940`） | `node.history` |
| 8 | `submit`（`:3628`・`submitDerivationKind`） | `submitParentNodeId` |

**`replay`（`:3892`）と `replayHistoryItem`（`:4704`）は数に入れる根拠を測り切れていない** ——
`replayKind`（`:4013`）は保存された作品の描き直しで、親は自分自身になりうる。
**実装の段で結線を読み、完了レポートで断定する。**

### 2-2. `refine save`（`cli.py:3408`）には積まない

**paint の応答を持たない経路である**（手元の score ファイルから 1 行作る）。
**積む値が無いので `null` になり、それは「記録が無い」で正しい。**
**T-234 の点呼は「描いた作品を保存する送り手」を数える** —— この経路は描いていない。
**⚠ 完了レポートで名指して報告する。**

### 2-3. `HistoryItem` は `HistoryPostBody` を継承している（`models.py:77`）

**したがって `HistoryPostBody` に 1 欄足せば応答モデルにも載る。**
（memory「`response_model` は消した鍵を戻す」の逆向き —— 宣言し忘れると鍵が黙って消える面。）

### 2-4. `_add_history_item` の呼び出し元は 2 か所だけ

`render.py:2076`（paint）と `history.py`（POST /api/history）。**`api_compose` は履歴を保存しない。**
既存の `sketch_state` の点呼（`test_sketch_state.py:245`）が数えている 8 か所と同じ形になる。

---

## 3. 実装の方針（段ごと）

| 段 | 触るファイル | 何を置くか |
|---|---|---|
| 1 | `server/src/inku_server/api_core/models.py` | `compose_fallback: str \| None = None`（`interpret_fallback` の隣） |
| 1 | `server/src/inku_server/db.py` | 列・移行 1 行・`_row_to_dict`（**鍵ごと欠かす**）・書き戻し |
| 1 | `server/src/inku_server/api_core/rendering.py` | `_add_history_item` の引数と dict の鍵 |
| 1 | `server/src/inku_server/api_core/routers/history.py` | `compose_fallback=body.compose_fallback` |
| **1（裁定で追加）** | `server/src/inku_server/api_core/routers/render.py` | **paint 経路が自分で書く** —— 落ちたら `compose_retry_reasons[0]`（無ければ `"stage2_fallback"`）、**落ちなければ `"none"`** |
| 2 | `web/src/routes/+page.svelte` | 応答型に `compose_fallback_used` / `compose_retry_reasons` を足し、**2 つの POST 本体**（`:4466` `:4492`）に実効値を積む |
| 2 | `cli/src/inku_cli/cli.py` | `_history_payload_from_result` に実効値を積む |
| 3 | `web/src/lib/`（新規モジュール） | 印の導出・三状態の導出を**純関数 1 か所**に置き、両コンポーネントから呼ぶ |
| 3 | `HistoryThumbnail.svelte` / `CanvasPanel.svelte` / `+page.svelte` | 条件を広げ、生成情報に三状態を出す |
| 3 | `i18n/ja.ts` `en.ts` `types.ts` | `composeFallbackBadge` ほか。**英語は `Score fallback`** |
| 4 | `web/src/lib/`（同上）＋ `+page.svelte` | 一度きりの確認。**画面のセッション内で作品 id の集合を持つ** |

**⚠ 実効値の積み方は `a ?? b` にする**（memory「実効値を送る・生のフィールドではない」）——
`compose_fallback_used` が偽のときに **`"none"` を積む**のが段 2 の要である。

---

## 4. 段が全部入った後の満点（**予測**）

| 面 | 着手前（実測） | **後（予測）** | 増分 |
|---|---|---|---|
| server（コンテナ） | **3435 passed / 31 skipped** | **3444 passed / 31 skipped** | **+9** |
| cli | **237 passed** | **239 passed** | **+2** |
| web | **449 pass / 0 fail** | **461 pass / 0 fail** | **+12** |
| `npm run check` | 268 FILES / 0 ERRORS / 2 WARNINGS | **268 FILES / 0 ERRORS / 2 WARNINGS** | **0**（ファイル数は新規 `.ts` 1 本で **269** になる可能性がある。**その場合は「増えた」と報告する**） |
| `lint:i18n` | 0 warnings / 0 errors | **0 warnings / 0 errors**（English strings は増える） | — |

**新しい検査ファイルは 3 本**:

- `server/tests/test_a_work_drawn_by_a_fallback_says_so.py` —— **9 本**
- `cli/tests/test_a_work_drawn_by_a_fallback_says_so.py` —— **2 本**
- `web/src/lib/a-work-drawn-by-a-fallback-says-so.test.ts` —— **12 本**

**段だけで赤くなる既存の検査は 0 本と予測する。**根拠 ——
① 描画に触らない（§5 の禁止）ので凍結物は動かない、
② `interpret_fallback` を読む既存の検査（`test_api.py:1961`〜`:1969`）は Stage 1 の列しか見ておらず、
新しい列は**鍵ごと欠かす**形で足すので既存の応答の形が変わらない、
③ web の既存 449 本に `compose_fallback` を読むものは 0 件（grep 実測）。

---

## 5. 摂動の予測（**本数ではなく名前の一覧**）

**摂動は 12 本**（契約の 11 本 ＋ 裁定で足した **P-12**）。当て方は `no-git-sync/scripts/perturb.py` を通す。

略号: `[S]` = `server/tests/test_a_work_drawn_by_a_fallback_says_so.py`、
`[C]` = `cli/tests/test_a_work_drawn_by_a_fallback_says_so.py`、
`[W]` = `web/src/lib/a-work-drawn-by-a-fallback-says-so.test.ts`、
`[既]` = `the-navigation-buttons-agree-on-which-way-is-newer.test.ts`。

| P | 何を壊す | **赤くなると予測する検査の名前（全体）** | 本数 |
|---|---|---|---|
| **P-1** | `history.py` の `compose_fallback=body.compose_fallback` を落とす | `[S] test_t230_a_client_saved_reason_comes_back_out`<br>`[S] test_t234_every_sender_that_saves_a_drawn_work_stacks_the_key` | **2** |
| **P-2** | `db.py` の移行表から `ALTER TABLE ... compose_fallback` の行を消す | `[S] test_t231_the_migration_adds_the_column_and_keeps_every_row`<br>`[S] test_t231_the_migration_has_no_default_and_no_backfill` | **2** |
| **P-3** | web の送り手から鍵を外す | `[W] T-232 the web sender stacks the reason when compose fell`<br>`[W] T-232 the web sender stacks none when compose held`<br>`[S] test_t234_every_sender_that_saves_a_drawn_work_stacks_the_key`<br>`[既] T-15` | **4** |
| **P-4** | cli の送り手から鍵を外す | `[C] test_t233_the_cli_stacks_the_reason_when_compose_fell`<br>`[C] test_t233_the_cli_stacks_none_when_compose_held`<br>`[S] test_t234_every_sender_that_saves_a_drawn_work_stacks_the_key` | **3** |
| **P-5** | 印の導出条件を「Stage 1 のみ」に戻す | `[W] T-235 the mark is derived from either layer`<br>`[W] T-235 both marks ask the shared derivation`<br>`[既] T-15` | **3** |
| **P-6** | 日英どちらかの文言の鍵を消す | `[W] T-236 the badge wording exists in both languages and names its layer`<br>`[既] T-15` | **2** |
| **P-7** | 確認の呼び出しを 1 か所外す | `[W] T-237 every refinement asks before it runs`（呼び出し点の点呼）<br>`[既] T-15` | **2** |
| **P-8** | 一度きりの記憶を外して毎回出るようにする | `[W] T-238 the same work is not asked about twice`<br>`[既] T-15` | **2** |
| **P-9** | 印の有無を見ずに常に確認を出す | `[W] T-239 an unmarked work is not asked about`<br>`[既] T-15` | **2** |
| **P-10** | `renderer.py:378` の `"margin": 12,` を 1 動かす | **T-240**（`testbox.sh --sync --corpora` の差分が 0 件でなくなる） | **1**（＋コンテナの全走で描画系が道連れ。**本数は予測しない** —— §5-3 ①） |
| **P-11** | 送り手が落ちなかったときに `"none"` を積むのをやめる | **web に当てたとき**: `[W] T-232 the web sender stacks none when compose held`／`[W] T-241 the sender writes none so the drawer can tell`／`[S] test_t234_...`／`[既] T-15` = **4**<br>**cli に当てたとき**: `[C] test_t233_the_cli_stacks_none_when_compose_held`／`[S] test_t234_...` = **2** | **4 / 2** |
| **P-12**（裁定で追加） | `render.py` の paint 経路の `compose_fallback=` の代入を落とす | `[S] test_t242_the_paint_route_writes_the_reason_when_compose_fell`<br>`[S] test_t242_the_paint_route_writes_none_when_compose_held`<br>`[S] test_t242_every_server_writer_of_a_work_also_writes_the_compose_state` | **3** |

### 5-1. P-10 の全走の本数を予測しない理由

**`margin` を動かすと凍結コーパスの SVG が全部ずれる。**赤くなるのは T-240 だけではなく、
**コーパスを照合する既存の検査が道連れで赤くなる**（memory「コーパス再走も道連れ」）。
**本数を予測すると外れることが分かっている数字を凍らせることになる**ので、
**「T-240 が赤くなること」だけを予測し、実測の本数は完了レポートに書く。**

### 5-2. どの予測がいちばん外れやすいか

**P-1 と T-241 の関係。** `[S] T-241` は **行を直に組んで `_row_to_dict` を読む**設計にするので、
**P-1（route の代入を落とす）では赤くならないと予測する。**
契約 §4 は P-1 の赤を「T-230・T-234」と書いており、T-241 を挙げていないので**契約と一致する**。
**もし赤くなったら、それは `[S] T-241` が route を通っていたということ**で、本数ではなく名前で報告する。

**次に外れやすいのは P-6 と `[既] T-16`。** 文言の鍵を消しても `lint:i18n` は
**English strings の本数が減るだけで errors にならない**と予測する（**T-16 は緑のまま**）。
ただし `npm run check` は型（`types.ts`）で赤くなる —— **`check` は `test:unit` の外なので道連れに数えない。**

### 5-3. 予測が外れる 5 通りのうち、本契約で起こりうるもの

- ①**摂動が描画に届く** → **P-10 だけが該当**。だから §5-1 で本数を予測しない
- ②**その周に自分が結線した先を数え落とす** → 起こりうる。**段 3 の純関数を 2 コンポーネント＋生成情報の
  3 か所から呼ぶ**ので、P-5 の道連れが 1 本増える可能性がある。**照合は名前で行う**
- ③**本数が相殺で一致する** → 起こりうる。**照合は名前の一覧で行う**
- ④**メタゲートを数え落とす** → §1-3 で 2 本を先に特定した。**server と cli には無い**
- ⑤**摂動が空振りする**（当てても既存の道と必ず一致する） → **P-11 が候補**。
  「`"none"` を積むのをやめる」は `null` になるだけなので、
  **三状態を主張する検査が無ければ空振りする。** それを捕まえるのが `[W] T-241` である

---

## 6. 触らないもの（契約 §5 ＋ 本書）

`server/src/inku_server/renderer.py`（P-10 の摂動を当てて戻す以外）・`stroke_engine`・
`schema.py` の Score・coerce の判定・参照コーパス・engine の版・
`android/`（1 ファイルも触らない）・pentala の `inku-lang/`・`APP_VERSION` 以外の版数・
`interpret_fallback` の列と印（作り直さない）・写生 fallback（列も印も足さない）・
既存の 449 / 237 / 3435 本の検査（1 本も書き換えない）。
