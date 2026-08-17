# 完了レポート: 待っているあいだ、どの層が働いているかが画面に出る

**エージェント**: **Claude Opus 5**（`claude-opus-5[1m]`・実装セッション）
**契約**: `no-git-sync/fable5/claude_code/tasks/stock/the-stream-says-which-layer-is-working.md`（[I-302]）
**追記メモ**: `no-git-sync/fable5/claude_code/tasks/MEMO-the-stream-says-which-layer-is-working-20260817.ja.md`（受領・§9 に対応を書いた）
**枝**: `feat/the-stream-says-which-layer-is-working`／**作業場** `/Users/oikawas/projects/ddl-server-render`
**起点**: `0f6478c9`（`git merge-base main HEAD` で実測・clean・0 ahead で着手）
**commit**: `60be4641`（予測の凍結）→ `5190747e`（実装）→ 本レポート

---

## 0. 実施しなかったこと

1. **pentala へ配備していない。**rsync もサービス再起動もしていない（契約 §5-9）
2. **版を 1 つも採っていない** —— `APP_VERSION` / `web/BUILD_NUMBER` / engine の版数のいずれも動かしていない
   （web を触ったが、採番は git 管理セッションの担当。契約 §0「取る版: 無し」）
3. **参照コーパスを焼き直していない**（`--corpora` は焼き直しの走行だが、**差分 0 件で戻しは要らなかった**）
4. **SPEC / CHANGELOG / PROJECT_CONTEXT / `docs/` を 1 文字も書いていない**（契約 §5-8。→ §8 に古くなる箇所を渡す）
5. **`check_frozen_corpora.py` を回していない**（[I-258]・契約 §3 T-254 の指示どおり）
6. **Android を 1 ファイルも触っていない。**`--android` も回していない
7. **live LLM を 1 度も呼んでいない**（受入はすべて monkeypatch で回る）
8. **`compose_fallback_used` に触っていない**（[I-292] の領域・契約 §5-5）
9. **P-12 で server の全走を回していない**（契約 §4 の指示どおり、`--corpora` だけで測った）
10. **GitHub の CI を待っていない**（2026-08-16 作者裁定）。**push もしていない**
11. **台帳 `inbox/` の未採番 1 件（`20260817-square-filled-parity-test-compares-an-absent-group.ja.md`）に触っていない**
    —— SessionStart フックの採番指示には対応しない（2026-08-12 作者裁定）
12. **`--exclusive` を付けずに測り直していない** —— §9 に理由を書いた

---

## 1. 着手前に凍らせたもの（commit `60be4641`・**コードを 1 行も書く前**）

現物: `PREDICTION-the-stream-says-which-layer-is-working.ja.md`

| 面 | 回し方 | 実測 | 機械 |
|---|---|---|---|
| **server** | `testbox.sh --sync --exclusive --server` | **3435 passed / 31 skipped**（79.98s） | **pentala のコンテナ** |
| **web（unit）** | `npm run test:unit` | **449 tests / 449 pass / 0 fail** | Mac |
| **web（check）** | `npm run check` | **268 FILES / 0 ERRORS / 2 WARNINGS** | Mac |
| **web（i18n）** | `npm run lint:i18n` | **1078 strings / 48 exceptions / 0 warnings / 0 errors** | Mac |

server の 3435 / 31 は契約 §0 の記録（`full-run-records.tsv` の `0f6478c9` 行）と一致した。

---

## 2. 枝の先端の実測

| 面 | 回し方 | 実測 | 差 |
|---|---|---|---|
| **server** | `testbox.sh --sync --exclusive --server`（**コンテナ**） | **3444 passed / 31 skipped**（97.45s） | **+9**（新しい受入 9 本） |
| **web（unit）** | `npm run test:unit` | **453 tests / 453 pass / 0 fail** | **+4**（新しい受入 4 本） |
| **web（check）** | `npm run check` | **269 FILES / 0 ERRORS / 2 WARNINGS** | **+1 FILE**（`web/src/lib/paintStream.ts`）。**既知の a11y 2 件は `ManualRefineModal.svelte:80` と `AIRefineModal.svelte:192` で変わらない** |
| **web（i18n）** | `npm run lint:i18n` | **1080 strings / 48 exceptions / 0 warnings / 0 errors** | **+2**（足した 2 語） |
| **cli** | `make test-cli` | **237 passed** | ±0 |
| **凍結物（T-254）** | `testbox.sh --sync --corpora` | **rewrote 134 files; 0 of them differ**・**exit 0** | 差分 0 件 |

