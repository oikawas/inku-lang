"""Surface texture domain for the default render engine."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

import svgwrite

from ...cloudform import generate_cloudform_contour, sample_closed_catmull_rom
from ...plugins import CanvasSize
from ...schema import (
    CLOSED_SHAPES,
    Instruction,
    SurfaceSpec,
    fill_is_asked_for,
)
from ...stroke_engine import (
    GRAMMARS,
    Support,
    centerline_normals,
    contour_stroke_path,
    synthesize_along,
)
from .determinism import _hash01, _hash_to_unit, _seed_for_instruction
from .document import _safe_svg_id
from .palette import _resolve_color
from .planning import _strip_fade_level


@dataclass(frozen=True)
class SurfaceMarkStyle:
    """The three read-only mark-policy facts surface rendering consumes."""

    mark_width_px: Callable[[Instruction, CanvasSize], float]
    weight_style: Mapping[str, Mapping[str, str | float]]
    texture_filter_weights: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "weight_style",
            MappingProxyType(
                {
                    weight: MappingProxyType(dict(attributes))
                    for weight, attributes in self.weight_style.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "texture_filter_weights",
            frozenset(self.texture_filter_weights),
        )


_CLOSED_SHAPES = CLOSED_SHAPES


def _px(coord: tuple[float, float], canvas: CanvasSize) -> tuple[float, float]:
    x, y = coord
    return x * canvas.width, y * canvas.height


def _size_px(size: Sequence[float], canvas: CanvasSize) -> tuple[float, float]:
    return size[0] * canvas.unit, size[1] * canvas.unit


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


def _ellipse_perimeter(rx: float, ry: float) -> float:
    a, b = abs(rx), abs(ry)
    if a + b <= 0:
        return 0.0
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def _stroke_sample_count(length_px: float, canvas: CanvasSize) -> int:
    """Surface's frozen engine-40 sampling scale."""
    target = canvas.unit * (1.0 / 49.0)
    if target <= 0:
        return 17
    return max(17, min(129, int(round(length_px / target))))


def _points_center(path: list[tuple[float, float]]) -> tuple[float, float]:
    if not path:
        return (0.0, 0.0)
    return (
        sum(x for x, _ in path) / len(path),
        sum(y for _, y in path) / len(path),
    )


def _uses_hand_stroke(weight: str) -> bool:
    return weight != "rotring" and weight in GRAMMARS


def _grid_step_px(weight: str, canvas: CanvasSize) -> float:
    grammar = GRAMMARS.get(weight)
    if grammar is None or grammar.quantize <= 0:
        return 0.0
    return canvas.unit * grammar.quantize


def _fill_scan_angle(seed: int) -> float:
    return _hash01(0, seed, "fill-angle") * math.pi


def _fill_stroke_seed(seed: int, index: int) -> int:
    """Preserve the engine-40 hatch stroke salt after the module move."""
    digest = hashlib.sha256(f"{seed}:fill-stroke:{index}".encode("utf-8")).digest()
    return struct.unpack("<Q", digest[:8])[0]


def _scanline_segments(
    contour: list[tuple[float, float]],
    angle: float,
    spacing: float,
    seed: int,
    jitter: float = 0.24,
) -> list[tuple[int, tuple[float, float], tuple[float, float]]]:
    ux, uy = math.cos(angle), math.sin(angle)
    nx, ny = -uy, ux
    projections = [x * nx + y * ny for x, y in contour]
    lo, hi = min(projections), max(projections)
    segments: list[tuple[int, tuple[float, float], tuple[float, float]]] = []
    offset = lo + spacing * 0.5
    index = 0
    while offset < hi and index < 4096:
        hits: list[float] = []
        for edge in range(len(contour)):
            ax, ay = contour[edge]
            bx, by = contour[(edge + 1) % len(contour)]
            da = ax * nx + ay * ny - offset
            db = bx * nx + by * ny - offset
            if (da <= 0.0 < db) or (db <= 0.0 < da):
                t = da / (da - db)
                px, py = ax + (bx - ax) * t, ay + (by - ay) * t
                hits.append(px * ux + py * uy)
        hits.sort()
        for pair in range(0, len(hits) - 1, 2):
            s0, s1 = hits[pair], hits[pair + 1]
            segments.append(
                (
                    index,
                    (nx * offset + ux * s0, ny * offset + uy * s0),
                    (nx * offset + ux * s1, ny * offset + uy * s1),
                )
            )
        step = 1.0 + (_hash01(index, seed, "fill-spacing") - 0.5) * jitter
        offset += spacing * step
        index += 1
    return segments


