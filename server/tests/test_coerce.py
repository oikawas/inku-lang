import pytest

from inku_server.coerce import coerce_score, count_hint_from_ddl, ensure_renderable_score
from inku_server.coerce.normalize import _mark_count, _with_total_density_budget
from inku_server.limits import DEFAULT_LIMITS
from inku_server.schema import Score


def test_ensure_renderable_score_rejects_empty_instructions():
    with pytest.raises(ValueError, match="no drawable instructions"):
        ensure_renderable_score(Score(instructions=[]))


def test_coerce_score_makes_gray_on_gray_visible():
    """The gray background survives; the foreground is what moves.

    Until 2026-08-02 this asserted `background == "white"`, because
    `_visible_background` turned every gray background white before the governor
    ran. That was a second, unconditional block on gray (I-104), and removing it
    is stage 5 of 契約 background-color-openness. The property this test defends
    -- gray-on-gray stays legible -- is carried by the foreground rule alone, so
    the assertions on the instruction below are unchanged.
    """
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

    assert fixed.background == "gray"
    assert fixed.instructions[0].color == "black"
    assert "made visible" in (fixed.instructions[0].note or "")


def test_coerce_score_keeps_tiny_particle_cloud_visible_and_bounded():
    """Same inversion as above (I-104): the background stays gray.

    Every other repair -- colour, fill, minimum size, count ceiling, density,
    clustering -- is asserted unchanged, so "keep the background" cannot be
    bought by dropping the foreground rules.
    """
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

    assert fixed.background == "gray"
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
            "background": "blue",
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
            "background": "blue",
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
    assert "single arrangement density clustered" in (fixed.instructions[0].note or "")


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
    assert any("coverage from DDL clause" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_keeps_small_ddl_mark_coverage_compact():
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
        ddl="Place one small red ellipse near the upper-right focus. Draw one gray line below it.",
    )

    mark = next(ins for ins in fixed.instructions if "small focal mark kept compact" in (ins.note or ""))
    assert mark.primitive == "ellipse"
    assert mark.size is not None
    assert max(mark.size) <= 0.06
    assert mark.arrangement is not None
    assert mark.arrangement.count == 1
    assert mark.arrangement.preserve_space is True


def test_coerce_score_preserves_radius_circle_coverage_as_circle():
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
        ddl="白い円を上端寄りの焦点に置く。半径は0.1。灰色の横線を二十本引く。",
    )

    circle = next(ins for ins in fixed.instructions if "白い円を上端寄り" in (ins.note or ""))
    assert circle.primitive == "circle"
    assert circle.radius == pytest.approx(0.1)
    assert circle.arrangement is not None
    assert circle.arrangement.preserve_space is True


def test_coerce_score_adds_counterweight_to_existing_visual_event_arrangement():
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.58, 0.42],
                    "radius": 0.05,
                    "color": "green",
                    "note": "visual event type inherited_memory preserved through existing shape",
                    "arrangement": {"count": 3, "layout": "scatter", "center": [0.50, 0.50]},
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="A remembered tree keeps growing.")
    event = next(ins for ins in fixed.instructions if "counterweight" in (ins.note or ""))

    assert event.arrangement is not None
    assert event.arrangement.center is not None
    assert abs(event.center[0] - event.arrangement.center[0]) >= 0.25
    assert abs(event.center[1] - event.arrangement.center[1]) >= 0.25
    assert event.arrangement.color_cycle
    assert event.arrangement.preserve_space is True


def test_coerce_score_marks_existing_support_as_visual_event_for_single_inherited_event():
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.12, 0.62],
                    "to": [0.82, 0.50],
                    "color": "blue",
                },
                {
                    "primitive": "arc",
                    "center": [0.56, 0.45],
                    "radius": 0.05,
                    "color": "blue",
                    "note": "visual event type inherited_memory restored as a three-part memory sequence",
                    "arrangement": {"count": 3, "layout": "scatter"},
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="A fisherman bows to the river. His father did. His grandfather did.")
    support = next(ins for ins in fixed.instructions if "inherited memory trace" in (ins.note or ""))

    assert support.primitive == "line"
    assert support.arrangement is not None
    assert support.arrangement.center is not None
    assert support.arrangement.color_cycle
    assert support.arrangement.preserve_space is True


def test_coerce_score_marks_compact_ddl_mark_as_visual_event_in_event_context():
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.6],
                    "to": [0.8, 0.6],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(
        score,
        ddl="A remembered museum wall keeps one quiet trace. Place one small red crayon dot near the lower right.",
    )
    mark = next(ins for ins in fixed.instructions if "small focal mark kept compact" in (ins.note or ""))

    assert "visual event preserved as compact focal accent" in (mark.note or "")
    assert mark.arrangement is not None
    assert mark.arrangement.center is not None
    assert mark.arrangement.color_cycle
    assert mark.arrangement.preserve_space is True


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
    assert all("white sensory layer made visible as pale blue" in (ins.note or "") for ins in fixed.instructions)


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

    assert any(ins.color == "green" or (ins.arrangement and "green" in ins.arrangement.color_cycle) for ins in fixed.instructions)
    assert any("green restored in color_cycle from DDL color intent" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_repairs_blue_from_sky_and_water_context():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="錆びた鉄骨が空を細かく分けている。")

    assert any(ins.color == "blue" or (ins.arrangement and "blue" in ins.arrangement.color_cycle) for ins in fixed.instructions)
    assert any("blue restored in color_cycle from DDL color intent" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_repairs_multiple_missing_colors_without_overwriting_green():
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

    fixed = coerce_score(score, ddl="青い夜の森に赤い落ち葉を散らす。")

    repaired = fixed.instructions[0]
    # `red` rather than the `gray` it arrived with: since ddl-engine 9 the repair
    # runs before the promotion, so a color delivered into the cycle reaches the
    # primary stroke on this pass instead of the next one. Only one of the three
    # is promoted -- an instruction has one primary stroke, and promoting a
    # second onto it would undo the first.
    assert repaired.color == "red"
    assert (repaired.note or "").count("promoted to primary stroke") == 1
    assert repaired.arrangement is not None
    assert repaired.arrangement.color_cycle == ["gray", "red", "blue", "green"]
    assert "red/blue/green restored in color_cycle from DDL color intent" in (repaired.note or "")
    assert "forest green kept as quiet residue behind warm leaves" in (repaired.note or "")


def test_coerce_score_keeps_bamboo_green_as_primary_contour():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.2],
                    "to": [0.8, 0.8],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="竹林の輪郭を細い線で引く。")

    repaired = fixed.instructions[0]
    assert repaired.color == "green"
    assert repaired.arrangement is not None
    assert repaired.arrangement.color_cycle == ["green"]
    assert "bamboo green kept as primary contour" in (repaired.note or "")


