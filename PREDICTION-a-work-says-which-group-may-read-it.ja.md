# 着手前の凍結: 作品は、どのグループが読んでよいかを自分で言う

**契約**: `no-git-sync/fable5/claude_code/tasks/stock/a-work-says-which-group-may-read-it.md`（台帳 I-191）
**実装セッション**: Claude Code / Opus 5（1M context）
**枝**: `feat/a-work-says-which-group-may-read-it` ／ **起点**: `da68feef`（`git merge-base` で実測）
**作業場**: `/Users/oikawas/projects/ddl-server-work`

**この文書はコードを 1 行も書く前に commit する。** あとから書いた数字は、測っていない数字である。

---

## 1. 着手前の満点（**この枝の先端 `da68feef` で自分で実測**）

| 面 | 実測 | 契約 §0-B の記載 | 一致 |
|---|---|---|---|
| `make test-server` | **3401 passed / 31 skipped**（593.57s） | 3401 passed / 31 skipped | ✔ |
| `make test-cli` | **235 passed** | 235 passed | ✔ |
| `npm run test:unit` | **446 pass / 0 fail** | 446 passed / 0 fail | ✔ |
| `npm run check` | **268 FILES / 0 ERRORS / 2 WARNINGS** | 同左 | ✔ |
| `npm run lint:i18n` | **1,076 strings / 48 exceptions / 0 warnings / 0 errors** | 同左 | ✔ |

`npm run check` の既知 2 件は `AIRefineModal.svelte:192` と `ManualRefineModal.svelte:80`（契約の記載どおり）。

**契約は満点のうち server の 1 行だけを「記録から引いた・測り直していない」と断っていた。**
**それも含めて 5 面すべてを自分で測り、5 面とも一致した。**

---

## 2. 契約 §0-B の行番号の突き合わせ（`da68feef`）

**名指しされた 34 点すべてが実物と一致した。** 食い違いは 0 件。

---

## 3. 発行時の契約に無かった事実（**着手前に測って、ここで凍らせる**）

### 3-1. 段 5 の宣言は **4 件ではなく 6 件**である

契約 §1 段 5 は番人 ②③ へ「同じ 4 件」を宣言せよと書き、その 4 件を
`ADDED_OPERATIONS` / `ADDED_SCHEMAS` / `CHANGED_SCHEMAS["HistoryItem"]` /
`CHANGED_OPERATIONS["GET /api/history"]` としている。

**しかし段 4 の項目 16 は `routers/lineage.py` の 2 ルートにも同じ query 引数を足す。**
その 2 ルートは番人 ②③ が比べる凍結ファイルの両方に **すでに `query:for_revision:opt` を持って載っている**
（2026-08-17 実測）:

- `server/tests/data/api-surface-before-the-guest-list.json`（番人 ③ が使う）
- `server/tests/data/api-surface-before-the-card.json`（番人 ② が使う）

| ルート | 凍結ファイル 2 つに在るか | 今日 `CHANGED_OPERATIONS` に在るか |
|---|---|---|
| `GET /api/history` | 在る | ③ に在る（`include_svg`）／**② には無い** |
| `GET /api/history/lineage-groups` | 在る | **②③ とも無い** |
| `GET /api/history/lineage-groups/{root_node_id}/items` | 在る | **②③ とも無い** |

**したがって宣言は ② が 6 件・③ が 6 件になる**（②③ とも
`CHANGED_OPERATIONS` へ 3 ルート分を置く。② は `GET /api/history` の項目自体が新設）。
**契約どおり 4 件だけ置くと、番人 ②③ の
`unchanged_ops_before == operations` が赤くなる。**

### 3-2. `_readable_sql` の `acl_group_id` は既に 2 か所で同じ値を書いている

`server/src/inku_server/db.py:1188` と `:1193` がどちらも `params["acl_group_id"] = actor["group_id"]` を書く。
**契約 §2 段 2 の生 SQL の断片が同じ鍵を 3 か所目で書くのは衝突ではない**（同じ値である）。

---

## 4. 摂動の予測（**17 本・実装前に凍結**）

**予測の読み方**: 「赤くなる T」は本契約が新設・裏返しする受入だけを数える。
web を赤くする摂動には全走メタゲート `T-15` が必ず +1 で付く（契約 §0-C）。

