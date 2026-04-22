"""JSON Score → SVG renderer.

楽譜(Score)を演奏(SVG)に変換する。揺らぎ(variation)の実現は Renderer 層で行う
(SPEC §13.8)。Phase 1 は静的描画のみ、perlin/wave は段階追加。
"""

from __future__ import annotations

import svgwrite

from .schema import Instruction, Score

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
        return dwg.line(start=_px(ins.from_), end=_px(ins.to), **attrs)

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
