# 着手前の凍結: 作品を焼いているあいだも、サーバーは他の要求に答え続ける

**契約**: `no-git-sync/fable5/claude_code/tasks/stock/the-server-keeps-answering-while-a-work-is-baked.md`（台帳 **I-284**）
**実装セッション**: Claude Code / **Opus 5（1M context）**
**枝**: `feat/the-server-keeps-answering-while-a-work-is-baked` ／ **起点**: `3f56b7c2`（`git merge-base HEAD main` で実測・**0 commit**）
**作業場**: `/Users/oikawas/projects/ddl-server-render`

**この文書はコードを 1 行も書く前に commit する。** あとから書いた数字は、測っていない数字である。

---

## 1. 着手前の満点（**この枝の先端 `3f56b7c2` で自分で実測**）

| 面 | 実測 | 契約 §0 の記載 | 一致 |
|---|---|---|---|
| `make test-server` | **3413 passed / 31 skipped**（968.84 秒） | 3,413 passed / 31 skipped | **✔** |

skip の 31 件の内訳も契約と同じ形である（NIM 未設定 30 件 = `test_composer.py:107` 15・`test_interpreter.py:87` 4・
`test_interpreter.py:93` 11、`cairosvg` 未導入 1 件 = `test_rasterizer.py:67`）。

**契約は満点を「main の checkout で測った」と断っている。**本セッションは**同じ commit の別の作業ツリー**で測り直した
（`server/.venv` が別・`__pycache__` が別）。

**⚠ 測定環境の申告** —— 10:36 に始めたこの全走の 2 分後、**別のセッション（[I-191]・作業場
`ddl-server-work`）が同じ Mac で `make test-server` を始めた**。8 コアを 2 本の全走が分け合っている。
**pass / skip の数は変わらないが、秒は伸びる。**したがって**本文書の 968.84 秒を契約の 581.03 秒と比べてはならない**
（1.67 倍の差は木ではなく機械の混み具合である）。
**B-1 の探り針（時間を測るもの）は、あちらが終わってから回す。**

`make test-cli` と web の 3 面は測っていない。**本契約は `cli/` にも `web/` にも 1 バイトも触らないためである**
（触らなかったことは受け入れ側が `git diff --name-only` で確かめられる）。

---

## 2. 契約 §0-B・§2 が名指す行番号の突き合わせ（`3f56b7c2`）

**名指しされた 20 点すべてが実物と一致した。食い違いは 0 件。**

| ファイル | 点 |
|---|---|
| `server/src/inku_server/api_core/thumbnails.py` | 63 `_run_thumbnail_build` / 79 `submit_thumbnail_build` / 196 `_offer` / 216 `_store_result` / 243 `_rebuild_worker` / 268 `get_context` / 269 `ProcessPoolExecutor` |
| `server/src/inku_server/api_core/state.py` | 39 `_THUMB_WORKERS` / 45 `_thumb_executor` / 48 `_thumb_slots` / 141 `_increment_thumb_stat` |
| `server/src/inku_server/api.py` | 54 `_lifespan` |
| `server/tests/conftest.py` | 34 `pytest_sessionfinish` / 45 `rebuild_in_process` / 69 `ProcessPoolExecutor` |
| `server/tests/test_the_rebuild_survives_one_bad_work.py` | 147 `test_the_rasterizing_leaves_this_process_and_the_writing_does_not` |
| `server/tests/test_the_thumbnail_is_an_image_not_the_drawing.py` | 204 `slow_bake` |
| `server/src/inku_server/api_core/rendering.py` | 649 `_submit_thumbnail_build` |
| `shared/src/inku_analysis/rasterizer.py` | 121 `should_fold` |
| `server/src/inku_server/renderer.py` | 378 `margin` |

### 2-1. `submit_thumbnail_build` の呼び出し元（**契約 §6 が数え直しを求めている**）

**製品コードの呼び出しは 1 か所**（`server/src/inku_server/api_core/rendering.py:649`）。
**発行側の「1 か所」と一致する。**

リポジトリ全体（`.venv` を除く `*.py` `*.md` `*.ts` `*.svelte` `*.kt`）で名前が現れるのは **3 行だけ**である:

| 行 | 種類 |
|---|---|
| `server/src/inku_server/api_core/rendering.py:31` | import の別名（`as _submit_thumbnail_build`） |
| `server/src/inku_server/api_core/rendering.py:649` | **呼び出し（1 か所）** |
| `server/src/inku_server/api_core/thumbnails.py:79` | 定義そのもの |

**試験からの呼び出しは 0 件である** —— つまり**この入口を通る受入は、いま 1 本も無い。**

### 2-2. §0-D の衝突予測を渡す周として測り直した

| 契約 | 起点からの変更パス数 | `server/tests/conftest.py` を触るか |
|---|---|---|
| `a-work-says-which-group-may-read-it.md`（[I-191]・走行中・`cbee1bd2`） | **24** | **触らない（0 件）** |

