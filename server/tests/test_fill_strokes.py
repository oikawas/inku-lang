"""v2.3 (engine 9): 塗りのストローク化・`filled` の復権・不活性 variation の seed 除外。

塗りは領域 fill ではなく、素材の筆致で内側を埋めること。閉図形が `filled` に
関わらず常に塗られていた挙動 (死にフィールド) を解消し、`surface` 指定時は
明示的な版表現が内部を担う。
"""

from __future__ import annotations

import math
import re

import pytest

from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.renderer import (
    _fill_scan_angle,
    _fill_scan_spacing,
    _scanline_segments,
    _seed_for_instruction,
    _stroke_width_px,
    render,
)
from inku_server.schema import Instruction, Score
from inku_server.stroke_engine import GRAMMARS

CANVAS = canvas_size_for_aspect(None)

SHAPES: dict[str, dict] = {
    "circle": {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.3},
    "ellipse": {"primitive": "ellipse", "center": [0.5, 0.5], "size": [0.5, 0.3]},
    "square": {"primitive": "square", "position": [0.2, 0.2], "size": [0.6, 0.6]},
    "triangle": {"primitive": "triangle", "position": [0.2, 0.2], "size": [0.6, 0.6]},
    "polygon": {
        "primitive": "polygon",
        "center": [0.5, 0.5],
        "radius": 0.3,
        "sides": 5,
    },
    "cloudform": {"primitive": "cloudform", "center": [0.5, 0.5], "size": [0.6, 0.5]},
}

HAND_WEIGHTS = sorted(set(GRAMMARS) - {"rotring"})


def _render(payload: dict, *, render_seed: int | None = 11, **extra):
    score = Score.model_validate({"instructions": [dict(payload, **extra)]})
    return render(score, render_seed=render_seed)


def _fill_groups(svg: str) -> list[str]:
    """塗りストローク群 (fill-stroke-v1) を丸ごと取り出す。"""
    return re.findall(r'<g class="fill-stroke-v1[^"]*">.*?</g>', svg, flags=re.S)


def _fill_paths(svg: str) -> list[str]:
    return [d for group in _fill_groups(svg) for d in re.findall(r'd="([^"]+)"', group)]


def _segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = dx * dx + dy * dy
    t = 0.0
    if length > 0:
        t = max(
            0.0,
            min(
                1.0,
                ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length,
            ),
        )
    return math.hypot(point[0] - (start[0] + dx * t), point[1] - (start[1] + dy * t))


def _points(path_d: str) -> list[tuple[float, float]]:
    return [
        (float(x), float(y))
        for x, y in re.findall(r"(-?\d+\.\d+) (-?\d+\.\d+)", path_d)
    ]


# --- A. 塗りのストローク化 -------------------------------------------------


@pytest.mark.parametrize("name", sorted(SHAPES))
@pytest.mark.parametrize("weight", HAND_WEIGHTS)
def test_filled_shape_is_filled_with_material_strokes(name: str, weight: str):
    svg = _render(SHAPES[name], weight=weight, filled=True)
    groups = _fill_groups(svg)
    assert len(groups) == 1
    assert len(_fill_paths(svg)) >= 3


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_unfilled_shape_has_no_fill_strokes(name: str):
    """`filled=False` は輪郭のみ。塗りストロークも領域 fill も出ない。"""
    svg = _render(SHAPES[name], weight="pencil", filled=False)
    assert _fill_groups(svg) == []
    # 墨色の塗りを持つのは輪郭帯 (evenodd の ring) と speck だけ。図形の内部は空。
    inked = [
        element
        for element in re.findall(r"<[a-z]+[^>]*>", svg)
        if 'fill="#111111"' in element
    ]
    for element in inked:
        assert 'fill-rule="evenodd"' in element or " opacity=" in element


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_fill_strokes_are_one_path_per_stroke(name: str):
    """1 パス = 1 筆。走査線の区間ごとに独立した筆になっている。"""
    svg = _render(SHAPES[name], weight="pencil", filled=True)
    paths = _fill_paths(svg)
    assert len(paths) == len(set(paths))
    for path_d in paths:
        assert path_d.count("M ") == 1


def test_fill_strokes_stay_inside_the_circle():
    ins = dict(SHAPES["circle"], weight="brush_thick", filled=True)
    svg = _render(ins)
    radius = 0.3 * CANVAS.unit
    width = _stroke_width_px("brush_thick", CANVAS)
    for x, y in _points("".join(_fill_paths(svg))):
        assert math.hypot(x - 500.0, y - 500.0) <= radius + width


