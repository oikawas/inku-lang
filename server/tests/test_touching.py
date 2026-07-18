from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pydantic import ValidationError

from inku_server.arc_geometry import arc_from_endpoints_and_sagitta
from inku_server.coerce import coerce_score
from inku_server.composer import (
    _enforce_relation_literal_gate,
    _literal_relation_types,
)
from inku_server.renderer import render
from inku_server.schema import Score, migrate_score_payload
from inku_server.stroke_engine import synthesize_stroke


_ARC_D = re.compile(
    r"M ([\d.-]+) ([\d.-]+) A ([\d.-]+) [\d.-]+ 0 ([01]) ([01]) ([\d.-]+) ([\d.-]+)"
)
_ROTATE = re.compile(r"rotate\(([-\d.]+),([-\d.]+),([-\d.]+)\)")


def _arc_instruction(
    start: tuple[float, float],
    end: tuple[float, float],
    sagitta: float,
    **extra: object,
) -> dict:
    geometry = arc_from_endpoints_and_sagitta(start, end, sagitta)
    result = {
        "primitive": "arc",
        "center": list(geometry.center),
        "radius": geometry.radius,
        "angle_start": geometry.angle_start,
        "angle_end": geometry.angle_end,
        "weight": "rotring",
    }
    result.update(extra)
    return result


def _score() -> Score:
    return Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.18, 0.50],
                    "to": [0.82, 0.44],
                    "weight": "rotring",
                },
                _arc_instruction(
                    (0.42, 0.50),
                    (0.58, 0.50),
                    0.06,
                    rotation=31,
                    relation={"type": "along", "gap": "narrow"},
                ),
                _arc_instruction(
                    (0.44, 0.50),
                    (0.56, 0.50),
                    0.045,
                    relation={"type": "touching", "contact": "both_ends"},
                ),
            ]
        }
    )


def _rotate(
    point: tuple[float, float], degrees: float, center: tuple[float, float]
) -> tuple[float, float]:
    angle = math.radians(degrees)
    dx, dy = point[0] - center[0], point[1] - center[1]
    return (
        center[0] + dx * math.cos(angle) - dy * math.sin(angle),
        center[1] + dx * math.sin(angle) + dy * math.cos(angle),
    )


def _svg_arcs(svg: str) -> list[dict[str, object]]:
    root = ET.fromstring(svg)
    result = []
    for element in root.iter():
        path_d = element.attrib.get("d", "")
        match = _ARC_D.fullmatch(path_d)
        if match is None:
            continue
        start = (float(match[1]), float(match[2]))
        end = (float(match[6]), float(match[7]))
        transform = element.attrib.get("transform", "")
        rotation = _ROTATE.fullmatch(transform)
        if rotation is not None:
            center = (float(rotation[2]), float(rotation[3]))
            start = _rotate(start, float(rotation[1]), center)
            end = _rotate(end, float(rotation[1]), center)
        result.append(
            {
                "start": start,
                "end": end,
                "radius": float(match[3]),
                "large": int(match[4]),
                "sweep": int(match[5]),
            }
        )
    return result


def _distance(
    left: tuple[float, float], right: tuple[float, float]
) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _center_and_tangents(arc: dict[str, object]):
    start = arc["start"]
    end = arc["end"]
    radius = arc["radius"]
    sweep = arc["sweep"]
    assert isinstance(start, tuple)
    assert isinstance(end, tuple)
    assert isinstance(radius, float)
    assert isinstance(sweep, int)
    dx, dy = end[0] - start[0], end[1] - start[1]
    chord = math.hypot(dx, dy)
    midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    offset = math.sqrt(max(0.0, radius * radius - chord * chord / 4))
    normal = (-dy / chord, dx / chord)
    candidates = [
        (midpoint[0] + normal[0] * offset, midpoint[1] + normal[1] * offset),
        (midpoint[0] - normal[0] * offset, midpoint[1] - normal[1] * offset),
    ]

    def cross(center):
        first = (start[0] - center[0], start[1] - center[1])
        second = (end[0] - center[0], end[1] - center[1])
        return first[0] * second[1] - first[1] * second[0]

    center = next(
        item for item in candidates if (cross(item) >= 0) == (sweep == 1)
    )

    def tangent(point):
        radial = (point[0] - center[0], point[1] - center[1])
        return (
            (-radial[1], radial[0])
            if sweep == 1
            else (radial[1], -radial[0])
        )

    return center, tangent(start), tangent(end)


