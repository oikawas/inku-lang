"""Stage 2 score coercion public API and ordered pipeline."""

from __future__ import annotations

from ..limits import DEFAULT_LIMITS, Limits
from ..schema import Instruction, Score
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
    _with_stated_count_fidelity,
    _with_stated_size,
    _with_unintentional_filled_shape_tempering,
    _with_visual_event_type_hints,
    _without_explicit_region_support,
    _without_spontaneous_grid,
    _without_unrequested_color_cycle,
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
    _with_surface_on_a_closed_shape,
    _with_total_density_budget,
    ensure_renderable_score,
)

__all__ = ["coerce_score", "count_hint_from_ddl", "ensure_renderable_score"]


def _folded_of_unrequested_color_cycle(
    instructions: list[Instruction],
    *,
    ddl: str | None,
    branch_report: dict[str, int] | None,
) -> list[Instruction]:
    """Run on both exits, which is why it is a function and not two call sites.

    Taking back a color the description never asked for is not a style choice,
    so it is not something INKU_COERCE_DISABLE switches off -- the same reason
    the hard ceiling holds on that exit too.
    """
    before = instructions
    folded = _without_unrequested_color_cycle(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "without_unrequested_color_cycle", before, folded)
    return folded


def coerce_score(
    score: Score,
    *,
    ddl: str | None = None,
    branch_report: dict[str, int] | None = None,
    limits: Limits = DEFAULT_LIMITS,
    limit_notes: list[str] | None = None,
    lang: str | None = None,
) -> Score:
    """LLM 生成 Score の欠損・不正フィールドを補修して Renderer が安全に描画できる状態にする。

    Every branch here either repairs an instruction or delivers something the
    description asked for. Nothing invents: the branches that used to add a
    visual event, a composition anchor, context energy, a motion floor, a
    surface tension mark or a focal-event reaction were folded away with the
    staffage level (v2.11.0), because adding what the description does not ask
    for works against the purpose of the application.

    `lang` is the language the description is written in. Only the count readers
    consult it, and only for the exclusions: a numeral with CJK beside it is a
    count in an English body and an angle or a fraction in a Japanese one. Every
    caller passes it; a caller that did not would keep answering 200 while
    reading counts by the other language's rules.
    """
    if _style_coerce_disabled():
        _branch_before = score.instructions
        # On this exit too, and for the same reason the two grid branches below run
        # here: being faithful to the description is not a matter of style. A size
        # the description stated is as much the description's as a count is.
        instructions = [
            _with_stated_size(_coerce_instruction(ins), raw=ins, ddl=ddl)
            for ins in score.instructions
        ]
        _record_branch_fire(branch_report, "coerce_instruction", _branch_before, instructions)
        _branch_before = instructions
        # On this exit too: a surface the renderer will not draw is a
        # renderability defect, not a matter of style, so switching the style
        # coercion off must not switch it back on.
        instructions = _with_surface_on_a_closed_shape(instructions)
        _record_branch_fire(branch_report, "with_surface_on_a_closed_shape", _branch_before, instructions)
        _branch_before = instructions
        instructions = _without_spontaneous_grid(instructions, ddl=ddl)
        _record_branch_fire(branch_report, "without_spontaneous_grid", _branch_before, instructions)
        _branch_before = instructions
        instructions = _with_literal_grid_fidelity(instructions, ddl=ddl, lang=lang)
        _record_branch_fire(branch_report, "with_literal_grid_fidelity", _branch_before, instructions)
        _branch_before = instructions
        instructions = _drop_invalid_relations(instructions)
        _record_branch_fire(branch_report, "drop_invalid_relations", _branch_before, instructions)
        _branch_before = instructions
        instructions = _without_explicit_region_support(instructions, ddl=ddl)
        _record_branch_fire(branch_report, "without_explicit_region_support", _branch_before, instructions)
        instructions = _folded_of_unrequested_color_cycle(
            instructions, ddl=ddl, branch_report=branch_report
        )
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
            _with_ddl_instruction_hints(
                # Immediately after the defaults go in, and holding `ins`: this is the
                # last point where a size the model omitted is still distinguishable
                # from one it wrote.
                _with_stated_size(_coerce_instruction(ins), raw=ins, ddl=ddl),
                ddl=ddl,
            ),
            original_background=score.background,
            background=background,
        )
        for ins in score.instructions
    ]
    _record_branch_fire(branch_report, "coerce_and_repair_instruction", _branch_before, instructions)
    _branch_before = instructions
    # Before anything downstream reads a surface or copies an instruction that
    # carries one, so every later branch sees the attachment the sentence meant.
    instructions = _with_surface_on_a_closed_shape(instructions)
    _record_branch_fire(branch_report, "with_surface_on_a_closed_shape", _branch_before, instructions)
    _branch_before = instructions
    instructions = _without_spontaneous_grid(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "without_spontaneous_grid", _branch_before, instructions)
    _branch_before = instructions
    instructions = _dedupe_instructions(instructions)
    _record_branch_fire(branch_report, "dedupe_instructions", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_ddl_coverage(
        instructions, ddl=ddl, background=background, limits=limits, lang=lang
    )
    _record_branch_fire(branch_report, "with_ddl_coverage", _branch_before, instructions)
    _branch_before = instructions
    # The repair runs first because the promotion can only read what is already
    # in a cycle: `_with_primary_color_delivery` looks for the requested color
    # among the `color_cycle`s, and `_with_color_delivery_repair` is what puts it
    # there. In the other order a delivered color could not be promoted until a
    # second pass over the same DDL, which made coerce not a fixed point.
    instructions = _with_color_delivery_repair(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "with_color_delivery_repair", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_primary_color_delivery(instructions, ddl=ddl, background=background)
    _record_branch_fire(branch_report, "with_primary_color_delivery", _branch_before, instructions)
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
    instructions = _with_context_density_governor(
        instructions, ddl=ddl, background=background, lang=lang
    )
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
    # After the strict path, so that "だけ / のみ / only / just" keeps the last
    # word on the clauses it speaks for. That half is measured: moving this call
    # above `_with_explicit_constraint_enforcement` turns the strict-road test
    # red.
    #
    # It also sits after both budgets, which reads like the same kind of claim
    # and is not. Moving it above `_with_total_density_budget` was measured on a
    # Score whose other group was over the cap, and the repaired count came out
    # identical either way: the budgets scale a count DOWN, and a count in the
    # 1..11 band this branch repairs is never the one they take. So the position
    # is right but nothing distinguishes it, and no test here pretends to.
    instructions = _with_stated_count_fidelity(
        instructions, ddl=ddl, background=background, limits=limits, lang=lang
    )
    _record_branch_fire(branch_report, "with_stated_count_fidelity", _branch_before, instructions)
    _branch_before = instructions
    instructions = _with_literal_grid_fidelity(instructions, ddl=ddl, lang=lang)
    _record_branch_fire(branch_report, "with_literal_grid_fidelity", _branch_before, instructions)
    _branch_before = instructions
    instructions = _drop_invalid_relations(instructions)
    _record_branch_fire(branch_report, "drop_invalid_relations", _branch_before, instructions)
    _branch_before = instructions
    instructions = _without_explicit_region_support(instructions, ddl=ddl)
    _record_branch_fire(branch_report, "without_explicit_region_support", _branch_before, instructions)
    instructions = _folded_of_unrequested_color_cycle(
        instructions, ddl=ddl, branch_report=branch_report
    )
    data = score.model_dump(by_alias=True)
    data["background"] = background
    if score.presence is None and effective_presence is not None:
        data["presence"] = effective_presence
    data["instructions"] = [ins.model_dump(by_alias=True) for ins in instructions]
    # Last word. Every governor above has had its say; nothing after this may
    # grow a count back, which is why it sits at the exit and not beside them.
    return _enforce_hard_ceiling(Score.model_validate(data), limits, limit_notes)
