"""Stage 2 出力の構造補修 (coerce layer).

設計原則 — primitive 個別コードを書かない:
  - PRIMITIVE_SPECS テーブルで「どの primitive に何が必要か」を宣言する
  - _coerce_instruction() は汎用ループで補修する
  - 新 primitive 追加 → PRIMITIVE_SPECS にエントリ追記のみ。ここは変えない
  - POST_COERCE で cross-field 制約を追加できる (arc 角度ゼロ補正など)

補修の優先順位:
  1. 型正規化 (coerce 関数で変換)
  2. cross-field fallback (center 欠損時に position を代用など)
  3. FieldSpec.default (上記すべて失敗時)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from .schema import Instruction, Score


# ── 型正規化ヘルパー ──────────────────────────────────────────────────────────────
# 各関数は「変換できなければ None を返す」契約。None → FieldSpec.default が使われる。

def _as_coord(v: Any) -> list[float] | None:
    """任意の値を [x, y] に正規化。"""
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        try:
            return [float(v[0]), float(v[1])]
        except (TypeError, ValueError):
            return None
    if isinstance(v, (int, float)):
        f = float(v)
        return [f, f]
    return None


def _as_positive_float(v: Any) -> float | None:
    """正の float に変換。0以下は None。"""
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _as_positive_size(v: Any) -> list[float] | None:
    """[w, h] に変換。いずれかが 0以下なら None。"""
    c = _as_coord(v)
    if c is None:
        return None
    return c if (c[0] > 0 and c[1] > 0) else None


def _as_float(v: Any) -> float | None:
    """float に変換 (0を含む有効値)。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── フィールド補修仕様 ──────────────────────────────────────────────────────────

@dataclass
class FieldSpec:
    """1フィールドの補修ルール。

    name:      対象フィールド名 (JSON by_alias)
    default:   欠損・不正値のときに使うデフォルト
    fallbacks: name が欠損時、代替として試みるフィールド名リスト (cross-field)
    coerce:    値の型検証・正規化関数。None を返すと default にフォールバック
    """

    name: str
    default: Any
    fallbacks: list[str] = dc_field(default_factory=list)
    coerce: Callable[[Any], Any] | None = None


# primitive → 必須フィールドの補修仕様テーブル
# 新 primitive を追加するときはここにエントリを追記するだけ
PRIMITIVE_SPECS: dict[str, list[FieldSpec]] = {
    "line": [
        FieldSpec("from",   [0.1, 0.5], coerce=_as_coord),
        FieldSpec("to",     [0.9, 0.5], coerce=_as_coord),
    ],
    "circle": [
        FieldSpec("center", [0.5, 0.5], fallbacks=["position"], coerce=_as_coord),
        FieldSpec("radius", 0.15,                               coerce=_as_positive_float),
    ],
    "ellipse": [
        FieldSpec("center", [0.5, 0.5], fallbacks=["position"], coerce=_as_coord),
        FieldSpec("size",   [0.3, 0.3],                          coerce=_as_positive_size),
    ],
    "arc": [
        FieldSpec("center",      [0.5, 0.5], fallbacks=["position"], coerce=_as_coord),
        FieldSpec("radius",      0.15,                               coerce=_as_positive_float),
        FieldSpec("angle_start", 0.0,                                coerce=_as_float),
        FieldSpec("angle_end",   270.0,                              coerce=_as_float),
    ],
    "square": [
        FieldSpec("position", [0.35, 0.35], fallbacks=["center"], coerce=_as_coord),
        FieldSpec("size",     [0.3, 0.3],                          coerce=_as_positive_size),
    ],
    "triangle": [
        FieldSpec("position", [0.35, 0.35], fallbacks=["center"], coerce=_as_coord),
        FieldSpec("size",     [0.3, 0.3],                          coerce=_as_positive_size),
    ],
}


# ── cross-field 制約補正 ──────────────────────────────────────────────────────────
# フィールド間依存がある制約のみここに書く。

def _fix_arc_angles(data: dict) -> None:
    """arc: angle_start == angle_end → 270° 広げる。"""
    if abs(data.get("angle_start", 0) - data.get("angle_end", 0)) < 1e-6:
        data["angle_end"] = (data.get("angle_start", 0) + 270.0) % 360.0


POST_COERCE: dict[str, Callable[[dict], None]] = {
    "arc": _fix_arc_angles,
}


VISIBLE_ON_BACKGROUND: dict[str, str] = {
    "white": "black",
    "black": "white",
    "gray": "black",
    "blue": "white",
    "red": "white",
    "green": "white",
}

MATERIAL_WEIGHT_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ロットリング", "rotring"), "rotring"),
    (("鉛筆", "pencil"), "pencil"),
    (("クレヨン", "crayon"), "crayon"),
    (("チョーク", "chalk"), "chalk"),
    (("細筆", "fine-brush", "fine brush"), "brush_thin"),
    (("太筆", "thick-brush", "thick brush", "厚塗り", "油絵"), "brush_thick"),
    (("水墨", "墨", "ink-wash", "ink wash"), "brush_thin"),
    (("縄", "ロープ", "rope"), "rope"),
)

MAX_EXPANDED_PRIMITIVES = 400
MAX_EXPANDED_PER_INSTRUCTION = 240
MAX_VISUAL_CLUSTERED_COUNT = 120

