"""JSON Score → SVG renderer.

楽譜(Score)を演奏(SVG)に変換する。揺らぎ(variation)の実現は Renderer 層で行う
(SPEC §13.8)。Phase 1 は静的描画のみ、perlin/wave は段階追加。
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import struct
from collections.abc import Sequence

import svgwrite

from .cloudform import generate_cloudform_contour, sample_closed_catmull_rom
from .color_catalogs import DEFAULT_COLOR_CATALOG_ID as DEFAULT_COLOR_CATALOG_ID
from .master_grid import MASTER_GRID_DECIMALS, fmt
from .plugins import CanvasSize, canvas_size_for_aspect
from .schema import (
    CLOSED_SHAPES,
    Instruction,
    Score,
    SurfaceSpec,
    Variation,
    fill_is_asked_for,
)
from .render_engines.default.determinism import (
    _SEED_ARRANGEMENT_FIELDS as _SEED_ARRANGEMENT_FIELDS,
    _SEED_INSTRUCTION_FIELDS as _SEED_INSTRUCTION_FIELDS,
    _VARIATION_SEED_FIELDS_ALL as _VARIATION_SEED_FIELDS_ALL,
    _WORK_COLOR_SEED_FIELDS as _WORK_COLOR_SEED_FIELDS,
    _hash01,
    _hash_to_unit,
    _needs_blur,
    _needs_contour_variation,
    _needs_path_variation,
    _periodic_value_noise_1d,
    _seed_for_instruction,
    _value_noise_1d,
    _variation_seed_fields as _variation_seed_fields,
    _wave_phase,
    new_render_seed as new_render_seed,
)
from .render_engines.default import planning as _planning
from .render_engines.default import document as _document
from .render_engines.default import palette as _palette
from .render_engines.default import layers as _layers
from .arc_geometry import arc_svg_flags
from .svg_compat import validate_compat_svg
from .stroke_engine import (
    GRAMMARS,
    Support,
    centerline_normals,
    contour_stroke_path,
    grid_point,
    outline_for_centerline,
    polygon_path,
    support_with_mark_word,
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

COLOR_MAP = _palette.COLOR_MAP
SVG_PROFILES = _document.SVG_PROFILES
HUE_HINTS = _palette.HUE_HINTS

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
AMPLITUDE_WIDTHS: dict[str, float] = {"fine": 0.35, "medium": 0.6, "broad": 2.0}

# The material layer is a tone beside the mark, not a second mark: no stratum may
# be wider than this share of the tool's own stroke. The tools that already state
# their strata as a ratio chose 0.20-0.28, and the absolute ones land between
# 0.17 and 0.47; the cap is set where pencil and chalk already sit, so it moves
# the two outliers and leaves the rest untouched (author's ruling, 2026-08-09).
MATERIAL_OUTLINE_MAX_WIDTH_RATIO = 0.33
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


def _outline_wander_px(offset_px: float, canvas: CanvasSize) -> float:
    """How far a stratum drifts off its own offset along the path.

    Strata that stay exactly parallel read as engraved rails rather than as a
    tool's own edges. Both emitters (the straight tools and the performed
    contours) ask here, so the amount is stated once and a test can bound the
    layer's distance to the ink without restating the formula.
    """
    return 0.35 * abs(offset_px) + 0.6 * _unit_scale(canvas)


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


# render engine 38: 薄墨 named on a line or an arc. A wash is how the ink was
# diluted, so the tool carries more of a thinner ink -- the mark comes out
# broad and pale rather than as the tool's ordinary band. The author chose
# these two numbers on 2026-08-16 from a contact sheet of four readings.
WASH_MARK_WIDTH_GAIN = 3.0
WASH_MARK_OPACITY_GAIN = 0.35


def _is_wash_mark(ins: Instruction) -> bool:
    """Whether this instruction is an open shape whose 面 says 薄墨.

    A closed shape's 薄墨 is its interior and is drawn by the surface-texture
    layer (`_has_surface_texture`), so widening its outline as well would say
    one word twice. Written as two statements rather than one expression
    because each half is a separate claim a perturbation aims at on its own.
    """
    if ins.primitive in _CLOSED_SHAPES:
        return False
    surface = ins.surface
    return surface is not None and surface.texture == "wash"


def _mark_width_gain(ins: Instruction) -> float:
    """How much broader this instruction's mark is than the tool's own band."""
    return WASH_MARK_WIDTH_GAIN if _is_wash_mark(ins) else 1.0


def _mark_width_px(ins: Instruction, canvas: CanvasSize) -> float:
    """The width of this instruction's mark (px). The one entrance.

    Every width in this module is asked for here rather than of
    `_stroke_width_px`, which knows only the tool and the thinness and so
    cannot see that a mark was described. Wiring only the call sites an open
    shape reaches would leave the rest indistinguishable from a missed one --
    a closed shape passes through unchanged, so routing all of them costs
    nothing and makes "did anyone forget?" a question `grep` can answer.
    """
    return _stroke_width_px(ins.weight, canvas, ins.thinness) * _mark_width_gain(ins)


def _nominal_mark_width_px(ins: Instruction, canvas: CanvasSize) -> float:
    """The same width with the thinness modifier left out.

    The material outline reads its ceiling against the tool's own mark and not
    against the thinned one, because how wide the tone is belongs to the tool's
    grain (`_material_outline_profile`). How much ink the tool is carrying is a
    different question, and the wash answers that one, so the gain applies here
    while the thinness does not.
    """
    return _stroke_width_px(ins.weight, canvas) * _mark_width_gain(ins)


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


SOLID_MOTTLE_BASE_FREQUENCY = 0.035
SOLID_MOTTLE_NUM_OCTAVES = 3
SOLID_MOTTLE_ALPHA_FLOOR = 0.31
SOLID_MOTTLE_OVERLAY_OPACITY = 0.22


def _solid_mottle_filter_id(
    ins: Instruction, render_seed: int | None, ins_idx: int, mark_idx: int
) -> tuple[str, int]:
    """A per-mark deterministic filter ID and seed, never a shared literal."""
    instruction_seed = _seed_for_instruction(ins, render_seed)
    identity = f"{instruction_seed}:{ins_idx}:{mark_idx}:solid-mottle".encode("utf-8")
    seed = struct.unpack("<I", hashlib.sha256(identity).digest()[:4])[0]
    return _safe_svg_id(f"solid-mottle-{ins_idx:03d}-{mark_idx:03d}-{seed:08x}"), seed


def _solid_mottle_filter_xml(filter_id: str, seed: int) -> str:
    """A standard filter whose alpha is a calibrated, deterministic mottle."""
    return (
        f'<filter id="{filter_id}" x="-2%" y="-2%" width="104%" height="104%" '
        'color-interpolation-filters="sRGB">'
        f'<feTurbulence type="fractalNoise" baseFrequency="{fmt(SOLID_MOTTLE_BASE_FREQUENCY)}" '
        f'numOctaves="{SOLID_MOTTLE_NUM_OCTAVES}" seed="{seed}" result="solidMottleNoise"/>'
        '<feColorMatrix in="solidMottleNoise" type="luminanceToAlpha" result="solidMottleAlpha"/>'
        f'<feComponentTransfer in="solidMottleAlpha" result="solidMottleFloor"><feFuncA type="table" '
        f'tableValues="{SOLID_MOTTLE_ALPHA_FLOOR} 1"/></feComponentTransfer>'
        '<feComposite in="SourceGraphic" in2="solidMottleFloor" operator="in"/>'
        "</filter>"
    )


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
        w, h = _size_px(ins.size, canvas)
        rx, ry = w / 2, h / 2
        return math.sqrt(max(0.0, rx * ry))
    if p in ("square", "triangle", "cloudform") and ins.size is not None:
        w, h = _size_px(ins.size, canvas)
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

    `_mark_width_px` is a pure function of the instruction, so this can ask it
    directly rather than having the seven call sites thread the width through.
    The representative-size clamp stays: it is the safety valve that keeps a
    figure smaller than its own mark from wandering further than it is wide.
    """
    width = _mark_width_px(ins, canvas)
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


