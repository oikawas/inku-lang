"""Direct ownership coverage for fixed permission-group seeding."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import groups
from inku_server.persistence.schema import PermissionGroupRow


def _seeder_or_skip():
    seeder = getattr(groups, "PermissionGroupSeeder", None)
    if seeder is None:
        pytest.skip("permission group seeder is intentionally absent during fail-first")
    return seeder


def test_groups_owns_permission_seed_and_db_delegates() -> None:
    seeder = getattr(groups, "PermissionGroupSeeder", None)
    assert seeder is not None
    assert is_dataclass(seeder) and seeder.__dataclass_params__.frozen
    instance = seeder(None, None, None)
    with pytest.raises(FrozenInstanceError):
        instance.session_factory = None
    function = ast.parse(inspect.getsource(db._ensure_permission_groups)).body[0]
    assert isinstance(function.body[-1], ast.Return)


def test_permission_seed_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _seeder_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    markers = [object(), object(), object()]
    monkeypatch.setattr(db._groups, "PermissionGroupSeeder", Recording)
    monkeypatch.setattr(db, "SessionLocal", markers[0])
    monkeypatch.setattr(db.uuid, "uuid4", markers[1])
    monkeypatch.setattr(db, "_now_ms", markers[2])
    db._permission_group_seeder()
    assert received == [tuple(markers)]


class _Session:
    def __init__(self, existing):
        self.existing = [SimpleNamespace(name=name) for name in existing]
        self.added = []
        self.commits = 0
        self.flushes = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def query(self, row_type):
        assert row_type is PermissionGroupRow
        return self

    def all(self):
        return self.existing

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1

    def flush(self):
        self.flushes += 1


def test_permission_seed_preserves_complete_vocabulary_short_circuit() -> None:
    session = _Session(groups.PERMISSION_GROUPS)
    _seeder_or_skip()(lambda: session, lambda: "id", lambda: 9).ensure(session)
    assert session.added == []
    assert (session.commits, session.flushes) == (0, 0)


def test_permission_seed_preserves_missing_order_and_session_finish_behavior() -> None:
    owned = _Session({"leaders"})
    borrowed = _Session({"admins", "users"})
    ids = iter(["admins-id", "users-id", "leaders-id"])
    seeder = _seeder_or_skip()(lambda: owned, lambda: next(ids), lambda: 123)

    seeder.ensure()
    seeder.ensure(borrowed)

    assert [(row.id, row.name, row.at) for row in owned.added] == [
        ("admins-id", "admins", 123),
        ("users-id", "users", 123),
    ]
    assert [(row.id, row.name, row.at) for row in borrowed.added] == [
        ("leaders-id", "leaders", 123)
    ]
    assert (owned.commits, owned.flushes) == (1, 0)
    assert (borrowed.commits, borrowed.flushes) == (0, 1)
