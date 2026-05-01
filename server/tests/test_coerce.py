import pytest

from inku_server.coerce import coerce_score, ensure_renderable_score
from inku_server.schema import Score


def test_ensure_renderable_score_rejects_empty_instructions():
    with pytest.raises(ValueError, match="no drawable instructions"):
        ensure_renderable_score(Score(instructions=[]))


def test_coerce_score_makes_gray_on_gray_visible():
    score = Score.model_validate(
        {
            "background": "gray",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.1, 0.5],
                    "to": [0.9, 0.5],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(score)

    assert fixed.background == "white"
    assert fixed.instructions[0].color == "black"
    assert "made visible" in (fixed.instructions[0].color_hint or "")


def test_coerce_score_keeps_tiny_particle_cloud_visible_and_bounded():
    score = Score.model_validate(
        {
            "background": "gray",
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.495, 0.495],
                    "size": [0.005, 0.005],
                    "filled": False,
                    "color": "gray",
                    "arrangement": {"count": 377, "layout": "scatter"},
                }
            ],
        }
    )

    fixed = coerce_score(score)
    ins = fixed.instructions[0]

    assert fixed.background == "white"
    assert ins.color == "black"
    assert ins.filled is True
    assert ins.size == (0.008, 0.008)
    assert ins.arrangement is not None
    assert ins.arrangement.count == 240
