"""Deterministic shared stroke synthesis for hand- and engraving-like tools."""

from __future__ import annotations

from collections.abc import Sequence
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
    # Exact repetition belongs to the computer tool. The zero defaults keep the
    # existing hand-tool grammars on their unchanged path.
    periodic: bool = False
    # Lattice pitch as a fraction of the canvas short side, not of the stroke.
    # The grid is the paper the tool works on, so one drawing has one grid: a
    # short line and a long one land on the same cells. The caller turns this
    # into px (`canvas.unit * quantize`) and passes it in as `grid_step`,
    # because this module does not know the canvas.
    quantize: float = 0.0
    width_steps: int = 0
    # How loose the hand is when this tool fills an area, from 0 (a machine:
    # every scan line parallel, every endpoint on the contour) to 1 (the loosest
    # brush). The renderer reads it for the three quantities that made a fill
    # read as a raster -- the scan angle, the pitch, and how far each stroke
    # reaches past the contour -- so the amplitude belongs to the tool and the
    # description never has to name it. Zero for `rotring` and `computer`:
    # exact repetition is the machine's signature, not a defect to sand off.
    fill_hand: float = 0.0
    # How much this tool's members of one repeated group differ in size, as a
    # fraction either side of the stated dimension (0.25 = 0.75x..1.25x). An
    # `Arrangement` declares "several of this shape", never "all of them the
    # same size", so the congruence was the engine's addition and this takes it
    # back out. One value for every hand tool rather than one derived from
    # `fill_hand`: the ruling (author, 2026-08-08) was given on samples that
    # applied the same +/-25% to tools spanning 0.05..0.90 of `fill_hand`, so
    # scaling it per tool would leave the picture that was approved. Zero for
    # `rotring` and `computer`, pinned by hand for the same reason `fill_hand`
    # is: exact repetition is the machine's signature.
    group_hand: float = 0.0
    # How far this tool's members of one repeated group turn away from the
    # stated angle, in degrees either side of it (12.0 = -12..+12). The same
    # argument as `group_hand`: an `Arrangement` says "several of this shape"
    # and never "all of them at the same angle", so the shared angle was the
    # engine's own addition. It is a separate field rather than a multiple of
    # `group_hand` because the two amplitudes were ruled on together as a pair
    # (author, 2026-08-08) and either could be retuned without the other. Zero
    # for `rotring` and `computer`, pinned by hand the way `fill_hand` and
    # `group_hand` are: exact repetition is the machine's signature.
    group_rot: float = 0.0
    # How far this tool's fill marks stand out from the field they sit on, as a
    # multiple of whichever branch contrast applies. 1.0 leaves the tool on the
    # branch's own value; above it the marks read as separate strokes rather
    # than as grain in a tone. It lives here rather than in the renderer because
    # "how much this tool separates from its own tone" is a property of the
    # tool, and a renderer that listed tool names would stop following the
    # description the moment one asked for a thin chalk.
    fill_contrast: float = 1.0


# Every hand tool gets the same amount of size variation inside a group. The
# ruling that set +/-25% was given on samples that used one amplitude for four
# tools whose `fill_hand` spans 18x, so this is a single constant rather than a
# per-tool value; a tool-by-tool adjustment is a later change, made once the
# effect is measured.
HAND_GROUP_SIZE = 0.25

# And the same amount of angle variation, in degrees. The ruling that set the
# pair (+/-25% and +/-12 degrees, author 2026-08-08) was given on one sample
# sheet that used one amplitude for every hand tool, so this is a single
# constant for the same reason `HAND_GROUP_SIZE` is.
HAND_GROUP_ROT = 12.0

