"""Direct authority and transaction coverage for render-limit storage."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "RenderLimitSettingsStore", None)
    if store is None:
        pytest.skip("render-limit settings store is intentionally absent during fail-first")
    return store


def test_settings_owns_render_limit_storage_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "RenderLimitSettingsStore", None)
    assert store is not None, "persistence.settings must own render-limit storage"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None, None).app_settings = None

    for name in (
        "_render_limit_settings_store",
        "get_render_limit_settings",
        "update_render_limit_settings",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert db._RENDER_LIMIT_SETTINGS_KEY == settings.RENDER_LIMIT_SETTINGS_KEY

    calls: list[tuple[str, object, object, tuple[object, ...]]] = []

    class RecordingStore:
        def __init__(self, dependency: object, normalizer: object) -> None:
            self.dependency = dependency
            self.normalizer = normalizer

        def get(self) -> str:
            calls.append(("get", self.dependency, self.normalizer, ()))
            return "get-sentinel"

        def update(self, *args: object) -> str:
            calls.append(("update", self.dependency, self.normalizer, args))
            return "update-sentinel"

    dependency = object()

    def normalizer(value: object) -> object:
        return value

    monkeypatch.setattr(db._settings, "RenderLimitSettingsStore", RecordingStore)
    monkeypatch.setattr(db, "_app_settings_store", lambda: dependency)
    monkeypatch.setattr(db, "normalize_limits", normalizer)
    assert db.get_render_limit_settings() == "get-sentinel"
    assert db.update_render_limit_settings({"known": 7}) == "update-sentinel"
    assert calls == [
        ("get", dependency, normalizer, ()),
        ("update", dependency, normalizer, ({"known": 7},)),
    ]


class _AppSettings:
    def __init__(self, value: dict | None, write_result: object | None = None) -> None:
        self.value = value
        self.write_result = write_result
        self.calls: list[tuple[object, ...]] = []

    def read(self, key: str) -> dict | None:
        self.calls.append(("read", key))
        return self.value

    def write(self, key: str, value: dict) -> object:
        self.calls.append(("write", key, value))
        return value if self.write_result is None else self.write_result


def test_render_limit_store_normalizes_every_read() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings({"known": "7"})
    seen: list[object] = []

    def normalize(value: object) -> dict:
        seen.append(value)
        return {"known": 7, "other": 2}

    assert store_type(dependency, normalize).get() == {"known": 7, "other": 2}
    assert seen == [{"known": "7"}]
    assert dependency.calls == [("read", settings.RENDER_LIMIT_SETTINGS_KEY)]


def test_render_limit_store_merges_only_known_keys_then_normalizes() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings({"known": 1, "other": 2}, write_result="stored")
    seen: list[object] = []

    def normalize(value: object) -> dict:
        seen.append(value)
        if len(seen) == 1:
            return {"known": 1, "other": 2}
        return dict(value)

    store = store_type(dependency, normalize)
    assert store.update({"known": 9, "unknown": 99}) == "stored"
    assert seen == [
        {"known": 1, "other": 2},
        {"known": 9, "other": 2},
    ]
    assert dependency.calls == [
        ("read", settings.RENDER_LIMIT_SETTINGS_KEY),
        ("write", settings.RENDER_LIMIT_SETTINGS_KEY, {"known": 9, "other": 2}),
    ]


def test_render_limit_store_preserves_non_dict_updates_and_exceptions() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings(None)
    calls: list[object] = []

    def normalize(value: object) -> dict:
        calls.append(value)
        return {"known": 1}

    assert store_type(dependency, normalize).update([]) == {"known": 1}
    assert calls == [None, {"known": 1}]

    class BrokenSettings(_AppSettings):
        def read(self, _key: str) -> dict | None:
            raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        store_type(BrokenSettings(None), normalize).get()