COLOR_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("白", "white"), "white"),
    (("黒", "black"), "black"),
    (("青", "blue"), "blue"),
    (("赤", "red"), "red"),
    (
        (
            "緑",
            "green",
            "森",
            "forest",
            "leaf",
            "草",
            "grass",
            "苔",
            "moss",
            "竹",
            "bamboo",
            "庭",
            "garden",
            "香り",
            "scent",
            "fragrance",
            "芽",
            "落ち葉",
            "若葉",
            "木の葉",
            "葉っぱ",
            "葉脈",
        ),
        "green",
    ),
    (("灰", "gray", "grey"), "gray"),
)

SHAPE_INTENT_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("山", "屋根", "尖", "鋭", "三角", "峰", "頂", "稜線", "切妻", "mountain", "roof", "sharp", "peak", "ridge", "triangle"), "triangle"),
    (("弧", "渦", "螺旋", "波紋", "巻", "arc", "spiral", "coil", "curl", "ripple"), "arc"),
    (("紙片", "破片", "折", "畳", "四角", "paper", "fragment", "fold", "shard", "square"), "square"),
)

MOTIF_INTENT_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("落ち葉", "若葉", "木の葉", "葉っぱ", "葉脈", "leaf", "leaves"), "leaf_cluster"),
    (("紙片", "破片", "折", "手紙", "paper", "fragment", "shard", "letter"), "paper_shard"),
    (("波紋", "渦", "螺旋", "巻", "ripple", "spiral", "coil"), "ripple_knot"),
    (("山", "屋根", "峰", "稜線", "切妻", "mountain", "roof", "ridge", "peak"), "mountain_sign"),
)


def _visible_background(background: str) -> str:
    if background == "gray":
        return "white"
    return background


def _shape_extent(ins: Instruction) -> float:
    if ins.primitive in ("circle", "arc"):
        return float(ins.radius or 0.0) * 2
    if ins.size:
        return max(float(ins.size[0]), float(ins.size[1]))
    if ins.from_ and ins.to:
        return max(abs(ins.from_[0] - ins.to[0]), abs(ins.from_[1] - ins.to[1]))
    return 0.0


def _is_tiny_unfilled_particle(ins: Instruction) -> bool:
    if ins.primitive not in ("circle", "ellipse", "square", "triangle"):
        return False
    if ins.filled:
        return False
    if not ins.arrangement or ins.arrangement.count < 40:
        return False
    return _shape_extent(ins) <= 0.012


def _with_visible_color(ins: Instruction, background: str) -> Instruction:
    if ins.color != background:
        return ins
    data = ins.model_dump(by_alias=True)
    hint = data.get("color_hint")
    norm_hint = (hint or "").lower()
    sensory_markers = (
        "soft light",
        "five-sense",
        "scent",
        "fragrance",
        "membrane",
        "haze",
        "atmosphere",
        "透明な膜",
        "柔らかな光",
        "五感",
        "香り",
        "匂",
        "気配",
    )
    is_sensory = any(marker in norm_hint or marker in (hint or "") for marker in sensory_markers)
    if is_sensory and background == "white":
        if any(marker in norm_hint or marker in (hint or "") for marker in ("scent", "fragrance", "香り", "匂")):
            data["color"] = "green"
            note = "white sensory layer made visible as pale green"
        else:
            data["color"] = "blue"
            note = "white sensory layer made visible as pale blue"
    else:
        data["color"] = VISIBLE_ON_BACKGROUND.get(background, "black")
        note = f"{background} foreground made visible"
    data["color_hint"] = f"{hint}; {note}" if hint else note
    return Instruction.model_validate(data)


def _with_visible_particle(ins: Instruction) -> Instruction:
    if not _is_tiny_unfilled_particle(ins):
        return ins
    data = ins.model_dump(by_alias=True)
    data["filled"] = True
    if ins.primitive == "circle":
        data["radius"] = max(float(ins.radius or 0.0), 0.006)
    elif ins.size:
        data["size"] = [max(float(ins.size[0]), 0.008), max(float(ins.size[1]), 0.008)]
    return Instruction.model_validate(data)


def _with_density_budget(ins: Instruction) -> Instruction:
    arr = ins.arrangement
    if arr is None or arr.layout != "scatter" or arr.count <= 240:
        return ins
    if _shape_extent(ins) > 0.018:
        return ins
    return _with_clustered_density(ins, "scatter density clustered to preserve negative space")


def _with_material_hint(ins: Instruction, ddl: str | None) -> Instruction:
    if not ddl or ins.weight != "pen":
        return ins
    lower = ddl.lower()
    for markers, weight in MATERIAL_WEIGHT_HINTS:
        if any(marker.lower() in lower for marker in markers):
            data = ins.model_dump(by_alias=True)
            data["weight"] = weight
            hint = data.get("color_hint")
            note = f"material inferred from DDL: {weight}"
            data["color_hint"] = f"{hint}; {note}" if hint else note
            return Instruction.model_validate(data)
    return ins


def _with_variation_hint(ins: Instruction, ddl: str | None) -> Instruction:
    if not ddl or ins.variation is not None:
        return ins
    lower = ddl.lower()
    variation: dict[str, object] | None = None
    if any(marker in ddl for marker in ("ゆっくり揺れる", "ゆっくり波打つ")) or "slow" in lower:
        variation = {
            "amplitude": "medium",
            "frequency": "slow",
            "quality": "wave",
            "dimensions": ["position_x", "position_y"],
        }
    elif any(marker in ddl for marker in ("細かく揺れる", "細かく震える", "震える")) or "trembling" in lower:
        variation = {
            "amplitude": "fine",
            "frequency": "medium",
            "quality": "perlin",
            "dimensions": ["position_y"] if ins.primitive == "line" else ["position_x", "position_y"],
        }
    elif any(marker in ddl for marker in ("滲む", "にじむ", "境界が滲む")) or "blurring" in lower:
        variation = {
            "amplitude": "medium",
            "frequency": "medium",
            "quality": "pink",
            "dimensions": ["position_x", "position_y"],
        }
    if variation is None:
        return ins
    data = ins.model_dump(by_alias=True)
    data["variation"] = variation
    return Instruction.model_validate(data)


