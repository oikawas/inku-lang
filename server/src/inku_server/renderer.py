"""JSON Score → SVG renderer.

楽譜(Score)を演奏(SVG)に変換する。揺らぎ(variation)の実現は Renderer 層で行う
(SPEC §13.8)。Phase 1 は静的描画のみ、perlin/wave は段階追加。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
import re
import struct
from typing import Any
from xml.sax.saxutils import escape

import svgwrite

from .cloudform import generate_cloudform_contour, sample_closed_catmull_rom
from .color_catalogs import DEFAULT_COLOR_CATALOG_ID
from .master_grid import fmt
from .plugins import CanvasSize, canvas_size_for_aspect
from .schema import (
    Arrangement,
    CanvasGroundSpec,
    CanvasSpec,
    Instruction,
    Score,
    SurfaceSpec,
    Variation,
)
from .arc_geometry import (
    arc_from_endpoints_and_sagitta,
    arc_point,
    arc_svg_flags,
    minor_arc_delta,
)
from .stroke_engine import (
    GRAMMARS,
    centerline_normals,
    contour_stroke_path,
    grid_point,
    outline_for_centerline,
    polygon_path,
    synthesize_along,
    synthesize_stroke,
)

logger = logging.getLogger(__name__)

CANVAS_PX = 1000

WEIGHT_TO_STROKE_WIDTH: dict[str, float] = {
    "silverpoint": 0.5,
    "pencil": 1.5,
    "pen": 2.0,
    "rotring": 1.0,
    "crayon": 4.0,
    "chalk": 3.0,
    "brush_thin": 3.0,
    "brush_thick": 8.0,
    "burin": 3.2,
    "drypoint": 2.6,
    "computer": 2.0,
}

# 太さの軸 (engine 16 段 3)。道具の既定幅に掛ける係数で、細い側にしか無い。
# 記述者は px を書かず、「細い」「極細」とだけ書く。
THINNESS_TO_WIDTH_SCALE: dict[str | None, float] = {
    None: 1.0,
    "fine": 0.6,
    "extra_fine": 0.35,
}

# どの道具をどれだけ細く引いても、最も細い道具 (銀筆) より細くはならない。
MIN_STROKE_WIDTH: float = WEIGHT_TO_STROKE_WIDTH["silverpoint"]

COLOR_MAP: dict[str, str] = {
    "white": "#ffffff",
    "black": "#111111",
    "blue": "#2c3e91",
    "red": "#a2342a",
    "green": "#2f6b3a",
    "gray": "#888888",
    # These neutral defaults keep all nine abstract colors renderable. Catalogs
    # may override them; band-based catalog resolution can still use them last.
    "yellow": "#a18308",
    "orange": "#a95a00",
    "purple": "#583a84",
}

SVG_PROFILES = frozenset({"display", "editable", "compat"})

HUE_HINTS: dict[str, tuple[str, ...]] = {
    "white": (
        "white",
        "ivory",
        "paper",
        "linen",
        "blanc",
        "bianco",
        "aspro",
        "白",
        "胡粉",
        "象牙",
        "生成",
    ),
    "black": (
        "black",
        "ink",
        "sumi",
        "obsidian",
        "basalt",
        "skotadi",
        "黒",
        "墨",
        "玄",
        "暗",
    ),
    "blue": (
        "blue",
        "cyan",
        "azure",
        "ultramarine",
        "cobalt",
        "lapis",
        "bleu",
        "azul",
        "青",
        "藍",
        "水色",
        "空色",
        "瑠璃",
    ),
    "green": (
        "green",
        "verd",
        "jade",
        "olive",
        "cactus",
        "緑",
        "青緑",
        "翡翠",
        "常磐",
        "玉",
        "草",
    ),
    "gray": (
        "gray",
        "grey",
        "silver",
        "ash",
        "stone",
        "granit",
        "petra",
        "灰",
        "鼠",
        "銀",
        "石",
    ),
    "red": (
        "red",
        "rose",
        "pink",
        "carmine",
        "cinnabar",
        "terra",
        "rosa",
        "vermilion",
        "赤",
        "朱",
        "紅",
        "桜",
        "桃",
        "薔薇",
    ),
    "yellow": (
        "yellow",
        "gold",
        "ochre",
        "ocra",
        "giallo",
        "jaune",
        "napoli",
        "kesar",
        "haldi",
        "sun",
        "ilios",
        "山吹",
        "金",
        "黄",
        "琉璃金",
    ),
    "orange": (
        "orange",
        "apricot",
        "terracotta",
        "cempasuchil",
        "ff4d00",
        "橙",
        "蜜柑",
    ),
    "purple": ("purple", "violet", "lilac", "murasaki", "宮廷紫", "藤", "紫"),
    "brown": (
        "brown",
        "sienna",
        "umber",
        "ombra",
        "chandan",
        "lera",
        "sepia",
        "茶",
        "土",
        "焦",
    ),
}

STYLE_TO_DASH: dict[str, str | None] = {
    "solid": None,
    "dashed": "12,8",
    "dotted": "2,6",
    "dash_dot": "12,6,2,6",
}

WEIGHT_STYLE: dict[str, dict[str, str | float]] = {
    "silverpoint": {"stroke_opacity": 0.72, "stroke_linecap": "butt"},
    "pencil": {"stroke_opacity": 0.66, "stroke_dasharray": "1,3"},
    "pen": {"stroke_opacity": 1.0},
    "rotring": {"stroke_opacity": 0.95, "stroke_linecap": "square"},
    "crayon": {"stroke_opacity": 0.78, "stroke_dasharray": "10,3,2,3"},
    "chalk": {"stroke_opacity": 0.7, "stroke_dasharray": "7,5,1,4"},
    "brush_thin": {"stroke_opacity": 0.9, "stroke_linecap": "round"},
    "brush_thick": {"stroke_opacity": 0.86, "stroke_linecap": "round"},
    "burin": {"stroke_opacity": 0.96, "stroke_linecap": "round"},
    "drypoint": {"stroke_opacity": 0.92, "stroke_linecap": "round"},
    "computer": {"stroke_opacity": 1.0, "stroke_linecap": "round"},
}

BACKGROUND = "#ffffff"

# engine 20: the frame an expanded group is fitted into once it has been moved
# onto its declared anchor. Marks are allowed to touch the edge, not to leave.
FRAME_LO = 0.02
FRAME_HI = 0.98

# SPEC §13.8: 揺らぎは Renderer 層で生成する (JSON Score は決定的な楽譜)
#
# 滲みは「図形の代表寸法に対する比率」で定義する (v2.1)。
# 絶対 px だと小図形は壊れ大図形は静止して見えるため、運動語彙 (fine/medium/
# broad) が図形に対する相対量として意味を持つようにする。
# 比率は v2.1 キャリブレーション (Build 637) で作者が候補 P3 を選択した値。
#
# The wander, unlike the bleed, is measured in stroke widths (engine 28).
# It is a property of the tool meeting the paper, not of how big the figure is:
# scaling it by the figure made a large arc leave its own line by eleven widths
# while a small one stayed on it, because the same 8% of a radius is invisible
# under a brush and a different line under a pencil. The vocabulary is unchanged
# (fine/medium/broad); only the ruler the words are read against moved.
AMPLITUDE_WIDTHS: dict[str, float] = {"fine": 0.35, "medium": 0.9, "broad": 2.0}
FREQUENCY_CYCLES: dict[str, float] = {"slow": 2.0, "medium": 6.0, "high": 14.0}

# 滲む (quality=pink): feGaussianBlur の stdDeviation も代表寸法比
BLUR_RATIO: dict[str, float] = {"fine": 0.009, "medium": 0.03, "broad": 0.07}
BLUR_MIN_RATIO = 0.0005  # canvas.unit 比の下限 (点に近い図形で滲みが消えない)

# 代表寸法が点に近い図形での暴走を防ぐ下限 (canvas.unit 比) と、
# 輪郭の自己交差・反転を防ぐ上限 (代表寸法比)。
REPRESENTATIVE_MIN_RATIO = 0.02
AMPLITUDE_CLAMP_RATIO = 0.40

# キャリブレーション用の primitive 別ゲイン。既定 1.0。
# line は代表寸法が線長のため、必要ならここだけで抑えられる。
PRIMITIVE_AMP_GAIN: dict[str, float] = {}

# 分割数は輪郭・線の長さに比例させ、セグメント長をほぼ一定に保つ。
SEGMENT_TARGET_RATIO = 0.01  # 目標セグメント長 = canvas.unit の 1%
SEGMENT_COUNT_MIN = 32
SEGMENT_COUNT_MAX = 200
STROKE_SAMPLE_TARGET_RATIO = 1.0 / 49.0  # 長さ = canvas.unit で現行の 49 本
STROKE_SAMPLE_MIN = 17
STROKE_SAMPLE_MAX = 129

# 材質層の強度候補。相対化の起点 (m0) は v2.0.5 相当。
# 採用段は MATERIAL_INTENSITY_LEVEL で選ぶ。
MATERIAL_INTENSITY: dict[str, dict[str, float]] = {
    "m0": {
        "texture_displacement": 1.0,
        "texture_blur": 1.0,
        "outline_offset": 1.0,
        "outline_opacity": 1.0,
        "speck_count": 1.0,
        "speck_spread": 1.0,
        "speck_opacity": 1.0,
    },
    "m1": {
        "texture_displacement": 1.8,
        "texture_blur": 1.3,
        "outline_offset": 1.8,
        "outline_opacity": 1.4,
        "speck_count": 1.5,
        "speck_spread": 1.4,
        "speck_opacity": 1.3,
    },
    "m2": {
        "texture_displacement": 2.8,
        "texture_blur": 1.6,
        "outline_offset": 2.8,
        "outline_opacity": 1.8,
        "speck_count": 2.2,
        "speck_spread": 1.8,
        "speck_opacity": 1.6,
    },
    # s1 / s2 は m2 の質感 filter を据え置いたまま、材質輪郭と speck だけを
    # 強める段。倍率ではなく下限 (floor) で上げるのは、弱い weight (pencil・
    # crayon) だけを引き上げ、既に読める weight (brush_thin/thick) の輪郭が
    # 二重線に崩れるのを避けるため。
    # engine 15: s1 の距離側 (outline_offset の倍率と下限) を 1.0 / 0.0 へ戻した。
    # 「材質層が弱い」への対処として距離を掛けていたが、強さを決めるのは濃さ
    # (outline_opacity の 1.8 と下限 0.50) のほうで、距離を掛けると痕跡が墨から
    # 離れて別の輪郭に見える。実測では帯の実測半幅に対し痕跡が pencil 4.5 倍・
    # chalk 6.5 倍・silverpoint 14 倍まで離れていた。表の値はもともと半幅の 0.7〜2.3 倍で
    # 設計されており、倍率と下限がそれを外へ押し出していた (作者裁定 2026-07-27)。
    "s1": {
        "texture_displacement": 2.8,
        "texture_blur": 1.6,
        "outline_offset": 1.0,
        "outline_opacity": 1.8,
        "speck_count": 2.6,
        "speck_spread": 1.8,
        "speck_opacity": 1.6,
        "outline_offset_floor_ratio": 0.0,
        "outline_opacity_floor": 0.50,
        "speck_opacity_floor": 0.40,
    },
    "s2": {
        "texture_displacement": 2.8,
        "texture_blur": 1.6,
        "outline_offset": 2.8,
        "outline_opacity": 1.8,
        "speck_count": 3.0,
        "speck_spread": 2.0,
        "speck_opacity": 1.6,
        "outline_offset_floor_ratio": 0.0050,
        "outline_opacity_floor": 0.62,
        "speck_opacity_floor": 0.50,
    },
}
# v2.1 キャリブレーション (Build 637) の 2 巡目で作者が s1 を選択。
# 1 巡目で m2 を選んだうえで「crayon・chalk は判別できるが弱い」との所感があり、
# 質感 filter を m2 に据え置いたまま材質輪郭と speck を下限で上げた段が s1。
MATERIAL_INTENSITY_LEVEL = "s1"

# speck 個数の周長比例化。基準は radius 0.2 の円の周長 (canvas.unit 比)。
SPECK_ANCHOR_PERIMETER_RATIO = 2 * math.pi * 0.2
SPECK_COUNT_MIN = 10
SPECK_COUNT_MAX_GAIN = 4  # 基準個数に対する上限倍率

# 質感 filter の定義。px 量は canvas.unit 相対で生成する
# (baseFrequency は 1/px 単位なので unit に反比例)。
TEXTURE_SPECS: dict[str, dict[str, float | int]] = {
    "pencil": {
        "margin": 12,
        "base_frequency": 0.9,
        "octaves": 2,
        "seed": 11,
        "displacement": 0.7,
    },
    "crayon": {
        "margin": 18,
        "base_frequency": 0.55,
        "octaves": 3,
        "seed": 17,
        "displacement": 1.8,
    },
    "chalk": {
        "margin": 25,
        "base_frequency": 0.75,
        "octaves": 3,
        "seed": 23,
        "displacement": 2.2,
        # "chalk's light and dark, more distinct" (author, 2026-08-07). Once the
        # fill had an underlay under it, chalk was the flattest of the three
        # tools on the scan branch -- and not for the reason it looked like.
        # Its COARSE tone was already the highest of them (2.30% against
        # crayon's 1.97%); what it was short of was grain, 5.26% against
        # crayon's 13.59%. Every lever that sounded right moved it by under a
        # point: raising `fill_contrast` does nothing because chalk's marks
        # already sit at 0.975 of the ink and the product caps them at the
        # description's own opacity; raising `tooth` only opens more of the
        # underlay, which is not paper; lowering the field moves the mean and
        # not the grain.
        #
        # What was removing the grain was this blur -- the largest of any tool,
        # against crayon's none -- applied over chalk's own displacement. At
        # 0.25 the grain comes back to 13.19%, level with crayon, and chalk
        # keeps a trace of the softness the blur was there for.
        #
        # This is display-only. At `compat` and `editable` chalk always had
        # 14.92%, and the frozen corpus is baked at `editable`, so no reference
        # byte moves with this number.
        "blur": 0.25,
    },
    "brush_thick": {
        "margin": 20,
        "base_frequency": 0.2,
        "octaves": 2,
        "seed": 31,
        "displacement": 1.4,
        "blur": 0.6,
    },
    "drypoint": {"margin": 35, "blur": 1.8},
}
TEXTURE_FILTER_WEIGHTS = frozenset(TEXTURE_SPECS)


def _material_gain(key: str) -> float:
    """材質強度候補の係数を返す。floor 系の既定は 0 (下限なし)。"""
    return MATERIAL_INTENSITY[MATERIAL_INTENSITY_LEVEL].get(key, 0.0)


def _outline_offset_px(offset: float, canvas: CanvasSize) -> float:
    """材質輪郭の法線オフセット。符号を保ったまま下限を課す。

    現行レベル s1 の下限は 0.0 なので素通りする。下限を持つのは s2 だけで、
    それは絶対値 (5px) なので細い道具の痕跡を墨から引き剥がす。採用するなら
    道具の幅に対する比で持ち直すこと (engine 15 の実測)。
    """
    floor = _material_gain("outline_offset_floor_ratio") * canvas.unit
    if floor <= 0 or abs(offset) >= floor:
        return offset
    return math.copysign(floor, offset)


def _outline_opacity(opacity: float) -> float:
    """材質輪郭の opacity。下限を課したうえで 1.0 に丸める。"""
    return min(1.0, max(opacity, _material_gain("outline_opacity_floor")))


def _unit_scale(canvas: CanvasSize) -> float:
    """px 定数を canvas.unit 相対へ写す係数。unit=1000 で厳密に 1.0。"""
    return canvas.unit / CANVAS_PX


def _stroke_width_px(
    weight: str, canvas: CanvasSize, thinness: str | None = None
) -> float:
    """weight と thinness の線幅 (px)。canvas.unit 相対 (unit=1000 で表の値そのもの)。

    太さは道具が内包する寸法で、thinness はそれを細い側へ寄せるだけの係数である
    (太い側は無い)。銀筆は最も細い道具なので、どの道具をどれだけ細く引いても
    銀筆の既定より細くはならない — 道具の順序は太さの指定では壊れない。
    """
    width = WEIGHT_TO_STROKE_WIDTH[weight] * THINNESS_TO_WIDTH_SCALE[thinness]
    return max(width, MIN_STROKE_WIDTH) * _unit_scale(canvas)


def _grid_step_px(weight: str, canvas: CanvasSize) -> float:
    """量子化する道具の目盛 (px)。量子化しない道具は 0.0。

    一枚の紙には一枚の方眼しかない。目盛はキャンバス短辺だけで決まり、置かれた
    対象の大きさにも位置にも依らないので、同じ絵の中のすべてのストロークが同じ
    セルへ落ちる。stroke_engine はキャンバスを知らないので、ここで px へ直して
    渡す。
    """
    grammar = GRAMMARS.get(weight)
    if grammar is None or grammar.quantize <= 0:
        return 0.0
    return canvas.unit * grammar.quantize


def _speck_count(base: int, path_len_px: float, canvas: CanvasSize) -> int:
    """speck の個数を輪郭長 (線なら線長) に比例させる。

    基準は radius 0.2 の円の周長で、そこで表の個数 (18/28/36) に一致する。
    """
    ratio = (path_len_px / canvas.unit) / SPECK_ANCHOR_PERIMETER_RATIO
    count = int(round(base * ratio * _material_gain("speck_count")))
    return max(SPECK_COUNT_MIN, min(base * SPECK_COUNT_MAX_GAIN, count))


def _speck_opacity(opacity: float) -> float:
    return min(
        1.0,
        max(
            opacity * _material_gain("speck_opacity"),
            _material_gain("speck_opacity_floor"),
        ),
    )


_GRID_ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')
_GRID_NUM_RE = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?")
# 識別子であって座標ではないため、グリッドを当てない属性。
_UNGRIDDED_ATTRS = frozenset({"version", "class", "id"})


def _apply_master_grid(svg: str) -> str:
    """全数値をマスターグリッドへ載せる。svgwrite が素の float で書いた属性も含む。

    書き出し箇所を一つずつ直す方式は漏れが黙って残るため、出力の単一地点で
    強制する。ここを通っていない数値は SVG 属性の外にしか存在しない。
    """

    def _attr(match: re.Match[str]) -> str:
        name, value = match.group(1), match.group(2)
        if name in _UNGRIDDED_ATTRS or "." not in value:
            return match.group(0)
        gridded = _GRID_NUM_RE.sub(lambda n: fmt(float(n.group(0))), value)
        return f'{name}="{gridded}"'

    return _GRID_ATTR_RE.sub(_attr, svg)


def _scale_dash(spec: str | None, scale: float) -> str | None:
    """dasharray の各値を canvas.unit 相対へ写す。scale=1.0 で文字列同一。"""
    if spec is None:
        return None
    return ",".join(fmt(float(part) * scale) for part in spec.split(","))


def _texture_filter_xml(weight: str, canvas: CanvasSize) -> str:
    """質感 filter の定義 XML を canvas.unit 相対で生成する。"""
    spec = TEXTURE_SPECS[weight]
    scale = _unit_scale(canvas)
    margin = spec["margin"]
    parts = [
        f'<filter id="texture-{weight}" x="-{margin}%" y="-{margin}%" '
        f'width="{100 + 2 * margin}%" height="{100 + 2 * margin}%">'
    ]
    if "base_frequency" in spec:
        # baseFrequency は 1/px なので unit に反比例させる
        frequency = float(spec["base_frequency"]) / scale
        parts.append(
            f'<feTurbulence type="fractalNoise" baseFrequency="{fmt(frequency)}" '
            f'numOctaves="{spec["octaves"]}" seed="{spec["seed"]}" result="noise"/>'
        )
        displacement = (
            float(spec["displacement"]) * scale * _material_gain("texture_displacement")
        )
        parts.append(
            f'<feDisplacementMap in="SourceGraphic" in2="noise" '
            f'scale="{fmt(displacement)}"/>'
        )
    if "blur" in spec:
        blur = float(spec["blur"]) * scale * _material_gain("texture_blur")
        parts.append(f'<feGaussianBlur stdDeviation="{fmt(blur)}"/>')
    parts.append("</filter>")
    return "".join(parts)


_VARIATION_SEED_FIELDS_ALL = frozenset(
    {"amplitude", "frequency", "quality", "dimensions"}
)
_WORK_COLOR_SEED_FIELDS = ("render_seed", "catalog_id", "abstract_color")

_SEED_INSTRUCTION_FIELDS = (
    "primitive",
    "from_",
    "to",
    "center",
    "radius",
    "sides",
    "position",
    "size",
    "angle_start",
    "angle_end",
    "rotation",
    "filled",
    "style",
    "weight",
    "thinness",
    "mode",
    "carve_depth",
    "variation",
    "arrangement",
    "surface",
)
_SEED_ARRANGEMENT_FIELDS = ("jitter",)


def _variation_seed_fields(ins: Instruction) -> frozenset[str] | None:
    """seed key に残す variation フィールド。None = variation ごと落とす。

    演奏されない variation が seed を動かすと、同じ意図が weight 次第で別の
    演奏になる。実際に消費されるフィールドだけを残す。判定は primitive ごとに
    異なる (cloudform は dimensions を見ず、残り 3 つを輪郭生成器の引数に使う)。
    """
    variation = ins.variation
    if variation is None:
        return None
    if ins.primitive == "cloudform":
        return frozenset({"amplitude", "frequency", "quality"})
    if _needs_blur(variation):
        # 滲みは stdDeviation だけを代表寸法と amplitude から決める。
        return frozenset({"amplitude", "quality"})
    if ins.primitive == "line":
        return _VARIATION_SEED_FIELDS_ALL if _needs_path_variation(variation) else None
    if _needs_contour_variation(variation):
        return _VARIATION_SEED_FIELDS_ALL
    return None


def _seed_for_instruction(ins: Instruction, performance_seed: int | None = None) -> int:
    """Instruction と演奏 seed から安定した乱数 seed を作る。"""
    dumped = ins.model_dump(mode="json")
    payload = {name: dumped[name] for name in _SEED_INSTRUCTION_FIELDS}
    arrangement = payload.get("arrangement")
    if isinstance(arrangement, dict):
        payload["arrangement"] = {
            name: arrangement[name] for name in _SEED_ARRANGEMENT_FIELDS
        }
    if payload.get("mode") == "additive":
        payload.pop("mode", None)
    if payload.get("carve_depth") is None:
        payload.pop("carve_depth", None)
    variation_payload = payload.get("variation")
    if isinstance(variation_payload, dict):
        fields = _variation_seed_fields(ins)
        if fields is None:
            # variation なしの Instruction と同じ key にする (pop ではなく None)。
            payload["variation"] = None
        elif fields is not _VARIATION_SEED_FIELDS_ALL:
            payload["variation"] = {
                name: value
                for name, value in variation_payload.items()
                if name in fields
            }
    surface = payload.get("surface")
    if isinstance(surface, dict):
        if surface.get("spacing_gradient") == "none":
            surface.pop("spacing_gradient", None)
        if surface.get("tone_steps") == 3:
            surface.pop("tone_steps", None)
    key = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if performance_seed is not None:
        key += f":render:{performance_seed}".encode("utf-8")
    digest = hashlib.sha256(key).digest()
    return struct.unpack("<Q", digest[:8])[0]


def new_render_seed() -> int:
    """演奏ごとのマクロ揺らぎ seed。明示 seed 指定時は再現可能。"""
    return secrets.randbits(53)


def _performance_touch_filter(render_seed: int, canvas: CanvasSize) -> tuple[str, str]:
    """固定図形にも seed ごとの微細な輪郭差を与える display 用 filter。

    baseFrequency は 1/px 単位なので canvas.unit に反比例、変位量は比例させる。
    unit=1000 では現行の値と一致する。
    """
    seed = int(render_seed)
    unit_scale = _unit_scale(canvas)
    filter_id = _safe_svg_id(f"performance_touch_{seed % 100000}")
    frequency = (
        0.012 + _hash01(0, seed, "performance-touch-frequency") * 0.008
    ) / unit_scale
    scale = (1.6 + _hash01(1, seed, "performance-touch-scale") * 1.4) * unit_scale
    xml = (
        f'<filter id="{filter_id}" x="-2%" y="-2%" width="104%" height="104%" color-interpolation-filters="sRGB">'
        f'<feTurbulence type="fractalNoise" baseFrequency="{fmt(frequency)}" numOctaves="2" '
        f'seed="{seed % 9973}" result="touchNoise"/>'
        f'<feDisplacementMap in="SourceGraphic" in2="touchNoise" scale="{fmt(scale)}" '
        'xChannelSelector="R" yChannelSelector="G"/>'
        "</filter>"
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


_CONTOUR_VARIATION_DIMS = ("position_x", "position_y", "radius")


def _needs_contour_variation(v: Variation | None) -> bool:
    """弧・閉図形の輪郭揺らぎ。line のゲートと対称で、図形の自然軸として radius を加える。"""
    if v is None:
        return False
    if v.quality in ("none", "pink"):
        return False
    return any(d in _CONTOUR_VARIATION_DIMS for d in v.dimensions)


def _wave_phase(seed: int) -> float:
    """seed から [0, 2π) の位相を決定的に導出する。

    wave は sin の位相が固定だと演奏 seed に依存せず、同じ Score が常に同じ
    山谷の位置になる。位相だけを seed 由来にすることで、周期性 (整数周波数
    なら t∈[0,1) で閉じる) と振幅・周波数の語彙を保ったまま演奏差を作る。
    """
    return _hash01(0, seed, "wave-phase") * 2 * math.pi


def _ellipse_perimeter(rx: float, ry: float) -> float:
    """楕円の周長 (Ramanujan の第二近似)。"""
    a, b = abs(rx), abs(ry)
    if a + b <= 0:
        return 0.0
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def _representative_size_px(ins: Instruction, canvas: CanvasSize) -> float:
    """揺らぎ振幅の基準となる図形の代表寸法 (px)。

    circle は半径、ellipse は半径の相乗平均、square/triangle は短辺の 1/2、
    polygon は外接半径、line は線長、arc は半径 (弦長ではない。touching の
    接点契約と整合させるため)。
    """
    p = ins.primitive
    if p in ("circle", "polygon", "arc") and ins.radius is not None:
        return ins.radius * canvas.unit
    if p == "ellipse" and ins.size is not None:
        rx = ins.size[0] * canvas.width / 2
        ry = ins.size[1] * canvas.height / 2
        return math.sqrt(max(0.0, rx * ry))
    if p in ("square", "triangle", "cloudform") and ins.size is not None:
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
        return min(w, h) / 2
    if p == "line":
        start = _px(ins.from_ if ins.from_ is not None else (0.5, 0.0), canvas)
        end = _px(ins.to if ins.to is not None else (0.5, 1.0), canvas)
        return math.hypot(end[0] - start[0], end[1] - start[1])
    return canvas.unit * REPRESENTATIVE_MIN_RATIO


def _clamped_representative_px(ins: Instruction, canvas: CanvasSize) -> float:
    return max(
        _representative_size_px(ins, canvas), canvas.unit * REPRESENTATIVE_MIN_RATIO
    )


def _amplitude_px(variation: Variation, ins: Instruction, canvas: CanvasSize) -> float:
    """Wobble amplitude (px), measured in stroke widths of the mark itself.

    `_stroke_width_px` is a pure function of the instruction, so this can ask it
    directly rather than having the seven call sites thread the width through.
    The representative-size clamp stays: it is the safety valve that keeps a
    figure smaller than its own mark from wandering further than it is wide.
    """
    width = _stroke_width_px(ins.weight, canvas, ins.thinness)
    rep = _clamped_representative_px(ins, canvas)
    amp = AMPLITUDE_WIDTHS[variation.amplitude] * PRIMITIVE_AMP_GAIN.get(
        ins.primitive, 1.0
    )
    return min(amp * width, AMPLITUDE_CLAMP_RATIO * rep)


def _blur_std_px(variation: Variation, ins: Instruction, canvas: CanvasSize) -> float:
    """滲み (quality=pink) の stdDeviation (px)。"""
    rep = _clamped_representative_px(ins, canvas)
    return max(canvas.unit * BLUR_MIN_RATIO, BLUR_RATIO[variation.amplitude] * rep)


def _segment_count(path_len_px: float, canvas: CanvasSize) -> int:
    """輪郭・線の長さに比例した分割数 (セグメント長をほぼ一定に保つ)。"""
    target = canvas.unit * SEGMENT_TARGET_RATIO
    if target <= 0:
        return SEGMENT_COUNT_MIN
    return max(
        SEGMENT_COUNT_MIN, min(SEGMENT_COUNT_MAX, int(round(path_len_px / target)))
    )


def _stroke_sample_count(length_px: float, canvas: CanvasSize) -> int:
    """手描きストロークの分割数。長さ = canvas.unit で現行の 49 本。"""
    target = canvas.unit * STROKE_SAMPLE_TARGET_RATIO
    if target <= 0:
        return STROKE_SAMPLE_MIN
    return max(
        STROKE_SAMPLE_MIN, min(STROKE_SAMPLE_MAX, int(round(length_px / target)))
    )


def _sample_offset(
    t: float, variation: Variation, seed: int, segment: int, amp: float
) -> float:
    freq = FREQUENCY_CYCLES[variation.frequency]
    q = variation.quality

    if q == "wave":
        return math.sin(t * 2 * math.pi * freq + _wave_phase(seed)) * amp
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
    amp: float,
    canvas: CanvasSize,
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

    segments = _segment_count(length, canvas)
    pts: list[tuple[float, float]] = [start_px]
    for i in range(1, segments):
        t = i / segments
        x = start_px[0] + t * dx
        y = start_px[1] + t * dy
        off = _sample_offset(t, variation, seed, i, amp)

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


def _periodic_value_noise_1d(x: float, seed: int, period: int) -> float:
    """周期境界つき value noise。閉じた輪郭の継ぎ目を連続にする。"""
    xi = math.floor(x)
    xf = x - xi
    v1 = _hash_to_unit(int(xi) % period, seed)
    v2 = _hash_to_unit((int(xi) + 1) % period, seed)
    t = xf * xf * (3 - 2 * xf)
    return v1 * (1 - t) + v2 * t


def _sample_offset_periodic(
    t: float, variation: Variation, seed: int, segment: int, amp: float
) -> float:
    """閉輪郭用の offset サンプル。t∈[0,1) を一周として周期連続にする。

    wave は FREQUENCY_CYCLES が整数値のため自動的に閉じる。seed 由来の位相を
    足しても周期は変わらないので閉合は保たれる。perlin は格子を周期化する。
    white は頂点毎の独立雑音なので継ぎ目の概念を持たない。
    """
    freq = FREQUENCY_CYCLES[variation.frequency]
    q = variation.quality
    if q == "wave":
        return math.sin(t * 2 * math.pi * freq + _wave_phase(seed)) * amp
    if q == "perlin":
        return _periodic_value_noise_1d(t * freq, seed, max(1, int(round(freq)))) * amp
    if q == "white":
        return _hash_to_unit(segment, seed) * amp
    return 0.0


def _offset_contour_point(
    x: float,
    y: float,
    off: float,
    center: tuple[float, float],
    axis_x: bool,
    axis_y: bool,
) -> tuple[float, float]:
    """dimensions の指定に応じて輪郭上の 1 点をずらす (line と対称の意味論)。

    position_x のみ: x 軸方向 / position_y のみ: y 軸方向 /
    両方または radius: 輪郭法線 (中心から外向き) 方向。
    """
    if axis_x and not axis_y:
        return (x + off, y)
    if axis_y and not axis_x:
        return (x, y + off)
    dx = x - center[0]
    dy = y - center[1]
    norm = math.hypot(dx, dy)
    if norm <= 1e-6:
        return (x, y)
    return (x + off * dx / norm, y + off * dy / norm)


def _closed_contour_with_variation(
    points: list[tuple[float, float]],
    center: tuple[float, float],
    variation: Variation,
    seed: int,
    amp: float,
) -> list[tuple[float, float]]:
    """閉じた輪郭の頂点列に周期揺らぎを適用する (circle / ellipse 用)。"""
    dims = set(variation.dimensions)
    axis_x = "position_x" in dims
    axis_y = "position_y" in dims
    n = len(points)
    result: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(points):
        off = _sample_offset_periodic(i / n, variation, seed, i, amp)
        result.append(_offset_contour_point(x, y, off, center, axis_x, axis_y))
    return result


def _edge_contour_with_anchors(
    corners: list[tuple[float, float]],
    variation: Variation | None,
    seed: int,
    amp: float,
    canvas: CanvasSize,
) -> tuple[list[tuple[float, float]], frozenset[int]]:
    """辺ごとに分割した閉輪郭と、角に当たる頂点 index を返す。

    variation を渡すと各辺に line と同じ揺らぎを適用し、分割数は _segment_count
    (揺らぎ輪郭の解像度)。振幅は辺ごとの長さではなく図形の代表寸法から決めた
    amp を共有する (横長の矩形で揺らぎが異方性を持たないようにするため)。
    variation なしは手描きストロークの中心線用で、分割数は line と同じ
    _stroke_sample_count に合わせる (筆の追従遅れの尺度を線と揃えるため)。
    """
    result: list[tuple[float, float]] = []
    anchors: list[int] = []
    n = len(corners)
    for i in range(n):
        start = corners[i]
        end = corners[(i + 1) % n]
        anchors.append(len(result))
        if variation is None:
            segments = _stroke_sample_count(
                math.hypot(end[0] - start[0], end[1] - start[1]), canvas
            )
            edge = [
                (
                    start[0] + (end[0] - start[0]) * k / segments,
                    start[1] + (end[1] - start[1]) * k / segments,
                )
                for k in range(segments + 1)
            ]
        else:
            edge = _line_with_variation(
                start, end, variation, seed + (i + 1) * 7919, amp, canvas
            )
        result.extend(edge[:-1])
    return result, frozenset(anchors)


def _edge_contour_with_variation(
    corners: list[tuple[float, float]],
    variation: Variation,
    seed: int,
    amp: float,
    canvas: CanvasSize,
) -> list[tuple[float, float]]:
    """多角形の各辺に line と同じ揺らぎを適用し、角を固定した閉輪郭を返す。"""
    return _edge_contour_with_anchors(corners, variation, seed, amp, canvas)[0]


def _arc_points_with_variation(
    cx: float,
    cy: float,
    r: float,
    start_deg: float,
    end_deg: float,
    variation: Variation,
    seed: int,
    amp: float,
    canvas: CanvasSize,
) -> list[tuple[float, float]]:
    """弧を分割し揺らぎを注入する。両端点は固定 (touching 接点契約の維持)。"""
    arc_len = r * abs(math.radians(end_deg) - math.radians(start_deg))
    base = _arc_points(
        cx, cy, r, start_deg, end_deg, _segment_count(arc_len, canvas) + 1
    )
    dims = set(variation.dimensions)
    axis_x = "position_x" in dims
    axis_y = "position_y" in dims
    last = len(base) - 1
    result: list[tuple[float, float]] = [base[0]]
    for i in range(1, last):
        x, y = base[i]
        off = _sample_offset(i / last, variation, seed, i, amp)
        result.append(_offset_contour_point(x, y, off, (cx, cy), axis_x, axis_y))
    result.append(base[last])
    return result


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
        return base**1.35
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
    jitter_a = _hash01(i, seed, "a") - 0.5
    jitter_b = _hash01(i, seed, "b") - 0.5

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


def _resolve_at_region(ins: Instruction, seed: int, index: int) -> Instruction:
    if ins.at is None:
        return ins
    x0, y0, x1, y1 = ins.at.region
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


def _resolve_performance_score(score: Score, performance_seed: int | None) -> Score:
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
            x0, y0, x1, y1 = ins.at.region
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
            )
            for i in range(n)
        ]
        result = [_shift(ins, tx - ax, ty - ay) for tx, ty in targets]
        return _finish_expanded_group(result, arr, member_seed=member_seed)

    if arr.layout == "horizontal":
        if arr.path != "none":
            targets = [
                _path_pos(i, n, seed, margin, arr.path, arr.rhythm_spacing)
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
                _path_pos(i, n, seed, margin, arr.path, arr.rhythm_spacing)
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
        targets = [
            (
                cx
                + r
                * math.cos(
                    math.radians(_rhythm_t(i, n, seed, arr.rhythm_spacing) * 360)
                ),
                cy
                - r
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
            _path_pos(i, n, seed, margin, arr.path, arr.rhythm_spacing)
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


def _inject_blur_filters(
    svg: str,
    blur_needed: dict[str, float],
    blur_elems: list[tuple[str, str]],
) -> str:
    """feGaussianBlur フィルター定義を defs に注入し、対象要素に filter 属性を付与する。

    blur_needed の key は filter id (振幅名 + std 値)。滲みは図形寸法比なので
    同じ振幅語でも図形ごとに std が変わる。
    """
    filter_xml = "".join(
        f'<filter id="{filter_id}" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feGaussianBlur in="SourceGraphic" stdDeviation="{fmt(std)}"/>'
        f"</filter>"
        for filter_id, std in sorted(blur_needed.items())
    )
    # svgwrite は "<defs />" を出力する (スペースあり)
    if "<defs />" in svg:
        svg = svg.replace("<defs />", f"<defs>{filter_xml}</defs>", 1)
    elif "<defs/>" in svg:
        svg = svg.replace("<defs/>", f"<defs>{filter_xml}</defs>", 1)
    else:
        svg = svg.replace("<defs>", f"<defs>{filter_xml}", 1)

    for eid, filter_id in blur_elems:
        id_start = svg.find(f'id="{eid}"')
        if id_start < 0:
            continue
        tag_start = svg.rfind("<", 0, id_start)
        tag_end = svg.find(">", id_start)
        if tag_start < 0 or tag_end < 0:
            continue
        if ' filter="' in svg[tag_start:tag_end]:
            continue
        svg = svg.replace(
            f'id="{eid}"', f'id="{eid}" filter="url(#{filter_id})"', 1
        )
    return svg


def _inject_texture_filters(
    svg: str, filters: set[str], canvas: CanvasSize
) -> str:
    if not filters:
        return svg
    filter_xml = "".join(
        _texture_filter_xml(weight, canvas) for weight in sorted(filters)
    )
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


def _texture_seed(
    ground: CanvasGroundSpec, kind: str, render_seed: int | None, index: int = 0
) -> int:
    """支持体の同一性だけから質感 seed を作る (render engine 15)。

    engine 14 までは Score 全体の dump をハッシュしていたため、地と無関係な変更 —
    instruction に coerce が書き込む色注記や、描画に一度も読まれない `absorbency` —
    が地の粒配置を動かしていた。地の seed が決めているのは「どの紙か」であって
    「どれだけ濃いか」ではないので、材質と紙目、そして演奏 seed だけを材料にする。
    `opacity` を上げれば同じ紙が濃くなり、`density` を上げれば同じ紙に粒が足される
    (先頭の粒は動かない)。`tone` は色調であって支持体ではない。
    """
    payload = {"material": ground.material, "grain": ground.grain}
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


# 支持体ごとの雑音の性格。(x 倍率, y 倍率, numOctaves, 横方向のぼかし)
# 粒の細かさは grain が決め、material はその粒の形を決める。
_GROUND_MATERIAL_NOISE = {
    "washi": (0.30, 1.70, 3, 0.0),
    "ink_wash": (0.10, 0.85, 2, 2.4),
}


def _ground_filter_xml(ground: CanvasGroundSpec, seed: int, filter_id: str) -> str:
    """地の雑音。**要素を足さずに**支持体の違いを出す。

    地は塗りつぶし 1 枚と、雑音をかけた 1 枚でできている。支持体の違いを
    描画要素として積むと、DDL が明示した図形より地のほうが要素数を食う
    （繊維を 38 本引いた版では、地だけで絵全体の 46% を占めた）。
    支持体は雑音の性格であって、描くものではない。

    - `washi` は楮の繊維が漉き込まれているので、雑音を一方向へ引き伸ばし、
      直交する向きにもう一枚重ねて交差させる
    - `ink_wash` は刷毛が横へ通っているので、横に長く引き伸ばして
      さらに横方向へぼかす
    """
    base = {"fine": 0.95, "medium": 0.55, "coarse": 0.28, "none": 0.45}.get(
        ground.grain, 0.55
    )
    shape = _GROUND_MATERIAL_NOISE.get(ground.material)
    tail = (
        '<feColorMatrix in="noise" type="saturate" values="0" result="mono"/>'
        '<feComponentTransfer in="mono"><feFuncA type="table" tableValues="0 1"/></feComponentTransfer>'
    )
    head = f'<filter id="{filter_id}" x="0" y="0" width="100%" height="100%">'
    if shape is None:
        return (
            f"{head}"
            f'<feTurbulence type="fractalNoise" baseFrequency="{base:g}" numOctaves="2" seed="{seed % 9973}" result="noise"/>'
            f"{tail}</filter>"
        )
    fx, fy, octaves, blur = shape
    warp = (
        f'<feTurbulence type="fractalNoise" baseFrequency="{base * fx:g} {base * fy:g}"'
        f' numOctaves="{octaves}" seed="{seed % 9973}" result="warp"/>'
    )
    if ground.material == "washi":
        # 繊維は一方向には寝ていない。直交する二枚を交差させる。
        cross = (
            f'<feTurbulence type="fractalNoise" baseFrequency="{base * fy:g} {base * fx:g}"'
            f' numOctaves="{octaves}" seed="{(seed + 7919) % 9973}" result="cross"/>'
            '<feBlend in="warp" in2="cross" mode="multiply" result="noise"/>'
        )
        return f"{head}{warp}{cross}{tail}</filter>"
    smear = f'<feGaussianBlur in="warp" stdDeviation="{blur:g} 0" result="noise"/>'
    return f"{head}{warp}{smear}{tail}</filter>"


def _render_canvas_ground(
    dwg: svgwrite.Drawing,
    score: Score,
    canvas: CanvasSize,
    bg: str,
    *,
    profile: str,
    render_seed: int | None,
):
    ground = _score_canvas_ground(score)
    if ground is None:
        return None, None
    seed = int(
        ground.seed
        if ground.seed is not None
        else _texture_seed(ground, "canvas-ground", render_seed)
    )
    tone = _ground_tone_color(ground, bg)
    group = dwg.g(id="layer_01_canvas_ground")
    if ground.material == "mezzotint":
        shift = canvas.unit * (0.001 + _hash01(0, seed, "register-shift") * 0.003)
        angle = _hash01(1, seed, "register-angle") * math.tau
        group.translate(math.cos(angle) * shift, math.sin(angle) * shift)
    group.add(
        dwg.rect(
            insert=(0, 0), size=(canvas.width, canvas.height), fill=tone, opacity=0.98
        )
    )
    color = (
        "#b8b8b8"
        if ground.material == "mezzotint"
        else ("#777777" if ground.material != "charcoal_ground" else "#222222")
    )
    if profile == "display":
        fid = _safe_svg_id(f"ground_texture_{seed % 100000}")
        texture_opacity = min(0.18, max(0.02, ground.opacity))
        group.add(
            dwg.rect(
                insert=(0, 0),
                size=(canvas.width, canvas.height),
                fill="#777777",
                opacity=texture_opacity,
                filter=f"url(#{fid})",
            )
        )
        return group, _ground_filter_xml(ground, seed, fid)
    count = _ground_dot_count(ground, profile)
    if ground.material == "ink_wash":
        # 刷毛が薄墨を通したあとの紙は、粒の見えかたが落ちる。
        count = max(4, int(count * 0.6))
    radius = {"fine": 0.7, "medium": 1.1, "coarse": 1.8, "none": 0.6}.get(
        ground.grain, 1.0
    )
    for i in range(count):
        x = _hash01(i, seed, "ground-x") * canvas.width
        y = _hash01(i, seed, "ground-y") * canvas.height
        if ground.material == "washi":
            # 同じ数の粒を、繊維の向きに引き伸ばす。要素は増やさない。
            angle = _hash01(i, seed, "fiber-angle") * math.tau
            half = radius * (2.2 + _hash01(i, seed, "fiber-len") * 3.4)
            dx, dy = math.cos(angle) * half, math.sin(angle) * half
            bow = (_hash01(i, seed, "fiber-bow") - 0.5) * half * 0.5
            group.add(
                dwg.path(
                    d=(
                        f"M {x - dx:.6f} {y - dy:.6f} "
                        f"Q {x - math.sin(angle) * bow:.6f} {y + math.cos(angle) * bow:.6f} "
                        f"{x + dx:.6f} {y + dy:.6f}"
                    ),
                    fill="none",
                    stroke=color,
                    stroke_width=max(0.4, radius * 0.5),
                    stroke_opacity=min(0.18, ground.opacity),
                    stroke_linecap="round",
                )
            )
            continue
        if ground.material == "ink_wash":
            # 刷毛の通ったところは濃い。粒の濃さを横帯で上下させる。
            band = 0.55 + 0.45 * math.sin(
                y / canvas.height * math.tau * 1.5 + _hash01(0, seed, "wash-phase") * math.tau
            )
            group.add(
                dwg.circle(
                    center=(x, y),
                    r=radius * (0.55 + _hash01(i, seed, "ground-r") * 0.8),
                    fill=color,
                    opacity=min(0.18, ground.opacity) * band,
                )
            )
            continue
        if ground.grain == "coarse" and i % 3 == 0:
            group.add(
                dwg.line(
                    start=(x - radius * 2.4, y),
                    end=(x + radius * 2.4, y + _hash_to_unit(i, seed) * radius),
                    stroke=color,
                    stroke_width=max(0.4, radius * 0.45),
                    stroke_opacity=min(0.18, ground.opacity),
                    stroke_linecap="round",
                )
            )
        else:
            group.add(
                dwg.circle(
                    center=(x, y),
                    r=radius * (0.55 + _hash01(i, seed, "ground-r") * 0.8),
                    fill=color,
                    opacity=min(0.18, ground.opacity),
                )
            )
    return group, None


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


def _shape_bbox(
    ins: Instruction, canvas: CanvasSize
) -> tuple[float, float, float, float] | None:
    if ins.primitive == "circle" and ins.center is not None and ins.radius is not None:
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        return cx - r, cy - r, r * 2, r * 2
    if ins.primitive == "ellipse" and ins.center is not None and ins.size is not None:
        cx, cy = _px(ins.center, canvas)
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
        return cx - w / 2, cy - h / 2, w, h
    if ins.primitive == "cloudform" and ins.center is not None and ins.size is not None:
        cx, cy = _px(ins.center, canvas)
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
        return cx - w * 0.56, cy - h * 0.56, w * 1.12, h * 1.12
    if (
        ins.primitive in ("square", "triangle")
        and ins.position is not None
        and ins.size is not None
    ):
        x, y = _px(ins.position, canvas)
        return x, y, ins.size[0] * canvas.width, ins.size[1] * canvas.height
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
        rx = ins.size[0] * canvas.width / 2
        ry = ins.size[1] * canvas.height / 2
        return _circle_points(
            cx, cy, rx, ry, _stroke_sample_count(_ellipse_perimeter(rx, ry), canvas)
        )
    if (
        ins.primitive in ("square", "triangle")
        and ins.position is not None
        and ins.size is not None
    ):
        x, y = _px(ins.position, canvas)
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
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
            (ins.size[0] * canvas.width, ins.size[1] * canvas.height),
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
SURFACE_DAB_SAMPLES = 5
SURFACE_WASH_LAYERS = 2
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
        max(_stroke_width_px(ins.weight, canvas, ins.thinness), radius * 1.3),
        ins.weight,
        _surface_stroke_seed(seed, index),
        closed=False,
        grid_step=_grid_step_px(ins.weight, canvas),
        wild=wild,
    )
    path_attrs = {
        "d": contour_stroke_path(stroke),
        "fill": color,
        "fill_opacity": opacity,
        "stroke": "none",
        "class_": f"surface-stroke-v1{' ' + class_ if class_ else ''}",
    }
    if use_filters and ins.weight in TEXTURE_FILTER_WEIGHTS and ins.weight != "drypoint":
        path_attrs["filter"] = f"url(#texture-{ins.weight})"
    group.add(dwg.path(**path_attrs))


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
    )
    path_attrs = {
        "d": contour_stroke_path(stroke),
        "fill": color,
        "fill_opacity": opacity,
        "stroke": "none",
        "class_": "surface-stroke-v1",
    }
    if use_filters and ins.weight in TEXTURE_FILTER_WEIGHTS and ins.weight != "drypoint":
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
    if surface.texture in {"stipple", "grain", "paper_grain"}:
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
                    _stroke_width_px(ins.weight, canvas, ins.thinness),
                    spacing * (0.44 + _hash01(index, seed, "wash-width") * 0.30),
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
                    opacity * 0.42,
                    seed=seed,
                    index=index,
                    wild=wild,
                    use_filters=use_filters,
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
                start = (cx + ox - lux * span / 2, cy + oy - luy * span / 2)
                end = (cx + ox + lux * span / 2, cy + oy + luy * span / 2)
                line_width = max(0.45, canvas.unit * 0.0016)
                hatch_class = f"hatch-spacing-{spacing * gradient:.3f}"
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
                count_samples = max(2, _stroke_sample_count(span, canvas))
                centerline = [
                    (
                        start[0] + (end[0] - start[0]) * i / (count_samples - 1),
                        start[1] + (end[1] - start[1]) * i / (count_samples - 1),
                    )
                    for i in range(count_samples)
                ]
                hatch_stroke = synthesize_along(
                    centerline,
                    line_width,
                    ins.weight,
                    _fill_stroke_seed(seed, i + layer_index * 4096),
                    closed=False,
                    grid_step=_grid_step_px(ins.weight, canvas),
                    wild=wild,
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
                and ins.weight in TEXTURE_FILTER_WEIGHTS
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
        or surface.texture == "none"
        or ins.primitive not in _CLOSED_SHAPES
    ):
        return None, None
    contour = _surface_contour(
        ins, canvas, render_seed=render_seed, ins_idx=ins_idx, mark_idx=mark_idx
    )
    if contour is None or len(contour) < 3:
        return None, None
    seed = _surface_seed(ins, ins_idx, mark_idx, render_seed)
    gid = _safe_svg_id(f"surface_{ins_idx:03d}_{mark_idx:03d}_{surface.texture}")
    group = dwg.g(id=gid)
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
    )
    return group, None


def build_texture_metadata(score: Score, *, svg_profile: str | None = None) -> dict:
    profile = _normalize_svg_profile(svg_profile)
    ground = _score_canvas_ground(score)
    surfaces = []
    for idx, ins in enumerate(score.instructions):
        if ins.surface is not None and ins.surface.texture != "none":
            surfaces.append(
                {
                    "instruction_index": idx,
                    "texture": ins.surface.texture,
                    "density": ins.surface.density,
                    "opacity": ins.surface.opacity,
                }
            )
    metadata = {
        "render_texture_version": "1",
        "render_texture_profile": profile,
        "texture_degraded": profile == "compat" and bool(surfaces),
    }
    if ground is not None:
        metadata["render_canvas_ground"] = ground.model_dump(
            mode="json", exclude_none=True
        )
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
    desc = (
        "Generated by inku. Groups and IDs are included for vector editing."
        if profile == "editable"
        else "Generated by inku. Portable SVG output."
    )
    metadata = json.dumps(
        {"generator": "inku", "svg_profile": profile},
        ensure_ascii=False,
        separators=(",", ":"),
    )
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
    catalog_id: str | None = None,
    canvas_aspect: str | None = None,
    svg_profile: str | None = None,
    render_seed: int | None = None,
    composition_seed: int | None = None,
    wild: bool = False,
) -> str:
    profile = _normalize_svg_profile(svg_profile)
    score = _resolve_performance_score(score, render_seed)
    structured = profile != "display"
    use_filters = profile == "display"
    cmap = {**COLOR_MAP, **(color_map or {})}
    work_assignment = _work_color_assignment(cmap, render_seed, catalog_id)
    canvas = canvas_size_for_aspect(canvas_aspect or _score_canvas_aspect(score))
    dwg = svgwrite.Drawing(
        size=(canvas.width, canvas.height),
        viewBox=f"0 0 {canvas.width} {canvas.height}",
    )
    bg = work_assignment.get(score.background, cmap.get(score.background, BACKGROUND))
    ground_layer, ground_filter_xml = _render_canvas_ground(
        dwg, score, canvas, bg, profile=profile, render_seed=render_seed
    )
    surface_filter_xml: list[str] = []
    performance_filter_xml: str | None = None
    if structured:
        artboard = dwg.g(id="inku_artboard")
        background = dwg.g(id="layer_00_background")
        background.add(
            dwg.rect(
                insert=(0, 0),
                size=(canvas.width, canvas.height),
                fill=bg,
                id="background",
            )
        )
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
        performance_filter_id, performance_filter_xml = _performance_touch_filter(
            render_seed, canvas
        )
        content["filter"] = f"url(#{performance_filter_id})"

    blur_needed: dict[str, float] = {}
    texture_filters = _texture_filter_weights(score) if use_filters else set()
    blur_elems: list[tuple[str, str]] = []
    elem_idx = 0

    ordered_instructions = sorted(
        enumerate(score.instructions), key=lambda pair: pair[1].mode == "carve"
    )
    # Placement is the composition seed's, the touch stays the performance
    # seed's. Read with `is None` and never with `or`: 0 is a seed a caller can
    # legitimately state, and it is how the rest of the server reads this field
    # (db.py:1911). Without a composition seed the placement falls back to the
    # performance seed, so every drawing made before this split replays.
    placement_seed = composition_seed if composition_seed is not None else render_seed
    for ins_idx, ins in ordered_instructions:
        expanded = (
            _expand_arrangement(
                ins, placement_seed, canvas, performance_seed=render_seed
            )
            if ins.arrangement
            else [ins]
        )
        instruction_group = (
            dwg.g(id=_instruction_svg_id(ins, ins_idx)) if structured else content
        )
        for mark_idx, single in enumerate(expanded):
            element = _render_instruction(
                dwg,
                single,
                cmap,
                canvas,
                work_assignment=work_assignment,
                use_filters=use_filters,
                render_seed=render_seed,
                ins_idx=ins_idx,
                mark_idx=mark_idx,
                wild=wild,
            )
            if element is not None:
                if structured:
                    element["id"] = _mark_svg_id(single, ins_idx, mark_idx)
                elif _needs_blur(single.variation):
                    v = single.variation
                    assert v is not None
                    # 滲みは図形寸法比なので、filter は振幅名ではなく値で識別する
                    std = _blur_std_px(v, single, canvas)
                    filter_id = f"blur-{v.amplitude}-{int(round(std * 10))}"
                    blur_needed[filter_id] = std
                    eid = f"e{elem_idx}"
                    element["id"] = eid
                    blur_elems.append((eid, filter_id))
                instruction_group.add(element)
            surface_group, surface_filter = _render_surface_texture(
                dwg,
                single,
                cmap,
                work_assignment,
                canvas,
                profile=profile,
                render_seed=render_seed,
                ins_idx=ins_idx,
                mark_idx=mark_idx,
                wild=wild,
                use_filters=use_filters,
            )
            if surface_group is not None:
                instruction_group.add(surface_group)
            if surface_filter is not None:
                surface_filter_xml.append(surface_filter)
            elem_idx += 1
        if structured:
            content.add(instruction_group)

    is_print = (
        _score_canvas_ground(score) is not None
        and _score_canvas_ground(score).material == "mezzotint"
        or any(ins.weight in {"burin", "drypoint"} for ins in score.instructions)
    )
    if is_print and render_seed is not None:
        plate_opacity = 0.02 + _hash01(0, int(render_seed), "plate-tone") * 0.04
        plate = dwg.rect(
            insert=(0, 0),
            size=(canvas.width, canvas.height),
            fill="#111111",
            opacity=plate_opacity,
            id="layer_15_plate_tone",
        )
        content.add(plate)

    presence_layer = _render_presence_layer(
        dwg, score, cmap, canvas, work_assignment=work_assignment
    )
    if presence_layer is not None:
        presence_content.add(presence_layer)

    if structured:
        dwg.add(artboard)
    else:
        dwg.add(content)
    svg = dwg.tostring()
    if ground_filter_xml or surface_filter_xml or performance_filter_xml:
        extra_filter_xml = (
            (ground_filter_xml or "")
            + "".join(surface_filter_xml)
            + (performance_filter_xml or "")
        )
        if "<defs />" in svg:
            svg = svg.replace("<defs />", f"<defs>{extra_filter_xml}</defs>", 1)
        elif "<defs/>" in svg:
            svg = svg.replace("<defs/>", f"<defs>{extra_filter_xml}</defs>", 1)
        else:
            svg = svg.replace("<defs>", f"<defs>{extra_filter_xml}", 1)
    svg = _inject_texture_filters(svg, texture_filters, canvas)
    if blur_elems:
        svg = _inject_blur_filters(svg, blur_needed, blur_elems)
    if structured:
        svg = _inject_svg_document_metadata(svg, profile=profile)
    return _apply_master_grid(svg)


_CLOSED_SHAPES = frozenset(
    {"circle", "ellipse", "square", "triangle", "polygon", "cloudform"}
)


def _texture_filter_weights(score: Score) -> set[str]:
    weights: set[str] = set()
    for ins in score.instructions:
        if ins.weight in TEXTURE_FILTER_WEIGHTS:
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
    presence_json = (
        score.presence.model_dump_json() if score.presence is not None else ""
    )
    instruction_key = "|".join(
        f"{ins.primitive}:{ins.color}:{ins.weight}:{ins.arrangement.count if ins.arrangement else 1}"
        for ins in score.instructions
    )
    digest = hashlib.sha256(
        f"{presence_json}|{instruction_key}".encode("utf-8")
    ).digest()
    return struct.unpack("<Q", digest[:8])[0]


def _render_presence_layer(
    dwg: svgwrite.Drawing,
    score: Score,
    cmap: dict[str, str],
    canvas: CanvasSize,
    *,
    work_assignment: dict[str, str],
):
    """抽象化された存在感を描く。自然文キーワードや具象部品はここでは扱わない。"""
    presence = score.presence
    if presence is None or presence.kind == "none":
        return None

    cx, cy = _presence_center_px(score, canvas)
    unit = canvas.unit
    color = work_assignment.get("gray", cmap.get("gray", COLOR_MAP["gray"]))
    dark = work_assignment.get("black", cmap.get("black", COLOR_MAP["black"]))
    visual_load = _score_visual_load(score)
    load_opacity = 0.52 if visual_load >= 120 else 0.70 if visual_load >= 60 else 1.0
    intensity_opacity = {"low": 0.13, "medium": 0.21, "high": 0.30}[
        presence.intensity
    ] * load_opacity
    gaze_opacity = {"none": 0.0, "low": 0.11, "medium": 0.18, "high": 0.26}[
        presence.gaze_pressure
    ] * load_opacity
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
            layer.add(
                dwg.line(
                    start=(cx + x_outer, cy + y_shift - radius_y * 0.06),
                    end=(cx + x_inner, cy + y_shift + radius_y * (0.10 + tilt * 0.06)),
                    stroke=color,
                    stroke_width=stroke,
                    stroke_opacity=intensity_opacity * 0.58,
                    stroke_linecap="round",
                )
            )
    elif presence.symmetry == "radial":
        for i in range(6):
            angle = phase + math.tau * i / 6.0
            inner = radius_x * 0.28
            outer = radius_x * 0.86
            layer.add(
                dwg.line(
                    start=(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
                    end=(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
                    stroke=color,
                    stroke_width=stroke,
                    stroke_opacity=intensity_opacity * 0.72,
                    stroke_linecap="round",
                )
            )

    if presence.gaze_pressure != "none":
        for i, side in enumerate((-1, 1, -1, 1, -1, 1)):
            t = (i + 1) / 7
            angle = phase + side * (0.34 + 0.08 * i)
            start_x = cx + math.cos(angle) * radius_x * (1.05 + 0.18 * (i % 2))
            start_y = cy + math.sin(angle) * radius_y * (0.72 + 0.08 * i)
            end_x = cx + math.cos(angle + math.pi) * radius_x * 0.12
            end_y = cy + (t - 0.5) * radius_y * 0.16
            layer.add(
                dwg.line(
                    start=(start_x, start_y),
                    end=(end_x, end_y),
                    stroke=dark,
                    stroke_width=stroke * 0.8,
                    stroke_opacity=gaze_opacity,
                    stroke_linecap="round",
                )
            )

    flow_angle = phase * 0.35 + tilt
    tx, ty = math.cos(flow_angle), math.sin(flow_angle)
    nx, ny = -ty, tx
    for i in range(contour_count):
        t = (i + 0.5) / contour_count
        along = (
            (t - 0.5)
            * radius_x
            * (1.18 + 0.18 * _hash01(i, seed, "presence-flow-span"))
        )
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
            d=f"M {fmt(x1)},{fmt(y1)} Q {fmt(xm)},{fmt(ym)} {fmt(x2)},{fmt(y2)}",
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
            px = (
                cx
                + tx * t * radius_x * 0.78
                + nx * (_hash01(i, seed, "group-x") - 0.5) * radius_x * 0.20
            )
            py = (
                cy
                + ty * t * radius_x * 0.78
                + ny * (_hash01(i, seed, "group-y") - 0.5) * radius_y * 0.58
            )
            layer.add(
                dwg.circle(
                    center=(px, py),
                    r=max(2.0, unit * 0.006),
                    fill=color,
                    fill_opacity=intensity_opacity * 0.72,
                )
            )
    elif presence.kind == "creature_like":
        for i in range(3):
            t = (i - 1) * 0.34
            layer.add(
                dwg.line(
                    start=(cx - radius_x * 0.30 + t * radius_x, cy + radius_y * 0.32),
                    end=(cx - radius_x * 0.05 + t * radius_x, cy + radius_y * 0.44),
                    stroke=color,
                    stroke_width=stroke,
                    stroke_opacity=intensity_opacity * 0.76,
                    stroke_linecap="round",
                )
            )

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


_ASCII_HINT_TOKEN_RE = re.compile(r"^[a-z]+$")
_ASCII_HINT_WORD_RE = re.compile(r"[0-9a-z]+")
_ACHROMATIC_COLORS = ("black", "gray", "white")
_CHROMATIC_COLORS = ("red", "orange", "yellow", "green", "blue", "purple")
_CHROMATIC_BANDS = {
    "red": (345.0, 50.0),
    "orange": (50.0, 80.0),
    "yellow": (80.0, 137.0),
    "green": (137.0, 200.0),
    "blue": (200.0, 280.0),
    "purple": (280.0, 345.0),
}
_CHROMATIC_BAND_CENTERS = {
    "red": 27.5,
    "orange": 65.0,
    "yellow": 108.5,
    "green": 168.5,
    "blue": 240.0,
    "purple": 312.5,
}
_OKLCH_CHROMA_FLOOR = 0.035
_HINT_HUE_PRIORITY = (
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "purple",
    "white",
    "black",
    "gray",
)


def _oklch_from_hex(value: str) -> tuple[float, float, float] | None:
    rgb = _hex_to_rgb(value)
    if rgb is None:
        return None

    def linearize(component: int) -> float:
        channel = component / 255
        return (
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )

    r, g, b = (linearize(component) for component in rgb)
    l_channel = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_channel = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_channel = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_root, m_root, s_root = (
        value ** (1 / 3) if value >= 0 else -((-value) ** (1 / 3))
        for value in (l_channel, m_channel, s_channel)
    )
    lightness = (
        0.2104542553 * l_root
        + 0.7936177850 * m_root
        - 0.0040720468 * s_root
    )
    a = 1.9779984951 * l_root - 2.4285922050 * m_root + 0.4505937099 * s_root
    b_axis = 0.0259040371 * l_root + 0.7827717662 * m_root - 0.8086757660 * s_root
    return lightness, math.hypot(a, b_axis), math.degrees(math.atan2(b_axis, a)) % 360


def _chromatic_band(hue: float) -> str:
    for name, (lower, upper) in _CHROMATIC_BANDS.items():
        if lower > upper:
            if hue >= lower or hue < upper:
                return name
        elif lower <= hue < upper:
            return name
    return "red"


def _circular_hue_distance(left: float, right: float) -> float:
    distance = abs(left - right) % 360
    return min(distance, 360 - distance)


def _work_color_choice(
    candidates: list[str],
    render_seed: int | None,
    catalog_id: str,
    abstract_color: str,
) -> str:
    ordered = sorted(set(candidates))
    if len(ordered) == 1:
        return ordered[0]
    values = {
        "render_seed": render_seed,
        "catalog_id": catalog_id,
        "abstract_color": abstract_color,
    }
    payload = "|".join(str(values[field]) for field in _WORK_COLOR_SEED_FIELDS)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return ordered[int.from_bytes(digest[:8], "big") % len(ordered)]


def _work_color_assignment(
    cmap: dict[str, str],
    render_seed: int | None,
    catalog_id: str | None,
) -> dict[str, str]:
    resolved_catalog_id = catalog_id or DEFAULT_COLOR_CATALOG_ID
    achromatic: list[tuple[float, str]] = []
    chromatic: dict[str, list[str]] = {
        color: [] for color in _CHROMATIC_COLORS
    }
    chromatic_hues: list[tuple[float, str]] = []
    seen: set[str] = set()
    for key, hex_value in cmap.items():
        if not key.startswith("palette:") or hex_value in seen:
            continue
        oklch = _oklch_from_hex(hex_value)
        if oklch is None:
            continue
        seen.add(hex_value)
        lightness, chroma, hue = oklch
        if chroma < _OKLCH_CHROMA_FLOOR:
            achromatic.append((lightness, hex_value))
        else:
            chromatic[_chromatic_band(hue)].append(hex_value)
            chromatic_hues.append((hue, hex_value))

    assignment: dict[str, str] = {}
    remaining = sorted(achromatic)
    for color in _ACHROMATIC_COLORS:
        fallback = cmap.get(color, COLOR_MAP[color])
        exact = next(
            (
                candidate
                for candidate in remaining
                if candidate[1].lower() == fallback.lower()
            ),
            None,
        )
        if exact is not None:
            remaining.remove(exact)
            assignment[color] = exact[1]
    for color in _ACHROMATIC_COLORS:
        if color in assignment:
            continue
        fallback = cmap.get(color, COLOR_MAP[color])
        if not remaining:
            assignment[color] = fallback
            continue
        target = _oklch_from_hex(fallback)
        target_lightness = target[0] if target is not None else 0.0
        best = min(
            remaining,
            key=lambda candidate: (
                abs(candidate[0] - target_lightness),
                candidate[1],
            ),
        )
        remaining.remove(best)
        assignment[color] = best[1]

    for color in _CHROMATIC_COLORS:
        candidates = chromatic[color]
        if candidates:
            assignment[color] = _work_color_choice(
                candidates, render_seed, resolved_catalog_id, color
            )
        elif chromatic_hues:
            target = _CHROMATIC_BAND_CENTERS[color]
            assignment[color] = min(
                chromatic_hues,
                key=lambda candidate: (
                    _circular_hue_distance(candidate[0], target),
                    candidate[1],
                ),
            )[1]
        else:
            assignment[color] = cmap.get(color, COLOR_MAP[color])
    return assignment


def _hint_hues(hint: str) -> set[str]:
    normalized = _norm_label(hint)
    words = set(_ASCII_HINT_WORD_RE.findall(normalized))
    hues: set[str] = set()
    for hue, tokens in HUE_HINTS.items():
        for token in tokens:
            lowered = token.lower()
            if (
                lowered in words
                if _ASCII_HINT_TOKEN_RE.fullmatch(lowered)
                else token in hint
            ):
                hues.add(hue)
                break
    return hues


def _resolve_color(
    color: str,
    color_hint: str | None,
    cmap: dict[str, str],
    *,
    work_assignment: dict[str, str] | None = None,
    render_seed: int | None = None,
    catalog_id: str | None = None,
) -> str:
    assignment = work_assignment or _work_color_assignment(
        cmap, render_seed, catalog_id
    )
    fallback = assignment.get(color, cmap[color])
    if not color_hint:
        return fallback
    desired_hues = _hint_hues(color_hint)
    if desired_hues == {"brown"}:
        return assignment["orange"]
    desired_hues.discard("brown")
    for desired in _HINT_HUE_PRIORITY:
        if desired in desired_hues:
            return assignment[desired]
    return fallback


def _has_surface_texture(ins: Instruction) -> bool:
    """surface が内部を担うか (閉図形のみ。線・弧では surface は描かれない)。"""
    return (
        ins.surface is not None
        and ins.surface.texture != "none"
        and ins.primitive in _CLOSED_SHAPES
    )


def _fills_interior(ins: Instruction) -> bool:
    """内部を埋めるか。

    塗り = 素材の既定の埋め方、`surface` = 明示的な版表現。両方は出さない。
    閉図形が `filled` に関わらず常に塗られていた挙動 (死にフィールド) は
    engine 9 で解消し、`filled` の記述どおりに演奏する。
    """
    if _has_surface_texture(ins):
        return False
    return bool(ins.filled)


def _stroke_attrs(
    ins: Instruction,
    cmap: dict[str, str],
    canvas: CanvasSize,
    *,
    work_assignment: dict[str, str],
    use_filters: bool = True,
) -> dict:
    do_fill = _fills_interior(ins)
    color = _resolve_color(
        ins.color,
        ins.color_hint,
        cmap,
        work_assignment=work_assignment,
    )
    weight_style = WEIGHT_STYLE.get(ins.weight, {})
    hint = _norm_label(ins.color_hint or "")
    attrs = {
        "stroke": color,
        "stroke_width": _stroke_width_px(ins.weight, canvas, ins.thinness),
        "fill": color if do_fill else "none",
        "stroke_linecap": weight_style.get("stroke_linecap", "round"),
    }
    if "stroke_opacity" in weight_style:
        attrs["stroke_opacity"] = weight_style["stroke_opacity"]
    if use_filters and ins.weight in TEXTURE_FILTER_WEIGHTS and ins.weight != "drypoint":
        attrs["filter"] = f"url(#texture-{ins.weight})"
    if any(
        token in hint
        for token in (
            "membrane",
            "haze",
            "fog",
            "mist",
            "atmosphere",
            "膜",
            "霞",
            "霧",
            "靄",
        )
    ):
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
    elif any(
        token in hint for token in ("waiting buds", "開花を待つ蕾", "蕾", "つぼみ")
    ):
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.72)
        if do_fill:
            attrs["fill_opacity"] = 0.58
    elif any(token in hint for token in ("five-sense", "五感")):
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.44)
        if do_fill:
            attrs["fill_opacity"] = 0.18
    elif "fade directional" in hint or "fade=directional" in hint:
        # engine 24: the member's own ceiling when the expansion wrote one, the
        # group-wide constant when it did not (a degenerate group, or a fading
        # instruction that never went through an arrangement).
        level = _fade_level_from_hint(ins.color_hint)
        ceiling = 0.48 if level is None else level
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), ceiling)
        if do_fill:
            attrs["fill_opacity"] = (
                0.30 if level is None
                else round(ceiling * _FADE_FILL_RATIO["directional"], 4)
            )
    elif "fade outward" in hint or "fade=outward" in hint:
        level = _fade_level_from_hint(ins.color_hint)
        ceiling = 0.40 if level is None else level
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), ceiling)
        if do_fill:
            attrs["fill_opacity"] = (
                0.22 if level is None
                else round(ceiling * _FADE_FILL_RATIO["outward"], 4)
            )
    if any(token in hint for token in ("reflection", "反射", "映り")):
        attrs["stroke_opacity"] = min(float(attrs.get("stroke_opacity", 1.0)), 0.52)
    scale = _unit_scale(canvas)
    dash = _scale_dash(STYLE_TO_DASH[ins.style], scale)
    texture_dash = _scale_dash(weight_style.get("stroke_dasharray"), scale)
    if dash:
        attrs["stroke_dasharray"] = dash
    elif texture_dash:
        attrs["stroke_dasharray"] = texture_dash
    return attrs


def _copy_attrs(attrs: dict) -> dict:
    return dict(attrs)


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


def _line_direction(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 1.0, 0.0
    return dx / length, dy / length


def _offset_polyline(
    points: list[tuple[float, float]],
    amount: float,
    *,
    wander: float = 0.0,
    wander_period: float = 1.0,
    seed: int = 0,
) -> list[tuple[float, float]]:
    """Offset an open polyline by `amount` along per-vertex normals.

    The material outline layers used to be straight start->end lines. Once the
    stroke centreline gained a gesture they had to follow that same curve, or the
    straight remnants read as a faint line joining the endpoints.

    `wander` adds a low-frequency drift to the offset along the arc length so the
    strata are not perfectly parallel rails — one of the cues the eye reads as a
    repeating pattern.
    """
    n = len(points)
    if n < 2:
        return list(points)
    out: list[tuple[float, float]] = []
    arc = 0.0
    for i in range(n):
        if i == 0:
            tx, ty = points[1][0] - points[0][0], points[1][1] - points[0][1]
        elif i == n - 1:
            tx, ty = points[-1][0] - points[-2][0], points[-1][1] - points[-2][1]
        else:
            tx, ty = points[i + 1][0] - points[i - 1][0], points[i + 1][1] - points[i - 1][1]
        length = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / length, tx / length
        off = amount
        if wander:
            off += wander * (_value_noise_1d(arc / max(1e-6, wander_period), seed) * 2 - 1)
        out.append((points[i][0] + nx * off, points[i][1] + ny * off))
        if i < n - 1:
            arc += math.hypot(
                points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]
            )
    return out


def _varied_dash_pattern(dash_units: float, mark: float, gap: float, seed: int) -> str:
    """A long, seed-varied dash pattern (unscaled) whose period spans the whole
    line, so no repeating dash cadence is visible. Pairs vary per index and per
    stratum seed; feed through `_scale_dash` to size and format it."""
    period = max(1.0, mark + gap)
    count = max(6, min(28, int(dash_units / period) + 3))
    vals: list[str] = []
    for i in range(count):
        m = mark * (0.5 + 1.3 * _hash01(i, seed, "dash-mark"))
        g = gap * (0.45 + 1.5 * _hash01(i, seed, "dash-gap"))
        vals.append(f"{m:.3f}")
        vals.append(f"{g:.3f}")
    return ",".join(vals)


def _polyline_sample(
    points: list[tuple[float, float]], t: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Position and unit tangent at arc-length fraction `t` (0..1) of a polyline."""
    if len(points) < 2:
        p = points[0] if points else (0.0, 0.0)
        return p, (1.0, 0.0)
    segs = [
        math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
        for i in range(len(points) - 1)
    ]
    total = sum(segs)
    if total < 1e-9:
        return points[0], (1.0, 0.0)
    target = t * total
    acc = 0.0
    for i, d in enumerate(segs):
        if acc + d >= target or i == len(segs) - 1:
            f = (target - acc) / d if d > 1e-9 else 0.0
            x = points[i][0] + (points[i + 1][0] - points[i][0]) * f
            y = points[i][1] + (points[i + 1][1] - points[i][1]) * f
            length = d or 1.0
            ux = (points[i + 1][0] - points[i][0]) / length
            uy = (points[i + 1][1] - points[i][1]) / length
            return (x, y), (ux, uy)
        acc += d
    return points[-1], (1.0, 0.0)


