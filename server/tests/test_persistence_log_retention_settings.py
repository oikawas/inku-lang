"""Direct authority and transaction coverage for log-retention settings."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "LogRetentionSettingsStore", None)
    if store is None:
        pytest.skip("log-retention store is intentionally absent during fail-first")
    return store


def test_settings_owns_log_retention_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "LogRetentionSettingsStore", None)
    assert store is not None, "persistence.settings must own log-retention settings"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).app_settings = None

    for name in (
        "_normalize_log_retention_settings",
        "_log_retention_settings_store",
        "get_log_retention_settings",
        "update_log_retention_settings",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert db._LOG_RETENTION_SETTINGS_KEY == settings.LOG_RETENTION_SETTINGS_KEY
    assert db._LOG_RETENTION_DEFAULT_SETTINGS is settings.LOG_RETENTION_DEFAULT_SETTINGS

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
    monkeypatch.setattr(db._settings, "LogRetentionSettingsStore", RecordingStore)
    monkeypatch.setattr(db, "_app_settings_store", lambda: dependency)
    assert db.get_log_retention_settings() == "get-sentinel"
    assert db.update_log_retention_settings(True, 30, "weekly", False) == "update-sentinel"
    assert calls == [
        ("get", dependency, ()),
        ("update", dependency, (True, 30, "weekly", False)),
    ]


def test_log_retention_normalization_preserves_defaults_and_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store_or_skip()
    monkeypatch.setattr(
        settings,
        "LOG_RETENTION_DEFAULT_SETTINGS",
        {"enabled": True, "retention_days": 0, "rotate": "bad", "compress": True},
    )
    assert settings.normalize_log_retention_settings(None) == {
        "enabled": True,
        "retention_days": 90,
        "rotate": "daily",
        "compress": True,
    }
    assert settings.normalize_log_retention_settings(
        {"enabled": 0, "retention_days": "30", "rotate": " WEEKLY ", "compress": 0}
    ) == {
        "enabled": False,
        "retention_days": 30,
        "rotate": "weekly",
        "compress": False,
    }

    for value in ("bad", None):
        with pytest.raises(ValueError, match="days must be an integer"):
            settings.normalize_log_retention_settings({"retention_days": value})
    for value in (0, 3651):
        with pytest.raises(ValueError, match="between 1 and 3650"):
            settings.normalize_log_retention_settings({"retention_days": value})
    with pytest.raises(ValueError, match="daily, weekly, or monthly"):
        settings.normalize_log_retention_settings({"rotate": "hourly"})


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


def test_log_retention_store_preserves_read_and_write() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings(
        {"enabled": False, "retention_days": "14", "rotate": "monthly", "compress": False}
    )
    store = store_type(dependency)
    assert store.get() == {
        "enabled": False,
        "retention_days": 14,
        "rotate": "monthly",
        "compress": False,
    }
    assert store.update(True, 30, "weekly", True) == {
        "enabled": True,
        "retention_days": 30,
        "rotate": "weekly",
        "compress": True,
    }
    assert dependency.calls[0] == ("read", settings.LOG_RETENTION_SETTINGS_KEY)
    assert dependency.calls[1][0:2] == ("write", settings.LOG_RETENTION_SETTINGS_KEY)


def test_log_retention_store_preserves_validation_and_exceptions() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings(None)
    with pytest.raises(ValueError, match="between 1 and 3650"):
        store_type(dependency).update(True, 0, "daily", True)
    assert dependency.calls == []

    class BrokenSettings(_AppSettings):
        def read(self, _key: str) -> dict | None:
            raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        store_type(BrokenSettings(None)).get()
