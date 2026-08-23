"""render engine 16 段 3: 太さの軸 (`thinness`)。

本番 1780 件に「太い / 太く」は 0 件で、要求は細い側にしかない。細さを言う手段が
道具名しかなかったので、「細い」は道具の選択へ流れ込み、最も細い道具 (銀筆) は
異なり入力 25 件のうち 1 件でしか選ばれなかった。太さは道具から独立した寸法で
あって揺らぎではない、という整理で `Instruction.thinness` を新設する。

契約 §4.5 の T-1〜T-7。
"""

from __future__ import annotations

import json
import pathlib

import pytest

from inku_server.coerce import coerce_score
from inku_server.composer import _score_tool_schema
from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.render_engines.default.determinism import _seed_for_instruction
from inku_server.render_engines.default.marks import (
    MIN_STROKE_WIDTH,
    THINNESS_TO_WIDTH_SCALE,
    WEIGHT_TO_STROKE_WIDTH,
    _stroke_width_px,
)
from inku_server.renderer import render
from inku_server.schema import Instruction, Score

CANVAS = canvas_size_for_aspect(None)


def _plain_mark(weight: str, thinness: str | None = None) -> Instruction:
    """A line that names the tool and nothing else.

    `_material_outline_profile` takes the instruction since render engine 38:
    both widths it reads are asked of `_mark_width_px`, which is where a
    described mark is seen. These probes are about the tool, so the subject
    states no surface -- the case whose numbers this file has always held.
    """
    return Instruction(
        primitive="line", **{"from": (0.18, 0.50)}, to=(0.82, 0.50),
        weight=weight, thinness=thinness,
    )

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "thinness_carry_h5.json"

# engine 15 の値。ここが動いたら太さの軸が道具の太さを書き換えている。
ENGINE_15_WIDTHS = {
    "silverpoint": 0.5,
    "pencil": 1.5,
    "pen": 2.0,
    "rotring": 1.0,
    "crayon": 4.0,
    "chalk": 3.0,
    "brush_thin": 3.0,
    "brush_thick": 8.0,
    "burin": 3.2,
    "drypoint": 2.6,
    "computer": 2.0,
}


def _line_score(weight: str, thinness: str | None) -> Score:
    return Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.18, 0.5],
                    "to": [0.82, 0.5],
                    "weight": weight,
                    "thinness": thinness,
                }
            ]
        }
    )


# --------------------------------------------------------------------------- #
# T-1 陽性: thinness だけ変えると線幅が変わる                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("weight", ["pen", "pencil", "brush_thick", "crayon", "chalk"])
def test_t1_fine_is_thinner_than_the_default(weight: str) -> None:
    default = _stroke_width_px(weight, CANVAS)
    fine = _stroke_width_px(weight, CANVAS, "fine")
    assert fine < default


@pytest.mark.parametrize("weight", ["pen", "pencil", "brush_thick", "crayon", "chalk"])
def test_t1_extra_fine_is_thinner_than_fine(weight: str) -> None:
    fine = _stroke_width_px(weight, CANVAS, "fine")
    extra_fine = _stroke_width_px(weight, CANVAS, "extra_fine")
    assert extra_fine < fine


def test_t1_the_drawing_changes_not_only_the_number() -> None:
    """幅の関数だけでなく、実際の SVG が別物になること。"""
    default = render(_line_score("pen", None), render_seed=12345, svg_profile="editable")
    fine = render(_line_score("pen", "fine"), render_seed=12345, svg_profile="editable")
    extra = render(
        _line_score("pen", "extra_fine"), render_seed=12345, svg_profile="editable"
    )
    assert default != fine
    assert fine != extra


# --------------------------------------------------------------------------- #
# T-2 陰性: thinness=None は道具の既定のまま                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("weight", sorted(ENGINE_15_WIDTHS))
def test_t2_default_width_is_the_engine_15_width(weight: str) -> None:
    assert _stroke_width_px(weight, CANVAS) == ENGINE_15_WIDTHS[weight]