# `fill_hand` runs with the tool's stiffness: the stiffer the tool, the tighter
# the hand that fills with it. The two machines are pinned at zero by hand
# rather than derived, because zero has to be exact.
GRAMMARS: dict[str, ToolGrammar] = {
    "silverpoint": ToolGrammar(
        0.93, 0.90, 0.08, 0.05, 0.04, 0.05, 0.02, 0.012,
        fill_hand=0.05, group_hand=HAND_GROUP_SIZE, group_rot=HAND_GROUP_ROT,
    ),
    "pencil": ToolGrammar(
        0.58, 0.68, 0.34, 0.42, 0.55, 0.12, 0.14, 0.05,
        fill_hand=0.60, group_hand=HAND_GROUP_SIZE, group_rot=HAND_GROUP_ROT,
    ),
    "pen": ToolGrammar(
        0.82, 0.80, 0.16, 0.12, 0.12, 0.08, 0.06, 0.022,
        fill_hand=0.25, group_hand=HAND_GROUP_SIZE, group_rot=HAND_GROUP_ROT,
    ),
    "rotring": ToolGrammar(
        1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        group_hand=0.0, group_rot=0.0,
    ),
    "crayon": ToolGrammar(
        0.48, 0.60, 0.38, 0.34, 0.75, 0.14, 0.18, 0.06,
        fill_hand=0.72, group_hand=HAND_GROUP_SIZE, group_rot=HAND_GROUP_ROT,
    ),
    # chalk carries the one `fill_contrast` above 1.0: "give chalk more contrast
    # than crayon" (author, 2026-08-07). The two tools sit either side of it in
    # coverage (0.250 against 0.333) and read almost alike otherwise, so the
    # separation has to be asked for rather than fall out of the widths.
    "chalk": ToolGrammar(
        0.42, 0.56, 0.42, 0.38, 0.90, 0.18, 0.20, 0.07,
        fill_hand=0.80,
        group_hand=HAND_GROUP_SIZE, group_rot=HAND_GROUP_ROT,
        fill_contrast=1.13,
    ),
    "brush_thin": ToolGrammar(
        0.36, 0.52, 0.66, 0.48, 0.48, 0.88, 0.28, 0.10,
        fill_hand=0.90, group_hand=HAND_GROUP_SIZE, group_rot=HAND_GROUP_ROT,
    ),
    "brush_thick": ToolGrammar(
        0.30, 0.48, 0.78, 0.55, 0.58, 0.92, 0.34, 0.13,
        fill_hand=1.00, group_hand=HAND_GROUP_SIZE, group_rot=HAND_GROUP_ROT,
    ),
    "burin": ToolGrammar(
        0.91, 0.86, 0.58, 0.09, 0.08, 0.98, 1.0, 0.018,
        fill_hand=0.10, group_hand=HAND_GROUP_SIZE, group_rot=HAND_GROUP_ROT,
    ),
    "drypoint": ToolGrammar(
        0.68, 0.70, 0.44, 0.20, 0.45, 0.55, 0.48, 0.05,
        fill_hand=0.45, group_hand=HAND_GROUP_SIZE, group_rot=HAND_GROUP_ROT,
    ),
    "computer": ToolGrammar(
        1.0,
        1.0,
        0.30,
        0.34,
        0.0,
        0.0,
        0.0,
        0.06,
        periodic=True,
        quantize=0.018,
        width_steps=4,
        group_hand=0.0,
        group_rot=0.0,
    ),
}

# The performance ceiling. OFF (predictable): tool-habit gesture only. ON
# (unleashed): the amplitude ceiling and the no-self-intersection guard are
# removed. Endpoint pinning and determinism are kept in both.
WILD_GAIN = 3.5


@dataclass(frozen=True)
class Support:
    """The sheet the tool works on.

    In painting the ground resists the hand: an absorbent sheet lets the ink
    spread, a toothy one refuses the tool and leaves the paper bare. There is
    one constant sheet by default, so what varies between works is which tool
    met it, not which paper was used.
    """

    absorb: float  # how much ink the sheet draws in
    tooth: float  # how much the sheet refuses the tool


DEFAULT_SUPPORT = Support(absorb=1.0, tooth=1.0)

