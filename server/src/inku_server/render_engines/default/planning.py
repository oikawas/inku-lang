"""Performance planning for the default render engine.

This module transforms Score / Instruction values into the final pre-draw
Instruction sequence. It deliberately owns no SVG document, layer, element, or
filter operations.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import struct
from collections.abc import Sequence
from typing import Any

from ...arc_geometry import (
    arc_from_endpoints_and_sagitta,
    arc_point,
    minor_arc_delta,
)
from ...cloudform import generate_cloudform_contour
from ...plugins import CanvasSize
from ...schema import Arrangement, Instruction, Score
from ...stroke_engine import GRAMMARS
from .determinism import _hash01, _seed_for_instruction

logger = logging.getLogger("inku_server.renderer")

# engine 20: the frame an expanded group is fitted into once it has been moved
# onto its declared anchor. Marks are allowed to touch the edge, not to leave.
FRAME_LO = 0.02
FRAME_HI = 0.98


def _scatter_pos(i: int, seed: int, margin: float) -> tuple[float, float]:
    """index i に対応する決定的な散布座標を返す (hash ベース)。"""
    span = 1.0 - 2 * margin
    h = hashlib.sha256(f"{seed}:s:{i}".encode()).digest()
    xv = struct.unpack("<I", h[:4])[0] / 0xFFFFFFFF
    yv = struct.unpack("<I", h[4:8])[0] / 0xFFFFFFFF
    return (margin + xv * span, margin + yv * span)


def _rhythm_t(i: int, n: int, seed: int, rhythm_spacing: str) -> float:
    """Return deterministic non-linear spacing for repeated arrangements."""
    if n <= 1:
        return 0.0
    base = i / (n - 1)
    if rhythm_spacing == "accelerando":
        return base**1.35
    if rhythm_spacing == "loose":
        jitter = (_hash01(i, seed, "rhythm-loose") - 0.5) * 0.16
        return _clamp01(base + jitter)
    if rhythm_spacing == "syncopated":
        beat = 0.09 if i % 2 else -0.045
        taper = math.sin(base * math.pi)
        return _clamp01(base + beat * taper)
    return base


# engine 32: the cross-axis spreads a path puts around its line. They are
# named because the gate that tells "the description's number, put on the short
# side" from "a constant fraction of the short side" has to move the stated
# number and see the drawing follow.
_PATH_WAVE_AMPLITUDE = 0.22
_PATH_JITTER = 0.08
_PATH_SPREAD = 0.30


def _path_pos(
    i: int,
    n: int,
    seed: int,
    margin: float,
    path: str,
    rhythm_spacing: str = "none",
    canvas: CanvasSize | None = None,
) -> tuple[float, float]:
    """Where member `i` of a path-following group lands, in normalized space.

    engine 32: the cross-axis spread goes on the short side. A path has two
    quantities and they are not the same kind. Along its line, `margin + t *
    span` says how much of the paper the group uses -- that is the paper's own
    length and stays proportional. Across it, the wave's swing and the jitter
    are the shape of the path, and written straight they became `0.22 * width`
    across and `0.22 * height` down, so the same wave came out with a swing of
    220px on the square canvas and 44px on the pillar. Only the second is
    levelled here; `margin` and `span` are untouched (author, 2026-08-12).
    """
    span = 1.0 - 2 * margin
    t = _rhythm_t(i, n, seed, rhythm_spacing)
    jitter_a = _hash01(i, seed, "a") - 0.5
    jitter_b = _hash01(i, seed, "b") - 0.5
    scale_x, scale_y = _short_side_scales(canvas)

    if path == "diagonal":
        x = margin + t * span
        y = 1.0 - margin - t * span
        return (
            _clamp01(x + jitter_a * _PATH_JITTER * scale_x),
            _clamp01(y + jitter_b * _PATH_JITTER * scale_y),
        )
    if path == "wave":
        x = margin + t * span
        y = 0.5 + (
            math.sin(t * math.pi * 2.0) * _PATH_WAVE_AMPLITUDE
            + jitter_b * _PATH_JITTER
        ) * scale_y
        return _clamp01(x), _clamp01(y)
    if path == "top_to_bottom":
        x = 0.5 + jitter_a * _PATH_SPREAD * scale_x
        y = margin + t * span
        return _clamp01(x), _clamp01(y)
    if path == "left_to_right":
        x = margin + t * span
        y = 0.5 + jitter_b * _PATH_SPREAD * scale_y
        return _clamp01(x), _clamp01(y)
    if path == "right_half":
        x = 0.56 + _hash01(i, seed, "x") * (0.44 - margin)
        y = margin + _hash01(i, seed, "y") * span
        return _clamp01(x), _clamp01(y)
    return _scatter_pos(i, seed, margin)


def _density_radius(density: str, preserve_space: bool) -> float:
    base = {
        "low": 0.035,
        "medium": 0.060,
        "high": 0.085,
        "none": 0.045,
    }.get(density, 0.045)
    return base * (0.85 if preserve_space else 1.0)


def _clustered_pos(
    i: int,
    n: int,
    seed: int,
    margin: float,
    path: str,
    *,
    cluster_count: int,
    density: str,
    preserve_space: bool,
    rhythm_spacing: str = "none",
    canvas: CanvasSize | None = None,
) -> tuple[float, float]:
    """大数量の配置を、均一散布ではなく複数のまとまりとして決定的に配置する。

    クラスタ内部を円周状に並べると、異なる絵に同じ輪状の記号が現れやすい。
    そのため、内部配置はパス方向を持つ短い帯として広げる。

    engine 32: the band is a shape, so it goes on the short side. Where the
    cluster sits is not, so it does not -- and `canvas` is deliberately not
    forwarded to the `_path_pos` call below, which resolves the cluster's
    centre. Forwarding it there would level the centres too, and "the middle
    cluster is above the others" would stop meaning the same thing on paper of
    a different shape (R3, author 2026-08-12).
    """
    cluster_count = max(1, min(cluster_count, n))
    cluster_index = i % cluster_count
    local_index = i // cluster_count
    local_total = max(1, math.ceil(n / cluster_count))
    center_margin = max(margin, 0.20 if preserve_space else margin)
    if path == "none":
        cx, cy = _scatter_pos(cluster_index, seed ^ 0xC1A57, center_margin)
    else:
        cx, cy = _path_pos(
            cluster_index,
            cluster_count,
            seed ^ 0xC1A57,
            center_margin,
            path,
            rhythm_spacing,
        )

    if path == "diagonal":
        axis_angle = -math.pi / 4
    elif path in ("top_to_bottom",):
        axis_angle = math.pi / 2
    elif path in ("left_to_right", "right_half", "wave"):
        axis_angle = 0.0
    else:
        axis_angle = _hash01(cluster_index, seed, "cluster-axis") * math.tau
    tx, ty = math.cos(axis_angle), math.sin(axis_angle)
    nx, ny = -ty, tx
    local_t = (local_index + 0.5) / local_total
    if rhythm_spacing != "none" and local_total > 1:
        local_t = _rhythm_t(
            local_index, local_total, seed ^ cluster_index, rhythm_spacing
        )
    centered = (local_t - 0.5) * 2.0
    radius = _density_radius(density, preserve_space)
    long_span = radius * (1.45 + _hash01(cluster_index, seed, "cluster-long") * 0.95)
    cross_span = radius * (0.28 + _hash01(cluster_index, seed, "cluster-cross") * 0.32)
    along = (
        centered * long_span + (_hash01(i, seed, "cluster-along") - 0.5) * radius * 0.20
    )
    cross = (
        (_hash01(i, seed, "cluster-cross-jitter") - 0.5)
        * cross_span
        * (1.25 - 0.45 * abs(centered))
    )
    bend = (
        math.sin(local_t * math.pi)
        * (_hash01(cluster_index, seed, "cluster-bend") - 0.5)
        * radius
        * 0.55
    )
    # The band is built in a rotated frame, so the offset is rotated first and
    # put on the short side second. Scaling `along` and `cross` before the
    # rotation would turn the rotation itself into a shear on a canvas that is
    # not square, and the band would come out neither its own shape nor the
    # canvas's.
    off_x = tx * along + nx * (cross + bend)
    off_y = ty * along + ny * (cross + bend)
    scale_x, scale_y = _short_side_scales(canvas)
    x = cx + off_x * scale_x
    y = cy + off_y * scale_y
    return _clamp01(x), _clamp01(y)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _ensure_line_coords(ins: Instruction) -> Instruction:
    """arrangement 付き line で from_/to が省略されたとき layout から補完する。

    horizontal → 縦線 (x=0.5 を後で _shift が動かす)
    vertical   → 横線
    scatter/radial/その他 → 縦線
    """
    if ins.primitive != "line" or (ins.from_ is not None and ins.to is not None):
        return ins
    arr = ins.arrangement
    if arr is not None and arr.layout == "vertical":
        default_from: list[float] = [0.0, 0.5]
        default_to: list[float] = [1.0, 0.5]
    else:
        default_from = [0.5, 0.0]
        default_to = [0.5, 1.0]
    data = ins.model_dump(by_alias=True)
    data["from"] = default_from
    data["to"] = default_to
    return Instruction.model_validate(data)


def _anchor(ins: Instruction) -> tuple[float, float]:
    """図形の論理的な中心座標を返す。"""
    if ins.primitive == "line" and ins.from_ and ins.to:
        return ((ins.from_[0] + ins.to[0]) / 2, (ins.from_[1] + ins.to[1]) / 2)
    if (
        ins.primitive in ("circle", "ellipse", "arc", "polygon", "cloudform")
        and ins.center
    ):
        return ins.center
    if ins.primitive in ("square", "triangle") and ins.position and ins.size:
        return (ins.position[0] + ins.size[0] / 2, ins.position[1] + ins.size[1] / 2)
    return (0.5, 0.5)


def _shift(ins: Instruction, dx: float, dy: float) -> Instruction:
    """ins を (dx, dy) だけ平行移動した新しい Instruction を返す。arrangement は除去。"""
    data = ins.model_dump(by_alias=True)
    arr = ins.arrangement
    data.pop("arrangement", None)
    if arr is not None:
        notes: list[str] = []
        if arr.density != "none":
            notes.append(f"density={arr.density}")
        if arr.fade != "none":
            notes.append(f"fade={arr.fade}")
        if arr.preserve_space:
            notes.append("preserve_space")
        if notes:
            hint = data.get("color_hint")
            effect_note = "; ".join(notes)
            data["color_hint"] = f"{hint}; {effect_note}" if hint else effect_note
    if ins.primitive == "line" and ins.from_ and ins.to:
        data["from"] = [ins.from_[0] + dx, ins.from_[1] + dy]
        data["to"] = [ins.to[0] + dx, ins.to[1] + dy]
    elif (
        ins.primitive in ("circle", "ellipse", "arc", "polygon", "cloudform")
        and ins.center
    ):
        data["center"] = [ins.center[0] + dx, ins.center[1] + dy]
    elif ins.primitive in ("square", "triangle") and ins.position:
        data["position"] = [ins.position[0] + dx, ins.position[1] + dy]
    return Instruction.model_validate(data)


def _apply_color_cycle(items: list[Instruction], cycle: list) -> list[Instruction]:
    if not cycle:
        return items
    result = []
    for i, single in enumerate(items):
        data = single.model_dump(by_alias=True)
        data["color"] = cycle[i % len(cycle)]
        data["color_hint"] = _render_effect_hint(single.color_hint)
        result.append(Instruction.model_validate(data))
    return result


def _strip_performance_fields(ins: Instruction) -> Instruction:
    data = ins.model_dump(by_alias=True)
    data.pop("at", None)
    data.pop("relation", None)
    return Instruction.model_validate(data)


def _move_anchor_to(
    ins: Instruction, target: tuple[float, float], *, keep_relation: bool = False
) -> Instruction:
    ax, ay = _anchor(ins)
    data = ins.model_dump(by_alias=True)
    data.pop("at", None)
    # 関係解決後の移動では relation は消費済み。region 配置 (at) 経路では保存し、
    # 後段の _resolve_relation に委ねる (v1.93: region が relation を食う競合の修正)。
    if not keep_relation:
        data.pop("relation", None)
    dx = target[0] - ax
    dy = target[1] - ay
    if ins.primitive == "line" and ins.from_ and ins.to:
        data["from"] = [_clamp01(ins.from_[0] + dx), _clamp01(ins.from_[1] + dy)]
        data["to"] = [_clamp01(ins.to[0] + dx), _clamp01(ins.to[1] + dy)]
    elif ins.primitive in ("circle", "ellipse", "arc", "polygon", "cloudform"):
        if ins.center:
            data["center"] = [
                _clamp01(ins.center[0] + dx),
                _clamp01(ins.center[1] + dy),
            ]
        else:
            data["center"] = [_clamp01(target[0]), _clamp01(target[1])]
    elif ins.primitive in ("square", "triangle"):
        if ins.position:
            data["position"] = [
                _clamp01(ins.position[0] + dx),
                _clamp01(ins.position[1] + dy),
            ]
        else:
            size = ins.size or (0.2, 0.2)
            data["size"] = list(size)
            data["position"] = [
                _clamp01(target[0] - size[0] / 2),
                _clamp01(target[1] - size[1] / 2),
            ]
    return Instruction.model_validate(data)


def _short_side_scales(canvas: CanvasSize | None) -> tuple[float, float]:
    """Per-axis factors that put a normalized extent on the short edge.

    Engine 30 did this for a mark's own size (`_size_px`); engine 31 does it for
    what the arrangement layer spreads -- the ring and the region -- and engine
    32 for the cluster's band and a path's cross-axis spread. A normalized
    extent becomes pixels
    through `canvas.width` on x and `canvas.height` on y, so on a non-square
    canvas the same number means a different number of pixels per axis. Scaling
    each axis by `unit / that axis` makes both come out `unit` pixels, which is
    what keeps a ring round and a square region square.
    """
    if canvas is None:
        return (1.0, 1.0)
    return (canvas.unit / canvas.width, canvas.unit / canvas.height)


def _region_in_short_side_units(
    region: Sequence[float], canvas: CanvasSize | None
) -> tuple[float, float, float, float]:
    """R3: the region's centre stays put, its extent goes to short-side units.

    The centre is deliberately left proportional -- "upper right" is the upper
    right of any canvas -- so only the half-extents are scaled.
    """
    x0, y0, x1, y1 = region
    sx, sy = _short_side_scales(canvas)
    if sx == 1.0 and sy == 1.0:
        # A square canvas has to come out byte-identical, and centre +/-
        # half-extent does not round-trip in floating point: for
        # [0.6, 0.18, 0.82, 0.4] it moves y0 by 2.78e-17, enough to cross a
        # rounding boundary downstream and change a frozen square case.
        return (x0, y0, x1, y1)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
    return (cx - hx * sx, cy - hy * sy, cx + hx * sx, cy + hy * sy)


def _resolve_at_region(
    ins: Instruction, seed: int, index: int, canvas: CanvasSize | None = None
) -> Instruction:
    if ins.at is None:
        return ins
    x0, y0, x1, y1 = _region_in_short_side_units(ins.at.region, canvas)
    x = x0 + (x1 - x0) * _hash01(index, seed, "region-x")
    y = y0 + (y1 - y0) * _hash01(index, seed, "region-y")
    return _move_anchor_to(ins, (x, y), keep_relation=True)


def _bbox_for_instruction(
    ins: Instruction, performance_seed: int | None = None, instruction_index: int = 0
) -> tuple[float, float, float, float] | None:
    """Return the performed outline bbox in canvas coordinates.

    Relation resolution observes the same rotation that SVG rendering later
    applies around the instruction anchor.
    """
    rotation = ins.rotation or 0.0

    def rotated_bbox(
        points: list[tuple[float, float]],
    ) -> tuple[float, float, float, float]:
        anchor = _anchor(ins)
        performed = [
            _rotate_screen_point(point, anchor, rotation) for point in points
        ]
        xs = [point[0] for point in performed]
        ys = [point[1] for point in performed]
        return min(xs), min(ys), max(xs), max(ys)

    if ins.primitive == "line" and ins.from_ and ins.to:
        return rotated_bbox([ins.from_, ins.to])
    if (
        ins.primitive in ("circle", "arc", "polygon")
        and ins.center
        and ins.radius is not None
    ):
        return (
            ins.center[0] - ins.radius,
            ins.center[1] - ins.radius,
            ins.center[0] + ins.radius,
            ins.center[1] + ins.radius,
        )
    if ins.primitive == "ellipse" and ins.center and ins.size:
        rx, ry = ins.size[0] / 2, ins.size[1] / 2
        angle = math.radians(rotation)
        half_width = math.hypot(rx * math.cos(angle), ry * math.sin(angle))
        half_height = math.hypot(rx * math.sin(angle), ry * math.cos(angle))
        return (
            ins.center[0] - half_width,
            ins.center[1] - half_height,
            ins.center[0] + half_width,
            ins.center[1] + half_height,
        )
    if ins.primitive == "cloudform" and ins.center and ins.size:
        contour = generate_cloudform_contour(
            ins.center,
            ins.size,
            performance_seed=_seed_for_instruction(ins, performance_seed),
            instruction_index=instruction_index,
            mark_index=0,
            variation=ins.variation,
            weight=ins.weight,
        )
        return rotated_bbox(list(contour.points))
    if ins.primitive in ("square", "triangle") and ins.position and ins.size:
        x, y = ins.position
        width, height = ins.size
        if ins.primitive == "triangle":
            return rotated_bbox(
                [(x + width / 2, y), (x, y + height), (x + width, y + height)]
            )
        return rotated_bbox(
            [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
        )
    return None


def _bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _bbox_radius(bbox: tuple[float, float, float, float]) -> float:
    return max(0.015, math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]) / 2)


def _relation_gap(seed: int, index: int, gap: str) -> float:
    ranges = {
        "narrow": (0.02, 0.05),
        "medium": (0.06, 0.12),
        "wide": (0.15, 0.30),
    }
    lo, hi = ranges.get(gap, ranges["medium"])
    return lo + (hi - lo) * _hash01(index, seed, "relation-gap")


def _rotate_screen_point(
    point: tuple[float, float],
    center: tuple[float, float],
    degrees: float,
) -> tuple[float, float]:
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    dx, dy = point[0] - center[0], point[1] - center[1]
    return (
        center[0] + dx * cosine - dy * sine,
        center[1] + dx * sine + dy * cosine,
    )


def _rotate_screen_vector(
    vector: tuple[float, float], degrees: float
) -> tuple[float, float]:
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        vector[0] * cosine - vector[1] * sine,
        vector[0] * sine + vector[1] * cosine,
    )


def _canvas_endpoint_geometry(
    ins: Instruction,
    seed: int,
    index: int,
) -> tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
] | None:
    """Return start/end points and their forward tangents in normalized space."""
    rotation = ins.rotation or 0.0
    if ins.primitive == "line" and ins.from_ and ins.to:
        center = _anchor(ins)
        start = _rotate_screen_point(ins.from_, center, rotation)
        end = _rotate_screen_point(ins.to, center, rotation)
        tangent = (end[0] - start[0], end[1] - start[1])
        if math.hypot(*tangent) < 1e-9:
            return None
        return start, end, tangent, tangent
    if (
        ins.primitive == "arc"
        and ins.center
        and ins.radius is not None
        and ins.angle_start is not None
        and ins.angle_end is not None
    ):
        start_angle = math.radians(ins.angle_start)
        end_angle = math.radians(ins.angle_end)
        start = arc_point(ins.center, ins.radius, ins.angle_start)
        end = arc_point(ins.center, ins.radius, ins.angle_end)
        direction = 1.0 if ins.angle_end > ins.angle_start else -1.0
        start_tangent = (
            -math.sin(start_angle) * direction,
            -math.cos(start_angle) * direction,
        )
        end_tangent = (
            -math.sin(end_angle) * direction,
            -math.cos(end_angle) * direction,
        )
        return (
            _rotate_screen_point(start, ins.center, rotation),
            _rotate_screen_point(end, ins.center, rotation),
            _rotate_screen_vector(start_tangent, rotation),
            _rotate_screen_vector(end_tangent, rotation),
        )
    if ins.primitive == "cloudform" and ins.center and ins.size:
        contour = generate_cloudform_contour(
            ins.center,
            ins.size,
            performance_seed=_seed_for_instruction(ins, seed),
            instruction_index=index,
            mark_index=0,
            variation=ins.variation,
            weight=ins.weight,
        )
        if len(contour.points) < 3:
            return None
        seam = _rotate_screen_point(contour.points[0], ins.center, rotation)
        after = _rotate_screen_point(contour.points[1], ins.center, rotation)
        before = _rotate_screen_point(contour.points[-1], ins.center, rotation)
        return (
            seam,
            seam,
            (after[0] - seam[0], after[1] - seam[1]),
            (seam[0] - before[0], seam[1] - before[1]),
        )
    return None


def _performed_arc_sagitta(ins: Instruction, seed: int, index: int) -> float | None:
    if (
        ins.primitive != "arc"
        or ins.center is None
        or ins.radius is None
        or ins.angle_start is None
        or ins.angle_end is None
    ):
        return None
    endpoints = _canvas_endpoint_geometry(ins, seed, index)
    if endpoints is None:
        return None
    start, end = endpoints[0], endpoints[1]
    delta = minor_arc_delta(ins.angle_start, ins.angle_end)
    local_apex = arc_point(
        ins.center,
        ins.radius,
        ins.angle_start + delta / 2.0,
    )
    apex = _rotate_screen_point(local_apex, ins.center, ins.rotation or 0.0)
    chord = (end[0] - start[0], end[1] - start[1])
    length = math.hypot(*chord)
    if length <= 1e-12:
        return None
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    normal = (-chord[1] / length, chord[0] / length)
    return (apex[0] - midpoint[0]) * normal[0] + (
        apex[1] - midpoint[1]
    ) * normal[1]


def _dropped_relation(ins: Instruction, index: int, reason: str) -> Instruction:
    """§14.4: 解決不能な relation は修復せず drop し、警告を記録する。"""
    logger.warning(
        "relation dropped at performance: index=%d type=%s reason=%s",
        index,
        ins.relation.type if ins.relation else None,
        reason,
    )
    return _strip_performance_fields(ins)


def _resolve_touching_relation(
    ins: Instruction,
    previous: list[Instruction],
    seed: int,
    index: int,
) -> Instruction:
    if ins.primitive not in {"line", "arc"} or not previous:
        return _dropped_relation(ins, index, "touching requires a line/arc with a prior")
    prior = previous[-1]
    if prior.primitive not in {"line", "arc"}:
        return _dropped_relation(ins, index, "prior is not a line/arc")
    prior_geometry = _canvas_endpoint_geometry(prior, seed, index - 1)
    if prior_geometry is None:
        return _dropped_relation(ins, index, "prior has no endpoint geometry")
    start, end = prior_geometry[0], prior_geometry[1]
    clean = _strip_performance_fields(ins)
    data = clean.model_dump(by_alias=True)
    data["rotation"] = None

    if ins.primitive == "line":
        data["from"] = list(start)
        data["to"] = list(end)
        return Instruction.model_validate(data)

    own_sagitta = _performed_arc_sagitta(ins, seed, index)
    if own_sagitta is None or abs(own_sagitta) <= 1e-12:
        return _dropped_relation(ins, index, "degenerate own sagitta")
    sagitta = own_sagitta
    if prior.primitive == "arc":
        prior_sagitta = _performed_arc_sagitta(prior, seed, index - 1)
        if prior_sagitta is None or abs(prior_sagitta) <= 1e-12:
            return _dropped_relation(ins, index, "degenerate prior sagitta")
        sagitta = -math.copysign(abs(own_sagitta), prior_sagitta)
    try:
        geometry = arc_from_endpoints_and_sagitta(start, end, sagitta)
    except ValueError as exc:
        return _dropped_relation(ins, index, f"minor-arc reconstruction failed: {exc}")
    data["center"] = list(geometry.center)
    data["radius"] = geometry.radius
    data["angle_start"] = geometry.angle_start
    data["angle_end"] = geometry.angle_end
    return Instruction.model_validate(data)


def _resolve_relation(
    ins: Instruction, previous: list[Instruction], seed: int, index: int
) -> Instruction:
    rel = ins.relation
    if rel is None:
        return _strip_performance_fields(ins)
    if rel.type == "touching":
        return _resolve_touching_relation(ins, previous, seed, index)
    if rel.type == "between" and len(previous) < 2:
        return _dropped_relation(ins, index, "between requires two priors")
    if rel.type != "between" and not previous:
        return _dropped_relation(ins, index, "no prior instruction")
    prev_bbox = (
        _bbox_for_instruction(previous[-1], seed, index - 1) if previous else None
    )
    if prev_bbox is None:
        return _dropped_relation(ins, index, "prior has no performed bbox")
    prev_center = _bbox_center(prev_bbox)
    prev_radius = _bbox_radius(prev_bbox)
    gap = _relation_gap(seed, index, rel.gap)

    if rel.type == "between":
        other_bbox = _bbox_for_instruction(previous[-2], seed, index - 2)
        if other_bbox is None:
            return _strip_performance_fields(ins)
        other_center = _bbox_center(other_bbox)
        jitter = 0.08 * (_hash01(index, seed, "between-jitter") - 0.5)
        target = (
            _clamp01((prev_center[0] + other_center[0]) / 2 + jitter),
            _clamp01((prev_center[1] + other_center[1]) / 2 - jitter),
        )
    elif rel.type == "along":
        if previous[-1].primitive == "line" and previous[-1].from_ and previous[-1].to:
            line_geometry = _canvas_endpoint_geometry(previous[-1], seed, index - 1)
            if line_geometry is None:
                return _strip_performance_fields(ins)
            line_start, line_end = line_geometry[0], line_geometry[1]
            t = 0.18 + 0.64 * _hash01(index, seed, "along-t")
            x, y = _point_on_line(line_start, line_end, t)
            ox, oy = _line_perp_offsets(line_start, line_end, gap)
            side = -1.0 if _hash01(index, seed, "along-side") < 0.5 else 1.0
            target = (_clamp01(x + ox * side), _clamp01(y + oy * side))
        elif (
            previous[-1].primitive == "cloudform"
            and previous[-1].center
            and previous[-1].size
        ):
            contour = generate_cloudform_contour(
                previous[-1].center,
                previous[-1].size,
                performance_seed=_seed_for_instruction(previous[-1], seed),
                instruction_index=index - 1,
                mark_index=0,
                variation=previous[-1].variation,
                weight=previous[-1].weight,
            )
            point_index = int(
                _hash01(index, seed, "along-cloudform") * len(contour.points)
            )
            px, py = _rotate_screen_point(
                contour.points[point_index % len(contour.points)],
                previous[-1].center,
                previous[-1].rotation or 0.0,
            )
            dx, dy = px - prev_center[0], py - prev_center[1]
            distance = max(math.hypot(dx, dy), 1e-9)
            target = (
                _clamp01(px + dx / distance * gap),
                _clamp01(py + dy / distance * gap),
            )
        else:
            angle = math.tau * _hash01(index, seed, "along-angle")
            target = (
                _clamp01(prev_center[0] + math.cos(angle) * (prev_radius + gap)),
                _clamp01(prev_center[1] + math.sin(angle) * (prev_radius + gap)),
            )
    elif rel.type == "cutting":
        target = prev_center
        if ins.primitive == "line":
            angle = math.tau * _hash01(index, seed, "cut-angle")
            length = 0.28 + 0.18 * _hash01(index, seed, "cut-length")
            data = ins.model_dump(by_alias=True)
            data.pop("relation", None)
            data.pop("at", None)
            data["from"] = [
                _clamp01(target[0] - math.cos(angle) * length / 2),
                _clamp01(target[1] - math.sin(angle) * length / 2),
            ]
            data["to"] = [
                _clamp01(target[0] + math.cos(angle) * length / 2),
                _clamp01(target[1] + math.sin(angle) * length / 2),
            ]
            return Instruction.model_validate(data)
    else:
        own_bbox = _bbox_for_instruction(ins, seed, index)
        own_radius = _bbox_radius(own_bbox) if own_bbox is not None else 0.0
        distance = prev_radius + own_radius + gap
        angle = math.tau * _hash01(index, seed, "not-touching-angle")
        target = (
            _clamp01(prev_center[0] + math.cos(angle) * distance),
            _clamp01(prev_center[1] + math.sin(angle) * distance),
        )
    return _move_anchor_to(ins, target)


def _instruction_extent(ins: Instruction) -> float:
    """One scalar used to carry an arrangement's member scale to its whole unit."""
    if ins.radius is not None:
        return max(abs(ins.radius), 1e-9)
    if ins.size is not None:
        return max(math.hypot(*ins.size), 1e-9)
    if ins.from_ is not None and ins.to is not None:
        return max(math.dist(ins.from_, ins.to), 1e-9)
    return 1.0


