"""Direct ownership coverage for owner-wide history-domain deletion."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence import history
from inku_server.persistence.schema import (
    Base,
    HistoryAclRow,
    HistoryRow,
    LineageEdgeRow,
    LineageNodeRow,
    OkugakiRow,
)


def _history_row(item_id: str, user_id: str) -> HistoryRow:
    return HistoryRow(
        id=item_id,
        user_id=user_id,
        at=1,
        input="work",
        score="{}",
        svg="<svg/>",
        trashed=0,
        for_share=0,
        share_group_id=None,
    )


def _writer_or_skip():
    owner = getattr(history, "HistoryOwnedDataPurgeWriter", None)
    if owner is None:
        pytest.skip("production owner is intentionally absent during fail-first")
    return owner


def test_history_owned_data_purge_writer_owns_delete_all_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = getattr(history, "HistoryOwnedDataPurgeWriter", None)
    assert owner is not None, "HistoryOwnedDataPurgeWriter must own delete_all"
    assert is_dataclass(owner) and owner.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        owner(None, None, None).session_factory = None
    assert str(inspect.signature(owner.delete_all)) == "(self, user_id: 'str') -> 'None'"
    assert str(inspect.signature(db.delete_all)) == "(user_id: 'str') -> 'None'"

    facade = ast.parse(inspect.getsource(db.delete_all)).body[0]
    assert isinstance(facade, ast.FunctionDef)
    assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    facade_source = inspect.getsource(db.delete_all)
    assert "_history.HistoryOwnedDataPurgeWriter(" in facade_source
    for dependency in ("SessionLocal", "_owner_actor", "_delete_acl_for_histories"):
        assert dependency in facade_source
    assert ").delete_all(user_id)" in facade_source
    assert "session.query" not in facade_source

    owner_source = inspect.getsource(owner)
    assert "access._owned_by(owner, HistoryRow.user_id)" in owner_source
    for row_type in ("OkugakiRow", "LineageEdgeRow", "LineageNodeRow", "HistoryRow"):
        assert f"session.query({row_type})" in owner_source
    assert "db" not in owner_source

    calls: list[tuple[tuple[object, ...], str]] = []

    class RecordingWriter:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def delete_all(self, user_id: str) -> str:
            calls.append((self.dependencies, user_id))
            return "sentinel"

    monkeypatch.setattr(db._history, "HistoryOwnedDataPurgeWriter", RecordingWriter)
    first_dependencies = (object(), object(), object())
    for name, dependency in zip(
        ("SessionLocal", "_owner_actor", "_delete_acl_for_histories"),
        first_dependencies,
        strict=True,
    ):
        monkeypatch.setattr(db, name, dependency)
    assert db.delete_all("actor") == "sentinel"

    second_dependencies = (object(), object(), object())
    for name, dependency in zip(
        ("SessionLocal", "_owner_actor", "_delete_acl_for_histories"),
        second_dependencies,
        strict=True,
    ):
        monkeypatch.setattr(db, name, dependency)
    assert db.delete_all("later") == "sentinel"
    assert calls == [(first_dependencies, "actor"), (second_dependencies, "later")]


def test_owned_data_purge_deletes_only_the_owners_history_domain_rows() -> None:
    writer_type = _writer_or_skip()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    rows: list[Any] = [
        _history_row("owned-history", "actor"),
        _history_row("other-history", "other"),
        HistoryAclRow(
            id="owned-acl",
            history_id="owned-history",
            subject_type="user",
            subject_id="guest",
            permission="write",
            at=1,
        ),
        HistoryAclRow(
            id="other-acl",
            history_id="other-history",
            subject_type="user",
            subject_id="actor",
            permission="write",
            at=1,
        ),
        LineageNodeRow(id="owned-node-a", user_id="actor", state="active", at=1),
        LineageNodeRow(id="owned-node-b", user_id="actor", state="active", at=2),
        LineageNodeRow(id="other-node-a", user_id="other", state="active", at=1),
        LineageNodeRow(id="other-node-b", user_id="other", state="active", at=2),
        LineageEdgeRow(
            id="owned-edge",
            user_id="actor",
            parent_node_id="owned-node-a",
            child_node_id="owned-node-b",
            derivation_kind="replay",
            metadata_json="{}",
            at=2,
        ),
        LineageEdgeRow(
            id="other-edge",
            user_id="other",
            parent_node_id="other-node-a",
            child_node_id="other-node-b",
            derivation_kind="replay",
            metadata_json="{}",
            at=2,
        ),
        OkugakiRow(
            id="owned-okugaki",
            user_id="actor",
            target_node_id="owned-node-a",
            branch_snapshot_json="[]",
            model="model",
            at=1,
            language="ja",
            body="owned",
            warnings_json="[]",
            fact_sheet_json="{}",
        ),
        OkugakiRow(
            id="other-okugaki",
            user_id="other",
            target_node_id="other-node-a",
            branch_snapshot_json="[]",
            model="model",
            at=1,
            language="ja",
            body="other",
            warnings_json="[]",
            fact_sheet_json="{}",
        ),
    ]
    with sessions() as session:
        session.add_all(rows)
        session.commit()

    acl_calls: list[list[str]] = []

    def delete_acl(session, history_ids: list[str]) -> None:
        acl_calls.append(list(history_ids))
        if history_ids:
            session.query(HistoryAclRow).filter(HistoryAclRow.history_id.in_(history_ids)).delete(
                synchronize_session=False
            )

    actor = {
        "id": "actor",
        "permission_groups": ["admins", "leaders"],
        "group_id": "shared-group",
    }
    writer = writer_type(sessions, lambda _user_id: actor, delete_acl)
    assert writer.delete_all("actor") is None
    assert acl_calls == [["owned-history"]]

    with sessions() as session:
        assert session.get(HistoryRow, "owned-history") is None
        assert session.get(HistoryAclRow, "owned-acl") is None
        assert session.get(OkugakiRow, "owned-okugaki") is None
        assert session.get(LineageEdgeRow, "owned-edge") is None
        assert session.get(LineageNodeRow, "owned-node-a") is None
        assert session.get(LineageNodeRow, "owned-node-b") is None

        assert session.get(HistoryRow, "other-history") is not None
        assert session.get(HistoryAclRow, "other-acl") is not None
        assert session.get(OkugakiRow, "other-okugaki") is not None
        assert session.get(LineageEdgeRow, "other-edge") is not None
        assert session.get(LineageNodeRow, "other-node-a") is not None
        assert session.get(LineageNodeRow, "other-node-b") is not None


def test_owned_data_purge_preserves_order_commit_and_empty_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer_type = _writer_or_skip()

    def run(ids: list[str]) -> list[object]:
        events: list[object] = []

        class Query:
            def __init__(self, target: object) -> None:
                self.target = target

            def filter(self, condition: object) -> Query:
                events.append(("filter", self.target, condition))
                return self

            def __iter__(self):
                events.append(("iterate", self.target))
                return iter((item_id,) for item_id in ids)

            def delete(self) -> int:
                events.append(("delete", self.target))
                return 1

        class Session:
            def __enter__(self) -> Session:
                events.append("enter")
                return self

            def __exit__(self, *_args: object) -> None:
                events.append("exit")

            def query(self, target: object) -> Query:
                events.append(("query", target))
                return Query(target)

            def commit(self) -> None:
                events.append("commit")

        def owner_actor(user_id: str) -> dict:
            events.append(("owner", user_id))
            return {"id": user_id}

        def session_factory() -> Session:
            events.append("session")
            return Session()

        def delete_acl(_session: Session, history_ids: list[str]) -> None:
            events.append(("acl", list(history_ids)))

        predicates: list[tuple[dict, object]] = []

        def owned_by(owner: dict, column: object) -> object:
            predicates.append((owner, column))
            return ("owned", column)

        monkeypatch.setattr(history.access, "_owned_by", owned_by)
        writer = writer_type(session_factory, owner_actor, delete_acl)
        assert writer.delete_all("actor") is None
        assert len(predicates) == 5
        assert all(owner == {"id": "actor"} for owner, _column in predicates)
        return events

    for ids in (["second", "first", "second"], []):
        events = run(ids)
        assert events[0:3] == [("owner", "actor"), "session", "enter"]
        assert ("acl", ids) in events
        assert [event for event in events if isinstance(event, tuple) and event[0] == "delete"] == [
            ("delete", OkugakiRow),
            ("delete", LineageEdgeRow),
            ("delete", LineageNodeRow),
            ("delete", HistoryRow),
        ]
        acl_index = events.index(("acl", ids))
        first_delete = events.index(("delete", OkugakiRow))
        assert acl_index < first_delete < events.index("commit") < events.index("exit")
        assert events.count("commit") == 1


def test_owned_data_purge_propagates_each_dependency_failure_without_retry() -> None:
    writer_type = _writer_or_skip()

    class IntendedFailure(RuntimeError):
        pass

    for fail_at in ("owner", "session", "query", "acl", "delete", "commit"):
        events: list[str] = []

        class Query:
            def __init__(self, target: object) -> None:
                self.target = target

            def filter(self, _condition: object) -> Query:
                events.append("filter")
                return self

            def __iter__(self):
                return iter([("owned",)])

            def delete(self) -> int:
                events.append(f"delete:{getattr(self.target, '__name__', self.target)}")
                if fail_at == "delete":
                    raise IntendedFailure("delete")
                return 1

        class Session:
            def __enter__(self) -> Session:
                events.append("enter")
                return self

            def __exit__(self, *_args: object) -> None:
                events.append("exit")

            def query(self, target: object) -> Query:
                events.append("query")
                if fail_at == "query":
                    raise IntendedFailure("query")
                return Query(target)

            def commit(self) -> None:
                events.append("commit")
                if fail_at == "commit":
                    raise IntendedFailure("commit")

        def owner_actor(user_id: str) -> dict:
            events.append("owner")
            if fail_at == "owner":
                raise IntendedFailure("owner")
            return {"id": user_id}

        def session_factory() -> Session:
            events.append("session")
            if fail_at == "session":
                raise IntendedFailure("session")
            return Session()

        def delete_acl(_session: Session, _ids: list[str]) -> None:
            events.append("acl")
            if fail_at == "acl":
                raise IntendedFailure("acl")

        writer = writer_type(session_factory, owner_actor, delete_acl)
        with pytest.raises(IntendedFailure, match=fail_at):
            writer.delete_all("actor")

        assert events.count("owner") == 1
        assert events.count("session") <= 1
        assert events.count("commit") <= 1
        if fail_at in {"owner", "session", "query", "acl", "delete"}:
            assert "commit" not in events
        if fail_at == "owner":
            assert events == ["owner"]
        elif fail_at == "session":
            assert events == ["owner", "session"]
        elif fail_at == "query":
            assert "acl" not in events
        elif fail_at == "acl":
            assert not any(event.startswith("delete:") for event in events)
