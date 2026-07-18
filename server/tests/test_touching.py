from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pydantic import ValidationError

from inku_server.arc_geometry import (
    arc_from_endpoints_and_sagitta,
    minor_arc_delta,
)
from inku_server.coerce import coerce_score
from inku_server.composer import (
    _enforce_relation_literal_gate,
    _literal_relation_types,
)
from inku_server.renderer import _resolve_performance_score, render
from inku_server.schema import Score, migrate_score_payload
from inku_server.stroke_engine import synthesize_stroke


_ARC_D = re.compile(
    r"M ([\d.-]+) ([\d.-]+) A ([\d.-]+) [\d.-]+ 0 ([01]) ([01]) ([\d.-]+) ([\d.-]+)"
)


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


_TRANSFORM = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
Affine = tuple[float, float, float, float, float, float]
_IDENTITY: Affine = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _multiply(left: Affine, right: Affine) -> Affine:
    a1, b1, c1, d1, e1, f1 = left
    a2, b2, c2, d2, e2, f2 = right
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _translation(x: float, y: float) -> Affine:
    return (1.0, 0.0, 0.0, 1.0, x, y)


def _parse_transform(value: str) -> Affine:
    result = _IDENTITY
    for name, arguments in _TRANSFORM.findall(value):
        values = [float(item) for item in re.split(r"[\s,]+", arguments.strip()) if item]
        if name == "matrix" and len(values) == 6:
            current = tuple(values)
        elif name == "translate" and values:
            current = _translation(values[0], values[1] if len(values) > 1 else 0.0)
        elif name == "scale" and values:
            sx = values[0]
            sy = values[1] if len(values) > 1 else sx
            current = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "rotate" and values:
            angle = math.radians(values[0])
            cosine, sine = math.cos(angle), math.sin(angle)
            current = (cosine, sine, -sine, cosine, 0.0, 0.0)
            if len(values) == 3:
                current = _multiply(
                    _translation(values[1], values[2]),
                    _multiply(current, _translation(-values[1], -values[2])),
                )
        else:
            raise AssertionError(f"unsupported SVG transform: {name}({arguments})")
        result = _multiply(result, current)
    return result


def _transform_point(point: tuple[float, float], matrix: Affine) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return (
        a * point[0] + c * point[1] + e,
        b * point[0] + d * point[1] + f,
    )


def _svg_arcs(svg: str) -> list[dict[str, object]]:
    root = ET.fromstring(svg)
    result: list[dict[str, object]] = []

    def visit(element: ET.Element, inherited: Affine) -> None:
        matrix = _multiply(
            inherited,
            _parse_transform(element.attrib.get("transform", "")),
        )
        path_d = element.attrib.get("d", "")
        match = _ARC_D.fullmatch(path_d)
        stroke_opacity = float(element.attrib.get("stroke-opacity", "1"))
        if match is not None and stroke_opacity >= 0.45:
            start = _transform_point((float(match[1]), float(match[2])), matrix)
            end = _transform_point((float(match[6]), float(match[7])), matrix)
            radius_scale = math.hypot(matrix[0], matrix[1])
            result.append(
                {
                    "start": start,
                    "end": end,
                    "radius": float(match[3]) * radius_scale,
                    "large": int(match[4]),
                    "sweep": int(match[5]),
                }
            )
        for child in element:
            visit(child, matrix)

    visit(root, _IDENTITY)
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

    center_side = (
        (center[0] - midpoint[0]) * normal[0]
        + (center[1] - midpoint[1]) * normal[1]
    )
    sagitta = radius - offset
    apex_side = -1.0 if center_side > 0.0 else 1.0
    apex = (
        midpoint[0] + normal[0] * sagitta * apex_side,
        midpoint[1] + normal[1] * sagitta * apex_side,
    )
    return center, tangent(start), tangent(end), apex