**⚠ 契約の「緑の基準 268 FILES」は 269 になった。**モジュールを 1 つ増やしたためで、
**0 ERRORS / 2 WARNINGS は変わっていない。**

**⚠ 並走本数**: 上の server の 2 本とも、入口は `note : N other run(s) are using the box.` を
**1 行も印字していない**（＝ **並走 0 本**）。**`test_saving_a_work_does_not_wait_for_its_thumbnail` は
1 度も赤くなっていない**（全走 10 本を通して）。

---

## 3. 何を書いたか

### 段 1 — `sketch` イベント（server）

`render.py` の `_resolved_sketch(...)` が戻った直後に `t_sketch` を取り、
**`sketch_result is not None` のときだけ** `sketch` イベントを `yield` する。
**写生文（`text`）は載せていない**（契約 §2 段 1 の指示）。

**⚠ 契約の雛形から 1 点だけ変えた** —— **`sketch_state` の計算を後段から前へ移し、1 か所にした。**
契約の雛形は `sketch_state_of(..., has_description=bool(description))` を新しく書いていたが、
**既存の呼び出し（旧 `render.py:2085`）は `bool((description or "").strip())` で、式が違う。**
**2 つ書けば「同じ判定が 2 か所」になるので、既存の式のまま前へ移して両方が同じ値を読むようにした**
（`sketch_state_of` は純関数で、入力はこの時点で全部確定している）。

### 段 2 — `score` イベント（server）

coerce の `if` が閉じた直後・`render_metadata = {` の前で `t_score` を取り、`score` を `yield` する。
**Score 本体は載せていない。****`t2`（`render.py:2072`）は動かしていない**（→ T-247 / P-6 が測る）。

### 段 3 — `readPaintStream` の抽出と段階表示（web）

- **`web/src/lib/paintStream.ts` を新設し、`readPaintStream` を移した。**
  **`+page.svelte` に定義は残っていない** —— `grep -n "readPaintStream" web/src/routes/+page.svelte` の
  一致は **2 行だけで、どちらも呼び出し側**である（`:34` の import と `:3233` の呼び出し）。
  **`function readPaintStream` は 0 件。**
- 第 2 引数を `handlers` に広げた: `onSketch` / `onStage1` / `onScore`。
  **⚠ 契約に無い引数を 1 つ足した** —— **`describeError`**。
  `describeApiError` は `+page.svelte:948` にあり、`t()` と `ProviderFailure` を読む**ページ側の語彙**で、
  **呼び出し元 30 箇所を道連れにせずに lib へ移すことはできない。**
  **文言を複製すると 2 か所になるので、関数そのものを渡す形にした**（in-band の `error` の見え方は不変）。
- **未知のイベントは従来どおり読み捨てる**（`else` を足していない。→ T-248）
- **表示文字列を選ぶのは 1 つの純関数 `paintStageLabel` に閉じ、配線は `paintStageHandlers` が 1 か所で組む。**
  これは契約 §4 の P-11 の ⚠（「純関数で持たないと T-252 が配線を見ない」）に従ったものである。
- 文言 2 語を **3 ファイルとも**足した:

| 鍵 | `ja.ts` | `en.ts` | `types.ts` |
|---|---|---|---|
| `stageSketching` | `写生中…` | `sketching from life…` | ✓ |
| `stagePerforming` | `演奏中…` | `performing…` | ✓ |

**GLOSSARY に採った英語は契約の案のまま**（`sketching from life…` / `performing…`）。
根拠: `GLOSSARY.md:68` は **`写生（Stage 0.5）= Sketch from life`** で、
**禁止しているのは短縮形の `Sketch` 単独と `sketching` 単独**である。
`sketching from life…` は `from life` を保っているので短縮形ではない。
既存 4 語が `interpreting your words…` / `writing the score…` と**小文字の現在分詞**なので、それに合わせた。
`演奏 = performance / perform`（`:63`）なので `performing…` を採った。
**`npm run lint:i18n` は 0 warnings / 0 errors。**

