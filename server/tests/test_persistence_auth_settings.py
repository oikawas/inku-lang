"""Direct authority and transaction coverage for authentication settings."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "AuthSettingsStore", None)
    if store is None:
        pytest.skip("auth settings store is intentionally absent during fail-first")
    return store


def test_settings_owns_auth_settings_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "AuthSettingsStore", None)
    assert store is not None, "persistence.settings must own auth settings"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None, None).app_settings = None

    for name in (
        "_normalize_auth_settings",
        "_auth_settings_store",
        "get_auth_settings",
        "update_auth_settings",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert db._AUTH_SETTINGS_KEY == settings.AUTH_SETTINGS_KEY
    assert db._AUTH_DEFAULT_SETTINGS is settings.AUTH_DEFAULT_SETTINGS

    calls: list[tuple[str, object, tuple[object, ...]]] = []

    class RecordingStore:
        def __init__(self, dependency, getenv) -> None:
            self.dependency = dependency
            self.getenv = getenv

        def get(self):
            calls.append(("get", self.dependency, ()))
            return "get-sentinel"

        def update(self, *args):
            calls.append(("update", self.dependency, args))
            return "update-sentinel"

    dependency = object()
    monkeypatch.setattr(db._settings, "AuthSettingsStore", RecordingStore)
    monkeypatch.setattr(db, "_app_settings_store", lambda: dependency)
    assert db.get_auth_settings() == "get-sentinel"
    assert db.update_auth_settings(True, False) == "update-sentinel"
    assert calls == [
        ("get", dependency, ()),
        ("update", dependency, (True, False)),
    ]


def test_auth_environment_defaults_preserve_current_parsing() -> None:
    _store_or_skip()
    values = {
        "INKU_AUTH_GOOGLE_ENABLED": "yes",
        "INKU_AUTH_LOCAL_ENABLED": " true ",
    }
    def getenv(key, default):
        return values.get(key, default)

    assert settings.auth_defaults_from_env(getenv) == {
        "google_enabled": True,
        "local_enabled": False,
    }
    assert settings.auth_defaults_from_env(lambda _key, default: default) == {
        "google_enabled": False,
        "local_enabled": True,
    }


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


def test_auth_store_preserves_stored_precedence_and_update() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings({"google_enabled": 0, "unrelated": True})
    values = {
        "INKU_AUTH_GOOGLE_ENABLED": "true",
        "INKU_AUTH_LOCAL_ENABLED": "false",
    }
    store = store_type(dependency, lambda key, default: values.get(key, default))
    assert store.get() == {"google_enabled": False, "local_enabled": False}
    assert store.update(1, 0) == {"google_enabled": True, "local_enabled": False}
    assert dependency.calls == [
        ("read", settings.AUTH_SETTINGS_KEY),
        (
            "write",
            settings.AUTH_SETTINGS_KEY,
            {"google_enabled": True, "local_enabled": False},
        ),
    ]


def test_auth_store_preserves_missing_rows_and_exceptions() -> None:
    store_type = _store_or_skip()
    def defaults(_key, default):
        return default

    assert store_type(_AppSettings(None), defaults).get() == {
        "google_enabled": False,
        "local_enabled": True,
    }

    class BrokenSettings(_AppSettings):
        def read(self, _key: str) -> dict | None:
            raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        store_type(BrokenSettings(None), defaults).get()
