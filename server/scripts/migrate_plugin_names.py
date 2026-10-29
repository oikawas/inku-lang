"""Count or migrate saved plugin names, once, while the Server is stopped.

The default is a read-only census. --write takes a verified SQLite snapshot
before updating saved DDL and its digests under a single writer lock. Never run
this against a live service database. Each core answer is journaled; the whole
report is saved beside the database unless --report is given.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from inku_server.persistence.plugin_name_migration import census, migrate_once


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="perform the one-time migration")
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    import inku_render

    database = args.database.expanduser().resolve(strict=True)
    reports = database.parent / "migration-backups"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = time.time_ns()
    journal = reports / f"{database.stem}-plugin-names-v2-{stamp}.jsonl"
    report_path = args.report or reports / f"{database.stem}-plugin-names-v2-{stamp}.json"
    operation = migrate_once if args.write else census
    result = operation(database, inku_render.pipeline_migrate_plugin_names,
                       workers=args.workers, timeout=args.timeout, journal=journal)
    report_path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    report_path.chmod(0o600)
    json.dump({"write": args.write, "report": str(report_path), "journal": str(journal),
               "counts": result["counts"], "refused": len(result["refused_records"])},
              sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