def _line_spans(
    contour: list[tuple[float, float]],
    point: tuple[float, float],
    direction: tuple[float, float],
) -> list[tuple[float, float]]:
    ux, uy = direction
    hits: list[float] = []
    for edge in range(len(contour)):
        ax, ay = contour[edge]
        bx, by = contour[(edge + 1) % len(contour)]
        ex, ey = bx - ax, by - ay
        denom = ux * ey - uy * ex
        if abs(denom) < 1e-12:
            continue
        dx, dy = ax - point[0], ay - point[1]
        t_edge = (dx * uy - dy * ux) / denom
        if not (0.0 <= t_edge < 1.0):
            continue
        hits.append((dx + ex * t_edge) * ux + (dy + ey * t_edge) * uy)
    hits.sort()
    return [(hits[i], hits[i + 1]) for i in range(0, len(hits) - 1, 2)]


def _surface_seed(
    ins: Instruction, ins_idx: int, mark_idx: int, render_seed: int | None
) -> int:
    if ins.surface is not None and ins.surface.seed is not None:
        return int(ins.surface.seed)
    key = (
        _strip_fade_level(ins).model_dump_json(by_alias=True)
        + f":surface:{ins_idx}:{mark_idx}:{render_seed}"
    )
    return struct.unpack("<Q", hashlib.sha256(key.encode("utf-8")).digest()[:8])[0]


def _surface_grain_seed(
    ins: Instruction, ins_idx: int, mark_idx: int, render_seed: int | None
) -> int:
    """Keep grain placement/jitter on the seed axis, not its visual controls."""
    surface = ins.surface
    assert surface is not None and surface.texture == "grain"
    if surface.seed is not None:
        return int(surface.seed)
    stable_surface = surface.model_copy(
        update={"density": 0.5, "scale": 0.5, "opacity": 0.5}
    )
    return _surface_seed(
        ins.model_copy(update={"surface": stable_surface}),
        ins_idx,
        mark_idx,
        render_seed,
    )

def _shape_bbox(
    ins: Instruction, canvas: CanvasSize
) -> tuple[float, float, float, float] | None:
    if ins.primitive == "circle" and ins.center is not None and ins.radius is not None:
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        return cx - r, cy - r, r * 2, r * 2
    if ins.primitive == "ellipse" and ins.center is not None and ins.size is not None:
        cx, cy = _px(ins.center, canvas)
        w, h = _size_px(ins.size, canvas)
        return cx - w / 2, cy - h / 2, w, h
    if ins.primitive == "cloudform" and ins.center is not None and ins.size is not None:
        cx, cy = _px(ins.center, canvas)
        w, h = _size_px(ins.size, canvas)
        return cx - w * 0.56, cy - h * 0.56, w * 1.12, h * 1.12
    if (
        ins.primitive in ("square", "triangle")
        and ins.position is not None
        and ins.size is not None
    ):
        x, y = _px(ins.position, canvas)
        w, h = _size_px(ins.size, canvas)
        return x, y, w, h
    if ins.primitive == "polygon" and ins.center is not None and ins.radius is not None:
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        return cx - r, cy - r, r * 2, r * 2
    return None


def _surface_contour(
    ins: Instruction,
    canvas: CanvasSize,
    *,
    render_seed: int | None,
    ins_idx: int,
    mark_idx: int,
) -> list[tuple[float, float]] | None:
    """surface が従う閉輪郭 (px)。粒も滲みもこの線から引く。

    engine 15 まで surface は `_shape_bbox` の中に一様乱数を撒いており、三角形にも
    雲形にも同じ矩形の散らばりが出ていた (外へはみ出す分を display だけが clipPath
    で隠していた)。ここを輪郭に替えると、粒の位置が図形の形に従い、プロファイル
    による差も消える。輪郭は幾何そのもの (`variation` は通さない)。雲形だけは輪郭の
    生成に演奏 seed が要るので、本体と同じ引数で引き直す。
    """
    if ins.primitive == "circle" and ins.center is not None and ins.radius is not None:
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        return _circle_points(
            cx, cy, r, r, _stroke_sample_count(2 * math.pi * r, canvas)
        )
    if ins.primitive == "ellipse" and ins.center is not None and ins.size is not None:
        cx, cy = _px(ins.center, canvas)
        w, h = _size_px(ins.size, canvas)
        rx, ry = w / 2, h / 2
        return _circle_points(
            cx, cy, rx, ry, _stroke_sample_count(_ellipse_perimeter(rx, ry), canvas)
        )
    if (
        ins.primitive in ("square", "triangle")
        and ins.position is not None
        and ins.size is not None
    ):
        x, y = _px(ins.position, canvas)
        w, h = _size_px(ins.size, canvas)
        if ins.primitive == "square":
            return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return [(x + w / 2, y), (x + w, y + h), (x, y + h)]
    if ins.primitive == "polygon" and ins.center is not None and ins.radius is not None:
        cx, cy = _px(ins.center, canvas)
        return _polygon_points(
            cx, cy, ins.radius * canvas.unit, ins.sides or 5, ins.rotation or 0.0
        )
    if ins.primitive == "cloudform" and ins.center is not None and ins.size is not None:
        cx, cy = _px(ins.center, canvas)
        contour = generate_cloudform_contour(
            (cx, cy),
            _size_px(ins.size, canvas),
            performance_seed=_seed_for_instruction(ins, render_seed),
            instruction_index=ins_idx,
            mark_index=mark_idx,
            variation=ins.variation,
            weight=ins.weight,
        )
        return list(sample_closed_catmull_rom(contour.points))
    return None


