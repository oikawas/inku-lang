import hashlib
import math
import re
from xml.etree import ElementTree

from inku_server.master_grid import MASTER_GRID_DECIMALS
from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.render_engines import current_render_engine
from inku_server.renderer import (
    _ellipse_perimeter,
    _speck_count,
    _clustered_pos,
    _expand_arrangement,
    _resolve_performance_score,
    new_render_seed,
    render,
)
from inku_server.schema import Instruction, Score

_MATERIAL_OUTLINE_ELEMENT = re.compile(r'<[a-z]+[^>]*class="material-outline"[^>]*/>')


def _ink_only(svg: str) -> str:
    """材質輪郭を落とした SVG。本体だけを数えたい検査はここを通す。

    engine 15 で `pen` — 既定の weight — が材質層を持ったので、素の要素を数える
    古い検査は装飾まで数えるようになった。抽出時に `material-outline` を除くのは
    `test_arc_strokes` / `test_touching` / `test_computer_touch` と同じ規律で、
    engine 15 で新たに必要になったのは既定の道具が裸でなくなったからである。
    """
    return _MATERIAL_OUTLINE_ELEMENT.sub("", svg)


def test_new_render_seed_is_javascript_safe_integer():
    for _ in range(100):
        seed = new_render_seed()
        assert 0 <= seed <= 2**53 - 1


def test_render_empty_score_has_background():
    svg = render(Score(instructions=[]))
    assert "<svg" in svg
    assert 'viewBox="0 0 1000 1000"' in svg
    assert "#ffffff" in svg


def test_render_seed_changes_touch_for_fixed_shapes_without_moving_geometry():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.2,
                    "filled": True,
                    "color": "red",
                }
            ]
        }
    )

    first = render(score, render_seed=29)
    replay = render(score, render_seed=29)
    alternate = render(score, render_seed=30)

    assert first == replay
    assert first != alternate
    assert 'id="performance_touch_29"' in first
    assert 'id="performance_touch_30"' in alternate
    assert 'cx="500.000000"' in first and 'cx="500.000000"' in alternate
    assert 'cy="500.000000"' in first and 'cy="500.000000"' in alternate


def test_render_seed_does_not_add_touch_filter_to_editable_profile():
    score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2}]}
    )

    svg = render(score, render_seed=29, svg_profile="editable")

    assert "performance_touch" not in svg
    assert "feDisplacementMap" not in svg


def test_render_canvas_aspect_plugin_changes_viewbox_without_stretching_circle():
    score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2}]}
    )

    svg = render(score, canvas_aspect="wide")

    assert 'viewBox="0 0 2350 1000"' in svg
    assert 'cx="1175.000000"' in svg
    assert 'cy="500.000000"' in svg
    assert 'r="200.000000"' in svg


def test_render_uses_score_canvas_when_no_explicit_aspect():
    score = Score.model_validate(
        {
            "canvas": "golden",
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}
            ],
        }
    )

    svg = render(score)

    assert 'viewBox="0 0 1618 1000"' in svg


def test_render_single_line_solid_pen_black():
    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.33], "to": [1.0, 0.33]}
            ]
        }
    )
    svg = render(score)
    assert "stroke-engine-v1" in svg
    assert "<path" in svg
    assert "#111111" in svg
    assert "stroke-dasharray" not in _ink_only(svg)


def test_render_wraps_primitives_in_canvas_clip():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [-0.2, 0.5],
                    "to": [1.2, 0.5],
                }
            ]
        }
    )
    svg = render(score)
    assert 'clip-path="url(#canvas-clip)"' in svg
    assert "<clipPath" in svg


def test_render_editable_svg_has_layer_groups_and_stable_ids():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "weight": "pencil",
                }
            ]
        }
    )

    svg = render(score, svg_profile="editable")

    assert "<title>inku render (editable SVG)</title>" in svg
    assert 'id="inku_artboard"' in svg
    assert 'id="layer_00_background"' in svg
    assert 'id="layer_10_content"' in svg
    assert 'id="instruction_000_line_black_pencil"' in svg
    assert 'id="mark_000_000_line"' in svg
    assert "clip-path" not in svg
    assert "filter=" not in svg


def test_render_compat_svg_is_portable_and_filter_free():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.12,
                    "weight": "chalk",
                    "variation": {
                        "quality": "pink",
                        "dimensions": ["position_x"],
                        "amplitude": "fine",
                    },
                }
            ]
        }
    )

    svg = render(score, svg_profile="compat")

    assert "<title>inku render (compat SVG)</title>" in svg
    assert 'id="mark_000_000_circle"' in svg
    assert "filter=" not in svg
    assert "<filter" not in svg


def test_render_polygon_outputs_svg_polygon():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "polygon",
                    "center": [0.5, 0.5],
                    "radius": 0.1,
                    "sides": 6,
                    "rotation": 15,
                }
            ]
        }
    )

    svg = render(score, svg_profile="editable")

    assert 'id="instruction_000_polygon_black_pen"' in svg
    assert 'id="mark_000_000_polygon"' in svg
    assert "<polygon" in svg


