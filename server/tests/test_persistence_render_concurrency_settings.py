"""Direct authority and transaction coverage for render-concurrency settings."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "RenderConcurrencySettingsStore", None)
    if store is None:
        pytest.skip(
            "render-concurrency settings store is intentionally absent during fail-first"
        )
    return store


def test_settings_owns_render_concurrency_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "RenderConcurrencySettingsStore", None)
    assert store is not None, "persistence.settings must own render concurrency"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).app_settings = None

    for name in (
        "_clamped_concurrency",
        "_normalize_render_concurrency_settings",
        "_render_concurrency_settings_store",
        "get_render_concurrency_settings",
        "update_render_concurrency_settings",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert db._RENDER_CONCURRENCY_SETTINGS_KEY == settings.RENDER_CONCURRENCY_SETTINGS_KEY
    assert db._RENDER_CONCURRENCY_DEFAULT_SETTINGS is settings.RENDER_CONCURRENCY_DEFAULT_SETTINGS
    assert db.RENDER_CONCURRENCY_MIN == settings.RENDER_CONCURRENCY_MIN
    assert db.RENDER_CONCURRENCY_MAX == settings.RENDER_CONCURRENCY_MAX

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
    monkeypatch.setattr(db._settings, "RenderConcurrencySettingsStore", RecordingStore)
    monkeypatch.setattr(db, "_app_settings_store", lambda: dependency)
    assert db.get_render_concurrency_settings() == "get-sentinel"
    assert db.update_render_concurrency_settings(5, 3) == "update-sentinel"
    assert calls == [
        ("get", dependency, ()),
        ("update", dependency, (5, 3)),
    ]


def test_render_concurrency_normalization_preserves_defaults_and_range() -> None:
    _store_or_skip()
    default = settings.normalize_render_concurrency_settings(None)
    assert default == settings.RENDER_CONCURRENCY_DEFAULT_SETTINGS
    assert default is not settings.RENDER_CONCURRENCY_DEFAULT_SETTINGS
    assert settings.normalize_render_concurrency_settings(
        {"server_limit": "5"}
    ) == {
        "server_limit": 5,
        "client_limit": int(settings.RENDER_CONCURRENCY_DEFAULT_SETTINGS["client_limit"]),
    }
    assert settings.normalize_render_concurrency_settings(
        {"server_limit": 1, "client_limit": 16}
    ) == {"server_limit": 1, "client_limit": 16}

    for value in ("bad", None):
        with pytest.raises(ValueError, match="server_limit must be an integer"):
            settings.clamped_concurrency(value, "server_limit")
    for value in (0, 17):
        with pytest.raises(ValueError, match="client_limit must be between 1 and 16"):
            settings.clamped_concurrency(value, "client_limit")


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


def test_render_concurrency_store_preserves_read_and_write() -> None:
    store_type = _store_or_skip()
    missing = _AppSettings(None)
    assert store_type(missing).get() == settings.RENDER_CONCURRENCY_DEFAULT_SETTINGS
    assert missing.calls == [("read", settings.RENDER_CONCURRENCY_SETTINGS_KEY)]

    dependency = _AppSettings({"server_limit": "6", "client_limit": 2})
    store = store_type(dependency)
    assert store.get() == {"server_limit": 6, "client_limit": 2}
    assert store.update(4, 7) == {"server_limit": 4, "client_limit": 7}
    assert dependency.calls == [
        ("read", settings.RENDER_CONCURRENCY_SETTINGS_KEY),
        (
            "write",
            settings.RENDER_CONCURRENCY_SETTINGS_KEY,
            {"server_limit": 4, "client_limit": 7},
        ),
    ]


def test_render_concurrency_store_preserves_validation_and_exceptions() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings(None)
    store = store_type(dependency)
    with pytest.raises(ValueError, match="server_limit must be between 1 and 16"):
        store.update(0, 4)
    assert dependency.calls == []

    class BrokenSettings(_AppSettings):
        def read(self, _key: str) -> dict | None:
            raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        store_type(BrokenSettings(None)).get()