def test_fill_strokes_stay_inside_a_concave_cloudform():
    """凹形でも交点対で切るので、筆が輪郭の外へ出ない。"""
    from inku_server.cloudform import generate_cloudform_contour, sample_closed_catmull_rom

    payload = dict(SHAPES["cloudform"], weight="pencil", filled=True)
    ins = Instruction.model_validate(payload)
    contour = generate_cloudform_contour(
        (0.5 * CANVAS.width, 0.5 * CANVAS.height),
        (0.6 * CANVAS.width, 0.5 * CANVAS.height),
        performance_seed=_seed_for_instruction(ins, 11),
        instruction_index=0,
        mark_index=0,
        variation=None,
        weight="pencil",
    )
    polygon = list(sample_closed_catmull_rom(contour.points))

    def excursion(point: tuple[float, float]) -> float:
        """輪郭の外へ出た距離 (内側なら 0)。"""
        x, y = point
        inside = False
        for index in range(len(polygon)):
            ax, ay = polygon[index]
            bx, by = polygon[(index + 1) % len(polygon)]
            if (ay <= y) != (by <= y):
                if x < ax + (y - ay) / (by - ay) * (bx - ax):
                    inside = not inside
        if inside:
            return 0.0
        return min(
            _segment_distance(point, polygon[index], polygon[(index + 1) % len(polygon)])
            for index in range(len(polygon))
        )

    svg = _render(payload)
    points = _points("".join(_fill_paths(svg)))
    assert points
    # はみ出しうるのは帯の半幅ぶんだけ (交点で切っているので端点は輪郭上)。
    assert max(excursion(point) for point in points) <= _stroke_width_px(
        "pencil", CANVAS
    )


def test_scan_angle_comes_from_the_instruction_seed():
    """固定角だと作品内で揃って機械的に見えるので、走査角は seed 由来。"""
    angles = {_fill_scan_angle(seed) for seed in range(64)}
    assert len(angles) == 64
    assert all(0.0 <= angle <= math.pi for angle in angles)


def test_scanline_spacing_is_jittered_but_bounded():
    contour = [(100.0, 100.0), (900.0, 100.0), (900.0, 900.0), (100.0, 900.0)]
    spacing = 20.0
    segments = _scanline_segments(contour, 0.0, spacing, seed=4242)
    offsets = [segment[1][1] for segment in segments]
    gaps = [b - a for a, b in zip(offsets, offsets[1:])]
    assert gaps
    assert all(spacing * 0.87 <= gap <= spacing * 1.13 for gap in gaps)
    assert len(set(round(gap, 6) for gap in gaps)) > 1


def test_tiny_shape_degrades_to_region_fill():
    """走査線が 3 本に満たない微小な粒子は領域 fill のまま (消えない)。"""
    tiny = {
        "primitive": "circle",
        "center": [0.5, 0.5],
        "radius": 0.004,
        "weight": "pencil",
        "filled": True,
    }
    svg = _render(tiny)
    assert _fill_groups(svg) == []
    assert 'fill="#111111"' in svg


def test_rotring_keeps_the_region_fill():
    """製図ペンは輪郭と同じく塗りも機械のまま。"""
    svg = _render(SHAPES["circle"], weight="rotring", filled=True)
    assert _fill_groups(svg) == []
    assert 'fill="#111111"' in svg
    unfilled = _render(SHAPES["circle"], weight="rotring", filled=False)
    assert 'fill="none"' in unfilled
    assert 'fill="#111111"' not in unfilled


@pytest.mark.parametrize("primitive", ["line", "arc"])
def test_open_primitives_have_no_fill_strokes(primitive: str):
    payload = {
        "line": {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]},
        "arc": {
            "primitive": "arc",
            "center": [0.5, 0.5],
            "radius": 0.3,
            "angle_start": 0,
            "angle_end": 180,
        },
    }[primitive]
    svg = _render(payload, weight="pencil", filled=True)
    assert _fill_groups(svg) == []


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_fill_strokes_are_deterministic(name: str):
    payload = dict(SHAPES[name], weight="chalk", filled=True)
    assert _render(payload, render_seed=5) == _render(payload, render_seed=5)
    assert _render(payload, render_seed=5) != _render(payload, render_seed=6)


# --- B. surface のストローク化 --------------------------------------------


def test_surface_suppresses_the_material_fill():
    """塗り = 素材の既定の埋め方、surface = 明示的な版表現。両方は出さない。"""
    payload = dict(
        SHAPES["square"],
        weight="pencil",
        filled=True,
        surface={"texture": "hatch", "direction": "diagonal_falling"},
    )
    svg = _render(payload)
    assert _fill_groups(svg) == []
    assert "surface-stroke-v1" in svg