def test_coerce_score_keeps_withered_grass_as_muted_green_gray():
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

    fixed = coerce_score(score, ddl="枯れ草の低い波を横に散らす。")

    repaired = fixed.instructions[0]
    # The muted reading is carried by the cycle holding both, which is unchanged.
    # The primary stroke became the requested green at ddl-engine 9, when the
    # repair moved in front of the promotion.
    assert repaired.color == "green"
    assert repaired.arrangement is not None
    assert repaired.arrangement.color_cycle == ["gray", "green"]
    assert "withered grass kept as muted green-gray" in (repaired.note or "")


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
    assert not any("green restored from DDL color intent" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_keeps_negated_green_out_of_color_cycles_and_composition_repair():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.5, 0.5],
                    "to": [0.72, 0.28],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="言えなかった言葉を白い余白に置き、緑には寄せず黒い線だけを残す。")

    assert all(ins.color != "green" for ins in fixed.instructions)
    assert all("green" not in (ins.arrangement.color_cycle if ins.arrangement else []) for ins in fixed.instructions)
    assert not any("composition anchor restored" in (ins.note or "") for ins in fixed.instructions)


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

    assert any(ins.color == "green" or (ins.arrangement and "green" in ins.arrangement.color_cycle) for ins in fixed.instructions)


def test_coerce_score_repairs_black_from_shadow_terms():
    score = Score.model_validate(
        {
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

    fixed = coerce_score(score, ddl="Warehouse grid cuts hold dust and late afternoon shadow.")

    assert any(ins.color == "black" or (ins.arrangement and "black" in ins.arrangement.color_cycle) for ins in fixed.instructions)


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
    hints = " ".join(ins.note or "" for ins in fixed.instructions)
    assert "triangle restored from DDL shape intent" in hints
    assert any(ins.primitive == "arc" and "coverage from DDL clause" in (ins.note or "") for ins in fixed.instructions)
    assert "square restored from DDL shape intent" in hints


def test_coerce_score_repairs_polygon_shape_intent_from_ddl():
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

    fixed = coerce_score(score, ddl="鉱物のような六角の結晶を右上に置く。")

    polygons = [ins for ins in fixed.instructions if ins.primitive == "polygon"]
    assert polygons
    assert polygons[0].sides == 6
    assert "polygon restored from DDL shape intent" in (polygons[0].note or "")


def test_coerce_score_prioritizes_triangle_delivery_for_ridge_intent_when_many_instructions():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.1, 0.1 + index * 0.08],
                    "to": [0.9, 0.1 + index * 0.08],
                    "color": "black",
                }
                for index in range(8)
            ],
        }
    )

    fixed = coerce_score(score, ddl="低い雲の下に街の屋根と稜線を鋭く置く。")

    assert any(ins.primitive == "triangle" for ins in fixed.instructions)
    assert len(fixed.instructions) == 10
    assert any("triangle restored from DDL shape intent" in (ins.note or "") for ins in fixed.instructions)
    assert any("mountain_sign motif restored from DDL intent" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_does_not_restore_triangle_for_roof_pressure_alone():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.4],
                    "to": [0.8, 0.4],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="遠雷の前、低い雲が街の屋根を押し沈めている。")

    assert not any("triangle restored from DDL shape intent" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_does_not_restore_mountain_sign_for_roof_without_mountain_context():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.4, 0.45],
                    "size": [0.18, 0.12],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="低い雲の下に街の屋根を重く置く。")

    assert not any("mountain_sign motif restored from DDL intent" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_adds_limited_compound_motifs_from_ddl():
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

    fixed = coerce_score(score, ddl="落ち葉の群れと折れた紙片を少しだけ散らす。")

    hints = [ins.note or "" for ins in fixed.instructions]
    assert sum("leaf_cluster motif restored from DDL intent" in hint for hint in hints) == 2
    assert sum("paper_shard motif restored from DDL intent" in hint for hint in hints) == 2
    assert len([hint for hint in hints if "motif restored from DDL intent" in hint]) == 4


def test_coerce_score_limits_compound_motifs_to_two_per_work():
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

    fixed = coerce_score(score, ddl="木の葉、紙片、波紋、山の印を置く。")

    motif_hints = [ins.note or "" for ins in fixed.instructions if "motif restored from DDL intent" in (ins.note or "")]
    assert len(motif_hints) == 4
    assert any("leaf_cluster motif restored from DDL intent" in hint for hint in motif_hints)
    assert any("paper_shard motif restored from DDL intent" in hint for hint in motif_hints)
    assert not any("ripple_knot motif restored from DDL intent" in hint for hint in motif_hints)
    assert not any("mountain_sign motif restored from DDL intent" in hint for hint in motif_hints)


def test_coerce_score_does_not_add_generic_anchor_for_minimal_quiet_scene():
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

    fixed = coerce_score(score, ddl="静かな余白に黒い線を一つだけ置く。")

    assert len(fixed.instructions) == 1
    assert not any("composition anchor restored for shape/color diversity" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_adds_generic_accent_when_shape_exists_but_color_is_flat():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.35, 0.35],
                    "size": [0.18, 0.18],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="水の冷たさが石の横に残る。")

    assert any(ins.color == "blue" or (ins.arrangement and "blue" in ins.arrangement.color_cycle) for ins in fixed.instructions)
    assert any("blue restored in color_cycle from DDL color intent" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_restores_human_presence_as_abstract_score_field():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.56, 0.52],
                    "size": [0.42, 0.16],
                    "color": "blue",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="雨のバス停で、待つ人の気配が透明な膜になっている。")

    assert fixed.presence is not None
    assert fixed.presence.kind == "figure_like"
    assert fixed.presence.symmetry == "none"
    assert fixed.presence.gaze_pressure == "none"


