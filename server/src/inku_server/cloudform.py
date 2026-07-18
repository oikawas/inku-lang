"""Deterministic cloudform contour synthesis.

Cloudform stores no contour coordinates in a Score.  The closed contour is a
performance result derived from the instruction index, mark index, and render
seed. The base is star-shaped; its second, inward normal displacement is
bounded by local curvature, nonlocal separation, and radial clearance.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

from .schema import Variation
from .stroke_engine import GRAMMARS


Point = tuple[float, float]


@dataclass(frozen=True)
class CloudContour:
    points: tuple[Point, ...]
    path_d: str


def _unit(seed: int, label: str, index: int) -> float:
    raw = hashlib.sha256(f"{seed}:{label}:{index}".encode("utf-8")).digest()[:8]
    return int.from_bytes(raw, "little") / (2**64 - 1)


def cloudform_seed(
    performance_seed: int | None,
    instruction_index: int,
    mark_index: int,
) -> int:
    """Derive the contour seed only from performance identity."""
    raw = (f"cloudform-v1:{performance_seed}:{instruction_index}:{mark_index}").encode(
        "utf-8"
    )
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "little")


def _frequency_range(variation: Variation | None) -> range:
    frequency = variation.frequency if variation is not None else "medium"
    if frequency == "slow":
        return range(2, 6)
    if frequency == "high":
        return range(5, 11)
    return range(3, 8)


def _variation_gain(variation: Variation | None) -> float:
    if variation is None:
        return 0.16
    return {"fine": 0.10, "medium": 0.17, "broad": 0.25}[variation.amplitude]


def _spectrum_power(variation: Variation | None) -> float:
    quality = variation.quality if variation is not None else "pink"
    return {
        "wave": 1.15,
        "pink": 0.50,
        "perlin": 0.72,
        "white": 0.0,
        "none": 0.58,
    }[quality]


def _normalized_harmonic_signal(
    theta: float,
    seed: int,
    *,
    label: str,
    frequencies: range,
    spectrum_power: float,
) -> float:
    total = 0.0
    normalizer = 0.0
    for harmonic in frequencies:
        amplitude = 1.0 / harmonic**spectrum_power
        phase = math.tau * _unit(seed, f"{label}-phase", harmonic)
        sign = -1.0 if _unit(seed, f"{label}-sign", harmonic) < 0.5 else 1.0
        total += sign * amplitude * math.cos(harmonic * theta + phase)
        normalizer += amplitude
    return total / max(normalizer, 1e-9)


def _base_radius(
    theta: float,
    seed: int,
    variation: Variation | None,
    weight: str,
) -> float:
    gain = _variation_gain(variation)
    primary = _normalized_harmonic_signal(
        theta,
        seed,
        label="contour",
        frequencies=_frequency_range(variation),
        spectrum_power=_spectrum_power(variation),
    )
    grammar = GRAMMARS.get(weight, GRAMMARS["pen"])
    touch = _normalized_harmonic_signal(
        theta,
        seed ^ 0x7001,
        label="touch",
        frequencies=range(9, 15),
        spectrum_power=0.65,
    )
    touch_gain = grammar.energy_lateral * 0.018

    return max(0.58, min(1.12, 0.88 + gain * primary + touch_gain * touch))


def _curvature_radius(before: Point, point: Point, after: Point) -> float:
    a = math.dist(before, point)
    b = math.dist(point, after)
    c = math.dist(after, before)
    twice_area = abs(
        (point[0] - before[0]) * (after[1] - before[1])
        - (point[1] - before[1]) * (after[0] - before[0])
    )
    if twice_area < 1e-9:
        return float("inf")
    return a * b * c / (2 * twice_area)


def _closed_catmull_rom_path(points: tuple[Point, ...]) -> str:
    count = len(points)
    if count < 3:
        raise ValueError("cloudform contour requires at least three points")
    commands = [f"M {points[0][0]:.3f} {points[0][1]:.3f}"]
    for index in range(count):
        p0 = points[(index - 1) % count]
        p1 = points[index]
        p2 = points[(index + 1) % count]
        p3 = points[(index + 2) % count]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        commands.append(
            f"C {c1[0]:.3f} {c1[1]:.3f} {c2[0]:.3f} {c2[1]:.3f} {p2[0]:.3f} {p2[1]:.3f}"
        )
    commands.append("Z")
    return " ".join(commands)


def sample_closed_catmull_rom(
    points: tuple[Point, ...], *, samples_per_segment: int = 5
) -> tuple[Point, ...]:
    """Sample the rendered closed cubic path for geometry diagnostics."""
    count = len(points)
    samples_per_segment = max(2, int(samples_per_segment))
    sampled: list[Point] = []
    for index in range(count):
        p0 = points[(index - 1) % count]
        p1 = points[index]
        p2 = points[(index + 1) % count]
        p3 = points[(index + 2) % count]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        for step in range(samples_per_segment):
            t = step / samples_per_segment
            inverse = 1.0 - t
            sampled.append(
                (
                    inverse**3 * p1[0]
                    + 3 * inverse**2 * t * c1[0]
                    + 3 * inverse * t**2 * c2[0]
                    + t**3 * p2[0],
                    inverse**3 * p1[1]
                    + 3 * inverse**2 * t * c1[1]
                    + 3 * inverse * t**2 * c2[1]
                    + t**3 * p2[1],
                )
            )
    return tuple(sampled)


def generate_cloudform_contour(
    center: Point,
    size: Point,
    *,
    performance_seed: int | None,
    instruction_index: int,
    mark_index: int,
    variation: Variation | None = None,
    weight: str = "pen",
    point_count: int = 49,
) -> CloudContour:
    """Generate a bounded, seamless closed contour in renderer coordinates."""
    point_count = max(24, min(72, int(point_count)))
    seed = cloudform_seed(performance_seed, instruction_index, mark_index)
    rx = max(1e-6, size[0] / 2)
    ry = max(1e-6, size[1] / 2)
    angles = tuple(math.tau * index / point_count for index in range(point_count))
    base_radii = tuple(_base_radius(theta, seed, variation, weight) for theta in angles)
    base_points = tuple(
        (
            center[0] + rx * radius * math.cos(theta),
            center[1] + ry * radius * math.sin(theta),
        )
        for theta, radius in zip(angles, base_radii, strict=True)
    )
    lengths = [
        math.dist(base_points[index], base_points[(index + 1) % point_count])
        for index in range(point_count)
    ]
    perimeter = max(sum(lengths), 1e-9)
    arc_positions: list[float] = []
    travelled = 0.0
    for length in lengths:
        arc_positions.append(travelled / perimeter)
        travelled += length

    gain = _variation_gain(variation)
    nominal_scale = min(rx, ry)
    displaced: list[Point] = []
    for index, (base_point, arc_position) in enumerate(
        zip(base_points, arc_positions, strict=True)
    ):
        before = base_points[(index - 1) % point_count]
        after = base_points[(index + 1) % point_count]
        tx, ty = after[0] - before[0], after[1] - before[1]
        tangent_length = max(math.hypot(tx, ty), 1e-9)
        nx, ny = -ty / tangent_length, tx / tangent_length
        toward_center = (center[0] - base_point[0], center[1] - base_point[1])
        if nx * toward_center[0] + ny * toward_center[1] < 0:
            nx, ny = -nx, -ny

        waist_signal = _normalized_harmonic_signal(
            math.tau * arc_position,
            seed ^ 0xC10D5EED,
            label="waist",
            frequencies=range(2, 5),
            spectrum_power=0.72,
        )
        requested = max(0.0, -waist_signal) ** 2 * (0.08 + gain * 0.36) * nominal_scale
        curvature_radius = _curvature_radius(before, base_point, after)
        nonlocal_separation = min(
            math.dist(base_point, other)
            for other_index, other in enumerate(base_points)
            if min(
                (other_index - index) % point_count,
                (index - other_index) % point_count,
            )
            > 3
        )
        radial_clearance = max(
            0.0,
            math.dist(base_point, center) - nominal_scale * 0.48,
        )
        # Staying below the local reach prevents normal offsets from folding or
        # meeting a non-adjacent part of the contour. This is geometry safety,
        # not a preference about which contour looks better.
        maximum = min(
            curvature_radius * 0.20,
            nonlocal_separation * 0.18,
            radial_clearance * 0.50,
            nominal_scale * (0.08 + gain * 0.36),
        )
        distance = min(requested, maximum)
        displaced.append((base_point[0] + nx * distance, base_point[1] + ny * distance))

    points = tuple(displaced)
    return CloudContour(points=points, path_d=_closed_catmull_rom_path(points))


def polygon_self_intersects(points: tuple[Point, ...]) -> bool:
    """Return whether non-adjacent polygon edges intersect (test/diagnostic aid)."""

    def orientation(a: Point, b: Point, c: Point) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    count = len(points)
    for first in range(count):
        a = points[first]
        b = points[(first + 1) % count]
        for second in range(first + 1, count):
            if second in {first, (first + 1) % count}:
                continue
            if first == 0 and second == count - 1:
                continue
            c = points[second]
            d = points[(second + 1) % count]
            o1 = orientation(a, b, c)
            o2 = orientation(a, b, d)
            o3 = orientation(c, d, a)
            o4 = orientation(c, d, b)
            if o1 * o2 < -1e-9 and o3 * o4 < -1e-9:
                return True
    return False