def _scale_instruction(ins: Instruction, scale: float) -> Instruction:
    """Scale one instruction around its own anchor without consuming relation."""
    if abs(scale - 1.0) < 1e-12:
        return ins
    data = ins.model_dump(by_alias=True)
    anchor = _anchor(ins)
    if ins.from_ is not None and ins.to is not None:
        data["from"] = [
            anchor[0] + (ins.from_[0] - anchor[0]) * scale,
            anchor[1] + (ins.from_[1] - anchor[1]) * scale,
        ]
        data["to"] = [
            anchor[0] + (ins.to[0] - anchor[0]) * scale,
            anchor[1] + (ins.to[1] - anchor[1]) * scale,
        ]
    if ins.radius is not None:
        data["radius"] = ins.radius * scale
    if ins.size is not None:
        data["size"] = [ins.size[0] * scale, ins.size[1] * scale]
    return Instruction.model_validate(data)


def _composite_member_copy(
    member: Instruction,
    *,
    source_anchor: tuple[float, float],
    target_head: Instruction,
    rotation_delta: float,
    scale: float,
    color: str | None,
) -> Instruction:
    """Carry one member through the transform chosen for its composite head."""
    scaled = _scale_instruction(member, scale)
    member_anchor = _anchor(scaled)
    dx = member_anchor[0] - source_anchor[0]
    dy = member_anchor[1] - source_anchor[1]
    radians = math.radians(rotation_delta)
    rotated = (
        dx * math.cos(radians) - dy * math.sin(radians),
        dx * math.sin(radians) + dy * math.cos(radians),
    )
    target_anchor = _anchor(target_head)
    moved = _move_anchor_to(
        scaled,
        (target_anchor[0] + rotated[0], target_anchor[1] + rotated[1]),
        keep_relation=True,
    )
    data = moved.model_dump(by_alias=True)
    data.pop("arrangement", None)
    if rotation_delta:
        data["rotation"] = (member.rotation or 0.0) + rotation_delta
    if color is not None:
        data["color"] = color
    return Instruction.model_validate(data)


