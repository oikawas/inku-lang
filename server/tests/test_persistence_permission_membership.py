"""Direct ownership coverage for permission-group memberships."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import groups


def _store_or_skip():
    store = getattr(groups, "PermissionGroupMembershipStore", None)
    if store is None:
        pytest.skip("membership store is intentionally absent during fail-first")
    return store


def test_groups_owns_memberships_and_db_delegates() -> None:
    store = getattr(groups, "PermissionGroupMembershipStore", None)
    assert store is not None
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None, None).uuid_fn = None
    for name in ("_permission_group_ids", "_permission_groups_of", "_set_permission_groups", "_holds_no_elevated_group"):
        fn = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(fn.body[-1], ast.Return)


def test_membership_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _store_or_skip()
    received = []
    class Recording:
        def __init__(self, *args): received.append(args)
    monkeypatch.setattr(db._groups, "PermissionGroupMembershipStore", Recording)
    marker_uuid, marker_now = object(), object()
    monkeypatch.setattr(db.uuid, "uuid4", marker_uuid)
    monkeypatch.setattr(db, "_now_ms", marker_now)
    db._permission_group_membership_store()
    assert received == [(marker_uuid, marker_now)]


def test_membership_facades_forward_exact_arguments(monkeypatch) -> None:
    _store_or_skip()
    calls = []
    class Recording:
        def __getattr__(self, name):
            def call(*args):
                calls.append((name, args))
                return name
            return call
    monkeypatch.setattr(db, "_permission_group_membership_store", lambda: Recording())
    session, row = object(), object()
    assert db._permission_group_ids(session) == "group_ids"
    assert db._permission_groups_of(session, "u") == "groups_of"
    assert db._set_permission_groups(session, row, ["users"]) == "set_groups"
    assert db._holds_no_elevated_group(session) == "holds_no_elevated_group"
    assert calls == [("group_ids", (session,)), ("groups_of", (session, "u")), ("set_groups", (session, row, ["users"])), ("holds_no_elevated_group", (session,))]


def test_membership_store_preserves_missing_group_error() -> None:
    store = _store_or_skip()(lambda: "id", lambda: 1)
    class Query:
        def all(self): return []
    class Session:
        def query(self, _row): return Query()
    with pytest.raises(ValueError, match="permission group not found: admins"):
        store.set_groups(Session(), type("Row", (), {"id": "u"})(), ["admins"])
