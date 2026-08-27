"""Direct ownership coverage for the legacy column migration coordinator."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from inku_server import db
from inku_server.persistence import legacy_schema


def _owner_types_or_fail():
    manifest_type = getattr(legacy_schema, "LegacyColumnMigrationManifest", None)
    migrator_type = getattr(legacy_schema, "LegacyColumnMigrator", None)
    assert manifest_type is not None
    assert migrator_type is not None
    return manifest_type, migrator_type


@pytest.mark.parametrize("include_fts", [False, True])
def test_frozen_owner_preserves_exact_transform_and_leaf_order(include_fts) -> None:
    manifest_type, migrator_type = _owner_types_or_fail()
    assert manifest_type.__dataclass_params__.frozen
    assert migrator_type.__dataclass_params__.frozen
    manifest = manifest_type(
        (("old-kind", "new-kind"),),
        {"added_history": "ALTER HISTORY"},
        {"added_lineage": "ALTER LINEAGE"},
        {"added_user": "ALTER USER"},
        (("history-index", "CREATE HISTORY INDEX"),),
        (("lineage-index", "CREATE LINEAGE INDEX"),),
    )
    with pytest.raises(AttributeError):
        manifest.history_column_migrations = {}

    events = []

    class Table:
        def create(self, *, bind, checkfirst):
            events.append(("table.create", bind, checkfirst))

    class Inspector:
        def get_columns(self, table_name):
            events.append(("get_columns", table_name))
            if table_name == "history":
                return [{"name": "vary_seed"}, {"name": "ddl"}]
            return []

        def has_table(self, table_name):
            events.append(("has_table", table_name))
            return True

    class Connection:
        def execute(self, statement, params=None):
            events.append(("execute", statement, params))

    connection = Connection()

    class BorrowedContext:
        def __enter__(self):
            events.append(("enter", connection))
            return connection

        def __exit__(self, *args):
            events.append(("exit", connection))

    class UnusedEngine:
        def begin(self):
            raise AssertionError("a borrowed connection must not open the engine")

    def nullcontext_fn(received):
        events.append(("nullcontext", received))
        return BorrowedContext()

    def inspect_fn(received):
        events.append(("inspect", received))
        return Inspector()

    def leaf(name):
        return lambda received: events.append((name, received))

    owner = migrator_type(
        UnusedEngine(),
        nullcontext_fn,
        inspect_fn,
        lambda source: source,
        Table(),
        manifest,
        leaf("render_hash"),
        leaf("nameplates"),
        leaf("history_fts"),
    )
    with pytest.raises(AttributeError):
        owner.manifest = manifest

    assert owner.migrate(connection, include_fts=include_fts) is None
    expected = [
        ("nullcontext", connection),
        ("enter", connection),
        ("table.create", connection, True),
        ("inspect", connection),
        ("get_columns", "history"),
        (
            "execute",
            "ALTER TABLE history RENAME COLUMN vary_seed TO composition_seed",
            None,
        ),
        ("execute", "ALTER HISTORY", None),
        (
            "execute",
            "UPDATE history SET expanded_ddl = ddl, ddl = NULL WHERE ddl IS NOT NULL",
            None,
        ),
        ("get_columns", "user_accounts"),
        ("has_table", "lineage_nodes"),
        ("get_columns", "lineage_nodes"),
        ("execute", "ALTER LINEAGE", None),
        ("execute", "ALTER USER", None),
        ("has_table", "lineage_edges"),
        (
            "execute",
            "UPDATE lineage_edges SET derivation_kind = :after WHERE derivation_kind = :before",
            {"before": "old-kind", "after": "new-kind"},
        ),
        ("execute", "CREATE HISTORY INDEX", None),
        ("execute", "CREATE LINEAGE INDEX", None),
        ("render_hash", connection),
        ("nameplates", connection),
    ]
    if include_fts:
        expected.append(("history_fts", connection))
    expected.append(("exit", connection))
    assert events == expected


def test_db_facade_constructs_manifest_and_owner_from_live_dependencies(monkeypatch) -> None:
    manifest_args = []
    owner_args = []
    migrate_calls = []
    connection = object()
    result = object()
    dependencies = [object() for _ in range(14)]

    class RecordingManifest:
        def __init__(self, *args):
            manifest_args.append(args)

    class RecordingMigrator:
        def __init__(self, *args):
            owner_args.append(args)

        def migrate(self, received, *, include_fts):
            migrate_calls.append((received, include_fts))
            return result

    monkeypatch.setattr(legacy_schema, "LegacyColumnMigrationManifest", RecordingManifest, raising=False)
    monkeypatch.setattr(legacy_schema, "LegacyColumnMigrator", RecordingMigrator, raising=False)
    names = (
        "engine",
        "nullcontext",
        "inspect",
        "text",
        "CoerceTraceCatalogRow",
        "_LINEAGE_KIND_RENAMES",
        "_HISTORY_COLUMN_MIGRATIONS",
        "_LINEAGE_NODE_COLUMN_MIGRATIONS",
        "_USER_ACCOUNT_COLUMN_MIGRATIONS",
        "_HISTORY_INDEX_MIGRATIONS",
        "_LINEAGE_NODE_INDEX_MIGRATIONS",
        "_backfill_render_hashes",
        "_migrate_renamed_catalog_nameplates",
        "_migrate_history_search",
    )
    values = dict(zip(names, dependencies, strict=True))
    values["CoerceTraceCatalogRow"] = type("Row", (), {"__table__": dependencies[4]})
    for name, value in values.items():
        monkeypatch.setattr(db, name, value)

    assert db._migrate_columns(connection, include_fts=False) is result
    assert manifest_args == [tuple(dependencies[5:11])]
    manifest = owner_args[0][5]
    assert owner_args == [
        (
            dependencies[0],
            dependencies[1],
            dependencies[2],
            dependencies[3],
            dependencies[4],
            manifest,
            dependencies[11],
            dependencies[12],
            dependencies[13],
        )
    ]
    assert migrate_calls == [(connection, False)]


def test_migrate_columns_adds_missing_history_columns(tmp_path, monkeypatch):
    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with legacy_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE history (
                id VARCHAR PRIMARY KEY,
                at BIGINT NOT NULL,
                input TEXT NOT NULL DEFAULT '',
                ddl TEXT,
                score TEXT NOT NULL DEFAULT '{}',
                svg TEXT NOT NULL DEFAULT '',
                output_path TEXT,
                elapsed_ms INTEGER NOT NULL DEFAULT 0,
                stage1_model VARCHAR,
                stage2_model VARCHAR,
                tokens_in INTEGER,
                tokens_out INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE user_accounts (
                id VARCHAR PRIMARY KEY,
                username VARCHAR NOT NULL,
                email VARCHAR NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR NOT NULL,
                group_id VARCHAR,
                at BIGINT NOT NULL
            )
        """))
        # One account that predates every settings column. Without a row here the
        # migrations below are only checked for the columns they add, not for the
        # values existing accounts end up carrying.
        conn.execute(text("""
            INSERT INTO user_accounts (id, username, email, password_hash, role, group_id, at)
            VALUES ('u-legacy', 'legacy', 'legacy@example.com', 'x', 'user', NULL, 0)
        """))

    monkeypatch.setattr(db, "engine", legacy_engine)
    db._migrate_columns()
    db._migrate_columns()

    columns = {col["name"] for col in inspect(legacy_engine).get_columns("history")}
    assert {
        "user_id",
        "catalog_id",
        "render_build_number",
        "render_color_profile",
        "render_engine_id",
        "render_engine_version",
        "render_color_catalog_id",
        "render_color_catalog_name",
        "render_color_catalog_sub",
        "render_color_catalog",
        "render_color_map",
        "render_canvas_aspect",
        "render_canvas_aspect_id",
        "render_canvas_aspect_ratio",
        "render_hash",
        "trashed",
        "starred",
    } <= columns
    user_columns = {col["name"] for col in inspect(legacy_engine).get_columns("user_accounts")}
    assert {"ui_theme", "ui_mode", "ui_custom", "tooltips_enabled", "model_settings", "batch_prompt_history", "demo_settings", "export_templates"} <= user_columns
    # An account that existed before the column keeps the visible side of every
    # setting the migration backfills. Asserting only that the column arrived
    # leaves the default free to flip: turning tooltips off for every existing
    # account passed all 118 tests before this line was added.
    with legacy_engine.connect() as conn:
        migrated = conn.execute(text(
            "SELECT ui_theme, ui_mode, tooltips_enabled FROM user_accounts WHERE id = 'u-legacy'"
        )).one()
    assert migrated.ui_theme == "light"
    assert migrated.ui_mode == "simple"
    assert bool(migrated.tooltips_enabled) is True
    indexes = {idx["name"] for idx in inspect(legacy_engine).get_indexes("history")}
    assert {"ix_history_user_id", "ix_history_user_trashed_at", "ix_history_user_starred_trashed_at"} <= indexes
    with legacy_engine.connect() as conn:
        sqlite_objects = {
            row[0]
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"))
        }
    assert "history_fts" in sqlite_objects
    assert {"history_fts_ai", "history_fts_ad", "history_fts_au"} <= sqlite_objects


def test_migrate_columns_raises_when_history_inspection_fails(monkeypatch):
    class BadInspector:
        def get_columns(self, table_name: str):
            raise RuntimeError(f"cannot inspect {table_name}")

    monkeypatch.setattr(db, "inspect", lambda conn: BadInspector())
    with pytest.raises(RuntimeError, match="failed to inspect history table columns"):
        db._migrate_columns()