def test_coerce_score_restores_animal_group_presence_without_extra_primitives():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="遠くの動物の群れの気配が横へ流れる。")

    assert fixed.presence is not None
    assert fixed.presence.kind == "group_like"
    assert fixed.presence.contour_density == "high"
    assert all("animal" not in (ins.color_hint or "") for ins in fixed.instructions)


def test_coerce_score_does_not_read_scatter_as_cat_presence():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.6, 0.6],
                    "size": [0.08, 0.04],
                    "color": "gray",
                    "arrangement": {"count": 40, "layout": "scatter"},
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="Scatter forty rotated squares along an undulating trace in the lower right.")

    assert fixed.presence is None


def test_coerce_score_dedupes_structurally_identical_auxiliary_layers():
    score = Score.model_validate(
        {
            "background": "blue",
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.75, 0.5],
                    "size": [0.3, 0.15],
                    "color": "white",
                    "color_hint": "透明な膜",
                    "arrangement": {"count": 3, "layout": "scatter", "path": "right_half", "margin": 0.45},
                },
                {
                    "primitive": "ellipse",
                    "center": [0.75, 0.5],
                    "size": [0.3, 0.15],
                    "color": "white",
                    "note": "material inferred from DDL",
                    "arrangement": {"count": 3, "layout": "scatter", "path": "right_half", "margin": 0.45},
                },
            ],
        }
    )

    fixed = coerce_score(score)

    assert len(fixed.instructions) == 1
    assert fixed.instructions[0].color_hint == "透明な膜"


def test_coerce_score_suppresses_plain_large_shape_duplicate_when_presence_is_active():
    score = Score.model_validate(
        {
            "presence": {"kind": "creature_like", "intensity": "low", "contour_density": "medium"},
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.7, 0.5],
                    "size": [0.3, 0.1],
                    "color": "black",
                    "color_hint": "透明な膜",
                    "note": "material inferred from DDL: pencil",
                },
                {
                    "primitive": "ellipse",
                    "center": [0.7, 0.5],
                    "size": [0.3, 0.1],
                    "color": "black",
                    "note": "material inferred from DDL: pencil",
                },
            ],
        }
    )

    fixed = coerce_score(score)

    assert len(fixed.instructions) == 1
    assert fixed.instructions[0].color_hint is not None
    assert "透明な膜" in fixed.instructions[0].color_hint


def test_coerce_score_governs_neon_blur_vertical_density_more_strictly():
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.03, 0.06],
                    "color": "red",
                    "color_hint": "涙のような滲み",
                    "arrangement": {
                        "count": 110,
                        "layout": "vertical",
                        "path": "top_to_bottom",
                        "density": "high",
                    },
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="夜のガラス越しに、街のネオンが涙のように滲んでいる。")

    arr = fixed.instructions[0].arrangement
    assert arr is not None
    assert arr.count == 18
    assert arr.density == "low"
    assert arr.fade == "directional"
    assert "neon blur vertical density governed" in (fixed.instructions[0].note or "")


def test_coerce_score_governs_quiet_vertical_rain_density():
    score = Score.model_validate(
        {
            "background": "blue",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.5, 0.0],
                    "to": [0.5, 1.0],
                    "color": "gray",
                    "color_hint": "雨",
                    "arrangement": {
                        "count": 110,
                        "layout": "vertical",
                        "path": "top_to_bottom",
                        "density": "high",
                    },
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="雨のバス停で、待つ人の気配が透明な膜になっている。")

    arr = fixed.instructions[0].arrangement
    assert arr is not None
    assert arr.count == 48
    assert arr.density == "low"
    assert arr.fade == "directional"


def test_coerce_score_governs_quiet_large_shape_repetition():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.35, 0.1],
                    "size": [0.3, 0.15],
                    "color": "black",
                    "color_hint": "低い雲",
                    "arrangement": {
                        "count": 30,
                        "layout": "vertical",
                        "path": "top_to_bottom",
                    },
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="遠雷の前、低い雲が街の屋根を押し沈めている。")

    arr = fixed.instructions[0].arrangement
    assert arr is not None
    assert arr.count == 16
    assert arr.density == "low"
    assert arr.preserve_space is True


def test_coerce_score_tempers_quiet_symbolic_fallback_shapes():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.4, 0.5],
                    "size": [0.24, 0.2],
                    "color": "white",
                    "note": "coverage from DDL clause: 右端に白いクレヨンの縦長の四角を置く",
                    "arrangement": {
                        "count": 20,
                        "layout": "scatter",
                    },
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="雨のバス停で、待つ人の気配が透明な膜になっている。")

    ins = fixed.instructions[0]
    arr = ins.arrangement
    assert ins.size is not None
    assert ins.size[0] <= 0.12
    assert ins.size[1] <= 0.09
    assert arr is not None
    assert arr.count == 8
    assert arr.density == "low"
    assert arr.preserve_space is True
    assert "quiet symbolic shape tempered" in (ins.note or "")


def test_coerce_score_repairs_polygon_fields_and_tempers_quiet_polygon():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "polygon",
                    "center": [0.55, 0.4],
                    "radius": 0.18,
                    "sides": 12,
                    "note": "coverage from DDL clause: 鉱物のような多角形を置く",
                    "arrangement": {"count": 20, "layout": "scatter"},
                }
            ]
        }
    )

    fixed = coerce_score(score, ddl="静かな部屋に鉱物のような多角形の気配が沈んでいる。")

    ins = fixed.instructions[0]
    arr = ins.arrangement
    assert ins.primitive == "polygon"
    assert ins.sides == 8
    assert ins.radius is not None and ins.radius <= 0.06
    assert arr is not None
    assert arr.count == 8
    assert "quiet symbolic shape tempered" in (ins.note or "")


