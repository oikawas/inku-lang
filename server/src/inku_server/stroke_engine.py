"""Deterministic shared stroke synthesis for hand- and engraving-like tools."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

from .master_grid import fmt


@dataclass(frozen=True)
class ToolGrammar:
    stiffness: float
    damping: float
    energy_width: float
    energy_lateral: float
    event_rate: float
    taper: float
    bulge: float
    # Tool-habit gesture amplitude as a fraction of the stroke length: a slow
    # low-frequency wander of the centreline itself (bends, curls, self-overlap),
    # distinct from `energy_lateral` which is scaled by pen width. Multiplied by
    # WILD_GAIN when the performance is unleashed. rotring keeps the machine pole.
    gesture: float


GRAMMARS: dict[str, ToolGrammar] = {
    "hair": ToolGrammar(0.93, 0.90, 0.08, 0.05, 0.04, 0.05, 0.02, 0.012),
    "pencil": ToolGrammar(0.58, 0.68, 0.34, 0.42, 0.55, 0.12, 0.14, 0.05),
    "pen": ToolGrammar(0.82, 0.80, 0.16, 0.12, 0.12, 0.08, 0.06, 0.022),
    "rotring": ToolGrammar(1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "crayon": ToolGrammar(0.48, 0.60, 0.38, 0.34, 0.75, 0.14, 0.18, 0.06),
    "chalk": ToolGrammar(0.42, 0.56, 0.42, 0.38, 0.90, 0.18, 0.20, 0.07),
    "brush_thin": ToolGrammar(0.36, 0.52, 0.66, 0.48, 0.48, 0.88, 0.28, 0.10),
    "brush_thick": ToolGrammar(0.30, 0.48, 0.78, 0.55, 0.58, 0.92, 0.34, 0.13),
    "burin": ToolGrammar(0.91, 0.86, 0.58, 0.09, 0.08, 0.98, 1.0, 0.018),
    "drypoint": ToolGrammar(0.68, 0.70, 0.44, 0.20, 0.45, 0.55, 0.48, 0.05),
}

# The performance ceiling. OFF (predictable): tool-habit gesture only. ON
# (unleashed): the amplitude ceiling and the no-self-intersection guard are
# removed. Endpoint pinning and determinism are kept in both.
WILD_GAIN = 3.5


@dataclass(frozen=True)
class StrokeSample:
    t: float
    x: float
    y: float
    width: float
    energy: float
    lateral: float
    event: str | None = None


@dataclass(frozen=True)
class StrokeResult:
    samples: tuple[StrokeSample, ...]
    outline: tuple[tuple[float, float], ...]
    event_count: int
    burr_side: int
    burr_opacity: float


@dataclass(frozen=True)
class ContourStrokeResult:
    """A stroke synthesized along an arbitrary centerline.

    `left` and `right` are the two banks of the stroke. For an open centerline
    they form one polygon; for a closed one they are the outer and inner rings
    of a band and must be filled with the even-odd rule.
    """

    samples: tuple[StrokeSample, ...]
    left: tuple[tuple[float, float], ...]
    right: tuple[tuple[float, float], ...]
    event_count: int
    burr_side: int
    burr_opacity: float
    closed: bool


def _unit(seed: int, label: str, index: int) -> float:
    raw = hashlib.sha256(f"{seed}:{label}:{index}".encode()).digest()[:8]
    return int.from_bytes(raw, "little") / (2**64 - 1)


def _smooth_noise(t: float, seed: int, octave: int) -> float:
    frequency = 2**octave
    x = t * frequency
    i = math.floor(x)
    f = x - i
    f = f * f * (3 - 2 * f)
    a = _unit(seed, f"energy-{octave}", i) * 2 - 1
    b = _unit(seed, f"energy-{octave}", i + 1) * 2 - 1
    return a * (1 - f) + b * f


def latent_energy(t: float, seed: int) -> float:
    # Amplitude 1/sqrt(f): power follows an approximately 1/f spectrum.
    values = [
        _smooth_noise(t, seed, octave) / math.sqrt(2**octave) for octave in range(1, 7)
    ]
    return max(-1.0, min(1.0, sum(values) / 1.75))


def _smooth_noise_salted(t: float, seed: int, salt: str, frequency: float) -> float:
    # Same value-noise as `_smooth_noise` but at an arbitrary (low) frequency and
    # an explicit salt, so envelopes and gestures draw from independent streams.
    x = t * frequency
    i = math.floor(x)
    f = x - i
    f = f * f * (3 - 2 * f)
    a = _unit(seed, salt, i) * 2 - 1
    b = _unit(seed, salt, i + 1) * 2 - 1
    return a * (1 - f) + b * f


# Fraction at each end over which the endpoint taper ramps. Inside it the window
# is 1.0, so the middle no longer carries a fixed central bulge.
_GESTURE_EDGE = 0.16


def _edge_window(t: float) -> float:
    # 1.0 across the middle, raised-cosine down to 0 at both endpoints. Replaces
    # the old `max(0, sin(pi t))` so wobble and gestures still vanish where the
    # endpoints are pinned, without imposing one symmetric hump on every stroke.
    if t <= 0.0 or t >= 1.0:
        return 0.0
    if t < _GESTURE_EDGE:
        return 0.5 * (1 - math.cos(math.pi * t / _GESTURE_EDGE))
    if t > 1.0 - _GESTURE_EDGE:
        return 0.5 * (1 - math.cos(math.pi * (1.0 - t) / _GESTURE_EDGE))
    return 1.0


def _swell(t: float, seed: int) -> float:
    # A slow per-stroke modulation of where the stroke reads as full, in
    # [0.45, 1.0]. Replaces the fixed sine peak so "where it is fat" wanders.
    n = _smooth_noise_salted(t, seed, "swell", 1.5)
    return 0.45 + 0.55 * (0.5 + 0.5 * n)


def _gesture_wave(t: float, seed: int, salt: str) -> float:
    # Low-frequency 2D drive for the centreline gesture, in [-1, 1]. One and two
    # cycles per stroke so it bends and curls rather than buzzes.
    a = _smooth_noise_salted(t, seed, salt, 1.0)
    b = _smooth_noise_salted(t, seed, salt, 2.0)
    return max(-1.0, min(1.0, a * 0.7 + b * 0.35))


def _event_map(seed: int, rate: float, count: int) -> dict[int, str]:
    events: dict[int, str] = {}
    # Bernoulli approximation to sparse Poisson arrivals; endpoint anchors excluded.
    probability = min(0.12, rate / max(1, count - 2))
    kinds = ("catch", "fade", "correction")
    for i in range(3, count - 3):
        if _unit(seed, "event-arrival", i) < probability:
            events[i] = kinds[
                int(_unit(seed, "event-kind", i) * len(kinds)) % len(kinds)
            ]
            if len(events) >= 2:
                break
    return events


def synthesize_stroke(
    start: tuple[float, float],
    end: tuple[float, float],
    base_width: float,
    weight: str,
    seed: int,
    samples: int = 49,
    *,
    wild: bool = False,
) -> StrokeResult:
    grammar = GRAMMARS[weight]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max(1e-6, math.hypot(dx, dy))
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    events = _event_map(seed, grammar.event_rate, samples)
    position = [start[0], start[1]]
    velocity = [dx / (samples - 1), dy / (samples - 1)]
    gesture_amp = length * grammar.gesture * (WILD_GAIN if wild else 1.0)
    result: list[StrokeSample] = []
    for i in range(samples):
        t = i / (samples - 1)
        target = (start[0] + dx * t, start[1] + dy * t)
        if i:
            # L1: damped second-order tracking, scaled so corners can later use the same integrator.
            velocity[0] = (
                velocity[0] * grammar.damping
                + (target[0] - position[0]) * grammar.stiffness
            )
            velocity[1] = (
                velocity[1] * grammar.damping
                + (target[1] - position[1]) * grammar.stiffness
            )
            position[0] += velocity[0] * 0.72
            position[1] += velocity[1] * 0.72
        energy = latent_energy(t, seed)
        envelope = _edge_window(t) * _swell(t, seed)
        lateral = (
            energy * grammar.energy_lateral * base_width * (0.18 + 0.82 * envelope)
        )
        event = events.get(i)
        event_width = 1.0
        if event == "catch":
            event_width = 1.45
            lateral += (_unit(seed, "catch-side", i) * 2 - 1) * base_width * 0.35
        elif event == "fade":
            event_width = 0.04
        elif event == "correction":
            # Length-based, not sample-index-based: a seed kick that does not
            # change texture when the sample count changes.
            lateral += (_unit(seed, "correction-kick", i) * 2 - 1) * base_width * 0.25
        profile = 1.0
        if grammar.taper:
            profile *= (1 - grammar.taper) + grammar.taper * envelope
        if grammar.bulge:
            profile *= 1 + grammar.bulge * envelope
        width = max(
            0.015,
            base_width
            * profile
            * (1 + grammar.energy_width * energy * 0.45)
            * event_width,
        )
        # Centreline gesture: a low-frequency 2D wander scaled by stroke length.
        # The edge window pins it to zero at both endpoints; determinism is from
        # the seed. Under `wild` the amplitude ceiling is lifted so the path may
        # fold and cross itself.
        gx = gy = 0.0
        if gesture_amp:
            win = _edge_window(t)
            g_lat = _gesture_wave(t, seed, "gesture-lat")
            g_lon = _gesture_wave(t, seed, "gesture-lon")
            gx = gesture_amp * win * (nx * g_lat + ux * g_lon)
            gy = gesture_amp * win * (ny * g_lat + uy * g_lon)
        result.append(
            StrokeSample(
                t,
                position[0] + nx * lateral + gx,
                position[1] + ny * lateral + gy,
                width,
                energy,
                lateral,
                event,
            )
        )
    # Pin intention endpoints. Width still carries the entry/exit profile.
    result[0] = StrokeSample(
        0.0, start[0], start[1], result[0].width, result[0].energy, 0.0, None
    )
    result[-1] = StrokeSample(
        1.0, end[0], end[1], result[-1].width, result[-1].energy, 0.0, None
    )
    left = [(p.x + nx * p.width / 2, p.y + ny * p.width / 2) for p in result]
    right = [(p.x - nx * p.width / 2, p.y - ny * p.width / 2) for p in reversed(result)]
    side = -1 if _unit(seed, "burr-side", 0) < 0.5 else 1
    slow_energy = sum(p.energy for p in result) / len(result)
    burr_opacity = 0.15 + 0.12 * (1 - slow_energy) + 0.08 * _unit(seed, "burr-ink", 0)
    return StrokeResult(
        tuple(result), tuple(left + right), len(events), side, min(0.35, burr_opacity)
    )


def polygon_path(points: tuple[tuple[float, float], ...]) -> str:
    if not points:
        return ""
    return "M " + " L ".join(f"{fmt(x)} {fmt(y)}" for x, y in points) + " Z"


def ring_path(
    outer: tuple[tuple[float, float], ...], inner: tuple[tuple[float, float], ...]
) -> str:
    """Two subpaths forming a band. The caller must fill it with even-odd."""
    return f"{polygon_path(outer)} {polygon_path(inner)}".strip()


def contour_stroke_path(result: ContourStrokeResult) -> str:
    if result.closed:
        return ring_path(result.left, result.right)
    return polygon_path(result.left + tuple(reversed(result.right)))


def centerline_normals(
    points: list[tuple[float, float]], closed: bool
) -> list[tuple[float, float]]:
    """Unit normal per vertex, taken from the neighbouring vertices."""
    last = len(points) - 1
    count = len(points)
    normals: list[tuple[float, float]] = []
    for index in range(count):
        if closed:
            before = points[index - 1]
            after = points[(index + 1) % count]
        else:
            before = points[max(0, index - 1)]
            after = points[min(last, index + 1)]
        dx, dy = after[0] - before[0], after[1] - before[1]
        length = max(1e-6, math.hypot(dx, dy))
        normals.append((-dy / length, dx / length))
    return normals


def _arc_length_parameters(
    points: list[tuple[float, float]], closed: bool
) -> list[float]:
    """Normalized arc length per vertex. A closed loop counts the seam segment."""
    running = [0.0]
    total = 0.0
    for index in range(1, len(points)):
        previous, current = points[index - 1], points[index]
        total += math.hypot(current[0] - previous[0], current[1] - previous[1])
        running.append(total)
    if closed and len(points) > 1:
        total += math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1])
    if total <= 1e-9:
        return [0.0] * len(points)
    return [value / total for value in running]


def outline_for_centerline(
    points: list[tuple[float, float]], widths: list[float]
) -> tuple[tuple[float, float], ...]:
    """Build one variable-width polygon around an arbitrary intended centerline."""
    if len(points) < 2:
        return tuple(points)
    left, right = _banks_for_centerline(points, widths, closed=False)
    return tuple(list(left) + list(reversed(right)))


def _banks_for_centerline(
    points: list[tuple[float, float]], widths: list[float], closed: bool
) -> tuple[tuple[tuple[float, float], ...], tuple[tuple[float, float], ...]]:
    normals = centerline_normals(points, closed)
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for index, (x, y) in enumerate(points):
        nx, ny = normals[index]
        width = widths[min(index, len(widths) - 1)]
        left.append((x + nx * width / 2, y + ny * width / 2))
        right.append((x - nx * width / 2, y - ny * width / 2))
    return tuple(left), tuple(right)


def synthesize_along(
    centerline: list[tuple[float, float]],
    base_width: float,
    weight: str,
    seed: int,
    *,
    closed: bool,
    anchors: frozenset[int] = frozenset(),
) -> ContourStrokeResult:
    """Synthesize one stroke that follows an arbitrary intended centerline.

    Same tool grammar as `synthesize_stroke`: the damped tracker lags behind the
    intention, latent energy modulates width and lateral drift, and sparse
    events (catch / fade / correction) interrupt the run. Only the target track
    differs, so a contour is played as a stroke rather than drawn as geometry.

    `anchors` are vertex indices the tool is required to reach exactly; the
    tracker is reset there, which is how a polygon corner reads as a joint
    between two strokes. A closed centerline with no anchors is instead closed
    by ramping the accumulated deviation back to its seam value, so the loop
    meets itself without a kink.
    """
    points = list(centerline)
    count = len(points)
    grammar = GRAMMARS[weight]
    if count < 2:
        sample = StrokeSample(0.0, points[0][0], points[0][1], base_width, 0.0, 0.0)
        return ContourStrokeResult(
            (sample,), tuple(points), tuple(points), 0, 1, 0.0, closed
        )

    normals = centerline_normals(points, closed)
    parameters = _arc_length_parameters(points, closed)
    events = _event_map(seed, grammar.event_rate, count)
    position = [points[0][0], points[0][1]]
    velocity = [0.0, 0.0]
    samples: list[StrokeSample] = []
    for index, target in enumerate(points):
        t = parameters[index]
        if index:
            # L1 with the intended step fed forward: the same damped tracker as
            # the straight-line synthesizer, but the spring only carries the
            # residual. On a straight run the tracker's lag is purely along the
            # track and invisible; on a curve it would turn into a radial error
            # that shrinks and dents the shape. Feeding the step forward leaves
            # deviation where the intention actually changes direction — the
            # corners — which is where a hand overshoots.
            previous = points[index - 1]
            step = (target[0] - previous[0], target[1] - previous[1])
            velocity[0] = (
                velocity[0] * grammar.damping
                + (target[0] - position[0] - step[0]) * grammar.stiffness
            )
            velocity[1] = (
                velocity[1] * grammar.damping
                + (target[1] - position[1] - step[1]) * grammar.stiffness
            )
            position[0] += step[0] + velocity[0] * 0.72
            position[1] += step[1] + velocity[1] * 0.72
        energy = latent_energy(t, seed)
        if closed:
            # A loop has no endpoints, so no edge taper: the old sine imposed a
            # spurious thin seam opposite a fat middle. The swell alone (floored)
            # keeps the loop unbroken while letting the fullness wander.
            envelope = _swell(t, seed)
        else:
            envelope = _edge_window(t) * _swell(t, seed)
        lateral = (
            energy * grammar.energy_lateral * base_width * (0.18 + 0.82 * envelope)
        )
        event = events.get(index)
        event_width = 1.0
        if event == "catch":
            event_width = 1.45
            lateral += (_unit(seed, "catch-side", index) * 2 - 1) * base_width * 0.35
        elif event == "fade":
            event_width = 0.04
        elif event == "correction":
            # Length-based seed kick (see synthesize_stroke).
            lateral += (_unit(seed, "correction-kick", index) * 2 - 1) * base_width * 0.25
        profile = 1.0
        if grammar.taper:
            profile *= (1 - grammar.taper) + grammar.taper * envelope
        if grammar.bulge:
            profile *= 1 + grammar.bulge * envelope
        width = max(
            0.015,
            base_width
            * profile
            * (1 + grammar.energy_width * energy * 0.45)
            * event_width,
        )
        nx, ny = normals[index]
        x, y = position[0] + nx * lateral, position[1] + ny * lateral
        if index in anchors:
            x, y, lateral, event = target[0], target[1], 0.0, None
            position = [target[0], target[1]]
        samples.append(StrokeSample(t, x, y, width, energy, lateral, event))

    if not closed:
        # Pin intention endpoints, as the straight-line synthesizer does.
        samples[0] = StrokeSample(
            0.0, points[0][0], points[0][1], samples[0].width, samples[0].energy, 0.0
        )
        samples[-1] = StrokeSample(
            1.0,
            points[-1][0],
            points[-1][1],
            samples[-1].width,
            samples[-1].energy,
            0.0,
        )
    elif not anchors and count > 2:
        samples = _closed_seam_correction(samples, points, parameters)

    performed = [(sample.x, sample.y) for sample in samples]
    widths = [sample.width for sample in samples]
    left, right = _banks_for_centerline(performed, widths, closed)
    side = -1 if _unit(seed, "burr-side", 0) < 0.5 else 1
    slow_energy = sum(sample.energy for sample in samples) / len(samples)
    burr_opacity = 0.15 + 0.12 * (1 - slow_energy) + 0.08 * _unit(seed, "burr-ink", 0)
    return ContourStrokeResult(
        tuple(samples),
        left,
        right,
        len(events),
        side,
        min(0.35, burr_opacity),
        closed,
    )


def _closed_seam_correction(
    samples: list[StrokeSample],
    points: list[tuple[float, float]],
    parameters: list[float],
) -> list[StrokeSample]:
    """Ramp the accumulated deviation so the loop meets itself at the seam."""
    span = parameters[-1]
    if span <= 1e-9:
        return samples
    first, last = samples[0], samples[-1]
    gap_x = (last.x - points[-1][0]) - (first.x - points[0][0])
    gap_y = (last.y - points[-1][1]) - (first.y - points[0][1])
    gap_width = last.width - first.width
    corrected: list[StrokeSample] = []
    for index, sample in enumerate(samples):
        factor = parameters[index] / span
        corrected.append(
            StrokeSample(
                sample.t,
                sample.x - gap_x * factor,
                sample.y - gap_y * factor,
                max(0.015, sample.width - gap_width * factor),
                sample.energy,
                sample.lateral,
                sample.event,
            )
        )
    return corrected
