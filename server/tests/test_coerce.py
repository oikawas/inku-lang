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
    assert ins.arrangement.count <= 120
    assert ins.arrangement.density == "high"
    assert ins.arrangement.cluster_count is not None
    assert ins.arrangement.preserve_space is True


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
    assert fixed.instructions[0].arrangement.count <= 120
    assert fixed.instructions[0].arrangement.density == "high"
    assert fixed.instructions[0].arrangement.cluster_count is not None
    assert fixed.instructions[0].arrangement.preserve_space is True
    assert "single arrangement density clustered" in (fixed.instructions[0].color_hint or "")


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


def test_coerce_score_preserves_multicolor_cycle_from_ddl_coverage():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(
        score,
        ddl="黒い横線を一本引く。赤・青・緑の小さな四角を三十個散らす。",
    )

    colored = [ins for ins in fixed.instructions if ins.arrangement and ins.arrangement.color_cycle]
    assert colored
    assert colored[0].arrangement is not None
    assert colored[0].arrangement.color_cycle == ["blue", "red", "green"] or colored[0].arrangement.color_cycle == ["red", "blue", "green"]


def test_coerce_score_adds_atmospheric_coverage_from_ddl():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="黒い横線を一本引く。透明な膜が反射を包む。")

    assert len(fixed.instructions) >= 2
    atmospheric = [ins for ins in fixed.instructions if "membrane haze" in (ins.color_hint or "")]
    assert atmospheric
    assert atmospheric[0].arrangement is not None
    assert atmospheric[0].arrangement.fade == "outward"
    assert atmospheric[0].arrangement.preserve_space is True


def test_coerce_score_adds_sensory_coverage_from_ddl():
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(
        score,
        ddl="黒い横線を一本引く。柔らかな光が上端に残る。沈丁花の香りが波打つ。桜の蕾が開花を待つ。",
    )

    hints = " ".join(ins.color_hint or "" for ins in fixed.instructions)
    assert "soft light" in hints
    assert "scent layer" in hints
    assert "waiting buds" in hints
    assert any(ins.arrangement and ins.arrangement.path == "wave" for ins in fixed.instructions)


def test_coerce_score_keeps_white_sensory_layers_pale_on_white_background():
    score = Score.model_validate(
        {
            "background": "white",
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
                    "primitive": "arc",
                    "center": [0.3, 0.7],
                    "radius": 0.14,
                    "angle_start": 205,
                    "angle_end": 335,
                    "color": "white",
                    "color_hint": "五感の気配",
                },
            ],
        }
    )

    fixed = coerce_score(score)

    assert [ins.color for ins in fixed.instructions] == ["blue", "blue"]
    assert all("white sensory layer made visible as pale blue" in (ins.color_hint or "") for ins in fixed.instructions)


def test_coerce_score_repairs_missing_green_from_natural_ddl():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.18, 0.08],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="竹林の香りを含む薄い楕円を波打つ軌跡に沿って散らす。")

    assert any(ins.color == "green" for ins in fixed.instructions)
    assert any("green restored from DDL color intent" in (ins.color_hint or "") for ins in fixed.instructions)


def test_coerce_score_does_not_repair_green_from_words_false_positive():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.18, 0.08],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="言えなかった言葉のために白い余白を残す。")

    assert not any(ins.color == "green" for ins in fixed.instructions)
    assert not any("green restored from DDL color intent" in (ins.color_hint or "") for ins in fixed.instructions)


def test_coerce_score_repairs_green_from_specific_leaf_terms():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.18, 0.08],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="木の葉と葉脈を細い楕円で散らす。")

    assert any(ins.color == "green" for ins in fixed.instructions)


def test_coerce_score_repairs_missing_shape_intents_from_ddl():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="鋭い山のかたちを置く。波紋の弧を添える。折れた紙片を散らす。")

    primitives = {ins.primitive for ins in fixed.instructions}
    assert {"triangle", "arc", "square"} <= primitives
    hints = " ".join(ins.color_hint or "" for ins in fixed.instructions)
    assert "triangle restored from DDL shape intent" in hints
    assert any(ins.primitive == "arc" and "coverage from DDL clause" in (ins.color_hint or "") for ins in fixed.instructions)
    assert "square restored from DDL shape intent" in hints
