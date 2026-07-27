"""engine 15 段 4: 材質層の穴を塞ぐ。

段 4a — `triangle` / `polygon` は `_render_corner_shape()` へ委譲するが、その関数に
材質輪郭の呼び出しが無かった。`square` は自前の分岐を持ち、そちらにはあった。
`cloudform` は段 3 で共通経路に載ったので、同じ穴として一緒に塞ぐ。

段 4b — `hair` と `pen` は本体のストロークしか持たない。`_uses_material_outline()`
は材質層 3 機構のうち 1 つしか見ないので、この関数で数えると `raster-bleed`
(computer) と `burr` (drypoint) を取り落とし、裸の道具を 4 つと誤る。実際に何も
持たないのは `hair` と `pen` の 2 つで、本番で最も使われている 1 位と 4 位である。
"""

from __future__ import annotations

import re
from xml.etree import ElementTree

import pytest

from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.renderer import render
from inku_server.schema import Score

RENDER_SEED = 12345
CANVAS = canvas_size_for_aspect(None)

# コーパスと同じ幾何。raster-bleed のセル数は図形の大きさで変わるので、
# 恒等検査 (D-10) はここを動かしてはいけない。
GEOMETRY: dict[str, dict] = {
    "line": {"from": [0.18, 0.50], "to": [0.82, 0.50]},
    "circle": {"center": [0.50, 0.50], "radius": 0.24},
    "ellipse": {"center": [0.50, 0.50], "size": [0.48, 0.30]},
    "triangle": {"position": [0.28, 0.28], "size": [0.44, 0.44]},
    "square": {"position": [0.28, 0.28], "size": [0.44, 0.44]},
    "polygon": {"center": [0.50, 0.50], "radius": 0.25, "sides": 7},
    "arc": {"center": [0.50, 0.50], "radius": 0.27, "angle_start": 15.0, "angle_end": 285.0},
    "cloudform": {"center": [0.50, 0.50], "size": [0.48, 0.32]},
}
# engine 12 から数値が動いていない 5 道具。
FROZEN_MATERIAL_TOOLS = ("pencil", "crayon", "chalk", "brush_thin", "brush_thick")
BARE_TOOLS = ("hair", "pen")
NO_MATERIAL_OUTLINE = ("rotring", "computer", "drypoint", "burin")


def _svg(primitive: str, weight: str, *, wild: bool = False) -> str:
    score = Score.model_validate(
        {"instructions": [{"primitive": primitive, "weight": weight, **GEOMETRY[primitive]}]}
    )
    return render(score, render_seed=RENDER_SEED, svg_profile="editable", wild=wild)


def _outline_nodes(svg: str) -> list[ElementTree.Element]:
    root = ElementTree.fromstring(svg)
    return [n for n in root.iter() if n.attrib.get("class") == "material-outline"]


def _outline_count(primitive: str, weight: str) -> int:
    return len(_outline_nodes(_svg(primitive, weight)))


def _dashes(primitive: str, weight: str) -> list[str | None]:
    return [n.attrib.get("stroke-dasharray") for n in _outline_nodes(_svg(primitive, weight))]


