"""Direct authority and transaction coverage for output-save settings."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from pathlib import Path

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "OutputSaveSettingsStore", None)
    if store is None:
        pytest.skip("output-save settings store is intentionally absent during fail-first")
    return store


def test_settings_owns_output_save_settings_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "OutputSaveSettingsStore", None)
    assert store is not None, "persistence.settings must own output-save settings"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).app_settings = None

    for name in (
        "_normalize_output_save_settings",
        "_output_save_settings_store",
        "get_output_save_settings",
        "update_output_save_settings",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert db._OUTPUT_SAVE_SETTINGS_KEY == settings.OUTPUT_SAVE_SETTINGS_KEY
    assert db._OUTPUT_SAVE_DEFAULT_SETTINGS is settings.OUTPUT_SAVE_DEFAULT_SETTINGS

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
    monkeypatch.setattr(db._settings, "OutputSaveSettingsStore", RecordingStore)
    monkeypatch.setattr(db, "_app_settings_store", lambda: dependency)
    assert db.get_output_save_settings() == "get-sentinel"
    assert db.update_output_save_settings(False, "/tmp/out", 1080) == "update-sentinel"
    assert calls == [
        ("get", dependency, ()),
        ("update", dependency, (False, "/tmp/out", 1080)),
    ]


def test_output_save_normalization_preserves_defaults_and_validation() -> None:
    _store_or_skip()
    default = settings.normalize_output_save_settings(None)
    assert default == settings.OUTPUT_SAVE_DEFAULT_SETTINGS
    assert default is not settings.OUTPUT_SAVE_DEFAULT_SETTINGS
    assert settings.normalize_output_save_settings(
        {"enabled": 0, "output_dir": "~/outputs", "png_size": "1080"}
    ) == {
        "enabled": False,
        "output_dir": str(Path("~/outputs").expanduser()),
        "png_size": 1080,
    }

    with pytest.raises(ValueError, match="must not be empty"):
        settings.normalize_output_save_settings({"output_dir": "  "})
    with pytest.raises(ValueError, match="absolute path"):
        settings.normalize_output_save_settings({"output_dir": "relative/out"})
    for value in (1440, "bad", None):
        with pytest.raises(ValueError, match="1080 or 2160"):
            settings.normalize_output_save_settings({"png_size": value})


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


def test_output_save_store_preserves_read_and_write() -> None:
    store_type = _store_or_skip()
    missing = _AppSettings(None)
    assert store_type(missing).get() == settings.OUTPUT_SAVE_DEFAULT_SETTINGS
    assert missing.calls == [("read", settings.OUTPUT_SAVE_SETTINGS_KEY)]

    dependency = _AppSettings(
        {"enabled": False, "output_dir": "/var/tmp/inku", "png_size": 1080}
    )
    store = store_type(dependency)
    assert store.get() == {
        "enabled": False,
        "output_dir": "/var/tmp/inku",
        "png_size": 1080,
    }
    assert store.update(True, "/var/tmp/new", 2160) == {
        "enabled": True,
        "output_dir": "/var/tmp/new",
        "png_size": 2160,
    }
    assert dependency.calls == [
        ("read", settings.OUTPUT_SAVE_SETTINGS_KEY),
        (
            "write",
            settings.OUTPUT_SAVE_SETTINGS_KEY,
            {"enabled": True, "output_dir": "/var/tmp/new", "png_size": 2160},
        ),
    ]


def test_output_save_store_preserves_validation_and_exceptions() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings(None)
    store = store_type(dependency)
    with pytest.raises(ValueError, match="absolute path"):
        store.update(True, "relative/out", 2160)
    assert dependency.calls == []

    class BrokenSettings(_AppSettings):
        def read(self, _key: str) -> dict | None:
            raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        store_type(BrokenSettings(None)).get()
