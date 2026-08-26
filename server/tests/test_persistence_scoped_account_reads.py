"""Direct privacy-scope coverage for account readers."""

from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _reader_or_skip():
    reader = accounts.UserAccountReader
    if not hasattr(reader, "list_users_for_actor") or not hasattr(reader, "list_group_peers"):
        pytest.skip("scoped account reads are intentionally absent during fail-first")
    return reader


def test_accounts_owns_scoped_reads_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = accounts.UserAccountReader
    assert hasattr(reader, "list_users_for_actor"), "account owner must own actor-scoped lists"
    assert hasattr(reader, "list_group_peers"), "account owner must own same-group peers"

    for name in ("list_users_for_actor", "list_group_peers"):
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
    actor = {"id": "u", "permission_groups": ["users"], "group_id": "g"}

    assert db.list_users_for_actor(actor) == "sentinel"
    assert db.list_group_peers("u") == "sentinel"
    assert calls == [
        (dependencies, "list_users_for_actor", (actor,)),
        (dependencies, "list_group_peers", ("u",)),
    ]


def test_actor_scoped_list_preserves_roles_group_filter_order_and_early_return() -> None:
    reader_type = _reader_or_skip()
    alpha = SimpleNamespace(id="a", username="alpha", group_id="g")
    beta = SimpleNamespace(id="b", username="beta", group_id="g")

    class Query:
        def __init__(self, session: Session) -> None:
            self.session = session

        def outerjoin(self, *_args: object) -> Query:
            self.session.events.append("outerjoin-group")
            return self

        def filter(self, condition: object) -> Query:
            self.session.events.append(("filter-group", condition.right.value))
            return self

        def order_by(self, _clause: object) -> Query:
            self.session.events.append("order-username-asc")
            return self

        def all(self) -> list[tuple[object, str]]:
            self.session.events.append("all")
            return [(alpha, "Group"), (beta, "Group")]

    class Session:
        def __init__(self) -> None:
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, *_row_types: object) -> Query:
            self.events.append("query-account-group")
            return Query(self)

    opened: list[Session] = []

    def factory() -> Session:
        session = Session()
        opened.append(session)
        return session

    reader = reader_type(
        factory,
        lambda row, group_name=None: {"id": row.id, "group_name": group_name},
        lambda *_args: True,
        "dummy",
    )
    admin = {"permission_groups": ["admins"], "group_id": None}
    leader = {"permission_groups": ["leaders"], "group_id": "g"}
    user = {"permission_groups": ["users"], "group_id": "g"}
    groupless_leader = {"permission_groups": ["leaders"], "group_id": None}

    assert [item["id"] for item in reader.list_users_for_actor(admin)] == ["a", "b"]
    assert opened[-1].events == ["query-account-group", "outerjoin-group", "order-username-asc", "all"]
    assert [item["id"] for item in reader.list_users_for_actor(leader)] == ["a", "b"]
    assert opened[-1].events == [
        "query-account-group",
        "outerjoin-group",
        ("filter-group", "g"),
        "order-username-asc",
        "all",
    ]
    opened_count = len(opened)
    assert reader.list_users_for_actor(user) == []
    assert reader.list_users_for_actor(groupless_leader) == []
    assert len(opened) == opened_count


def test_group_peers_preserve_early_empty_scope_filter_order_and_projection() -> None:
    reader_type = _reader_or_skip()
    caller = SimpleNamespace(id="u", group_id="g")
    peers = [SimpleNamespace(id="a", username="alpha"), SimpleNamespace(id="b", username="beta")]

    class Query:
        def __init__(self, session: Session) -> None:
            self.session = session

        def filter(self, *conditions: object) -> Query:
            self.session.events.append(("filter", len(conditions)))
            return self

        def order_by(self, _clause: object) -> Query:
            self.session.events.append("order-username-asc")
            return self

        def all(self) -> list[object]:
            self.session.events.append("all")
            return peers

    class Session:
        def __init__(self, value: object | None) -> None:
            self.value = value
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _row_type: object, key: object) -> object | None:
            self.events.append(("get", key))
            return self.value

        def query(self, _row_type: object) -> Query:
            self.events.append("query-account")
            return Query(self)

    def reader_for(session: Session):
        return reader_type(lambda: session, lambda *_args: {}, lambda *_args: True, "dummy")

    missing = Session(None)
    assert reader_for(missing).list_group_peers("missing") == []
    assert missing.events == [("get", "missing")]

    groupless = Session(SimpleNamespace(id="u", group_id=None))
    assert reader_for(groupless).list_group_peers("u") == []
    assert groupless.events == [("get", "u")]

    present = Session(caller)
    assert reader_for(present).list_group_peers("u") == [
        {"id": "a", "username": "alpha"},
        {"id": "b", "username": "beta"},
    ]
    assert present.events == [("get", "u"), "query-account", ("filter", 2), "order-username-asc", "all"]


def test_scoped_reader_exceptions_propagate() -> None:
    reader_type = _reader_or_skip()

    class Session:
        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, *_args: object) -> object:
            raise RuntimeError("query failed")

    with pytest.raises(RuntimeError, match="query failed"):
        reader_type(Session, lambda *_args: {}, lambda *_args: True, "dummy").list_group_peers("u")
