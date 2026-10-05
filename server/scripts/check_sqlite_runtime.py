"""Verify the release SQLite identity and, optionally, isolated persistence operations."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import _sqlite3

ROOT = Path("/opt/inku-sqlite")


def identity() -> dict:
    contract = json.loads((ROOT / "contract.json").read_text())
    metadata = json.loads((ROOT / "metadata.json").read_text())
    if any(metadata.get(key) != value for key, value in contract.items()):
        raise RuntimeError("SQLite artifact metadata does not match the release contract")
    if sqlite3.sqlite_version != contract["sqlite_version"] or sys.version.split()[0] != contract["python_version"]:
        raise RuntimeError("Python is using a different SQLite or Python version")
    library = (ROOT / "lib" / "libsqlite3.so.0").resolve(strict=True)
    loaded = {line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()}
    if str(library) not in loaded:
        raise RuntimeError("Python has not loaded the selected SQLite library")
    for path, key in ((library, "library_sha256"), (Path(_sqlite3.__file__), "module_sha256")):
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata[key]:
            raise RuntimeError("SQLite artifact checksum mismatch")
    for name in ("Ubuntu-libsqlite3-copyright.txt", "CPython-LICENSE.txt"):
        if not (ROOT / "licenses" / name).stat().st_size:
            raise RuntimeError("SQLite distribution notice is missing")
    return metadata


def operations() -> None:
    # Nothing in /data or an application DB is opened; all fixture data is temporary.
    with tempfile.TemporaryDirectory(prefix="inku-sqlite-smoke-") as folder:
        database = Path(folder) / "source.db"
        backup = Path(folder) / "backup.db"
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            if connection.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
                raise RuntimeError("WAL is unavailable")
            connection.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
            connection.execute("CREATE TABLE child(parent_id REFERENCES parent(id))")
            connection.execute("INSERT INTO parent VALUES (1)")
            connection.execute("INSERT INTO child VALUES (1)")
            connection.execute("CREATE VIRTUAL TABLE search USING fts5(body)")
            connection.execute("INSERT INTO search VALUES ('two red kites')")
            connection.commit()
            try:
                connection.execute("INSERT INTO child VALUES (2)")
            except sqlite3.IntegrityError:
                connection.rollback()
            else:
                raise RuntimeError("Foreign key rejection failed")
            if connection.execute("SELECT count(*) FROM child").fetchone() != (1,):
                raise RuntimeError("Transaction rollback failed")
            if connection.execute("SELECT count(*) FROM search WHERE search MATCH 'kites'").fetchone() != (1,):
                raise RuntimeError("FTS5 query failed")
            if connection.execute("SELECT json_valid(?), json_extract(?, '$.value')", ('{"value":1}', '{"value":1}')).fetchone() != (1, 1):
                raise RuntimeError("JSON functions failed")
            with sqlite3.connect(backup) as target:
                connection.backup(target)
        with sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True) as saved:
            saved.execute("PRAGMA query_only=ON")
            if saved.execute("PRAGMA quick_check(1)").fetchall() != [("ok",)]:
                raise RuntimeError("Backup integrity failed")
            if saved.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("Backup foreign keys failed")
            if saved.execute("SELECT count(*) FROM search WHERE search MATCH 'kites'").fetchone() != (1,):
                raise RuntimeError("Committed WAL data did not reach the backup")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-operations", action="store_true")
    args = parser.parse_args()
    result = identity()
    if args.check_operations:
        operations()
        result["operations_ok"] = True
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
