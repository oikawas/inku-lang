"""Direct policy tests for the persistence-owned backup service."""

from __future__ import annotations

import inspect
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import backup


class _SettingStore:
    def __init__(self, value: dict | None = None) -> None:
        self.value = None if value is None else dict(value)
        self.writes: list[tuple[str, dict]] = []

    def read(self, key: str) -> dict | None:
        assert key == "db_backup_settings"
        return None if self.value is None else dict(self.value)

    def write(self, key: str, value: dict) -> dict:
        assert key == "db_backup_settings"
        self.value = dict(value)
        self.writes.append((key, dict(value)))
        return value


def _sqlite_database(path: Path, marker: str = "source") -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE evidence (marker TEXT NOT NULL)")
        connection.execute("INSERT INTO evidence VALUES (?)", (marker,))
    return path


def _service(
    tmp_path: Path,
    *,
    store: _SettingStore | None = None,
    source: Path | None = None,
    now_ms: int = 1_800_000_000_000,
    dialect_name: str = "sqlite",
):
    service_type = getattr(backup, "BackupService", None)
    assert service_type is not None, "persistence.backup must own BackupService"
    store = store or _SettingStore()
    return service_type(
        backup_dir=tmp_path / "backups",
        dialect_name=dialect_name,
        database_path=lambda: source,
        now_ms=lambda: now_ms,
        read_setting=store.read,
        write_setting=store.write,
    )


def _defaults(**overrides: int) -> dict:
    value = {
        "interval_days": 7,
        "max_generations": 4,
        "backup_hour": 3,
        "backup_minute": 0,
        "last_auto_backup_at": 0,
    }
    value.update(overrides)
    return value


def test_persistence_backup_owns_policy_without_importing_db(tmp_path: Path) -> None:
    source = inspect.getsource(backup)
    assert "inku_server.db" not in source
    assert "from .. import db" not in source
    service = _service(tmp_path)

    assert backup.DB_BACKUP_SETTINGS_KEY == "db_backup_settings"
    assert backup.DB_BACKUP_LIST_LIMIT == 50
    assert backup.DB_BACKUP_DEFAULT_SETTINGS == _defaults()
    assert service.normalize_settings(None) == _defaults()
    assert service.normalize_settings({"last_auto_backup_at": "bad"}) == _defaults()
    assert service.normalize_settings({"interval_days": "8", "max_generations": "5"}) == _defaults(
        interval_days=8,
        max_generations=5,
    )
    with pytest.raises(ValueError, match="interval days"):
        service.normalize_settings({"interval_days": 0})
    with pytest.raises(ValueError, match="max generations"):
        service.normalize_settings({"max_generations": 101})
    with pytest.raises(ValueError, match="backup_hour"):
        service.normalize_settings({"backup_hour": 24})


