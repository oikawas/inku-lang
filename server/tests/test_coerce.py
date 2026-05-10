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

    assert any(ins.color == "green" or (ins.arrangement and "green" in ins.arrangement.color_cycle) for ins in fixed.instructions)
    assert any("green restored in color_cycle from DDL color intent" in (ins.color_hint or "") for ins in fixed.instructions)


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
    assert any("blue restored in color_cycle from DDL color intent" in (ins.color_hint or "") for ins in fixed.instructions)


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
    assert repaired.color == "gray"
    assert repaired.arrangement is not None
    assert repaired.arrangement.color_cycle == ["gray", "red", "blue", "green"]
    assert "red/blue/green restored in color_cycle from DDL color intent" in (repaired.color_hint or "")
    assert "forest green kept as quiet residue behind warm leaves" in (repaired.color_hint or "")


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
    assert "bamboo green kept as primary contour" in (repaired.color_hint or "")


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
    assert repaired.color == "gray"
    assert repaired.arrangement is not None
    assert repaired.arrangement.color_cycle == ["gray", "green"]
    assert "withered grass kept as muted green-gray" in (repaired.color_hint or "")


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
    assert not any("composition anchor restored" in (ins.color_hint or "") for ins in fixed.instructions)


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
    assert "polygon restored from DDL shape intent" in (polygons[0].color_hint or "")


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
    assert any("triangle restored from DDL shape intent" in (ins.color_hint or "") for ins in fixed.instructions)
    assert any("mountain_sign motif restored from DDL intent" in (ins.color_hint or "") for ins in fixed.instructions)


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

    assert not any("triangle restored from DDL shape intent" in (ins.color_hint or "") for ins in fixed.instructions)


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

    assert not any("mountain_sign motif restored from DDL intent" in (ins.color_hint or "") for ins in fixed.instructions)


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

    hints = [ins.color_hint or "" for ins in fixed.instructions]
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

    motif_hints = [ins.color_hint or "" for ins in fixed.instructions if "motif restored from DDL intent" in (ins.color_hint or "")]
    assert len(motif_hints) == 4
    assert any("leaf_cluster motif restored from DDL intent" in hint for hint in motif_hints)
    assert any("paper_shard motif restored from DDL intent" in hint for hint in motif_hints)
    assert not any("ripple_knot motif restored from DDL intent" in hint for hint in motif_hints)
    assert not any("mountain_sign motif restored from DDL intent" in hint for hint in motif_hints)


def test_coerce_score_adds_generic_anchor_for_line_only_warm_scene():
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

    fixed = coerce_score(score, ddl="夏祭りの灯りが遠くで揺れる。")

    anchors = [ins for ins in fixed.instructions if "composition anchor restored for shape/color diversity" in (ins.color_hint or "")]
    assert len(anchors) == 1
    assert anchors[0].primitive == "ellipse"
    assert anchors[0].color == "red"


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
    assert not any("composition anchor restored for shape/color diversity" in (ins.color_hint or "") for ins in fixed.instructions)


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
    assert any("blue restored in color_cycle from DDL color intent" in (ins.color_hint or "") for ins in fixed.instructions)


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
                    "color_hint": "material inferred from DDL",
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
                    "color_hint": "透明な膜; material inferred from DDL: pencil",
                },
                {
                    "primitive": "ellipse",
                    "center": [0.7, 0.5],
                    "size": [0.3, 0.1],
                    "color": "black",
                    "color_hint": "material inferred from DDL: pencil",
                },
            ],
        }
    )

    fixed = coerce_score(score)

    assert len(fixed.instructions) == 1
    assert fixed.instructions[0].color_hint is not None
    assert "透明な膜" in fixed.instructions[0].color_hint


