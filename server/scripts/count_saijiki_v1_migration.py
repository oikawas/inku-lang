"""Count what the Saijiki v1 migration would do to an isolated copy of a database.

Read-only: the copy is opened with SQLite's ``mode=ro`` (and ``immutable``) and
nothing is written.
It prints one JSON object of counts, the word replacements the core would make,
and the ids (never the contents) of records the core refuses or that carry a
sweep it cannot associate. The copy must sit inside a run root that carries
the isolated-rehearsal marker, as for rehearse_persistence_migration.py.
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
                        help="count this many rows of each kind, drawn at random")
    args = parser.parse_args()
    database = _resolve_guarded_database(args.run_root, args.database)

    import inku_render

    # immutable: the copy may sit on a read-only mount, where SQLite could not
    # create the journal files a read-only open of a WAL database otherwise needs.
    connection = sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True)
    try:
        report = census(connection, inku_render.pipeline_migrate_saijiki_v1, sample=args.sample)
    finally:
        connection.close()
    json.dump({"ok": True, "census": report}, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
