"""Direct ownership coverage for single-user automatic-login resolution."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import accounts
from inku_server.persistence.schema import UserAccountRow


def _resolver_or_skip():
    resolver = getattr(accounts, "SingleUserAccountResolver", None)
    if resolver is None:
        pytest.skip("single-user account resolver is intentionally absent during fail-first")
    return resolver


class _PinStore:
    def __init__(self, pinned=None):
        self.pinned = pinned
        self.updates = []

    def get(self):
        return self.pinned

    def update(self, user_id):
        self.updates.append(user_id)


class _Query:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Session:
    def __init__(self, account=None):
        self.account = account
        self.queries = []

    def query(self, model):
        self.queries.append(model)
        assert model is UserAccountRow
        return _Query(self.account)


class _OwnedSession:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *_args):
        return False


def _resolver(*, pin_store=None, get_user=None, session=None, oldest=None, create=None):
    resolver_type = _resolver_or_skip()
    return resolver_type(
        pin_store or _PinStore(),
        get_user or (lambda _user_id: None),
        (lambda: _OwnedSession(session or _Session())),
        oldest or (lambda _session: None),
        create or (lambda: None),
    )


def test_accounts_owns_single_user_account_resolution_and_db_delegates(monkeypatch) -> None:
    resolver = getattr(accounts, "SingleUserAccountResolver", None)
    assert resolver is not None
    assert is_dataclass(resolver) and resolver.__dataclass_params__.frozen
    instance = _resolver()
    with pytest.raises(FrozenInstanceError):
        instance.get_user_fn = None
    parsed = ast.parse(inspect.getsource(db.single_user_account)).body[0]
    assert isinstance(parsed.body[-1], ast.Return)

    class Delegate:
        def resolve(self):
            return {"id": "delegated"}

    monkeypatch.setattr(db, "_single_user_account_resolver", lambda: Delegate())
    assert db.single_user_account() == {"id": "delegated"}


def test_resolver_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _resolver_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    markers = [object() for _ in range(5)]
    monkeypatch.setattr(db._accounts, "SingleUserAccountResolver", Recording)
    monkeypatch.setattr(db, "_single_user_pin_store", lambda: markers[0])
    monkeypatch.setattr(db, "get_user", markers[1])
    monkeypatch.setattr(db, "SessionLocal", markers[2])
    monkeypatch.setattr(db, "_oldest_admin_id", markers[3])
    monkeypatch.setattr(db, "_create_single_user_account", markers[4])
    db._single_user_account_resolver()
    assert received == [tuple(markers)]


def test_valid_pin_wins_without_fallback_or_write() -> None:
    pin_store = _PinStore("pinned")
    calls = []
    resolver = _resolver(
        pin_store=pin_store,
        get_user=lambda user_id: {"id": user_id},
        oldest=lambda _session: calls.append("oldest"),
        create=lambda: calls.append("create"),
    )
    assert resolver.resolve() == {"id": "pinned"}
    assert calls == []
    assert pin_store.updates == []


def test_stale_pin_falls_back_to_oldest_admin_and_repins() -> None:
    pin_store = _PinStore("stale")
    seen = []

    def get_user(user_id):
        seen.append(user_id)
        return None if user_id == "stale" else {"id": user_id}

    resolver = _resolver(
        pin_store=pin_store,
        get_user=get_user,
        oldest=lambda _session: "admin",
        create=lambda: pytest.fail("existing admin must not create an account"),
    )
    assert resolver.resolve() == {"id": "admin"}
    assert seen == ["stale", "admin"]
    assert pin_store.updates == ["admin"]


def test_accounts_without_an_admin_refuse_instead_of_creating() -> None:
    session = _Session(account=object())
    resolver = _resolver(
        session=session,
        create=lambda: pytest.fail("populated database must not create an account"),
    )
    assert resolver.resolve() is None
    assert session.queries == [UserAccountRow]


def test_empty_database_creates_resolves_and_pins_only_a_real_account() -> None:
    for created_id, projected, expected_updates in (
        (None, None, []),
        ("created", None, []),
        ("created", {"id": "created"}, ["created"]),
    ):
        pin_store = _PinStore()
        resolver = _resolver(
            pin_store=pin_store,
            session=_Session(account=None),
            get_user=lambda _user_id, value=projected: value,
            create=lambda value=created_id: value,
        )
        assert resolver.resolve() == projected
        assert pin_store.updates == expected_updates