def _expand_composite_groups(
    score: Score,
    *,
    placement_seed: int | None,
    performance_seed: int | None,
    canvas: CanvasSize | None,
) -> Score:
    """Expand each contiguous composite as copies of one ordered instruction unit."""
    expanded: list[Instruction] = []
    index = 0
    while index < len(score.instructions):
        head = score.instructions[index]
        arrangement = head.arrangement
        group_size = arrangement.group_size if arrangement is not None else 1
        if arrangement is None or group_size == 1:
            expanded.append(head)
            index += 1
            continue
        members = score.instructions[index : index + group_size]
        prepared_head = _ensure_line_coords(head)
        if performance_seed is not None:
            prepared_head = _resolve_at_region(
                prepared_head, int(performance_seed), index, canvas
            )
        copies = _expand_arrangement(
            prepared_head,
            placement_seed,
            canvas,
            performance_seed=performance_seed,
        )
        source_anchor = _anchor(prepared_head)
        source_rotation = prepared_head.rotation or 0.0
        source_extent = _instruction_extent(prepared_head)
        cycle = list(arrangement.color_cycle)
        for copy_head in copies:
            expanded.append(copy_head)
            rotation_delta = (copy_head.rotation or 0.0) - source_rotation
            scale = _instruction_extent(copy_head) / source_extent
            color = copy_head.color if cycle else None
            for member in members[1:]:
                expanded.append(
                    _composite_member_copy(
                        member,
                        source_anchor=source_anchor,
                        target_head=copy_head,
                        rotation_delta=rotation_delta,
                        scale=scale,
                        color=color,
                    )
                )
        index += group_size
    data = score.model_dump(by_alias=True)
    data["instructions"] = [item.model_dump(by_alias=True) for item in expanded]
    return Score.model_validate(data)