@pytest.mark.parametrize("texture", ["hatch", "crosshatch"])
def test_surface_hatch_is_played_as_strokes(texture: str):
    svg = _render(SHAPES["square"], weight="pencil", surface={"texture": texture})
    assert "surface-stroke-v1" in svg
    assert "hatch-spacing-" in svg
    # 幾何直線ではなくなる (地の枠や speck は <line> を使わない)。
    assert "<line" not in svg


@pytest.mark.parametrize("texture", ["stipple", "grain", "wash", "aquatint", "bleed"])
def test_surface_grains_stay_geometric(texture: str):
    """粒と滲みは筆致ではないので現状維持。"""
    svg = _render(SHAPES["square"], weight="pencil", surface={"texture": texture})
    assert "surface-stroke-v1" not in svg


def test_rotring_surface_hatch_stays_geometric():
    svg = _render(SHAPES["square"], weight="rotring", surface={"texture": "hatch"})
    assert "surface-stroke-v1" not in svg
    assert "<line" in svg


# --- C. 演奏されない variation を seed key に入れない ----------------------


INACTIVE_VARIATIONS = [
    {"quality": "none", "dimensions": ["position_x"]},
    {"quality": "wave", "dimensions": []},
    {"quality": "perlin", "dimensions": ["rotation"]},
    {"quality": "white", "dimensions": ["length"]},
]


@pytest.mark.parametrize("variation", INACTIVE_VARIATIONS)
@pytest.mark.parametrize("name", sorted(set(SHAPES) - {"cloudform"}))
def test_inactive_variation_does_not_change_the_performance(name: str, variation: dict):
    """演奏されない variation は seed を動かさない (バイト一致)。

    cloudform だけは quality / amplitude / frequency を輪郭生成器が常に消費する
    ので対象外 (dimensions だけが不活性。下の専用テストで見る)。
    """
    payload = dict(SHAPES[name], weight="pencil", filled=True)
    assert _render(payload) == _render(payload, variation=variation)


@pytest.mark.parametrize("variation", INACTIVE_VARIATIONS)
def test_inactive_variation_does_not_change_a_line(variation: dict):
    payload = {
        "primitive": "line",
        "from": [0.1, 0.5],
        "to": [0.9, 0.5],
        "weight": "crayon",
    }
    assert _render(payload) == _render(payload, variation=variation)


def test_cloudform_ignores_dimensions_but_keeps_the_other_fields():
    """cloudform は dimensions を見ず、残り 3 つを輪郭生成器の引数に使う。"""
    payload = dict(SHAPES["cloudform"], weight="pencil")
    base = {"quality": "perlin", "amplitude": "broad", "frequency": "high"}
    assert _render(payload, variation=base) == _render(
        payload, variation=dict(base, dimensions=["rotation"])
    )
    assert _render(payload, variation=base) != _render(
        payload, variation=dict(base, amplitude="fine")
    )


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_active_variation_still_changes_the_performance(name: str):
    """ゲートが開く variation は従来どおり演奏に効く。"""
    payload = dict(SHAPES[name], weight="pencil", filled=True)
    active = {
        "quality": "wave",
        "amplitude": "broad",
        "frequency": "medium",
        "dimensions": ["position_x", "position_y"],
    }
    assert _render(payload) != _render(payload, variation=active)


def test_pink_variation_keeps_amplitude_in_the_seed():
    """滲みは stdDeviation だけを使うので、amplitude の差だけが効く。"""
    payload = dict(SHAPES["circle"], weight="pencil")
    pink = {"quality": "pink", "amplitude": "fine", "dimensions": ["position_x"]}
    assert _render(payload, variation=pink) == _render(
        payload, variation=dict(pink, dimensions=["rotation"], frequency="high")
    )
    assert _render(payload, variation=pink) != _render(
        payload, variation=dict(pink, amplitude="broad")
    )


def test_fill_scan_spacing_has_a_floor():
    """完全被覆は狙わない。線幅 1.5 倍と canvas 比の大きい方を下限にする。"""
    for weight in HAND_WEIGHTS:
        ins = Instruction.model_validate(dict(SHAPES["circle"], weight=weight))
        spacing = _fill_scan_spacing(ins, CANVAS)
        assert spacing >= _stroke_width_px(weight, CANVAS) * 1.5
        assert spacing >= CANVAS.unit * 0.012