def test_coerce_score_restores_motion_energy_without_increasing_count():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.08, 0.04],
                    "color": "red",
                    "arrangement": {"count": 5, "layout": "scatter"},
                }
            ]
        }
    )

    fixed = coerce_score(score, ddl="夏祭りの後、路面に残った色紙が湿って丸まっている。")

    ins = fixed.instructions[0]
    assert ins.arrangement is not None
    assert ins.arrangement.count == 5
    assert ins.arrangement.path == "wave"
    assert ins.arrangement.rhythm_spacing == "loose"
    assert ins.rotation is not None
    assert ins.variation is not None
    assert ins.variation.quality == "wave"
    assert "motion energy restored" in (ins.note or "")


def test_coerce_score_drops_support_shape_for_explicit_numeric_regions():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.337, 0.498],
                    "radius": 0.09,
                    "at": {"region": [0.227, 0.411, 0.447, 0.584]},
                },
                {
                    "primitive": "arc",
                    "center": [0.651, 0.493],
                    "radius": 0.09,
                    "at": {"region": [0.541, 0.406, 0.761, 0.579]},
                },
                {
                    "primitive": "arc",
                    "center": [0.58, 0.52],
                    "radius": 0.11,
                    "color": "red",
                    "arrangement": {"count": 3, "layout": "scatter"},
                },
            ]
        }
    )
    ddl = (
        "細い弧を一枚 領域 [0.227, 0.411, 0.447, 0.584]に置く。"
        "細い弧を一枚 領域 [0.541, 0.406, 0.761, 0.579]に置く。"
    )

    fixed = coerce_score(score, ddl=ddl)

    assert len(fixed.instructions) == 2
    assert all(ins.at is not None for ins in fixed.instructions)
    assert not any(
        "motion floor restored" in (ins.note or "")
        for ins in fixed.instructions
    )


def test_coerce_score_promotes_requested_cycle_color_to_primary_stroke():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "color": "gray",
                    "arrangement": {"count": 4, "layout": "horizontal", "color_cycle": ["gray", "red"]},
                }
            ]
        }
    )

    fixed = coerce_score(score, ddl="赤い余韻が薄い線として残る。")

    assert fixed.instructions[0].color == "red"
    assert "red promoted to primary stroke from DDL color intent" in (fixed.instructions[0].note or "")


def test_coerce_score_enforces_explicit_shape_and_count_constraints_after_repairs():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.4, 0.4],
                    "size": [0.12, 0.12],
                    "color": "black",
                },
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "color": "black",
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="黒い四角だけを三つだけ、楽しいリズムで置く。")

    assert len(fixed.instructions) == 1
    assert fixed.instructions[0].primitive == "square"
    assert fixed.instructions[0].arrangement is not None
    assert fixed.instructions[0].arrangement.count == 3
    assert "explicit count constraint enforced" in (fixed.instructions[0].note or "")


def test_coerce_score_enforces_color_only_constraints_after_repairs():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.18, 0.08],
                    "color": "green",
                    "arrangement": {"count": 6, "layout": "scatter", "color_cycle": ["red", "blue", "green"]},
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="赤と青のみで、弾む楕円を散らす。")

    ins = fixed.instructions[0]
    assert ins.color in {"red", "blue"}
    assert ins.arrangement is not None
    assert set(ins.arrangement.color_cycle) <= {"red", "blue"}
    assert "explicit color-only constraint enforced" in (ins.note or "")


def test_coerce_score_tempers_single_large_shape_in_quiet_trace_context():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.5, 0.5],
                    "size": [0.82, 0.52],
                    "color": "gray",
                    "filled": True,
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="地下鉄の壁に、過ぎ去る列車の気配が銀色の筋を残す。")

    ins = fixed.instructions[0]
    assert ins.size is not None
    assert ins.size[0] <= 0.34
    assert ins.size[1] <= 0.24
    assert "quiet single large shape tempered" in (ins.note or "")


def test_coerce_score_governs_unrequested_saturated_background_in_presence_scene():
    score = Score.model_validate(
        {
            "background": "blue",
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.18, 0.08],
                    "color": "white",
                    "filled": True,
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="雨のバス停で、待つ人の気配が透明な膜になっている。")

    assert fixed.background == "white"
    # The governor's own subject is the background, and it still drops the
    # unrequested blue to white. The mark became `blue` at ddl-engine 9: the DDL
    # asks for it, the repair delivers it into the cycle, and the promotion now
    # runs after the repair rather than a pass behind it.
    assert fixed.instructions[0].color == "blue"
    assert "white foreground made visible" in (fixed.instructions[0].note or "")


def test_coerce_score_keeps_black_when_the_normalized_ddl_states_the_fill_clause():
    """契約 background-color-openness (2026-08-02) で裏返した表明。

    旧名 `..._governs_stage1_inferred_black_background_when_source_did_not_request_it`。
    原文に情景語しかなくても、正規化DDL が「背景を黒で塗りつぶす」と書いていれば
    それは記述の側の指示であり、ガバナは守らない。本番 DB の 22 件が
    この分岐で白へ落ちていた（§0.2 の実測）。

    ガバナ自体は残っている。原文にも正規化DDL にも明示が無い場合は依然として
    白へ落ちる（`test_coerce_score_governs_generated_background_plan_...` が対照）。
    """
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.62, 0.28],
                    "size": [0.18, 0.12],
                    "color": "gray",
                    "filled": True,
                }
            ],
        }
    )

    fixed = coerce_score(
        score,
        ddl="古い鏡の奥に、忘れた部屋の冷たい気配が沈んでいる。\n背景を黒で塗りつぶす。灰色の四角を置く。",
    )

    assert fixed.background == "black"


