"""Direct authority and transaction coverage for thumbnail settings."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "ThumbnailSettingsStore", None)
    if store is None:
        pytest.skip("thumbnail settings store is intentionally absent during fail-first")
    return store


def test_settings_owns_thumbnail_settings_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "ThumbnailSettingsStore", None)
    assert store is not None, "persistence.settings must own thumbnail settings"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).app_settings = None

    for name in (
        "_normalize_thumbnail_settings",
        "_thumbnail_settings_store",
        "get_thumbnail_settings",
        "update_thumbnail_settings",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert db._THUMBNAIL_SETTINGS_KEY == settings.THUMBNAIL_SETTINGS_KEY
    assert db._THUMBNAIL_DEFAULT_SETTINGS is settings.THUMBNAIL_DEFAULT_SETTINGS
    assert db.THUMBNAIL_WORKERS_MIN == settings.THUMBNAIL_WORKERS_MIN
    assert db.THUMBNAIL_WORKERS_MAX == settings.THUMBNAIL_WORKERS_MAX

    calls: list[tuple[str, object, tuple[object, ...]]] = []

    class RecordingStore:
        def __init__(self, dependency: object) -> None:
            self.dependency = dependency

        def get(self) -> str:
            calls.append(("get", self.dependency, ()))
            return "get-sentinel"

        def update(self, *args: object) -> str:
            calls.append(("update", self.dependency, args))
            return "update-sentinel"

    dependency = object()
    monkeypatch.setattr(db._settings, "ThumbnailSettingsStore", RecordingStore)
    monkeypatch.setattr(db, "_app_settings_store", lambda: dependency)
    assert db.get_thumbnail_settings() == "get-sentinel"
    assert db.update_thumbnail_settings(True, 7) == "update-sentinel"
    assert calls == [
        ("get", dependency, ()),
        ("update", dependency, (True, 7)),
    ]


def test_thumbnail_normalization_preserves_defaults_fallback_and_clamp() -> None:
    _store_or_skip()
    default = settings.normalize_thumbnail_settings(None)
    assert default == settings.THUMBNAIL_DEFAULT_SETTINGS
    assert default is not settings.THUMBNAIL_DEFAULT_SETTINGS
    assert settings.normalize_thumbnail_settings({"hidpi": 1, "workers": "7"}) == {
        "hidpi": True,
        "workers": 7,
    }
    assert settings.normalize_thumbnail_settings({"workers": "bad"})["workers"] == 4
    assert settings.normalize_thumbnail_settings({"workers": 0})["workers"] == 1
    assert settings.normalize_thumbnail_settings({"workers": 99})["workers"] == 16


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


def test_thumbnail_store_preserves_read_and_write() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings({"hidpi": True, "workers": "6"})
    store = store_type(dependency)
    assert store.get() == {"hidpi": True, "workers": 6}
    assert store.update(False, 20) == {"hidpi": False, "workers": 16}
    assert dependency.calls == [
        ("read", settings.THUMBNAIL_SETTINGS_KEY),
        (
            "write",
            settings.THUMBNAIL_SETTINGS_KEY,
            {"hidpi": False, "workers": 16},
        ),
    ]


def test_thumbnail_store_preserves_dependency_exceptions() -> None:
    store_type = _store_or_skip()

    class BrokenSettings(_AppSettings):
        def read(self, _key: str) -> dict | None:
            raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        store_type(BrokenSettings(None)).get()
