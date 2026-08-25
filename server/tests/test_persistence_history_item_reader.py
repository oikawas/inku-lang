"""Direct ownership and behavior coverage for ID-addressed history reads."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import history
from inku_server.persistence.schema import HistoryRow


class _Query:
    def __init__(self, session: "_Session") -> None:
        self._session = session
        self.filters: tuple[object, ...] = ()

    def filter(self, *filters: object) -> "_Query":
        self.filters = filters
        return self

    def all(self) -> list[SimpleNamespace]:
        self._session.rows_seen = self._session.rows
        return self._session.rows


class _Session:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.rows_seen: list[SimpleNamespace] | None = None
        self.query_models: list[object] = []
        self.query_result = _Query(self)

    def __enter__(self) -> "_Session":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def query(self, model: object) -> _Query:
        self.query_models.append(model)
        return self.query_result


def test_get_items_is_owned_by_history_item_reader() -> None:
    owner = getattr(history, "HistoryItemReader", None)
    assert owner is not None, "HistoryItemReader must own ID-addressed history reads"
    assert is_dataclass(owner)
    assert owner.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        owner(None, None, None).session_factory = None

    signature = inspect.signature(db.get_items)
    assert str(signature) == "(user_id: 'str', ids: 'list[str]') -> 'list[dict]'"
    facade_source = inspect.getsource(db.get_items)
    assert "HistoryItemReader" in facade_source
    assert "with SessionLocal" not in facade_source
    assert "SessionLocal" in facade_source
    assert "_actor_of" in facade_source
    assert "_rows_to_dicts_with_lineage" in facade_source

    owner_source = inspect.getsource(owner.get_items)
    assert "access._readable_by(actor, HistoryRow.user_id, HistoryRow.id)" in owner_source
    assert "ledger I-094" in owner_source
    assert "order_by" not in owner_source
    module_source = inspect.getsource(history)
    assert "from inku_server import db" not in module_source
    assert "from . import lineage" not in module_source
    assert "persistence.engine" not in module_source
    assert "persistence.config" not in module_source


def test_get_items_keeps_empty_access_query_projection_and_requested_order(monkeypatch) -> None:
    empty_calls: list[str] = []
    monkeypatch.setattr(db, "SessionLocal", lambda: empty_calls.append("session"))
    monkeypatch.setattr(db, "_actor_of", lambda user_id: empty_calls.append(user_id))
    monkeypatch.setattr(
        db,
        "_rows_to_dicts_with_lineage",
        lambda session, rows, actor: empty_calls.append("project"),
    )
    assert db.get_items("viewer", []) == []
    assert empty_calls == []

    first = SimpleNamespace(id="first")
    later = SimpleNamespace(id="later")
    session = _Session([first, later])
    calls: list[tuple[str, object]] = []
    actor = {"id": "viewer"}

    def actor_of(user_id: str) -> dict:
        calls.append(("actor", user_id))
        return actor

    def readable_by(actual_actor: dict, owner_column: object, item_column: object) -> str:
        calls.append(("readable", (actual_actor, owner_column, item_column)))
        return "readable-clause"

    def project(actual_session: object, rows: list[SimpleNamespace], actual_actor: dict) -> list[dict]:
        calls.append(("project", (actual_session, rows, actual_actor)))
        return [{"id": row.id, "shared": row.id == "later"} for row in rows]

    monkeypatch.setattr(db, "SessionLocal", lambda: session)
    monkeypatch.setattr(db, "_actor_of", actor_of)
    monkeypatch.setattr(db, "_rows_to_dicts_with_lineage", project)
    monkeypatch.setattr(history.access, "_readable_by", readable_by)

    assert db.get_items("viewer", ["later", "missing", "first"]) == [
        {"id": "later", "shared": True},
        {"id": "first", "shared": False},
    ]
    assert session.query_models == [HistoryRow]
    assert session.rows_seen == [first, later]
    assert calls == [
        ("actor", "viewer"),
        ("readable", (actor, HistoryRow.user_id, HistoryRow.id)),
        ("project", (session, [first, later], actor)),
    ]

    readable, requested, trashed = session.query_result.filters
    assert readable == "readable-clause"
    assert getattr(requested.left, "name", None) == "id"
    assert list(requested.right.value) == ["later", "missing", "first"]
    assert getattr(trashed.left, "name", None) == "trashed"
    assert trashed.right.value == 0
    assert trashed.compare(HistoryRow.trashed == 0)


def test_get_items_keeps_last_duplicate_index_and_call_time_dependencies(monkeypatch) -> None:
    alpha = SimpleNamespace(id="alpha")
    beta = SimpleNamespace(id="beta")
    session = _Session([beta, alpha])
    first_calls: list[str] = []
    second_calls: list[str] = []

    monkeypatch.setattr(db, "SessionLocal", lambda: session)
    monkeypatch.setattr(db, "_actor_of", lambda user_id: {"id": "first"})
    monkeypatch.setattr(
        db,
        "_rows_to_dicts_with_lineage",
        lambda actual_session, rows, actor: (
            first_calls.append(actor["id"]) or [{"id": row.id} for row in rows]
        ),
    )
    monkeypatch.setattr(history.access, "_readable_by", lambda *args: "first-readable")
    assert db.get_items("viewer", ["beta", "alpha", "beta"]) == [
        {"id": "alpha"},
        {"id": "beta"},
    ]
    assert session.rows_seen == [beta, alpha]
    assert first_calls == ["first"]

    monkeypatch.setattr(db, "_actor_of", lambda user_id: {"id": "second"})
    monkeypatch.setattr(
        db,
        "_rows_to_dicts_with_lineage",
        lambda actual_session, rows, actor: (
            second_calls.append(actor["id"]) or [{"id": row.id} for row in rows]
        ),
    )
    monkeypatch.setattr(history.access, "_readable_by", lambda *args: "second-readable")
    assert db.get_items("viewer", ["beta", "alpha", "beta"]) == [
        {"id": "alpha"},
        {"id": "beta"},
    ]
    assert second_calls == ["second"]
    assert session.query_result.filters[0] == "second-readable"
