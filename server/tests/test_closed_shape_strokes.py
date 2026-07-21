"""v2.2 (engine 8): 閉図形の輪郭を手描きストロークで描く経路のテスト。

材質エンジン (stroke_engine の ToolGrammar) は line にしか適用されておらず、
閉図形は素の SVG 図形 + 材質輪郭だけで描かれていた。閉図形の輪郭を一筆の
ストロークとして合成する経路を検証する。
"""

from __future__ import annotations

import math
import re
from xml.etree import ElementTree

import pytest

from inku_server.renderer import (
    _edge_contour_with_anchors,
    _seed_for_instruction,
    _stroke_width_px,
    render,
)
from inku_server.schema import Instruction, Score
from inku_server.stroke_engine import GRAMMARS, synthesize_along

from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect

CANVAS = canvas_size_for_aspect(None)

# 対象の閉図形。cloudform は専用の輪郭生成器を持つので対象外。
SHAPES: dict[str, dict] = {
    "circle": {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2},
    "ellipse": {"primitive": "ellipse", "center": [0.5, 0.5], "size": [0.3, 0.2]},
    "square": {"primitive": "square", "position": [0.3, 0.3], "size": [0.4, 0.4]},
    "triangle": {"primitive": "triangle", "position": [0.3, 0.3], "size": [0.4, 0.4]},
    "polygon": {
        "primitive": "polygon",
        "center": [0.5, 0.5],
        "radius": 0.2,
        "sides": 6,
    },
}

HAND_WEIGHTS = sorted(set(GRAMMARS) - {"rotring"})

WAVE = {
    "amplitude": "medium",
    "frequency": "medium",
    "quality": "wave",
    "dimensions": ["position_x", "position_y"],
}


def _render(name: str, *, weight: str = "pencil", render_seed: int | None, **extra):
    payload = dict(SHAPES[name], weight=weight, **extra)
    score = Score.model_validate({"instructions": [payload]})
    return render(score, render_seed=render_seed)


def _stroke_paths(svg: str) -> list[str]:
    """輪郭ストロークの帯 (contour-stroke-v1 群の path) の d を取り出す。"""
    root = ElementTree.fromstring(svg)
    result: list[str] = []

    def visit(element: ElementTree.Element, inside: bool) -> None:
        band = inside or "contour-stroke-v1" in element.attrib.get("class", "")
        if band and element.tag.endswith("path"):
            result.append(element.attrib["d"])
        for child in element:
            visit(child, band)

    visit(root, False)
    return result


def _subpath_points(subpath: str) -> list[tuple[float, float]]:
    return [
        (float(x), float(y))
        for x, y in re.findall(r"(-?[\d.]+) (-?[\d.]+)", subpath)
    ]


@pytest.mark.parametrize("name", sorted(SHAPES))
@pytest.mark.parametrize("weight", HAND_WEIGHTS)
def test_hand_weights_get_a_contour_stroke(name: str, weight: str):
    """手描き系 weight の閉図形は輪郭が帯として演奏される。"""
    svg = _render(name, weight=weight, render_seed=11)
    assert "contour-stroke-v1" in svg
    assert len(_stroke_paths(svg)) == 1


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_rotring_stays_geometric(name: str):
    """rotring (製図ペン) は幾何のまま。輪郭ストロークを持たない。"""
    svg = _render(name, weight="rotring", render_seed=11)
    assert "contour-stroke-v1" not in svg
    assert _stroke_paths(svg) == []


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_contour_stroke_is_deterministic_per_seed(name: str):
    """同一 (Score, render_seed) の演奏はバイト一致する。"""
    first = _render(name, render_seed=111)
    replay = _render(name, render_seed=111)
    assert first == replay


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_contour_stroke_follows_render_seed(name: str):
    """演奏 seed を変えると筆致が動く (v2.0.5 の seed 追随契約)。"""
    a = _stroke_paths(_render(name, render_seed=111))
    b = _stroke_paths(_render(name, render_seed=222))
    assert a != b


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_intended_geometry_is_kept_as_the_body(name: str):
    """本体要素 (塗り) は幾何のまま残り、輪郭だけが帯に置き換わる。"""
    svg = _render(name, render_seed=11)
    expected = {
        "circle": "<circle",
        "ellipse": "<ellipse",
        "square": "<rect",
        "triangle": "<polygon",
        "polygon": "<polygon",
    }[name]
    # 地の矩形 (塗りなし) と speck (opacity 付き) を除いた墨色の要素が本体。
    bodies = [
        item
        for item in re.findall(rf"{re.escape(expected)}[^>]*>", svg)
        if 'fill="#111111"' in item and " opacity=" not in item
    ]
    assert len(bodies) == 1
    # 実線では本体の stroke を落とし、輪郭は帯だけが担う。
    assert 'stroke="none"' in bodies[0]