def _resolve_performance_score(
    score: Score,
    performance_seed: int | None,
    canvas: CanvasSize | None = None,
    *,
    composition_seed: int | None = None,
) -> Score:
    placement_seed = (
        composition_seed if composition_seed is not None else performance_seed
    )
    score = _expand_composite_groups(
        score,
        placement_seed=placement_seed,
        performance_seed=performance_seed,
        canvas=canvas,
    )
    if performance_seed is None:
        return score
    resolved: list[Instruction] = []
    seed = int(performance_seed)
    for index, original in enumerate(score.instructions):
        ins = _ensure_line_coords(original)
        if ins.arrangement and ins.arrangement.layout == "grid":
            if ins.relation is not None:
                logger.warning(
                    "relation dropped at performance: index=%d type=%s reason=grid layout",
                    index,
                    ins.relation.type,
                )
            data = ins.model_dump(by_alias=True)
            data.pop("relation", None)
            ins = Instruction.model_validate(data)
        else:
            ins = _resolve_at_region(ins, seed, index, canvas)
            ins = _resolve_relation(ins, resolved, seed, index)
        resolved.append(ins)
    data = score.model_dump(by_alias=True)
    data["instructions"] = [ins.model_dump(by_alias=True) for ins in resolved]
    return Score.model_validate(data)


