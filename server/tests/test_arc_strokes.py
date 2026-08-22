"""v2.4 (engine 10): 弧 (arc) の輪郭を手描きストロークで描く経路のテスト。

engine 9 まで arc は幾何の弧 (`<path d="M..A..">` / 変奏 polyline) のまま描かれ、
line / 閉図形だけが材質エンジン (stroke_engine の ToolGrammar) で帯として演奏
されていた。engine 10 で arc も帯として演奏する。

要の設計 (論点1 = A): 幾何の弧は不可視の意図要素 (`stroke="none"`) として残し、
帯を上に重ねる。touching の接点契約はこの意図弧の座標が担保するので、抽出器
(`test_touching._svg_arcs`) は無改変で弧を 1 個だけ数える。接点端も taper のまま
(論点2)。
"""

from __future__ import annotations

import re
from xml.etree import ElementTree

import pytest

from inku_server.render_engines.default.determinism import _seed_for_instruction
from inku_server.renderer import render
from inku_server.schema import Instruction, Score
from inku_server.stroke_engine import GRAMMARS

ARC: dict = {
    "primitive": "arc",
    "center": [0.5, 0.5],
    "radius": 0.2,
    "angle_start": 0,
    "angle_end": 120,
}

HAND_WEIGHTS = sorted(set(GRAMMARS) - {"rotring"})

WAVE = {
    "amplitude": "medium",
    "frequency": "medium",
    "quality": "wave",
    "dimensions": ["position_x", "position_y"],
}


def _render(*, weight: str = "pencil", render_seed: int | None, **extra):
    payload = dict(ARC, weight=weight, **extra)
    score = Score.model_validate({"instructions": [payload]})
    return render(score, render_seed=render_seed)


def _band_paths(svg: str) -> list[str]:
    """帯 (arc-stroke-v1 群の path) の d を取り出す。"""
    root = ElementTree.fromstring(svg)
    result: list[str] = []

    def visit(element: ElementTree.Element, inside: bool) -> None:
        band = inside or "arc-stroke-v1" in element.attrib.get("class", "")
        if band and element.tag.endswith("path"):
            d = element.attrib.get("d", "")
            # 意図弧 (M..A..) と材質輪郭 (material-outline) は帯ではない。
            if "A " not in d and "material-outline" not in element.attrib.get(
                "class", ""
            ):
                result.append(d)
        for child in element:
            visit(child, band)

    visit(root, False)
    return result


def _intended_arcs(svg: str) -> list[str]:
    """抽出器と同じ規準で意図弧を数える (kind を返す)。

    `test_touching._svg_arcs` の判定と整合させる: `stroke-opacity` 既定 "1"・
    `material-outline` クラス無し。弧コマンド path (`A` を含む) と、弧をなす
    polyline を数える。帯 (`M..L..Z`) と burr (opacity < 0.45) は数えない。
    """
    root = ElementTree.fromstring(svg)
    result: list[str] = []

    def visit(element: ElementTree.Element) -> None:
        opacity = float(element.attrib.get("stroke-opacity", "1"))
        is_material = "material-outline" in element.attrib.get("class", "")
        if opacity >= 0.45 and not is_material:
            if element.tag.endswith("path") and "A " in element.attrib.get("d", ""):
                result.append("path")
            elif element.tag.endswith("polyline") and element.attrib.get("points"):
                result.append("polyline")
        for child in element:
            visit(child)

    visit(root)
    return result


@pytest.mark.parametrize("weight", HAND_WEIGHTS)
def test_hand_weights_get_an_arc_stroke(weight: str):
    """手描き系 weight の弧は帯として演奏される。"""
    svg = _render(weight=weight, render_seed=11)
    assert "arc-stroke-v1" in svg
    assert len(_band_paths(svg)) == 1


def test_rotring_stays_geometric():
    """rotring (製図ペン) は幾何の弧のまま。帯を持たない。"""
    svg = _render(weight="rotring", render_seed=11)
    assert "arc-stroke-v1" not in svg
    assert _band_paths(svg) == []
    # 幾何の弧コマンドがそのまま残る。
    assert _intended_arcs(svg) == ["path"]


