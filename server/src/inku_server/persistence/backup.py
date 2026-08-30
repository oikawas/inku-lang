"""Verified SQLite snapshots shared by migrations and operator backups."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time as clock_time, timedelta
from pathlib import Path
from urllib.parse import quote


DB_BACKUP_SETTINGS_KEY = "db_backup_settings"
DB_BACKUP_DEFAULT_SETTINGS = {
    "interval_days": 7,
    "max_generations": 4,
    "backup_hour": 3,
    "backup_minute": 0,
    "last_auto_backup_at": 0,
}
# How many entries the status payload carries. The counts and the total size are
# reported for every file, so a truncated list never hides how much disk is used.
DB_BACKUP_LIST_LIMIT = 50


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

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the exact path atomically and keep credential-bearing backups
    # owner-only from their first byte. O_EXCL also refuses symlink replacement.
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise SQLiteSnapshotError("SQLite snapshot destination already exists") from exc
    except OSError as exc:
        raise SQLiteSnapshotError("SQLite snapshot destination could not be created") from exc
    created = True
    try:
        os.close(descriptor)
        with sqlite3.connect(_read_only_uri(source), uri=True) as source_connection:
            with sqlite3.connect(destination) as destination_connection:
                source_connection.backup(destination_connection)
        verify_sqlite_snapshot(destination)
    except Exception as exc:
        if created:
            destination.unlink(missing_ok=True)
        if isinstance(exc, SQLiteSnapshotError):
            raise
        raise SQLiteSnapshotError("SQLite Backup API failed") from exc
    return SQLiteSnapshot(path=destination, size_bytes=destination.stat().st_size)


@dataclass(frozen=True)
class BackupService:
    """Backup policy with host runtime dependencies supplied explicitly."""

    backup_dir: Path
    dialect_name: str
    database_path: Callable[[], Path | None]
    now_ms: Callable[[], int]
    read_setting: Callable[[str], dict | None]
    write_setting: Callable[[str, dict], dict]

    def normalize_settings(self, settings: dict | None) -> dict:
        clean = dict(DB_BACKUP_DEFAULT_SETTINGS)
        if not isinstance(settings, dict):
            return clean
        if "interval_days" in settings:
            try:
                interval_days = int(settings["interval_days"])
            except (TypeError, ValueError) as exc:
                raise ValueError("backup interval days must be an integer") from exc
            if interval_days < 1 or interval_days > 365:
                raise ValueError("backup interval days must be between 1 and 365")
            clean["interval_days"] = interval_days
        if "max_generations" in settings:
            try:
                max_generations = int(settings["max_generations"])
            except (TypeError, ValueError) as exc:
                raise ValueError("backup max generations must be an integer") from exc
            if max_generations < 1 or max_generations > 100:
                raise ValueError("backup max generations must be between 1 and 100")
            clean["max_generations"] = max_generations
        for key, limit in (("backup_hour", 23), ("backup_minute", 59)):
            if key not in settings:
                continue
            try:
                value = int(settings[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"backup {key} must be an integer") from exc
            if value < 0 or value > limit:
                raise ValueError(f"backup {key} must be between 0 and {limit}")
            clean[key] = value
        if "last_auto_backup_at" in settings:
            try:
                clean["last_auto_backup_at"] = max(0, int(settings["last_auto_backup_at"]))
            except (TypeError, ValueError):
                clean["last_auto_backup_at"] = 0
        return clean

    def get_settings(self) -> dict:
        return self.normalize_settings(self.read_setting(DB_BACKUP_SETTINGS_KEY))

    def update_settings(
        self,
        interval_days: int,
        max_generations: int,
        backup_hour: int | None = None,
        backup_minute: int | None = None,
    ) -> dict:
        current = self.get_settings()
        current["interval_days"] = interval_days
        current["max_generations"] = max_generations
        if backup_hour is not None:
            current["backup_hour"] = backup_hour
        if backup_minute is not None:
            current["backup_minute"] = backup_minute
        clean = self.normalize_settings(current)
        return self.write_setting(DB_BACKUP_SETTINGS_KEY, clean)

    def backup_file(self, kind: str, at_ms: int) -> Path:
        timestamp = datetime.fromtimestamp(at_ms / 1000).strftime("%Y%m%d-%H%M%S")
        return self.backup_dir / kind / f"inku-{kind}-{timestamp}.db"

    def copy_sqlite_database(self, destination: Path) -> None:
        source = self.database_path()
        if not source or not source.exists():
            raise ValueError("SQLite DB file is not available")
        create_sqlite_snapshot(source, destination)

    def prune_auto_backups(self, max_generations: int) -> None:
        auto_dir = self.backup_dir / "auto"
        if not auto_dir.exists():
            return
        backups = sorted(
            auto_dir.glob("inku-auto-*.db"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old in backups[max_generations:]:
            old.unlink(missing_ok=True)

    def create_backup(self, *, manual: bool = False) -> dict:
        if self.dialect_name != "sqlite":
            raise ValueError("DB backup replicas are supported only for SQLite file databases")
        at_ms = self.now_ms()
        kind = "manual" if manual else "auto"
        path = self.backup_file(kind, at_ms)
        self.copy_sqlite_database(path)
        settings = self.get_settings()
        if not manual:
            settings["last_auto_backup_at"] = at_ms
            self.write_setting(DB_BACKUP_SETTINGS_KEY, settings)
            self.prune_auto_backups(settings["max_generations"])
        return {
            "path": str(path),
            "at": at_ms,
            "manual": manual,
            "size_bytes": path.stat().st_size if path.exists() else None,
        }

    def next_scheduled_at(self, settings: dict | None = None) -> int:
        """Wall-clock instant the next automatic backup is due, in ms.

        The interval picks the day and the configured time picks the moment within
        it, so a copy taken late in the evening does not drag every later one along
        with it. 0 means "no automatic backup has ever run", which is due at once.
        """
        settings = settings or self.get_settings()
        last_at = int(settings.get("last_auto_backup_at") or 0)
        if last_at <= 0:
            return 0
        due_date = (
            datetime.fromtimestamp(last_at / 1000)
            + timedelta(days=int(settings["interval_days"]))
        ).date()
        due = datetime.combine(
            due_date,
            clock_time(
                hour=int(settings["backup_hour"]),
                minute=int(settings["backup_minute"]),
            ),
        )
        return int(due.timestamp() * 1000)

    def ensure_scheduled_backup(self) -> dict | None:
        settings = self.get_settings()
        due_at = self.next_scheduled_at(settings)
        if due_at > 0 and self.now_ms() < due_at:
            return None
        try:
            return self.create_backup(manual=False)
        except ValueError:
            return None

    def list_backups(self, limit: int = DB_BACKUP_LIST_LIMIT) -> dict:
        """Every retained copy, newest first, with the generation the prune counts by."""
        entries: list[dict] = []
        total_size = 0
        for kind in ("auto", "manual"):
            directory = self.backup_dir / kind
            if not directory.exists():
                continue
            for path in directory.glob(f"inku-{kind}-*.db"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                entries.append(
                    {
                        "kind": kind,
                        "name": path.name,
                        "at": int(stat.st_mtime * 1000),
                        "size_bytes": stat.st_size,
                    }
                )
                total_size += stat.st_size
        entries.sort(key=lambda entry: entry["at"], reverse=True)
        # Generation 1 is the newest automatic copy, matching the order
        # prune_auto_backups walks: the highest number is the one dropped next.
        # Manual copies are never pruned, so they are outside the numbering.
        generation = 0
        for entry in entries:
            if entry["kind"] == "auto":
                generation += 1
                entry["generation"] = generation
            else:
                entry["generation"] = None
        return {
            "entries": entries[:limit],
            "total_count": len(entries),
            "total_size_bytes": total_size,
        }

    def status(self) -> dict:
        settings = self.get_settings()
        supported = self.dialect_name == "sqlite" and self.database_path() is not None
        auto_dir = self.backup_dir / "auto"
        manual_dir = self.backup_dir / "manual"
        auto_count = len(list(auto_dir.glob("inku-auto-*.db"))) if auto_dir.exists() else 0
        manual_count = (
            len(list(manual_dir.glob("inku-manual-*.db"))) if manual_dir.exists() else 0
        )
        listing = self.list_backups()
        return {
            **settings,
            "supported": supported,
            "backup_dir": str(self.backup_dir),
            "auto_count": auto_count,
            "manual_count": manual_count,
            "next_auto_backup_at": self.next_scheduled_at(settings),
            "backups": listing["entries"],
            "backups_total_count": listing["total_count"],
            "backups_total_size_bytes": listing["total_size_bytes"],
        }