def _signed_distance_to_chord(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    normal = (-dy / length, dx / length)
    return (point[0] - midpoint[0]) * normal[0] + (
        point[1] - midpoint[1]
    ) * normal[1]


def _angle(left: tuple[float, float], right: tuple[float, float]) -> float:
    denominator = math.hypot(*left) * math.hypot(*right)
    cosine = max(
        -1.0,
        min(1.0, (left[0] * right[0] + left[1] * right[1]) / denominator),
    )
    return math.degrees(math.acos(cosine))



def test_svg_arc_extractor_self_calibrates_overlap_and_opposition() -> None:
    svg = """<svg xmlns="http://www.w3.org/2000/svg">
      <g transform="rotate(27,50,50)">
        <path d="M 20 50 A 40 40 0 0 0 80 50" />
        <path d="M 20 50 A 40 40 0 0 1 80 50" />
      </g>
    </svg>"""
    first, opposite = _svg_arcs(svg)
    assert _distance(first["start"], opposite["start"]) == pytest.approx(0.0)
    assert _distance(first["end"], opposite["end"]) == pytest.approx(0.0)

    _, first_start_tangent, _, first_apex = _center_and_tangents(first)
    _, opposite_start_tangent, _, opposite_apex = _center_and_tangents(opposite)
    first_side = _signed_distance_to_chord(
        first_apex, first["start"], first["end"]
    )
    opposite_side = _signed_distance_to_chord(
        opposite_apex, opposite["start"], opposite["end"]
    )

    assert first_side * first_side > 0.0
    assert first_side * opposite_side < 0.0
    assert _angle(first_start_tangent, first_start_tangent) < 1e-5
    assert _angle(first_start_tangent, opposite_start_tangent) >= 30.0

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

        first_center, first_start_tangent, first_end_tangent, first_apex = (
            _center_and_tangents(first)
        )
        second_center, second_start_tangent, second_end_tangent, second_apex = (
            _center_and_tangents(second)
        )
        assert _angle(first_start_tangent, second_start_tangent) >= 30.0
        assert _angle(first_end_tangent, second_end_tangent) >= 30.0
        assert first_center != second_center
        first_side = _signed_distance_to_chord(
            first_apex, first["start"], first["end"]
        )
        second_side = _signed_distance_to_chord(
            second_apex, second["start"], second["end"]
        )
        # Stage 0.6-0.7: opposing sides reject overlap; cusp rejects a smooth circle.
        assert first_side * second_side < 0.0

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


def _assert_touching_pairs_from_svg(score: Score, svg: str) -> None:
    arcs = _svg_arcs(svg)
    expected_arc_count = sum(
        instruction.primitive == "arc" for instruction in score.instructions
    )
    assert len(arcs) == expected_arc_count
    arc_by_instruction: dict[int, dict[str, object]] = {}
    arc_index = 0
    for instruction_index, instruction in enumerate(score.instructions):
        if instruction.primitive != "arc":
            continue
        arc_by_instruction[instruction_index] = arcs[arc_index]
        arc_index += 1
    assert arc_index == len(arcs)

    for instruction_index, instruction in enumerate(score.instructions):
        if instruction.relation is None or instruction.relation.type != "touching":
            continue
        previous = arc_by_instruction[instruction_index - 1]
        current = arc_by_instruction[instruction_index]
        assert _distance(previous["start"], current["start"]) <= 2.0
        assert _distance(previous["end"], current["end"]) <= 2.0
        assert previous["large"] == current["large"] == 0

        _, previous_start_tangent, previous_end_tangent, previous_apex = (
            _center_and_tangents(previous)
        )
        _, current_start_tangent, current_end_tangent, current_apex = (
            _center_and_tangents(current)
        )
        assert _angle(previous_start_tangent, current_start_tangent) >= 30.0
        assert _angle(previous_end_tangent, current_end_tangent) >= 30.0
        previous_side = _signed_distance_to_chord(
            previous_apex, previous["start"], previous["end"]
        )
        current_side = _signed_distance_to_chord(
            current_apex, current["start"], current["end"]
        )
        # Opposing apex sides reject overlap; cusp alone only rejects a smooth circle.
        assert previous_side * current_side < 0.0

        assert instruction.radius is not None
        assert instruction.angle_start is not None
        assert instruction.angle_end is not None
        expected_sagitta = instruction.radius * (
            1.0
            - math.cos(
                math.radians(
                    abs(minor_arc_delta(instruction.angle_start, instruction.angle_end))
                )
                / 2.0
            )
        )
        chord = _distance(current["start"], current["end"])
        radius = current["radius"]
        assert isinstance(radius, float)
        actual_sagitta = radius - math.sqrt(radius * radius - chord * chord / 4.0)
        assert actual_sagitta == pytest.approx(expected_sagitta * 1000.0, rel=0.20)


@pytest.mark.parametrize(
    "name",
    [
        "00-single-b-touching.json",
        "01-young-b-touching.json",
        "02-green-b-touching.json",
        "04-fallen-b-touching.json",
    ],
)
def test_leaf_bench_touching_pairs_close_after_all_svg_transforms(name: str) -> None:
    path = Path(__file__).parents[2] / "cli" / "bench" / "leaf" / name
    original = Score.model_validate_json(path.read_text())
    score = coerce_score(original)
    assert len(score.instructions) == len(original.instructions)
    # 00 has no rotation and cannot expose the ancestor-transform regression by itself.
    for seed in range(1, 6):
        _assert_touching_pairs_from_svg(score, render(score, render_seed=seed))


def test_along_reads_a_rotated_line_in_canvas_coordinates() -> None:
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "rotation": 90,
                },
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.02,
                    "relation": {"type": "along", "gap": "narrow"},
                },
            ]
        }
    )
    resolved = _resolve_performance_score(score, 1)
    center = resolved.instructions[1].center
    assert center is not None
    assert 0.019 <= abs(center[0] - 0.5) <= 0.051
    assert 0.2 <= center[1] <= 0.8

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


def test_judge_scores_change_only_color_and_weight() -> None:
    score_dir = Path(__file__).parents[2] / "cli" / "bench" / "leaf"
    for name in (
        "00-single-b-touching",
        "01-young-b-touching",
        "02-green-b-touching",
        "04-fallen-b-touching",
    ):
        regular = json.loads((score_dir / f"{name}.json").read_text())
        judge = json.loads((score_dir / f"{name}-judge.json").read_text())
        assert len(regular["instructions"]) == len(judge["instructions"])
        for regular_instruction, judge_instruction in zip(
            regular["instructions"], judge["instructions"], strict=True
        ):
            expected = dict(regular_instruction)
            expected["color"] = "black"
            expected["weight"] = "rotring"
            assert judge_instruction == expected
        Score.model_validate(judge)


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
