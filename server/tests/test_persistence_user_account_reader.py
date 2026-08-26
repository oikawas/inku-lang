"""Direct ownership and authentication coverage for user-account reads."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import importlib
import importlib.util
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db


accounts = (
    importlib.import_module("inku_server.persistence.accounts")
    if importlib.util.find_spec("inku_server.persistence.accounts") is not None
    else None
)


def _reader_or_skip():
    if accounts is None:
        pytest.skip("production accounts module is intentionally absent during fail-first")
    reader = getattr(accounts, "UserAccountReader", None)
    if reader is None:
        pytest.skip("production user-account owner is intentionally absent during fail-first")
    return reader


def test_persistence_accounts_owns_reader_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert accounts is not None, "persistence.accounts must own user-account reads"
    reader = getattr(accounts, "UserAccountReader", None)
    assert reader is not None, "UserAccountReader must own user-account reads"
    assert is_dataclass(reader) and reader.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        reader(None, None, None, "dummy").session_factory = None

    for name in ("_account_reader", "list_users", "get_user", "authenticate_user"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[tuple[object, ...], str, tuple[object, ...]]] = []

    class RecordingReader:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def __getattr__(self, name: str):
            def call(*args: object):
                calls.append((self.dependencies, name, args))
                return "sentinel"

            return call

    monkeypatch.setattr(db._accounts, "UserAccountReader", RecordingReader)
    session_factory = object()
    projector = object()
    verifier = object()
    dummy_hash = "dummy-hash"
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    monkeypatch.setattr(db, "_user_to_dict", projector)
    monkeypatch.setattr(db, "verify_password", verifier)
    monkeypatch.setattr(db, "_DUMMY_PASSWORD_HASH", dummy_hash)
    dependencies = (session_factory, projector, verifier, dummy_hash)

    assert isinstance(db._account_reader(), RecordingReader)
    assert db.list_users() == "sentinel"
    assert db.get_user("u") == "sentinel"
    assert db.authenticate_user(" name ", "secret") == "sentinel"
    assert calls == [
        (dependencies, "list_users", ()),
        (dependencies, "get_user", ("u",)),
        (dependencies, "authenticate_user", (" name ", "secret")),
    ]


def test_list_and_get_preserve_join_order_group_lookup_and_projection() -> None:
    reader_type = _reader_or_skip()
    first = SimpleNamespace(id="u1", username="alpha", group_id="g1")
    second = SimpleNamespace(id="u2", username="beta", group_id=None)
    group = SimpleNamespace(id="g1", name="Group")

    class Query:
        def __init__(self, session: Session) -> None:
            self.session = session

        def outerjoin(self, *_args: object) -> Query:
            self.session.events.append("outerjoin-group")
            return self

        def order_by(self, _clause: object) -> Query:
            self.session.events.append("order-username-asc")
            return self

        def all(self) -> list[tuple[object, str | None]]:
            self.session.events.append("all")
            return [(first, "Group"), (second, None)]

    class Session:
        def __init__(self, account: object | None = None) -> None:
            self.account = account
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, *_row_types: object) -> Query:
            self.events.append("query-account-group")
            return Query(self)

        def get(self, row_type: object, key: object) -> object | None:
            table = getattr(row_type, "__tablename__", "unknown")
            self.events.append(("get", table, key))
            if table == "user_accounts":
                return self.account
            return group

    projections: list[tuple[str, str | None]] = []

    def project(row: object, group_name: str | None = None) -> dict:
        projections.append((row.id, group_name))
        return {"id": row.id, "group_name": group_name}

    listing = Session()
    reader = reader_type(lambda: listing, project, lambda *_args: True, "dummy")
    assert reader.list_users() == [
        {"id": "u1", "group_name": "Group"},
        {"id": "u2", "group_name": None},
    ]
    assert listing.events == ["query-account-group", "outerjoin-group", "order-username-asc", "all"]

    missing = Session(None)
    assert reader_type(lambda: missing, project, lambda *_args: True, "dummy").get_user("missing") is None
    assert missing.events == [("get", "user_accounts", "missing")]

    present = Session(first)
    assert reader_type(lambda: present, project, lambda *_args: True, "dummy").get_user("u1") == {
        "id": "u1",
        "group_name": "Group",
    }
    assert present.events == [("get", "user_accounts", "u1"), ("get", "user_groups", "g1")]
    assert projections == [("u1", "Group"), ("u2", None), ("u1", "Group")]


def test_authentication_preserves_strip_dummy_hash_and_success_projection() -> None:
    reader_type = _reader_or_skip()
    row = SimpleNamespace(id="u", username="name", password_hash="real-hash", group_id="g")
    group = SimpleNamespace(name="Group")

    class Query:
        def __init__(self, session: Session) -> None:
            self.session = session

        def filter(self, condition: object) -> Query:
            self.session.username = condition.right.value
            return self

        def first(self) -> object | None:
            return self.session.row

    class Session:
        def __init__(self, value: object | None) -> None:
            self.row = value
            self.username: str | None = None

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            return Query(self)

        def get(self, _row_type: object, _key: object) -> object:
            return group

    sessions = [Session(None), Session(row), Session(row)]
    verifications: list[tuple[str, str]] = []
    results = iter((True, False, True))

    def verify(password: str, stored_hash: str) -> bool:
        verifications.append((password, stored_hash))
        return next(results)

    reader = reader_type(
        lambda: sessions.pop(0),
        lambda value, group_name=None: {"id": value.id, "group_name": group_name},
        verify,
        "dummy-hash",
    )
    assert reader.authenticate_user(" missing ", "first") is None
    assert reader.authenticate_user(" name ", "second") is None
    assert reader.authenticate_user(" name ", "third") == {"id": "u", "group_name": "Group"}
    assert verifications == [
        ("first", "dummy-hash"),
        ("second", "real-hash"),
        ("third", "real-hash"),
    ]


def test_reader_exceptions_propagate() -> None:
    reader_type = _reader_or_skip()

    class Session:
        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, *_args: object) -> object:
            raise RuntimeError("query failed")

    with pytest.raises(RuntimeError, match="query failed"):
        reader_type(Session, lambda *_args: {}, lambda *_args: True, "dummy").list_users()