def test_coerce_score_governs_a_dark_background_no_clause_asked_for():
    """契約 description-propagation-cut (2026-08-04) で裏返した表明。

    旧名 `..._governs_generated_background_plan_without_original_source_context`。
    旧版はこの同じ DDL で `white` を表明していた。判定していたのは
    `_looks_like_generated_background_plan` で、「利用者が機械生成のプランを
    **記述欄に貼った**」ことを見抜く番人だった。切断で記述は coerce へ届かなく
    なり、番人に判ずる素性が残らなくなった。残せば本番の DDL の普通の形
    （単一行・4 節以上・先頭が `背景を`）に誤爆して明示句の判定へ到達しない
    ——濃色 604 件のうち 54 件が白へ落ちる。番人は撤去した。

    ガバナ自体は残っている。この表明はその対照で、**明示句も marker も無い**
    濃色は依然として白へ落ちる（上の
    `test_coerce_score_keeps_black_when_the_normalized_ddl_states_the_fill_clause`
    が逆向き）。
    """
    score = Score.model_validate(
        {
            "background": "blue",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.5, 0.0],
                    "to": [0.5, 1.0],
                    "color": "white",
                    "arrangement": {"count": 110, "layout": "vertical"},
                }
            ],
        }
    )

    fixed = coerce_score(
        score,
        ddl=(
            "静かな気配の中に、白い細筆の細い縦線を三百本、上から下へ散らす。"
            "黒い細い余白線を存在の重心として右上の焦点へ二本引く。透明な膜を重ねる。境界が滲む。"
        ),
    )

    assert fixed.background == "white"


def test_coerce_score_keeps_the_fill_clause_of_a_production_shaped_ddl():
    """The case the removed guard used to wash. Same shape as the one above with
    the fill clause restored: a single line, five clauses, opening with 背景を."""
    score = Score.model_validate(
        {
            "background": "blue",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.5, 0.0],
                    "to": [0.5, 1.0],
                    "color": "white",
                    "arrangement": {"count": 110, "layout": "vertical"},
                }
            ],
        }
    )

    fixed = coerce_score(
        score,
        ddl=(
            "背景を青で塗りつぶす。画面全体に白い細筆の細い縦線を三百本、上から下へ散らす。"
            "黒い細い余白線を存在の重心として右上の焦点へ二本引く。透明な膜を重ねる。境界が滲む。"
        ),
    )

    assert fixed.background == "blue"


def test_coerce_score_keeps_explicit_black_background_in_direct_ddl():
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.6],
                    "to": [0.8, 0.4],
                    "color": "white",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="背景を黒で塗りつぶす。白い線を一本引く。")

    assert fixed.background == "black"


def test_coerce_score_governs_incidental_dusk_background():
    score = Score.model_validate(
        {
            "background": "red",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.6],
                    "to": [0.8, 0.4],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="夕暮れの坂道で、自転車の影だけが先に帰っていく。")

    assert fixed.background == "white"


def test_coerce_score_keeps_explicit_sunset_sky_background():
    score = Score.model_validate(
        {
            "background": "red",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.6],
                    "to": [0.8, 0.4],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="夕暮れの空を赤い背景として置き、自転車の影を細く走らせる。")

    assert fixed.background == "red"


def test_coerce_score_keeps_explicit_dark_field_background():
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.62, 0.35],
                    "radius": 0.12,
                    "angle_start": 210,
                    "angle_end": 330,
                    "color": "white",
                    "color_hint": "crescent",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="A single white crescent waits in an off-center dark field.")

    assert fixed.background == "black"
    assert any(ins.color == "white" for ins in fixed.instructions)


def test_coerce_score_keeps_dawn_black_when_the_normalized_ddl_states_the_fill_clause():
    """契約 background-color-openness (2026-08-02) で裏返した表明。

    旧名 `..._governs_dawn_background_generated_from_source_context`。
    DAWN_MARKERS は「夜明け」を非明示と読むが、明示句はその推論より先に効く。
    明示句が信じられるのに夜明けを要さない、というのが段 1 の順序である。
    """
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.26],
                    "size": [0.42, 0.12],
                    "color": "white",
                    "filled": True,
                    "color_hint": "soft light",
                }
            ],
        }
    )

    fixed = coerce_score(
        score,
        ddl=(
            "夜明けの湖で、最初の光が水のしわを金色にほどく。\n"
            "背景を黒で塗りつぶす。白い薄い水彩の横長の楕円を柔らかな光として上端寄りに三つ重ねる。"
            "白い薄い水彩の楕円を五感の気配として右上に二つ重ねる。"
        ),
    )

    assert fixed.background == "black"


def test_coerce_score_tempers_unintentional_large_filled_shape():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.62, 0.45],
                    "size": [0.86, 0.48],
                    "color": "red",
                    "filled": True,
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="カフェの奥に赤い形が残る。")

    ins = fixed.instructions[0]
    assert ins.size is not None
    assert ins.size[0] <= 0.42
    assert ins.size[1] <= 0.30
    assert "large filled shape tempered" in (ins.note or "")


def test_coerce_score_restores_rhythm_and_ma_without_count_growth():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.08, 0.04],
                    "color": "blue",
                    "arrangement": {"count": 7, "layout": "scatter"},
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="余白の間に楽しいリズムで青い楕円が跳ねる。")

    ins = fixed.instructions[0]
    assert ins.arrangement is not None
    assert ins.arrangement.count == 7
    assert ins.arrangement.path in {"wave", "diagonal"}
    assert ins.arrangement.rhythm_spacing == "syncopated"
    assert ins.arrangement.preserve_space is True
    assert ins.arrangement.fade == "outward"
    assert "rhythm variation restored without increasing count" in (ins.note or "")
    assert "ma pressure restored" in (ins.note or "")


def test_coerce_score_restores_ma_for_thin_planar_drift_without_count_growth():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.46, 0.46],
                    "size": [0.08, 0.05],
                    "color": "gray",
                    "rotation": 12,
                    "arrangement": {"count": 6, "layout": "scatter", "path": "wave"},
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="北風の交差点で、新聞紙が迷うように回っている。")

    ins = fixed.instructions[0]
    assert ins.arrangement is not None
    assert ins.arrangement.count == 6
    assert ins.arrangement.preserve_space is True
    assert ins.arrangement.margin >= 0.22
    assert ins.arrangement.fade == "outward"
    assert "ma pressure restored" in (ins.note or "")