FRAME_LO = _planning.FRAME_LO
FRAME_HI = _planning.FRAME_HI
_scatter_pos = _planning._scatter_pos
_rhythm_t = _planning._rhythm_t
_PATH_WAVE_AMPLITUDE = _planning._PATH_WAVE_AMPLITUDE
_PATH_JITTER = _planning._PATH_JITTER
_PATH_SPREAD = _planning._PATH_SPREAD
_path_pos = _planning._path_pos
_density_radius = _planning._density_radius
_clustered_pos = _planning._clustered_pos
_clamp01 = _planning._clamp01
_ensure_line_coords = _planning._ensure_line_coords
_anchor = _planning._anchor
_shift = _planning._shift
_apply_color_cycle = _planning._apply_color_cycle
_strip_performance_fields = _planning._strip_performance_fields
_move_anchor_to = _planning._move_anchor_to
_short_side_scales = _planning._short_side_scales
_region_in_short_side_units = _planning._region_in_short_side_units
_resolve_at_region = _planning._resolve_at_region
_bbox_for_instruction = _planning._bbox_for_instruction
_bbox_center = _planning._bbox_center
_bbox_radius = _planning._bbox_radius
_relation_gap = _planning._relation_gap
_rotate_screen_point = _planning._rotate_screen_point
_rotate_screen_vector = _planning._rotate_screen_vector
_canvas_endpoint_geometry = _planning._canvas_endpoint_geometry
_performed_arc_sagitta = _planning._performed_arc_sagitta
_dropped_relation = _planning._dropped_relation
_resolve_touching_relation = _planning._resolve_touching_relation
_resolve_relation = _planning._resolve_relation
_instruction_extent = _planning._instruction_extent
_scale_instruction = _planning._scale_instruction
_composite_member_copy = _planning._composite_member_copy
_expand_composite_groups = _planning._expand_composite_groups
_resolve_performance_score = _planning._resolve_performance_score
_render_effect_hint = _palette._render_effect_hint
_FADE_NEAR_FAR = _planning._FADE_NEAR_FAR
_FADE_FILL_RATIO = _planning._FADE_FILL_RATIO
_FADE_SPAN_EPS = _planning._FADE_SPAN_EPS
_FADE_LEVEL_RE = _planning._FADE_LEVEL_RE
_FADE_LEVEL_TAG_RE = _planning._FADE_LEVEL_TAG_RE
_fade_levels = _planning._fade_levels
_apply_fade_levels = _planning._apply_fade_levels
_scale_member = _planning._scale_member
_turn_member = _planning._turn_member
_apply_member_sizes = _planning._apply_member_sizes
_apply_member_rotations = _planning._apply_member_rotations
_finish_expanded_group = _planning._finish_expanded_group
_fade_level_from_hint = _planning._fade_level_from_hint
_strip_fade_level = _planning._strip_fade_level
_expand_arrangement_layout = _planning._expand_arrangement_layout
_fit_axis_scales = _planning._fit_axis_scales
_fit_group_to_anchor = _planning._fit_group_to_anchor
ARRANGEMENT_QUANTUM = _planning.ARRANGEMENT_QUANTUM
_quantise = _planning._quantise
_quantise_instructions = _planning._quantise_instructions
_expand_arrangement = _planning._expand_arrangement
_norm_label = _palette._norm_label
_line_perp_offsets = _planning._line_perp_offsets
_point_on_line = _planning._point_on_line


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