def _angle(left: tuple[float, float], right: tuple[float, float]) -> float:
    denominator = math.hypot(*left) * math.hypot(*right)
    cosine = max(
        -1.0,
        min(1.0, (left[0] * right[0] + left[1] * right[1]) / denominator),
    )
    return math.degrees(math.acos(cosine))


def test_touching_schema_is_strict_versioned_and_migration_is_idempotent() -> None:
    legacy = {"instructions": []}
    assert migrate_score_payload(migrate_score_payload(legacy)) == {
        "version": "0.1.0",
        "instructions": [],
    }
    relation = {"type": "touching", "contact": "both_ends"}
    score = Score.model_validate(
        {
            "version": "0.1.0",
            "instructions": [
                {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5]},
                {
                    "primitive": "line",
                    "from": [0.3, 0.4],
                    "to": [0.7, 0.4],
                    "relation": relation,
                },
            ],
        }
    )
    assert score.instructions[1].relation.contact == "both_ends"
    with pytest.raises(ValidationError):
        Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "line",
                        "from": [0.2, 0.5],
                        "to": [0.8, 0.5],
                        "relation": {"type": "touching"},
                    }
                ]
            }
        )


def test_invalid_touching_is_drop_only_for_closed_or_endpointless_targets() -> None:
    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1},
                {
                    "primitive": "arc",
                    "center": [0.5, 0.5],
                    "radius": 0.08,
                    "angle_start": 20,
                    "angle_end": 120,
                    "relation": {"type": "touching", "contact": "both_ends"},
                },
                {
                    "primitive": "circle",
                    "center": [0.4, 0.4],
                    "radius": 0.04,
                    "relation": {"type": "touching", "contact": "both_ends"},
                },
            ]
        }
    )
    report: dict[str, int] = {}
    coerced = coerce_score(score, branch_report=report)
    assert all(instruction.relation is None for instruction in coerced.instructions)
    assert report["drop_invalid_relations"] == 2


def test_touching_svg_geometry_and_replay_contract_across_200_seeds() -> None:
    score = _score()
    seen_poses: set[tuple[float, float, float]] = set()
    for seed in range(200):
        svg = render(score, render_seed=seed)
        assert svg == render(score, render_seed=seed)
        arcs = _svg_arcs(svg)
        assert len(arcs) == 2
        first, second = arcs
        assert first["large"] == second["large"] == 0
        assert _distance(first["start"], second["start"]) <= 2.0
        assert _distance(first["end"], second["end"]) <= 2.0

        first_center, first_start_tangent, first_end_tangent = (
            _center_and_tangents(first)
        )
        second_center, second_start_tangent, second_end_tangent = (
            _center_and_tangents(second)
        )
        assert _angle(first_start_tangent, second_start_tangent) >= 30.0
        assert _angle(first_end_tangent, second_end_tangent) >= 30.0
        assert first_center != second_center

        for arc in arcs:
            start = arc["start"]
            end = arc["end"]
            radius = arc["radius"]
            assert isinstance(start, tuple)
            assert isinstance(end, tuple)
            assert isinstance(radius, float)
            chord = _distance(start, end)
            sweep_degrees = math.degrees(2.0 * math.asin(chord / (2.0 * radius)))
            assert sweep_degrees < 180.0
            sagitta = radius - math.sqrt(radius * radius - chord * chord / 4.0)
            expected = 60.0 if arc is first else 45.0
            assert sagitta == pytest.approx(expected, rel=0.20)

        first_start = first["start"]
        first_end = first["end"]
        assert isinstance(first_start, tuple)
        assert isinstance(first_end, tuple)
        seen_poses.add(
            (
                round((first_start[0] + first_end[0]) / 2.0, 3),
                round((first_start[1] + first_end[1]) / 2.0, 3),
                round(
                    math.degrees(
                        math.atan2(
                            first_end[1] - first_start[1],
                            first_end[0] - first_start[0],
                        )
                    ),
                    3,
                ),
            )
        )
    assert len(seen_poses) > 1


