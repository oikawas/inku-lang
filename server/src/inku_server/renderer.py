"""JSON Score → SVG renderer.

楽譜(Score)を演奏(SVG)に変換する。揺らぎ(variation)の実現は Renderer 層で行う
(SPEC §13.8)。Phase 1 は静的描画のみ、perlin/wave は段階追加。
"""

from __future__ import annotations

import hashlib
import math
import struct

import svgwrite

from .schema import Arrangement, Instruction, Score, Variation

CANVAS_PX = 1000

WEIGHT_TO_STROKE_WIDTH: dict[str, float] = {
    "hair": 0.5,
    "pencil": 1.5,
    "pen": 2.0,
    "rotring": 1.0,
    "crayon": 4.0,
    "chalk": 3.0,
    "brush_thin": 3.0,
    "brush_thick": 8.0,
    "rope": 10.0,
}

COLOR_MAP: dict[str, str] = {
    "white": "#ffffff",
    "black": "#111111",
    "blue": "#2c3e91",
    "red": "#a2342a",
    "green": "#2f6b3a",
    "gray": "#888888",
}

STYLE_TO_DASH: dict[str, str | None] = {
    "solid": None,
    "dashed": "12,8",
    "dotted": "2,6",
    "dash_dot": "12,6,2,6",
}

BACKGROUND = "#ffffff"

# SPEC §13.8: 揺らぎは Renderer 層で生成する (JSON Score は決定的な楽譜)
AMPLITUDE_PX: dict[str, float] = {"fine": 4.0, "medium": 12.0, "broad": 30.0}
FREQUENCY_CYCLES: dict[str, float] = {"slow": 2.0, "medium": 6.0, "high": 14.0}
SEGMENT_COUNT = 80  # polyline の分割数


def _seed_for_instruction(ins: Instruction) -> int:
    """同一 Score は同一 SVG を出す (決定的)。"""
    key = ins.model_dump_json().encode("utf-8")
    digest = hashlib.sha256(key).digest()
    return struct.unpack("<Q", digest[:8])[0]


def _hash_to_unit(i: int, seed: int) -> float:
    """i と seed から [-1, 1] の擬似乱数値を決定的に生成。"""
    h = hashlib.sha256(f"{seed}:{i}".encode("utf-8")).digest()
    val = struct.unpack("<q", h[:8])[0]
    return val / float(2**63)


def _value_noise_1d(x: float, seed: int) -> float:
    """smoothstep 補間の 1D value noise (擬似 perlin)。"""
    xi = math.floor(x)
    xf = x - xi
    v1 = _hash_to_unit(xi, seed)
    v2 = _hash_to_unit(xi + 1, seed)
    t = xf * xf * (3 - 2 * xf)
    return v1 * (1 - t) + v2 * t


def _needs_variation(v: Variation | None) -> bool:
    if v is None:
        return False
    if v.quality == "none":
        return False
    return any(d in ("position_x", "position_y") for d in v.dimensions)


