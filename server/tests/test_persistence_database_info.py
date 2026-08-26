"""Direct ownership and edge coverage for database runtime diagnostics."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest
from sqlalchemy import create_engine

from inku_server import db
from inku_server.persistence import engine as persistence_engine
from inku_server.persistence.config import PersistenceConfig


def _reader_or_skip():
    reader = getattr(persistence_engine, "DatabaseInfoReader", None)
    if reader is None:
        pytest.skip("database info reader is intentionally absent during fail-first")
    return reader


def test_engine_owns_database_info_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = getattr(persistence_engine, "DatabaseInfoReader", None)
    assert reader is not None, "persistence.engine must own database diagnostics"
    assert is_dataclass(reader) and reader.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        reader(None, None).engine = None
    for name in ("_database_info_reader", "database_info"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    class RecordingReader:
        def __init__(self, received_engine, received_config) -> None:
            assert received_engine is db.engine
            assert received_config is db.PERSISTENCE_CONFIG

        def get(self):
            return {"sentinel": True}

    monkeypatch.setattr(persistence_engine, "DatabaseInfoReader", RecordingReader)
    assert db.database_info() == {"sentinel": True}


def test_database_info_reports_file_path_and_current_size(tmp_path) -> None:
    reader = _reader_or_skip()
    database_path = tmp_path / "runtime.sqlite"
    database_path.write_bytes(b"sqlite-bytes")
    url = f"sqlite:///{database_path}"
    sql_engine = create_engine(url)
    try:
        info = reader(sql_engine, PersistenceConfig(url, url)).get()
    finally:
        sql_engine.dispose()
    assert info["backend"] == "sqlite"
    assert info["driver"] == "pysqlite"
    assert info["database"] == str(database_path)
    assert info["file_path"] == str(database_path)
    assert info["file_size_bytes"] == len(b"sqlite-bytes")
    assert info["is_default"] is False


def test_database_info_preserves_memory_database_absence() -> None:
    reader = _reader_or_skip()
    url = "sqlite:///:memory:"
    sql_engine = create_engine(url)
    try:
        info = reader(sql_engine, PersistenceConfig(url, url)).get()
    finally:
        sql_engine.dispose()
    assert info["database"] == ":memory:"
    assert info["file_path"] is None
    assert info["file_size_bytes"] is None


def test_database_info_preserves_missing_file_and_masked_url(tmp_path) -> None:
    reader = _reader_or_skip()
    database_path = tmp_path / "missing.sqlite"
    url = f"sqlite:///{database_path}"
    sql_engine = create_engine(url)
    try:
        info = reader(sql_engine, PersistenceConfig(url, url)).get()
    finally:
        sql_engine.dispose()
    assert info["url"] == url
    assert info["file_path"] == str(database_path)
    assert info["file_size_bytes"] is None
