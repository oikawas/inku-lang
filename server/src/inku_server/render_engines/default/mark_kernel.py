"""Pure deterministic mark geometry for the default render engine.

This module computes scalars and point collections only. SVG construction and
serialization remain in :mod:`marks`, which consumes this kernel.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from ...plugins import CanvasSize
from ...schema import Variation
from ...stroke_engine import centerline_normals
from .determinism import (
    _hash_to_unit,
    _periodic_value_noise_1d,
    _value_noise_1d,
    _wave_phase,
)

# Integer cycle counts also keep closed wave contours continuous at the seam.
FREQUENCY_CYCLES: dict[str, float] = {"slow": 2.0, "medium": 6.0, "high": 14.0}

# Segment counts scale with path length to keep segment length nearly constant.
SEGMENT_TARGET_RATIO = 0.01
SEGMENT_COUNT_MIN = 32
SEGMENT_COUNT_MAX = 200

# A path one canvas unit long keeps the existing 49 hand-stroke samples.
STROKE_SAMPLE_TARGET_RATIO = 1.0 / 49.0
STROKE_SAMPLE_MIN = 17
STROKE_SAMPLE_MAX = 129


def _ellipse_perimeter(rx: float, ry: float) -> float:
    """Return an ellipse perimeter using Ramanujan's second approximation."""
    a, b = abs(rx), abs(ry)
    if a + b <= 0:
        return 0.0
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def _segment_count(path_len_px: float, canvas: CanvasSize) -> int:
    """Scale the segment count with path length to keep segment length stable."""
    target = canvas.unit * SEGMENT_TARGET_RATIO
    if target <= 0:
        return SEGMENT_COUNT_MIN
    return max(
        SEGMENT_COUNT_MIN, min(SEGMENT_COUNT_MAX, int(round(path_len_px / target)))
    )


def _stroke_sample_count(length_px: float, canvas: CanvasSize) -> int:
    """Return the hand-stroke sample count; one canvas unit keeps 49 samples."""
    target = canvas.unit * STROKE_SAMPLE_TARGET_RATIO
    if target <= 0:
        return STROKE_SAMPLE_MIN
    return max(
        STROKE_SAMPLE_MIN, min(STROKE_SAMPLE_MAX, int(round(length_px / target)))
    )


def _sample_offset(
    t: float, variation: Variation, seed: int, segment: int, amp: float
) -> float:
    freq = FREQUENCY_CYCLES[variation.frequency]
    q = variation.quality

    if q == "wave":
        return math.sin(t * 2 * math.pi * freq + _wave_phase(seed)) * amp
    if q == "perlin":
        return _value_noise_1d(t * freq, seed) * amp
    if q == "pink":
        # The existing lightweight pink noise combines two Perlin octaves.
        return (
            _value_noise_1d(t * freq, seed) * amp
            + _value_noise_1d(t * freq * 2, seed ^ 0x9E37) * amp * 0.5
        ) / 1.5
    if q == "white":
        return _hash_to_unit(segment, seed) * amp
    return 0.0


