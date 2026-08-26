"""Direct ownership coverage for legacy-role membership backfill."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import groups
from inku_server.persistence.schema import PermissionGroupRow, UserAccountRow, UserPermissionGroupRow


def _migrator_or_skip():
    migrator = getattr(groups, "LegacyRoleMembershipMigrator", None)
    if migrator is None:
        pytest.skip("legacy role migrator is intentionally absent during fail-first")
    return migrator


def test_groups_owns_legacy_backfill_and_db_delegates() -> None:
    migrator = getattr(groups, "LegacyRoleMembershipMigrator", None)
    assert migrator is not None
    assert is_dataclass(migrator) and migrator.__dataclass_params__.frozen
    instance = migrator(None, None, None)
    with pytest.raises(FrozenInstanceError):
        instance.session_factory = None
    function = ast.parse(inspect.getsource(db._migrate_roles_to_permission_groups)).body[0]
    assert isinstance(function.body[-1], ast.Return)


def test_legacy_backfill_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _migrator_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    markers = [object(), object(), object()]
    monkeypatch.setattr(db._groups, "LegacyRoleMembershipMigrator", Recording)
    monkeypatch.setattr(db, "SessionLocal", markers[0])
    monkeypatch.setattr(db.uuid, "uuid4", markers[1])
    monkeypatch.setattr(db, "_now_ms", markers[2])
    db._legacy_role_membership_migrator()
    assert received == [tuple(markers)]


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def distinct(self):
        return self

    def all(self):
        return self.rows


class _Session:
    def __init__(self, permission_groups, assigned, accounts):
        self.permission_groups = permission_groups
        self.assigned = assigned
        self.accounts = accounts
        self.added = []
        self.commits = 0
        self.flushes = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def query(self, target):
        if target is PermissionGroupRow:
            return _Query(self.permission_groups)
        if target is UserPermissionGroupRow.user_id:
            return _Query([(user_id,) for user_id in self.assigned])
        if target is UserAccountRow:
            return _Query(self.accounts)
        raise AssertionError(target)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1

    def flush(self):
        self.flushes += 1


def test_legacy_backfill_preserves_mapping_fallback_and_existing_memberships() -> None:
    session = _Session(
        [
            SimpleNamespace(name="admins", id="g-admins"),
            SimpleNamespace(name="leaders", id="g-leaders"),
            SimpleNamespace(name="users", id="g-users"),
        ],
        {"existing"},
        [
            SimpleNamespace(id="admin", role="admin"),
            SimpleNamespace(id="leader", role="group_lead"),
            SimpleNamespace(id="unknown", role="obsolete"),
            SimpleNamespace(id="existing", role="admin"),
        ],
    )
    ids = iter(["m1", "m2", "m3"])
    _migrator_or_skip()(lambda: session, lambda: next(ids), lambda: 123).migrate(session)
    assert [
        (row.id, row.user_id, row.permission_group_id, row.at) for row in session.added
    ] == [
        ("m1", "admin", "g-admins", 123),
        ("m2", "leader", "g-leaders", 123),
        ("m3", "unknown", "g-users", 123),
    ]
    assert (session.commits, session.flushes) == (0, 1)


def test_legacy_backfill_preserves_no_group_short_circuit_and_owned_commit() -> None:
    empty = _Session([], set(), [SimpleNamespace(id="u", role="admin")])
    _migrator_or_skip()(lambda: empty, lambda: "unused", lambda: 1).migrate()
    assert empty.added == []
    assert (empty.commits, empty.flushes) == (0, 0)

    owned = _Session(
        [SimpleNamespace(name="users", id="g-users")],
        set(),
        [SimpleNamespace(id="u", role="unknown")],
    )
    _migrator_or_skip()(lambda: owned, lambda: "m", lambda: 2).migrate()
    assert [(row.user_id, row.permission_group_id) for row in owned.added] == [
        ("u", "g-users")
    ]
    assert (owned.commits, owned.flushes) == (1, 0)
