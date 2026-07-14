"""Read-only composition mirrors shared by the inku server and CLI.

This package must remain independent from interpretation, composition, coerce,
and rendering. Its results are for human-facing inspection only.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

PRIMITIVES = ("line", "circle", "ellipse", "triangle", "square", "polygon", "arc")
COLORS = ("white", "black", "blue", "red", "green", "gray")
LAYOUTS = ("horizontal", "vertical", "radial", "scatter", "grid")
PATHS = ("none", "diagonal", "wave", "top_to_bottom", "left_to_right", "right_half")
DENSITIES = ("none", "low", "medium", "high")


def _pair(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def _instruction_center(instruction: dict[str, Any]) -> tuple[float, float] | None:
    center = _pair(instruction.get("center"))
    if center is not None:
        return center
    position = _pair(instruction.get("position"))
    size = _pair(instruction.get("size"))
    if position is not None:
        return position[0] + (size[0] / 2 if size else 0), position[1] + (size[1] / 2 if size else 0)
    start, end = _pair(instruction.get("from")), _pair(instruction.get("to"))
    if start is not None and end is not None:
        return (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
    region = instruction.get("at")
    if isinstance(region, dict) and isinstance(region.get("region"), (list, tuple)) and len(region["region"]) == 4:
        x0, y0, x1, y1 = (float(value) for value in region["region"])
        return (x0 + x1) / 2, (y0 + y1) / 2
    return None


def composition_family(score: dict[str, Any]) -> str:
    votes: Counter[str] = Counter()
    centers: list[tuple[float, float]] = []
    for instruction in score.get("instructions") or []:
        if not isinstance(instruction, dict):
            continue
        center = _instruction_center(instruction)
        if center is not None:
            centers.append(center)
        arrangement = instruction.get("arrangement")
        if not isinstance(arrangement, dict):
            continue
        path, layout = arrangement.get("path"), arrangement.get("layout")
        if path == "diagonal":
            votes["diagonal_band"] += 2
        elif path == "right_half":
            votes["one_sided_focus"] += 2
        elif path == "top_to_bottom":
            votes["vertical_rhythm"] += 2
        elif path == "left_to_right":
            votes["horizontal_strata"] += 2
        elif path == "wave":
            votes["dispersal"] += 1
        if layout == "vertical":
            votes["vertical_rhythm"] += 1
        elif layout == "horizontal":
            votes["horizontal_strata"] += 1
        elif layout == "radial":
            votes["radial_concentric"] += 2
        elif layout in {"scatter", "grid"}:
            votes["dispersal"] += 1
    if centers:
        avg_x = sum(point[0] for point in centers) / len(centers)
        avg_y = sum(point[1] for point in centers) / len(centers)
        if 0.42 <= avg_x <= 0.58 and 0.42 <= avg_y <= 0.58:
            votes["central_stillness"] += 2
        if avg_x < 0.25 or avg_x > 0.75 or avg_y < 0.25 or avg_y > 0.75:
            votes["edge_retreat"] += 2
        elif avg_x < 0.40 or avg_x > 0.60:
            votes["one_sided_focus"] += 2
    return votes.most_common(1)[0][0] if votes else "dispersal"


def composition_vector(score: dict[str, Any]) -> tuple[float, ...]:
    """Return a deterministic schema-only vector with no public score meaning."""
    instructions = [item for item in score.get("instructions") or [] if isinstance(item, dict)]
    total = max(1, len(instructions))
    primitive = Counter(str(item.get("primitive")) for item in instructions)
    color = Counter(str(item.get("color")) for item in instructions)
    layout: Counter[str] = Counter()
    path: Counter[str] = Counter()
    density: Counter[str] = Counter()
    angle = [0.0] * 8
    for item in instructions:
        arrangement = item.get("arrangement")
        if isinstance(arrangement, dict):
            layout[str(arrangement.get("layout") or "horizontal")] += 1
            path[str(arrangement.get("path") or "none")] += 1
            density[str(arrangement.get("density") or "none")] += 1
        start, end = _pair(item.get("from")), _pair(item.get("to"))
        if start is not None and end is not None:
            radians = math.atan2(end[1] - start[1], end[0] - start[0]) % math.pi
            angle[int((radians / math.pi) * 8) % 8] += 1
        rotation = item.get("rotation")
        if isinstance(rotation, (int, float)):
            angle[int(((float(rotation) % 180) / 180) * 8) % 8] += 1
    angle_total = max(1.0, sum(angle))
    families = (
        "central_stillness", "diagonal_band", "one_sided_focus", "vertical_rhythm",
        "horizontal_strata", "radial_concentric", "edge_retreat", "dispersal",
    )
    family = composition_family(score)
    return tuple(
        [1.0 if family == name else 0.0 for name in families]
        + [primitive[name] / total for name in PRIMITIVES]
        + [color[name] / total for name in COLORS]
        + [layout[name] / total for name in LAYOUTS]
        + [path[name] / total for name in PATHS]
        + [density[name] / total for name in DENSITIES]
        + [value / angle_total for value in angle]
    )


def composition_distance(first: dict[str, Any], second: dict[str, Any]) -> float:
    a, b = composition_vector(first), composition_vector(second)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def motif_signatures(score: dict[str, Any]) -> tuple[str, ...]:
    """Return deterministic primitive/color/placement motif keys."""
    signatures: Counter[str] = Counter()
    for item in score.get("instructions") or []:
        if not isinstance(item, dict):
            continue
        primitive = str(item.get("primitive") or "unknown")
        color = str(item.get("color") or "unknown")
        arrangement = item.get("arrangement") if isinstance(item.get("arrangement"), dict) else {}
        count = int(arrangement.get("count") or 1)
        if count >= 12:
            size_class = "bundle"
        else:
            radius = float(item.get("radius") or 0)
            size = _pair(item.get("size"))
            extent = radius * 2 if radius else max(size or (0.0, 0.0))
            size_class = "large" if extent >= 0.34 else "small" if extent <= 0.12 else "medium"
        center = _instruction_center(item) or (0.5, 0.5)
        horizontal = "left" if center[0] < 0.34 else "right" if center[0] > 0.66 else "center"
        vertical = "top" if center[1] < 0.34 else "bottom" if center[1] > 0.66 else "middle"
        placement = str(arrangement.get("path") or arrangement.get("layout") or f"{horizontal}_{vertical}")
        signatures[f"{size_class}_{primitive}:{color}:{placement}"] += 1
    return tuple(sorted(key if count == 1 else f"{key}×{count}" for key, count in signatures.items()))


__all__ = ["composition_distance", "composition_family", "composition_vector", "motif_signatures"]