def test_coerce_score_adds_ma_pressure_to_prairie_horizon_line():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.0, 0.82],
                    "to": [1.0, 0.82],
                    "color": "black",
                    "color_hint": "prairie horizon",
                    "arrangement": {"count": 1, "layout": "horizontal"},
                },
                {
                    "primitive": "square",
                    "position": [0.68, 0.79],
                    "size": [0.03, 0.03],
                    "color": "red",
                    "color_hint": "small red interruption",
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="A prairie horizon sits low, with one small red interruption.")

    horizon = next(ins for ins in fixed.instructions if "prairie horizon" in (ins.color_hint or ""))
    assert horizon.arrangement is not None
    assert horizon.arrangement.preserve_space is True
    assert horizon.arrangement.fade == "outward"


def test_coerce_score_marks_existing_reflection_as_visual_event():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.25, 0.5],
                    "to": [0.75, 0.5],
                    "color": "gray",
                    "color_hint": "faint reflection",
                    "arrangement": {"count": 3, "layout": "scatter"},
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="Rain on a bus-stop window leaves transparent reflections.")

    assert any("visual event preserved as a reflected accent" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_adds_ma_pressure_for_sparse_chalk_wall():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.24, 0.22],
                    "to": [0.24, 0.78],
                    "color": "gray",
                    "color_hint": "cold brick wall dust",
                    "arrangement": {"count": 5, "layout": "vertical"},
                },
                {
                    "primitive": "square",
                    "position": [0.60, 0.48],
                    "size": [0.035, 0.035],
                    "color": "gray",
                    "arrangement": {"count": 12, "layout": "scatter", "margin": 0.08},
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="Cold brick wall dust is held by sparse chalk lines.")

    arranged = [ins for ins in fixed.instructions if ins.arrangement is not None]
    assert arranged
    assert all(ins.arrangement.preserve_space is True for ins in arranged)
    assert all(ins.arrangement.margin >= 0.22 for ins in arranged)
    assert any("ma pressure restored through spacing and preserved negative space" in (ins.note or "") for ins in arranged)
    assert any("visual event preserved as chalk dust tension" in (ins.note or "") for ins in arranged)


def test_coerce_score_marks_blue_note_pause_as_existing_visual_event():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.45, 0.42],
                    "radius": 0.16,
                    "angle_start": 15,
                    "angle_end": 220,
                    "color": "blue",
                    "color_hint": "blue-note value",
                    "arrangement": {"count": 2, "layout": "horizontal"},
                },
                {
                    "primitive": "square",
                    "position": [0.62, 0.52],
                    "size": [0.05, 0.05],
                    "color": "black",
                    "color_hint": "dark pause",
                    "arrangement": {"count": 1, "layout": "horizontal"},
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="Blue-note value moves through two thin arcs and a dark pause.")

    assert any("visual event preserved as a blue-note pause accent" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_does_not_read_crescent_as_scent_or_green():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.55, 0.45],
                    "radius": 0.12,
                    "angle_start": 30,
                    "angle_end": 260,
                    "color": "white",
                    "color_hint": "crescent sensory layer",
                    "note": "white sensory layer made visible as pale green",
                    "arrangement": {"count": 1, "color_cycle": ["green", "white"]},
                },
                {
                    "primitive": "ellipse",
                    "center": [0.72, 0.28],
                    "size": [0.3, 0.3],
                    "color": "blue",
                    "color_hint": "five-sense presence",
                    "note": "white sensory layer made visible as pale blue",
                }
            ],
        }
    )

    fixed = coerce_score(
        score,
        ddl="Fill background with black. Place a white crescent arc in the upper right. "
        "Layer two pale white watercolor ellipses in the upper right as five-sense presence.",
    )

    hints = " ".join(ins.color_hint or "" for ins in fixed.instructions)
    colors = {ins.color for ins in fixed.instructions}
    assert "scent layer" not in hints
    assert "five-sense presence" not in hints
    assert "green" not in colors
    assert all("green" not in (ins.arrangement.color_cycle if ins.arrangement else []) for ins in fixed.instructions)


def test_coerce_score_shapes_repeated_lines_as_event_without_adding_density():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.12, 0.5],
                    "to": [0.88, 0.5],
                    "color": "red",
                    "arrangement": {"count": 12, "layout": "horizontal"},
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="風鈴の余韻が薄い影を揺らしている。")

    line = next(ins for ins in fixed.instructions if ins.primitive == "line")
    assert line.arrangement is not None
    assert line.arrangement.count == 12
    assert line.arrangement.rhythm_spacing == "syncopated"
    assert line.arrangement.preserve_space is True
    assert line.arrangement.margin >= 0.18
    assert line.from_ != (0.12, 0.5)
    assert line.to != (0.88, 0.5)
    assert "visual event shaped with syncopated gaps" in (line.note or "")


def test_coerce_score_adds_motion_to_open_road_pull_focus():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.15, 0.85],
                    "to": [0.72, 0.28],
                    "color": "gray",
                    "color_hint": "open road",
                    "arrangement": {"count": 1, "layout": "scatter"},
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="An open road pulls one gray line toward the upper-right focus.")

    road = next(ins for ins in fixed.instructions if "open road" in (ins.color_hint or ""))
    assert road.arrangement is not None
    assert road.arrangement.path != "none"
    assert road.arrangement.rhythm_spacing != "none"
    assert "motion energy restored through trajectory and rotation" in (road.note or "")
    assert "visual event preserved as a road-pull focus accent" in (road.note or "")


def test_coerce_score_marks_shared_footstep_beat_as_visual_event():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.25, 0.50],
                    "to": [0.75, 0.50],
                    "color": "gray",
                    "color_hint": "急ぐ人々の靴音",
                    "arrangement": {"count": 4, "layout": "scatter"},
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="地下鉄の階段で、急ぐ人々の靴音が一瞬だけ同じ拍子になった。")

    assert any("visual event preserved as shared footstep beat" in (ins.note or "") for ins in fixed.instructions)