def _dedupe_instructions(instructions: list[Instruction]) -> list[Instruction]:
    deduped: list[Instruction] = []
    seen: set[str] = set()
    for ins in instructions:
        key = json.dumps(ins.model_dump(by_alias=True, exclude_none=True), sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ins)
    return deduped


def _expanded_count(ins: Instruction) -> int:
    if ins.arrangement is None:
        return 1
    return max(1, int(ins.arrangement.count))


def _with_arrangement_count(ins: Instruction, count: int, note: str) -> Instruction:
    if ins.arrangement is None or ins.arrangement.count == count:
        return ins
    data = ins.model_dump(by_alias=True)
    arrangement = dict(data["arrangement"])
    arrangement["count"] = max(1, int(count))
    data["arrangement"] = arrangement
    hint = data.get("color_hint")
    data["color_hint"] = f"{hint}; {note}" if hint else note
    return Instruction.model_validate(data)


def _density_label(original_count: int) -> str:
    if original_count >= 180:
        return "high"
    if original_count >= 80:
        return "medium"
    return "low"


def _cluster_count(original_count: int) -> int:
    if original_count >= 500:
        return 9
    if original_count >= 240:
        return 7
    if original_count >= 120:
        return 5
    return 3


def _clustered_visual_count(original_count: int) -> int:
    if original_count <= MAX_VISUAL_CLUSTERED_COUNT:
        return original_count
    return min(MAX_VISUAL_CLUSTERED_COUNT, max(48, int(original_count * 0.42)))


def _with_clustered_density(ins: Instruction, note: str) -> Instruction:
    arr = ins.arrangement
    if arr is None:
        return ins
    original_count = arr.count
    data = ins.model_dump(by_alias=True)
    arr_data = dict(data["arrangement"])
    arr_data["count"] = _clustered_visual_count(original_count)
    existing_density = arr_data.get("density", "none")
    arr_data["density"] = existing_density if existing_density != "none" else _density_label(original_count)
    arr_data["cluster_count"] = arr_data.get("cluster_count") or _cluster_count(original_count)
    arr_data["preserve_space"] = True
    arr_data["margin"] = max(float(arr_data.get("margin") or 0.1), 0.18)
    if arr_data.get("fade", "none") == "none":
        arr_data["fade"] = "directional" if arr.path != "none" or arr.layout in ("horizontal", "vertical") else "outward"
    data["arrangement"] = arr_data
    hint = data.get("color_hint")
    full_note = f"{note}; original count {original_count}"
    data["color_hint"] = f"{hint}; {full_note}" if hint else full_note
    return Instruction.model_validate(data)


def _with_per_instruction_density_budget(instructions: list[Instruction]) -> list[Instruction]:
    adjusted: list[Instruction] = []
    for ins in instructions:
        if ins.arrangement is None or ins.arrangement.count <= MAX_EXPANDED_PER_INSTRUCTION:
            adjusted.append(ins)
            continue
        adjusted.append(_with_clustered_density(ins, "single arrangement density clustered to preserve negative space"))
    return adjusted


def _with_total_density_budget(instructions: list[Instruction]) -> list[Instruction]:
    total = sum(_expanded_count(ins) for ins in instructions)
    if total <= MAX_EXPANDED_PRIMITIVES:
        return instructions

    remaining_budget = MAX_EXPANDED_PRIMITIVES
    remaining = list(instructions)
    adjusted: list[Instruction] = []
    for index, ins in enumerate(remaining):
        count = _expanded_count(ins)
        rest_minimum = len(remaining) - index - 1
        if ins.arrangement is None:
            adjusted.append(ins)
            remaining_budget -= 1
            continue
        if remaining_budget <= rest_minimum + 1:
            allowed = 1
        else:
            remaining_total = sum(_expanded_count(item) for item in remaining[index:])
            share = count / remaining_total if remaining_total > 0 else 0
            allowed = max(1, int((remaining_budget - rest_minimum) * share))
        if allowed < count and count > 80:
            adjusted_ins = _with_clustered_density(ins, "expanded density clustered to preserve negative space")
            if _expanded_count(adjusted_ins) > allowed:
                adjusted_ins = _with_arrangement_count(adjusted_ins, allowed, "expanded density capped after clustering")
        else:
            adjusted_ins = _with_arrangement_count(ins, allowed, "expanded density capped to preserve negative space")
        adjusted.append(adjusted_ins)
        remaining_budget -= _expanded_count(adjusted_ins)
    return adjusted


def _requested_colors_from_ddl(ddl: str | None) -> set[str]:
    if not ddl:
        return set()
    lower = ddl.lower()
    colors: set[str] = set()
    for markers, color in COLOR_MARKERS:
        if any(marker.lower() in lower or marker in ddl for marker in markers):
            colors.add(color)
    return colors