def _expected_specks(base: int, path_len_px: float) -> int:
    """周長比例化後の speck 個数 (検査の意図を保つため規則から算出する)。"""
    return _speck_count(base, path_len_px, canvas_size_for_aspect(None))


def test_render_dashed_line_has_dasharray():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "style": "dashed",
                }
            ]
        }
    )
    svg = render(score)
    assert "stroke-dasharray" in svg
    assert "12.000000,8.000000" in svg


def test_render_pencil_line_uses_material_texture():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "weight": "pencil",
                }
            ]
        }
    )
    svg = render(score)
    assert 'fill-opacity="0.660000"' in svg
    # Material strata are aperiodic-dashed polylines along the centreline.
    assert svg.count("<polyline") >= 2
    assert "stroke-dasharray=" in svg
    assert 'id="texture-pencil"' in svg
    assert 'filter="url(#texture-pencil)"' in svg
    assert svg.count("<circle") >= _expected_specks(18, 1000.0)


def test_render_chalk_line_uses_blurred_powder_texture():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "weight": "chalk",
                }
            ]
        }
    )
    svg = render(score)
    assert 'id="texture-chalk"' in svg
    assert 'filter="url(#texture-chalk)"' in svg
    assert svg.count("<polyline") >= 2
    assert "stroke-dasharray=" in svg
    assert "<feTurbulence" in svg
    assert "<feDisplacementMap" in svg
    assert svg.count("<circle") >= _expected_specks(34, 1000.0)


def test_render_crayon_line_adds_rubbed_layers():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "weight": "crayon",
                }
            ]
        }
    )
    svg = render(score)
    # Material texture layers ride the (gestured) centreline as polylines now.
    assert svg.count("<polyline") >= 4
    assert "stroke-engine-v1" in svg
    assert "stroke-dasharray=" in svg
    assert 'id="texture-crayon"' in svg
    assert svg.count("<circle") >= _expected_specks(26, 1000.0)


def test_render_scatter_path_wave_places_items_on_trace():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.01,
                    "arrangement": {
                        "count": 5,
                        "layout": "scatter",
                        "path": "wave",
                        "margin": 0.1,
                    },
                }
            ]
        }
    )
    svg = render(score)
    assert 'cx="100.000000"' in svg
    assert 'cx="300.000000"' in svg
    assert 'cx="500.000000"' in svg
    assert 'cx="700.000000"' in svg
    assert 'cx="900.000000"' in svg
    assert _ink_only(svg).count("<circle") == 5


def test_render_rhythm_spacing_breaks_equal_repetition():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.01,
                    "arrangement": {
                        "count": 5,
                        "layout": "horizontal",
                        "margin": 0.1,
                        "rhythm_spacing": "syncopated",
                    },
                }
            ]
        }
    )

    svg = render(score)
    root = ElementTree.fromstring(_ink_only(svg))
    xs = [
        float(node.attrib["cx"])
        for node in root.iter()
        if node.tag.endswith("circle") and "cx" in node.attrib
    ]
    gaps = [round(xs[index + 1] - xs[index], 3) for index in range(len(xs) - 1)]
    assert len(xs) == 5
    assert len(set(gaps)) > 1


def test_render_arrangement_path_right_half_constrains_x():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.01,
                    "arrangement": {
                        "count": 4,
                        "layout": "scatter",
                        "path": "right_half",
                        "margin": 0.1,
                    },
                }
            ]
        }
    )
    svg = render(score)
    assert 'cx="300.' not in svg
    assert 'cx="100.' not in svg
    assert _ink_only(svg).count("<circle") == 4


def test_render_clustered_arrangement_uses_fade_and_preserves_elements():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.49, 0.49],
                    "size": [0.014, 0.014],
                    "color": "black",
                    "arrangement": {
                        "count": 24,
                        "layout": "scatter",
                        "density": "high",
                        "cluster_count": 5,
                        "fade": "outward",
                        "preserve_space": True,
                        "margin": 0.2,
                    },
                }
            ]
        }
    )

    svg = render(score)

    assert svg.count("<rect") >= 25
    # v2.2 (engine 8): 手描き weight の閉図形は輪郭を帯で描くので、輪郭側の
    # 濃度は stroke-opacity ではなく帯の fill-opacity に載る。
    assert 'fill-opacity="0.400000"' in svg
    # v2.3 (engine 9): `filled` の復権により、塗らない図形には fade の塗り濃度
    # (0.22) は載らない。fade は輪郭帯の濃度として読める。
    assert 'fill-opacity="0.22"' not in svg


def test_clustered_positions_do_not_form_constant_radius_ring():
    points = [
        _clustered_pos(
            i,
            48,
            12345,
            0.2,
            "none",
            cluster_count=1,
            density="high",
            preserve_space=True,
        )
        for i in range(48)
    ]
    cx = sum(x for x, _ in points) / len(points)
    cy = sum(y for _, y in points) / len(points)
    distances = sorted(math.hypot(x - cx, y - cy) for x, y in points)

    assert distances[-1] > distances[0] * 2.5


