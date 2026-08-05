"""Score-only normalization and renderability repair."""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from ..language_support.registry import INSTRUCTION_LANGUAGE_REGISTRY
from ..limits import DEFAULT_LIMITS, Limits
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


# The four constants that used to live here -- the per-work total, the
# per-instruction total, and the two ends of the representative band -- now come
# from `..limits`. Read them off a Limits instance so the follow-up contract can
# swap the source in one place.


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
    machine_note = data.get("note")
    data["note"] = f"{machine_note}; {note}" if machine_note else note
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


def _with_density_budget(ins: Instruction, limits: Limits = DEFAULT_LIMITS) -> Instruction:
    arr = ins.arrangement
    if arr is None or arr.layout != "scatter" or arr.count <= limits.max_expanded_per_instruction:
        return ins
    if _shape_extent(ins) > 0.018:
        return ins
    return _with_clustered_density(ins, "scatter density clustered to preserve negative space", limits)


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
    data.pop("note", None)
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def _with_structural_duplicate_repair(instructions: list[Instruction]) -> list[Instruction]:
    """Merge structurally identical helper layers that differ only in machine notes."""
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
            and not _is_atmospheric_effect_hint(ins.color_hint)
            and _is_plain_material_hint(ins.note)
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
    machine_note = data.get("note")
    data["note"] = f"{machine_note}; {note}" if machine_note else note
    return Instruction.model_validate(data)


def _with_note(ins: Instruction, note: str) -> Instruction:
    data = ins.model_dump(by_alias=True)
    machine_note = data.get("note")
    data["note"] = f"{machine_note}; {note}" if machine_note else note
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


def _clustered_visual_count(original_count: int, limits: Limits = DEFAULT_LIMITS) -> int:
    if original_count <= limits.represented_count_max:
        return original_count
    return min(
        limits.represented_count_max,
        max(limits.represented_count_min, int(original_count * 0.42)),
    )


def _budgeted_count(count: int, limits: Limits = DEFAULT_LIMITS) -> int:
    """A stated count is literal below the threshold and represented above it.

    The description asked for a number; below the threshold the number is not a
    guess to be second-guessed. Above it the number cannot be counted by eye, so
    the group is shown as a band instead of a tally.

    Above the threshold this defers to _clustered_visual_count -- the same
    function the density governor applies to Stage 2's own output -- so that a
    count arriving by either route lands on the SAME number, not merely inside
    the same band.
    """
    if count < limits.literal_count_threshold:
        return count
    return _clustered_visual_count(count, limits)


def _with_clustered_density(ins: Instruction, note: str, limits: Limits = DEFAULT_LIMITS) -> Instruction:
    arr = ins.arrangement
    if arr is None or arr.layout == "grid":
        return ins
    original_count = arr.count
    data = ins.model_dump(by_alias=True)
    arr_data = dict(data["arrangement"])
    arr_data["count"] = _clustered_visual_count(original_count, limits)
    existing_density = arr_data.get("density", "none")
    arr_data["density"] = existing_density if existing_density != "none" else _density_label(original_count)
    arr_data["cluster_count"] = arr_data.get("cluster_count") or _cluster_count(original_count)
    arr_data["preserve_space"] = True
    arr_data["margin"] = max(float(arr_data.get("margin") or 0.1), 0.18)
    if arr_data.get("fade", "none") == "none":
        arr_data["fade"] = "directional" if arr.path != "none" or arr.layout in ("horizontal", "vertical") else "outward"
    data["arrangement"] = arr_data
    machine_note = data.get("note")
    full_note = f"{note}; original count {original_count}"
    data["note"] = f"{machine_note}; {full_note}" if machine_note else full_note
    return Instruction.model_validate(data)


def _with_per_instruction_density_budget(
    instructions: list[Instruction], limits: Limits = DEFAULT_LIMITS
) -> list[Instruction]:
    adjusted: list[Instruction] = []
    for ins in instructions:
        if (
            ins.arrangement is None
            or ins.arrangement.layout == "grid"
            or ins.arrangement.count <= limits.max_expanded_per_instruction
        ):
            adjusted.append(ins)
            continue
        adjusted.append(
            _with_clustered_density(
                ins, "single arrangement density clustered to preserve negative space", limits
            )
        )
    return adjusted


def _with_total_density_budget(
    instructions: list[Instruction], limits: Limits = DEFAULT_LIMITS
) -> list[Instruction]:
    """Bring the total back under budget by representing the largest groups first.

    Counted and uncountable are different things. Twelve squares can be counted by
    eye; two hundred dots cannot. Shrinking every group in proportion spends the
    budget on the groups a reader could have verified, so the large groups give way
    first and the small ones stay literal for as long as the budget allows.
    """

    def is_grid(ins: Instruction) -> bool:
        return ins.arrangement is not None and ins.arrangement.layout == "grid"

    adjusted = list(instructions)
    movable = [index for index, ins in enumerate(adjusted) if not is_grid(ins) and ins.arrangement is not None]
    total = sum(_expanded_count(ins) for ins in adjusted if not is_grid(ins))
    if total <= limits.max_expanded_primitives:
        return instructions

    # Represent the largest group, check the budget, and only then reach for the next.
    for index in sorted(movable, key=lambda i: _expanded_count(adjusted[i]), reverse=True):
        if total <= limits.max_expanded_primitives:
            break
        before = _expanded_count(adjusted[index])
        candidate = _with_clustered_density(
            adjusted[index], "largest group represented to fit the total density budget", limits
        )
        after = _expanded_count(candidate)
        if after < before:
            adjusted[index] = candidate
            total -= before - after

    if total <= limits.max_expanded_primitives or not movable:
        return adjusted

    # Representing every group is not always enough. What is left is a ceiling the
    # large groups share: the highest one under which the total fits. Groups already
    # below it are untouched, so the small ones still come through whole.
    counts = [_expanded_count(adjusted[index]) for index in movable]
    fixed = sum(_expanded_count(ins) for ins in adjusted if not is_grid(ins)) - sum(counts)
    ceiling = 1
    for candidate in range(1, max(counts) + 1):
        if fixed + sum(min(count, candidate) for count in counts) <= limits.max_expanded_primitives:
            ceiling = candidate
        else:
            break
    for index in movable:
        if _expanded_count(adjusted[index]) > ceiling:
            adjusted[index] = _with_arrangement_count(
                adjusted[index], ceiling, "expanded density capped to preserve negative space"
            )
    return adjusted


