"""Coordinate one stopped-service Saijiki v3 database and package cutover.

The operator owns service stopping and the durable one-attempt guard. Recovery
uses the committed database marker to distinguish rollback from completion.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from .backup import create_sqlite_snapshot
from .invariants import capture_invariants, require_integrity, verify_invariants
from .saijiki_v3_migration import (
    DONE_SETTING, MigrationAlreadyWritten, _already_written, _canonical, _execute,
    migrate_saved_records, migrate_unit_v3,
)
from .saijiki_v3_plugins import plan_packages


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic(path: Path, value: bytes, mode: int) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".saijiki-v3-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _package_path(root: Path, relative: str) -> Path:
    name = Path(relative)
    if name.is_absolute() or len(name.parts) != 2 or name.name != "package.json" or ".." in name.parts:
        raise ValueError("invalid_package_path")
    parent = root / name.parent
    if parent.is_symlink() or parent.resolve(strict=True).parent != root:
        raise ValueError("invalid_package_directory")
    path = parent / name.name
    if path.is_symlink() or not path.is_file():
        raise ValueError("invalid_package_file")
    return path


def recover(database: Path, packages: Path, recovery: Path) -> str:
    """After interruption, either finish an already committed cutover or restore old packages."""
    if database.is_symlink() or packages.is_symlink() or recovery.is_symlink():
        raise ValueError("recovery_symlink")
    database = database.resolve(strict=True)
    root = packages.resolve(strict=True)
    recovery = recovery.resolve(strict=True)
    manifest_file = recovery / "manifest.json"
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise ValueError("invalid_recovery_manifest")
    manifest = json.loads(manifest_file.read_text())
    if manifest["database"] != str(database) or manifest["packages"] != str(root):
        raise ValueError("recovery_identity_mismatch")
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        committed = connection.execute("SELECT 1 FROM app_settings WHERE key=?", (DONE_SETTING,)).fetchone() is not None
    for entry in manifest["files"]:
        path = _package_path(root, entry["path"])
        current = _hash(path.read_bytes())
        if committed:
            if current != entry["after"]:
                raise RuntimeError("committed_package_mismatch_manual_recovery_required")
        elif current != entry["before"]:
            if current != entry["after"]:
                raise RuntimeError("package_changed_manual_recovery_required")
            backup_name = Path(entry["backup"])
            if len(backup_name.parts) != 1 or backup_name.name != str(backup_name):
                raise ValueError("invalid_backup_name")
            backup = recovery / backup_name
            if backup.is_symlink() or _hash(backup.read_bytes()) != entry["before"]:
                raise RuntimeError("invalid_package_backup")
            _atomic(path, backup.read_bytes(), entry["mode"])
    return "committed" if committed else "rolled_back"


def cutover(database: Path, packages: Path, recovery: Path, *, journal: Path,
            workers: int = 4, timeout: float = 120.0, allow_refused: bool = False) -> dict[str, Any]:
    """Migrate once; caller must stop every writer and guard this attempt externally."""
    database = database.resolve(strict=True)
    if packages.is_symlink():
        raise ValueError("invalid_package_root")
    packages = packages.resolve(strict=True)
    recovery.mkdir(mode=0o700)  # exclusive: an uncertain attempt must not be retried
    package_report, proposed = plan_packages(packages)
    if package_report["refused_records"]:
        raise ValueError("package_migration_refused")
    entries = []
    for index, (path, new) in enumerate(sorted(proposed.items())):
        relative = str(path.relative_to(packages))
        if _package_path(packages, relative) != path:
            raise ValueError("invalid_package_path")
        old = path.read_bytes()
        backup = f"package-{index}.json"
        descriptor = os.open(recovery / backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(old)
            output.flush()
            os.fsync(output.fileno())
        entries.append({"path": relative, "backup": backup, "before": _hash(old), "after": _hash(new),
                        "mode": path.stat().st_mode & 0o777})
    manifest = {"database": str(database), "packages": str(packages), "files": entries}
    _atomic(recovery / "manifest.json", _canonical(manifest).encode(), 0o600)
    snapshot = create_sqlite_snapshot(database, recovery / "database-before.db")
    engine = create_engine(f"sqlite:///{database}", future=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                if _already_written(connection):
                    raise MigrationAlreadyWritten(str(database))
                before = capture_invariants(connection)
                report = migrate_saved_records(connection, migrate_unit_v3, workers=workers,
                                               checked=lambda: verify_invariants(connection, before),
                                               journal=journal, timeout=timeout, abort_on_failure=not allow_refused)
                if report["refused_records"] and not allow_refused:
                    raise ValueError("saved_record_migration_refused")
                summary = {"refused_records": len(report["refused_records"]), "statements": report["statements"]}
                _execute(connection, "INSERT INTO app_settings(key, value, at) VALUES (?, ?, ?)",
                         (DONE_SETTING, _canonical(summary), int(time.time() * 1000)))
                require_integrity(connection)
                for entry, (path, new) in zip(entries, sorted(proposed.items()), strict=True):
                    if _hash(path.read_bytes()) != entry["before"]:
                        raise RuntimeError("package_changed_during_cutover")
                    _atomic(path, new, entry["mode"])
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    except BaseException:
        recover(database, packages, recovery)
        raise
    finally:
        engine.dispose()
    if recover(database, packages, recovery) != "committed":
        raise RuntimeError("commit_not_recorded")
    report.update(snapshot=str(snapshot.path), packages=package_report, recovery=str(recovery))
    return report
