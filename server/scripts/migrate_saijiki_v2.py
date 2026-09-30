"""Move the saved records of the Server's SQLite database to Saijiki v2, once.

Run it with the new release's code and native wheel while the service is
stopped, before the new release starts (the author, 2026-09-30: by hand, not at
startup). It keeps a verified Backup API snapshot in ``migration-backups/``
beside the database, then writes under a single writer lock; a failure rolls
back and keeps the snapshot, and a second run refuses. Records the core
refuses stay as they were. Each answer of the core is written to a journal
beside the snapshot as it comes, so a run that stops leaves what it got. The
whole report -- counts, every refused record with its error and text, and the
timings -- is written to --report (by default beside the snapshot); stdout
carries the counts only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from inku_server.persistence.saijiki_migration import migrate_once


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="the SQLite database to migrate")
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1),
                        help="ask the core from this many worker processes at once")
    parser.add_argument("--report", type=Path, default=None,
                        help="write the whole report here (default: beside the snapshot)")
    args = parser.parse_args()

    import inku_render

    journal = args.database.expanduser().resolve().parent / "migration-backups" / (
        f"{args.database.stem}-saijiki-v2-journal-{time.time_ns()}.jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    print(f"journal: {journal}", file=sys.stderr, flush=True)
    report = migrate_once(args.database, inku_render.pipeline_migrate_saijiki_v1, workers=args.workers,
                          progress=lambda line: print(line, file=sys.stderr, flush=True), journal=journal)
    path = args.report or Path(report["snapshot"]).with_name(
        f"{args.database.stem}-saijiki-v2-{time.time_ns()}.json")
    path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    counts = {key: value for key, value in report.items()
              if key not in {"refused_records", "unassociated_sweep_records"}}
    counts["refused_records"] = len(report["refused_records"])
    counts["unassociated_sweep_records"] = len(report["unassociated_sweep_records"])
    counts["report"] = str(path)
    json.dump({"ok": True, "migration": counts}, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