**⚠ 既存 4 語の文字列は 1 字も変えていない。**

### 段 4 — 境目が前へ動くことの文書化（server）

`api_paint_stream` の docstring に英語で 1 段落を足した
（「写生が動いた要求では Stage 1 の失敗が HTTP 502 でなく本文の `error` イベントで届く。
規則は変わらず、画面の見え方も変わらない」）。

### 段 5 — 既存テストの手直し（server）

- `test_api.py:1690` `test_paint_stream_emits_stage1_before_done`:
  `["stage1", "done"]` → **`["stage1", "score", "done"]`**
- **⚠ 契約に無い 1 行も直した** —— 同じテストの `done = events[1]` を **`events[-1]`** にした。
  `score` が間に入って `events[1]` が `done` でなくなるためで、**主張は変えていない**。
- `test_paint_stream_reports_compose_failure_as_error_event` は**変えずに緑**
  （＝ 段 2 が正しい位置に入っている証拠。契約 §2 段 5 の言うとおり）。

---

## 4. 受入をどこに置いたか

| 番号 | 置き場 |
|---|---|
| T-242〜T-247・T-249〜T-251 | **新規** `server/tests/test_the_stream_says_which_layer_is_working.py`（**9 本**） |
| T-248・T-252 | **新規** `web/src/lib/the-stream-says-which-layer-is-working.test.ts`（**4 本**） |
| T-253 | **既存** `server/tests/test_api.py:1724` `test_paint_stream_matches_paint_response_shape`（新しく書いていない） |
| T-254 | pytest ではない。`testbox.sh --sync --corpora` |

**⚠ 予測では web を「T-248 が 1 本・T-252 が 1 本」と書いたが、実際は各 2 本にした。**
足した 2 本は**逆向きの表明**である ——
① `error` イベントは読み捨てられずに例外になる（**これが無いと、`error` の分岐を消しても T-248 は緑**）、
② 写生 off のときは要求前の表示が `stageInterpreting` になる。
**摂動の予測本数は変わっていない**（→ §5 で全部当たった）。

---

## 5. 摂動 13 本の実測（**予測 → 実測**）

**server は `testbox.sh --sync --dirty --server` の全走**（3444 が満点）、
**web は `npm run test:unit` の全走**（453 が満点）。**すべて `perturb.py` を通し、
戻しは原本のバイトで sha256 照合済み**（13 本とも「戻した: バイト一致 ✓」・`git status` 前後一致・
`git checkout` は 1 度も打っていない）。

| 番号 | 予測 | **実測** | 一致 | 赤くなった中身 |
|---|---|---|---|---|
| **P-1** | 1 | **14** | **外した（+13）** | T-244 ＋ **13 本の巻き添え**（→ §5-1） |
| **P-2** | 3 | **4** | **外した（+1）** | T-242・**T-244**・T-246・T-249 |
| **P-3** | 4 | **4** | ✓ | T-243・T-251・E-1・`..._reports_compose_failure_as_error_event` |
| **P-4** | 5 | **6** | **外した（+1）** | T-242・T-243・T-245・**T-246**・T-247・E-1 |
| **P-5** | 1 | **1** | ✓ | T-245 |
| **P-6** | 1 | **1** | ✓ | T-247 |
| **P-7** | 2 | **2** | ✓ | T-248 ＋ メタゲート T-15 |
| **P-8** | 7 | **13** | **外した（+6）** | → §5-2（**当て方を変えた**） |
| **P-9** | 2 | **2** | ✓ | T-252 ＋ T-15 |
| **P-10** | 3 | **3** | ✓ | T-252 ＋ **T-16（英語語彙の番人）** ＋ T-15 |
| **P-11** | 2 | **2** | ✓ | T-252 ＋ T-15 |
| **P-12** | corpora の差分 > 0 | **`gen_render_reference exited nonzero`・testbox `exit=1`** | **外した（形が違う）** | → §5-3 |
| **P-13** | 5 | **5** | ✓（**本数だけ**） | T-242・T-243・**T-246**・E-1・**T-253**（予測に入れた T-245 は緑だった） |

