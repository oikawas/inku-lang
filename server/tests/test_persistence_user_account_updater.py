"""Direct authority and transaction coverage for managed account updates."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _updater_or_skip():
    updater = getattr(accounts, "UserAccountUpdater", None)
    if updater is None:
        pytest.skip("account updater is intentionally absent during fail-first")
    return updater


def test_accounts_owns_updater_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    updater = getattr(accounts, "UserAccountUpdater", None)
    assert updater is not None, "persistence.accounts must own managed account updates"
    assert is_dataclass(updater) and updater.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        updater(*([None] * 7)).session_factory = None

    for name in ("_account_updater", "update_user"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert inspect.signature(db.update_user).parameters["group_id"].default is db._UNSET

    calls: list[tuple[tuple[object, ...], tuple[object, ...], dict[str, object]]] = []

    class RecordingUpdater:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def update_user(self, *args: object, **kwargs: object) -> str:
            calls.append((self.dependencies, args, kwargs))
            return "sentinel"

    monkeypatch.setattr(db._accounts, "UserAccountUpdater", RecordingUpdater)
    dependencies = tuple(object() for _ in range(6)) + (db._UNSET,)
    monkeypatch.setattr(db, "SessionLocal", dependencies[0])
    monkeypatch.setattr(db, "_hash_password", dependencies[1])
    monkeypatch.setattr(db, "_set_permission_groups", dependencies[2])
    monkeypatch.setattr(db, "has_permission_group", dependencies[3])
    monkeypatch.setattr(db, "_holds_no_elevated_group", dependencies[4])
    monkeypatch.setattr(db, "_user_to_dict", dependencies[5])

    assert db.update_user("u", email=" mail ") == "sentinel"
    assert calls == [
        (
            dependencies,
            ("u",),
            {
                "username": None,
                "email": " mail ",
                "password": None,
                "permission_groups": None,
                "group_id": dependencies[6],
                "actor": None,
            },
        )
    ]


def test_updater_preserves_actor_scope_and_missing_target() -> None:
    updater_type = _updater_or_skip()
    row = SimpleNamespace(id="u", group_id="g", username="old", email="old@example.test")

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

        def get(self, _row_type: object, _key: object) -> object:
            return SimpleNamespace(name="Group")

        def commit(self) -> None:
            self.events.append("commit")

        def refresh(self, _row: object) -> None:
            self.events.append("refresh")

    opened: list[Session] = []

    def factory() -> Session:
        session = Session(row)
        opened.append(session)
        return session

    def has_group(actor: dict, name: str) -> bool:
        return name in actor.get("permission_groups", [])

    unset = object()
    updater = updater_type(
        factory,
        lambda value: f"hash:{value}",
        lambda *_args: [],
        has_group,
        lambda session: session.events.append("elevated-filter") or object(),
        lambda value, group_name=None: {"id": value.id, "group_name": group_name},
        unset,
    )
    user = {"permission_groups": ["users"], "group_id": "g"}
    groupless_leader = {"permission_groups": ["leaders"], "group_id": None}
    leader = {"permission_groups": ["leaders"], "group_id": "g"}

    assert updater.update_user("u", actor=user, group_id=unset) is None
    assert opened[-1].events == ["query", ("filter", 1)]
    assert updater.update_user("u", actor=groupless_leader, group_id=unset) is None
    assert opened[-1].events == ["query", ("filter", 1)]
    assert updater.update_user("u", actor=leader, group_id=unset) == {"id": "u", "group_name": "Group"}
    assert opened[-1].events[:5] == ["query", ("filter", 1), "elevated-filter", ("filter", 2), "first"]

    missing = Session(None)
    missing_updater = updater_type(
        lambda: missing, lambda value: value, lambda *_args: [], has_group,
        lambda _session: object(), lambda *_args: {}, object()
    )
    assert missing_updater.update_user("missing", group_id=missing_updater.unset) is None
    assert "commit" not in missing.events


def test_updater_preserves_fields_group_sentinel_and_transaction_order() -> None:
    updater_type = _updater_or_skip()
    unset = object()
    group = SimpleNamespace(name="New Group")
    row = SimpleNamespace(
        id="u", group_id="old", username="old", email="old@example.test", password_hash="old-hash"
    )

    class Query:
        def __init__(self, session: Session) -> None:
            self.session = session

        def filter(self, *_conditions: object) -> Query:
            return self

        def first(self) -> object:
            return self.session.row

    class Session:
        def __init__(self, found_group: object | None = group) -> None:
            self.row = row
            self.group = found_group
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            return Query(self)

        def get(self, row_type: object, key: object) -> object | None:
            self.events.append(("get", getattr(row_type, "__tablename__", "unknown"), key))
            return self.group

        def commit(self) -> None:
            self.events.append("commit")

        def refresh(self, value: object) -> None:
            self.events.append(("refresh", value))

    def build(session: Session):
        def set_groups(active: object, value: object, groups: object) -> list[str]:
            assert active is session
            session.events.append(("set-groups", value, groups))
            return ["users"]

        def project(value: object, group_name: str | None = None) -> dict:
            session.events.append(("project", value, group_name))
            return {"id": value.id, "group_name": group_name}

        return updater_type(
            lambda: session, lambda value: f"hash:{value}", set_groups,
            lambda actor, name: name in actor.get("permission_groups", []),
            lambda _session: object(), project, unset
        )

    session = Session()
    result = build(session).update_user(
        "u", username=" New ", email=" new@example.test ", password="secret",
        permission_groups=["users"], group_id="new"
    )
    assert (row.username, row.email, row.password_hash, row.group_id) == (
        "New", "new@example.test", "hash:secret", "new"
    )
    assert session.events == [
        ("set-groups", row, ["users"]),
        ("get", "user_groups", "new"),
        "commit",
        ("refresh", row),
        ("get", "user_groups", "new"),
        ("project", row, "New Group"),
    ]
    assert result == {"id": "u", "group_name": "New Group"}

    for field, message in (("username", "username is required"), ("email", "email is required")):
        invalid = Session()
        with pytest.raises(ValueError, match=message):
            build(invalid).update_user("u", **{field: " "})
        assert "commit" not in invalid.events

    missing_group = Session(None)
    with pytest.raises(ValueError, match="group not found"):
        build(missing_group).update_user("u", group_id="missing")
    assert "commit" not in missing_group.events

    unchanged = Session()
    build(unchanged).update_user("u", group_id=unset)
    assert not any(isinstance(event, tuple) and event[0] == "get" and event[2] == "old" for event in unchanged.events)

    cleared = Session()
    build(cleared).update_user("u", group_id=None)
    assert row.group_id is None


def test_updater_exceptions_propagate() -> None:
    updater_type = _updater_or_skip()

    class Session:
        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, *_args: object) -> object:
            raise RuntimeError("query failed")

    updater = updater_type(Session, lambda value: value, lambda *_args: [], lambda *_args: False,
                           lambda _session: object(), lambda *_args: {}, object())
    with pytest.raises(RuntimeError, match="query failed"):
        updater.update_user("u", group_id=updater.unset)
