"""Direct ownership and authenticated API coverage for history trash state."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.api import app
from inku_server.persistence import history
from inku_server.persistence.schema import Base, HistoryAclRow, HistoryRow
from inku_server.render_engines.default.adapter import DefaultRenderEngine


def _row(item_id: str, user_id: str, *, trashed: int = 0) -> HistoryRow:
    return HistoryRow(id=item_id, user_id=user_id, at=1, input="work", score="{}", svg="<svg/>", trashed=trashed)


_FORBIDDEN_HISTORY_IMPORT_PARTS = {
    "api_core", "config", "db", "engine", "lineage", "renderer", "render_engines", "router", "search",
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


def test_history_trash_state_writer_owns_transitions_and_db_delegates() -> None:
    owner = getattr(history, "HistoryTrashStateWriter", None)
    assert owner is not None, "HistoryTrashStateWriter must own trash-state writes"
    assert is_dataclass(owner) and owner.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        owner(None, None).session_factory = None
    assert str(inspect.signature(owner.trash_items)) == "(self, user_id: 'str', ids: 'list[str]') -> 'int'"
    assert str(inspect.signature(owner.restore_items)) == "(self, user_id: 'str', ids: 'list[str]') -> 'int'"
    for facade_name, method_name in (("trash_items", "trash_items"), ("restore_items", "restore_items")):
        assert str(inspect.signature(getattr(db, facade_name))) == "(user_id: 'str', ids: 'list[str]') -> 'int'"
        facade = ast.parse(inspect.getsource(getattr(db, facade_name))).body[0]
        assert isinstance(facade, ast.FunctionDef) and len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
        source = inspect.getsource(getattr(db, facade_name))
        assert "_history.HistoryTrashStateWriter(SessionLocal, _actor_of)" in source
        assert f").{method_name}(user_id, ids)" in source and "session.query" not in source
    source = inspect.getsource(owner)
    assert source.count("access._writable_by(actor, HistoryRow.user_id, HistoryRow.id)") == 2
    assert source.count("synchronize_session=False") == 2
    restore_source = inspect.getsource(owner.restore_items)
    assert "HistoryRow.trashed == 1" in restore_source
    assert ".update({HistoryRow.trashed: 0}, synchronize_session=False)" in restore_source
    assert all(not (set(target.lstrip(".").split(".")) & _FORBIDDEN_HISTORY_IMPORT_PARTS) for target in _import_targets(inspect.getsource(history)))


def test_trash_facades_resolve_dependencies_at_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class RecordingWriter:
        def __init__(self, *dependencies: object) -> None:
            calls.append(("dependencies", dependencies))

        def trash_items(self, *arguments: object) -> int:
            calls.append(("trash", arguments))
            return 3

        def restore_items(self, *arguments: object) -> int:
            calls.append(("restore", arguments))
            return 4

    monkeypatch.setattr(db._history, "HistoryTrashStateWriter", RecordingWriter)
    first, second = (object(), object()), (object(), object())
    monkeypatch.setattr(db, "SessionLocal", first[0])
    monkeypatch.setattr(db, "_actor_of", first[1])
    assert db.trash_items("first-user", ["first-item"]) == 3
    monkeypatch.setattr(db, "SessionLocal", second[0])
    monkeypatch.setattr(db, "_actor_of", second[1])
    assert db.restore_items("second-user", ["second-item"]) == 4
    assert calls == [
        ("dependencies", first), ("trash", ("first-user", ["first-item"])),
        ("dependencies", second), ("restore", ("second-user", ["second-item"])),
    ]


def test_trash_writer_preserves_sqlalchemy_access_state_count_and_commit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    actors = {
        "owner": {"id": "owner", "permission_groups": [], "group_id": "group"},
        "admin": {"id": "admin", "permission_groups": ["admins"], "group_id": None},
        "leader": {"id": "leader", "permission_groups": ["leaders"], "group_id": "group"},
        "reader": {"id": "reader", "permission_groups": [], "group_id": None},
        "writer": {"id": "writer", "permission_groups": [], "group_id": None},
        "other": {"id": "other", "permission_groups": [], "group_id": None},
    }
    with sessions() as session:
        session.add_all([_row("owned", "owner"), _row("owned-trash", "owner", trashed=1), _row("write", "owner"), _row("read", "owner"), _row("other", "other")])
        session.add_all([
            HistoryAclRow(id="write-acl", history_id="write", subject_type="user", subject_id="writer", permission="write", at=1),
            HistoryAclRow(id="read-acl", history_id="read", subject_type="user", subject_id="reader", permission="read", at=1),
        ])
        session.commit()
    writer = history.HistoryTrashStateWriter(sessions, actors.__getitem__)
    assert writer.trash_items("owner", []) == 0
    assert writer.trash_items("owner", ["owned", "owned-trash", "missing"]) == 1
    assert writer.trash_items("owner", ["owned"]) == 0
    assert writer.restore_items("owner", ["owned", "owned-trash"]) == 2
    assert writer.restore_items("owner", ["owned", "owned-trash"]) == 0
    assert writer.trash_items("writer", ["write"]) == 1
    assert writer.trash_items("admin", ["other"]) == 1
    assert writer.trash_items("reader", ["read"]) == 0
    assert writer.trash_items("leader", ["read"]) == 0
    assert writer.trash_items("other", ["owned"]) == 0


def test_trash_writer_keeps_bulk_order_and_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[object] = []

    class Query:
        def filter(self, *clauses: object) -> "Query":
            events.append("filter")
            return self

        def update(self, values: dict[object, int], *, synchronize_session: bool) -> int:
            events.append(("update", values, synchronize_session))
            return 7

    class Session:
        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def query(self, model: object) -> Query:
            events.append("query")
            return Query()

        def commit(self) -> None:
            events.append("commit")

    monkeypatch.setattr(history.access, "_writable_by", lambda *arguments: events.append(("writable", arguments)) or True)
    writer = history.HistoryTrashStateWriter(
        lambda: events.append("session") or Session(),
        lambda user_id: events.append(("actor", user_id)) or {"id": user_id},
    )
    assert writer.trash_items("owner", ["item"]) == 7
    assert events[0:5] == [("actor", "owner"), "session", "query", ("writable", ({"id": "owner"}, HistoryRow.user_id, HistoryRow.id)), "filter"]
    assert events[-1] == "commit" and events[-2][0] == "update" and events[-2][2] is False
    events.clear()
    assert writer.trash_items("owner", []) == 0 and events == []
    assert writer.restore_items("owner", []) == 0 and events == []

    class FailingSession(Session):
        def commit(self) -> None: raise RuntimeError("commit failure")

    failing = history.HistoryTrashStateWriter(lambda: FailingSession(), lambda _: {"id": "owner"})
    with pytest.raises(RuntimeError, match="^commit failure$"):
        failing.restore_items("owner", ["item"])


def _api_user(prefix: str) -> tuple[dict, dict[str, str], str, str]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"{prefix}-group-{suffix}")
    user = db.add_user(username=f"{prefix}-{suffix}", email=f"{prefix}-{suffix}@example.test", password="password-123", permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token, group["id"]


def test_authenticated_trash_and_restore_keep_response_seam_render_free(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    owner, headers, token, group = _api_user("trash-owner")
    try:
        item = db.add_item({"id": str(uuid.uuid4()), "user_id": owner["id"], "at": 1, "input": "work", "ddl": "背景を白で塗る。", "score": {"canvas": "square", "instructions": []}, "svg": "<svg xmlns='http://www.w3.org/2000/svg'/>", "history_visibility": "normal"})
        monkeypatch.setattr(DefaultRenderEngine, "render", lambda *args, **kwargs: pytest.fail("render called"))
        trashed = client.post("/api/history/trash", json={"ids": [item["id"]]}, headers=headers)
        restored = client.post("/api/history/restore", json={"ids": [item["id"]]}, headers=headers)
        assert trashed.status_code == restored.status_code == 200
        assert trashed.json() == restored.json() == {"ok": True, "count": 1}
    finally:
        db.delete_all(owner["id"])
        db.delete_session(token)
        db.delete_user(owner["id"])
        db.delete_user_group(group)
