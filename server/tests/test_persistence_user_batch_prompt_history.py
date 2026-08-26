"""Direct authority and transaction coverage for persisted batch prompt history."""

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
    store = getattr(settings, "UserBatchPromptHistoryStore", None)
    if store is None:
        pytest.skip("batch prompt history store is intentionally absent during fail-first")
    return store


def test_settings_owns_batch_prompt_history_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "UserBatchPromptHistoryStore", None)
    assert store is not None, "persistence.settings must own batch prompt history"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).session_factory = None

    for name in (
        "_normalize_batch_prompt_history",
        "_user_batch_prompt_history_store",
        "get_user_batch_prompt_history",
        "update_user_batch_prompt_history",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    assert db._BATCH_PROMPT_HISTORY_LIMIT == settings.BATCH_PROMPT_HISTORY_LIMIT
    assert db._BATCH_PROMPT_HISTORY_MAX_TEXT == settings.BATCH_PROMPT_HISTORY_MAX_TEXT

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
    monkeypatch.setattr(db._settings, "UserBatchPromptHistoryStore", RecordingStore)
    monkeypatch.setattr(db, "SessionLocal", dependency)

    assert db.get_user_batch_prompt_history("u") == "get-sentinel"
    assert db.update_user_batch_prompt_history("u", ["one"]) == "update-sentinel"
    assert calls == [
        ("get", dependency, ("u",)),
        ("update", dependency, ("u", ["one"])),
    ]


def test_batch_prompt_history_preserves_normalization_and_limits() -> None:
    _store_or_skip()
    assert settings.normalize_batch_prompt_history(
        ["  one\r\n two  ", "one\n two", "", " three "]
    ) == ["one\n two", "three"]
    assert len(settings.normalize_batch_prompt_history([str(i) for i in range(60)])) == 50
    with pytest.raises(ValueError, match="must contain strings"):
        settings.normalize_batch_prompt_history(["one", 2])
    with pytest.raises(ValueError, match="item is too long"):
        settings.normalize_batch_prompt_history(["x" * 20_001])


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


def test_batch_prompt_history_preserves_read_fallbacks() -> None:
    missing = _Session(None)
    assert _build(missing).get("missing") == []
    assert missing.events == [("get", "user_accounts", "missing")]

    for raw in ("broken", "{}", '["ok", 2]'):
        session = _Session(SimpleNamespace(batch_prompt_history=raw))
        assert _build(session).get("u") == []

    session = _Session(SimpleNamespace(batch_prompt_history='["  one  ", "one", "two"]'))
    assert _build(session).get("u") == ["one", "two"]


def test_batch_prompt_history_preserves_update_transaction_and_exceptions() -> None:
    missing = _Session(None)
    assert _build(missing).update("missing", ["one"]) is None
    assert "commit" not in missing.events

    row = SimpleNamespace(batch_prompt_history="[]")
    session = _Session(row)
    assert _build(session).update("u", ["  一  ", "二"]) == ["一", "二"]
    assert json.loads(row.batch_prompt_history) == ["一", "二"]
    assert session.events == [("get", "user_accounts", "u"), "commit"]

    class BrokenSession(_Session):
        def get(self, _row_type: object, _key: object) -> object:
            raise RuntimeError("get failed")

    with pytest.raises(RuntimeError, match="get failed"):
        _build(BrokenSession(None)).update("u", ["one"])
