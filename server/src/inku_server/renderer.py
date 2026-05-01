"""JSON Score → SVG renderer.

楽譜(Score)を演奏(SVG)に変換する。揺らぎ(variation)の実現は Renderer 層で行う
(SPEC §13.8)。Phase 1 は静的描画のみ、perlin/wave は段階追加。
"""

from __future__ import annotations

import hashlib
import math
import re
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

HUE_HINTS: dict[str, tuple[str, ...]] = {
    "white": ("white", "ivory", "paper", "linen", "blanc", "bianco", "aspro", "白", "胡粉", "象牙", "生成"),
    "black": ("black", "ink", "sumi", "obsidian", "basalt", "skotadi", "黒", "墨", "玄", "暗"),
    "blue": ("blue", "cyan", "azure", "ultramarine", "cobalt", "lapis", "bleu", "blu", "ai", "azul", "青", "藍", "水色", "空色", "瑠璃"),
    "green": ("green", "verd", "vert", "jade", "olive", "cactus", "tall", "緑", "青緑", "翡翠", "常磐", "玉", "草"),
    "gray": ("gray", "grey", "silver", "ash", "stone", "granit", "petra", "灰", "鼠", "銀", "石"),
    "red": ("red", "rose", "pink", "carmine", "cinnabar", "terra", "rosa", "shu", "vermilion", "赤", "朱", "紅", "桜", "桃", "薔薇"),
    "yellow": ("yellow", "gold", "ochre", "ocra", "giallo", "jaune", "napoli", "kesar", "haldi", "sun", "ilios", "山吹", "金", "黄", "琉璃金"),
    "orange": ("orange", "apricot", "terracotta", "cempasuchil", "ff4d00", "橙", "蜜柑"),
    "purple": ("purple", "violet", "lilac", "murasaki", "宮廷紫", "藤", "紫"),
    "brown": ("brown", "sienna", "umber", "ombra", "chandan", "lera", "sepia", "茶", "土", "焦"),
}

STYLE_TO_DASH: dict[str, str | None] = {
    "solid": None,
    "dashed": "12,8",
    "dotted": "2,6",
    "dash_dot": "12,6,2,6",
}

WEIGHT_STYLE: dict[str, dict[str, str | float]] = {
    "hair": {"stroke_opacity": 0.72, "stroke_linecap": "butt"},
    "pencil": {"stroke_opacity": 0.66, "stroke_dasharray": "1,3"},
    "pen": {"stroke_opacity": 1.0},
    "rotring": {"stroke_opacity": 0.95, "stroke_linecap": "square"},
    "crayon": {"stroke_opacity": 0.78, "stroke_dasharray": "10,3,2,3"},
    "chalk": {"stroke_opacity": 0.7, "stroke_dasharray": "7,5,1,4"},
    "brush_thin": {"stroke_opacity": 0.9, "stroke_linecap": "round"},
    "brush_thick": {"stroke_opacity": 0.86, "stroke_linecap": "round"},
    "rope": {"stroke_opacity": 0.88, "stroke_dasharray": "14,5"},
}

BACKGROUND = "#ffffff"

# SPEC §13.8: 揺らぎは Renderer 層で生成する (JSON Score は決定的な楽譜)
AMPLITUDE_PX: dict[str, float] = {"fine": 7.0, "medium": 12.0, "broad": 30.0}
FREQUENCY_CYCLES: dict[str, float] = {"slow": 2.0, "medium": 6.0, "high": 14.0}
SEGMENT_COUNT = 80  # polyline の分割数

