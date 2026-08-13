# 実装前の予測 — [I-227] 塗りは、ほかの面の語と同じ 1 語になる

**⚠ この文書はコードを 1 行も書く前に commit する**（実装と受け入れが同じセッションのときの歯止め）。
**実装後に実測と突き合わせ、外れたぶんはレポートへ差分として書く。**

- 契約: `no-git-sync/fable5/claude_code/tasks/the-fill-is-a-surface-word-like-the-rest.md`
- 起点: `954665fc` ／ 枝 `feat/the-fill-is-a-surface-word-like-the-rest`
- 作業場: `/Users/oikawas/projects/ddl-server-render`
- 契約が凍らせた満点: **`make test-server` で 3,173 passed / 31 skipped**（`cli/bench/leaf` の symlink は本作業場にも在る）

## 0. 実装前に自分で測った事実（契約の外）

| 何 | 実測 |
|---|---|
| 段 3 の 2 つ目の規則が発火する既存 case | **3 ファイル・5 命令**（`B-production-fill-clause` 2 / `B-production-no-fill-clause` 2 / `B-white-filled-circle` 1）。契約 §3 の但し書きと一致 |
| `b_coerce` の総数 | **30** |
| `branch_report` の記録方法 | `_record_branch_fire` は `report.setdefault(name, 0)` を**発火の有無に関わらず**行う |

⚠ **したがって `ddl-engine-18` の `changed_from_previous` は 3 ではなく 30 になると予測する。**
新しい枝の名前が全 case の `branch_report` に鍵として入るからで、engine 11 が
「21 件すべてが changed に挙がり、Score は 1 つも動いていない」と書いたのと同じ現象である。
**Score そのものが動くのは上の 3 ファイル。**

## 1. 設計上の判断（契約が指定していない箇所）

1. **枝の名前と置き場所** — `coerce/normalize.py` の `_with_fill_as_a_surface_word`。
   `coerce_score` の**両方の出口**で `without_explicit_region_support` の直後・
   `without_unrequested_color_cycle` の直前に置く。`filled` を書きうる枝
   （`_with_visible_particle` / `_fallback_instruction_from_clause` / `_with_unintentional_filled_shape_tempering`）が
   全部済んだ後でなければ、内側の言い方を 1 つに寄せる最後の一言にならない。
2. **⚠ 演奏 seed に `solid` を透明にする** — `_SEED_INSTRUCTION_FIELDS` は `surface` を含むので、
   段 3 が既存の `filled=true` に `surface` を足すと**本番の全作品の筆致 seed が動く**。
   契約 段 4-11「絵は今日と変わらないこと」を満たすため、`_seed_for_instruction` は
   `texture=="solid"` の surface を落として `filled=True` へ畳む（`_variation_seed_fields` が
   演奏されない variation に対して既にやっている作法）。**今日 `solid` を持つ Score は 1 つも無いので、
   既存のバイトは 1 つも動かない。**
3. **T-6 は生の Score で測る**（coerce を通さない）。上の 2 のおかげで
   「`filled=true` だけ」と「`texture="solid"` だけ」は renderer にとって同じ演奏になる。
   ⚠ **その帰結として P-4（`solid`→`filled` の導出だけ落とす）では T-6 は赤くならない** ——
   契約の予測と食い違う。理由は下の P-4 の行に書く。

## 2. 満点の予測

**新規に足すゲート = 14 本**（`server/tests/test_the_fill_is_a_surface_word_like_the_rest.py`）

| T | テスト名 | 本数 |
|---|---|---|
| T-1 | `test_solid_is_a_texture_and_every_quality_word_reaches_the_enum` | 1 |
| T-2 | `test_texture_for_surface_maps_both_languages` | 1 |
| T-3 | `test_the_stage1_phrases_did_not_move` | 1 |
| T-4 | `test_a_filled_closed_shape_gains_the_solid_texture` / `test_filled_on_a_line_does_not_gain_a_surface` | 2 |
| T-5 | `test_a_solid_texture_gains_filled` | 1 |
| T-6 | `test_the_two_ways_of_asking_for_a_fill_render_identical_bytes` / `test_a_solid_surface_fills_the_interior` | 2 |
| T-8 | `test_the_instruction_declaration_order_did_not_move` | 1 |
| T-9 | `test_the_tool_schema_offers_solid` | 1 |
| T-10 | `test_the_visible_particle_repair_leaves_a_note` / `test_the_branch_is_named_in_the_report` | 2 |
| T-11 | `test_the_few_shot_examples_carry_the_surface_sentence` | 1 |
| T-12 | `test_ddl_engine_18_is_baked_and_matches_its_manifest` | 1 |

**T-7 は既存の `test_a_small_mark_stays_small_whoever_wrote_it.py::test_no_frozen_engine_below_this_one_was_rewritten` が観測点**
（版が上がると `DDL_ENGINE_VERSION == "17"` と `checked == 571` の 2 つが赤くなるので、そこで 18 / 620 へ直す）。
**新しく 1 本足さない** —— 同じことを 2 度測る検査は、片方だけ直されて腐る。

