"""Rehearse the exact migration inside a marker-guarded isolated run tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine

from inku_server.persistence.migrations import (
    MIGRATION_CHECKSUM,
    MIGRATION_NAME,
    MIGRATION_VERSION,
    PRODUCTION_STAGE0_FINGERPRINT,
    history_fts_state,
    schema_fingerprint,
)

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
    try:
        database.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("rehearsal database escapes its isolated run root") from exc
    if not database.is_file():
        raise RuntimeError("rehearsal database is not a file")
    return database


def _encoded(value: object) -> bytes:
    if value is None:
        return b"n"
    payload = value if isinstance(value, bytes) else str(value).encode("utf-8")
    return len(payload).to_bytes(8, "big") + payload


def _history_evidence(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    with sqlite3.connect(path) as connection:
        cursor = connection.execute(
            "SELECT CAST(id AS BLOB), CAST(input AS BLOB), CAST(score AS BLOB), "
            "CAST(svg AS BLOB) FROM history ORDER BY id"
        )
        while rows := cursor.fetchmany(512):
            for row in rows:
                for value in row:
                    digest.update(_encoded(value))
                count += 1
    return count, digest.hexdigest()


def _preflight(
    path: Path,
    expected_fingerprint: str,
    expected_fts_state: str,
) -> tuple[int, str]:
    engine = create_engine(f"sqlite:///{path}", future=True)
    try:
        with engine.connect() as connection:
            fingerprint = schema_fingerprint(connection)
            fts_state = history_fts_state(connection)
    finally:
        engine.dispose()
    if fingerprint != expected_fingerprint or fts_state != expected_fts_state:
        raise RuntimeError("production snapshot fingerprint does not match Stage 0")
    return _history_evidence(path)


def _postflight(path: Path, before: tuple[int, str]) -> dict[str, object]:
    after = _history_evidence(path)
    if after != before:
        raise RuntimeError("canonical history digest changed during rehearsal")
    with sqlite3.connect(path) as connection:
        quick = connection.execute("PRAGMA quick_check").fetchall()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchmany(1)
        registry = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
    if quick != [("ok",)] or foreign_keys:
        raise RuntimeError("post-migration SQLite integrity check failed")
    if registry != [(MIGRATION_VERSION, MIGRATION_NAME, MIGRATION_CHECKSUM)]:
        raise RuntimeError("post-migration registry does not match the reviewed baseline")
    return {
        "history_rows": after[0],
        "history_digest_sha256": after[1],
        "migration_version": MIGRATION_VERSION,
        "migration_name": MIGRATION_NAME,
        "migration_checksum": MIGRATION_CHECKSUM,
    }


def rehearse(
    run_root: Path,
    relative_database: Path,
    expected_fingerprint: str,
    expected_fts_state: str = "complete",
) -> dict[str, object]:
    """Run migration and idempotent restart against the guarded copy."""
    path = _resolve_guarded_database(run_root, relative_database)
    before = _preflight(path, expected_fingerprint, expected_fts_state)
    os.environ["INKU_DB_URL"] = f"sqlite:///{path}"
    os.environ["INKU_THUMBS_DB_URL"] = "sqlite:///:memory:"
    os.environ["INKU_DB_BACKUP_SCHEDULER"] = "0"

    started = time.monotonic()
    from inku_server import db

    db.init_db()
    db.init_db()
    result = _postflight(path, before)
    result["duration_ms"] = round((time.monotonic() - started) * 1000)
    result["ok"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--expect-fingerprint", default=PRODUCTION_STAGE0_FINGERPRINT)
    parser.add_argument("--expect-fts-state", choices=("absent", "complete"), default="complete")
    args = parser.parse_args()
    try:
        result = rehearse(
            args.run_root,
            args.database,
            args.expect_fingerprint,
            args.expect_fts_state,
        )
    except Exception as exc:  # noqa: BLE001 - never expose a private path or row.
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
