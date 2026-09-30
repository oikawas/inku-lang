"""Rehearse the one-time Saijiki v2 migration on an isolated writable copy.

The copy must sit inside a run root that carries the isolated-rehearsal marker,
as for count_saijiki_v1_migration.py. The migration is the one
migrate_saijiki_v2.py writes (``saijiki_migration.migrate_once``): its safety
snapshot lands inside the run root, and its report, with how long each step
took, is written to --out as report.json, and each answer of the core to
journal.jsonl as it comes; stdout carries the counts only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from count_saijiki_v1_migration import _resolve_guarded_database

from inku_server.persistence.saijiki_migration import migrate_once


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1,
                        help="ask the core from this many worker processes at once")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="kill a call that runs longer than this many seconds, list its record, and go on")
    parser.add_argument("--out", type=Path, required=True, help="write progress.log and report.json here")
    args = parser.parse_args()
    database = _resolve_guarded_database(args.run_root, args.database)

    import inku_render

    with (args.out / "progress.log").open("a", encoding="utf-8", buffering=1) as log:
        report = migrate_once(database, inku_render.pipeline_migrate_saijiki_v1, workers=args.workers,
                              progress=lambda line: log.write(line + "\n"), journal=args.out / "journal.jsonl",
                              timeout=args.timeout)
    (args.out / "report.json").write_text(
        json.dumps({"ok": True, "rehearsal": report}, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    counts = {key: value for key, value in report.items()
              if key not in {"refused_records", "unassociated_sweep_records"}}
    counts["refused_records"] = len(report["refused_records"])
    counts["unassociated_sweep_records"] = len(report["unassociated_sweep_records"])
    json.dump({"ok": True, "rehearsal": counts}, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