_score_canvas_aspect = _document._score_canvas_aspect
_score_canvas_ground = _document._score_canvas_ground


_score_support = _layers._score_support


def _instruction_support(ins: Instruction, support: Support) -> Support:
    """Raise the sheet where the instruction itself said how the mark runs.

    Open shapes only. A closed shape's 粒 or にじみ is its interior, drawn by
    the surface-texture layer, so working the sheet as well would say one word
    twice and draw it twice.
    """
    surface = ins.surface
    if surface is None or ins.primitive in _CLOSED_SHAPES:
        return support
    return support_with_mark_word(support, surface.texture)


_texture_seed = _layers._texture_seed
_ground_tone_color = _layers._ground_tone_color
_GROUND_MM = _layers._GROUND_MM
_GROUND_GRAIN_RADIUS = _layers._GROUND_GRAIN_RADIUS
_GROUND_OPACITY_DEFAULT = _layers._GROUND_OPACITY_DEFAULT
_GROUND_DENSITY_DEFAULT = _layers._GROUND_DENSITY_DEFAULT
GROUND_BYTE_BUDGET = _layers.GROUND_BYTE_BUDGET
_MEZZOTINT_PLATE = _layers._MEZZOTINT_PLATE
_ground_mm = _layers._ground_mm
_GroundRandom = _layers._GroundRandom
_ground_wrapped = _layers._ground_wrapped
_paper_ground_layers = _layers._paper_ground_layers
_washi_ground_layers = _layers._washi_ground_layers
_ink_wash_ground_layers = _layers._ink_wash_ground_layers
_charcoal_ground_layers = _layers._charcoal_ground_layers
_canvas_ground_layers = _layers._canvas_ground_layers
_drawing_paper_ground_layers = _layers._drawing_paper_ground_layers
_mezzotint_ground_layers = _layers._mezzotint_ground_layers
_PAPER_COARSE_TILES = _layers._PAPER_COARSE_TILES
_PAPER_COARSE_RADIUS = _layers._PAPER_COARSE_RADIUS
_GROUND_LAYER_BUILDERS = _layers._GROUND_LAYER_BUILDERS
_render_canvas_ground = _layers._render_canvas_ground


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
        max(_mark_width_px(ins, canvas), radius * 1.3),
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
        signature = WEIGHT_STYLE.get(ins.weight, {})
        path_attrs["stroke_opacity"] = signature.get("stroke_opacity", 1.0)
        if "stroke_linecap" in signature:
            path_attrs["stroke_linecap"] = signature["stroke_linecap"]
        if "stroke_dasharray" in signature:
            path_attrs["stroke_dasharray"] = signature["stroke_dasharray"]
    if use_filters and ins.weight in TEXTURE_FILTER_WEIGHTS and ins.weight != "drypoint":
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
        reach = max(mark_radius * 2.0, _mark_width_px(ins, canvas) * 0.75)
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
    support: Support,
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
                    _mark_width_px(ins, canvas),
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
    support: Support,
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
    )
    return group, None


