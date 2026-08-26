"""Direct authority and transaction coverage for persisted plugin storage."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
import json
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "UserPluginStorageStore", None)
    if store is None:
        pytest.skip("plugin storage store is intentionally absent during fail-first")
    return store


def test_settings_owns_plugin_storage_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    store = getattr(settings, "UserPluginStorageStore", None)
    assert store is not None, "persistence.settings must own user plugin storage"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).session_factory = None

    for name in (
        "_normalize_plugin_storage",
        "_user_plugin_storage_store",
        "get_user_plugin_storage",
        "update_user_plugin_storage",
        "update_user_plugin_value",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert db._PLUGIN_STORAGE_MAX_BYTES == settings.PLUGIN_STORAGE_MAX_BYTES

    calls: list[tuple[str, object, tuple[object, ...]]] = []

    class RecordingStore:
        def __init__(self, dependency: object) -> None:
            self.dependency = dependency

        def get(self, *args: object) -> str:
            calls.append(("get", self.dependency, args))
            return "get-sentinel"

        def update(self, *args: object) -> str:
            calls.append(("update", self.dependency, args))
            return "update-sentinel"

        def update_value(self, *args: object) -> str:
            calls.append(("value", self.dependency, args))
            return "value-sentinel"

    dependency = object()
    monkeypatch.setattr(db._settings, "UserPluginStorageStore", RecordingStore)
    monkeypatch.setattr(db, "SessionLocal", dependency)
    assert db.get_user_plugin_storage("u") == "get-sentinel"
    assert db.update_user_plugin_storage("u", {"p": {}}) == "update-sentinel"
    assert db.update_user_plugin_value("u", "p", {"x": 1}) == "value-sentinel"
    assert calls == [
        ("get", dependency, ("u",)),
        ("update", dependency, ("u", {"p": {}})),
        ("value", dependency, ("u", "p", {"x": 1})),
    ]


def test_plugin_storage_preserves_validation_and_byte_ceiling() -> None:
    _store_or_skip()
    value = {"plugin.one-2": {"enabled": True}}
    assert settings.normalize_plugin_storage(value) == value
    cases = (
        ([], "must be an object"),
        ({"": {}}, "non-empty string"),
        ({"bad id": {}}, "unsupported characters"),
        ({"x" * 81: {}}, "unsupported characters"),
        ({"valid": []}, "values must be objects"),
    )
    for storage, message in cases:
        with pytest.raises(ValueError, match=message):
            settings.normalize_plugin_storage(storage)
    with pytest.raises(ValueError, match="too large"):
        settings.normalize_plugin_storage({"valid": {"text": "あ" * 7_000}})


class _Session:
    def __init__(self, row: object | None) -> None:
        self.row = row
        self.events: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, row_type: object, key: object) -> object | None:
        self.events.append(("get", getattr(row_type, "__tablename__", "unknown"), key))
        return self.row

    def commit(self) -> None:
        self.events.append("commit")


def _build(session: _Session):
    return _store_or_skip()(lambda: session)


def test_plugin_storage_preserves_read_write_fallbacks() -> None:
    _store_or_skip()
    for row in (
        None,
        SimpleNamespace(plugin_storage="broken"),
        SimpleNamespace(plugin_storage="[]"),
        SimpleNamespace(plugin_storage='{"bad id": {}}'),
    ):
        assert _build(_Session(row)).get("u") == {}

    missing = _Session(None)
    assert _build(missing).update("missing", {"p": {}}) is None
    assert "commit" not in missing.events

    row = SimpleNamespace(plugin_storage="{}")
    session = _Session(row)
    value = {"日本語": "保持"}
    assert _build(session).update("u", {"p": value}) == {"p": value}
    assert json.loads(row.plugin_storage) == {"p": value}
    assert session.events == [("get", "user_accounts", "u"), "commit"]


def test_plugin_storage_preserves_single_value_merge_and_exceptions() -> None:
    _store_or_skip()
    row = SimpleNamespace(plugin_storage='{"old": {"x": 1}}')
    session = _Session(row)
    result = _build(session).update_value("u", "new", {"y": 2})
    assert result == {"old": {"x": 1}, "new": {"y": 2}}
    assert json.loads(row.plugin_storage) == result
    assert session.events == [
        ("get", "user_accounts", "u"),
        ("get", "user_accounts", "u"),
        "commit",
    ]

    class BrokenSession(_Session):
        def get(self, _row_type: object, _key: object) -> object:
            raise RuntimeError("get failed")

    with pytest.raises(RuntimeError, match="get failed"):
        _build(BrokenSession(None)).get("u")
