"""Image input provenance survives saving without becoming drawable text."""

from __future__ import annotations

import json
import sqlite3
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.api_core import rendering
from inku_server.api_core.models import HistoryItem
from inku_server.persistence import migrations
from inku_server.persistence.schema import Base, HistoryRow
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.persistence.ddl_migration import migrate_history_ddl


IMAGE_RECORD = {
    "image": {"sent": {"media_type": "image/jpeg", "width": 80, "height": 60,
                       "sha256": "a" * 64, "byte_len": 512},
              "original_width": 800, "original_height": 600},
    "declared_ratio": {"width_units": 4, "height_units": 3},
    "nearest_format_id": "a4_landscape",
    "rounds": [{"stage": "write_image_ddl", "prompt_id": "inku.image-ddl-prompt.v1",
                "prompt_digest": "b" * 64, "problems": 0, "instructions": 1}],
    "before_review": "墨で円を描く。",
    "drawing": {"media_type": "image/png", "width": 1024, "height": 768,
                "sha256": "c" * 64, "byte_len": 1024},
}


def _v4_database(path):
    # Reuse the characterized historical fixture and its existing manual move.
    spec = importlib.util.spec_from_file_location(
        "image_history_ddl_fixture", Path(__file__).with_name("test_history_ddl_migration.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._source(path)
    migrate_history_ddl(path, source_commit=module.SOURCE_SHA)
    return create_engine(f"sqlite:///{path}")


def _start(engine, path):
    return migrations.ensure_current_schema(
        engine=engine, database_path=path,
        create_schema=lambda _: pytest.fail("existing database recreated"),
        seed_fresh=lambda _: pytest.fail("existing database reseeded"),
        apply_legacy=lambda _: pytest.fail("legacy migration replayed"),
    )


def test_v4_adds_nullable_image_fields_once_and_preserves_saved_values(tmp_path):
    path = (tmp_path / "image-history.db").resolve()
    engine = _v4_database(path)
    with engine.connect() as connection:
        before = list(connection.exec_driver_sql("SELECT rowid,* FROM history ORDER BY id"))
    try:
        first = _start(engine, path)
        assert first.mode == "registered_upgrade" and first.snapshot.path.is_file()
        assert _start(engine, path).mode == "current"
        with engine.connect() as connection:
            columns = {row[1]: row for row in connection.exec_driver_sql("PRAGMA table_info(history)")}
            for name in migrations.IMAGE_HISTORY_COLUMNS:
                assert columns[name][2:5] == ("TEXT", 0, None)
            after = list(connection.exec_driver_sql("SELECT rowid,* FROM history ORDER BY id"))
            assert [tuple(row[:-2]) for row in after] == [tuple(row) for row in before]
            assert all(tuple(row[-2:]) == (None, None) for row in after)
            assert connection.exec_driver_sql("SELECT version FROM schema_migrations ORDER BY version").all() == [
                (3,), (4,), (5,),
            ]
        with sqlite3.connect(first.snapshot.path) as snapshot:
            assert "image_ddl" not in {row[1] for row in snapshot.execute("PRAGMA table_info(history)")}
    finally:
        engine.dispose()


def test_failed_image_upgrade_rolls_back_both_columns_and_registry(tmp_path, monkeypatch):
    path = (tmp_path / "image-history.db").resolve()
    engine = _v4_database(path)
    monkeypatch.setattr(migrations, "require_integrity", lambda _: (_ for _ in ()).throw(RuntimeError("injected")))
    try:
        with pytest.raises(migrations.MigrationExecutionError) as failed:
            _start(engine, path)
        assert failed.value.snapshot.path.is_file()
        with engine.connect() as connection:
            assert not set(migrations.IMAGE_HISTORY_COLUMNS) & {
                row[1] for row in connection.exec_driver_sql("PRAGMA table_info(history)")
            }
            assert connection.exec_driver_sql("SELECT version FROM schema_migrations ORDER BY version").all() == [(3,), (4,)]
    finally:
        engine.dispose()


def test_image_record_survives_history_save_listing_replay_and_ddl_derivation(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'roundtrip.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    actor = {"id": "owner", "permission_groups": ["users"]}
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    monkeypatch.setattr(db, "_actor_of", lambda _: actor)
    monkeypatch.setattr(db, "render_hash_for_item", lambda _: "rh3:" + "d" * 64)
    monkeypatch.setattr(db, "description_hash", lambda text: "description:" + text)
    monkeypatch.setattr(rendering, "_submit_thumbnail_build", lambda _: None)
    try:
        saved = rendering._add_history_item(
            actor=actor, input_text="", source_text="", ddl="墨で円を描く。", score={},
            svg="<svg/>", at=1, image_provenance="作者が写した海岸。", image_ddl=IMAGE_RECORD,
            render_metadata={"render_hash": "rh3:" + "d" * 64}, save_artifacts=False,
            idempotency_key="image-save",
        )
        detail = db.get_items("owner", [saved["id"]])[0]
        listing = db.list_items("owner", include_svg=False)[0][0]
        replay = db.add_item({"id": "ignored", "user_id": "owner", "at": 2,
                              "idempotency_key": "image-save"})
        derived = db.add_item({"id": "edited", "user_id": "owner", "at": 3,
                               "input": "", "source_text": "", "ddl": "墨で線を描く。",
                               "lineage_parent_node_id": saved["lineage_node_id"], "derivation_kind": "ddl_edit"})
        for item in (saved, detail, listing, replay, derived):
            assert item["input"] == item["source_text"] == ""
            assert item["image_provenance"] == "作者が写した海岸。"
            assert item["image_ddl"] == IMAGE_RECORD
            assert HistoryItem.model_validate(item).image_ddl == IMAGE_RECORD
        assert detail["description_locked"] is True
        assert listing["description_locked"] is True
        assert replay["_idempotent_replay"] is True
        legacy = VariationAuthorityStore(engine).read_legacy_history("owner", saved["id"])
        assert legacy.description == ""
        assert legacy.metadata["image_ddl"] == IMAGE_RECORD
        assert legacy.metadata["image_provenance"] == "作者が写した海岸。"
        reread = db.add_item({"id": "reread", "user_id": "owner", "at": 4,
                             "input": "新しい記述。", "lineage_parent_node_id": saved["lineage_node_id"],
                             "derivation_kind": "description_edit"})
        assert reread["image_provenance"] is None and reread["image_ddl"] is None
        with session_factory() as session:
            stored = session.get(HistoryRow, saved["id"])
            assert json.loads(stored.image_ddl) == IMAGE_RECORD
            assert stored.input == stored.source_text == ""
    finally:
        engine.dispose()
