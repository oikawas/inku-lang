"""Direct coverage for the legacy history FTS installation decision."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass

import pytest
from sqlalchemy import create_engine

from inku_server import db
from inku_server.persistence import migrations


REQUIRED_HISTORY_COLUMNS = frozenset(
    {"input", "ddl", "stage1_model", "stage2_model", "catalog_id"}
)


def _installer_or_fail():
    installer_type = getattr(migrations, "LegacyHistoryFtsInstaller", None)
    assert installer_type is not None
    return installer_type


@pytest.mark.parametrize("installed", [False, True])
def test_migrations_owns_frozen_installer_with_exact_decision_branches(installed) -> None:
    installer_type = _installer_or_fail()
    assert is_dataclass(installer_type) and installer_type.__dataclass_params__.frozen
    connection = object()
    inspected = []
    installed_with = []

    class Inspector:
        def get_columns(self, table_name):
            inspected.append(table_name)
            return [{"name": name} for name in REQUIRED_HISTORY_COLUMNS]

    def inspect_fn(received):
        assert received is connection
        return Inspector()

    def install_fn(received, *, rebuild):
        installed_with.append((received, rebuild))
        return installed

    owner = installer_type(REQUIRED_HISTORY_COLUMNS, inspect_fn, install_fn)
    with pytest.raises(FrozenInstanceError):
        owner.required_columns = frozenset()

    assert owner.install(connection) is installed
    assert inspected == ["history"]
    assert installed_with == [(connection, True)]


def test_installer_refuses_partial_history_without_calling_fts_installer() -> None:
    connection = object()
    inspect_calls = []
    install_calls = []

    class Inspector:
        def get_columns(self, table_name):
            assert table_name == "history"
            return [{"name": name} for name in REQUIRED_HISTORY_COLUMNS - {"catalog_id"}]

    def inspect_fn(received):
        inspect_calls.append(received)
        return Inspector()

    def install_fn(*args, **kwargs):
        install_calls.append((args, kwargs))
        return True

    owner = _installer_or_fail()(REQUIRED_HISTORY_COLUMNS, inspect_fn, install_fn)

    assert owner.install(connection) is False
    assert inspect_calls == [connection]
    assert install_calls == []


@pytest.mark.parametrize("enabled", [False, True])
def test_db_facade_constructs_at_call_time_and_assigns_global_flag(monkeypatch, enabled) -> None:
    connection = object()
    created = []
    calls = []

    class RecordingInstaller:
        def __init__(self, *args):
            created.append(args)

        def install(self, received):
            calls.append(received)
            return enabled

    inspect_fn = object()
    install_fn = object()
    monkeypatch.setattr(migrations, "LegacyHistoryFtsInstaller", RecordingInstaller, raising=False)
    monkeypatch.setattr(db, "inspect", inspect_fn)
    monkeypatch.setattr(db, "install_history_fts", install_fn)
    monkeypatch.setattr(db, "_HISTORY_FTS_ENABLED", not enabled)

    assert db._migrate_history_search(connection) is None
    assert created == [(REQUIRED_HISTORY_COLUMNS, inspect_fn, install_fn)]
    assert calls == [connection]
    assert db._HISTORY_FTS_ENABLED is enabled


@pytest.mark.parametrize("missing_column", [*sorted(REQUIRED_HISTORY_COLUMNS), None])
def test_real_sqlite_installs_fts_only_for_a_complete_history_table(missing_column) -> None:
    engine = create_engine("sqlite://")
    columns = [name for name in sorted(REQUIRED_HISTORY_COLUMNS) if name != missing_column]
    column_sql = ", ".join(f"{name} TEXT" for name in columns)

    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE TABLE history ({column_sql})")
        if missing_column is None:
            connection.exec_driver_sql(
                "INSERT INTO history(input, ddl, stage1_model, stage2_model, catalog_id) "
                "VALUES ('search needle', 'ddl body', 'stage one', 'stage two', 'catalog')"
            )
        db._HISTORY_FTS_ENABLED = True
        db._migrate_history_search(connection)
        object_names = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE name LIKE 'history_fts%'"
            )
        }

        if missing_column is not None:
            assert db._HISTORY_FTS_ENABLED is False
            assert object_names == set()
        else:
            assert db._HISTORY_FTS_ENABLED is True
            assert object_names == {
                "history_fts",
                "history_fts_ai",
                "history_fts_config",
                "history_fts_data",
                "history_fts_docsize",
                "history_fts_idx",
                "history_fts_ad",
                "history_fts_au",
            }
            assert connection.exec_driver_sql(
                "SELECT rowid FROM history_fts WHERE history_fts MATCH 'needle'"
            ).scalar_one() == 1

    engine.dispose()
