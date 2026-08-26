"""Direct ownership coverage for owner-scoped trash purge selection."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence import history
from inku_server.persistence.schema import Base, HistoryAclRow, HistoryRow


def _row(
    item_id: str,
    user_id: str,
    *,
    trashed: int,
    for_share: int = 0,
    share_group_id: str | None = None,
) -> HistoryRow:
    return HistoryRow(
        id=item_id,
        user_id=user_id,
        at=1,
        input="work",
        score="{}",
        svg="<svg/>",
        trashed=trashed,
        for_share=for_share,
        share_group_id=share_group_id,
    )


_FORBIDDEN_HISTORY_IMPORT_PARTS = {
    "accounts",
    "api_core",
    "config",
    "db",
    "delete_all",
    "engine",
    "okugaki",
    "renderer",
    "render_engines",
    "router",
}


def _import_targets(source: str) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            module_prefix = f"{prefix}{node.module}." if node.module else prefix
            targets.update(f"{module_prefix}{alias.name}" for alias in node.names)
    return targets


def test_history_trash_purge_writer_owns_selection_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = getattr(history, "HistoryTrashPurgeWriter", None)
    assert owner is not None, "HistoryTrashPurgeWriter must own trash purge selection"
    assert is_dataclass(owner) and owner.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        owner(None, None, None).session_factory = None
    assert str(inspect.signature(owner.delete_all_trashed_items)) == (
        "(self, user_id: 'str') -> 'int'"
    )
    assert str(inspect.signature(db.delete_all_trashed_items)) == "(user_id: 'str') -> 'int'"

    facade = ast.parse(inspect.getsource(db.delete_all_trashed_items)).body[0]
    assert isinstance(facade, ast.FunctionDef)
    assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    facade_source = inspect.getsource(db.delete_all_trashed_items)
    assert "_history.HistoryTrashPurgeWriter(" in facade_source
    for dependency in ("SessionLocal", "_owner_actor", "delete_items"):
        assert dependency in facade_source
    assert ").delete_all_trashed_items(user_id)" in facade_source
    assert "session.query" not in facade_source

    owner_source = inspect.getsource(owner)
    assert "access._owned_by(owner, HistoryRow.user_id)" in owner_source
    assert "HistoryRow.trashed == 1" in owner_source
    assert "session.query(HistoryRow.id)" in owner_source
    assert "access._writable_by" not in owner_source
    assert "Ownership, not write permission" in owner_source
    assert "return self.delete_items_fn(user_id, ids, require_trashed=True)" in owner_source
    assert all(
        not (set(target.lstrip(".").split(".")) & _FORBIDDEN_HISTORY_IMPORT_PARTS)
        for target in _import_targets(inspect.getsource(history))
    )

    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    class RecordingWriter:
        def __init__(self, *dependencies: object) -> None:
            calls.append(("dependencies", dependencies, {}))

        def delete_all_trashed_items(self, *args: object, **kwargs: object) -> int:
            calls.append(("delete", args, kwargs))
            return 17

    monkeypatch.setattr(db._history, "HistoryTrashPurgeWriter", RecordingWriter)
    first_dependencies = (object(), object(), object())
    for name, dependency in zip(
        ("SessionLocal", "_owner_actor", "delete_items"),
        first_dependencies,
        strict=True,
    ):
        monkeypatch.setattr(db, name, dependency)
    assert db.delete_all_trashed_items("actor") == 17
    later_dependencies = (object(), object(), object())
    for name, dependency in zip(
        ("SessionLocal", "_owner_actor", "delete_items"),
        later_dependencies,
        strict=True,
    ):
        monkeypatch.setattr(db, name, dependency)
    assert db.delete_all_trashed_items("later") == 17
    assert calls == [
        ("dependencies", first_dependencies, {}),
        ("delete", ("actor",), {}),
        ("dependencies", later_dependencies, {}),
        ("delete", ("later",), {}),
    ]


def test_trash_purge_selects_only_owned_trashed_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    rows = [
        _row("owned-trash-a", "actor", trashed=1),
        _row("owned-trash-b", "actor", trashed=1),
        _row("owned-active", "actor", trashed=0),
        _row("other-trash", "other", trashed=1),
        _row("same-group-trash", "group-member", trashed=1, for_share=1, share_group_id="group"),
        _row("read-acl-trash", "reader-owner", trashed=1),
        _row("write-acl-trash", "writer-owner", trashed=1),
    ]
    acl_rows = [
        HistoryAclRow(
            id=f"acl-{permission}",
            history_id=item_id,
            subject_type="user",
            subject_id="actor",
            permission=permission,
            at=1,
        )
        for item_id, permission in (
            ("read-acl-trash", "read"),
            ("write-acl-trash", "write"),
        )
    ]
    with sessions() as session:
        session.add_all([*rows, *acl_rows])
        session.commit()

    actor = {
        "id": "actor",
        "permission_groups": ["admins", "leaders"],
        "group_id": "group",
    }
    calls: list[tuple[str, list[str], bool]] = []

    def delete_items(user_id: str, ids: list[str], *, require_trashed: bool) -> int:
        calls.append((user_id, list(ids), require_trashed))
        return len(ids)

    writer = history.HistoryTrashPurgeWriter(sessions, lambda _user_id: actor, delete_items)
    assert writer.delete_all_trashed_items("actor") == 2
    assert len(calls) == 1
    user_id, selected, require_trashed = calls[0]
    assert user_id == "actor"
    assert set(selected) == {"owned-trash-a", "owned-trash-b"}
    assert "owned-active" not in selected
    assert "other-trash" not in selected
    assert "same-group-trash" not in selected
    assert "read-acl-trash" not in selected
    assert "write-acl-trash" not in selected
    assert require_trashed is True


def test_trash_purge_preserves_query_order_session_boundary_and_empty_delegation() -> None:
    events: list[str] = []

    class Query:
        def filter(self, *filters: object) -> Query:
            events.append("filter")
            assert len(filters) == 2
            return self

        def __iter__(self):
            events.append("iterate")
            return iter([("second",), ("first",), ("second",)])

    class Session:
        exited = False

        def __enter__(self) -> Session:
            events.append("enter")
            return self

        def __exit__(self, *_args: object) -> None:
            self.exited = True
            events.append("exit")

        def query(self, *columns: object) -> Query:
            events.append("query")
            assert columns == (HistoryRow.id,)
            return Query()

    session = Session()

    def owner_actor(user_id: str) -> dict:
        events.append("owner")
        assert user_id == "actor"
        return {"id": user_id}

    def session_factory() -> Session:
        events.append("session")
        return session

    def delete_items(user_id: str, ids: list[str], *, require_trashed: bool) -> int:
        events.append("delete")
        assert session.exited
        assert user_id == "actor"
        assert ids == ["second", "first", "second"]
        assert require_trashed is True
        return 405

    writer = history.HistoryTrashPurgeWriter(session_factory, owner_actor, delete_items)
    assert writer.delete_all_trashed_items("actor") == 405
    assert events == ["owner", "session", "enter", "query", "filter", "iterate", "exit", "delete"]

    empty_calls: list[tuple[str, list[str], bool]] = []

    class EmptyQuery(Query):
        def __iter__(self):
            return iter(())

    class EmptySession(Session):
        def query(self, *columns: object) -> EmptyQuery:
            assert columns == (HistoryRow.id,)
            return EmptyQuery()

    def delete_empty(user_id: str, ids: list[str], *, require_trashed: bool) -> int:
        empty_calls.append((user_id, list(ids), require_trashed))
        return 0

    empty_writer = history.HistoryTrashPurgeWriter(
        EmptySession,
        lambda user_id: {"id": user_id},
        delete_empty,
    )
    assert empty_writer.delete_all_trashed_items("empty") == 0
    assert empty_calls == [("empty", [], True)]


def test_trash_purge_propagates_dependency_exceptions_without_retry() -> None:
    calls = {"owner": 0, "session": 0, "delete": 0}

    def fail_owner(_user_id: str) -> dict:
        calls["owner"] += 1
        raise RuntimeError("owner")

    def unused_session() -> object:
        calls["session"] += 1
        pytest.fail("owner failure opened a session")

    def unused_delete(*_args: object, **_kwargs: object) -> int:
        calls["delete"] += 1
        pytest.fail("selection failure delegated deletion")

    with pytest.raises(RuntimeError, match="owner"):
        history.HistoryTrashPurgeWriter(
            unused_session,
            fail_owner,
            unused_delete,
        ).delete_all_trashed_items("actor")
    assert calls == {"owner": 1, "session": 0, "delete": 0}

    class QueryFailureSession:
        def __enter__(self) -> QueryFailureSession:
            calls["session"] += 1
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def query(self, *_columns: object) -> object:
            raise LookupError("query")

    with pytest.raises(LookupError, match="query"):
        history.HistoryTrashPurgeWriter(
            QueryFailureSession,
            lambda _user_id: {"id": "actor"},
            unused_delete,
        ).delete_all_trashed_items("actor")
    assert calls["session"] == 1
    assert calls["delete"] == 0

    class EmptySession:
        def __enter__(self) -> EmptySession:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def query(self, *_columns: object) -> EmptySession:
            return self

        def filter(self, *_filters: object) -> EmptySession:
            return self

        def __iter__(self):
            return iter(())

    def fail_delete(*_args: object, **_kwargs: object) -> int:
        calls["delete"] += 1
        raise ValueError("delete")

    with pytest.raises(ValueError, match="delete"):
        history.HistoryTrashPurgeWriter(
            EmptySession,
            lambda _user_id: {"id": "actor"},
            fail_delete,
        ).delete_all_trashed_items("actor")
    assert calls["delete"] == 1