def test_db_facade_observes_runtime_monkeypatch_seams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_one = _sqlite_database(tmp_path / "one.sqlite", "one")
    source_two = _sqlite_database(tmp_path / "two.sqlite", "two")
    first_store = _SettingStore(_defaults(interval_days=2))
    second_store = _SettingStore(_defaults(interval_days=9))

    monkeypatch.setattr(db, "_DB_BACKUP_DIR", tmp_path / "first")
    monkeypatch.setattr(db, "_sqlite_db_path", lambda: source_one)
    monkeypatch.setattr(db, "_now_ms", lambda: int(datetime(2030, 1, 2, 3, 4, 5).timestamp() * 1000))
    monkeypatch.setattr(db, "_read_app_setting", first_store.read)
    monkeypatch.setattr(db, "_write_app_setting", first_store.write)
    first = db.create_db_backup(manual=True)

    assert Path(first["path"]).parent == tmp_path / "first" / "manual"
    assert Path(first["path"]).name == "inku-manual-20300102-030405.db"
    assert db.get_db_backup_settings()["interval_days"] == 2

    monkeypatch.setattr(db, "_DB_BACKUP_DIR", tmp_path / "second")
    monkeypatch.setattr(db, "_sqlite_db_path", lambda: source_two)
    monkeypatch.setattr(db, "_now_ms", lambda: int(datetime(2031, 2, 3, 4, 5, 6).timestamp() * 1000))
    monkeypatch.setattr(db, "_read_app_setting", second_store.read)
    monkeypatch.setattr(db, "_write_app_setting", second_store.write)
    second = db.create_db_backup(manual=True)

    second_path = Path(second["path"])
    assert second_path.parent == tmp_path / "second" / "manual"
    assert second_path.name == "inku-manual-20310203-040506.db"
    with sqlite3.connect(second_path) as connection:
        assert connection.execute("SELECT marker FROM evidence").fetchone() == ("two",)
    assert db.get_db_backup_settings()["interval_days"] == 9
    db.update_db_backup_settings(6, 3, 11, 12)
    assert second_store.writes[-1][1] == _defaults(
        interval_days=6,
        max_generations=3,
        backup_hour=11,
        backup_minute=12,
    )

    monkeypatch.setattr(db, "engine", SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    with pytest.raises(ValueError, match="only for SQLite"):
        db.create_db_backup(manual=True)


def test_automatic_backup_updates_timestamp_and_prunes_only_old_automatic_files(
    tmp_path: Path,
) -> None:
    source = _sqlite_database(tmp_path / "source.sqlite")
    store = _SettingStore(_defaults(max_generations=2, last_auto_backup_at=123))
    service = _service(tmp_path, store=store, source=source)
    auto_dir = tmp_path / "backups" / "auto"
    manual_dir = tmp_path / "backups" / "manual"
    auto_dir.mkdir(parents=True)
    manual_dir.mkdir(parents=True)
    oldest = auto_dir / "inku-auto-20200101-030000.db"
    newest = auto_dir / "inku-auto-20200102-030000.db"
    manual = manual_dir / "inku-manual-20200101-120000.db"
    for path, mtime in ((oldest, 1_000), (newest, 2_000), (manual, 500)):
        path.write_bytes(path.name.encode())
        os.utime(path, (mtime, mtime))

    result = service.create_backup()

    assert result["manual"] is False
    backup.verify_sqlite_snapshot(Path(result["path"]))
    assert store.value == _defaults(max_generations=2, last_auto_backup_at=1_800_000_000_000)
    assert {path.name for path in auto_dir.glob("inku-auto-*.db")} == {
        newest.name,
        Path(result["path"]).name,
    }
    assert manual.read_bytes() == manual.name.encode()


def test_manual_backup_neither_updates_settings_nor_prunes_files(tmp_path: Path) -> None:
    source = _sqlite_database(tmp_path / "source.sqlite")
    original = _defaults(max_generations=1, last_auto_backup_at=123)
    store = _SettingStore(original)
    service = _service(tmp_path, store=store, source=source)
    auto_dir = tmp_path / "backups" / "auto"
    manual_dir = tmp_path / "backups" / "manual"
    auto_dir.mkdir(parents=True)
    manual_dir.mkdir(parents=True)
    for index in range(3):
        (auto_dir / f"inku-auto-2020010{index + 1}-030000.db").write_bytes(b"auto")
    retained_manual = manual_dir / "inku-manual-20200101-120000.db"
    retained_manual.write_bytes(b"manual")

    result = service.create_backup(manual=True)

    assert result["manual"] is True
    backup.verify_sqlite_snapshot(Path(result["path"]))
    assert store.value == original
    assert store.writes == []
    assert len(list(auto_dir.glob("inku-auto-*.db"))) == 3
    assert retained_manual.read_bytes() == b"manual"


def test_schedule_waits_before_due_and_creates_one_verified_backup_when_due(tmp_path: Path) -> None:
    source = _sqlite_database(tmp_path / "source.sqlite")
    last = datetime(2030, 1, 2, 9, 30)
    due = datetime(2030, 1, 3, 22, 45)
    store = _SettingStore(
        _defaults(
            interval_days=1,
            backup_hour=22,
            backup_minute=45,
            last_auto_backup_at=int(last.timestamp() * 1000),
        )
    )
    clock = [int(datetime(2030, 1, 3, 22, 44).timestamp() * 1000)]
    service_type = getattr(backup, "BackupService", None)
    assert service_type is not None, "persistence.backup must own BackupService"
    service = service_type(
        backup_dir=tmp_path / "backups",
        dialect_name="sqlite",
        database_path=lambda: source,
        now_ms=lambda: clock[0],
        read_setting=store.read,
        write_setting=store.write,
    )

    assert service.next_scheduled_at() == int(due.timestamp() * 1000)
    assert service.ensure_scheduled_backup() is None
    assert not (tmp_path / "backups" / "auto").exists()

    clock[0] = int(datetime(2030, 1, 3, 22, 46).timestamp() * 1000)
    result = service.ensure_scheduled_backup()

    assert result is not None
    created = list((tmp_path / "backups" / "auto").glob("inku-auto-*.db"))
    assert created == [Path(result["path"])]
    backup.verify_sqlite_snapshot(created[0])


def test_listing_and_status_keep_order_generations_aggregates_limit_and_keys(tmp_path: Path) -> None:
    store = _SettingStore(_defaults())
    source = tmp_path / "available.sqlite"
    service = _service(tmp_path, store=store, source=source)
    auto_dir = tmp_path / "backups" / "auto"
    manual_dir = tmp_path / "backups" / "manual"
    auto_dir.mkdir(parents=True)
    manual_dir.mkdir(parents=True)
    total_size = 0
    for index in range(52):
        kind = "auto" if index % 2 == 0 else "manual"
        directory = auto_dir if kind == "auto" else manual_dir
        path = directory / f"inku-{kind}-20300101-{index:06d}.db"
        payload = bytes([index]) * (index + 1)
        path.write_bytes(payload)
        os.utime(path, (1_000 + index, 1_000 + index))
        total_size += len(payload)

    listing = service.list_backups(limit=3)
    assert set(listing) == {"entries", "total_count", "total_size_bytes"}
    assert len(listing["entries"]) == 3
    assert listing["total_count"] == 52
    assert listing["total_size_bytes"] == total_size
    assert [entry["kind"] for entry in listing["entries"]] == ["manual", "auto", "manual"]
    assert [entry["generation"] for entry in listing["entries"]] == [None, 1, None]

    status = service.status()
    assert set(status) == {
        "interval_days",
        "max_generations",
        "backup_hour",
        "backup_minute",
        "last_auto_backup_at",
        "supported",
        "backup_dir",
        "auto_count",
        "manual_count",
        "next_auto_backup_at",
        "backups",
        "backups_total_count",
        "backups_total_size_bytes",
    }
    assert status["supported"] is True
    assert status["backup_dir"] == str(tmp_path / "backups")
    assert status["auto_count"] == 26
    assert status["manual_count"] == 26
    assert status["next_auto_backup_at"] == 0
    assert len(status["backups"]) == 50
    assert status["backups_total_count"] == 52
    assert status["backups_total_size_bytes"] == total_size


def test_copy_failure_changes_neither_settings_nor_retained_files(tmp_path: Path) -> None:
    missing_source = tmp_path / "missing.sqlite"
    original = _defaults(max_generations=1, last_auto_backup_at=123)
    store = _SettingStore(original)
    service = _service(tmp_path, store=store, source=missing_source)
    auto_dir = tmp_path / "backups" / "auto"
    manual_dir = tmp_path / "backups" / "manual"
    auto_dir.mkdir(parents=True)
    manual_dir.mkdir(parents=True)
    retained = {
        auto_dir / "inku-auto-20200101-030000.db": b"old-auto",
        auto_dir / "inku-auto-20200102-030000.db": b"new-auto",
        manual_dir / "inku-manual-20200101-120000.db": b"manual",
    }
    for path, content in retained.items():
        path.write_bytes(content)

    with pytest.raises(ValueError, match="not available"):
        service.create_backup()

    assert store.value == original
    assert store.writes == []
    assert {path: path.read_bytes() for path in retained} == retained
    assert {path for path in (tmp_path / "backups").rglob("*.db")} == set(retained)