def test_coerce_score_governs_quiet_high_density_scatter():
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.02, 0.05],
                    "color": "white",
                    "color_hint": "ネオンの滲み",
                    "arrangement": {
                        "count": 180,
                        "layout": "scatter",
                        "density": "high",
                    },
                },
            ],
        }
    )

    fixed = coerce_score(score, ddl="夜のガラス越しに、街のネオンが涙のように滲んでいる。")

    arr = fixed.instructions[0].arrangement
    assert arr is not None
    assert arr.count == 24
    assert arr.preserve_space is True
    assert arr.fade == "outward"
    assert "neon blur density governed" in (fixed.instructions[0].color_hint or "")
    assert any("quiet expression accent restored" in (ins.color_hint or "") for ins in fixed.instructions)


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
    assert "neon blur vertical density governed" in (fixed.instructions[0].color_hint or "")


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
                    "color_hint": "coverage from DDL clause: 右端に白いクレヨンの縦長の四角を置く",
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
    assert "quiet symbolic shape tempered" in (ins.color_hint or "")


def test_coerce_score_repairs_polygon_fields_and_tempers_quiet_polygon():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "polygon",
                    "center": [0.55, 0.4],
                    "radius": 0.18,
                    "sides": 12,
                    "color_hint": "coverage from DDL clause: 鉱物のような多角形を置く",
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
    assert "quiet symbolic shape tempered" in (ins.color_hint or "")


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
    assert "motion energy restored" in (ins.color_hint or "")


def test_coerce_score_restores_context_energy_for_regressed_scenes_without_touching_good_presence_scene():
    base = Score.model_validate(
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

    leaf = coerce_score(base, ddl="秋の森で、落ち葉が湿った土に深い赤を沈めている。")
    assert any("leaf/grain energy restored" in (ins.color_hint or "") for ins in leaf.instructions)

    corridor = coerce_score(base, ddl="廃校の廊下に、夕方の光が長い沈黙を置いていく。")
    assert any("silence/layer energy restored" in (ins.color_hint or "") for ins in corridor.instructions)

    factory = coerce_score(base, ddl="静かな工場跡で、錆びた鉄骨が空を細かく分けている。")
    assert any(ins.primitive == "polygon" and "hard edge energy restored" in (ins.color_hint or "") for ins in factory.instructions)

    bicycle = coerce_score(base, ddl="夕暮れの坂道で、自転車の影だけが先に帰っていく。")
    assert any("playful motion energy restored as a small moving color cluster" in (ins.color_hint or "") for ins in bicycle.instructions)

    red_scene = Score.model_validate(
        {
            "background": "red",
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.05, 0.02],
                    "color": "black",
                }
            ],
        }
    )
    red_bicycle = coerce_score(red_scene, ddl="夕暮れの坂道で、自転車の影だけが先に帰っていく。")
    playful = [ins for ins in red_bicycle.instructions if "playful motion energy restored as a small moving color cluster" in (ins.color_hint or "")]
    assert red_bicycle.background == "white"
    assert playful
    assert playful[0].primitive == "ellipse"
    assert playful[0].color == "red"
    assert playful[0].arrangement is not None
    assert playful[0].arrangement.count == 5
    assert "red" in playful[0].arrangement.color_cycle

    bus_stop = coerce_score(base, ddl="雨のバス停で、待つ人の気配が透明な膜になっている。")
    assert not any("energy restored" in (ins.color_hint or "") for ins in bus_stop.instructions)


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
    assert "explicit count constraint enforced" in (fixed.instructions[0].color_hint or "")


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
    assert "explicit color-only constraint enforced" in (ins.color_hint or "")


def test_coerce_score_does_not_treat_motif_only_as_color_only_constraint():
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

    fixed = coerce_score(score, ddl="夕暮れの坂道で、黒い影だけが先に帰っていく。")

    playful = [ins for ins in fixed.instructions if "playful motion energy restored as a small moving color cluster" in (ins.color_hint or "")]
    assert fixed.background == "white"
    assert playful
    assert playful[0].color == "red"
    assert playful[0].arrangement is not None
    assert "red" in playful[0].arrangement.color_cycle
    assert not any("explicit color-only constraint enforced" in (ins.color_hint or "") for ins in fixed.instructions)


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
    assert "quiet single large shape tempered" in (ins.color_hint or "")


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
    assert fixed.instructions[0].color == "black"
    assert "white foreground made visible" in (fixed.instructions[0].color_hint or "")


