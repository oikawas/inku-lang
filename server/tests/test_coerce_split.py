"""Mechanical boundaries for the split coerce package."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from inku_server.coerce import coerce_score, count_hint_from_ddl, ensure_renderable_score
from inku_server.schema import Score


COERCE_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "inku_server" / "coerce"
GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "coerce_golden.json"

EXPECTED_BRANCH_ORDER = [
    "with_background_dominance_governor",
    "coerce_and_repair_instruction",
    # Before anything downstream reads a surface or copies an instruction that
    # carries one (ddl-engine 15), so every later branch sees the attachment the
    # `面: ...` sentence meant rather than the one Stage 2 happened to write.
    "with_surface_on_a_closed_shape",
    "without_spontaneous_grid",
    "dedupe_instructions",
    "with_ddl_coverage",
    # These two are not interchangeable, and were swapped at ddl-engine 9. The
    # repair is what puts a requested color into a `color_cycle`; the promotion
    # searches the cycles for that color and can only find what is already
    # there. Run the other way round, a delivered color is promoted one pass
    # late and coerce is not a fixed point for its own output. Reordering this
    # pair again is a decision about that, not a reshuffle of an inventory.
    "with_color_delivery_repair",
    "with_primary_color_delivery",
    "with_shape_delivery_repair",
    "with_complex_motif_repair",
    "with_structural_duplicate_repair",
    "presence_from_ddl",
    "with_presence_auxiliary_shape_repair",
    "with_unintentional_filled_shape_tempering",
    "with_context_density_governor",
    "with_motion_energy",
    "with_rhythm_variation",
    "with_repetition_event_variation",
    "with_crescent_sensory_suppression",
    "with_ma_pressure",
    "with_semantic_visual_event_hints",
    "with_visual_event_type_hints",
    "with_existing_event_counterweight",
    "with_per_instruction_density_budget",
    "with_total_density_budget",
    "with_explicit_constraint_enforcement",
    # After both budgets and after the strict road (ddl-engine 11). Before the
    # budgets a repaired count is one they are free to thin again, and before the
    # strict road it would overwrite what "だけ / のみ / only / just" decided.
    "with_stated_count_fidelity",
    "with_literal_grid_fidelity",
    "drop_invalid_relations",
    "without_explicit_region_support",
    # Second to last, and on both exits (ddl-engine 18). It says the interior's
    # state once, in one vocabulary, whichever of the two ways it arrived in --
    # so it has to run after everything that can write `filled` or a `surface`:
    # the repair inside the instruction pass, the three fallbacks inside
    # `with_ddl_coverage`, and the tempering of a large filled shape. Run before
    # any of them and a fill they add is left saying only half of itself.
    "with_fill_as_a_surface_word",
    # Last, and on both exits (ddl-engine 10). It reads the cycle the delivery
    # branches above have finished writing, so it cannot sit among them: run
    # earlier, it would fold a cycle a later branch then rebuilds.
    "without_unrequested_color_cycle",
]


def _module_ast(name: str) -> ast.Module:
    return ast.parse((COERCE_PACKAGE / name).read_text())


def test_normalize_functions_do_not_accept_ddl() -> None:
    functions = (
        node
        for node in ast.walk(_module_ast("normalize.py"))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    offenders = [
        node.name
        for node in functions
        if any(argument.arg == "ddl" for argument in (*node.args.args, *node.args.kwonlyargs))
    ]
    assert offenders == []


def test_normalize_does_not_import_compose() -> None:
    imports = (
        node
        for node in ast.walk(_module_ast("normalize.py"))
        if isinstance(node, (ast.Import, ast.ImportFrom))
    )
    offenders = []
    for node in imports:
        if isinstance(node, ast.Import):
            offenders.extend(alias.name for alias in node.names if "compose" in alias.name.split("."))
        elif node.module and "compose" in node.module.split("."):
            offenders.append(node.module)
    assert offenders == []


def test_coerce_score_branch_order_is_frozen() -> None:
    cases = json.loads(GOLDEN_PATH.read_text())["cases"]
    case_input = cases["H-01"]["input"]
    report: dict[str, int] = {}

    coerce_score(
        Score.model_validate(case_input["score"]),
        ddl=case_input["ddl"],
        branch_report=report,
    )

    assert list(report) == EXPECTED_BRANCH_ORDER


def test_public_coerce_api_is_importable() -> None:
    assert callable(coerce_score)
    assert callable(ensure_renderable_score)
    assert callable(count_hint_from_ddl)