**契約 §0-D が唯一警戒していた点は、2026-08-17 10:40 時点では現実になっていない。**
交わるパスは 0 件である（あちらの 24 パスに `thumbnails.py` `state.py` `api.py` `conftest.py` は 1 つも無い）。

---

## 3. 発行時の契約に無かった判断（**着手前に決めて、ここで凍らせる**）

### 3-1. T-220 は**自己校正**で据える（秒でも絶対回数でも据えない）

契約は「相方が回れた回数が、同じ長さの純 Python のときと同じ桁である」とだけ書き、
起点の実測（焼き付け 9.00 秒で **486 回**・純 Python 9.51 秒で **32,674 回**）を添えている。
**その 2 つの数はこの Mac のこの日の数であって、CI でも別の周でも再現しない。**

**据え方**: 1 本の検査の中で 2 つの窓を測る ——
**① 子プロセスで 1 枚焼いているあいだ**に相方（テストの本体スレッド）が回った回数、
**② 何も走っていない同じ長さの窓**で同じループが回った回数。
**① ≥ ② / 10 を主張する。**

**判別力**: 起点の比は **486 / 32,674 = 1/67** なので、P-1（スレッド内 `bake` へ戻す）は 1/10 の閾値を必ず割る。

### 3-2. `_lifespan` の畳みは `cancel_futures` を**使わない**

`concurrent.futures.CancelledError` は Python 3.8 以降 `asyncio.CancelledError` の別名で、**`BaseException` 直下**である。
`_store_result`（**再構築と共有の関数**）の `except Exception` はこれを捕らえない。
`cancel_futures=True` で畳むと、待っている保存側のスレッドへ `CancelledError` が抜ける。
**共有の関数を触らずに済ませるため、`shutdown(wait=False)` で畳む**（投げ済みの焼き付けは終わってから子が落ちる）。
**畳んだあとに再生成しない旗を 1 つ持つ** —— 持たないと、停止後に届いた保存が段 3 の作り直しで子を蘇らせる。

### 3-3. T-217 は「親が書いた」だけでは据えない（**契約の P-1 の予測を満たすため**）

契約 §4 は **P-1（スレッド内 `bake` へ戻す）が T-217 を赤くする**と予測している。
しかし T-217 を「`put_thumb` がこの pid で呼ばれた」だけで据えると、**スレッド内 `bake` でも親が書くので緑のままになる。**

**据え方**: 手本の `test_the_rasterizing_leaves_this_process_and_the_writing_does_not` が
1 本で 2 つ主張しているのに倣い、**「pool が実際に焼いて返した結果を、この pid が書いた」を主張する。**
P-1 では pool が 1 度も使われないので赤くなる。

### 3-4. 段 5 の既定からの抜け道は**マーカー**で作る

autouse の `bake_in_process` は**既定で全部の検査に効く**。
**本当に子プロセスへ出るのを見る 3 本（T-216・T-217・T-220）だけが `@pytest.mark.child_bake_pool` で抜ける。**
`rebuild_in_process`（opt-in）はそのまま残す —— **autouse を再構築にも効かせると、
手本の T-R3 が `real_pool = thumbnails.ProcessPoolExecutor` で掴むものが差し替え後の値になり、あの検査が壊れる。**

### 3-5. 統計は 1 作品につき 1 件のまま

段 3 は「作り直しても駄目なら `failed` を 1 つ数えて戻る」と言う。
既存の `_run_thumbnail_build` は `completed` / `unavailable` を 1 件数える。
**両方を数えると 1 作品で 2 件になる。**したがって焼き付けの結果を
`"completed"` / `"unavailable"` / `"failed"` のどれか 1 つに畳んでから 1 度だけ数える。**新しい統計は足さない。**

---

## 4. 新しく置く受入と、その置き場

| 番号 | 置き場 | 名前 |
|---|---|---|
| T-215 | **新設** `server/tests/test_the_server_keeps_answering_while_a_work_is_baked.py` | 保存した作品にサムネイルが付く（往復） |
| T-216 | 同上（`child_bake_pool`） | 焼き付けがこのプロセスを出る |
| T-217 | 同上（`child_bake_pool`） | 書き込みは親に残る |
| T-218 | 同上 | 壊れた pool から回復する |
| T-219 | **既存を裏返す** `test_the_thumbnail_is_an_image_not_the_drawing.py:195` | 保存は焼き付けを待たない（**遅い焼き付けを実際に作って**） |
| T-220 | 新設（`child_bake_pool`） | 焼いているあいだ、他のスレッドが進む |
| T-221 | 新設 | 止めると子も止まる |
| T-222 | 新設 | 試験の既定が同じプロセスで焼く |
| T-223 | **pytest ではない** | `server/scripts/check_frozen_corpora.py` がバイト一致 |

**新設は 7 本、既存の裏返しが 1 本、pytest でないものが 1 本。**