def _tag_counts(svg: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in ElementTree.fromstring(svg).iter():
        tag = node.tag.rsplit("}", 1)[-1]
        counts[tag] = counts.get(tag, 0) + 1
    return counts


# --- 段 4a: D-5 / D-6 / D-7 --------------------------------------------------


@pytest.mark.parametrize("weight", FROZEN_MATERIAL_TOOLS)
@pytest.mark.parametrize("primitive", ("triangle", "polygon"))
def test_d5_corner_shapes_get_their_material_outline(primitive: str, weight: str) -> None:
    """D-5 (陽性): 5 道具 × triangle / polygon の 10 通りに材質輪郭が出る。"""
    assert _outline_count(primitive, weight) > 0


@pytest.mark.parametrize("weight", FROZEN_MATERIAL_TOOLS)
def test_d5b_cloudform_gets_its_material_outline(weight: str) -> None:
    """D-5 の系: cloudform も同じ経路に載ったので材質輪郭が出る (段 3 の効果)。"""
    assert _outline_count("cloudform", weight) > 0


@pytest.mark.parametrize("primitive", ("triangle", "polygon", "cloudform"))
@pytest.mark.parametrize("weight", NO_MATERIAL_OUTLINE)
def test_d6_tools_without_a_material_outline_did_not_gain_one(
    weight: str, primitive: str
) -> None:
    """D-6 (陰性): 道具のゲートを壊していない。表に足しすぎてもいない。"""
    assert _outline_count(primitive, weight) == 0


# engine 14 で凍結されていた `square` の材質輪郭。`_render_corner_shape` へ寄せた
# 副作用で square が動いていないことの恒等検査 (D-7)。
SQUARE_OUTLINE_DASHES: dict[str, list[str]] = {
    "pencil": ["1.000000,7.000000", "1.000000,5.000000"],
    "chalk": [
        "8.000000,12.000000,1.000000,8.000000",
        "5.000000,10.000000,1.000000,6.000000",
    ],
    "brush_thin": ["22.000000,9.000000", "14.000000,8.000000"],
    "brush_thick": [
        "18.000000,7.000000,3.000000,11.000000",
        "11.000000,9.000000",
    ],
    "crayon": [
        "2.000000,5.000000,9.000000,7.000000",
        "4.000000,8.000000",
        "2.000000,5.000000,9.000000,7.000000",
    ],
}


@pytest.mark.parametrize("weight", FROZEN_MATERIAL_TOOLS)
def test_d7_square_material_outline_is_unchanged(weight: str) -> None:
    """D-7 (恒等): square の材質輪郭は本数も dash も engine 14 のまま。"""
    assert _dashes("square", weight) == SQUARE_OUTLINE_DASHES[weight]


@pytest.mark.parametrize("weight", FROZEN_MATERIAL_TOOLS)
def test_d7b_square_material_outline_keeps_its_element_type(weight: str) -> None:
    """D-7 の対: square の層は `<rect>` のまま (演奏由来の polygon になっていない)。"""
    tags = {n.tag.rsplit("}", 1)[-1] for n in _outline_nodes(_svg("square", weight))}
    assert tags == {"rect"}


# --- 段 4b: D-8 / D-9 / D-12 -------------------------------------------------


@pytest.mark.parametrize(
    "primitive",
    ("line", "arc", "circle", "ellipse", "square", "triangle", "polygon", "cloudform"),
)
@pytest.mark.parametrize("weight", BARE_TOOLS)
def test_d8_bare_tools_now_leave_a_material_trace(weight: str, primitive: str) -> None:
    """D-8 (陽性): `pen` / `hair` は全 8 図形で材質輪郭を持つ。"""
    assert _outline_count(primitive, weight) > 0


@pytest.mark.parametrize("primitive", ("line", "circle", "triangle"))
@pytest.mark.parametrize("weight", NO_MATERIAL_OUTLINE)
def test_d9_the_other_tools_did_not_gain_a_material_outline(
    weight: str, primitive: str
) -> None:
    """D-9 (陰性): rotring / computer / drypoint / burin には材質輪郭が無い。

    `burin` は本番 1 instruction で既に plate_tone を持つので与えない。
    `drypoint` の `burr` は片側・非対称で、対称な材質輪郭とは別物なので置き換えない。
    """
    assert _outline_count(primitive, weight) == 0


@pytest.mark.parametrize(
    "primitive",
    ("line", "arc", "circle", "ellipse", "square", "triangle", "polygon", "cloudform"),
)
def test_d12_hair_leaves_one_stratum_and_pen_two(primitive: str) -> None:
    """D-12 (判別): `hair` = 毛の分かれ 1 本、`pen` = 2 本の穂先。本数を仕様として固定する。"""
    assert _outline_count(primitive, "hair") == 1
    assert _outline_count(primitive, "pen") == 2


def _rendered_offsets(weight: str) -> list[float]:
    """描画に出る法線オフセット (px)。

    **仕様表の値ではなくここを見ること。** `_MATERIAL_OUTLINE_SPECS` の値には
    強度レベルの gain (s1 で 2.8 倍) と下限 (3.5px) が掛かるので、表を読むだけの
    検査は絵と無関係な数を固定してしまう。
    """
    from inku_server.renderer import _material_outline_profile

    return [entry[0] for entry in _material_outline_profile(weight, CANVAS)]


def test_pen_strata_are_symmetric_about_the_ink() -> None:
    """`pen` の 2 本はつけペンの穂先なので、中心線の両側に対称に置く。"""
    offsets = _rendered_offsets("pen")
    assert len(offsets) == 2
    assert offsets[0] < 0 < offsets[1]
    assert abs(abs(offsets[0]) - offsets[1]) < 1e-9


def test_pen_strata_run_just_outside_the_band_edge() -> None:
    """`pen` の穂先は帯の縁のすぐ外を走る。

    基準幅 2.0px の帯の縁は中心線から 1.0px。強度レベル s1 の下限 3.5px を
    通すと痕跡が墨から 3.5px 離れ、閉輪郭で二重の輪に見えた (作者目視
    2026-07-27 で差し戻し)。`pen` は下限を免除してある。
    """
    from inku_server.renderer import _stroke_width_px

    half_width = _stroke_width_px("pen", CANVAS) / 2
    for offset in _rendered_offsets("pen"):
        assert half_width < abs(offset) < half_width * 2


def test_the_offset_floor_still_governs_every_frozen_tool() -> None:
    """下限を免除したのは `pen` だけで、engine 12 の 5 道具には今も掛かっている。

    `pencil` は表の値 (-1.0 / 1.2) に gain 2.8 を掛けても下限 3.5px に届かないので
    両方とも下限に張り付く。ここが動いたら凍結された 5 道具の出力が動いている。
    """
    from inku_server.renderer import _OUTLINE_OFFSET_FLOOR_EXEMPT, _material_gain

    assert _OUTLINE_OFFSET_FLOOR_EXEMPT == frozenset({"pen"})
    floor = _material_gain("outline_offset_floor_ratio") * CANVAS.unit
    assert _rendered_offsets("pencil") == [-floor, floor]
    for weight in ("chalk", "brush_thin", "brush_thick", "crayon"):
        assert all(abs(offset) >= floor for offset in _rendered_offsets(weight))


def test_hair_stratum_sits_at_the_floor_like_pencil() -> None:
    """`hair` の痕跡は下限に張り付いており、`pencil` と同じ位置に出る。

    契約は「`hair` の offset を全道具で最小に」としていたが、**強度レベル s1 では
    到達できない** — 下限 3.5px より内側の値は表に何を書いても下限へ丸められる。
    作者は 2026-07-27 にこの状態の描画を目視して承認しているので、ここは
    「承認された絵」を固定する。動かすなら下限そのものの裁定が要る。
    """
    floor = 3.5
    assert _rendered_offsets("hair") == [-floor]
    assert _rendered_offsets("pencil") == [-floor, floor]


def test_bare_tools_get_no_specks() -> None:
    """粒は柔らかく崩れる画材 (chalk / crayon / pencil) の印。硬い道具には与えない。"""
    from inku_server.renderer import _SPECK_SPECS

    assert set(_SPECK_SPECS) == {"pencil", "crayon", "chalk"}


# --- D-10 / D-11: 他の 2 機構の恒等検査 --------------------------------------


@pytest.mark.parametrize("primitive", ("line", "circle", "triangle"))
def test_d10_computer_raster_bleed_cell_count_is_unchanged(primitive: str) -> None:
    """D-10 (恒等): computer の raster-bleed セル数は engine 14 と一致する。

    セル数は図形の大きさで変わるので、コーパスと同じ幾何で数える。
    """
    frozen = {"line": 29, "circle": 74, "triangle": 67}
    cells = len(re.findall(r'class="raster-bleed"', _svg(primitive, "computer")))
    assert cells == frozen[primitive]


@pytest.mark.parametrize("primitive", ("line", "circle", "triangle"))
def test_d11_drypoint_burr_is_still_a_single_stratum(primitive: str) -> None:
    """D-11 (恒等): `burr` は 1 本のまま。

    実装は出力に識別子を持たない (class も "burr" の文字も無い) ので、同じ図形の
    `burin` との差 — 余分な `polyline` / `polygon` — で数える。
    """
    drypoint = _tag_counts(_svg(primitive, "drypoint"))
    burin = _tag_counts(_svg(primitive, "burin"))
    extra = sum(
        drypoint.get(tag, 0) - burin.get(tag, 0) for tag in ("polyline", "polygon")
    )
    assert extra == 1