def _render_effect_hint(color_hint: str | None) -> str | None:
    """color_cycle 時も、色選択ではなく描画効果に関わるヒントだけは残す。"""
    if not color_hint:
        return None
    hint = _norm_label(color_hint)
    effect_tokens = (
        "membrane",
        "haze",
        "fog",
        "mist",
        "atmosphere",
        "膜",
        "霞",
        "霧",
        "靄",
        "soft light",
        "柔らかな光",
        "陽光",
        "日差し",
        "scent",
        "fragrance",
        "香り",
        "匂",
        "waiting buds",
        "開花を待つ蕾",
        "蕾",
        "つぼみ",
        "five-sense",
        "五感",
        "fade directional",
        "fade=directional",
        "fade outward",
        "fade=outward",
        "reflection",
        "反射",
        "映り",
    )
    kept = [token for token in effect_tokens if token in hint]
    return "; ".join(kept) if kept else None


# engine 24: `fade` declares how a group falls off, so each member carries its
# own ceiling instead of one constant for the whole group. The pairs are the
# near and the far end of the ramp (author ruling A-1 = F1); the fill keeps the
# ratio the engine-23 constants had (0.22/0.40 outward, 0.30/0.48 directional).
_FADE_NEAR_FAR: dict[str, tuple[float, float]] = {
    "outward": (0.62, 0.18),
    "directional": (0.70, 0.26),
}
_FADE_FILL_RATIO: dict[str, float] = {"outward": 0.55, "directional": 0.625}
# A group whose members are all the same distance from the centre is not an
# "outward" fade at all: a ring is equidistant by construction, and so is a pair.
_FADE_SPAN_EPS = 1e-9
_FADE_LEVEL_RE = re.compile(r"fade_level=(\d+(?:\.\d+)?)")
_FADE_LEVEL_TAG_RE = re.compile(r"(?:;\s*)?fade_level=\d+(?:\.\d+)?")