@pytest.mark.parametrize("name", ["square", "triangle", "polygon"])
@pytest.mark.parametrize("seed", [0, 7, 111, 98765])
def test_corners_are_pinned(name: str, seed: int):
    """角は筆の継ぎ目として固定される (F-4 の角固定契約の維持)。"""
    corners = [(100.0, 100.0), (900.0, 120.0), (860.0, 900.0), (140.0, 880.0)]
    contour, anchors = _edge_contour_with_anchors(corners, None, seed, 0.0, CANVAS)
    stroke = synthesize_along(
        contour,
        _stroke_width_px("brush_thick", CANVAS),
        "brush_thick",
        seed,
        closed=True,
        anchors=anchors,
    )
    for index in sorted(anchors):
        sample = stroke.samples[index]
        assert (sample.x, sample.y) == pytest.approx(contour[index])
    # 角以外は筆が理想線から離れている (固定が「揺れなし」を意味しない)。
    moved = max(
        math.hypot(sample.x - point[0], sample.y - point[1])
        for index, (sample, point) in enumerate(zip(stroke.samples, contour))
        if index not in anchors
    )
    assert moved > 0.0


@pytest.mark.parametrize("weight", HAND_WEIGHTS)
@pytest.mark.parametrize("seed", [0, 7, 111, 98765])
def test_closed_contour_meets_itself_at_the_seam(weight: str, seed: int):
    """角を持たない閉輪郭は継ぎ目で自分自身に出会う (閉合契約)。

    継ぎ目の段差が、隣り合うサンプル間隔と同程度に収まっていることを見る。
    """
    count = 64
    contour = [
        (500.0 + 200.0 * math.cos(i * math.tau / count),
         500.0 + 200.0 * math.sin(i * math.tau / count))
        for i in range(count)
    ]
    stroke = synthesize_along(
        contour,
        _stroke_width_px(weight, CANVAS),
        weight,
        seed,
        closed=True,
    )
    first, last = stroke.samples[0], stroke.samples[-1]
    seam = math.hypot(last.x - first.x, last.y - first.y)
    spacing = 2 * math.pi * 200.0 / count
    assert seam < spacing * 1.5


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_contour_stroke_band_is_a_closed_ring(name: str):
    """帯は外周・内周の 2 つの閉サブパスで、even-odd で塗られる。"""
    svg = _render(name, render_seed=11)
    path = _stroke_paths(svg)[0]
    subpaths = [item for item in path.split("M") if item.strip()]
    assert len(subpaths) == 2
    assert path.count("Z") == 2
    assert 'fill-rule="evenodd"' in svg
    outer, inner = (_subpath_points(item) for item in subpaths)
    assert len(outer) == len(inner) > 2


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_variation_is_performed_before_the_stroke(name: str):
    """揺らぎを演奏した輪郭に対してストロークを合成する (合成順序)。"""
    plain = _stroke_paths(_render(name, render_seed=11))
    varied = _stroke_paths(_render(name, render_seed=11, variation=WAVE))
    assert plain != varied


@pytest.mark.parametrize("name", ["circle", "ellipse", "square"])
def test_material_outline_and_specks_survive(name: str):
    """材質輪郭・speck は帯と併存する (置き換えられるのは本体の輪郭だけ)。"""
    svg = _render(name, weight="chalk", render_seed=11)
    assert 'class="material-outline"' in svg
    assert "contour-stroke-v1" in svg
    assert svg.count("<circle") >= 2


def test_dashed_style_keeps_a_geometric_outline():
    """破線・点線は線種そのものが記述なので、細い幾何輪郭を残して読ませる。"""
    svg = _render("circle", render_seed=11, style="dashed")
    body = re.search(r"<circle[^>]*>", svg)
    assert body is not None
    assert 'stroke="none"' not in body.group(0)
    assert "stroke-dasharray" in body.group(0)


def test_seed_key_is_shared_with_the_material_layers():
    """帯と材質層は同じ instruction seed から演奏される。"""
    ins = Instruction.model_validate(dict(SHAPES["circle"], weight="pencil"))
    assert _seed_for_instruction(ins, 111) != _seed_for_instruction(ins, 222)
    assert _seed_for_instruction(ins) == _seed_for_instruction(ins, None)
