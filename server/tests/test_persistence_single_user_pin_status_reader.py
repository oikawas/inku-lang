"""Direct ownership coverage for single-user pin status reads."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts
from inku_server.persistence.schema import UserAccountRow


def _reader_or_skip():
    reader = getattr(accounts, "SingleUserPinStatusReader", None)
    if reader is None:
        pytest.skip("single-user pin status reader is intentionally absent during fail-first")
    return reader


class _PinStore:
    def __init__(self, pinned=None):
        self.pinned = pinned

    def get(self):
        return self.pinned


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.order_args = []

    def order_by(self, *args):
        self.order_args.append(args)
        return self

    def all(self):
        return self.rows


class _Session:
    def __init__(self, rows=None):
        self.query_result = _Query(rows or [])
        self.models = []

    def query(self, model):
        self.models.append(model)
        assert model is UserAccountRow
        return self.query_result


class _OwnedSession:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *_args):
        return False


def _reader(*, pinned=None, get_user=None, session=None, groups=None, enabled=False):
    reader_type = _reader_or_skip()
    return reader_type(
        _PinStore(pinned),
        get_user or (lambda _user_id: None),
        lambda: _OwnedSession(session or _Session()),
        groups or (lambda _session, _user_id: []),
        lambda: enabled,
    )


def test_accounts_owns_single_user_pin_status_and_db_delegates(monkeypatch) -> None:
    reader = getattr(accounts, "SingleUserPinStatusReader", None)
    assert reader is not None
    assert is_dataclass(reader) and reader.__dataclass_params__.frozen
    instance = _reader()
    with pytest.raises(FrozenInstanceError):
        instance.get_user_fn = None
    parsed = ast.parse(inspect.getsource(db.single_user_pin_status)).body[0]
    assert isinstance(parsed.body[-1], ast.Return)

    class Delegate:
        def read(self):
            return {"enabled": True}

    monkeypatch.setattr(db, "_single_user_pin_status_reader", lambda: Delegate())
    assert db.single_user_pin_status() == {"enabled": True}


def test_status_reader_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _reader_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    markers = [object() for _ in range(5)]
    monkeypatch.setattr(db._accounts, "SingleUserPinStatusReader", Recording)
    monkeypatch.setattr(db, "_single_user_pin_store", lambda: markers[0])
    monkeypatch.setattr(db, "get_user", markers[1])
    monkeypatch.setattr(db, "SessionLocal", markers[2])
    monkeypatch.setattr(db, "_permission_groups_of", markers[3])
    monkeypatch.setattr(db, "single_user_mode_enabled", markers[4])
    db._single_user_pin_status_reader()
    assert received == [tuple(markers)]


def test_missing_or_stale_pin_has_no_username_and_preserves_exact_shape() -> None:
    for pinned in (None, "stale"):
        seen = []
        reader = _reader(
            pinned=pinned,
            get_user=lambda user_id: seen.append(user_id),
            enabled=True,
        )
        assert reader.read() == {
            "enabled": True,
            "user_id": pinned,
            "username": None,
            "eligible": [],
        }
        assert seen == (["stale"] if pinned else [])


def test_status_projects_pin_and_lists_only_admins_in_query_order() -> None:
    rows = [
        SimpleNamespace(id="first", username="First"),
        SimpleNamespace(id="plain", username="Plain"),
        SimpleNamespace(id="third", username="Third"),
    ]
    session = _Session(rows)
    groups_by_id = {"first": ["admins"], "plain": ["users"], "third": ["admins", "users"]}
    reader = _reader(
        pinned="third",
        get_user=lambda user_id: {"id": user_id, "username": "Third"},
        session=session,
        groups=lambda received_session, user_id: groups_by_id[user_id],
        enabled=True,
    )
    assert reader.read() == {
        "enabled": True,
        "user_id": "third",
        "username": "Third",
        "eligible": [
            {"id": "first", "username": "First"},
            {"id": "third", "username": "Third"},
        ],
    }
    assert session.models == [UserAccountRow]
    assert len(session.query_result.order_args) == 1
