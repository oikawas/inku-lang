"""A restore writes only a verified copy of the same shape, and never without a safety copy."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from inku_server.persistence.backup import (
    BackupNotFoundError,
    BackupSchemaMismatchError,
    BackupService,
    SQLiteSnapshotError,
)


def _service(tmp_path: Path, clock: list[int]) -> BackupService:
    live = tmp_path / "live.db"
    with sqlite3.connect(live) as connection:
        connection.execute("CREATE TABLE works (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO works VALUES ('before')")
    settings: dict = {}
    return BackupService(
        backup_dir=tmp_path / "backups",
        dialect_name="sqlite",
        database_path=lambda: live,
        now_ms=lambda: clock[0],
        read_setting=settings.get,
        write_setting=lambda key, value: settings.__setitem__(key, value) or value,
    )


def _works(path: Path) -> list[str]:
    with sqlite3.connect(path) as connection:
        return [row[0] for row in connection.execute("SELECT id FROM works ORDER BY id")]


def test_restore_replaces_the_contents_after_saving_them(tmp_path):
    clock = [1_700_000_000_000]
    service = _service(tmp_path, clock)
    name = Path(service.create_backup(manual=True)["path"]).name
    with sqlite3.connect(service.database_path()) as connection:
        connection.execute("INSERT INTO works VALUES ('after')")
    clock[0] += 2000
    result = service.restore_backup("manual", name)
    assert _works(service.database_path()) == ["before"]
    assert _works(service.backup_dir / "manual" / result["safety_backup"]) == ["after", "before"]


def test_restore_refuses_another_shape_and_a_broken_copy_before_touching_anything(tmp_path):
    clock = [1_700_000_000_000]
    service = _service(tmp_path, clock)
    name = Path(service.create_backup(manual=True)["path"]).name
    with sqlite3.connect(service.backup_dir / "manual" / name) as connection:
        connection.execute("CREATE TABLE extra (id INTEGER)")
    with pytest.raises(BackupSchemaMismatchError):
        service.restore_backup("manual", name)
    (service.backup_dir / "manual" / name).write_bytes(b"not a database")
    with pytest.raises(SQLiteSnapshotError):
        service.restore_backup("manual", name)
    assert [p.name for p in (service.backup_dir / "manual").iterdir()] == [name]
    assert _works(service.database_path()) == ["before"]


@pytest.mark.parametrize(("kind", "name"), [
    ("manual", "../live.db"), ("manual", "inku-auto-20231114-221320.db"), ("other", "inku-other-20231114-221320.db"),
    ("manual", "inku-manual-20231114-221320.db"),
])
def test_only_a_listed_copy_can_be_named(tmp_path, kind, name):
    service = _service(tmp_path, [1_700_000_000_000])
    with pytest.raises(BackupNotFoundError):
        service.delete_backup(kind, name)