def test_t2_stating_the_default_draws_the_same_as_omitting_it() -> None:
    """`thinness: null` を明示した Score と、鍵ごと無い Score が同じ絵になること。

    engine 15 との同一性は凍結コーパスが持つ。ここが留めるのは、既定値の側から
    絵が動かないこと — 演奏 seed に `thinness` を入れた (C-7) 影響で、値が None
    でも seed 鍵の JSON は変わる。だから「明示 None」と「省略」が同じ鍵になる
    ことを確かめないと、既定の作品が 2 つに割れる。
    """
    omitted = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.18, 0.5], "to": [0.82, 0.5], "weight": "pen"}
            ]
        }
    )
    stated = _line_score("pen", None)
    assert _seed_for_instruction(omitted.instructions[0]) == _seed_for_instruction(
        stated.instructions[0]
    )
    assert render(omitted, render_seed=12345, svg_profile="editable") == render(
        stated, render_seed=12345, svg_profile="editable"
    )


def test_t2_thinness_is_in_the_performance_seed_allowlist() -> None:
    """C-7。allowlist に入っていないと、細さが演奏の手を変えない。"""
    base = _line_score("pen", None).instructions[0]
    fine = _line_score("pen", "fine").instructions[0]
    assert _seed_for_instruction(base) != _seed_for_instruction(fine)


# --------------------------------------------------------------------------- #
# T-3 恒等: 道具の 11 の値は動かない                                             #
# --------------------------------------------------------------------------- #
def test_t3_weight_table_is_unchanged() -> None:
    assert WEIGHT_TO_STROKE_WIDTH == ENGINE_15_WIDTHS


# --------------------------------------------------------------------------- #
# T-4 保存: coerce は thinness を落とさない                                      #
# --------------------------------------------------------------------------- #
def test_t4_coerce_keeps_thinness() -> None:
    """LLM を呼ばない決定的なテスト。入力は H5 の実測 Score そのもの。"""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    score = Score.model_validate(fixture["score_stage2"])
    before = [ins.thinness for ins in score.instructions if ins.thinness]
    assert before, "fixture が thinness を持っていない"

    coerced = coerce_score(score, ddl=fixture["ddl"])
    after = [ins.thinness for ins in coerced.instructions if ins.thinness]
    assert sorted(after) == sorted(before)


# --------------------------------------------------------------------------- #
# T-5 不干渉: coerce が作る instruction に thinness は付かない (C-6)              #
# --------------------------------------------------------------------------- #
def test_t5_coerce_does_not_put_thinness_on_what_it_invents() -> None:
    """記述された細さが乗るのは記述された図形だけである。

    coerce は添景・律動・視覚事象で自分から instruction を作る。そこへ細さを
    継がせると、作者が書かなかった線の太さを coerce が決めることになる。
    """
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    score = Score.model_validate(fixture["score_stage2"])
    original = len(score.instructions)
    coerced = coerce_score(score, ddl=fixture["ddl"])
    added = coerced.instructions[original:]
    assert all(ins.thinness is None for ins in added)


def test_t5_the_coerce_source_holds_no_thinness_literal() -> None:
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "inku_server" / "coerce"
    for path in sorted(root.glob("*.py")):
        assert "thinness" not in path.read_text(encoding="utf-8"), path.name


# --------------------------------------------------------------------------- #
# T-6 順序: 極細でも銀筆の既定より細くならない                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("weight", sorted(ENGINE_15_WIDTHS))
@pytest.mark.parametrize("thinness", ["fine", "extra_fine"])
def test_t6_no_tool_goes_below_the_thinnest_tool(weight: str, thinness: str) -> None:
    assert _stroke_width_px(weight, CANVAS, thinness) >= ENGINE_15_WIDTHS["silverpoint"]