def test_render_sensory_layers_have_distinct_opacity():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.2],
                    "size": [0.42, 0.12],
                    "color": "white",
                    "filled": True,
                    "color_hint": "柔らかな光",
                },
                {
                    "primitive": "ellipse",
                    "center": [0.55, 0.55],
                    "size": [0.05, 0.024],
                    "color": "green",
                    "filled": True,
                    "color_hint": "沈丁花の香り",
                },
            ]
        }
    )
    svg = render(score)

    assert 'fill-opacity="0.140000"' in svg
    assert 'fill-opacity="0.200000"' in svg


def test_render_brush_lines_use_layered_material_texture():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.4],
                    "to": [1.0, 0.4],
                    "weight": "brush_thin",
                },
                {
                    "primitive": "line",
                    "from": [0.0, 0.6],
                    "to": [1.0, 0.6],
                    "weight": "brush_thick",
                },
            ]
        }
    )
    svg = render(score)
    # Material texture layers ride the (gestured) centreline as polylines now.
    assert svg.count("<polyline") >= 5
    assert svg.count("stroke-engine-v1") == 2
    assert "stroke-dasharray=" in svg
    assert 'id="texture-brush_thick"' in svg


def test_render_circle_material_applies_outline_texture():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.18,
                    "weight": "chalk",
                }
            ]
        }
    )
    svg = render(score)
    assert svg.count("<circle") >= 2 + _expected_specks(36, 2 * math.pi * 180.0)
    assert 'id="texture-chalk"' in svg
    assert 'stroke-dasharray="8.000000,12.000000,1.000000,8.000000"' in svg


def test_render_ellipse_material_applies_outline_texture():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.4, 0.2],
                    "weight": "crayon",
                }
            ]
        }
    )
    svg = render(score)
    assert svg.count("<ellipse") >= 4
    assert svg.count("<circle") >= _expected_specks(28, _ellipse_perimeter(200.0, 100.0))
    assert 'id="texture-crayon"' in svg
    assert 'stroke-dasharray="2.000000,5.000000,9.000000,7.000000"' in svg


def test_render_square_material_applies_outline_texture():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.3, 0.3],
                    "size": [0.3, 0.3],
                    "weight": "pencil",
                }
            ]
        }
    )
    svg = render(score)
    assert svg.count("<rect") >= 4
    assert svg.count("<circle") >= _expected_specks(18, 4 * 300.0)
    assert 'id="texture-pencil"' in svg
    assert 'stroke-dasharray="1.000000,7.000000"' in svg


def test_render_circle():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.2,
                    "color": "red",
                }
            ]
        }
    )
    svg = render(score)
    assert "<circle" in svg
    assert 'cx="500' in svg
    assert 'cy="500' in svg
    assert 'r="200' in svg
    assert "#a2342a" in svg


def test_render_ellipse():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.4, 0.2],
                    "color": "blue",
                }
            ]
        }
    )
    svg = render(score)
    assert "<ellipse" in svg
    assert 'cx="500' in svg
    assert 'cy="500' in svg
    assert 'rx="200' in svg
    assert 'ry="100' in svg
    assert "#2c3e91" in svg


def test_render_square():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.1, 0.1],
                    "size": [0.3, 0.3],
                }
            ]
        }
    )
    svg = render(score)
    assert "<rect" in svg
    assert 'x="100' in svg
    assert 'y="100' in svg
    assert 'width="300' in svg
    assert 'height="300' in svg


def test_render_triangle():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "triangle",
                    "position": [0.0, 0.0],
                    "size": [1.0, 1.0],
                    "color": "green",
                }
            ]
        }
    )
    svg = render(score)
    assert "<polygon" in svg
    assert "500" in svg
    assert "1000" in svg
    assert "#2f6b3a" in svg


def test_render_square_rotation_applies_center_transform():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.35, 0.35],
                    "size": [0.3, 0.3],
                    "rotation": -30,
                }
            ]
        }
    )
    svg = render(score)
    assert "<rect" in svg
    assert 'transform="rotate(-30.000000,500.000000,500.000000)"' in svg


def test_render_line_rotation_applies_midpoint_transform():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.25, 0.5],
                    "to": [0.75, 0.5],
                    "rotation": 45,
                }
            ]
        }
    )
    svg = render(score)
    assert "<path" in svg
    assert 'transform="rotate(45.000000,500.000000,500.000000)"' in svg


def test_render_color_hint_uses_catalog_palette_match():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.2,
                    "color": "red",
                    "color_hint": "桜色",
                }
            ]
        }
    )
    svg = render(score, color_map={"palette:Rose Pastel": "#ffc1cc"})
    assert "#ffc1cc" in svg
    assert "#a2342a" not in svg


def test_render_color_hint_falls_back_to_abstract_color():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "color": "blue",
                    "color_hint": "透明な気配",
                }
            ]
        }
    )
    svg = render(score)
    assert "#2c3e91" in svg


