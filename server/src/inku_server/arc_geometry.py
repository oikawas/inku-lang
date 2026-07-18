"""Shared minor-arc geometry used by relation resolution and SVG rendering."""

from __future__ import annotations

import math
from typing import NamedTuple


Point = tuple[float, float]


class ArcGeometry(NamedTuple):
    center: Point
    radius: float
    angle_start: float
    angle_end: float


def minor_arc_delta(angle_start: float, angle_end: float) -> float:
    """Return the signed sweep in [-180, 180), using mathematical angles."""
    return (angle_end - angle_start + 180.0) % 360.0 - 180.0


def arc_point(center: Point, radius: float, angle_degrees: float) -> Point:
    angle = math.radians(angle_degrees)
    return (
        center[0] + radius * math.cos(angle),
        center[1] - radius * math.sin(angle),
    )


def arc_svg_flags(angle_start: float, angle_end: float) -> tuple[int, int]:
    """Return SVG large-arc and sweep flags for the numeric signed sweep."""
    delta = angle_end - angle_start
    return (1 if abs(delta) > 180.0 else 0, 0 if delta > 0.0 else 1)


def arc_from_endpoints_and_sagitta(
    start: Point,
    end: Point,
    sagitta: float,
) -> ArcGeometry:
    """Construct the P1→P2 minor arc whose signed screen-space sagitta is b.

    The sign convention fixes ``perp(dx, dy) = (-dy, dx)``. Positive sagitta
    bulges toward that normal, while the center lies on the opposite side.
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    chord = math.hypot(dx, dy)
    height = abs(sagitta)
    if chord <= 1e-12:
        raise ValueError("arc chord must be non-zero")
    if height <= 1e-12 or height >= chord / 2.0:
        raise ValueError("arc sagitta must be positive and smaller than half the chord")

    radius = chord * chord / (8.0 * height) + height / 2.0
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    normal = (-dy / chord, dx / chord)
    sign = 1.0 if sagitta > 0.0 else -1.0
    center = (
        midpoint[0] - sign * (radius - height) * normal[0],
        midpoint[1] - sign * (radius - height) * normal[1],
    )

    def angle(point: Point) -> float:
        return math.degrees(
            math.atan2(-(point[1] - center[1]), point[0] - center[0])
        )

    angle_start = angle(start)
    delta = minor_arc_delta(angle_start, angle(end))
    if abs(delta) >= 180.0 - 1e-9:
        raise ValueError("arc must use a sweep smaller than 180 degrees")
    return ArcGeometry(center, radius, angle_start, angle_start + delta)


def signed_arc_sagitta(
    center: Point,
    radius: float,
    angle_start: float,
    angle_end: float,
) -> float:
    """Measure signed sagitta relative to the arc's directed chord."""
    delta = minor_arc_delta(angle_start, angle_end)
    start = arc_point(center, radius, angle_start)
    end = arc_point(center, radius, angle_start + delta)
    apex = arc_point(center, radius, angle_start + delta / 2.0)
    dx, dy = end[0] - start[0], end[1] - start[1]
    chord = math.hypot(dx, dy)
    if chord <= 1e-12:
        raise ValueError("arc chord must be non-zero")
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    normal = (-dy / chord, dx / chord)
    return (apex[0] - midpoint[0]) * normal[0] + (
        apex[1] - midpoint[1]
    ) * normal[1]