def _fade_levels(
    items: list[Instruction],
    arr: Arrangement,
    *,
    center: tuple[float, float] | None = None,
) -> list[float] | None:
    """One opacity ceiling per member, or None when the group cannot fade.

    `outward` reads the distance from the group's centre: the stated
    `arrangement.center` when there is one, the centre the layout laid the group
    around when the layout has one of its own, and the centroid of the expanded
    anchors otherwise. `directional` reads the expansion order, which is the
    order the path lays the members down in.

    A ring passes its own centre because the centroid is not it: `_rhythm_t`
    spans 0 to 1 inclusive, so the first mark is drawn twice and pulls the mean
    off the axis by radius/count. Measured from there the ring is not
    equidistant, and it would fade -- once around itself, which is the pattern
    the degenerate rule exists to prevent.
    """
    near_far = _FADE_NEAR_FAR.get(arr.fade)
    if near_far is None or len(items) < 2:
        return None
    near, far = near_far
    count = len(items)
    if arr.fade == "directional":
        ratios = [index / (count - 1) for index in range(count)]
    else:
        anchors = [_anchor(item) for item in items]
        if arr.center is not None:
            cx, cy = arr.center
        elif center is not None:
            cx, cy = center
        else:
            cx = sum(anchor[0] for anchor in anchors) / count
            cy = sum(anchor[1] for anchor in anchors) / count
        distances = [math.hypot(x - cx, y - cy) for x, y in anchors]
        span = max(distances) - min(distances)
        # Ranking an equidistant group by index would draw a gradient running
        # once around the ring -- a pattern the description never states.
        if span < _FADE_SPAN_EPS:
            return None
        nearest = min(distances)
        ratios = [(distance - nearest) / span for distance in distances]
    return [near + (far - near) * ratio for ratio in ratios]


def _apply_fade_levels(
    items: list[Instruction],
    arr: Arrangement,
    *,
    center: tuple[float, float] | None = None,
) -> list[Instruction]:
    """Write each member's ceiling onto its `color_hint`.

    `color_hint` is the carriage because `Instruction` has no opacity field and
    `fade=<mode>` already travels there. It is outside `_SEED_INSTRUCTION_FIELDS`,
    so the tag moves no performance seed and the hand stays byte-identical.
    """
    levels = _fade_levels(items, arr, center=center)
    if levels is None:
        return items
    result: list[Instruction] = []
    for item, level in zip(items, levels):
        data = item.model_dump(by_alias=True)
        hint = data.get("color_hint")
        tag = f"fade_level={level:.4f}"
        data["color_hint"] = f"{hint}; {tag}" if hint else tag
        result.append(Instruction.model_validate(data))
    return result


def _scale_member(ins: Instruction, k: float) -> Instruction:
    """Scale one member about its own `_anchor` by `k`, keeping the aspect.

    Every branch here has to leave `_anchor(ins)` where it was: the group is
    placed afterwards by `_fit_group_to_anchor`, which reads nothing but the
    anchors, so a rule that moved one would hand the placement a different
    group. circle/ellipse/arc/polygon/cloudform are anchored on `center` and
    never touch it; `square`/`triangle` are anchored on the middle of a bbox
    whose corner is `position`, so growing `size` has to pull the corner back
    by half the growth; a line is anchored on its midpoint, so both ends move
    away from the midpoint rather than one end away from the other.
    """
    data = ins.model_dump(by_alias=True)
    if ins.primitive == "line" and ins.from_ and ins.to:
        mx = (ins.from_[0] + ins.to[0]) / 2
        my = (ins.from_[1] + ins.to[1]) / 2
        data["from"] = [mx + (ins.from_[0] - mx) * k, my + (ins.from_[1] - my) * k]
        data["to"] = [mx + (ins.to[0] - mx) * k, my + (ins.to[1] - my) * k]
        return Instruction.model_validate(data)
    if ins.primitive in ("square", "triangle") and ins.position and ins.size:
        w, h = ins.size
        data["size"] = [w * k, h * k]
        data["position"] = [
            ins.position[0] - (w * k - w) / 2,
            ins.position[1] - (h * k - h) / 2,
        ]
        return Instruction.model_validate(data)
    if ins.radius is not None:
        data["radius"] = ins.radius * k
        return Instruction.model_validate(data)
    if ins.size is not None:
        data["size"] = [ins.size[0] * k, ins.size[1] * k]
        return Instruction.model_validate(data)
    return ins


def _turn_member(ins: Instruction, dr: float) -> Instruction:
    """Turn one member by `dr` degrees, leaving every coordinate where it is.

    `rotation` is already an engine quantity and every consumer of it turns the
    shape about `_anchor(ins)` -- relation resolution, the tangents an arc hands
    the mark after it, and `_apply_rotation` in the SVG writer. The anchor a
    member was laid out on is therefore the point it spins around, which is why
    this needs none of the three coordinate corrections `_scale_member` needs.
    """
    data = ins.model_dump(by_alias=True)
    data["rotation"] = (ins.rotation or 0.0) + dr
    return Instruction.model_validate(data)


def _apply_member_sizes(
    items: list[Instruction], arr: Arrangement, member_seed: int | None
) -> list[Instruction]:
    """Give each member of a group its own size (engine 25).

    `Arrangement` is "several of this shape"; it never says "all of them the
    same size". Until here `_shift` rewrote coordinates and nothing else, so
    the N members came out congruent -- the largest signature the engine was
    adding on its own. This takes it back out; nothing is added to the
    vocabulary and no field is added to the schema.

    Three groups keep their exact repetition. `grid` is the tiling whose point
    is that the cells match (author ruling, 2026-08-08); a group of one has
    nobody to differ from; and the machine tools carry a `group_hand` of zero,
    the same rule `fill_hand` follows.
    """
    if member_seed is None or arr.layout == "grid" or len(items) < 2:
        return items
    hand = GRAMMARS[items[0].weight].group_hand
    if hand <= 0.0:
        return items
    result: list[Instruction] = []
    for i, item in enumerate(items):
        k = 1 + (_hash01(i, member_seed, "member-size") - 0.5) * 2 * hand
        result.append(_scale_member(item, k))
    return result


def _apply_member_rotations(
    items: list[Instruction], arr: Arrangement, member_seed: int | None
) -> list[Instruction]:
    """Give each member of a group its own angle (engine 26).

    The other half of what engine 25 started: an `Arrangement` says "several of
    this shape" and no more says "all of them at the same angle" than it says
    "all of them the same size". The two amplitudes were ruled on as a pair,
    +/-25% and +/-12 degrees (author, 2026-08-08), and the second one arrives
    here. It reads the same `member_seed` as the size with a different salt, so
    the angles come off the performance rather than the composition seed
    (engine 23's split), and it turns each member about its own anchor, so the
    group is placed on exactly the coordinates engine 25 placed it on.

    This exclusion list is longer than the size rule's, and deliberately so.

    A `line` is left alone because there the angle *is* what the mark says:
    tilting the blades of grass tips the grass over (author ruling, 2026-08-08).
    A group that states `rotation` is left alone for the mirror reason -- the
    description has already answered the question. That test is `is not None`
    and not a truthy one: `rotation: 0` is an answer ("do not tilt these"), and
    141 groups in production give exactly that answer.

    A `circle` is left alone because an angle cannot be seen on one. Turning it
    would change no pixel and move the performance seed, which is the worse
    half of both outcomes.

    `grid` (whose point is that the cells match), a group of one, and the
    machine tools carry over unchanged from the size rule; the machines are
    pinned by a `group_rot` of zero, the way `group_hand` and `fill_hand` are.
    """
    if member_seed is None or arr.layout == "grid" or len(items) < 2:
        return items
    stated = items[0]
    if stated.primitive in ("line", "circle") or stated.rotation is not None:
        return items
    spread = GRAMMARS[stated.weight].group_rot
    if spread <= 0.0:
        return items
    result: list[Instruction] = []
    for i, item in enumerate(items):
        dr = (_hash01(i, member_seed, "member-rot") - 0.5) * 2 * spread
        result.append(_turn_member(item, dr))
    return result