def _point_in_polygon(px: float, py: float, contour: list[tuple[float, float]]) -> bool:
    """交差数による内外判定。凹形 (雲形) もそのまま扱える。"""
    inside = False
    count = len(contour)
    for index in range(count):
        ax, ay = contour[index]
        bx, by = contour[(index + 1) % count]
        if (ay > py) != (by > py):
            t = (py - ay) / (by - ay)
            if px < ax + (bx - ax) * t:
                inside = not inside
    return inside


def _surface_color(
    ins: Instruction, cmap: dict[str, str], work_assignment: dict[str, str]
) -> str:
    return _resolve_color(
        ins.color,
        ins.color_hint,
        cmap,
        work_assignment=work_assignment,
    )


def _surface_line_angle(surface: SurfaceSpec) -> float:
    return {
        "horizontal": 0.0,
        "vertical": math.pi / 2,
        "diagonal_rising": -math.pi / 4,
        "diagonal_falling": math.pi / 4,
        "none": math.pi / 4,
    }.get(surface.direction, math.pi / 4)


SURFACE_MARK_MAX = 90
# Far past the row index a hatch layer can reach (80 rows, 4096 per layer), so
# the second span of a row never lands on another row's stroke seed.
HATCH_SPAN_SEED_STRIDE = 1048576
SURFACE_DAB_SAMPLES = 5
SURFACE_WASH_LAYERS = 2
# One sweep's width, as a multiple of the pitch the sweeps are laid down at.
# The band decides whether a wash reads as a field or as a set of stripes: below
# 1.0 the paper between two sweeps is never reached by either of them.
SURFACE_WASH_WIDTH_BASE = 0.88
SURFACE_WASH_WIDTH_SPAN = 0.60
# Each sweep carries this fraction of the surface's stated opacity. The layers
# overlap, so the ink a reader sees is the composite rather than this number.
# Doubling the width above closes the gaps, which also darkened the wash; the
# factor comes down from 0.42 so the ink lands back where it was.
SURFACE_WASH_OPACITY = 0.22
SURFACE_BLEED_RINGS = 3


def _surface_stroke_seed(seed: int, index: int) -> int:
    """surface の 1 筆ごとの seed。塗りや輪郭と波形を共有させない。"""
    digest = hashlib.sha256(f"{seed}:surface-stroke:{index}".encode("utf-8")).digest()
    return struct.unpack("<Q", digest[:8])[0]


def _surface_scatter(
    contour: list[tuple[float, float]], count: int, seed: int
) -> list[tuple[float, float]]:
    """輪郭の内部に位置を撒く。走査線と輪郭の交点区間から引く。

    `_render_fill_strokes` と同じ `_scanline_segments` を使うので、凹形も交点対の
    まま扱え、bbox の外へ粒が出ることがない。走査線に沿う方向と法線方向の両方に
    hash で散らすため、行として読めるほどは揃わない。
    """
    if count <= 0 or len(contour) < 3:
        return []
    angle = _fill_scan_angle(seed)
    xs = [point[0] for point in contour]
    ys = [point[1] for point in contour]
    diagonal = max(1e-6, math.hypot(max(xs) - min(xs), max(ys) - min(ys)))
    rows = max(2, int(round(math.sqrt(count * 1.6))))
    spacing = diagonal / rows
    segments = _scanline_segments(contour, angle, spacing, seed)
    lengths = [
        math.hypot(end[0] - start[0], end[1] - start[1])
        for _, start, end in segments
    ]
    total = sum(lengths)
    if total <= 0.0:
        return []
    nx, ny = -math.sin(angle), math.cos(angle)
    points: list[tuple[float, float]] = []
    for index, ((_, start, end), length) in enumerate(zip(segments, lengths)):
        share = count * length / total
        taken = int(share)
        if _hash01(index, seed, "surface-share") < share - taken:
            taken += 1
        for j in range(taken):
            salt_index = index * 4096 + j
            u = (j + _hash01(salt_index, seed, "surface-u")) / taken
            px = start[0] + (end[0] - start[0]) * u
            py = start[1] + (end[1] - start[1]) * u
            drift = (_hash01(salt_index, seed, "surface-n") - 0.5) * spacing * 0.8
            qx, qy = px + nx * drift, py + ny * drift
            if _point_in_polygon(qx, qy, contour):
                px, py = qx, qy
            points.append((px, py))
    return points


