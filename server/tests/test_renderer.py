from inku_server.renderer import render
from inku_server.schema import Instruction, Score


def test_render_empty_score_has_background():
    svg = render(Score(instructions=[]))
    assert "<svg" in svg
    assert 'viewBox="0 0 1000 1000"' in svg
    assert "#f7f5ef" in svg


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


def test_line_missing_endpoints_raises():
    import pytest

    score = Score(instructions=[Instruction(primitive="line")])
    with pytest.raises(ValueError):
        render(score)