def test_coerce_score_does_not_add_edge_light_when_presence_handles_gaze():
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.45, 0.52],
                    "size": [0.18, 0.08],
                    "color": "blue",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="夜のガラス越しに、視線の圧力が透明な膜のように滲む。")

    assert not any("edge light event restored" in (ins.note or "") for ins in fixed.instructions)
    assert fixed.presence is not None
    assert fixed.presence.gaze_pressure == "medium"


def test_coerce_score_does_not_add_edge_light_for_dark_context_without_cutting_light():
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.4, 0.4],
                    "size": [0.2, 0.2],
                    "color": "black",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="遠雷の前、低い黒い雲が街の屋根を押し沈めている。")

    assert not any("edge light event restored" in (ins.note or "") for ins in fixed.instructions)


def test_fallback_score_preserves_explicit_count_circle_and_polygon():
    from inku_server.api_core.routers.render import _fallback_score_from_ddl

    circle = _fallback_score_from_ddl("黒い円を三つだけ置く。", lang="ja")
    assert circle.instructions[0].primitive == "circle"
    assert circle.instructions[0].arrangement is not None
    assert circle.instructions[0].arrangement.count == 3

    polygon = _fallback_score_from_ddl("青い六角の多角形を二つ置く。", lang="ja")
    assert polygon.instructions[0].primitive == "polygon"
    assert polygon.instructions[0].sides == 6
    assert polygon.instructions[0].arrangement is not None
    assert polygon.instructions[0].arrangement.count == 2


def test_stage2_fallback_coverage_preserves_right_edge_and_presence_context():
    from inku_server.api_core.routers.render import _fallback_score_from_ddl
    from inku_server.coerce import coerce_score

    ddl = (
        "背景を青で塗りつぶす。"
        "画面右端に黒い太筆の縦線を一本引く。"
        "その周りに白い細筆の楕円を三十個、波打つ軌跡に沿って散らす。"
        "線は滲む。"
    )
    score = coerce_score(
        _fallback_score_from_ddl(ddl, lang="ja"),
        ddl=f"雨のバス停で、待つ人の気配が透明な膜になっている。\n{ddl}",
    )

    # 契約 background-color-openness (2026-08-02): 「背景を青で塗りつぶす」は明示句なので
    # ガバナは守らない（旧表明は white）。この test の主題は右端の線と presence の保存で、
    # 背景色はその副産物である
    assert score.background == "blue"
    assert score.presence is not None
    assert score.presence.kind == "figure_like"
    right_edge_lines = [
        ins
        for ins in score.instructions
        if ins.primitive == "line"
        and ins.from_ is not None
        and ins.to is not None
        and ins.from_[0] >= 0.85
        and ins.to[0] >= 0.85
    ]
    assert right_edge_lines



def test_coerce_disable_keeps_structural_repair_but_skips_style_repairs(monkeypatch):
    monkeypatch.setenv("INKU_COERCE_DISABLE", "1")
    score = Score.model_validate({
        "instructions": [
            {"primitive": "line", "color": "black", "relation": {"type": "cutting", "gap": "medium"}},
        ]
    })

    fixed = coerce_score(score, ddl="黒い線を一本引く。赤い円を添える。")

    assert len(fixed.instructions) == 1
    assert fixed.instructions[0].from_ == (0.1, 0.5)
    assert fixed.instructions[0].to == (0.9, 0.5)
    assert fixed.instructions[0].relation is None



def test_count_hint_allows_2000_only_for_literal_grid_request():
    assert count_hint_from_ddl("黒い線を2000本格子状に敷き詰める。") == 2000
    assert count_hint_from_ddl("灰色の線を二千本、一面に敷き詰める。") == 2000
    assert count_hint_from_ddl("黒い線を2000本散らす。") == 1000
    assert count_hint_from_ddl("Tile two thousand short gray pencil vertical lines across the canvas.") == 2000
    assert count_hint_from_ddl("Tile six hundred small rotated red squares across the canvas.") == 600
    assert count_hint_from_ddl("Tile thin black lines in four directions across the wall.") is None
    assert count_hint_from_ddl("黒い線を四つの方向で一面に敷き詰める。黒い線を三本並べる。") is None
    assert count_hint_from_ddl("Tile gray lines across the canvas. Line up three black lines.") is None


def test_coerce_rejects_spontaneous_grid_from_non_tiling_motif_label():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.75, 0.5],
                    "size": [0.03, 0.03],
                    "arrangement": {
                        "count": 4,
                        "layout": "grid",
                        "rows": 2,
                        "cols": 2,
                        "jitter": 0.12,
                    },
                }
            ]
        }
    )

    fixed = coerce_score(
        score,
        ddl="Scatter four thin rotated gray squares in the right half as warehouse grid cuts.",
    )
    arr = fixed.instructions[0].arrangement
    assert arr is not None
    assert arr.layout == "scatter"
    assert arr.count == 4
    assert arr.rows is None
    assert arr.cols is None


def test_coerce_keeps_grid_for_literal_english_tiling_request():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.5, 0.5],
                    "size": [0.03, 0.03],
                    "arrangement": {"count": 400, "layout": "grid"},
                }
            ]
        }
    )

    fixed = coerce_score(score, ddl="Tile four hundred small gray squares across the whole canvas.")
    arr = fixed.instructions[0].arrangement
    assert arr is not None
    assert arr.layout == "grid"
    # The literal count survives the grid restoration whole. It used to lose one
    # cell to the hard ceiling, because coerce added a composition anchor of its
    # own and 400 tiles plus one anchor is 401 marks; that anchor was staffage and
    # went away with the level (v2.11.0), so the description now gets all 400.
    assert arr.count == DEFAULT_LIMITS.max_expanded_primitives
    assert sum(_mark_count(ins) for ins in fixed.instructions) <= DEFAULT_LIMITS.max_expanded_primitives


