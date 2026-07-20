"""F-4: 弧・閉図形への variation 演奏のテスト。

render A/B 監査 (intent-audit) で SAME (variation 不演奏) と確定していた
circle / ellipse / triangle / square / arc (+polygon) が演奏されること、
および variation なしの既存出力が変わらないことを検証する。
"""

import math

import pytest

from inku_server.renderer import (
    SEGMENT_COUNT,
    _arc_points_with_variation,
    _edge_contour_with_variation,
    _sample_offset_periodic,
    render,
)
from inku_server.schema import Score, Variation

BASES: dict[str, dict] = {
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
    "arc": {
        "primitive": "arc",
        "center": [0.5, 0.5],
        "radius": 0.2,
        "angle_start": 0,
        "angle_end": 270,
    },
}


def _render_with(base: dict, variation: dict | None) -> str:
    ins = dict(base)
    if variation is not None:
        ins["variation"] = variation
    score = Score.model_validate({"instructions": [ins]})
    return render(score, render_seed=42)


@pytest.mark.parametrize("primitive", sorted(BASES))
@pytest.mark.parametrize("quality", ["perlin", "wave", "white"])
def test_contour_variation_is_performed(primitive: str, quality: str):
    base = BASES[primitive]
    plain = _render_with(base, None)
    varied = _render_with(
        base,
        {
            "amplitude": "medium",
            "frequency": "medium",
            "quality": quality,
            "dimensions": ["position_x", "position_y"],
        },
    )
    assert plain != varied


@pytest.mark.parametrize("primitive", ["circle", "arc"])
@pytest.mark.parametrize(
    "dimensions",
    [["position_x"], ["position_y"], ["radius"]],
)
def test_contour_variation_each_dimension(primitive: str, dimensions: list[str]):
    base = BASES[primitive]
    plain = _render_with(base, None)
    varied = _render_with(
        base,
        {
            "amplitude": "medium",
            "frequency": "medium",
            "quality": "perlin",
            "dimensions": dimensions,
        },
    )
    assert plain != varied


@pytest.mark.parametrize("primitive", sorted(BASES))
def test_gate_closed_output_unchanged(primitive: str):
    """quality=none や dims 対象外は演奏せず、既存出力とバイト一致する。"""
    base = BASES[primitive]
    plain = _render_with(base, None)
    quality_none = _render_with(
        base,
        {
            "amplitude": "medium",
            "frequency": "medium",
            "quality": "none",
            "dimensions": ["position_x", "position_y"],
        },
    )
    dims_out_of_scope = _render_with(
        base,
        {
            "amplitude": "medium",
            "frequency": "medium",
            "quality": "perlin",
            "dimensions": ["rotation"],
        },
    )
    assert plain == quality_none
    assert plain == dims_out_of_scope


@pytest.mark.parametrize("primitive", sorted(BASES))
def test_contour_variation_is_deterministic(primitive: str):
    base = BASES[primitive]
    variation = {
        "amplitude": "medium",
        "frequency": "medium",
        "quality": "perlin",
        "dimensions": ["position_x", "position_y"],
    }
    first = _render_with(base, variation)
    replay = _render_with(base, variation)
    assert first == replay


def test_pink_still_uses_blur_not_contour():
    """pink (滲み) は既存の blur 機構のまま。輪郭 polygon 化しない。"""
    varied = _render_with(
        BASES["circle"],
        {
            "amplitude": "medium",
            "frequency": "medium",
            "quality": "pink",
            "dimensions": ["position_x", "position_y"],
        },
    )
    assert "<circle" in varied
    assert "feGaussianBlur" in varied


def test_arc_endpoints_are_pinned():
    """弧の両端点は固定 (touching 接点契約の維持)。"""
    variation = Variation(
        amplitude="broad",
        frequency="medium",
        quality="perlin",
        dimensions=["radius"],
    )
    pts = _arc_points_with_variation(500.0, 500.0, 200.0, 0.0, 270.0, variation, 123)
    assert pts[0] == pytest.approx((700.0, 500.0))
    assert pts[-1] == pytest.approx((500.0, 700.0))
    # 内部点は理想弧から動いている
    interior_moved = any(
        abs(math.hypot(x - 500.0, y - 500.0) - 200.0) > 1.0 for x, y in pts[1:-1]
    )
    assert interior_moved


def test_polygon_corners_are_pinned():
    """辺展開の多角形は角を固定する。"""
    corners = [(100.0, 100.0), (900.0, 100.0), (900.0, 900.0), (100.0, 900.0)]
    variation = Variation(
        amplitude="broad",
        frequency="medium",
        quality="perlin",
        dimensions=["position_x", "position_y"],
    )
    contour = _edge_contour_with_variation(corners, variation, 123)
    assert len(contour) == 4 * SEGMENT_COUNT
    for i, corner in enumerate(corners):
        assert contour[i * SEGMENT_COUNT] == pytest.approx(corner)


@pytest.mark.parametrize("frequency", ["slow", "medium", "high"])
def test_periodic_sampler_is_continuous_at_seam(frequency: str):
    """閉輪郭の継ぎ目 (t=1→0) でオフセットが連続する。"""
    for quality in ("perlin", "wave"):
        variation = Variation(
            amplitude="broad",
            frequency=frequency,
            quality=quality,
            dimensions=["radius"],
        )
        at_end = _sample_offset_periodic(1.0 - 1e-9, variation, 99, 0)
        at_start = _sample_offset_periodic(0.0, variation, 99, 0)
        assert abs(at_end - at_start) < 1e-3