def _surface_dab(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    canvas: CanvasSize,
    point: tuple[float, float],
    radius: float,
    color: str,
    opacity: float,
    *,
    seed: int,
    index: int,
    wild: bool,
    use_filters: bool,
    support: Support,
    mark_style: SurfaceMarkStyle,
    class_: str | None = None,
) -> None:
    """粒を 1 つ置く。1 点 = 1 筆。

    粒は円ではなく、道具を一度当てた痕跡である。幅は道具と粒の大きさの太い方 —
    細い道具でも粒は粒の大きさを持ち、太筆なら筆の幅が出る — で、長さは
    `surface.scale` が決める。rotring だけは engine 8 の裁定どおり幾何のままに
    するので、位置だけが輪郭由来になる。

    幅を道具の線幅だけで決めると、同じ `scale` の粒が engine 15 の円の 1/3.6 の
    墨しか置かず、面が消えた (実測: 正方形内部の平均濃度 1.74 → 0.48)。
    """
    px, py = point
    if not _uses_hand_stroke(ins.weight):
        attrs: dict = {
            "center": (px, py),
            "r": radius,
            "fill": color,
            "opacity": opacity,
            "stroke": "none",
        }
        if class_:
            attrs["class_"] = class_
        group.add(dwg.circle(**attrs))
        return
    angle = _hash01(index, seed, "surface-dab-angle") * math.pi
    length = radius * (1.9 + _hash01(index, seed, "surface-dab-length") * 1.6)
    ux = math.cos(angle) * length / 2
    uy = math.sin(angle) * length / 2
    centerline = [
        (
            px - ux + 2 * ux * i / (SURFACE_DAB_SAMPLES - 1),
            py - uy + 2 * uy * i / (SURFACE_DAB_SAMPLES - 1),
        )
        for i in range(SURFACE_DAB_SAMPLES)
    ]
    stroke = synthesize_along(
        centerline,
        max(mark_style.mark_width_px(ins, canvas), radius * 1.3),
        ins.weight,
        _surface_stroke_seed(seed, index),
        closed=False,
        grid_step=_grid_step_px(ins.weight, canvas),
        wild=wild,
        support=support,
    )
    path_attrs = {
        "d": contour_stroke_path(stroke),
        "fill": color,
        "fill_opacity": opacity,
        "stroke": "none",
        "class_": f"surface-stroke-v1{' ' + class_ if class_ else ''}",
    }
    if class_ == "surface-grain-dab":
        # A grain keeps the same tool grammar after its fill has become a tile.
        # These portable stroke attributes are the grammar's structural
        # signature; the path itself remains fill-only.
        signature = mark_style.weight_style.get(ins.weight, {})
        path_attrs["stroke_opacity"] = signature.get("stroke_opacity", 1.0)
        if "stroke_linecap" in signature:
            path_attrs["stroke_linecap"] = signature["stroke_linecap"]
        if "stroke_dasharray" in signature:
            path_attrs["stroke_dasharray"] = signature["stroke_dasharray"]
    if (
        use_filters
        and ins.weight in mark_style.texture_filter_weights
        and ins.weight != "drypoint"
    ):
        path_attrs["filter"] = f"url(#texture-{ins.weight})"
    group.add(dwg.path(**path_attrs))


def _surface_grain_pattern_id(ins_idx: int, mark_idx: int) -> str:
    return f"surface_pattern_{ins_idx:03d}_{mark_idx:03d}_grain"


def _surface_grain_logical_mark_count(density: float, canvas: CanvasSize) -> int:
    """Fixed-tile grain count; the destination only repeats this definition."""
    tile_area = (canvas.unit * 0.08) ** 2
    reference_area = canvas.unit * canvas.unit * 0.18
    return max(1, math.ceil((22 + density * 120) * tile_area / reference_area))


def _surface_grain_carrier_path(contour: list[tuple[float, float]]) -> str:
    start, *rest = contour
    commands = [f"M {start[0]:.6f} {start[1]:.6f}"]
    commands.extend(f"L {x:.6f} {y:.6f}" for x, y in rest)
    return " ".join(commands) + " Z"


def _surface_grain_wrap_offsets(
    point: tuple[float, float], reach: float, tile: float
) -> list[tuple[float, float]]:
    """Copies crossing a tile edge are the same logical mark in the next tile."""
    x, y = point
    x_offsets = [0.0]
    y_offsets = [0.0]
    if x < reach:
        x_offsets.append(tile)
    if x > tile - reach:
        x_offsets.append(-tile)
    if y < reach:
        y_offsets.append(tile)
    if y > tile - reach:
        y_offsets.append(-tile)
    return [(dx, dy) for dx in x_offsets for dy in y_offsets]