def _score_contains_color(instructions: list[Instruction], color: str) -> bool:
    for ins in instructions:
        if ins.color == color:
            return True
        arr = ins.arrangement
        if arr and color in arr.color_cycle:
            return True
    return False


def _color_repair_order(colors: set[str]) -> list[str]:
    ordered = [color for color in ("red", "blue", "green", "white", "black", "gray") if color in colors]
    return ordered or sorted(colors)


def _green_intent_context(ddl: str | None) -> str | None:
    if not ddl:
        return None
    lower = ddl.lower()
    if "竹" in ddl or "bamboo" in lower:
        return "bamboo green kept as primary contour"
    if any(marker in ddl for marker in ("枯れ草", "枯草", "枯れた草", "枯葉")) or "withered grass" in lower or "dry grass" in lower:
        return "withered grass kept as muted green-gray"
    if ("森" in ddl or "forest" in lower) and any(marker in ddl for marker in ("落ち葉", "紅葉", "秋")):
        return "forest green kept as quiet residue behind warm leaves"
    return None


def _with_color_cycle_delivery(ins: Instruction, colors: list[str], *, ddl: str | None = None) -> Instruction:
    data = ins.model_dump(by_alias=True)
    arr_data = dict(data.get("arrangement") or {})
    cycle: list[str] = []
    existing_cycle = arr_data.get("color_cycle")
    if isinstance(existing_cycle, list):
        cycle.extend(str(color) for color in existing_cycle)
    base_color = data.get("color")
    green_context = _green_intent_context(ddl) if "green" in colors else None
    if green_context and "bamboo" in green_context:
        data["color"] = "green"
        base_color = "green"
    if isinstance(base_color, str):
        cycle.insert(0, base_color)
    if green_context and "withered" in green_context and "gray" not in cycle:
        cycle.insert(0, "gray")
    for color in colors:
        if color not in cycle:
            cycle.append(color)
    if not cycle:
        return ins
    if "count" not in arr_data:
        arr_data["count"] = max(2, len(cycle))
        arr_data["layout"] = arr_data.get("layout") or "scatter"
        arr_data["margin"] = max(float(arr_data.get("margin") or 0.1), 0.16)
    arr_data["color_cycle"] = cycle
    data["arrangement"] = arr_data
    hint = data.get("color_hint")
    note = f"{'/'.join(colors)} restored in color_cycle from DDL color intent"
    if green_context:
        note = f"{note}; {green_context}"
    data["color_hint"] = f"{hint}; {note}" if hint else note
    return Instruction.model_validate(data)


def _with_color_delivery_repair(instructions: list[Instruction], *, ddl: str | None) -> list[Instruction]:
    requested = _requested_colors_from_ddl(ddl)
    if not requested:
        return instructions

    repaired = list(instructions)
    missing = {color for color in requested if not _score_contains_color(repaired, color)}
    if not missing:
        return repaired

    candidate_index = next(
        (
            index for index, ins in enumerate(repaired)
            if ins.primitive in ("ellipse", "arc", "circle", "square", "triangle")
        ),
        0 if repaired else -1,
    )
    if candidate_index < 0:
        return repaired
    repaired[candidate_index] = _with_color_cycle_delivery(repaired[candidate_index], _color_repair_order(missing), ddl=ddl)
    return repaired


def _requested_shapes_from_ddl(ddl: str | None) -> set[str]:
    if not ddl:
        return set()
    lower = ddl.lower()
    shapes: set[str] = set()
    for markers, primitive in SHAPE_INTENT_MARKERS:
        if any(marker.lower() in lower or marker in ddl for marker in markers):
            shapes.add(primitive)
    return shapes


def _score_contains_primitive(instructions: list[Instruction], primitive: str) -> bool:
    return any(ins.primitive == primitive for ins in instructions)


def _shape_repair_instruction(primitive: str, *, index: int, background: str) -> Instruction:
    color = VISIBLE_ON_BACKGROUND.get(background, "black")
    offset = min(index, 3) * 0.08
    common: dict[str, Any] = {
        "primitive": primitive,
        "color": color,
        "weight": "brush_thin",
        "color_hint": f"{primitive} restored from DDL shape intent",
    }
    if primitive == "triangle":
        common.update({
            "position": [0.58 - offset, 0.22 + offset],
            "size": [0.18, 0.16],
            "rotation": -18 + index * 11,
        })
    elif primitive == "arc":
        common.update({
            "center": [0.66 - offset, 0.34 + offset],
            "radius": 0.13,
            "angle_start": 205,
            "angle_end": 25,
            "rotation": -10 + index * 9,
        })
    else:
        common.update({
            "position": [0.56 - offset, 0.30 + offset],
            "size": [0.16, 0.11],
            "rotation": -25 + index * 13,
        })
    return Instruction.model_validate(common)


def _with_shape_delivery_repair(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
) -> list[Instruction]:
    requested = _requested_shapes_from_ddl(ddl)
    if not requested:
        return instructions

    repaired = list(instructions)
    for primitive in ("triangle", "arc", "square"):
        if primitive not in requested or _score_contains_primitive(repaired, primitive):
            continue
        limit = 8 if primitive == "triangle" else 6
        if len(repaired) >= limit:
            if primitive == "triangle":
                replace_index = next(
                    (
                        index for index, ins in enumerate(repaired)
                        if ins.primitive in ("line", "ellipse", "square") and ins.arrangement is None
                    ),
                    -1,
                )
                if replace_index >= 0:
                    repaired[replace_index] = _shape_repair_instruction(
                        primitive,
                        index=replace_index,
                        background=background,
                    )
                    continue
            break
        repaired.append(_shape_repair_instruction(primitive, index=len(repaired), background=background))
    return repaired


