"""Direct ownership and behavior coverage for the generic app-setting store."""

from __future__ import annotations

import importlib
import inspect
import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence.schema import AppSettingRow


def _session_factory():
    engine = create_engine("sqlite://")
    AppSettingRow.__table__.create(engine)
    return sessionmaker(bind=engine)


def test_persistence_settings_owns_store_and_db_facades_follow_runtime_dependencies(
    monkeypatch,
) -> None:
    settings = importlib.import_module("inku_server.persistence.settings")

    settings_source = inspect.getsource(settings)
    assert "inku_server.db" not in settings_source
    assert "from .. import db" not in settings_source
    assert "_SETTING_KEY" not in settings_source

    assert str(inspect.signature(db._read_app_setting)) == "(key: 'str') -> 'dict | None'"
    assert str(inspect.signature(db._write_app_setting)) == "(key: 'str', value: 'dict') -> 'dict'"
    read_source = inspect.getsource(db._read_app_setting)
    write_source = inspect.getsource(db._write_app_setting)
    assert "AppSettingRow" not in read_source
    assert "AppSettingRow" not in write_source
    assert "json." not in read_source
    assert "json." not in write_source

    first_factory = _session_factory()
    direct_store = settings.AppSettingsStore(first_factory, lambda: 100)
    assert direct_store.read("missing") is None
    with first_factory() as session:
        session.add_all(
            [
                AppSettingRow(key="malformed", value="{", at=1),
                AppSettingRow(key="scalar", value='["not", "an", "object"]', at=2),
                AppSettingRow(key="object", value='{"name": "雪"}', at=3),
            ]
        )
        session.commit()
    assert direct_store.read("malformed") is None
    assert direct_store.read("scalar") is None
    assert direct_store.read("object") == {"name": "雪"}

    monkeypatch.setattr(db, "SessionLocal", first_factory)
    monkeypatch.setattr(db, "_now_ms", lambda: 101)
    inserted = {"name": "雪", "rank": 1}
    assert db._write_app_setting("facade", inserted) is inserted
    with first_factory() as session:
        row = session.get(AppSettingRow, "facade")
        assert row is not None
        assert row.value == json.dumps(inserted, ensure_ascii=False)
        assert row.at == 101

    monkeypatch.setattr(db, "_now_ms", lambda: 202)
    updated = {"name": "霧", "rank": 2}
    assert db._write_app_setting("facade", updated) is updated
    with first_factory() as session:
        row = session.get(AppSettingRow, "facade")
        assert row is not None
        assert row.value == json.dumps(updated, ensure_ascii=False)
        assert row.at == 202
        assert session.scalars(select(AppSettingRow).where(AppSettingRow.key == "facade")).all() == [row]

    second_factory = _session_factory()
    monkeypatch.setattr(db, "SessionLocal", second_factory)
    monkeypatch.setattr(db, "_now_ms", lambda: 303)
    second = {"fresh": True}
    assert db._write_app_setting("facade", second) is second
    assert db._read_app_setting("facade") == second
    with first_factory() as session:
        assert session.get(AppSettingRow, "facade").value == json.dumps(updated, ensure_ascii=False)