def test_ellipse_missing_size_raises():
    import pytest

    score = Score(instructions=[Instruction(primitive="ellipse", center=(0.5, 0.5))])
    with pytest.raises(ValueError):
        render(score)


def test_variation_schema_roundtrip():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.33],
                    "to": [1.0, 0.33],
                    "weight": "pencil",
                    "variation": {
                        "amplitude": "fine",
                        "frequency": "high",
                        "quality": "perlin",
                        "dimensions": ["position_y"],
                    },
                }
            ]
        }
    )
    assert score.instructions[0].variation is not None
    assert score.instructions[0].variation.amplitude == "fine"


def test_render_arc_quarter():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.5, 0.5],
                    "radius": 0.3,
                    "angle_start": 0.0,
                    "angle_end": 90.0,
                }
            ]
        }
    )
    svg = render(score)
    assert "<path" in svg
    # 始点: center + r east = (0.8*1000, 0.5*1000) = (800, 500)
    assert "M 800.000000 500.000000" in svg
    # 終点: center + r north (y-flip) = (500, 0.5*1000 - 300) = (500, 200)
    assert "A 300.000000 300.000000 0 0 0 500.000000 200.000000" in svg


def test_render_arc_half_upper():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.5, 0.5],
                    "radius": 0.2,
                    "angle_start": 0.0,
                    "angle_end": 180.0,
                }
            ]
        }
    )
    svg = render(score)
    # delta=180 is edge: large_arc=0, then 180 exactly → 0。sweep=0 (CCW)
    assert "<path" in svg


def test_arc_missing_angles_raises():
    import pytest

    score = Score(
        instructions=[Instruction(primitive="arc", center=(0.5, 0.5), radius=0.3)]
    )
    with pytest.raises(ValueError, match="angle_start"):
        render(score)


def test_render_line_with_perlin_variation_emits_variable_width_path():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.333],
                    "to": [1.0, 0.333],
                    "variation": {
                        "amplitude": "fine",
                        "frequency": "medium",
                        "quality": "perlin",
                        "dimensions": ["position_y"],
                    },
                }
            ]
        }
    )
    svg = render(score)
    assert "<path" in svg
    assert "<polyline" not in _ink_only(svg)


def test_render_line_with_wave_variation_emits_variable_width_path():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.5, 0.0],
                    "to": [0.5, 1.0],
                    "variation": {
                        "amplitude": "broad",
                        "frequency": "medium",
                        "quality": "wave",
                        "dimensions": ["position_x"],
                    },
                }
            ]
        }
    )
    svg = render(score)
    assert "<path" in svg
    assert "<polyline" not in _ink_only(svg)


def test_render_line_variation_is_deterministic():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "variation": {
                        "amplitude": "medium",
                        "frequency": "high",
                        "quality": "perlin",
                        "dimensions": ["position_y"],
                    },
                }
            ]
        }
    )
    assert render(score) == render(score)


def test_render_line_quality_none_still_straight():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "variation": {
                        "amplitude": "fine",
                        "frequency": "medium",
                        "quality": "none",
                        "dimensions": ["position_y"],
                    },
                }
            ]
        }
    )
    svg = render(score)
    assert "<path" in svg
    assert "<polyline" not in _ink_only(svg)


def test_line_missing_endpoints_uses_default():
    score = Score(instructions=[Instruction(primitive="line")])
    svg = render(score)
    assert "<path" in svg


def test_render_circle_with_pink_variation_emits_blur_filter():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.2,
                    "variation": {"quality": "pink", "amplitude": "medium"},
                }
            ]
        }
    )
    svg = render(score)
    assert "feGaussianBlur" in svg
    # 滲みは図形寸法比なので filter id に std 値が入る (r=200 * 0.03 = 6.0px)
    assert 'filter="url(#blur-medium-60)"' in svg
    assert 'stdDeviation="6.000000"' in svg
    assert "<circle" in svg
    assert "<polyline" not in svg


def test_render_textured_pink_variation_keeps_valid_svg_filter_attribute():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "triangle",
                    "position": [0.4, 0.4],
                    "size": [0.2, 0.2],
                    "weight": "chalk",
                    "variation": {"quality": "pink", "amplitude": "medium"},
                }
            ]
        }
    )
    svg = render(score)
    ElementTree.fromstring(svg)
    # v2.2 (engine 8): 塗り本体と輪郭の帯がそれぞれ質感 filter を持つ。
    # engine 15 で triangle にも材質輪郭が届いた分だけ 2 つ増え、square / circle と
    # 同じ 4 になった (どちらも以前から 4 だった)。
    assert svg.count('filter="url(#texture-chalk)"') == 4
    assert svg.count('filter="url(#blur-medium)"') == 0


def test_render_line_with_pink_variation_emits_blur_not_polyline():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "variation": {
                        "quality": "pink",
                        "amplitude": "fine",
                        "dimensions": ["position_y"],
                    },
                }
            ]
        }
    )
    svg = render(score)
    assert "feGaussianBlur" in svg
    assert "<path" in svg
    assert "<polyline" not in _ink_only(svg)