| P | 何を壊すか | **契約の予測** | **自分の予測（凍結）** | 差 |
|---|---|---|---|---|
| P-1 | `_readable_by` の旗の節だけを消す | T-192・T-194 | **T-192・T-194・T-200** | **+T-200** |
| P-2 | `_readable_sql` の旗の節だけを消す | T-200 | **T-200** | — |
| P-3 | 旗の節から `share_group_id` の一致を外す | T-193 | **T-193** | — |
| P-4 | 旗の節を `acl_history_id` の枝の外（`scope` 側）へ移す | T-195 | **T-195** | — |
| P-5 | 宛先を省いたときの自組織の充填を NULL のままにする | T-197・T-192 | **T-197・T-192** | — |
| P-6 | 非 admin の名指しチェックを外す | T-198 | **T-198** | — |
| P-7 | 旗を下ろすときに `share_group_id` も NULL にする | T-199 | **T-199** | — |
| P-8 | `_writable_by` にも旗の節を足す | T-196 | **T-196** | — |
| P-9 | ORM の絞り込みの filter を外す | T-200 | **T-200** | — |
| P-10 | 生 SQL の `for_share_clause` を差し込み点の片方だけから外す | T-200 | **T-200** | — |
| P-11 | cli の要求の query から `for_share` を落とす | T-201 | **T-201** | — |
| P-12 | `+page.svelte` の `onToggleForShare=…` を消す | T-202（+`T-15`） | **T-202（+`T-15`）** | — |
| P-13 | `historyManagerState` の `params.set` 1 か所だけを消す | T-203（+`T-15`） | **T-203（+`T-15`）** | — |
| P-14 | 宣言から `CHANGED_SCHEMAS["HistoryItem"]` の `for_share` を外す | T-204 | **T-204** | — |
| P-15 | 宣言していない query 引数を `GET /api/history` へ 1 つ足す | T-204（+記録 1 本） | **T-204（+記録 1 本）** | — |
| P-16 | `EXPECTED_ROUTE_COUNT` を 95 に戻す | T-205 | **T-205** | — |
| P-17 | `_row_to_dict` の `bool()` を外して生の整数を載せる | T-191 | **T-191** | — |

### 4-1. P-1 で T-200 も赤くなると予測する理由（**契約との唯一の差**）

**T-200 は 2 つの経路（ORM と生 SQL）が同じ集合を返すことを主張する。**
生 SQL の経路を旗の節が通るためには、**母集団に「他人の・旗の立った作品」が要る**
（自分の作品なら所有者の枝だけで見え、旗の節は判別力を持たない）。
**その母集団のもとでは、P-1（ORM 側の旗の節を消す）は ORM の返す集合を縮めるので、
2 経路が食い違って T-200 も赤くなる。**
**P-1 で T-200 が緑になる書き方は、P-2 で T-200 が緑になる書き方でもある** ——
つまり契約 §3 の P-1 と P-2 の予測は同時には満たせない。**判別力の高いほう（両方赤）を選ぶ。**

### 4-2. 合計の予測

- **17 本の摂動で、延べ 23 の T が赤くなる**（契約の予測は 22。差は 4-1 の 1 件）
- **加えて web を触る 2 本（P-12・P-13）に `T-15` が +1 ずつ = 延べ 2**
- **schema を動かす摂動（P-15）に記録 `test_api_surface.py::test_api_surface_is_unchanged` が 1 本**
- **番人 ④ `test_the_groups_decide_what_you_may_do.py` は、どの摂動でも赤くならない**（契約 §0-C。
  `HistoryItem` は凍結 78 名に無い）。**これは空振りではない**

### 4-3. 摂動が空振りしうる既知の罠（着手前に織り込む）

- **P-17 は `bool()` を外すだけでは HTTP 応答では測れない** ——
  `response_model=HistoryItem` の `for_share: bool` が `1` を `True` へ強制する
  （「`response_model` は消した鍵を戻す」と同じ型）。
  **したがって T-191 は `db.list_items` が返す dict の型を測る**（`_row_to_dict` が `bool()` を書く位置）
- **摂動を当てるたびにビルドの成否を見る**（`^e: ` の検出。0 件なら「赤くなった」ではなく結果なし）
- **戻したら値を読む**（古い `pyc` が残る）

---

## 5. 満点との差の予測（実装後）

- **server**: 3401 → **3401 + 新設テストの本数**。新設は `test_a_work_says_which_group_may_read_it.py`（T-190〜T-200）
- **cli**: 235 → **235 + 1**（T-201）
- **web**: 446 → **446 + T-203 の新設ぶん**。`T-105` の 1 本は裏返すので本数は増えない
- **`npm run check`**: **0 ERRORS / 2 WARNINGS のまま**（既知 2 件以外を増やさない）
- **`lint:i18n`**: 英語の文字列が **1,076 → 1,076 + 足したラベルのぶん**、warnings/errors は **0 のまま**
