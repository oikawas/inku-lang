"""Deterministic shared stroke synthesis for hand- and engraving-like tools."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math


@dataclass(frozen=True)
class ToolGrammar:
    stiffness: float
    damping: float
    energy_width: float
    energy_lateral: float
    event_rate: float
    taper: float
    bulge: float


GRAMMARS: dict[str, ToolGrammar] = {
    "hair": ToolGrammar(0.93, 0.90, 0.08, 0.05, 0.04, 0.05, 0.02),
    "pencil": ToolGrammar(0.58, 0.68, 0.34, 0.42, 0.55, 0.12, 0.14),
    "pen": ToolGrammar(0.82, 0.80, 0.16, 0.12, 0.12, 0.08, 0.06),
    "rotring": ToolGrammar(1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "crayon": ToolGrammar(0.48, 0.60, 0.38, 0.34, 0.75, 0.14, 0.18),
    "chalk": ToolGrammar(0.42, 0.56, 0.42, 0.38, 0.90, 0.18, 0.20),
    "brush_thin": ToolGrammar(0.36, 0.52, 0.66, 0.48, 0.48, 0.88, 0.28),
    "brush_thick": ToolGrammar(0.30, 0.48, 0.78, 0.55, 0.58, 0.92, 0.34),
    "burin": ToolGrammar(0.91, 0.86, 0.58, 0.09, 0.08, 0.98, 1.0),
    "drypoint": ToolGrammar(0.68, 0.70, 0.44, 0.20, 0.45, 0.55, 0.48),
}


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
) -> StrokeResult:
    grammar = GRAMMARS[weight]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max(1e-6, math.hypot(dx, dy))
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    events = _event_map(seed, grammar.event_rate, samples)
    position = [start[0], start[1]]
    velocity = [dx / (samples - 1), dy / (samples - 1)]
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
        envelope = max(0.0, math.sin(math.pi * t))
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
            lateral += math.sin((i % 5) * math.pi / 2) * base_width * 0.25
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
        result.append(
            StrokeSample(
                t,
                position[0] + nx * lateral,
                position[1] + ny * lateral,
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
    return "M " + " L ".join(f"{x:.3f} {y:.3f}" for x, y in points) + " Z"
