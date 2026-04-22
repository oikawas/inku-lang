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


def test_line_missing_endpoints_raises():
    import pytest

    score = Score(instructions=[Instruction(primitive="line")])
    with pytest.raises(ValueError):
        render(score)