# Which of the two quantities each tool actually meets, as (absorb, tooth).
# A brush is drunk by the sheet; a waxy or hard tool is refused by it; a pen
# barely meets either. The machines meet neither: a plotter or a sampled curve
# has no contact with paper at all, so they must stay byte-identical.
TOOL_SUPPORT_BIAS: dict[str, tuple[float, float]] = {
    "brush_thin": (1.00, 0.15),
    "brush_thick": (1.00, 0.15),
    "crayon": (0.10, 1.00),
    "pencil": (0.10, 1.00),
    # chalk is refused harder than the other two waxy tools: "for chalk, raise
    # the amount of skipping on the line side" (author, 2026-08-07). At 1.00 it
    # showed the same 4.8% bare paper as crayon and pencil, which is 1.25 gaps
    # in a stroke; at 1.30 it shows 9.5% in 1.65 gaps. Above 1.0 the sheet
    # refuses this tool more than fully, which is what the tool is.
    "chalk": (0.10, 1.30),
    "pen": (0.15, 0.15),
    "silverpoint": (0.05, 0.25),
    "drypoint": (0.00, 0.35),
    "burin": (0.00, 0.10),
    "rotring": (0.00, 0.00),
    "computer": (0.00, 0.00),
}


@dataclass(frozen=True)
class ResistanceLevel:
    """How hard the sheet pushes back. `g0` reproduces engine 18 exactly."""

    bleed_amp: float
    bleed_span: float  # window half-width as a fraction of the sample count
    bleed_rate: float
    skip_depth: float
    skip_span: float
    skip_rate: float


RESISTANCE_LEVELS: dict[str, ResistanceLevel] = {
    "g0": ResistanceLevel(0.00, 0.00, 0.0, 0.00, 0.00, 0.0),
    "g1": ResistanceLevel(0.35, 0.10, 0.9, 0.70, 0.05, 0.9),
    "g2": ResistanceLevel(0.70, 0.16, 1.5, 0.88, 0.07, 1.5),
    "g3": ResistanceLevel(1.20, 0.24, 2.2, 1.00, 0.10, 2.2),
}

# The adopted level (author, 2026-07-31). The others are kept so the monotonic
# ordering g1 < g2 < g3 stays checkable.
RESISTANCE = RESISTANCE_LEVELS["g2"]

# Envelope level above which no ink is laid down at all. Narrowing the width
# was measured to be invisible — the tools the sheet refuses are also the
# thinnest ones (pencil 1.5px), so a pinch sinks into the antialiasing. A gap
# is not a thin line: it is bare paper.
SKIP_CUT_LEVEL = 0.55


@dataclass(frozen=True)
class StrokeSample:
    t: float
    x: float
    y: float
    width: float
    energy: float
    lateral: float
    event: str | None = None
    # Distance between the intended position and the grid point it was rounded
    # to. Zero for every tool that does not quantize. This is what the computer
    # throws away when it samples, and what its material layer gives back.
    residual: float = 0.0


@dataclass(frozen=True)
class StrokeResult:
    samples: tuple[StrokeSample, ...]
    outline: tuple[tuple[float, float], ...]
    event_count: int
    burr_side: int
    burr_opacity: float
    # Side of one lattice cell, in px. Zero unless the tool quantizes.
    grid_step: float = 0.0
    # Samples where the sheet refused the tool and no ink is laid down. The
    # outline above already carries the breaks; a caller that rebuilds the
    # outline around its own centerline needs the mask to keep them.
    cuts: tuple[bool, ...] = ()


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
    # Side of one lattice cell, in px. Zero unless the tool quantizes.
    grid_step: float = 0.0


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


# The terminal is a property of the ROLE, not of the tool. The same brush ends a
# contour thin (`taper`, what `_edge_window` gives) and ends a fill stroke heavy,
# because laying down paint is heaviest the moment the brush lands. Constants are
# the ones the author approved off the run 856 sample: 1.45x where it lands,
# settling over a tenth of the run, and only the lift narrowing, to 0.55.
_LOADED_LANDING = 0.45
_LOADED_SETTLE = 0.10
_LOADED_LIFT_AT = 0.94
_LOADED_LIFT_TO = 0.55


