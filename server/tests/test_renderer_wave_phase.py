"""v2.0.5: wave 揺らぎの seed 位相と、材質輪郭の演奏 seed 追随のテスト。

wave は sin の位相が固定だったため、同一 Score の演奏が render_seed に依存せず
決定的だった (perlin / pink / white は seed 依存)。位相を seed 由来にする変更と、
材質輪郭 (pencil / chalk / crayon / brush_*) が演奏 seed を混ぜる変更を検証する。
"""

import hashlib
import math
import re

import pytest

from inku_server.renderer import (
    AMPLITUDE_RATIO,
    _arc_points_with_variation,
    _edge_contour_with_variation,
    _sample_offset_periodic,
    _segment_count,
    _seed_for_instruction,
    render,
)
from inku_server.schema import Instruction, Score, Variation

from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect

CANVAS = canvas_size_for_aspect(None)
# 弧: 半径 200px が代表寸法 / 多角形: 800px 角の短辺 1/2 = 400px が代表寸法
ARC_AMP = AMPLITUDE_RATIO["broad"] * 200.0
POLY_AMP = AMPLITUDE_RATIO["broad"] * 400.0
EDGE_SEGMENTS = _segment_count(800.0, CANVAS)

WAVE = {
    "amplitude": "medium",
    "frequency": "medium",
    "quality": "wave",
    "dimensions": ["position_x", "position_y"],
}