def _add_powder_specks(
    dwg: svgwrite.Drawing,
    group,
    centerline: list[tuple[float, float]],
    attrs: dict,
    seed: int,
    canvas: CanvasSize,
    *,
    count: int,
    spread: float,
    radius: float,
    opacity: float,
) -> None:
    color = attrs.get("stroke", "#111111")
    min_radius = 0.35 * _unit_scale(canvas)
    for idx in range(count):
        # Non-uniform spacing: jitter each speck within its slot so the powder
        # does not sit on an even grid.
        t = min(1.0, max(0.0, (idx + 0.5 + (_hash01(idx, seed, "speck-t") - 0.5)) / count))
        (px, py), (ux, uy) = _polyline_sample(centerline, t)
        perp = _hash_to_unit(idx, seed) * spread
        ox, oy = -uy * perp, ux * perp
        along = _hash_to_unit(idx + 101, seed) * spread * 0.45
        group.add(
            dwg.circle(
                center=(px + ox + ux * along, py + oy + uy * along),
                r=max(
                    min_radius,
                    radius * (0.75 + abs(_hash_to_unit(idx + 202, seed)) * 0.7),
                ),
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
    canvas: CanvasSize,
    *,
    spread: float,
    radius: float,
    opacity: float,
) -> None:
    color = attrs.get("stroke", "#111111")
    min_radius = 0.35 * _unit_scale(canvas)
    for idx, (px, py) in enumerate(points):
        ox = _hash_to_unit(idx, seed) * spread
        oy = _hash_to_unit(idx + 157, seed) * spread
        group.add(
            dwg.circle(
                center=(px + ox, py + oy),
                r=max(
                    min_radius,
                    radius * (0.75 + abs(_hash_to_unit(idx + 263, seed)) * 0.7),
                ),
                fill=color,
                stroke="none",
                opacity=opacity,
            )
        )


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


def _rect_points(
    x: float, y: float, w: float, h: float, count: int
) -> list[tuple[float, float]]:
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


def _arc_points(
    cx: float, cy: float, r: float, start_deg: float, end_deg: float, count: int
) -> list[tuple[float, float]]:
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


def _outline_attrs(
    attrs: dict, *, stroke_width: float, opacity: float, dash: str | None = None
) -> dict:
    result = _copy_attrs(attrs)
    result["fill"] = "none"
    result["stroke_width"] = stroke_width
    result["stroke_opacity"] = opacity
    # 材質装飾であることを明示する。読み手 (弧抽出・ラスタライザ等) が主線と
    # 装飾を区別するのに opacity の大小へ頼らずに済ませるため。
    result["class"] = "material-outline"
    if dash is not None:
        result["stroke_dasharray"] = dash
    return result


_MATERIAL_OUTLINE_SPECS: dict[str, list[tuple[float, float, float, float, str]]] = {
    # (offset_px, 絶対幅_px, base_width 係数, opacity, dasharray)
    "pencil": [(-1.0, 0.45, 0.0, 0.24, "1,7"), (1.2, 0.5, 0.0, 0.20, "1,5")],
    "chalk": [(-3.2, 1.2, 0.0, 0.30, "8,12,1,8"), (3.6, 1.0, 0.0, 0.24, "5,10,1,6")],
    "brush_thin": [(-1.6, 1.0, 0.0, 0.32, "22,9"), (1.8, 1.4, 0.0, 0.28, "14,8")],
    "brush_thick": [
        (-4.0, 0.0, 0.28, 0.36, "18,7,3,11"),
        (3.2, 0.0, 0.22, 0.28, "11,9"),
    ],
    "crayon": [
        (-3.4, 0.0, 0.24, 0.24, "2,5,9,7"),
        (-1.5, 0.0, 0.20, 0.20, "4,8"),
        (2.4, 0.0, 0.22, 0.22, "2,5,9,7"),
    ],
    # engine 15. 本番で最も使われている pen (3261 instruction・1 位) が、本体の
    # ストロークしか持たないまま残っていた。数値は道具の性格を文法テーブル
    # (`stroke_engine.GRAMMARS`) から引いている。
    # pen (つけペン) の痕跡は割れた 2 本の穂先。±1.40px は基準幅 2.0px の帯の縁
    # (±1.0) のすぐ外で、他の道具と同じく帯の実測半幅の 1〜2 倍に収まる。dash は
    # brush_thin の 22,9 より細かく pencil の 1,7 より連続寄りで、穂先らしく
    # ほぼ途切れない。
    "pen": [(-1.40, 0.38, 0.0, 0.24, "14,3"), (1.40, 0.34, 0.0, 0.20, "12,4")],
}

# (基準個数, spread_px, radius_px, opacity)。個数は周長比例の基準値。
_SPECK_SPECS: dict[str, tuple[int, float, float, float]] = {
    "pencil": (18, 1.8, 0.45, 0.20),
    "crayon": (28, 4.0, 0.75, 0.18),
    "chalk": (36, 5.5, 0.9, 0.26),
}


def _material_outline_profile(
    weight: str, canvas: CanvasSize, thinness: str | None = None
) -> list[tuple[float, float, float, str | None]]:
    """材質輪郭の (offset, 線幅, opacity, dasharray)。すべて canvas.unit 相対。

    細く引いた線の材質層は墨と同じだけ細くなる。基準を公称幅に据え置くと、
    墨だけが細って材質が取り残される。
    """
    spec = _MATERIAL_OUTLINE_SPECS.get(weight)
    if not spec:
        return []
    scale = _unit_scale(canvas)
    base_width = _stroke_width_px(weight, canvas, thinness)
    offset_gain = _material_gain("outline_offset")
    opacity_gain = _material_gain("outline_opacity")
    return [
        (
            _outline_offset_px(offset * scale * offset_gain, canvas),
            abs_width * scale + base_width * width_ratio,
            _outline_opacity(opacity * opacity_gain),
            _scale_dash(dash, scale),
        )
        for offset, abs_width, width_ratio, opacity, dash in spec
    ]


def _speck_profile(
    weight: str, path_len_px: float, canvas: CanvasSize
) -> tuple[int, float, float, float] | None:
    """speck の (個数, spread, radius, opacity)。個数は輪郭長比例、寸法は unit 相対。"""
    spec = _SPECK_SPECS.get(weight)
    if spec is None:
        return None
    base_count, spread, radius, opacity = spec
    scale = _unit_scale(canvas)
    return (
        _speck_count(base_count, path_len_px, canvas),
        spread * scale * _material_gain("speck_spread"),
        radius * scale,
        _speck_opacity(opacity),
    )


def _uses_material_outline(weight: str) -> bool:
    return weight in _MATERIAL_OUTLINE_SPECS or weight in _SPECK_SPECS


def _add_material_circle_outline(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    attrs: dict,
    cx: float,
    cy: float,
    r: float,
    canvas: CanvasSize,
    render_seed: int | None = None,
) -> None:
    seed = _seed_for_instruction(ins, render_seed)
    for offset, width, opacity, dash in _material_outline_profile(ins.weight, canvas, ins.thinness):
        group.add(
            dwg.circle(
                center=(cx, cy),
                r=max(0.0, r + offset),
                **_outline_attrs(attrs, stroke_width=width, opacity=opacity, dash=dash),
            )
        )
    specks = _speck_profile(ins.weight, 2 * math.pi * r, canvas)
    if specks is not None:
        count, spread, radius, opacity = specks
        _add_specks_at_points(
            dwg,
            group,
            _circle_points(cx, cy, r, r, count),
            attrs,
            seed,
            canvas,
            spread=spread,
            radius=radius,
            opacity=opacity,
        )


def _add_material_ellipse_outline(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    attrs: dict,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    canvas: CanvasSize,
    render_seed: int | None = None,
) -> None:
    seed = _seed_for_instruction(ins, render_seed)
    for offset, width, opacity, dash in _material_outline_profile(ins.weight, canvas, ins.thinness):
        group.add(
            dwg.ellipse(
                center=(cx, cy),
                r=(max(0.0, rx + offset), max(0.0, ry + offset)),
                **_outline_attrs(attrs, stroke_width=width, opacity=opacity, dash=dash),
            )
        )
    specks = _speck_profile(ins.weight, _ellipse_perimeter(rx, ry), canvas)
    if specks is not None:
        count, spread, radius, opacity = specks
        _add_specks_at_points(
            dwg,
            group,
            _circle_points(cx, cy, rx, ry, count),
            attrs,
            seed,
            canvas,
            spread=spread,
            radius=radius,
            opacity=opacity,
        )


def _add_material_rect_outline(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    attrs: dict,
    x: float,
    y: float,
    w: float,
    h: float,
    canvas: CanvasSize,
    render_seed: int | None = None,
) -> None:
    seed = _seed_for_instruction(ins, render_seed)
    for offset, width, opacity, dash in _material_outline_profile(ins.weight, canvas, ins.thinness):
        group.add(
            dwg.rect(
                insert=(x - offset, y - offset),
                size=(max(0.0, w + offset * 2), max(0.0, h + offset * 2)),
                **_outline_attrs(attrs, stroke_width=width, opacity=opacity, dash=dash),
            )
        )
    specks = _speck_profile(ins.weight, 2 * (w + h), canvas)
    if specks is not None:
        count, spread, radius, opacity = specks
        _add_specks_at_points(
            dwg,
            group,
            _rect_points(x, y, w, h, count),
            attrs,
            seed,
            canvas,
            spread=spread,
            radius=radius,
            opacity=opacity,
        )


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
    canvas: CanvasSize,
    render_seed: int | None = None,
) -> None:
    seed = _seed_for_instruction(ins, render_seed)
    for offset, width, opacity, dash in _material_outline_profile(ins.weight, canvas, ins.thinness):
        group.add(
            dwg.path(
                d=_arc_path_d(cx, cy, max(0.0, r + offset), start_deg, end_deg),
                **_outline_attrs(attrs, stroke_width=width, opacity=opacity, dash=dash),
            )
        )
    arc_len = r * abs(math.radians(end_deg) - math.radians(start_deg))
    specks = _speck_profile(ins.weight, arc_len, canvas)
    if specks is not None:
        count, spread, radius, opacity = specks
        _add_specks_at_points(
            dwg,
            group,
            _arc_points(cx, cy, r, start_deg, end_deg, count),
            attrs,
            seed,
            canvas,
            spread=spread,
            radius=radius,
            opacity=opacity,
        )


