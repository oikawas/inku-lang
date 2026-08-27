"""Direct ownership coverage for renamed catalog nameplate migration."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from inku_server import db
from inku_server.persistence import migrations


UPDATE_SQL = "UPDATE history SET catalog_id = :new_id WHERE catalog_id = :old_id"
EXPECTED_RENAMES = {
    "japanese": "ink_season",
    "mexican": "vivid_material",
    "indian": "dye_earth",
    "british": "weathered_heritage",
    "egyptian": "desert_mineral",
    "impressionism": "open_air_light",
    "greek": "sea_stone",
    "renaissance": "fresco_study",
    "nordic": "cool_material",
    "chinese": "ink_porcelain",
}


class _Text:
    def __init__(self):
        self.sources = []

    def __call__(self, source):
        self.sources.append(source)
        return source


class _Connection:
    def __init__(self, *, fail_at=None):
        self.calls = []
        self.fail_at = fail_at
        self.error = ValueError("update failed")

    def execute(self, statement, params):
        self.calls.append((statement, params))
        if len(self.calls) == self.fail_at:
            raise self.error
        return None


def _migrator_or_fail():
    migrator_type = getattr(migrations, "RenamedCatalogNameplateMigrator", None)
    assert migrator_type is not None
    return migrator_type


def test_migrations_owns_frozen_migrator_with_exact_order_sql_and_parameters() -> None:
    migrator_type = _migrator_or_fail()
    assert is_dataclass(migrator_type) and migrator_type.__dataclass_params__.frozen
    renames = {"old-second": "new-second", "old-first": "new-first"}
    text_fn = _Text()
    conn = _Connection()
    migrator = migrator_type(renames, text_fn)

    with pytest.raises(FrozenInstanceError):
        migrator.renamed_catalog_ids = {}
    assert migrator.migrate(conn) is None
    assert text_fn.sources == [UPDATE_SQL, UPDATE_SQL]
    assert conn.calls == [
        (UPDATE_SQL, {"new_id": "new-second", "old_id": "old-second"}),
        (UPDATE_SQL, {"new_id": "new-first", "old_id": "old-first"}),
    ]


def test_migrator_wraps_the_exact_failing_pair_and_preserves_cause() -> None:
    renames = {"old-one": "new-one", "old-two": "new-two", "old-three": "new-three"}
    text_fn = _Text()
    conn = _Connection(fail_at=2)
    migrator = _migrator_or_fail()(renames, text_fn)

    with pytest.raises(
        RuntimeError,
        match="^failed to migrate renamed color catalog nameplate: old-two -> new-two$",
    ) as caught:
        migrator.migrate(conn)

    assert caught.value.__cause__ is conn.error
    assert conn.calls == [
        (UPDATE_SQL, {"new_id": "new-one", "old_id": "old-one"}),
        (UPDATE_SQL, {"new_id": "new-two", "old_id": "old-two"}),
    ]


def test_db_migrator_facade_constructs_and_delegates_at_call_time(monkeypatch) -> None:
    created = []
    calls = []
    renames = object()
    text_fn = object()
    conn = object()
    result = object()

    class Recording:
        def __init__(self, *args):
            created.append(args)

        def migrate(self, received):
            calls.append(received)
            return result

    monkeypatch.setattr(migrations, "RenamedCatalogNameplateMigrator", Recording, raising=False)
    monkeypatch.setattr(db, "RENAMED_COLOR_CATALOG_IDS", renames)
    monkeypatch.setattr(db, "text", text_fn)

    assert db._migrate_renamed_catalog_nameplates(conn) is result
    assert created == [(renames, text_fn)]
    assert calls == [conn]


def _legacy_history_db(path: Path, rows: list[tuple[str, str, str]]) -> None:
    """A `history` table as an older build left it, with rows already in place."""
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE history (
            id VARCHAR PRIMARY KEY, catalog_id VARCHAR,
            render_color_catalog_id VARCHAR, render_color_map TEXT
        )
        """
    )
    connection.executemany("INSERT INTO history VALUES (?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()


def _migrated(tmp_path: Path, rows: list[tuple[str, str, str]]) -> list[tuple]:
    from inku_server.db import _migrate_renamed_catalog_nameplates

    db_path = tmp_path / f"nameplates-{uuid.uuid4().hex[:8]}.db"
    _legacy_history_db(db_path, rows)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        _migrate_renamed_catalog_nameplates(conn)
    with engine.begin() as conn:
        rows_out = list(
            conn.execute(
                text("SELECT id, catalog_id, render_color_catalog_id, render_color_map FROM history")
            )
        )
    engine.dispose()
    return rows_out


SNAPSHOT_JSON = json.dumps({"black": "#111111", "palette:Sumi": "#111111"}, ensure_ascii=False)
_MIGRATION_OLD_ID = "japanese"


@pytest.mark.parametrize(("old_id", "new_id"), sorted(EXPECTED_RENAMES.items()))
def test_the_migration_moves_each_old_nameplate(tmp_path, old_id, new_id):
    """One case per pair, so a table that lost a pair loses a green test."""
    rows = _migrated(tmp_path, [("w-1", old_id, old_id, SNAPSHOT_JSON)])

    assert rows[0][1] == new_id


def test_the_migration_does_not_touch_the_colors_a_work_was_drawn_in(tmp_path):
    """The nameplate is the only thing wrong; the colors were always right."""
    rows = _migrated(
        tmp_path,
        [("w-1", _MIGRATION_OLD_ID, _MIGRATION_OLD_ID, SNAPSHOT_JSON)],
    )

    assert rows[0][3] == SNAPSHOT_JSON


def test_the_migration_does_not_touch_the_id_a_work_was_drawn_with(tmp_path):
    """Author's ruling 2026-08-09, and the reason is measured below.

    `render_color_catalog_id` is seed material for the chromatic assignment, so
    rewriting it repaints the work out of its own unchanged snapshot -- which is
    the symptom this whole change removes.
    """
    rows = _migrated(
        tmp_path,
        [("w-1", _MIGRATION_OLD_ID, _MIGRATION_OLD_ID, SNAPSHOT_JSON)],
    )

    assert rows[0][2] == _MIGRATION_OLD_ID


def test_the_migration_is_idempotent(tmp_path):
    """The transform is safe if an accepted legacy migration retries it."""
    from inku_server.db import _migrate_renamed_catalog_nameplates

    db_path = tmp_path / "idempotent.db"
    _legacy_history_db(
        db_path,
        [("w-1", _MIGRATION_OLD_ID, _MIGRATION_OLD_ID, SNAPSHOT_JSON)],
    )
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        _migrate_renamed_catalog_nameplates(conn)
        first = conn.execute(text("SELECT catalog_id FROM history")).scalar_one()
    with engine.begin() as conn:
        _migrate_renamed_catalog_nameplates(conn)
        second = conn.execute(text("SELECT catalog_id FROM history")).scalar_one()
    engine.dispose()

    assert first == second == EXPECTED_RENAMES[_MIGRATION_OLD_ID]
