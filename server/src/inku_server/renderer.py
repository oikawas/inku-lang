"""JSON Score → SVG renderer.

楽譜(Score)を演奏(SVG)に変換する。揺らぎ(variation)の実現は Renderer 層で行う
(SPEC §13.8)。Phase 1 は静的描画のみ、perlin/wave は段階追加。
"""

from __future__ import annotations

import hashlib
import math
import struct

import svgwrite

from .schema import Instruction, Score, Variation

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

BACKGROUND = "#f7f5ef"

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


def render(score: Score) -> str:
    dwg = svgwrite.Drawing(
        size=(CANVAS_PX, CANVAS_PX),
        viewBox=f"0 0 {CANVAS_PX} {CANVAS_PX}",
    )
    dwg.add(dwg.rect(insert=(0, 0), size=(CANVAS_PX, CANVAS_PX), fill=BACKGROUND))

    for ins in score.instructions:
        element = _render_instruction(dwg, ins)
        if element is not None:
            dwg.add(element)

    return dwg.tostring()


def _stroke_attrs(ins: Instruction) -> dict:
    attrs = {
        "stroke": COLOR_MAP[ins.color],
        "stroke_width": WEIGHT_TO_STROKE_WIDTH[ins.weight],
        "fill": "none",
        "stroke_linecap": "round",
    }
    dash = STYLE_TO_DASH[ins.style]
    if dash:
        attrs["stroke_dasharray"] = dash
    return attrs


def _px(coord: tuple[float, float]) -> tuple[float, float]:
    x, y = coord
    return x * CANVAS_PX, y * CANVAS_PX


def _render_instruction(dwg: svgwrite.Drawing, ins: Instruction):
    attrs = _stroke_attrs(ins)

    if ins.primitive == "line":
        if ins.from_ is None or ins.to is None:
            raise ValueError("line requires 'from' and 'to'")
        start = _px(ins.from_)
        end = _px(ins.to)
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

    raise NotImplementedError(f"primitive '{ins.primitive}' not yet supported")
