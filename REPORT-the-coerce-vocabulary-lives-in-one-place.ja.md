# 完了レポート: coerce の語彙は 1 か所に在る（台帳 I-115）

- **エージェント**: Opus 5（`claude-opus-5[1m]`）／実装セッション
- **契約**: `no-git-sync/fable5/claude_code/tasks/stock/the-coerce-vocabulary-lives-in-one-place.md`
- **枝**: `feat/the-coerce-vocabulary-lives-in-one-place`／**起点 `e188850b`**（`git merge-base` で実測）
- **先端**: `ea203c00`／作業場 `/Users/oikawas/projects/ddl-server-render`
- **commit 3 本**: `0157fab7`（予測の凍結）・`53275281`（移設と番人）・`ea203c00`（T-287）

---

## 0. 実施しなかったこと

1. **`web` / `cli` / `android` を 1 ファイルも触っていない。**それらの試験も回していない（契約 §7）。
2. **pentala へ配備していない。**rsync もサービス再起動もしていない。
3. **`APP_VERSION` / `web/BUILD_NUMBER` / engine の版を 1 つも動かしていない。**
4. **SPEC / CHANGELOG / PROJECT_CONTEXT を書いていない。**
5. **語を 1 つも捨てていない・足していない**（T-282 / T-283 で測った）。**日英の対も揃えていない**（§0-B 2）。
6. **`full-run-records.tsv` の行を commit していない**（2026-08-17 作者裁定。走行は 6 回ぶん自動で入っている）。
7. **CI は待っていない**（2026-08-16 作者裁定）。
8. **正規表現に埋まった語彙 3 か所を移していない**（→ §5-2。marker の形に移せない）。
9. **宣言済みの語だけを持つ直書き 8 か所を移していない**（作者裁定 2026-08-17 で選んだ範囲の外。→ §5-1）。

---

## 1. 契約 §0-A の数字を 4 か所で読み直した（着手前・`e188850b`）

**契約は「§0-A を測り直さなくてよい」と書いているが、段 0 の測定（39 か所の分類）を作るには
39 か所を数え直す必要があり、そこで契約と合わない実測が出た。**作者裁定 2026-08-17 で
**「実測どおり未宣言を全部」**を選んでもらった。

| | 契約 | 実測 | なぜ違ったか |
|---|---|---|---|
| 移す箇所 | 39 | **44**（＋段 4 が名指す `scene_markers` で 45） | 下の 1〜3 |
| 移す未宣言語（異なり） | 110 | **119** | 下の 1〜3 |
| T-283 の期待値 | 684 | **693** | 574 + 119 |
| `note` / `color_hint` を照合する箇所 | 3 | **7** | 下の 1 |

1. **契約が語彙に数えていた `compose.py:842`（`_has_focal_event_hint`）は `ins.note` を照合していた。**
   9 語（`visual event`・`vanishing trace` …）は層が自分で書いた note なので移していない（**−9 語**）。
   同じ理由で `:830`（`machine_note`）・`:743` `:752`（`descriptive_hint`）・`:1186`（`green_context`＝層が返した文）・
   `normalize.py:451`（`hint.lower()`）・**`normalize.py:184` の `sensory_markers`（`color_hint` を照合）**も据え置いた。
2. **契約の走査道具 `count_coerce_markers.py` は `not in` を見ていない。**
   `compose.py:737` の `"crescent" not in ddl.lower()` は記述を判ずる未宣言語だった（**＋1 語**）。
3. **同じ道具は「名前に束ねた tuple」を見ていない**（引数が `Name` だと素通りする）。記述を照合するものが 6 本あり、
   5 本に未宣言語があった: `compose.py:1623 markers`（60 語・未宣言 25）・`:1703 mark_markers`（8）・
   `:1702 size_markers`（4）・`:1077 POLYCHROME_MARKERS`（2）・`:256 blur_markers`（1）。
   **⚠ 契約 §0-A 5 の「`blur_markers` は全語が宣言側にも在る」は誤りで、`にじ` が未宣言だった**
   （`scene_markers` のほうは契約どおり全語が宣言済みだった）。

**⚠ 発行側へ渡す事実**: **この 3 つは道具の穴であって、契約の書き手の読み落としではない。**
本契約で置いた番人（`test_the_coerce_vocabulary_lives_in_one_place.py`）は 3 つとも塞いである。

---

## 2. 段 0 の測定（**コードを 1 行も書く前**・commit `0157fab7` で凍結）

### 2-A. 39 か所（実測 56 か所）が通る道と戻り値

