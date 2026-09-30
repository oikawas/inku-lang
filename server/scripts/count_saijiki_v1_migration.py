"""Count what the Saijiki v1 migration would do to an isolated copy of a database.

Read-only: the copy is opened with SQLite's ``mode=ro`` (and ``immutable``) and
nothing is written. The count is the same plan the startup migration writes
(``saijiki_migration.plan``): what each kind of saved record would become,
every record the core refuses with its error and text, the sweeps it cannot
associate, and the time the core took. With --out, the whole report is written
there as report.json; stdout carries the counts only. The copy must sit inside
a run root that carries the isolated-rehearsal marker, as for
rehearse_persistence_migration.py.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from inku_server.persistence.saijiki_migration import census

_RUN_MARKER = ".inku-persistence-rehearsal"
_RUN_MARKER_CONTENT = "I-372 isolated copy\n"


def _resolve_guarded_database(run_root: Path, relative_database: Path) -> Path:
    root = run_root.expanduser().resolve(strict=True)
    marker = root / _RUN_MARKER
    if marker.is_symlink() or not marker.is_file():
        raise RuntimeError("isolated rehearsal marker is missing")
    if marker.read_text(encoding="utf-8") != _RUN_MARKER_CONTENT:
        raise RuntimeError("isolated rehearsal marker is invalid")
    if relative_database.is_absolute() or ".." in relative_database.parts:
        raise RuntimeError("rehearsal database must be a contained relative path")
    unresolved = root / relative_database
    if unresolved.is_symlink():
        raise RuntimeError("rehearsal database must not be a symlink")
    database = unresolved.resolve(strict=True)
    database.relative_to(root)
    if not database.is_file():
        raise RuntimeError("rehearsal database is not a file")
    return database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--sample", type=int, default=None,
                        help="count this many variations and works, drawn at random")
    parser.add_argument("--refused-texts", type=int, default=0,
                        help="kept for the sampling lane; every refused record is listed with its text")
    parser.add_argument("--history-ids", type=Path, default=None,
                        help="count only these works (<history id> or <history id>:<column>, one per line)")
    parser.add_argument("--workers", type=int, default=1,
                        help="ask the core from this many threads at once")
    parser.add_argument("--out", type=Path, default=None,
                        help="write progress.log and report.json here")
    args = parser.parse_args()
    database = _resolve_guarded_database(args.run_root, args.database)

    import inku_render

    # immutable: the copy may sit on a read-only mount, where SQLite could not
    # create the journal files a read-only open of a WAL database otherwise needs.
    connection = sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True)
    log = (args.out / "progress.log").open("a", encoding="utf-8", buffering=1) if args.out else None
    ids = None
    if args.history_ids:
        ids = {line.strip().partition(":")[0]
               for line in args.history_ids.read_text(encoding="utf-8").splitlines() if line.strip()}
    try:
        report = census(connection, inku_render.pipeline_migrate_saijiki_v1, workers=args.workers,
                        sample=args.sample, history_ids=ids, progress=(lambda line: log.write(line + "\n")) if log else None)
    finally:
        connection.close()
        if log:
            log.close()
    if args.out:
        (args.out / "report.json").write_text(
            json.dumps({"ok": True, "census": report}, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    counts = {key: value for key, value in report.items()
              if key not in {"refused_records", "unassociated_sweep_records"}}
    counts["refused_records"] = len(report["refused_records"])
    counts["unassociated_sweep_records"] = len(report["unassociated_sweep_records"])
    json.dump({"ok": True, "census": counts}, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
