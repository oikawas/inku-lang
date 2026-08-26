"""Direct ownership coverage for authorization actor lookup."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _reader_or_skip():
    reader = getattr(accounts, "AccountActorReader", None)
    if reader is None:
        pytest.skip("account actor reader is intentionally absent during fail-first")
    return reader


def test_accounts_owns_actor_lookup_and_db_delegates() -> None:
    reader = getattr(accounts, "AccountActorReader", None)
    assert reader is not None
    assert is_dataclass(reader) and reader.__dataclass_params__.frozen
    instance = reader(None, None)
    with pytest.raises(FrozenInstanceError):
        instance.session_factory = None
    function = ast.parse(inspect.getsource(db._actor_of)).body[0]
    assert isinstance(function.body[-1], ast.Return)


def test_actor_reader_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _reader_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    markers = [object(), object()]
    monkeypatch.setattr(db._accounts, "AccountActorReader", Recording)
    monkeypatch.setattr(db, "SessionLocal", markers[0])
    monkeypatch.setattr(db, "_permission_groups_of", markers[1])
    db._account_actor_reader()
    assert received == [tuple(markers)]


class _Session:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def query(self, _row_type):
        return self

    def filter(self, *_args):
        return self

    def first(self):
        return self.row


def test_actor_reader_preserves_unknown_id_safe_fallback() -> None:
    reader = _reader_or_skip()(
        lambda: _Session(None),
        lambda *_args: pytest.fail("memberships must not be read for an unknown account"),
    )
    assert reader.get("missing") == {
        "id": "missing",
        "permission_groups": [],
        "group_id": None,
    }


def test_actor_reader_preserves_memberships_and_group_id() -> None:
    row = SimpleNamespace(group_id="group-1")
    session = _Session(row)
    calls = []
    reader = _reader_or_skip()(
        lambda: session,
        lambda active_session, user_id: calls.append((active_session, user_id))
        or ["users", "leaders"],
    )
    assert reader.get("member") == {
        "id": "member",
        "permission_groups": ["users", "leaders"],
        "group_id": "group-1",
    }
    assert calls == [(session, "member")]
