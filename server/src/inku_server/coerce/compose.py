"""DDL-aware score composition and repair."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from ..counts import (
    # The count readers live in `..counts` so the plugin expansion layer reads a
    # stated count the same way this layer does.  Private names are imported as
    # they are: the Android mirror transcribes them under these names.
    _count_follows_ddl_request,
    _explicit_counts_from_ddl,
    _is_literal_grid_request,
    _single_mark_count_from_clause,
    _strict_count_hint_from_ddl,
    count_hint_from_ddl,
)
from ..language_support.registry import INSTRUCTION_LANGUAGE_REGISTRY
from ..limits import DEFAULT_LIMITS, Limits, note_limit
from ..schema import Instruction, fill_is_asked_for
from .normalize import (
    VISIBLE_ON_BACKGROUND,
    _budgeted_count,
    _closed_shape_area,
    _coerce_marker_values,
    _cluster_count,
    _expanded_count,
    _mark_count,
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


# Deliberately not the note `_with_explicit_constraint_enforcement` writes. Two
# branches now make a stated count true, and a shared note would make it
# impossible to read from a Score which of them did it.
STATED_COUNT_FIDELITY_NOTE = "stated count from the clause honoured"


EXPLICIT_COUNT_NOTE = "explicit count constraint enforced"


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
    if any(marker in ddl or marker in lower for marker in VARIATION_SLOW_WAVE_MARKERS):
        variation = {
            "amplitude": "medium",
            "frequency": "slow",
            "quality": "wave",
            "dimensions": ["position_x", "position_y"],
        }
    elif any(marker in ddl or marker in lower for marker in VARIATION_FINE_TREMBLE_MARKERS):
        variation = {
            "amplitude": "fine",
            "frequency": "medium",
            "quality": "perlin",
            "dimensions": ["position_y"] if ins.primitive == "line" else ["position_x", "position_y"],
        }
    elif any(marker in ddl or marker in lower for marker in VARIATION_BLURRED_EDGE_MARKERS):
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


RHYTHM_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("rhythm")


VISUAL_EVENT_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("visual_event")


MA_PRESSURE_CONTEXT_MARKERS: tuple[str, ...] = _coerce_marker_values("ma_pressure")


SEMANTIC_VISUAL_EVENT_HINTS: tuple[tuple[tuple[str, ...], str], ...] = _coerce_marker_values("semantic_visual_event_hints")


INTENTIONAL_LARGE_SURFACE_MARKERS: tuple[str, ...] = _coerce_marker_values("intentional_large_surface")


EXPLICIT_SURFACE_MARKERS: tuple[str, ...] = _coerce_marker_values("explicit_surface")


SUNSET_SKY_MARKERS: tuple[str, ...] = _coerce_marker_values("sunset_sky")


DAWN_MARKERS: tuple[str, ...] = _coerce_marker_values("dawn")


NIGHT_MARKERS: tuple[str, ...] = _coerce_marker_values("night")


# One system per judgement, moved out of the branches below so the words
# coerce reacts to are all readable in language_support (ledger I-115). The
# comparison at each site is unchanged -- `_marker_in_text` bounds an ASCII
# word where a bare `in` does not, so the two are not interchangeable.
VARIATION_SLOW_WAVE_MARKERS: tuple[str, ...] = _coerce_marker_values("variation_slow_wave")
VARIATION_FINE_TREMBLE_MARKERS: tuple[str, ...] = _coerce_marker_values("variation_fine_tremble")
VARIATION_BLURRED_EDGE_MARKERS: tuple[str, ...] = _coerce_marker_values("variation_blurred_edge")
NEON_BLUR_SCENE_MARKERS: tuple[str, ...] = _coerce_marker_values("neon_blur_scene")
NEON_BLUR_EVIDENCE_MARKERS: tuple[str, ...] = _coerce_marker_values("neon_blur_evidence")
TEMPORAL_CHAIN_SEQUENCE_MARKERS: tuple[str, ...] = _coerce_marker_values("temporal_chain_sequence")
TEMPORAL_CHAIN_ACTION_MARKERS: tuple[str, ...] = _coerce_marker_values("temporal_chain_action")
TEMPORAL_CHAIN_BEFORE_AFTER_MARKERS: tuple[str, ...] = _coerce_marker_values("temporal_chain_before_after")
TEMPORAL_CHAIN_REACTION_MARKERS: tuple[str, ...] = _coerce_marker_values("temporal_chain_reaction")
CRESCENT_SCENE_MARKERS: tuple[str, ...] = _coerce_marker_values("crescent_scene")
WITHERED_GRASS_MARKERS: tuple[str, ...] = _coerce_marker_values("withered_grass_green")
AUTUMN_FOREST_SCENE_MARKERS: tuple[str, ...] = _coerce_marker_values("autumn_forest_scene")
AUTUMN_LEAF_FALL_MARKERS: tuple[str, ...] = _coerce_marker_values("autumn_leaf_fall")
PRESENCE_CENTER_UPPER_RIGHT_MARKERS: tuple[str, ...] = _coerce_marker_values("presence_center_upper_right")
PRESENCE_CENTER_UPPER_LEFT_MARKERS: tuple[str, ...] = _coerce_marker_values("presence_center_upper_left")
PRESENCE_CENTER_LOWER_RIGHT_MARKERS: tuple[str, ...] = _coerce_marker_values("presence_center_lower_right")
PRESENCE_CENTER_LOWER_LEFT_MARKERS: tuple[str, ...] = _coerce_marker_values("presence_center_lower_left")
PRESENCE_CENTER_RIGHT_HALF_MARKERS: tuple[str, ...] = _coerce_marker_values("presence_center_right_half")
PRESENCE_CENTER_LEFT_HALF_MARKERS: tuple[str, ...] = _coerce_marker_values("presence_center_left_half")
PRESENCE_INTENSITY_HIGH_MARKERS: tuple[str, ...] = _coerce_marker_values("presence_intensity_high")
CLAUSE_NAMES_A_MARK_MARKERS: tuple[str, ...] = _coerce_marker_values("clause_names_a_mark")
CLAUSE_SHAPE_CLOUDFORM_MARKERS: tuple[str, ...] = _coerce_marker_values("clause_shape_cloudform")
CLAUSE_SHAPE_ELLIPSE_MARKERS: tuple[str, ...] = _coerce_marker_values("clause_shape_ellipse")
CLAUSE_SHAPE_CIRCLE_MARKERS: tuple[str, ...] = _coerce_marker_values("clause_shape_circle")
SMALL_MARK_SIZE_MARKERS: tuple[str, ...] = _coerce_marker_values("small_mark_size")
SMALL_MARK_KIND_MARKERS: tuple[str, ...] = _coerce_marker_values("small_mark_kind")
RADIUS_CLAUSE_MARKERS: tuple[str, ...] = _coerce_marker_values("radius_clause")
CLAUSE_REFLECTION_MARKERS: tuple[str, ...] = _coerce_marker_values("clause_reflection")
CLAUSE_FADING_MARKERS: tuple[str, ...] = _coerce_marker_values("clause_fading")
SENSORY_KIND_LIGHT_MARKERS: tuple[str, ...] = _coerce_marker_values("sensory_kind_light")
SENSORY_KIND_SCENT_MARKERS: tuple[str, ...] = _coerce_marker_values("sensory_kind_scent")
SENSORY_KIND_BUD_MARKERS: tuple[str, ...] = _coerce_marker_values("sensory_kind_bud")
SENSORY_KIND_SENSE_MARKERS: tuple[str, ...] = _coerce_marker_values("sensory_kind_sense")
LINE_AT_RIGHT_EDGE_MARKERS: tuple[str, ...] = _coerce_marker_values("line_at_right_edge")
LINE_IS_VERTICAL_MARKERS: tuple[str, ...] = _coerce_marker_values("line_is_vertical")
LINE_IS_HORIZONTAL_MARKERS: tuple[str, ...] = _coerce_marker_values("line_is_horizontal")
POLYGON_IS_HEXAGONAL_MARKERS: tuple[str, ...] = _coerce_marker_values("polygon_is_hexagonal")
FALLBACK_PLACE_RIGHT_HALF_MARKERS: tuple[str, ...] = _coerce_marker_values("fallback_place_right_half")
FALLBACK_PLACE_UPPER_RIGHT_MARKERS: tuple[str, ...] = _coerce_marker_values("fallback_place_upper_right")
FALLBACK_PLACE_UPPER_EDGE_MARKERS: tuple[str, ...] = _coerce_marker_values("fallback_place_upper_edge")
FALLBACK_ARRANGEMENT_SCATTER_MARKERS: tuple[str, ...] = _coerce_marker_values("fallback_arrangement_scatter")
FALLBACK_ARRANGEMENT_LINE_UP_MARKERS: tuple[str, ...] = _coerce_marker_values("fallback_arrangement_line_up")
GRID_REQUESTS_SQUARE_MARKERS: tuple[str, ...] = _coerce_marker_values("grid_requests_square")
GRID_REQUESTS_LINE_MARKERS: tuple[str, ...] = _coerce_marker_values("grid_requests_line")


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
    return (
        _any_marker_in_text(NEON_BLUR_SCENE_MARKERS, ddl, lower)
        and _any_marker_in_text(NEON_BLUR_EVIDENCE_MARKERS, ddl, lower)
    )


def _context_has_motion(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    return _any_marker_in_text(MOTION_CONTEXT_MARKERS, ddl, lower)


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
    if not fill_is_asked_for(ins) or ins.arrangement is not None:
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
    sequence = _any_marker_in_text(TEMPORAL_CHAIN_SEQUENCE_MARKERS, text, lower)
    action = _any_marker_in_text(TEMPORAL_CHAIN_ACTION_MARKERS, text, lower)
    if sequence and action:
        return True

    before_after = _any_marker_in_text(TEMPORAL_CHAIN_BEFORE_AFTER_MARKERS, text, lower)
    reaction = _any_marker_in_text(TEMPORAL_CHAIN_REACTION_MARKERS, text, lower)
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
    if not ddl or not any(marker in ddl.lower() for marker in CRESCENT_SCENE_MARKERS):
        return instructions

    adjusted: list[Instruction] = []
    for ins in instructions:
        descriptive_hint = (ins.color_hint or "").lower()
        if "five-sense" in descriptive_hint or "scent layer" in descriptive_hint:
            continue
        # The green can sit in either place, so both are asked about. Keying the
        # whole branch on `ins.color` made the cycle cleanup a side effect of the
        # primary color happening to be green, and a later stage that rewrites
        # `color` -- the promotion to a primary stroke, once it ran early enough
        # to reach this -- left the green in the cycle for the renderer to draw.
        cycle = list(ins.arrangement.color_cycle) if ins.arrangement is not None else []
        carries_green = ins.color == "green" or "green" in cycle
        if "crescent" in descriptive_hint and "sensory layer" in descriptive_hint and carries_green:
            data = ins.model_dump(by_alias=True)
            if ins.color == "green":
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


def _with_context_density_governor(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
    lang: str | None = None,
) -> list[Instruction]:
    """静けさ・膜・記憶系の入力で、密度や大きな反復面が主題を上書きするのを抑える。"""
    if not _context_has_density_governor(ddl):
        return instructions

    has_vertical_context = _context_has_vertical_density(ddl)
    has_neon_blur_context = _context_has_neon_blur_density(ddl)
    requested_counts = _explicit_counts_from_ddl(ddl, lang=lang)
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
    return adjusted


DDL_CLAUSE_SPLIT = re.compile(r"[。\n;；]+|(?<!\d)\.\s+")
# Words that ask for many colors at once. A description carrying one of these
# has asked for a cycle, so the rule that folds unrequested cycles away must
# not touch it.
POLYCHROME_MARKERS: tuple[str, ...] = _coerce_marker_values("polychrome_request")


def _split_ddl_clauses(ddl: str) -> list[str]:
    return [part.strip() for part in DDL_CLAUSE_SPLIT.split(ddl) if part.strip()]


def _marks_only_ddl(ddl: str | None) -> str:
    """Drop the background clauses, keep everything else.

    `_ddl_clauses` also drops clauses without a shape word, which is right for
    counting the marks a description asks for and wrong here: it would throw
    away `落ち葉が散る` and `静かな水面` whole, and those are exactly the
    descriptions whose one color this layer is about.
    """
    if not ddl:
        return ""
    kept = [
        clause
        for clause in _split_ddl_clauses(ddl)
        if not (clause.startswith("背景") or clause.lower().startswith("background"))
    ]
    return "。".join(kept)


def _has_polychrome_phrase(ddl: str | None) -> bool:
    if not ddl:
        return False
    return _any_marker_in_text(POLYCHROME_MARKERS, ddl, ddl.lower())


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
    # A known order, for determinism -- not a ranking. The table below is not a
    # statement about which color matters more: nothing in the description says
    # that, and inventing it here would be the house style this layer must not
    # add. Colors the table does not name follow it rather than falling out.
    ordered = [color for color in ("red", "blue", "green", "white", "black", "gray") if color in colors]
    return ordered + [color for color in sorted(colors) if color not in ordered]


def _green_intent_context(ddl: str | None) -> str | None:
    if not ddl:
        return None
    if "green" in _negated_colors_from_text(ddl):
        return None
    lower = ddl.lower()
    if "竹" in ddl or "bamboo" in lower:
        return "bamboo green kept as primary contour"
    if any(marker in ddl or marker in lower for marker in WITHERED_GRASS_MARKERS):
        return "withered grass kept as muted green-gray"
    if any(marker in ddl or marker in lower for marker in AUTUMN_FOREST_SCENE_MARKERS) and any(
        marker in ddl for marker in AUTUMN_LEAF_FALL_MARKERS
    ):
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
    # The cycle hands one color to each member in turn, so a color listed twice
    # takes twice the members. That weighting was never asked for: it fell out
    # of inserting the base color without looking, and its size depends on how
    # long the cycle happens to be. The two lines below already look.
    if isinstance(base_color, str) and base_color not in cycle:
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
    # A stroke already carrying a color the description asked for is not taken
    # for another one. An instruction has a single primary stroke, so promoting
    # onto it a second time undoes the first: within one pass that left the last
    # requested color standing and a note for each that no longer held, and
    # across passes red and blue traded the same stroke back and forth forever.
    # Either way the winner would be decided by where the words sit in
    # `_color_repair_order`, which is a known order for determinism, not a
    # ranking -- the thing this layer must not invent.
    wanted = set(requested)
    for color in requested:
        if _score_contains_primary_color(repaired, color):
            continue
        candidate_index = next(
            (
                index
                for index, ins in enumerate(repaired)
                if ins.color not in wanted
                and ins.arrangement is not None
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


def _without_unrequested_color_cycle(instructions: list[Instruction], *, ddl: str | None) -> list[Instruction]:
    """Fold a cycle away when the description named exactly one color.

    The renderer hands `cycle[i % len(cycle)]` to each member in turn, so a
    two-color cycle gives the named color to half the members and an unnamed
    color to the other half. Nothing in the description asked for that split.
    This is not about honouring a distribution the description states -- no
    description states one -- but about removing one nobody asked for.

    The cycle keeps one entry rather than being emptied. Emptying it does not
    draw the same picture: `_apply_color_cycle` rebuilds `color_hint` from the
    effect allowlist and returns early on an empty cycle, so emptying the cycle
    also skips that rebuild -- and a stored Score whose `color_hint` carries an
    old machine note ("black restored in color_cycle...") then hands the renderer
    a color word the description never named. Measured on the [I-173] sample:
    58 of the 100 instructions that carry a cycle have another color's name
    sitting in `color_hint`, and four of them lost the named color entirely when
    the cycle went to `[]`. One entry is still not a cycle -- `len(cycle) <= 1`
    reads that off the Score -- and it keeps the rebuild on the path it was on.
    """
    marks_only = _marks_only_ddl(ddl)
    if not marks_only or _has_polychrome_phrase(ddl):
        return instructions
    requested = _requested_colors_from_ddl(marks_only)
    if len(requested) != 1:
        return instructions
    named = next(iter(requested))

    folded = list(instructions)
    for index, ins in enumerate(folded):
        arr = ins.arrangement
        if arr is None:
            continue
        cycle = list(arr.color_cycle or [])
        # A cycle that never carries the named color is not dilution but a
        # failure to deliver, and delivery is another layer's work.
        if len(cycle) < 2 or named not in cycle or not any(color != named for color in cycle):
            continue
        data = ins.model_dump(by_alias=True)
        arr_data = dict(data.get("arrangement") or {})
        arr_data["color_cycle"] = [named]
        data["arrangement"] = arr_data
        data["color"] = named
        # One clause, no semicolon: `_append_note` dedupes by splitting the note
        # on ";", so a two-clause note never matches itself and gets appended
        # again on every pass -- which would cost coerce the fixed point engine 9
        # bought.
        _append_note(data, f"color_cycle reduced to {named} alone as the DDL names it alone")
        folded[index] = Instruction.model_validate(data)
    return folded


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
    if any(marker in context or marker in lower for marker in PRESENCE_CENTER_UPPER_RIGHT_MARKERS):
        return [0.68, 0.34]
    if any(marker in context or marker in lower for marker in PRESENCE_CENTER_UPPER_LEFT_MARKERS):
        return [0.32, 0.34]
    if any(marker in context or marker in lower for marker in PRESENCE_CENTER_LOWER_RIGHT_MARKERS):
        return [0.68, 0.66]
    if any(marker in context or marker in lower for marker in PRESENCE_CENTER_LOWER_LEFT_MARKERS):
        return [0.32, 0.66]
    if any(marker in context or marker in lower for marker in PRESENCE_CENTER_RIGHT_HALF_MARKERS):
        return [0.68, 0.50]
    if any(marker in context or marker in lower for marker in PRESENCE_CENTER_LEFT_HALF_MARKERS):
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
    intensity = "high" if any(
        marker in ddl or marker in ddl.lower() for marker in PRESENCE_INTENSITY_HIGH_MARKERS
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
    clauses = _split_ddl_clauses(ddl)
    return [
        clause
        for clause in clauses
        if not (clause.startswith("背景") or clause.lower().startswith("background"))
        and _any_marker_in_text(CLAUSE_NAMES_A_MARK_MARKERS, clause, clause.lower())
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
    # Read first, because it is the only shape word here that no other branch
    # would catch: a clause naming 雲形 falls through every test below to the
    # `line` default, and a repair that pairs clauses with groups then pushes
    # the clause's count onto whatever line the Score happens to carry.
    if any(marker in clause or marker in lower for marker in CLAUSE_SHAPE_CLOUDFORM_MARKERS):
        return "cloudform"
    if ("多角形" in clause) or ("五角" in clause) or ("六角" in clause) or ("polygon" in lower):
        return "polygon"
    if ("四角" in clause) or ("square" in lower) or ("rectangle" in lower):
        return "square"
    if ("三角" in clause) or ("triangle" in lower):
        return "triangle"
    if ("弧" in clause) or ("arc" in lower):
        return "arc"
    if any(marker in clause or marker in lower for marker in CLAUSE_SHAPE_ELLIPSE_MARKERS):
        return "ellipse"
    if any(marker in clause or marker in lower for marker in CLAUSE_SHAPE_CIRCLE_MARKERS):
        return "circle"
    return "line"


def _is_small_mark_clause(clause: str) -> bool:
    lower = clause.lower()
    return (
        _any_marker_in_text(SMALL_MARK_SIZE_MARKERS, clause, lower)
        and _any_marker_in_text(SMALL_MARK_KIND_MARKERS, clause, lower)
    )


def _radius_hint_from_clause(clause: str) -> float | None:
    lower = clause.lower()
    match = re.search(r"(?:半径|radius(?:\s+is)?|r)\s*(?:は|=|:)?\s*(0?\.\d+|1(?:\.0+)?)", lower if any(marker in lower for marker in RADIUS_CLAUSE_MARKERS) else clause)
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
    return any(marker in clause or marker in lower for marker in CLAUSE_REFLECTION_MARKERS)


def _is_fading_clause(clause: str) -> bool:
    lower = clause.lower()
    return any(marker in clause or marker in lower for marker in CLAUSE_FADING_MARKERS)


def _sensory_kind(clause: str) -> str | None:
    lower = clause.lower()
    if _any_marker_in_text(SENSORY_KIND_LIGHT_MARKERS, clause, lower):
        return "light"
    if _any_marker_in_text(SENSORY_KIND_SCENT_MARKERS, clause, lower):
        return "scent"
    if _any_marker_in_text(SENSORY_KIND_BUD_MARKERS, clause, lower):
        return "bud"
    if _any_marker_in_text(SENSORY_KIND_SENSE_MARKERS, clause, lower):
        return "sense"
    return None


def _fallback_instruction_from_clause(
    clause: str,
    *,
    index: int,
    background: str,
    limits: Limits = DEFAULT_LIMITS,
    lang: str | None = None,
    notes: list[str] | None = None,
) -> Instruction:
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
        if any(marker in clause or marker in lower for marker in LINE_AT_RIGHT_EDGE_MARKERS):
            common.update({"from": [0.88, 0.18 + offset / 2], "to": [0.88, 0.82 - offset / 2], "rotation": 0})
        elif any(marker in clause or marker in lower for marker in LINE_IS_VERTICAL_MARKERS):
            x = 0.58 + min(index, 3) * 0.08
            common.update({"from": [x, 0.20 + offset / 2], "to": [x, 0.78 - offset / 2], "rotation": 0})
        elif any(marker in clause or marker in lower for marker in LINE_IS_HORIZONTAL_MARKERS):
            y = 0.38 + min(index, 3) * 0.08
            common.update({"from": [0.16, y], "to": [0.84, y], "rotation": 0})
        else:
            common.update({"from": [0.16 + offset, 0.76 - offset], "to": [0.78, 0.30 + offset], "rotation": -8 + index * 7})
    elif primitive == "arc":
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "radius": 0.11, "angle_start": 210, "angle_end": 330})
    elif primitive == "polygon":
        sides = 6 if any(marker in clause or marker in lower for marker in POLYGON_IS_HEXAGONAL_MARKERS) else 5
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "radius": 0.055, "sides": sides, "rotation": -18 + index * 9})
    elif primitive == "circle":
        radius = _radius_hint_from_clause(clause) or (0.038 if _is_small_mark_clause(clause) else 0.10)
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "radius": radius})
    elif primitive == "ellipse":
        size = [0.06, 0.032] if _is_small_mark_clause(clause) else [0.16, 0.09]
        common.update({"center": [0.68 - offset / 2, 0.30 + offset], "size": size, "rotation": -18 + index * 9})
    elif primitive == "cloudform":
        # center + size, not the position + size the `else` branch below writes:
        # the renderer draws a cloudform only when both `center` and `size` are
        # present, so a cloudform laid out like a square is an invisible mark.
        size = [0.10, 0.06] if _is_small_mark_clause(clause) else [0.26, 0.15]
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

    if any(marker in clause or marker in lower for marker in FALLBACK_PLACE_RIGHT_HALF_MARKERS):
        if "center" in common:
            common["center"] = [0.66, common["center"][1]]
        elif "position" in common:
            common["position"] = [0.66, common["position"][1]]
    if any(marker in clause or marker in lower for marker in FALLBACK_PLACE_UPPER_RIGHT_MARKERS) and "center" in common:
        common["center"] = [0.68, 0.30]
    elif any(marker in clause or marker in lower for marker in FALLBACK_PLACE_UPPER_EDGE_MARKERS) and "center" in common:
        common["center"] = [common["center"][0], 0.22]

    count = count_hint_from_ddl(clause, limits, lang=lang, notes=notes)
    cycle = _color_cycle_from_clause(clause, background)
    if count and _is_literal_grid_request(clause):
        if count > limits.schema_count_max:
            note_limit(
                notes,
                "schema_count_max",
                f"a tiling of {count} is over the {limits.schema_count_max} one "
                "arrangement may declare",
            )
        common["arrangement"] = {
            "count": min(count, limits.schema_count_max),
            "layout": "grid",
            "jitter": 0.12,
            "margin": 0.08,
        }
    elif count and any(marker in clause or marker in lower for marker in FALLBACK_ARRANGEMENT_SCATTER_MARKERS):
        common["arrangement"] = {
            "count": _budgeted_count(count, limits, notes),
            "layout": "scatter",
            "margin": 0.18,
        }
    elif count and any(marker in clause or marker in lower for marker in FALLBACK_ARRANGEMENT_LINE_UP_MARKERS):
        common["arrangement"] = {
            "count": _budgeted_count(count, limits, notes),
            "layout": "horizontal",
            "margin": 0.1,
        }
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


def _with_ddl_coverage(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
    limits: Limits = DEFAULT_LIMITS,
    lang: str | None = None,
    notes: list[str] | None = None,
) -> list[Instruction]:
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
        fallback = _fallback_instruction_from_clause(
            clause,
            index=len(augmented),
            background=background,
            limits=limits,
            lang=lang,
            notes=notes,
        )
        key = (fallback.primitive, fallback.color, fallback.weight)
        if key in existing:
            continue
        augmented.append(fallback)
        existing.add(key)
    return augmented


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
    lang: str | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> list[Instruction]:
    """Preserve explicit literal-tiling count and full-field coverage."""
    if not _is_literal_grid_request(ddl):
        return instructions
    count_hint = count_hint_from_ddl(ddl or "", lang=lang)
    if instructions and not any(
        ins.arrangement is not None and ins.arrangement.layout == "grid"
        for ins in instructions
    ):
        lower = (ddl or "").lower()
        requested_primitive: str | None = None
        if any(marker in lower for marker in GRID_REQUESTS_SQUARE_MARKERS):
            requested_primitive = "square"
        elif any(marker in lower for marker in GRID_REQUESTS_LINE_MARKERS):
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
                # "tile the whole field" with no numeral in it: the description
                # states coverage, not a count, so the count is ours to pick and
                # the most it may be is the most this installation draws. A bare
                # 400 here made a RAISED ceiling unreachable -- 400 was the order
                # itself, so nothing was ever trimmed and no note was written,
                # and an administrator saw a limit go up with no change on the
                # page and no reason anywhere. Lowering the ceiling always
                # worked, because _enforce_hard_ceiling cuts afterwards.
                "count": count_hint or limits.max_expanded_primitives,
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
        _append_note(first, EXPLICIT_COUNT_NOTE)
        repaired = [Instruction.model_validate(first)]

    return repaired


def _arrangement_count(ins: Instruction) -> int:
    """How many marks this instruction draws: no arrangement is one mark."""
    return ins.arrangement.count if ins.arrangement is not None else 1


def _is_the_only_answer_to_another_count(
    instructions: list[Instruction],
    position: int,
    spoken_for: frozenset[int],
    limits: Limits,
) -> bool:
    """Would renumbering this group leave another stated number with no group?

    Not "does it answer another number" -- two groups of two both answer a
    stated two, and renumbering either leaves the other standing. Only the last
    group answering a number is protected, because that is the case where the
    repair would trade one broken promise for another.
    """
    count = _arrangement_count(instructions[position])
    for value in spoken_for:
        if not _count_follows_ddl_request(count, frozenset({value}), limits):
            continue
        others = sum(
            1
            for other, ins in enumerate(instructions)
            if other != position
            and _count_follows_ddl_request(_arrangement_count(ins), frozenset({value}), limits)
        )
        if others == 0:
            return True
    return False


def _group_the_clause_names(
    instructions: list[Instruction],
    clause: str,
    *,
    ddl: str | None,
    index: int,
    background: str,
    limits: Limits,
    spoken_for: frozenset[int],
    lang: str | None = None,
    notes: list[str] | None = None,
) -> int | None:
    """Which group this clause is about, when exactly one answer is available.

    The clause is read into an instruction the same way `_with_ddl_coverage`
    reads it, so the pairing uses the product's own reading of the clause rather
    than a second one written here. The reading then goes through the same DDL
    hints every instruction went through on the way in: a clause that names no
    material reads as `pen`, while the instruction it names was moved to
    `pencil` by a material word elsewhere in the description, and comparing the
    two unhinted makes a group that matches look like a group that does not.

    Two kinds of group are not candidates. One already repaired by the strict
    path: that path speaks for "だけ / のみ / only / just", and this one must not
    overwrite what it decided. And one already answering a different number the
    description states: `_primitive_from_clause` reads a shape word anywhere in
    the clause, so 焦点 makes a clause about lines read as a clause about
    circles, and without this the three lines it asks for would be taken out of
    the hundred and fifty-five circles standing next to them.
    """
    fallback = _with_ddl_instruction_hints(
        _fallback_instruction_from_clause(
            clause, index=index, background=background, limits=limits, lang=lang, notes=notes
        ),
        ddl=ddl,
    )
    candidates = [
        position
        for position, ins in enumerate(instructions)
        if EXPLICIT_COUNT_NOTE not in (ins.note or "")
        and not _is_the_only_answer_to_another_count(instructions, position, spoken_for, limits)
    ]
    triple = [
        position
        for position in candidates
        if (instructions[position].primitive, instructions[position].color, instructions[position].weight)
        == (fallback.primitive, fallback.color, fallback.weight)
    ]
    if triple:
        return triple[0] if len(triple) == 1 else None
    figure = [position for position in candidates if instructions[position].primitive == fallback.primitive]
    return figure[0] if len(figure) == 1 else None


def _stated_count_fidelity_band(limits: Limits) -> int:
    """The largest stated number this repair will make true.

    Not a boundary of its own. `literal_count_threshold` already draws the line
    SPEC defines -- below it a stated number is drawn as stated, at or above it
    the group is shown as a band because a reader cannot count that many by eye
    -- and the band this repair honours is the literal side of that same line.
    Writing the number here as a constant of its own would give one boundary two
    names, and the day one of them moved nobody would notice the other stay
    behind.
    """
    return limits.literal_count_threshold - 1


def _marks_with(instructions: list[Instruction], position: int, replacement: Instruction) -> int:
    """How many marks the work would draw with `replacement` in `position`.

    Counted with `_mark_count`, which is the reader the hard ceiling at the exit
    of coerce uses. Any other reader here would let through exactly the works
    that ceiling then trims -- and a grid is the case that separates them, since
    it draws rows*cols marks whatever its count says.
    """
    return sum(
        _mark_count(replacement if index == position else ins)
        for index, ins in enumerate(instructions)
    )


def _with_stated_count(ins: Instruction, count: int) -> Instruction:
    data = ins.model_dump(by_alias=True)
    arrangement = dict(data.get("arrangement") or {})
    if not arrangement and count == 1:
        return ins
    arrangement["count"] = count
    arrangement["layout"] = arrangement.get("layout") or "scatter"
    data["arrangement"] = arrangement
    _append_note(data, STATED_COUNT_FIDELITY_NOTE)
    return Instruction.model_validate(data)


def _with_stated_count_fidelity(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    background: str,
    limits: Limits = DEFAULT_LIMITS,
    lang: str | None = None,
    notes: list[str] | None = None,
) -> list[Instruction]:
    """Make a count stated in plain words true of the group the clause names.

    Until now one branch made a stated number true, and it answered only to
    "だけ / のみ / only / just". A plain "三つ" was protected from thinning and
    nothing more: a number Stage 2 had already missed stayed missed, and the
    miss cost the group its protection too, so a group written as 74 and drawn
    as 73 was thinned to 64 by a governor that no longer recognized it.

    It repairs only what pairs unambiguously -- one clause, one group. A clause
    matching two groups or none is left alone: a number pushed onto a guess
    changes the count of a group the clause never named, which is a worse defect
    than the one being repaired. It stops at the literal band, because at
    `literal_count_threshold` and above SPEC asks for the group to be shown
    rather than counted, and this branch has no business overruling that.

    It also declines a number it cannot deliver whole. This branch runs after
    both density budgets, so nothing above it will make room; what does run
    after it is the hard ceiling at the exit of coerce, and that ceiling trims.
    A trimmed count is the worst of the three outcomes: 233 asked for and 200
    drawn is neither the number the description stated, nor the number Stage 2
    chose, nor a representative count -- it is what a division happened to
    return, and no reader of the Score can say what it means. When the number
    will not fit, leaving Stage 2's count where it is at least says something
    true about how the work was made.
    """
    if not ddl or not instructions:
        return instructions
    every_stated_count = _explicit_counts_from_ddl(ddl, lang=lang)
    band = _stated_count_fidelity_band(limits)
    stated = {value for value in every_stated_count if 1 <= value <= band}
    # A number the description stated and this repair declined to make true, for
    # no reason other than the counting threshold. The picture is not what the
    # sentence asked for and nothing else in the work says why.
    for value in sorted(every_stated_count - stated):
        if value > band:
            note_limit(
                notes,
                "literal_count_threshold",
                f"a stated {value} is at or above the {limits.literal_count_threshold} "
                "a reader can count, so it is not made literally true",
            )
            break
    if not stated:
        return instructions

    repaired = list(instructions)
    for index, clause in enumerate(_ddl_clauses(ddl)):
        # The same reader that answered "which counts were asked for at all",
        # narrowed to this clause. `_single_mark_count_from_clause` is the other
        # candidate and cannot be used here: it reaches English through
        # `_english_count_hint`, whose noun list holds lines and squares but not
        # circles, so "three black pen circles" reads as no count at all.
        values = {
            value
            for value in _explicit_counts_from_ddl(clause, lang=lang)
            if value in stated
        }
        if len(values) != 1:
            continue
        value = values.pop()
        # A number larger than one instruction is allowed to carry is a number no
        # group can hold, so there is nothing here to pair it with. Under the
        # shipping limits this cannot bind -- the band tops out one below
        # `literal_count_threshold`, which equals `max_expanded_per_instruction`
        # -- but the two are separate settings with no rounding between them, so
        # an install that raises the threshold reaches it.
        if value > limits.max_expanded_per_instruction:
            note_limit(
                notes,
                "max_expanded_per_instruction",
                f"a stated {value} is over the {limits.max_expanded_per_instruction} "
                "one instruction may draw, so no group was moved onto it",
            )
            continue
        # A number the Score already carries somewhere is a number this branch
        # has nothing to add to. Moving a second group onto it would answer a
        # request that was answered, and take a count nobody asked to change.
        if any(
            _count_follows_ddl_request(_arrangement_count(ins), frozenset({value}), limits)
            for ins in repaired
        ):
            continue
        target = _group_the_clause_names(
            repaired,
            clause,
            ddl=ddl,
            index=index,
            background=background,
            limits=limits,
            spoken_for=frozenset(every_stated_count - {value}),
            lang=lang,
            notes=notes,
        )
        if target is None:
            continue
        candidate = _with_stated_count(repaired[target], value)
        # Measured against the work as it stands, so a clause repaired earlier
        # in this same loop is already counted: two clauses each fitting on
        # their own can be over the ceiling together, and the second one is the
        # one that has to give way.
        if _marks_with(repaired, target, candidate) > limits.max_expanded_primitives:
            note_limit(
                notes,
                "max_expanded_primitives",
                f"a stated {value} would put the work over the "
                f"{limits.max_expanded_primitives}-mark budget, so it was declined",
            )
            continue
        repaired[target] = candidate
    return repaired


def _with_stated_size(coerced: Instruction, *, raw: Instruction, ddl: str | None) -> Instruction:
    """Fill a size the model left empty from the clause that asked for the mark.

    `raw` is the instruction before _coerce_instruction filled the defaults: it is the only
    place where "the model said nothing" and "the model said 0.15" still differ.

    The values are borrowed from `_fallback_instruction_from_clause`, which reads the same
    clause with the same two readers when coerce writes the mark itself. That is the whole
    claim: a description that says "small" reaches the same size whether Stage 2 wrote the
    mark or coerce did, and before this the two answers were 0.15 and 0.038.

    Exactly one clause, or nothing. With two the description does not say which of them this
    mark answers, and reading the DDL whole instead of clause by clause would shrink a circle
    because an ellipse elsewhere in the description is small.

    Only circle and ellipse: `_is_small_mark_clause` carries no 四角 / 三角 among its mark
    words, so a square clause cannot make it true, and arc and polygon have no small-clause
    size to borrow.
    """
    primitive = coerced.primitive
    if primitive == "circle":
        if raw.radius is not None:
            return coerced
    elif primitive == "ellipse":
        if raw.size is not None:
            return coerced
    else:
        return coerced

    stated = [
        clause
        for clause in _ddl_clauses(ddl)
        if _primitive_from_clause(clause) == primitive and _is_small_mark_clause(clause)
    ]
    if len(stated) != 1:
        return coerced

    data = coerced.model_dump(by_alias=True)
    if primitive == "circle":
        data["radius"] = _radius_hint_from_clause(stated[0]) or 0.038
    else:
        data["size"] = [0.06, 0.032]
    return Instruction.model_validate(data)


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
