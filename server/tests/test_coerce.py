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


def test_coerce_score_prioritizes_triangle_delivery_for_roof_intent_when_many_instructions():
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

    accents = [ins for ins in fixed.instructions if "composition accent restored for shape/color diversity" in (ins.color_hint or "")]
    assert len(accents) == 1
    assert accents[0].primitive == "arc"
    assert accents[0].color == "blue"


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
    assert fixed.presence.symmetry == "bilateral"
    assert fixed.presence.gaze_pressure == "low"


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
    assert arr.count == 64
    assert arr.preserve_space is True
    assert arr.fade == "outward"
    assert "quiet density governed" in (fixed.instructions[0].color_hint or "")
    assert any("quiet expression accent restored" in (ins.color_hint or "") for ins in fixed.instructions)


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
