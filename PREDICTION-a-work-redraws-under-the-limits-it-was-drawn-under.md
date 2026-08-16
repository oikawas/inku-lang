# 予測（着手前に凍結）: 作品は、それが描かれた上限で描き直される

**書いた人**: 実装セッション（Claude Code / Opus 5, 1M context）／**2026-08-16**
**契約**: `no-git-sync/fable5/claude_code/tasks/stock/a-work-redraws-under-the-limits-it-was-drawn-under.md`
**枝** `feat/a-work-redraws-under-the-limits-it-was-drawn-under` ／ **この commit の親** `d8d2ac0a`
**台帳** I-154

> **⚠ この文書はコードを 1 行も書く前に commit する**（実行規約 §2-8）。
> **凍らせずに後から書いた数字は、測っていない数字として扱う。**
> **マージ後に `no-git-sync/` へ移す**（公開ツリーへ残さない）。

---

## 1. 満点（**着手前に、この作業場・枝の先端 `d8d2ac0a` で自分が測った**）

| 面 | 値 | 所要 |
|---|---|---|
| `make test-server` | **3271 passed / 31 skipped / 0 failed** | 608.05s |
| `make test-cli` | **227 passed / 0 failed** | 10.39s |
| `make test-web` | **375 pass / 0 fail / 0 skipped**（`ℹ tests 375`） | 5.09s |

**契約 §0-B が `98bed25f` の記録から引いた参考値「3,271 passed / 31 skipped」と一致した**（食い違い 0）。

server の skip 31 の内訳は本契約と関係が無い ——
`test_composer.py:107`（15）・`test_interpreter.py:87`（4）・`:93`（11）が
「NVIDIA NIM test backend is not configured」、`test_rasterizer.py:67`（1）が `cairosvg` 不在。

---

## 2. 起点で確かめた §0-B（**食い違い 0 件**）

`no-git-sync/scripts/contract_report.py` を起点 `d8d2ac0a` で回した:

```
引用 111 か所（重複を除いて 83 か所）/ ファイル 22 本を、起点と 1 行ずつ突き合わせた
うち 34 か所は契約が記号名を書いているので、その行に在るかも見た
ずれ 0 —— 起点から動いていないので、行番号は引き直さなくてよい
```

**契約 §0-B の行番号・記号名は 1 か所も動いていない。**

### 2-1. 発行側の断定と食い違った点（**3 件・実測**）

- **① 動くスキーマは 5 つではなく 6 つ。** §0-B は「本契約が触る 5 つのスキーマ」と述べるが、
  **`ComposeResponse` も `unchanged_schema_names`（78 件）に入っている**（実測）。
  §1-21 の列挙は 6 つなので、**実施は 6 つで行う**。
  `PaintRequest` `RenderSvgRequest` `RenderScoreRequest` `PaintResponse` `ComposeResponse` `RenderScoreResponse`
  の 6 つ全部が `unchanged_schema_names` に在ることを `python3` で数えた
- **② 段 6-22 が名指す `_CHANGED_SCHEMAS` は、本契約が触るスキーマを 1 つも見ていない。**
  `server/tests/test_the_groups_decide_what_you_may_do.py:179` の `_CHANGED_SCHEMAS` は
  **`UserAccountItem` `UserAccountCreateBody` `UserAccountUpdateBody` の 3 つだけ**で、本契約は触らない。
  本契約の 6 スキーマを見ているのは **`:226` の `declared_additions`** であり、
  **これは既に「宣言した鍵だけを取り除いてから digest する」機構を持っている**（上の 2 本と同じ形）。
  **したがって実施は `declared_additions` への宣言追加**で、`_CHANGED_SCHEMAS` は触らない。
  **段 6-22 の「added/removed の機構を足す」は、既に在るものを足せと言っている**
- **③ §0-B の「9 つの上限の読み取り箇所」の表のうち、`server/src/inku_server/counts.py:416` `:417`
  （`_count_follows_ddl_request`）は値を丸めも落としもしない**（`bool` を返す述語）。
  段 4 の痕はこの行ではなく、実際に `min` を取る／`continue` する行に置く。
  **9 つそれぞれの結線先は下の 4-1 に列挙して凍らせる**

---

## 3. 予測（**実装前に凍らせる**）

### 3-1. 満点はいくつになるか

| 面 | 予測 | 内訳 |
|---|---|---|
| server | **3289 passed / 31 skipped / 0 failed**（**+18**） | T-95 T-96 T-97 T-98 T-99 T-100 T-101 T-103 T-104 を各 1 本（**9 項目**）＋ **T-102 を 9 case の parametrize 1 関数（9 項目）** |
| cli | **229 passed**（**+2**） | T-105 と T-106 を 1 本ずつ |
| web | **376 pass / 0 fail**（**+1**） | 新設 `*.test.ts` に T-107 を 1 本 |

