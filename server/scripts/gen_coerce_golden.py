"""Refreeze the expected side of the coerce golden set.

Run from ``server/`` with the repository-standard uv cache environment::

    uv run python scripts/gen_coerce_golden.py --refreeze

The golden set carries its own inputs, so this script never reaches the network
or a database: it replays every frozen input through ``coerce_score`` and writes
the result back. ``--refreeze`` is required, because rewriting the expected side
is how a real regression gets erased. Change it only when coerce's output is
meant to move, and say so in the report.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess

from inku_server.coerce import coerce_score
from inku_server.schema import Score

GOLDEN_PATH = pathlib.Path(__file__).resolve().parents[1] / "tests" / "golden" / "coerce_golden.json"


def replay(case_input: dict) -> tuple[dict, dict[str, int], int]:
    report: dict[str, int] = {}
    score = coerce_score(
        Score.model_validate(case_input["score"]),
        ddl=case_input["ddl"],
        branch_report=report,
        tenkei=case_input["tenkei"],
        plugin_instructions_present=case_input["plugin_instructions_present"],
    )
    return score.model_dump(mode="json", by_alias=True), dict(sorted(report.items())), len(score.instructions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refreeze", action="store_true",
                        help="rewrite the expected side; without it the script only reports drift")
    args = parser.parse_args()

    document = json.loads(GOLDEN_PATH.read_text())
    cases = document["cases"]
    reached: set[str] = set()
    drifted: list[str] = []

    for case_id, case in sorted(cases.items()):
        dump, report, count = replay(case["input"])
        reached |= set(report)
        expected = case.get("expected")
        if expected is not None and (
            expected["score"] != dump
            or expected["branch_report"] != report
            or expected["instruction_count"] != count
        ):
            drifted.append(case_id)
        case["expected"] = {"score": dump, "instruction_count": count, "branch_report": report}

    fired = {b for c in cases.values() for b, n in c["expected"]["branch_report"].items() if n}
    missing = sorted(reached - fired)

    print(f"cases: {len(cases)}")
    print(f"branches reached: {len(reached)} / with a witness: {len(fired)}")
    if missing:
        print(f"branches without a witness: {missing}")
    print(f"drifted cases: {len(drifted)}{' -> ' + ', '.join(drifted) if drifted else ''}")

    if not args.refreeze:
        print("\nnothing written (pass --refreeze to rewrite the expected side)")
        return

    document["branches_reached"] = sorted(reached)
    document["branches_with_a_witness"] = sorted(fired)
    document["commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=GOLDEN_PATH.parents[3],
    ).stdout.strip()
    GOLDEN_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=1, sort_keys=False) + "\n")
    print(f"\nwrote {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
