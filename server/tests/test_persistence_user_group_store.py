"""Direct ownership and transaction coverage for user groups."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import importlib
import importlib.util
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db

groups = (
    importlib.import_module("inku_server.persistence.groups")
    if importlib.util.find_spec("inku_server.persistence.groups") is not None
    else None
)


def _store_or_skip():
    if groups is None:
        pytest.skip("production groups module is intentionally absent during fail-first")
    store = getattr(groups, "UserGroupStore", None)
    if store is None:
        pytest.skip("production user-group owner is intentionally absent during fail-first")
    return store


def test_persistence_groups_owns_store_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert groups is not None, "persistence.groups must own user groups"
    store = getattr(groups, "UserGroupStore", None)
    assert store is not None, "UserGroupStore must own user groups"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None, None, None).session_factory = None

    projected = groups.group_to_dict(SimpleNamespace(id="g", name="Group", at=7))
    assert projected == {"id": "g", "name": "Group", "at": 7}

    for name in (
        "_group_to_dict",
        "list_user_groups",
        "add_user_group",
        "update_user_group",
        "delete_user_group",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[tuple[object, ...], str, tuple[object, ...]]] = []

    class RecordingStore:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def __getattr__(self, name: str):
            def call(*args: object):
                calls.append((self.dependencies, name, args))
                return "sentinel"

            return call

    monkeypatch.setattr(db._groups, "UserGroupStore", RecordingStore)
    monkeypatch.setattr(db._groups, "group_to_dict", lambda _row: "sentinel-projection")
    session_factory = object()
    uuid_fn = object()
    now_fn = object()
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    monkeypatch.setattr(db.uuid, "uuid4", uuid_fn)
    monkeypatch.setattr(db, "_now_ms", now_fn)
    dependencies = (session_factory, uuid_fn, now_fn)

    assert db._group_to_dict("row") == "sentinel-projection"
    assert db.list_user_groups() == "sentinel"
    assert db.add_user_group(" name ") == "sentinel"
    assert db.update_user_group("g", " name ") == "sentinel"
    assert db.delete_user_group("g") == "sentinel"
    assert calls == [
        (dependencies, "list_user_groups", ()),
        (dependencies, "add_user_group", (" name ",)),
        (dependencies, "update_user_group", ("g", " name ")),
        (dependencies, "delete_user_group", ("g",)),
    ]


def test_list_and_add_preserve_order_validation_projection_and_transaction() -> None:
    store_type = _store_or_skip()

    def fail_if_opened() -> None:
        raise AssertionError("invalid group name must not open a session")

    validating = store_type(fail_if_opened, lambda: "uuid", lambda: 10)
    for name in ("", "   "):
        with pytest.raises(ValueError, match="group name is required"):
            validating.add_user_group(name)

    rows = [
        SimpleNamespace(id="a", name="Alpha", at=1),
        SimpleNamespace(id="b", name="Beta", at=2),
    ]

    class Query:
        def __init__(self, events: list[object]) -> None:
            self.events = events

        def order_by(self, _clause: object) -> Query:
            self.events.append("order-name-asc")
            return self

        def all(self) -> list[object]:
            self.events.append("all")
            return rows

    class Session:
        def __init__(self) -> None:
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            self.events.append("query")
            return Query(self.events)

        def add(self, row: object) -> None:
            self.events.append(("add", row))

        def commit(self) -> None:
            self.events.append("commit")

        def refresh(self, row: object) -> None:
            self.events.append(("refresh", row))

    listing = Session()
    store = store_type(lambda: listing, lambda: "uuid", lambda: 10)
    assert store.list_user_groups() == [
        {"id": "a", "name": "Alpha", "at": 1},
        {"id": "b", "name": "Beta", "at": 2},
    ]
    assert listing.events == ["query", "order-name-asc", "all"]

    adding = Session()
    added = store_type(lambda: adding, lambda: "uuid-1", lambda: 20).add_user_group(" Group ")
    row = adding.events[0][1]
    assert (row.id, row.name, row.at) == ("uuid-1", "Group", 20)
    assert adding.events == [("add", row), "commit", ("refresh", row)]
    assert added == {"id": "uuid-1", "name": "Group", "at": 20}


def test_update_preserves_validation_missing_and_commit_refresh() -> None:
    store_type = _store_or_skip()

    def fail_if_opened() -> None:
        raise AssertionError("invalid group name must not open a session")

    with pytest.raises(ValueError, match="group name is required"):
        store_type(fail_if_opened, lambda: "uuid", lambda: 10).update_user_group("g", " ")

    class Session:
        def __init__(self, row: object | None) -> None:
            self.row = row
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _row_type: object, key: object) -> object | None:
            self.events.append(("get", key))
            return self.row

        def commit(self) -> None:
            self.events.append("commit")

        def refresh(self, row: object) -> None:
            self.events.append(("refresh", row))

    missing = Session(None)
    store = store_type(lambda: missing, lambda: "uuid", lambda: 30)
    assert store.update_user_group("missing", "Name") is None
    assert missing.events == [("get", "missing")]

    row = SimpleNamespace(id="g", name="Old", at=1)
    present = Session(row)
    updated = store_type(lambda: present, lambda: "uuid", lambda: 30).update_user_group(
        "g", " New "
    )
    assert (row.name, row.at) == ("New", 30)
    assert present.events == [("get", "g"), "commit", ("refresh", row)]
    assert updated == {"id": "g", "name": "New", "at": 30}


def test_delete_preserves_in_use_missing_acl_cleanup_and_commit_order() -> None:
    store_type = _store_or_skip()
    row = SimpleNamespace(id="g", name="Group", at=1)

    class Query:
        def __init__(self, session: Session, kind: str) -> None:
            self.session = session
            self.kind = kind

        def filter(self, *_conditions: object) -> Query:
            self.session.events.append(("filter", self.kind))
            return self

        def first(self) -> object | None:
            self.session.events.append(("first", self.kind))
            return self.session.account

        def delete(self, *, synchronize_session: bool) -> int:
            self.session.events.append(("bulk-delete", self.kind, synchronize_session))
            return 1

    class Session:
        def __init__(self, account: object | None, group: object | None) -> None:
            self.account = account
            self.group = group
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, row_type: object) -> Query:
            kind = getattr(row_type, "__tablename__", str(row_type))
            self.events.append(("query", kind))
            return Query(self, kind)

        def get(self, _row_type: object, key: object) -> object | None:
            self.events.append(("get", key))
            return self.group

        def delete(self, value: object) -> None:
            self.events.append(("delete", value))

        def commit(self) -> None:
            self.events.append("commit")

    in_use = Session(object(), row)
    with pytest.raises(ValueError, match="group has users"):
        store_type(lambda: in_use, lambda: "uuid", lambda: 10).delete_user_group("g")
    assert all(event[0] != "get" for event in in_use.events if isinstance(event, tuple))

    missing = Session(None, None)
    assert store_type(lambda: missing, lambda: "uuid", lambda: 10).delete_user_group("g") is False
    assert not any(event[0] == "bulk-delete" for event in missing.events if isinstance(event, tuple))

    present = Session(None, row)
    assert store_type(lambda: present, lambda: "uuid", lambda: 10).delete_user_group("g") is True
    assert present.events[-3:] == [
        ("bulk-delete", "history_acl", False),
        ("delete", row),
        "commit",
    ]


def test_store_exceptions_propagate() -> None:
    store_type = _store_or_skip()

    class Query:
        def order_by(self, _clause: object) -> Query:
            return self

        def all(self) -> list[object]:
            raise RuntimeError("query failed")

    class Session:
        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            return Query()

    with pytest.raises(RuntimeError, match="query failed"):
        store_type(Session, lambda: "uuid", lambda: 10).list_user_groups()
