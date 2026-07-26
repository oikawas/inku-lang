"""What the pipeline does to a count Stage 2 already got right.

The v2.7.5 benchmark could not answer this: it measured the final Score, which is
the model and coerce together, at the cost of six LLM runs. These cases hold a
compliant Stage 2 output for every single-group line of `cli/bench/count`, paired
with the DDL that line actually produced, so the deterministic half can be
measured on its own in milliseconds.

The numbers below are a **baseline, not a target**. Nineteen of the fifty cases
lose their count today, every one of them to `_with_context_density_governor`, and
the loss is twice as heavy in English as in Japanese. Work that sets out to fix
that is expected to break this test; update the pins in the same commit so the
change shows up in the diff.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inku_server.coerce import coerce_score
from inku_server.schema import Score

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "count_preservation_cases.json"
PAYLOAD = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in PAYLOAD["cases"]}

# measured at v2.7.5 / Build 714
CUT_TODAY = {
    "ja-11", "ja-12", "ja-14", "ja-20", "ja-21",
    "en-09", "en-11", "en-12", "en-13", "en-14", "en-15", "en-16", "en-18",
    "en-20", "en-21", "en-22", "en-23", "en-24", "en-25",
}


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
    if case_id in CUT_TODAY:
        pytest.xfail(f"requested {case['requested']}, coerce returns {got}")
    assert _kept(case, got), f"requested {case['requested']}, coerce returns {got}"


def test_every_loss_today_comes_from_the_quiet_density_governor() -> None:
    """One branch owns the whole gap. A second one appearing changes the diagnosis."""
    culprits: set[str] = set()
    for case_id in sorted(CUT_TODAY):
        case = CASES[case_id]
        got, report = _replay(case)
        assert not _kept(case, got), f"{case_id} now survives; drop it from CUT_TODAY"
        culprits |= {
            branch
            for branch, fired in report.items()
            if fired and ("density" in branch or "budget" in branch)
        }
    assert culprits == {"with_context_density_governor"}


def test_the_loss_is_heavier_in_english() -> None:
    """The language gap in the final Score is not only a prompt gap."""
    per_lang = {"ja": 0, "en": 0}
    for case_id in CUT_TODAY:
        per_lang[CASES[case_id]["lang"]] += 1
    assert per_lang == {"ja": 5, "en": 14}
