# 予測の凍結 — 待っているあいだ、どの層が働いているかが画面に出る

**エージェント**: Claude Opus 5（実装セッション）
**契約**: `no-git-sync/fable5/claude_code/tasks/stock/the-stream-says-which-layer-is-working.md`（[I-302]）
**枝**: `feat/the-stream-says-which-layer-is-working`／**作業場** `/Users/oikawas/projects/ddl-server-render`
**起点**: `0f6478c9`（clean・0 ahead・`git merge-base main HEAD` で実測）
**この文書を書いた時点で、製品コードもテストも 1 行も書いていない。**

---

## 1. 着手前の満点（実測）

| 面 | 回し方 | 実測 | 測った機械 |
|---|---|---|---|
| **server** | `testbox.sh --sync --exclusive --server` | **3435 passed / 31 skipped**（79.98s） | **pentala のテスト専用コンテナ**（`inku-test:local`・run tree `test-runs/ddl-server-render`） |
| **web（unit）** | `npm run test:unit` | **449 tests / 449 pass / 0 fail / 0 skip** | Mac |
| **web（check）** | `npm run check` | **268 FILES / 0 ERRORS / 2 WARNINGS**（既知の a11y 2 件） | Mac |
| **web（i18n）** | `npm run lint:i18n` | **1078 English strings / 48 allowed exceptions / 0 warnings / 0 errors** | Mac |

server の 3435 / 31 は契約 §0 の記録（`full-run-records.tsv` の `0f6478c9` 行）と一致した。

---

## 2. 受入をどこに置くか（予定）

| 番号 | 置き場 |
|---|---|
| T-242〜T-247・T-249〜T-251 | **新規** `server/tests/test_the_stream_says_which_layer_is_working.py`（**9 個の test 関数**。T-250 は 1 ケースのみ、parametrize しない） |
| T-248・T-252 | **新規** `web/src/lib/the-stream-says-which-layer-is-working.test.ts`（**T-252 は 1 個の test で ja / en を loop する**） |
| T-253 | **既存** `server/tests/test_api.py:1724` `test_paint_stream_matches_paint_response_shape`（新しく書かない） |
| T-254 | pytest ではない。`testbox.sh --sync --corpora` の差分 0 件 |

**段 5 で直す既存テスト**: `server/tests/test_api.py:1690` `test_paint_stream_emits_stage1_before_done`
（`["stage1", "done"]` → `["stage1", "score", "done"]`）。以下では **E-1** と呼ぶ。

---

## 3. 摂動 13 本の予測（**本数で凍らせる**）

**数え方**: pytest は **赤くなる test 関数／parametrize ケースの数**。web は **赤くなる `test()` の数**。
**web の摂動は全走のメタゲート（`the-navigation-buttons-agree-on-which-way-is-newer.test.ts` の
子プロセス全走・`fail === 0` を主張）を道連れにするので +1 を含める。**
**server 側に同種のメタゲートは無い**（`grep -rln subprocess server/tests` で全 11 ファイルを見たが、
全 test を子プロセスで走らせるものは無い）。

| 番号 | 壊すもの | **予測本数** | 内訳（予測） |
|---|---|---|---|
| **P-1** | `sketch` の `yield` を `interpret` 呼び出しより後ろへ | **1** | T-244 |
| **P-2** | `sketch` の `yield` を消す | **3** | T-242・T-246・T-249 |
| **P-3** | `sketch` を条件なしに常に出す（`sketch_result` が `None` でも落ちない形で） | **4** | T-243・T-251・E-1・`test_paint_stream_reports_compose_failure_as_error_event` |
| **P-4** | `score` の `yield` を消す | **5** | T-242・T-243・T-245・T-247・E-1 |
| **P-5** | `score` の `yield` を `_render_with_metadata` の後ろへ | **1** | T-245 |
| **P-6** | `t2`（`render.py:2033`）を `score` の位置へ繰り上げる | **1** | T-247 |
| **P-7** | `readPaintStream` の分岐に `else { throw }` を足す | **2** | T-248 ＋ メタゲート |
| **P-8** | `api_paint_stream` の `first = next(events)` を消す | **7** | T-250・T-251 ＋ `test_t1_paint_stream_refuses_a_description_that_the_cut_empties`（**`LABEL_ONLY` が 5 件なので 5 ケース**） |
| **P-9** | `ja.ts` の `stageSketching` を `stageInterpreting` と同じ文字列にする | **2** | T-252 ＋ メタゲート |
| **P-10** | `en.ts` から `stagePerforming` の行を消す | **3** | T-252 ＋ **T-16「英語語彙の番人が clean」**（i18n-lint の規則 1 が日英の鍵の一致を見る）＋ メタゲート |
| **P-11** | `onScore` を配線しない（lib 側のハンドラ組み立てから外す） | **2** | T-252 ＋ メタゲート |
| **P-12** | `server/src/inku_server/renderer.py:378` `"margin": 12,` を 1 動かす | **corpora の差分 > 0**（T-254） | **pytest の全走は回さない**（描画が動く摂動なので大量に赤くなる。契約が求めているのは「T-254 に判別力があるか」だけ） |
| **P-13** | `score` の `yield` を `done` の `yield` の後ろへ | **5** | T-242・T-243・T-245・T-253・E-1 |

### 予測の根拠のうち、素直でないもの

- **P-3 は `sketch_result` を素で参照すると `AttributeError` になり、全走が読めない本数だけ赤くなる。**
  そこで**「条件を外し、`None` でも落ちない payload で常に出す」形で当てる**（`grain` などを `None` 許容にする）。
  **当てた現物は報告に載せる。**
- **P-4 は契約の予測が「T-242・T-243」だが、`score` イベントを読む T-245 と T-247 も落ちる。**
  **P-13 も契約は T-253 だけを挙げているが、イベント列と「描画より前」を見る 4 本が道連れになる。**
- **P-5 と P-13 は `t_score = time.perf_counter()` を動かさず `yield` だけを動かす。**
  したがって **T-247（`score` の `elapsed_ms` < 50）は両方で緑のまま**である。
- **P-6 の T-247 が成立するのは、`_render_metadata`（メタデータを組む側）が `t2` より前に呼ばれるからである**
  （`render.py:2011` で呼ばれ、`t2` は `:2033`）。50 ms 眠らせると `elapsed_stage2_ms` にだけ載り、
  `score` の `elapsed_ms` には載らない。**`t2` を繰り上げると両方が 50 未満になって割れる。**
- **P-10 は 3 本。**「T-252 だけ」と読むと 1 本外す —— en.ts から鍵が消えると i18n-lint の
  **規則 1（`en.ts` と `ja.ts` は同じ鍵ちょうど）** が error を出し、それを見る web の T-16 も赤くなる。

---

## 4. 予測を外したときに報告すること

- **当たらなかった摂動は「冗長」で片づけない。**そのゲートの逆向き（何を壊せば赤くなるか）を測って書く。
- **本数が予測より多かった／少なかったものは、どの test が増減したかを名指しで書く。**

---

## 5. この commit の時点で「まだ無い」もの

- 製品コードの変更（`render.py` のイベント 2 つ・`paintStream.ts`・i18n の 2 語）は **1 行も書いていない**
- 受入 T-242〜T-254 は **1 本も書いていない**
- 摂動は **1 本も当てていない**
