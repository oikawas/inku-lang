"""JSON Score → SVG renderer.

楽譜(Score)を演奏(SVG)に変換する。揺らぎ(variation)の実現は Renderer 層で行う
(SPEC §13.8)。Phase 1 は静的描画のみ、perlin/wave は段階追加。
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import re
import struct
from xml.sax.saxutils import escape

import svgwrite

from .plugins import CanvasSize, canvas_size_for_aspect
from .schema import CanvasGroundSpec, CanvasSpec, Instruction, Score, SurfaceSpec, Variation

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

SVG_PROFILES = frozenset({"display", "editable", "compat"})

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


def _seed_for_instruction(ins: Instruction, performance_seed: int | None = None) -> int:
    """Instruction と演奏 seed から安定した乱数 seed を作る。"""
    key = ins.model_dump_json().encode("utf-8")
    if performance_seed is not None:
        key += f":render:{performance_seed}".encode("utf-8")
    digest = hashlib.sha256(key).digest()
    return struct.unpack("<Q", digest[:8])[0]


def new_render_seed() -> int:
    """演奏ごとのマクロ揺らぎ seed。明示 seed 指定時は再現可能。"""
    return secrets.randbits(53)


def _performance_touch_filter(render_seed: int) -> tuple[str, str]:
    """固定図形にも seed ごとの微細な輪郭差を与える display 用 filter。"""
    seed = int(render_seed)
    filter_id = _safe_svg_id(f"performance_touch_{seed % 100000}")
    frequency = 0.012 + _hash01(0, seed, "performance-touch-frequency") * 0.008
    scale = 1.6 + _hash01(1, seed, "performance-touch-scale") * 1.4
    xml = (
        f'<filter id="{filter_id}" x="-2%" y="-2%" width="104%" height="104%" color-interpolation-filters="sRGB">'
        f'<feTurbulence type="fractalNoise" baseFrequency="{frequency:.5f}" numOctaves="2" '
        f'seed="{seed % 9973}" result="touchNoise"/>'
        f'<feDisplacementMap in="SourceGraphic" in2="touchNoise" scale="{scale:.2f}" '
        'xChannelSelector="R" yChannelSelector="G"/>'
        '</filter>'
    )
    return filter_id, xml


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


def _rhythm_t(i: int, n: int, seed: int, rhythm_spacing: str) -> float:
    """Return deterministic non-linear spacing for repeated arrangements."""
    if n <= 1:
        return 0.0
    base = i / (n - 1)
    if rhythm_spacing == "accelerando":
        return base ** 1.35
    if rhythm_spacing == "loose":
        jitter = (_hash01(i, seed, "rhythm-loose") - 0.5) * 0.16
        return _clamp01(base + jitter)
    if rhythm_spacing == "syncopated":
        beat = 0.09 if i % 2 else -0.045
        taper = math.sin(base * math.pi)
        return _clamp01(base + beat * taper)
    return base


def _path_pos(
    i: int,
    n: int,
    seed: int,
    margin: float,
    path: str,
    rhythm_spacing: str = "none",
) -> tuple[float, float]:
    span = 1.0 - 2 * margin
    t = _rhythm_t(i, n, seed, rhythm_spacing)
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
) -> tuple[float, float]:
    """大数量の配置を、均一散布ではなく複数のまとまりとして決定的に配置する。

    クラスタ内部を円周状に並べると、異なる絵に同じ輪状の記号が現れやすい。
    そのため、内部配置はパス方向を持つ短い帯として広げる。
    """
    cluster_count = max(1, min(cluster_count, n))
    cluster_index = i % cluster_count
    local_index = i // cluster_count
    local_total = max(1, math.ceil(n / cluster_count))
    center_margin = max(margin, 0.20 if preserve_space else margin)
    if path == "none":
        cx, cy = _scatter_pos(cluster_index, seed ^ 0xC1A57, center_margin)
    else:
        cx, cy = _path_pos(cluster_index, cluster_count, seed ^ 0xC1A57, center_margin, path, rhythm_spacing)

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
        local_t = _rhythm_t(local_index, local_total, seed ^ cluster_index, rhythm_spacing)
    centered = (local_t - 0.5) * 2.0
    radius = _density_radius(density, preserve_space)
    long_span = radius * (1.45 + _hash01(cluster_index, seed, "cluster-long") * 0.95)
    cross_span = radius * (0.28 + _hash01(cluster_index, seed, "cluster-cross") * 0.32)
    along = centered * long_span + (_hash01(i, seed, "cluster-along") - 0.5) * radius * 0.20
    cross = (_hash01(i, seed, "cluster-cross-jitter") - 0.5) * cross_span * (1.25 - 0.45 * abs(centered))
    bend = math.sin(local_t * math.pi) * (_hash01(cluster_index, seed, "cluster-bend") - 0.5) * radius * 0.55
    x = cx + tx * along + nx * (cross + bend)
    y = cy + ty * along + ny * (cross + bend)
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
    if ins.primitive in ("circle", "ellipse", "arc", "polygon") and ins.center:
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
    elif ins.primitive in ("circle", "ellipse", "arc", "polygon") and ins.center:
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


def _move_anchor_to(ins: Instruction, target: tuple[float, float]) -> Instruction:
    ax, ay = _anchor(ins)
    data = ins.model_dump(by_alias=True)
    data.pop("at", None)
    data.pop("relation", None)
    dx = target[0] - ax
    dy = target[1] - ay
    if ins.primitive == "line" and ins.from_ and ins.to:
        data["from"] = [_clamp01(ins.from_[0] + dx), _clamp01(ins.from_[1] + dy)]
        data["to"] = [_clamp01(ins.to[0] + dx), _clamp01(ins.to[1] + dy)]
    elif ins.primitive in ("circle", "ellipse", "arc", "polygon"):
        if ins.center:
            data["center"] = [_clamp01(ins.center[0] + dx), _clamp01(ins.center[1] + dy)]
        else:
            data["center"] = [_clamp01(target[0]), _clamp01(target[1])]
    elif ins.primitive in ("square", "triangle"):
        if ins.position:
            data["position"] = [_clamp01(ins.position[0] + dx), _clamp01(ins.position[1] + dy)]
        else:
            size = ins.size or (0.2, 0.2)
            data["size"] = list(size)
            data["position"] = [_clamp01(target[0] - size[0] / 2), _clamp01(target[1] - size[1] / 2)]
    return Instruction.model_validate(data)


def _resolve_at_region(ins: Instruction, seed: int, index: int) -> Instruction:
    if ins.at is None:
        return ins
    x0, y0, x1, y1 = ins.at.region
    x = x0 + (x1 - x0) * _hash01(index, seed, "region-x")
    y = y0 + (y1 - y0) * _hash01(index, seed, "region-y")
    return _move_anchor_to(ins, (x, y))


def _bbox_for_instruction(ins: Instruction) -> tuple[float, float, float, float] | None:
    if ins.primitive == "line" and ins.from_ and ins.to:
        return (min(ins.from_[0], ins.to[0]), min(ins.from_[1], ins.to[1]), max(ins.from_[0], ins.to[0]), max(ins.from_[1], ins.to[1]))
    if ins.primitive in ("circle", "arc", "polygon") and ins.center and ins.radius is not None:
        return (ins.center[0] - ins.radius, ins.center[1] - ins.radius, ins.center[0] + ins.radius, ins.center[1] + ins.radius)
    if ins.primitive == "ellipse" and ins.center and ins.size:
        return (ins.center[0] - ins.size[0] / 2, ins.center[1] - ins.size[1] / 2, ins.center[0] + ins.size[0] / 2, ins.center[1] + ins.size[1] / 2)
    if ins.primitive in ("square", "triangle") and ins.position and ins.size:
        return (ins.position[0], ins.position[1], ins.position[0] + ins.size[0], ins.position[1] + ins.size[1])
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


def _resolve_relation(ins: Instruction, previous: list[Instruction], seed: int, index: int) -> Instruction:
    rel = ins.relation
    if rel is None:
        return _strip_performance_fields(ins)
    if rel.type == "between" and len(previous) < 2:
        return _strip_performance_fields(ins)
    if rel.type != "between" and not previous:
        return _strip_performance_fields(ins)
    prev_bbox = _bbox_for_instruction(previous[-1]) if previous else None
    if prev_bbox is None:
        return _strip_performance_fields(ins)
    prev_center = _bbox_center(prev_bbox)
    prev_radius = _bbox_radius(prev_bbox)
    gap = _relation_gap(seed, index, rel.gap)

    if rel.type == "between":
        other_bbox = _bbox_for_instruction(previous[-2])
        if other_bbox is None:
            return _strip_performance_fields(ins)
        other_center = _bbox_center(other_bbox)
        jitter = 0.08 * (_hash01(index, seed, "between-jitter") - 0.5)
        target = (_clamp01((prev_center[0] + other_center[0]) / 2 + jitter), _clamp01((prev_center[1] + other_center[1]) / 2 - jitter))
    elif rel.type == "along":
        if previous[-1].primitive == "line" and previous[-1].from_ and previous[-1].to:
            t = 0.18 + 0.64 * _hash01(index, seed, "along-t")
            x, y = _point_on_line(previous[-1].from_, previous[-1].to, t)
            ox, oy = _line_perp_offsets(previous[-1].from_, previous[-1].to, gap)
            side = -1.0 if _hash01(index, seed, "along-side") < 0.5 else 1.0
            target = (_clamp01(x + ox * side), _clamp01(y + oy * side))
        else:
            angle = math.tau * _hash01(index, seed, "along-angle")
            target = (_clamp01(prev_center[0] + math.cos(angle) * (prev_radius + gap)), _clamp01(prev_center[1] + math.sin(angle) * (prev_radius + gap)))
    elif rel.type == "cutting":
        target = prev_center
        if ins.primitive == "line":
            angle = math.tau * _hash01(index, seed, "cut-angle")
            length = 0.28 + 0.18 * _hash01(index, seed, "cut-length")
            data = ins.model_dump(by_alias=True)
            data.pop("relation", None)
            data.pop("at", None)
            data["from"] = [_clamp01(target[0] - math.cos(angle) * length / 2), _clamp01(target[1] - math.sin(angle) * length / 2)]
            data["to"] = [_clamp01(target[0] + math.cos(angle) * length / 2), _clamp01(target[1] + math.sin(angle) * length / 2)]
            return Instruction.model_validate(data)
    else:
        own_bbox = _bbox_for_instruction(ins)
        own_radius = _bbox_radius(own_bbox) if own_bbox is not None else 0.0
        distance = prev_radius + own_radius + gap
        angle = math.tau * _hash01(index, seed, "not-touching-angle")
        target = (_clamp01(prev_center[0] + math.cos(angle) * distance), _clamp01(prev_center[1] + math.sin(angle) * distance))
    return _move_anchor_to(ins, target)


def _resolve_performance_score(score: Score, performance_seed: int | None) -> Score:
    if performance_seed is None:
        return score
    resolved: list[Instruction] = []
    seed = int(performance_seed)
    for index, original in enumerate(score.instructions):
        ins = _ensure_line_coords(original)
        ins = _resolve_at_region(ins, seed, index)
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
        "membrane", "haze", "fog", "mist", "atmosphere", "膜", "霞", "霧", "靄",
        "soft light", "柔らかな光", "陽光", "日差し",
        "scent", "fragrance", "香り", "匂",
        "waiting buds", "開花を待つ蕾", "蕾", "つぼみ",
        "five-sense", "五感",
        "fade directional", "fade=directional", "fade outward", "fade=outward",
        "reflection", "反射", "映り",
    )
    kept = [token for token in effect_tokens if token in hint]
    return "; ".join(kept) if kept else None


def _expand_arrangement(ins: Instruction, performance_seed: int | None = None) -> list[Instruction]:
    """arrangement を展開して N 個の Instruction を返す。"""
    arr = ins.arrangement
    assert arr is not None
    ins = _ensure_line_coords(ins)
    if arr.count == 1:
        data = ins.model_dump(by_alias=True)
        data.pop("arrangement", None)
        return _apply_color_cycle([Instruction.model_validate(data)], arr.color_cycle)
    n = arr.count
    margin = max(arr.margin, 0.20) if arr.preserve_space else arr.margin
    ax, ay = _anchor(ins)
    seed = _seed_for_instruction(ins, performance_seed)
    cluster_count = arr.cluster_count or 0

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
            )
            for i in range(n)
        ]
        result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    if arr.layout == "horizontal":
        if arr.path != "none":
            targets = [_path_pos(i, n, seed, margin, arr.path, arr.rhythm_spacing) for i in range(n)]
            result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
            return _apply_color_cycle(result, arr.color_cycle)
        span = 1.0 - 2 * margin
        targets = [(margin + _rhythm_t(i, n, seed, arr.rhythm_spacing) * span, ay) for i in range(n)]
        result = [_shift(ins, tx - ax, 0.0) for tx, _ in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    if arr.layout == "vertical":
        if arr.path != "none":
            targets = [_path_pos(i, n, seed, margin, arr.path, arr.rhythm_spacing) for i in range(n)]
            result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
            return _apply_color_cycle(result, arr.color_cycle)
        span = 1.0 - 2 * margin
        targets = [(ax, margin + _rhythm_t(i, n, seed, arr.rhythm_spacing) * span) for i in range(n)]
        result = [_shift(ins, 0.0, ty - ay) for _, ty in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    if arr.layout == "radial":
        cx = arr.center[0] if arr.center else 0.5
        cy = arr.center[1] if arr.center else 0.5
        r = arr.radius if arr.radius else 0.3
        targets = [
            (
                cx + r * math.cos(math.radians(_rhythm_t(i, n, seed, arr.rhythm_spacing) * 360)),
                cy - r * math.sin(math.radians(_rhythm_t(i, n, seed, arr.rhythm_spacing) * 360)),
            )
            for i in range(n)
        ]
        result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
        return _apply_color_cycle(result, arr.color_cycle)

    if arr.layout == "scatter":
        targets = [_path_pos(i, n, seed, margin, arr.path, arr.rhythm_spacing) for i in range(n)]
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
        id_start = svg.find(f'id="{eid}"')
        if id_start < 0:
            continue
        tag_start = svg.rfind("<", 0, id_start)
        tag_end = svg.find(">", id_start)
        if tag_start < 0 or tag_end < 0:
            continue
        if ' filter="' in svg[tag_start:tag_end]:
            continue
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



def _score_canvas_aspect(score: Score) -> str:
    if isinstance(score.canvas, CanvasSpec):
        return score.canvas.aspect
    return str(score.canvas or "square")


def _score_canvas_ground(score: Score) -> CanvasGroundSpec | None:
    if isinstance(score.canvas, CanvasSpec):
        ground = score.canvas.ground
        if ground is not None and ground.material != "plain":
            return ground
    return None


def _texture_seed(score: Score, kind: str, render_seed: int | None, index: int = 0) -> int:
    payload = score.model_dump(mode="json", by_alias=True)
    key = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if render_seed is not None:
        key += f":render:{render_seed}"
    key += f":texture:{kind}:{index}"
    return struct.unpack("<Q", hashlib.sha256(key.encode("utf-8")).digest()[:8])[0]


def _ground_tone_color(ground: CanvasGroundSpec, bg: str) -> str:
    return {
        "white": bg,
        "off_white": "#f7f3e8",
        "warm": "#f3ead8",
        "cool": "#eef3f4",
        "gray": "#e4e2dc",
        "black": "#151515",
    }.get(ground.tone, bg)


def _ground_dot_count(ground: CanvasGroundSpec, profile: str) -> int:
    base = {"fine": 70, "medium": 45, "coarse": 28, "none": 18}.get(ground.grain, 45)
    count = max(4, int(base * max(0.05, ground.density)))
    if profile == "compat":
        return min(18, count)
    if profile == "editable":
        return min(90, count)
    return min(140, count)


def _ground_filter_xml(ground: CanvasGroundSpec, seed: int, filter_id: str) -> str:
    freq = {"fine": "0.95", "medium": "0.55", "coarse": "0.28", "none": "0.45"}.get(ground.grain, "0.55")
    opacity = min(0.18, max(0.02, ground.opacity))
    return (
        f'<filter id="{filter_id}" x="0" y="0" width="100%" height="100%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="{freq}" numOctaves="2" seed="{seed % 9973}" result="noise"/>'
        '<feColorMatrix in="noise" type="saturate" values="0" result="mono"/>'
        f'<feComponentTransfer in="mono"><feFuncA type="table" tableValues="0 {opacity:.3f}"/></feComponentTransfer>'
        '</filter>'
    )


def _render_canvas_ground(dwg: svgwrite.Drawing, score: Score, canvas: CanvasSize, bg: str, *, profile: str, render_seed: int | None):
    ground = _score_canvas_ground(score)
    if ground is None:
        return None, None
    seed = int(ground.seed if ground.seed is not None else _texture_seed(score, "canvas-ground", render_seed))
    tone = _ground_tone_color(ground, bg)
    group = dwg.g(id="layer_01_canvas_ground")
    group.add(dwg.rect(insert=(0, 0), size=(canvas.width, canvas.height), fill=tone, opacity=0.98))
    if profile == "display":
        fid = _safe_svg_id(f"ground_texture_{seed % 100000}")
        group.add(dwg.rect(insert=(0, 0), size=(canvas.width, canvas.height), fill="#777777", opacity=1.0, filter=f"url(#{fid})"))
        return group, _ground_filter_xml(ground, seed, fid)
    color = "#777777" if ground.material != "charcoal_ground" else "#222222"
    count = _ground_dot_count(ground, profile)
    radius = {"fine": 0.7, "medium": 1.1, "coarse": 1.8, "none": 0.6}.get(ground.grain, 1.0)
    for i in range(count):
        x = _hash01(i, seed, "ground-x") * canvas.width
        y = _hash01(i, seed, "ground-y") * canvas.height
        if ground.grain == "coarse" and i % 3 == 0:
            group.add(dwg.line(start=(x - radius * 2.4, y), end=(x + radius * 2.4, y + _hash_to_unit(i, seed) * radius), stroke=color, stroke_width=max(0.4, radius * 0.45), stroke_opacity=min(0.18, ground.opacity), stroke_linecap="round"))
        else:
            group.add(dwg.circle(center=(x, y), r=radius * (0.55 + _hash01(i, seed, "ground-r") * 0.8), fill=color, opacity=min(0.18, ground.opacity)))
    return group, None


def _surface_seed(ins: Instruction, ins_idx: int, mark_idx: int, render_seed: int | None) -> int:
    if ins.surface is not None and ins.surface.seed is not None:
        return int(ins.surface.seed)
    key = ins.model_dump_json(by_alias=True) + f":surface:{ins_idx}:{mark_idx}:{render_seed}"
    return struct.unpack("<Q", hashlib.sha256(key.encode("utf-8")).digest()[:8])[0]


def _shape_bbox(ins: Instruction, canvas: CanvasSize) -> tuple[float, float, float, float] | None:
    if ins.primitive == "circle" and ins.center is not None and ins.radius is not None:
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        return cx - r, cy - r, r * 2, r * 2
    if ins.primitive == "ellipse" and ins.center is not None and ins.size is not None:
        cx, cy = _px(ins.center, canvas)
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
        return cx - w / 2, cy - h / 2, w, h
    if ins.primitive in ("square", "triangle") and ins.position is not None and ins.size is not None:
        x, y = _px(ins.position, canvas)
        return x, y, ins.size[0] * canvas.width, ins.size[1] * canvas.height
    if ins.primitive == "polygon" and ins.center is not None and ins.radius is not None:
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        return cx - r, cy - r, r * 2, r * 2
    return None


def _add_shape_to_clip(dwg: svgwrite.Drawing, clip, ins: Instruction, canvas: CanvasSize) -> None:
    if ins.primitive == "circle" and ins.center is not None and ins.radius is not None:
        cx, cy = _px(ins.center, canvas)
        clip.add(dwg.circle(center=(cx, cy), r=ins.radius * canvas.unit))
    elif ins.primitive == "ellipse" and ins.center is not None and ins.size is not None:
        cx, cy = _px(ins.center, canvas)
        clip.add(dwg.ellipse(center=(cx, cy), r=(ins.size[0] * canvas.width / 2, ins.size[1] * canvas.height / 2)))
    elif ins.primitive == "square" and ins.position is not None and ins.size is not None:
        x, y = _px(ins.position, canvas)
        clip.add(dwg.rect(insert=(x, y), size=(ins.size[0] * canvas.width, ins.size[1] * canvas.height)))
    elif ins.primitive == "triangle" and ins.position is not None and ins.size is not None:
        x, y = _px(ins.position, canvas)
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
        clip.add(dwg.polygon(points=[(x + w / 2, y), (x, y + h), (x + w, y + h)]))
    elif ins.primitive == "polygon" and ins.center is not None and ins.radius is not None:
        cx, cy = _px(ins.center, canvas)
        clip.add(dwg.polygon(points=_polygon_points(cx, cy, ins.radius * canvas.unit, ins.sides or 5, ins.rotation or 0.0)))


def _surface_color(ins: Instruction, cmap: dict[str, str]) -> str:
    return _resolve_color(ins.color, ins.color_hint, cmap)


def _surface_line_angle(surface: SurfaceSpec) -> float:
    return {"horizontal": 0.0, "vertical": math.pi / 2, "diagonal_rising": -math.pi / 4, "diagonal_falling": math.pi / 4, "none": math.pi / 4}.get(surface.direction, math.pi / 4)


def _render_surface_vectors(dwg: svgwrite.Drawing, group, ins: Instruction, canvas: CanvasSize, cmap: dict[str, str], *, seed: int, clipped: bool) -> None:
    surface = ins.surface
    bbox = _shape_bbox(ins, canvas)
    if surface is None or surface.texture == "none" or bbox is None:
        return
    x, y, w, h = bbox
    color = _surface_color(ins, cmap)
    opacity = min(0.75, surface.opacity)
    density = max(0.02, surface.density)
    scale = max(0.04, surface.scale)
    area_factor = max(0.2, min(1.8, (w * h) / (canvas.unit * canvas.unit * 0.18)))
    if surface.texture in {"stipple", "grain", "paper_grain", "wash"}:
        count = int((22 + density * 120) * area_factor)
        radius = max(0.45, canvas.unit * (0.002 + scale * 0.004))
        if surface.texture == "wash":
            count = max(8, int(count * 0.28))
            radius *= 3.5
            opacity *= 0.42
        for i in range(min(count, 180 if clipped else 90)):
            px = x + _hash01(i, seed, "surface-x") * w
            py = y + _hash01(i, seed, "surface-y") * h
            group.add(dwg.circle(center=(px, py), r=radius * (0.55 + _hash01(i, seed, "surface-r") * 1.1), fill=color, opacity=opacity * (0.45 + _hash01(i, seed, "surface-o") * 0.55), stroke="none"))
    elif surface.texture == "hatch":
        angle = _surface_line_angle(surface)
        spacing = max(5.0, canvas.unit * (0.010 + (1.0 - density) * 0.025))
        span = math.hypot(w, h) * 1.3
        cx = x + w / 2
        cy = y + h / 2
        ux, uy = math.cos(angle), math.sin(angle)
        nx, ny = -uy, ux
        count = min(80, max(3, int(span / spacing)))
        for i in range(-count // 2, count // 2 + 1):
            jitter = _hash_to_unit(i + 500, seed) * spacing * 0.16
            ox = nx * (i * spacing + jitter)
            oy = ny * (i * spacing + jitter)
            group.add(dwg.line(start=(cx + ox - ux * span / 2, cy + oy - uy * span / 2), end=(cx + ox + ux * span / 2, cy + oy + uy * span / 2), stroke=color, stroke_width=max(0.45, canvas.unit * 0.0016), stroke_opacity=opacity, stroke_linecap="round"))
    elif surface.texture == "bleed":
        blur = max(1.0, canvas.unit * (0.006 + surface.bleed * 0.018))
        group.add(dwg.ellipse(center=(x + w / 2, y + h / 2), r=(w / 2 + blur, h / 2 + blur), fill=color, opacity=min(0.26, opacity * 0.42), stroke="none"))


def _render_surface_texture(dwg: svgwrite.Drawing, ins: Instruction, cmap: dict[str, str], canvas: CanvasSize, *, profile: str, render_seed: int | None, ins_idx: int, mark_idx: int):
    surface = ins.surface
    if surface is None or surface.texture == "none" or ins.primitive not in _CLOSED_SHAPES:
        return None, None
    seed = _surface_seed(ins, ins_idx, mark_idx, render_seed)
    gid = _safe_svg_id(f"surface_{ins_idx:03d}_{mark_idx:03d}_{surface.texture}")
    group = dwg.g(id=gid)
    if profile == "display":
        clip_id = _safe_svg_id(f"clip_{gid}_{seed % 100000}")
        clip = dwg.defs.add(dwg.clipPath(id=clip_id))
        _add_shape_to_clip(dwg, clip, ins, canvas)
        group["clip-path"] = f"url(#{clip_id})"
        if surface.texture in {"wash", "bleed"}:
            fid = _safe_svg_id(f"surface_filter_{gid}_{seed % 100000}")
            bbox = _shape_bbox(ins, canvas)
            if bbox is not None:
                x, y, w, h = bbox
                color = _surface_color(ins, cmap)
                rect = dwg.rect(insert=(x, y), size=(w, h), fill=color, opacity=min(0.55, surface.opacity), filter=f"url(#{fid})")
                group.add(rect)
                return group, f'<filter id="{fid}" x="-12%" y="-12%" width="124%" height="124%"><feTurbulence type="fractalNoise" baseFrequency="0.18" numOctaves="2" seed="{seed % 9973}" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="{1.5 + surface.bleed * 9:.2f}"/><feGaussianBlur stdDeviation="{surface.bleed * 5:.2f}"/></filter>'
        _render_surface_vectors(dwg, group, ins, canvas, cmap, seed=seed, clipped=True)
        return group, None
    _render_surface_vectors(dwg, group, ins, canvas, cmap, seed=seed, clipped=False)
    return group, None


def build_texture_metadata(score: Score, *, svg_profile: str | None = None) -> dict:
    profile = _normalize_svg_profile(svg_profile)
    ground = _score_canvas_ground(score)
    surfaces = []
    for idx, ins in enumerate(score.instructions):
        if ins.surface is not None and ins.surface.texture != "none":
            surfaces.append({"instruction_index": idx, "texture": ins.surface.texture, "density": ins.surface.density, "opacity": ins.surface.opacity})
    metadata = {"render_texture_version": "1", "render_texture_profile": profile, "texture_degraded": profile == "compat" and bool(surfaces)}
    if ground is not None:
        metadata["render_canvas_ground"] = ground.model_dump(mode="json", exclude_none=True)
    if surfaces:
        metadata["render_surface_textures"] = surfaces
    return metadata

def _normalize_svg_profile(svg_profile: str | None) -> str:
    profile = (svg_profile or "display").strip().lower()
    if profile not in SVG_PROFILES:
        raise ValueError(f"unsupported svg profile: {svg_profile}")
    return profile


def _safe_svg_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")
    if not safe:
        safe = "item"
    if not re.match(r"[A-Za-z_]", safe):
        safe = f"inku_{safe}"
    return safe


def _instruction_svg_id(ins: Instruction, ins_idx: int) -> str:
    parts = [f"instruction_{ins_idx:03d}", ins.primitive, ins.color, ins.weight]
    if ins.style != "solid":
        parts.append(ins.style)
    return _safe_svg_id("_".join(parts))


def _mark_svg_id(ins: Instruction, ins_idx: int, mark_idx: int) -> str:
    return _safe_svg_id(f"mark_{ins_idx:03d}_{mark_idx:03d}_{ins.primitive}")


def _inject_svg_document_metadata(svg: str, *, profile: str) -> str:
    title = f"inku render ({profile} SVG)"
    desc = "Generated by inku. Groups and IDs are included for vector editing." if profile == "editable" else "Generated by inku. Portable SVG output."
    metadata = json.dumps({"generator": "inku", "svg_profile": profile}, ensure_ascii=False, separators=(",", ":"))
    document_metadata = (
        f"<title>{escape(title)}</title>"
        f"<desc>{escape(desc)}</desc>"
        f'<metadata id="inku_metadata">{escape(metadata)}</metadata>'
    )
    return re.sub(r"(<svg\b[^>]*>)", r"\1" + document_metadata, svg, count=1)


def render(
    score: Score,
    color_map: dict[str, str] | None = None,
    *,
    canvas_aspect: str | None = None,
    svg_profile: str | None = None,
    render_seed: int | None = None,
) -> str:
    profile = _normalize_svg_profile(svg_profile)
    score = _resolve_performance_score(score, render_seed)
    structured = profile != "display"
    use_filters = profile == "display"
    cmap = {**COLOR_MAP, **(color_map or {})}
    canvas = canvas_size_for_aspect(canvas_aspect or _score_canvas_aspect(score))
    dwg = svgwrite.Drawing(
        size=(canvas.width, canvas.height),
        viewBox=f"0 0 {canvas.width} {canvas.height}",
    )
    bg = cmap.get(score.background, BACKGROUND)
    ground_layer, ground_filter_xml = _render_canvas_ground(
        dwg, score, canvas, bg, profile=profile, render_seed=render_seed
    )
    surface_filter_xml: list[str] = []
    performance_filter_xml: str | None = None
    if structured:
        artboard = dwg.g(id="inku_artboard")
        background = dwg.g(id="layer_00_background")
        background.add(dwg.rect(insert=(0, 0), size=(canvas.width, canvas.height), fill=bg, id="background"))
        content = dwg.g(id="layer_10_content")
        presence_content = dwg.g(id="layer_20_presence")
        artboard.add(background)
        if ground_layer is not None:
            artboard.add(ground_layer)
        artboard.add(content)
        artboard.add(presence_content)
    else:
        dwg.add(dwg.rect(insert=(0, 0), size=(canvas.width, canvas.height), fill=bg))
        if ground_layer is not None:
            dwg.add(ground_layer)
        clip_id = "canvas-clip"
        clip = dwg.defs.add(dwg.clipPath(id=clip_id))
        clip.add(dwg.rect(insert=(0, 0), size=(canvas.width, canvas.height)))
        content = dwg.g(clip_path=f"url(#{clip_id})")
        presence_content = content

    if use_filters and render_seed is not None:
        performance_filter_id, performance_filter_xml = _performance_touch_filter(render_seed)
        content["filter"] = f"url(#{performance_filter_id})"

    blur_needed: dict[str, float] = {}
    texture_filters = _texture_filter_weights(score) if use_filters else set()
    blur_elems: list[tuple[str, str]] = []
    elem_idx = 0

    for ins_idx, ins in enumerate(score.instructions):
        expanded = _expand_arrangement(ins, render_seed) if ins.arrangement else [ins]
        instruction_group = dwg.g(id=_instruction_svg_id(ins, ins_idx)) if structured else content
        for mark_idx, single in enumerate(expanded):
            element = _render_instruction(dwg, single, cmap, canvas, use_filters=use_filters, render_seed=render_seed)
            if element is not None:
                if structured:
                    element["id"] = _mark_svg_id(single, ins_idx, mark_idx)
                elif _needs_blur(single.variation):
                    v = single.variation
                    assert v is not None
                    blur_needed[v.amplitude] = BLUR_STD[v.amplitude]
                    eid = f"e{elem_idx}"
                    element["id"] = eid
                    blur_elems.append((eid, v.amplitude))
                instruction_group.add(element)
            surface_group, surface_filter = _render_surface_texture(
                dwg, single, cmap, canvas, profile=profile, render_seed=render_seed,
                ins_idx=ins_idx, mark_idx=mark_idx,
            )
            if surface_group is not None:
                instruction_group.add(surface_group)
            if surface_filter is not None:
                surface_filter_xml.append(surface_filter)
            elem_idx += 1
        if structured:
            content.add(instruction_group)

    presence_layer = _render_presence_layer(dwg, score, cmap, canvas)
    if presence_layer is not None:
        presence_content.add(presence_layer)

    if structured:
        dwg.add(artboard)
    else:
        dwg.add(content)
    svg = dwg.tostring()
    if ground_filter_xml or surface_filter_xml or performance_filter_xml:
        extra_filter_xml = (ground_filter_xml or "") + "".join(surface_filter_xml) + (performance_filter_xml or "")
        if "<defs />" in svg:
            svg = svg.replace("<defs />", f"<defs>{extra_filter_xml}</defs>", 1)
        elif "<defs/>" in svg:
            svg = svg.replace("<defs/>", f"<defs>{extra_filter_xml}</defs>", 1)
        else:
            svg = svg.replace("<defs>", f"<defs>{extra_filter_xml}", 1)
    svg = _inject_texture_filters(svg, texture_filters)
    if blur_elems:
        svg = _inject_blur_filters(svg, blur_needed, blur_elems)
    if structured:
        svg = _inject_svg_document_metadata(svg, profile=profile)
    return svg


_CLOSED_SHAPES = frozenset({"circle", "ellipse", "square", "triangle", "polygon"})


def _texture_filter_weights(score: Score) -> set[str]:
    weights: set[str] = set()
    for ins in score.instructions:
        if ins.weight in TEXTURE_FILTERS:
            weights.add(ins.weight)
    return weights


def _score_visual_load(score: Score) -> int:
    load = 0
    for ins in score.instructions:
        if ins.arrangement is not None:
            load += max(1, int(ins.arrangement.count))
        else:
            load += 1
    return load


def _presence_center_px(score: Score, canvas: CanvasSize) -> tuple[float, float]:
    presence = score.presence
    if presence is None or presence.center is None:
        return canvas.width * 0.52, canvas.height * 0.50
    x, y = presence.center
    return _clamp01(x) * canvas.width, _clamp01(y) * canvas.height


def _presence_seed(score: Score) -> int:
    presence_json = score.presence.model_dump_json() if score.presence is not None else ""
    instruction_key = "|".join(
        f"{ins.primitive}:{ins.color}:{ins.weight}:{ins.arrangement.count if ins.arrangement else 1}"
        for ins in score.instructions
    )
    digest = hashlib.sha256(f"{presence_json}|{instruction_key}".encode("utf-8")).digest()
    return struct.unpack("<Q", digest[:8])[0]


def _render_presence_layer(dwg: svgwrite.Drawing, score: Score, cmap: dict[str, str], canvas: CanvasSize):
    """抽象化された存在感を描く。自然文キーワードや具象部品はここでは扱わない。"""
    presence = score.presence
    if presence is None or presence.kind == "none":
        return None

    cx, cy = _presence_center_px(score, canvas)
    unit = canvas.unit
    color = cmap.get("gray", COLOR_MAP["gray"])
    dark = cmap.get("black", COLOR_MAP["black"])
    visual_load = _score_visual_load(score)
    load_opacity = 0.52 if visual_load >= 120 else 0.70 if visual_load >= 60 else 1.0
    intensity_opacity = {"low": 0.13, "medium": 0.21, "high": 0.30}[presence.intensity] * load_opacity
    gaze_opacity = {"none": 0.0, "low": 0.11, "medium": 0.18, "high": 0.26}[presence.gaze_pressure] * load_opacity
    contour_count = {"low": 4, "medium": 7, "high": 11}[presence.contour_density]
    radius_x = unit * {"low": 0.18, "medium": 0.24, "high": 0.30}[presence.intensity]
    radius_y = unit * {"low": 0.24, "medium": 0.32, "high": 0.40}[presence.intensity]
    stroke = max(1.2, unit * 0.003)
    layer = dwg.g(id="presence_layer")
    seed = _presence_seed(score)
    phase = math.tau * _hash01(0, seed, "presence-phase")
    tilt = (_hash01(1, seed, "presence-tilt") - 0.5) * 1.2

    if presence.symmetry == "bilateral":
        for i, side in enumerate((-1, 1, -1, 1)):
            y_shift = (-0.36 + i * 0.24) * radius_y
            x_outer = side * radius_x * (0.34 + 0.10 * _hash01(i, seed, "sym-x"))
            x_inner = side * radius_x * (0.10 + 0.08 * _hash01(i, seed, "sym-inner"))
            layer.add(dwg.line(
                start=(cx + x_outer, cy + y_shift - radius_y * 0.06),
                end=(cx + x_inner, cy + y_shift + radius_y * (0.10 + tilt * 0.06)),
                stroke=color,
                stroke_width=stroke,
                stroke_opacity=intensity_opacity * 0.58,
                stroke_linecap="round",
            ))
    elif presence.symmetry == "radial":
        for i in range(6):
            angle = phase + math.tau * i / 6.0
            inner = radius_x * 0.28
            outer = radius_x * 0.86
            layer.add(dwg.line(
                start=(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
                end=(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
                stroke=color,
                stroke_width=stroke,
                stroke_opacity=intensity_opacity * 0.72,
                stroke_linecap="round",
            ))

    if presence.gaze_pressure != "none":
        for i, side in enumerate((-1, 1, -1, 1, -1, 1)):
            t = (i + 1) / 7
            angle = phase + side * (0.34 + 0.08 * i)
            start_x = cx + math.cos(angle) * radius_x * (1.05 + 0.18 * (i % 2))
            start_y = cy + math.sin(angle) * radius_y * (0.72 + 0.08 * i)
            end_x = cx + math.cos(angle + math.pi) * radius_x * 0.12
            end_y = cy + (t - 0.5) * radius_y * 0.16
            layer.add(dwg.line(
                start=(start_x, start_y),
                end=(end_x, end_y),
                stroke=dark,
                stroke_width=stroke * 0.8,
                stroke_opacity=gaze_opacity,
                stroke_linecap="round",
            ))

    flow_angle = phase * 0.35 + tilt
    tx, ty = math.cos(flow_angle), math.sin(flow_angle)
    nx, ny = -ty, tx
    for i in range(contour_count):
        t = (i + 0.5) / contour_count
        along = (t - 0.5) * radius_x * (1.18 + 0.18 * _hash01(i, seed, "presence-flow-span"))
        cross = math.sin(t * math.pi * 1.7 + phase) * radius_y * 0.32
        cross += (_hash01(i, seed, "presence-flow-cross") - 0.5) * radius_y * 0.28
        px = cx + tx * along + nx * cross
        py = cy + ty * along + ny * cross
        half = radius_x * (0.09 + 0.04 * _hash01(i, seed, "presence-flow-half"))
        lift = radius_y * (0.05 + 0.04 * _hash01(i, seed, "presence-flow-lift"))
        side = -1.0 if i % 2 else 1.0
        x1 = px - tx * half - nx * lift * side
        y1 = py - ty * half - ny * lift * side
        x2 = px + tx * half + nx * lift * side
        y2 = py + ty * half + ny * lift * side
        xm = px + nx * lift * side * 1.4
        ym = py + ny * lift * side * 1.4
        path = dwg.path(
            d=f"M {x1:.2f},{y1:.2f} Q {xm:.2f},{ym:.2f} {x2:.2f},{y2:.2f}",
            fill="none",
            stroke=color,
            stroke_width=stroke,
            stroke_opacity=intensity_opacity * 0.82,
            stroke_linecap="round",
        )
        layer.add(path)

    if presence.kind == "group_like":
        for i in range(7):
            t = (i - 3) / 3.5
            px = cx + tx * t * radius_x * 0.78 + nx * (_hash01(i, seed, "group-x") - 0.5) * radius_x * 0.20
            py = cy + ty * t * radius_x * 0.78 + ny * (_hash01(i, seed, "group-y") - 0.5) * radius_y * 0.58
            layer.add(dwg.circle(
                center=(px, py),
                r=max(2.0, unit * 0.006),
                fill=color,
                fill_opacity=intensity_opacity * 0.72,
            ))
    elif presence.kind == "creature_like":
        for i in range(3):
            t = (i - 1) * 0.34
            layer.add(dwg.line(
                start=(cx - radius_x * 0.30 + t * radius_x, cy + radius_y * 0.32),
                end=(cx - radius_x * 0.05 + t * radius_x, cy + radius_y * 0.44),
                stroke=color,
                stroke_width=stroke,
                stroke_opacity=intensity_opacity * 0.76,
                stroke_linecap="round",
            ))

    return layer


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


def _stroke_attrs(ins: Instruction, cmap: dict[str, str], *, use_filters: bool = True) -> dict:
    do_fill = ins.primitive in _CLOSED_SHAPES or ins.filled
    color = _resolve_color(ins.color, ins.color_hint, cmap)
    weight_style = WEIGHT_STYLE.get(ins.weight, {})
    hint = _norm_label(ins.color_hint or "")
    attrs = {
        "stroke": color,
        "stroke_width": WEIGHT_TO_STROKE_WIDTH[ins.weight],
        "fill": color if do_fill else "none",
        "stroke_linecap": weight_style.get("stroke_linecap", "round"),
    }
    if "stroke_opacity" in weight_style:
        attrs["stroke_opacity"] = weight_style["stroke_opacity"]
    if use_filters and ins.weight in TEXTURE_FILTERS:
        attrs["filter"] = f"url(#texture-{ins.weight})"
    if any(token in hint for token in ("membrane", "haze", "fog", "mist", "atmosphere", "膜", "霞", "霧", "靄")):
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.26)
        if do_fill:
            attrs["fill_opacity"] = 0.12
    elif any(token in hint for token in ("soft light", "柔らかな光", "陽光", "日差し")):
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.30)
        if do_fill:
            attrs["fill_opacity"] = 0.14
    elif any(token in hint for token in ("scent", "fragrance", "香り", "匂")):
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.38)
        if do_fill:
            attrs["fill_opacity"] = 0.20
    elif any(token in hint for token in ("waiting buds", "開花を待つ蕾", "蕾", "つぼみ")):
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.72)
        if do_fill:
            attrs["fill_opacity"] = 0.58
    elif any(token in hint for token in ("five-sense", "五感")):
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.44)
        if do_fill:
            attrs["fill_opacity"] = 0.18
    elif "fade directional" in hint or "fade=directional" in hint:
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.48)
        if do_fill:
            attrs["fill_opacity"] = 0.30
    elif "fade outward" in hint or "fade=outward" in hint:
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.40)
        if do_fill:
            attrs["fill_opacity"] = 0.22
    if any(token in hint for token in ("reflection", "反射", "映り")):
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.52)
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


def _polygon_points(cx: float, cy: float, r: float, sides: int, rotation_deg: float = 0.0) -> list[tuple[float, float]]:
    sides = min(max(int(sides), 5), 8)
    start = math.radians(rotation_deg - 90)
    return [
        (
            cx + math.cos(start + math.tau * i / sides) * r,
            cy + math.sin(start + math.tau * i / sides) * r,
        )
        for i in range(sides)
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
        for idx, (px, py) in enumerate(_circle_points(cx, cy, r, r, 16)):
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
    canvas: CanvasSize,
    *,
    use_filters: bool = True,
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
            if use_filters:
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
    return _apply_rotation(group, ins, canvas)


def _px(coord: tuple[float, float], canvas: CanvasSize) -> tuple[float, float]:
    x, y = coord
    return x * canvas.width, y * canvas.height


def _apply_rotation(element, ins: Instruction, canvas: CanvasSize):
    if ins.rotation is None or abs(ins.rotation) < 1e-9:
        return element
    cx, cy = _px(_anchor(ins), canvas)
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


def _render_instruction(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    cmap: dict[str, str] = COLOR_MAP,
    canvas: CanvasSize | None = None,
    *,
    use_filters: bool = True,
    render_seed: int | None = None,
):
    canvas = canvas or canvas_size_for_aspect(None)
    attrs = _stroke_attrs(ins, cmap, use_filters=use_filters)

    if ins.primitive == "line":
        start = _px(ins.from_ if ins.from_ is not None else (0.5, 0.0), canvas)
        end = _px(ins.to if ins.to is not None else (0.5, 1.0), canvas)
        if _needs_path_variation(ins.variation):
            assert ins.variation is not None
            points = _line_with_variation(
                start, end, ins.variation, _seed_for_instruction(ins, render_seed)
            )
            return _apply_rotation(dwg.polyline(points=points, **attrs), ins, canvas)
        textured = _material_line_group(dwg, ins, start, end, attrs, canvas, use_filters=use_filters)
        if textured is not None:
            return textured
        return _apply_rotation(dwg.line(start=start, end=end, **attrs), ins, canvas)

    if ins.primitive == "circle":
        if ins.center is None or ins.radius is None:
            raise ValueError("circle requires 'center' and 'radius'")
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(dwg.circle(center=(cx, cy), r=r, **attrs))
            _add_material_circle_outline(dwg, group, ins, attrs, cx, cy, r)
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(dwg.circle(center=(cx, cy), r=r, **attrs), ins, canvas)

    if ins.primitive == "ellipse":
        if ins.center is None or ins.size is None:
            raise ValueError("ellipse requires 'center' and 'size'")
        cx, cy = _px(ins.center, canvas)
        rx = ins.size[0] * canvas.width / 2
        ry = ins.size[1] * canvas.height / 2
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(dwg.ellipse(center=(cx, cy), r=(rx, ry), **attrs))
            _add_material_ellipse_outline(dwg, group, ins, attrs, cx, cy, rx, ry)
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(dwg.ellipse(center=(cx, cy), r=(rx, ry), **attrs), ins, canvas)

    if ins.primitive == "square":
        if ins.position is None or ins.size is None:
            raise ValueError("square requires 'position' and 'size'")
        x, y = _px(ins.position, canvas)
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(dwg.rect(insert=(x, y), size=(w, h), **attrs))
            _add_material_rect_outline(dwg, group, ins, attrs, x, y, w, h)
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(dwg.rect(insert=(x, y), size=(w, h), **attrs), ins, canvas)

    if ins.primitive == "triangle":
        if ins.position is None or ins.size is None:
            raise ValueError("triangle requires 'position' and 'size'")
        x, y = _px(ins.position, canvas)
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
        points = [
            (x + w / 2, y),
            (x, y + h),
            (x + w, y + h),
        ]
        return _apply_rotation(dwg.polygon(points=points, **attrs), ins, canvas)

    if ins.primitive == "polygon":
        if ins.center is None or ins.radius is None:
            raise ValueError("polygon requires 'center' and 'radius'")
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        points = _polygon_points(cx, cy, r, ins.sides or 5)
        return _apply_rotation(dwg.polygon(points=points, **attrs), ins, canvas)

    if ins.primitive == "arc":
        if ins.center is None or ins.radius is None:
            raise ValueError("arc requires 'center' and 'radius'")
        if ins.angle_start is None or ins.angle_end is None:
            raise ValueError("arc requires 'angle_start' and 'angle_end'")
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        path_d = _arc_path_d(cx, cy, r, ins.angle_start, ins.angle_end)
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(dwg.path(d=path_d, **attrs))
            _add_material_arc_outline(dwg, group, ins, attrs, cx, cy, r, ins.angle_start, ins.angle_end)
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(dwg.path(d=path_d, **attrs), ins, canvas)

    raise NotImplementedError(f"primitive '{ins.primitive}' not yet supported")