def _finish_expanded_group(
    items: list[Instruction],
    arr: Arrangement,
    *,
    center: tuple[float, float] | None = None,
    member_seed: int | None = None,
) -> list[Instruction]:
    """The one exit every layout branch takes: colour cycle, fade, size, angle.

    Order matters. `_apply_color_cycle` rebuilds `color_hint` from the effect
    allowlist, so a level written before it is dropped -- and 43.5% of the
    groups in production state a cycle.

    Size and angle come last and are read by none of the three before them: the
    fade ramp is measured from the anchors and the member count, and neither
    `_scale_member` nor `_turn_member` moves an anchor, so engine 24's ceilings
    arrive unchanged. The two are ordered size-then-angle for the same reason,
    which is to say for no reason that shows: the size rule reads `radius` /
    `size` / the endpoints and the angle rule reads `rotation`, so neither can
    see what the other wrote and swapping them draws the same picture.

    `center` is the centre the layout laid the group around, for the branches
    that have one; see `_fade_levels`.
    """
    return _apply_member_rotations(
        _apply_member_sizes(
            _apply_fade_levels(
                _apply_color_cycle(items, arr.color_cycle), arr, center=center
            ),
            arr,
            member_seed,
        ),
        arr,
        member_seed,
    )


def _fade_level_from_hint(color_hint: str | None) -> float | None:
    """Read a member's ceiling out of the raw hint.

    Read before `_norm_label`: normalisation replaces the dot, so "0.3000"
    reaches the consumer as "0 3000" and the value is gone.
    """
    if not color_hint:
        return None
    match = _FADE_LEVEL_RE.search(color_hint)
    return float(match.group(1)) if match else None


def _strip_fade_level(ins: Instruction) -> Instruction:
    """Drop the engine-24 level tag, keeping `fade=<mode>` itself.

    The surface seed hashes the whole instruction dump, so a per-member tag
    would move the texture of every mark in a fading group.
    """
    hint = ins.color_hint
    if not hint or "fade_level=" not in hint:
        return ins
    stripped = _FADE_LEVEL_TAG_RE.sub("", hint).strip().strip(";").strip()
    data = ins.model_dump(by_alias=True)
    data["color_hint"] = stripped or None
    return Instruction.model_validate(data)


def _expand_arrangement_layout(
    ins: Instruction,
    placement_seed: int | None = None,
    canvas: CanvasSize | None = None,
    *,
    performance_seed: int | None = None,
) -> list[Instruction]:
    """arrangement を展開して N 個の Instruction を返す。

    The two seeds are separate on purpose (engine 25). `placement_seed` decides
    where the members land, which is the composition seed's business since
    engine 23; `performance_seed` decides how big each one is, which belongs to
    the performance. Feeding the size from the placement seed would make the
    drawing's shapes follow the composition seed and undo that split on the day
    it was made.
    """
    arr = ins.arrangement
    assert arr is not None
    ins = _ensure_line_coords(ins)
    # Derived from the instruction as stated, before any member is shifted, so
    # every member of one group is drawn from the same sequence.
    member_seed = _seed_for_instruction(ins, performance_seed)
    if arr.count == 1 and arr.layout != "grid":
        data = ins.model_dump(by_alias=True)
        data.pop("arrangement", None)
        return _finish_expanded_group(
            [Instruction.model_validate(data)], arr, member_seed=member_seed
        )
    n = arr.count
    margin = max(arr.margin, 0.20) if arr.preserve_space else arr.margin
    ax, ay = _anchor(ins)
    seed = _seed_for_instruction(ins, placement_seed)
    cluster_count = arr.cluster_count or 0

    if arr.layout == "grid":
        if ins.at is not None:
            x0, y0, x1, y1 = _region_in_short_side_units(ins.at.region, canvas)
        else:
            x0 = y0 = margin
            x1 = y1 = 1.0 - margin
        region_width = max(x1 - x0, 1e-9)
        region_height = max(y1 - y0, 1e-9)
        rows = arr.rows
        cols = arr.cols
        if rows is not None and cols is not None:
            pass
        elif rows is not None:
            cols = min(64, max(1, math.ceil(n / rows)))
        elif cols is not None:
            rows = min(64, max(1, math.ceil(n / cols)))
        else:
            physical_aspect = region_width / region_height
            if canvas is not None:
                physical_aspect *= canvas.width / canvas.height
            cols = min(64, max(1, math.ceil(math.sqrt(n * physical_aspect))))
            rows = min(64, max(1, math.ceil(n / cols)))
        assert rows is not None and cols is not None
        cell_width = region_width / cols
        cell_height = region_height / rows
        targets: list[tuple[float, float]] = []
        for row in range(rows):
            row_t = _rhythm_t(row, rows, seed ^ 0xA53C, arr.rhythm_spacing)
            cy = y0 + (0.5 + row_t * (rows - 1)) * cell_height
            for col in range(cols):
                col_t = _rhythm_t(col, cols, seed ^ 0xC3A5, arr.rhythm_spacing)
                cx = x0 + (0.5 + col_t * (cols - 1)) * cell_width
                dx = (
                    (_hash01(row * cols + col, seed, "grid-jitter-x") - 0.5)
                    * arr.jitter
                    * cell_width
                )
                dy = (
                    (_hash01(row * cols + col, seed, "grid-jitter-y") - 0.5)
                    * arr.jitter
                    * cell_height
                )
                targets.append(
                    (
                        min(x1, max(x0, cx + dx)),
                        min(y1, max(y0, cy + dy)),
                    )
                )
        result: list[Instruction] = []
        for tx, ty in targets:
            shifted = _shift(ins, tx - ax, ty - ay)
            data = shifted.model_dump(by_alias=True)
            data.pop("at", None)
            data.pop("relation", None)
            result.append(Instruction.model_validate(data))
        return _finish_expanded_group(result, arr, member_seed=member_seed)

    if cluster_count > 0 and arr.layout in ("scatter", "horizontal", "vertical"):
        path = arr.path
        if path == "none" and arr.layout == "horizontal":
            path = "left_to_right"
        elif path == "none" and arr.layout == "vertical":
            path = "top_to_bottom"
        targets = [
            _clustered_pos(
                i,
                n,
                seed,
                margin,
                path,
                cluster_count=cluster_count,
                density=arr.density,
                preserve_space=arr.preserve_space,
                rhythm_spacing=arr.rhythm_spacing,
                canvas=canvas,
            )
            for i in range(n)
        ]
        result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
        return _finish_expanded_group(result, arr, member_seed=member_seed)

    if arr.layout == "horizontal":
        if arr.path != "none":
            targets = [
                _path_pos(i, n, seed, margin, arr.path, arr.rhythm_spacing, canvas)
                for i in range(n)
            ]
            result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
            return _finish_expanded_group(result, arr, member_seed=member_seed)
        span = 1.0 - 2 * margin
        targets = [
            (margin + _rhythm_t(i, n, seed, arr.rhythm_spacing) * span, ay)
            for i in range(n)
        ]
        result = [_shift(ins, tx - ax, 0.0) for tx, _ in targets]
        return _finish_expanded_group(result, arr, member_seed=member_seed)

    if arr.layout == "vertical":
        if arr.path != "none":
            targets = [
                _path_pos(i, n, seed, margin, arr.path, arr.rhythm_spacing, canvas)
                for i in range(n)
            ]
            result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
            return _finish_expanded_group(result, arr, member_seed=member_seed)
        span = 1.0 - 2 * margin
        targets = [
            (ax, margin + _rhythm_t(i, n, seed, arr.rhythm_spacing) * span)
            for i in range(n)
        ]
        result = [_shift(ins, 0.0, ty - ay) for _, ty in targets]
        return _finish_expanded_group(result, arr, member_seed=member_seed)

    if arr.layout == "radial":
        # engine 20: `center` is radial's own rotation centre. When the
        # description does not state one, the ring turns around the declared
        # anchor -- not around the middle of the canvas.
        cx = arr.center[0] if arr.center else ax
        cy = arr.center[1] if arr.center else ay
        r = arr.radius if arr.radius else 0.3
        # engine 31: the stated radius is one length, so it has to buy the same
        # number of pixels on both axes. Written straight, `r` in normalized
        # coordinates becomes `r * width` across and `r * height` down, and the
        # ring came out with the canvas's own aspect (0.19 on the pillar). The
        # radius stays the description's; only its trip to pixels is levelled.
        scale_x, scale_y = _short_side_scales(canvas)
        rx, ry = r * scale_x, r * scale_y
        targets = [
            (
                cx
                + rx
                * math.cos(
                    math.radians(_rhythm_t(i, n, seed, arr.rhythm_spacing) * 360)
                ),
                cy
                - ry
                * math.sin(
                    math.radians(_rhythm_t(i, n, seed, arr.rhythm_spacing) * 360)
                ),
            )
            for i in range(n)
        ]
        result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
        return _finish_expanded_group(result, arr, center=(cx, cy), member_seed=member_seed)

    if arr.layout == "scatter":
        targets = [
            _path_pos(i, n, seed, margin, arr.path, arr.rhythm_spacing, canvas)
            for i in range(n)
        ]
        result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
        return _finish_expanded_group(result, arr, member_seed=member_seed)

    return _finish_expanded_group([ins], arr, member_seed=member_seed)