**判定の 56 か所すべてが真偽を返す。「一致した語そのもの」を返す箇所は 0 か所だった。**

| 通る道 | 箇所 | 戻り値 |
|---|---|---|
| `any(marker in X for marker in (...))` | 24 | 真偽 |
| `_any_marker_in_text((...), text, lower)` | 12 | 真偽（`_marker_in_text` の `any()`） |
| 素の `"x" in lower` / `"x" not in lower` | 20 | 真偽 |

**➡ T-284 は skip した**（理由を `pytest.mark.skip` の文字列に書いてある）。**P-6 は予測どおり空振りした**（→ §4）。

**⚠ 順序が効く箇所は既存の宣言側に在る** —— `MATERIAL_WEIGHT_HINTS`・`COLOR_MARKERS`・`SHAPE_INTENT_MARKERS`・
`MOTIF_INTENT_MARKERS`・`SEMANTIC_VISUAL_EVENT_HINTS` は `for markers, value in ...` で回して**最初に当たった組の値を返す**。
**本契約はこの 5 系統の中身を動かしていない。**

### 2-B. 移設で壊してはならなかった機構（実測して設計に反映した）

**`_marker_in_text` は ASCII の語に語境界の正規表現をかけ、素の `in` は生の部分一致である。**

```python
# _marker_in_text: "slow" は "slowly" に当たらない
re.search(rf"(?<![a-z]){re.escape(marker_lower)}(?![a-z])", lower)
# 素の in: "slow" は "slowly" に当たる
"slow" in lower
```

**➡ 照合の式は 1 か所も機構を変えていない。** リテラルの tuple を定数へ置き換えただけである。
**⚠ 実装中に 1 度、`"crescent" not in ddl.lower()` を `_any_marker_in_text` へ寄せて機構を変えてしまい、
その場で素の `in` へ戻した**（`crescents` に当たらなくなる摂動を、番人ではなく自分で見つけた）。

---

## 3. 立てた系統（45 本）

**系統名は「その分岐が何を判じているか」で付けた**（契約 段 1）。**既存 27 系統と重なる名前は無い。**
`新` の列は、その系統が宣言側へ**初めて**持ち込んだ語の数（0 なら全語が既に別系統に在った）。

