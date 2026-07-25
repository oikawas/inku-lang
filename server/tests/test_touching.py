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
from inku_server.renderer import (
    _needs_contour_variation,
    _resolve_performance_score,
    render,
)
from inku_server.schema import Score, migrate_score_payload
from inku_server.stroke_engine import synthesize_stroke


_ARC_D = re.compile(
    r"M ([\d.-]+) ([\d.-]+) A ([\d.-]+) [\d.-]+ 0 ([01]) ([01]) ([\d.-]+) ([\d.-]+)"
)
_POINT_PAIR = re.compile(r"(-?[\d.]+(?:[eE][+-]?\d+)?)[,\s]+(-?[\d.]+(?:[eE][+-]?\d+)?)")
# A polyline is read as a performed arc only if it turns far enough to be one.
# Measured on the leaf benchmark, performed arcs sweep 122deg-169deg, while a
# performed line reads as 17deg. A shallower arc would be dropped, but the arc
# count assertion turns that into a failure rather than a silent pass.
_MIN_POLYLINE_ARC_SWEEP_DEGREES = 45.0
_LOCAL_LEAF_BENCH_DIR = Path(__file__).parents[2] / "cli" / "bench" / "leaf"
_requires_local_leaf_bench = pytest.mark.skipif(
    not _LOCAL_LEAF_BENCH_DIR.is_dir(),
    reason="local-only CLI leaf benchmark is not available",
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
                    relation={"type": "touching"},
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


def _fit_arc_through_endpoints(
    points: list[tuple[float, float]],
) -> tuple[tuple[float, float], float] | None:
    """Least-squares circle through the polyline's two endpoints.

    An arc performed with variation is a sampled polyline whose interior
    vertices sit off the nominal circle, so its radius has to be recovered by
    fitting. Fitting all five circle degrees of freedom is ill-conditioned on a
    single noisy arc, but the performance pins both endpoints exactly, which
    puts the centre on the chord's perpendicular bisector and leaves one free
    parameter: the signed offset `t` along that bisector. Requiring
    |p - centre|^2 == t^2 + (chord/2)^2 is then linear in `t`, so the fit is a
    closed form and the variation noise averages out across the vertices.
    """
    if len(points) < 3:
        return None
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    chord = math.hypot(dx, dy)
    if chord < 1e-9:
        return None
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    normal = (-dy / chord, dx / chord)
    half_chord_squared = chord * chord / 4.0
    numerator = denominator = 0.0
    for x, y in points:
        offset_x, offset_y = x - midpoint[0], y - midpoint[1]
        along = offset_x * normal[0] + offset_y * normal[1]
        numerator += along * (
            offset_x * offset_x + offset_y * offset_y - half_chord_squared
        )
        denominator += 2.0 * along * along
    if denominator < 1e-9:
        return None
    t = numerator / denominator
    center = (midpoint[0] + normal[0] * t, midpoint[1] + normal[1] * t)
    return center, math.sqrt(t * t + half_chord_squared)


def _swept_degrees(
    points: list[tuple[float, float]], center: tuple[float, float]
) -> float:
    """Signed angle traversed around `center`, accumulated vertex by vertex.

    Positive means the SVG positive-angle direction, i.e. the sweep flag of the
    equivalent arc command. The magnitude replaces the large-arc flag, which a
    polyline does not carry.
    """
    total = 0.0
    previous = math.atan2(points[0][1] - center[1], points[0][0] - center[0])
    for x, y in points[1:]:
        current = math.atan2(y - center[1], x - center[0])
        total += (current - previous + math.pi) % (2 * math.pi) - math.pi
        previous = current
    return math.degrees(total)


def _polyline_arc(
    points: list[tuple[float, float]],
) -> dict[str, object] | None:
    fit = _fit_arc_through_endpoints(points)
    if fit is None:
        return None
    center, radius = fit
    swept = _swept_degrees(points, center)
    if abs(swept) < _MIN_POLYLINE_ARC_SWEEP_DEGREES:
        return None
    return {
        "start": points[0],
        "end": points[-1],
        "radius": radius,
        "large": 0 if abs(swept) < 180.0 else 1,
        "sweep": 1 if swept > 0.0 else 0,
        "swept": swept,
        "kind": "polyline",
    }


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
        radius_scale = math.hypot(matrix[0], matrix[1])
        # 材質装飾は主線ではないので数えない。class が正で、opacity は保険
        # (v2.1 で材質強度が上がり、装飾の opacity だけでは主線と分離できない)。
        is_material = "material-outline" in element.attrib.get("class", "")
        if match is not None and not is_material and stroke_opacity >= 0.45:
            start = _transform_point((float(match[1]), float(match[2])), matrix)
            end = _transform_point((float(match[6]), float(match[7])), matrix)
            sweep_degrees = _arc_command_sweep_degrees(
                start, end, float(match[3]) * radius_scale, int(match[4]), int(match[5])
            )
            result.append(
                {
                    "start": start,
                    "end": end,
                    "radius": float(match[3]) * radius_scale,
                    "large": int(match[4]),
                    "sweep": int(match[5]),
                    "swept": sweep_degrees,
                    "kind": "path",
                }
            )
        points_attribute = element.attrib.get("points", "")
        if (
            element.tag.endswith("polyline")
            and points_attribute
            and not is_material
            and stroke_opacity >= 0.45
        ):
            points = [
                _transform_point((float(x), float(y)), matrix)
                for x, y in _POINT_PAIR.findall(points_attribute)
            ]
            arc = _polyline_arc(points)
            if arc is not None:
                result.append(arc)
        for child in element:
            visit(child, matrix)

    visit(root, _IDENTITY)
    return result


def _arc_command_sweep_degrees(
    start: tuple[float, float],
    end: tuple[float, float],
    radius: float,
    large: int,
    sweep: int,
) -> float:
    """Signed swept angle of an arc command, in the same convention as
    `_swept_degrees`, so both arc shapes are comparable."""
    chord = _distance(start, end)
    half = math.degrees(math.asin(min(1.0, chord / (2.0 * radius))))
    magnitude = 2.0 * (180.0 - half if large == 1 else half)
    return magnitude if sweep == 1 else -magnitude


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

def test_svg_arc_extractor_reads_a_performed_polyline_like_its_arc_command() -> None:
    center, radius = (50.0, 50.0), 40.0
    start_degrees, end_degrees = 200.0, 340.0
    samples = 81

    def on_circle(degrees: float, offset: float) -> tuple[float, float]:
        angle = math.radians(degrees)
        return (
            center[0] + (radius + offset) * math.cos(angle),
            center[1] + (radius + offset) * math.sin(angle),
        )

    points = []
    for index in range(samples):
        degrees = start_degrees + (end_degrees - start_degrees) * index / (samples - 1)
        # Interior vertices wander off the circle exactly as variation moves them.
        wander = 0.0 if index in (0, samples - 1) else 7.0 * math.sin(index * 1.7)
        points.append(on_circle(degrees, wander))
    rendered = " ".join(f"{x},{y}" for x, y in points)
    start, end = on_circle(start_degrees, 0.0), on_circle(end_degrees, 0.0)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg">
      <g transform="rotate(27,50,50)">
        <path d="M {start[0]} {start[1]} A {radius} {radius} 0 0 1 {end[0]} {end[1]}" />
        <polyline points="{rendered}" fill="none" />
      </g>
    </svg>"""
    command, performed = _svg_arcs(svg)

    assert command["kind"] == "path"
    assert performed["kind"] == "polyline"
    assert _distance(command["start"], performed["start"]) == pytest.approx(0.0)
    assert _distance(command["end"], performed["end"]) == pytest.approx(0.0)
    assert performed["radius"] == pytest.approx(command["radius"], rel=0.10)
    assert performed["sweep"] == command["sweep"] == 1
    assert performed["large"] == command["large"] == 0
    assert command["swept"] == pytest.approx(end_degrees - start_degrees, abs=1e-6)
    # Accumulating the turn vertex by vertex charges the wander to the sweep.
    assert performed["swept"] == pytest.approx(command["swept"], abs=12.0)


def test_svg_arc_extractor_flags_a_major_polyline_arc() -> None:
    """A polyline carries no large-arc flag, so the minor-arc contract is
    re-derived from the angle the vertices actually sweep."""
    points = [
        (
            50.0 + 40.0 * math.cos(math.radians(20.0 + 320.0 * index / 80.0)),
            50.0 + 40.0 * math.sin(math.radians(20.0 + 320.0 * index / 80.0)),
        )
        for index in range(81)
    ]
    rendered = " ".join(f"{x},{y}" for x, y in points)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{rendered}" fill="none" /></svg>'
    )
    (major,) = _svg_arcs(svg)
    assert major["swept"] == pytest.approx(320.0)
    assert major["large"] == 1


def test_svg_arc_extractor_ignores_a_performed_line() -> None:
    points = [(100.0 + index * 5.0, 200.0 + math.sin(index) * 6.0) for index in range(81)]
    rendered = " ".join(f"{x},{y}" for x, y in points)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{rendered}" fill="none" /></svg>'
    )
    assert _svg_arcs(svg) == []


def test_touching_schema_is_strict_versioned_and_migration_is_idempotent() -> None:
    legacy = {"instructions": []}
    assert migrate_score_payload(migrate_score_payload(legacy)) == {
        "version": "0.1.0",
        "instructions": [],
    }
    relation = {"type": "touching"}
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
    assert score.instructions[1].relation.type == "touching"
    # 厳格さの検査。contact が退役した (v2.7.2) ので「touching なら contact 必須」は
    # もう無いが、未知フィールドの拒否は残っている。
    with pytest.raises(ValidationError):
        Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "line",
                        "from": [0.2, 0.5],
                        "to": [0.8, 0.5],
                        "relation": {"type": "touching", "hold": "tight"},
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
                    "relation": {"type": "touching"},
                },
                {
                    "primitive": "circle",
                    "center": [0.4, 0.4],
                    "radius": 0.04,
                    "relation": {"type": "touching"},
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
        # No variation on this score: both arcs stay single arc commands.
        assert first["kind"] == second["kind"] == "path"
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
        arc = arcs[arc_index]
        # A performed arc is a sampled polyline; an unperformed one stays a
        # single arc command.
        expected_kind = (
            "polyline" if _needs_contour_variation(instruction.variation) else "path"
        )
        assert arc["kind"] == expected_kind
        arc_by_instruction[instruction_index] = arc
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
        assert abs(previous["swept"]) < 180.0
        assert abs(current["swept"]) < 180.0

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
@_requires_local_leaf_bench
def test_leaf_bench_touching_pairs_close_after_all_svg_transforms(name: str) -> None:
    path = _LOCAL_LEAF_BENCH_DIR / name
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
@_requires_local_leaf_bench
def test_formal_leaf_bench_scores_use_only_strict_schema(name: str) -> None:
    path = _LOCAL_LEAF_BENCH_DIR / name
    score = Score.model_validate_json(path.read_text())
    assert any(
        instruction.relation is not None
        and instruction.relation.type == "touching"
        for instruction in score.instructions
    )


@_requires_local_leaf_bench
def test_judge_scores_change_only_color_and_weight() -> None:
    score_dir = _LOCAL_LEAF_BENCH_DIR
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

    spontaneous_data = base.model_dump(by_alias=True)
    spontaneous_data["instructions"][1]["relation"] = {"type": "touching"}
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


def test_retired_fields_are_dropped_from_saved_scores() -> None:
    """v2.7.2 で退役した 2 フィールドは、保存済み Score の再生を妨げない。

    pentala の保存済み 1780 件のうち contact が 41 件で使われている (thickness は
    0 件)。`extra="forbid"` があるので、落とす経路が無いと再生時に ValidationError
    で弾かれる。absorbency は退役していない — 値は読まれないが、地の texture seed が
    Score 全体のハッシュなので、消すと地を持つ 23 件の粒配置が変わる。
    """
    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5]},
                {
                    "primitive": "line",
                    "from": [0.3, 0.4],
                    "to": [0.7, 0.4],
                    "relation": {"type": "touching", "contact": "both_ends"},
                    "variation": {
                        "quality": "wave",
                        "dimensions": ["position_y", "thickness"],
                    },
                },
            ],
        }
    )
    assert not hasattr(score.instructions[1].relation, "contact")
    assert score.instructions[1].relation.type == "touching"
    assert score.instructions[1].variation.dimensions == ["position_y"]

    # 落とすのは退役した 2 つだけで、未知フィールドは今も拒否する。
    with pytest.raises(ValidationError):
        Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "line",
                        "from": [0.2, 0.5],
                        "to": [0.8, 0.5],
                        "relation": {"type": "along", "grip": "firm"},
                    }
                ]
            }
        )
