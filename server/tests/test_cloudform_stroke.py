"""engine 15 段 3: cloudform を既存の閉輪郭経路に載せる。

engine 14 まで cloudform の分岐は `generate_cloudform_contour()` の Catmull-Rom
パスをそのまま出しており、`stroke_engine` を一度も通っていなかった。それでいて
出力の class は `"cloudform contour-v1 stroke-engine-touch"` を名乗っていた。

届いていなかったのは `wild` だけではない。材質層 3 機構 — 材質輪郭・
`raster-bleed` (computer)・`burr` (drypoint) — がすべて 0 だった。ここでは
`_render_contour_hand_stroke()` を通ったことと、道具ごとの `wild` の届き方を固定
する。輪郭生成そのもの (`generate_cloudform_contour`) は engine 14 のままで、
変えたのは「その輪郭をどう演奏するか」だけである。
"""

from __future__ import annotations

import re
from xml.etree import ElementTree

import pytest

from inku_server.renderer import render
from inku_server.schema import Score

RENDER_SEED = 12345
CLOUDFORM = {"primitive": "cloudform", "center": [0.50, 0.50], "size": [0.48, 0.32]}

# wild が届く 9 道具。`computer` は誤差なく反復するので wild を効かせない
# (engine 13 の裁定)、`rotring` は機械の極なので手描き合成に入らない。
WILD_REACHES = (
    "brush_thick", "brush_thin", "burin", "chalk", "crayon",
    "drypoint", "pen", "pencil", "silverpoint",
)
WILD_IMMUNE = ("computer", "rotring")


def _svg(weight: str, *, wild: bool = False) -> str:
    score = Score.model_validate({"instructions": [{**CLOUDFORM, "weight": weight}]})
    return render(score, render_seed=RENDER_SEED, svg_profile="editable", wild=wild)


def _classes(svg: str) -> set[str]:
    return {token for value in re.findall(r'class="([^"]+)"', svg) for token in value.split()}


# --- D-1 / D-2: wild の届き方 ------------------------------------------------


@pytest.mark.parametrize("weight", WILD_REACHES)
def test_d1_wild_moves_the_cloudform_of_each_hand_tool(weight: str) -> None:
    """D-1 (陽性): 9 道具それぞれで cloudform の wild ON ≠ OFF になる。

    道具ごとに別のアサーションにする。1 道具だけ直って残り 8 が素通りのままでも
    「digest 集合が変わった」は成立してしまい、判別力が落ちる。
    """
    assert _svg(weight, wild=False) != _svg(weight, wild=True)


@pytest.mark.parametrize("weight", WILD_IMMUNE)
def test_d2_wild_leaves_the_machine_poles_identical(weight: str) -> None:
    """D-2 (陰性): computer / rotring の cloudform は wild ON = OFF のまま。"""
    assert _svg(weight, wild=False) == _svg(weight, wild=True)


# --- D-3 / D-4: 経路の証拠 ---------------------------------------------------


@pytest.mark.parametrize("weight", (*WILD_REACHES, "computer"))
def test_d3_cloudform_carries_the_shared_contour_stroke_class(weight: str) -> None:
    """D-3 (構造): 素通り経路が残っていない証拠として `contour-stroke-v1` が出る。"""
    assert "contour-stroke-v1" in _classes(_svg(weight))


def test_d3b_rotring_cloudform_stays_geometric() -> None:
    """D-3 の対: rotring は幾何のまま (機械の極を手描き経路に入れていない)。"""
    assert "contour-stroke-v1" not in _classes(_svg("rotring"))


@pytest.mark.parametrize("weight", (*WILD_REACHES, *WILD_IMMUNE))
def test_d4_stroke_engine_touch_marks_only_what_went_through_it(weight: str) -> None:
    """D-4 (構造): `stroke-engine-touch` は実際に stroke_engine を通ったときだけ付く。

    engine 14 では rotring の cloudform もこの語を名乗っていた。class 名が事実に
    反していると読み手を誤らせるので、通ったときだけ付ける。
    """
    went_through = weight != "rotring"
    assert ("stroke-engine-touch" in _classes(_svg(weight))) is went_through


# --- 材質層 3 機構が届いたこと -----------------------------------------------


def _tag_counts(svg: str) -> dict[str, int]:
    root = ElementTree.fromstring(svg)
    counts: dict[str, int] = {}
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        counts[tag] = counts.get(tag, 0) + 1
    return counts


def test_drypoint_cloudform_gains_its_burr() -> None:
    """`burr` は class も "burr" の文字も持たないので、余分な閉多角形で数える。"""
    drypoint = _tag_counts(_svg("drypoint"))
    burin = _tag_counts(_svg("burin"))
    assert drypoint.get("polygon", 0) == burin.get("polygon", 0) + 1


def test_computer_cloudform_gains_its_raster_bleed() -> None:
    assert "raster-bleed" in _classes(_svg("computer"))
    assert "raster-bleed" not in _classes(_svg("pen"))