| 系統 | ja | en | 新 | 名を決めた理由 |
|---|---|---|---|---|
| `variation_slow_wave` | 2 | 1 | 3 | `_with_variation_hint` の第 1 分岐。ゆっくりした波の揺らぎを付ける |
| `variation_fine_tremble` | 3 | 1 | 2 | 同・第 2 分岐。細かい震え |
| `variation_blurred_edge` | 3 | 1 | 4 | 同・第 3 分岐。境界の滲み |
| `neon_blur_scene` | 3 | 3 | 0 | ネオン滲みの密度governor が要求する 2 条件のうち「場面」の側 |
| `neon_blur_evidence` | 3 | 2 | 1 | 同・「滲みの証拠」の側。**連言なので 1 系統に畳めない** |
| `temporal_chain_sequence` | 5 | 3 | 6 | 時間の連鎖の証拠 4 つのうち「順序を言う語」 |
| `temporal_chain_action` | 8 | 9 | 13 | 同・「動作の語」 |
| `temporal_chain_before_after` | 1 | 2 | 1 | 同・「前後を言う語」 |
| `temporal_chain_reaction` | 3 | 5 | 5 | 同・「反応を言う語」。4 つは `and` で結ばれるので別々に要る |
| `polychrome_request` | 4 | 2 | 2 | 既に `POLYCHROME_MARKERS` という定数名だったものの中身。多色を明示的に求める語 |
| `withered_grass_green` | 4 | 2 | 6 | 緑を枯れ色へ寄せる分岐 |
| `autumn_forest_scene` | 1 | 1 | 0 | 森の緑の分岐の前段（`森` / `forest`）。**`and` の左辺** |
| `autumn_leaf_fall` | 3 | 0 | 1 | 同・右辺（落ち葉）。**日本語しか語が無い**（→ §3-A） |
| `presence_center_upper_right` | 1 | 1 | 2 | presence の中心を右上へ置く |
| `presence_center_upper_left` | 1 | 1 | 2 | 同・左上 |
| `presence_center_lower_right` | 1 | 1 | 2 | 同・右下 |
| `presence_center_lower_left` | 1 | 1 | 2 | 同・左下 |
| `presence_center_right_half` | 1 | 1 | 2 | 同・右半分 |
| `presence_center_left_half` | 1 | 1 | 2 | 同・左半分 |
| `presence_intensity_high` | 3 | 3 | 6 | presence の強度を high にする語。**契約時は日英が別の行だったので 1 系統に統べた** |
| `clause_names_a_mark` | 33 | 27 | 25 | 句が「痕跡を名指しているか」。DDL を句へ割るときの選別 |
| `clause_shape_cloudform` | 1 | 1 | 2 | 句が指す形（雲形）。以下 3 つは同じ if 連鎖の中 |
| `clause_shape_ellipse` | 1 | 2 | 3 | 同・楕円 |
| `clause_shape_circle` | 2 | 3 | 5 | 同・円 |
| `small_mark_size` | 2 | 4 | 4 | 「小さな痕跡の句」の 2 条件のうち大きさ |
| `small_mark_kind` | 3 | 5 | 8 | 同・形。**連言なので別々** |
| `clause_reflection` | 2 | 2 | 1 | 句が反射を言っているか |
| `clause_fading` | 2 | 4 | 2 | 句が消えを言っているか |
| `sensory_kind_light` | 4 | 3 | 5 | 感覚層の種別（光） |
| `sensory_kind_scent` | 3 | 2 | 2 | 同・香り |
| `sensory_kind_bud` | 3 | 2 | 5 | 同・蕾 |
| `sensory_kind_sense` | 3 | 3 | 3 | 同・気配 |
| `line_at_right_edge` | 2 | 1 | 3 | fallback の線を画面右端へ置く |
| `line_is_vertical` | 1 | 1 | 2 | 同・縦線 |
| `line_is_horizontal` | 1 | 1 | 2 | 同・横線 |
| `polygon_is_hexagonal` | 2 | 2 | 1 | fallback の多角形を 6 角にする |
| `fallback_place_right_half` | 1 | 1 | 2 | fallback の配置を右半分へ。**`presence_center_*` と同じ語だが別の判定なので束ねていない** |
| `fallback_place_upper_right` | 1 | 1 | 2 | 同・右上 |
| `fallback_place_upper_edge` | 1 | 2 | 3 | 同・上端 |
| `fallback_arrangement_scatter` | 1 | 1 | 2 | fallback の配置を散らす |
| `fallback_arrangement_line_up` | 1 | 1 | 2 | 同・並べる |
| `grid_requests_square` | 1 | 4 | 2 | 格子が四角を求めているか |
| `grid_requests_line` | 2 | 2 | 4 | 同・線 |
| `crescent_scene` | 0 | 1 | 1 | 三日月の場面。**英語しか語が無い**（→ §3-A） |
| `radius_clause` | 0 | 1 | 1 | 半径の数値を読む前の haystack の選別。**英語しか語が無い**（→ §3-A） |

### 3-A. 片方の言語しか語を持たない系統は 3 本（**揃えるための語は 1 つも足していない**）

| 系統 | 有る側 | 無い側に語が無い理由（実測） |
|---|---|---|
| `autumn_leaf_fall` | ja 3 | 元の条件が `any(marker in ddl for marker in ("落ち葉","紅葉","秋"))` で、**英語側の語が最初から書かれていなかった** |
| `crescent_scene` | en 1 | 元が `"crescent" not in ddl.lower()`。**日本語の「三日月」は書かれていなかった** |
| `radius_clause` | en 1 | 元が `lower if "radius" in lower else clause`。**日本語の「半径」は同じ行の正規表現の中に在る**（→ §5-2） |

**この 3 本は T-281 の `SINGLE_LANGUAGE_SYSTEMS` に名指しで挙げてある。**
**列挙から外れた系統が片言語になったら T-281 が赤くなる**（P-5 で実測）。
**⚠ これは [I-317] の材料である**（契約 §0-B 2）。**`server/scripts/coerce_marker_pairs.py --lopsided` が表を出す**（T-288）。

---

## 4. 摂動 8 本の実測（**予測は `0157fab7` で凍結済み**）

**回し方**: `perturb.py --run 'testbox.sh --sync --dirty --server'`。**8 本とも原本のバイトで戻し、sha256 が一致した。
`git checkout` は 1 度も打っていない。**