def _loaded_profile(t: float) -> float:
    landing = 1.0 + _LOADED_LANDING * math.exp(-t / _LOADED_SETTLE)
    if t < _LOADED_LIFT_AT:
        return landing
    span = 1.0 - _LOADED_LIFT_AT
    return landing * (_LOADED_LIFT_TO + (1.0 - _LOADED_LIFT_TO) * (1.0 - t) / span)


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


def _quantize(value: float, step: float) -> float:
    return value if step <= 0 else round(value / step) * step


def grid_point(value: float, step: float) -> float:
    """The lattice point a value rounds to, for callers outside this module.

    The renderer places the computer's material cells on the same lattice the
    geometry was rounded onto, so both must round by one rule.
    """
    return _quantize(value, step)


def _machine_energy(t: float) -> float:
    # Commensurate, fixed frequencies: every computer stroke repeats the same
    # figure, independently of its render seed.
    return 0.72 * math.sin(t * math.tau * 5) + 0.28 * math.sin(t * math.tau * 10)


def _machine_swell(t: float) -> float:
    # The selectable symmetric envelope formerly imposed by engine 11.
    return 0.45 + 0.55 * math.sin(math.pi * t)


def _machine_gesture(t: float) -> float:
    # Whole cycles pin both endpoints without a separate edge window.
    return math.sin(t * math.tau * 2)


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


def _support_envelope(
    n: int, seed: int, label: str, bias: float, rate: float, span_ratio: float
) -> list[float]:
    """Sparse raised-cosine arrivals over the run. Endpoints stay pinned."""
    # Short runs and zero-bias tools never receive an arrival.
    if bias <= 0 or rate <= 0 or span_ratio <= 0 or n < 8:
        return [0.0] * n
    span = max(2, int(round(n * span_ratio)))
    # The eligible range must NOT shrink with the span, or a stronger level
    # fires less often than a weaker one (measured: bleed vanished at g2/g3).
    probability = min(0.35, rate * bias / max(1, n - 4))
    centres: list[int] = []
    for i in range(2, n - 2):
        if _unit(seed, f"{label}-arrival", i) < probability:
            centres.append(i)
            if len(centres) >= 3:
                break
    out = [0.0] * n
    for c in centres:
        size = 0.6 + 0.4 * _unit(seed, f"{label}-size", c)
        for k in range(-span, span + 1):
            idx = c + k
            if 0 <= idx < n:
                # Raised cosine: the event has no edge of its own.
                window = 0.5 * (1 + math.cos(math.pi * k / span))
                # Overlaps take the strongest, never the product: two drops
                # that meet make one wider drop, not a blob.
                out[idx] = max(out[idx], size * window)
    return out


def _support_response(
    widths: list[float], weight: str, seed: int, support: Support
) -> tuple[list[float], list[bool]]:
    """Meet the sheet: swell where it drank the ink, cut where it refused.

    One mechanism, two signs, drawn from two independent seeds so a sheet that
    absorbs and a sheet that refuses do not fire in the same places.
    """
    absorb, tooth = TOOL_SUPPORT_BIAS.get(weight, (0.0, 0.0))
    absorb *= support.absorb
    tooth *= support.tooth
    level = RESISTANCE
    n = len(widths)
    swell = _support_envelope(
        n, seed, "bleed", absorb, level.bleed_rate, level.bleed_span
    )
    pinch = _support_envelope(
        n, seed ^ 0x5BD1, "skip", tooth, level.skip_rate, level.skip_span
    )
    strength = level.skip_depth * tooth
    out = [
        max(0.015, w * (1.0 + level.bleed_amp * absorb * s) * (1.0 - strength * p))
        for w, s, p in zip(widths, swell, pinch)
    ]
    return out, [strength * p >= SKIP_CUT_LEVEL for p in pinch]


def _cut_runs(cuts: list[bool], minimum: int) -> list[list[int]]:
    """Index runs of samples that still carry ink, split at the bare paper."""
    runs: list[list[int]] = []
    current: list[int] = []
    for index, cut in enumerate(cuts):
        if cut:
            if len(current) >= minimum:
                runs.append(current)
            current = []
        else:
            current.append(index)
    if len(current) >= minimum:
        runs.append(current)
    return runs


