"""Manual, atomic single-DDL migration with aggregate preservation evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import struct
import time
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import create_engine

from .backup import create_sqlite_snapshot
from .ddl_source import select_ddl
from .invariants import capture_invariants, require_integrity, verify_invariants
from .legacy_v3_schema import Base as LegacyBase
from .migrations import (
    LEGACY_V3_CHECKSUM, LEGACY_V3_NAME, LEGACY_V3_VERSION,
    MIGRATION_CHECKSUM, MIGRATION_NAME, MIGRATION_VERSION, MigrationStateError,
    _require_single_ddl_schema, _verify_registry, history_fts_state, schema_fingerprint,
)

# Characterized v3 inputs: the frozen ORM baseline and the deployed baseline.
# Adding tables, columns, constraints or indexes requires an explicit review;
# a matching registry alone never admits an unknown physical schema.
ACCEPTED_V3_FINGERPRINTS = frozenset({
    "b254795e98f07ba93731e2e5c8d3a6a19c8586346528b7b0b869f2a5e33bc3ea",
    "a5635cc89503895877c971d4f14a9ec3a2481d048e994a1b9d98bab1d5457160",
})


class DdlMigrationError(MigrationStateError):
    """Refusal or rollback; a completed safety backup is retained."""

    def __init__(self, message: str, *, backup: Path | None = None) -> None:
        super().__init__(message)
        self.backup = backup


def _name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise DdlMigrationError("unexpected persistent SQL identifier")
    return '"' + value + '"'


def _database(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or path != path.resolve():
        raise DdlMigrationError("database must be an existing canonical regular file")
    return path


def _engine(path: Path, *, readonly: bool):
    uri = "file:" + quote(str(path), safe="/") + ("?mode=ro" if readonly else "?mode=rw")
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True, timeout=30))


def _registry(connection) -> list[dict]:
    return [dict(zip(("version", "name", "checksum"), row, strict=True)) for row in
            connection.exec_driver_sql("SELECT version,name,checksum FROM schema_migrations ORDER BY version")]


def _require_v3(connection, *, restored_fingerprint: str | None = None) -> None:
    if _registry(connection) != [{"version": LEGACY_V3_VERSION, "name": LEGACY_V3_NAME,
                                  "checksum": LEGACY_V3_CHECKSUM}]:
        raise DdlMigrationError("expected the reviewed v3 registry")
    fingerprint = schema_fingerprint(connection)
    if fingerprint not in ACCEPTED_V3_FINGERPRINTS and fingerprint != restored_fingerprint:
        raise DdlMigrationError("unrecognized v3 physical schema fingerprint: " + fingerprint)
    tables = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in LegacyBase.metadata.sorted_tables:
        if table.name not in tables:
            raise DdlMigrationError("v3 persistent table is missing: " + table.name)
        columns = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({_name(table.name)})")}
        if not set(table.columns.keys()) <= columns:
            raise DdlMigrationError("v3 persistent columns are missing: " + table.name)
    history = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(history)")}
    if "ddl_source_origin" in history:
        raise DdlMigrationError("v3 registry contains a partial single-DDL schema")
    if sqlite3.sqlite_version_info < (3, 35, 0):
        raise DdlMigrationError("SQLite DROP COLUMN support is required")
    if history_fts_state(connection) == "partial":
        raise DdlMigrationError("history FTS objects are internally inconsistent")
    require_integrity(connection)


def _encoded(value) -> bytes:
    if value is None:
        return b"n"
    if isinstance(value, bytes):
        payload, kind = value, b"b"
    elif isinstance(value, int):
        payload, kind = str(value).encode("ascii"), b"i"
    elif isinstance(value, float):
        payload, kind = struct.pack("!d", value), b"f"
    else:
        payload, kind = str(value).encode("utf-8"), b"t"
    return kind + len(payload).to_bytes(8, "big") + payload


def _hash_query(connection, sql: str) -> tuple[int, str]:
    count, digest = 0, hashlib.sha256()
    result = connection.exec_driver_sql(sql)
    while rows := result.fetchmany(256):
        for row in rows:
            digest.update(len(row).to_bytes(4, "big"))
            for value in row:
                digest.update(_encoded(value))
            count += 1
    return count, digest.hexdigest()


def _protected(connection, *, exclude_ddl: bool) -> dict:
    evidence = {}
    for (table,) in connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "AND name NOT LIKE 'history_fts%' AND name <> 'schema_migrations' ORDER BY name"
    ):
        info = list(connection.exec_driver_sql(f"PRAGMA table_info({_name(table)})"))
        columns = [row[1] for row in info if not (
            exclude_ddl and table == "history" and row[1] in {"ddl", "expanded_ddl", "ddl_source_origin"}
        )]
        order = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]] or columns
        fields = ",".join(_name(column) for column in columns)
        if table == "history":
            fields = "rowid," + fields
        evidence[table] = (columns, _hash_query(connection, f"SELECT {fields} FROM {_name(table)} ORDER BY " +
                                               ",".join(_name(column) for column in order)))
    return evidence


def _selection(connection, *, current: bool) -> tuple[int, dict, str]:
    counts = {"ddl": 0, "legacy_expanded": 0, "absent": 0}
    digest, count = hashlib.sha256(), 0
    sql = ("SELECT id,ddl,ddl_source_origin FROM history ORDER BY id" if current else
           "SELECT id,ddl,expanded_ddl FROM history ORDER BY id")
    from .ddl_source import has_ddl_body
    for work_id, ddl, other in connection.exec_driver_sql(sql):
        if any(value is not None and not isinstance(value, str) for value in (ddl, other)):
            raise DdlMigrationError("history instruction values must be TEXT or NULL")
        selected, origin = (ddl, other) if current else select_ddl(ddl, other)
        if origin not in (None, "legacy_expanded"):
            raise DdlMigrationError("unrecognized saved DDL source origin")
        counts["legacy_expanded" if origin else "ddl" if has_ddl_body(selected) else "absent"] += 1
        for value in (work_id, selected, origin):
            digest.update(_encoded(value))
        count += 1
    return count, counts, digest.hexdigest()


def _require_links(connection, *, current: bool) -> int:
    columns = "h.ddl,h.ddl_source_origin" if current else "h.ddl,h.expanded_ddl"
    rows = connection.exec_driver_sql(
        "SELECT l.history_id,l.ddl_digest," + columns + " FROM pipeline_history_links AS l "
        "LEFT JOIN history AS h ON h.id=l.history_id"
    )
    count = 0
    for work_id, recorded, ddl, other in rows:
        selected = ddl if current else select_ddl(ddl, other)[0]
        if selected is None or hashlib.sha256(selected.encode("utf-8")).hexdigest() != recorded:
            raise DdlMigrationError("linked history selected DDL does not match its saved digest")
        count += 1
    return count


def _fts_contents_match(connection) -> None:
    if history_fts_state(connection) != "complete":
        return
    # rank=1 checks an external-content index against its content table.
    connection.exec_driver_sql("INSERT INTO history_fts(history_fts,rank) VALUES('integrity-check',1)")


def inspect_database(path: Path, *, expect_version: int = 3, expected_fingerprint: str | None = None,
                     source_commit: str, _restored_fingerprint: str | None = None) -> dict:
    if expect_version != LEGACY_V3_VERSION or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise DdlMigrationError("expected v3 and an exact product source SHA")
    path = _database(path)
    engine = _engine(path, readonly=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA query_only=ON")
            state = _verify_registry(connection)
            current = state == "current"
            if current:
                _require_single_ddl_schema(connection)
                require_integrity(connection)
                if history_fts_state(connection) == "partial":
                    raise DdlMigrationError("history FTS objects are internally inconsistent")
            else:
                _require_v3(connection, restored_fingerprint=_restored_fingerprint)
            fingerprint = schema_fingerprint(connection)
            if expected_fingerprint is not None and fingerprint != expected_fingerprint:
                raise DdlMigrationError("database schema does not match the expected fingerprint")
            rows, counts, selection_hash = _selection(connection, current=current)
            links = _require_links(connection, current=current)
            registry = _registry(connection)
            page_size = connection.exec_driver_sql("PRAGMA page_size").scalar_one()
            page_count = connection.exec_driver_sql("PRAGMA page_count").scalar_one()
            logical_bytes = page_size * page_count
            return {
                "status": "already_current" if current else "dry_run", "source_commit": source_commit,
                "source_registry": registry, "target_registry": registry if current else registry + [{
                    "version": MIGRATION_VERSION, "name": MIGRATION_NAME, "checksum": MIGRATION_CHECKSUM,
                }], "source_fingerprint": fingerprint, "target_fingerprint": fingerprint if current else None,
                "rows": rows, "classifications": counts, "selection_digest": selection_hash,
                "linked_history": links, "sqlite_version": sqlite3.sqlite_version,
                "backup": None, "report": None, "elapsed_seconds": 0.0,
                "storage": {"source_logical_bytes": logical_bytes,
                            "free_bytes": shutil.disk_usage(path.parent).free,
                            "minimum_free_bytes": logical_bytes * 3 + 16 * 1024 * 1024},
                "pragmas": {"journal_mode": connection.exec_driver_sql("PRAGMA journal_mode").scalar_one(),
                            "page_size": page_size, "foreign_keys": connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()},
                "verification": {"source_schema": True, "selected_link_digests": True, "integrity": True},
            }
    finally:
        engine.dispose()


def _write_report(path: Path, report: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _replace_report(path: Path, report: dict) -> None:
    pending = path.with_name(path.name + f".pending-{time.time_ns()}")
    _write_report(pending, report)
    pending.replace(path)


def migrate_history_ddl(path: Path, *, source_commit: str, expect_version: int = 3,
                        expected_fingerprint: str | None = None, report_path: Path | None = None,
                        _restored_fingerprint: str | None = None, _restoration: dict | None = None) -> dict:
    began = time.monotonic()
    before_report = inspect_database(path, expect_version=expect_version,
                                     expected_fingerprint=expected_fingerprint, source_commit=source_commit,
                                     _restored_fingerprint=_restored_fingerprint)
    if before_report["status"] == "already_current":
        return before_report
    if before_report["storage"]["free_bytes"] < before_report["storage"]["minimum_free_bytes"]:
        raise DdlMigrationError("insufficient free space for a safety backup and SQLite transaction")
    if _restoration is not None:
        before_report["restoration"] = _restoration
    if report_path is not None and (not report_path.is_absolute() or report_path != report_path.resolve() or
                                    not report_path.parent.is_dir() or report_path.exists() or report_path.is_symlink()):
        raise DdlMigrationError("report must be a new canonical file in an existing directory")
    backup_path = path.parent / "migration-backups" / f"{path.stem}-pre-history-ddl-{time.time_ns()}.db"
    snapshot = create_sqlite_snapshot(path, backup_path)
    report_path = report_path or snapshot.path.with_suffix(".report.json")
    prepared = dict(before_report, status="prepared", backup=str(snapshot.path), report=str(report_path))
    try:
        _write_report(report_path, prepared)
    except OSError as error:
        raise DdlMigrationError("could not persist the prepared migration report", backup=snapshot.path) from error
    snapshot_engine = _engine(snapshot.path, readonly=True)
    engine = _engine(path, readonly=False)
    final = dict(prepared)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                _require_v3(connection, restored_fingerprint=_restored_fingerprint)
                if schema_fingerprint(connection) != before_report["source_fingerprint"]:
                    raise DdlMigrationError("source schema changed before the writer lock")
                with snapshot_engine.connect() as safe:
                    if (schema_fingerprint(safe) != schema_fingerprint(connection) or
                            _protected(safe, exclude_ddl=False) != _protected(connection, exclude_ddl=False) or
                            list(safe.exec_driver_sql("SELECT * FROM schema_migrations ORDER BY version")) !=
                            list(connection.exec_driver_sql("SELECT * FROM schema_migrations ORDER BY version"))):
                        raise DdlMigrationError("safety backup differs from the locked preimage")
                protected = _protected(connection, exclude_ddl=True)
                canonical = capture_invariants(connection)
                rows, counts, selected_digest = _selection(connection, current=False)
                _require_links(connection, current=False)
                fts_before = history_fts_state(connection)
                connection.exec_driver_sql("ALTER TABLE history ADD COLUMN ddl_source_origin TEXT")
                pending = list(connection.exec_driver_sql("SELECT id,ddl,expanded_ddl FROM history"))
                for work_id, ddl, expanded in pending:
                    selected, origin = select_ddl(ddl, expanded)
                    if origin is not None:
                        connection.exec_driver_sql("UPDATE history SET ddl=?,ddl_source_origin=? WHERE id=?",
                                                   (selected, origin, work_id))
                connection.exec_driver_sql("ALTER TABLE history DROP COLUMN expanded_ddl")
                _require_single_ddl_schema(connection)
                if _selection(connection, current=True) != (rows, counts, selected_digest):
                    raise DdlMigrationError("selected instruction bytes changed during migration")
                if _protected(connection, exclude_ddl=True) != protected:
                    raise DdlMigrationError("migration changed protected persistent values or rowids")
                verify_invariants(connection, canonical)
                _require_links(connection, current=True)
                if history_fts_state(connection) != fts_before:
                    raise DdlMigrationError("history FTS schema changed during migration")
                _fts_contents_match(connection)
                require_integrity(connection)
                connection.exec_driver_sql(
                    "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",
                    (MIGRATION_VERSION, MIGRATION_NAME, MIGRATION_CHECKSUM, int(time.time() * 1000)),
                )
                _verify_registry(connection)
                final.update(status="migrated", target_registry=_registry(connection),
                             target_fingerprint=schema_fingerprint(connection), rows=rows, classifications=counts,
                             selection_digest=selected_digest, elapsed_seconds=round(time.monotonic() - began, 3),
                             report=str(report_path),
                             writer_foreign_keys=connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(),
                             verification={"source_schema": True, "backup_matches_locked_preimage": True,
                                           "selected_bytes": True, "all_protected_values": True,
                                           "primary_keys_and_rowids": True, "selected_link_digests": True,
                                           "fts": True, "integrity": True, "target_schema": True})
                _replace_report(report_path, dict(final, status="committing"))
                connection.commit()
            except Exception as error:
                connection.rollback()
                reason = str(error) if isinstance(error, DdlMigrationError) else type(error).__name__
                _replace_report(report_path, dict(prepared, status="rolled_back", error=reason))
                raise DdlMigrationError("history DDL migration rolled back: " + reason, backup=snapshot.path) from error
        try:
            _replace_report(report_path, final)
        except OSError as error:
            raise DdlMigrationError("migration committed; final report persistence is uncertain",
                                    backup=snapshot.path) from error
        return final
    finally:
        snapshot_engine.dispose()
        engine.dispose()
