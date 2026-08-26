"""Direct ownership coverage for bootstrap-admin account seeding."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts
from inku_server.persistence.schema import UserAccountRow, UserGroupRow


def _seeder_or_skip():
    seeder = getattr(accounts, "BootstrapAdminSeeder", None)
    if seeder is None:
        pytest.skip("bootstrap admin seeder is intentionally absent during fail-first")
    return seeder


def _dependencies(**overrides):
    values = {
        "session_factory": None,
        "bootstrap_password_fn": lambda: "bootstrap-password",
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
        self.added = []
        self.queries = []

    def query(self, model):
        self.queries.append(model)
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


def test_accounts_owns_bootstrap_admin_seeding_and_db_delegates(monkeypatch) -> None:
    seeder = getattr(accounts, "BootstrapAdminSeeder", None)
    assert seeder is not None
    assert is_dataclass(seeder) and seeder.__dataclass_params__.frozen
    instance = seeder(**_dependencies())
    with pytest.raises(FrozenInstanceError):
        instance.session_factory = None
    function = ast.parse(inspect.getsource(db._ensure_bootstrap_admin)).body[0]
    assert isinstance(function.body[-1], ast.Return)
    calls = []

    class Delegate:
        def ensure(self, session):
            calls.append(session)
            return "delegated"

    monkeypatch.setattr(db, "_bootstrap_admin_seeder", lambda: Delegate())
    marker = object()
    assert db._ensure_bootstrap_admin(marker) == "delegated"
    assert calls == [marker]


def test_bootstrap_admin_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _seeder_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    markers = [object() for _ in range(8)]
    monkeypatch.setattr(db._accounts, "BootstrapAdminSeeder", Recording)
    monkeypatch.setattr(db, "SessionLocal", markers[0])
    monkeypatch.setattr(db, "_bootstrap_admin_password", markers[1])
    monkeypatch.setattr(db, "_hash_password", markers[2])
    monkeypatch.setattr(db, "_derived_role", markers[3])
    monkeypatch.setattr(db, "_set_permission_groups", markers[4])
    monkeypatch.setattr(db.uuid, "uuid4", markers[5])
    monkeypatch.setattr(db, "_now_ms", markers[6])
    monkeypatch.setattr(db.os, "getenv", markers[7])
    db._bootstrap_admin_seeder()
    assert received == [tuple(markers)]


def test_bootstrap_admin_preserves_existing_account_and_missing_password_noops() -> None:
    seeder_type = _seeder_or_skip()
    existing = _Session(account=object())
    seeder_type(**_dependencies(bootstrap_password_fn=lambda: pytest.fail())).ensure(existing)
    assert existing.queries == [UserAccountRow]
    assert existing.added == []
    assert existing.events == []

    group = SimpleNamespace(id="group-id")
    missing_password = _Session(group=group)
    seeder_type(**_dependencies(bootstrap_password_fn=lambda: None)).ensure(
        missing_password
    )
    assert missing_password.queries == [UserAccountRow, UserGroupRow]
    assert missing_password.added == []
    assert missing_password.events == []


def test_bootstrap_admin_preserves_row_membership_and_session_semantics() -> None:
    seeder_type = _seeder_or_skip()
    cases = [
        (False, ["add", "flush", "groups", "flush"]),
        (True, ["add", "flush", "groups", "commit"]),
    ]
    for owned, expected_events in cases:
        events = []
        session = _Session(group=SimpleNamespace(id="group-id"), events=events)

        def set_groups(received_session, row, names):
            assert received_session is session
            assert row is session.added[0]
            assert names == ["admins"]
            events.append("groups")

        getenv = {
            "INKU_BOOTSTRAP_ADMIN_USERNAME": "operator",
            "INKU_BOOTSTRAP_ADMIN_EMAIL": "operator@example.test",
        }
        def session_factory():
            return _OwnedSession(session)

        seeder = seeder_type(
            **_dependencies(
                session_factory=session_factory,
                set_permission_groups_fn=set_groups,
                getenv_fn=lambda name, default=None: getenv.get(name, default),
            )
        )
        seeder.ensure(None if owned else session)

        assert events == expected_events
        assert len(session.added) == 1
        row = session.added[0]
        assert row.id == "account-id"
        assert row.username == "operator"
        assert row.email == "operator@example.test"
        assert row.password_hash == "hash:bootstrap-password"
        assert row.role == "admins"
        assert row.group_id == "group-id"
        assert row.at == 1234