**既存テストの本数は動かさない。** T-108 は既存 3 本の**中身**を拡張するので項目数を増やさない。
**`server/tests/test_limits_are_settings.py` の `test_t7_every_coerce_site_passes_the_limits`
（`coerce_score(` が 5 か所・各所に `limits=limits`）は緑のまま**である ——
段 1 は `_effective_limits()` を `_limits_for_render()` へ差し替えるだけで、
`coerce_score` の呼び出し点も `limits=limits` の書き方も動かさない。

**⚠ 新設テストの項目数は書き方（parametrize の粒度）で変わる。**
**まとめ方を変えたら実測を報告に書き、この予測との差を明示する。**

### 3-2. `api-surface-baseline.json`

**digest は必ず動く。** 動くのは **6 スキーマの properties と digest だけ**を予測する:

| スキーマ | 足す鍵 |
|---|---|
| `PaintRequest` | `limits` |
| `RenderSvgRequest` | `limits` |
| `RenderScoreRequest` | `limits` |
| `PaintResponse` | `render_limits_source` |
| `ComposeResponse` | `render_limits_source` |
| `RenderScoreResponse` | `render_limits_source` |

**operation の増減は 0。ルートは 1 本も増やさない。**
**`/api/render-svg` のヘッダは OpenAPI の表面に出ないので、`params`/`responses` は動かない**（予測）。

### 3-3. 既定の設定で絵が動かないこと

**`render_engine` の版数は動かさない**（契約 §6）。段 4 は痕を `limit_notes` の**リストへ append するだけ**で、
**Score の `note` 欄へ埋める文字列は 1 バイトも変えない**。
`_enforce_hard_ceiling` が既に書いている 2 本も、**instruction へ埋める側は今の文字列のまま**にし、
**リストへ積む側にだけ `<上限名>: ` を前置する**。

**したがって参照コーパスは 0 件動く**と予測する。動いたら段 4 が既定を動かしている。

### 3-4. 摂動（**契約 §3 の 13 本 ＋ T-97 用に足す 1 本**）

**⚠ 数え方**: 「赤くなる本数」は **pytest / node:test の失敗**した**項目数**。
**焼き直せば緑になる記録（`test_api_surface_is_unchanged`）は別欄に分けて数える。**

| P | 何を壊すか | 赤くなると予測する T | 予測本数 | 上乗せ（道連れ） |
|---|---|---|---|---|
| **P-1** | `_limits_for_render` の `work` の枝が**今日の設定を返す**（出所の名前は動かさない） | T-95・T-98 | **2** | 0。**T-99 は緑**（欄は在り続ける） |
| **P-2** | `work_unrecorded` を `settings` と同じ文字列にする | T-96 | **1** | 0 |
| **P-3** | 応答モデルから `render_limits_source` を落とす | T-99・T-105・T-108 | **3 + 記録 1** | 記録 = `test_api_surface_is_unchanged`。T-108 は 3 本の宣言検査なので**実測は 3+1+1+1=6 になりうる**（下の注） |
| **P-4** | `/api/render-svg` のヘッダを落とす | T-99 | **1** | 0 |
| **P-5** | 出所の優先順位を逆にする（行 > 注文書） | T-100 | **1** | 0。**T-101 は緑**（作品を持たないので注文書の道のまま） |
| **P-6** | 段 3 の要素ごとの `min` を外す | T-101 | **1** | 0 |
| **P-7** | `represented_count_max` の痕だけ書かない | T-102（9 case のうち **1**） | **1** | 0 |
| **P-8** | 痕を常に 9 つ全部書く（効いていなくても） | T-103 | **1** | 0。**T-102 は緑**（名前は載るから） |
| **P-9** | `document_format.py` の予算を `DEFAULT_LIMITS` へ戻す | T-104 | **1** | 0 |
| **P-10** | CLI の allowlist から `render_limits_source` を落とす | T-105 | **1** | 0 |
| **P-11** | CLI の書き出しから `work_id` を落とす | T-106 | **1** | 0 |
| **P-12** | web の表示から痕を落とす | T-107 | **1 + 1** | **+1 = `T-15` メタゲート**（`the-navigation-buttons-agree-on-which-way-is-newer.test.ts:321` が自分以外の全 `*.test.ts` を子プロセスで回す） |
| **P-13** | 段 6 の宣言を「そのスキーマは何が動いてもよい」形にする | T-108 | **1** | 0 |
| **P-14**（**本セッションが足す**） | `work` が **無い**とき出所を `"work"` と名乗らせる | **T-97** | **1** | 0。**T-96 は緑**（`work_unrecorded` は動かない） |

**合計の予測: 摂動 14 本 / 赤 17 項目（記録 1 本は別勘定）。**

