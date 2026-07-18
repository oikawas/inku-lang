from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from inku_server.cloudform import (
    generate_cloudform_contour,
    polygon_self_intersects,
    sample_closed_catmull_rom,
)
from inku_server.coerce import coerce_score
from inku_server.composer import SYSTEM_PROMPT as COMPOSER_PROMPT_JA
from inku_server.composer import SYSTEM_PROMPT_EN as COMPOSER_PROMPT_EN
from inku_server.interpreter import (
    EXAMPLE_POOL,
    EXAMPLE_POOL_EN,
    SYSTEM_PROMPT_PREFIX,
    SYSTEM_PROMPT_PREFIX_EN,
)
from inku_server import db
from inku_server.renderer import (
    _bbox_for_instruction,
    _resolve_performance_score,
    render,
)
from inku_server.schema import Score, migrate_score_payload


def _cloud_score(**instruction_overrides: object) -> Score:
    instruction = {
        "primitive": "cloudform",
        "center": [0.5, 0.5],
        "size": [0.48, 0.32],
        "color": "black",
        "weight": "pen",
    }
    instruction.update(instruction_overrides)
    return Score.model_validate(
        {"version": "0.1.0", "background": "white", "instructions": [instruction]}
    )


def _contour(seed: int, *, mark_index: int = 0):
    return generate_cloudform_contour(
        (500.0, 500.0),
        (480.0, 320.0),
        performance_seed=seed,
        instruction_index=2,
        mark_index=mark_index,
    )


def test_cloudform_schema_is_strict_and_stores_no_contour_coordinates() -> None:
    score = _cloud_score()
    assert score.instructions[0].primitive == "cloudform"
    assert "points" not in score.instructions[0].model_dump()
    with pytest.raises(ValidationError):
        _cloud_score(points=[[0.0, 0.0], [1.0, 1.0]])


def test_legacy_score_migration_is_idempotent_and_version_is_strict() -> None:
    legacy = {"background": "white", "instructions": []}
    once = migrate_score_payload(legacy)
    twice = migrate_score_payload(once)
    assert (
        once
        == twice
        == {
            "version": "0.1.0",
            "background": "white",
            "instructions": [],
        }
    )
    assert Score.model_validate(legacy).version == "0.1.0"
    with pytest.raises(ValidationError):
        Score.model_validate({**legacy, "version": "future"})


def test_cloudform_is_closed_deterministic_and_self_intersection_free_200_seeds() -> (
    None
):
    for seed in range(200):
        contour = _contour(seed)
        assert contour.path_d.startswith("M ")
        assert contour.path_d.endswith(" Z")
        assert not polygon_self_intersects(contour.points)
        assert not polygon_self_intersects(sample_closed_catmull_rom(contour.points))
        assert contour == _contour(seed)


def test_cloudform_replay_varies_and_same_seed_matches_exactly() -> None:
    score = _cloud_score()
    same_a = render(score, render_seed=731)
    same_b = render(score, render_seed=731)
    assert same_a == same_b
    paths = {
        re.search(
            r'<path[^>]*class="cloudform[^"]*"[^>]*d="([^"]+)"',
            render(score, render_seed=seed),
        ).group(1)
        for seed in range(5)
    }
    assert len(paths) == 5


def test_arranged_cloudforms_have_distinct_contours() -> None:
    score = _cloud_score(
        arrangement={"count": 4, "layout": "horizontal", "margin": 0.15}
    )
    svg = render(score, render_seed=912)
    paths = re.findall(r'<path[^>]*class="cloudform[^"]*"[^>]*d="([^"]+)"', svg)
    assert len(paths) == 4
    assert len(set(paths)) == 4


@pytest.mark.parametrize("profile", ["display", "editable", "compat"])
@pytest.mark.parametrize("texture", ["wash", "stipple", "hatch", "aquatint"])
def test_cloudform_surface_profiles_and_carve(profile: str, texture: str) -> None:
    score = _cloud_score(
        surface={"texture": texture},
        mode="carve",
        carve_depth="bright",
    )
    svg = render(score, render_seed=44, svg_profile=profile)
    assert "cloudform" in svg
    assert f"surface_000_000_{texture}" in svg


def test_coerce_does_not_inject_cloudform() -> None:
    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.2,
                }
            ],
        }
    )
    coerced = coerce_score(score)
    assert all(ins.primitive != "cloudform" for ins in coerced.instructions)


def test_stage1_selection_rules_and_negative_examples_are_bilingual() -> None:
    assert (
        "未知・不明瞭な対象の fallback に雲形を使ってはいけない" in SYSTEM_PROMPT_PREFIX
    )
    assert "Never use cloudform as a fallback" in SYSTEM_PROMPT_PREFIX_EN
    assert any(
        "雲形" not in example["output"] and "謎の装置" in example["input"]
        for example in EXAMPLE_POOL
    )
    assert any(
        "cloudform" not in example["output"] and "mysterious device" in example["input"]
        for example in EXAMPLE_POOL_EN
    )