def test_coerce_score_governs_stage1_inferred_black_background_when_source_did_not_request_it():
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

    assert fixed.background == "white"


def test_coerce_score_governs_generated_background_plan_without_original_source_context():
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

    assert fixed.background == "white"


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


def test_coerce_score_governs_dawn_background_generated_from_source_context():
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

    assert fixed.background == "white"


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
    assert "large filled shape tempered" in (ins.color_hint or "")


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
    assert "rhythm variation restored without increasing count" in (ins.color_hint or "")
    assert "ma pressure restored" in (ins.color_hint or "")


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
    assert "ma pressure restored" in (ins.color_hint or "")


def test_coerce_score_adds_surface_tension_for_heavy_surface_context():
    score = Score.model_validate(
        {
            "background": "red",
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.22],
                    "size": [0.24, 0.14],
                    "color": "black",
                    "filled": True,
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="赤い布の上で、熟した果実が重く静かな影を落とす。")

    assert len(fixed.instructions) == 2
    assert fixed.instructions[1].primitive == "arc"
    assert fixed.instructions[1].weight == "hair"
    assert "surface tension restored" in (fixed.instructions[1].color_hint or "")


def test_coerce_score_adds_edge_light_event_for_dark_light_context():
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.24, 0.12],
                    "to": [0.24, 0.88],
                    "color": "blue",
                    "weight": "hair",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="真夜中の港で、遠い灯台の光だけが黒い海を切っている。")

    edge = [ins for ins in fixed.instructions if "edge light event restored" in (ins.color_hint or "")]
    assert edge
    assert edge[0].primitive == "line"
    assert edge[0].arrangement is not None
    assert edge[0].arrangement.count == 2
    assert edge[0].arrangement.preserve_space is True


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

    assert not any("edge light event restored" in (ins.color_hint or "") for ins in fixed.instructions)
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

    assert not any("edge light event restored" in (ins.color_hint or "") for ins in fixed.instructions)


def test_coerce_score_prefers_vanishing_trace_over_weak_edge_light_context():
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

    fixed = coerce_score(score, ddl="黒い夜の窓辺で、指で描いた円がすぐに消えかけている。")

    assert not any("edge light event restored" in (ins.color_hint or "") for ins in fixed.instructions)
    assert any("vanishing trace restored" in (ins.color_hint or "") for ins in fixed.instructions)


def test_coerce_score_uses_edge_light_over_vanishing_trace_for_strong_light_cut():
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

    fixed = coerce_score(score, ddl="真夜中の港で、灯台の一筋の光が黒い海を切って消えていく。")

    assert any("edge light event restored" in (ins.color_hint or "") for ins in fixed.instructions)
    assert not any("vanishing trace restored" in (ins.color_hint or "") for ins in fixed.instructions)


def test_coerce_score_adds_vanishing_trace_for_fading_context():
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.42, 0.50],
                    "size": [0.10, 0.04],
                    "color": "gray",
                }
            ],
        }
    )

    fixed = coerce_score(score, ddl="雪原の端で、小さな足跡が遠くの青へ消えていく。")

    trace = [ins for ins in fixed.instructions if "vanishing trace restored" in (ins.color_hint or "")]
    assert trace
    assert trace[0].primitive == "arc"
    assert trace[0].arrangement is not None
    assert trace[0].arrangement.fade == "directional"
    assert trace[0].arrangement.rhythm_spacing == "loose"


def test_fallback_score_preserves_explicit_count_circle_and_polygon():
    from inku_server.api import _fallback_score_from_ddl

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
    from inku_server.api import _fallback_score_from_ddl
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

    assert score.background == "white"
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