def _requested_motifs_from_ddl(ddl: str | None) -> list[str]:
    if not ddl:
        return []
    lower = ddl.lower()
    motifs: list[str] = []
    for markers, motif in MOTIF_INTENT_MARKERS:
        if any(marker.lower() in lower or marker in ddl for marker in markers):
            motifs.append(motif)
    return motifs


def _score_contains_motif(instructions: list[Instruction], motif: str) -> bool:
    return any(motif in (ins.color_hint or "") for ins in instructions)


def _composition_repair_suppressed(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    return any(
        marker in ddl or marker in lower
        for marker in (
            "余白",
            "静か",
            "薄い",
            "一つ",
            "ひとつ",
            "だけ",
            "少しだけ",
            "quiet",
            "minimal",
            "single",
            "only",
            "negative space",
        )
    )


def _score_colors_with_cycles(instructions: list[Instruction]) -> set[str]:
    colors: set[str] = set()
    for ins in instructions:
        colors.add(ins.color)
        if ins.arrangement:
            colors.update(ins.arrangement.color_cycle)
    return colors


def _has_visible_anchor(instructions: list[Instruction]) -> bool:
    for ins in instructions:
        if ins.primitive == "line":
            continue
        if 0.08 <= _shape_extent(ins) <= 0.42:
            return True
    return False


def _composition_accent_color(ddl: str | None, instructions: list[Instruction], background: str) -> str | None:
    existing = _score_colors_with_cycles(instructions)
    requested = [color for color in _color_repair_order(_requested_colors_from_ddl(ddl)) if color not in existing and color != background]
    if requested:
        return requested[0]
    if existing and not existing <= {"black", "gray"}:
        return None
    lower = (ddl or "").lower()
    if any(marker in (ddl or "") or marker in lower for marker in ("祭", "火", "灯", "温", "赤", "warm", "fire", "light")):
        return "red" if background != "red" else "white"
    if any(marker in (ddl or "") or marker in lower for marker in ("水", "夜", "湖", "冷", "青", "water", "night", "cold")):
        return "blue" if background != "blue" else "white"
    if any(marker in (ddl or "") or marker in lower for marker in ("森", "草", "苔", "庭", "竹", "green", "forest", "grass")):
        return "green" if background != "green" else "white"
    return None


def _composition_anchor_instruction(*, color: str, background: str) -> Instruction:
    visible = color if color != background else VISIBLE_ON_BACKGROUND.get(background, "black")
    return Instruction.model_validate({
        "primitive": "ellipse",
        "center": [0.64, 0.40],
        "size": [0.18, 0.11],
        "rotation": -18,
        "color": visible,
        "weight": "brush_thick",
        "color_hint": "composition anchor restored for shape/color diversity",
    })


def _composition_accent_instruction(*, color: str, background: str) -> Instruction:
    visible = color if color != background else VISIBLE_ON_BACKGROUND.get(background, "black")
    return Instruction.model_validate({
        "primitive": "arc",
        "center": [0.36, 0.62],
        "radius": 0.09,
        "angle_start": 18,
        "angle_end": 205,
        "rotation": 8,
        "color": visible,
        "weight": "brush_thin",
        "color_hint": "composition accent restored for shape/color diversity",
    })


def _with_composition_diversity_repair(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
) -> list[Instruction]:
    if not ddl or _composition_repair_suppressed(ddl) or len(instructions) >= 10:
        return instructions

    repaired = list(instructions)
    primitives = {ins.primitive for ins in repaired}
    colors = _score_colors_with_cycles(repaired)
    accent_color = _composition_accent_color(ddl, repaired, background)
    needs_anchor = bool(repaired) and not _has_visible_anchor(repaired) and (primitives == {"line"} or len(primitives) == 1)
    needs_accent = accent_color is not None and accent_color not in colors

    if needs_anchor:
        repaired.append(_composition_anchor_instruction(
            color=accent_color or VISIBLE_ON_BACKGROUND.get(background, "black"),
            background=background,
        ))
        colors = _score_colors_with_cycles(repaired)

    if needs_accent and accent_color not in colors and len(repaired) < 10:
        repaired.append(_composition_accent_instruction(color=accent_color, background=background))

    return repaired


def _motif_repair_instructions(motif: str, *, index: int, background: str) -> list[Instruction]:
    color = VISIBLE_ON_BACKGROUND.get(background, "black")
    offset = min(index, 2) * 0.08
    if motif == "leaf_cluster":
        return [
            Instruction.model_validate({
                "primitive": "ellipse",
                "center": [0.38 + offset, 0.44],
                "size": [0.13, 0.035],
                "rotation": -28,
                "color": "green" if background != "green" else "white",
                "color_hint": "leaf_cluster motif restored from DDL intent",
            }),
            Instruction.model_validate({
                "primitive": "arc",
                "center": [0.40 + offset, 0.44],
                "radius": 0.08,
                "angle_start": 200,
                "angle_end": 335,
                "rotation": -24,
                "color": color,
                "weight": "brush_thin",
                "color_hint": "leaf_cluster motif restored from DDL intent",
            }),
        ]
    if motif == "paper_shard":
        return [
            Instruction.model_validate({
                "primitive": "square",
                "position": [0.56 - offset, 0.36 + offset],
                "size": [0.13, 0.09],
                "rotation": -24,
                "color": color,
                "color_hint": "paper_shard motif restored from DDL intent",
            }),
            Instruction.model_validate({
                "primitive": "line",
                "from": [0.55 - offset, 0.43 + offset],
                "to": [0.70 - offset, 0.37 + offset],
                "color": color,
                "weight": "hair",
                "color_hint": "paper_shard motif restored from DDL intent",
            }),
        ]
    if motif == "ripple_knot":
        return [
            Instruction.model_validate({
                "primitive": "arc",
                "center": [0.62 - offset, 0.58],
                "radius": 0.10,
                "angle_start": 25,
                "angle_end": 210,
                "color": "blue" if background != "blue" else "white",
                "color_hint": "ripple_knot motif restored from DDL intent",
            }),
            Instruction.model_validate({
                "primitive": "ellipse",
                "center": [0.62 - offset, 0.58],
                "size": [0.055, 0.025],
                "rotation": 18,
                "color": color,
                "color_hint": "ripple_knot motif restored from DDL intent",
            }),
        ]
    return [
        Instruction.model_validate({
            "primitive": "triangle",
            "position": [0.50 - offset, 0.27 + offset],
            "size": [0.18, 0.15],
            "rotation": -12,
            "color": color,
            "color_hint": "mountain_sign motif restored from DDL intent",
        }),
        Instruction.model_validate({
            "primitive": "line",
            "from": [0.59 - offset, 0.25 + offset],
            "to": [0.59 - offset, 0.45 + offset],
            "color": color,
            "weight": "hair",
            "color_hint": "mountain_sign motif restored from DDL intent",
        }),
    ]


def _with_complex_motif_repair(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
) -> list[Instruction]:
    motifs = _requested_motifs_from_ddl(ddl)
    if not motifs:
        return instructions
    repaired = list(instructions)
    added = 0
    for motif in motifs:
        if added >= 2 or _score_contains_motif(repaired, motif):
            continue
        motif_instructions = _motif_repair_instructions(motif, index=added, background=background)
        if len(repaired) + len(motif_instructions) > 10:
            continue
        repaired.extend(motif_instructions)
        added += 1
    return repaired


def _ddl_clauses(ddl: str | None) -> list[str]:
    if not ddl:
        return []
    clauses = [part.strip() for part in re.split(r"[。\n;；]+", ddl) if part.strip()]
    markers = (
        "線", "点", "円", "楕円", "四角", "三角", "弧", "塗りつぶす", "散らす", "並べる",
        "膜", "霞", "霧", "靄", "気配", "余韻", "反射", "映り", "消え", "滲",
        "光", "陽光", "日差し", "香", "匂", "蕾", "つぼみ", "開花", "五感", "温",
        "line", "dot", "circle", "ellipse", "square", "triangle", "arc", "scatter", "fill",
        "membrane", "haze", "fog", "mist", "trace", "reflection", "fade", "fading", "blur",
        "light", "sunlight", "scent", "fragrance", "bud", "bloom", "sense", "warm",
    )
    return [
        clause
        for clause in clauses
        if not (clause.startswith("背景") or clause.lower().startswith("background"))
        and any(marker in clause for marker in markers)
    ]


def _color_from_clause(clause: str, background: str) -> str:
    lower = clause.lower()
    for markers, color in COLOR_MARKERS:
        if any(marker in clause or marker in lower for marker in markers):
            if color != background:
                return color
    return VISIBLE_ON_BACKGROUND.get(background, "black")


def _color_cycle_from_clause(clause: str, background: str) -> list[str]:
    lower = clause.lower()
    colors: list[str] = []
    for markers, color in COLOR_MARKERS:
        if color == background:
            continue
        if any(marker in clause or marker in lower for marker in markers):
            colors.append(color)
    if ("色とりどり" in clause or "多色" in clause or "colorful" in lower or "multi-color" in lower) and len(colors) < 3:
        colors.extend(color for color in ("red", "blue", "green", "black", "gray") if color != background)
    deduped: list[str] = []
    for color in colors:
        if color not in deduped:
            deduped.append(color)
    return deduped


def _weight_from_clause(clause: str) -> str:
    lower = clause.lower()
    for markers, weight in MATERIAL_WEIGHT_HINTS:
        if any(marker.lower() in lower for marker in markers):
            return weight
    return "pen"


def _primitive_from_clause(clause: str) -> str:
    lower = clause.lower()
    if ("四角" in clause) or ("square" in lower) or ("rectangle" in lower):
        return "square"
    if ("三角" in clause) or ("triangle" in lower):
        return "triangle"
    if ("弧" in clause) or ("arc" in lower):
        return "arc"
    if ("円" in clause) or ("楕円" in clause) or ("circle" in lower) or ("ellipse" in lower):
        return "ellipse"
    return "line"


def _is_atmospheric_clause(clause: str) -> bool:
    lower = clause.lower()
    return any(
        marker in clause or marker in lower
        for marker in ("膜", "霞", "霧", "靄", "気配", "余韻", "透明", "membrane", "haze", "fog", "mist", "atmosphere")
    )


def _is_reflection_clause(clause: str) -> bool:
    lower = clause.lower()
    return any(marker in clause or marker in lower for marker in ("反射", "映り", "reflection", "reflected"))


def _is_fading_clause(clause: str) -> bool:
    lower = clause.lower()
    return any(marker in clause or marker in lower for marker in ("消え", "薄れ", "fade", "fading", "vanish", "dissolve"))


def _sensory_kind(clause: str) -> str | None:
    lower = clause.lower()
    if any(marker in clause or marker in lower for marker in ("光", "陽光", "日差し", "柔ら", "light", "sunlight", "soft")):
        return "light"
    if any(marker in clause or marker in lower for marker in ("香", "匂", "沈丁花", "scent", "fragrance")):
        return "scent"
    if any(marker in clause or marker in lower for marker in ("蕾", "つぼみ", "開花", "bud", "bloom")):
        return "bud"
    if any(marker in clause or marker in lower for marker in ("五感", "気配", "訪れ", "sense", "presence", "arrival")):
        return "sense"
    return None


def _fallback_instruction_from_clause(clause: str, *, index: int, background: str) -> Instruction:
    primitive = _primitive_from_clause(clause)
    sensory_kind = _sensory_kind(clause)
    if sensory_kind == "sense":
        primitive = "arc"
    elif sensory_kind:
        primitive = "ellipse"
    elif _is_atmospheric_clause(clause):
        primitive = "ellipse"
    elif _is_reflection_clause(clause):
        primitive = "line"
    color = _color_from_clause(clause, background)
    weight = _weight_from_clause(clause)
    if (sensory_kind or _is_atmospheric_clause(clause)) and weight == "pen":
        weight = "chalk"
    common: dict[str, Any] = {
        "primitive": primitive,
        "color": color,
        "weight": weight,
        "color_hint": f"coverage from DDL clause: {clause[:48]}",
    }
    offset = min(index, 4) * 0.09
    if primitive == "line":
        common.update({"from": [0.16 + offset, 0.76 - offset], "to": [0.78, 0.30 + offset], "rotation": -8 + index * 7})
    elif primitive == "arc":
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "radius": 0.11, "angle_start": 210, "angle_end": 330})
    elif primitive == "ellipse":
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "size": [0.16, 0.09], "rotation": -18 + index * 9})
    else:
        common.update({"position": [0.58 - offset / 2, 0.24 + offset], "size": [0.14, 0.10], "rotation": -12 + index * 8})

    count = count_hint_from_ddl(clause)
    lower = clause.lower()
    cycle = _color_cycle_from_clause(clause, background)
    if count and (("散らす" in clause) or ("scatter" in lower)):
        common["arrangement"] = {"count": min(count, 120), "layout": "scatter", "margin": 0.18}
    elif count and (("並べる" in clause) or ("line up" in lower)):
        common["arrangement"] = {"count": min(count, 80), "layout": "horizontal", "margin": 0.1}
    elif sensory_kind == "light":
        common.update(
            {
                "filled": True,
                "center": [0.50, 0.22 + min(index, 2) * 0.04],
                "size": [0.42, 0.12],
                "rotation": -6 + index * 4,
                "color": "white" if background != "white" else "blue",
                "arrangement": {
                    "count": 3,
                    "layout": "horizontal",
                    "margin": 0.24,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                },
                "color_hint": f"{common['color_hint']}; soft light",
            }
        )
    elif sensory_kind == "scent":
        common.update(
            {
                "center": [0.56, 0.54],
                "size": [0.05, 0.024],
                "rotation": -18,
                "color": "green" if background != "green" else "white",
                "arrangement": {
                    "count": 7,
                    "layout": "scatter",
                    "path": "wave",
                    "margin": 0.24,
                    "density": "low",
                    "fade": "directional",
                    "preserve_space": True,
                },
                "color_hint": f"{common['color_hint']}; scent layer",
            }
        )
    elif sensory_kind == "bud":
        common.update(
            {
                "center": [0.70, 0.62],
                "size": [0.055, 0.026],
                "rotation": -30,
                "color": "red" if background != "red" else "white",
                "arrangement": {
                    "count": 5,
                    "layout": "scatter",
                    "path": "diagonal",
                    "margin": 0.18,
                },
                "color_hint": f"{common['color_hint']}; waiting buds",
            }
        )
    elif sensory_kind == "sense":
        common.update(
            {
                "center": [0.34, 0.70],
                "radius": 0.14,
                "angle_start": 205,
                "angle_end": 335,
                "color": "white" if background != "white" else "blue",
                "arrangement": {
                    "count": 3,
                    "layout": "radial",
                    "margin": 0.22,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                },
                "color_hint": f"{common['color_hint']}; five-sense presence",
            }
        )
    elif _is_atmospheric_clause(clause):
        common["arrangement"] = {
            "count": 5,
            "layout": "scatter",
            "margin": 0.24,
            "density": "low",
            "cluster_count": 3,
            "fade": "outward",
            "preserve_space": True,
        }
        common["filled"] = True
        common["color_hint"] = f"{common['color_hint']}; membrane haze"
    elif _is_reflection_clause(clause):
        common["arrangement"] = {
            "count": 9,
            "layout": "vertical",
            "path": "wave",
            "margin": 0.18,
            "density": "low",
            "fade": "directional",
            "preserve_space": True,
        }
        common["color_hint"] = f"{common['color_hint']}; reflection"
    elif _is_fading_clause(clause):
        common["arrangement"] = {
            "count": 7,
            "layout": "scatter",
            "path": "diagonal",
            "margin": 0.24,
            "density": "low",
            "fade": "directional",
            "preserve_space": True,
        }
        common["color_hint"] = f"{common['color_hint']}; fading"
    if cycle:
        arrangement = dict(common.get("arrangement") or {"count": max(len(cycle), 3), "layout": "scatter", "margin": 0.18})
        arrangement["color_cycle"] = cycle
        common["arrangement"] = arrangement
    return Instruction.model_validate(common)


