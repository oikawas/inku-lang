"""Concrete storage failures at the manual single-DDL boundary, without drawing."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from inku_server.persistence import ddl_migration as migration
from inku_server.persistence import legacy_v3_migrations as frozen
from inku_server.persistence import legacy_v3_schema as legacy
from inku_server.persistence import migrations

SOURCE_SHA = "566716f25fa146b332d0efe9b83b8a0fbcaf7caf"


def _source(path: Path) -> None:
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        legacy.Base.metadata.create_all(connection)
        connection.exec_driver_sql(frozen._REGISTRY_DDL)
        frozen._record_baseline(connection)
        for work_id, ddl, expanded in (
            ("both", " \nCircle.\n", "Different."), ("legacy", None, "\n墨。\n"),
            ("blank", "\u00a0\u3000", "old text"), ("null", None, None), ("empty", "", "\n "),
        ):
            connection.execute(legacy.HistoryRow.__table__.insert().values(
                id=work_id, at=1, input="description\x00kept", ddl=ddl, expanded_ddl=expanded,
                score='{"saved": "unaltered"}', svg="<svg>saved</svg>", note="original note",
                render_seed="9223372036854775807", render_canvas_aspect_ratio=1.5,
            ))
        frozen.install_history_fts(connection, rebuild=True)
        connection.execute(legacy.PipelineHistoryLinkRow.__table__.insert().values(
            owner_id="owner", history_id="legacy", variation_id="variation", revision=1,
            ddl_digest=hashlib.sha256("\n墨。\n".encode()).hexdigest(),
            fork_context_bytes=b"\x00\xff", fork_context_digest="preserved",
        ))
    engine.dispose()


def _history(path: Path) -> list:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT id,ddl,ddl_source_origin FROM history ORDER BY id").fetchall()


def test_manual_unification_preserves_text_other_values_search_and_second_start(tmp_path):
    path = (tmp_path / "source.db").resolve()
    _source(path)
    report = migration.migrate_history_ddl(path, source_commit=SOURCE_SHA)
    assert report["status"] == "migrated" and all(report["verification"].values())
    assert report["classifications"] == {"ddl": 1, "legacy_expanded": 2, "absent": 2}
    assert _history(path) == [
        ("blank", "old text", "legacy_expanded"), ("both", " \nCircle.\n", None),
        ("empty", "", None), ("legacy", "\n墨。\n", "legacy_expanded"), ("null", None, None),
    ]
    with sqlite3.connect(path) as connection:
        assert "expanded_ddl" not in {row[1] for row in connection.execute("PRAGMA table_info(history)")}
        assert connection.execute("SELECT id FROM history WHERE rowid IN "
                                  "(SELECT rowid FROM history_fts WHERE history_fts MATCH 'old')").fetchall() == [("blank",)]
        assert connection.execute("SELECT fork_context_bytes FROM pipeline_history_links").fetchone() == (b"\x00\xff",)
    assert json.loads(Path(report["report"]).read_text())["status"] == "migrated"
    engine = create_engine(f"sqlite:///{path}")
    for _ in range(2):
        outcome = migrations.ensure_current_schema(
            engine=engine, database_path=path, create_schema=lambda _: pytest.fail("recreated schema"),
            seed_fresh=lambda _: pytest.fail("reseeded"), apply_legacy=lambda _: pytest.fail("inverse transform"),
        )
        assert outcome.mode == "current"
    engine.dispose()
    assert migration.migrate_history_ddl(path, source_commit=SOURCE_SHA)["status"] == "already_current"
    assert len(list((tmp_path / "migration-backups").glob("*.db"))) == 1


def test_failure_after_column_drop_rolls_back_text_schema_registry_and_keeps_backup(tmp_path, monkeypatch):
    path = (tmp_path / "source.db").resolve()
    _source(path)
    monkeypatch.setattr(migration, "_fts_contents_match", lambda _: (_ for _ in ()).throw(RuntimeError("injected")))
    with pytest.raises(migration.DdlMigrationError, match="rolled back") as failed:
        migration.migrate_history_ddl(path, source_commit=SOURCE_SHA)
    with sqlite3.connect(path) as connection:
        assert {"expanded_ddl"} <= {row[1] for row in connection.execute("PRAGMA table_info(history)")}
        assert connection.execute("SELECT ddl FROM history WHERE id='legacy'").fetchone() == (None,)
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [(3,)]
    assert failed.value.backup.is_file()
    assert json.loads(failed.value.backup.with_suffix(".report.json").read_text())["status"] == "rolled_back"


def test_snapshot_changed_before_writer_lock_is_refused_without_overwriting_new_data(tmp_path, monkeypatch):
    path = (tmp_path / "source.db").resolve()
    _source(path)
    real_snapshot = migration.create_sqlite_snapshot
    def snapshot_then_change(source, destination):
        snapshot = real_snapshot(source, destination)
        with sqlite3.connect(source) as connection:
            connection.execute("UPDATE history SET note='new writer' WHERE id='legacy'")
        return snapshot
    monkeypatch.setattr(migration, "create_sqlite_snapshot", snapshot_then_change)
    with pytest.raises(migration.DdlMigrationError, match="locked preimage"):
        migration.migrate_history_ddl(path, source_commit=SOURCE_SHA)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT note,ddl FROM history WHERE id='legacy'").fetchone() == ("new writer", None)
        assert "ddl_source_origin" not in {row[1] for row in connection.execute("PRAGMA table_info(history)")}


def test_old_database_and_mismatched_current_physical_schema_cannot_start(tmp_path):
    path = (tmp_path / "source.db").resolve()
    _source(path)
    engine = create_engine(f"sqlite:///{path}")
    options = dict(engine=engine, database_path=path, create_schema=lambda _: pytest.fail("old startup write"),
                   seed_fresh=lambda _: None, apply_legacy=lambda _: pytest.fail("legacy startup write"))
    with pytest.raises(migrations.MigrationStateError, match="manual history DDL"):
        migrations.ensure_current_schema(**options)
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO schema_migrations VALUES(?,?,?,1)",
                                   (migrations.MIGRATION_VERSION, migrations.MIGRATION_NAME, migrations.MIGRATION_CHECKSUM))
    with pytest.raises(migrations.MigrationStateError, match="physical schema"):
        migrations.ensure_current_schema(**options)
    engine.dispose()


def test_registered_v2_restore_uses_frozen_v3_copy_and_preserves_original(tmp_path):
    from inku_server.persistence.legacy_restore import restore_copy
    source, destination = (tmp_path / "old.db").resolve(), (tmp_path / "copy.db").resolve()
    _source(source)
    with sqlite3.connect(source) as connection:
        connection.execute("DROP TABLE provider_observations")
        connection.execute("UPDATE schema_migrations SET version=?,name=?,checksum=?",
                           (frozen._PREVIOUS_MIGRATION_VERSION, frozen._PREVIOUS_MIGRATION_NAME,
                            frozen._PREVIOUS_MIGRATION_CHECKSUM))
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = restore_copy(source, destination)
    assert result["version"] == 3 and result["source_preserved"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert migration.migrate_history_ddl(destination, source_commit=SOURCE_SHA,
                                         _restored_fingerprint=result["fingerprint"])["status"] == "migrated"


def test_unknown_v3_shape_is_refused_even_when_the_registry_matches(tmp_path):
    path = (tmp_path / "unknown.db").resolve()
    _source(path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE extra_archive(id INTEGER PRIMARY KEY, payload BLOB)")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(migration.DdlMigrationError, match="unrecognized v3 physical schema"):
        migration.migrate_history_ddl(path, source_commit=SOURCE_SHA)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not (tmp_path / "migration-backups").exists()


def test_saved_link_digest_mismatch_refuses_before_backup_or_any_write(tmp_path):
    path = (tmp_path / "linked.db").resolve()
    _source(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE pipeline_history_links SET ddl_digest='mismatch'")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(migration.DdlMigrationError, match="saved digest"):
        migration.migrate_history_ddl(path, source_commit=SOURCE_SHA)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not (tmp_path / "migration-backups").exists()


def test_reviewed_pre_registry_backup_is_restored_only_in_an_explicit_copy(tmp_path, monkeypatch):
    import importlib.util

    from inku_server.persistence.legacy_restore import restore_copy
    fixture_path = Path(__file__).with_name("test_lineage_migration.py")
    spec = importlib.util.spec_from_file_location("v175_frozen_fixture", fixture_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, destination = (tmp_path / "v175.db").resolve(), (tmp_path / "copy.db").resolve()
    module._create_v175_database(source)
    monkeypatch.setenv("INKU_BOOTSTRAP_ADMIN_PASSWORD", "test-restoration-password")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = restore_copy(source, destination)
    assert result["mode"] == "legacy" and result["source_preserved"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    report = migration.migrate_history_ddl(destination, source_commit=SOURCE_SHA,
                                           _restored_fingerprint=result["fingerprint"], _restoration=result)
    assert report["classifications"] == {"ddl": 0, "legacy_expanded": 1, "absent": 0}
    assert _history(destination) == [("history-1", "円を置く。", "legacy_expanded")]
    assert json.loads(Path(report["report"]).read_text())["restoration"] == result