def test_render_pink_variation_deterministic():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.3, 0.3],
                    "size": [0.2, 0.4],
                    "variation": {"quality": "pink", "amplitude": "broad"},
                }
            ]
        }
    )
    assert render(score) == render(score)


def test_render_presence_layer_is_abstract_and_filter_free():
    score = Score.model_validate(
        {
            "presence": {
                "kind": "figure_like",
                "intensity": "medium",
                "center": [0.56, 0.52],
                "symmetry": "bilateral",
                "gaze_pressure": "medium",
                "contour_density": "medium",
            },
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.3, 0.12],
                    "color": "blue",
                }
            ],
        }
    )

    svg = render(score, svg_profile="editable")

    ElementTree.fromstring(svg)
    assert 'id="layer_20_presence"' in svg
    assert 'id="presence_layer"' in svg
    assert "filter=" not in svg
    assert "eye" not in svg.lower()
    assert "face" not in svg.lower()
    assert "animal" not in svg.lower()


def test_render_omits_presence_layer_when_absent():
    svg = render(Score.model_validate({"instructions": []}), svg_profile="editable")

    assert 'id="presence_layer"' not in svg


def test_render_presence_layer_gets_subtler_when_scene_is_dense():
    sparse = Score.model_validate(
        {
            "presence": {
                "kind": "figure_like",
                "intensity": "medium",
                "symmetry": "bilateral",
            },
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}
            ],
        }
    )
    dense = Score.model_validate(
        {
            "presence": {
                "kind": "figure_like",
                "intensity": "medium",
                "symmetry": "bilateral",
            },
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "arrangement": {"count": 160, "layout": "vertical"},
                }
            ],
        }
    )

    sparse_svg = render(sparse)
    dense_svg = render(dense)

    assert 'stroke-opacity="0.172200"' in sparse_svg
    assert 'stroke-opacity="0.089544"' in dense_svg


def test_render_color_cycle_preserves_effect_hint_opacity():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.3, 0.1],
                    "color": "black",
                    "color_hint": "透明な膜; white restored in color_cycle from DDL color intent",
                    "arrangement": {
                        "count": 2,
                        "layout": "horizontal",
                        "color_cycle": ["black", "white"],
                    },
                }
            ],
        }
    )

    svg = render(score)

    # v2.3 (engine 9): 塗らない図形 (filled 未指定) では膜の濃度は輪郭帯に載る。
    assert svg.count('fill-opacity="0.260000"') == 2
    assert 'fill="#111111"' in svg
    assert 'fill="#ffffff"' in svg


def test_render_region_uses_seed_for_reproducible_macro_variation():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "at": {"region": [0.2, 0.2, 0.8, 0.8]},
                    "radius": 0.04,
                }
            ]
        }
    )

    svg_a = render(score, render_seed=101)
    svg_b = render(score, render_seed=101)
    svg_c = render(score, render_seed=202)

    assert svg_a == svg_b
    assert svg_a != svg_c


def test_render_not_touching_relation_moves_second_mark_away_from_previous():
    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.08},
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.03,
                    "relation": {"type": "not_touching", "gap": "narrow"},
                },
            ]
        }
    )

    svg = render(score, render_seed=5)

    assert svg.count("<circle") >= 2
    assert _ink_only(svg).count('cx="500.000000"') == 1


def test_render_cutting_relation_crosses_previous_line_center():
    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5]},
                {
                    "primitive": "line",
                    "from": [0.1, 0.1],
                    "to": [0.2, 0.1],
                    "relation": {"type": "cutting"},
                },
            ]
        }
    )

    resolved = _resolve_performance_score(score, 7)
    first, second = resolved.instructions

    assert first.from_ == (0.2, 0.5)
    assert first.to == (0.8, 0.5)
    assert second.from_ is not None and second.to is not None
    assert _segments_intersect(first.from_, first.to, second.from_, second.to)


def _segments_intersect(p1, p2, p3, p4) -> bool:
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])

    d1 = ccw(p3, p4, p1)
    d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3)
    d4 = ccw(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True
    return False


def test_not_touching_relation_never_overlaps_across_seeds():
    for seed in range(1, 101):
        score = Score.model_validate(
            {
                "instructions": [
                    {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.08},
                    {
                        "primitive": "circle",
                        "center": [0.5, 0.5],
                        "radius": 0.05,
                        "relation": {"type": "not_touching", "gap": "narrow"},
                    },
                ]
            }
        )
        resolved = _resolve_performance_score(score, seed)
        first, second = resolved.instructions
        distance = math.hypot(
            first.center[0] - second.center[0], first.center[1] - second.center[1]
        )
        assert distance >= first.radius + second.radius, (
            f"seed={seed} overlapped: distance={distance}"
        )


def test_cutting_relation_always_crosses_previous_line_across_seeds():
    for seed in range(1, 101):
        score = Score.model_validate(
            {
                "instructions": [
                    {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5]},
                    {
                        "primitive": "line",
                        "from": [0.1, 0.1],
                        "to": [0.2, 0.1],
                        "relation": {"type": "cutting"},
                    },
                ]
            }
        )
        resolved = _resolve_performance_score(score, seed)
        first, second = resolved.instructions
        assert _segments_intersect(
            tuple(first.from_), tuple(first.to), tuple(second.from_), tuple(second.to)
        ), f"seed={seed} did not cross"