def _line_with_variation(
    start_px: tuple[float, float],
    end_px: tuple[float, float],
    variation: Variation,
    seed: int,
    amp: float,
    canvas: CanvasSize,
) -> list[tuple[float, float]]:
    """Return vertices after applying variation to a straight polyline.

    Dimension selection is symmetric with contour variation: x alone moves on
    the x axis, y alone moves on the y axis, and both move perpendicular to the
    line.
    """
    dx = end_px[0] - start_px[0]
    dy = end_px[1] - start_px[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return [start_px, end_px]

    # Unit vector perpendicular to the line direction.
    perp_x = -dy / length
    perp_y = dx / length

    dims = set(variation.dimensions)
    axis_x = "position_x" in dims
    axis_y = "position_y" in dims

    segments = _segment_count(length, canvas)
    pts: list[tuple[float, float]] = [start_px]
    for i in range(1, segments):
        t = i / segments
        x = start_px[0] + t * dx
        y = start_px[1] + t * dy
        off = _sample_offset(t, variation, seed, i, amp)

        if axis_x and not axis_y:
            x += off
        elif axis_y and not axis_x:
            y += off
        else:
            x += off * perp_x
            y += off * perp_y

        pts.append((x, y))
    pts.append(end_px)
    return pts


def _sample_offset_periodic(
    t: float, variation: Variation, seed: int, segment: int, amp: float
) -> float:
    """Sample a periodic offset for one lap of a closed contour.

    Wave closes because ``FREQUENCY_CYCLES`` contains integers; a seed-derived
    phase does not change the period. Perlin noise uses a periodic lattice.
    White noise is independent per vertex and has no seam continuity.
    """
    freq = FREQUENCY_CYCLES[variation.frequency]
    q = variation.quality
    if q == "wave":
        return math.sin(t * 2 * math.pi * freq + _wave_phase(seed)) * amp
    if q == "perlin":
        return _periodic_value_noise_1d(t * freq, seed, max(1, int(round(freq)))) * amp
    if q == "white":
        return _hash_to_unit(segment, seed) * amp
    return 0.0


def _offset_contour_point(
    x: float,
    y: float,
    off: float,
    center: tuple[float, float],
    axis_x: bool,
    axis_y: bool,
) -> tuple[float, float]:
    """Offset one contour point according to the selected dimensions.

    X alone moves on the x axis, y alone moves on the y axis, and both or
    radius move along the outward contour normal. This mirrors line variation.
    """
    if axis_x and not axis_y:
        return (x + off, y)
    if axis_y and not axis_x:
        return (x, y + off)
    dx = x - center[0]
    dy = y - center[1]
    norm = math.hypot(dx, dy)
    if norm <= 1e-6:
        return (x, y)
    return (x + off * dx / norm, y + off * dy / norm)


def _closed_contour_with_variation(
    points: list[tuple[float, float]],
    center: tuple[float, float],
    variation: Variation,
    seed: int,
    amp: float,
) -> list[tuple[float, float]]:
    """Apply periodic variation to a closed circle or ellipse contour."""
    dims = set(variation.dimensions)
    axis_x = "position_x" in dims
    axis_y = "position_y" in dims
    n = len(points)
    result: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(points):
        off = _sample_offset_periodic(i / n, variation, seed, i, amp)
        result.append(_offset_contour_point(x, y, off, center, axis_x, axis_y))
    return result


def _edge_contour_with_anchors(
    corners: list[tuple[float, float]],
    variation: Variation | None,
    seed: int,
    amp: float,
    canvas: CanvasSize,
) -> tuple[list[tuple[float, float]], frozenset[int]]:
    """Return a per-edge closed contour and the vertex indices at its corners.

    With variation, each edge uses the line algorithm and ``_segment_count``.
    Every edge shares the amplitude derived from the figure's representative
    size so an elongated rectangle does not become anisotropic. Without
    variation, the contour is a hand-stroke centerline and uses
    ``_stroke_sample_count`` to keep the tool-lag scale aligned with a line.
    """
    result: list[tuple[float, float]] = []
    anchors: list[int] = []
    n = len(corners)
    for i in range(n):
        start = corners[i]
        end = corners[(i + 1) % n]
        anchors.append(len(result))
        if variation is None:
            segments = _stroke_sample_count(
                math.hypot(end[0] - start[0], end[1] - start[1]), canvas
            )
            edge = [
                (
                    start[0] + (end[0] - start[0]) * k / segments,
                    start[1] + (end[1] - start[1]) * k / segments,
                )
                for k in range(segments + 1)
            ]
        else:
            edge = _line_with_variation(
                start, end, variation, seed + (i + 1) * 7919, amp, canvas
            )
        result.extend(edge[:-1])
    return result, frozenset(anchors)


def _edge_contour_with_variation(
    corners: list[tuple[float, float]],
    variation: Variation,
    seed: int,
    amp: float,
    canvas: CanvasSize,
) -> list[tuple[float, float]]:
    """Apply line variation to polygon edges while keeping corners anchored."""
    return _edge_contour_with_anchors(corners, variation, seed, amp, canvas)[0]


def _arc_points_with_variation(
    cx: float,
    cy: float,
    r: float,
    start_deg: float,
    end_deg: float,
    variation: Variation,
    seed: int,
    amp: float,
    canvas: CanvasSize,
) -> list[tuple[float, float]]:
    """Segment and vary an arc while keeping both touching endpoints fixed."""
    arc_len = r * abs(math.radians(end_deg) - math.radians(start_deg))
    base = _arc_points(
        cx, cy, r, start_deg, end_deg, _segment_count(arc_len, canvas) + 1
    )
    dims = set(variation.dimensions)
    axis_x = "position_x" in dims
    axis_y = "position_y" in dims
    last = len(base) - 1
    result: list[tuple[float, float]] = [base[0]]
    for i in range(1, last):
        x, y = base[i]
        off = _sample_offset(i / last, variation, seed, i, amp)
        result.append(_offset_contour_point(x, y, off, (cx, cy), axis_x, axis_y))
    result.append(base[last])
    return result


def _line_direction(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 1.0, 0.0
    return dx / length, dy / length


def _offset_polyline(
    points: list[tuple[float, float]],
    amount: float,
    *,
    wander: float = 0.0,
    wander_period: float = 1.0,
    seed: int = 0,
) -> list[tuple[float, float]]:
    """Offset an open polyline by `amount` along per-vertex normals.

    The material outline layers used to be straight start->end lines. Once the
    stroke centreline gained a gesture they had to follow that same curve, or the
    straight remnants read as a faint line joining the endpoints.

    `wander` adds a low-frequency drift to the offset along the arc length so the
    strata are not perfectly parallel rails — one of the cues the eye reads as a
    repeating pattern.
    """
    n = len(points)
    if n < 2:
        return list(points)
    out: list[tuple[float, float]] = []
    arc = 0.0
    for i in range(n):
        if i == 0:
            tx, ty = points[1][0] - points[0][0], points[1][1] - points[0][1]
        elif i == n - 1:
            tx, ty = points[-1][0] - points[-2][0], points[-1][1] - points[-2][1]
        else:
            tx, ty = (
                points[i + 1][0] - points[i - 1][0],
                points[i + 1][1] - points[i - 1][1],
            )
        length = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / length, tx / length
        off = amount
        if wander:
            off += wander * (
                _value_noise_1d(arc / max(1e-6, wander_period), seed) * 2 - 1
            )
        out.append((points[i][0] + nx * off, points[i][1] + ny * off))
        if i < n - 1:
            arc += math.hypot(
                points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]
            )
    return out


def _dash_spec_stats(dash: str | None) -> tuple[float, float]:
    """The coverage and grain a tool's dash pattern implies.

    The patterns in `_MATERIAL_OUTLINE_SPECS` carry a tool's character -- the pen
    is nearly continuous, the pencil is mostly gap -- and that tuning is worth
    keeping once the cadence is gone. Coverage is the share of the path the
    pattern marked; grain is its natural wavelength, in unscaled units.
    """
    if not dash:
        return 1.0, 0.0
    values = [abs(float(v)) for v in dash.split(",") if v.strip()]
    if not values or sum(values) <= 0:
        return 1.0, 0.0
    # An odd-length pattern swaps marks and gaps on every repeat, so read it twice.
    if len(values) % 2:
        values = values + values
    marks, gaps = values[0::2], values[1::2]
    coverage = sum(marks) / sum(values)
    grain = sum(marks) / len(marks) + sum(gaps) / len(gaps)
    return coverage, grain


def _contact_field(t: float, seed: int) -> float:
    """The paper's tooth at two scales, read along the path. Roughly 0..1."""
    return 0.62 * _value_noise_1d(t, seed) + 0.38 * _value_noise_1d(
        t * 2.7 + 13.1, seed + 977
    )


CONTACT_LENGTH_QUANTUM = 6


def _quantise_contact_length(value: float) -> float:
    return round(value, CONTACT_LENGTH_QUANTUM)


def _resample_by_length(
    points: list[tuple[float, float]], step: float, closed: bool
) -> list[tuple[float, float]]:
    """Walk a polyline and emit a point every `step` px of arc length.

    `_resample_points` picks by index, which is even only when the source
    vertices are. The contact field is read against distance on the paper, so it
    needs a walk that is even in length.
    """
    step = _quantise_contact_length(step)
    if step <= 0 or len(points) < 2:
        return list(points)
    path = points + [points[0]] if closed else points
    out = [path[0]]
    carry = 0.0
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        seg = _quantise_contact_length(math.hypot(bx - ax, by - ay))
        if seg <= 1e-9:
            continue
        travelled = step - carry
        while travelled <= seg:
            f = travelled / seg
            out.append((ax + (bx - ax) * f, ay + (by - ay) * f))
            travelled += step
        carry = (carry + seg) % step
    return out


def _contact_fragments(
    points: list[tuple[float, float]],
    *,
    coverage: float,
    grain_px: float,
    seed: int,
    closed: bool,
) -> list[tuple[list[tuple[float, float]], float]]:
    """The pieces of an outline where the tool actually met the paper.

    A dasharray repeats. However long the pattern, a long contour walks through
    it several times and the eye finds the cadence -- and the material layer is
    not a dotted line, it is where a tool dragged across a grain and kept losing
    the paper. So presence is a smooth noise field read along the arc length, and
    the outline exists where the field clears a threshold.

    The threshold is the (1 - coverage) quantile of the field's own samples, not
    a constant: that way each tool keeps the share of the path its dash pattern
    used to mark, while nothing about the spacing repeats. Fragments come back
    with a weight, so the thinly-touching ones are fainter than the ones the tool
    bore down on.
    """
    if len(points) < 2:
        return []
    if grain_px <= 0 or coverage >= 0.999:
        return [(list(points), 1.0)]

    # Three samples per grain resolves a skip; the cap keeps a long contour from
    # turning into thousands of SVG vertices.
    total = _quantise_contact_length(
        sum(
            _quantise_contact_length(math.hypot(b[0] - a[0], b[1] - a[1]))
            for a, b in zip(points, points[1:] + points[:1] if closed else points[1:])
        )
    )
    if total <= 1e-6:
        return []
    grain_px = _quantise_contact_length(grain_px)
    step = _quantise_contact_length(max(grain_px / 3.0, total / 600.0, 0.8))
    walk = _resample_by_length(points, step, closed)
    if len(walk) < 3:
        return [(list(points), 1.0)]

    field = [_contact_field(i * step / grain_px, seed) for i in range(len(walk))]
    ordered = sorted(field)
    index = min(len(ordered) - 1, max(0, int((1.0 - coverage) * len(ordered))))
    threshold = ordered[index]
    span = max(1e-6, ordered[-1] - threshold)

    runs: list[list[int]] = []
    current: list[int] = []
    for i, value in enumerate(field):
        if value >= threshold:
            current.append(i)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    # On a closed path the seam is not an end: a run that touches both ends is
    # one fragment that happens to be written in two halves.
    if closed and len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == len(field) - 1:
        runs[0] = runs[-1] + runs[0]
        runs.pop()

    def _crossing(outside: int, inside: int) -> tuple[float, float]:
        """Where the field crosses the threshold between two samples.

        Without this the ends of every fragment land on a sample, so every
        length is a multiple of `step` and the lengths themselves become the
        cadence -- the regularity comes back through the sampling instead of
        through the pattern.
        """
        f_out, f_in = field[outside], field[inside]
        if abs(f_in - f_out) < 1e-9:
            return walk[inside]
        f = min(1.0, max(0.0, (threshold - f_out) / (f_in - f_out)))
        ax, ay = walk[outside]
        bx, by = walk[inside]
        return (ax + (bx - ax) * f, ay + (by - ay) * f)

    fragments: list[tuple[list[tuple[float, float]], float]] = []
    for run in runs:
        piece = [walk[i] for i in run]
        if run[0] - 1 >= 0:
            piece.insert(0, _crossing(run[0] - 1, run[0]))
        if run[-1] + 1 < len(field):
            piece.append(_crossing(run[-1] + 1, run[-1]))
        if len(piece) < 2:
            continue
        length = _quantise_contact_length(
            sum(
                _quantise_contact_length(math.hypot(b[0] - a[0], b[1] - a[1]))
                for a, b in zip(piece, piece[1:])
            )
        )
        if length < 0.6:
            continue
        margin = sum(field[i] - threshold for i in run) / len(run)
        weight = min(1.0, 0.55 + 0.75 * (margin / span))
        fragments.append((piece, weight))
    return fragments


def _polyline_sample(
    points: list[tuple[float, float]], t: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Position and unit tangent at arc-length fraction `t` (0..1) of a polyline."""
    if len(points) < 2:
        p = points[0] if points else (0.0, 0.0)
        return p, (1.0, 0.0)
    segs = [
        math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
        for i in range(len(points) - 1)
    ]
    total = sum(segs)
    if total < 1e-9:
        return points[0], (1.0, 0.0)
    target = t * total
    acc = 0.0
    for i, d in enumerate(segs):
        if acc + d >= target or i == len(segs) - 1:
            f = (target - acc) / d if d > 1e-9 else 0.0
            x = points[i][0] + (points[i + 1][0] - points[i][0]) * f
            y = points[i][1] + (points[i + 1][1] - points[i][1]) * f
            length = d or 1.0
            ux = (points[i + 1][0] - points[i][0]) / length
            uy = (points[i + 1][1] - points[i][1]) / length
            return (x, y), (ux, uy)
        acc += d
    return points[-1], (1.0, 0.0)


def _circle_points(
    cx: float, cy: float, rx: float, ry: float, count: int
) -> list[tuple[float, float]]:
    return [
        (
            cx + math.cos(i * 2 * math.pi / count) * rx,
            cy + math.sin(i * 2 * math.pi / count) * ry,
        )
        for i in range(count)
    ]


def _rect_points(
    x: float, y: float, w: float, h: float, count: int
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    perimeter = max(1.0, 2 * (w + h))
    for i in range(count):
        d = ((i + 0.5) / count) * perimeter
        if d <= w:
            points.append((x + d, y))
        elif d <= w + h:
            points.append((x + w, y + d - w))
        elif d <= 2 * w + h:
            points.append((x + w - (d - w - h), y + h))
        else:
            points.append((x, y + h - (d - 2 * w - h)))
    return points


def _arc_points(
    cx: float, cy: float, r: float, start_deg: float, end_deg: float, count: int
) -> list[tuple[float, float]]:
    if count <= 1:
        count = 2
    start = math.radians(start_deg)
    end = math.radians(end_deg)
    return [
        (
            cx + math.cos(start + (end - start) * i / (count - 1)) * r,
            cy - math.sin(start + (end - start) * i / (count - 1)) * r,
        )
        for i in range(count)
    ]


def _polygon_points(
    cx: float, cy: float, r: float, sides: int, rotation_deg: float = 0.0
) -> list[tuple[float, float]]:
    sides = min(max(int(sides), 5), 8)
    start = math.radians(rotation_deg - 90)
    return [
        (
            cx + math.cos(start + math.tau * i / sides) * r,
            cy + math.sin(start + math.tau * i / sides) * r,
        )
        for i in range(sides)
    ]


def _resample_points(
    path: list[tuple[float, float]], count: int
) -> list[tuple[float, float]]:
    """Select ``count`` points at index-based regular intervals along a path."""
    if count <= 0 or not path:
        return []
    last = len(path)
    return [path[min(last - 1, int(index * last / count))] for index in range(count)]


def _offset_performed_path(
    path: list[tuple[float, float]],
    amount: float,
    closed: bool,
    center: tuple[float, float],
    *,
    wander: float = 0.0,
    wander_period: float = 1.0,
    seed: int = 0,
) -> list[tuple[float, float]]:
    """Offset a performed centerline along its normal; positive points outward.

    Contour order changes the normal sign: circles point inward while arcs point
    outward. A single majority vote against the figure center aligns the result
    with the geometric ``r + offset`` convention.

    `wander` adds a low-frequency drift to the offset along the arc length, the
    same way `_offset_polyline` does it for the straight tools: strata that stay
    exactly parallel read as engraved rails rather than as a tool's own edges.
    """
    normals = centerline_normals(path, closed)
    votes = 0
    for (x, y), (nx, ny) in zip(path, normals):
        votes += 1 if nx * (x - center[0]) + ny * (y - center[1]) >= 0 else -1
    sign = 1.0 if votes >= 0 else -1.0
    out: list[tuple[float, float]] = []
    arc = 0.0
    for i, ((x, y), (nx, ny)) in enumerate(zip(path, normals)):
        off = amount
        if wander:
            off += wander * (
                _value_noise_1d(arc / max(1e-6, wander_period), seed) * 2 - 1
            )
        out.append((x + nx * off * sign, y + ny * off * sign))
        if i + 1 < len(path):
            arc += math.hypot(path[i + 1][0] - x, path[i + 1][1] - y)
    return out


def _closed_path_length(path: list[tuple[float, float]]) -> float:
    """Return a closed polyline perimeter in pixels for perimeter-scaled marks."""
    if len(path) < 2:
        return 0.0
    return sum(
        math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:] + path[:1])
    )


def _points_center(path: list[tuple[float, float]]) -> tuple[float, float]:
    """Return the approximate center used to vote on normal orientation."""
    if not path:
        return (0.0, 0.0)
    return (
        sum(x for x, _ in path) / len(path),
        sum(y for _, y in path) / len(path),
    )


def _px(coord: tuple[float, float], canvas: CanvasSize) -> tuple[float, float]:
    x, y = coord
    return x * canvas.width, y * canvas.height


def _size_px(size: Sequence[float], canvas: CanvasSize) -> tuple[float, float]:
    """Both extents follow the short edge, so a mark keeps the proportion the
    description gave it: a square stays square, and a 2:1 ellipse stays 2:1 on
    any canvas. The aspect decides where a mark sits, not what shape it is --
    placement still goes through _px, which keeps using width and height.
    """
    return size[0] * canvas.unit, size[1] * canvas.unit
