"""Direct ownership and transaction coverage for selected permanent deletion."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

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
)


def _row(
    item_id: str,
    user_id: str,
    *,
    trashed: int,
    node_id: str | None = None,
) -> HistoryRow:
    return HistoryRow(
        id=item_id,
        user_id=user_id,
        at=1,
        input="work",
        score="{}",
        svg="<svg/>",
        trashed=trashed,
        lineage_node_id=node_id,
    )


def _node(node_id: str, user_id: str, history_id: str | None) -> LineageNodeRow:
    return LineageNodeRow(
        id=node_id,
        user_id=user_id,
        history_id=history_id,
        state="active",
        description_hash=f"description-{node_id}",
        render_hash=f"render-{node_id}",
        at=1,
    )


def _edge(edge_id: str, user_id: str, parent_id: str, child_id: str) -> LineageEdgeRow:
    return LineageEdgeRow(
        id=edge_id,
        user_id=user_id,
        parent_node_id=parent_id,
        child_node_id=child_id,
        derivation_kind="replay",
        metadata_json='{"proof":true}',
        at=1,
    )


_FORBIDDEN_HISTORY_IMPORT_PARTS = {
    "api_core",
    "config",
    "db",
    "engine",
    "renderer",
    "render_engines",
    "router",
    "search",
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


def test_history_permanent_delete_writer_owns_delete_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = getattr(history, "HistoryPermanentDeleteWriter", None)
    assert owner is not None, "HistoryPermanentDeleteWriter must own selected permanent deletion"
    assert is_dataclass(owner) and owner.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        owner(None, None, None, None).session_factory = None
    expected_signature = (
        "(self, user_id: 'str', ids: 'list[str]', *, "
        "require_trashed: 'bool' = False) -> 'int'"
    )
    assert str(inspect.signature(owner.delete_items)) == expected_signature
    assert str(inspect.signature(db.delete_items)) == (
        "(user_id: 'str', ids: 'list[str]', *, require_trashed: 'bool' = False) -> 'int'"
    )

    facade = ast.parse(inspect.getsource(db.delete_items)).body[0]
    assert isinstance(facade, ast.FunctionDef)
    assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    facade_source = inspect.getsource(db.delete_items)
    assert "_history.HistoryPermanentDeleteWriter(" in facade_source
    for dependency in ("SessionLocal", "_actor_of", "_now_ms", "_delete_acl_for_histories"):
        assert dependency in facade_source
    assert ").delete_items(user_id, ids, require_trashed=require_trashed)" in facade_source
    assert "session.query" not in facade_source

    owner_source = inspect.getsource(owner)
    assert "access._writable_by(actor, HistoryRow.user_id, HistoryRow.id)" in owner_source
    assert "HistoryRow.id.in_(ids)" in owner_source
    assert "HistoryRow.trashed == 1" in owner_source
    assert "LineageEdgeRow.parent_node_id.in_(node_ids)" in owner_source
    assert "LineageEdgeRow.child_node_id.in_(node_ids)" in owner_source
    assert "self.delete_acl_for_histories_fn(session, [row.id for row in rows])" in owner_source
    assert "return len(rows)" in owner_source
    assert all(
        not (set(target.lstrip(".").split(".")) & _FORBIDDEN_HISTORY_IMPORT_PARTS)
        for target in _import_targets(inspect.getsource(history))
    )

    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    class RecordingWriter:
        def __init__(self, *dependencies: object) -> None:
            calls.append(("dependencies", dependencies, {}))

        def delete_items(self, *args: object, **kwargs: object) -> int:
            calls.append(("delete", args, kwargs))
            return 7

    monkeypatch.setattr(db._history, "HistoryPermanentDeleteWriter", RecordingWriter)
    dependencies = (object(), object(), object(), object())
    for name, dependency in zip(
        ("SessionLocal", "_actor_of", "_now_ms", "_delete_acl_for_histories"),
        dependencies,
        strict=True,
    ):
        monkeypatch.setattr(db, name, dependency)
    assert db.delete_items("actor", ["item"], require_trashed=True) == 7
    later_dependencies = (object(), object(), object(), object())
    for name, dependency in zip(
        ("SessionLocal", "_actor_of", "_now_ms", "_delete_acl_for_histories"),
        later_dependencies,
        strict=True,
    ):
        monkeypatch.setattr(db, name, dependency)
    assert db.delete_items("later", ["other"]) == 7
    assert calls == [
        ("dependencies", dependencies, {}),
        ("delete", ("actor", ["item"]), {"require_trashed": True}),
        ("dependencies", later_dependencies, {}),
        ("delete", ("later", ["other"]), {"require_trashed": False}),
    ]


def test_permanent_delete_empty_ids_use_no_dependencies() -> None:
    def fail(*_args: object) -> object:
        pytest.fail("empty deletion used a dependency")

    writer = history.HistoryPermanentDeleteWriter(fail, fail, fail, fail)
    assert writer.delete_items("actor", []) == 0


def test_permanent_delete_preserves_access_trash_lineage_acl_and_count() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    actors = {
        "owner": {"id": "owner", "permission_groups": [], "group_id": "group"},
        "admin": {"id": "admin", "permission_groups": ["admins"], "group_id": None},
        "writer": {"id": "writer", "permission_groups": [], "group_id": None},
        "reader": {"id": "reader", "permission_groups": [], "group_id": None},
        "leader": {"id": "leader", "permission_groups": ["leaders"], "group_id": "group"},
        "outsider": {"id": "outsider", "permission_groups": [], "group_id": None},
    }
    rows = [
        _row("owner-delete", "owner", trashed=1, node_id="selected-node"),
        _row("owner-no-node", "owner", trashed=1),
        _row("owner-active", "owner", trashed=0),
        _row("write-delete", "owner", trashed=1, node_id="write-node"),
        _row("read-row", "owner", trashed=1),
        _row("leader-row", "owner", trashed=1),
        _row("admin-delete", "other-owner", trashed=1),
    ]
    nodes = [
        _node("parent-node", "owner", None),
        _node("selected-node", "owner", "owner-delete"),
        _node("child-node", "owner", None),
        _node("write-node", "owner", "write-delete"),
        _node("unrelated-parent", "owner", None),
        _node("unrelated-child", "owner", None),
    ]
    edges = [
        _edge("parent-edge", "owner", "parent-node", "selected-node"),
        _edge("child-edge", "owner", "selected-node", "child-node"),
        _edge("unrelated-edge", "owner", "unrelated-parent", "unrelated-child"),
    ]
    acl_rows = [
        HistoryAclRow(
            id=f"acl-{item_id}",
            history_id=item_id,
            subject_type="user",
            subject_id=subject_id,
            permission=permission,
            at=1,
        )
        for item_id, subject_id, permission in (
            ("owner-delete", "reader", "read"),
            ("owner-no-node", "reader", "read"),
            ("owner-active", "reader", "read"),
            ("write-delete", "writer", "write"),
            ("read-row", "reader", "read"),
        )
    ]
    with sessions() as session:
        session.add_all([*rows, *nodes, *edges, *acl_rows])
        session.commit()

    cleanup_calls: list[list[str]] = []
    clock_calls: list[int] = []

    def now_ms() -> int:
        clock_calls.append(404_000)
        return 404_000

    def cleanup(session: object, ids: list[str]) -> None:
        cleanup_calls.append(list(ids))
        if ids:
            session.query(HistoryAclRow).filter(HistoryAclRow.history_id.in_(ids)).delete(
                synchronize_session=False
            )

    writer = history.HistoryPermanentDeleteWriter(sessions, actors.__getitem__, now_ms, cleanup)

    assert writer.delete_items(
        "owner",
        ["owner-delete", "owner-no-node", "owner-active", "missing"],
        require_trashed=True,
    ) == 2
    assert set(cleanup_calls[-1]) == {"owner-delete", "owner-no-node"}
    assert writer.delete_items("reader", ["read-row"]) == 0
    assert cleanup_calls[-1] == []
    assert writer.delete_items("leader", ["leader-row"]) == 0
    assert cleanup_calls[-1] == []
    assert writer.delete_items("outsider", ["leader-row"]) == 0
    assert cleanup_calls[-1] == []
    assert writer.delete_items("writer", ["write-delete"], require_trashed=True) == 1
    assert cleanup_calls[-1] == ["write-delete"]
    assert writer.delete_items("admin", ["admin-delete"], require_trashed=True) == 1
    assert cleanup_calls[-1] == ["admin-delete"]
    assert len(clock_calls) == 6

    with sessions() as session:
        assert session.get(HistoryRow, "owner-delete") is None
        assert session.get(HistoryRow, "owner-no-node") is None
        assert session.get(HistoryRow, "write-delete") is None
        assert session.get(HistoryRow, "admin-delete") is None
        assert session.get(HistoryRow, "owner-active") is not None
        assert session.get(HistoryRow, "read-row") is not None
        assert session.get(HistoryRow, "leader-row") is not None
        selected = session.get(LineageNodeRow, "selected-node")
        write_node = session.get(LineageNodeRow, "write-node")
        for node in (selected, write_node):
            assert node is not None
            assert node.state == "tombstone"
            assert node.history_id is None
            assert node.description_hash is None
            assert node.render_hash is None
            assert node.deleted_at == 404_000
        assert session.get(LineageEdgeRow, "parent-edge").metadata_json == "{}"
        assert session.get(LineageEdgeRow, "child-edge").metadata_json == "{}"
        assert session.get(LineageEdgeRow, "unrelated-edge").metadata_json == '{"proof":true}'
        remaining_acl_ids = {
            row.history_id for row in session.query(HistoryAclRow).all()
        }
        assert remaining_acl_ids == {"owner-active", "read-row"}


class _RecordingQuery:
    def __init__(self, session: "_RecordingSession", model: object) -> None:
        self.session = session
        self.model = model

    def filter(self, *clauses: object) -> "_RecordingQuery":
        self.session.events.append(("filter", self.model, len(clauses)))
        return self

    def all(self) -> list[object]:
        self.session.events.append(("all", self.model))
        if self.model is HistoryRow:
            return list(self.session.rows)
        if self.model is LineageNodeRow:
            return list(self.session.nodes)
        if self.model is LineageEdgeRow:
            return list(self.session.edges)
        raise AssertionError(f"unexpected query model: {self.model}")


class _RecordingSession:
    def __init__(
        self,
        events: list[object],
        *,
        rows: list[object],
        nodes: list[object] | None = None,
        edges: list[object] | None = None,
        fail_at: str | None = None,
    ) -> None:
        self.events = events
        self.rows = rows
        self.nodes = nodes or []
        self.edges = edges or []
        self.fail_at = fail_at

    def __enter__(self) -> "_RecordingSession":
        self.events.append("enter")
        return self

    def __exit__(self, exc_type: object, *_args: object) -> None:
        self.events.append(("exit", exc_type))

    def query(self, model: object) -> _RecordingQuery:
        self.events.append(("query", model))
        if self.fail_at == "query":
            raise RuntimeError("query failure")
        return _RecordingQuery(self, model)

    def delete(self, row: object) -> None:
        self.events.append(("delete", row.id))
        if self.fail_at == "delete":
            raise RuntimeError("delete failure")

    def commit(self) -> None:
        self.events.append("commit-attempt")
        if self.fail_at == "commit":
            raise RuntimeError("commit failure")
        self.events.append("commit-ok")


def test_permanent_delete_keeps_mutation_order_zero_match_and_sibling_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    row = SimpleNamespace(id="selected", lineage_node_id="selected-node")
    node = SimpleNamespace(
        state="active",
        history_id="selected",
        description_hash="description",
        render_hash="render",
        deleted_at=None,
    )
    parent_edge = SimpleNamespace(metadata_json='{"parent":true}')
    child_edge = SimpleNamespace(metadata_json='{"child":true}')
    session = _RecordingSession(
        events,
        rows=[row],
        nodes=[node],
        edges=[parent_edge, child_edge],
    )

    monkeypatch.setattr(
        history.access,
        "_writable_by",
        lambda *args: events.append(("writable", args)) or object(),
    )

    def cleanup(_session: object, ids: list[str]) -> None:
        events.append(("acl", list(ids)))

    writer = history.HistoryPermanentDeleteWriter(
        lambda: events.append("session") or session,
        lambda user_id: events.append(("actor", user_id)) or {"id": user_id},
        lambda: events.append("clock") or 404,
        cleanup,
    )
    assert writer.delete_items("writer", ["selected"], require_trashed=True) == 1
    assert node.state == "tombstone"
    assert node.history_id is None
    assert node.description_hash is None
    assert node.render_hash is None
    assert node.deleted_at == 404
    assert parent_edge.metadata_json == child_edge.metadata_json == "{}"
    assert events.index(("acl", ["selected"])) < events.index(("delete", "selected"))
    assert events.index(("delete", "selected")) < events.index("commit-attempt")
    assert events.count("commit-attempt") == events.count("commit-ok") == 1
    writable = next(event for event in events if isinstance(event, tuple) and event[0] == "writable")
    assert writable[1] == ({"id": "writer"}, HistoryRow.user_id, HistoryRow.id)

    events.clear()
    zero_session = _RecordingSession(events, rows=[])
    zero_writer = history.HistoryPermanentDeleteWriter(
        lambda: zero_session,
        lambda _user_id: {"id": "actor"},
        lambda: events.append("clock") or 405,
        cleanup,
    )
    assert zero_writer.delete_items("actor", ["missing"]) == 0
    assert "clock" in events
    assert ("acl", []) in events
    assert events.index(("acl", [])) < events.index("commit-attempt")
    assert events.count("commit-attempt") == events.count("commit-ok") == 1


@pytest.mark.parametrize("fail_at", ["actor", "session", "query", "clock", "cleanup", "delete", "commit"])
def test_permanent_delete_propagates_failures_without_false_success(
    fail_at: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    row = SimpleNamespace(id="selected", lineage_node_id=None)
    session = _RecordingSession(events, rows=[row], fail_at=fail_at)
    monkeypatch.setattr(history.access, "_writable_by", lambda *_args: object())

    def actor_of(user_id: str) -> dict:
        events.append(("actor", user_id))
        if fail_at == "actor":
            raise RuntimeError("actor failure")
        return {"id": user_id}

    def session_factory() -> _RecordingSession:
        events.append("session")
        if fail_at == "session":
            raise RuntimeError("session failure")
        return session

    def now_ms() -> int:
        events.append("clock")
        if fail_at == "clock":
            raise RuntimeError("clock failure")
        return 404

    def cleanup(_session: object, ids: list[str]) -> None:
        events.append(("acl", list(ids)))
        if fail_at == "cleanup":
            raise RuntimeError("cleanup failure")

    writer = history.HistoryPermanentDeleteWriter(session_factory, actor_of, now_ms, cleanup)
    with pytest.raises(RuntimeError, match=rf"^{fail_at} failure$"):
        writer.delete_items("actor", ["selected"])
    assert "commit-ok" not in events
    if fail_at != "commit":
        assert "commit-attempt" not in events
    else:
        assert events.count("commit-attempt") == 1
    if fail_at in {"query", "clock", "cleanup", "delete", "commit"}:
        assert any(
            isinstance(event, tuple) and event[0] == "exit" and event[1] is RuntimeError
            for event in events
        )
