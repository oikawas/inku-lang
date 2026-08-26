"""Direct authority and transaction coverage for the single-user pin."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "SingleUserPinStore", None)
    if store is None:
        pytest.skip("single-user pin store is intentionally absent during fail-first")
    return store


def test_settings_owns_single_user_pin_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "SingleUserPinStore", None)
    assert store is not None, "persistence.settings must own single-user pin storage"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).app_settings = None

    for name in ("_single_user_pin_store", "single_user_pinned_id"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert isinstance(facade.body[-1], ast.Return)
    assert db._SINGLE_USER_SETTING_KEY == settings.SINGLE_USER_SETTINGS_KEY
    for name in ("single_user_account", "single_user_pinned_id", "set_single_user_pin"):
        source = inspect.getsource(getattr(db, name))
        assert "_read_app_setting" not in source
        assert "_write_app_setting" not in source

    class RecordingStore:
        def __init__(self, dependency) -> None:
            self.dependency = dependency

        def get(self):
            return "pin-sentinel"

    dependency = object()
    monkeypatch.setattr(db._settings, "SingleUserPinStore", RecordingStore)
    monkeypatch.setattr(db, "_app_settings_store", lambda: dependency)
    assert db.single_user_pinned_id() == "pin-sentinel"


class _AppSettings:
    def __init__(self, value: dict | None) -> None:
        self.value = value
        self.calls: list[tuple[object, ...]] = []

    def read(self, key: str) -> dict | None:
        self.calls.append(("read", key))
        return self.value

    def write(self, key: str, value: dict) -> dict:
        self.calls.append(("write", key, value))
        self.value = value
        return value


def test_single_user_pin_store_preserves_missing_and_present_reads() -> None:
    store_type = _store_or_skip()
    missing = _AppSettings(None)
    assert store_type(missing).get() is None
    assert missing.calls == [("read", settings.SINGLE_USER_SETTINGS_KEY)]

    present = _AppSettings({"user_id": "user-1", "future": 7})
    assert store_type(present).get() == "user-1"


def test_single_user_pin_store_merge_writes_without_losing_other_fields() -> None:
    store_type = _store_or_skip()
    dependency = _AppSettings({"future": {"kept": True}, "user_id": "old"})
    assert store_type(dependency).update("new") == "new"
    assert dependency.calls == [
        ("read", settings.SINGLE_USER_SETTINGS_KEY),
        (
            "write",
            settings.SINGLE_USER_SETTINGS_KEY,
            {"future": {"kept": True}, "user_id": "new"},
        ),
    ]


def test_single_user_pin_store_preserves_read_and_write_exceptions() -> None:
    store_type = _store_or_skip()

    class BrokenRead(_AppSettings):
        def read(self, _key: str) -> dict | None:
            raise RuntimeError("read failed")

    with pytest.raises(RuntimeError, match="read failed"):
        store_type(BrokenRead(None)).get()

    class BrokenWrite(_AppSettings):
        def write(self, _key: str, _value: dict) -> dict:
            raise RuntimeError("write failed")

    with pytest.raises(RuntimeError, match="write failed"):
        store_type(BrokenWrite({"future": 1})).update("new")
