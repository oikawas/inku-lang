"""Direct ownership coverage for empty-database single-user account creation."""

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
from inku_server.persistence.schema import UserAccountRow, UserGroupRow


def _creator_or_skip():
    creator = getattr(accounts, "SingleUserAccountCreator", None)
    if creator is None:
        pytest.skip("single-user account creator is intentionally absent during fail-first")
    return creator


def _dependencies(**overrides):
    values = {
        "session_factory": None,
        "ensure_default_user_group_fn": lambda: None,
        "ensure_permission_groups_fn": lambda: None,
        "bootstrap_password_fn": lambda: "chosen-password",
        "random_password_fn": lambda size: f"random-{size}",
        "hash_password_fn": lambda password: f"hash:{password}",
        "derived_role_fn": lambda names: "+".join(names),
        "set_permission_groups_fn": lambda session, row, names: None,
        "uuid_fn": lambda: "account-id",
        "now_ms_fn": lambda: 1234,
        "getenv_fn": lambda name, default=None: default,
    }
    values.update(overrides)
    return values


class _Query:
    def __init__(self, row):
        self.row = row

    def order_by(self, *_args):
        return self

    def first(self):
        return self.row


class _Session:
    def __init__(self, account=None, group=None, events=None):
        self.account = account
        self.group = group
        self.events = events if events is not None else []
        self.models = []
        self.added = []

    def query(self, model):
        self.models.append(model)
        if model is UserAccountRow:
            return _Query(self.account)
        if model is UserGroupRow:
            return _Query(self.group)
        raise AssertionError(f"unexpected query model: {model}")

    def add(self, row):
        self.events.append("add")
        self.added.append(row)

    def flush(self):
        self.events.append("flush")

    def commit(self):
        self.events.append("commit")


class _OwnedSession:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *_args):
        return False


def test_accounts_owns_single_user_account_creation_and_db_delegates(monkeypatch) -> None:
    creator = getattr(accounts, "SingleUserAccountCreator", None)
    assert creator is not None
    assert is_dataclass(creator) and creator.__dataclass_params__.frozen
    instance = creator(**_dependencies())
    with pytest.raises(FrozenInstanceError):
        instance.session_factory = None
    parsed = ast.parse(inspect.getsource(db._create_single_user_account)).body[0]
    assert isinstance(parsed.body[-1], ast.Return)

    class Delegate:
        def create(self):
            return "delegated"

    monkeypatch.setattr(db, "_single_user_account_creator", lambda: Delegate())
    assert db._create_single_user_account() == "delegated"


def test_single_user_account_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _creator_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    markers = [object() for _ in range(11)]
    monkeypatch.setattr(db._accounts, "SingleUserAccountCreator", Recording)
    monkeypatch.setattr(db, "SessionLocal", markers[0])
    monkeypatch.setattr(db, "_ensure_default_user_group", markers[1])
    monkeypatch.setattr(db, "_ensure_permission_groups", markers[2])
    monkeypatch.setattr(db, "_bootstrap_admin_password", markers[3])
    monkeypatch.setattr(db.secrets, "token_urlsafe", markers[4])
    monkeypatch.setattr(db, "_hash_password", markers[5])
    monkeypatch.setattr(db, "_derived_role", markers[6])
    monkeypatch.setattr(db, "_set_permission_groups", markers[7])
    monkeypatch.setattr(db.uuid, "uuid4", markers[8])
    monkeypatch.setattr(db, "_now_ms", markers[9])
    monkeypatch.setattr(db.os, "getenv", markers[10])
    db._single_user_account_creator()
    assert received == [tuple(markers)]


def test_single_user_account_preserves_seed_order_and_existing_account_noop() -> None:
    creator_type = _creator_or_skip()
    events = []
    session = _Session(account=object(), events=events)
    creator = creator_type(
        **_dependencies(
            session_factory=lambda: _OwnedSession(session),
            ensure_default_user_group_fn=lambda: events.append("default-group"),
            ensure_permission_groups_fn=lambda: events.append("permission-groups"),
            bootstrap_password_fn=lambda: pytest.fail("password must not resolve"),
        )
    )
    assert creator.create() is None
    assert events == ["default-group", "permission-groups"]
    assert session.models == [UserAccountRow]
    assert session.added == []


def test_single_user_account_preserves_password_row_membership_and_commit_order() -> None:
    creator_type = _creator_or_skip()
    for explicit_password, expected_password in (
        ("chosen-password", "chosen-password"),
        (None, "random-32"),
    ):
        events = []
        session = _Session(group=SimpleNamespace(id="group-id"), events=events)

        def set_groups(received_session, row, names):
            assert received_session is session
            assert row is session.added[0]
            assert names == ["admins"]
            events.append("groups")

        env = {
            "INKU_BOOTSTRAP_ADMIN_USERNAME": "operator",
            "INKU_BOOTSTRAP_ADMIN_EMAIL": "operator@example.test",
        }
        creator = creator_type(
            **_dependencies(
                session_factory=lambda: _OwnedSession(session),
                ensure_default_user_group_fn=lambda: events.append("default-group"),
                ensure_permission_groups_fn=lambda: events.append("permission-groups"),
                bootstrap_password_fn=lambda: explicit_password,
                set_permission_groups_fn=set_groups,
                getenv_fn=lambda name, default=None: env.get(name, default),
            )
        )
        assert creator.create() == "account-id"
        assert events == [
            "default-group",
            "permission-groups",
            "add",
            "flush",
            "groups",
            "commit",
        ]
        row = session.added[0]
        assert row.id == "account-id"
        assert row.username == "operator"
        assert row.email == "operator@example.test"
        assert row.password_hash == f"hash:{expected_password}"
        assert row.role == "admins"
        assert row.group_id == "group-id"
        assert row.at == 1234


def test_single_user_account_rolls_back_when_admin_membership_fails(tmp_path) -> None:
    creator_type = _creator_or_skip()
    engine = create_engine(f"sqlite:///{tmp_path / 'single-user.sqlite'}")
    UserGroupRow.__table__.create(engine)
    UserAccountRow.__table__.create(engine)
    factory = sessionmaker(bind=engine)

    def fail_membership(_session, _row, _names):
        raise RuntimeError("membership failed")

    creator = creator_type(
        **_dependencies(
            session_factory=factory,
            set_permission_groups_fn=fail_membership,
        )
    )

    with pytest.raises(RuntimeError, match="membership failed"):
        creator.create()

    with factory() as session:
        assert session.get(UserAccountRow, "account-id") is None