def _sample_offset(t: float, variation: Variation, seed: int, segment: int) -> float:
    amp = AMPLITUDE_PX[variation.amplitude]
    freq = FREQUENCY_CYCLES[variation.frequency]
    q = variation.quality

    if q == "wave":
        return math.sin(t * 2 * math.pi * freq) * amp
    if q == "perlin":
        return _value_noise_1d(t * freq, seed) * amp
    if q == "pink":
        # 簡易 pink: perlin 2 オクターブ合成
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
) -> list[tuple[float, float]]:
    """直線の polyline に揺らぎを適用した頂点列を返す。

    dimensions の指定:
    - position_x のみ: x 軸方向に揺らす
    - position_y のみ: y 軸方向に揺らす
    - 両方 (または position_x+position_y+他): 線に垂直方向に揺らす
    """
    dx = end_px[0] - start_px[0]
    dy = end_px[1] - start_px[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return [start_px, end_px]

    # 線の方向に垂直な単位ベクトル
    perp_x = -dy / length
    perp_y = dx / length

    dims = set(variation.dimensions)
    axis_x = "position_x" in dims
    axis_y = "position_y" in dims

    pts: list[tuple[float, float]] = [start_px]
    for i in range(1, SEGMENT_COUNT):
        t = i / SEGMENT_COUNT
        x = start_px[0] + t * dx
        y = start_px[1] + t * dy
        off = _sample_offset(t, variation, seed, i)

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


def _scatter_pos(i: int, seed: int, margin: float) -> tuple[float, float]:
    """index i に対応する決定的な散布座標を返す (hash ベース)。"""
    span = 1.0 - 2 * margin
    h = hashlib.sha256(f"{seed}:s:{i}".encode()).digest()
    xv = struct.unpack("<I", h[:4])[0] / 0xFFFFFFFF
    yv = struct.unpack("<I", h[4:8])[0] / 0xFFFFFFFF
    return (margin + xv * span, margin + yv * span)


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
    if ins.primitive in ("circle", "ellipse", "arc") and ins.center:
        return ins.center
    if ins.primitive in ("square", "triangle") and ins.position and ins.size:
        return (ins.position[0] + ins.size[0] / 2, ins.position[1] + ins.size[1] / 2)
    return (0.5, 0.5)


def _shift(ins: Instruction, dx: float, dy: float) -> Instruction:
    """ins を (dx, dy) だけ平行移動した新しい Instruction を返す。arrangement は除去。"""
    data = ins.model_dump(by_alias=True)
    data.pop("arrangement", None)
    if ins.primitive == "line" and ins.from_ and ins.to:
        data["from"] = [ins.from_[0] + dx, ins.from_[1] + dy]
        data["to"] = [ins.to[0] + dx, ins.to[1] + dy]
    elif ins.primitive in ("circle", "ellipse", "arc") and ins.center:
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
        result.append(Instruction.model_validate(data))
    return result


def _expand_arrangement(ins: Instruction) -> list[Instruction]:
    """arrangement を展開して N 個の Instruction を返す。"""
    arr = ins.arrangement
    assert arr is not None
    ins = _ensure_line_coords(ins)
    if arr.count == 1:
        data = ins.model_dump(by_alias=True)
        data.pop("arrangement", None)
        return _apply_color_cycle([Instruction.model_validate(data)], arr.color_cycle)
    n = arr.count
    margin = arr.margin
    ax, ay = _anchor(ins)
    seed = _seed_for_instruction(ins)

    if arr.layout == "horizontal":
        span = 1.0 - 2 * margin
        targets = [(margin + i / max(n - 1, 1) * span, ay) for i in range(n)]
        result = [_shift(ins, tx - ax, 0.0) for tx, _ in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    if arr.layout == "vertical":
        span = 1.0 - 2 * margin
        targets = [(ax, margin + i / max(n - 1, 1) * span) for i in range(n)]
        result = [_shift(ins, 0.0, ty - ay) for _, ty in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    if arr.layout == "radial":
        cx = arr.center[0] if arr.center else 0.5
        cy = arr.center[1] if arr.center else 0.5
        r = arr.radius if arr.radius else 0.3
        targets = [
            (cx + r * math.cos(math.radians(i * 360 / n)),
             cy - r * math.sin(math.radians(i * 360 / n)))
            for i in range(n)
        ]
        result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    if arr.layout == "scatter":
        targets = [_scatter_pos(i, seed, margin) for i in range(n)]
        result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    return _apply_color_cycle([ins], arr.color_cycle)


def render(score: Score) -> str:
    dwg = svgwrite.Drawing(
        size=(CANVAS_PX, CANVAS_PX),
        viewBox=f"0 0 {CANVAS_PX} {CANVAS_PX}",
    )
    bg = COLOR_MAP.get(score.background, BACKGROUND)
    dwg.add(dwg.rect(insert=(0, 0), size=(CANVAS_PX, CANVAS_PX), fill=bg))

    for ins in score.instructions:
        expanded = _expand_arrangement(ins) if ins.arrangement else [ins]
        for single in expanded:
            element = _render_instruction(dwg, single)
            if element is not None:
                dwg.add(element)

    return dwg.tostring()


def _stroke_attrs(ins: Instruction) -> dict:
    attrs = {
        "stroke": COLOR_MAP[ins.color],
        "stroke_width": WEIGHT_TO_STROKE_WIDTH[ins.weight],
        "fill": COLOR_MAP[ins.color] if ins.filled else "none",
        "stroke_linecap": "round",
    }
    dash = STYLE_TO_DASH[ins.style]
    if dash:
        attrs["stroke_dasharray"] = dash
    return attrs


def _px(coord: tuple[float, float]) -> tuple[float, float]:
    x, y = coord
    return x * CANVAS_PX, y * CANVAS_PX


def _arc_path_d(cx: float, cy: float, r: float, start_deg: float, end_deg: float) -> str:
    """SVG <path d> の A コマンドで弧を描く文字列を返す。

    角度は度、0°=東、CCW 正 (数学慣習)。y 軸は画面下向きなので
    y 成分は反転。CCW 描画は SVG の sweep-flag=0 に対応する。
    """
    sa = math.radians(start_deg)
    ea = math.radians(end_deg)
    x1 = cx + r * math.cos(sa)
    y1 = cy - r * math.sin(sa)
    x2 = cx + r * math.cos(ea)
    y2 = cy - r * math.sin(ea)

    delta = (end_deg - start_deg) % 360
    large_arc = 1 if delta > 180 else 0
    sweep = 0 if end_deg > start_deg else 1  # math CCW → SVG 反時計回り (y 反転後)

    return (
        f"M {x1:.3f} {y1:.3f} "
        f"A {r:.3f} {r:.3f} 0 {large_arc} {sweep} {x2:.3f} {y2:.3f}"
    )


def _render_instruction(dwg: svgwrite.Drawing, ins: Instruction):
    attrs = _stroke_attrs(ins)

    if ins.primitive == "line":
        start = _px(ins.from_ if ins.from_ is not None else (0.5, 0.0))
        end = _px(ins.to if ins.to is not None else (0.5, 1.0))
        if _needs_variation(ins.variation):
            assert ins.variation is not None
            points = _line_with_variation(
                start, end, ins.variation, _seed_for_instruction(ins)
            )
            return dwg.polyline(points=points, **attrs)
        return dwg.line(start=start, end=end, **attrs)

    if ins.primitive == "circle":
        if ins.center is None or ins.radius is None:
            raise ValueError("circle requires 'center' and 'radius'")
        cx, cy = _px(ins.center)
        return dwg.circle(center=(cx, cy), r=ins.radius * CANVAS_PX, **attrs)

    if ins.primitive == "ellipse":
        if ins.center is None or ins.size is None:
            raise ValueError("ellipse requires 'center' and 'size'")
        cx, cy = _px(ins.center)
        rx = ins.size[0] * CANVAS_PX / 2
        ry = ins.size[1] * CANVAS_PX / 2
        return dwg.ellipse(center=(cx, cy), r=(rx, ry), **attrs)

    if ins.primitive == "square":
        if ins.position is None or ins.size is None:
            raise ValueError("square requires 'position' and 'size'")
        x, y = _px(ins.position)
        w = ins.size[0] * CANVAS_PX
        h = ins.size[1] * CANVAS_PX
        return dwg.rect(insert=(x, y), size=(w, h), **attrs)

    if ins.primitive == "triangle":
        if ins.position is None or ins.size is None:
            raise ValueError("triangle requires 'position' and 'size'")
        x, y = _px(ins.position)
        w = ins.size[0] * CANVAS_PX
        h = ins.size[1] * CANVAS_PX
        points = [
            (x + w / 2, y),
            (x, y + h),
            (x + w, y + h),
        ]
        return dwg.polygon(points=points, **attrs)

    if ins.primitive == "arc":
        if ins.center is None or ins.radius is None:
            raise ValueError("arc requires 'center' and 'radius'")
        if ins.angle_start is None or ins.angle_end is None:
            raise ValueError("arc requires 'angle_start' and 'angle_end'")
        cx, cy = _px(ins.center)
        r = ins.radius * CANVAS_PX
        path_d = _arc_path_d(cx, cy, r, ins.angle_start, ins.angle_end)
        return dwg.path(d=path_d, **attrs)

    raise NotImplementedError(f"primitive '{ins.primitive}' not yet supported")
