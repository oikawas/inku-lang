"""Direct authority and transaction coverage for atomic generation counts."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _counter_or_skip():
    counter = getattr(accounts, "UserGenerationCounter", None)
    if counter is None:
        pytest.skip("generation counter is intentionally absent during fail-first")
    return counter


def test_accounts_owns_generation_counter_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = getattr(accounts, "UserGenerationCounter", None)
    assert counter is not None, "persistence.accounts must own atomic generation counts"
    assert is_dataclass(counter) and counter.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        counter(None).session_factory = None

    for name in ("_user_generation_counter", "increment_user_generation_count"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert inspect.signature(db.increment_user_generation_count).parameters["amount"].default == 1

    calls: list[tuple[tuple[object, ...], tuple[object, ...], dict[str, object]]] = []

    class RecordingCounter:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def increment_user_generation_count(self, *args: object, **kwargs: object) -> int:
            calls.append((self.dependencies, args, kwargs))
            return 7

    dependency = object()
    monkeypatch.setattr(db._accounts, "UserGenerationCounter", RecordingCounter)
    monkeypatch.setattr(db, "SessionLocal", dependency)
    assert db.increment_user_generation_count("u", 3) == 7
    assert calls == [((dependency,), ("u",), {"amount": 3})]


class _Session:
    def __init__(self, *, rowcount: int = 1, row: object | None = None) -> None:
        self.result = SimpleNamespace(rowcount=rowcount)
        self.row = row
        self.events: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: object, params: dict[str, object]) -> object:
        self.events.append(("execute", " ".join(str(statement).split()), params))
        return self.result

    def rollback(self) -> None:
        self.events.append("rollback")

    def commit(self) -> None:
        self.events.append("commit")

    def get(self, row_type: object, key: object) -> object | None:
        self.events.append(("get", getattr(row_type, "__tablename__", "unknown"), key))
        return self.row


def test_generation_counter_rejects_nonpositive_amount_before_opening_session() -> None:
    counter_type = _counter_or_skip()
    opened = False

    def factory() -> _Session:
        nonlocal opened
        opened = True
        return _Session()

    counter = counter_type(factory)
    for amount in (0, -1):
        with pytest.raises(ValueError, match="amount must be positive"):
            counter.increment_user_generation_count("u", amount)
    assert not opened


def test_generation_counter_preserves_atomic_sql_and_transaction_results() -> None:
    counter_type = _counter_or_skip()
    missing = _Session(rowcount=0)
    assert counter_type(lambda: missing).increment_user_generation_count("missing", 2) is None
    assert missing.events[-1] == "rollback"
    assert "commit" not in missing.events

    row = SimpleNamespace(image_generation_count=9)
    session = _Session(row=row)
    assert counter_type(lambda: session).increment_user_generation_count("u", 3) == 9
    statement = session.events[0]
    assert statement[0] == "execute"
    assert "SET image_generation_count = COALESCE(image_generation_count, 0) + :amount" in statement[1]
    assert "WHERE id = :user_id" in statement[1]
    assert statement[2] == {"amount": 3, "user_id": "u"}
    assert session.events[1:] == ["commit", ("get", "user_accounts", "u")]

    vanished = _Session(row=None)
    assert counter_type(lambda: vanished).increment_user_generation_count("u") is None
    zero = _Session(row=SimpleNamespace(image_generation_count=None))
    assert counter_type(lambda: zero).increment_user_generation_count("u") == 0


def test_generation_counter_propagates_execute_errors() -> None:
    counter_type = _counter_or_skip()

    class BrokenSession(_Session):
        def execute(self, _statement: object, _params: dict[str, object]) -> object:
            raise RuntimeError("execute failed")

    with pytest.raises(RuntimeError, match="execute failed"):
        counter_type(BrokenSession).increment_user_generation_count("u")
