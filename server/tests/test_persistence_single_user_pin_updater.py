"""Direct ownership coverage for single-user pin validation and update."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts
from inku_server.persistence.schema import UserAccountRow


def _updater_or_skip():
    updater = getattr(accounts, "SingleUserPinUpdater", None)
    if updater is None:
        pytest.skip("single-user pin updater is intentionally absent during fail-first")
    return updater


class _PinStore:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.updates = []

    def update(self, user_id):
        self.events.append("pin-update")
        self.updates.append(user_id)


class _Session:
    def __init__(self, row=None, events=None):
        self.row = row
        self.events = events if events is not None else []
        self.gets = []

    def get(self, model, user_id):
        self.events.append("account-get")
        self.gets.append((model, user_id))
        return self.row


class _OwnedSession:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *_args):
        return False


def _updater(*, enabled=True, session=None, groups=None, pin_store=None, status=None):
    updater_type = _updater_or_skip()
    return updater_type(
        lambda: enabled,
        lambda: _OwnedSession(session or _Session()),
        groups or (lambda _session, _user_id: []),
        pin_store or _PinStore(),
        status or (lambda: {"status": "current"}),
    )


def test_accounts_owns_single_user_pin_update_and_db_delegates(monkeypatch) -> None:
    updater = getattr(accounts, "SingleUserPinUpdater", None)
    assert updater is not None
    assert is_dataclass(updater) and updater.__dataclass_params__.frozen
    instance = _updater()
    with pytest.raises(FrozenInstanceError):
        instance.mode_enabled_fn = None
    parsed = ast.parse(inspect.getsource(db.set_single_user_pin)).body[0]
    assert isinstance(parsed.body[-1], ast.Return)

    class Delegate:
        def update(self, user_id):
            return {"user_id": user_id}

    monkeypatch.setattr(db, "_single_user_pin_updater", lambda: Delegate())
    assert db.set_single_user_pin("chosen") == {"user_id": "chosen"}


def test_updater_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _updater_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    markers = [object() for _ in range(5)]
    monkeypatch.setattr(db._accounts, "SingleUserPinUpdater", Recording)
    monkeypatch.setattr(db, "single_user_mode_enabled", markers[0])
    monkeypatch.setattr(db, "SessionLocal", markers[1])
    monkeypatch.setattr(db, "_permission_groups_of", markers[2])
    monkeypatch.setattr(db, "_single_user_pin_store", lambda: markers[3])
    monkeypatch.setattr(db, "single_user_pin_status", markers[4])
    db._single_user_pin_updater()
    assert received == [tuple(markers)]


def test_mode_off_refuses_before_account_lookup_or_write() -> None:
    events = []
    session = _Session(row=SimpleNamespace(id="chosen"), events=events)
    pin_store = _PinStore(events)
    updater = _updater(enabled=False, session=session, pin_store=pin_store)
    with pytest.raises(ValueError, match="^single-user mode is not enabled$"):
        updater.update("chosen")
    assert events == []
    assert pin_store.updates == []


def test_missing_or_non_admin_account_refuses_without_writing() -> None:
    for row, groups, message in (
        (None, [], "user not found"),
        (SimpleNamespace(id="chosen"), ["users"], "the single user must hold the admins permission group"),
    ):
        pin_store = _PinStore()
        updater = _updater(
            session=_Session(row=row),
            groups=lambda _session, _user_id, value=groups: value,
            pin_store=pin_store,
        )
        with pytest.raises(ValueError, match=f"^{message}$"):
            updater.update("chosen")
        assert pin_store.updates == []


def test_valid_admin_is_written_before_current_status_is_returned() -> None:
    events = []
    session = _Session(row=SimpleNamespace(id="chosen"), events=events)
    pin_store = _PinStore(events)

    def groups(received_session, user_id):
        assert received_session is session
        assert user_id == "chosen"
        events.append("groups")
        return ["admins"]

    def status():
        events.append("status")
        return {"user_id": "chosen"}

    updater = _updater(session=session, groups=groups, pin_store=pin_store, status=status)
    assert updater.update("chosen") == {"user_id": "chosen"}
    assert session.gets == [(UserAccountRow, "chosen")]
    assert pin_store.updates == ["chosen"]
    assert events == ["account-get", "groups", "pin-update", "status"]
