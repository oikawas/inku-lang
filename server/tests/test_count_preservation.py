"""What the pipeline does to a count Stage 2 already got right.

The v2.7.5 benchmark could not answer this: it measured the final Score, which is
the model and coerce together, at the cost of six LLM runs. These cases hold a
compliant Stage 2 output for every single-group line of `cli/bench/count`, paired
with the DDL that line actually produced, so the deterministic half can be
measured on its own in milliseconds.

At v2.7.5 nineteen of the fifty lost their count, all to
`_with_context_density_governor`, and the loss was three times heavier in English.
A count the description states outright is now left alone, and all fifty survive.
The governor still thins counts nobody asked for — `test_the_governor_still_thins_
counts_nobody_asked_for` is what keeps this from being a suite that passes by
switching the branch off.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from inku_server.coerce import coerce_score
from inku_server.coerce.normalize import MAX_EXPANDED_PRIMITIVES, _with_total_density_budget
from inku_server.schema import Instruction, Score

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "count_preservation_cases.json"
PAYLOAD = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in PAYLOAD["cases"]}


def _replay(case: dict) -> tuple[int, dict[str, int]]:
    report: dict[str, int] = {}
    out = coerce_score(Score.model_validate(case["score"]), ddl=case["ddl"], branch_report=report)
    counts = [(ins.arrangement.count if ins.arrangement else 1) for ins in out.instructions]
    return (max(counts) if counts else 0), report


def _kept(case: dict, got: int) -> bool:
    if case["kind"] == "literal":
        return got == case["requested"]
    return 80 <= got <= 120


def test_the_fixture_covers_both_languages_and_every_band() -> None:
    assert len(CASES) == 50
    assert sum(1 for case in CASES.values() if case["lang"] == "ja") == 25
    assert {case["kind"] for case in CASES.values()} == {"literal", "represented"}


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_compliant_counts_survive_coerce(case_id: str) -> None:
    case = CASES[case_id]
    got, _ = _replay(case)
    assert _kept(case, got), f"requested {case['requested']}, coerce returns {got}"


def test_neither_language_is_favoured() -> None:
    """The v2.7.5 gap was ja 20/25 against en 11/25. Halves that differ are the symptom."""
    kept = {"ja": 0, "en": 0}
    for case in CASES.values():
        got, _ = _replay(case)
        kept[case["lang"]] += int(_kept(case, got))
    assert kept == {"ja": 25, "en": 25}


@pytest.mark.parametrize(
    ("case_id", "unrequested_count"),
    [("ja-11", 137), ("en-11", 137), ("ja-14", 200), ("en-15", 300)],
)
def test_the_governor_still_thins_counts_nobody_asked_for(case_id: str, unrequested_count: int) -> None:
    """Exempting a requested count must not amount to switching the branch off.

    Same DDL, same instruction, a count the description never mentions: the quiet
    reading of the scene still applies and the count still comes down.
    """
    case = copy.deepcopy(CASES[case_id])
    case["score"]["instructions"][0]["arrangement"]["count"] = unrequested_count
    got, report = _replay(case)
    assert got < unrequested_count, f"{case_id}: {unrequested_count} passed through untouched"
    assert report.get("with_context_density_governor")


def _line(count: int) -> Instruction:
    return Instruction.model_validate(
        {
            "primitive": "line",
            "from": [0.1, 0.5],
            "to": [0.9, 0.5],
            "color": "black",
            "arrangement": {"count": count, "layout": "scatter"},
        }
    )


def test_the_total_budget_gives_way_from_the_largest_group() -> None:
    """180+150+130 is over budget; the 180 yields and the two smaller ones stay whole."""
    out = _with_total_density_budget([_line(180), _line(150), _line(130)])
    counts = [ins.arrangement.count for ins in out]
    assert counts[1:] == [150, 130]
    assert counts[0] < 180
    assert sum(counts) <= MAX_EXPANDED_PRIMITIVES


def test_the_total_budget_shares_one_ceiling_rather_than_emptying_groups() -> None:
    """Ten equal groups meet one ceiling; none is reduced to a token single mark."""
    out = _with_total_density_budget([_line(110) for _ in range(10)])
    counts = [ins.arrangement.count for ins in out]
    assert len(set(counts)) == 1
    assert min(counts) > 1
    assert sum(counts) <= MAX_EXPANDED_PRIMITIVES


def test_the_total_budget_never_inflates_a_group_to_spend_the_budget() -> None:
    """The old proportional pass raised a requested 120 to 232 to use up the room."""
    out = _with_total_density_budget([_line(200), _line(200), _line(120)])
    assert [ins.arrangement.count for ins in out][2] <= 120


def test_a_represented_count_only_stands_in_for_a_large_request() -> None:
    """80-120 is exempt because it stands in for 240 or more, not because it is 80-120."""
    case = copy.deepcopy(CASES["ja-11"])  # this description asks for 74; nothing large
    case["score"]["instructions"][0]["arrangement"]["count"] = 110
    got, _ = _replay(case)
    assert got < 110