def _resample_points(
    path: list[tuple[float, float]], count: int
) -> list[tuple[float, float]]:
    """path から count 点を等間隔 (index 基準) に取り出す。"""
    if count <= 0 or not path:
        return []
    last = len(path)
    return [path[min(last - 1, int(index * last / count))] for index in range(count)]


def _offset_performed_path(
    path: list[tuple[float, float]],
    amount: float,
    closed: bool,
    center: tuple[float, float],
) -> list[tuple[float, float]]:
    """演奏後の中心線を法線方向へ amount だけずらす。正が外側。

    法線の符号は輪郭の生成順で変わる (円は内向き、弧は外向き) ので、図形の中心に
    対して一度だけ多数決で決める。幾何版の `r + offset` と向きを揃えるため。
    """
    normals = centerline_normals(path, closed)
    votes = 0
    for (x, y), (nx, ny) in zip(path, normals):
        votes += 1 if nx * (x - center[0]) + ny * (y - center[1]) >= 0 else -1
    sign = 1.0 if votes >= 0 else -1.0
    return [
        (x + nx * amount * sign, y + ny * amount * sign)
        for (x, y), (nx, ny) in zip(path, normals)
    ]


def _closed_path_length(path: list[tuple[float, float]]) -> float:
    """閉じた折れ線の周長 (px)。粒の個数を周長比例で決めるのに使う。"""
    if len(path) < 2:
        return 0.0
    return sum(
        math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:] + path[:1])
    )


