"""Disposable Stage 0 relation harness for the leaf-sketch benchmark.

This module deliberately keeps the prototype relation vocabulary outside the
canonical Score schema. When the feature flag is enabled, API-bound raw Score
payloads are translated to a private ``color_hint`` marker before Pydantic
validation. The renderer consumes and removes that marker during performance
resolution. With the flag disabled, payloads are returned unchanged and the
strict schema rejects the prototype relation types as it always has.
"""

from __future__ import annotations

from copy import deepcopy
import math
import os
from typing import Any


FEATURE_FLAG = "INKU_SKETCH_RELATIONS"
_MARKER_PREFIX = "__inku_leaf_sketch_relation__:"
_TOUCHING_MARKER = f"{_MARKER_PREFIX}touching:both_ends"
_CONTINUING_MARKER = f"{_MARKER_PREFIX}continuing"


def sketch_relations_enabled() -> bool:
    return os.getenv(FEATURE_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def arc_geometry_from_bow(
    start: tuple[float, float],
    end: tuple[float, float],
    bow: float,
) -> dict[str, Any]:
    """Convert the sketch ``from/to + bow`` notation to a strict minor arc.

    The fixed sign convention uses ``perp(dx, dy) = (-dy, dx)`` in normalized
    screen coordinates. A positive bow therefore bulges toward that normal;
    the circle center is placed on the opposite side of the chord.
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    chord = math.hypot(dx, dy)
    height = abs(bow)
    if chord <= 1e-12:
        raise ValueError("leaf-sketch arc chord must be non-zero")
    if height <= 1e-12:
        raise ValueError("leaf-sketch arc bow must be non-zero")
    if height >= chord / 2.0:
        raise ValueError("leaf-sketch bow must be smaller than half the chord")

    radius = chord * chord / (8.0 * height) + height / 2.0
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    normal = (-dy / chord, dx / chord)
    sign = 1.0 if bow > 0 else -1.0
    center = (
        midpoint[0] - sign * (radius - height) * normal[0],
        midpoint[1] - sign * (radius - height) * normal[1],
    )

    def angle(point: tuple[float, float]) -> float:
        return math.degrees(math.atan2(-(point[1] - center[1]), point[0] - center[0]))

    angle_start = angle(start)
    angle_end = angle(end)
    delta = (angle_end - angle_start + 180.0) % 360.0 - 180.0
    if abs(delta) >= 180.0 - 1e-9:
        raise ValueError(
            "leaf-sketch bow must describe an arc smaller than 180 degrees"
        )
    return {
        "center": [center[0], center[1]],
        "radius": radius,
        "angle_start": angle_start,
        "angle_end": angle_start + delta,
    }


def _point(value: Any) -> tuple[float, float] | None:
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in value
        )
    ):
        return float(value[0]), float(value[1])
    return None


def prepare_sketch_score_payload(score_payload: dict[str, Any]) -> dict[str, Any]:
    """Translate prototype arc notation and relations outside the strict schema."""
    if not sketch_relations_enabled():
        return score_payload

    prepared = deepcopy(score_payload)
    instructions = prepared.get("instructions")
    if not isinstance(instructions, list):
        return prepared

    previous_arc_points: tuple[tuple[float, float], tuple[float, float]] | None = None
    for instruction in instructions:
        if not isinstance(instruction, dict):
            previous_arc_points = None
            continue
        relation = instruction.get("relation")
        relation_type = relation.get("type") if isinstance(relation, dict) else None

        if (
            instruction.get("primitive") == "arc"
            and isinstance(instruction.get("bow"), (int, float))
            and not isinstance(instruction.get("bow"), bool)
        ):
            start = _point(instruction.get("from"))
            end = _point(instruction.get("to"))
            span = instruction.get("span")
            if (
                start is None
                and end is None
                and isinstance(span, (int, float))
                and not isinstance(span, bool)
            ):
                start = (0.5 - float(span) / 2.0, 0.5)
                end = (0.5 + float(span) / 2.0, 0.5)
            if (
                (start is None or end is None)
                and relation_type == "touching"
                and previous_arc_points is not None
            ):
                start, end = previous_arc_points
            if start is not None and end is not None:
                instruction.update(
                    arc_geometry_from_bow(start, end, float(instruction["bow"]))
                )
                instruction.pop("from", None)
                instruction.pop("to", None)
                instruction.pop("span", None)
                instruction.pop("bow", None)
                previous_arc_points = (start, end)
            else:
                previous_arc_points = None
        else:
            previous_arc_points = None

        if not isinstance(relation, dict):
            continue
        marker: str | None = None
        if relation_type == "touching" and relation.get("contact") == "both_ends":
            marker = _TOUCHING_MARKER
        elif relation_type == "continuing" and set(relation) == {"type"}:
            marker = _CONTINUING_MARKER
        if marker is None:
            continue

        instruction.pop("relation", None)
        hint = instruction.get("color_hint")
        instruction["color_hint"] = f"{hint}; {marker}" if hint else marker
    return prepared


def sketch_relation_marker(color_hint: str | None) -> str | None:
    if not sketch_relations_enabled() or not color_hint:
        return None
    for part in (item.strip() for item in color_hint.split(";")):
        if part == _TOUCHING_MARKER:
            return "touching"
        if part == _CONTINUING_MARKER:
            return "continuing"
    return None


def strip_sketch_relation_marker(color_hint: str | None) -> str | None:
    if not color_hint:
        return color_hint
    kept = [
        part.strip()
        for part in color_hint.split(";")
        if part.strip() and not part.strip().startswith(_MARKER_PREFIX)
    ]
    return "; ".join(kept) or None
