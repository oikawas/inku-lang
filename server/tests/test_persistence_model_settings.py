"""Direct authority and transaction coverage for model connection settings."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "ModelSettingsStore", None)
    if store is None:
        pytest.skip("model settings store is intentionally absent during fail-first")
    return store


def test_settings_owns_model_settings_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "ModelSettingsStore", None)
    assert store is not None, "persistence.settings must own model settings"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None, None, None).app_settings = None

    factory = ast.parse(inspect.getsource(db._model_settings_store)).body[0]
    assert isinstance(factory, ast.FunctionDef)
    assert isinstance(factory.body[-1], ast.Return)
    for name in ("get_model_settings", "update_model_settings"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert db._MODEL_SETTINGS_KEY == settings.MODEL_SETTINGS_KEY

    calls: list[tuple[str, object]] = []

    class RecordingStore:
        def __init__(self, app_settings, normalize, storage) -> None:
            calls.extend(
                [("dependency", app_settings), ("normalize", normalize), ("storage", storage)]
            )

        def get(self):
            return "get-sentinel"

        def update(self, value):
            calls.append(("update", value))
            return "update-sentinel"

    dependency = object()
    monkeypatch.setattr(db._settings, "ModelSettingsStore", RecordingStore)
    monkeypatch.setattr(db, "_app_settings_store", lambda: dependency)
    assert db.get_model_settings() == "get-sentinel"
    assert db.update_model_settings({"marker": 1}) == "update-sentinel"
    assert calls[0] == ("dependency", dependency)
    assert calls[3] == ("dependency", dependency)
    assert calls[-1] == ("update", {"marker": 1})


class _AppSettings:
    def __init__(self, value: dict | None) -> None:
        self.value = value
        self.calls: list[tuple[object, ...]] = []

    def read(self, key: str) -> dict | None:
        self.calls.append(("read", key))
        return self.value

    def write(self, key: str, value: dict) -> dict:
        self.calls.append(("write", key, value))
        return value


def test_model_settings_store_normalizes_reads() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings({"stored": True})
    calls: list[object] = []

    def normalize(value):
        calls.append(value)
        return {"runtime": value}

    store = store_type(dependency, normalize, lambda value: value)
    assert store.get() == {"runtime": {"stored": True}}
    assert calls == [{"stored": True}]
    assert dependency.calls == [("read", settings.MODEL_SETTINGS_KEY)]


def test_model_settings_store_projects_then_normalizes_writes() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings(None)
    calls: list[tuple[str, object]] = []

    def storage(value):
        calls.append(("storage", value))
        return {"encrypted": value["secret"]}

    def normalize(value):
        calls.append(("normalize", value))
        return {"runtime": value}

    store = store_type(dependency, normalize, storage)
    assert store.update({"secret": "opaque"}) == {
        "runtime": {"encrypted": "opaque"}
    }
    assert calls == [
        ("storage", {"secret": "opaque"}),
        ("normalize", {"encrypted": "opaque"}),
    ]
    assert dependency.calls == [
        ("write", settings.MODEL_SETTINGS_KEY, {"encrypted": "opaque"})
    ]


def test_model_settings_store_preserves_exceptions() -> None:
    store_type = _store_or_skip()

    class BrokenSettings(_AppSettings):
        def read(self, _key: str) -> dict | None:
            raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        store_type(BrokenSettings(None), lambda value: value, lambda value: value).get()

    def broken_storage(_value):
        raise ValueError("projection failed")

    dependency = _AppSettings(None)
    with pytest.raises(ValueError, match="projection failed"):
        store_type(dependency, lambda value: value, broken_storage).update({})
    assert dependency.calls == []