# 滲む (quality=pink): SVG feGaussianBlur の stdDeviation
BLUR_STD: dict[str, float] = {"fine": 2.0, "medium": 6.0, "broad": 15.0}
TEXTURE_FILTERS: dict[str, str] = {
    "pencil": (
        '<filter id="texture-pencil" x="-12%" y="-12%" width="124%" height="124%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="11" result="noise"/>'
        '<feDisplacementMap in="SourceGraphic" in2="noise" scale="0.7"/>'
        '</filter>'
    ),
    "crayon": (
        '<filter id="texture-crayon" x="-18%" y="-18%" width="136%" height="136%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.55" numOctaves="3" seed="17" result="noise"/>'
        '<feDisplacementMap in="SourceGraphic" in2="noise" scale="1.8"/>'
        '</filter>'
    ),
    "chalk": (
        '<filter id="texture-chalk" x="-25%" y="-25%" width="150%" height="150%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.75" numOctaves="3" seed="23" result="noise"/>'
        '<feDisplacementMap in="SourceGraphic" in2="noise" scale="2.2"/>'
        '<feGaussianBlur stdDeviation="0.9"/>'
        '</filter>'
    ),
    "brush_thick": (
        '<filter id="texture-brush_thick" x="-20%" y="-20%" width="140%" height="140%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.2" numOctaves="2" seed="31" result="noise"/>'
        '<feDisplacementMap in="SourceGraphic" in2="noise" scale="1.4"/>'
        '<feGaussianBlur stdDeviation="0.6"/>'
        '</filter>'
    ),
}


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


def _needs_blur(v: Variation | None) -> bool:
    """quality=pink → SVG feGaussianBlur で滲み表現。"""
    return v is not None and v.quality == "pink"


def _needs_path_variation(v: Variation | None) -> bool:
    """quality=perlin/wave/white かつ dimensions 指定あり → polyline 揺らぎ。pink は blur で処理。"""
    if v is None:
        return False
    if v.quality in ("none", "pink"):
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


def _hash01(i: int, seed: int, salt: str) -> float:
    h = hashlib.sha256(f"{seed}:{salt}:{i}".encode()).digest()
    return struct.unpack("<I", h[:4])[0] / 0xFFFFFFFF


