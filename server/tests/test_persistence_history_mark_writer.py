"""Direct ownership and authenticated PATCH coverage for history marks."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace
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


def _row(item_id: str, user_id: str, *, note: str | None = None) -> HistoryRow:
    return HistoryRow(
        id=item_id,
        user_id=user_id,
        at=1,
        input="work",
        score="{}",
        svg="<svg/>",
        note=note,
    )


def _project(row: HistoryRow) -> dict:
    return {
        "id": row.id,
        "starred": bool(row.starred),
        "for_revision": bool(row.for_revision),
        "note": row.note,
    }


def test_history_mark_writer_owns_both_marks_and_db_delegates() -> None:
    owner = getattr(history, "HistoryMarkWriter", None)
    assert owner is not None, "HistoryMarkWriter must own history mark writes"
    assert is_dataclass(owner)
    assert owner.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        owner(None, None, None).session_factory = None

    assert str(inspect.signature(db.set_item_starred)) == (
        "(user_id: 'str', item_id: 'str', starred: 'bool', note: 'str | None' = None) -> 'dict | None'"
    )
    assert str(inspect.signature(db.set_item_for_revision)) == (
        "(user_id: 'str', item_id: 'str', for_revision: 'bool') -> 'dict | None'"
    )
    for facade_name, method_name in (
        ("set_item_starred", "set_item_starred"),
        ("set_item_for_revision", "set_item_for_revision"),
    ):
        tree = ast.parse(inspect.getsource(getattr(db, facade_name)))
        function = tree.body[0]
        assert isinstance(function, ast.FunctionDef)
        assert len(function.body) == 1
        assert isinstance(function.body[0], ast.Return)
        source = inspect.getsource(getattr(db, facade_name))
        assert "_history.HistoryMarkWriter(SessionLocal, _actor_of, _row_to_dict)" in source
        assert f").{method_name}(" in source
        assert "session.query" not in source

    owner_source = inspect.getsource(owner)
    writable = "access._writable_by(actor, HistoryRow.user_id, HistoryRow.id)"
    assert owner_source.count(writable) == 2
    assert "clean_note = note.strip()[:240]" in owner_source
    assert "row.note = clean_note or None" in owner_source
    assert "Independent of starred: neither reads the other." in owner_source
    module_source = inspect.getsource(history)
    for forbidden in (
        "from inku_server import db",
        "api_core.routers",
        "persistence.engine",
        "persistence.config",
        "persistence.search",
        "persistence.lineage",
    ):
        assert forbidden not in module_source


def test_mark_facades_resolve_dependencies_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class RecordingWriter:
        def __init__(self, *dependencies: object) -> None:
            calls.append(("dependencies", dependencies))

        def set_item_starred(self, *arguments: object) -> dict:
            calls.append(("starred", arguments))
            return {"mark": "starred"}

        def set_item_for_revision(self, *arguments: object) -> dict:
            calls.append(("revision", arguments))
            return {"mark": "revision"}

    first_dependencies = (object(), object(), object())
    second_dependencies = (object(), object(), object())
    monkeypatch.setattr(db._history, "HistoryMarkWriter", RecordingWriter)
    monkeypatch.setattr(db, "SessionLocal", first_dependencies[0])
    monkeypatch.setattr(db, "_actor_of", first_dependencies[1])
    monkeypatch.setattr(db, "_row_to_dict", first_dependencies[2])
    assert db.set_item_starred("user", "item", True, " note ") == {"mark": "starred"}
    monkeypatch.setattr(db, "SessionLocal", second_dependencies[0])
    monkeypatch.setattr(db, "_actor_of", second_dependencies[1])
    monkeypatch.setattr(db, "_row_to_dict", second_dependencies[2])
    assert db.set_item_for_revision("user", "item", False) == {"mark": "revision"}
    assert calls == [
        ("dependencies", first_dependencies),
        ("starred", ("user", "item", True, " note ")),
        ("dependencies", second_dependencies),
        ("revision", ("user", "item", False)),
    ]


def test_mark_writer_preserves_real_sqlalchemy_access_state_and_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        session.add(_row("item", "owner", note="keep"))
        session.add(
            HistoryAclRow(
                id="read-acl", history_id="item", subject_type="user", subject_id="reader", permission="read", at=1
            )
        )
        session.add(
            HistoryAclRow(
                id="write-acl", history_id="item", subject_type="user", subject_id="writer", permission="write", at=1
            )
        )
        session.commit()

    writer = history.HistoryMarkWriter(sessions, actors.__getitem__, _project)
    assert writer.set_item_starred("owner", "item", True, " " + "x" * 241) == {
        "id": "item",
        "starred": True,
        "for_revision": False,
        "note": "x" * 240,
    }
    assert writer.set_item_starred("owner", "item", False, "   ")["note"] is None
    assert writer.set_item_starred("owner", "item", True, "keep")["note"] == "keep"
    assert writer.set_item_starred("owner", "item", False)["note"] == "keep"
    assert writer.set_item_for_revision("writer", "item", True)["for_revision"] is True
    assert writer.set_item_for_revision("admin", "item", False)["for_revision"] is False
    assert writer.set_item_starred("reader", "item", True) is None
    assert writer.set_item_starred("leader", "item", True) is None
    assert writer.set_item_for_revision("other", "item", True) is None
    assert writer.set_item_for_revision("owner", "missing", True) is None

    events: list[str] = []
    row = SimpleNamespace(id="ordered", starred=0, for_revision=1, note="before")

    class Query:
        def filter(self, *clauses: object) -> "Query":
            events.append("filter")
            return self

        def first(self) -> SimpleNamespace:
            events.append("first")
            return row

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

        def refresh(self, refreshed: object) -> None:
            assert refreshed is row
            events.append("refresh")

    monkeypatch.setattr(history.access, "_writable_by", lambda *arguments: events.append("writable") or True)
    ordered = history.HistoryMarkWriter(lambda: Session(), lambda _: {"id": "owner"}, lambda value: events.append("project") or {"id": value.id})
    assert ordered.set_item_for_revision("owner", "ordered", False) == {"id": "ordered"}
    assert row.starred == 0 and row.for_revision == 0 and row.note == "before"
    assert events == ["query", "writable", "filter", "first", "commit", "refresh", "project"]


def _api_item(user_id: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "at": 1,
        "input": "work",
        "ddl": "背景を白で塗る。",
        "score": {"canvas": "square", "instructions": []},
        "svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
        "history_visibility": "normal",
    }


def _api_user(prefix: str) -> tuple[dict, dict[str, str], str, str]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"{prefix}-group-{suffix}")
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token, group["id"]


def test_authenticated_mark_patches_are_render_free_and_hide_inaccessible_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    owner, owner_headers, owner_token, owner_group = _api_user("mark-owner")
    other, other_headers, other_token, other_group = _api_user("mark-other")
    try:
        item = db.add_item(_api_item(owner["id"]))
        monkeypatch.setattr(
            DefaultRenderEngine,
            "render",
            lambda *args, **kwargs: pytest.fail("render called"),
        )
        starred = client.patch(
            f"/api/history/{item['id']}/star",
            json={"starred": True, "note": " focused "},
            headers=owner_headers,
        )
        revision = client.patch(
            f"/api/history/{item['id']}/for-revision",
            json={"for_revision": True},
            headers=owner_headers,
        )
        inaccessible = client.patch(
            f"/api/history/{item['id']}/star",
            json={"starred": False},
            headers=other_headers,
        )
        missing = client.patch(
            f"/api/history/{uuid.uuid4()}/for-revision",
            json={"for_revision": False},
            headers=owner_headers,
        )
        assert starred.status_code == 200 and starred.json()["note"] == "focused"
        assert revision.status_code == 200 and revision.json()["for_revision"] is True
        assert inaccessible.status_code == 404
        assert missing.status_code == 404
    finally:
        db.delete_all(owner["id"])
        db.delete_session(owner_token)
        db.delete_user(owner["id"])
        db.delete_user_group(owner_group)
        db.delete_all(other["id"])
        db.delete_session(other_token)
        db.delete_user(other["id"])
        db.delete_user_group(other_group)