def test_stage2_only_transcribes_cloudform_without_contour_fields() -> None:
    assert 'primitive="cloudform", center+size' in COMPOSER_PROMPT_JA
    assert "輪郭座標・制御点は生成しない" in COMPOSER_PROMPT_JA
    assert 'primitive="cloudform" with center+size' in COMPOSER_PROMPT_EN
    assert "Never generate contour coordinates or control points" in COMPOSER_PROMPT_EN
    assert "同じ雲形 instruction を必ず残す" in COMPOSER_PROMPT_JA
    assert "the output must retain the same cloudform instruction" in COMPOSER_PROMPT_EN
    assert "\"mode\":\"carve\",\"carve_depth\":\"bright\"" in COMPOSER_PROMPT_JA
    assert "\"mode\":\"carve\",\"carve_depth\":\"bright\"" in COMPOSER_PROMPT_EN


def test_stage2_literal_delivery_restores_explicit_cloudform_from_ellipse() -> None:
    from inku_server.composer import _enforce_cloudform_literal_delivery

    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.75, 0.5],
                    "size": [0.1, 0.08],
                    "arrangement": {"count": 7, "layout": "scatter"},
                }
            ]
        }
    )

    restored = _enforce_cloudform_literal_delivery(
        score, "Scatter seven small green cloudforms across the right half."
    )
    untouched = _enforce_cloudform_literal_delivery(score, "Scatter seven ellipses.")

    replaced_square = _enforce_cloudform_literal_delivery(
        Score.model_validate(
            {
                "instructions": [
                    {"primitive": "square", "position": [0.1, 0.3], "size": [0.2, 0.2]},
                    {"primitive": "square", "position": [0.6, 0.4], "size": [0.2, 0.1]},
                ]
            }
        ),
        "黒い四角を置く。赤い雲形を置く。",
    )

    assert restored.instructions[0].primitive == "cloudform"
    assert restored.instructions[0].arrangement.count == 7
    assert untouched.instructions[0].primitive == "ellipse"
    assert replaced_square.instructions[0].primitive == "square"
    assert replaced_square.instructions[1].primitive == "cloudform"
    assert replaced_square.instructions[1].center == (0.7, 0.45)
    omitted = _enforce_cloudform_literal_delivery(
        Score.model_validate(
            {
                "instructions": [
                    {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}
                ]
            }
        ),
        "Scatter seven small green cloudforms across the right half.",
    )

    assert omitted.instructions[-1].primitive == "cloudform"
    assert omitted.instructions[-1].arrangement is not None
    assert omitted.instructions[-1].arrangement.count == 7


def test_stage2_timeout_fallback_preserves_explicit_cloudform() -> None:
    from inku_server.api import _fallback_score_from_ddl

    score = _fallback_score_from_ddl(
        "Scatter seven small green cloudforms across the right half.", lang="en"
    )

    assert score.instructions[0].primitive == "cloudform"
    assert score.instructions[0].arrangement is not None
    assert score.instructions[0].arrangement.count == 7


def test_stage2_literal_print_transcription_composes_cloudform_carve() -> None:
    from inku_server.composer import _enforce_print_literal_transcription

    score = _cloud_score(color="white")
    result = _enforce_print_literal_transcription(
        score,
        "Ground: black mezzotint. Carve light from the dark ground (bright). Place one white cloudform.",
    )

    assert not isinstance(result.canvas, str)
    assert result.canvas.ground is not None
    assert result.canvas.ground.material == "mezzotint"
    assert result.canvas.ground.tone == "black"
    assert result.instructions[0].mode == "carve"
    assert result.instructions[0].carve_depth == "bright"


def test_literal_not_touching_relation_is_transcribed_to_cloudform() -> None:
    from inku_server.composer import _enforce_relation_literal_gate

    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.1, 0.35],
                    "size": [0.3, 0.3],
                },
                {
                    "primitive": "cloudform",
                    "center": [0.7, 0.5],
                    "size": [0.3, 0.3],
                },
            ]
        }
    )

    result = _enforce_relation_literal_gate(
        score,
        "黒い四角を置く。赤い雲形を前の形に触れないように置く。",
    )

    assert result.instructions[1].relation is not None
    assert result.instructions[1].relation.type == "not_touching"

    reversed_score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "cloudform", "center": [0.7, 0.5], "size": [0.3, 0.2]},
                {"primitive": "square", "position": [0.1, 0.35], "size": [0.3, 0.3]},
            ]
        }
    )
    reordered = _enforce_relation_literal_gate(
        reversed_score,
        "黒い四角を置く。赤い雲形を置く。前の形に触れない。",
    )
    assert reordered.instructions[0].primitive == "square"
    assert reordered.instructions[1].primitive == "cloudform"
    assert reordered.instructions[1].relation is not None
    assert reordered.instructions[1].relation.type == "not_touching"


