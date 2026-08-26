"""Direct authority and transaction coverage for persisted demo settings."""

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
    store = getattr(settings, "UserDemoSettingsStore", None)
    if store is None:
        pytest.skip("demo settings store is intentionally absent during fail-first")
    return store


def test_settings_owns_demo_settings_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    store = getattr(settings, "UserDemoSettingsStore", None)
    assert store is not None, "persistence.settings must own user demo settings"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).session_factory = None

    for name in (
        "_normalize_demo_settings",
        "_user_demo_settings_store",
        "get_user_demo_settings",
        "update_user_demo_settings",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    assert db._DEMO_DEFAULT_SETTINGS is settings.DEMO_DEFAULT_SETTINGS

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

    dependency = object()
    monkeypatch.setattr(db._settings, "UserDemoSettingsStore", RecordingStore)
    monkeypatch.setattr(db, "SessionLocal", dependency)
    assert db.get_user_demo_settings("u") == "get-sentinel"
    assert db.update_user_demo_settings("u", {"save_db": True}) == "update-sentinel"
    assert calls == [
        ("get", dependency, ("u",)),
        ("update", dependency, ("u", {"save_db": True})),
    ]


def test_demo_settings_preserves_defaults_and_legacy_model_pair() -> None:
    _store_or_skip()
    default = settings.normalize_demo_settings({})
    assert default == settings.DEMO_DEFAULT_SETTINGS
    legacy = settings.normalize_demo_settings(
        {"prompt_provider": "nvidia", "prompt_model": "ollama:gpt-oss:20b"}
    )
    assert (legacy["prompt_provider"], legacy["prompt_model"]) == ("ollama", "gpt-oss:20b")
    own_colon = settings.normalize_demo_settings(
        {"prompt_provider": "ollama", "prompt_model": "gpt-oss:20b"}
    )
    assert (own_colon["prompt_provider"], own_colon["prompt_model"]) == (
        "ollama",
        "gpt-oss:20b",
    )


def test_demo_settings_preserves_validation_and_ranges() -> None:
    _store_or_skip()
    cases = (
        ([], "must be an object"),
        ({"prompt_provider": " "}, "prompt provider is required"),
        ({"prompt_model": 1}, "prompt model is required"),
        ({"seed_phrase": 1}, "seed phrase must be a string"),
        ({"seed_phrase": " "}, "seed phrase is required"),
        ({"seed_phrase": "x" * 1001}, "seed phrase is too long"),
        ({"interval_seconds": "no"}, "interval must be an integer"),
        ({"interval_seconds": 0}, "interval must be between"),
        ({"interval_seconds": 3601}, "interval must be between"),
        ({"timeout_seconds": "no"}, "timeout must be an integer"),
        ({"timeout_seconds": 59}, "timeout must be between"),
        ({"timeout_seconds": 86401}, "timeout must be between"),
    )
    for value, message in cases:
        with pytest.raises(ValueError, match=message):
            settings.normalize_demo_settings(value)

    clean = settings.normalize_demo_settings(
        {
            "save_db": 1,
            "save_files": 0,
            "prompt_provider": " ollama ",
            "prompt_model": " model ",
            "seed_phrase": " phrase ",
            "interval_seconds": "45",
            "timeout_seconds": "7200",
        }
    )
    assert clean == {
        "save_db": True,
        "save_files": False,
        "prompt_provider": "ollama",
        "prompt_model": "model",
        "seed_phrase": "phrase",
        "interval_seconds": 45,
        "timeout_seconds": 7200,
    }


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


def test_demo_settings_preserves_read_write_fallbacks_and_exceptions() -> None:
    for row in (None, SimpleNamespace(demo_settings="broken"), SimpleNamespace(demo_settings="[]")):
        session = _Session(row)
        assert _build(session).get("u") == settings.DEMO_DEFAULT_SETTINGS

    missing = _Session(None)
    assert _build(missing).update("missing", {}) is None
    assert "commit" not in missing.events

    row = SimpleNamespace(demo_settings="{}")
    session = _Session(row)
    result = _build(session).update("u", {"seed_phrase": " 雪 ", "interval_seconds": 2})
    assert result["seed_phrase"] == "雪"
    assert json.loads(row.demo_settings) == result
    assert session.events == [("get", "user_accounts", "u"), "commit"]

    class BrokenSession(_Session):
        def get(self, _row_type: object, _key: object) -> object:
            raise RuntimeError("get failed")

    with pytest.raises(RuntimeError, match="get failed"):
        _build(BrokenSession(None)).get("u")
