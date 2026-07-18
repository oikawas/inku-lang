from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from inku_server.api import _render_score_svg
from inku_server.renderer import (
    _arc_path_d,
    _endpoint_geometry,
    _resolve_performance_score,
)
from inku_server.schema import Score
from inku_server.sketch_relations import (
    arc_geometry_from_bow,
    prepare_sketch_score_payload,
)


def _leaf_payload() -> dict:
    return {
        "instructions": [
            {
                "primitive": "arc",
                "span": 0.16,
                "bow": 0.06,
                "at": {"region": [0.35, 0.40, 0.65, 0.60]},
                "weight": "pencil",
                "color": "green",
                "variation": {
                    "amplitude": "fine",
                    "frequency": "high",
                    "quality": "perlin",
                    "dimensions": ["position_x", "position_y"],
                },
            },
            {
                "primitive": "arc",
                "bow": -0.06,
                "relation": {"type": "touching", "contact": "both_ends"},
                "weight": "pencil",
                "color": "green",
                "variation": {
                    "amplitude": "fine",
                    "frequency": "high",
                    "quality": "perlin",
                    "dimensions": ["position_x", "position_y"],
                },
            },
        ]
    }


def _assert_point_close(
    actual: tuple[float, float], expected: tuple[float, float]
) -> None:
    assert actual[0] == pytest.approx(expected[0], abs=1e-8)
    assert actual[1] == pytest.approx(expected[1], abs=1e-8)


def test_bow_conversion_uses_mirrored_minor_arcs_with_requested_sagitta() -> None:
    start = (0.42, 0.50)
    end = (0.58, 0.50)
    positive = arc_geometry_from_bow(start, end, 0.06)
    negative = arc_geometry_from_bow(start, end, -0.06)

    assert positive["radius"] == pytest.approx(0.08333333333333334)
    assert negative["radius"] == pytest.approx(positive["radius"])
    assert positive["center"][0] == pytest.approx(0.50)
    assert negative["center"][0] == pytest.approx(0.50)
    assert positive["center"][1] == pytest.approx(0.4766666666666667)
    assert negative["center"][1] == pytest.approx(0.5233333333333333)
    assert abs(positive["angle_end"] - positive["angle_start"]) < 180
    assert abs(negative["angle_end"] - negative["angle_start"]) < 180


def test_svg_arc_uses_minor_flag_for_negative_minor_angle_range() -> None:
    path = _arc_path_d(0.5, 0.5, 0.1, 143.0, 37.0)

    assert " 0 0 1 " in path


def test_prototype_relations_remain_outside_strict_schema_when_flag_is_off(
    monkeypatch,
) -> None:
    monkeypatch.delenv("INKU_SKETCH_RELATIONS", raising=False)
    payload = _leaf_payload()

    assert prepare_sketch_score_payload(payload) is payload
    with pytest.raises(ValidationError):
        Score.model_validate(payload)


def test_render_svg_boundary_is_flag_gated(monkeypatch) -> None:
    payload = _leaf_payload()
    monkeypatch.delenv("INKU_SKETCH_RELATIONS", raising=False)
    with pytest.raises(ValidationError):
        _render_score_svg(
            payload,
            catalog_id=None,
            render_seed=5,
        )

    monkeypatch.setenv("INKU_SKETCH_RELATIONS", "1")
    svg = _render_score_svg(
        payload,
        catalog_id=None,
        render_seed=5,
    )
    assert svg.startswith("<svg")


def test_touching_snaps_both_arc_endpoints_after_region_resolution(monkeypatch) -> None:
    monkeypatch.setenv("INKU_SKETCH_RELATIONS", "1")
    score = Score.model_validate(prepare_sketch_score_payload(_leaf_payload()))

    positions: list[tuple[float, float]] = []
    for seed in (11, 29):
        resolved = _resolve_performance_score(score, seed)
        first = _endpoint_geometry(resolved.instructions[0], seed, 0)
        second = _endpoint_geometry(resolved.instructions[1], seed, 1)
        assert first is not None
        assert second is not None
        _assert_point_close(second[0], first[0])
        _assert_point_close(second[1], first[1])
        assert resolved.instructions[1].variation is not None
        assert "__inku_leaf_sketch_relation__" not in (
            resolved.instructions[1].color_hint or ""
        )
        positions.append(first[0])

    assert positions[0] != positions[1]


def test_continuing_snaps_to_cloudform_seam_and_matches_terminal_tangent(
    monkeypatch,
) -> None:
    monkeypatch.setenv("INKU_SKETCH_RELATIONS", "1")
    payload = {
        "instructions": [
            {
                "primitive": "cloudform",
                "center": [0.70, 0.82],
                "size": [0.16, 0.12],
                "weight": "chalk",
                "color": "gray",
                "variation": {
                    "amplitude": "fine",
                    "frequency": "high",
                    "quality": "perlin",
                },
            },
            {
                "primitive": "arc",
                "center": [0.50, 0.50],
                "radius": 0.04,
                "angle_start": 180,
                "angle_end": 20,
                "relation": {"type": "continuing"},
                "weight": "chalk",
                "color": "gray",
            },
        ]
    }
    score = Score.model_validate(prepare_sketch_score_payload(payload))
    resolved = _resolve_performance_score(score, 41)
    previous = _endpoint_geometry(resolved.instructions[0], 41, 0)
    follower = _endpoint_geometry(resolved.instructions[1], 41, 1)

    assert previous is not None
    assert follower is not None
    _assert_point_close(follower[0], previous[1])
    previous_tangent = previous[3]
    follower_tangent = follower[2]
    dot = (
        previous_tangent[0] * follower_tangent[0]
        + previous_tangent[1] * follower_tangent[1]
    )
    lengths = math.hypot(*previous_tangent) * math.hypot(*follower_tangent)
    assert dot / lengths == pytest.approx(1.0, abs=1e-8)


def test_unresolvable_continuing_is_drop_only(monkeypatch) -> None:
    monkeypatch.setenv("INKU_SKETCH_RELATIONS", "1")
    payload = {
        "instructions": [
            {
                "primitive": "circle",
                "center": [0.40, 0.40],
                "radius": 0.08,
            },
            {
                "primitive": "arc",
                "center": [0.60, 0.60],
                "radius": 0.04,
                "angle_start": 180,
                "angle_end": 20,
                "relation": {"type": "continuing"},
            },
        ]
    }
    score = Score.model_validate(prepare_sketch_score_payload(payload))
    resolved = _resolve_performance_score(score, 7)
    follower = resolved.instructions[1]

    assert follower.center == pytest.approx((0.60, 0.60))
    assert follower.relation is None
    assert "__inku_leaf_sketch_relation__" not in (follower.color_hint or "")


def test_all_leaf_sketch_scores_validate_through_flagged_api_boundary(
    monkeypatch,
) -> None:
    monkeypatch.setenv("INKU_SKETCH_RELATIONS", "1")
    scores_dir = (
        Path(__file__).resolve().parents[2] / "cli" / "bench" / "leaf-sketch" / "scores"
    )
    paths = sorted(scores_dir.glob("*.json"))

    assert len(paths) == 10
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        Score.model_validate(prepare_sketch_score_payload(payload))
        svg = _render_score_svg(payload, catalog_id=None, render_seed=3)
        assert svg.startswith("<svg")
