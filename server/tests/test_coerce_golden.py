"""The gate for refactors of ``coerce_score``.

The render-engine reference corpus renders literal Scores and never calls
coerce, and the ddl-engine corpus reaches ten of coerce's branches. Neither one
notices if a branch changes what it produces. This golden set does: it replays
frozen inputs through ``coerce_score`` and pins the whole output, plus the
per-branch fire report, so a failure names the branch that moved.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from inku_server.coerce import coerce_score
from inku_server.schema import Score

GOLDEN_PATH = pathlib.Path(__file__).resolve().parent / "golden" / "coerce_golden.json"
GOLDEN = json.loads(GOLDEN_PATH.read_text())
CASES = GOLDEN["cases"]


def _replay(case_input: dict) -> tuple[dict, dict[str, int], int]:
    report: dict[str, int] = {}
    score = coerce_score(
        Score.model_validate(case_input["score"]),
        ddl=case_input["ddl"],
        branch_report=report,
        tenkei=case_input["tenkei"],
        plugin_instructions_present=case_input["plugin_instructions_present"],
    )
    return score.model_dump(mode="json", by_alias=True), dict(sorted(report.items())), len(score.instructions)


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_coerce_output_matches_the_frozen_golden(case_id: str) -> None:
    case = CASES[case_id]
    dump, report, count = _replay(case["input"])
    expected = case["expected"]

    moved = sorted(
        branch
        for branch in set(report) | set(expected["branch_report"])
        if report.get(branch) != expected["branch_report"].get(branch)
    )
    assert report == expected["branch_report"], f"{case_id}: branch fire counts moved for {moved}"
    assert count == expected["instruction_count"], f"{case_id}: instruction count moved"
    assert dump == expected["score"], f"{case_id}: coerced score moved"


def test_every_branch_coerce_reaches_has_a_witness() -> None:
    """A branch nobody fires is a branch this gate does not protect."""
    reached: set[str] = set()
    fired: set[str] = set()
    for case in CASES.values():
        _, report, _ = _replay(case["input"])
        reached |= set(report)
        fired |= {branch for branch, count in report.items() if count}
    assert reached - fired == set(), (
        "these branches are reached but never fire, so a refactor could break them unseen: "
        f"{sorted(reached - fired)}. Add a case that fires each one."
    )


def test_the_golden_records_the_branches_it_claims_to_cover() -> None:
    reached: set[str] = set()
    for case in CASES.values():
        _, report, _ = _replay(case["input"])
        reached |= set(report)
    assert sorted(reached) == GOLDEN["branches_reached"], (
        "coerce reaches a different set of branches than the golden was frozen against. "
        "If a branch was added or removed, refreeze with scripts/gen_coerce_golden.py --refreeze "
        "and add a case that fires the new one."
    )


def test_the_golden_carries_a_synthetic_case_for_each_branch_it_targets() -> None:
    """Synthetic cases exist to reach what real works never do; keep them honest."""
    for case_id, case in sorted(CASES.items()):
        target = case.get("targets")
        if target is None:
            continue
        _, report, _ = _replay(case["input"])
        assert report.get(target), f"{case_id} no longer fires its target branch {target}"