def test_between_relation_places_within_previous_pair_neighborhood_across_seeds():
    for seed in range(1, 101):
        score = Score.model_validate(
            {
                "instructions": [
                    {"primitive": "circle", "center": [0.3, 0.3], "radius": 0.04},
                    {"primitive": "circle", "center": [0.7, 0.7], "radius": 0.04},
                    {
                        "primitive": "circle",
                        "center": [0.5, 0.5],
                        "radius": 0.03,
                        "relation": {"type": "between", "gap": "medium"},
                    },
                ]
            }
        )
        resolved = _resolve_performance_score(score, seed)
        first, second, third = resolved.instructions
        margin = 0.15
        x0, x1 = sorted((first.center[0], second.center[0]))
        y0, y1 = sorted((first.center[1], second.center[1]))
        assert x0 - margin <= third.center[0] <= x1 + margin, (
            f"seed={seed} x out of neighborhood: {third.center}"
        )
        assert y0 - margin <= third.center[1] <= y1 + margin, (
            f"seed={seed} y out of neighborhood: {third.center}"
        )


def test_surface_schema_accepts_canvas_ground_and_clamps_units():
    score = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {
                    "material": "paper",
                    "tone": "off_white",
                    "grain": "fine",
                    "density": 2.0,
                    "opacity": -1.0,
                },
            },
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.16,
                    "filled": True,
                    "surface": {
                        "texture": "wash",
                        "density": 1.5,
                        "opacity": 0.45,
                        "bleed": -0.3,
                    },
                }
            ],
        }
    )

    assert score.canvas.ground.density == 1.0
    assert score.canvas.ground.opacity == 0.0
    assert score.instructions[0].surface.density == 1.0
    assert score.instructions[0].surface.bleed == 0.0


def test_render_display_canvas_ground_uses_filter_behind_content():
    score = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {"material": "paper", "tone": "off_white", "grain": "fine"},
            },
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}
            ],
        }
    )

    svg = render(score, render_seed=123)

    assert 'id="ground_texture_' in svg
    assert "<feTurbulence" in svg
    root = ElementTree.fromstring(svg)
    texture_rects = [
        element
        for element in root.iter()
        if element.tag.endswith("rect")
        and element.attrib.get("fill") == "#777777"
        and "ground_texture_" in element.attrib.get("filter", "")
    ]
    assert len(texture_rects) == 1
    assert 0.02 <= float(texture_rects[0].attrib["opacity"]) <= 0.18
    assert 'tableValues="0 1"' in svg
    assert any(
        element.tag.endswith("rect")
        and element.attrib.get("fill") == "#f7f3e8"
        and element.attrib.get("opacity") == "0.980000"
        for element in root.iter()
    )
    assert svg.index('id="layer_01_canvas_ground"') < svg.index(
        '<g clip-path="url(#canvas-clip)"'
    )


def test_canvas_ground_non_display_profiles_remain_filter_free():
    score = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {"material": "paper", "tone": "off_white", "grain": "fine"},
            },
            "instructions": [],
        }
    )

    editable = render(score, svg_profile="editable", render_seed=123)
    compat = render(score, svg_profile="compat", render_seed=123)

    assert '<filter id="ground_texture_' not in editable
    assert '<filter id="ground_texture_' not in compat
    for svg in (editable, compat):
        root = ElementTree.fromstring(svg)
        assert any(
            element.tag.endswith("rect")
            and element.attrib.get("fill") == "#f7f3e8"
            and element.attrib.get("opacity") == "0.980000"
            for element in root.iter()
        )


def test_render_display_surface_stipple_follows_the_shape_without_a_clip():
    """engine 16: 粒は輪郭の内側から引くので display の clipPath が要らない。

    engine 15 までは bbox に一様乱数で撒いてはみ出した分を display だけが
    clipPath で隠しており、editable では図形の外に粒が出ていた。
    """
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.16,
                    "filled": True,
                    "surface": {"texture": "stipple", "density": 0.5, "opacity": 0.3},
                }
            ]
        }
    )

    svg = render(score, render_seed=123)

    assert 'id="surface_000_000_stipple"' in svg
    assert "clip_surface_000_000_stipple" not in svg
    assert svg.count("surface-stroke-v1") > 10


def test_render_editable_surface_has_stable_group_id_without_filters():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.35, 0.35],
                    "size": [0.3, 0.3],
                    "filled": True,
                    "surface": {"texture": "hatch", "direction": "diagonal_falling"},
                }
            ]
        }
    )

    svg = render(score, svg_profile="editable", render_seed=123)

    assert 'id="surface_000_000_hatch"' in svg
    # v2.3 (engine 9): ハッチも材質エンジンを通るので幾何直線ではなく帯になる。
    assert "surface-stroke-v1" in svg
    assert "<filter" not in svg
    assert "clip-path" not in svg