def test_t6_the_floor_is_the_thinnest_tool_not_a_new_number() -> None:
    assert MIN_STROKE_WIDTH == min(WEIGHT_TO_STROKE_WIDTH.values())
    assert MIN_STROKE_WIDTH == WEIGHT_TO_STROKE_WIDTH["silverpoint"]


def test_t6_the_scale_has_no_thick_side() -> None:
    assert THINNESS_TO_WIDTH_SCALE[None] == 1.0
    assert all(
        scale < 1.0 for key, scale in THINNESS_TO_WIDTH_SCALE.items() if key is not None
    )


# --------------------------------------------------------------------------- #
# T-7 構造: 両方のスキーマに出る (§4.4 ①)                                        #
# --------------------------------------------------------------------------- #
def test_t7_thinness_is_in_the_instruction_schema() -> None:
    assert "thinness" in Instruction.model_fields
    assert "thinness" in Instruction.model_json_schema()["properties"]


def test_t7_thinness_reaches_the_score_tool_schema() -> None:
    """LLM に渡るのはこちら。`Instruction` 側だけ見ると素通りする。"""
    properties = _score_tool_schema()["properties"]["instructions"]["items"]["properties"]
    assert "thinness" in properties
    enum = properties["thinness"]["anyOf"][0]["enum"]
    assert enum == ["fine", "extra_fine"]


def test_t7_the_stage2_prompts_carry_the_conversion_table() -> None:
    from inku_server.composer import SYSTEM_PROMPT, SYSTEM_PROMPT_EN

    assert "# 太さ → thinness 変換 (必須)" in SYSTEM_PROMPT
    assert "extra_fine" in SYSTEM_PROMPT
    assert "# Thinness → thinness (required)" in SYSTEM_PROMPT_EN
    assert "extra_fine" in SYSTEM_PROMPT_EN


def test_t7_the_stage1_prompts_carry_the_thinness_rule() -> None:
    from inku_server.interpreter import SYSTEM_PROMPT_PREFIX, SYSTEM_PROMPT_PREFIX_EN

    assert "極細" in SYSTEM_PROMPT_PREFIX
    assert "太い指定は無い" in SYSTEM_PROMPT_PREFIX
    assert "extra fine" in SYSTEM_PROMPT_PREFIX_EN
    assert "there is no thicker side" in SYSTEM_PROMPT_PREFIX_EN


# --------------------------------------------------------------------------- #
# 材質層は墨に追随する                                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("weight", ["brush_thick", "crayon"])
def test_material_outline_follows_the_thinned_ink(weight: str) -> None:
    """墨に比例する材質層が、細く引いた墨に追随すること。

    材質輪郭の幅は `abs_width + base_width * width_ratio`。基準を
    `WEIGHT_TO_STROKE_WIDTH` に据え置くと、墨だけが細って材質が取り残される。
    比例項を持つのは太筆とクレヨンの 2 道具である。
    """
    from inku_server.render_engines.default.marks import _material_outline_profile

    default = _material_outline_profile(_plain_mark(weight), CANVAS)
    thinned = _material_outline_profile(_plain_mark(weight, "extra_fine"), CANVAS)
    assert len(default) == len(thinned)
    assert all(a[1] > b[1] for a, b in zip(default, thinned))


@pytest.mark.parametrize("weight", ["pen", "pencil", "chalk", "brush_thin"])
def test_material_outline_absolute_widths_do_not_move(weight: str) -> None:
    """絶対幅で書かれた材質層は細さで動かない (`width_ratio` が 0)。

    材質は道具そのものの粗さで、線を細く引いても紙の目や粉の粒は細らない。
    距離も同じ理由で動かさない — engine 15 の「強さは距離ではない」のまま。
    """
    from inku_server.render_engines.default.marks import _material_outline_profile

    assert _material_outline_profile(_plain_mark(weight), CANVAS) == _material_outline_profile(
        _plain_mark(weight, "extra_fine"), CANVAS
    )
