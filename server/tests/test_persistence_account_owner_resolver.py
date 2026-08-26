"""Direct ownership coverage for administrator and history-owner lookup."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts
from inku_server.persistence.schema import UserAccountRow


def _resolver_or_skip():
    resolver = getattr(accounts, "AccountOwnerResolver", None)
    if resolver is None:
        pytest.skip("account owner resolver is intentionally absent during fail-first")
    return resolver


class _Query:
    def __init__(self, row, operations):
        self.row = row
        self.operations = operations

    def join(self, *_args):
        self.operations.append("join")
        return self

    def filter(self, *_args):
        self.operations.append("filter")
        return self

    def order_by(self, *_args):
        self.operations.append("order_by")
        return self

    def first(self):
        self.operations.append("first")
        return self.row


class _Session:
    def __init__(self, rows):
        self.rows = list(rows)
        self.operations = []
        self.models = []

    def query(self, model):
        self.models.append(model)
        return _Query(self.rows.pop(0), self.operations)


class _OwnedSession:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *_args):
        return False


def test_accounts_owns_account_owner_resolution_and_db_delegates(monkeypatch) -> None:
    resolver = getattr(accounts, "AccountOwnerResolver", None)
    assert resolver is not None
    assert is_dataclass(resolver) and resolver.__dataclass_params__.frozen
    instance = resolver(None)
    with pytest.raises(FrozenInstanceError):
        instance.session_factory = None
    for function in (db._oldest_admin_id, db._history_owner_user_id):
        parsed = ast.parse(inspect.getsource(function)).body[0]
        assert isinstance(parsed.body[-1], ast.Return)

    calls = []

    class Delegate:
        def oldest_admin_id(self, session):
            calls.append(("admin", session))
            return "admin-id"

        def history_owner_user_id(self, session):
            calls.append(("history", session))
            return "history-id"

    delegate = Delegate()
    monkeypatch.setattr(db, "_account_owner_resolver", lambda: delegate)
    marker = object()
    assert db._oldest_admin_id(marker) == "admin-id"
    assert db._history_owner_user_id(marker) == "history-id"
    assert calls == [("admin", marker), ("history", marker)]


def test_account_owner_factory_receives_runtime_session_factory(monkeypatch) -> None:
    _resolver_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    marker = object()
    monkeypatch.setattr(db._accounts, "AccountOwnerResolver", Recording)
    monkeypatch.setattr(db, "SessionLocal", marker)
    db._account_owner_resolver()
    assert received == [(marker,)]


def test_oldest_admin_preserves_membership_query_and_none() -> None:
    resolver = _resolver_or_skip()(None)
    session = _Session([SimpleNamespace(id="admin-id")])
    assert resolver.oldest_admin_id(session) == "admin-id"
    assert session.models == [UserAccountRow]
    assert session.operations == ["join", "join", "filter", "order_by", "first"]

    empty = _Session([None])
    assert resolver.oldest_admin_id(empty) is None


def test_history_owner_preserves_admin_fallback_and_owned_session() -> None:
    resolver_type = _resolver_or_skip()
    borrowed = _Session([None, SimpleNamespace(id="oldest-user")])
    resolver = resolver_type(lambda: pytest.fail("borrowed session must be reused"))
    assert resolver.history_owner_user_id(borrowed) == "oldest-user"
    assert borrowed.models == [UserAccountRow, UserAccountRow]
    assert borrowed.operations[-2:] == ["order_by", "first"]

    owned_session = _Session([SimpleNamespace(id="admin-id")])
    owned = resolver_type(lambda: _OwnedSession(owned_session))
    assert owned.history_owner_user_id() == "admin-id"

    empty = _Session([None, None])
    assert resolver_type(lambda: _OwnedSession(empty)).history_owner_user_id() is None
