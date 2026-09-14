"""Structural compatibility for externally saved, versionless Score payloads.

New authoring is compiled by the shared Rust pipeline. This seam never accepts
DDL or prose. It only supplies geometry omitted by old Score writers, bridges
the two historical spellings of a solid fill, removes relations the renderer
cannot resolve, and applies the recorded resource limits.
"""

from __future__ import annotations

from contextlib import nullcontext
from itertools import zip_longest
from typing import Any

from .limits import DEFAULT_LIMITS, Limits, note_limit, using_limits
from .schema import CLOSED_SHAPES, Instruction, Score, SurfaceSpec


SAVED_FOCUS_IDS = frozenset(
    {
        "upper_right",
        "upper_left",
        "lower_right",
        "lower_left",
        "upper_edge",
        "right_half",
    }
)
VARIATION_AMPLITUDES = frozenset({"small", "medium", "large"})
SAVED_SCORE_BRANCH_ORDER = (
    "structural_defaults",
    "legacy_fill_spelling",
    "invalid_relations",
    "resource_limits",
)


_MISSING = object()


def _change_count(before: list[Instruction], after: list[Instruction]) -> int:
    return sum(
        left is _MISSING
        or right is _MISSING
        or left.model_dump(mode="json", by_alias=True)
        != right.model_dump(mode="json", by_alias=True)
        for left, right in zip_longest(before, after, fillvalue=_MISSING)
    )


def _record_branch(
    trace: object | None,
    branch_report: dict[str, int],
    branch: str,
    before: list[Instruction],
    after: list[Instruction],
) -> None:
    changed = _change_count(before, after)
    branch_report[branch] = changed
    if trace is not None:
        trace.record_branch(
            branch,
            [item.model_dump(mode="json", by_alias=True) for item in before],
            [item.model_dump(mode="json", by_alias=True) for item in after],
            change_count=changed,
            path="/instructions",
        )


def _with_structural_defaults(ins: Instruction) -> Instruction:
    """Supply only geometry that old versionless Score writers could omit."""
    if ins.arc_form == "crescent":
        return ins
    data = ins.model_dump(by_alias=True)
    if ins.primitive == "line":
        data["from"] = data.get("from") or [0.1, 0.5]
        data["to"] = data.get("to") or [0.9, 0.5]
    elif ins.primitive in {"circle", "arc", "polygon"}:
        data["center"] = data.get("center") or data.get("position") or [0.5, 0.5]
        data["radius"] = data.get("radius") or 0.15
        if ins.primitive == "arc":
            start = data.get("angle_start")
            end = data.get("angle_end")
            data["angle_start"] = 0.0 if start is None else start
            data["angle_end"] = 270.0 if end is None else end
            if abs(float(data["angle_start"]) - float(data["angle_end"])) < 1e-6:
                data["angle_end"] = (float(data["angle_start"]) + 270.0) % 360.0
        if ins.primitive == "polygon":
            data["sides"] = data.get("sides") or 5
    elif ins.primitive in {"ellipse", "cloudform"}:
        data["center"] = data.get("center") or data.get("position") or [0.5, 0.5]
        data["size"] = data.get("size") or [0.3, 0.3]
    elif ins.primitive in {"square", "triangle"}:
        data["position"] = data.get("position") or data.get("center") or [0.35, 0.35]
        data["size"] = data.get("size") or [0.3, 0.3]
    return Instruction.model_validate(data)


def _with_legacy_fill_spelling(instructions: list[Instruction]) -> list[Instruction]:
    """Keep `filled=true` and `surface.texture=solid` mutually readable."""
    result = list(instructions)
    for index, ins in enumerate(result):
        if ins.primitive not in CLOSED_SHAPES:
            continue
        surface = ins.surface
        if surface is not None and surface.texture == "solid" and not ins.filled:
            result[index] = ins.model_copy(update={"filled": True})
        elif ins.filled and (surface is None or surface.texture == "none"):
            solid = (
                SurfaceSpec(texture="solid")
                if surface is None
                else surface.model_copy(update={"texture": "solid"})
            )
            result[index] = ins.model_copy(update={"surface": solid})
    return result


