import pytest

from inku_server.coerce import coerce_score, count_hint_from_ddl, ensure_renderable_score
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


def test_coerce_score_dedupes_repeated_arranged_instructions():
    repeated = {
        "primitive": "line",
        "from": [0.0, 0.5],
        "to": [1.0, 0.5],
        "color": "white",
        "arrangement": {"count": 20, "layout": "vertical", "path": "wave"},
    }
    score = Score.model_validate({"background": "black", "instructions": [repeated, repeated, repeated]})

    fixed = coerce_score(score)

    assert len(fixed.instructions) == 1
    assert fixed.instructions[0].arrangement is not None
    assert fixed.instructions[0].arrangement.count == 20


def test_coerce_score_caps_total_expanded_density():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "arrangement": {"count": 300, "layout": "vertical"},
                },
                {
                    "primitive": "square",
                    "position": [0.5, 0.5],
                    "size": [0.01, 0.01],
                    "arrangement": {"count": 300, "layout": "scatter"},
                },
            ],
        }
    )

    fixed = coerce_score(score)

    total = sum(ins.arrangement.count if ins.arrangement else 1 for ins in fixed.instructions)
    assert total <= 400


def test_coerce_score_caps_single_arrangement_density():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "arrangement": {"count": 377, "layout": "vertical"},
                }
            ],
        }
    )

    fixed = coerce_score(score)

    assert fixed.instructions[0].arrangement is not None
    assert fixed.instructions[0].arrangement.count == 240
    assert "single arrangement density capped" in (fixed.instructions[0].color_hint or "")


def test_coerce_score_infers_material_and_variation_from_ddl():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.5],
                    "to": [1.0, 0.5],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="黒いクレヨンの横線を五本並べる。細かく震える。")
    ins = fixed.instructions[0]

    assert ins.weight == "crayon"
    assert ins.variation is not None
    assert ins.variation.quality == "perlin"


def test_coerce_score_adds_ddl_coverage_when_stage2_collapses_to_one_instruction():
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "color": "white",
                }
            ],
        }
    )

    fixed = coerce_score(
        score,
        ddl="白い線を三本並べる。赤い小さな四角を八個散らす。青い弧を二本置く。",
    )

    assert len(fixed.instructions) >= 3
    assert {ins.primitive for ins in fixed.instructions} >= {"line", "square", "arc"}
    assert any("coverage from DDL clause" in (ins.color_hint or "") for ins in fixed.instructions)


def test_count_hint_from_ddl_extracts_japanese_numbers():
    assert count_hint_from_ddl("白い線を二百三十三本散らす。") == 233
    assert count_hint_from_ddl("赤い点を47個散らす。") == 47
