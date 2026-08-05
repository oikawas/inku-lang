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
    "without_spontaneous_grid",
    "dedupe_instructions",
    "with_ddl_coverage",
    "with_primary_color_delivery",
    "with_color_delivery_repair",
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
    "with_literal_grid_fidelity",
    "drop_invalid_relations",
    "without_explicit_region_support",
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