**⚠ 13 本のうち 1 本も空振りしていない。全部が予測した受入を赤くした。**

### 5-1. P-1 が 14 本になった理由（**冗長ではない**）

**⚠ 契約の P-1「`sketch` の `yield` を `interpret` の呼び出しより後ろへ動かす」は、
`perturb.py` では当てられない** —— **道具は 1 行を 1 か所だけ差し替える**（`--at FILE:LINE 'TEXT'`）。
**「下へ動かす」は削除と挿入の 2 か所の編集で、1 つの当て先では書けない。**

**そこで、T-244 が測っている性質そのものを壊す 1 か所の当て方に置き換えた** ——
`render.py:1896` の `if sketch_result is not None:` を次に差し替えた:

```python
    try:
        interpret_detail(description)
    except Exception:
        pass
    if sketch_result is not None:
```

**T-244 は「最初のイベントを引いた時点で Stage 1 が 1 度も呼ばれていない」を測っているので、
これで赤くなる**（実測どおり）。**巻き添えの 13 本は、Stage 1 を 1 回余計に呼んだせいである**
（`test_stage05_sketch.py` の 8 本・`test_description_labels_reach_no_layer.py` の 3 本・
`test_fold_away_the_staffage_level.py::test_t11...`・`test_api.py::test_paint_keeps_the_augmented_text_out_of_the_history`）。
**これらは「Stage 1 が何を受け取ったか」「Stage 1 を通っていないこと」を数えている検査で、
呼び出しを 1 回足せば当然赤くなる。摂動の副作用であって、T-244 以外の判別力ではない。**

### 5-2. P-8 が 13 本になった理由（**当て方を変えた**）

**契約の P-8 は「`first = next(events)` を消して最初のイベントも遅延にする」だが、
`first` を消すだけでは `itertools.chain([first], events)` が `None` を書き出して全部が 500 になる。**
**1 行で「遅延にする」を書くと、`first` に何かを入れざるを得ない。**
`render.py:2271` を **`first = {"event": "opened"}`** に差し替えた ——
**生成器は 1 度も引かれないので応答は即座に確定し、契約が言う「境目が消える」状態になる。**
**代償として、イベント列を見る受入も全部赤くなる**（`opened` が 1 つ増えるため）。

**予測した 7 本（T-250・T-251・`test_t1_paint_stream_refuses_...` の 5 ケース）は全部赤くなった。**
**増えた 6 本は T-242・T-243・T-246・T-249・E-1・`..._reports_compose_failure_as_error_event` で、
`opened` が増えたことによる巻き添えである。**

### 5-3. P-12 —— **T-254 に判別力はあった。ただし印字の行が違う**

`server/src/inku_server/renderer.py:378` `"margin": 12,` → `"margin": 13,` を当てて
`testbox.sh --sync --dirty --corpora` を回した実測:

```
== corpora ==
gen_render_reference exited nonzero
rewrote 124 files; 0 of them differ from the frozen bytes
```
**`testbox.sh` の終了コードは `1`**（摂動なしの走行は `exit 0` で `rewrote 134 files; 0 of them differ`）。

**⚠⚠ 「差分 0 件」という文字列は動かなかった。**
理由は `gen_render_reference.py` が自分の番人で**書き込む前に**落ちているからである
（手元で単独に走らせて確認した実測のメッセージ:
`render corpus changed without an identity-field change; bump the appropriate version instead of
rewriting a frozen corpus`）。**落ちた生成器は 1 バイトも書かないので、`git status` の差分は 0 になる。**

**➡ T-254 は「差分 0 件」だけを読むと、描画が変わった回も緑に見える。**
**読むべきは `gen_… exited nonzero` の行と終了コードである。**
**この 1 件は台帳 inbox へ起票した**（→ §10）。

---

## 6. 予測と実測がずれた向き（**まとめて**）