WAVE_SHAPES: dict[str, dict] = {
    "line": {"primitive": "line", "from": [0.2, 0.2], "to": [0.8, 0.8]},
    "arc": {
        "primitive": "arc",
        "center": [0.5, 0.5],
        "radius": 0.2,
        "angle_start": 0,
        "angle_end": 270,
    },
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

# 材質輪郭を持つ weight のみを対象にする (variation なし)。
MATERIAL_SHAPES: dict[str, dict] = {
    "pencil_circle": {
        "primitive": "circle",
        "center": [0.5, 0.5],
        "radius": 0.2,
        "weight": "pencil",
    },
    "chalk_square": {
        "primitive": "square",
        "position": [0.3, 0.3],
        "size": [0.4, 0.4],
        "weight": "chalk",
    },
    "crayon_arc": {
        "primitive": "arc",
        "center": [0.5, 0.5],
        "radius": 0.2,
        "angle_start": 0,
        "angle_end": 270,
        "weight": "crayon",
    },
    "brush_thin_line": {
        "primitive": "line",
        "from": [0.2, 0.2],
        "to": [0.8, 0.8],
        "weight": "brush_thin",
    },
    "pencil_ellipse": {
        "primitive": "ellipse",
        "center": [0.5, 0.5],
        "size": [0.3, 0.2],
        "weight": "pencil",
    },
}

# v2.1 (比例レンダリング) で採取し直した render_seed=None 出力の sha256 (先頭 32 桁)。
# seed 未指定の演奏が不変であることの固定。v2.0.4 の値からの差分は speck 個数の
# 周長比例化と stroke 分割数の長さ比例化のみで、材質の寸法・dasharray・線幅は
# canvas.unit=1000 で以前とバイト一致する。
MATERIAL_NONE_SEED_DIGESTS = {
    "brush_thin_line": "c3e3c095b91b63b172c7b9f62ca14496",
    "chalk_square": "16acc45062fe0d6cdb6f4cd03fcf62c8",
    "crayon_arc": "adb61fda83813c20accd8ce80d2d7623",
    "pencil_circle": "fa729f4ea8d4d2868ea1338ab04eeb77",
    "pencil_ellipse": "7258a0d890266424bd6283b0175e6f32",
}


def _render(ins: dict, *, variation: dict | None = None, render_seed: int | None):
    payload = dict(ins)
    if variation is not None:
        payload["variation"] = variation
    score = Score.model_validate({"instructions": [payload]})
    return render(score, render_seed=render_seed)


def _digest(svg: str) -> str:
    """座標を 6 桁に丸めてから取るダイジェスト。

    生バイトは macOS と Linux で sin/cos の最終桁が食い違うことがあり
    (例: 430.32532431101913 と 430.3253243110191)、環境差でテストが割れる。
    ここで確かめたいのは演奏内容の同一性なので、表示桁を揃えてから比較する。
    """
    normalized = re.sub(
        r"\d+\.\d+", lambda m: f"{round(float(m.group(0)), 6):.6f}", svg
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _without_touch_filter(svg: str) -> str:
    """display 用 performance touch filter を取り除く。

    この filter は固定図形にも seed ごとの差を与えるため、素の比較では
    「seed で SVG が変わる」ことが常に真になってしまう。ここで見たいのは
    ジオメトリ (polyline / polygon / path / speck 座標) の差なので除外する。
    """
    svg = re.sub(
        r'<filter id="performance_touch_[^>]*>.*?</filter>', "", svg, flags=re.S
    )
    return re.sub(r'filter="url\(#performance_touch_[^"]*\)"', "", svg)


@pytest.mark.parametrize("primitive", sorted(WAVE_SHAPES))
def test_wave_geometry_follows_render_seed(primitive: str):
    """開曲線・閉輪郭のいずれでも、演奏 seed を変えると wave の山谷が動く。"""
    a = _render(WAVE_SHAPES[primitive], variation=WAVE, render_seed=111)
    b = _render(WAVE_SHAPES[primitive], variation=WAVE, render_seed=222)
    assert _without_touch_filter(a) != _without_touch_filter(b)


@pytest.mark.parametrize("primitive", sorted(WAVE_SHAPES))
def test_wave_is_deterministic_per_seed(primitive: str):
    """同一 (Score, seed) の演奏はバイト一致する。"""
    first = _render(WAVE_SHAPES[primitive], variation=WAVE, render_seed=111)
    replay = _render(WAVE_SHAPES[primitive], variation=WAVE, render_seed=111)
    assert first == replay


@pytest.mark.parametrize("frequency", ["slow", "medium", "high"])
@pytest.mark.parametrize("seed", [0, 7, 111, 222, 98765])
def test_wave_closed_contour_stays_closed(frequency: str, seed: int):
    """整数周波数の閉輪郭は位相導入後も継ぎ目 (t=1→0) で連続する。"""
    variation = Variation(
        amplitude="broad",
        frequency=frequency,
        quality="wave",
        dimensions=["radius"],
    )
    at_end = _sample_offset_periodic(1.0 - 1e-9, variation, seed, 0, ARC_AMP)
    at_start = _sample_offset_periodic(0.0, variation, seed, 0, ARC_AMP)
    assert abs(at_end - at_start) < 1e-3


@pytest.mark.parametrize("seed", [0, 7, 111, 222, 98765])
def test_wave_arc_endpoints_are_pinned(seed: int):
    """弧の両端点は位相導入後も固定 (touching 接点契約の維持)。"""
    variation = Variation(
        amplitude="broad",
        frequency="medium",
        quality="wave",
        dimensions=["radius"],
    )
    pts = _arc_points_with_variation(
        500.0, 500.0, 200.0, 0.0, 270.0, variation, seed, ARC_AMP, CANVAS
    )
    assert pts[0] == pytest.approx((700.0, 500.0))
    assert pts[-1] == pytest.approx((500.0, 700.0))
    interior_moved = any(
        abs(math.hypot(x - 500.0, y - 500.0) - 200.0) > 1.0 for x, y in pts[1:-1]
    )
    assert interior_moved


@pytest.mark.parametrize("seed", [0, 7, 111, 222, 98765])
def test_wave_polygon_corners_are_pinned(seed: int):
    """辺展開の角は位相導入後も固定。"""
    corners = [(100.0, 100.0), (900.0, 100.0), (900.0, 900.0), (100.0, 900.0)]
    variation = Variation(
        amplitude="broad",
        frequency="medium",
        quality="wave",
        dimensions=["position_x", "position_y"],
    )
    contour = _edge_contour_with_variation(corners, variation, seed, POLY_AMP, CANVAS)
    assert len(contour) == 4 * EDGE_SEGMENTS
    for i, corner in enumerate(corners):
        assert contour[i * EDGE_SEGMENTS] == pytest.approx(corner)


def test_wave_phase_differs_between_seeds_at_same_t():
    """位相そのものが seed で変わる (振幅・周波数の語彙は不変)。"""
    variation = Variation(
        amplitude="medium",
        frequency="medium",
        quality="wave",
        dimensions=["radius"],
    )
    samples = {
        seed: _sample_offset_periodic(0.13, variation, seed, 3, ARC_AMP)
        for seed in (111, 222, 333)
    }
    assert len(set(round(v, 9) for v in samples.values())) == 3


@pytest.mark.parametrize("name", sorted(MATERIAL_SHAPES))
def test_material_outline_follows_render_seed(name: str):
    """材質輪郭 (specks / 層の乱れ) が演奏 seed に追随する。"""
    a = _render(MATERIAL_SHAPES[name], render_seed=111)
    b = _render(MATERIAL_SHAPES[name], render_seed=222)
    assert _without_touch_filter(a) != _without_touch_filter(b)


@pytest.mark.parametrize("name", sorted(MATERIAL_SHAPES))
def test_material_outline_is_deterministic_per_seed(name: str):
    a = _render(MATERIAL_SHAPES[name], render_seed=111)
    b = _render(MATERIAL_SHAPES[name], render_seed=111)
    assert a == b


@pytest.mark.parametrize("name", sorted(MATERIAL_SHAPES))
def test_material_outline_none_seed_is_byte_compatible(name: str):
    """render_seed=None の演奏は main (v2.0.4) とバイト一致する。"""
    svg = _render(MATERIAL_SHAPES[name], render_seed=None)
    assert _digest(svg) == MATERIAL_NONE_SEED_DIGESTS[name]


def test_seed_for_instruction_ignores_none_performance_seed():
    """演奏 seed 未指定時は seed key が変わらない (後方互換の根拠)。"""
    ins = Instruction.model_validate(MATERIAL_SHAPES["pencil_circle"])
    assert _seed_for_instruction(ins) == _seed_for_instruction(ins, None)
    assert _seed_for_instruction(ins) != _seed_for_instruction(ins, 111)