def test_cloudform_proportion_maps_to_contour_aspect() -> None:
    contour = generate_cloudform_contour(
        (0.5, 0.5),
        (0.9, 0.2),
        performance_seed=72,
        instruction_index=0,
        mark_index=0,
    )
    xs = [point[0] for point in contour.points]
    ys = [point[1] for point in contour.points]
    assert (max(xs) - min(xs)) > (max(ys) - min(ys)) * 3


def test_cloudform_touch_grammar_changes_edge_without_breaking_replay() -> None:
    kwargs = {
        "center": (500.0, 500.0),
        "size": (500.0, 320.0),
        "performance_seed": 994,
        "instruction_index": 0,
        "mark_index": 0,
    }
    pencil = generate_cloudform_contour(**kwargs, weight="pencil")
    rotring = generate_cloudform_contour(**kwargs, weight="rotring")
    assert pencil.path_d != rotring.path_d
    assert rotring == generate_cloudform_contour(**kwargs, weight="rotring")


def test_periodic_seam_has_continuous_discrete_curvature() -> None:
    points = _contour(117).points

    def turn(index: int) -> float:
        before = points[(index - 1) % len(points)]
        point = points[index]
        after = points[(index + 1) % len(points)]
        first = (point[0] - before[0], point[1] - before[1])
        second = (after[0] - point[0], after[1] - point[1])
        dot = first[0] * second[0] + first[1] * second[1]
        cross = first[0] * second[1] - first[1] * second[0]
        return abs(__import__("math").atan2(cross, dot))

    seam_turns = [turn(len(points) - 1), turn(0), turn(1)]
    assert max(seam_turns) - min(seam_turns) < 0.35


def test_cloudform_can_be_previous_relation_contour() -> None:
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "cloudform",
                    "center": [0.5, 0.5],
                    "size": [0.42, 0.28],
                },
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.03,
                    "relation": {"type": "along", "gap": "narrow"},
                },
            ]
        }
    )
    resolved = _resolve_performance_score(score, 301)
    cloud = resolved.instructions[0]
    follower = resolved.instructions[1]
    assert _bbox_for_instruction(cloud, 301, 0) is not None
    assert follower.center is not None
    assert follower.center != (0.5, 0.5)
    assert "cloudform" in render(score, render_seed=301)


def test_cloudform_render_does_not_add_contour_to_rh2_inputs() -> None:
    score = _cloud_score().model_dump(mode="json", by_alias=True)
    base = {
        "score": score,
        "render_seed": 22,
        "vary_seed": 4,
        "canvas_aspect": "square",
        "render_color_catalog_id": "default",
        "render_engine_id": "default",
        "render_engine_version": "4",
        "svg": render(_cloud_score(), render_seed=22),
    }
    changed_artifact = {**base, "svg": render(_cloud_score(), render_seed=23)}
    assert db.render_hash_for_item(base).startswith("rh2:")
    assert db.render_hash_for_item(changed_artifact) == db.render_hash_for_item(base)


@pytest.mark.parametrize("relation_type", ["along", "not_touching", "cutting"])
def test_cloudform_previous_contour_supports_relation_types(relation_type: str) -> None:
    follower = {
        "primitive": "circle",
        "center": [0.5, 0.5],
        "radius": 0.025,
        "relation": {"type": relation_type, "gap": "narrow"},
    }
    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "cloudform", "center": [0.5, 0.5], "size": [0.44, 0.3]},
                follower,
            ]
        }
    )
    resolved = _resolve_performance_score(score, 802)
    assert resolved.instructions[1].relation is None
    assert resolved.instructions[1].center is not None
    assert render(score, render_seed=802).count("cloudform") >= 1


def test_cloudform_previous_contour_supports_between_relation() -> None:
    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "circle", "center": [0.2, 0.3], "radius": 0.04},
                {"primitive": "cloudform", "center": [0.75, 0.65], "size": [0.3, 0.2]},
                {
                    "primitive": "square",
                    "position": [0.45, 0.45],
                    "size": [0.04, 0.04],
                    "relation": {"type": "between", "gap": "medium"},
                },
            ]
        }
    )
    resolved = _resolve_performance_score(score, 803)
    square = resolved.instructions[2]
    assert square.relation is None
    assert square.position is not None
    assert 0.2 < square.position[0] < 0.75