@pytest.mark.parametrize(
    "weight", ["pencil", "crayon", "chalk", "brush_thin", "brush_thick"]
)
def test_stroke_engine_pins_touching_intention_endpoints(weight: str) -> None:
    start = (120.0, 340.0)
    end = (810.0, 620.0)
    stroke = synthesize_stroke(start, end, 2.0, weight, seed=41)
    assert (stroke.samples[0].x, stroke.samples[0].y) == start
    assert (stroke.samples[-1].x, stroke.samples[-1].y) == end


@pytest.mark.parametrize(
    "name",
    [
        "00-single-b-touching.json",
        "01-young-b-touching.json",
        "02-green-b-touching.json",
        "04-fallen-b-touching.json",
    ],
)
def test_formal_leaf_bench_scores_use_only_strict_schema(name: str) -> None:
    path = Path(__file__).parents[2] / "cli" / "bench" / "leaf" / name
    score = Score.model_validate_json(path.read_text())
    assert any(
        instruction.relation is not None
        and instruction.relation.type == "touching"
        and instruction.relation.contact == "both_ends"
        for instruction in score.instructions
    )


def test_stage2_literal_gate_maps_explicit_touching_and_drops_spontaneous() -> None:
    base = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5]},
                {"primitive": "line", "from": [0.3, 0.4], "to": [0.7, 0.4]},
            ]
        }
    )
    explicit = _enforce_relation_literal_gate(base, "前の線に触れる")
    assert explicit.instructions[1].relation is not None
    assert explicit.instructions[1].relation.type == "touching"
    assert explicit.instructions[1].relation.contact == "both_ends"

    spontaneous_data = base.model_dump(by_alias=True)
    spontaneous_data["instructions"][1]["relation"] = {
        "type": "touching",
        "contact": "both_ends",
    }
    spontaneous = _enforce_relation_literal_gate(
        Score.model_validate(spontaneous_data),
        "二本の線を離して置く",
    )
    assert spontaneous.instructions[1].relation is None


def test_general_30_inputs_do_not_enable_touching_spontaneously() -> None:
    general_inputs = [
        "白い円を一つ置く",
        "黒い線を左から右へ引く",
        "青い点を七つ散らす",
        "赤い四角を回転して置く",
        "緑の楕円を上下に並べる",
        "灰色の波線を描く",
        "細い線を画面全体に敷き詰める",
        "白い三角を右上へ置く",
        "黒い弧を一本置く",
        "青い雲形を中央へ置く",
        "赤い点線をゆっくり波打たせる",
        "緑の線を斜めに三本並べる",
        "灰色の円を離して置く",
        "白い線を短く描く",
        "黒い楕円を横長にする",
        "Place one white circle",
        "Draw a black line from left to right",
        "Scatter seven blue dots",
        "Place a rotated red square",
        "Arrange green ellipses vertically",
        "Draw a gray wavy line",
        "Tile thin lines across the canvas",
        "Place a white triangle at upper right",
        "Place one black arc",
        "Place a blue cloudform in the center",
        "Make a red dotted line undulate slowly",
        "Arrange three green diagonal lines",
        "Place gray circles apart",
        "Draw a short white line",
        "Make one black ellipse wide",
    ]
    assert len(general_inputs) == 30
    assert all("touching" not in _literal_relation_types(text) for text in general_inputs)
