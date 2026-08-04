"""DDL-aware score composition and repair."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from ..language_support.registry import INSTRUCTION_LANGUAGE_REGISTRY
from ..schema import Instruction
from .normalize import (
    MAX_EXPANDED_PER_INSTRUCTION,
    VISIBLE_ON_BACKGROUND,
    _closed_shape_area,
    _coerce_marker_values,
    _cluster_count,
    _expanded_count,
    _shape_extent,
)


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


def _coerce_marker_dict(name: str) -> dict[str, tuple[str, ...]]:
    merged: dict[str, list[str]] = {}
    for support in INSTRUCTION_LANGUAGE_REGISTRY.values():
        language_values = support.coerce_markers.get(name, {})
        if not isinstance(language_values, dict):
            continue
        for key, markers in language_values.items():
            merged.setdefault(str(key), []).extend(str(marker) for marker in markers)
    return {key: tuple(markers) for key, markers in merged.items()}


MATERIAL_WEIGHT_HINTS: tuple[tuple[tuple[str, ...], str], ...] = _coerce_marker_values("material_weight_hints")


MAX_QUIET_VISUAL_COUNT = 64


MAX_QUIET_VERTICAL_COUNT = 48


MAX_NEON_BLUR_VISUAL_COUNT = 24


MAX_NEON_BLUR_VERTICAL_COUNT = 18


MAX_QUIET_LARGE_SHAPE_COUNT = 16


MAX_QUIET_SYMBOLIC_SHAPE_COUNT = 8


MAX_QUIET_SYMBOLIC_SHAPE_WIDTH = 0.12


MAX_QUIET_SYMBOLIC_SHAPE_HEIGHT = 0.09


MAX_QUIET_SINGLE_SHAPE_WIDTH = 0.34


MAX_QUIET_SINGLE_SHAPE_HEIGHT = 0.24


MAX_QUIET_SINGLE_SHAPE_RADIUS = 0.17


MAX_QUIET_SINGLE_SHAPE_AREA = 0.14


MAX_UNINTENTIONAL_FILLED_SHAPE_WIDTH = 0.42


MAX_UNINTENTIONAL_FILLED_SHAPE_HEIGHT = 0.30


MAX_UNINTENTIONAL_FILLED_SHAPE_RADIUS = 0.20


MAX_UNINTENTIONAL_FILLED_SHAPE_AREA = 0.20


COLOR_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = _coerce_marker_values("color_markers")


def _marker_in_text(marker: str, text: str, lower: str) -> bool:
    marker_lower = marker.lower()
    if marker.isascii() and any(ch.isalpha() for ch in marker):
        return re.search(rf"(?<![a-z]){re.escape(marker_lower)}(?![a-z])", lower) is not None
    return marker in text or marker_lower in lower


def _any_marker_in_text(markers: tuple[str, ...], text: str, lower: str) -> bool:
    return any(_marker_in_text(marker, text, lower) for marker in markers)


NEGATED_COLOR_MARKERS: dict[str, tuple[str, ...]] = _coerce_marker_dict("negated_color_markers")


SHAPE_INTENT_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = _coerce_marker_values("shape_intent_markers")


MOTIF_INTENT_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = _coerce_marker_values("motif_intent_markers")


def _with_material_hint(ins: Instruction, ddl: str | None) -> Instruction:
    if not ddl or ins.weight != "pen":
        return ins
    lower = ddl.lower()
    for markers, weight in MATERIAL_WEIGHT_HINTS:
        if any(marker.lower() in lower for marker in markers):
            data = ins.model_dump(by_alias=True)
            data["weight"] = weight
            note = f"material inferred from DDL: {weight}"
            _append_note(data, note)
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


QUIET_DENSITY_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("quiet_density")


VERTICAL_DENSITY_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("vertical_density")


MOTION_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("motion")


COLORFUL_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("colorful")


LEAF_GRAIN_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("leaf_grain")


SILENCE_LAYER_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("silence_layer")


HARD_EDGE_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("hard_edge")


PLAYFUL_MOTION_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("playful_motion")


EDGE_LIGHT_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("edge_light")


STRONG_EDGE_LIGHT_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("strong_edge_light")


VANISHING_TRACE_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("vanishing_trace")


RHYTHM_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("rhythm")


VISUAL_EVENT_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("visual_event")


MA_PRESSURE_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("ma_pressure")


SEMANTIC_VISUAL_EVENT_HINTS: tuple[tuple[tuple[str, ...], str], ...] = _coerce_marker_values("semantic_visual_event_hints")


SURFACE_TENSION_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("surface_tension")


INTENTIONAL_LARGE_SURFACE_MARKERS: tuple[str, ...] = _coerce_marker_values("intentional_large_surface")


EXPLICIT_SURFACE_MARKERS: tuple[str, ...] = _coerce_marker_values("explicit_surface")


SUNSET_SKY_MARKERS: tuple[str, ...] = _coerce_marker_values("sunset_sky")


DAWN_MARKERS: tuple[str, ...] = _coerce_marker_values("dawn")


NIGHT_MARKERS: tuple[str, ...] = _coerce_marker_values("night")


# The clause is the description's own instruction; the scene markers above are
# inferences about it. An explicit clause must not need a sunset to be believed.
_EXPLICIT_BACKGROUND_CLAUSE = re.compile(
    r"背景を[^。、\n]{1,12}?(?:で|に)(?:塗|ぬ|埋|し)"
    r"|(?:fill|paint)\s+(?:the\s+)?background",
    re.I,
)


def _context_has_density_governor(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    return _any_marker_in_text(QUIET_DENSITY_CONTEXT_MARKERS, ddl, lower)


def _context_has_vertical_density(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    return _any_marker_in_text(VERTICAL_DENSITY_CONTEXT_MARKERS, ddl, lower)


def _context_has_neon_blur_density(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    scene_markers = ("夜", "ガラス", "ネオン", "night", "glass", "neon")
    blur_markers = ("涙", "滲", "にじ", "blur", "tear")
    return _any_marker_in_text(scene_markers, ddl, lower) and _any_marker_in_text(blur_markers, ddl, lower)


def _context_has_motion(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    return _any_marker_in_text(MOTION_CONTEXT_MARKERS, ddl, lower)


def _context_has_colorful_accent(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    return _any_marker_in_text(COLORFUL_CONTEXT_MARKERS, ddl, lower)


def _context_has_marker(ddl: str | None, markers: tuple[str, ...]) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    return _any_marker_in_text(markers, ddl, lower)


def _with_arrangement_density_governor(ins: Instruction, *, count: int, density: str, fade: str, note: str) -> Instruction:
    if ins.arrangement is None:
        return ins
    data = ins.model_dump(by_alias=True)
    arr_data = dict(data["arrangement"])
    original_count = int(arr_data.get("count") or 1)
    arr_data["count"] = min(original_count, max(1, int(count)))
    arr_data["density"] = density
    arr_data["preserve_space"] = True
    arr_data["margin"] = max(float(arr_data.get("margin") or 0.1), 0.22)
    if arr_data.get("fade", "none") == "none":
        arr_data["fade"] = fade
    if arr_data.get("cluster_count") is None and arr_data["count"] >= 32:
        arr_data["cluster_count"] = min(5, _cluster_count(original_count))
    data["arrangement"] = arr_data
    full_note = f"{note}; original count {original_count}"
    _append_note(data, full_note)
    return Instruction.model_validate(data)


def _cap_size(size: tuple[float, float] | list[float], max_width: float, max_height: float) -> list[float]:
    width = float(size[0])
    height = float(size[1])
    scale = min(1.0, max_width / width if width > 0 else 1.0, max_height / height if height > 0 else 1.0)
    return [max(0.01, width * scale), max(0.01, height * scale)]


def _with_quiet_symbolic_shape_tempering(ins: Instruction, *, ddl: str | None) -> Instruction:
    if not _context_has_density_governor(ddl) or ins.primitive not in ("square", "triangle", "polygon"):
        return ins
    if ins.primitive != "polygon" and ins.size is None:
        return ins
    if ins.primitive == "polygon" and ins.radius is None:
        return ins
    hint = ins.note or ""
    if not any(marker in hint for marker in ("coverage from DDL clause", "motif restored", "shape intent", "fallback from DDL")):
        return ins

    arr = ins.arrangement
    if ins.primitive == "polygon":
        needs_size_cap = float(ins.radius or 0.0) > MAX_QUIET_SYMBOLIC_SHAPE_WIDTH / 2
    else:
        assert ins.size is not None
        size = list(ins.size)
        needs_size_cap = size[0] > MAX_QUIET_SYMBOLIC_SHAPE_WIDTH or size[1] > MAX_QUIET_SYMBOLIC_SHAPE_HEIGHT
    needs_count_cap = arr is not None and arr.count > MAX_QUIET_SYMBOLIC_SHAPE_COUNT
    if not needs_size_cap and not needs_count_cap:
        return ins

    data = ins.model_dump(by_alias=True)
    if needs_size_cap:
        if ins.primitive == "polygon":
            data["radius"] = min(float(ins.radius or 0.1), MAX_QUIET_SYMBOLIC_SHAPE_WIDTH / 2)
        else:
            data["size"] = _cap_size(size, MAX_QUIET_SYMBOLIC_SHAPE_WIDTH, MAX_QUIET_SYMBOLIC_SHAPE_HEIGHT)
    if arr is not None:
        arr_data = dict(data["arrangement"])
        if needs_count_cap:
            arr_data["count"] = MAX_QUIET_SYMBOLIC_SHAPE_COUNT
        arr_data["preserve_space"] = True
        arr_data["margin"] = max(float(arr_data.get("margin") or 0.1), 0.24)
        if arr_data.get("fade", "none") == "none":
            arr_data["fade"] = "outward"
        if arr_data.get("density", "none") == "none":
            arr_data["density"] = "low"
        data["arrangement"] = arr_data
    note = "quiet symbolic shape tempered to avoid fallback dominance"
    _append_note(data, note)
    return Instruction.model_validate(data)


def _has_intentional_large_surface(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    return _any_marker_in_text(INTENTIONAL_LARGE_SURFACE_MARKERS, ddl, lower)


def _source_context(ddl: str | None) -> str:
    """The whole context, not its first line.

    Until the description-propagation cut the context was `原文\\nDDL`, so the
    first line was the original description and reading only it was the point.
    Coerce now receives the DDL alone, and 13.6% of production DDLs are
    multi-line: keeping the first-line read would stop the markers below at
    line 1 and never see a background clause that sits on line 2.
    """
    if not ddl:
        return ""
    return ddl.strip()


def _has_explicit_background_intent(ddl: str | None) -> bool:
    """Whether the DDL itself asked for the background it carries.

    `_looks_like_generated_background_plan` used to guard the top of this
    function: it spotted a machine-generated plan pasted into the DESCRIPTION
    field and refused to read it as the author's own intent. That guard was a
    judgement about provenance, and the cut removed the only text whose
    provenance it could judge -- coerce no longer sees a description at all.
    Left in place it misfired on the production DDL, whose ordinary shape
    ("背景を黒で塗りつぶす。" plus four more clauses) satisfied every one of its
    conditions, and returned early before the clause check below: 54 of 604 dark
    production works washed to white, 1 with the guard gone.
    """
    if not ddl:
        return False
    context = _source_context(ddl) or ddl
    if _EXPLICIT_BACKGROUND_CLAUSE.search(ddl):
        return True
    lower = context.lower()
    if _any_marker_in_text(EXPLICIT_SURFACE_MARKERS, context, lower):
        return True
    if _any_marker_in_text(SUNSET_SKY_MARKERS, context, lower):
        return True
    if _any_marker_in_text(DAWN_MARKERS, context, lower):
        return False
    return _any_marker_in_text(NIGHT_MARKERS, context, lower)


def _with_background_dominance_governor(background: str, *, ddl: str | None) -> str:
    """主題指定なしの濃色背景が画面全体を支配するのを避ける。"""
    if background not in {"black", "red", "blue", "green"}:
        return background
    if _has_explicit_background_intent(ddl) or _has_intentional_large_surface(ddl):
        return background
    if _color_only_constraint_from_ddl(ddl):
        return background
    if _context_has_density_governor(ddl) or _presence_from_ddl(ddl) is not None:
        return "white"
    return background


def _with_quiet_single_shape_tempering(ins: Instruction, *, ddl: str | None) -> Instruction:
    if _has_intentional_large_surface(ddl):
        return ins
    if ins.arrangement is not None or ins.primitive not in ("circle", "ellipse", "square", "triangle", "polygon"):
        return ins
    if _closed_shape_area(ins) < MAX_QUIET_SINGLE_SHAPE_AREA:
        return ins

    data = ins.model_dump(by_alias=True)
    if ins.primitive in ("circle", "polygon"):
        data["radius"] = min(float(ins.radius or MAX_QUIET_SINGLE_SHAPE_RADIUS), MAX_QUIET_SINGLE_SHAPE_RADIUS)
    elif ins.size is not None:
        data["size"] = _cap_size(ins.size, MAX_QUIET_SINGLE_SHAPE_WIDTH, MAX_QUIET_SINGLE_SHAPE_HEIGHT)
    note = "quiet single large shape tempered to keep trace/space legible"
    _append_note(data, note)
    return Instruction.model_validate(data)


def _with_unintentional_filled_shape_tempering(ins: Instruction, *, ddl: str | None) -> Instruction:
    if _has_intentional_large_surface(ddl):
        return ins
    if _context_has_density_governor(ddl):
        return ins
    if not ins.filled or ins.arrangement is not None:
        return ins
    if ins.primitive not in ("circle", "ellipse", "square", "triangle", "polygon"):
        return ins
    if _closed_shape_area(ins) < MAX_UNINTENTIONAL_FILLED_SHAPE_AREA:
        return ins

    data = ins.model_dump(by_alias=True)
    if ins.primitive in ("circle", "polygon"):
        data["radius"] = min(float(ins.radius or MAX_UNINTENTIONAL_FILLED_SHAPE_RADIUS), MAX_UNINTENTIONAL_FILLED_SHAPE_RADIUS)
    elif ins.size is not None:
        data["size"] = _cap_size(
            ins.size,
            MAX_UNINTENTIONAL_FILLED_SHAPE_WIDTH,
            MAX_UNINTENTIONAL_FILLED_SHAPE_HEIGHT,
        )
    note = "large filled shape tempered to avoid unintended surface dominance"
    _append_note(data, note)
    return Instruction.model_validate(data)


def _with_motion_energy(instructions: list[Instruction], *, ddl: str | None) -> list[Instruction]:
    """動きのある入力では count を増やさず、軌跡・回転・揺らぎで発散を保つ。"""
    if not _context_has_motion(ddl):
        return instructions

    adjusted: list[Instruction] = []
    for index, ins in enumerate(instructions):
        if ins.arrangement is not None and ins.arrangement.layout == "grid":
            adjusted.append(ins)
            continue
        data = ins.model_dump(by_alias=True)
        changed = False
        if ins.arrangement is not None:
            arr_data = dict(data["arrangement"])
            if arr_data.get("path", "none") == "none":
                arr_data["path"] = "wave" if index % 2 == 0 else "diagonal"
                changed = True
            if arr_data.get("rhythm_spacing", "none") == "none":
                arr_data["rhythm_spacing"] = "loose"
                changed = True
            if ins.primitive in ("ellipse", "square", "triangle", "polygon") and data.get("rotation") is None:
                data["rotation"] = -24 if index % 2 == 0 else 18
                changed = True
            data["arrangement"] = arr_data
        elif ins.primitive in ("line", "ellipse", "arc", "square", "triangle", "polygon") and data.get("rotation") is None:
            data["rotation"] = -18 if index % 2 == 0 else 22
            changed = True

        if ins.variation is None and ins.primitive in ("line", "ellipse", "arc", "polygon"):
            data["variation"] = {
                "amplitude": "medium",
                "frequency": "slow",
                "quality": "wave",
                "dimensions": ["position_x", "position_y"],
            }
            changed = True

        if changed:
            note = "motion energy restored through trajectory and rotation"
            _append_note(data, note)
        adjusted.append(Instruction.model_validate(data))
    return adjusted


def _without_explicit_region_support(
    instructions: list[Instruction],
    *,
    ddl: str | None,
) -> list[Instruction]:
    """Keep composition-resolved DDL at one instruction per numeric region."""

    if not ddl:
        return instructions
    region_count = len(
        re.findall(
            r"(?:領域|region)\s*\[\s*(?:0(?:\.\d+)?|1(?:\.0+)?)\s*,",
            ddl,
            flags=re.IGNORECASE,
        )
    )
    if region_count == 0 or len(instructions) <= region_count:
        return instructions
    region_anchored = [
        ins for ins in instructions if ins.at is not None and ins.at.region is not None
    ]
    return (
        region_anchored[:region_count]
        if len(region_anchored) >= region_count
        else instructions[:region_count]
    )


def _has_motion_path(instructions: list[Instruction]) -> bool:
    return any(
        ins.arrangement is not None
        and (ins.arrangement.layout == "grid" or ins.arrangement.path != "none")
        and _expanded_count(ins) >= 3
        for ins in instructions
    )


def _motion_floor_instruction(*, ddl: str | None, background: str) -> Instruction:
    requested = [color for color in _color_repair_order(_requested_colors_from_ddl(ddl)) if color != background]
    color = requested[0] if requested else ("red" if background != "red" else VISIBLE_ON_BACKGROUND.get(background, "black"))
    return Instruction.model_validate(
        {
            "primitive": "arc",
            "center": [0.58, 0.52],
            "radius": 0.11,
            "angle_start": 205,
            "angle_end": 330,
            "rotation": -16,
            "color": color,
            "weight": "silverpoint",
            "note": "motion floor restored as a small directional trace",
            "arrangement": {
                "count": 3,
                "layout": "scatter",
                "path": "diagonal",
                "margin": 0.24,
                "density": "low",
                "fade": "directional",
                "preserve_space": True,
                "rhythm_spacing": "loose",
            },
        }
    )


def _with_motion_floor(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
) -> list[Instruction]:
    """動作語があるのに全体が静物化した場合だけ、少数の方向性を補う。"""
    if not _context_has_motion(ddl):
        return instructions
    if _strict_count_hint_from_ddl(ddl) is not None or _primitive_only_constraint_from_ddl(ddl):
        return instructions
    if len(instructions) >= 10 or _has_motion_path(instructions):
        return instructions
    if any("motion floor restored" in (ins.note or "") for ins in instructions):
        return instructions
    return [*instructions, _motion_floor_instruction(ddl=ddl, background=background)]


def _with_rhythm_variation(instructions: list[Instruction], *, ddl: str | None) -> list[Instruction]:
    """楽しい・躍動的な文脈では数を足さず、配置リズムだけを強める。"""
    if not _context_has_marker(ddl, RHYTHM_CONTEXT_MARKERS):
        return instructions

    adjusted: list[Instruction] = []
    for index, ins in enumerate(instructions):
        if ins.arrangement is not None and ins.arrangement.layout == "grid":
            adjusted.append(ins)
            continue
        data = ins.model_dump(by_alias=True)
        changed = False
        if ins.arrangement is not None:
            arr_data = dict(data["arrangement"])
            if arr_data.get("path", "none") == "none":
                arr_data["path"] = "wave" if index % 2 == 0 else "diagonal"
                changed = True
            if arr_data.get("density", "none") == "none":
                arr_data["density"] = "low"
                changed = True
            if arr_data.get("rhythm_spacing", "none") == "none":
                arr_data["rhythm_spacing"] = "syncopated"
                changed = True
            if float(arr_data.get("margin") or 0.1) < 0.14:
                arr_data["margin"] = 0.14
                changed = True
            data["arrangement"] = arr_data
        if ins.primitive in ("line", "ellipse", "arc", "square", "triangle", "polygon") and data.get("rotation") is None:
            data["rotation"] = -15 if index % 2 == 0 else 21
            changed = True
        if ins.variation is None and ins.primitive in ("line", "ellipse", "arc", "polygon"):
            data["variation"] = {
                "amplitude": "medium",
                "frequency": "medium",
                "quality": "wave",
                "dimensions": ["position_x", "position_y", "rotation"],
            }
            changed = True
        if changed:
            note = "rhythm variation restored without increasing count"
            _append_note(data, note)
        adjusted.append(Instruction.model_validate(data))
    return adjusted


def _clamp_unit(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _repair_seed(text: str | None, salt: str) -> int:
    digest = hashlib.sha256(f"{salt}:{text or ''}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _seed_choice(text: str | None, salt: str, values: tuple[Any, ...]) -> Any:
    return values[_repair_seed(text, salt) % len(values)]


def _seed_float(text: str | None, salt: str, low: float, high: float) -> float:
    value = (_repair_seed(text, salt) % 10000) / 9999
    return round(low + (high - low) * value, 3)


def _offset_from_anchor(anchor: tuple[float, float], *, ddl: str | None, salt: str, distance: float) -> list[float]:
    directions = ((1, -1), (1, 1), (-1, -1), (-1, 1), (1, 0), (-1, 0), (0, -1), (0, 1))
    dx, dy = _seed_choice(ddl, salt, directions)
    jitter_x = _seed_float(ddl, f"{salt}-jx", -0.018, 0.018)
    jitter_y = _seed_float(ddl, f"{salt}-jy", -0.018, 0.018)
    return [_clamp_unit(anchor[0] + dx * distance + jitter_x), _clamp_unit(anchor[1] + dy * distance + jitter_y)]


def _has_nearby_contour(instructions: list[Instruction], event: Instruction, *, radius: float = 0.25) -> bool:
    ex, ey = _instruction_anchor(event)
    for ins in instructions:
        if ins is event or _has_focal_event_hint(ins):
            continue
        if _shape_extent(ins) <= 0.0:
            continue
        ax, ay = _instruction_anchor(ins)
        if ((ax - ex) ** 2 + (ay - ey) ** 2) ** 0.5 <= radius:
            return True
    return False


def _with_repetition_event_variation(instructions: list[Instruction], *, ddl: str | None) -> list[Instruction]:
    """反復線が支配する場面では、線群自体に間隔差と欠落感を作る。"""
    if not (
        _context_has_motion(ddl)
        or _context_has_marker(ddl, VISUAL_EVENT_CONTEXT_MARKERS)
        or _context_has_marker(ddl, RHYTHM_CONTEXT_MARKERS)
    ):
        return instructions
    if _strict_count_hint_from_ddl(ddl) is not None or _primitive_only_constraint_from_ddl(ddl):
        return instructions

    adjusted: list[Instruction] = []
    for index, ins in enumerate(instructions):
        if ins.arrangement is not None and ins.arrangement.layout == "grid":
            adjusted.append(ins)
            continue
        if ins.primitive != "line" or ins.arrangement is None or _expanded_count(ins) < 6:
            adjusted.append(ins)
            continue
        data = ins.model_dump(by_alias=True)
        arr_data = dict(data["arrangement"])
        changed = False
        if arr_data.get("rhythm_spacing", "none") in ("none", "loose"):
            arr_data["rhythm_spacing"] = "syncopated"
            changed = True
        if float(arr_data.get("margin") or 0.1) < 0.18:
            arr_data["margin"] = 0.18
            changed = True
        if arr_data.get("fade", "none") == "none":
            arr_data["fade"] = "directional"
            changed = True
        if not arr_data.get("preserve_space", False):
            arr_data["preserve_space"] = True
            changed = True
        if arr_data.get("path", "none") == "none":
            arr_data["path"] = "wave" if index % 2 == 0 else "diagonal"
            changed = True
        if ins.from_ is not None and ins.to is not None and _shape_extent(ins) >= 0.35:
            offset = 0.035 if index % 2 == 0 else -0.035
            data["from"] = [_clamp_unit(float(ins.from_[0]) + 0.04), _clamp_unit(float(ins.from_[1]) + offset)]
            data["to"] = [_clamp_unit(float(ins.to[0]) - 0.10), _clamp_unit(float(ins.to[1]) - offset)]
            changed = True
        if changed:
            data["arrangement"] = arr_data
            _append_note(data, "visual event shaped with syncopated gaps")
            adjusted.append(Instruction.model_validate(data))
        else:
            adjusted.append(ins)
    return adjusted


def _has_angular_event_anchor(instructions: list[Instruction]) -> bool:
    return any(
        ins.primitive in ("square", "triangle", "polygon") and _shape_extent(ins) >= 0.035
        for ins in instructions
    )


def _context_has_strong_vanishing_trace(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    vanish_markers = (
        "消え",
        "消える",
        "消えかけ",
        "ほどけ",
        "薄れ",
        "fade",
        "fading",
        "dissolve",
        "dissolved",
        "vanish",
        "vanishing",
    )
    trace_subject_markers = (
        "足跡",
        "白い息",
        "輪郭",
        "人影",
        "円",
        "跡",
        "footprint",
        "breath",
        "outline",
        "figure",
        "circle",
        "trace",
    )
    return _any_marker_in_text(vanish_markers, ddl, lower) and _any_marker_in_text(trace_subject_markers, ddl, lower)


VISUAL_EVENT_TYPE_MARKERS: dict[str, tuple[tuple[str, ...], ...]] = {
    "shared_object": (
        ("二人", "見知らぬ二人", "別々", "手", "two", "strangers", "hands"),
        ("同じ", "一枚", "別々の端", "same", "opposite edges", "opposite"),
        ("新聞", "地図", "紙", "newspaper", "map", "paper"),
        ("手を伸ば", "分け合", "押さえ", "held", "hold", "reached", "split"),
    ),
    "sound_in_space": (
        ("音", "響", "きし", "鳴", "sound", "sounds", "echo", "creak", "chime", "rang", "ring"),
        ("空間", "奥行", "広が", "測", "示", "倉庫", "部屋", "space", "depth", "wide", "measure", "measured", "showed", "warehouse", "room"),
    ),
    "vanishing_outline": (
        ("消え", "現れ", "現れて", "戻", "霧", "霞", "輪郭", "outline", "appeared", "disappeared", "dissolved", "returned", "fog", "mist"),
        ("輪郭", "影", "友人", "人影", "先", "outline", "figure", "friend", "ahead", "trace"),
    ),
    "inherited_memory": (
        ("祖母", "父", "祖父", "父の父", "grandmother", "father", "grandfather"),
        ("植え", "今も", "そうして", "昨日", "記憶", "planted", "still stands", "did", "yesterday", "memory"),
    ),
    "anticipatory_shift": (
        ("先に", "前に", "before", "ahead"),
        ("持ち上", "届", "満た", "明るく", "帰", "rose", "arrived", "filled", "lit up", "returned"),
    ),
    "temporal_chain": (
        ("順に", "一斉", "その後", "あとで", "また", "in order", "again and again", "at once"),
        ("揺", "渡り", "動", "猫", "窓", "笛", "whistle", "moving", "moved", "crossed", "cat", "laundry", "window"),
    ),
    "brief_arrival_departure": (
        ("舞い降り", "降り", "landed", "arrived"),
        ("飛び去", "去っ", "left", "departed"),
        ("カラス", "鳥", "crow", "bird"),
    ),
}


def _has_temporal_chain_evidence(text: str, lower: str) -> bool:
    sequence = _any_marker_in_text(
        ("順に", "一斉", "その後", "あとで", "また", "in order", "again and again", "at once"),
        text,
        lower,
    )
    action = _any_marker_in_text(
        ("揺", "渡り", "動", "犬", "羊", "猫", "窓", "笛", "whistle", "moving", "moved", "crossed", "dog", "flock", "cat", "laundry", "window"),
        text,
        lower,
    )
    if sequence and action:
        return True

    before_after = _any_marker_in_text(("先に", "before", "after"), text, lower)
    reaction = _any_marker_in_text(
        ("一斉", "順に", "その瞬間", "looked up", "at once", "dog moved", "flock moved", "moving the"),
        text,
        lower,
    )
    return before_after and reaction and action


def _detect_visual_event_type(ddl: str | None) -> str | None:
    if not ddl:
        return None
    lower = ddl.lower()
    for event_type, evidence_groups in VISUAL_EVENT_TYPE_MARKERS.items():
        if event_type == "temporal_chain":
            if _has_temporal_chain_evidence(ddl, lower):
                return event_type
            continue
        if event_type == "anticipatory_shift" and _any_marker_in_text(
            ("発車ベル", "案内板", "departure board", "bell"),
            ddl,
            lower,
        ):
            continue
        if all(_any_marker_in_text(group, ddl, lower) for group in evidence_groups):
            return event_type
    return None


def _visual_event_recipe(
    event_type: str,
    *,
    color: str,
    background: str,
) -> Instruction | None:
    visible = color if color != background else VISIBLE_ON_BACKGROUND.get(background, "black")
    event_cycle = [visible, "gray"] if visible != "gray" else ["gray", "black"]
    if event_type == "shared_object":
        return Instruction.model_validate(
            {
                "primitive": "square",
                "position": [0.31, 0.58],
                "size": [0.18, 0.055],
                "rotation": -8,
                "color": visible,
                "weight": "brush_thin",
                "note": "visual event type shared_object restored as a shared surface hinge",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "left_to_right",
                    "color_cycle": event_cycle,
                    "margin": 0.24,
                    "center": [0.68, 0.36],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "syncopated",
                },
            }
        )
    if event_type == "sound_in_space":
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": [0.63, 0.40],
                "radius": 0.066,
                "angle_start": 18,
                "angle_end": 214,
                "rotation": -20,
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event type sound_in_space restored as a spatial echo",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "wave",
                    "color_cycle": event_cycle,
                    "margin": 0.24,
                    "center": [0.34, 0.68],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    if event_type == "vanishing_outline":
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [0.36, 0.54],
                "to": [0.70, 0.38],
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event type vanishing_outline restored as a fading contour",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "diagonal",
                    "margin": 0.26,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    if event_type == "inherited_memory":
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": [0.56, 0.45],
                "radius": 0.092,
                "angle_start": 24,
                "angle_end": 232,
                "rotation": 15,
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event type inherited_memory restored as a three-part memory sequence",
                "arrangement": {
                    "count": 3,
                    "layout": "scatter",
                    "path": "diagonal",
                    "color_cycle": event_cycle,
                    "margin": 0.24,
                    "center": [0.32, 0.64],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    if event_type == "temporal_chain":
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [0.36, 0.52],
                "to": [0.72, 0.39],
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event type temporal_chain restored as an ordered reaction path",
                "arrangement": {
                    "count": 3,
                    "layout": "scatter",
                    "path": "diagonal",
                    "color_cycle": event_cycle,
                    "margin": 0.24,
                    "center": [0.32, 0.64],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "syncopated",
                },
            }
        )
    if event_type == "anticipatory_shift":
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": [0.58, 0.34],
                "radius": 0.084,
                "angle_start": 18,
                "angle_end": 206,
                "rotation": -22,
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event type anticipatory_shift restored as an early hinge",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "wave",
                    "color_cycle": event_cycle,
                    "margin": 0.24,
                    "center": [0.34, 0.66],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "syncopated",
                },
            }
        )
    if event_type == "brief_arrival_departure":
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": [0.64, 0.36],
                "radius": 0.074,
                "angle_start": 32,
                "angle_end": 238,
                "rotation": -26,
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event type brief_arrival_departure restored as an arrival-leaving trace",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "diagonal",
                    "color_cycle": event_cycle,
                    "margin": 0.26,
                    "center": [0.33, 0.67],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "syncopated",
                },
            }
        )
    return None


def _visual_event_instruction(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    color: str,
    background: str,
) -> Instruction:
    lower = (ddl or "").lower()
    source = ddl or ""
    visible = color if color != background else VISIBLE_ON_BACKGROUND.get(background, "black")
    event_type = _detect_visual_event_type(ddl)
    if event_type is not None:
        event = _visual_event_recipe(event_type, color=color, background=background)
        if event is not None:
            return event
    if _any_marker_in_text(("同じ新聞", "手を伸ば", "分け合", "一言も交わさず"), source, lower):
        return Instruction.model_validate(
            {
                "primitive": "square",
                "position": [0.45, 0.45],
                "size": [0.18, 0.055],
                "rotation": -8,
                "color": visible,
                "weight": "brush_thin",
                "note": "visual event restored as a shared newspaper hinge",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "left_to_right",
                    "margin": 0.24,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "syncopated",
                },
            }
        )
    if _any_marker_in_text(("高い窓", "午後の光", "読まない本", "斜めに落ち"), source, lower):
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [0.33, 0.24],
                "to": [0.68, 0.63],
                "color": "white" if background != "white" else visible,
                "weight": "silverpoint",
                "note": "visual event restored as diagonal afternoon light",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "diagonal",
                    "margin": 0.26,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    if _any_marker_in_text(("festival", "dancers", "moved his feet", "under the table"), source, lower):
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": [0.55, 0.63],
                "radius": 0.075,
                "angle_start": 205,
                "angle_end": 342,
                "rotation": 10,
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event restored as hidden foot rhythm",
                "arrangement": {
                    "count": 3,
                    "layout": "scatter",
                    "path": "wave",
                    "margin": 0.25,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "syncopated",
                },
            }
        )
    if _any_marker_in_text(("line of birds", "river surface", "another road", "鳥の列", "川面", "もう一つの道"), source, lower):
        event_cycle = [visible, "gray"] if visible != "gray" else ["gray", "black"]
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [0.27, 0.34],
                "to": [0.45, 0.38],
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event restored as doubled river road",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "diagonal",
                    "color_cycle": event_cycle,
                    "margin": 0.25,
                    "center": [0.72, 0.68],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    if _any_marker_in_text(("発車ベル", "案内板", "明るくな", "departure board", "lit up", "bell"), source, lower):
        event_cycle = ["blue", "gray"] if background != "blue" else [visible, "gray"]
        return Instruction.model_validate(
            {
                "primitive": "square",
                "position": [0.58, 0.27],
                "size": [0.16, 0.072],
                "rotation": -6,
                "color": "blue" if background != "blue" else visible,
                "weight": "brush_thin",
                "note": "visual event restored as a pre-bell light hinge",
                "arrangement": {
                    "count": 1,
                    "layout": "scatter",
                    "path": "diagonal",
                    "color_cycle": event_cycle,
                    "center": [0.34, 0.66],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "syncopated",
                },
            }
        )
    if _any_marker_in_text(("礼をする", "父も", "父の父", "毎朝", "bow", "bows", "father did", "father's father", "each morning"), source, lower):
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": [0.56, 0.45],
                "radius": 0.096,
                "angle_start": 24,
                "angle_end": 232,
                "rotation": 15,
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event restored as an inherited bow sequence",
                "arrangement": {
                    "count": 3,
                    "layout": "scatter",
                    "path": "diagonal",
                    "margin": 0.24,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    if _any_marker_in_text(("whistled", "whistle", "dog moved", "flock moved", "listen", "口笛", "犬が動", "羊の群れ"), source, lower):
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [0.39, 0.48],
                "to": [0.72, 0.36],
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event restored as a chain reaction",
                "arrangement": {
                    "count": 3,
                    "layout": "scatter",
                    "path": "diagonal",
                    "margin": 0.24,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "syncopated",
                },
            }
        )
    if _any_marker_in_text(("tatami", "tilted the quiet", "whole room", "部屋全体", "傾け"), source, lower):
        event_cycle = [visible, "gray"] if visible != "gray" else ["gray", "black"]
        return Instruction.model_validate(
            {
                "primitive": "ellipse",
                "center": [0.56, 0.49],
                "size": [0.11, 0.034],
                "rotation": -16,
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event restored as a tilted-room drop",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "wave",
                    "color_cycle": event_cycle,
                    "margin": 0.24,
                    "center": [0.34, 0.68],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    if _any_marker_in_text(("scent", "fragrance", "grass"), source, lower):
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": [0.64, 0.42],
                "radius": 0.058,
                "angle_start": 15,
                "angle_end": 185,
                "rotation": -26,
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event restored as a small sensory drift",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "wave",
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    if _any_marker_in_text(("雨", "反射", "透明", "滲", "rain", "reflection", "reflections", "transparent", "window"), source, lower):
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [0.54, 0.42],
                "to": [0.75, 0.38],
                "color": "blue" if background != "blue" else "white",
                "weight": "silverpoint",
                "note": "visual event restored as a thin reflected cut",
                "arrangement": {"count": 1, "layout": "scatter", "density": "low", "fade": "outward", "preserve_space": True},
            }
        )
    if _any_marker_in_text(
        ("地平", "水平", "余白", "静か", "horizon", "prairie", "open road", "negative space", "quiet"),
        source,
        lower,
    ):
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [0.60, 0.61],
                "to": [0.71, 0.58],
                "color": visible,
                "weight": "brush_thin",
                "note": "visual event restored as a small broken line",
                "arrangement": {"count": 1, "layout": "scatter", "density": "low", "fade": "outward", "preserve_space": True},
            }
        )
    if _any_marker_in_text(("光", "灯", "月", "light", "moon", "neon", "sign"), source, lower):
        return Instruction.model_validate(
            {
                "primitive": "square",
                "position": [0.64, 0.28],
                "size": [0.11, 0.065],
                "rotation": -18,
                "color": visible,
                "weight": "brush_thin",
                "note": "visual event restored as a small light plane",
                "arrangement": {"count": 1, "layout": "scatter", "density": "low", "fade": "outward", "preserve_space": True},
            }
        )
    if _any_marker_in_text(("jazz", "syncopated", "backbeat", "blue-note", "improvised"), source, lower):
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": [0.66, 0.38],
                "radius": 0.06,
                "angle_start": 20,
                "angle_end": 210,
                "rotation": 24,
                "color": visible,
                "weight": "silverpoint",
                "note": "visual event restored as a small offbeat arc",
                "arrangement": {"count": 1, "layout": "scatter", "density": "low", "fade": "outward", "preserve_space": True},
            }
        )
    if _any_marker_in_text(("quilt", "patchwork", "handmade", "folk"), source, lower):
        anchor = _instruction_anchor(instructions[0]) if instructions else (0.58, 0.42)
        return Instruction.model_validate(
            {
                "primitive": "square",
                "position": _offset_from_anchor(anchor, ddl=ddl, salt="rhythm-offset", distance=0.075),
                "size": [_seed_float(ddl, "rhythm-offset-w", 0.058, 0.086), _seed_float(ddl, "rhythm-offset-h", 0.04, 0.064)],
                "rotation": _seed_choice(ddl, "rhythm-offset-rotation", (-28, -14, 12, 22, 34)),
                "color": visible,
                "weight": "brush_thin",
                "note": "visual event restored as a small handmade rhythm offset",
                "arrangement": {
                    "count": 2,
                    "layout": "scatter",
                    "path": "diagonal",
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "syncopated",
                },
            }
        )
    if not _has_angular_event_anchor(instructions):
        anchor = _instruction_anchor(instructions[0]) if instructions else (0.62, 0.40)
        cx, cy = _offset_from_anchor(anchor, ddl=ddl, salt="compact-event", distance=0.092)
        length = _seed_float(ddl, "compact-event-length", 0.10, 0.16)
        slant = _seed_choice(ddl, "compact-event-slant", (-1, 1))
        event_cycle = [visible, "gray"] if visible != "gray" else ["gray", "black"]
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [_clamp_unit(cx - length / 2), _clamp_unit(cy + slant * length * 0.16)],
                "to": [_clamp_unit(cx + length / 2), _clamp_unit(cy - slant * length * 0.16)],
                "rotation": _seed_choice(ddl, "compact-event-rotation", (-24, -10, 12, 26)),
                "color": visible,
                "weight": "brush_thin",
                "note": "visual event restored as a compact off-center mark",
                "arrangement": {
                    "count": 1,
                    "layout": "scatter",
                    "path": "diagonal",
                    "color_cycle": event_cycle,
                    "center": [
                        _clamp_unit(1.0 - cx + _seed_float(ddl, "compact-event-center-x", -0.035, 0.035)),
                        _clamp_unit(1.0 - cy + _seed_float(ddl, "compact-event-center-y", -0.035, 0.035)),
                    ],
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    return Instruction.model_validate(
        {
            "primitive": "arc",
            "center": _offset_from_anchor(_instruction_anchor(instructions[0]) if instructions else (0.62, 0.40), ddl=ddl, salt="focal-pulse", distance=0.075),
            "radius": _seed_float(ddl, "focal-pulse-radius", 0.044, 0.066),
            "angle_start": _seed_choice(ddl, "focal-pulse-angle-start", (18, 28, 35, 46)),
            "angle_end": _seed_choice(ddl, "focal-pulse-angle-end", (192, 220, 245, 272)),
            "rotation": _seed_choice(ddl, "focal-pulse-rotation", (-28, -12, 8, 22)),
            "color": color,
            "weight": "silverpoint",
            "note": "visual event restored as a small focal pulse",
            "arrangement": {"count": 1, "layout": "scatter", "density": "low", "fade": "outward", "preserve_space": True},
        }
    )


def _with_visual_event(instructions: list[Instruction], *, ddl: str | None, background: str) -> list[Instruction]:
    """抽象画としての見せ場を、既存語彙に足りない形で小さく補う。"""
    event_type = _detect_visual_event_type(ddl)
    if not _context_has_marker(ddl, VISUAL_EVENT_CONTEXT_MARKERS) and event_type is None:
        return instructions
    if _strict_count_hint_from_ddl(ddl) is not None or _primitive_only_constraint_from_ddl(ddl):
        return instructions
    if any("visual event restored" in (ins.note or "") for ins in instructions):
        return instructions
    if len(instructions) >= 10:
        return instructions

    requested = [color for color in _color_repair_order(_requested_colors_from_ddl(ddl)) if color != background]
    color = requested[0] if requested else ("blue" if background != "blue" else VISIBLE_ON_BACKGROUND.get(background, "black"))
    accent = _visual_event_instruction(instructions, ddl=ddl, color=color, background=background)
    return [*instructions, accent]


def _with_visual_event_type_hints(instructions: list[Instruction], *, ddl: str | None) -> list[Instruction]:
    event_type = _detect_visual_event_type(ddl)
    if event_type is None:
        return instructions
    if any(event_type in (ins.note or "") for ins in instructions):
        return instructions

    adjusted: list[Instruction] = []
    applied = False
    note = f"visual event type {event_type} detected through abstract event evidence"
    for ins in instructions:
        data = ins.model_dump(by_alias=True)
        if not applied and _has_focal_event_hint(ins):
            _append_note(data, note)
            applied = True
        adjusted.append(Instruction.model_validate(data))
    if applied:
        return adjusted
    return instructions


def _with_crescent_sensory_suppression(instructions: list[Instruction], *, ddl: str | None, background: str) -> list[Instruction]:
    if not ddl or "crescent" not in ddl.lower():
        return instructions

    adjusted: list[Instruction] = []
    for ins in instructions:
        descriptive_hint = (ins.color_hint or "").lower()
        if "five-sense" in descriptive_hint or "scent layer" in descriptive_hint:
            continue
        if "crescent" in descriptive_hint and "sensory layer" in descriptive_hint and ins.color == "green":
            data = ins.model_dump(by_alias=True)
            data["color"] = "blue" if background != "blue" else "white"
            if isinstance(data.get("note"), str):
                data["note"] = (
                    data["note"]
                    .replace("white sensory layer made visible as pale green", "crescent white layer kept abstract")
                    .replace("pale green", "pale blue")
                )
            arrangement = data.get("arrangement")
            if isinstance(arrangement, dict):
                arrangement["color_cycle"] = [
                    item for item in (arrangement.get("color_cycle") or []) if item != "green"
                ]
            _append_note(data, "crescent sensory color suppressed")
            adjusted.append(Instruction.model_validate(data))
            continue
        adjusted.append(ins)
    return adjusted or instructions


def _with_ma_pressure(instructions: list[Instruction], *, ddl: str | None) -> list[Instruction]:
    """余白・間の文脈では描画数を増やさず、配置余白と薄れ方で圧を作る。"""
    if not _context_has_marker(ddl, MA_PRESSURE_CONTEXT_MARKERS):
        return instructions

    adjusted: list[Instruction] = []
    for ins in instructions:
        if ins.arrangement is None or ins.arrangement.layout == "grid":
            adjusted.append(ins)
            continue
        data = ins.model_dump(by_alias=True)
        arr_data = dict(data["arrangement"])
        changed = False
        if not arr_data.get("preserve_space", False):
            arr_data["preserve_space"] = True
            changed = True
        if float(arr_data.get("margin") or 0.1) < 0.22:
            arr_data["margin"] = 0.22
            changed = True
        if arr_data.get("fade", "none") == "none":
            arr_data["fade"] = "outward"
            changed = True
        if arr_data.get("density", "none") == "none":
            arr_data["density"] = "low"
            changed = True
        if changed:
            data["arrangement"] = arr_data
            note = "ma pressure restored through spacing and preserved negative space"
            _append_note(data, note)
            adjusted.append(Instruction.model_validate(data))
        else:
            adjusted.append(ins)
    return adjusted


def _with_semantic_visual_event_hints(instructions: list[Instruction], *, ddl: str | None) -> list[Instruction]:
    """言語別markerで、既存要素に含まれる意味上の見せ場を明示する。"""
    if not SEMANTIC_VISUAL_EVENT_HINTS:
        return instructions

    source = ddl or ""
    lower_source = source.lower()
    adjusted = instructions
    for markers, note in SEMANTIC_VISUAL_EVENT_HINTS:
        if note in " ".join(ins.note or "" for ins in adjusted):
            continue
        if not _any_marker_in_text(markers, source, lower_source):
            continue

        next_instructions: list[Instruction] = []
        applied = False
        for ins in adjusted:
            data = ins.model_dump(by_alias=True)
            description_hint = data.get("color_hint") or ""
            marker_in_hint = _any_marker_in_text(markers, description_hint, description_hint.lower())
            machine_note = data.get("note") or ""
            if not applied and marker_in_hint and "visual event" not in machine_note.lower():
                _append_note(data, note)
                applied = True
            next_instructions.append(Instruction.model_validate(data))
        adjusted = next_instructions
    return adjusted


FOCAL_EVENT_MIN_EXTENT = 0.075


FOCAL_EVENT_MIN_LINE_EXTENT = 0.14


def _has_focal_event_hint(ins: Instruction) -> bool:
    hint = (ins.note or "").lower()
    return any(
        marker in hint
        for marker in (
            "visual event",
            "vanishing trace",
            "edge light event",
            "playful motion",
            "motion floor",
            "surface tension",
            "action residue",
            "temporal hinge",
            "presence weight",
        )
    )


def _instruction_anchor(ins: Instruction) -> tuple[float, float]:
    if ins.primitive == "line" and ins.from_ is not None and ins.to is not None:
        return ((ins.from_[0] + ins.to[0]) / 2, (ins.from_[1] + ins.to[1]) / 2)
    if ins.primitive in ("circle", "ellipse", "arc", "polygon", "cloudform") and ins.center is not None:
        return ins.center
    if ins.primitive in ("square", "triangle") and ins.position is not None and ins.size is not None:
        return (ins.position[0] + ins.size[0] / 2, ins.position[1] + ins.size[1] / 2)
    return (0.62, 0.40)


def _opposes_anchor(anchor: tuple[float, float], center: tuple[float, float] | None) -> bool:
    if center is None:
        return False
    ax, ay = anchor
    cx, cy = center
    return (
        (ax - 0.5) * (cx - 0.5) <= 0
        and (ay - 0.5) * (cy - 0.5) <= 0
        and abs(ax - cx) >= 0.25
        and abs(ay - cy) >= 0.25
    )


def _counterweight_center_for_anchor(anchor: tuple[float, float], *, ddl: str | None, salt: str) -> list[float]:
    ax, ay = anchor
    x_base = (
        _seed_float(ddl, f"{salt}-counter-x", 0.18, 0.32)
        if ax >= 0.5
        else _seed_float(ddl, f"{salt}-counter-x", 0.68, 0.82)
    )
    y_base = (
        _seed_float(ddl, f"{salt}-counter-y", 0.18, 0.32)
        if ay >= 0.5
        else _seed_float(ddl, f"{salt}-counter-y", 0.68, 0.82)
    )
    if abs(ax - x_base) < 0.25:
        x_base = 0.18 if ax >= 0.5 else 0.82
    if abs(ay - y_base) < 0.25:
        y_base = 0.18 if ay >= 0.5 else 0.82
    return [_clamp_unit(x_base), _clamp_unit(y_base)]


def _event_color_cycle(color: str, background: str) -> list[str]:
    visible = VISIBLE_ON_BACKGROUND.get(background, "black")
    cycle: list[str] = []
    for item in (color, visible, "gray", "black", "white"):
        if item != background and item not in cycle:
            cycle.append(item)
        if len(cycle) >= 2:
            break
    return cycle or [visible]


def _with_existing_event_counterweight(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
) -> list[Instruction]:
    event_type = _detect_visual_event_type(ddl)
    has_context = _context_has_marker(ddl, VISUAL_EVENT_CONTEXT_MARKERS) or event_type is not None
    has_existing_event = any(_has_focal_event_hint(ins) for ins in instructions)
    has_compact_mark = any(
        "small focal mark kept compact" in (ins.note or "").lower()
        or "circle focal mark kept compact" in (ins.note or "").lower()
        for ins in instructions
    )
    if not has_existing_event and not (has_context and has_compact_mark):
        return instructions

    support_index: int | None = None
    if event_type == "inherited_memory" and has_existing_event:
        for candidate_index, candidate in enumerate(instructions):
            candidate_hint = (candidate.note or "").lower()
            if _has_focal_event_hint(candidate):
                continue
            if "small focal mark kept compact" in candidate_hint or "circle focal mark kept compact" in candidate_hint:
                continue
            if _shape_extent(candidate) > 0.0:
                support_index = candidate_index
                break

    adjusted: list[Instruction] = []
    for index, ins in enumerate(instructions):
        if ins.arrangement is not None and ins.arrangement.layout == "grid":
            adjusted.append(ins)
            continue
        hint = (ins.note or "").lower()
        compact_mark = "small focal mark kept compact" in hint or "circle focal mark kept compact" in hint
        focal_event = _has_focal_event_hint(ins)
        supporting_event = index == support_index
        if not focal_event and not compact_mark and not supporting_event:
            adjusted.append(ins)
            continue

        data = ins.model_dump(by_alias=True)
        arr_data = dict(data.get("arrangement") or {"count": 1, "layout": "scatter"})
        anchor = _instruction_anchor(ins)
        arr_center = arr_data.get("center")
        parsed_center: tuple[float, float] | None = None
        if isinstance(arr_center, (list, tuple)) and len(arr_center) == 2:
            parsed_center = (float(arr_center[0]), float(arr_center[1]))
        if not _opposes_anchor(anchor, parsed_center):
            arr_data["center"] = _counterweight_center_for_anchor(anchor, ddl=ddl, salt=f"event-{index}")
        if not arr_data.get("color_cycle"):
            arr_data["color_cycle"] = _event_color_cycle(str(data.get("color") or "black"), background)
        if arr_data.get("path", "none") == "none":
            arr_data["path"] = _seed_choice(ddl, f"event-{index}-path", ("diagonal", "wave", "left_to_right"))
        if arr_data.get("rhythm_spacing", "none") == "none":
            arr_data["rhythm_spacing"] = "loose"
        if arr_data.get("density", "none") == "none":
            arr_data["density"] = "low"
        if arr_data.get("fade", "none") == "none":
            arr_data["fade"] = "outward"
        if float(arr_data.get("margin") or 0.1) < 0.22:
            arr_data["margin"] = 0.22
        arr_data["preserve_space"] = True
        data["arrangement"] = arr_data
        if compact_mark and not focal_event:
            _append_note(data, "visual event preserved as compact focal accent")
        if supporting_event:
            _append_note(data, "visual event inherited memory trace preserved on existing support")
        _append_note(data, "visual event counterweight preserved through opposing placement")
        adjusted.append(Instruction.model_validate(data))
    return adjusted


def _with_minimum_focal_extent(ins: Instruction) -> Instruction:
    hint = (ins.note or "").lower()
    if "small focal mark kept compact" in hint or "circle focal mark kept compact" in hint:
        return ins
    if not _has_focal_event_hint(ins):
        return ins
    if _shape_extent(ins) >= FOCAL_EVENT_MIN_EXTENT:
        return ins

    data = ins.model_dump(by_alias=True)
    changed = False
    if ins.primitive == "line" and ins.from_ is not None and ins.to is not None:
        cx, cy = _instruction_anchor(ins)
        dx = ins.to[0] - ins.from_[0]
        dy = ins.to[1] - ins.from_[1]
        length = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        target = max(FOCAL_EVENT_MIN_LINE_EXTENT, length)
        ux, uy = dx / length, dy / length
        data["from"] = [_clamp_unit(cx - ux * target / 2), _clamp_unit(cy - uy * target / 2)]
        data["to"] = [_clamp_unit(cx + ux * target / 2), _clamp_unit(cy + uy * target / 2)]
        changed = True
    elif ins.primitive in ("circle", "arc", "polygon"):
        data["radius"] = max(float(ins.radius or 0.0), FOCAL_EVENT_MIN_EXTENT / 2)
        changed = True
    elif ins.primitive == "ellipse" and ins.size is not None:
        data["size"] = [
            max(float(ins.size[0]), FOCAL_EVENT_MIN_EXTENT),
            max(float(ins.size[1]), FOCAL_EVENT_MIN_EXTENT * 0.42),
        ]
        changed = True
    elif ins.primitive in ("square", "triangle") and ins.size is not None:
        data["size"] = [
            max(float(ins.size[0]), FOCAL_EVENT_MIN_EXTENT),
            max(float(ins.size[1]), FOCAL_EVENT_MIN_EXTENT * 0.62),
        ]
        changed = True

    if not changed:
        return ins
    _append_note(data, "focal event visibility floor applied")
    return Instruction.model_validate(data)


def _has_adjacent_reaction(instructions: list[Instruction]) -> bool:
    return any("adjacent reaction" in (ins.note or "").lower() for ins in instructions)


def _adjacent_reaction_instruction(
    event: Instruction,
    *,
    ddl: str | None,
    background: str,
) -> Instruction:
    requested = [color for color in _color_repair_order(_requested_colors_from_ddl(ddl)) if color != background]
    color = requested[0] if requested else VISIBLE_ON_BACKGROUND.get(background, "black")
    cx, cy = _instruction_anchor(event)
    rx, ry = _offset_from_anchor((cx, cy), ddl=ddl, salt="adjacent-reaction", distance=_seed_float(ddl, "adjacent-reaction-distance", 0.062, 0.11))
    primitive = _seed_choice(ddl, "adjacent-reaction-primitive", ("arc", "line", "ellipse"))
    data: dict[str, Any] = {
            "primitive": primitive,
            "color": color,
            "weight": "silverpoint",
            "note": "visual event adjacent reaction added to hold focal event",
            "arrangement": {
                "count": _seed_choice(ddl, "adjacent-reaction-count", (1, 2)),
                "layout": "scatter",
                "path": _seed_choice(ddl, "adjacent-reaction-path", ("diagonal", "wave", "left_to_right")),
                "margin": 0.22,
                "density": "low",
                "fade": "outward",
                "preserve_space": True,
                "rhythm_spacing": "loose",
            },
        }
    if primitive == "arc":
        data.update({
            "center": [rx, ry],
            "radius": _seed_float(ddl, "adjacent-reaction-radius", 0.038, 0.066),
            "angle_start": _seed_choice(ddl, "adjacent-reaction-angle-start", (18, 24, 36, 48)),
            "angle_end": _seed_choice(ddl, "adjacent-reaction-angle-end", (156, 192, 216, 244)),
            "rotation": _seed_choice(ddl, "adjacent-reaction-rotation", (-32, -18, -6, 14, 26)),
        })
    elif primitive == "ellipse":
        data.update({
            "center": [rx, ry],
            "size": [_seed_float(ddl, "adjacent-reaction-w", 0.058, 0.092), _seed_float(ddl, "adjacent-reaction-h", 0.018, 0.04)],
            "rotation": _seed_choice(ddl, "adjacent-reaction-ellipse-rotation", (-30, -12, 16, 32)),
        })
    else:
        length = _seed_float(ddl, "adjacent-reaction-line-length", 0.07, 0.13)
        slant = _seed_choice(ddl, "adjacent-reaction-line-slant", (-1, 1))
        data.update({
            "from": [_clamp_unit(rx - length / 2), _clamp_unit(ry + slant * length * 0.18)],
            "to": [_clamp_unit(rx + length / 2), _clamp_unit(ry - slant * length * 0.18)],
        })
    return Instruction.model_validate(data)


def _with_focal_event_floor(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
) -> list[Instruction]:
    """見せ場を密度ではなく、最小視認サイズと近接反応で支える。"""
    event_type = _detect_visual_event_type(ddl)
    if not _context_has_marker(ddl, VISUAL_EVENT_CONTEXT_MARKERS) and event_type is None:
        return instructions
    if _strict_count_hint_from_ddl(ddl) is not None or _primitive_only_constraint_from_ddl(ddl):
        return instructions

    adjusted = [_with_minimum_focal_extent(ins) for ins in instructions]
    if _has_adjacent_reaction(adjusted) or len(adjusted) >= 9:
        return adjusted

    event = next((ins for ins in adjusted if _has_focal_event_hint(ins)), None)
    if event is None:
        return adjusted
    drawable_count = sum(1 for ins in adjusted if _shape_extent(ins) > 0.0)
    if drawable_count > 2 and _has_nearby_contour(adjusted, event):
        return adjusted
    return [*adjusted, _adjacent_reaction_instruction(event, ddl=ddl, background=background)]


def _context_energy_instruction(kind: str, *, background: str, ddl: str | None = None) -> Instruction:
    visible = VISIBLE_ON_BACKGROUND.get(background, "black")
    if kind == "leaf_grain":
        return Instruction.model_validate(
            {
                "primitive": "ellipse",
                "center": [0.42, 0.62],
                "size": [0.045, 0.018],
                "rotation": -28,
                "color": "red" if background != "red" else visible,
                "filled": True,
                "note": "leaf/grain energy restored without density growth",
                "arrangement": {
                    "count": 6,
                    "layout": "scatter",
                    "path": "diagonal",
                    "margin": 0.22,
                    "density": "low",
                    "fade": "directional",
                    "preserve_space": True,
                    "color_cycle": ["red", "gray", "green"] if background not in {"red", "gray", "green"} else [visible],
                },
            }
        )
    if kind == "silence_layer":
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [0.18, 0.70],
                "to": [0.82, 0.38],
                "rotation": -7,
                "color": visible,
                "weight": "silverpoint",
                "note": "silence/layer energy restored as a long optical trace",
                "arrangement": {
                    "count": 4,
                    "layout": "horizontal",
                    "path": "diagonal",
                    "margin": 0.20,
                    "density": "low",
                    "fade": "directional",
                    "preserve_space": True,
                },
            }
        )
    if kind == "hard_edge":
        return Instruction.model_validate(
            {
                "primitive": "polygon",
                "center": [0.66, 0.35],
                "radius": 0.045,
                "sides": 6,
                "rotation": 18,
                "color": "gray" if background != "gray" else visible,
                "weight": "brush_thin",
                "note": "hard edge visual event restored with polygonal rust/steel fragments",
                "arrangement": {
                    "count": 5,
                    "layout": "scatter",
                    "path": "diagonal",
                    "margin": 0.18,
                    "density": "low",
                    "fade": "directional",
                    "preserve_space": True,
                    "color_cycle": ["gray", "black"] if background not in {"gray", "black"} else [visible],
                },
            }
        )
    if kind == "edge_light":
        light_color = "white" if background in {"black", "blue", "red", "green"} else "blue"
        cycle = [light_color, "gray"]
        if background == "white":
            cycle.insert(0, "blue")
        return Instruction.model_validate(
            {
                "primitive": "line",
                "from": [0.58, 0.30],
                "to": [0.84, 0.24],
                "rotation": -8,
                "color": light_color,
                "weight": "silverpoint",
                "note": "edge light event restored as a small cutting point",
                "arrangement": {
                    "count": 2,
                    "layout": "horizontal",
                    "path": "diagonal",
                    "margin": 0.18,
                    "density": "low",
                    "fade": "directional",
                    "preserve_space": True,
                    "color_cycle": cycle,
                },
            }
        )
    if kind == "vanishing_trace":
        trace_color = "blue" if background == "white" else VISIBLE_ON_BACKGROUND.get(background, "white")
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": _offset_from_anchor((0.62, 0.50), ddl=ddl, salt="vanishing-trace", distance=0.11),
                "radius": _seed_float(ddl, "vanishing-trace-radius", 0.056, 0.088),
                "angle_start": _seed_choice(ddl, "vanishing-trace-angle-start", (184, 205, 222, 238)),
                "angle_end": _seed_choice(ddl, "vanishing-trace-angle-end", (292, 315, 334, 350)),
                "rotation": _seed_choice(ddl, "vanishing-trace-rotation", (-32, -18, -4, 16)),
                "color": trace_color,
                "weight": "silverpoint",
                "note": "vanishing trace restored with a fading endpoint",
                "arrangement": {
                    "count": 3,
                    "layout": "scatter",
                    "path": "diagonal",
                    "margin": 0.24,
                    "density": "low",
                    "fade": "directional",
                    "preserve_space": True,
                    "rhythm_spacing": "loose",
                },
            }
        )
    playful_color = "white" if background == "red" else "red" if background != "red" else visible
    return Instruction.model_validate(
        {
            "primitive": "ellipse",
            "center": [0.62, 0.40],
            "size": [0.055, 0.024],
            "rotation": -24,
            "color": playful_color,
            "filled": True,
            "weight": "brush_thick",
            "note": "playful motion energy restored as a small moving color cluster",
            "arrangement": {
                "count": 5,
                "layout": "scatter",
                "path": "wave",
                "margin": 0.20,
                "density": "low",
                "fade": "outward",
                "preserve_space": True,
                "color_cycle": (
                    ["white", "blue", "black"] if background == "red"
                    else ["red", "blue", "white"] if background not in {"red", "blue", "white"}
                    else [playful_color]
                ),
            },
        }
    )


def _has_context_energy(instructions: list[Instruction], kind: str) -> bool:
    marker = kind.replace("_", " ")
    return any(kind in (ins.note or "") or marker in (ins.note or "") for ins in instructions)


def _with_context_energy_repair(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
) -> list[Instruction]:
    """退行しやすい文脈に、密度ではなく局所的な層・粒度・硬さ・喜びを足す。"""
    if not ddl or len(instructions) >= 10:
        return instructions

    repaired = list(instructions)
    candidates: list[tuple[str, tuple[str, ...]]] = [
        ("leaf_grain", LEAF_GRAIN_CONTEXT_MARKERS),
        ("silence_layer", SILENCE_LAYER_CONTEXT_MARKERS),
        ("hard_edge", HARD_EDGE_CONTEXT_MARKERS),
        ("edge_light", EDGE_LIGHT_CONTEXT_MARKERS),
        ("vanishing_trace", VANISHING_TRACE_CONTEXT_MARKERS),
        ("playful_motion", PLAYFUL_MOTION_CONTEXT_MARKERS),
    ]
    for kind, markers in candidates:
        if len(repaired) >= 10:
            break
        if not _context_has_marker(ddl, markers) or _has_context_energy(repaired, kind):
            continue
        if kind == "edge_light":
            if _presence_from_ddl(ddl) is not None:
                continue
            if not _context_has_marker(ddl, STRONG_EDGE_LIGHT_CONTEXT_MARKERS):
                continue
        if kind == "vanishing_trace":
            if _has_context_energy(repaired, "edge_light"):
                continue
            if not _context_has_strong_vanishing_trace(ddl):
                continue
        repaired.append(_context_energy_instruction(kind, background=background, ddl=ddl))
    return repaired


def _has_surface_tension(instructions: list[Instruction]) -> bool:
    return any("surface tension restored" in (ins.note or "") for ins in instructions)


def _with_surface_tension(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
) -> list[Instruction]:
    """大きな面の静けさを壊さず、薄い圧痕で視覚的な持続を足す。"""
    if not _context_has_marker(ddl, SURFACE_TENSION_CONTEXT_MARKERS):
        return instructions
    if _strict_count_hint_from_ddl(ddl) is not None or _primitive_only_constraint_from_ddl(ddl):
        return instructions
    if len(instructions) >= 9 or _has_surface_tension(instructions):
        return instructions
    if background == "white" and not any(_closed_shape_area(ins) >= 0.08 for ins in instructions):
        return instructions

    color = "black" if background != "black" else VISIBLE_ON_BACKGROUND.get(background, "white")
    tension = Instruction.model_validate(
        {
            "primitive": "arc",
            "center": [0.58, 0.62],
            "radius": 0.18,
            "angle_start": 198,
            "angle_end": 342,
            "rotation": -4,
            "color": color,
            "weight": "silverpoint",
            "note": "surface tension restored as a quiet shadow trace",
        }
    )
    return [*instructions, tension]


def _has_compensating_accent(instructions: list[Instruction]) -> bool:
    for ins in instructions:
        if "quiet expression accent restored" in (ins.note or ""):
            return True
    return any(
        (ins.color in {"red", "green", "blue"} and _expanded_count(ins) <= 12 and _closed_shape_area(ins) <= 0.03)
        or (ins.primitive == "arc" and _expanded_count(ins) <= 9)
        for ins in instructions
    )


def _quiet_expression_accent(*, ddl: str | None, background: str) -> Instruction:
    color = "red" if _context_has_colorful_accent(ddl) and background != "red" else "green" if background != "green" else "blue"
    if _context_has_motion(ddl):
        return Instruction.model_validate(
            {
                "primitive": "arc",
                "center": [0.68, 0.34],
                "radius": 0.12,
                "angle_start": 205,
                "angle_end": 325,
                "color": color if color != background else VISIBLE_ON_BACKGROUND.get(background, "black"),
                "weight": "silverpoint",
                "note": "quiet expression accent restored after density governance",
                "arrangement": {
                    "count": 3,
                    "layout": "radial",
                    "margin": 0.24,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                },
            }
        )
    return Instruction.model_validate(
        {
            "primitive": "ellipse",
            "center": [0.67, 0.35],
            "size": [0.055, 0.026],
            "rotation": -18,
            "color": color if color != background else VISIBLE_ON_BACKGROUND.get(background, "black"),
            "weight": "pencil",
            "filled": True,
            "note": "quiet expression accent restored after density governance",
        }
    )


def _with_quiet_expression_compensation(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
    governed_count: int,
) -> list[Instruction]:
    if governed_count == 0 or not _context_has_density_governor(ddl) or _has_compensating_accent(instructions):
        return instructions
    if len(instructions) >= 8:
        return instructions
    return [*instructions, _quiet_expression_accent(ddl=ddl, background=background)]


def _with_context_density_governor(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
    allow_accent: bool = True,
) -> list[Instruction]:
    """静けさ・膜・記憶系の入力で、密度や大きな反復面が主題を上書きするのを抑える。"""
    if not _context_has_density_governor(ddl):
        return instructions

    has_vertical_context = _context_has_vertical_density(ddl)
    has_neon_blur_context = _context_has_neon_blur_density(ddl)
    requested_counts = _explicit_counts_from_ddl(ddl)
    adjusted: list[Instruction] = []
    governed_count = 0
    for ins in instructions:
        if ins.arrangement is not None and ins.arrangement.layout == "grid":
            adjusted.append(ins)
            continue
        ins = _with_quiet_symbolic_shape_tempering(ins, ddl=ddl)
        ins = _with_quiet_single_shape_tempering(ins, ddl=ddl)
        ins = _with_unintentional_filled_shape_tempering(ins, ddl=ddl)
        arr = ins.arrangement
        if arr is None:
            adjusted.append(ins)
            continue

        # A count the description stated outright is not the governor's to thin.
        # Quiet is a reading of the scene; "two hundred thirty-three" is not a reading.
        # The shape temperings above still apply: they touch size, not how many.
        if _count_follows_ddl_request(arr.count, requested_counts):
            adjusted.append(ins)
            continue

        is_vertical_arrangement = arr.layout == "vertical" or arr.path == "top_to_bottom"
        is_vertical_load = is_vertical_arrangement or (has_vertical_context and ins.primitive == "line")
        vertical_count_cap = MAX_NEON_BLUR_VERTICAL_COUNT if has_neon_blur_context else MAX_QUIET_VERTICAL_COUNT
        if is_vertical_load and arr.count > vertical_count_cap:
            governed_count += 1
            adjusted.append(
                _with_arrangement_density_governor(
                    ins,
                    count=vertical_count_cap,
                    density="low",
                    fade="directional",
                    note=(
                        "neon blur vertical density governed to keep transparent streaks legible"
                        if has_neon_blur_context
                        else "quiet vertical density governed to keep membrane/space legible"
                    ),
                )
            )
            continue

        if _closed_shape_area(ins) >= 0.04 and arr.count > MAX_QUIET_LARGE_SHAPE_COUNT:
            governed_count += 1
            adjusted.append(
                _with_arrangement_density_governor(
                    ins,
                    count=MAX_QUIET_LARGE_SHAPE_COUNT,
                    density="low",
                    fade="outward",
                    note="quiet large-shape repetition governed to preserve negative space",
                )
            )
            continue

        if arr.count > MAX_QUIET_VISUAL_COUNT:
            governed_count += 1
            count_cap = MAX_NEON_BLUR_VISUAL_COUNT if has_neon_blur_context else MAX_QUIET_VISUAL_COUNT
            adjusted.append(
                _with_arrangement_density_governor(
                    ins,
                    count=count_cap,
                    density="medium" if arr.count >= 120 else "low",
                    fade="outward" if arr.layout == "scatter" else "directional",
                    note=(
                        "neon blur density governed to avoid particle dominance"
                        if has_neon_blur_context
                        else "quiet density governed to preserve lightness"
                    ),
                )
            )
            continue

        adjusted.append(ins)
    if not allow_accent:
        return adjusted
    return _with_quiet_expression_compensation(
        adjusted,
        ddl=ddl,
        background=background,
        governed_count=governed_count,
    )


def _requested_colors_from_ddl(ddl: str | None) -> set[str]:
    if not ddl:
        return set()
    lower = ddl.lower()
    colors: set[str] = set()
    for markers, color in COLOR_MARKERS:
        if _any_marker_in_text(markers, ddl, lower):
            colors.add(color)
    return colors - _negated_colors_from_text(ddl)


def _negated_colors_from_text(text: str | None) -> set[str]:
    if not text:
        return set()
    lower = text.lower()
    return {
        color
        for color, markers in NEGATED_COLOR_MARKERS.items()
        if _any_marker_in_text(markers, text, lower)
    }


def _score_contains_color(instructions: list[Instruction], color: str) -> bool:
    for ins in instructions:
        if ins.color == color:
            return True
        arr = ins.arrangement
        if arr and color in arr.color_cycle:
            return True
    return False


def _score_contains_primary_color(instructions: list[Instruction], color: str) -> bool:
    return any(ins.color == color for ins in instructions)


def _color_repair_order(colors: set[str]) -> list[str]:
    ordered = [color for color in ("red", "blue", "green", "white", "black", "gray") if color in colors]
    return ordered or sorted(colors)


def _green_intent_context(ddl: str | None) -> str | None:
    if not ddl:
        return None
    if "green" in _negated_colors_from_text(ddl):
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
    if "small focal mark kept compact" in (data.get("note") or ""):
        arr_data["density"] = arr_data.get("density") or "low"
        arr_data["fade"] = arr_data.get("fade") or "outward"
        arr_data["preserve_space"] = True
    arr_data["color_cycle"] = cycle
    data["arrangement"] = arr_data
    note = f"{'/'.join(colors)} restored in color_cycle from DDL color intent"
    if green_context:
        note = f"{note}; {green_context}"
    _append_note(data, note)
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


def _with_primary_color_delivery(instructions: list[Instruction], *, ddl: str | None, background: str) -> list[Instruction]:
    """要求色が cycle の補助色だけに留まる場合、主strokeへ昇格して色の読みを強める。"""
    requested = [
        color
        for color in _color_repair_order(_requested_colors_from_ddl(ddl))
        if color != background and color not in {"white"}
    ]
    if not requested:
        return instructions
    if _color_only_constraint_from_ddl(ddl):
        return instructions

    repaired = list(instructions)
    for color in requested:
        if _score_contains_primary_color(repaired, color):
            continue
        candidate_index = next(
            (
                index
                for index, ins in enumerate(repaired)
                if ins.arrangement is not None
                and color in ins.arrangement.color_cycle
                and ins.primitive in ("line", "arc", "ellipse", "square", "triangle", "polygon")
            ),
            -1,
        )
        if candidate_index < 0:
            continue
        data = repaired[candidate_index].model_dump(by_alias=True)
        data["color"] = color
        _append_note(data, f"{color} promoted to primary stroke from DDL color intent")
        repaired[candidate_index] = Instruction.model_validate(data)
    return repaired


def _requested_shapes_from_ddl(ddl: str | None) -> set[str]:
    if not ddl:
        return set()
    lower = ddl.lower()
    shapes: set[str] = set()
    for markers, primitive in SHAPE_INTENT_MARKERS:
        if _any_marker_in_text(markers, ddl, lower):
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
        "note": f"{primitive} restored from DDL shape intent",
    }
    if primitive == "triangle":
        common.update({
            "position": [0.58 - offset, 0.22 + offset],
            "size": [0.18, 0.16],
            "rotation": -18 + index * 11,
        })
    elif primitive == "polygon":
        common.update({
            "center": [0.62 - offset, 0.34 + offset],
            "radius": 0.06,
            "sides": 6,
            "rotation": -18 + index * 13,
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
    for primitive in ("polygon", "triangle", "arc", "square"):
        if primitive not in requested or _score_contains_primitive(repaired, primitive):
            continue
        limit = 8 if primitive in ("triangle", "polygon") else 6
        if len(repaired) >= limit:
            if primitive in ("triangle", "polygon"):
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
        if _any_marker_in_text(markers, ddl, lower):
            motifs.append(motif)
    return motifs


def _score_contains_motif(instructions: list[Instruction], motif: str) -> bool:
    return any(motif in (ins.note or "") for ins in instructions)


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
    source = ddl or ""
    if _any_marker_in_text(("祭", "火", "灯", "温", "赤", "warm", "fire", "light"), source, lower):
        return "red" if background != "red" else "white"
    if _any_marker_in_text(("水", "夜", "湖", "冷", "青", "water", "night", "cold"), source, lower):
        return "blue" if background != "blue" else "white"
    if _any_marker_in_text(("森", "草", "苔", "庭", "竹", "green", "forest", "grass"), source, lower):
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
        "note": "composition anchor restored for shape/color diversity",
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
        "note": "composition accent restored for shape/color diversity",
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
                "note": "leaf_cluster motif restored from DDL intent",
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
                "note": "leaf_cluster motif restored from DDL intent",
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
                "note": "paper_shard motif restored from DDL intent",
            }),
            Instruction.model_validate({
                "primitive": "line",
                "from": [0.55 - offset, 0.43 + offset],
                "to": [0.70 - offset, 0.37 + offset],
                "color": color,
                "weight": "silverpoint",
                "note": "paper_shard motif restored from DDL intent",
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
                "note": "ripple_knot motif restored from DDL intent",
            }),
            Instruction.model_validate({
                "primitive": "ellipse",
                "center": [0.62 - offset, 0.58],
                "size": [0.055, 0.025],
                "rotation": 18,
                "color": color,
                "note": "ripple_knot motif restored from DDL intent",
            }),
        ]
    return [
        Instruction.model_validate({
            "primitive": "triangle",
            "position": [0.50 - offset, 0.27 + offset],
            "size": [0.18, 0.15],
            "rotation": -12,
            "color": color,
            "note": "mountain_sign motif restored from DDL intent",
        }),
        Instruction.model_validate({
            "primitive": "line",
            "from": [0.59 - offset, 0.25 + offset],
            "to": [0.59 - offset, 0.45 + offset],
            "color": color,
            "weight": "silverpoint",
            "note": "mountain_sign motif restored from DDL intent",
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


HUMAN_PRESENCE_MARKERS: tuple[str, ...] = (
    "人", "人物", "人影", "人型", "顔", "表情", "視線", "まなざし", "眼差し", "目線", "誰か", "群衆",
    "human", "person", "people", "figure", "face", "gaze", "look", "crowd",
)


CREATURE_PRESENCE_MARKERS: tuple[str, ...] = (
    "動物", "獣", "鳥", "魚", "犬", "猫", "馬", "鹿", "群れ", "羽", "翼", "尾", "尻尾",
    "animal", "creature", "bird", "fish", "dog", "cat", "horse", "deer", "flock", "herd", "tail", "wing",
)


GROUP_PRESENCE_MARKERS: tuple[str, ...] = (
    "群れ", "群衆", "複数", "集ま", "並ぶ", "crowd", "group", "flock", "herd", "many figures",
)


GAZE_PRESENCE_MARKERS: tuple[str, ...] = (
    "顔", "視線", "まなざし", "眼差し", "目線", "見つめ", "face", "gaze", "look", "stare",
)


SYMMETRY_PRESENCE_MARKERS: tuple[str, ...] = (
    "人型", "顔", "正面", "対称", "figure", "face", "frontal", "symmetry",
)


def _context_has_any(context: str, markers: tuple[str, ...]) -> bool:
    lower = context.lower()
    return _any_marker_in_text(markers, context, lower)


def _presence_center_from_context(context: str) -> list[float] | None:
    lower = context.lower()
    if any(marker in context or marker in lower for marker in ("右上", "upper right")):
        return [0.68, 0.34]
    if any(marker in context or marker in lower for marker in ("左上", "upper left")):
        return [0.32, 0.34]
    if any(marker in context or marker in lower for marker in ("右下", "lower right")):
        return [0.68, 0.66]
    if any(marker in context or marker in lower for marker in ("左下", "lower left")):
        return [0.32, 0.66]
    if any(marker in context or marker in lower for marker in ("右半分", "right half")):
        return [0.68, 0.50]
    if any(marker in context or marker in lower for marker in ("左半分", "left half")):
        return [0.32, 0.50]
    return None


def _presence_from_ddl(ddl: str | None) -> dict | None:
    if not ddl:
        return None
    has_human = _context_has_any(ddl, HUMAN_PRESENCE_MARKERS)
    has_creature = _context_has_any(ddl, CREATURE_PRESENCE_MARKERS)
    if not has_human and not has_creature:
        return None

    has_group = _context_has_any(ddl, GROUP_PRESENCE_MARKERS)
    has_gaze = _context_has_any(ddl, GAZE_PRESENCE_MARKERS)
    kind = "group_like" if has_group else "creature_like" if has_creature and not has_human else "figure_like"
    intensity = "high" if any(marker in ddl for marker in ("強い", "圧力", "濃い")) or any(
        marker in ddl.lower() for marker in ("strong", "pressure", "dense")
    ) else "medium" if has_gaze or has_group else "low"
    contour_density = "high" if has_group else "medium" if has_creature or has_gaze else "low"
    symmetry = "bilateral" if _context_has_any(ddl, SYMMETRY_PRESENCE_MARKERS) else "none"
    gaze_pressure = "medium" if has_gaze else "none"
    presence: dict[str, object] = {
        "kind": kind,
        "intensity": intensity,
        "symmetry": symmetry,
        "gaze_pressure": gaze_pressure,
        "contour_density": contour_density,
    }
    if center := _presence_center_from_context(ddl):
        presence["center"] = center
    return presence


def _ddl_clauses(ddl: str | None) -> list[str]:
    if not ddl:
        return []
    clauses = [part.strip() for part in re.split(r"[。\n;；]+|(?<!\d)\.\s+", ddl) if part.strip()]
    markers = (
        "線", "点", "円", "楕円", "四角", "三角", "多角形", "五角", "六角", "弧", "塗りつぶす", "散らす", "並べる",
        "膜", "霞", "霧", "靄", "気配", "余韻", "反射", "映り", "消え", "滲",
        "光", "陽光", "日差し", "香", "匂", "蕾", "つぼみ", "開花", "五感", "温",
        "line", "dot", "circle", "ellipse", "square", "triangle", "polygon", "arc", "scatter", "fill",
        "membrane", "haze", "fog", "mist", "trace", "reflection", "fade", "fading", "blur",
        "light", "sunlight", "scent", "fragrance", "bud", "bloom", "sense", "warm",
    )
    return [
        clause
        for clause in clauses
        if not (clause.startswith("背景") or clause.lower().startswith("background"))
        and _any_marker_in_text(markers, clause, clause.lower())
    ]


def _color_from_clause(clause: str, background: str) -> str:
    lower = clause.lower()
    negated = _negated_colors_from_text(clause)
    for markers, color in COLOR_MARKERS:
        if color in negated:
            continue
        if any(marker in clause or marker in lower for marker in markers):
            if color != background:
                return color
    return VISIBLE_ON_BACKGROUND.get(background, "black")


def _color_cycle_from_clause(clause: str, background: str) -> list[str]:
    lower = clause.lower()
    negated = _negated_colors_from_text(clause)
    colors: list[str] = []
    for markers, color in COLOR_MARKERS:
        if color == background or color in negated:
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
    if ("多角形" in clause) or ("五角" in clause) or ("六角" in clause) or ("polygon" in lower):
        return "polygon"
    if ("四角" in clause) or ("square" in lower) or ("rectangle" in lower):
        return "square"
    if ("三角" in clause) or ("triangle" in lower):
        return "triangle"
    if ("弧" in clause) or ("arc" in lower):
        return "arc"
    if ("楕円" in clause) or ("ellipse" in lower) or ("oval" in lower):
        return "ellipse"
    if ("点" in clause) or ("円" in clause) or ("dot" in lower) or ("point" in lower) or ("circle" in lower):
        return "circle"
    return "line"


def _is_small_mark_clause(clause: str) -> bool:
    lower = clause.lower()
    size_markers = ("小さ", "細い", "tiny", "small", "little", "thin")
    mark_markers = ("点", "円", "楕円", "dot", "point", "circle", "ellipse", "oval")
    return _any_marker_in_text(size_markers, clause, lower) and _any_marker_in_text(mark_markers, clause, lower)


def _single_mark_count_from_clause(clause: str) -> int | None:
    lower = clause.lower()
    if re.search(r"\b(one|a|single)\b", lower) or any(marker in clause for marker in ("一つ", "一個", "一点", "一本")):
        return 1
    return count_hint_from_ddl(clause)


def _radius_hint_from_clause(clause: str) -> float | None:
    lower = clause.lower()
    match = re.search(r"(?:半径|radius(?:\s+is)?|r)\s*(?:は|=|:)?\s*(0?\.\d+|1(?:\.0+)?)", lower if "radius" in lower else clause)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if value <= 0:
        return None
    return min(value, 0.22)


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
    if _any_marker_in_text(("光", "陽光", "日差し", "柔ら", "light", "sunlight", "soft"), clause, lower):
        return "light"
    if _any_marker_in_text(("香", "匂", "沈丁花", "scent", "fragrance"), clause, lower):
        return "scent"
    if _any_marker_in_text(("蕾", "つぼみ", "開花", "bud", "bloom"), clause, lower):
        return "bud"
    if _any_marker_in_text(("五感", "気配", "訪れ", "sense", "presence", "arrival"), clause, lower):
        return "sense"
    return None


def _fallback_instruction_from_clause(clause: str, *, index: int, background: str) -> Instruction:
    lower = clause.lower()
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
        "note": f"coverage from DDL clause: {clause[:48]}",
    }
    offset = min(index, 4) * 0.09
    if primitive == "line":
        if any(marker in clause or marker in lower for marker in ("画面右端", "右端", "right edge")):
            common.update({"from": [0.88, 0.18 + offset / 2], "to": [0.88, 0.82 - offset / 2], "rotation": 0})
        elif any(marker in clause or marker in lower for marker in ("縦線", "vertical line")):
            x = 0.58 + min(index, 3) * 0.08
            common.update({"from": [x, 0.20 + offset / 2], "to": [x, 0.78 - offset / 2], "rotation": 0})
        elif any(marker in clause or marker in lower for marker in ("横線", "horizontal line")):
            y = 0.38 + min(index, 3) * 0.08
            common.update({"from": [0.16, y], "to": [0.84, y], "rotation": 0})
        else:
            common.update({"from": [0.16 + offset, 0.76 - offset], "to": [0.78, 0.30 + offset], "rotation": -8 + index * 7})
    elif primitive == "arc":
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "radius": 0.11, "angle_start": 210, "angle_end": 330})
    elif primitive == "polygon":
        sides = 6 if ("六角" in clause or "hex" in lower or "mineral" in lower or "鉱物" in clause) else 5
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "radius": 0.055, "sides": sides, "rotation": -18 + index * 9})
    elif primitive == "circle":
        radius = _radius_hint_from_clause(clause) or (0.038 if _is_small_mark_clause(clause) else 0.10)
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "radius": radius})
    elif primitive == "ellipse":
        size = [0.06, 0.032] if _is_small_mark_clause(clause) else [0.16, 0.09]
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "size": size, "rotation": -18 + index * 9})
    else:
        common.update({"position": [0.58 - offset / 2, 0.24 + offset], "size": [0.14, 0.10], "rotation": -12 + index * 8})

    if _is_small_mark_clause(clause):
        common["filled"] = True
        common["arrangement"] = {
            "count": _single_mark_count_from_clause(clause) or 1,
            "layout": "scatter",
            "path": "none",
            "margin": 0.24,
            "density": "low",
            "fade": "outward",
            "preserve_space": True,
            "rhythm_spacing": "none",
        }
        common["note"] = f"{common['note']}; small focal mark kept compact with preserved negative space"
    elif primitive == "circle":
        common["arrangement"] = {
            "count": 1,
            "layout": "scatter",
            "path": "none",
            "margin": 0.24,
            "density": "low",
            "fade": "outward",
            "preserve_space": True,
            "rhythm_spacing": "none",
        }
        common["note"] = f"{common['note']}; circle focal mark kept compact with preserved negative space"

    if any(marker in clause or marker in lower for marker in ("右半分", "right half")):
        if "center" in common:
            common["center"] = [0.66, common["center"][1]]
        elif "position" in common:
            common["position"] = [0.66, common["position"][1]]
    if any(marker in clause or marker in lower for marker in ("右上", "upper right")) and "center" in common:
        common["center"] = [0.68, 0.30]
    elif any(marker in clause or marker in lower for marker in ("上端", "upper edge", "top edge")) and "center" in common:
        common["center"] = [common["center"][0], 0.22]

    count = count_hint_from_ddl(clause)
    cycle = _color_cycle_from_clause(clause, background)
    if count and _is_literal_grid_request(clause):
        common["arrangement"] = {
            "count": min(count, 2000),
            "layout": "grid",
            "jitter": 0.12,
            "margin": 0.08,
        }
    elif count and (("散らす" in clause) or ("scatter" in lower)):
        common["arrangement"] = {"count": min(count, 120), "layout": "scatter", "margin": 0.18}
    elif count and (("並べる" in clause) or ("line up" in lower)):
        common["arrangement"] = {"count": min(count, 80), "layout": "horizontal", "margin": 0.1}
    elif _is_small_mark_clause(clause):
        pass
    elif primitive == "circle" and _radius_hint_from_clause(clause) is not None:
        common["arrangement"] = {
            "count": 1,
            "layout": "scatter",
            "margin": 0.24,
            "density": "low",
            "fade": "outward",
            "preserve_space": True,
        }
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
                "color_hint": "soft light",
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
                "color_hint": "scent layer",
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
                "color_hint": "waiting buds",
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
                "color_hint": "five-sense presence",
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
        common["color_hint"] = "membrane haze"
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
        common["color_hint"] = "reflection"
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
        common["color_hint"] = "fading"
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
    "千": 1000,
}


def _parse_small_japanese_number(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "千":
        return 1000
    if "千" in text:
        head, tail = text.split("千", 1)
        value = (_KANJI_NUMBERS.get(head, 1) if head else 1) * 1000
        rest = _parse_small_japanese_number(tail)
        return value + (rest or 0)
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


def _is_literal_grid_request(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    if any(marker in ddl for marker in ("敷き詰め", "格子状", "格子に", "一面に並", "全面に並")):
        return True
    return re.search(r"\b(?:tile|tiled|tiling)\b", lower) is not None


def _without_spontaneous_grid(
    instructions: list[Instruction],
    *,
    ddl: str | None,
) -> list[Instruction]:
    """Keep grid behind an explicit literal-tiling request boundary."""
    if not ddl or _is_literal_grid_request(ddl):
        return instructions
    adjusted: list[Instruction] = []
    for ins in instructions:
        arr = ins.arrangement
        if arr is None or arr.layout != "grid":
            adjusted.append(ins)
            continue
        data = ins.model_dump(by_alias=True)
        arr_data = dict(data["arrangement"])
        arr_data["layout"] = "scatter"
        arr_data["rows"] = None
        arr_data["cols"] = None
        arr_data["jitter"] = None
        data["arrangement"] = arr_data
        adjusted.append(Instruction.model_validate(data))
    return adjusted


def count_hint_from_ddl(ddl: str) -> int | None:
    """Extract a conservative count hint from a normalized DDL fragment."""
    literal_grid = _is_literal_grid_request(ddl)
    clauses = re.split(r"[。.!?]+", ddl)
    candidates = [clause for clause in clauses if _is_literal_grid_request(clause)] if literal_grid else [ddl]
    pattern = r"(\d{1,4}|[一二三四五六七八九十百千]{1,8})(?:本|個|つ(?!の方向)|点|枚)"
    for candidate in candidates:
        match = re.search(pattern, candidate)
        if not match:
            continue
        value = _parse_small_japanese_number(match.group(1))
        if value is not None:
            maximum = 2000 if literal_grid else 1000
            return min(max(value, 1), maximum)
    return _english_count_hint(ddl)


ENGLISH_SMALL_NUMBERS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


ENGLISH_COUNT_UNITS: dict[str, int] = {
    **ENGLISH_SMALL_NUMBERS,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def _english_count_hint(ddl: str) -> int | None:
    literal_grid = _is_literal_grid_request(ddl)
    clauses = re.split(r"[.!?]+", ddl)
    candidates = [clause for clause in clauses if _is_literal_grid_request(clause)] if literal_grid else [ddl]
    words = re.findall(r"[a-z]+", " ".join(candidates).lower().replace("-", " "))
    count_nouns = {
        "line", "lines", "stroke", "strokes", "square", "squares",
        "cloudform", "cloudforms", "tile", "tiles", "brick", "bricks",
    }
    number_words = set(ENGLISH_COUNT_UNITS) | {"hundred", "thousand", "and"}
    for start, word in enumerate(words):
        if word not in number_words or word == "and":
            continue
        end = start
        phrase: list[str] = []
        while end < len(words) and words[end] in number_words:
            phrase.append(words[end])
            end += 1
        if not any(noun in count_nouns for noun in words[end : end + 9]):
            continue
        total = 0
        current = 0
        for token in phrase:
            if token == "and":
                continue
            if token == "hundred":
                current = max(current, 1) * 100
            elif token == "thousand":
                total += max(current, 1) * 1000
                current = 0
            else:
                current += ENGLISH_COUNT_UNITS[token]
        value = total + current
        if value:
            maximum = 2000 if _is_literal_grid_request(ddl) else 1000
            return min(max(value, 1), maximum)
    return None


def _parse_count_token(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    if token in ENGLISH_SMALL_NUMBERS:
        return ENGLISH_SMALL_NUMBERS[token]
    return _parse_small_japanese_number(token)


COUNTED_OBJECT_WORDS: frozenset[str] = frozenset(
    {
        "line", "lines", "stroke", "strokes", "square", "squares", "circle", "circles",
        "ellipse", "ellipses", "oval", "ovals", "triangle", "triangles", "arc", "arcs",
        "polygon", "polygons", "cloudform", "cloudforms", "dot", "dots", "mark", "marks",
        "point", "points", "tile", "tiles", "brick", "bricks", "shape", "shapes",
    }
)

JAPANESE_COUNT_PATTERN = re.compile(r"(\d{1,4}|[一二三四五六七八九十百千]{1,8})(?:本|個|つ(?!の方向)|点|枚)")

# The description asked for a number, so the number is not a guess to be second-guessed.
# 240 is where coerce itself stops expanding (MAX_EXPANDED_PER_INSTRUCTION); above it the
# prompt asks Stage 2 for a representative 80-120 instead of the literal value.
LITERAL_COUNT_THRESHOLD = MAX_EXPANDED_PER_INSTRUCTION
REPRESENTED_COUNT_RANGE = (80, 120)


def _explicit_counts_from_ddl(ddl: str | None) -> frozenset[int]:
    """Every count the description states outright, in either language.

    `count_hint_from_ddl` answers "what is the count here" and stops at the first
    match. This answers "which counts were asked for at all", which is what tells a
    group written to order apart from one a governor is free to thin.
    """
    if not ddl:
        return frozenset()
    counts: set[int] = set()
    for token in JAPANESE_COUNT_PATTERN.findall(ddl):
        value = _parse_small_japanese_number(token)
        if value:
            counts.add(value)
    words = re.findall(r"[a-z]+", ddl.lower().replace("-", " "))
    number_words = set(ENGLISH_COUNT_UNITS) | {"hundred", "thousand", "and"}
    index = 0
    while index < len(words):
        if words[index] not in number_words or words[index] == "and":
            index += 1
            continue
        end = index
        phrase: list[str] = []
        while end < len(words) and words[end] in number_words:
            phrase.append(words[end])
            end += 1
        if any(word in COUNTED_OBJECT_WORDS for word in words[end : end + 9]):
            total = 0
            current = 0
            for token in phrase:
                if token == "and":
                    continue
                if token == "hundred":
                    current = max(current, 1) * 100
                elif token == "thousand":
                    total += max(current, 1) * 1000
                    current = 0
                else:
                    current += ENGLISH_COUNT_UNITS[token]
            if total + current:
                counts.add(total + current)
        index = end
    return frozenset(counts)


def _count_follows_ddl_request(count: int, requested: frozenset[int]) -> bool:
    """Is this count the one the description asked for, literally or as its stand-in?"""
    if count in requested:
        return True
    low, high = REPRESENTED_COUNT_RANGE
    if low <= count <= high:
        return any(value >= LITERAL_COUNT_THRESHOLD for value in requested)
    return False


def _strict_count_hint_from_ddl(ddl: str | None) -> int | None:
    if not ddl:
        return None
    lower = ddl.lower()
    patterns = (
        r"(\d{1,3}|[一二三四五六七八九十百]{1,8})(?:本|個|つ|点|枚)?(?:だけ|のみ)",
        r"(?:only|just)\s+(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\b",
        r"\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:only|just)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, lower if "only" in pattern or "just" in pattern else ddl)
        if not match:
            continue
        value = _parse_count_token(match.group(1))
        if value is not None:
            return min(max(value, 1), 1000)
    return None


ONLY_PRIMITIVE_MARKERS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("円だけ", "円のみ", "丸だけ", "丸のみ", "circle only", "circles only", "only circle", "only circles"), ("circle",)),
    (("楕円だけ", "楕円のみ", "oval only", "ovals only", "ellipse only", "ellipses only"), ("ellipse",)),
    (("線だけ", "線のみ", "line only", "lines only", "only line", "only lines"), ("line",)),
    (("四角だけ", "四角のみ", "square only", "squares only", "rectangle only", "only squares"), ("square",)),
    (("三角だけ", "三角のみ", "triangle only", "triangles only", "only triangles"), ("triangle",)),
    (("多角形だけ", "多角形のみ", "polygon only", "polygons only", "only polygons"), ("polygon",)),
    (("弧だけ", "弧のみ", "arc only", "arcs only", "only arcs"), ("arc",)),
)


def _primitive_only_constraint_from_ddl(ddl: str | None) -> set[str]:
    if not ddl:
        return set()
    lower = ddl.lower()
    primitives: set[str] = set()
    for markers, allowed in ONLY_PRIMITIVE_MARKERS:
        if any(marker in ddl or marker in lower for marker in markers):
            primitives.update(allowed)
    return primitives


def _color_only_constraint_from_ddl(ddl: str | None) -> list[str]:
    if not ddl:
        return []
    lower = ddl.lower()
    japanese_color = r"(?:白|黒|青|赤|緑|灰)(?:色)?"
    japanese_list = rf"{japanese_color}(?:\s*(?:と|、|・|,|/)\s*{japanese_color})*"
    english_color = r"(?:white|black|blue|red|green|gray|grey)"
    english_list = rf"{english_color}(?:\s*(?:and|,|/)\s*{english_color})*"
    has_color_only_phrase = bool(
        re.search(rf"{japanese_list}\s*(?:だけ|のみ|に限定|で限定)", ddl)
        or re.search(rf"(?:{english_list})\s+only\b", lower)
        or re.search(rf"limited to\s+(?:{english_list})", lower)
    )
    if not has_color_only_phrase:
        return []
    requested = _color_repair_order(_requested_colors_from_ddl(ddl))
    return requested


def _append_note(data: dict[str, Any], note: str) -> None:
    hint = data.get("note")
    if isinstance(hint, str) and note in (part.strip() for part in hint.split(";")):
        return
    data["note"] = f"{hint}; {note}" if hint else note


def _as_circle_instruction(ins: Instruction, note: str) -> Instruction:
    if ins.primitive == "circle":
        return ins
    data = ins.model_dump(by_alias=True)
    center = data.get("center") or data.get("position") or [0.5, 0.5]
    if ins.primitive == "ellipse" and ins.size is not None:
        radius = min(max(float(ins.size[0]), float(ins.size[1])) / 2, 0.45)
    elif ins.primitive in ("arc", "polygon") and ins.radius is not None:
        radius = float(ins.radius)
    elif ins.size is not None:
        radius = min(max(float(ins.size[0]), float(ins.size[1])) / 2, 0.45)
    else:
        radius = 0.12
    converted = {
        "primitive": "circle",
        "center": center,
        "radius": max(0.005, radius),
        "color": data.get("color", "black"),
        "weight": data.get("weight", "pen"),
        "filled": data.get("filled", False),
        "style": data.get("style", "solid"),
        "arrangement": data.get("arrangement"),
        "variation": data.get("variation"),
        "color_hint": data.get("color_hint"),
        "note": data.get("note"),
    }
    _append_note(converted, note)
    return Instruction.model_validate(converted)


def _with_literal_grid_fidelity(
    instructions: list[Instruction],
    *,
    ddl: str | None,
) -> list[Instruction]:
    """Preserve explicit literal-tiling count and full-field coverage."""
    if not _is_literal_grid_request(ddl):
        return instructions
    count_hint = count_hint_from_ddl(ddl or "")
    if instructions and not any(
        ins.arrangement is not None and ins.arrangement.layout == "grid"
        for ins in instructions
    ):
        lower = (ddl or "").lower()
        requested_primitive: str | None = None
        if any(marker in lower for marker in ("四角", "square", "squares", "brick", "bricks")):
            requested_primitive = "square"
        elif any(marker in lower for marker in ("線", "雨脚", "line", "stroke")):
            requested_primitive = "line"
        target_index = next(
            (
                index
                for index, ins in enumerate(instructions)
                if requested_primitive is None or ins.primitive == requested_primitive
            ),
            0,
        )
        data = instructions[target_index].model_dump(by_alias=True)
        arr_data = dict(data.get("arrangement") or {})
        arr_data.update(
            {
                "count": count_hint or 400,
                "layout": "grid",
                "path": "none",
                "margin": 0.08,
                "density": "none",
                "cluster_count": None,
                "fade": "none",
                "preserve_space": False,
            }
        )
        data["arrangement"] = arr_data
        instructions = list(instructions)
        instructions[target_index] = Instruction.model_validate(data)
    adjusted: list[Instruction] = []
    for ins in instructions:
        arr = ins.arrangement
        if arr is None or arr.layout != "grid":
            adjusted.append(ins)
            continue
        data = ins.model_dump(by_alias=True)
        arr_data = dict(data["arrangement"])
        if count_hint is not None:
            if arr.rows is not None and arr.cols is not None and arr.rows * arr.cols != count_hint:
                arr_data["rows"] = None
                arr_data["cols"] = None
            arr_data["count"] = count_hint
        arr_data["margin"] = min(float(arr_data.get("margin") or 0.1), 0.08)
        arr_data["density"] = "none"
        arr_data["cluster_count"] = None
        arr_data["fade"] = "none"
        arr_data["preserve_space"] = False
        data["arrangement"] = arr_data
        adjusted.append(Instruction.model_validate(data))
    return adjusted


def _with_explicit_constraint_enforcement(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
) -> list[Instruction]:
    primitive_only = _primitive_only_constraint_from_ddl(ddl)
    color_only = _color_only_constraint_from_ddl(ddl)
    strict_count = _strict_count_hint_from_ddl(ddl)

    repaired = list(instructions)
    if primitive_only:
        constrained: list[Instruction] = []
        for ins in repaired:
            if ins.primitive in primitive_only:
                constrained.append(ins)
            elif primitive_only == {"circle"} and ins.primitive == "ellipse":
                constrained.append(_as_circle_instruction(ins, "explicit circle-only constraint enforced"))
        if constrained:
            repaired = constrained

    if color_only:
        visible_first = next((color for color in color_only if color != background), color_only[0])
        color_set = set(color_only)
        adjusted: list[Instruction] = []
        for ins in repaired:
            data = ins.model_dump(by_alias=True)
            changed = False
            if data.get("color") not in color_set:
                data["color"] = visible_first
                changed = True
            arr_data = data.get("arrangement")
            if arr_data:
                arr_data = dict(arr_data)
                cycle = [color for color in arr_data.get("color_cycle", []) if color in color_set]
                if arr_data.get("color_cycle") and cycle != arr_data.get("color_cycle"):
                    arr_data["color_cycle"] = cycle or [visible_first]
                    data["arrangement"] = arr_data
                    changed = True
            if changed:
                _append_note(data, "explicit color-only constraint enforced")
            adjusted.append(Instruction.model_validate(data))
        repaired = adjusted

    if strict_count is not None and repaired:
        first = repaired[0].model_dump(by_alias=True)
        if strict_count == 1:
            first["arrangement"] = None
        else:
            arr_data = dict(first.get("arrangement") or {})
            arr_data["count"] = strict_count
            arr_data["layout"] = arr_data.get("layout") or "scatter"
            first["arrangement"] = arr_data
        _append_note(first, "explicit count constraint enforced")
        repaired = [Instruction.model_validate(first)]

    return repaired


def _with_ddl_instruction_hints(ins: Instruction, *, ddl: str | None) -> Instruction:
    hinted = _with_material_hint(ins, ddl)
    return _with_variation_hint(hinted, ddl)


def _record_branch_fire(
    report: dict[str, int] | None,
    name: str,
    before: list[Instruction],
    after: list[Instruction],
) -> None:
    if report is None:
        return
    report.setdefault(name, 0)
    changed = abs(len(before) - len(after))
    changed += sum(
        first.model_dump(by_alias=True) != second.model_dump(by_alias=True)
        for first, second in zip(before, after)
    )
    if changed:
        report[name] += changed


def _record_value_branch_fire(
    report: dict[str, int] | None,
    name: str,
    before: object,
    after: object,
) -> None:
    if report is None:
        return
    report.setdefault(name, 0)
    if before != after:
        report[name] += 1


def _style_coerce_disabled() -> bool:
    return os.getenv("INKU_COERCE_DISABLE", "").strip().lower() in {"1", "true", "yes", "on"}
