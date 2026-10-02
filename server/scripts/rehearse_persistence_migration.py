"""Rehearse the exact migration inside a marker-guarded isolated run tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
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


def _resolve_guarded_database(run_root: Path, relative_database: Path, *, history_ddl: bool = False) -> Path:
    root = run_root.expanduser().resolve(strict=True)
    marker = root / _RUN_MARKER
    if marker.is_symlink() or not marker.is_file():
        raise RuntimeError("isolated rehearsal marker is missing")
    expected_marker = "I-706 history-ddl isolated copy\n" if history_ddl else _RUN_MARKER_CONTENT
    if marker.read_text(encoding="utf-8") != expected_marker:
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
    if MIGRATION_VERSION >= 4:
        raise RuntimeError("legacy rehearsal requires the historical source; select history-ddl for v4")
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
    parser.add_argument("--migration", choices=("legacy", "history-ddl"), default="legacy")
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    try:
        result = rehearse_history_ddl(args.run_root, args.database, args.source_commit) if args.migration == "history-ddl" else rehearse(
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


def rehearse_history_ddl(run_root: Path, relative_database: Path, source_commit: str) -> dict[str, object]:
    """Migrate once, verify full invariants, then boot twice in fresh processes."""
    from inku_server.persistence.ddl_migration import inspect_database

    path = _resolve_guarded_database(run_root, relative_database, history_ddl=True)
    snapshot = json.loads((path.parent / "snapshot.json").read_text(encoding="utf-8"))
    before = _history_evidence(path)
    report_path = path.parent / "migration-report.json"
    command = [sys.executable, str(Path(__file__).with_name("migrate_history_ddl.py")),
               "--database", str(path), "--expect-version", "3", "--source-commit", source_commit,
               "--expect-fingerprint", snapshot["source_fingerprint"], "--report", str(report_path), "--apply"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    (path.parent / "migration-stdout.json").write_text(completed.stdout, encoding="utf-8")
    (path.parent / "migration-stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError("manual history DDL migration failed; copy and diagnostics retained")
    report = json.loads(completed.stdout)
    if (report != json.loads(report_path.read_text(encoding="utf-8")) or report["status"] != "migrated"
            or report["source_commit"] != source_commit or not report["verification"]
            or not all(value is True for value in report["verification"].values())):
        raise RuntimeError("manual migration report is not fully verified")
    if _history_evidence(path) != before:
        raise RuntimeError("canonical history artifacts changed")
    environment = dict(os.environ, INKU_DB_URL=f"sqlite:///{path}",
                       INKU_THUMBS_DB_URL="sqlite:///:memory:", INKU_DB_BACKUP_SCHEDULER="0")
    for _ in range(2):
        subprocess.run([sys.executable, "-c", "from inku_server import db; db.init_db()"],
                       env=environment, check=True, capture_output=True)
        current = inspect_database(path, expect_version=3, source_commit=source_commit)
        if (current["status"] != "already_current" or current["target_registry"] != report["target_registry"]
                or current["target_fingerprint"] != report["target_fingerprint"]
                or current["selection_digest"] != report["selection_digest"]
                or current["rows"] != report["rows"] or current["classifications"] != report["classifications"]
                or not all(value is True for value in current["verification"].values())
                or _history_evidence(path) != before):
            raise RuntimeError("startup changed or failed current schema identity")
    result = {"ok": True, "migration": "history-ddl", "source_commit": source_commit,
              "sqlite_version": sqlite3.sqlite_version, "startup_count": 2,
              "migration_report": str(report_path), "candidate_copy_retained": True,
              "canonical_history_digest_sha256": before[1], "history_rows": before[0]}
    (path.parent / "rehearsal.json").write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    sys.exit(main())