def _render_surface_grain_pattern(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    canvas: CanvasSize,
    *,
    seed: int,
    color: str,
    opacity: float,
    wild: bool,
    support: Support,
    pattern_id: str,
    mark_style: SurfaceMarkStyle,
) -> str:
    """Build one finite tool-made grain tile, independent of its carrier area."""
    surface = ins.surface
    assert surface is not None and surface.texture == "grain"
    tile = canvas.unit * 0.08
    radius = max(0.45, canvas.unit * (0.002 + max(0.04, surface.scale) * 0.004))
    marks = dwg.g(class_="surface-grain-pattern-v1")
    for index in range(
        _surface_grain_logical_mark_count(max(0.02, surface.density), canvas)
    ):
        point = (
            _hash01(index, seed, "surface-grain-x") * tile,
            _hash01(index, seed, "surface-grain-y") * tile,
        )
        mark_radius = radius * (0.55 + _hash01(index, seed, "surface-r") * 1.1)
        mark_opacity = opacity * (0.45 + _hash01(index, seed, "surface-o") * 0.55)
        reach = max(
            mark_radius * 2.0, mark_style.mark_width_px(ins, canvas) * 0.75
        )
        logical_mark = dwg.g(class_="surface-grain-mark")
        for dx, dy in _surface_grain_wrap_offsets(point, reach, tile):
            _surface_dab(
                dwg,
                logical_mark,
                ins,
                canvas,
                (point[0] + dx, point[1] + dy),
                mark_radius,
                color,
                mark_opacity,
                seed=seed,
                index=index,
                wild=wild,
                use_filters=False,
                class_="surface-grain-dab",
                support=support,
                mark_style=mark_style,
            )
        marks.add(logical_mark)
    return (
        f'<pattern id="{pattern_id}" patternUnits="userSpaceOnUse" '
        f'width="{tile:.6f}" height="{tile:.6f}">{marks.tostring()}</pattern>'
    )

def _surface_sweep(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    canvas: CanvasSize,
    start: tuple[float, float],
    end: tuple[float, float],
    width: float,
    color: str,
    opacity: float,
    *,
    seed: int,
    index: int,
    wild: bool,
    use_filters: bool,
    support: Support,
    mark_style: SurfaceMarkStyle,
) -> None:
    """走査線 1 本を 1 筆として引く。薄墨の層はこれを重ねて作る。"""
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if length <= 0.0:
        return
    if not _uses_hand_stroke(ins.weight):
        group.add(
            dwg.line(
                start=start,
                end=end,
                stroke=color,
                stroke_width=width,
                stroke_opacity=opacity,
                stroke_linecap="round",
            )
        )
        return
    count = max(2, _stroke_sample_count(length, canvas))
    centerline = [
        (
            start[0] + (end[0] - start[0]) * i / (count - 1),
            start[1] + (end[1] - start[1]) * i / (count - 1),
        )
        for i in range(count)
    ]
    stroke = synthesize_along(
        centerline,
        width,
        ins.weight,
        _surface_stroke_seed(seed, index),
        closed=False,
        grid_step=_grid_step_px(ins.weight, canvas),
        wild=wild,
        support=support,
    )
    path_attrs = {
        "d": contour_stroke_path(stroke),
        "fill": color,
        "fill_opacity": opacity,
        "stroke": "none",
        "class_": "surface-stroke-v1",
    }
    if (
        use_filters
        and ins.weight in mark_style.texture_filter_weights
        and ins.weight != "drypoint"
    ):
        path_attrs["filter"] = f"url(#texture-{ins.weight})"
    group.add(dwg.path(**path_attrs))


