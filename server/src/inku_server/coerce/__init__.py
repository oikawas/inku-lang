"""Stage 2 score coercion public API and ordered pipeline."""

from __future__ import annotations

from ..limits import DEFAULT_LIMITS, Limits
from ..schema import Score
from .compose import (
    _presence_from_ddl,
    _record_branch_fire,
    _record_value_branch_fire,
    _style_coerce_disabled,
    _with_background_dominance_governor,
    _with_color_delivery_repair,
    _with_complex_motif_repair,
    _with_context_density_governor,
    _with_crescent_sensory_suppression,
    _with_ddl_coverage,
    _with_ddl_instruction_hints,
    _with_existing_event_counterweight,
    _with_explicit_constraint_enforcement,
    _with_literal_grid_fidelity,
    _with_ma_pressure,
    _with_motion_energy,
    _with_primary_color_delivery,
    _with_repetition_event_variation,
    _with_rhythm_variation,
    _with_semantic_visual_event_hints,
    _with_shape_delivery_repair,
    _with_unintentional_filled_shape_tempering,
    _with_visual_event_type_hints,
    _without_explicit_region_support,
    _without_spontaneous_grid,
    count_hint_from_ddl,
)
from .normalize import (
    _coerce_instruction,
    _enforce_hard_ceiling,
    _dedupe_instructions,
    _drop_invalid_relations,
    _repair_coerced_instruction,
    _with_per_instruction_density_budget,
    _with_presence_auxiliary_shape_repair,
    _with_structural_duplicate_repair,
    _with_total_density_budget,
    ensure_renderable_score,
)

__all__ = ["coerce_score", "count_hint_from_ddl", "ensure_renderable_score"]