| 番号 | 何を壊したか | 予測 | 実測 | 赤くなった受入 |
|---|---|---|---|---|
| **P-1** | `withered_grass_green` から `枯れた草` を落とす | 2 | **2** ✓ | T-282・T-283 |
| **P-2** | 同系統へ `つけたし` を足す | 1 | **2** ✗ | T-282・T-283 |
| **P-3a** | **契約の例のまま** `("上端",)` を `compose.py` へ書き戻す | 0 | **0** ✓ | —（→ 下） |
| **P-3b** | **未宣言の語** `("上の端",)` を書き戻す | 1 | **1** ✓ | T-280 |
| **P-4** | `_coerce_marker_values` の呼び出しを関数の中へ | 1 | **1** ✓ | T-285 |
| **P-5** | `ja.py` にだけ系統を足す（語は既宣言のものを再利用） | 1 | **1** ✓ | T-281 |
| **P-6** | 移設した系統の語順を逆にする | 0 | **0** ✓ | —（→ 下） |
| **P-7** | `note` の文字列 `visual event` を `en.py` の系統へ載せる | 1 | **3** ✗ | T-280・T-282・T-283 |

**契約の 7 本ぶんの合計は 予測 7 本 / 実測 10 本。外した向きは 2 つとも「予測より多く赤くなった」である。**

- **P-2 と P-7 を外した理由**: **T-282（移設した語の集合が一致する）が、語を足す向きにも効く。**
  契約は P-2 → T-283 だけ・P-7 → T-280 だけと見立てていたが、**T-282 は「今の宣言 − 起点の宣言 == 移した 119 語」
  という等式なので、宣言側へ 1 語でも足すと必ず赤くなる。**外したのは受入の設計であって摂動ではない。
- **P-3a（契約の例）が空振りしたのは予測どおり** —— **`上端` は移設後に宣言側へ入るので、
  「未宣言のリテラルが無い」という主張に当たらない。**契約の例のままでは判別力が無いことを実測した。
  **未宣言の語（`上の端`）に替えると 1 本赤くなる**（P-3b）。
- **P-6 が空振りしたのも予測どおり** —— 段 0 の実測（一致した語を返す箇所が 0）から、**順序に判別力が無い。**
  **逆向きも測った: 語順を逆にした木の全走は 3462 passed / 32 skipped で、起点と 1 本も変わらない。**
  **順序を守る受入は本契約には無い**（据える先が無いため）。

---

## 5. 移設していない直書き（**残った現物を数えた**）

### 5-1. 語が全部宣言済みの直書き 8 か所（作者裁定で選んだ範囲の外）

| 箇所 | 語数 | 中身 |
|---|---|---|
| `compose.py:743` | 4 | `発車ベル`・`案内板`・`departure board`・`bell` |
| `compose.py:1198` | 2 | `竹`・`bamboo` |
| `compose.py:1693` | 4 | `色とりどり`・`多色`・`colorful`・`multi-color` |
| `compose.py:1718` | 4 | `多角形`・`五角`・`六角`・`polygon` |
| `compose.py:1720` | 3 | `四角`・`square`・`rectangle` |
| `compose.py:1722` | 2 | `三角`・`triangle` |
| `compose.py:1724` | 2 | `弧`・`arc` |
| `compose.py:1759` | 12 | `膜`・`霞`・`霧`・`靄` ほか（大気効果） |

**⚠ このうち `:1718` `:1720` `:1722` `:1724` は、移設した `:1716`（雲形）`:1726`（楕円）`:1728`（円）と
同じ if 連鎖の中に在る。**連鎖の半分だけが宣言側を読む形になった。**次の契約の材料である。**

### 5-2. marker の形に移せない語彙 3 か所（正規表現）

| 箇所 | 中身 |
|---|---|
| `compose.py:230` | `背景を[^。、\n]{1,12}?(?:で\|に)(?:塗\|ぬ\|埋\|し)` ＋ `(?:fill\|paint)\s+(?:the\s+)?background` |
| `compose.py:505` | `(?:領域\|region)` |
| `compose.py:1742` | `(?:半径\|radius(?:\s+is)?\|r)` |

**⚠ `半径` はここに在るため、`radius_clause` が英語だけの系統になっている**（→ §3-A）。

### 5-3. `note` / `color_hint` を照合する 7 か所（語彙ではない・触っていない）

`compose.py:360`（`_with_ddl_coverage`）・`:830`・`:743`〔`descriptive_hint`〕・`:752`・`:881`（`_has_focal_event_hint`）・
`:958` `:959`（compact mark）・`normalize.py:451`・`normalize.py:184`（`sensory_markers` は `color_hint` を照合）。
**番人はこれらを `NOTE_LITERALS`（リテラルそのもの）と照合先の変数名で除外している。行番号では除外していない。**

---

## 6. 受入の結果