# A break between two subpaths of one `d`. Kept inside the point tuple rather
# than beside it so every existing consumer of `outline` / `left` / `right`
# keeps its shape; the path builders below are the only readers.
_BREAK = (float("nan"), float("nan"))


def _is_break(point: tuple[float, float]) -> bool:
    return point[0] != point[0]


def synthesize_stroke(
    start: tuple[float, float],
    end: tuple[float, float],
    base_width: float,
    weight: str,
    seed: int,
    samples: int = 49,
    *,
    wild: bool = False,
    grid_step: float = 0.0,
    support: Support = DEFAULT_SUPPORT,
) -> StrokeResult:
    """Synthesize one straight stroke.

    `grid_step` is the side of one lattice cell in px, already resolved against
    the canvas by the caller. Zero means the tool does not quantize.

    `support` is the sheet being worked on. It is one constant by default; a
    work that names its own ground swaps it here.
    """
    grammar = GRAMMARS[weight]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max(1e-6, math.hypot(dx, dy))
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    events = _event_map(seed, grammar.event_rate, samples)
    position = [start[0], start[1]]
    velocity = [dx / (samples - 1), dy / (samples - 1)]
    gesture_amp = length * grammar.gesture
    if wild and not grammar.periodic:
        gesture_amp *= WILD_GAIN
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
        if grammar.periodic:
            energy = _machine_energy(t)
            envelope = _machine_swell(t)
        else:
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
            if grammar.periodic:
                # A machine repeats laterally but does not hesitate or reverse
                # along its direction of travel.
                win = 1.0
                g_lat = _machine_gesture(t)
                g_lon = 0.0
            else:
                win = _edge_window(t)
                g_lat = _gesture_wave(t, seed, "gesture-lat")
                g_lon = _gesture_wave(t, seed, "gesture-lon")
            gx = gesture_amp * win * (nx * g_lat + ux * g_lon)
            gy = gesture_amp * win * (ny * g_lat + uy * g_lon)
        x = position[0] + nx * lateral + gx
        y = position[1] + ny * lateral + gy
        residual = 0.0
        if grid_step > 0:
            qx, qy = _quantize(x, grid_step), _quantize(y, grid_step)
            residual = math.hypot(x - qx, y - qy)
            x, y = qx, qy
        if grammar.width_steps:
            width = max(0.015, _quantize(width, base_width / grammar.width_steps))
        result.append(
            StrokeSample(t, x, y, width, energy, lateral, event, residual)
        )
    # Pin intention endpoints. Width still carries the entry/exit profile.
    result[0] = StrokeSample(
        0.0, start[0], start[1], result[0].width, result[0].energy, 0.0, None
    )
    result[-1] = StrokeSample(
        1.0, end[0], end[1], result[-1].width, result[-1].energy, 0.0, None
    )
    # Meet the sheet last, so the tool grammar is what arrives at the paper.
    widths, cuts = _support_response(
        [p.width for p in result], weight, seed, support
    )
    result = [
        StrokeSample(p.t, p.x, p.y, w, p.energy, p.lateral, p.event, p.residual)
        for p, w in zip(result, widths)
    ]
    if any(cuts):
        outline: list[tuple[float, float]] = []
        for run in _cut_runs(cuts, minimum=2):
            if outline:
                outline.append(_BREAK)
            outline.extend(
                (result[i].x + nx * result[i].width / 2, result[i].y + ny * result[i].width / 2)
                for i in run
            )
            outline.extend(
                (result[i].x - nx * result[i].width / 2, result[i].y - ny * result[i].width / 2)
                for i in reversed(run)
            )
    else:
        left = [(p.x + nx * p.width / 2, p.y + ny * p.width / 2) for p in result]
        right = [
            (p.x - nx * p.width / 2, p.y - ny * p.width / 2) for p in reversed(result)
        ]
        outline = left + right
    side = -1 if _unit(seed, "burr-side", 0) < 0.5 else 1
    slow_energy = sum(p.energy for p in result) / len(result)
    burr_opacity = 0.15 + 0.12 * (1 - slow_energy) + 0.08 * _unit(seed, "burr-ink", 0)
    return StrokeResult(
        tuple(result),
        tuple(outline),
        len(events),
        side,
        min(0.35, burr_opacity),
        grid_step,
        tuple(cuts),
    )


