# 予測（着手前に凍結）: 公開の一覧は、ログインに要るものだけを持つ

**書いた人**: 実装セッション（Claude Code / Opus 5, 1M context）／**2026-08-16**
**契約**: `no-git-sync/fable5/claude_code/tasks/stock/the-public-list-holds-only-what-login-needs.md`
**枝** `feat/the-public-list-holds-only-what-login-needs` ／ **この commit の親** `8b93bb9d`

> **⚠ この文書はコードを 1 行も書く前に commit する**（実行規約 §2-8）。
> **凍らせずに後から書いた数字は、測っていない数字として扱う。**
> **マージ後に `no-git-sync/` へ移す**（公開ツリーへ残さない）。

---

## 1. 満点（**着手前に、この作業場・枝の先端 `8b93bb9d` で自分が測った**）

| 面 | 値 | 所要 |
|---|---|---|
| `make test-server` | **3242 passed / 31 skipped / 0 failed** | 904.76s |
| `make test-cli` | **225 passed / 0 failed** | 43.87s |
| `make test-web` | **373 pass / 0 fail / 0 skipped**（`ℹ tests 373`） | 9.6s |

server の skip 31 の内訳は NVIDIA NIM 未設定と `cairosvg` 不在で、本契約と関係が無い。

---

## 2. 起点で確かめた §0-B（**食い違い 0 件**）

契約 §0-B と冒頭の表が名指す **44 か所を 1 行ずつ突き合わせ、全部が現物と一致した**。
`public.py:28` `:102` `:216`・`auth.py:10` `:14` `:15` `:62`・`api.py:245`・
`test_route_authorization.py:21` `:45`（`EXPECTED_ROUTE_COUNT = 95`・`len(PUBLIC) == 6`）・
`test_the_card_only_adds_one_route.py:48` `:87`・`test_the_acl_only_adds_to_the_api_surface.py:137`（宣言 1 件）・
`test_api.py:111` `:175`・`test_the_work_remembers_its_own_colors.py:649`・
`cli.py:385`（`auth=False`）`:2204` `:3611` `:3626` `:3776`・
`+page.svelte:1803` `:2579` `:6019` `:6479` `:6520`・`AuthPanel.svelte:15`（props 8 つ・カタログもプロンプトも無い）・
`server-components.{ja.,}md:99`（6 path の手書き列挙・「合計82」）。
**`api-surface-baseline.json` の digest も `d5d312e12d7da3b5a118a06dda5562edf7f2f9de8a134c3ebdc9a0c3c54fb287` のまま。**

`login()`（`+page.svelte:2579`）の後処理の `Promise.all` は **9 本**で、
**`loadColorCatalogs()` も `fetchPrompts()` も入っていない**ことを確認した（契約の断定どおり）。

---

## 3. 予測（**実装前に凍らせる**）

### 3-1. 満点はいくつになるか

| 面 | 予測 | 内訳 |
|---|---|---|
| server | **3252 passed / 31 skipped / 0 failed**（**+10**） | 新設ファイルに **9 項目**（T-80 = 3 ルート × 2 本 = 6、T-82 = 3 ルート × 1 本 = 3）、`test_route_authorization.py` に T-89 を **1 本** |
| cli | **226 passed**（**+1**） | T-86 を 1 本 |
| web | **375 pass**（**+2**） | 新設 `*.test.ts` に T-87 と T-88 を 1 本ずつ |

**既存テストの本数は動かない。** 段 2・段 3・段 4 はいずれも既存テストの中身を書き換えるだけで、
関数を足さない（T-79 は既存 `test_every_route_is_guarded_or_listed_public` の
`unguarded == PUBLIC` が `PUBLIC` の縮小によってそのまま主張になる。T-81 と T-83 は
`test_the_card_only_adds_one_route.py` の既存 2 関数の中で満たされる。T-84・T-85 も同じ）。

**`EXPECTED_ROUTE_COUNT = 95` は動かさない**（ルートを 1 本も増やさない）。

### 3-2. `api-surface-baseline.json`

**digest は必ず動く。** 動く行は **3 operation の `params` と digest の 4 か所だけ**を予測する
（`GET /api/prompts`・`GET /api/color-catalogs`・`GET /api/auth/config` が
`cookie:inku_session:opt` と `header:authorization:opt` を得る）。
**schema は 1 つも動かない。operation の増減も 0。**

### 3-3. 摂動（**契約 §3 の予測を、実装前にそのまま引き受ける**）

| P | 契約が赤くなると言う T | 自分の上乗せ予測 |
|---|---|---|
| P-1 | T-79・T-80・T-82・T-83・T-84（+ 記録 1 本） | 記録 = `test_api_surface_is_unchanged` |
| P-2 | T-79・T-80・T-82・T-83・T-84（+ 記録 1 本）・**T-85 は緑** | 同上 |
| P-3 | T-79・T-80・T-82・T-83・T-84（+ 記録 1 本） | 同上 |
| P-4 | **T-83・T-84 のみ**（+ 記録 1 本）・T-79/80/81/82 は緑 | 宣言の機構が白紙委任でないことを測る |
| P-5 | T-87 | |
| P-6 | T-87 | |
| P-7 | T-86 | |
| P-8 | T-89 | |
| P-9 | T-89 | |
| P-10 | T-87（**緑のままなら領域を切り出せていない**） | |

**⚠ P-1〜P-4 で赤くなる「記録 1 本」は受入 T に数えない**（焼き直した瞬間に緑になるため）。
**⚠ P-1〜P-3 は `test_public_list_names_only_real_routes` を赤くしない**（`PUBLIC ⊆ paths` は
公開へ戻しても成り立つ）。**赤くなる本数を数えるとき、この 1 本を数えに入れない。**

---

## 4. 予測が外れる筋（先に書いておく）

- **T-79 が P-4 で赤くならない**のは、query 引数を足してもガードの集合が動かないため。これは意図した鈍さである
- **T-85 が P-2 で緑のまま**なのは、段 3 で認証つきの呼び方へ変えた後だから。
  認可を外しても認証つきの要求は 200 を返す。**これは契約が明示している**
- **新設ファイルの項目数は、書き方（parametrize の粒度）で変わる。**
  上の +10 は「3 ルートを parametrize する」前提の数であり、**まとめ方を変えたら本数も変わる。**
  **その場合は実測を報告に書き、この予測との差を明示する**
