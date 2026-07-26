"""Replay the frozen compliant Scores through coerce and report what survives.

No LLM call. The question is whether the deterministic part of the pipeline keeps
a count that Stage 2 already got right.

    uv run python scripts/measure_count_preservation.py
    uv run python scripts/measure_count_preservation.py --verbose
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from inku_server.coerce import coerce_score
from inku_server.schema import Score

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "server" / "tests" / "fixtures" / "count_preservation_cases.json"

BANDS = [("2-11", 2, 11), ("12-49", 12, 49), ("50-119", 50, 119),
         ("120-239", 120, 239), ("240-299", 240, 299), ("300+", 300, 10**9)]


def band_of(n: int) -> str:
    for name, lo, hi in BANDS:
        if lo <= n <= hi:
            return name
    raise ValueError(n)


def kept(case: dict) -> tuple[bool, int, list[str]]:
    report: dict[str, int] = {}
    out = coerce_score(Score.model_validate(case["score"]), ddl=case["ddl"], branch_report=report)
    counts = [(ins.arrangement.count if ins.arrangement else 1) for ins in out.instructions]
    got = max(counts) if counts else 0
    if case["kind"] == "literal":
        ok = got == case["requested"]
    else:
        ok = 80 <= got <= 120
    fired = sorted(name for name, n in report.items() if n)
    return ok, got, fired


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    per_lang: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    per_band: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    cut: list[tuple[str, int, int, list[str]]] = []

    for case in payload["cases"]:
        ok, got, fired = kept(case)
        lang, band = case["lang"], band_of(case["requested"])
        per_lang[lang][1] += 1
        per_band[(lang, band)][1] += 1
        if ok:
            per_lang[lang][0] += 1
            per_band[(lang, band)][0] += 1
        else:
            cut.append((case["id"], case["requested"], got, fired))

    print(f"{'band':10s} " + " ".join(f"{lang:>9s}" for lang in ("ja", "en")))
    for name, *_ in BANDS:
        row = " ".join(
            f"{per_band[(lang, name)][0]:>4d}/{per_band[(lang, name)][1]:<4d}" for lang in ("ja", "en")
        )
        print(f"{name:10s} {row}")
    print()
    for lang in ("ja", "en"):
        hit, total = per_lang[lang]
        print(f"{lang}: {hit}/{total} kept")
    total_hit = sum(v[0] for v in per_lang.values())
    total_all = sum(v[1] for v in per_lang.values())
    print(f"total: {total_hit}/{total_all} kept")

    if args.verbose and cut:
        print("\ncut:")
        for case_id, requested, got, fired in cut:
            branches = ", ".join(b for b in fired if "density" in b or "budget" in b or "governor" in b)
            print(f"  {case_id}  requested {requested:>4d} -> {got:<4d}  {branches}")


if __name__ == "__main__":
    main()