def _points_center(path: list[tuple[float, float]]) -> tuple[float, float]:
    """法線の向きを多数決で決めるための図形中心。厳密な重心である必要はない。"""
    if not path:
        return (0.0, 0.0)
    return (
        sum(x for x, _ in path) / len(path),
        sum(y for _, y in path) / len(path),
    )


def _add_material_performed_outline(
    dwg: svgwrite.Drawing,
    group,
    ins: Instruction,
    attrs: dict,
    path: list[tuple[float, float]],
    canvas: CanvasSize,
    render_seed: int | None,
    *,
    closed: bool,
    path_len_px: float,
    center: tuple[float, float],
) -> None:
    """材質輪郭と粉を、幾何ではなく演奏後の中心線から作る。

    幾何から引くと、墨が暴れたときに材質層だけが元の位置に罫線として取り残される
    (engine 12 が直線で直したのと同じ型の不具合)。呼ぶのは wild のときだけで、
    OFF の出力は幾何版のまま 1 バイトも動かさない。
    """
    seed = _seed_for_instruction(ins, render_seed)
    for offset, width, opacity, dash in _material_outline_profile(ins.weight, canvas, ins.thinness):
        points = _offset_performed_path(path, offset, closed, center)
        element = dwg.polygon if closed else dwg.polyline
        group.add(
            element(
                points=points,
                **_outline_attrs(
                    attrs, stroke_width=width, opacity=opacity, dash=dash
                ),
            )
        )
    specks = _speck_profile(ins.weight, path_len_px, canvas)
    if specks is not None:
        count, spread, radius, opacity = specks
        _add_specks_at_points(
            dwg,
            group,
            _resample_points(path, count),
            attrs,
            seed,
            canvas,
            spread=spread,
            radius=radius,
            opacity=opacity,
        )


