"""Focused acceptance for the versioned SQLite startup boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import inku_server.persistence.migrations as migrations
from inku_server.persistence import backup
from inku_server.persistence.backup import SQLiteSnapshotError, create_sqlite_snapshot
from inku_server.persistence.migrations import (
    ACCEPTED_LEGACY_STATES,
    MIGRATION_CHECKSUM,
    MIGRATION_NAME,
    MIGRATION_VERSION,
    MigrationExecutionError,
    MigrationStateError,
    ensure_current_schema,
    history_fts_state,
    schema_fingerprint,
)


_HISTORY_DDL = """
CREATE TABLE history (
    id TEXT PRIMARY KEY,
    input TEXT NOT NULL DEFAULT '',
    ddl TEXT,
    score TEXT NOT NULL DEFAULT '{}',
    svg TEXT NOT NULL DEFAULT '',
    stage1_model TEXT,
    stage2_model TEXT,
    catalog_id TEXT
)
"""
_REHEARSAL_SCRIPT = Path(__file__).parents[1] / "scripts" / "rehearse_persistence_migration.py"
_V175_FINGERPRINT = "01f03f2602e5a98c8fa2129195e0243db1375054cfeedd28265260a0d6d27737"


def _create_v175_database(path: Path) -> None:
    fixture_path = Path(__file__).with_name("test_lineage_migration.py")
    spec = importlib.util.spec_from_file_location("i372_lineage_fixture", fixture_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the existing v175 fixture")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._create_v175_database(path)


def _engine(path: Path):
    return create_engine(f"sqlite:///{path}", future=True)


def _create_history_schema(connection) -> None:
    connection.exec_driver_sql(_HISTORY_DDL)


def _no_op(_connection) -> None:
    return None


def _registry_row(engine) -> tuple[int, str, str]:
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT version, name, checksum FROM schema_migrations"
        ).one()
    return int(row[0]), str(row[1]), str(row[2])


def test_fresh_database_records_baseline_and_second_start_skips_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "fresh.db"
    engine = _engine(path)
    calls = {"create": 0, "seed": 0, "legacy": 0}

    def create_schema(connection) -> None:
        calls["create"] += 1
        _create_history_schema(connection)

    def seed(connection) -> None:
        calls["seed"] += 1
        connection.execute(
            text("INSERT INTO history(id, input, score, svg) VALUES ('fresh', '', '{}', '')")
        )

    def legacy(_connection) -> None:
        calls["legacy"] += 1

    first = ensure_current_schema(
        engine=engine,
        database_path=path,
        create_schema=create_schema,
        seed_fresh=seed,
        apply_legacy=legacy,
    )
    monkeypatch.setattr(
        migrations,
        "require_integrity",
        lambda _connection: pytest.fail("current startup replayed the full integrity scan"),
    )
    second = ensure_current_schema(
        engine=engine,
        database_path=path,
        create_schema=create_schema,
        seed_fresh=seed,
        apply_legacy=legacy,
    )

    assert first.mode == "fresh"
    assert second.mode == "current"
    assert calls == {"create": 1, "seed": 1, "legacy": 0}
    assert _registry_row(engine) == (
        MIGRATION_VERSION,
        MIGRATION_NAME,
        MIGRATION_CHECKSUM,
    )
    engine.dispose()


def test_registry_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "checksum.db"
    engine = _engine(path)
    ensure_current_schema(
        engine=engine,
        database_path=path,
        create_schema=_create_history_schema,
        seed_fresh=_no_op,
        apply_legacy=_no_op,
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE schema_migrations SET checksum='wrong'")

    with pytest.raises(MigrationStateError, match="reviewed baseline"):
        ensure_current_schema(
            engine=engine,
            database_path=path,
            create_schema=_create_history_schema,
            seed_fresh=_no_op,
            apply_legacy=_no_op,
        )
    engine.dispose()


def test_unknown_legacy_schema_fails_before_snapshot_or_mutation(tmp_path: Path) -> None:
    path = tmp_path / "unknown.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE mystery (id TEXT PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO mystery VALUES ('kept', 'unchanged')")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    engine = _engine(path)

    with pytest.raises(MigrationStateError, match="unrecognized pre-registry"):
        ensure_current_schema(
            engine=engine,
            database_path=path,
            create_schema=_no_op,
            seed_fresh=_no_op,
            apply_legacy=_no_op,
        )

    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not (tmp_path / "migration-backups").exists()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value FROM mystery").fetchone() == ("unchanged",)
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='schema_migrations'"
        ).fetchone() == (0,)
    engine.dispose()


def test_legacy_failure_rolls_back_source_and_retains_verified_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(_HISTORY_DDL)
        connection.execute(
            "INSERT INTO history(id, input, score, svg) VALUES (?, ?, ?, ?)",
            ("work-1", "original", '{"instructions":[]}', "<svg/>")
        )
    engine = _engine(path)
    with engine.connect() as connection:
        fingerprint = schema_fingerprint(connection)
    monkeypatch.setitem(ACCEPTED_LEGACY_STATES, (fingerprint, "absent"), "test-legacy")

    def fail_after_write(connection) -> None:
        connection.exec_driver_sql("UPDATE history SET input='mutated'")
        raise RuntimeError("injected migration failure")

    with pytest.raises(MigrationExecutionError) as failure:
        ensure_current_schema(
            engine=engine,
            database_path=path,
            create_schema=_no_op,
            seed_fresh=_no_op,
            apply_legacy=fail_after_write,
        )

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT input FROM history").fetchone() == ("original",)
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='schema_migrations'"
        ).fetchone() == (0,)
    snapshots = list((tmp_path / "migration-backups").glob("*.db"))
    assert len(snapshots) == 1
    assert failure.value.snapshot.path == snapshots[0]
    backup.verify_sqlite_snapshot(snapshots[0])
    engine.dispose()


def test_legacy_success_preserves_canonical_bytes_and_becomes_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "legacy-success.db"
    payload = ("work-1", "ink\x00text", '{"instructions":[{"n":1}]}', "<svg>墨</svg>")
    with sqlite3.connect(path) as connection:
        connection.executescript(_HISTORY_DDL)
        connection.execute(
            "INSERT INTO history(id, input, score, svg) VALUES (?, ?, ?, ?)",
            payload,
        )
    engine = _engine(path)
    with engine.connect() as connection:
        fingerprint = schema_fingerprint(connection)
    monkeypatch.setitem(ACCEPTED_LEGACY_STATES, (fingerprint, "absent"), "test-legacy")

    first = ensure_current_schema(
        engine=engine,
        database_path=path,
        create_schema=_no_op,
        seed_fresh=_no_op,
        apply_legacy=_no_op,
    )
    second = ensure_current_schema(
        engine=engine,
        database_path=path,
        create_schema=_no_op,
        seed_fresh=_no_op,
        apply_legacy=lambda _connection: pytest.fail("legacy migration replayed"),
    )

    assert first.mode == "legacy"
    assert first.fingerprint_name == "test-legacy"
    assert first.snapshot is not None
    assert second.mode == "current"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT id, input, score, svg FROM history").fetchone() == payload
    engine.dispose()


def test_partial_fts_state_fails_without_guessing_a_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "partial-fts.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(_HISTORY_DDL)
        connection.executescript(
            """
            CREATE TABLE history_fts (value TEXT);
            CREATE TABLE history_fts_config (value TEXT);
            CREATE TABLE history_fts_data (value TEXT);
            CREATE TABLE history_fts_docsize (value TEXT);
            CREATE TABLE history_fts_idx (value TEXT);
            CREATE TRIGGER history_fts_ai AFTER INSERT ON history BEGIN SELECT 1; END;
            CREATE TRIGGER history_fts_ad AFTER DELETE ON history BEGIN SELECT 1; END;
            CREATE TRIGGER history_fts_au AFTER UPDATE ON history BEGIN SELECT 1; END;
            """
        )
    engine = _engine(path)
    with engine.connect() as connection:
        fingerprint = schema_fingerprint(connection)
        assert history_fts_state(connection) == "partial"
    monkeypatch.setitem(ACCEPTED_LEGACY_STATES, (fingerprint, "partial"), "must-not-run")

    with pytest.raises(MigrationStateError, match="internally inconsistent"):
        ensure_current_schema(
            engine=engine,
            database_path=path,
            create_schema=_no_op,
            seed_fresh=_no_op,
            apply_legacy=lambda _connection: pytest.fail("partial FTS was repaired"),
        )
    assert not (tmp_path / "migration-backups").exists()
    engine.dispose()


def test_snapshot_failure_has_no_plain_file_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "snapshot.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE kept (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO kept(value) VALUES ('canonical')")
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    real_connect = backup.sqlite3.connect

    def fail_destination(database, *args, **kwargs):
        if Path(database) == destination:
            raise sqlite3.OperationalError("injected destination failure")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(backup.sqlite3, "connect", fail_destination)
    with pytest.raises(SQLiteSnapshotError, match="Backup API failed"):
        create_sqlite_snapshot(source, destination)

    assert not destination.exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_digest


def test_rehearsal_cli_requires_marker_guarded_containment(tmp_path: Path) -> None:
    database = tmp_path / "candidate.db"
    _create_v175_database(database)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    completed = subprocess.run(
        [
            sys.executable,
            str(_REHEARSAL_SCRIPT),
            "--run-root",
            str(tmp_path),
            "--database",
            database.name,
            "--expect-fingerprint",
            _V175_FINGERPRINT,
            "--expect-fts-state",
            "absent",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {"error": "RuntimeError", "ok": False}
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='schema_migrations'"
        ).fetchone() == (0,)


def test_rehearsal_cli_migrates_only_the_marked_copy(tmp_path: Path) -> None:
    database = tmp_path / "candidate.db"
    _create_v175_database(database)
    (tmp_path / ".inku-persistence-rehearsal").write_text(
        "I-372 isolated copy\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    completed = subprocess.run(
        [
            sys.executable,
            str(_REHEARSAL_SCRIPT),
            "--run-root",
            str(tmp_path),
            "--database",
            database.name,
            "--expect-fingerprint",
            _V175_FINGERPRINT,
            "--expect-fts-state",
            "absent",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["history_rows"] == 1
    assert result["migration_version"] == MIGRATION_VERSION
    assert result["migration_checksum"] == MIGRATION_CHECKSUM
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone() == (1,)