@pytest.mark.parametrize("weight", HAND_WEIGHTS)
def test_intended_arc_is_kept_invisible_for_solid(weight: str):
    """実線では意図の弧を不可視 (stroke=none) で残す。抽出器は 1 個だけ数える。"""
    svg = _render(weight=weight, render_seed=11)
    assert _intended_arcs(svg) == ["path"]
    # 意図弧は塗りも stroke も持たない (帯が線を担う)。
    intended = [
        item
        for item in re.findall(r"<path[^>]*>", svg)
        if " A " in item and "material-outline" not in item
    ]
    assert len(intended) == 1
    assert 'stroke="none"' in intended[0]
    assert 'fill="none"' in intended[0]


@pytest.mark.parametrize("weight", HAND_WEIGHTS)
def test_varied_arc_keeps_a_polyline_intent(weight: str):
    """変奏ありの弧は演奏後の polyline を意図要素として残す (kind=polyline)。"""
    svg = _render(weight=weight, render_seed=11, variation=WAVE)
    assert _intended_arcs(svg) == ["polyline"]
    assert "arc-stroke-v1" in svg
    assert len(_band_paths(svg)) == 1


def test_arc_stroke_is_deterministic_per_seed():
    """同一 (Score, render_seed) の演奏はバイト一致する。"""
    assert _render(render_seed=111) == _render(render_seed=111)


def test_arc_stroke_follows_render_seed():
    """演奏 seed を変えると筆致が動く。"""
    assert _band_paths(_render(render_seed=111)) != _band_paths(_render(render_seed=222))


def test_variation_is_performed_before_the_stroke():
    """揺らぎを演奏した弧に対してストロークを合成する (合成順序)。"""
    plain = _band_paths(_render(render_seed=11))
    varied = _band_paths(_render(render_seed=11, variation=WAVE))
    assert plain != varied


@pytest.mark.parametrize("weight", ["pencil", "crayon", "chalk"])
def test_material_outline_and_specks_survive(weight: str):
    """材質輪郭・speck は帯と併存する (置き換えられるのは本体の輪郭だけ)。"""
    svg = _render(weight=weight, render_seed=11)
    assert 'class="material-outline' in svg
    assert "arc-stroke-v1" in svg
    # speck は小円。地の点とは別に材質の speck が乗る。
    assert svg.count("<circle") >= 1
    # 材質輪郭・speck を足しても意図弧は 1 個のまま。
    assert _intended_arcs(svg) == ["path"]


def test_dashed_style_keeps_a_visible_arc():
    """破線・点線は線種そのものが記述なので、細い弧を残して読ませる。"""
    svg = _render(render_seed=11, style="dashed")
    intended = [
        item
        for item in re.findall(r"<path[^>]*>", svg)
        if " A " in item and "material-outline" not in item
    ]
    assert len(intended) == 1
    assert 'stroke="none"' not in intended[0]
    assert "stroke-dasharray" in intended[0]
    # 破線でも意図弧は 1 個 (可視の細い弧 = 意図要素そのもの、二重計上しない)。
    assert _intended_arcs(svg) == ["path"]
    assert "arc-stroke-v1" in svg


def test_drypoint_emits_a_burr():
    """drypoint は中心線に沿って burr (polyline) を出す。帯にはテクスチャを載せない。"""
    svg = _render(weight="drypoint", render_seed=11)
    assert "arc-stroke-v1" in svg
    # burr は低 opacity の polyline なので抽出器には拾われない。
    assert _intended_arcs(svg) == ["path"]
    root = ElementTree.fromstring(svg)
    burrs = [
        element
        for element in root.iter()
        if element.tag.endswith("polyline")
        and element.attrib.get("stroke", "none") != "none"
        and float(element.attrib.get("stroke-opacity", "1")) < 0.45
    ]
    assert len(burrs) == 1


def test_seed_key_is_shared_with_the_material_layers():
    """帯と材質層は同じ instruction seed から演奏される。"""
    ins = Instruction.model_validate(dict(ARC, weight="pencil"))
    assert _seed_for_instruction(ins, 111) != _seed_for_instruction(ins, 222)
    assert _seed_for_instruction(ins) == _seed_for_instruction(ins, None)