# The computer's material layer. A hand tool leaves something beside the
# stroke (graphite dust, bristle, wax); a computer leaves the remainder of
# sampling. The geometry is rounded onto a lattice, and the difference between
# where the ink was headed and the lattice point it landed on is thrown away.
# These cells give that difference back as tone: the geometry repeats without
# error, the material shows where the error went. No seed, so the same figure
# always bleeds the same way.
RASTER_BLEED_OPACITY = 0.45


def _add_raster_bleed(dwg, group, samples, grid_step: float, color: str) -> None:
    """Add one lattice cell per sample the rounding moved, under the stroke."""
    if grid_step <= 0:
        return
    half = grid_step / 2
    for sample in samples:
        if sample.residual <= 0.0:
            continue
        # The cell sits on the lattice, not at the intended position: it is the
        # cell the ink was rounded into.
        x = grid_point(sample.x, grid_step)
        y = grid_point(sample.y, grid_step)
        group.add(
            dwg.rect(
                insert=(x - half, y - half),
                size=(grid_step, grid_step),
                fill=color,
                fill_opacity=RASTER_BLEED_OPACITY * min(1.0, sample.residual / half),
                stroke="none",
                class_="raster-bleed",
            )
        )


def _material_line_group(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    start: tuple[float, float],
    end: tuple[float, float],
    attrs: dict,
    canvas: CanvasSize,
    *,
    use_filters: bool = True,
    include_base: bool = True,
    render_seed: int | None = None,
    centerline: list[tuple[float, float]] | None = None,
):
    # 直線の材質層は閉輪郭とは別実装で、道具ごとの数値もここが独自に持っている。
    # ゲートを `_MATERIAL_OUTLINE_SPECS` から引くことで、表に道具を足したのに
    # 直線だけ裸のまま、という食い違いが起きないようにする (engine 15)。
    if ins.weight not in _MATERIAL_OUTLINE_SPECS:
        return None

    # The texture layers ride the actual (possibly gestured) centreline, not the
    # straight start->end line. Without a centreline they fall back to it.
    path = [tuple(p) for p in centerline] if centerline else [start, end]
    group = dwg.g()
    seed = _seed_for_instruction(ins, render_seed)
    scale = _unit_scale(canvas)
    offset_gain = _material_gain("outline_offset")
    opacity_gain = _material_gain("outline_opacity")
    spread_gain = _material_gain("speck_spread")
    length = math.hypot(end[0] - start[0], end[1] - start[1])

    def _layer_opacity(value: float) -> float:
        return _outline_opacity(value * opacity_gain)

    def _layer_offset(amount: float) -> float:
        return _outline_offset_px(amount * scale * offset_gain, canvas)

    dash_units = length / max(1e-6, scale)

    def _emit_layer(
        amount: float, layer_attrs: dict, mark: float, gap: float, k: int
    ) -> None:
        # Each stratum gets its own seed, so its weave and its dash pattern are
        # out of step with the others; the pattern is long enough to span the
        # line, so no repeating dash cadence is visible.
        la = _copy_attrs(layer_attrs)
        la["fill"] = "none"
        la["class_"] = "material-outline"
        off_px = _layer_offset(amount)
        layer_seed = seed + k * 7919
        wander = 0.35 * abs(off_px) + 0.6 * scale
        pts = _offset_polyline(
            path, off_px, wander=wander, wander_period=60.0 * scale, seed=layer_seed
        )
        la["stroke_dasharray"] = _scale_dash(
            _varied_dash_pattern(dash_units, mark, gap, layer_seed), scale
        )
        group.add(dwg.polyline(points=pts, **la))

    if include_base:
        base = _copy_attrs(attrs)
        base["fill"] = "none"
        base["class_"] = "material-outline"
        group.add(
            dwg.polyline(
                points=_offset_polyline(
                    path, 0.0, wander=0.5 * scale, wander_period=70.0 * scale, seed=seed
                ),
                **base,
            )
        )

    if ins.weight == "pencil":
        for k, amount in enumerate((-0.9, 1.1)):
            layer_attrs = _copy_attrs(attrs)
            layer_attrs["stroke_width"] = 0.45 * scale
            layer_attrs["stroke_opacity"] = _layer_opacity(0.26)
            if use_filters:
                layer_attrs["filter"] = "url(#texture-pencil)"
            _emit_layer(amount, layer_attrs, 1.0, 7.0, k)
        _add_powder_specks(
            dwg,
            group,
            path,
            attrs,
            seed,
            canvas,
            count=_speck_count(18, length, canvas),
            spread=1.8 * scale * spread_gain,
            radius=0.45 * scale,
            opacity=_speck_opacity(0.20),
        )
    elif ins.weight == "chalk":
        for k, amount in enumerate((-3.0, 3.4)):
            layer_attrs = _copy_attrs(attrs)
            layer_attrs["stroke_width"] = 1.1 * scale
            layer_attrs["stroke_opacity"] = _layer_opacity(0.28)
            _emit_layer(amount, layer_attrs, 8.0, 11.0, k)
        _add_powder_specks(
            dwg,
            group,
            path,
            attrs,
            seed,
            canvas,
            count=_speck_count(34, length, canvas),
            spread=5.5 * scale * spread_gain,
            radius=0.9 * scale,
            opacity=_speck_opacity(0.26),
        )
    elif ins.weight == "brush_thin":
        for k, amount in enumerate((-1.4, 1.8)):
            layer_attrs = _copy_attrs(attrs)
            layer_attrs["stroke_width"] = (0.9 + k * 0.5) * scale
            layer_attrs["stroke_opacity"] = _layer_opacity(0.32)
            _emit_layer(amount, layer_attrs, 22.0, 9.0, k)
    elif ins.weight == "pen":
        # 割れた 2 本の穂先。帯の縁 (基準幅 2.0px の半分) のすぐ外を走る。
        for k, amount in enumerate((-1.40, 1.40)):
            layer_attrs = _copy_attrs(attrs)
            layer_attrs["stroke_width"] = (0.38 - k * 0.04) * scale
            layer_attrs["stroke_opacity"] = _layer_opacity(0.24 - k * 0.04)
            _emit_layer(amount, layer_attrs, 14.0 - k * 2.0, 3.0 + k, k)
    else:
        amounts = (-3.2, -1.4, 2.0, 3.6) if ins.weight == "crayon" else (-3.5, 2.8, 5.0)
        mark, gap = (6.0, 6.0) if ins.weight == "crayon" else (14.0, 9.0)
        for k, amount in enumerate(amounts):
            layer_attrs = _copy_attrs(attrs)
            layer_attrs["stroke_width"] = max(
                0.8 * scale,
                _stroke_width_px(ins.weight, canvas, ins.thinness)
                * (0.25 if ins.weight == "crayon" else 0.30),
            )
            layer_attrs["stroke_opacity"] = _layer_opacity(
                0.24 if ins.weight == "crayon" else 0.38
            )
            _emit_layer(amount, layer_attrs, mark, gap, k)
        if ins.weight == "crayon":
            _add_powder_specks(
                dwg,
                group,
                path,
                attrs,
                seed,
                canvas,
                count=_speck_count(26, length, canvas),
                spread=4.0 * scale * spread_gain,
                radius=0.75 * scale,
                opacity=_speck_opacity(0.18),
            )
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


def _arc_path_d(
    cx: float, cy: float, r: float, start_deg: float, end_deg: float
) -> str:
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

    large_arc, sweep = arc_svg_flags(start_deg, end_deg)

    return (
        f"M {fmt(x1)} {fmt(y1)} A {fmt(r)} {fmt(r)} 0 {large_arc} {sweep} {fmt(x2)} {fmt(y2)}"
    )


def _render_hand_stroke(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    start: tuple[float, float],
    end: tuple[float, float],
    attrs: dict,
    canvas: CanvasSize,
    render_seed: int | None,
    *,
    use_filters: bool,
    wild: bool = False,
):
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    base_width = _stroke_width_px(ins.weight, canvas, ins.thinness)
    grid_step = _grid_step_px(ins.weight, canvas)
    stroke = synthesize_stroke(
        start,
        end,
        base_width,
        ins.weight,
        _seed_for_instruction(ins, render_seed),
        samples=_stroke_sample_count(length, canvas),
        wild=wild,
        grid_step=grid_step,
    )
    group = dwg.g(
        class_=f"stroke-engine-v1 controls-{len(stroke.samples)} events-{stroke.event_count}"
    )
    color = attrs.get("stroke", "#111111")
    opacity = float(attrs.get("stroke_opacity", 1.0))
    _add_raster_bleed(dwg, group, stroke.samples, stroke.grid_step, color)
    outline = stroke.outline
    material_centerline = [(s.x, s.y) for s in stroke.samples]
    if _needs_path_variation(ins.variation):
        assert ins.variation is not None
        centerline = _line_with_variation(
            start,
            end,
            ins.variation,
            _seed_for_instruction(ins, render_seed),
            _amplitude_px(ins.variation, ins, canvas),
            canvas,
        )
        varied = synthesize_stroke(
            start,
            end,
            base_width,
            ins.weight,
            _seed_for_instruction(ins, render_seed),
            samples=len(centerline),
            wild=wild,
            grid_step=grid_step,
        )
        # The varied centerline gets its own outline, but the sheet already met
        # the tool: carry the breaks over so a wavering line is refused exactly
        # where a straight one would be.
        outline = outline_for_centerline(
            centerline, [sample.width for sample in varied.samples], varied.cuts
        )
        material_centerline = centerline
    path_attrs = {
        "d": polygon_path(outline),
        "fill": color,
        "fill_opacity": opacity,
        "stroke": "none",
    }
    if (
        use_filters
        and ins.weight in TEXTURE_FILTER_WEIGHTS
        and ins.weight != "drypoint"
    ):
        path_attrs["filter"] = f"url(#texture-{ins.weight})"
    group.add(dwg.path(**path_attrs))

    material = _material_line_group(
        dwg,
        ins,
        start,
        end,
        attrs,
        canvas,
        use_filters=False,
        include_base=False,
        render_seed=render_seed,
        centerline=material_centerline,
    )
    if material is not None:
        group.add(material)
    if ins.style != "solid":
        styled_attrs = _copy_attrs(attrs)
        styled_attrs["stroke_width"] = max(0.45 * _unit_scale(canvas), base_width * 0.42)
        styled_attrs.pop("filter", None)
        group.add(dwg.line(start=start, end=end, **styled_attrs))

    if ins.weight == "drypoint":
        dx, dy = end[0] - start[0], end[1] - start[1]
        norm = max(1e-6, math.hypot(dx, dy))
        nx, ny = -dy / norm, dx / norm
        offset = stroke.burr_side * base_width
        points = [
            (sample.x + nx * offset, sample.y + ny * offset)
            for sample in stroke.samples
        ]
        burr_attrs = {
            "points": points,
            "fill": "none",
            "stroke": color,
            "stroke_width": base_width * 1.25,
            "stroke_opacity": stroke.burr_opacity,
            "stroke_linecap": "round",
        }
        if use_filters:
            burr_attrs["filter"] = "url(#texture-drypoint)"
        group.add(dwg.polyline(**burr_attrs))
    return _apply_rotation(group, ins, canvas)


def _uses_hand_stroke(weight: str) -> bool:
    """手描きストローク合成の対象か。rotring (製図ペン) だけが幾何のまま。"""
    return weight != "rotring" and weight in GRAMMARS


def _body_attrs_for_contour_stroke(
    attrs: dict, ins: Instruction, *, region_fill: bool = True
) -> dict:
    """輪郭をストロークで描くとき、本体要素に残す属性。

    実線は輪郭を帯に置き換えるので stroke を落とす。破線・点線は線種そのものが
    記述なので、細めた幾何輪郭を残して線種を読ませる (line 側で style != solid
    のとき幾何線を重ねているのと対称)。

    `region_fill=False` のとき本体は塗りも持たない。内部は塗りストローク群が
    担うか (`filled=True`)、そもそも描かれない (`filled=False` / `surface` 指定)。
    """
    result = _copy_attrs(attrs)
    if not region_fill:
        result["fill"] = "none"
        result.pop("fill_opacity", None)
    if ins.style == "solid":
        result["stroke"] = "none"
        result.pop("stroke_width", None)
        result.pop("stroke_opacity", None)
        result.pop("stroke_dasharray", None)
        result.pop("stroke_linecap", None)
    else:
        result["stroke_width"] = float(result.get("stroke_width", 1.0)) * 0.42
    return result


FILL_SPACING_WIDTH_GAIN = 1.5
FILL_SPACING_UNIT_RATIO = 0.012
FILL_SPACING_JITTER = 0.24
FILL_MIN_SCANLINES = 3
FILL_MIN_STROKE_WIDTHS = 1.2

# --- render engine 22: the underlay, and the branch above it ----------------
# The one threshold. Which marks go on top of the underlay is decided by how
# much of the field one pass of scan lines would cover -- the stroke width over
# the scan pitch -- and by nothing else. Listing tool names here would cut the
# frozen corpus identically today and diverge the moment a description asks for
# a thin crayon, which is why `C-fill-circle-crayon-extra_fine` exists.
FILL_COVERAGE_BRANCH = 0.2
# What the scan branch packs to once it has an underlay under it (author, 2026-08-06).
FILL_COVERAGE_TARGET = 0.9
# The underlay's opacity as a ratio of the marks' own, never an absolute: a work
# whose description asked for a pale fill has to keep a pale underlay. At 0.50
# the field read as a separate, paler shape with darker strokes lying on it;
# the author asked for it to blend with the strokes instead ("the contrast is
# still open", 2026-08-07), so the field sits close under them and what the
# marks add is texture rather than a second tone.
FILL_UNDERLAY_OPACITY_RATIO = 0.75

# The three amplitudes that turn a raster into a hand. Each is a band the author
# set (DESIGN-01-FILL 7) and the tool picks its place in the band through
# `ToolGrammar.fill_hand`, so no description ever names them. `fill_hand` is 0
# for the machines, and all three collapse to nothing there.
#
# The angle band is read by BOTH branches. It was a 45-degree scatter on the
# texture branch for one round -- a rubbed tone laid in several directions --
# and the author took that back: "put the length and the direction back to
# engine 21, but give the direction a wobble of a few degrees" (2026-08-07).
# Engine 21's direction was one angle for the whole region, so what is left is
# this band, and the two branches now differ in where the marks are put, not in
# which way they run.
FILL_ANGLE_MIN_DEG = 2.2
FILL_ANGLE_SPAN_DEG = 1.6
FILL_PITCH_CV_MIN = 0.24
FILL_PITCH_CV_SPAN = 0.10
# How far each end of a scan stroke reaches past the contour, or falls short of
# it, **in multiples of the tool's own width**. The sign is drawn per end, so one
# stroke can overshoot at the landing and undershoot at the lift.
#
# It was a fraction of the stroke's LENGTH first, which is the wrong quantity:
# it made the error depend on how big the shape is rather than on what is
# drawing it, so the same pen missed by 17px in a large form and 2px in a small
# one. "How precisely can this tool stop where it means to" belongs to the tool,
# and the author asked for it to be proportional to the width rather than
# hard-coded (2026-08-07): a wide brush lands about its own width off, a fine
# pen a fraction of that. Halving what the length-based rule gave the widest
# tool lands at 1.5 widths, and the thin tools fall much further than half
# because their width is what shrank.
FILL_REACH_WIDTHS_MIN = 1.0
FILL_REACH_WIDTHS_SPAN = 0.5

