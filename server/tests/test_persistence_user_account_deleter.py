"""Direct authority and cleanup coverage for account deletion."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _deleter_or_skip():
    deleter = getattr(accounts, "UserAccountDeleter", None)
    if deleter is None:
        pytest.skip("account deleter is intentionally absent during fail-first")
    return deleter


def test_accounts_owns_deleter_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    deleter = getattr(accounts, "UserAccountDeleter", None)
    assert deleter is not None, "persistence.accounts must own account deletion"
    assert is_dataclass(deleter) and deleter.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        deleter(*([None] * 6)).session_factory = None

    for name in ("_account_deleter", "delete_user"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert inspect.signature(db.delete_user).parameters["cascade"].default is False
    assert inspect.signature(db.delete_user).parameters["actor"].default is None

    calls: list[tuple[tuple[object, ...], tuple[object, ...], dict[str, object]]] = []

    class RecordingDeleter:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def delete_user(self, *args: object, **kwargs: object) -> bool:
            calls.append((self.dependencies, args, kwargs))
            return True

    monkeypatch.setattr(db._accounts, "UserAccountDeleter", RecordingDeleter)
    dependencies = tuple(object() for _ in range(6))
    monkeypatch.setattr(db, "SessionLocal", dependencies[0])
    monkeypatch.setattr(db, "has_permission_group", dependencies[1])
    monkeypatch.setattr(db, "_holds_no_elevated_group", dependencies[2])
    monkeypatch.setattr(db, "_owner_actor", dependencies[3])
    monkeypatch.setattr(db, "_owned_by", dependencies[4])
    monkeypatch.setattr(db, "_delete_acl_for_histories", dependencies[5])

    assert db.delete_user("u", cascade=True, actor={"id": "a"}) is True
    assert calls == [(dependencies, ("u",), {"cascade": True, "actor": {"id": "a"}})]


def test_deleter_preserves_actor_scope_and_missing_target() -> None:
    deleter_type = _deleter_or_skip()
    row = SimpleNamespace(id="u")

    class Query:
        def __init__(self, session: Session) -> None:
            self.session = session

        def filter(self, *conditions: object) -> Query:
            self.session.events.append(("filter", len(conditions)))
            return self

        def first(self) -> object | None:
            self.session.events.append("first")
            return self.session.row

    class Session:
        def __init__(self, value: object | None) -> None:
            self.row = value
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            self.events.append("query")
            return Query(self)

    def has_group(actor: dict, name: str) -> bool:
        return name in actor.get("permission_groups", [])

    opened: list[Session] = []

    def factory(value: object | None = row):
        def open_session() -> Session:
            session = Session(value)
            opened.append(session)
            return session

        return open_session

    def build(session_factory):
        return deleter_type(
            session_factory,
            has_group,
            lambda session: session.events.append("elevated-filter") or object(),
            lambda user_id: {"id": user_id},
            lambda *_args: object(),
            lambda *_args: None,
        )

    user = {"permission_groups": ["users"], "group_id": "g"}
    groupless_leader = {"permission_groups": ["leaders"], "group_id": None}
    assert build(factory()).delete_user("u", actor=user) is False
    assert opened[-1].events == ["query", ("filter", 1)]
    assert build(factory()).delete_user("u", actor=groupless_leader) is False
    assert opened[-1].events == ["query", ("filter", 1)]

    missing = build(factory(None))
    assert missing.delete_user("missing") is False
    assert opened[-1].events == ["query", ("filter", 1), "first"]


def test_deleter_preserves_history_gate_and_complete_cleanup_order() -> None:
    deleter_type = _deleter_or_skip()
    row = SimpleNamespace(id="u")

    def kind_of(target: object) -> str:
        owner = getattr(target, "class_", None)
        if owner is not None:
            return f"{owner.__tablename__}.id"
        return getattr(target, "__tablename__", str(target))

    class Query:
        def __init__(self, session: Session, kind: str) -> None:
            self.session = session
            self.kind = kind

        def filter(self, *_conditions: object) -> Query:
            self.session.events.append(("filter", self.kind))
            return self

        def first(self) -> object | None:
            self.session.events.append(("first", self.kind))
            if self.kind == "user_accounts":
                return row
            if self.kind == "history":
                return self.session.history
            return None

        def delete(self, **kwargs: object) -> int:
            self.session.events.append(("bulk-delete", self.kind, kwargs))
            return 1

        def __iter__(self):
            self.session.events.append(("iterate", self.kind))
            return iter([("h1",), ("h2",)])

    class Session:
        def __init__(self, history: object | None = None) -> None:
            self.history = history
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, target: object) -> Query:
            kind = kind_of(target)
            self.events.append(("query", kind))
            return Query(self, kind)

        def delete(self, value: object) -> None:
            self.events.append(("delete-row", value))

        def commit(self) -> None:
            self.events.append("commit")

    owner_calls: list[str] = []

    def owner_actor(user_id: str) -> dict:
        owner_calls.append(user_id)
        return {"id": user_id}

    def owned_by(actor: dict, column: object) -> tuple[str, str, str]:
        return ("owned", actor["id"], str(column))

    acl_calls: list[list[str]] = []

    def build(session: Session):
        return deleter_type(
            lambda: session,
            lambda actor, name: name in actor.get("permission_groups", []),
            lambda _session: object(),
            owner_actor,
            owned_by,
            lambda active, ids: acl_calls.append(ids) if active is session else None,
        )

    blocked = Session(history=object())
    with pytest.raises(ValueError, match="user has history"):
        build(blocked).delete_user("u")
    assert "commit" not in blocked.events

    cascade = Session()
    assert build(cascade).delete_user("u", cascade=True) is True
    assert owner_calls[-1] == "u"
    assert acl_calls == [["h1", "h2"]]
    deleted_kinds = [event[1] for event in cascade.events if event[0] == "bulk-delete"]
    assert deleted_kinds == [
        "history",
        "history_acl",
        "okugaki",
        "user_sessions",
        "external_identities",
        "unread_words",
        "lineage_edges",
        "lineage_nodes",
        "user_permission_groups",
    ]
    history_acl_delete = next(event for event in cascade.events if event[:2] == ("bulk-delete", "history_acl"))
    assert history_acl_delete[2] == {"synchronize_session": False}
    assert cascade.events[-2:] == [("delete-row", row), "commit"]


def test_deleter_exceptions_propagate() -> None:
    deleter_type = _deleter_or_skip()

    class Session:
        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, *_args: object) -> object:
            raise RuntimeError("query failed")

    with pytest.raises(RuntimeError, match="query failed"):
        deleter_type(Session, lambda *_args: False, lambda _session: object(),
                     lambda value: {"id": value}, lambda *_args: object(),
                     lambda *_args: None).delete_user("u")
