"""Score-only normalization and renderability repair."""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from ..language_support.registry import INSTRUCTION_LANGUAGE_REGISTRY
from ..schema import Instruction, Score


def _coerce_marker_values(name: str) -> tuple[Any, ...]:
    values: list[Any] = []
    for support in INSTRUCTION_LANGUAGE_REGISTRY.values():
        language_values = support.coerce_markers.get(name, ())
        if isinstance(language_values, tuple):
            values.extend(language_values)
    return tuple(values)


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


def _as_polygon_sides(v: Any) -> int | None:
    """polygon の頂点数を 5-8 に正規化。"""
    try:
        return min(max(int(v), 5), 8)
    except (TypeError, ValueError):
        return None


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
    "cloudform": [
        FieldSpec("center", [0.5, 0.5], fallbacks=["position"], coerce=_as_coord),
        FieldSpec("size",   [0.3, 0.3],                          coerce=_as_positive_size),
    ],
    "arc": [
        FieldSpec("center",      [0.5, 0.5], fallbacks=["position"], coerce=_as_coord),
        FieldSpec("radius",      0.15,                               coerce=_as_positive_float),
        FieldSpec("angle_start", 0.0,                                coerce=_as_float),
        FieldSpec("angle_end",   270.0,                              coerce=_as_float),
    ],
    "polygon": [
        FieldSpec("center", [0.5, 0.5], fallbacks=["position"], coerce=_as_coord),
        FieldSpec("radius", 0.12,                              coerce=_as_positive_float),
        FieldSpec("sides",  5,                                 coerce=_as_polygon_sides),
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


MAX_EXPANDED_PRIMITIVES = 400


MAX_EXPANDED_PER_INSTRUCTION = 240


MAX_VISUAL_CLUSTERED_COUNT = 120


def _shape_extent(ins: Instruction) -> float:
    if ins.primitive in ("circle", "arc", "polygon"):
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


def _dedupe_instructions(instructions: list[Instruction]) -> list[Instruction]:
    deduped: list[Instruction] = []
    seen: set[str] = set()
    for ins in instructions:
        # Relations are sequential operations whose result depends on the
        # preceding performed instruction. Identical payloads at different
        # positions are therefore not duplicates.
        if ins.relation is not None:
            deduped.append(ins)
            continue
        key = json.dumps(ins.model_dump(by_alias=True, exclude_none=True), sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ins)
    return deduped


def _dedupe_instruction_key(ins: Instruction) -> str:
    data = ins.model_dump(by_alias=True, exclude_none=True)
    data.pop("color_hint", None)
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def _with_structural_duplicate_repair(instructions: list[Instruction]) -> list[Instruction]:
    """color_hint だけが違う同一補助層を統合する。"""
    repaired: list[Instruction] = []
    seen: set[str] = set()
    for ins in instructions:
        if ins.relation is not None:
            repaired.append(ins)
            continue
        key = _dedupe_instruction_key(ins)
        if key in seen:
            continue
        seen.add(key)
        repaired.append(ins)
    return repaired


ATMOSPHERIC_EFFECT_MARKERS: tuple[str, ...] = _coerce_marker_values("atmospheric_effect")


def _closed_shape_geometry_key(ins: Instruction) -> tuple | None:
    if ins.primitive not in ("circle", "ellipse", "square", "triangle", "polygon"):
        return None
    if ins.primitive == "circle" and ins.center is not None:
        return ("circle", round(ins.center[0], 2), round(ins.center[1], 2), round(ins.radius or 0.1, 2))
    if ins.primitive == "ellipse" and ins.center is not None and ins.size is not None:
        return (
            "ellipse",
            round(ins.center[0], 2),
            round(ins.center[1], 2),
            round(ins.size[0], 2),
            round(ins.size[1], 2),
        )
    if ins.primitive in ("square", "triangle") and ins.position is not None and ins.size is not None:
        return (
            ins.primitive,
            round(ins.position[0], 2),
            round(ins.position[1], 2),
            round(ins.size[0], 2),
            round(ins.size[1], 2),
        )
    if ins.primitive == "polygon" and ins.center is not None:
        return (
            "polygon",
            round(ins.center[0], 2),
            round(ins.center[1], 2),
            round(ins.radius or 0.1, 2),
            int(ins.sides or 5),
        )
    return None


def _closed_shape_area(ins: Instruction) -> float:
    if ins.primitive == "circle":
        radius = ins.radius if ins.radius is not None else 0.1
        return radius * radius
    if ins.primitive == "ellipse" and ins.size is not None:
        return ins.size[0] * ins.size[1]
    if ins.primitive in ("square", "triangle") and ins.size is not None:
        return ins.size[0] * ins.size[1]
    if ins.primitive == "polygon":
        radius = ins.radius if ins.radius is not None else 0.1
        return radius * radius
    return 0.0


def _is_atmospheric_effect_hint(hint: str | None) -> bool:
    if not hint:
        return False
    lower = hint.lower()
    return any(marker in hint or marker.lower() in lower for marker in ATMOSPHERIC_EFFECT_MARKERS)


def _is_plain_material_hint(hint: str | None) -> bool:
    if not hint:
        return True
    lower = hint.lower()
    return "material inferred from ddl" in lower and not _is_atmospheric_effect_hint(hint)


def _with_presence_auxiliary_shape_repair(instructions: list[Instruction], presence: Any) -> list[Instruction]:
    """presence 有効時に、補助的な大きい閉図形のプレーン重複を抑える。"""
    kind = presence.get("kind") if isinstance(presence, dict) else getattr(presence, "kind", None)
    if presence is None or kind == "none":
        return instructions

    atmospheric_keys = {
        key
        for ins in instructions
        if (key := _closed_shape_geometry_key(ins)) is not None
        and _closed_shape_area(ins) >= 0.025
        and _is_atmospheric_effect_hint(ins.color_hint)
    }
    if not atmospheric_keys:
        return instructions

    repaired: list[Instruction] = []
    for ins in instructions:
        key = _closed_shape_geometry_key(ins)
        if (
            key in atmospheric_keys
            and _closed_shape_area(ins) >= 0.025
            and _is_plain_material_hint(ins.color_hint)
        ):
            continue
        repaired.append(ins)
    return repaired


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
    if arr is None or arr.layout == "grid":
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
        if (
            ins.arrangement is None
            or ins.arrangement.layout == "grid"
            or ins.arrangement.count <= MAX_EXPANDED_PER_INSTRUCTION
        ):
            adjusted.append(ins)
            continue
        adjusted.append(_with_clustered_density(ins, "single arrangement density clustered to preserve negative space"))
    return adjusted


def _with_total_density_budget(instructions: list[Instruction]) -> list[Instruction]:
    def is_grid(ins: Instruction) -> bool:
        return ins.arrangement is not None and ins.arrangement.layout == "grid"

    total = sum(_expanded_count(ins) for ins in instructions if not is_grid(ins))
    if total <= MAX_EXPANDED_PRIMITIVES:
        return instructions

    remaining_budget = MAX_EXPANDED_PRIMITIVES
    remaining = list(instructions)
    adjusted: list[Instruction] = []
    for index, ins in enumerate(remaining):
        if is_grid(ins):
            adjusted.append(ins)
            continue
        count = _expanded_count(ins)
        rest_minimum = sum(1 for item in remaining[index + 1:] if not is_grid(item))
        if ins.arrangement is None:
            adjusted.append(ins)
            remaining_budget -= 1
            continue
        if remaining_budget <= rest_minimum + 1:
            allowed = 1
        else:
            remaining_total = sum(
                _expanded_count(item)
                for item in remaining[index:]
                if not is_grid(item)
            )
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


def _repair_visibility(ins: Instruction, background: str) -> Instruction:
    repaired = _with_visible_color(ins, background)
    repaired = _with_visible_particle(repaired)
    return _with_density_budget(repaired)


def ensure_renderable_score(score: Score) -> None:
    """Raise when Stage 2 returned no drawable instructions."""
    if not score.instructions:
        raise ValueError("Stage 2 returned no drawable instructions")


def _has_relation_contour(ins: Instruction) -> bool:
    if ins.primitive == "line":
        return ins.from_ is not None and ins.to is not None
    if ins.primitive in {"circle", "arc", "polygon"}:
        return ins.center is not None and ins.radius is not None
    if ins.primitive in {"ellipse", "cloudform"}:
        return ins.center is not None and ins.size is not None
    if ins.primitive in {"square", "triangle"}:
        return ins.position is not None and ins.size is not None
    return False


def _drop_invalid_relations(instructions: list[Instruction]) -> list[Instruction]:
    result: list[Instruction] = []
    for index, ins in enumerate(instructions):
        relation = ins.relation
        if relation is None:
            result.append(ins)
            continue
        invalid = index == 0 or not result or not _has_relation_contour(result[-1])
        if relation.type == "between":
            invalid = invalid or len(result) < 2 or not _has_relation_contour(result[-2])
        elif relation.type == "touching":
            invalid = invalid or ins.primitive not in {"line", "arc"}
            invalid = invalid or result[-1].primitive not in {"line", "arc"}
        if invalid:
            data = ins.model_dump(by_alias=True)
            data.pop("relation", None)
            result.append(Instruction.model_validate(data))
        else:
            result.append(ins)
    return result


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