# The texture branch. Below the threshold the tool is too thin for parallel
# lines to become a field -- at pencil width it would take eight times the lines
# -- and that is not how the tool is used: a pencil rubs a tone. The underlay
# already holds the field, so these marks only have to give it grain.
# A rubbed mark runs the width of the form, like a scan stroke does: "the same
# length as the non-texture branch" (author, 2026-08-07). It was six scan
# pitches first, then twelve; both read as a scatter of short dashes rather than
# as strokes laid across a shape. The length is now whatever the form gives --
# the mark is cut where the form ends and let past by the tool's own width --
# and only the COUNT is chosen, off the mean chord.
#
# 1.0 lays the same total stroke length one classic scan pass laid. It ran at
# half that for two rounds; the author asked to "double it" (2026-08-07) once
# the marks had gone back to running the width of the form, which is what puts
# it exactly on the classic pass.
FILL_TEXTURE_DENSITY = 1.0
# How much darker a mark is than the field it sits on. The marks are meant to
# rise out of the fill, not to be drawn on top of it: "bring the line and the
# background closer; only some of the strokes should read as standing out"
# (author, 2026-08-07, who put the number at 1.2-1.3 and then at 1.1). 1.0 would
# make the marks invisible.
FILL_TEXTURE_CONTRAST = 1.10
# Half-width of the per-mark draw around that contrast: a fill laid with a thin
# tool came out as one even tone, and "I want the mottling of a fill with the
# thin tools too" (author, 2026-08-07). The band is centred on the contrast, so
# the MEAN tone of the branch is exactly what it was and only its spread is new.
# The floor of the band is 1.0 -- a mark paler than the field it sits on still
# darkens it, because the two are composited, so pale marks buy no light
# patches. Light comes from the field being uneven under them, not from here.
FILL_TEXTURE_TONE_SPREAD = 0.10

# --- the reserve: withdrawn --------------------------------------------------
# There is no bare-ground mechanism here any more. "Would it be good to add bare
# ground showing through where the fill was left out?" (author, 2026-08-07)
# opened it, and two shapes were tried against the picture: an isotropic patch,
# rejected for lying across the run of the strokes ("it even looks like a tear
# in the paper"), and then a streak ALONG the strokes, rejected in its turn --
# "it does not look natural, so drawing the reserve as a shape is withdrawn"
# (author, 2026-08-07). The author's own third suggestion, drawing the reserve
# with the tool's own line, is closed by the same round's other note: "the line
# drawing of the reserve can not be made out by eye" -- one mark of bare ground
# is 1.5px at pencil and reads as nothing.
#
# What is left of the round is in `_field_tone_patches` below: the light in a
# fill now comes from the field being uneven, not from the field being absent.

# --- the field's own mottling -----------------------------------------------
# A flat field is what made a thin-tool fill read as one even tone, and varying
# the MARKS did not move it (run 859 round 6: the picture is the same at four
# times the spread). The tone has to be in the field, so the field is laid in
# layers: a lighter one over the whole form, and further ones carrying holes.
# Where a layer is missing the fill is paler, and everywhere else they composite
# to exactly the flat value the field had before -- so the change adds mottling
# without moving the tone the author already approved. Kept and extended:
# "this one is good, it gives variation, so adopt it" (author, 2026-08-07).
#
# The pale patches are HOLES in a layer rather than dark patches drawn on top.
# A patch drawn on top would put a second colour into the fill; a hole shows
# whatever is under the work, which is what a thinner load of ink does.
FILL_FIELD_TONE_DROP = 0.10
# Two independent sets of patches rather than one. One set gives every patch the
# same tone; two let the patches of one fall across the patches of the other, so
# the edges stop lining up and the fill has places that are paler still.
FILL_FIELD_TONE_LAYERS = 2
# "Can the outline be blurred, roughly?" (author, 2026-08-07). A patch was one
# hole with one edge, so its rim was a single step of the whole drop and read as
# a drawn contour. Each patch is now a nest of rings, each ring a hole in its own
# layer, so the rim comes down in as many steps as there are rings.
#
# NOT a filter. `use_filters` is display-only, so a blur built that way would
# take the mottling out of the `compat` and `editable` profiles altogether --
# the same reason the machine's raster halo is a real element (DESIGN-01-FILL
# 5-1). Three steps is what "roughly" buys: the ring count multiplies the number
# of paths, and past three the steps are finer than the drop they divide.
#
# The rings share one blob shape and differ only in their scale and in their
# per-vertex roughness, which is what stops an inner ring from crossing an outer
# one: the roughness is a FACTOR on the radius rather than a term added to it,
# so the ratio of two rings is bounded by the ratio of their scales. Roughening
# each ring separately is the "roughly" -- concentric copies of one outline
# would read as contour lines on a map.
FILL_FIELD_TONE_RINGS = 3
FILL_FIELD_TONE_RING_STEP = 0.22  # each ring this much smaller than the last
FILL_FIELD_TONE_COUNT_MIN = 3
FILL_FIELD_TONE_COUNT_SPAN = 3  # so 3, 4 or 5
FILL_FIELD_TONE_RADIUS_MIN = 0.18  # of the form's short side
FILL_FIELD_TONE_RADIUS_SPAN = 0.17
FILL_FIELD_TONE_INSET = 0.04  # kept this far inside the outline, same units
FILL_FIELD_TONE_WOBBLE = 0.24
FILL_FIELD_TONE_ROUGHNESS = 0.10
FILL_FIELD_TONE_SEGMENTS = 32
# The scan branch's own. It used to be 1/0.75 = 1.33 -- the marks at the ink's
# own density over a field at 0.75 of it -- which the author asked to bring down
# as well, naming brush_thick, the widest tool and so the highest contrast.
FILL_SCAN_CONTRAST = 1.15

# --- the machine's fill: a raster line, not a hatch -------------------------
# `computer` is the one periodic tool, and its fill is a scan line in the sense
# a screen means it. The author asked for the cathode-ray reading (2026-08-07):
# a dense core that bleeds at its edges, and a faint shadow visible between the
# lines. So the machine keeps the classic pitch -- packing it to coverage 0.9
# closes the gaps and the lines stop being readable as lines -- and each line is
# laid as a wide faint halo with a narrow core on top, which is a soft edge
# built out of real elements rather than a filter (filters are display-only, and
# this has to survive `compat` and `editable`).
#
# The line is drawn as a straight band rather than performed: the tool grammar's
# lateral drift bent it visibly along its run, and "keep it at a level that
# reads as straight" was the correction. The direction is free -- any angle, the
# seed's -- but one region gets one angle, which the scan layout already gives.
# The halo is a fixed STEP below the core, not a fraction of it: "keep the
# scan line's density within a swing of 0.1" (author, 2026-08-07). A ratio put
# the two 0.56 apart and the line read as a thin dark rule inside a pale band
# rather than as one line with a soft edge.
FILL_RASTER_HALO_WIDTHS = 2.6
FILL_RASTER_HALO_STEP = 0.10
FILL_RASTER_CORE_WIDTHS = 0.55


def _fill_scan_angle(seed: int) -> float:
    """塗りの走査角 (0〜π)。固定角だと作品内で揃って機械的に見える。"""
    return _hash01(0, seed, "fill-angle") * math.pi


def _fill_scan_spacing(ins: Instruction, canvas: CanvasSize) -> float:
    """走査線の間隔。完全被覆は狙わない (実際の塗りも紙目を残す)。"""
    return max(
        _stroke_width_px(ins.weight, canvas, ins.thinness) * FILL_SPACING_WIDTH_GAIN,
        canvas.unit * FILL_SPACING_UNIT_RATIO,
    )


def _fill_coverage(ins: Instruction, canvas: CanvasSize) -> float:
    """How much of the field one pass of scan lines covers: width over pitch.

    A ratio of two lengths, so it does not move with the canvas: the same
    instruction reaches the same branch on every aspect.
    """
    return _stroke_width_px(ins.weight, canvas, ins.thinness) / _fill_scan_spacing(
        ins, canvas
    )


def _fill_takes_scan_branch(ins: Instruction, canvas: CanvasSize) -> bool:
    """Scan lines at or above the coverage threshold, texture below it.

    A periodic tool keeps the scan branch whatever its coverage. Exact
    repetition is the computer's signature (DESIGN-01-FILL 5-4) and the texture
    branch has no regular placement to carry it, so sending the machine there
    would delete the very thing that has to survive this change. This reads the
    machine property the grammar already declares; it is not a list of tool
    names, and the coverage rule still decides every hand tool.
    """
    if GRAMMARS[ins.weight].periodic:
        return True
    return _fill_coverage(ins, canvas) >= FILL_COVERAGE_BRANCH


def _fill_hand(ins: Instruction) -> float:
    return GRAMMARS[ins.weight].fill_hand


def _fill_contrast(ins: Instruction) -> float:
    """The tool's own multiplier on whichever branch contrast applies."""
    return GRAMMARS[ins.weight].fill_contrast


def _fill_angle_amplitude(hand: float) -> float:
    """Half-width of the per-mark angle draw, in radians, from the tool's hand.

    Both branches read this one band. The constants state a standard deviation,
    which is what the contract measures, so the half-width of the uniform draw
    that produces it is sqrt(3) times as wide. A machine draws nothing: zero has
    to be exact, and `hand` is pinned at zero for the two machine grammars.
    """
    if not hand:
        return 0.0
    return math.radians(FILL_ANGLE_MIN_DEG + FILL_ANGLE_SPAN_DEG * hand) * math.sqrt(3.0)


def _fill_is_scannable(
    ins: Instruction,
    contour: list[tuple[float, float]],
    canvas: CanvasSize,
    render_seed: int | None,
) -> bool:
    """Is the shape big enough to be filled at all, or is it one touch?

    Measured at the classic pitch, not at the one the scan branch now packs to.
    "Too small to be scanned" is a property of the shape and the tool that was
    settled in engine 16; re-deciding it against a denser pitch would quietly
    turn dabs back into fills and move cases this change was not aimed at.
    """
    seed = _seed_for_instruction(ins, render_seed)
    segments = _scanline_segments(
        contour, _fill_scan_angle(seed), _fill_scan_spacing(ins, canvas), seed
    )
    return len({index for index, _, _ in segments}) >= FILL_MIN_SCANLINES


def _polygon_area(contour: list[tuple[float, float]]) -> float:
    total = 0.0
    for index in range(len(contour)):
        ax, ay = contour[index]
        bx, by = contour[(index + 1) % len(contour)]
        total += ax * by - bx * ay
    return abs(total) / 2.0


def _field_tone_patches(
    contour: list[tuple[float, float]], seed: int, short_side: float
) -> tuple[tuple[tuple[tuple[float, float], ...], ...], ...]:
    """The paler places in the field, one layer per (set, ring).

    Isotropic on purpose: this is how much ink the ground took where the tool
    passed, which belongs to the sheet and has no direction of its own.

    A patch is a NEST of rings, not one outline, so that its rim comes down in
    steps instead of in one. Ring `r` of every patch in set `s` goes into the
    layer at `s * FILL_FIELD_TONE_RINGS + r`, and a patch is kept only if all of
    its rings survive the clamp -- half a nest is the single step this replaced.
    That is what lets a caller walk a patch through its rings by index.
    """
    if len(contour) < 3 or short_side <= 0:
        return ()
    cx = sum(point[0] for point in contour) / len(contour)
    cy = sum(point[1] for point in contour) / len(contour)
    inset = short_side * FILL_FIELD_TONE_INSET
    layers: list[list[tuple[tuple[float, float], ...]]] = []
    for layer in range(FILL_FIELD_TONE_LAYERS):
        count = FILL_FIELD_TONE_COUNT_MIN + int(
            _hash01(layer, seed, "fill-field-tone-count") * FILL_FIELD_TONE_COUNT_SPAN
        )
        rings: list[list[tuple[tuple[float, float], ...]]] = [
            [] for _ in range(FILL_FIELD_TONE_RINGS)
        ]
        for step in range(count):
            index = layer * 64 + step
            bearing = _hash01(index, seed, "fill-field-tone-angle") * 2 * math.pi
            radius = short_side * (
                FILL_FIELD_TONE_RADIUS_MIN
                + FILL_FIELD_TONE_RADIUS_SPAN
                * _hash01(index, seed, "fill-field-tone-radius")
            )
            spans = [
                span for span in _line_spans(
                    contour, (cx, cy), (math.cos(bearing), math.sin(bearing))
                )
                if span[0] <= 0.0 <= span[1]
            ]
            if not spans:
                continue
            place = spans[0][1] * _hash01(index, seed, "fill-field-tone-place") * 0.6
            centre = (cx + math.cos(bearing) * place, cy + math.sin(bearing) * place)
            nest = []
            for ring in range(FILL_FIELD_TONE_RINGS):
                blob = _wobbly_blob(
                    centre[0],
                    centre[1],
                    radius * (1.0 - FILL_FIELD_TONE_RING_STEP * ring),
                    seed,
                    index,
                    ring=ring,
                )
                clamped = _clamp_inside(blob, centre, contour, inset)
                if clamped is None:
                    break
                nest.append(clamped)
            if len(nest) < FILL_FIELD_TONE_RINGS:
                continue
            for ring, outline in enumerate(nest):
                rings[ring].append(outline)
        layers.extend(ring for ring in rings if ring)
    return tuple(tuple(layer) for layer in layers)


def _field_tones(
    ins: Instruction,
    contour: list[tuple[float, float]],
    canvas: CanvasSize,
    render_seed: int | None,
):
    """The pale patches of one texture-branch fill, in the picture's own units."""
    xs = [point[0] for point in contour]
    ys = [point[1] for point in contour]
    short_side = min(max(xs) - min(xs), max(ys) - min(ys))
    return _field_tone_patches(
        contour, _seed_for_instruction(ins, render_seed), short_side
    )


def _wobbly_blob(
    cx: float, cy: float, radius: float, seed: int, index: int, *, ring: int = 0
) -> tuple[tuple[float, float], ...]:
    """A disc pulled out of round by two low harmonics and roughened per vertex.

    The harmonics are the patch's own shape and do not depend on `ring`, so the
    rings of one patch are the same blob at different sizes. The roughness does
    depend on it, and it MULTIPLIES the radius rather than adding to it: that
    bounds one ring against the next by the ratio of their scales alone, so a
    rough inner ring can not cross out through a pinched outer one.
    """
    amp2 = FILL_FIELD_TONE_WOBBLE * (_hash01(index, seed, "fill-blob-h2") - 0.5) * 2
    amp3 = FILL_FIELD_TONE_WOBBLE * (_hash01(index, seed, "fill-blob-h3") - 0.5) * 2
    phase2 = _hash01(index, seed, "fill-blob-p2") * 2 * math.pi
    phase3 = _hash01(index, seed, "fill-blob-p3") * 2 * math.pi
    points = []
    for step in range(FILL_FIELD_TONE_SEGMENTS):
        theta = step * 2 * math.pi / FILL_FIELD_TONE_SEGMENTS
        rough = (
            _hash01(
                (index * FILL_FIELD_TONE_SEGMENTS + step) * FILL_FIELD_TONE_RINGS + ring,
                seed,
                "fill-blob-edge",
            )
            - 0.5
        ) * 2
        r = (
            radius
            * (
                1.0
                + amp2 * math.sin(2 * theta + phase2)
                + amp3 * math.sin(3 * theta + phase3)
            )
            * (1.0 + FILL_FIELD_TONE_ROUGHNESS * rough)
        )
        points.append((cx + math.cos(theta) * r, cy + math.sin(theta) * r))
    return tuple(points)


def _clamp_inside(
    points: tuple[tuple[float, float], ...],
    centre: tuple[float, float],
    contour: list[tuple[float, float]],
    inset: float,
) -> tuple[tuple[float, float], ...] | None:
    """Pull every vertex back inside the contour, along its own ray from `centre`.

    A hole that crosses the outline is not a hole: even-odd counts one crossing
    out there and paints the region OUTSIDE the form. Clamping per vertex keeps
    the patch's own shape wherever it already fitted.
    """
    out: list[tuple[float, float]] = []
    for x, y in points:
        dx, dy = x - centre[0], y - centre[1]
        distance = math.hypot(dx, dy)
        if distance <= 1e-9:
            return None
        ux, uy = dx / distance, dy / distance
        spans = [
            span for span in _line_spans(contour, centre, (ux, uy))
            if span[0] <= 0.0 <= span[1]
        ]
        if not spans:
            return None
        limit = spans[0][1] - inset
        if limit <= 0:
            return None
        scale = min(1.0, limit / distance)
        out.append((centre[0] + ux * distance * scale, centre[1] + uy * distance * scale))
    return tuple(out)


def _fill_underlay(dwg: svgwrite.Drawing, ins: Instruction, contour, attrs, tones=()):
    """The field itself, laid as a real element under whatever marks go on top.

    Both branches get one. It is what lets the marks leave the contour: before
    engine 22 the stroke WAS the fill, so a stroke that crossed the outline
    spilled paint outside the shape and every scan line had to be cut at the
    intersection. That cut is the third regularity the eye reads as a raster
    (DESIGN-01-FILL 3.2). With the boundary held here, the marks are free.

    Not a filter. `use_filters` is display-only, so an underlay built out of a
    filter would make the fill VANISH in the `compat` and `editable` profiles
    (DESIGN-01-FILL 5-1).

    `tones` are the paler places, laid as holes in the layers stacked over a
    darker base rather than as pale patches painted on top -- paint on top would
    put a second colour into the fill, while a hole shows what is under the
    work. Where every layer is present they composite to exactly the flat
    opacity the field used to have, so the mottling does not move the tone the
    author approved; where some are missing the field is paler by that many
    steps, and the rings of one patch are what turn its rim into several.
    """
    opacity = float(attrs.get("fill_opacity", attrs.get("stroke_opacity", 1.0)))
    field = opacity * FILL_UNDERLAY_OPACITY_RATIO
    color = attrs.get("stroke", "#111111")
    if not tones:
        return dwg.polygon(
            points=list(contour),
            class_="fill-underlay-v1",
            fill=color,
            fill_opacity=field,
            stroke="none",
        )
    base = field * (1.0 - FILL_FIELD_TONE_DROP)
    group = dwg.g(class_="fill-field-v2")
    group.add(
        dwg.path(
            d=polygon_path(tuple(contour)),
            class_="fill-underlay-v1 field-base",
            fill=color,
            fill_opacity=base,
            fill_rule="evenodd",
            stroke="none",
        )
    )
    if tones:
        # Solved so that the base under all the layers equals the flat field
        # exactly: (1 - base)(1 - each)^n = 1 - field.
        rest = (1.0 - field) / (1.0 - base) if base < 1.0 else 1.0
        each = 1.0 - rest ** (1.0 / len(tones))
        for patches in tones:
            group.add(
                dwg.path(
                    d=" ".join(
                        [
                            polygon_path(tuple(contour)),
                            *[polygon_path(patch) for patch in patches],
                        ]
                    ),
                    class_=f"fill-underlay-v1 tones-{len(patches)}",
                    fill=color,
                    fill_opacity=each,
                    fill_rule="evenodd",
                    stroke="none",
                )
            )
    return group


def _fill_stroke_seed(seed: int, index: int) -> int:
    """筆ごとの seed。輪郭帯と共有すると同じ energy 波形が内部にも出る。"""
    digest = hashlib.sha256(f"{seed}:fill-stroke:{index}".encode("utf-8")).digest()
    return struct.unpack("<Q", digest[:8])[0]


def _scanline_segments(
    contour: list[tuple[float, float]],
    angle: float,
    spacing: float,
    seed: int,
    jitter: float = FILL_SPACING_JITTER,
) -> list[tuple[int, tuple[float, float], tuple[float, float]]]:
    """走査線と閉輪郭の交点を対で取り、輪郭内部の区間を返す。

    交点で切るので clipPath が要らず、凹形 (cloudform) も交点対のまま扱える。
    辺の判定を半開区間にしてあるので、頂点をかすめる走査線を二重に数えない。

    `jitter` is the full width of the uniform pitch multiplier, so the
    coefficient of variation of the gaps is `jitter / sqrt(12)`. The default is
    the engine-21 value; the fill branch passes its own, drawn from the tool.
    """
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
    """Where an infinite line through `point` runs inside the closed contour.

    Returned as entry/exit parameters along `direction`, in pairs, so a concave
    form gives several spans and none of them crosses the void. Same half-open
    edge test as `_scanline_segments`, so a line grazing a vertex is not
    counted twice.

    `_scanline_segments` cuts every row at one shared angle; this cuts one row
    at its own. The fill needs both: the rows are laid out parallel so the
    pitch means something, then each row is turned and re-cut so that "how far
    past the contour" is measured against the line the stroke actually travels.
    """
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
        # point + t*u = A + s*e, crossed with u: s = (d x u) / (u x e).
        t_edge = (dx * uy - dy * ux) / denom
        if not (0.0 <= t_edge < 1.0):
            continue
        hits.append((dx + ex * t_edge) * ux + (dy + ey * t_edge) * uy)
    hits.sort()
    return [(hits[i], hits[i + 1]) for i in range(0, len(hits) - 1, 2)]