build_texture_metadata = _document.build_texture_metadata
_normalize_svg_profile = _document._normalize_svg_profile
_safe_svg_id = _document._safe_svg_id
_instruction_svg_id = _document._instruction_svg_id
_mark_svg_id = _document._mark_svg_id
_inject_svg_document_metadata = _document._inject_svg_document_metadata
_new_svg_drawing = _document._new_svg_drawing
_build_root_groups = _document._build_root_groups
_attach_root_groups = _document._attach_root_groups
_inject_extra_defs = _document._inject_extra_defs


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
    # Built before the score is resolved because `_resolve_at_region` needs it.
    # Resolution only replaces `instructions` and passes `canvas` through, so
    # the aspect read here is the same one the old order read after it.
    canvas = canvas_size_for_aspect(canvas_aspect or _score_canvas_aspect(score))
    score = _resolve_performance_score(
        score, render_seed, canvas, composition_seed=composition_seed
    )
    structured = profile != "display"
    use_filters = profile == "display"
    cmap = {**COLOR_MAP, **(color_map or {})}
    work_assignment = _work_color_assignment(cmap, render_seed, catalog_id)
    dwg = _new_svg_drawing(canvas)
    bg = work_assignment.get(score.background, cmap.get(score.background, BACKGROUND))
    ground_layer, ground_defs_xml = _render_canvas_ground(
        dwg, score, canvas, bg, profile=profile, render_seed=render_seed
    )
    surface_filter_xml: list[str] = []
    solid_mottle_filter_xml: list[str] = []
    performance_filter_xml: str | None = None
    artboard, content, presence_content = _build_root_groups(
        dwg, canvas, bg, ground_layer, structured=structured
    )

    if use_filters and render_seed is not None:
        performance_filter_id, performance_filter_xml = _performance_touch_filter(
            render_seed, canvas
        )
        content["filter"] = f"url(#{performance_filter_id})"

    blur_needed: dict[str, float] = {}
    texture_filters = _texture_filter_weights(score) if use_filters else set()
    blur_elems: list[tuple[str, str]] = []
    elem_idx = 0

    # The sheet this work is worked on. Resolved once from the ground the work
    # names, then handed down by argument -- never held in a module variable,
    # because the more places read it the quieter a missed hand-over gets.
    sheet = _score_support(score)
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
            solid_mottle_id: str | None = None
            if (
                profile != "compat"
                and _is_noncomputer_solid_fill(single)
            ):
                solid_mottle_id, solid_mottle_seed = _solid_mottle_filter_id(
                    single, render_seed, ins_idx, mark_idx
                )
                solid_mottle_filter_xml.append(
                    _solid_mottle_filter_xml(solid_mottle_id, solid_mottle_seed)
                )
            element = _render_instruction(
                dwg,
                single,
                cmap,
                canvas,
                work_assignment=work_assignment,
                use_filters=use_filters,
                solid_mottle_filter_id=solid_mottle_id,
                render_seed=render_seed,
                ins_idx=ins_idx,
                mark_idx=mark_idx,
                wild=wild,
                support=sheet,
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
                support=sheet,
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

    _attach_root_groups(dwg, artboard, content, structured=structured)
    svg = dwg.tostring()
    svg = _inject_extra_defs(
        svg,
        [
            ground_defs_xml or "",
            *surface_filter_xml,
            *solid_mottle_filter_xml,
            performance_filter_xml or "",
        ],
    )
    svg = _inject_texture_filters(svg, texture_filters, canvas)
    if blur_elems:
        svg = _inject_blur_filters(svg, blur_needed, blur_elems)
    if structured:
        svg = _inject_svg_document_metadata(svg, profile=profile)
    svg = _apply_master_grid(svg)
    if profile == "compat":
        validate_compat_svg(svg)
    return svg


# The set moved to `schema.py` so coerce decides by the same one. The private
# name stays because this module reads it in three places.
_CLOSED_SHAPES = CLOSED_SHAPES


def _texture_filter_weights(score: Score) -> set[str]:
    weights: set[str] = set()
    for ins in score.instructions:
        if ins.weight in TEXTURE_FILTER_WEIGHTS:
            weights.add(ins.weight)
    return weights


_score_visual_load = _layers._score_visual_load
_presence_center_px = _layers._presence_center_px
_presence_seed = _layers._presence_seed
_render_presence_layer = _layers._render_presence_layer


_hex_to_rgb = _palette._hex_to_rgb
_hue_from_hex = _palette._hue_from_hex
_ASCII_HINT_TOKEN_RE = _palette._ASCII_HINT_TOKEN_RE
_ASCII_HINT_WORD_RE = _palette._ASCII_HINT_WORD_RE
_ACHROMATIC_COLORS = _palette._ACHROMATIC_COLORS
_CHROMATIC_COLORS = _palette._CHROMATIC_COLORS
_CHROMATIC_BANDS = _palette._CHROMATIC_BANDS
_CHROMATIC_BAND_CENTERS = _palette._CHROMATIC_BAND_CENTERS
_OKLCH_CHROMA_FLOOR = _palette._OKLCH_CHROMA_FLOOR
_HINT_HUE_PRIORITY = _palette._HINT_HUE_PRIORITY
_oklch_from_hex = _palette._oklch_from_hex
_chromatic_band = _palette._chromatic_band
_circular_hue_distance = _palette._circular_hue_distance
_work_color_choice = _palette._work_color_choice
_work_color_assignment = _palette._work_color_assignment
_hint_hues = _palette._hint_hues
_resolve_color = _palette._resolve_color


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
        "stroke_width": _mark_width_px(ins, canvas),
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
    if _is_wash_mark(ins):
        # render engine 38. Multiplied rather than capped, and last: 薄墨 is a
        # dilution, so it pales whatever this mark was already going to be
        # instead of naming a ceiling of its own. The clauses above name
        # ceilings because a hint says how strongly the thing is present; a
        # mark already faint for another reason must not come back up to 0.35.
        attrs["stroke_opacity"] = round(
            float(attrs.get("stroke_opacity", 1.0)) * WASH_MARK_OPACITY_GAIN,
            MASTER_GRID_DECIMALS,
        )
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



def _dash_spec_stats(dash: str | None) -> tuple[float, float]:
    """The coverage and grain a tool's dash pattern implies.

    The patterns in `_MATERIAL_OUTLINE_SPECS` carry a tool's character -- the pen
    is nearly continuous, the pencil is mostly gap -- and that tuning is worth
    keeping once the cadence is gone. Coverage is the share of the path the
    pattern marked; grain is its natural wavelength, in unscaled units.
    """
    if not dash:
        return 1.0, 0.0
    values = [abs(float(v)) for v in dash.split(",") if v.strip()]
    if not values or sum(values) <= 0:
        return 1.0, 0.0
    # An odd-length pattern swaps marks and gaps on every repeat, so read it twice.
    if len(values) % 2:
        values = values + values
    marks, gaps = values[0::2], values[1::2]
    coverage = sum(marks) / sum(values)
    grain = sum(marks) / len(marks) + sum(gaps) / len(gaps)
    return coverage, grain


def _contact_field(t: float, seed: int) -> float:
    """The paper's tooth at two scales, read along the path. Roughly 0..1."""
    return 0.62 * _value_noise_1d(t, seed) + 0.38 * _value_noise_1d(
        t * 2.7 + 13.1, seed + 977
    )


# Paper-contact decisions share the SVG's six-decimal length lattice. A libm
# ULP is far below this precision, but before engine 29 it could add a sample,
# move the sample-derived quantile, and replace a whole fragment.
CONTACT_LENGTH_QUANTUM = 6


def _quantise_contact_length(value: float) -> float:
    return round(value, CONTACT_LENGTH_QUANTUM)


def _resample_by_length(
    points: list[tuple[float, float]], step: float, closed: bool
) -> list[tuple[float, float]]:
    """Walk a polyline and emit a point every `step` px of arc length.

    `_resample_points` picks by index, which is even only when the source
    vertices are. The contact field is read against distance on the paper, so it
    needs a walk that is even in length.
    """
    step = _quantise_contact_length(step)
    if step <= 0 or len(points) < 2:
        return list(points)
    path = points + [points[0]] if closed else points
    out = [path[0]]
    carry = 0.0
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        seg = _quantise_contact_length(math.hypot(bx - ax, by - ay))
        if seg <= 1e-9:
            continue
        travelled = step - carry
        while travelled <= seg:
            f = travelled / seg
            out.append((ax + (bx - ax) * f, ay + (by - ay) * f))
            travelled += step
        carry = (carry + seg) % step
    return out


def _contact_fragments(
    points: list[tuple[float, float]],
    *,
    coverage: float,
    grain_px: float,
    seed: int,
    closed: bool,
) -> list[tuple[list[tuple[float, float]], float]]:
    """The pieces of an outline where the tool actually met the paper.

    A dasharray repeats. However long the pattern, a long contour walks through
    it several times and the eye finds the cadence -- and the material layer is
    not a dotted line, it is where a tool dragged across a grain and kept losing
    the paper. So presence is a smooth noise field read along the arc length, and
    the outline exists where the field clears a threshold.

    The threshold is the (1 - coverage) quantile of the field's own samples, not
    a constant: that way each tool keeps the share of the path its dash pattern
    used to mark, while nothing about the spacing repeats. Fragments come back
    with a weight, so the thinly-touching ones are fainter than the ones the tool
    bore down on.
    """
    if len(points) < 2:
        return []
    if grain_px <= 0 or coverage >= 0.999:
        return [(list(points), 1.0)]

    # Three samples per grain resolves a skip; the cap keeps a long contour from
    # turning into thousands of SVG vertices.
    total = _quantise_contact_length(
        sum(
            _quantise_contact_length(math.hypot(b[0] - a[0], b[1] - a[1]))
            for a, b in zip(
                points, points[1:] + points[:1] if closed else points[1:]
            )
        )
    )
    if total <= 1e-6:
        return []
    grain_px = _quantise_contact_length(grain_px)
    step = _quantise_contact_length(max(grain_px / 3.0, total / 600.0, 0.8))
    walk = _resample_by_length(points, step, closed)
    if len(walk) < 3:
        return [(list(points), 1.0)]

    field = [_contact_field(i * step / grain_px, seed) for i in range(len(walk))]
    ordered = sorted(field)
    index = min(len(ordered) - 1, max(0, int((1.0 - coverage) * len(ordered))))
    threshold = ordered[index]
    span = max(1e-6, ordered[-1] - threshold)

    runs: list[list[int]] = []
    current: list[int] = []
    for i, value in enumerate(field):
        if value >= threshold:
            current.append(i)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    # On a closed path the seam is not an end: a run that touches both ends is
    # one fragment that happens to be written in two halves.
    if closed and len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == len(field) - 1:
        runs[0] = runs[-1] + runs[0]
        runs.pop()

    def _crossing(outside: int, inside: int) -> tuple[float, float]:
        """Where the field crosses the threshold between two samples.

        Without this the ends of every fragment land on a sample, so every
        length is a multiple of `step` and the lengths themselves become the
        cadence -- the regularity comes back through the sampling instead of
        through the pattern.
        """
        f_out, f_in = field[outside], field[inside]
        if abs(f_in - f_out) < 1e-9:
            return walk[inside]
        f = min(1.0, max(0.0, (threshold - f_out) / (f_in - f_out)))
        ax, ay = walk[outside]
        bx, by = walk[inside]
        return (ax + (bx - ax) * f, ay + (by - ay) * f)

    fragments: list[tuple[list[tuple[float, float]], float]] = []
    for run in runs:
        piece = [walk[i] for i in run]
        if run[0] - 1 >= 0:
            piece.insert(0, _crossing(run[0] - 1, run[0]))
        if run[-1] + 1 < len(field):
            piece.append(_crossing(run[-1] + 1, run[-1]))
        if len(piece) < 2:
            continue
        length = _quantise_contact_length(
            sum(
                _quantise_contact_length(math.hypot(b[0] - a[0], b[1] - a[1]))
                for a, b in zip(piece, piece[1:])
            )
        )
        if length < 0.6:
            continue
        margin = sum(field[i] - threshold for i in run) / len(run)
        weight = min(1.0, 0.55 + 0.75 * (margin / span))
        fragments.append((piece, weight))
    return fragments


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
    attrs: dict,
    *,
    stroke_width: float,
    opacity: float,
    dash: str | None = None,
    stratum: int | None = None,
) -> dict:
    result = _copy_attrs(attrs)
    result["fill"] = "none"
    result["stroke_width"] = stroke_width
    result["stroke_opacity"] = opacity
    # 材質装飾であることを明示する。読み手 (弧抽出・ラスタライザ等) が主線と
    # 装飾を区別するのに opacity の大小へ頼らずに済ませるため。
    #
    # engine 28: a stratum index rides along. A tool's strata used to be one
    # element each, so "the pen leaves two split nibs" could be read off the
    # element count; contact broke each stratum into fragments, and their widths
    # are not distinct either once the width cap folds two of them together. The
    # index keeps the claim observable instead of leaving it to arithmetic.
    result["class"] = (
        "material-outline" if stratum is None else f"material-outline stratum-{stratum}"
    )
    if dash is not None:
        result["stroke_dasharray"] = dash
    else:
        # The body attrs carry the tool's own broken quality (`WEIGHT_STYLE`,
        # e.g. pencil "1,3"). While this helper always overwrote it there was
        # nothing to strip; now that contact decides where the outline exists,
        # an inherited pattern would cut the fragments a second time on a fixed
        # cadence -- exactly the regularity the fragments are there to remove.
        result.pop("stroke_dasharray", None)
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
    ins: Instruction, canvas: CanvasSize
) -> list[tuple[float, float, float, str | None]]:
    """材質輪郭の (offset, 線幅, opacity, dasharray)。すべて canvas.unit 相対。

    細く引いた線の材質層は墨と同じだけ細くなる。基準を公称幅に据え置くと、
    墨だけが細って材質が取り残される。

    It takes the instruction rather than the tool because both widths below are
    asked of `_mark_width_px` / `_nominal_mark_width_px`, and those two are the
    only places left that know a mark can be described (render engine 38). All
    five callers already had the instruction in hand.
    """
    spec = _MATERIAL_OUTLINE_SPECS.get(ins.weight)
    if not spec:
        return []
    scale = _unit_scale(canvas)
    base_width = _mark_width_px(ins, canvas)
    offset_gain = _material_gain("outline_offset")
    opacity_gain = _material_gain("outline_opacity")
    nominal_width = _nominal_mark_width_px(ins, canvas)
    half = base_width / 2.0
    out = []
    for offset, abs_width, width_ratio, opacity, dash in spec:
        # engine 28: both of these are read against the tool's own mark now.
        # While the layer sat on the ideal geometry its distance to the band was
        # incidental, so the table could carry absolute numbers and nobody saw
        # what they came to beside the ink. Riding the band, two of them showed:
        # brush_thin's second stratum was 0.47 of its own mark (the widest of any
        # tool) and sat 1.07 half-widths out (the closest), so the tone read as a
        # second mark rather than as tone. Author's ruling: fit the tool.
        # The cap reads the tool's nominal stroke, not the thinned one. How wide
        # the tone is belongs to the tool's own grain -- paper tooth and powder
        # do not get finer because the line was drawn finer, which is what
        # `test_material_outline_absolute_widths_do_not_move` holds. Where it
        # sits is a different question, and that one is asked of the actual mark.
        width = min(
            abs_width * scale + base_width * width_ratio,
            nominal_width * MATERIAL_OUTLINE_MAX_WIDTH_RATIO,
        )
        placed = _outline_offset_px(offset * scale * offset_gain, canvas)
        # A stratum centred inside the mark cannot be tone beside it; it only
        # thickens the mark. Put it on the edge and let the wander take it out.
        placed = math.copysign(max(abs(placed), half), placed)
        out.append(
            (
                placed,
                width,
                _outline_opacity(opacity * opacity_gain),
                _scale_dash(dash, scale),
            )
        )
    return out


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
    for offset, width, opacity, dash in _material_outline_profile(ins, canvas):
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
    for offset, width, opacity, dash in _material_outline_profile(ins, canvas):
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
    for offset, width, opacity, dash in _material_outline_profile(ins, canvas):
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
    for offset, width, opacity, dash in _material_outline_profile(ins, canvas):
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
    *,
    wander: float = 0.0,
    wander_period: float = 1.0,
    seed: int = 0,
) -> list[tuple[float, float]]:
    """演奏後の中心線を法線方向へ amount だけずらす。正が外側。

    法線の符号は輪郭の生成順で変わる (円は内向き、弧は外向き) ので、図形の中心に
    対して一度だけ多数決で決める。幾何版の `r + offset` と向きを揃えるため。

    `wander` adds a low-frequency drift to the offset along the arc length, the
    same way `_offset_polyline` does it for the straight tools: strata that stay
    exactly parallel read as engraved rails rather than as a tool's own edges.
    """
    normals = centerline_normals(path, closed)
    votes = 0
    for (x, y), (nx, ny) in zip(path, normals):
        votes += 1 if nx * (x - center[0]) + ny * (y - center[1]) >= 0 else -1
    sign = 1.0 if votes >= 0 else -1.0
    out: list[tuple[float, float]] = []
    arc = 0.0
    for i, ((x, y), (nx, ny)) in enumerate(zip(path, normals)):
        off = amount
        if wander:
            off += wander * (
                _value_noise_1d(arc / max(1e-6, wander_period), seed) * 2 - 1
            )
        out.append((x + nx * off * sign, y + ny * off * sign))
        if i + 1 < len(path):
            arc += math.hypot(path[i + 1][0] - x, path[i + 1][1] - y)
    return out


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
    (engine 12 が直線で直したのと同じ型の不具合)。

    engine 28: **すべての描画がここを通る**。以前は wild のときだけで、OFF は幾何版の
    `r + offset` を使っていた —— つまり装飾が意図した幾何に貼りついたまま墨だけが
    離れ、破線の幽霊が絵の中に露出していた。作者裁定 (2026-08-09):
    **装飾は墨の実態に対してオフセットを取る。**

    掠れも同じ裁定で変わった。装飾は道具が紙の地と接したときの掠れであって、
    規則的な点線ではない。dasharray は捨て、`_contact_fragments` が返す
    「触れていた区間」だけを描く。
    """
    seed = _seed_for_instruction(ins, render_seed)
    scale = _unit_scale(canvas)
    element = dwg.polyline
    for k, (offset, width, opacity, dash) in enumerate(
        _material_outline_profile(ins, canvas)
    ):
        layer_seed = seed + k * 7919
        coverage, grain = _dash_spec_stats(dash)
        points = _offset_performed_path(
            path,
            offset,
            closed,
            center,
            wander=_outline_wander_px(offset, canvas),
            wander_period=60.0 * scale,
            seed=layer_seed,
        )
        for piece, weight in _contact_fragments(
            points,
            coverage=coverage,
            grain_px=grain * scale,
            seed=layer_seed,
            closed=closed,
        ):
            group.add(
                element(
                    points=piece,
                    **_outline_attrs(
                        attrs,
                        stroke_width=width,
                        opacity=opacity * weight,
                        stratum=k,
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


    def _emit_layer(
        amount: float, layer_attrs: dict, mark: float, gap: float, k: int
    ) -> None:
        # Each stratum gets its own seed, so its weave and its contact are out of
        # step with the others.
        #
        # engine 28: the dasharray is gone. Its pattern was long, but a pattern
        # still repeats, and this layer is the tool losing the paper's grain --
        # not a dotted line (author's ruling, 2026-08-09). `mark` and `gap` now
        # say what share of the line the tool held and at what wavelength, and
        # the contact field decides where.
        la = _copy_attrs(layer_attrs)
        la["fill"] = "none"
        la["class_"] = f"material-outline stratum-{k}"
        # Same reason as `_outline_attrs`: the tool's own `WEIGHT_STYLE` dash
        # would cut the fragments a second time, on a fixed cadence.
        la.pop("stroke_dasharray", None)
        base_opacity = la.get("stroke_opacity", 1.0)
        off_px = _layer_offset(amount)
        layer_seed = seed + k * 7919
        wander = _outline_wander_px(off_px, canvas)
        pts = _offset_polyline(
            path, off_px, wander=wander, wander_period=60.0 * scale, seed=layer_seed
        )
        for piece, weight in _contact_fragments(
            pts,
            coverage=mark / max(1e-6, mark + gap),
            grain_px=(mark + gap) * scale,
            seed=layer_seed,
            closed=False,
        ):
            frag = _copy_attrs(la)
            frag["stroke_opacity"] = base_opacity * weight
            group.add(dwg.polyline(points=piece, **frag))

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
                _mark_width_px(ins, canvas)
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


def _size_px(size: Sequence[float], canvas: CanvasSize) -> tuple[float, float]:
    """Both extents follow the short edge, so a mark keeps the proportion the
    description gave it: a square stays square, and a 2:1 ellipse stays 2:1 on
    any canvas. The aspect decides where a mark sits, not what shape it is --
    placement still goes through _px, which keeps using width and height.
    """
    return size[0] * canvas.unit, size[1] * canvas.unit


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
    support: Support,
    wild: bool = False,
):
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    base_width = _mark_width_px(ins, canvas)
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
        support=support,
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
            support=support,
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
        _mark_width_px(ins, canvas) * FILL_SPACING_WIDTH_GAIN,
        canvas.unit * FILL_SPACING_UNIT_RATIO,
    )


def _fill_coverage(ins: Instruction, canvas: CanvasSize) -> float:
    """How much of the field one pass of scan lines covers: width over pitch.

    A ratio of two lengths, so it does not move with the canvas: the same
    instruction reaches the same branch on every aspect.
    """
    return _mark_width_px(ins, canvas) / _fill_scan_spacing(
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


def _is_noncomputer_solid_fill(ins: Instruction) -> bool:
    return (
        _fills_interior(ins)
        and ins.surface is not None
        and ins.surface.texture == "solid"
        and not GRAMMARS[ins.weight].periodic
    )


def _render_solid_mottle_fill(
    dwg: svgwrite.Drawing,
    ins: Instruction,
    contour: list[tuple[float, float]],
    attrs: dict,
    mottle_filter_id: str | None,
):
    """A real base fill, with a filter overlay only where the profile permits it."""
    opacity = float(attrs.get("fill_opacity", attrs.get("stroke_opacity", 1.0)))
    color = attrs.get("stroke", "#111111")
    path_d = polygon_path(tuple(contour))
    group = dwg.g(class_="solid-fill-v1")
    group.add(
        dwg.path(
            d=path_d,
            class_="solid-base-fill-v1",
            fill=color,
            fill_opacity=opacity,
            stroke="none",
        )
    )
    if mottle_filter_id is not None:
        group.add(
            dwg.path(
                d=path_d,
                class_="solid-mottle-overlay-v1",
                fill=color,
                fill_opacity=opacity * SOLID_MOTTLE_OVERLAY_OPACITY,
                stroke="none",
                filter=f"url(#{mottle_filter_id})",
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
    support: Support,
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
    base_width = _mark_width_px(ins, canvas)
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
                        support=support,
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
    support: Support,
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
    width = _mark_width_px(ins, canvas)
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
            support=support,
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
    support: Support,
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
        max(_mark_width_px(ins, canvas), short_axis),
        ins.weight,
        _fill_stroke_seed(seed, 0),
        closed=False,
        grid_step=_grid_step_px(ins.weight, canvas),
        wild=wild,
        support=support,
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
    solid_mottle_filter_id: str | None = None,
    support: Support,
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
    if _is_noncomputer_solid_fill(ins):
        return _render_solid_mottle_fill(
            dwg, ins, contour, attrs, solid_mottle_filter_id
        ), False
    if not _uses_hand_stroke(ins.weight):
        return None, True
    if len(contour) < 3:
        return None, True

    if not _fill_is_scannable(ins, contour, canvas, render_seed):
        group = _render_fill_dab(
            dwg, ins, contour, attrs, canvas, render_seed,
            use_filters=use_filters, wild=wild,
            support=support,
        )
        return (None, True) if group is None else (group, False)

    scan_branch = _fill_takes_scan_branch(ins, canvas)
    render_marks = _render_fill_strokes if scan_branch else _render_fill_texture
    marks = render_marks(
        dwg, ins, contour, attrs, canvas, render_seed, use_filters=use_filters,
        wild=wild, support=support,
    )
    if marks is None:
        # Nothing survived the minimum-length filter. Fall through to the dab
        # rather than leaving a bare underlay: an area with no mark on it is the
        # flat fill this engine has been taking apart since 9.
        group = _render_fill_dab(
            dwg, ins, contour, attrs, canvas, render_seed,
            use_filters=use_filters, wild=wild,
            support=support,
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
    support: Support,
    closed: bool = True,
    anchors: frozenset[int] = frozenset(),
    wild: bool = False,
) -> tuple[object, list[tuple[float, float]]]:
    """閉輪郭を一筆のストロークとして合成し、帯 (ring) として描く。

    戻り値の 2 つめは演奏後の中心線。材質層がこれに追随できるように返す
    (幾何から引くと墨だけが動いて材質が取り残される)。
    """
    base_width = _mark_width_px(ins, canvas)
    stroke = synthesize_along(
        contour,
        base_width,
        ins.weight,
        _seed_for_instruction(ins, render_seed),
        closed=closed,
        anchors=anchors,
        grid_step=_grid_step_px(ins.weight, canvas),
        wild=wild,
        support=support,
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
    support: Support,
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
    base_width = _mark_width_px(ins, canvas)
    stroke = synthesize_along(
        centerline,
        base_width,
        ins.weight,
        seed,
        closed=False,
        grid_step=_grid_step_px(ins.weight, canvas),
        wild=wild,
        support=support,
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
        # engine 28: the band's own samples, not the ideal arc. The geometric
        # helper stayed on `r + offset` and was left behind whenever the ink
        # wandered, which is the ghost the author saw beside the mark.
        arc_len = r * abs(math.radians(ins.angle_end) - math.radians(ins.angle_start))
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
    solid_mottle_filter_id: str | None = None,
    support: Support,
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
        if not _is_noncomputer_solid_fill(ins):
            return _apply_rotation(dwg.polygon(points=points, **attrs), ins, canvas)
        fill_group, _ = _interior_fill(
            dwg,
            ins,
            points,
            attrs,
            canvas,
            render_seed,
            use_filters=use_filters,
            solid_mottle_filter_id=solid_mottle_filter_id,
            support=support,
            wild=wild,
        )
        body_attrs = _copy_attrs(attrs)
        body_attrs["fill"] = "none"
        body_attrs.pop("fill_opacity", None)
        group = dwg.g()
        group.add(dwg.polygon(points=points, **body_attrs))
        assert fill_group is not None
        group.add(fill_group)
        return _apply_rotation(group, ins, canvas)
    fill_group, region_fill = _interior_fill(
        dwg,
        ins,
        points,
        attrs,
        canvas,
        render_seed,
        use_filters=use_filters,
        solid_mottle_filter_id=solid_mottle_filter_id,
        wild=wild,
        support=support,
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
        support=support,
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
    solid_mottle_filter_id: str | None = None,
    support: Support,
    render_seed: int | None = None,
    ins_idx: int = 0,
    mark_idx: int = 0,
    wild: bool = False,
):
    canvas = canvas or canvas_size_for_aspect(None)
    # Once, here: every mark of this instruction meets the same sheet, and a
    # word about how the mark runs belongs to this instruction alone.
    support = _instruction_support(ins, support)
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
                support=support,
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
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
        )
        body_attrs = (
            _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
            if hand
            else (
                _body_attrs_for_contour_stroke(attrs, ins, region_fill=True)
                if fill_group is not None
                else attrs
            )
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
                    support=support,
                )
                group.add(contour_group)
            if _uses_material_outline(ins.weight):
                if performed is not None:
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
        size_w, size_h = _size_px(ins.size, canvas)
        rx, ry = size_w / 2, size_h / 2
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
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
        )
        body_attrs = (
            _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
            if hand
            else (
                _body_attrs_for_contour_stroke(attrs, ins, region_fill=True)
                if fill_group is not None
                else attrs
            )
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
                    support=support,
                )
                group.add(contour_group)
            if _uses_material_outline(ins.weight):
                if performed is not None:
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
            _size_px(ins.size, canvas),
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
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
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
                support=support,
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
        w, h = _size_px(ins.size, canvas)
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
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
        )
        body_attrs = (
            _body_attrs_for_contour_stroke(attrs, ins, region_fill=region_fill)
            if hand
            else (
                _body_attrs_for_contour_stroke(attrs, ins, region_fill=True)
                if fill_group is not None
                else attrs
            )
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
                    support=support,
                )
                group.add(contour_group)
            if _uses_material_outline(ins.weight):
                if performed is not None:
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
        w, h = _size_px(ins.size, canvas)
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
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
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
            solid_mottle_filter_id=solid_mottle_filter_id,
            wild=wild,
            support=support,
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
                support=support,
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
