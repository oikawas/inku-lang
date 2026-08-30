"""Direct validation and transaction coverage for account creation."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence import accounts
from inku_server.persistence.schema import Base, UserAccountRow


def _creator_or_skip():
    creator = getattr(accounts, "UserAccountCreator", None)
    if creator is None:
        pytest.skip("account creator is intentionally absent during fail-first")
    return creator


def test_accounts_owns_creator_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    creator = getattr(accounts, "UserAccountCreator", None)
    assert creator is not None, "persistence.accounts must own account creation"
    assert is_dataclass(creator) and creator.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        creator(*([None] * 8)).session_factory = None

    for name in ("_account_creator", "add_user"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[tuple[object, ...], tuple[object, ...]]] = []

    class RecordingCreator:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def add_user(self, *args: object) -> str:
            calls.append((self.dependencies, args))
            return "sentinel"

    monkeypatch.setattr(db._accounts, "UserAccountCreator", RecordingCreator)
    dependencies = tuple(object() for _ in range(8))
    monkeypatch.setattr(db, "SessionLocal", dependencies[0])
    monkeypatch.setattr(db.uuid, "uuid4", dependencies[1])
    monkeypatch.setattr(db, "_now_ms", dependencies[2])
    monkeypatch.setattr(db, "_hash_password", dependencies[3])
    monkeypatch.setattr(db, "_normalize_permission_groups", dependencies[4])
    monkeypatch.setattr(db, "_derived_role", dependencies[5])
    monkeypatch.setattr(db, "_set_permission_groups", dependencies[6])
    monkeypatch.setattr(db, "_user_to_dict", dependencies[7])

    assert isinstance(db._account_creator(), RecordingCreator)
    assert db.add_user(" name ", " mail ", "secret", ["users"], "g") == "sentinel"
    assert calls == [
        (dependencies, (" name ", " mail ", "secret", ["users"], "g")),
    ]


def test_creator_validates_before_session_and_builds_exact_row() -> None:
    creator_type = _creator_or_skip()
    events: list[object] = []

    def fail_session() -> None:
        raise AssertionError("invalid input must not open a session")

    creator = creator_type(
        fail_session,
        lambda: "uuid",
        lambda: 7,
        lambda password: f"hash:{password}",
        lambda groups: events.append(("normalize", groups)) or ["users"],
        lambda groups: events.append(("role", groups)) or "user",
        lambda *_args: None,
        lambda *_args: {},
    )
    with pytest.raises(ValueError, match="username is required"):
        creator.add_user(" ", "mail@example.test", "secret", ["users"], None)
    with pytest.raises(ValueError, match="email is required"):
        creator.add_user("name", " ", "secret", ["users"], None)
    assert events == []


def test_creator_preserves_group_check_single_commit_refresh_and_projection() -> None:
    creator_type = _creator_or_skip()
    group = SimpleNamespace(name="Group")

    class Session:
        def __init__(self, found_group: object | None) -> None:
            self.group = found_group
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, row_type: object, key: object) -> object | None:
            self.events.append(("get", getattr(row_type, "__tablename__", "unknown"), key))
            return self.group

        def add(self, row: object) -> None:
            self.events.append(("add", row))

        def flush(self) -> None:
            self.events.append("flush")

        def commit(self) -> None:
            self.events.append("commit")

        def refresh(self, row: object) -> None:
            self.events.append(("refresh", row))

    def build(session: Session):
        def set_groups(active_session: object, row: object, wanted: object) -> None:
            assert active_session is session
            session.events.append(("set-groups", row, wanted))

        def project(row: object, group_name: str | None = None) -> dict:
            session.events.append(("project", row, group_name))
            return {"id": row.id, "group_name": group_name}

        return creator_type(
            lambda: session,
            lambda: "uuid-1",
            lambda: 123,
            lambda password: f"hash:{password}",
            lambda groups: [name.strip() for name in groups],
            lambda groups: "admin" if "admins" in groups else "user",
            set_groups,
            project,
        )

    missing = Session(None)
    with pytest.raises(ValueError, match="group not found"):
        build(missing).add_user(" Name ", " mail@example.test ", "secret", ["users"], "missing")
    assert missing.events == [("get", "user_groups", "missing")]

    present = Session(group)
    result = build(present).add_user(
        " Name ", " mail@example.test ", "secret", [" admins "], "g"
    )
    row = present.events[1][1]
    assert (row.id, row.username, row.email, row.password_hash, row.role, row.group_id, row.at) == (
        "uuid-1", "Name", "mail@example.test", "hash:secret", "admin", "g", 123
    )
    assert present.events == [
        ("get", "user_groups", "g"),
        ("add", row),
        "flush",
        ("set-groups", row, ["admins"]),
        "commit",
        ("refresh", row),
        ("get", "user_groups", "g"),
        ("project", row, "Group"),
    ]
    assert result == {"id": "uuid-1", "group_name": "Group"}

    no_group = Session(None)
    result = build(no_group).add_user("Name", "mail@example.test", "secret", ["users"], None)
    assert all(not (isinstance(event, tuple) and event[0] == "get") for event in no_group.events)
    assert result == {"id": "uuid-1", "group_name": None}


def test_creator_rolls_back_the_account_when_permission_assignment_fails(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'accounts.db'}", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def fail_permission_assignment(*_args: object) -> None:
        raise RuntimeError("permission assignment failed")

    creator = _creator_or_skip()(
        session_factory,
        lambda: "user-1",
        lambda: 123,
        lambda password: f"hash:{password}",
        lambda _groups: ["users"],
        lambda _groups: "user",
        fail_permission_assignment,
        lambda *_args: {},
    )
    try:
        with pytest.raises(RuntimeError, match="permission assignment failed"):
            creator.add_user("name", "mail@example.test", "secret", ["users"], None)

        with session_factory() as session:
            assert session.query(UserAccountRow).count() == 0
    finally:
        engine.dispose()


def test_creator_exceptions_propagate() -> None:
    creator_type = _creator_or_skip()

    def fail_normalize(_groups: object) -> list[str]:
        raise RuntimeError("normalize failed")

    with pytest.raises(RuntimeError, match="normalize failed"):
        creator_type(
            lambda: None,
            lambda: "uuid",
            lambda: 1,
            lambda value: value,
            fail_normalize,
            lambda _groups: "user",
            lambda *_args: None,
            lambda *_args: {},
        ).add_user("name", "mail@example.test", "secret", ["users"], None)