def _has_contour(ins: Instruction) -> bool:
    if ins.primitive == "line":
        return ins.from_ is not None and ins.to is not None
    if ins.primitive == "arc" and ins.arc_form == "crescent":
        return ins.center is not None and ins.size is not None
    if ins.primitive in {"circle", "arc", "polygon"}:
        return ins.center is not None and ins.radius is not None
    if ins.primitive in {"ellipse", "cloudform"}:
        return ins.center is not None and ins.size is not None
    if ins.primitive in {"square", "triangle"}:
        return ins.position is not None and ins.size is not None
    return False


def _without_invalid_relations(instructions: list[Instruction]) -> list[Instruction]:
    result: list[Instruction] = []
    for ins in instructions:
        relation = ins.relation
        if relation is None:
            result.append(ins)
            continue
        invalid = not result or not _has_contour(result[-1])
        if relation.type == "between":
            invalid = invalid or len(result) < 2 or not _has_contour(result[-2])
        elif relation.type == "touching":
            invalid = invalid or ins.primitive not in {"line", "arc"}
            invalid = invalid or result[-1].primitive not in {"line", "arc"}
        if invalid:
            result.append(ins.model_copy(update={"relation": None}))
        else:
            result.append(ins)
    return result


def _expanded_count(ins: Instruction) -> int:
    return max(1, int(ins.arrangement.count)) if ins.arrangement is not None else 1


def _with_note(ins: Instruction, note: str) -> Instruction:
    existing = ins.note
    return ins.model_copy(update={"note": f"{existing}; {note}" if existing else note})


def _with_arrangement_count(ins: Instruction, count: int, note: str) -> Instruction:
    if ins.arrangement is None or ins.arrangement.count == count:
        return ins
    arrangement = ins.arrangement.model_copy(update={"count": max(1, int(count))})
    return _with_note(ins.model_copy(update={"arrangement": arrangement}), note)


def _density_label(count: int, limits: Limits) -> str:
    if count >= limits.represented_count_max * 3 // 2:
        return "high"
    if count >= limits.represented_count_max * 2 // 3:
        return "medium"
    return "low"


def _clustered_visual_count(
    count: int, limits: Limits, notes: list[str] | None
) -> int:
    if count <= limits.represented_count_max:
        return count
    represented = min(
        limits.represented_count_max,
        max(limits.represented_count_min, int(count * 0.42)),
    )
    note_limit(
        notes,
        "represented_count_max",
        f"a group of {count} is above the {limits.represented_count_max} "
        f"a reader can count, so it is drawn as {represented}",
    )
    if int(count * 0.42) < limits.represented_count_min:
        note_limit(
            notes,
            "represented_count_min",
            f"the representative count was raised from {int(count * 0.42)} to "
            f"{limits.represented_count_min}",
        )
    return represented