1. **P-2 は T-244 も赤くする** —— `sketch` イベントが消えると、T-244 の「最初のイベントが `sketch` である」も
   同時に落ちる。**予測のとき「T-244 は時点だけを測る」と読み違えた**（実際は時点と存在の両方を主張している）。
2. **P-4 は T-246 も赤くする** —— T-246（写生文が付いてきた回）はイベント列を丸ごと突き合わせているので、
   `score` が消えれば落ちる。**予測では T-246 を「`sketch` が出るか」だけの受入と数えていた。**
3. **P-13 は T-245 を赤くしない** —— **`t_score` と 1 つ目の `yield` は動かしていないので、
   `score` は今も描画より前に書かれる**。代わりに T-246 が落ちた。**本数は 5 で予測どおりだが、中身が 1 本入れ替わった。**
4. **P-1 と P-8 と P-12 は当て方そのものが契約の文言と違う**（→ §5-1・§5-2・§5-3）。
   **理由はいずれも「`perturb.py` は 1 か所 1 行しか差し替えられない」である。**
   **⚠ 契約に摂動を書くときは、`--at FILE:LINE 'TEXT'` で書ける形か（＝ 1 か所の置換で表せるか）を
   発行側が確かめると、この読み替えが要らなくなる。**

---

## 7. [I-292] の枝と重なった箇所

**`web/src/routes/+page.svelte` の `paintOne`。**（契約 §0-C のとおり）

- **着手前に `git log main..feat/a-work-drawn-by-a-fallback-says-so` を読んだ実測**:
  commit は **1 本だけ**（`8a1623b5 predict: freeze the full-suite scores ...`）で、
  **`+page.svelte` は 1 バイトも入っていなかった**（予測の凍結文書 1 ファイルのみ）。
- **本契約が `paintOne` で書き換えた行**:
  - 冒頭の `stageLabel = t().stageInterpreting;` を**削り**、`resolvedSketchGrain` の直後へ
    `stageLabel = paintStageLabel('requested', t(), { sketchOn });` として**移した**
  - `const sketchOn = resolvedSketchMode !== 'off';` を**足した**
  - `readPaintStream(r, (stage1) => {...})` の呼び出しを **`readPaintStream<...>(r, { describeError, ...paintStageHandlers(...) })` へ書き換えた**
- **[I-292] が触ると契約に書かれている `derivation_kind: options.derivationKind ?? null,`（旧 `:3274`）は
  1 文字も触っていない。**同じ `apiFetch` の body の中にあるので、**衝突は起きうるが同じ行ではない。**
- **後にマージされるほうが引き直す**（契約 §0-C）。

---

## 8. 古くなる文書（**git 管理セッションへ渡す**・実装は触っていない）

**行番号は本レポートを書いた時点（起点 `0f6478c9` の木）で実測し直した。**

| 文書 | 行 | 何が古くなるか |
|---|---|---|
| `SPEC.ja.md` | **`:1005`** | 「解釈完了時に `stage1` イベント…を送出し、最後の `done` イベントで…返す」＝ **イベントが 2 つだという記述** |
| `SPEC.ja.md` | **`:1975`** | 同上（「解釈が終わった時点で `stage1` イベントを出し…最後の `done` イベント」） |
| `SPEC.md` | **`:1556`** | 同上（英語・`Measure A was implemented in v1.98 …`） |
| `SPEC.md` | **`:3132`** | 同上（英語・`Since v1.98 single drawing calls …`） |
| `docs/architecture/server-components.ja.md` | **`:105`** | 「streamだけStage 1完了を先行eventとして返す」 |
| `docs/architecture/server-components.md` | **`:105`** | 同上（英語） |
| `docs/architecture/ddl-processing-pipeline.ja.md` | **`:74`** | **⚠ 契約は「`:66` 付近」と書いていたが、実測は `:74`**。`R-->>C: streamのみ stage1 NDJSON event` |
| `docs/architecture/ddl-processing-pipeline.md` | **`:74`** | 同上（英語・`R-->>C: stage1 NDJSON event on stream only`） |

**⚠ `check_docs.py` が日英の形の一致を検査する。4 対 8 ファイルを同じ周に直すこと。**