def _render_surface_vectors(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    canvas: CanvasSize,
    cmap: dict[str, str],
    work_assignment: dict[str, str],
    *,
    seed: int,
    contour: list[tuple[float, float]],
    support: Support,
    mark_style: SurfaceMarkStyle,
    wild: bool = False,
    use_filters: bool = False,
) -> None:
    surface = ins.surface
    bbox = _shape_bbox(ins, canvas)
    if surface is None or surface.texture == "none" or bbox is None:
        return
    x, y, w, h = bbox
    color = _surface_color(ins, cmap, work_assignment)
    opacity = min(0.75, surface.opacity)
    density = max(0.02, surface.density)
    scale = max(0.04, surface.scale)
    area_factor = max(0.2, min(1.8, (w * h) / (canvas.unit * canvas.unit * 0.18)))
    if surface.texture in {"stipple", "paper_grain"}:
        count = min(SURFACE_MARK_MAX, int((22 + density * 120) * area_factor))
        radius = max(0.45, canvas.unit * (0.002 + scale * 0.004))
        for index, point in enumerate(_surface_scatter(contour, count, seed)):
            _surface_dab(
                dwg,
                group,
                ins,
                canvas,
                point,
                radius * (0.55 + _hash01(index, seed, "surface-r") * 1.1),
                color,
                opacity * (0.45 + _hash01(index, seed, "surface-o") * 0.55),
                seed=seed,
                index=index,
                wild=wild,
                use_filters=use_filters,
                support=support,
                mark_style=mark_style,
            )
    elif surface.texture == "wash":
        # 薄墨は粒ではなく層である。同じ図形を角度違いに 2 度掃き、重なった所だけが
        # 濃くなる。走査線は `_render_fill_strokes` と同じ機構で輪郭に切られる。
        # 間隔を筆の幅より広く取るのは、隙間なく塗ると織物に見えるからである
        # (最初の実装は間隔 22px に幅 14〜21px を 2 層重ねて布地になった)。
        spacing = max(10.0, canvas.unit * (0.052 - density * 0.024))
        index = 0
        base_angle = _fill_scan_angle(seed)
        for layer in range(SURFACE_WASH_LAYERS):
            layer_seed = seed + layer * 7919
            # 層は角度を変えない。二度目の掃きが一度目とほぼ同じ向きだから、重なりは
            # 濃淡になる。無関係な角度で重ねると格子になり、薄墨でなく織物に見えた。
            angle = base_angle + (
                _hash01(layer, seed, "wash-angle") - 0.5
            ) * math.radians(16)
            segments = _scanline_segments(contour, angle, spacing, layer_seed)
            for _, start, end in segments:
                width = max(
                    mark_style.mark_width_px(ins, canvas),
                    spacing
                    * (
                        SURFACE_WASH_WIDTH_BASE
                        + _hash01(index, seed, "wash-width") * SURFACE_WASH_WIDTH_SPAN
                    ),
                )
                _surface_sweep(
                    dwg,
                    group,
                    ins,
                    canvas,
                    start,
                    end,
                    width,
                    color,
                    opacity * SURFACE_WASH_OPACITY,
                    seed=seed,
                    index=index,
                    wild=wild,
                    use_filters=use_filters,
                    support=support,
                    mark_style=mark_style,
                )
                index += 1
    elif surface.texture in {"hatch", "crosshatch"}:
        angle = _surface_line_angle(surface)
        spacing = max(5.0, canvas.unit * (0.010 + (1.0 - density) * 0.025))
        span = math.hypot(w, h) * 1.3
        cx = x + w / 2
        cy = y + h / 2
        count = min(80, max(3, int(span / spacing)))
        angles = [angle]
        if surface.texture == "crosshatch":
            angles.append(
                angle + math.radians(60 + _hash01(8, seed, "cross-angle") * 30)
            )
        for layer_index, layer_angle in enumerate(angles):
            lux, luy = math.cos(layer_angle), math.sin(layer_angle)
            lnx, lny = -luy, lux
            for i in range(-count // 2, count // 2 + 1):
                progress = (i + count / 2) / max(1, count)
                gradient = 1.0
                if surface.spacing_gradient == "coarse_to_dense":
                    gradient = 1.35 - progress * 0.7
                elif surface.spacing_gradient == "dense_to_coarse":
                    gradient = 0.65 + progress * 0.7
                offset = (
                    i * spacing * gradient
                    + _hash_to_unit(i + layer_index * 401 + 500, seed) * spacing * 0.12
                )
                ox, oy = lnx * offset, lny * offset
                line_width = max(0.45, canvas.unit * 0.0016)
                hatch_class = f"hatch-spacing-{spacing * gradient:.3f}"
                # A surface belongs to the shape that carries it, so the row is
                # cut where the shape ends instead of running the fixed 1.3x
                # diagonal it was laid out on. Nothing above this line moves:
                # the angle, the pitch, the gradient and the per-row jitter
                # still decide where a row sits and how it leans -- only its two
                # ends do. `_line_spans` returns entry/exit pairs, so a concave
                # form gives several spans and each one is drawn on its own; a
                # row never crosses the void. A row that misses the contour
                # returns no span and draws nothing.
                # Not a clipPath: the compat profile emits none (SPEC 1180), and
                # a cut that only display can see is not a cut.
                row_point = (cx + ox, cy + oy)
                stroke_index = i + layer_index * 4096
                for span_index, (t0, t1) in enumerate(
                    _line_spans(contour, row_point, (lux, luy))
                ):
                    chord = t1 - t0
                    if chord <= 0.0:
                        continue
                    start = (row_point[0] + lux * t0, row_point[1] + luy * t0)
                    end = (row_point[0] + lux * t1, row_point[1] + luy * t1)
                    if not _uses_hand_stroke(ins.weight):
                        group.add(
                            dwg.line(
                                start=start,
                                end=end,
                                stroke=color,
                                stroke_width=line_width,
                                stroke_opacity=opacity,
                                stroke_linecap="round",
                                class_=hatch_class,
                            )
                        )
                        continue
                    # ハッチも版の筆致であって幾何直線ではない。中心線・角度・間隔は
                    # そのままに、描画だけ材質エンジンを通す。
                    # The sample count follows the length actually travelled --
                    # a two-pixel corner span given the whole diagonal's samples
                    # is not the same stroke the material engine was asked for.
                    count_samples = max(2, _stroke_sample_count(chord, canvas))
                    centerline = [
                        (
                            start[0] + (end[0] - start[0]) * sample / (count_samples - 1),
                            start[1] + (end[1] - start[1]) * sample / (count_samples - 1),
                        )
                        for sample in range(count_samples)
                    ]
                    # The first span of a row keeps the row's own stroke seed,
                    # so a convex shape -- every corpus case is one -- performs
                    # each row exactly as it was asked to. Later spans, which
                    # only a concave form has, take their own.
                    hatch_stroke = synthesize_along(
                        centerline,
                        line_width,
                        ins.weight,
                        _fill_stroke_seed(
                            seed, stroke_index + span_index * HATCH_SPAN_SEED_STRIDE
                        ),
                        closed=False,
                        grid_step=_grid_step_px(ins.weight, canvas),
                        wild=wild,
                        support=support,
                    )
                    group.add(
                        dwg.path(
                            d=contour_stroke_path(hatch_stroke),
                            fill=color,
                            fill_opacity=opacity,
                            stroke="none",
                            class_=f"surface-stroke-v1 {hatch_class}",
                        )
                    )
    elif surface.texture == "aquatint":
        steps = surface.tone_steps
        band = w / steps
        radius = max(0.45, canvas.unit * (0.0015 + scale * 0.0025))
        # 帯は図形の中で濃度が段になること。粒そのものは他の粒系と同じ機構なので、
        # 一度だけ輪郭から撒き、どの帯に落ちたかで残す確率と濃度を決める。
        count = min(SURFACE_MARK_MAX, max(5, int((18 + density * 90) * area_factor)))
        for index, point in enumerate(_surface_scatter(contour, count, seed)):
            step = min(steps - 1, max(0, int((point[0] - x) / band))) if band > 0 else 0
            boundary_jitter = (
                (_hash01(step, seed, "aquatint-boundary") - 0.5) * band * 0.08
            )
            shifted = (point[0] + boundary_jitter, point[1])
            if not _point_in_polygon(shifted[0], shifted[1], contour):
                shifted = point
            _surface_dab(
                dwg,
                group,
                ins,
                canvas,
                shifted,
                radius,
                color,
                opacity * (0.35 + 0.65 * (step + 1) / steps),
                seed=seed,
                index=index,
                wild=wild,
                use_filters=use_filters,
                class_=f"aquatint-step-{step + 1}",
                support=support,
                mark_style=mark_style,
            )
    elif surface.texture == "bleed":
        # 「端が滲む」は端の話である。engine 15 までは bbox 中心の楕円を 1 個置いて
        # いたので、三角にも雲形にも同じ楕円が出て、端は滲んでいなかった。輪郭を
        # 外へ押し出した帯を重ねる。押し出す量は頂点ごとに揺れるので、同心の輪郭
        # ではなく染み出しとして読める。
        blur = max(1.0, canvas.unit * (0.010 + surface.bleed * 0.030))
        normals = centerline_normals(contour, True)
        center = _points_center(contour)
        outward = sum(
            (point[0] - center[0]) * nx + (point[1] - center[1]) * ny
            for point, (nx, ny) in zip(contour, normals)
        )
        sign = 1.0 if outward >= 0.0 else -1.0
        for ring in range(SURFACE_BLEED_RINGS):
            # 内側の輪は輪郭に重なる。滲みは縁の両側に起こるので、帯は縁から外へ
            # 立ち上がるのであって、図形から離れた所に輪が浮くのではない。
            level = ring / (SURFACE_BLEED_RINGS - 1) if SURFACE_BLEED_RINGS > 1 else 0.0
            pushed = []
            for i, (point, (nx, ny)) in enumerate(zip(contour, normals)):
                seep = (
                    sign
                    * blur
                    * level
                    * (0.55 + _hash01(i + ring * 613, seed, "bleed-seep") * 0.9)
                )
                pushed.append((point[0] + nx * seep, point[1] + ny * seep))
            ring_opacity = min(0.30, opacity * 0.55) * (1.0 - level * 0.55)
            ring_width = max(1.2, blur * (1.05 - level * 0.45))
            if not _uses_hand_stroke(ins.weight):
                group.add(
                    dwg.polygon(
                        points=pushed,
                        fill="none",
                        stroke=color,
                        stroke_width=ring_width,
                        stroke_opacity=ring_opacity,
                    )
                )
                continue
            stroke = synthesize_along(
                pushed,
                ring_width,
                ins.weight,
                _surface_stroke_seed(seed, 90000 + ring),
                closed=True,
                grid_step=_grid_step_px(ins.weight, canvas),
                wild=wild,
                support=support,
            )
            path_attrs = {
                "d": contour_stroke_path(stroke),
                "fill": color,
                "fill_opacity": ring_opacity,
                "fill_rule": "evenodd",
                "stroke": "none",
                "class_": f"surface-stroke-v1 bleed-ring-{ring + 1}",
            }
            if (
                use_filters
                and ins.weight in mark_style.texture_filter_weights
                and ins.weight != "drypoint"
            ):
                path_attrs["filter"] = f"url(#texture-{ins.weight})"
            group.add(dwg.path(**path_attrs))


def _render_surface_texture(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    cmap: dict[str, str],
    work_assignment: dict[str, str],
    canvas: CanvasSize,
    *,
    profile: str,
    render_seed: int | None,
    ins_idx: int,
    mark_idx: int,
    support: Support,
    mark_style: SurfaceMarkStyle,
    wild: bool = False,
    use_filters: bool = False,
):
    """図形の面の質感を描く。

    engine 16: display と editable で機構を揃える。engine 15 までは `wash` と
    `bleed` が display でだけ feTurbulence をかけた矩形になっており、同じ語が
    プロファイル次第で無関係な 2 つの絵になっていた。両者とも輪郭から筆致で描き、
    プロファイルの差は他の層と同じく材質フィルタの有無だけにする。粒が輪郭の
    内側から引かれるようになったので、display の clipPath も要らない (`bleed` は
    外へ染み出すので、clip はむしろ描いたものを消してしまう)。
    """
    surface = ins.surface
    if (
        surface is None
        # `solid` alongside `none`: the material's default fill is drawn by the
        # fill layer, not here, and a group left empty would still move bytes.
        or surface.texture in ("none", "solid")
        or ins.primitive not in _CLOSED_SHAPES
    ):
        return None, None
    contour = _surface_contour(
        ins, canvas, render_seed=render_seed, ins_idx=ins_idx, mark_idx=mark_idx
    )
    if contour is None or len(contour) < 3:
        return None, None
    seed = (
        _surface_grain_seed(ins, ins_idx, mark_idx, render_seed)
        if surface.texture == "grain"
        else _surface_seed(ins, ins_idx, mark_idx, render_seed)
    )
    gid = _safe_svg_id(f"surface_{ins_idx:03d}_{mark_idx:03d}_{surface.texture}")
    group = dwg.g(id=gid)
    if surface.texture == "grain":
        color = _surface_color(ins, cmap, work_assignment)
        opacity = min(0.75, surface.opacity)
        pattern_id = _surface_grain_pattern_id(ins_idx, mark_idx)
        grain_defs = _render_surface_grain_pattern(
            dwg,
            ins,
            canvas,
            seed=seed,
            color=color,
            opacity=opacity,
            wild=wild,
            support=support,
            pattern_id=pattern_id,
            mark_style=mark_style,
        )
        group.add(
            dwg.path(
                d=_surface_grain_carrier_path(contour),
                fill=f"url(#{pattern_id})",
                stroke="none",
                class_="surface-grain-carrier-v1",
            )
        )
        return group, grain_defs
    _render_surface_vectors(
        dwg,
        group,
        ins,
        canvas,
        cmap,
        work_assignment,
        seed=seed,
        contour=contour,
        wild=wild,
        use_filters=use_filters and profile == "display",
        support=support,
        mark_style=mark_style,
    )
    return group, None



def _has_surface_texture(ins: Instruction) -> bool:
    """surface が内部を担うか (閉図形のみ。線・弧では surface は描かれない)。

    `solid` は数に入らない。それは版の表現ではなく素材の既定の埋め方で、
    面の質感を描く層はそれを 1 本も引かない (→ `_fills_interior`)。
    """
    return (
        ins.surface is not None
        and ins.surface.texture not in ("none", "solid")
        and ins.primitive in _CLOSED_SHAPES
    )


def _fills_interior(ins: Instruction) -> bool:
    """内部を埋めるか。

    塗り = 素材の既定の埋め方、`surface` の質感 = 明示的な版表現。両方は出さない。
    その「塗り」は `filled=true` とも `texture="solid"` とも書ける — おもての語彙
    では 塗り はほかの 8 語と同じ 1 語で、Score でも同じ欄へ入る (ddl engine 18)。
    閉図形が `filled` に関わらず常に塗られていた挙動 (死にフィールド) は
    engine 9 で解消し、記述どおりに演奏する。
    """
    if _has_surface_texture(ins):
        return False
    return fill_is_asked_for(ins)