def test_coerce_restores_literal_grid_count_and_full_field_margin():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.48, 0.45],
                    "to": [0.52, 0.55],
                    "arrangement": {
                        "count": 120,
                        "layout": "grid",
                        "rows": 12,
                        "cols": 10,
                        "margin": 0.45,
                        "density": "high",
                        "cluster_count": 5,
                        "fade": "outward",
                        "preserve_space": True,
                    },
                }
            ]
        }
    )

    fixed = coerce_score(
        score,
        ddl="Tile two thousand short gray pencil vertical lines across the whole canvas.",
    )
    arr = fixed.instructions[0].arrangement
    assert arr is not None
    # The restoration still reads 2000 out of the description and still clears the
    # mismatched rows/cols; the hard ceiling is what brings the total back down.
    assert arr.count == DEFAULT_LIMITS.max_expanded_primitives
    assert arr.rows is None and arr.cols is None
    assert arr.margin == 0.08
    assert arr.density == "none"
    assert arr.cluster_count is None
    assert arr.fade == "none"
    assert arr.preserve_space is False


def test_coerce_restores_missing_literal_grid_arrangement():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.49, 0.49],
                    "size": [0.02, 0.02],
                    "color": "red",
                },
                {
                    "primitive": "arc",
                    "center": [0.72, 0.68],
                    "radius": 0.07,
                    "color": "black",
                    "arrangement": {"count": 3, "layout": "radial"},
                },
            ]
        }
    )

    fixed = coerce_score(
        score,
        ddl="赤い小さな四角を回転させて画面全体に六百個敷き詰める。黒い弧を三つ並べる。",
    )
    grid = fixed.instructions[0].arrangement
    assert grid is not None
    assert grid.layout == "grid"
    # 600 tiles were restored from the description and then met the ceiling; the
    # three arcs beside them are small enough to come through whole.
    assert grid.count == DEFAULT_LIMITS.max_expanded_primitives - 3
    assert grid.margin == 0.08
    assert grid.path == "none"
    assert grid.density == "none"
    assert grid.fade == "none"
    assert grid.preserve_space is False
    assert fixed.instructions[1].arrangement is not None
    assert fixed.instructions[1].arrangement.layout == "radial"


def test_coerce_restores_missing_literal_grid_with_default_count():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.46, 0.5],
                    "to": [0.54, 0.5],
                    "color": "black",
                }
            ]
        }
    )

    fixed = coerce_score(score, ddl="Tile thin black lines in four directions across the whole wall.")
    grid = fixed.instructions[0].arrangement
    assert grid is not None
    assert grid.layout == "grid"
    # The whole ceiling, as in the explicit four-hundred case above.
    assert grid.count == DEFAULT_LIMITS.max_expanded_primitives


def test_coerce_preserves_literal_grid_against_style_and_density_interventions():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.48, 0.45],
                    "to": [0.52, 0.55],
                    "color": "black",
                    "arrangement": {
                        "count": 2000,
                        "layout": "grid",
                        "rows": 40,
                        "cols": 50,
                        "jitter": 0.2,
                        "path": "none",
                        "margin": 0.08,
                        "density": "none",
                        "cluster_count": None,
                        "fade": "none",
                        "preserve_space": False,
                        "rhythm_spacing": "none",
                    },
                }
            ]
        }
    )

    fixed = coerce_score(
        score,
        ddl="静かな余白の中で、楽しく動く黒い線を2000本格子状に敷き詰める。",
    )
    grid = next(
        ins for ins in fixed.instructions
        if ins.arrangement is not None and ins.arrangement.layout == "grid"
    )
    arr = grid.arrangement
    assert arr is not None
    # Style and density interventions still leave the lattice alone. The hard
    # ceiling does reach it -- deliberately, it is the one bound no layout is
    # exempt from -- but it drops the lattice to a smaller lattice of the same
    # shape rather than punching holes in it.
    assert arr.rows is not None and arr.cols is not None
    assert arr.rows * arr.cols <= DEFAULT_LIMITS.max_expanded_primitives
    assert arr.count == arr.rows * arr.cols
    assert abs((arr.rows / arr.cols) / (40 / 50) - 1) < 0.10
    assert arr.jitter == 0.2
    assert arr.path == "none"
    assert arr.margin == 0.08
    assert arr.density == "none"
    assert arr.cluster_count is None
    assert arr.fade == "none"
    assert arr.preserve_space is False
    assert arr.rhythm_spacing == "none"


def test_total_density_budget_does_not_charge_or_shrink_grid():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.49, 0.45],
                    "to": [0.51, 0.55],
                    "arrangement": {
                        "count": 2000,
                        "layout": "grid",
                        "rows": 40,
                        "cols": 50,
                    },
                },
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.005,
                    "filled": True,
                    "arrangement": {"count": 500, "layout": "scatter"},
                },
            ]
        }
    )

    # The governor itself is what this test is about, so measure the governor.
    governed = _with_total_density_budget(list(score.instructions))
    governed_grid = next(i for i in governed if i.arrangement and i.arrangement.layout == "grid")
    governed_scatter = next(i for i in governed if i.arrangement and i.arrangement.layout == "scatter")
    assert governed_grid.arrangement is not None
    assert governed_grid.arrangement.count == 2000
    assert governed_grid.arrangement.rows == 40 and governed_grid.arrangement.cols == 50
    assert governed_scatter.arrangement is not None
    assert governed_scatter.arrangement.count < 500

    # Through the entry point the grid is no longer untouchable: the hard ceiling
    # runs after every governor and answers to no layout. The exemption above is
    # about thinning, which would leave a lattice full of holes; the ceiling
    # shrinks the lattice instead.
    fixed = coerce_score(score)
    grid = next(ins for ins in fixed.instructions if ins.arrangement and ins.arrangement.layout == "grid")
    scatter = next(ins for ins in fixed.instructions if ins.arrangement and ins.arrangement.layout == "scatter")

    assert grid.arrangement is not None
    assert grid.arrangement.rows is not None and grid.arrangement.cols is not None
    assert abs((grid.arrangement.rows / grid.arrangement.cols) / (40 / 50) - 1) < 0.10
    assert scatter.arrangement is not None
    assert scatter.arrangement.count < 500
    assert sum(_mark_count(ins) for ins in fixed.instructions) <= DEFAULT_LIMITS.max_expanded_primitives