| 番号 | 結果 | 実測 |
|---|---|---|
| **T-280** | ✅ | `coerce/` に未宣言の照合リテラルは 0。**逆向き**（note の 16 語が `COERCE_MARKERS` に載っていない）も同じ検査が測る |
| **T-281** | ✅ | 系統 27 → **72**（ja 70 / en 71）。片言語の 3 本は名指しで列挙 |
| **T-282** | ✅ | 起点の宣言 574 語 − 今の宣言 693 語の差が、移した 119 語と**集合として一致** |
| **T-283** | ✅ | **574 + 119 = 693**。**重複による目減りは無かった**（**270 語が 2 系統以上に載っている**が、数えるのは異なり語なので動かない） |
| **T-284** | ⏭️ skip | 段 0 で該当 0 か所。理由を skip の文字列に書いた |
| **T-285** | ✅ | `_coerce_marker_values` / `_coerce_marker_dict` の呼び出し **63 本がすべてモジュール先頭**。関数の中は 0 |
| **T-286** | ✅ | `testbox.sh --sync --corpora` が **`exit 0`**（`ea203c00`）。`rewrote 134 files; 0 of them differ`・`exited nonzero` の行は 0 |
| **T-287** | ✅ | **既存の検査では足りなかったので 1 本足した** —— golden は凍結値と照合するだけで、同じ入力を 2 度通さない。`coerce_score` を golden の 43 件すべての記述で 2 度通して dump を比べる検査を置いた |
| **T-288** | ✅ | `server/scripts/coerce_marker_pairs.py`（合否なし）。`--lopsided` で 6 系統が挙がる |
| **T-289** | ✅ | 全走 **3462 passed / 32 skipped**（`container:ddl-server`・`ea203c00`・exit 0）／ruff **All checks passed**。**消した検査は 0 本** |

### 6-A. 満点の推移（**コンテナの数字。Mac ではない**）

| 木 | 実測 | 予測 | 差 |
|---|---|---|---|
| 起点 `e188850b`（着手前） | **3454 passed / 31 skipped** | 3454 / 31 | — |
| 先端 `ea203c00` | **3462 passed / 32 skipped** | 3459 / 32 | **passed が +3 多い** |

**外した理由**: 予測は受入 T-280〜T-285 の 5 本＋skip 1 本だけを数えていた。実際に置いたのは 8 本＋skip 1 本で、
**予測に入れていなかったのは 3 本**である。

1. `test_the_scan_reads_all_four_shapes_and_skips_the_notes` —— **番人が 4 つの形すべてを読めることを、
   合成した断片で測る。**移設後の `coerce/` には `not in` の判定が 1 つも残らないので、
   **現物だけでは番人のその腕が 1 度も歩かれない**（結線しない探り針になる）。
2. `test_every_declared_system_is_reachable_from_the_registry` —— 宣言が registry から引けることの点呼。
3. `test_the_same_description_coerces_to_the_same_score_twice` —— T-287（→ §6）。

---

## 7. 古くなる文書（**実測した。実装は触っていない**）

- **`SPEC.ja.md:441` `:443` と `SPEC.md:655-668` は、古くなるのではなく、この変更で初めて字義どおりになる。**
  両方が「coerce の言語依存 marker は言語サポートが所有する」「言語固有語彙を共通コアへ混入させない」と書いており、
  **`compose.py` に 119 語が在るあいだ、この記述は偽だった。**日英とも記述は在り、**対応も取れている**（英語側だけ欠けてはいない）。
- **数字を書いた文書は無い** —— `574` / `27 系統` / `COERCE_MARKERS` を公開文書で grep したが、
  **語数や系統数を書いた箇所は 1 つも無かった**（`docs/history/` の 2 件は分離を述べた記述で、数字を持たない）。
- **⚠ 移植側に材料がある** —— `android/app/src/main/java/app/inku/mobile/pipeline/ServerScoreCoercer.kt` と
  `ServerScoreCounts.kt` は**自前の直書きリスト**（`LITERAL_GRID_MARKERS_JA` など）を持っている。
  **server の 119 語が宣言側に出たので、移植が読める形になった。本契約は `android/` を触っていない。**

---

## 8. 起票したほうがよいと考えたもの（**起票していない。判断を仰ぐ**）

1. **同じ if 連鎖の半分だけが宣言側を読む形になった**（→ §5-1 の ⚠）。
2. **`half` の 3 系統（`presence_center_*` と `fallback_place_*`）は同じ語を別の判定として持っている。**
   [I-317] が発火を数えたとき、**どちらが効いているかは系統名で分かる**が、**同じ語が 2 度数えられる**ことは書いておく価値がある。
3. **`count_coerce_markers.py` は 3 つの穴を持ったまま `no-git-sync/scripts/` に在る**（→ §1）。
   **番人のほうが精密なので、道具を番人の走査へ寄せるか、道具を捨てるかの判断が要る。**