def _path_pos(i: int, n: int, seed: int, margin: float, path: str) -> tuple[float, float]:
    span = 1.0 - 2 * margin
    t = i / max(n - 1, 1)
    jitter_a = (_hash01(i, seed, "a") - 0.5)
    jitter_b = (_hash01(i, seed, "b") - 0.5)

    if path == "diagonal":
        x = margin + t * span
        y = 1.0 - margin - t * span
        return _clamp01(x + jitter_a * 0.08), _clamp01(y + jitter_b * 0.08)
    if path == "wave":
        x = margin + t * span
        y = 0.5 + math.sin(t * math.pi * 2.0) * 0.22 + jitter_b * 0.08
        return _clamp01(x), _clamp01(y)
    if path == "top_to_bottom":
        x = 0.5 + jitter_a * 0.30
        y = margin + t * span
        return _clamp01(x), _clamp01(y)
    if path == "left_to_right":
        x = margin + t * span
        y = 0.5 + jitter_b * 0.30
        return _clamp01(x), _clamp01(y)
    if path == "right_half":
        x = 0.56 + _hash01(i, seed, "x") * (0.44 - margin)
        y = margin + _hash01(i, seed, "y") * span
        return _clamp01(x), _clamp01(y)
    return _scatter_pos(i, seed, margin)


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
        data["color_hint"] = None
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
        if arr.path != "none":
            targets = [_path_pos(i, n, seed, margin, arr.path) for i in range(n)]
            result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
            return _apply_color_cycle(result, arr.color_cycle)
        span = 1.0 - 2 * margin
        targets = [(margin + i / max(n - 1, 1) * span, ay) for i in range(n)]
        result = [_shift(ins, tx - ax, 0.0) for tx, _ in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    if arr.layout == "vertical":
        if arr.path != "none":
            targets = [_path_pos(i, n, seed, margin, arr.path) for i in range(n)]
            result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
            return _apply_color_cycle(result, arr.color_cycle)
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
        targets = [_path_pos(i, n, seed, margin, arr.path) for i in range(n)]
        result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    return _apply_color_cycle([ins], arr.color_cycle)


def _inject_blur_filters(
    svg: str,
    blur_needed: dict[str, float],
    blur_elems: list[tuple[str, str]],
) -> str:
    """feGaussianBlur フィルター定義を defs に注入し、対象要素に filter 属性を付与する。"""
    filter_xml = "".join(
        f'<filter id="blur-{amp}" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feGaussianBlur in="SourceGraphic" stdDeviation="{std:.1f}"/>'
        f'</filter>'
        for amp, std in sorted(blur_needed.items())
    )
    # svgwrite は "<defs />" を出力する (スペースあり)
    if "<defs />" in svg:
        svg = svg.replace("<defs />", f"<defs>{filter_xml}</defs>", 1)
    elif "<defs/>" in svg:
        svg = svg.replace("<defs/>", f"<defs>{filter_xml}</defs>", 1)
    else:
        svg = svg.replace("<defs>", f"<defs>{filter_xml}", 1)

    for eid, amp in blur_elems:
        svg = svg.replace(f'id="{eid}"', f'id="{eid}" filter="url(#blur-{amp})"', 1)
    return svg


def _inject_texture_filters(svg: str, filters: set[str]) -> str:
    if not filters:
        return svg
    filter_xml = "".join(TEXTURE_FILTERS[weight] for weight in sorted(filters))
    if "<defs />" in svg:
        return svg.replace("<defs />", f"<defs>{filter_xml}</defs>", 1)
    if "<defs/>" in svg:
        return svg.replace("<defs/>", f"<defs>{filter_xml}</defs>", 1)
    return svg.replace("<defs>", f"<defs>{filter_xml}", 1)


def render(score: Score, color_map: dict[str, str] | None = None) -> str:
    cmap = {**COLOR_MAP, **(color_map or {})}
    dwg = svgwrite.Drawing(
        size=(CANVAS_PX, CANVAS_PX),
        viewBox=f"0 0 {CANVAS_PX} {CANVAS_PX}",
    )
    bg = cmap.get(score.background, BACKGROUND)
    dwg.add(dwg.rect(insert=(0, 0), size=(CANVAS_PX, CANVAS_PX), fill=bg))
    clip_id = "canvas-clip"
    clip = dwg.defs.add(dwg.clipPath(id=clip_id))
    clip.add(dwg.rect(insert=(0, 0), size=(CANVAS_PX, CANVAS_PX)))
    content = dwg.g(clip_path=f"url(#{clip_id})")

    blur_needed: dict[str, float] = {}
    texture_filters = _texture_filter_weights(score)
    blur_elems: list[tuple[str, str]] = []
    elem_idx = 0

    for ins in score.instructions:
        expanded = _expand_arrangement(ins) if ins.arrangement else [ins]
        for single in expanded:
            element = _render_instruction(dwg, single, cmap)
            if element is not None:
                if _needs_blur(single.variation):
                    v = single.variation
                    assert v is not None
                    blur_needed[v.amplitude] = BLUR_STD[v.amplitude]
                    eid = f"e{elem_idx}"
                    element["id"] = eid
                    blur_elems.append((eid, v.amplitude))
                content.add(element)
            elem_idx += 1

    dwg.add(content)
    svg = dwg.tostring()
    svg = _inject_texture_filters(svg, texture_filters)
    if blur_elems:
        svg = _inject_blur_filters(svg, blur_needed, blur_elems)
    return svg


_CLOSED_SHAPES = frozenset({"circle", "ellipse", "square", "triangle"})


def _texture_filter_weights(score: Score) -> set[str]:
    weights: set[str] = set()
    for ins in score.instructions:
        if ins.weight in TEXTURE_FILTERS:
            weights.add(ins.weight)
    return weights


def _norm_label(value: str) -> str:
    return re.sub(r"[\s:_()'\".,/-]+", " ", value.lower()).strip()


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not m:
        return None
    raw = m.group(1)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _hue_from_hex(value: str) -> str | None:
    rgb = _hex_to_rgb(value)
    if rgb is None:
        return None
    r, g, b = [c / 255 for c in rgb]
    mx = max(r, g, b)
    mn = min(r, g, b)
    lightness = (mx + mn) / 2
    if mx - mn < 0.08:
        if lightness > 0.82:
            return "white"
        if lightness < 0.2:
            return "black"
        return "gray"
    if mx == r:
        hue = (60 * ((g - b) / (mx - mn)) + 360) % 360
    elif mx == g:
        hue = 60 * ((b - r) / (mx - mn)) + 120
    else:
        hue = 60 * ((r - g) / (mx - mn)) + 240
    if 15 <= hue < 45:
        return "orange"
    if 45 <= hue < 75:
        return "yellow"
    if 75 <= hue < 165:
        return "green"
    if 165 <= hue < 255:
        return "blue"
    if 255 <= hue < 315:
        return "purple"
    return "red"


def _hint_hues(hint: str) -> set[str]:
    normalized = _norm_label(hint)
    hues: set[str] = set()
    for hue, tokens in HUE_HINTS.items():
        if any(token.lower() in normalized or token in hint for token in tokens):
            hues.add(hue)
    return hues


def _resolve_color(color: str, color_hint: str | None, cmap: dict[str, str]) -> str:
    fallback = cmap[color]
    if not color_hint:
        return fallback

    hint = _norm_label(color_hint)
    desired_hues = _hint_hues(color_hint)
    if not hint and not desired_hues:
        return fallback

    best_score = 0
    best_hex = fallback
    for key, hex_value in cmap.items():
        if not isinstance(hex_value, str) or not hex_value.startswith("#"):
            continue
        is_palette = key.startswith("palette:")
        label = _norm_label(key.removeprefix("palette:"))
        score = 0
        if label and label in hint:
            score += 6
        for part in label.split():
            if len(part) >= 3 and part in hint:
                score += 3
        candidate_hue = _hue_from_hex(hex_value)
        if candidate_hue in desired_hues:
            score += 4
        for hue in desired_hues:
            if is_palette and any(token.lower() in label for token in HUE_HINTS[hue]):
                score += 2
        if is_palette and score > 0:
            score += 1
        if key == color:
            score += 1
        if score > best_score:
            best_score = score
            best_hex = hex_value

    return best_hex


def _stroke_attrs(ins: Instruction, cmap: dict[str, str]) -> dict:
    do_fill = ins.primitive in _CLOSED_SHAPES or ins.filled
    color = _resolve_color(ins.color, ins.color_hint, cmap)
    weight_style = WEIGHT_STYLE.get(ins.weight, {})
    attrs = {
        "stroke": color,
        "stroke_width": WEIGHT_TO_STROKE_WIDTH[ins.weight],
        "fill": color if do_fill else "none",
        "stroke_linecap": weight_style.get("stroke_linecap", "round"),
    }
    if "stroke_opacity" in weight_style:
        attrs["stroke_opacity"] = weight_style["stroke_opacity"]
    if ins.weight in TEXTURE_FILTERS:
        attrs["filter"] = f"url(#texture-{ins.weight})"
    dash = STYLE_TO_DASH[ins.style]
    texture_dash = weight_style.get("stroke_dasharray")
    if dash:
        attrs["stroke_dasharray"] = dash
    elif texture_dash:
        attrs["stroke_dasharray"] = texture_dash
    return attrs


def _copy_attrs(attrs: dict) -> dict:
    return dict(attrs)


def _line_perp_offsets(start: tuple[float, float], end: tuple[float, float], amount: float) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 0.0, 0.0
    return -dy / length * amount, dx / length * amount


def _point_on_line(start: tuple[float, float], end: tuple[float, float], t: float) -> tuple[float, float]:
    return (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)


def _line_direction(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 1.0, 0.0
    return dx / length, dy / length


def _add_powder_specks(
    dwg: svgwrite.Drawing,
    group,
    start: tuple[float, float],
    end: tuple[float, float],
    attrs: dict,
    seed: int,
    *,
    count: int,
    spread: float,
    radius: float,
    opacity: float,
) -> None:
    color = attrs.get("stroke", "#111111")
    for idx in range(count):
        t = (idx + 0.5) / count
        px, py = _point_on_line(start, end, t)
        ox, oy = _line_perp_offsets(start, end, _hash_to_unit(idx, seed) * spread)
        along = _hash_to_unit(idx + 101, seed) * spread * 0.45
        ux, uy = _line_direction(start, end)
        group.add(
            dwg.circle(
                center=(px + ox + ux * along, py + oy + uy * along),
                r=max(0.35, radius * (0.75 + abs(_hash_to_unit(idx + 202, seed)) * 0.7)),
                fill=color,
                stroke="none",
                opacity=opacity,
            )
        )


def _add_specks_at_points(
    dwg: svgwrite.Drawing,
    group,
    points: list[tuple[float, float]],
    attrs: dict,
    seed: int,
    *,
    spread: float,
    radius: float,
    opacity: float,
) -> None:
    color = attrs.get("stroke", "#111111")
    for idx, (px, py) in enumerate(points):
        ox = _hash_to_unit(idx, seed) * spread
        oy = _hash_to_unit(idx + 157, seed) * spread
        group.add(
            dwg.circle(
                center=(px + ox, py + oy),
                r=max(0.35, radius * (0.75 + abs(_hash_to_unit(idx + 263, seed)) * 0.7)),
                fill=color,
                stroke="none",
                opacity=opacity,
            )
        )


def _circle_points(cx: float, cy: float, rx: float, ry: float, count: int) -> list[tuple[float, float]]:
    return [
        (
            cx + math.cos(i * 2 * math.pi / count) * rx,
            cy + math.sin(i * 2 * math.pi / count) * ry,
        )
        for i in range(count)
    ]


def _rect_points(x: float, y: float, w: float, h: float, count: int) -> list[tuple[float, float]]:
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


def _arc_points(cx: float, cy: float, r: float, start_deg: float, end_deg: float, count: int) -> list[tuple[float, float]]:
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


def _outline_attrs(attrs: dict, *, stroke_width: float, opacity: float, dash: str | None = None) -> dict:
    result = _copy_attrs(attrs)
    result["fill"] = "none"
    result["stroke_width"] = stroke_width
    result["stroke_opacity"] = opacity
    if dash is not None:
        result["stroke_dasharray"] = dash
    return result


def _add_rope_twists(
    dwg: svgwrite.Drawing,
    group,
    start: tuple[float, float],
    end: tuple[float, float],
    attrs: dict,
    seed: int,
) -> None:
    ux, uy = _line_direction(start, end)
    px, py = -uy, ux
    color = attrs.get("stroke", "#111111")
    for idx in range(13):
        t = (idx + 0.5) / 13
        cx, cy = _point_on_line(start, end, t)
        phase = -1 if idx % 2 else 1
        span = 8.0 + abs(_hash_to_unit(idx, seed)) * 2.5
        half_u = 3.0
        p1 = (cx - ux * half_u + px * span * phase, cy - uy * half_u + py * span * phase)
        p2 = (cx + ux * half_u - px * span * phase, cy + uy * half_u - py * span * phase)
        group.add(
            dwg.line(
                start=p1,
                end=p2,
                stroke=color,
                stroke_width=1.2,
                stroke_opacity=0.42,
                stroke_linecap="round",
            )
        )


def _material_outline_profile(weight: str, base_width: float) -> list[tuple[float, float, float, str | None]]:
    if weight == "pencil":
        return [(-1.0, 0.45, 0.24, "1,7"), (1.2, 0.5, 0.20, "1,5")]
    if weight == "chalk":
        return [(-3.2, 1.2, 0.30, "8,12,1,8"), (3.6, 1.0, 0.24, "5,10,1,6")]
    if weight == "brush_thin":
        return [(-1.6, 1.0, 0.32, "22,9"), (1.8, 1.4, 0.28, "14,8")]
    if weight == "brush_thick":
        return [(-4.0, base_width * 0.28, 0.36, "18,7,3,11"), (3.2, base_width * 0.22, 0.28, "11,9")]
    if weight == "crayon":
        return [(-3.4, base_width * 0.24, 0.24, "2,5,9,7"), (-1.5, base_width * 0.20, 0.20, "4,8"), (2.4, base_width * 0.22, 0.22, "2,5,9,7")]
    if weight == "rope":
        return [(-5.0, base_width * 0.35, 0.46, "4,8"), (5.0, base_width * 0.35, 0.46, "4,8")]
    return []


def _speck_profile(weight: str) -> tuple[int, float, float, float] | None:
    if weight == "pencil":
        return 18, 1.8, 0.45, 0.20
    if weight == "crayon":
        return 28, 4.0, 0.75, 0.18
    if weight == "chalk":
        return 36, 5.5, 0.9, 0.26
    return None


def _uses_material_outline(weight: str) -> bool:
    return bool(_material_outline_profile(weight, WEIGHT_TO_STROKE_WIDTH[weight])) or _speck_profile(weight) is not None


def _add_material_circle_outline(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    attrs: dict,
    cx: float,
    cy: float,
    r: float,
) -> None:
    seed = _seed_for_instruction(ins)
    for offset, width, opacity, dash in _material_outline_profile(ins.weight, WEIGHT_TO_STROKE_WIDTH[ins.weight]):
        group.add(dwg.circle(center=(cx, cy), r=max(0.0, r + offset), **_outline_attrs(attrs, stroke_width=width, opacity=opacity, dash=dash)))
    if ins.weight == "rope":
        for idx, (px, py) in enumerate(_circle_points(cx, cy, r, 16)):
            angle = math.atan2(py - cy, px - cx)
            tangent = (-math.sin(angle), math.cos(angle))
            normal = (math.cos(angle), math.sin(angle))
            span = 6.0 + abs(_hash_to_unit(idx, seed)) * 2.0
            p1 = (px + tangent[0] * 3.0 + normal[0] * span, py + tangent[1] * 3.0 + normal[1] * span)
            p2 = (px - tangent[0] * 3.0 - normal[0] * span, py - tangent[1] * 3.0 - normal[1] * span)
            group.add(dwg.line(start=p1, end=p2, stroke=attrs.get("stroke", "#111111"), stroke_width=1.1, stroke_opacity=0.40, stroke_linecap="round"))
    specks = _speck_profile(ins.weight)
    if specks is not None:
        count, spread, radius, opacity = specks
        _add_specks_at_points(dwg, group, _circle_points(cx, cy, r, r, count), attrs, seed, spread=spread, radius=radius, opacity=opacity)


def _add_material_ellipse_outline(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    attrs: dict,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
) -> None:
    seed = _seed_for_instruction(ins)
    for offset, width, opacity, dash in _material_outline_profile(ins.weight, WEIGHT_TO_STROKE_WIDTH[ins.weight]):
        group.add(
            dwg.ellipse(
                center=(cx, cy),
                r=(max(0.0, rx + offset), max(0.0, ry + offset)),
                **_outline_attrs(attrs, stroke_width=width, opacity=opacity, dash=dash),
            )
        )
    specks = _speck_profile(ins.weight)
    if specks is not None:
        count, spread, radius, opacity = specks
        _add_specks_at_points(dwg, group, _circle_points(cx, cy, rx, ry, count), attrs, seed, spread=spread, radius=radius, opacity=opacity)


def _add_material_rect_outline(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    attrs: dict,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    seed = _seed_for_instruction(ins)
    for offset, width, opacity, dash in _material_outline_profile(ins.weight, WEIGHT_TO_STROKE_WIDTH[ins.weight]):
        group.add(
            dwg.rect(
                insert=(x - offset, y - offset),
                size=(max(0.0, w + offset * 2), max(0.0, h + offset * 2)),
                **_outline_attrs(attrs, stroke_width=width, opacity=opacity, dash=dash),
            )
        )
    specks = _speck_profile(ins.weight)
    if specks is not None:
        count, spread, radius, opacity = specks
        _add_specks_at_points(dwg, group, _rect_points(x, y, w, h, count), attrs, seed, spread=spread, radius=radius, opacity=opacity)


def _add_material_arc_outline(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    attrs: dict,
    cx: float,
    cy: float,
    r: float,
    start_deg: float,
    end_deg: float,
) -> None:
    seed = _seed_for_instruction(ins)
    for offset, width, opacity, dash in _material_outline_profile(ins.weight, WEIGHT_TO_STROKE_WIDTH[ins.weight]):
        group.add(
            dwg.path(
                d=_arc_path_d(cx, cy, max(0.0, r + offset), start_deg, end_deg),
                **_outline_attrs(attrs, stroke_width=width, opacity=opacity, dash=dash),
            )
        )
    specks = _speck_profile(ins.weight)
    if specks is not None:
        count, spread, radius, opacity = specks
        _add_specks_at_points(dwg, group, _arc_points(cx, cy, r, start_deg, end_deg, count), attrs, seed, spread=spread, radius=radius, opacity=opacity)


def _material_line_group(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    start: tuple[float, float],
    end: tuple[float, float],
    attrs: dict,
):
    if ins.weight not in ("pencil", "crayon", "chalk", "brush_thin", "brush_thick", "rope"):
        return None

    group = dwg.g()
    base = _copy_attrs(attrs)
    group.add(dwg.line(start=start, end=end, **base))
    seed = _seed_for_instruction(ins)

    if ins.weight == "pencil":
        for idx, amount in enumerate((-0.9, 1.1)):
            ox, oy = _line_perp_offsets(start, end, amount)
            layer_attrs = _copy_attrs(attrs)
            layer_attrs["stroke_width"] = 0.45
            layer_attrs["stroke_opacity"] = 0.26
            layer_attrs["stroke_dasharray"] = "1,7"
            layer_attrs["filter"] = "url(#texture-pencil)"
            jitter = _hash_to_unit(idx, seed) * 0.6
            group.add(
                dwg.line(
                    start=(start[0] + ox + jitter, start[1] + oy),
                    end=(end[0] + ox - jitter, end[1] + oy),
                    **layer_attrs,
                )
            )
        _add_powder_specks(dwg, group, start, end, attrs, seed, count=18, spread=1.8, radius=0.45, opacity=0.20)
    elif ins.weight == "chalk":
        for idx, amount in enumerate((-3.0, 3.4)):
            ox, oy = _line_perp_offsets(start, end, amount)
            layer_attrs = _copy_attrs(attrs)
            layer_attrs["stroke_width"] = 1.1
            layer_attrs["stroke_opacity"] = 0.28
            layer_attrs["stroke_dasharray"] = "8,12,1,8"
            jitter = _hash_to_unit(idx, seed) * 1.4
            group.add(
                dwg.line(
                    start=(start[0] + ox + jitter, start[1] + oy),
                    end=(end[0] + ox - jitter, end[1] + oy),
                    **layer_attrs,
                )
            )
        _add_powder_specks(dwg, group, start, end, attrs, seed, count=34, spread=5.5, radius=0.9, opacity=0.26)
    elif ins.weight == "brush_thin":
        for idx, amount in enumerate((-1.4, 1.8)):
            ox, oy = _line_perp_offsets(start, end, amount)
            layer_attrs = _copy_attrs(attrs)
            layer_attrs["stroke_width"] = 0.9 + idx * 0.5
            layer_attrs["stroke_opacity"] = 0.32
            layer_attrs["stroke_dasharray"] = "22,9"
            jitter = _hash_to_unit(idx, seed) * 1.1
            group.add(
                dwg.line(
                    start=(start[0] + ox + jitter, start[1] + oy),
                    end=(end[0] + ox - jitter, end[1] + oy),
                    **layer_attrs,
                )
            )
    elif ins.weight == "rope":
        ox, oy = _line_perp_offsets(start, end, 4.0)
        twist_attrs = _copy_attrs(attrs)
        twist_attrs["stroke_width"] = max(1.0, WEIGHT_TO_STROKE_WIDTH[ins.weight] * 0.35)
        twist_attrs["stroke_opacity"] = 0.55
        twist_attrs["stroke_dasharray"] = "4,8"
        group.add(dwg.line(start=(start[0] + ox, start[1] + oy), end=(end[0] + ox, end[1] + oy), **twist_attrs))
        group.add(dwg.line(start=(start[0] - ox, start[1] - oy), end=(end[0] - ox, end[1] - oy), **twist_attrs))
        _add_rope_twists(dwg, group, start, end, attrs, seed)
    else:
        amounts = (-3.2, -1.4, 2.0, 3.6) if ins.weight == "crayon" else (-3.5, 2.8, 5.0)
        for idx, amount in enumerate(amounts):
            ox, oy = _line_perp_offsets(start, end, amount)
            jitter = _hash_to_unit(idx, seed) * (2.2 if ins.weight == "crayon" else 2.8)
            layer_attrs = _copy_attrs(attrs)
            layer_attrs["stroke_width"] = max(0.8, WEIGHT_TO_STROKE_WIDTH[ins.weight] * (0.25 if ins.weight == "crayon" else 0.30))
            layer_attrs["stroke_opacity"] = 0.24 if ins.weight == "crayon" else 0.38
            layer_attrs["stroke_dasharray"] = "2,5,9,7" if ins.weight == "crayon" else "18,7,3,11"
            group.add(
                dwg.line(
                    start=(start[0] + ox + jitter, start[1] + oy),
                    end=(end[0] + ox - jitter, end[1] + oy),
                    **layer_attrs,
                )
            )
        if ins.weight == "crayon":
            _add_powder_specks(dwg, group, start, end, attrs, seed, count=26, spread=4.0, radius=0.75, opacity=0.18)
    return _apply_rotation(group, ins)


def _px(coord: tuple[float, float]) -> tuple[float, float]:
    x, y = coord
    return x * CANVAS_PX, y * CANVAS_PX


def _apply_rotation(element, ins: Instruction):
    if ins.rotation is None or abs(ins.rotation) < 1e-9:
        return element
    cx, cy = _px(_anchor(ins))
    element.rotate(ins.rotation, center=(cx, cy))
    return element


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


def _render_instruction(dwg: svgwrite.Drawing, ins: Instruction, cmap: dict[str, str] = COLOR_MAP):
    attrs = _stroke_attrs(ins, cmap)

    if ins.primitive == "line":
        start = _px(ins.from_ if ins.from_ is not None else (0.5, 0.0))
        end = _px(ins.to if ins.to is not None else (0.5, 1.0))
        if _needs_path_variation(ins.variation):
            assert ins.variation is not None
            points = _line_with_variation(
                start, end, ins.variation, _seed_for_instruction(ins)
            )
            return _apply_rotation(dwg.polyline(points=points, **attrs), ins)
        textured = _material_line_group(dwg, ins, start, end, attrs)
        if textured is not None:
            return textured
        return _apply_rotation(dwg.line(start=start, end=end, **attrs), ins)

    if ins.primitive == "circle":
        if ins.center is None or ins.radius is None:
            raise ValueError("circle requires 'center' and 'radius'")
        cx, cy = _px(ins.center)
        r = ins.radius * CANVAS_PX
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(dwg.circle(center=(cx, cy), r=r, **attrs))
            _add_material_circle_outline(dwg, group, ins, attrs, cx, cy, r)
            return _apply_rotation(group, ins)
        return _apply_rotation(dwg.circle(center=(cx, cy), r=r, **attrs), ins)

    if ins.primitive == "ellipse":
        if ins.center is None or ins.size is None:
            raise ValueError("ellipse requires 'center' and 'size'")
        cx, cy = _px(ins.center)
        rx = ins.size[0] * CANVAS_PX / 2
        ry = ins.size[1] * CANVAS_PX / 2
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(dwg.ellipse(center=(cx, cy), r=(rx, ry), **attrs))
            _add_material_ellipse_outline(dwg, group, ins, attrs, cx, cy, rx, ry)
            return _apply_rotation(group, ins)
        return _apply_rotation(dwg.ellipse(center=(cx, cy), r=(rx, ry), **attrs), ins)

    if ins.primitive == "square":
        if ins.position is None or ins.size is None:
            raise ValueError("square requires 'position' and 'size'")
        x, y = _px(ins.position)
        w = ins.size[0] * CANVAS_PX
        h = ins.size[1] * CANVAS_PX
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(dwg.rect(insert=(x, y), size=(w, h), **attrs))
            _add_material_rect_outline(dwg, group, ins, attrs, x, y, w, h)
            return _apply_rotation(group, ins)
        return _apply_rotation(dwg.rect(insert=(x, y), size=(w, h), **attrs), ins)

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
        return _apply_rotation(dwg.polygon(points=points, **attrs), ins)

    if ins.primitive == "arc":
        if ins.center is None or ins.radius is None:
            raise ValueError("arc requires 'center' and 'radius'")
        if ins.angle_start is None or ins.angle_end is None:
            raise ValueError("arc requires 'angle_start' and 'angle_end'")
        cx, cy = _px(ins.center)
        r = ins.radius * CANVAS_PX
        path_d = _arc_path_d(cx, cy, r, ins.angle_start, ins.angle_end)
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(dwg.path(d=path_d, **attrs))
            _add_material_arc_outline(dwg, group, ins, attrs, cx, cy, r, ins.angle_start, ins.angle_end)
            return _apply_rotation(group, ins)
        return _apply_rotation(dwg.path(d=path_d, **attrs), ins)

    raise NotImplementedError(f"primitive '{ins.primitive}' not yet supported")
