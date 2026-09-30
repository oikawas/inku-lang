"""Move the saved records of the Server's SQLite database to Saijiki v2, once.

Run it with the new release's code and native wheel while the service is
stopped, before the new release starts (the author, 2026-09-30: by hand, not at
startup). It keeps a verified Backup API snapshot in ``migration-backups/``
beside the database, then writes under a single writer lock; a failure rolls
back and keeps the snapshot, and a second run refuses. Records the core
refuses stay as they were. A call to the core that gives no answer within
--timeout seconds, or whose process dies, stops the whole run: nothing is
written, the snapshot stays, and the exit status is not zero (the author,
2026-09-30: a production migration that fails stops there). Each answer of the core is written to a journal
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


def _blank_list(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="the SQLite database to migrate")
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1),
                        help="ask the core from this many worker processes at once")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="stop the whole run if a call to the core gives no answer within this many seconds")
    parser.add_argument("--blank", type=Path, default=None,
                        help="empty these history texts instead of migrating them (<history id>:<column>, one per line)")
    parser.add_argument("--report", type=Path, default=None,
                        help="write the whole report here (default: beside the snapshot)")
    args = parser.parse_args()

    import inku_render

    journal = args.database.expanduser().resolve().parent / "migration-backups" / (
        f"{args.database.stem}-saijiki-v2-journal-{time.time_ns()}.jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    print(f"journal: {journal}", file=sys.stderr, flush=True)
    report = migrate_once(args.database, inku_render.pipeline_migrate_saijiki_v1, workers=args.workers,
                          progress=lambda line: print(line, file=sys.stderr, flush=True), journal=journal,
                          timeout=args.timeout, abort_on_failure=True, blank=_blank_list(args.blank))
    path = args.report or Path(report["snapshot"]).with_name(
        f"{args.database.stem}-saijiki-v2-{time.time_ns()}.json")
    path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    counts = {key: value for key, value in report.items()
              if key not in {"refused_records", "blanked_records", "unassociated_sweep_records"}}
    counts["refused_records"] = len(report["refused_records"])
    counts["unassociated_sweep_records"] = len(report["unassociated_sweep_records"])
    counts["blanked_records"] = len(report["blanked_records"])
    counts["report"] = str(path)
    json.dump({"ok": True, "migration": counts}, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
