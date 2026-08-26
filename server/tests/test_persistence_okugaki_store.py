"""Direct ownership and transaction coverage for the Okugaki store."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import importlib
import importlib.util
import inspect
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from inku_server import db

okugaki = (
    importlib.import_module("inku_server.persistence.okugaki")
    if importlib.util.find_spec("inku_server.persistence.okugaki") is not None
    else None
)


def _store_or_skip():
    if okugaki is None:
        pytest.skip("production Okugaki module is intentionally absent during fail-first")
    store = getattr(okugaki, "OkugakiStore", None)
    if store is None:
        pytest.skip("production Okugaki owner is intentionally absent during fail-first")
    return store


def _row(**overrides: object) -> SimpleNamespace:
    values = {
        "id": "okugaki-1",
        "target_node_id": "node-1",
        "branch_snapshot_json": '["node-1"]',
        "model": "provider/model",
        "at": 10,
        "language": "ja",
        "body": "body",
        "warnings_json": "[]",
        "fact_sheet_json": "{}",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _item() -> dict:
    return {
        "target_node_id": "node-1",
        "branch_snapshot": ["node-1"],
        "model": "provider/model",
        "at": 10,
        "language": "ja",
        "body": "body",
    }


def test_persistence_okugaki_owns_store_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    assert okugaki is not None, "persistence.okugaki must own Okugaki persistence"
    store = getattr(okugaki, "OkugakiStore", None)
    assert store is not None, "OkugakiStore must own Okugaki persistence"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None, None, None, None).session_factory = None

    for name in (
        "_okugaki_to_dict",
        "add_okugaki",
        "list_okugaki",
        "get_okugaki_by_idempotency",
        "delete_okugaki",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[tuple[object, ...], str, tuple[object, ...], dict]] = []

    class RecordingStore:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def __getattr__(self, name: str):
            def call(*args: object, **kwargs: object):
                calls.append((self.dependencies, name, args, kwargs))
                return "sentinel"

            return call

    monkeypatch.setattr(db._okugaki, "OkugakiStore", RecordingStore)
    dependencies = (object(), object(), object(), object())
    for name, dependency in zip(
        ("SessionLocal", "_actor_of", "_owner_actor", "_canonical_json"),
        dependencies,
        strict=True,
    ):
        monkeypatch.setattr(db, name, dependency)
    assert db.add_okugaki("user", {"item": True}, idempotency_key="key") == "sentinel"
    assert calls == [
        (dependencies, "add_okugaki", ("user", {"item": True}), {"idempotency_key": "key"})
    ]


def test_projection_keeps_json_fallbacks_and_exact_shape() -> None:
    _store_or_skip()
    assert okugaki.okugaki_to_dict(_row(
        branch_snapshot_json="bad", warnings_json=None, fact_sheet_json="[]"
    )) == {
        "id": "okugaki-1",
        "target_node_id": "node-1",
        "branch_snapshot": [],
        "model": "provider/model",
        "at": 10,
        "language": "ja",
        "body": "body",
        "warnings": [],
        "fact_sheet": [],
    }


def test_add_preserves_precheck_target_rejection_and_integrity_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_type = _store_or_skip()
    monkeypatch.setattr(okugaki.access, "_owned_by", lambda *_args: object())
    monkeypatch.setattr(okugaki.access, "_readable_node", lambda *_args: object())

    class Query:
        def __init__(self, answers: list[object | None]) -> None:
            self.answers = answers

        def filter(self, *_conditions: object) -> Query:
            return self

        def first(self) -> object | None:
            return self.answers.pop(0)

    class Session:
        def __init__(self, answers: list[object | None], *, fail_commit: bool = False) -> None:
            self.query_object = Query(answers)
            self.fail_commit = fail_commit
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            return self.query_object

        def add(self, row: object) -> None:
            self.events.append(("add", row))

        def commit(self) -> None:
            self.events.append("commit")
            if self.fail_commit:
                raise IntegrityError("insert", {}, RuntimeError("duplicate"))

        def rollback(self) -> None:
            self.events.append("rollback")

        def refresh(self, row: object) -> None:
            self.events.append(("refresh", row))

    existing = _row()
    replay_session = Session([existing])
    store = store_type(lambda: replay_session, lambda user_id: {"id": user_id}, lambda _: {}, str)
    replay = store.add_okugaki("user", _item(), idempotency_key="key")
    assert replay["_idempotent_replay"] is True
    assert replay_session.events == []

    missing_target_session = Session([None])
    store = store_type(lambda: missing_target_session, lambda user_id: {"id": user_id}, lambda _: {}, str)
    with pytest.raises(ValueError, match="lineage target not found"):
        store.add_okugaki("user", _item())
    assert missing_target_session.events == []

    race_session = Session([None, object(), existing], fail_commit=True)
    store = store_type(lambda: race_session, lambda user_id: {"id": user_id}, lambda _: {}, lambda _: "json")
    replay = store.add_okugaki("user", _item(), idempotency_key="key")
    assert replay["_idempotent_replay"] is True
    assert race_session.events[1:] == ["commit", "rollback"]

    lost_race_session = Session([None, object(), None], fail_commit=True)
    store = store_type(lambda: lost_race_session, lambda user_id: {"id": user_id}, lambda _: {}, lambda _: "json")
    with pytest.raises(IntegrityError):
        store.add_okugaki("user", _item(), idempotency_key="key")
    assert lost_race_session.events[1:] == ["commit", "rollback"]


def test_list_and_lookup_keep_distinct_read_and_owner_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    store_type = _store_or_skip()
    read_calls: list[tuple[object, ...]] = []
    owner_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        okugaki.access,
        "_readable_by",
        lambda *args: read_calls.append(args) or object(),
    )
    monkeypatch.setattr(
        okugaki.access,
        "_owned_by",
        lambda *args: owner_calls.append(args) or object(),
    )
    row = _row()

    class Query:
        def filter(self, *_conditions: object) -> Query:
            return self

        def order_by(self, *_columns: object) -> Query:
            return self

        def all(self) -> list[object]:
            return [row]

        def first(self) -> object:
            return row

    class Session:
        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            return Query()

    store = store_type(Session, lambda user_id: {"actor": user_id}, lambda user_id: {"owner": user_id}, str)
    assert len(store.list_okugaki("reader", "node-1")) == 1
    assert len(read_calls) == 1 and len(read_calls[0]) == 2
    assert store.get_okugaki_by_idempotency("owner", "key")["id"] == "okugaki-1"
    assert owner_calls == [({"owner": "owner"}, okugaki.OkugakiRow.user_id)]


def test_delete_preserves_writable_boundary_commit_and_false_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_type = _store_or_skip()
    write_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        okugaki.access,
        "_writable_by",
        lambda *args: write_calls.append(args) or object(),
    )

    class Query:
        def __init__(self, row: object | None) -> None:
            self.row = row

        def filter(self, *_conditions: object) -> Query:
            return self

        def first(self) -> object | None:
            return self.row

    class Session:
        def __init__(self, row: object | None) -> None:
            self.row = row
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            return Query(self.row)

        def delete(self, row: object) -> None:
            self.events.append(("delete", row))

        def commit(self) -> None:
            self.events.append("commit")

    present = object()
    present_session = Session(present)
    store = store_type(lambda: present_session, lambda user_id: {"id": user_id}, lambda _: {}, str)
    assert store.delete_okugaki("user", "okugaki")
    assert present_session.events == [("delete", present), "commit"]

    absent_session = Session(None)
    store = store_type(lambda: absent_session, lambda user_id: {"id": user_id}, lambda _: {}, str)
    assert not store.delete_okugaki("user", "missing")
    assert absent_session.events == []
    assert len(write_calls) == 2