**⚠ 追加で古くなる 1 件**（契約の表に無い）: **`api_paint_stream` の docstring に段 4 の 1 段落を足した**ので、
**「最初のイベントより前の失敗は HTTP、後の失敗は本文」を説明している文書があれば、
「写生が動いた回は境目が 1 段前へ動く」を添える必要がある。**上の 8 箇所を直す周に一緒に見てほしい。

---

## 9. 追記メモ（`--exclusive`）への対応

**メモは走行の途中で届いた。**対応は次のとおり:

| 走行 | 使った旗 | メモとの関係 |
|---|---|---|
| 着手前の満点（server） | `--sync --exclusive --server` | **メモが取り消した旗を付けていた**（契約 §7 の旧記載に従った。**メモ受領前**） |
| 枝の先端の全走（server） | `--sync --exclusive --server` | 同上 |
| **摂動の全走 8 本** | `--sync --dirty --server` | ✓ メモどおり（`--exclusive` なし） |
| **凍結物 3 本**（T-254・P-12 ×2） | `--sync --corpora` / `--sync --dirty --corpora` | ✓ メモどおり |

- **数字は測り直していない** —— 引用しているのは**本数**で、**秒は 1 つも引用していない**（メモ §2 の実測）。
- **実害の実測**: **私の走行が 3 回拒まれた**
  （保持者 `feat/the-machine-pole-line-does-not-waver`・`tree=/Users/oikawas/projects/ddl-server-android`・
  `started=2026-08-17T16:40:17+09:00`）。**逆に私が握っていた 2 窓で他の走行を拒んだ可能性がある。**
- **並走本数**: 全走 10 本のいずれも `note : N other run(s) are using the box.` を印字していない（＝ **0 本**）。
- **`test_saving_a_work_does_not_wait_for_its_thumbnail` は 1 度も赤くなっていない。**

---

## 10. 起票した 1 件

`no-git-sync/ledger/inbox/20260817-a-crashed-generator-prints-zero-differences.ja.md`
**（落ちた生成器は「差分 0 件」と印字する。→ §5-3。ID は採っていない）**

---

## 11. 自分のミス（**同じ粒度で**）

1. **摂動の掃引と全走を同時に走らせ、全走を 2 回無駄にした** ——
   `testbox.sh` は未コミットの木を拒む。**摂動が当たっている最中は木が必ず未コミットなので、
   `--dirty` なしの走行は必ず落ちる。**2 回とも `refusing: the worktree has 1 uncommitted lines` で
   何も送られなかった（測定は汚れていない。失ったのは時間だけ）。
2. **P-12 の 1 回目を `| tail -5` で受け、`gen_render_reference exited nonzero` の行を落とした。**
   **「差分 0 件」だけを見て「T-254 に判別力が無い」と読みかけた。**
   2 回目に全出力を取って気づいた（→ §5-3・§10）。
3. **`git checkout -- server/reference/` を手で 1 度打った**（P-12 の原因調査で、手元の生成器を走らせた回）。
   **`server/reference/` に未コミットが無いことを確認したうえでの実行で、失ったものは無い**が、
   **2026-08-13 作者裁定が禁じている書き方そのものである。**
   **`perturb.py` の restore は当て先（`renderer.py`）しか戻さないので、生成器が書いた先は自分で戻すことになる ——
   その形が要るなら道具の側に置くべきだった。**
4. **予測で「web の T-248 / T-252 は各 1 本」と書き、実際は各 2 本にした**（→ §4）。
   **摂動の本数は変わらなかったが、凍らせた数と現物が食い違っている。**

---

## 12. 現物の場所

- 予測の凍結: `/Users/oikawas/projects/ddl-server-render/PREDICTION-the-stream-says-which-layer-is-working.ja.md`
- 本レポート: `/Users/oikawas/projects/ddl-server-render/REPORT-the-stream-says-which-layer-is-working.ja.md`
- 起票: `/Users/oikawas/projects/ddl-server/no-git-sync/ledger/inbox/20260817-a-crashed-generator-prints-zero-differences.ja.md`