def _cluster_count(count: int, represented: int, limits: Limits) -> int:
    if count >= limits.represented_count_max * 25 // 6:
        band = 9
    elif count >= limits.represented_count_max * 2:
        band = 7
    elif count >= limits.represented_count_max:
        band = 5
    else:
        band = 3
    scaled = max(1, band * limits.represented_count_max // DEFAULT_LIMITS.represented_count_max)
    return max(scaled, -(-represented // 24))


def _with_clustered_density(
    ins: Instruction,
    note: str,
    limits: Limits,
    notes: list[str] | None,
) -> Instruction:
    arrangement = ins.arrangement
    if arrangement is None or arrangement.layout == "grid":
        return ins
    original = arrangement.count
    represented = _clustered_visual_count(original, limits, notes)
    density = arrangement.density
    fade = arrangement.fade
    updated = arrangement.model_copy(
        update={
            "count": represented,
            "density": density if density != "none" else _density_label(original, limits),
            "cluster_count": arrangement.cluster_count
            or _cluster_count(original, represented, limits),
            "preserve_space": True,
            "margin": max(float(arrangement.margin), 0.18),
            "fade": fade
            if fade != "none"
            else (
                "directional"
                if arrangement.path != "none"
                or arrangement.layout in {"horizontal", "vertical"}
                else "outward"
            ),
        }
    )
    return _with_note(
        ins.model_copy(update={"arrangement": updated}),
        f"{note}; original count {original}",
    )


def _with_resource_budgets(
    instructions: list[Instruction], limits: Limits, notes: list[str] | None
) -> list[Instruction]:
    adjusted: list[Instruction] = []
    for ins in instructions:
        arrangement = ins.arrangement
        if (
            arrangement is None
            or arrangement.layout == "grid"
            or arrangement.count <= limits.max_expanded_per_instruction
        ):
            adjusted.append(ins)
            continue
        note_limit(
            notes,
            "max_expanded_per_instruction",
            f"an arrangement of {arrangement.count} is over the "
            f"{limits.max_expanded_per_instruction} one instruction may draw, so it is clustered",
        )
        adjusted.append(
            _with_clustered_density(
                ins,
                "single arrangement density clustered to preserve negative space",
                limits,
                notes,
            )
        )

    movable = [
        index
        for index, ins in enumerate(adjusted)
        if ins.arrangement is not None and ins.arrangement.layout != "grid"
    ]
    total = sum(
        _expanded_count(ins)
        for ins in adjusted
        if ins.arrangement is None or ins.arrangement.layout != "grid"
    )
    if total > limits.max_expanded_primitives:
        note_limit(
            notes,
            "max_expanded_primitives",
            f"the work asked for {total} marks and the budget is "
            f"{limits.max_expanded_primitives}, so the largest groups were represented",
        )
        for index in sorted(
            movable, key=lambda item: _expanded_count(adjusted[item]), reverse=True
        ):
            if total <= limits.max_expanded_primitives:
                break
            before = _expanded_count(adjusted[index])
            candidate = _with_clustered_density(
                adjusted[index],
                "largest group represented to fit the total density budget",
                limits,
                notes,
            )
            after = _expanded_count(candidate)
            if after < before:
                adjusted[index] = candidate
                total -= before - after
    if total > limits.max_expanded_primitives and movable:
        counts = [_expanded_count(adjusted[index]) for index in movable]
        fixed = total - sum(counts)
        ceiling = 1
        for candidate in range(1, max(counts) + 1):
            if fixed + sum(min(count, candidate) for count in counts) <= limits.max_expanded_primitives:
                ceiling = candidate
            else:
                break
        for index in movable:
            if _expanded_count(adjusted[index]) > ceiling:
                adjusted[index] = _with_arrangement_count(
                    adjusted[index],
                    ceiling,
                    "expanded density capped to preserve negative space",
                )
    return _with_hard_ceiling(adjusted, limits, notes)


def _mark_count(ins: Instruction) -> int:
    arrangement = ins.arrangement
    if arrangement is None:
        return 1
    if (
        arrangement.layout == "grid"
        and arrangement.rows is not None
        and arrangement.cols is not None
    ):
        return max(1, arrangement.rows * arrangement.cols)
    return max(1, int(arrangement.count))


def _grid_within(ins: Instruction, ceiling: int, note: str) -> Instruction:
    arrangement = ins.arrangement
    assert arrangement is not None
    if arrangement.rows is None or arrangement.cols is None:
        return _with_arrangement_count(ins, ceiling, note)
    rows, cols = arrangement.rows, arrangement.cols
    new_rows, new_cols = 1, 1
    for candidate_rows in range(1, rows + 1):
        candidate_cols = max(1, min(cols, round(candidate_rows * cols / rows)))
        if candidate_rows * candidate_cols <= ceiling and (
            candidate_rows * candidate_cols > new_rows * new_cols
        ):
            new_rows, new_cols = candidate_rows, candidate_cols
    updated = arrangement.model_copy(
        update={"rows": new_rows, "cols": new_cols, "count": new_rows * new_cols}
    )
    return _with_note(ins.model_copy(update={"arrangement": updated}), note)


def _composite_mark_counts(instructions: list[Instruction]) -> list[int]:
    counts = [0] * len(instructions)
    index = 0
    while index < len(instructions):
        instruction = instructions[index]
        arrangement = instruction.arrangement
        group_size = arrangement.group_size if arrangement is not None else 1
        counts[index] = _mark_count(instruction) * group_size
        index += group_size
    return counts


def _instruction_boundary(instructions: list[Instruction], limit: int) -> int:
    boundary = 0
    index = 0
    while index < len(instructions) and index < limit:
        arrangement = instructions[index].arrangement
        group_size = arrangement.group_size if arrangement is not None else 1
        stop = index + group_size
        if stop > limit:
            break
        boundary = stop
        index = stop
    return boundary


def _with_hard_ceiling(
    instructions: list[Instruction], limits: Limits, notes: list[str] | None
) -> list[Instruction]:
    result = list(instructions)
    if len(result) > limits.max_instructions:
        boundary = _instruction_boundary(result, limits.max_instructions)
        if boundary == 0:
            boundary = limits.max_instructions
            result = [
                ins.model_copy(
                    update={
                        "arrangement": ins.arrangement.model_copy(update={"group_size": 1})
                    }
                )
                if ins.arrangement is not None and ins.arrangement.group_size > 1
                else ins
                for ins in result[:boundary]
            ]
        else:
            result = result[:boundary]
        note = f"instruction list capped at {boundary}; {len(instructions) - boundary} dropped"
        if result:
            result[-1] = _with_note(result[-1], note)
        note_limit(notes, "max_instructions", note)

    counts = _composite_mark_counts(result)
    if sum(counts) <= limits.max_expanded_primitives:
        return result
    ceiling = 1
    for candidate in range(1, max(counts) + 1):
        if sum(min(count, candidate) for count in counts) <= limits.max_expanded_primitives:
            ceiling = candidate
        else:
            break
    note = f"hard ceiling {limits.max_expanded_primitives} applied to the whole work"
    note_limit(notes, "max_expanded_primitives", note)
    for index, ins in enumerate(result):
        if counts[index] <= ceiling or ins.arrangement is None:
            continue
        if ins.arrangement.layout == "grid":
            result[index] = _grid_within(ins, ceiling, note)
        elif ins.arrangement.group_size > 1:
            result[index] = _with_arrangement_count(
                ins, max(1, ceiling // ins.arrangement.group_size), note
            )
        else:
            result[index] = _with_arrangement_count(ins, ceiling, note)
    return result


def coerce_saved_score(
    payload: Score | dict[str, Any],
    *,
    limits: Limits,
    lang: str | None = None,
    limit_notes: list[str] | None = None,
    trace: object | None = None,
) -> Score:
    """Deserialize a historical Score without consulting its DDL or prose."""
    del lang
    branch_report: dict[str, int] = {}
    with using_limits(limits):
        score = payload if isinstance(payload, Score) else Score.model_validate(payload)
        activation = trace.activate() if trace is not None else nullcontext()
        with activation:
            before = list(score.instructions)
            instructions = [_with_structural_defaults(ins) for ins in before]
            _record_branch(trace, branch_report, "structural_defaults", before, instructions)

            before = instructions
            instructions = _with_legacy_fill_spelling(before)
            _record_branch(trace, branch_report, "legacy_fill_spelling", before, instructions)

            before = instructions
            instructions = _without_invalid_relations(before)
            _record_branch(trace, branch_report, "invalid_relations", before, instructions)

            before = instructions
            instructions = _with_resource_budgets(before, limits, limit_notes)
            _record_branch(trace, branch_report, "resource_limits", before, instructions)

            data = score.model_dump(by_alias=True)
            data["instructions"] = [ins.model_dump(by_alias=True) for ins in instructions]
            result = Score.model_validate(data)
        if trace is not None:
            trace.finish(
                result.model_dump(mode="json", by_alias=True),
                branch_report,
                disabled=False,
            )
        return result
