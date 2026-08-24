"""Verified SQLite snapshots shared by migrations and operator backups."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


class SQLiteSnapshotError(RuntimeError):
    """A consistent, readable SQLite snapshot could not be produced."""


@dataclass(frozen=True)
class SQLiteSnapshot:
    """Aggregate evidence for a completed SQLite-native snapshot."""

    path: Path
    size_bytes: int


def _read_only_uri(path: Path) -> str:
    return f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"


def verify_sqlite_snapshot(path: Path) -> None:
    """Open a snapshot read-only and require SQLite's quick integrity check."""
    try:
        with sqlite3.connect(_read_only_uri(path), uri=True) as connection:
            result = connection.execute("PRAGMA quick_check").fetchall()
    except sqlite3.Error as exc:
        raise SQLiteSnapshotError("SQLite snapshot could not be opened") from exc
    if result != [("ok",)]:
        raise SQLiteSnapshotError("SQLite snapshot failed quick_check")


def create_sqlite_snapshot(source: Path, destination: Path) -> SQLiteSnapshot:
    """Create and verify a WAL-safe snapshot through SQLite's Backup API.

    There is deliberately no plain-file fallback. A main-file copy can omit
    committed WAL pages and look successful while silently losing data.
    """
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if source == destination:
        raise SQLiteSnapshotError("SQLite snapshot destination equals its source")
    if not source.is_file():
        raise SQLiteSnapshotError("SQLite snapshot source is not available")
    if destination.exists():
        raise SQLiteSnapshotError("SQLite snapshot destination already exists")

    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with sqlite3.connect(_read_only_uri(source), uri=True) as source_connection:
            with sqlite3.connect(destination) as destination_connection:
                created = True
                source_connection.backup(destination_connection)
        verify_sqlite_snapshot(destination)
    except Exception as exc:
        if created:
            destination.unlink(missing_ok=True)
        if isinstance(exc, SQLiteSnapshotError):
            raise
        raise SQLiteSnapshotError("SQLite Backup API failed") from exc
    return SQLiteSnapshot(path=destination, size_bytes=destination.stat().st_size)