def _closed_subpath(points) -> str:
    return "M " + " L ".join(f"{fmt(x)} {fmt(y)}" for x, y in points) + " Z"


def _split_at_breaks(
    points: tuple[tuple[float, float], ...], minimum: int
) -> list[list[tuple[float, float]]]:
    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for point in points:
        if _is_break(point):
            if len(current) >= minimum:
                runs.append(current)
            current = []
        else:
            current.append(point)
    if len(current) >= minimum:
        runs.append(current)
    return runs


def polygon_path(points: tuple[tuple[float, float], ...]) -> str:
    """One `d` for one stroke, however many runs the sheet left it in.

    Where the ground refused the tool the outline carries a break, and the ink
    on either side becomes a separate subpath. Several subpaths inside one `d`
    are still ONE element (`ring_path` already relies on this), so cutting the
    ink never adds an element to the drawing.
    """
    if not points:
        return ""
    if any(_is_break(point) for point in points):
        return " ".join(
            _closed_subpath(run) for run in _split_at_breaks(points, 3)
        ).strip()
    return _closed_subpath(points)


def ring_path(
    outer: tuple[tuple[float, float], ...], inner: tuple[tuple[float, float], ...]
) -> str:
    """Two subpaths forming a band. The caller must fill it with even-odd."""
    return f"{polygon_path(outer)} {polygon_path(inner)}".strip()


