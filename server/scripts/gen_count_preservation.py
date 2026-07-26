"""Freeze the count-preservation cases from the v2.7.5 benchmark runs.

Each case is a Score that already honours the requested count — the literal value
below 240, a representative 80-120 above it — paired with the expanded DDL the
benchmark actually sent. Replaying these through `coerce_score` asks the one
question the LLM benchmark cannot answer cheaply: if Stage 2 is perfect, does the
rest of the pipeline keep the count? Regenerating needs the `cli/out2` runs listed
in `SOURCES`; the frozen JSON is what the measurement reads.

    uv run python scripts/gen_count_preservation.py --write
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT2 = REPO / "cli" / "out2"
TARGET = REPO / "server" / "tests" / "fixtures" / "count_preservation_cases.json"

SOURCES = {
    "ja": ["713-v2.7.4-count-stage5-ja-r1", "713-v2.7.4-count-stage5-ja-r2", "713-v2.7.4-count-stage5-ja-r3"],
    "en": ["713-v2.7.4-count-stage5b-en-r1", "713-v2.7.4-count-stage5b-en-r2", "713-v2.7.4-count-stage5b-en-r3"],
}

# single-group bench lines only: one requested count, one instruction, no matching to do
REQUESTED = {
    1: 3, 2: 7, 3: 11, 4: 12, 5: 19, 6: 24, 7: 33, 8: 47, 9: 53, 10: 61,
    11: 74, 12: 86, 13: 99, 14: 117, 15: 120, 16: 155, 17: 188, 18: 220,
    19: 239, 20: 240, 21: 260, 22: 290, 23: 320, 24: 500, 25: 800,
}

REPRESENTATIVE = 110  # inside the 80-120 band the prompt asks for at 240 and above


def _source_doc(lang: str, line: int) -> tuple[dict, str]:
    """First run whose result is a real Stage 2 response, not the deterministic fallback."""
    for run in SOURCES[lang]:
        path = OUT2 / run / f"inku-batch-{line:03d}.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not doc.get("compose_fallback_used"):
            return doc, run
    raise SystemExit(f"no non-fallback sample for {lang} line {line}")


def build() -> dict:
    cases = []
    for lang in ("ja", "en"):
        for line, requested in sorted(REQUESTED.items()):
            doc, run = _source_doc(lang, line)
            score = copy.deepcopy(doc["score"])
            instructions = score.get("instructions") or []
            if not instructions:
                raise SystemExit(f"empty score for {lang} line {line}")
            # the instruction carrying the repetition is the one with the largest count
            idx = max(
                range(len(instructions)),
                key=lambda k: ((instructions[k].get("arrangement") or {}).get("count", 0)),
            )
            ins = instructions[idx]
            ins.setdefault("arrangement", {"count": 1, "layout": "scatter"})
            ins["arrangement"]["count"] = requested if requested < 240 else REPRESENTATIVE
            ins.pop("color_hint", None)  # coerce writes its notes here; start clean
            score["instructions"] = [ins]
            cases.append(
                {
                    "id": f"{lang}-{line:02d}",
                    "lang": lang,
                    "line": line,
                    "requested": requested,
                    "kind": "literal" if requested < 240 else "represented",
                    "source_run": run,
                    "ddl": doc["ddl"],
                    "score": score,
                }
            )
    return {
        "note": (
            "Compliant Stage 2 output for each single-group line of cli/bench/count. "
            "Replay through coerce_score to measure whether the pipeline keeps the count."
        ),
        "requested_counts": REQUESTED,
        "representative_count": REPRESENTATIVE,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.write:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(text, encoding="utf-8")
        print(f"wrote {TARGET.relative_to(REPO)} ({len(payload['cases'])} cases)")
    else:
        print(f"{len(payload['cases'])} cases; pass --write to freeze")


if __name__ == "__main__":
    main()