**coerce golden に合成 case を 1 件足す** → `test_coerce_output_matches_the_frozen_golden` が **+1 件**。
（`test_every_branch_coerce_reaches_has_a_witness` が「発火しない枝」を許さないので、case は必須）

**したがって満点 = 3,173 + 14 + 1 = 3,188 passed / 31 skipped。**

### 実装で赤くなり、直して緑へ戻す既存の検査（削除ではない）

| # | 何 | なぜ |
|---|---|---|
| 1 | `test_omote_surface_category.py::test_omote_texture_values_cover_the_enum_minus_ground_and_default` | `score_value` の集合が `none` と `solid` を得る |
| 2 | `test_omote_surface_category.py::test_the_four_words_that_are_not_textures_carry_no_texture_value` | 2026-08-12 の裁定（塗り→filled）を 2026-08-13 の裁定が覆した |
| 3 | `test_prompt_digests.py::test_stage2_prompt_and_tool_expected_values` | Stage 2 本文 4 行＋作例と、tool schema の enum |
| 4 | `test_prompt_digests.py::test_schema_description_changes_stage2_but_not_system_prompt` | 同上（指紋 2 つ） |
| 5 | `test_api_surface.py::test_api_surface_is_unchanged` | `SurfaceSpec.texture` の enum。baseline を焼き直す |
| 6 | `test_the_acl_only_adds_to_the_api_surface.py` | 凍結面との差分に `SurfaceSpec` を宣言する |
| 7 | `test_the_card_only_adds_one_route.py` | 同上 |
| 8 | `test_api.py` の `ddl_engine_version == "17"` **4 箇所** | 版が 18 になる |
| 9 | `test_coerce_split.py::test_coerce_score_branch_order_is_frozen` | 枝が 1 本増える |
| 10 | `test_coerce_golden.py` の 41 件 | `branch_report` に鍵が 1 つ増える。`--refreeze` で焼き直す |
| 11 | `test_ddl_reference.py` / `test_android_reference_fixtures_are_current.py` | `ddl-engine-18` を焼くまで |
| 12 | `test_layer_version_history.py` | 注記 18 を足すまで |
| 13 | `test_a_small_mark_stays_small_whoever_wrote_it.py::test_no_frozen_engine_below_this_one_was_rewritten` | T-7（上記） |

## 3. 摂動の予測

**当てる先は製品コード。テスト自身を書き換える摂動は置かない。**
「赤くなる T」は確信して書く。「全走の赤」は**見積もり**であり、外れることを織り込んでいる
（巻き添えの範囲は走らせるまで測れない）。

| P | 何を壊すか | 赤くなる T（確信） | 全走の赤（見積もり） |
|---|---|---|---|
| **P-1** | `SurfaceTexture` から `solid` を外す | T-1 / T-2 / T-9 ＋ T-4a / T-5 / T-6a / T-6b / T-10b（枝が Score を検証できず落ちる） | **35** |
| **P-2** | `塗り` の `score_value` を消す | T-1 / T-2 | **3** |
| **P-3** | 段 3 の枝を no-op にする | T-4a / T-5 / T-10b | **11** |
| **P-4** | 逆向きの導出だけ落とす（`solid`→`filled`） | T-5 のみ。**⚠ T-6 は緑のまま** | **3** |
| **P-5** | 枝から閉図形の判定を外す | T-4b | **2** |
| **P-6** | renderer が `solid` を質感として描く | T-6a / T-6b | **3** |
| **P-7** | `Instruction` から `filled` を消す | T-8 ＋ 宣言順に依存する検査すべて | **80** |
| **P-8** | `_with_visible_particle` の note を消す | T-10a | **3** |
| **P-9** | few-shot の新しい例を消す | T-11 | **3** |
| **P-10** | Stage 1 の定型を `面: 塗る。` に変える | T-3 | **10** |
| **P-11** | `ddl-engine-18` を焼かずに版数だけ上げる | T-12 | **20** |
| **P-12** | `WebDdlSpec.kt` の Stage 2 定数を 1 文字変える | T-13（Android のみ） | server **0** / Android **2** |
| **P-13** | `ddl-engine-17/` の 1 ファイルを新しい実装の出力で上書きする | T-7 | **1** |

### P-4 が契約の予測とずれる理由（実装前に書いておく）

契約は P-4 で T-5 と T-6 が赤くなると予測している。**T-6 は緑のままになる。**
上の設計判断 2 のとおり、renderer は `filled=true` と `texture="solid"` を**同じ演奏**として扱う
（そうしないと、段 3 が既存の塗り図形に `surface` を足した瞬間に本番の全作品の筆致が動く）。
したがって coerce の逆向きの導出は**描画にとっては冗長**で、判別力を持つのは
「Score がどう言うか」を測る T-5 と、保存済み作品・Android・replay の側だけである。
**これは空振りではなく、既存の道と必ず一致する配線**（→ `perturbation_miss_may_mean_the_value_never_differs`）。

## 4. §4 の LLM 実測の予測（契約が凍らせたもの）

発行側の予測: **日英あわせて 8 回中 5〜8 回**で `surface.texture="solid"` が届く。
本セッションはこの予測を動かさない。**ハード上限は 900 秒へ上げ、外したことと
フォールバックの本数をレポートの冒頭に書く。**