def test_render_compat_surface_degrades_without_filter_or_clip_path():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.4, 0.22],
                    "filled": True,
                    "surface": {"texture": "wash", "density": 0.3, "opacity": 0.45},
                }
            ]
        }
    )

    svg = render(score, svg_profile="compat", render_seed=123)

    assert 'id="surface_000_000_wash"' in svg
    assert "<filter" not in svg
    assert "clip-path" not in svg


def test_surface_texture_seed_is_deterministic_and_performance_seed_sensitive():
    score = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {"material": "paper", "grain": "fine"},
            },
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.16,
                    "filled": True,
                    "surface": {"texture": "grain", "density": 0.5},
                }
            ],
        }
    )

    svg_a = render(score, svg_profile="editable", render_seed=123)
    svg_b = render(score, svg_profile="editable", render_seed=123)
    svg_c = render(score, svg_profile="editable", render_seed=456)

    assert svg_a == svg_b
    assert svg_a != svg_c
    assert "surface_000_000_grain" in svg_c


def test_render_engine_reports_texture_metadata():
    score = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {"material": "paper", "tone": "warm", "grain": "medium"},
            },
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.16,
                    "filled": True,
                    "surface": {"texture": "wash", "density": 0.3, "opacity": 0.45},
                }
            ],
        }
    )

    result = current_render_engine().render(
        score, svg_profile="compat", render_seed=123
    )

    assert result.metadata["render_texture_version"] == "1"
    assert result.metadata["render_texture_profile"] == "compat"
    assert result.metadata["texture_degraded"] is True
    assert result.metadata["render_canvas_ground"]["material"] == "paper"
    assert result.metadata["render_surface_textures"][0]["texture"] == "wash"


def _assert_centers(
    items: list[Instruction], expected: list[tuple[float, float]]
) -> None:
    centers = [item.center for item in items]
    assert all(center is not None for center in centers)
    assert len(centers) == len(expected)
    for center, target in zip(centers, expected):
        assert center is not None
        assert math.isclose(center[0], target[0])
        assert math.isclose(center[1], target[1])


def _grid_circle(**arrangement: object) -> Instruction:
    return Instruction.model_validate(
        {
            "primitive": "circle",
            "center": [0.5, 0.5],
            "radius": 0.01,
            "arrangement": {"count": 1, "layout": "grid", "jitter": 0, **arrangement},
        }
    )


def test_grid_explicit_rows_and_cols_override_count():
    expanded = _expand_arrangement(_grid_circle(rows=2, cols=3), performance_seed=123)

    assert len(expanded) == 6
    _assert_centers(
        expanded,
        [
            (7 / 30, 0.3),
            (0.5, 0.3),
            (23 / 30, 0.3),
            (7 / 30, 0.7),
            (0.5, 0.7),
            (23 / 30, 0.7),
        ],
    )


def test_grid_count_estimates_rows_and_cols_and_honors_margin():
    instruction = _grid_circle(count=5, margin=0.2)
    expanded = _expand_arrangement(instruction, performance_seed=123)

    assert len(expanded) == 6
    assert all(0.2 <= item.center[0] <= 0.8 for item in expanded if item.center)
    assert all(0.2 <= item.center[1] <= 0.8 for item in expanded if item.center)


def test_grid_uses_at_region_instead_of_margin():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    **_grid_circle(rows=2, cols=2, margin=0.4).model_dump(
                        by_alias=True
                    ),
                    "at": {"region": [0.1, 0.2, 0.5, 0.8]},
                }
            ]
        }
    )

    resolved = _resolve_performance_score(score, 123)
    expanded = _expand_arrangement(resolved.instructions[0], performance_seed=123)

    _assert_centers(
        expanded,
        [
            (0.2, 0.35),
            (0.4, 0.35),
            (0.2, 0.65),
            (0.4, 0.65),
        ],
    )
    assert all(item.at is None for item in expanded)


def test_grid_jitter_is_deterministic_and_seed_sensitive():
    instruction = _grid_circle(count=16, jitter=0.8)

    first = _expand_arrangement(instruction, performance_seed=123)
    replay = _expand_arrangement(instruction, performance_seed=123)
    alternate = _expand_arrangement(instruction, performance_seed=456)

    assert [item.center for item in first] == [item.center for item in replay]
    assert [item.center for item in first] != [item.center for item in alternate]


def test_grid_rhythm_changes_both_axis_spacing():
    regular = _expand_arrangement(_grid_circle(rows=3, cols=3), performance_seed=123)
    loose = _expand_arrangement(
        _grid_circle(rows=3, cols=3, rhythm_spacing="loose"),
        performance_seed=123,
    )

    assert [item.center for item in regular] != [item.center for item in loose]
    assert len({item.center[0] for item in loose if item.center}) == 3
    assert len({item.center[1] for item in loose if item.center}) == 3