**⚠ P-3 の T-108 は 1 項目ではない。** T-108 は既存 3 本
（`test_the_acl_only_adds_to_the_api_surface.py`・`test_the_card_only_adds_one_route.py`・
`test_the_groups_decide_what_you_may_do.py`）の拡張なので、
**鍵を落とす摂動は 3 本とも赤くする**。**P-3 の実測は 1（T-99）+ 1（T-105）+ 3（T-108）+ 1（記録）= 6 と予測する。**

**⚠ P-14 の理由**（契約 §3 末尾が要求した明示）: **P-1 は `work` の枝を落とすので `settings` の道が残る**。
T-97（`work_id` 無しの `/api/render-score` が出所 `settings`）に当たる摂動が発行日には無かった。
P-14 は `work is None` の枝の戻り値だけを差し替えるので、**T-97 だけを赤くする**。

### 3-5. コーパス再走の道連れ（**0 本と予測する**）

`test_every_reader_counts_the_same_way.py::test_t1_the_expand_and_coerce_corpora_are_byte_identical` と
`test_limits_are_settings.py::test_t12_frozen_corpus_is_unchanged_at_the_defaults` は
**生きた `coerce_score` で焼き直して突き合わせる**ので、coerce の**出力**が動く摂動には反応する。

**本契約の摂動 14 本は 1 本も coerce の出力を動かさない**と予測する ——
P-7 と P-8 は痕（`limit_notes` のリスト）だけを動かし、**Score のバイトを動かさない**（3-3 のとおり）。
**動いたら 3-3 の設計が守られていない徴候である。**

---

## 4. 実装の設計で凍らせること

### 4-1. 段 4 の痕の結線先（**9 つ・1 対 1**）

| 上限 | 痕を書く行（起点 `d8d2ac0a` の行番号） | いつ書くか |
|---|---|---|
| `max_instructions` | `coerce/normalize.py:737`（`_enforce_hard_ceiling`） | 命令数が上限を超えて切られたとき |
| `max_expanded_primitives` | `coerce/normalize.py:757`（同上）／ `:582`〜`:608`（`_with_total_density_budget`）／ `coerce/compose.py:2477` | 総量が上限を超えて丸められた／候補が落ちたとき |
| `max_expanded_per_instruction` | `coerce/normalize.py:229`（`_with_density_budget`）／ `:553`（`_with_per_instruction_density_budget`）／ `coerce/compose.py:2450` | 1 命令の本数が上限を超えたとき |
| `literal_count_threshold` | `coerce/normalize.py:518`（`_budgeted_count`）／ `coerce/compose.py:2424`（`_stated_count_fidelity_band`） | 明示個数が閾値以上で帯へ移ったとき |
| `represented_count_max` | `coerce/normalize.py:498` `:501`（`_clustered_visual_count`） | 上側で丸められたとき |
| `represented_count_min` | `coerce/normalize.py:502`（同上） | 下側で持ち上げられたとき |
| `ddl_count_max` | `counts.py:96` `:157` | 記述の数詞が上限で丸められたとき（非 grid） |
| `ddl_count_max_grid` | `counts.py:96` `:157` | 同上（grid） |
| `schema_count_max` | `coerce/compose.py:1853` | grid の個数が上限で丸められたとき |

**⚠ `schema.py:362` の validator には書かない**（契約 §1-14。ContextVar を足さない）。

### 4-2. 痕の形

`list[str]`。**各行の先頭に上限の名前を置く** —— `represented_count_max: ...` の形。
**instruction の `note` 欄へ埋める文字列は今のまま**（3-3）。

### 4-3. 出所の 4 つの定数

`api_core/rendering.py` の `COLOR_SOURCE_SNAPSHOT`（`:374`）の隣に置く。
`"request"` / `"work"` / `"work_unrecorded"` / `"settings"`、ヘッダは `LIMITS_SOURCE_HEADER`。

---

## 5. 予測が外れる筋（先に書いておく）

- **新設テストの項目数**は parametrize の粒度で変わる。3-1 の +18 は
  「T-102 を 9 case の 1 関数・他を各 1 本」で数えた数である
- **T-99 を 4 経路の parametrize で置くと +3 になる**（4 項目）。その場合 server は +21 になる。
  **どちらで置いたかを報告に書く**
- **P-3 の実測が予測 6 を超える**なら、`render_limits_source` を読む番人が他にも在る。
  **赤くなったテスト名を読み、T-108 の 3 本と分けて数える**
- **段 4 の結線で参照コーパスが動いたら**、instruction の `note` 欄へ痕が漏れている。
  **3-3 の設計に戻す**（版数は動かさない）
- **`_render_score_svg` の戻り値を 3 つ組から 4 つ組にする**ので、呼び出し元を数え落とすと
  段 1 の時点で赤が出る。**呼び出し元は起点で 2 か所**
  （`routers/history.py:308`・`routers/render.py:1775`）と数えた
