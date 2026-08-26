"""Direct ownership coverage for legacy unowned-history owner assignment."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from inku_server import db
from inku_server.persistence import history
from inku_server.persistence.schema import HistoryRow


class _Query:
    def __init__(self, session: _Session):
        self.session = session

    def filter(self, criterion):
        self.session.events.append(("filter", criterion))
        return self

    def update(self, values, *, synchronize_session):
        self.session.events.append(("update", values, synchronize_session))
        return 2


class _Session:
    def __init__(self):
        self.events = []

    def __enter__(self):
        self.events.append(("enter",))
        return self

    def __exit__(self, *_args):
        self.events.append(("exit",))
        return False

    def query(self, model):
        self.events.append(("query", model))
        return _Query(self)

    def flush(self):
        self.events.append(("flush",))

    def commit(self):
        self.events.append(("commit",))


def _event_names(session: _Session) -> list[str]:
    return [event[0] for event in session.events]


def test_history_owns_frozen_backfill_and_no_owner_is_a_noop() -> None:
    backfill_type = getattr(history, "UnownedHistoryOwnerBackfill", None)
    assert backfill_type is not None
    assert is_dataclass(backfill_type) and backfill_type.__dataclass_params__.frozen

    borrowed = _Session()

    def no_owner(session):
        session.events.append(("owner",))
        return None

    backfill = backfill_type(lambda: pytest.fail("borrowed session must be reused"), no_owner)
    with pytest.raises(FrozenInstanceError):
        backfill.session_factory = None
    assert backfill.assign(borrowed) is None
    assert _event_names(borrowed) == ["owner"]


def test_backfill_resolves_owner_before_null_only_update_and_flushes_borrowed_session() -> None:
    backfill_type = getattr(history, "UnownedHistoryOwnerBackfill", None)
    assert backfill_type is not None
    borrowed = _Session()

    def owner_id(session):
        session.events.append(("owner",))
        return "owner-id"

    backfill = backfill_type(lambda: pytest.fail("borrowed session must be reused"), owner_id)
    assert backfill.assign(borrowed) is None

    assert _event_names(borrowed) == ["owner", "query", "filter", "update", "flush"]
    assert borrowed.events[1] == ("query", HistoryRow)
    assert borrowed.events[2][1].compare(HistoryRow.user_id.is_(None))
    assert borrowed.events[3] == ("update", {HistoryRow.user_id: "owner-id"}, False)


def test_backfill_opens_and_commits_owned_session() -> None:
    backfill_type = getattr(history, "UnownedHistoryOwnerBackfill", None)
    assert backfill_type is not None
    owned = _Session()

    def owner_id(session):
        session.events.append(("owner",))
        return "owner-id"

    backfill = backfill_type(lambda: owned, owner_id)
    assert backfill.assign() is None
    assert _event_names(owned) == [
        "enter",
        "owner",
        "query",
        "filter",
        "update",
        "commit",
        "exit",
    ]


def test_db_facade_constructs_and_delegates_at_call_time(monkeypatch) -> None:
    created = []
    calls = []
    session_factory = object()
    owner_resolver = object()
    borrowed = object()
    result = object()

    class Recording:
        def __init__(self, *args):
            created.append(args)

        def assign(self, session=None):
            calls.append(session)
            return result

    monkeypatch.setattr(history, "UnownedHistoryOwnerBackfill", Recording, raising=False)
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    monkeypatch.setattr(db, "_history_owner_user_id", owner_resolver)

    assert db._assign_unowned_history_to_admin(borrowed) is result
    assert created == [(session_factory, owner_resolver)]
    assert calls == [borrowed]
