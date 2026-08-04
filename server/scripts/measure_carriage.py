"""Report both directions of carriage over a corpus. No LLM, no database.

    uv run python scripts/measure_carriage.py
    uv run python scripts/measure_carriage.py --works /path/to/works.jsonl

The gate in tests/test_carriage.py asserts that the instrument discriminates;
it deliberately fixes no threshold (契約 description-propagation-cut §5-6). This
script produces the numbers a report quotes.

Two directions:

    dropped -- what the DDL declares does not reach the Score
    added   -- what the DDL never declared reaches it anyway

`--works` takes a jsonl with `ddl` (or `expanded_ddl`) and `score`. When a line
also carries `score_pre_coerce`, that is used as the "before" and nothing is
re-coerced -- which is the only honest way to read the added direction, since a
saved work has already been through coerce and replaying it measures a second
pass rather than the authorship of the first. The trace of a paint carries that
field (`include_trace`), so a harness run produces both directions directly.

Without `--works` the frozen count fixture is used, which is the corpus every
checkout carries and where the "before" is a literal Stage 2 Score.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from inku_server.carriage import carriage_report
from inku_server.coerce import coerce_score
from inku_server.schema import Score

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "server" / "tests" / "fixtures" / "count_preservation_cases.json"


def _cases_from_fixture() -> list[tuple[str, dict, dict | None]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [(case["ddl"], case["score"], None) for case in payload["cases"]]


def _cases_from_works(path: Path) -> list[tuple[str, dict, dict | None]]:
    cases: list[tuple[str, dict, dict | None]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        work = json.loads(line)
        ddl = work.get("expanded_ddl") or work.get("ddl")
        score = work.get("score")
        if not ddl or not isinstance(score, dict) or not score.get("instructions"):
            continue
        pre = work.get("score_pre_coerce")
        cases.append((ddl, pre if isinstance(pre, dict) else score,
                      score if isinstance(pre, dict) else None))
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--works", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    cases = _cases_from_works(args.works) if args.works else _cases_from_fixture()
    source = str(args.works) if args.works else "tests/fixtures/count_preservation_cases.json"

    skipped = 0
    declared_total = 0
    dropped_total = 0
    works_with_a_drop = 0
    additions_total = 0
    ungrounded_total = 0
    works_with_an_addition = 0
    works_with_an_ungrounded_addition = 0
    instructions_in = 0
    instructions_out = 0
    branches: Counter[str] = Counter()
    ungrounded_branches: Counter[str] = Counter()

    for ddl, payload, recorded_after in cases:
        try:
            before = Score.model_validate(payload)
            report_branches: dict[str, int] = {}
            if recorded_after is None:
                after = coerce_score(before, ddl=ddl, branch_report=report_branches)
            else:
                # The run already coerced this one; replaying would measure a
                # second pass over an output, not the first pass over an input.
                after = Score.model_validate(recorded_after)
        except Exception:  # noqa: BLE001 -- a work saved under an older schema
            skipped += 1
            continue
        report = carriage_report(ddl, before=before, after=after, branch_report=report_branches)

        declared_total += len(report.declared_colors) + len(report.declared_primitives)
        dropped_total += len(report.dropped)
        works_with_a_drop += 1 if report.dropped else 0
        additions_total += len(report.additions)
        ungrounded_total += len(report.ungrounded)
        works_with_an_addition += 1 if report.additions else 0
        works_with_an_ungrounded_addition += 1 if report.ungrounded else 0
        instructions_in += report.instructions_in
        instructions_out += report.instructions_out
        branches.update(report.branches_that_fired)
        if report.ungrounded:
            ungrounded_branches.update(report.branches_that_fired)
        if args.verbose and report.ungrounded:
            print(f"  {ddl[:48]!r}")
            for addition in report.ungrounded:
                print(f"    + {addition.primitive} {addition.color} :: {addition.note}")

    looked_at = len(cases) - skipped
    print(f"source: {source}")
    print(f"works looked at: {looked_at}  (skipped, unreadable score: {skipped})")
    if not looked_at:
        print("no case was measured -- this is a result of zero, not a clean sweep")
        return
    print()
    print("direction 1 -- what the DDL declares does not reach the Score")
    print(f"  declared items (colour or shape): {declared_total}")
    print(f"  drop warnings: {dropped_total}")
    print(f"  works with at least one drop: {works_with_a_drop} / {looked_at}"
          f"  ({works_with_a_drop / looked_at:.1%})")
    print()
    print("direction 2 -- what the DDL never declared reaches the Score anyway")
    print(f"  instructions in -> out: {instructions_in} -> {instructions_out}"
          f"  (+{instructions_out - instructions_in})")
    print(f"  instructions authored by the layer: {additions_total}")
    print(f"  of those, answering to no clause at all: {ungrounded_total}")
    print(f"  works with at least one addition: {works_with_an_addition} / {looked_at}"
          f"  ({works_with_an_addition / looked_at:.1%})")
    print(f"  works with an ungrounded addition: {works_with_an_ungrounded_addition} / {looked_at}"
          f"  ({works_with_an_ungrounded_addition / looked_at:.1%})")
    print()
    print("branches that fired on works with an ungrounded addition:")
    for name, count in ungrounded_branches.most_common(12):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