---

## 5. 摂動の予測（**9 本・実装前に凍結**）

**予測の読み方**: 「赤くなる T」は本契約が新設・裏返しする受入だけを数える。
**当て方は全部 `no-git-sync/scripts/perturb.py` の 1 行置換**である（戻す 1 行を手で書かない）。

| P | 当て先（1 行） | **契約の予測** | **自分の予測（凍結）** | 差 |
|---|---|---|---|---|
| P-1 | `_run_thumbnail_build` の焼き付け 1 行 → `build_one(...)` | T-216・T-217・T-220 | **T-216・T-217・T-220** | — |
| P-2 | `_offer` の `pool.submit(svg_to_png, …)` → `pool.submit(build_one, …)` | T-216 | **T-216 ＋ 既存 T-R3** | **+T-R3** |
| P-3 | `_store_result` を呼ぶ 1 行 → 子で `build_one` を呼んで待つ | T-217 | **T-217** | — |
| P-4 | 段 3 の作り直しの 1 行 → `return None` | T-218 | **T-218** | — |
| P-5 | `_bake_pool = None` → import 時に pool を作る | T-216・T-222 | **T-216・T-217・T-222** | **+T-217** |
| P-6 | `_lifespan` の `shutdown_bake_pool()` → `pass` | T-221 | **T-221** | — |
| P-7 | conftest の autouse の差し替え 1 行 → `pass` | T-219・T-222 | **T-219・T-222** | — |
| P-8 | `renderer.py:378` の `margin` を 1 動かす | T-223 | **T-223（＋描画系 pytest の道連れ多数）** | — |
| P-9 | `submit_thumbnail_build` の submit 行 → 投げずにスロットを返す | T-215 | **T-215・T-216・T-217・T-219・T-220・T-222** | **+5** |

**延べ**: 契約の予測 **13** ／ **自分の予測 19（新設 T のみ）＋ 既存 T-R3 が 1**。

### 5-1. P-5 で T-217 も赤くなると予測する理由

T-216 も T-217 も、**保存の経路が `thumbnails.ProcessPoolExecutor` を「呼ばれたときに」引く**ことに乗っている
（記録用の subclass を差し替えてから保存を起こし、何が構築されて何が投げられたかを見る）。
**import 時に pool ができていると、差し替えより先に本物ができているので、構築も submit も観測できない。**
T-216 は「構築されたクラスが 1 つも記録されない」で赤くなり、
**T-217 は「pool が焼いた結果を書いた」が観測できないので同じ理由で赤くなる**（→ 3-3）。

### 5-2. P-9 で 6 本が赤くなると予測する理由（**契約との最大の差**）

契約は P-9 を T-215 だけの摂動として置いている。
**しかし T-216・T-217・T-220・T-222 は、いずれも製品の入口 `submit_thumbnail_build` を通して焼き付けを起こす。**
**投げるのをやめれば、焼き付けそのものが 1 度も起きないので、これら全部が赤くなる。**
T-219 も「遅い焼き付けが実際に起きた」を主張するので赤くなる（→ 4 の裏返し）。

**⚠ これは P-9 の判別力が高いという意味ではなく、逆である** ——
**P-9 は「入口を殺す」摂動なので、入口の下にある受入を全部道連れにする。**
**P-9 が T-215 だけを赤くする書き方は、T-216〜T-222 が入口を通っていない書き方であり、
そちらのほうが弱い**（契約 §2 段 2 が「呼び出し元は 1 か所」と言う、その 1 か所を通らない受入になる）。
**判別力の高いほう（入口を通す）を選ぶ。**

### 5-3. 空振りしうる既知の罠（着手前に織り込む）

- **摂動を当てるたびにビルドの成否を見る**（`^e: ` の検出。0 件なら「赤くなった」ではなく**結果なし**）
- **戻したら値を読む**（`PYTHONDONTWRITEBYTECODE=1` は `make` が持つが、直接 pytest を叩くと古い `pyc` が残る）
- **P-8 は描画を変える唯一の摂動である。**当てる前に commit する（生成物は摂動より長生きする）
- **P-2 は `_offer` を壊す** —— あの関数は再構築と保存の両方が使う。**再構築側の T-R3 が道連れで赤くなるのは
  空振りではなく、共有していることの証拠である**

---

## 6. 満点との差の予測（実装後）

- **server**: 起点の満点 **+ 7**（新設 7 本。T-219 は既存の裏返しなので本数は増えない）
- **cli / web**: **変わらない**（1 バイトも触らない）
- **`check_frozen_corpora.py`**: **差分 0 件のまま**（render も ddl も）
- **試験一式の所要**: **伸びない**（段 5 の autouse が既定で同じプロセスに留める）。
  **⚠ ただし `child_bake_pool` の 3 本は本物の spawn を起こす。**その 3 本ぶんの spawn の実費は伸びる ——
  **伸びた秒は報告に書く**
