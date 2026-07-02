import math
from xml.etree import ElementTree

from inku_server.renderer import _clustered_pos, render
from inku_server.schema import Instruction, Score


def test_render_empty_score_has_background():
    svg = render(Score(instructions=[]))
    assert "<svg" in svg
    assert 'viewBox="0 0 1000 1000"' in svg
    assert "#ffffff" in svg


def test_render_canvas_aspect_plugin_changes_viewbox_without_stretching_circle():
    score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2}]}
    )

    svg = render(score, canvas_aspect="wide")

    assert 'viewBox="0 0 2350 1000"' in svg
    assert 'cx="1175.0"' in svg
    assert 'cy="500.0"' in svg
    assert 'r="200.0"' in svg


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
        {"instructions": [{"primitive": "line", "from": [0.0, 0.33], "to": [1.0, 0.33]}]}
    )
    svg = render(score)
    assert "<line" in svg
    assert 'x1="0.0"' in svg and 'y1="330' in svg
    assert 'x2="1000.0"' in svg and 'y2="330' in svg
    assert "#111111" in svg
    assert "stroke-dasharray" not in svg


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
                    "variation": {"quality": "pink", "dimensions": ["position_x"], "amplitude": "fine"},
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
    assert "12,8" in svg


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
    assert 'stroke-opacity="0.66"' in svg
    assert 'stroke-dasharray="1,3"' in svg
    assert 'id="texture-pencil"' in svg
    assert 'filter="url(#texture-pencil)"' in svg
    assert svg.count("<circle") >= 18


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
    assert 'stroke-dasharray="7,5,1,4"' in svg
    assert "<feTurbulence" in svg
    assert "<feDisplacementMap" in svg
    assert svg.count("<circle") >= 34


def test_render_rope_line_adds_twist_layers():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "weight": "rope",
                }
            ]
        }
    )
    svg = render(score)
    assert svg.count("<line") >= 16
    assert 'stroke-dasharray="14,5"' in svg
    assert 'stroke-dasharray="4,8"' in svg
    assert 'stroke-opacity="0.42"' in svg


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
    assert svg.count("<line") >= 5
    assert 'stroke-dasharray="10,3,2,3"' in svg
    assert 'stroke-dasharray="2,5,9,7"' in svg
    assert 'id="texture-crayon"' in svg
    assert svg.count("<circle") >= 26


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
    assert 'cx="99.999' in svg
    assert 'cx="300.000' in svg
    assert 'cx="500.0"' in svg
    assert 'cx="700.000' in svg
    assert 'cx="900.0"' in svg
    assert svg.count("<circle") == 5


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
    root = ElementTree.fromstring(svg)
    xs = [float(node.attrib["cx"]) for node in root.iter() if node.tag.endswith("circle") and "cx" in node.attrib]
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
    assert svg.count("<circle") == 4


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
    assert 'stroke-opacity="0.4"' in svg
    assert 'fill-opacity="0.22"' in svg


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

    assert 'fill-opacity="0.14"' in svg
    assert 'fill-opacity="0.2"' in svg


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
    assert svg.count("<line") >= 7
    assert 'stroke-dasharray="22,9"' in svg
    assert 'stroke-dasharray="18,7,3,11"' in svg
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
    assert svg.count("<circle") >= 38
    assert 'id="texture-chalk"' in svg
    assert 'stroke-dasharray="8,12,1,8"' in svg


def test_render_rope_circle_applies_twist_texture():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.18,
                    "weight": "rope",
                }
            ]
        }
    )

    svg = render(score)

    assert "<circle" in svg
    assert svg.count("<line") >= 16
    assert 'stroke-dasharray="4,8"' in svg


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
    assert svg.count("<circle") >= 28
    assert 'id="texture-crayon"' in svg
    assert 'stroke-dasharray="2,5,9,7"' in svg


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
    assert svg.count("<circle") >= 18
    assert 'id="texture-pencil"' in svg
    assert 'stroke-dasharray="1,7"' in svg


def test_render_arc_material_applies_outline_texture():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.5, 0.5],
                    "radius": 0.25,
                    "angle_start": 0,
                    "angle_end": 180,
                    "weight": "rope",
                }
            ]
        }
    )
    svg = render(score)
    assert svg.count("<path") >= 3
    assert 'stroke-dasharray="4,8"' in svg


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
    assert 'transform="rotate(-30.0,500.0,500.0)"' in svg


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
    assert "<line" in svg
    assert 'transform="rotate(45.0,500.0,500.0)"' in svg


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
    assert 'M 800.000 500.000' in svg
    # 終点: center + r north (y-flip) = (500, 0.5*1000 - 300) = (500, 200)
    assert 'A 300.000 300.000 0 0 0 500.000 200.000' in svg


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
        instructions=[
            Instruction(primitive="arc", center=(0.5, 0.5), radius=0.3)
        ]
    )
    with pytest.raises(ValueError, match="angle_start"):
        render(score)


def test_render_line_with_perlin_variation_emits_polyline():
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
    assert "<polyline" in svg
    assert "<line" not in svg


def test_render_line_with_wave_variation_emits_polyline():
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
    assert "<polyline" in svg


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
    assert "<line" in svg
    assert "<polyline" not in svg


def test_line_missing_endpoints_uses_default():
    score = Score(instructions=[Instruction(primitive="line")])
    svg = render(score)
    assert "<line" in svg


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
    assert 'filter="url(#blur-medium)"' in svg
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
    assert svg.count('filter="url(#texture-chalk)"') == 1
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
    assert "<line" in svg
    assert "<polyline" not in svg


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
                {"primitive": "ellipse", "center": [0.5, 0.5], "size": [0.3, 0.12], "color": "blue"}
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
            "presence": {"kind": "figure_like", "intensity": "medium", "symmetry": "bilateral"},
            "instructions": [{"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}],
        }
    )
    dense = Score.model_validate(
        {
            "presence": {"kind": "figure_like", "intensity": "medium", "symmetry": "bilateral"},
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

    assert 'stroke-opacity="0.1722"' in sparse_svg
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

    assert svg.count('fill-opacity="0.12"') == 2
    assert 'fill="#111111"' in svg
    assert 'fill="#ffffff"' in svg


def test_render_region_uses_seed_for_reproducible_macro_variation():
    score = Score.model_validate({
        "instructions": [
            {"primitive": "circle", "at": {"region": [0.2, 0.2, 0.8, 0.8]}, "radius": 0.04}
        ]
    })

    svg_a = render(score, render_seed=101)
    svg_b = render(score, render_seed=101)
    svg_c = render(score, render_seed=202)

    assert svg_a == svg_b
    assert svg_a != svg_c


def test_render_not_touching_relation_moves_second_mark_away_from_previous():
    score = Score.model_validate({
        "instructions": [
            {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.08},
            {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.03, "relation": {"type": "not_touching", "gap": "narrow"}},
        ]
    })

    svg = render(score, render_seed=5)

    assert svg.count("<circle") >= 2
    assert svg.count('cx="500.0"') == 1


def test_render_cutting_relation_crosses_previous_line_center():
    score = Score.model_validate({
        "instructions": [
            {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5]},
            {"primitive": "line", "from": [0.1, 0.1], "to": [0.2, 0.1], "relation": {"type": "cutting"}},
        ]
    })

    svg = render(score, render_seed=7)

    assert 'x1="200.0"' in svg
    assert 'x2="800.0"' in svg
    assert '500.0' in svg