def _raster_band(
    start: tuple[float, float],
    end: tuple[float, float],
    width: float,
) -> str:
    """One straight scan line of the machine's raster, as a band.

    Four corners and nothing else. The tool grammar is deliberately not on this
    path: a performed line wanders by a third of its width, which over a run
    this long stops reading as a straight line, and straightness is what the
    machine's fill is.

    Not quantised. Rounding the four corners onto the 18px lattice moved each of
    them by up to 9px independently, which made the band's WIDTH vary from line
    to line and left the ends stepped against the outline -- "keep the scan
    line's width constant, and leave the start and the end unprocessed"
    (author, 2026-08-07). The computer's lattice signature stays on its contour,
    where the material layer can still give the residual back; a raster line
    does not have one to give.
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 0:
        return ""
    nx, ny = -dy / length * width / 2, dx / length * width / 2
    corners = [
        (start[0] + nx, start[1] + ny),
        (end[0] + nx, end[1] + ny),
        (end[0] - nx, end[1] - ny),
        (start[0] - nx, start[1] - ny),
    ]
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in corners) + " Z"


def _render_fill_strokes(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    contour: list[tuple[float, float]],
    attrs: dict,
    canvas: CanvasSize,
    render_seed: int | None,
    *,
    use_filters: bool,
    wild: bool = False,
):
    """閉図形の内部を素材の筆致で埋める。1 パス = 1 筆。

    塗りは領域 fill ではなく、細かいストロークで内側を埋めること。走査線が
    `FILL_MIN_SCANLINES` 本に満たない微小図形では None を返し、呼び出し側が
    `_render_fill_dab` へ回す (engine 16 まではここで領域 fill へ縮退していた)。

    Engine 22 took the three regularities the eye reads as a raster out of this
    function. The scan angle now moves per stroke, the pitch is drawn far wider,
    and the ends leave the contour instead of being cut at the intersection --
    which they can only do because `_fill_underlay` is holding the boundary
    underneath. All three amplitudes come from the tool (`fill_hand`) and are
    zero for a machine, so `computer` still lays the same exact raster it did.
    """
    if len(contour) < 3:
        return None
    base_width = _stroke_width_px(ins.weight, canvas, ins.thinness)
    grid_step = _grid_step_px(ins.weight, canvas)
    seed = _seed_for_instruction(ins, render_seed)
    hand = _fill_hand(ins)
    raster = GRAMMARS[ins.weight].periodic
    if raster:
        # A screen's raster: the lines keep their pitch so the gaps between them
        # stay readable, and the faint shadow the author asked to see between
        # them is the underlay showing through. The angle is the work's own --
        # a raster does not have to be horizontal, it has to be ONE direction
        # across the region, which the scan layout already guarantees.
        spacing = _fill_scan_spacing(ins, canvas)
        angle = _fill_scan_angle(seed)
    else:
        # The underlay carries the field, so the scan lines are free to pack to
        # the coverage the author chose instead of to whatever the pitch gave.
        spacing = base_width / FILL_COVERAGE_TARGET
        angle = _fill_scan_angle(seed)
    pitch_cv = (FILL_PITCH_CV_MIN + FILL_PITCH_CV_SPAN * hand) if hand else 0.0
    segments = _scanline_segments(
        contour,
        angle,
        spacing,
        seed,
        jitter=pitch_cv * math.sqrt(12.0),
    )
    if len({index for index, _, _ in segments}) < FILL_MIN_SCANLINES:
        return None

    color = attrs.get("stroke", "#111111")
    # 塗りストロークは輪郭ではなく塗りなので、濃度は fill 側の指定に従う。
    opacity = float(attrs.get("fill_opacity", attrs.get("stroke_opacity", 1.0)))
    # The marks sit close over the field, on this branch as on the texture one:
    # the difference between the two is what the fill reads as, and the author
    # closed it here too (2026-08-07). A ratio of the underlay's, never an
    # absolute, so a description asking for a pale fill keeps the relation.
    mark_opacity = min(
        opacity,
        opacity
        * FILL_UNDERLAY_OPACITY_RATIO
        * FILL_SCAN_CONTRAST
        * _fill_contrast(ins),
    )
    minimum = base_width * FILL_MIN_STROKE_WIDTHS
    angle_amp = _fill_angle_amplitude(hand)
    reach = (
        base_width * (FILL_REACH_WIDTHS_MIN + FILL_REACH_WIDTHS_SPAN * hand)
        if hand
        else 0.0
    )
    paths: list[dict] = []
    for order, (index, start, end) in enumerate(segments):
        chord = math.hypot(end[0] - start[0], end[1] - start[1])
        if chord <= minimum:
            continue
        ux = (end[0] - start[0]) / chord
        uy = (end[1] - start[1]) / chord
        mx = (start[0] + end[0]) / 2
        my = (start[1] + end[1]) / 2
        # Turn this row on its own midpoint, then cut it against the contour
        # again. Rotating the chord and keeping its old length would make the
        # reach below a fraction of a line the stroke no longer travels: near
        # the edge of a round form a few degrees change the span several-fold.
        if angle_amp:
            delta = (_hash01(order, seed, "fill-angle-stroke") - 0.5) * 2 * angle_amp
            cos_d, sin_d = math.cos(delta), math.sin(delta)
            ux, uy = ux * cos_d - uy * sin_d, ux * sin_d + uy * cos_d
            spans = [
                span for span in _line_spans(contour, (mx, my), (ux, uy))
                if span[0] <= 0.0 <= span[1]
            ]
            if not spans:
                continue
            t0, t1 = spans[0]
        else:
            t0, t1 = -chord / 2, chord / 2
        length = t1 - t0
        if length <= minimum:
            continue
        # One end overshoots the contour, the other may fall short of it. The
        # sign is drawn per end: an implementation that only insets would leave
        # the edge as tidy as the cut it replaced.
        r0 = reach
        r1 = reach
        if _hash01(order, seed, "fill-reach-start") < 0.5:
            r0 = -r0
        if _hash01(order, seed, "fill-reach-end") < 0.5:
            r1 = -r1
        p0 = (mx + ux * (t0 - r0), my + uy * (t0 - r0))
        p1 = (mx + ux * (t1 + r1), my + uy * (t1 + r1))
        if index % 2:
            # 走査線ごとに往復させる。終端の向きが交互になり手の運びとして読める。
            p0, p1 = p1, p0
        span = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        count = max(2, _stroke_sample_count(span, canvas))
        centerline = [
            (
                p0[0] + (p1[0] - p0[0]) * i / (count - 1),
                p0[1] + (p1[1] - p0[1]) * i / (count - 1),
            )
            for i in range(count)
        ]
        # A raster line is one line with a soft edge, so it is laid twice: a
        # wide faint halo and a narrow dense core on the same centreline. Two
        # real elements rather than a blur, because `use_filters` is
        # display-only and the machine has to look the same in every profile.
        layers = (
            (
                (base_width * FILL_RASTER_HALO_WIDTHS, mark_opacity - FILL_RASTER_HALO_STEP),
                (base_width * FILL_RASTER_CORE_WIDTHS, mark_opacity),
            )
            if raster
            else ((base_width, mark_opacity),)
        )
        for width, layer_opacity in layers:
            if raster:
                # Straight, because a raster line is straight. Performing it
                # through the tool grammar bent it along its run: the machine's
                # lateral drift is 0.34 of the width and reads as a wobble at
                # this length. The lattice is still met -- the endpoints are
                # rounded onto it -- so engine 18's signature survives.
                path_d = _raster_band(p0, p1, width)
            else:
                path_d = contour_stroke_path(
                    synthesize_along(
                        centerline,
                        width,
                        ins.weight,
                        _fill_stroke_seed(seed, order),
                        closed=False,
                        grid_step=grid_step,
                        wild=wild,
                        terminal="loaded",
                    )
                )
            path_attrs = {
                "d": path_d,
                "fill": color,
                "fill_opacity": layer_opacity,
                "stroke": "none",
            }
            if (
                use_filters
                and ins.weight in TEXTURE_FILTER_WEIGHTS
                and ins.weight != "drypoint"
            ):
                path_attrs["filter"] = f"url(#texture-{ins.weight})"
            paths.append(path_attrs)

    if not paths:
        return None
    group = dwg.g(class_=f"fill-stroke-v1 strokes-{len(paths)}")
    for path_attrs in paths:
        group.add(dwg.path(**path_attrs))
    return group


def _render_fill_texture(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    contour: list[tuple[float, float]],
    attrs: dict,
    canvas: CanvasSize,
    render_seed: int | None,
    *,
    use_filters: bool,
    wild: bool = False,
):
    """塗りの上層を、走査線ではなく撒かれた痕で作る (engine 22 段 2)。

    Below the coverage threshold a pass of parallel lines does not become a
    field. Closing the gaps would take eight times the lines at pencil width and
    twenty-four at silverpoint (DESIGN-01-FILL 3.3), and that is not how the
    tool is used: a pencil rubs a tone rather than ruling it. The underlay
    already holds the field, so these marks only have to give it grain.

    Positions come from `_surface_scatter`, the same scatter the surface layer
    uses, so a concave shape stays inside its own outline and nothing lands in
    the bounding box but outside the form. The marks are the tool's own width --
    not the grain-sized dabs the surface layer draws -- because what is being
    rubbed here is the tool itself.

    The scatter is the whole of the difference from the scan branch. Length,
    direction and end treatment are the scan branch's own (author, 2026-08-07,
    taking back the 45-degree spread of the round before): what separates a
    rubbed tone from a ruled one is that the marks are not on rows.

    One thing varies that did not: each mark takes its own tone from a band
    round the branch contrast. A mark runs from one side of the form to the
    other and is cut by nothing but the contour -- the reserve that used to
    break it into pieces was withdrawn (author, 2026-08-07).
    """
    if len(contour) < 3:
        return None
    seed = _seed_for_instruction(ins, render_seed)
    pitch = _fill_scan_spacing(ins, canvas)
    width = _stroke_width_px(ins.weight, canvas, ins.thinness)
    xs = [point[0] for point in contour]
    ys = [point[1] for point in contour]
    short_side = min(max(xs) - min(xs), max(ys) - min(ys))
    span_limit = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    area = _polygon_area(contour)
    # The mean chord of the form, which is what a full-length mark will be. For
    # a circle `area / short_side` is exactly it, and for anything else it is
    # the right order. Only the COUNT is decided here; the LENGTH is the form's.
    mean_chord = max(pitch, area / short_side) if short_side > 0 else pitch
    # One classic scan pass lays about `area / pitch` of stroke length. Sizing
    # the count off that keeps the branch anchored to the ink the fill used to
    # carry, rather than to a number chosen to look right on one shape. The
    # floor is the scan-line minimum: a shape big enough to have been scanned
    # has to come out of this branch with marks on it, or the boundary between
    # "filled" and "one dab" would quietly move off the value engine 16 measured.
    count = max(
        FILL_MIN_SCANLINES,
        int(area / (pitch * mean_chord) * FILL_TEXTURE_DENSITY),
    )
    points = _surface_scatter(contour, count, seed)
    if not points:
        return None

    color = attrs.get("stroke", "#111111")
    opacity = float(attrs.get("fill_opacity", attrs.get("stroke_opacity", 1.0)))
    # The marks rise out of the field; they are not drawn on top of it. Tying
    # their opacity to the underlay's keeps the contrast where the author put it
    # ("only some of the strokes should read as standing out", 2026-08-07) at
    # every density a description can ask for, and never darker than the ink the
    # description actually specified.
    mark_opacity = min(
        opacity,
        opacity
        * FILL_UNDERLAY_OPACITY_RATIO
        * FILL_TEXTURE_CONTRAST
        * _fill_contrast(ins),
    )
    grid_step = _grid_step_px(ins.weight, canvas)
    hand = _fill_hand(ins)
    base_angle = _fill_scan_angle(seed)
    spread = _fill_angle_amplitude(hand)
    reach = width * (FILL_REACH_WIDTHS_MIN + FILL_REACH_WIDTHS_SPAN * hand)
    group = dwg.g(class_=f"fill-texture-v1 marks-{len(points)}")
    for index, (px, py) in enumerate(points):
        # The marks run the region's one direction, wobbling by the few degrees
        # the hand gives -- the same band the scan branch draws from. What makes
        # this branch a rubbed tone rather than a ruled one is where the marks
        # are put, which is a scatter, not which way they run.
        angle = base_angle + (_hash01(index, seed, "fill-texture-angle") - 0.5) * 2 * spread
        half = span_limit
        dx, dy = math.cos(angle), math.sin(angle)
        # A mark is cut where the form ends, and then let past it -- or stopped
        # short of it -- by the same tool-width reach the scan branch uses, with
        # the sign drawn per end. An implementation that only overshoots leaves
        # one edge as tidy as the cut it replaced, and one that overshoots at
        # both ends is the spill that was already rejected once (F-1).
        spans = [
            span for span in _line_spans(contour, (px, py), (dx, dy))
            if span[0] <= 0.0 <= span[1]
        ]
        if not spans:
            continue
        inside_start, inside_end = spans[0]
        r0 = reach if _hash01(index, seed, "fill-texture-reach-start") >= 0.5 else -reach
        r1 = reach if _hash01(index, seed, "fill-texture-reach-end") >= 0.5 else -reach
        start = max(-half, inside_start - r0)
        end = min(half, inside_end + r1)
        if end - start <= width:
            continue
        # One tone per mark, drawn from a band centred on the branch contrast.
        # The mean is unchanged; what is new is that two neighbouring marks are
        # no longer the same grey, which is the whole of the mottling.
        tone = mark_opacity * (
            1.0
            + (_hash01(index, seed, "fill-texture-tone") - 0.5)
            * 2
            * FILL_TEXTURE_TONE_SPREAD
        )
        tone = min(opacity, tone)
        length = end - start
        count_samples = max(2, _stroke_sample_count(length, canvas))
        centerline = [
            (
                px + dx * (start + length * i / (count_samples - 1)),
                py + dy * (start + length * i / (count_samples - 1)),
            )
            for i in range(count_samples)
        ]
        stroke = synthesize_along(
            centerline,
            width,
            ins.weight,
            _fill_stroke_seed(seed, index),
            closed=False,
            grid_step=grid_step,
            wild=wild,
            terminal="loaded",
        )
        path_attrs = {
            "d": contour_stroke_path(stroke),
            "fill": color,
            "fill_opacity": tone,
            "stroke": "none",
        }
        if (
            use_filters
            and ins.weight in TEXTURE_FILTER_WEIGHTS
            and ins.weight != "drypoint"
        ):
            path_attrs["filter"] = f"url(#texture-{ins.weight})"
        group.add(dwg.path(**path_attrs))
    return group


FILL_DAB_SAMPLES = 5
# 円のように長短の軸が等しい図形での運びの下限 (長い方の軸に対する比)。
# 端の taper (`_edge_window`) が両端の 16% ずつを削るので、運びが短すぎると全幅の
# 平坦部が残らず、図形の内側が空いて輪郭だけの絵になる — 縮退が防いでいた当の失敗
# である。0.30 では engine 15 の領域 fill の 56〜92% の墨しか置かなかった。
# 0.90 で 85〜105%、1.10 では 115% まで行き過ぎる (実測は結果レポート §段2)。
FILL_DAB_MIN_TRAVEL = 0.90


def _render_fill_dab(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    contour: list[tuple[float, float]],
    attrs: dict,
    canvas: CanvasSize,
    render_seed: int | None,
    *,
    use_filters: bool,
    wild: bool = False,
):
    """微小な塗りを「塗る」のでなく「置く」。1 筆の打点として描く。

    走査線が `FILL_MIN_SCANLINES` 本に届かない図形は、内部を走査して埋める対象では
    なく、物としては筆を一度置いた跡である。engine 15 まではここで領域 fill へ
    縮退しており、内部を持つ本番 instruction の 78% が平坦な塗りになっていた
    (その 99.3% が短辺 2% 未満の粒である)。

    筆は図形の長い方の軸に沿って運び、幅は短い方の軸が決める。円のように両軸が
    等しい図形では運びが短くなり、細長い図形では一本の長い筆になる。新しい機構は
    要らない — engine 12 以降の筆致文法が「一筆の始まりと終わり」を既に持っている。
    """
    if len(contour) < 3:
        return None
    xs = [point[0] for point in contour]
    ys = [point[1] for point in contour]
    width_px = max(xs) - min(xs)
    height_px = max(ys) - min(ys)
    if width_px <= 0.0 and height_px <= 0.0:
        return None
    cx = (max(xs) + min(xs)) / 2
    cy = (max(ys) + min(ys)) / 2
    along_x = width_px >= height_px
    long_axis = width_px if along_x else height_px
    short_axis = height_px if along_x else width_px
    # 運びは「長い方 − 短い方」。円では 0 になるので下限を置き、点にならないようにする。
    travel = max(long_axis - short_axis, long_axis * FILL_DAB_MIN_TRAVEL)
    half = travel / 2
    start = (cx - half, cy) if along_x else (cx, cy - half)
    end = (cx + half, cy) if along_x else (cx, cy + half)
    centerline = [
        (
            start[0] + (end[0] - start[0]) * i / (FILL_DAB_SAMPLES - 1),
            start[1] + (end[1] - start[1]) * i / (FILL_DAB_SAMPLES - 1),
        )
        for i in range(FILL_DAB_SAMPLES)
    ]
    seed = _seed_for_instruction(ins, render_seed)
    stroke = synthesize_along(
        centerline,
        max(_stroke_width_px(ins.weight, canvas, ins.thinness), short_axis),
        ins.weight,
        _fill_stroke_seed(seed, 0),
        closed=False,
        grid_step=_grid_step_px(ins.weight, canvas),
        wild=wild,
    )
    path_attrs = {
        "d": contour_stroke_path(stroke),
        "fill": attrs.get("stroke", "#111111"),
        "fill_opacity": float(
            attrs.get("fill_opacity", attrs.get("stroke_opacity", 1.0))
        ),
        "stroke": "none",
    }
    if use_filters and ins.weight in TEXTURE_FILTER_WEIGHTS and ins.weight != "drypoint":
        path_attrs["filter"] = f"url(#texture-{ins.weight})"
    group = dwg.g(class_="fill-dab-v1")
    group.add(dwg.path(**path_attrs))
    return group


def _interior_fill(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    contour: list[tuple[float, float]],
    attrs: dict,
    canvas: CanvasSize,
    render_seed: int | None,
    *,
    use_filters: bool,
    wild: bool = False,
) -> tuple[object | None, bool]:
    """内部表現を返す。戻り値は (内部の描画, 領域 fill に縮退したか)。

    rotring (製図ペン) は engine 8 で輪郭を筆致から外してあるのと同じ理由で、
    塗りも機械の塗り = 領域 fill のままにする。手の道具では、走査線に届かない
    微小な図形も領域 fill にはせず、1 筆の打点として置く (engine 16 段 2)。

    Engine 22 puts an underlay under the marks and splits what goes on top:
    scan lines where the tool is wide enough for them to become a field,
    scattered marks where it is not. The underlay is common to both branches --
    the threshold decides only what sits on it -- because the three works the
    author named as striped were drawn with pen, crayon and pencil, and a design
    that gave the underlay to the wide branch alone would reach none of them
    (run 857 §1).

    A dab is not a filled area, so it gets no underlay. It is one touch of the
    tool, it has no scan strokes to let off the contour, and an underlay would
    put back exactly the flat region fill engine 16 took out of tiny shapes.
    """
    if not _fills_interior(ins):
        return None, False
    if not _uses_hand_stroke(ins.weight):
        return None, True
    if len(contour) < 3:
        return None, True

    if not _fill_is_scannable(ins, contour, canvas, render_seed):
        group = _render_fill_dab(
            dwg, ins, contour, attrs, canvas, render_seed,
            use_filters=use_filters, wild=wild,
        )
        return (None, True) if group is None else (group, False)

    scan_branch = _fill_takes_scan_branch(ins, canvas)
    render_marks = _render_fill_strokes if scan_branch else _render_fill_texture
    marks = render_marks(
        dwg, ins, contour, attrs, canvas, render_seed, use_filters=use_filters, wild=wild
    )
    if marks is None:
        # Nothing survived the minimum-length filter. Fall through to the dab
        # rather than leaving a bare underlay: an area with no mark on it is the
        # flat fill this engine has been taking apart since 9.
        group = _render_fill_dab(
            dwg, ins, contour, attrs, canvas, render_seed,
            use_filters=use_filters, wild=wild,
        )
        return (None, True) if group is None else (group, False)

    # The field's mottling is the texture branch's, and only its. The scan
    # branch packs to the coverage the author set and its own strokes already
    # leave the field uneven -- "I want the mottling of a fill with the THIN
    # tools too" (author, 2026-08-07) -- so a second mechanism here would be
    # doing what that one already does.
    tones = () if scan_branch else _field_tones(ins, contour, canvas, render_seed)
    group = dwg.g(class_="fill-v2")
    group.add(_fill_underlay(dwg, ins, contour, attrs, tones))
    group.add(marks)
    return group, False


def _render_contour_hand_stroke(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    contour: list[tuple[float, float]],
    attrs: dict,
    canvas: CanvasSize,
    render_seed: int | None,
    *,
    use_filters: bool,
    closed: bool = True,
    anchors: frozenset[int] = frozenset(),
    wild: bool = False,
) -> tuple[object, list[tuple[float, float]]]:
    """閉輪郭を一筆のストロークとして合成し、帯 (ring) として描く。

    戻り値の 2 つめは演奏後の中心線。材質層がこれに追随できるように返す
    (幾何から引くと墨だけが動いて材質が取り残される)。
    """
    base_width = _stroke_width_px(ins.weight, canvas, ins.thinness)
    stroke = synthesize_along(
        contour,
        base_width,
        ins.weight,
        _seed_for_instruction(ins, render_seed),
        closed=closed,
        anchors=anchors,
        grid_step=_grid_step_px(ins.weight, canvas),
        wild=wild,
    )
    group = dwg.g(
        class_=(
            f"contour-stroke-v1 controls-{len(stroke.samples)} "
            f"events-{stroke.event_count}"
        )
    )
    color = attrs.get("stroke", "#111111")
    opacity = float(attrs.get("stroke_opacity", 1.0))
    _add_raster_bleed(dwg, group, stroke.samples, stroke.grid_step, color)
    path_attrs = {
        "d": contour_stroke_path(stroke),
        "fill": color,
        "fill_opacity": opacity,
        "fill_rule": "evenodd",
        "stroke": "none",
    }
    if use_filters and ins.weight in TEXTURE_FILTER_WEIGHTS and ins.weight != "drypoint":
        path_attrs["filter"] = f"url(#texture-{ins.weight})"
    group.add(dwg.path(**path_attrs))

    if ins.weight == "drypoint":
        offset = stroke.burr_side * base_width
        normals = centerline_normals(
            [(sample.x, sample.y) for sample in stroke.samples], closed
        )
        burr_attrs = {
            "points": [
                (sample.x + nx * offset, sample.y + ny * offset)
                for sample, (nx, ny) in zip(stroke.samples, normals)
            ],
            "fill": "none",
            "stroke": color,
            "stroke_width": base_width * 1.25,
            "stroke_opacity": stroke.burr_opacity,
            "stroke_linecap": "round",
        }
        if use_filters:
            burr_attrs["filter"] = "url(#texture-drypoint)"
        group.add(dwg.polygon(**burr_attrs))
    return group, [(sample.x, sample.y) for sample in stroke.samples]


def _render_arc_hand_stroke(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    cx: float,
    cy: float,
    r: float,
    attrs: dict,
    canvas: CanvasSize,
    render_seed: int | None,
    *,
    use_filters: bool,
    wild: bool = False,
):
    """弧を一筆のストロークとして演奏し、帯として描く (line / 閉図形と対称)。

    幾何の弧は不可視の意図要素 (`stroke="none"`) として残す。touching の接点契約は
    この意図弧の座標が担保するので、帯は自由端と同じく両端で 0 へ細ってよい
    (幅の下限を置かない)。抽出器 (`_svg_arcs`) は stroke-opacity 既定 "1"・
    `material-outline` クラス無しでこの意図要素を 1 個だけ数える。
    """
    assert ins.angle_start is not None and ins.angle_end is not None
    seed = _seed_for_instruction(ins, render_seed)
    varied = _needs_contour_variation(ins.variation)
    if varied:
        assert ins.variation is not None
        centerline = _arc_points_with_variation(
            cx,
            cy,
            r,
            ins.angle_start,
            ins.angle_end,
            ins.variation,
            seed,
            _amplitude_px(ins.variation, ins, canvas),
            canvas,
        )
    else:
        arc_len = r * abs(math.radians(ins.angle_end) - math.radians(ins.angle_start))
        centerline = _arc_points(
            cx, cy, r, ins.angle_start, ins.angle_end, _stroke_sample_count(arc_len, canvas)
        )
    base_width = _stroke_width_px(ins.weight, canvas, ins.thinness)
    stroke = synthesize_along(
        centerline,
        base_width,
        ins.weight,
        seed,
        closed=False,
        grid_step=_grid_step_px(ins.weight, canvas),
        wild=wild,
    )
    group = dwg.g(
        class_=(
            f"arc-stroke-v1 controls-{len(stroke.samples)} events-{stroke.event_count}"
        )
    )

    # 意図要素: 実線は不可視、破線・点線は細い線種として可視化 (line 側で
    # style != solid のとき幾何線を重ねているのと対称)。どちらも 1 要素なので
    # 抽出器に二重計上されない。
    body_attrs = _body_attrs_for_contour_stroke(attrs, ins, region_fill=False)
    body_attrs.pop("filter", None)
    if varied:
        group.add(dwg.polyline(points=centerline, **body_attrs))
    else:
        group.add(
            dwg.path(
                d=_arc_path_d(cx, cy, r, ins.angle_start, ins.angle_end), **body_attrs
            )
        )

    color = attrs.get("stroke", "#111111")
    opacity = float(attrs.get("stroke_opacity", 1.0))
    _add_raster_bleed(dwg, group, stroke.samples, stroke.grid_step, color)
    path_attrs = {
        "d": contour_stroke_path(stroke),
        "fill": color,
        "fill_opacity": opacity,
        "stroke": "none",
    }
    if use_filters and ins.weight in TEXTURE_FILTER_WEIGHTS and ins.weight != "drypoint":
        path_attrs["filter"] = f"url(#texture-{ins.weight})"
    group.add(dwg.path(**path_attrs))

    if ins.weight == "drypoint":
        offset = stroke.burr_side * base_width
        normals = centerline_normals(
            [(sample.x, sample.y) for sample in stroke.samples], False
        )
        burr_attrs = {
            "points": [
                (sample.x + nx * offset, sample.y + ny * offset)
                for sample, (nx, ny) in zip(stroke.samples, normals)
            ],
            "fill": "none",
            "stroke": color,
            "stroke_width": base_width * 1.25,
            "stroke_opacity": stroke.burr_opacity,
            "stroke_linecap": "round",
        }
        if use_filters:
            burr_attrs["filter"] = "url(#texture-drypoint)"
        group.add(dwg.polyline(**burr_attrs))

    if _uses_material_outline(ins.weight):
        if wild:
            arc_len = r * abs(
                math.radians(ins.angle_end) - math.radians(ins.angle_start)
            )
            _add_material_performed_outline(
                dwg,
                group,
                ins,
                attrs,
                [(sample.x, sample.y) for sample in stroke.samples],
                canvas,
                render_seed,
                closed=False,
                path_len_px=arc_len,
                center=(cx, cy),
            )
        else:
            _add_material_arc_outline(
                dwg,
                group,
                ins,
                attrs,
                cx,
                cy,
                r,
                ins.angle_start,
                ins.angle_end,
                canvas,
                render_seed,
            )
    return _apply_rotation(group, ins, canvas)


def _render_corner_shape(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    corners: list[tuple[float, float]],
    attrs: dict,
    canvas: CanvasSize,
    render_seed: int | None,
    *,
    use_filters: bool,
    wild: bool = False,
):
    """角を持つ閉図形 (triangle / polygon) を描く。角は筆の継ぎ目として固定。"""
    varied = _needs_contour_variation(ins.variation)
    contour, anchors = _edge_contour_with_anchors(
        corners,
        ins.variation if varied else None,
        _seed_for_instruction(ins, render_seed),
        _amplitude_px(ins.variation, ins, canvas) if ins.variation else 0.0,
        canvas,
    )
    points = contour if varied else corners
    if not _uses_hand_stroke(ins.weight):
        return _apply_rotation(dwg.polygon(points=points, **attrs), ins, canvas)
    fill_group, region_fill = _interior_fill(
        dwg, ins, points, attrs, canvas, render_seed, use_filters=use_filters, wild=wild
    )
    body_attrs = _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
    group = dwg.g()
    group.add(dwg.polygon(points=points, **body_attrs))
    if fill_group is not None:
        group.add(fill_group)
    contour_group, performed = _render_contour_hand_stroke(
        dwg,
        ins,
        contour,
        attrs,
        canvas,
        render_seed,
        use_filters=use_filters,
        anchors=anchors,
        wild=wild,
    )
    group.add(contour_group)
    # engine 15: この関数には材質輪郭の呼び出しが無かったので、triangle と polygon
    # だけが 5 道具すべてで裸のまま残っていた (square は自前の分岐に持っている)。
    # 角のある閉図形に幾何版の輪郭ヘルパーは無いため、演奏後の中心線から引く。
    # wild の有無で作り方を変えないのは、ここに凍結された幾何版が無く、engine 14 の
    # 教訓 (材質が墨から離れる) をそのまま適用できるからである。
    if _uses_material_outline(ins.weight):
        _add_material_performed_outline(
            dwg,
            group,
            ins,
            attrs,
            performed,
            canvas,
            render_seed,
            closed=True,
            path_len_px=_closed_path_length(performed),
            center=_points_center(points),
        )
    return _apply_rotation(group, ins, canvas)


def _render_instruction(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    cmap: dict[str, str] = COLOR_MAP,
    canvas: CanvasSize | None = None,
    *,
    work_assignment: dict[str, str] | None = None,
    use_filters: bool = True,
    render_seed: int | None = None,
    ins_idx: int = 0,
    mark_idx: int = 0,
    wild: bool = False,
):
    canvas = canvas or canvas_size_for_aspect(None)
    assignment = work_assignment or _work_color_assignment(cmap, render_seed, None)
    attrs = _stroke_attrs(
        ins,
        cmap,
        canvas,
        work_assignment=assignment,
        use_filters=use_filters,
    )
    if ins.mode == "carve":
        depth = ins.carve_depth or "half"
        attrs["stroke"] = {"light": "#8a8a8a", "half": "#c7c7c7", "bright": "#ffffff"}[
            depth
        ]
        attrs["fill"] = attrs["stroke"] if attrs.get("fill") != "none" else "none"
        attrs["stroke_opacity"] = {"light": 0.58, "half": 0.78, "bright": 0.96}[depth]

    if ins.primitive == "line":
        start = _px(ins.from_ if ins.from_ is not None else (0.5, 0.0), canvas)
        end = _px(ins.to if ins.to is not None else (0.5, 1.0), canvas)
        if ins.weight != "rotring":
            return _render_hand_stroke(
                dwg,
                ins,
                start,
                end,
                attrs,
                canvas,
                render_seed,
                use_filters=use_filters,
                wild=wild,
            )
        return _apply_rotation(dwg.line(start=start, end=end, **attrs), ins, canvas)

    if ins.primitive == "circle":
        if ins.center is None or ins.radius is None:
            raise ValueError("circle requires 'center' and 'radius'")
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        hand = _uses_hand_stroke(ins.weight)
        varied = _needs_contour_variation(ins.variation)
        if varied:
            assert ins.variation is not None
            contour = _closed_contour_with_variation(
                _circle_points(
                    cx, cy, r, r, _segment_count(2 * math.pi * r, canvas)
                ),
                (cx, cy),
                ins.variation,
                _seed_for_instruction(ins, render_seed),
                _amplitude_px(ins.variation, ins, canvas),
            )
        else:
            contour = _circle_points(
                cx, cy, r, r, _stroke_sample_count(2 * math.pi * r, canvas)
            )
        fill_group, region_fill = _interior_fill(
            dwg,
            ins,
            contour,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            wild=wild,
        )
        body_attrs = (
            _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
            if hand
            else attrs
        )
        if varied:
            element = dwg.polygon(points=contour, **body_attrs)
        else:
            element = dwg.circle(center=(cx, cy), r=r, **body_attrs)
        if hand or fill_group is not None or _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(element)
            if fill_group is not None:
                group.add(fill_group)
            performed: list[tuple[float, float]] | None = None
            if hand:
                contour_group, performed = _render_contour_hand_stroke(
                    dwg,
                    ins,
                    contour,
                    attrs,
                    canvas,
                    render_seed,
                    use_filters=use_filters,
                    wild=wild,
                )
                group.add(contour_group)
            if _uses_material_outline(ins.weight):
                if wild and performed is not None:
                    _add_material_performed_outline(
                        dwg,
                        group,
                        ins,
                        attrs,
                        performed,
                        canvas,
                        render_seed,
                        closed=True,
                        path_len_px=2 * math.pi * r,
                        center=(cx, cy),
                    )
                else:
                    _add_material_circle_outline(
                        dwg, group, ins, attrs, cx, cy, r, canvas, render_seed
                    )
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(element, ins, canvas)

    if ins.primitive == "ellipse":
        if ins.center is None or ins.size is None:
            raise ValueError("ellipse requires 'center' and 'size'")
        cx, cy = _px(ins.center, canvas)
        rx = ins.size[0] * canvas.width / 2
        ry = ins.size[1] * canvas.height / 2
        hand = _uses_hand_stroke(ins.weight)
        varied = _needs_contour_variation(ins.variation)
        if varied:
            assert ins.variation is not None
            contour = _closed_contour_with_variation(
                _circle_points(
                    cx,
                    cy,
                    rx,
                    ry,
                    _segment_count(_ellipse_perimeter(rx, ry), canvas),
                ),
                (cx, cy),
                ins.variation,
                _seed_for_instruction(ins, render_seed),
                _amplitude_px(ins.variation, ins, canvas),
            )
        else:
            contour = _circle_points(
                cx,
                cy,
                rx,
                ry,
                _stroke_sample_count(_ellipse_perimeter(rx, ry), canvas),
            )
        fill_group, region_fill = _interior_fill(
            dwg,
            ins,
            contour,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            wild=wild,
        )
        body_attrs = (
            _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
            if hand
            else attrs
        )
        if varied:
            element = dwg.polygon(points=contour, **body_attrs)
        else:
            element = dwg.ellipse(center=(cx, cy), r=(rx, ry), **body_attrs)
        if hand or fill_group is not None or _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(element)
            if fill_group is not None:
                group.add(fill_group)
            performed: list[tuple[float, float]] | None = None
            if hand:
                contour_group, performed = _render_contour_hand_stroke(
                    dwg,
                    ins,
                    contour,
                    attrs,
                    canvas,
                    render_seed,
                    use_filters=use_filters,
                    wild=wild,
                )
                group.add(contour_group)
            if _uses_material_outline(ins.weight):
                if wild and performed is not None:
                    _add_material_performed_outline(
                        dwg,
                        group,
                        ins,
                        attrs,
                        performed,
                        canvas,
                        render_seed,
                        closed=True,
                        path_len_px=_ellipse_perimeter(rx, ry),
                        center=(cx, cy),
                    )
                else:
                    _add_material_ellipse_outline(
                        dwg, group, ins, attrs, cx, cy, rx, ry, canvas, render_seed
                    )
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(element, ins, canvas)

    if ins.primitive == "cloudform":
        if ins.center is None or ins.size is None:
            raise ValueError("cloudform requires center and size")
        cx, cy = _px(ins.center, canvas)
        contour = generate_cloudform_contour(
            (cx, cy),
            (ins.size[0] * canvas.width, ins.size[1] * canvas.height),
            performance_seed=_seed_for_instruction(ins, render_seed),
            instruction_index=ins_idx,
            mark_index=mark_idx,
            variation=ins.variation,
            weight=ins.weight,
        )
        # 塗りは描かれた曲線に沿わせたいので、制御点ではなく Catmull-Rom を
        # 標本化した密なポリゴンを走査する。凹みも交点対のまま扱える。
        sampled = list(sample_closed_catmull_rom(contour.points))
        fill_group, region_fill = _interior_fill(
            dwg,
            ins,
            sampled,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            wild=wild,
        )
        # engine 15: 同じ密なポリラインを閉輪郭の共通経路へ渡す。square / circle /
        # polygon と同じ道を通るので、材質層の 3 機構 (材質輪郭・raster-bleed・
        # burr) と wild がまとめて届く。輪郭生成そのものは engine 14 のまま。
        hand = _uses_hand_stroke(ins.weight)
        if hand:
            body_attrs = _body_attrs_for_contour_stroke(
                attrs, ins, region_fill=region_fill
            )
        elif fill_group is not None:
            body_attrs = _copy_attrs(attrs)
            body_attrs["fill"] = "none"
            body_attrs.pop("fill_opacity", None)
        else:
            body_attrs = attrs
        path = dwg.path(d=contour.path_d, **body_attrs)
        # class は事実だけを名乗る。rotring は幾何のままなので触れていない。
        path["class"] = "cloudform contour-v1" + (
            " stroke-engine-touch" if hand else ""
        )
        if fill_group is None and not hand:
            return _apply_rotation(path, ins, canvas)
        group = dwg.g()
        group.add(path)
        if fill_group is not None:
            group.add(fill_group)
        if hand:
            contour_group, performed = _render_contour_hand_stroke(
                dwg,
                ins,
                sampled,
                attrs,
                canvas,
                render_seed,
                use_filters=use_filters,
                closed=True,
                wild=wild,
            )
            group.add(contour_group)
            if _uses_material_outline(ins.weight):
                _add_material_performed_outline(
                    dwg,
                    group,
                    ins,
                    attrs,
                    performed,
                    canvas,
                    render_seed,
                    closed=True,
                    path_len_px=_closed_path_length(performed),
                    center=_points_center(sampled),
                )
        return _apply_rotation(group, ins, canvas)

    if ins.primitive == "square":
        if ins.position is None or ins.size is None:
            raise ValueError("square requires 'position' and 'size'")
        x, y = _px(ins.position, canvas)
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        hand = _uses_hand_stroke(ins.weight)
        varied = _needs_contour_variation(ins.variation)
        contour, anchors = _edge_contour_with_anchors(
            corners,
            ins.variation if varied else None,
            _seed_for_instruction(ins, render_seed),
            _amplitude_px(ins.variation, ins, canvas) if ins.variation else 0.0,
            canvas,
        )
        fill_group, region_fill = _interior_fill(
            dwg,
            ins,
            contour if varied else corners,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            wild=wild,
        )
        body_attrs = (
            _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
            if hand
            else attrs
        )
        if varied:
            element = dwg.polygon(points=contour, **body_attrs)
        else:
            element = dwg.rect(insert=(x, y), size=(w, h), **body_attrs)
        if hand or fill_group is not None or _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(element)
            if fill_group is not None:
                group.add(fill_group)
            performed = None
            if hand:
                contour_group, performed = _render_contour_hand_stroke(
                    dwg,
                    ins,
                    contour,
                    attrs,
                    canvas,
                    render_seed,
                    use_filters=use_filters,
                    anchors=anchors,
                    wild=wild,
                )
                group.add(contour_group)
            if _uses_material_outline(ins.weight):
                if wild and performed is not None:
                    _add_material_performed_outline(
                        dwg,
                        group,
                        ins,
                        attrs,
                        performed,
                        canvas,
                        render_seed,
                        closed=True,
                        path_len_px=2 * (w + h),
                        center=(x + w / 2, y + h / 2),
                    )
                else:
                    _add_material_rect_outline(
                        dwg, group, ins, attrs, x, y, w, h, canvas, render_seed
                    )
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(element, ins, canvas)

    if ins.primitive == "triangle":
        if ins.position is None or ins.size is None:
            raise ValueError("triangle requires 'position' and 'size'")
        x, y = _px(ins.position, canvas)
        w = ins.size[0] * canvas.width
        h = ins.size[1] * canvas.height
        corners = [
            (x + w / 2, y),
            (x, y + h),
            (x + w, y + h),
        ]
        return _render_corner_shape(
            dwg,
            ins,
            corners,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            wild=wild,
        )

    if ins.primitive == "polygon":
        if ins.center is None or ins.radius is None:
            raise ValueError("polygon requires 'center' and 'radius'")
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        return _render_corner_shape(
            dwg,
            ins,
            _polygon_points(cx, cy, r, ins.sides or 5),
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            wild=wild,
        )

    if ins.primitive == "arc":
        if ins.center is None or ins.radius is None:
            raise ValueError("arc requires 'center' and 'radius'")
        if ins.angle_start is None or ins.angle_end is None:
            raise ValueError("arc requires 'angle_start' and 'angle_end'")
        cx, cy = _px(ins.center, canvas)
        r = ins.radius * canvas.unit
        if _uses_hand_stroke(ins.weight):
            return _render_arc_hand_stroke(
                dwg,
                ins,
                cx,
                cy,
                r,
                attrs,
                canvas,
                render_seed,
                use_filters=use_filters,
                wild=wild,
            )
        if _needs_contour_variation(ins.variation):
            assert ins.variation is not None
            contour = _arc_points_with_variation(
                cx,
                cy,
                r,
                ins.angle_start,
                ins.angle_end,
                ins.variation,
                _seed_for_instruction(ins, render_seed),
                _amplitude_px(ins.variation, ins, canvas),
                canvas,
            )
            element = dwg.polyline(points=contour, **attrs)
        else:
            path_d = _arc_path_d(cx, cy, r, ins.angle_start, ins.angle_end)
            element = dwg.path(d=path_d, **attrs)
        if _uses_material_outline(ins.weight):
            group = dwg.g()
            group.add(element)
            _add_material_arc_outline(
                dwg,
                group,
                ins,
                attrs,
                cx,
                cy,
                r,
                ins.angle_start,
                ins.angle_end,
                canvas,
                render_seed,
            )
            return _apply_rotation(group, ins, canvas)
        return _apply_rotation(element, ins, canvas)

    raise NotImplementedError(f"primitive '{ins.primitive}' not yet supported")