def test_grid_variation_uses_distinct_per_element_phases():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.45, 0.48],
                    "to": [0.55, 0.52],
                    "variation": {
                        "amplitude": "fine",
                        "frequency": "high",
                        "quality": "wave",
                        "dimensions": ["position_y"],
                    },
                    "arrangement": {
                        "count": 4,
                        "layout": "grid",
                        "rows": 2,
                        "cols": 2,
                        "jitter": 0,
                    },
                }
            ]
        }
    )

    root = ElementTree.fromstring(render(score, svg_profile="compat", render_seed=123))
    paths = [
        node.attrib["d"]
        for node in root.iter()
        if node.tag.endswith("path") and node.attrib.get("fill") == "#111111"
    ]

    assert len(paths) == 4
    assert len(set(paths)) == 4


def test_legacy_arrangement_layouts_keep_golden_output():
    layouts = ("horizontal", "vertical", "radial", "scatter")
    rendered = []
    for layout in layouts:
        score = Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "circle",
                        "center": [0.5, 0.5],
                        "radius": 0.05,
                        "arrangement": {"count": 5, "layout": layout},
                    }
                ]
            }
        )
        rendered.append(render(score, svg_profile="compat", render_seed=123))

    digest = hashlib.sha256("".join(rendered).encode()).hexdigest()
    # engine 12 (エンベロープの脱・規則化 + 中心線ジェスチャ) で再採取。
    # 幅エンベロープが sin(pi t) の対称な山から _edge_window * _swell へ変わり、
    # 中心線に低周波のジェスチャが乗った分だけ値が動く。書き出される数値の個数は
    # engine 11 と同じ 1444 個で、動いたのは値だけである。
    # engine 10 まではこのダイジェストが素のバイト列だったため macOS でしか通らな
    # かった。全数値がグリッドに載ったので、以後はどの OS でも同じ値になる。
    # engine 15 (演奏 seed の allowlist 化 + 材質輪郭の距離是正) で再採取。
    # ここは既定 weight の pen を使うので、pen が材質輪郭を持った分も入っている。
    # engine 16 段 3 (太さの軸) で再採取。`thinness` が演奏 seed の allowlist に
    # 入った (C-7) ので、値が既定の None でも seed 鍵が変わる。幅そのものは
    # 動いていない (thinness=None の倍率は 1.0)。
    # engine 19 (地の抵抗) で再採取。既定 weight の pen は紙に弱く触れる
    # (吸う 0.15 / 弾く 0.15) ので幅が動く。書き出される数値は 1444 個から
    # 1724 個へ増えたが、これは墨が切れて subpath が増えたぶんであり、
    # 要素は 1 つも増えていない (`test_ground_resistance.py` が留めている)。
    assert digest == "a81beef258f526fc7066b09b17e77dff1d01a0888c8eca8ccc1db8a293c23a8d"


def test_every_emitted_number_sits_on_the_master_grid():
    """出力のどの数値もマスターグリッドを超える桁を持たない。

    書き出し箇所を一つずつ直す方式は漏れが黙って残る。素の float を書く経路が
    後から足されたら、ここで落ちる。engine 10 では points / cx / cy が 17 桁を
    書いており、それが macOS と Linux でコーパスが割れる原因だった。
    """
    shapes = (
        {"primitive": "polygon", "center": [0.5, 0.5], "radius": 0.25, "sides": 7},
        {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.24, "filled": True},
        {"primitive": "arc", "center": [0.5, 0.5], "radius": 0.27,
         "angle_start": 15.0, "angle_end": 285.0, "weight": "chalk"},
        {"primitive": "line", "from": [0.18, 0.5], "to": [0.82, 0.5],
         "weight": "brush_thick",
         "variation": {"amplitude": "broad", "frequency": "high", "quality": "perlin",
                       "dimensions": ["position_x", "position_y"]}},
    )
    off_grid = []
    checked = 0
    for shape in shapes:
        score = Score.model_validate({"instructions": [dict(shape)]})
        for profile in ("editable", "compat", "display"):
            svg = render(score, svg_profile=profile, render_seed=12345)
            for name, value in re.findall(r'([\w:-]+)="([^"]*)"', svg):
                # version は SVG 文書の版 ("1.1")、class / id は識別子であって座標ではない。
                if name in ("class", "id", "version"):
                    continue
                for decimals in re.findall(r"\d+\.(\d+)", value):
                    checked += 1
                    if len(decimals) != MASTER_GRID_DECIMALS:
                        off_grid.append((shape["primitive"], profile, name, decimals))
    assert checked > 1000, checked
    assert off_grid == []


def test_grid_render_is_bit_deterministic_for_same_score_and_seed():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.48, 0.45],
                    "to": [0.52, 0.55],
                    "arrangement": {
                        "count": 100,
                        "layout": "grid",
                        "rows": 10,
                        "cols": 10,
                        "jitter": 0.3,
                    },
                }
            ]
        }
    )

    assert render(score, render_seed=987) == render(score, render_seed=987)