def _with_ddl_coverage(instructions: list[Instruction], *, ddl: str | None, background: str) -> list[Instruction]:
    clauses = _ddl_clauses(ddl)
    if len(instructions) != 1 or len(clauses) <= 1:
        return instructions
    existing = {
        (
            ins.primitive,
            ins.color,
            ins.weight,
        )
        for ins in instructions
    }
    augmented = list(instructions)
    for clause in clauses:
        if len(augmented) >= 5:
            break
        fallback = _fallback_instruction_from_clause(clause, index=len(augmented), background=background)
        key = (fallback.primitive, fallback.color, fallback.weight)
        if key in existing:
            continue
        augmented.append(fallback)
        existing.add(key)
    return augmented


_KANJI_NUMBERS: dict[str, int] = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "百": 100,
}


def _parse_small_japanese_number(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "百":
        return 100
    if text.endswith("百") and len(text) == 2:
        return _KANJI_NUMBERS.get(text[0], 1) * 100
    if "百" in text:
        head, tail = text.split("百", 1)
        value = (_KANJI_NUMBERS.get(head, 1) if head else 1) * 100
        rest = _parse_small_japanese_number(tail)
        return value + (rest or 0)
    if text == "十":
        return 10
    if text.endswith("十") and len(text) == 2:
        return _KANJI_NUMBERS.get(text[0], 1) * 10
    if "十" in text:
        head, tail = text.split("十", 1)
        value = (_KANJI_NUMBERS.get(head, 1) if head else 1) * 10
        return value + (_KANJI_NUMBERS.get(tail, 0) if tail else 0)
    if len(text) == 1:
        return _KANJI_NUMBERS.get(text)
    return None


def count_hint_from_ddl(ddl: str) -> int | None:
    """Extract a conservative count hint from a normalized DDL fragment."""
    match = re.search(r"(\d{1,4}|[一二三四五六七八九十百]{1,8})(?:本|個|つ|点|枚)", ddl)
    if not match:
        return None
    value = _parse_small_japanese_number(match.group(1))
    if value is None:
        return None
    return min(max(value, 1), 1000)


def _repair_visibility(ins: Instruction, background: str) -> Instruction:
    repaired = _with_visible_color(ins, background)
    repaired = _with_visible_particle(repaired)
    return _with_density_budget(repaired)


def _coerce_and_repair_instruction(
    ins: Instruction,
    *,
    original_background: str,
    background: str,
    ddl: str | None,
) -> Instruction:
    coerced = _coerce_instruction(ins)
    coerced = _with_material_hint(coerced, ddl)
    coerced = _with_variation_hint(coerced, ddl)
    if original_background == "gray" and coerced.color == "gray":
        coerced = _with_visible_color(coerced, "gray")
    return _repair_visibility(coerced, background)


def ensure_renderable_score(score: Score) -> None:
    """Raise when Stage 2 returned no drawable instructions."""
    if not score.instructions:
        raise ValueError("Stage 2 returned no drawable instructions")


# ── 汎用補修ループ ────────────────────────────────────────────────────────────────

def _coerce_instruction(ins: Instruction) -> Instruction:
    """PRIMITIVE_SPECS テーブルを参照して 1 命令を補修する。

    補修の流れ:
      1. フィールドが None → fallbacks を順に試みる
      2. 値を coerce 関数で型正規化 (None なら default へ)
      3. POST_COERCE で cross-field 制約を適用
    """
    data = ins.model_dump(by_alias=True)

    for spec in PRIMITIVE_SPECS.get(ins.primitive, []):
        val = data.get(spec.name)

        # (1) None → fallback を順に試みる
        if val is None:
            for fb in spec.fallbacks:
                fb_val = data.get(fb)
                if fb_val is not None:
                    val = fb_val
                    break

        # (2) 型正規化。失敗 (None 返却) なら default を使う
        if val is not None and spec.coerce is not None:
            val = spec.coerce(val)

        if val is None:
            val = list(spec.default) if isinstance(spec.default, list) else spec.default

        data[spec.name] = val

    # (3) cross-field 補正
    if post := POST_COERCE.get(ins.primitive):
        post(data)

    return Instruction.model_validate(data)


def coerce_score(score: Score, *, ddl: str | None = None) -> Score:
    """LLM 生成 Score の欠損・不正フィールドを補修して Renderer が安全に描画できる状態にする。"""
    background = _visible_background(score.background)
    instructions = [
        _coerce_and_repair_instruction(ins, original_background=score.background, background=background, ddl=ddl)
        for ins in score.instructions
    ]
    instructions = _dedupe_instructions(instructions)
    instructions = _with_ddl_coverage(instructions, ddl=ddl, background=background)
    instructions = _with_color_delivery_repair(instructions, ddl=ddl)
    instructions = _with_shape_delivery_repair(instructions, ddl=ddl, background=background)
    instructions = _with_complex_motif_repair(instructions, ddl=ddl, background=background)
    instructions = _with_composition_diversity_repair(instructions, ddl=ddl, background=background)
    instructions = _with_per_instruction_density_budget(instructions)
    instructions = _with_total_density_budget(instructions)
    data = score.model_dump(by_alias=True)
    data["background"] = background
    data["instructions"] = [ins.model_dump(by_alias=True) for ins in instructions]
    return Score.model_validate(data)