def contour_stroke_path(result: ContourStrokeResult) -> str:
    if result.closed:
        # A closed band keeps its even-odd ring: cutting it would open the
        # figure rather than leave bare paper inside the line.
        return ring_path(result.left, result.right)
    if not any(_is_break(point) for point in result.left):
        return polygon_path(result.left + tuple(reversed(result.right)))
    left_runs = _split_at_breaks(result.left, 2)
    right_runs = _split_at_breaks(result.right, 2)
    # Both banks are cut at the same samples, so the runs pair up.
    return " ".join(
        _closed_subpath(left_run + list(reversed(right_run)))
        for left_run, right_run in zip(left_runs, right_runs)
    ).strip()


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
    points: list[tuple[float, float]],
    widths: list[float],
    cuts: Sequence[bool] = (),
) -> tuple[tuple[float, float], ...]:
    """Build one variable-width polygon around an arbitrary intended centerline.

    `cuts` marks the samples where the sheet refused the tool. Rebuilding the
    outline around a centerline the caller varied would otherwise drop those
    breaks and leave the ink whole, so the runs are carried over here too.
    """
    if len(points) < 2:
        return tuple(points)
    left, right = _banks_for_centerline(points, widths, closed=False)
    if not any(cuts):
        return tuple(list(left) + list(reversed(right)))
    outline: list[tuple[float, float]] = []
    for run in _cut_runs(list(cuts)[: len(left)], minimum=2):
        if outline:
            outline.append(_BREAK)
        outline.extend(left[index] for index in run)
        outline.extend(right[index] for index in reversed(run))
    return tuple(outline)


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
    grid_step: float = 0.0,
    wild: bool = False,
    support: Support = DEFAULT_SUPPORT,
    terminal: str = "taper",
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

    `grid_step` is the side of one lattice cell in px, already resolved against
    the canvas by the caller. Zero means the tool does not quantize.

    `wild` unleashes the same centreline gesture the straight-line synthesizer
    carries, so the toggle reaches contours, arcs, fills and hatches rather than
    lines alone. With it off the amplitude is zero and nothing moves.

    `terminal` selects how the width ends. "taper" is the drawing terminal every
    open stroke had before render engine 22: thin in, thin out. "loaded" is the
    painting terminal -- heavy where the tool lands, cut at the lift. It applies
    to the width alone; the lateral drift keeps reading the same envelope, and a
    periodic tool is left on its own branch untouched.
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
    gesture_amp = 0.0
    if wild and not grammar.periodic:
        total_length = max(
            1e-6,
            sum(
                math.hypot(
                    points[index + 1][0] - points[index][0],
                    points[index + 1][1] - points[index][1],
                )
                for index in range(count - 1)
            ),
        )
        # A loop is measured by the radius its perimeter implies, not by the
        # perimeter: scaling the gesture by arc length makes a polygon a star
        # and flattens a circle, because a circumference is not a size.
        size = total_length / math.tau if closed else total_length
        gesture_amp = size * grammar.gesture * WILD_GAIN
    gestures = [0.0] * count
    if gesture_amp:
        gestures = [_gesture_wave(t, seed, "gesture-lat") for t in parameters]
        if closed:
            # How big the figure is belongs to the Score, not to the
            # performance. A gesture with a non-zero mean would inflate or
            # shrink the whole loop, so it is centred before it is applied.
            mean = sum(gestures) / count
            gestures = [value - mean for value in gestures]
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
        if grammar.periodic:
            energy = _machine_energy(t)
            envelope = 1.0 if closed else _machine_swell(t)
        elif closed:
            # A loop has no endpoints, so no edge taper: the old sine imposed a
            # spurious thin seam opposite a fat middle. The swell alone (floored)
            # keeps the loop unbroken while letting the fullness wander.
            energy = latent_energy(t, seed)
            envelope = _swell(t, seed)
        else:
            energy = latent_energy(t, seed)
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
        if terminal == "loaded" and not grammar.periodic:
            # The loaded envelope replaces the taper/bulge shaping outright: it
            # is a different terminal, not a modifier on top of the old one.
            # `periodic` is excluded here rather than earlier so the machine
            # never leaves the branch that keeps it byte-identical.
            profile = _loaded_profile(t)
        else:
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
        gesture = 0.0
        if gesture_amp:
            win = 1.0 if closed else _edge_window(t)
            if anchors:
                # A corner is a joint the tool has to reach exactly. A gesture
                # on the vertices beside it reads as a spike, so the window
                # closes before the anchor and opens again after it.
                win *= min(
                    1.0, min(abs(index - anchor) for anchor in anchors) / 12.0
                )
            gesture = gesture_amp * win * gestures[index]
        nx, ny = normals[index]
        x = position[0] + nx * (lateral + gesture)
        y = position[1] + ny * (lateral + gesture)
        residual = 0.0
        if grid_step > 0:
            qx, qy = _quantize(x, grid_step), _quantize(y, grid_step)
            residual = math.hypot(x - qx, y - qy)
            x, y = qx, qy
        if grammar.width_steps:
            width = max(0.015, _quantize(width, base_width / grammar.width_steps))
        if index in anchors:
            x, y, lateral, event = target[0], target[1], 0.0, None
            position = [target[0], target[1]]
            residual = 0.0
        samples.append(StrokeSample(t, x, y, width, energy, lateral, event, residual))

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

    # Meet the sheet last, so the tool grammar is what arrives at the paper.
    widths, cuts = _support_response(
        [sample.width for sample in samples], weight, seed, support
    )
    samples = [
        StrokeSample(s.t, s.x, s.y, w, s.energy, s.lateral, s.event, s.residual)
        for s, w in zip(samples, widths)
    ]
    performed = [(sample.x, sample.y) for sample in samples]
    left, right = _banks_for_centerline(performed, widths, closed)
    if not closed and any(cuts):
        left = tuple(
            _BREAK if cut else point for point, cut in zip(left, cuts)
        )
        right = tuple(
            _BREAK if cut else point for point, cut in zip(right, cuts)
        )
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
        grid_step,
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
                sample.residual,
            )
        )
    return corrected