def coerce_score(
    score: Score,
    *,
    ddl: str | None = None,
    branch_report: dict[str, int] | None = None,
    limits: Limits = DEFAULT_LIMITS,
    limit_notes: list[str] | None = None,
) -> Score:
    """LLM 生成 Score の欠損・不正フィールドを補修して Renderer が安全に描画できる状態にする。

    Every branch here either repairs an instruction or delivers something the
    description asked for. Nothing invents: the branches that used to add a
    visual event, a composition anchor, context energy, a motion floor, a
    surface tension mark or a focal-event reaction were folded away with the
    staffage level (v2.11.0), because adding what the description does not ask
    for works against the purpose of the application.
    """
    if _style_coerce_disabled():
        _branch_before = score.instructions
        instructions = [_coerce_instruction(ins) for ins in score.instructions]
        _record_branch_fire(branch_report, "coerce_instruction", _branch_before, instructions)
        _branch_before = instructions
        instructions = _without_spontaneous_grid(instructions, ddl=ddl)
        _record_branch_fire(branch_report, "without_spontaneous_grid", _branch_before, instructions)
        _branch_before = instructions
        instructions = _with_literal_grid_fidelity(instructions, ddl=ddl)
        _record_branch_fire(branch_report, "with_literal_grid_fidelity", _branch_before, instructions)
        _branch_before = instructions
        instructions = _drop_invalid_relations(instructions)
        _record_branch_fire(branch_report, "drop_invalid_relations", _branch_before, instructions)
        _branch_before = instructions
        instructions = _without_explicit_region_support(instructions, ddl=ddl)
        _record_branch_fire(branch_report, "without_explicit_region_support", _branch_before, instructions)
        data = score.model_dump(by_alias=True)
        data["instructions"] = [ins.model_dump(by_alias=True) for ins in instructions]
        # The ceiling holds on this exit too. It is a guard on drawing cost, so it
        # must not be something INKU_COERCE_DISABLE can switch off.
        return _enforce_hard_ceiling(Score.model_validate(data), limits, limit_notes)
    background = _with_background_dominance_governor(score.background, ddl=ddl)
    _record_value_branch_fire(
        branch_report,
        "with_background_dominance_governor",
        score.background,
        background,
    )
    _branch_before = score.instructions
    instructions = [
        _repair_coerced_instruction(
            _with_ddl_instruction_hints(_coerce_instruction(ins), ddl=ddl),
            original_background=score.background,
            background=background,
        )
        for ins in score.instructions
    ]
    _record_branch_fire(branch_report, "coerce_and_repair_instruction", _branch_before, instructions)
    _branch_before = instructions
    instructions = _without_spontaneous_grid(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "without_spontaneous_grid", _branch_before, instructions)
    _branch_before = instructions
    instructions = _dedupe_instructions(instructions)
    _record_branch_fire(branch_report, "dedupe_instructions", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_ddl_coverage(instructions, ddl=ddl, background=background, limits=limits)
    _record_branch_fire(branch_report, "with_ddl_coverage", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_primary_color_delivery(instructions, ddl=ddl, background=background)
    _record_branch_fire(branch_report, "with_primary_color_delivery", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_color_delivery_repair(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "with_color_delivery_repair", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_shape_delivery_repair(instructions, ddl=ddl, background=background)
    _record_branch_fire(branch_report, "with_shape_delivery_repair", _branch_before, instructions)
    # B9 delivers the motif the DDL asked for, so it runs for every input.
    _branch_before = instructions
    instructions = _with_complex_motif_repair(instructions, ddl=ddl, background=background)
    _record_branch_fire(branch_report, "with_complex_motif_repair", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_structural_duplicate_repair(instructions)
    _record_branch_fire(branch_report, "with_structural_duplicate_repair", _branch_before, instructions)
    effective_presence = score.presence or _presence_from_ddl(ddl)
    _record_value_branch_fire(
        branch_report,
        "presence_from_ddl",
        score.presence,
        effective_presence,
    )
    _branch_before = instructions
    instructions = _with_presence_auxiliary_shape_repair(instructions, effective_presence)
    _record_branch_fire(branch_report, "with_presence_auxiliary_shape_repair", _branch_before, instructions)
    _branch_before = instructions
    instructions = [_with_unintentional_filled_shape_tempering(ins, ddl=ddl) for ins in instructions]
    _record_branch_fire(branch_report, "with_unintentional_filled_shape_tempering", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_context_density_governor(instructions, ddl=ddl, background=background)
    _record_branch_fire(branch_report, "with_context_density_governor", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_motion_energy(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "with_motion_energy", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_rhythm_variation(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "with_rhythm_variation", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_repetition_event_variation(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "with_repetition_event_variation", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_crescent_sensory_suppression(instructions, ddl=ddl, background=background)
    _record_branch_fire(branch_report, "with_crescent_sensory_suppression", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_ma_pressure(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "with_ma_pressure", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_semantic_visual_event_hints(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "with_semantic_visual_event_hints", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_visual_event_type_hints(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "with_visual_event_type_hints", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_existing_event_counterweight(instructions, ddl=ddl, background=background)
    _record_branch_fire(branch_report, "with_existing_event_counterweight", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_per_instruction_density_budget(instructions, limits)
    _record_branch_fire(branch_report, "with_per_instruction_density_budget", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_total_density_budget(instructions, limits)
    _record_branch_fire(branch_report, "with_total_density_budget", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_explicit_constraint_enforcement(instructions, ddl=ddl, background=background)
    _record_branch_fire(branch_report, "with_explicit_constraint_enforcement", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_literal_grid_fidelity(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "with_literal_grid_fidelity", _branch_before, instructions)
    _branch_before = instructions
    instructions = _drop_invalid_relations(instructions)
    _record_branch_fire(branch_report, "drop_invalid_relations", _branch_before, instructions)
    _branch_before = instructions
    instructions = _without_explicit_region_support(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "without_explicit_region_support", _branch_before, instructions)
    data = score.model_dump(by_alias=True)
    data["background"] = background
    if score.presence is None and effective_presence is not None:
        data["presence"] = effective_presence
    data["instructions"] = [ins.model_dump(by_alias=True) for ins in instructions]
    # Last word. Every governor above has had its say; nothing after this may
    # grow a count back, which is why it sits at the exit and not beside them.
    return _enforce_hard_ceiling(Score.model_validate(data), limits, limit_notes)