def _mark_count(ins: Instruction) -> int:
    """How many marks this instruction actually puts on the page.

    `_expanded_count` reads `arrangement.count`, which is what the two density
    governors budget against. A grid is drawn differently: when rows and cols are
    both declared the renderer lays out rows*cols cells and ignores count, so a
    grid of rows=40 cols=50 draws 2000 marks whatever count says. The ceiling has
    to answer for what is drawn, not for what was declared.
    """
    arr = ins.arrangement
    if arr is None:
        return 1
    if arr.layout == "grid" and arr.rows is not None and arr.cols is not None:
        return max(1, arr.rows * arr.cols)
    return max(1, int(arr.count))


def _grid_within(ins: Instruction, ceiling: int, note: str) -> Instruction:
    """Drop a grid to the largest lattice under the ceiling that keeps its shape.

    Thinning a lattice is not an option -- a lattice with holes in it is not a
    lattice -- so the rows-to-cols ratio is what survives and the cell count is
    what gives way.
    """
    arr = ins.arrangement
    assert arr is not None
    if arr.rows is None or arr.cols is None:
        return _with_arrangement_count(ins, ceiling, note)
    rows, cols = arr.rows, arr.cols
    # Derive cols from rows at the original ratio, so the shape is preserved by
    # construction rather than by trimming whichever side happens to be larger,
    # and take the largest such lattice that fits.
    new_rows, new_cols = 1, 1
    for candidate_rows in range(1, rows + 1):
        candidate_cols = max(1, min(cols, round(candidate_rows * cols / rows)))
        if candidate_rows * candidate_cols > ceiling:
            continue
        if candidate_rows * candidate_cols > new_rows * new_cols:
            new_rows, new_cols = candidate_rows, candidate_cols
    data = ins.model_dump(by_alias=True)
    arrangement = dict(data["arrangement"])
    arrangement["rows"] = new_rows
    arrangement["cols"] = new_cols
    arrangement["count"] = new_rows * new_cols
    data["arrangement"] = arrangement
    return _with_note(Instruction.model_validate(data), note)


def _enforce_hard_ceiling(
    score: Score, limits: Limits = DEFAULT_LIMITS, notes: list[str] | None = None
) -> Score:
    """The last word on how many marks leave coerce, grid included.

    The density governors above deliberately spare grids: a lattice with holes in
    it is not a lattice. That exemption is right for *thinning* and wrong for the
    ceiling -- a work is still a work, and 10,000 marks is not a drawing anyone
    waited for. This runs after every governor and answers to no layout.
    """
    instructions = list(score.instructions)
    changed = False

    if len(instructions) > limits.max_instructions:
        dropped = len(instructions) - limits.max_instructions
        instructions = instructions[: limits.max_instructions]
        note = f"instruction list capped at {limits.max_instructions}; {dropped} dropped"
        instructions[-1] = _with_note(instructions[-1], note)
        if notes is not None:
            notes.append(note)
        changed = True

    counts = [_mark_count(ins) for ins in instructions]
    total = sum(counts)
    if total > limits.max_expanded_primitives:
        # The ceiling the large groups share: the highest one under which the
        # total fits. Groups already below it are untouched, so a small group
        # still comes through whole.
        ceiling = 1
        for candidate in range(1, max(counts) + 1):
            if sum(min(count, candidate) for count in counts) <= limits.max_expanded_primitives:
                ceiling = candidate
            else:
                break
        note = f"hard ceiling {limits.max_expanded_primitives} applied to the whole work"
        if notes is not None:
            notes.append(note)
        for index, ins in enumerate(instructions):
            if counts[index] <= ceiling or ins.arrangement is None:
                continue
            if ins.arrangement.layout == "grid":
                instructions[index] = _grid_within(ins, ceiling, note)
            else:
                instructions[index] = _with_arrangement_count(ins, ceiling, note)
            changed = True

    if not changed:
        return score
    data = score.model_dump(by_alias=True)
    data["instructions"] = [ins.model_dump(by_alias=True) for ins in instructions]
    return Score.model_validate(data)


def _repair_visibility(ins: Instruction, background: str) -> Instruction:
    repaired = _with_visible_color(ins, background)
    repaired = _with_visible_particle(repaired)
    return _with_density_budget(repaired)


def _repair_coerced_instruction(
    ins: Instruction,
    *,
    original_background: str,
    background: str,
) -> Instruction:
    repaired = ins
    if original_background == "gray" and repaired.color == "gray":
        repaired = _with_visible_color(repaired, "gray")
    return _repair_visibility(repaired, background)


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