def _fit_axis_scales(anchor: float, offsets: list[float]) -> tuple[float, float]:
    """Shrink factors for one axis, one per direction (engine 20, R5).

    Each side is shrunk only by what overflows on that side, so the spread away
    from the frame is kept. A similarity shrink would collapse the whole group
    for the sake of the one mark that overflows.
    """
    positive = [offset for offset in offsets if offset > 0]
    negative = [offset for offset in offsets if offset < 0]
    forward = min(1.0, (FRAME_HI - anchor) / max(positive)) if positive else 1.0
    backward = min(1.0, (FRAME_LO - anchor) / min(negative)) if negative else 1.0
    return max(forward, 0.0), max(backward, 0.0)


def _fit_group_to_anchor(
    ins: Instruction, expanded: list[Instruction]
) -> list[Instruction]:
    """Move an expanded group so that it sits on the declared anchor.

    The layout branches decide how the group scatters; this decides where the
    group is. Until engine 19 the second question was answered by the seed
    alone, so 77.8% of the expanded marks never consulted the coordinates the
    description had stated.
    """
    ax, ay = _anchor(ins)
    points = [_anchor(item) for item in expanded]
    cx = sum(point[0] for point in points) / len(points)
    cy = sum(point[1] for point in points) / len(points)
    offsets = [(px - cx, py - cy) for px, py in points]
    x_forward, x_backward = _fit_axis_scales(ax, [dx for dx, _ in offsets])
    y_forward, y_backward = _fit_axis_scales(ay, [dy for _, dy in offsets])
    result: list[Instruction] = []
    for item, (px, py), (dx, dy) in zip(expanded, points, offsets):
        tx = ax + dx * (x_forward if dx > 0 else x_backward)
        ty = ay + dy * (y_forward if dy > 0 else y_backward)
        result.append(_shift(item, tx - px, ty - py))
    return result


# engine 21: the expansion is the only place where a libm result reaches a
# hash. `_seed_for_instruction` hashes the whole instruction dump, so the
# one-ULP gap between macOS libm and glibc (measured: sin/cos disagree for
# 7-10 of 60 arguments) turned into a completely different performance seed and
# moved the drawing by 0.08-0.17px -- which is why the frozen corpus could not
# be reproduced on Linux. Everywhere else a one-ULP difference is absorbed by
# the six decimals the SVG prints; only the hash amplifies it.
ARRANGEMENT_QUANTUM = 9


def _quantise(value: Any) -> Any:
    """Round every float under `value` to `ARRANGEMENT_QUANTUM` decimals."""
    if isinstance(value, float):
        return round(value, ARRANGEMENT_QUANTUM)
    # Coordinate pairs come back as tuples, not lists; a list-only walk
    # quantises nothing at all and does so silently.
    if isinstance(value, (list, tuple)):
        return type(value)(_quantise(item) for item in value)
    if isinstance(value, dict):
        return {key: _quantise(item) for key, item in value.items()}
    return value


def _quantise_instructions(items: list[Instruction]) -> list[Instruction]:
    """Take the platform out of an expanded group.

    1e-9 of a normalised coordinate is 1e-6 px on a 1000px canvas, under the
    precision the SVG prints, so this cannot be seen; the one-ULP noise it
    removes could be, because the seed reads the coordinate exactly.
    """
    return [
        Instruction.model_validate(_quantise(item.model_dump(by_alias=True)))
        for item in items
    ]


def _expand_arrangement(
    ins: Instruction,
    placement_seed: int | None = None,
    canvas: CanvasSize | None = None,
    *,
    performance_seed: int | None = None,
) -> list[Instruction]:
    """Expand an arrangement and place the resulting group on its anchor."""
    expanded = _expand_arrangement_layout(
        ins, placement_seed, canvas, performance_seed=performance_seed
    )
    if not expanded:
        return expanded
    arr = ins.arrangement
    if arr is not None and arr.layout == "grid" and ins.at is not None:
        # The one branch that already reads a stated position: a grid tiles
        # `at.region`, and for that instruction `at` survives performance
        # resolution instead of being folded into the anchor. Fitting here would
        # replace the region the description gave with the shape's own centre,
        # which for a tiling is the coordinate nobody stated.
        return _quantise_instructions(expanded)
    return _quantise_instructions(_fit_group_to_anchor(ins, expanded))


def _norm_label(value: str) -> str:
    return re.sub(r"[\s:_()'\".,/-]+", " ", value.lower()).strip()


def _line_perp_offsets(
    start: tuple[float, float], end: tuple[float, float], amount: float
) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 0.0, 0.0
    return -dy / length * amount, dx / length * amount


def _point_on_line(
    start: tuple[float, float], end: tuple[float, float], t: float
) -> tuple[float, float]:
    return (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)

