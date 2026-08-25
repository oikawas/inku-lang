from __future__ import annotations

import ast
import inspect

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from inku_server import api as api_module, db
from inku_server.api_core.routers import history as history_router
from inku_server.persistence import history
from inku_server.persistence.schema import Base, HistoryAclRow, HistoryRow


def test_history_item_position_reader_owns_the_exact_query_and_db_is_thin_facade() -> None:
    reader = history.HistoryItemPositionReader
    expected = inspect.Signature(
        [
            inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("user_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation="str"),
            inspect.Parameter("item_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation="str"),
            inspect.Parameter("trashed", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=False, annotation="bool"),
            inspect.Parameter("starred", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=False, annotation="bool"),
            inspect.Parameter("for_revision", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=False, annotation="bool"),
            inspect.Parameter("for_share", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=False, annotation="bool"),
        ],
        return_annotation="int | None",
    )
    assert reader.__dataclass_params__.frozen
    assert inspect.signature(reader.item_position) == expected
    assert inspect.signature(db.item_position) == expected.replace(parameters=list(expected.parameters.values())[1:])

    db_tree = ast.parse(inspect.getsource(db))
    facade = next(node for node in db_tree.body if isinstance(node, ast.FunctionDef) and node.name == "item_position")
    assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    assert "HistoryRow" not in ast.unparse(facade)

    history_tree = ast.parse(inspect.getsource(history))
    reader_node = next(node for node in history_tree.body if isinstance(node, ast.ClassDef) and node.name == "HistoryItemPositionReader")
    method = next(node for node in reader_node.body if isinstance(node, ast.FunctionDef) and node.name == "item_position")
    readable_calls = [
        node for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "access"
        and node.func.attr == "_readable_by"
    ]
    assert len(readable_calls) == 2
    assert all([ast.unparse(arg) for arg in call.args] == ["actor", "HistoryRow.user_id", "HistoryRow.id"] for call in readable_calls)
    assert "query_text" not in ast.unparse(method)


def test_db_item_position_resolves_owner_dependencies_at_each_call(monkeypatch) -> None:
    calls = []
    downstream_calls = []

    class Reader:
        def __init__(self, session_factory, actor_of_fn) -> None:
            calls.append((session_factory, actor_of_fn))

        def item_position(self, *args):
            downstream_calls.append(args)
            return len(calls)

    monkeypatch.setattr(db._history, "HistoryItemPositionReader", Reader)
    first_session_factory, second_session_factory = object(), object()
    first_actor_of, second_actor_of = object(), object()
    monkeypatch.setattr(db, "SessionLocal", first_session_factory)
    monkeypatch.setattr(db, "_actor_of", first_actor_of)
    assert db.item_position("first", "a") == 1
    monkeypatch.setattr(db, "SessionLocal", second_session_factory)
    monkeypatch.setattr(db, "_actor_of", second_actor_of)
    assert db.item_position("second", "b", True, True, True, True) == 2
    assert calls == [(first_session_factory, first_actor_of), (second_session_factory, second_actor_of)]
    assert downstream_calls == [
        ("first", "a", False, False, False, False),
        ("second", "b", True, True, True, True),
    ]


def test_history_item_position_preserves_visibility_filters_flags_and_zero_based_order() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        session.add_all(
            [
                HistoryRow(id="a", user_id="owner", at=30, trashed=0, history_visibility="normal"),
                HistoryRow(id="b", user_id="owner", at=20, trashed=0, history_visibility="normal"),
                HistoryRow(id="c", user_id="owner", at=20, trashed=0, history_visibility="normal", starred=1, for_revision=1, for_share=1),
                HistoryRow(id="trash", user_id="owner", at=40, trashed=1, history_visibility="normal"),
                HistoryRow(id="hidden", user_id="owner", at=50, trashed=0, history_visibility="lineage_only"),
                HistoryRow(id="private", user_id="other", at=60, trashed=0, history_visibility="normal"),
                HistoryRow(id="granted", user_id="other", at=10, trashed=0, history_visibility="normal"),
                HistoryAclRow(id="grant", history_id="granted", subject_type="user", subject_id="recipient", permission="read", at=1),
            ]
        )
        session.commit()
    reader = history.HistoryItemPositionReader(
        sessions, lambda user_id: {"id": user_id, "permission_groups": [], "group_id": None}
    )
    assert reader.item_position("owner", "a") == 0
    assert reader.item_position("owner", "b") == 1
    assert reader.item_position("owner", "c") == 2
    assert reader.item_position("owner", "trash", trashed=True) == 0
    assert reader.item_position("owner", "c", starred=True) == 0
    assert reader.item_position("owner", "c", for_revision=True) == 0
    assert reader.item_position("owner", "c", for_share=True) == 0
    assert reader.item_position("owner", "b", starred=True) is None
    assert reader.item_position("owner", "b", for_revision=True) is None
    assert reader.item_position("owner", "b", for_share=True) is None
    assert reader.item_position("owner", "hidden") is None
    assert reader.item_position("owner", "missing") is None
    assert reader.item_position("recipient", "granted") == 0
    assert reader.item_position("recipient", "private") is None


def test_history_router_keeps_anchor_page_delegation(monkeypatch) -> None:
    calls = []

    def item_position(*args, **kwargs):
        calls.append((args, kwargs))
        return 12

    monkeypatch.setattr(history_router._db, "item_position", item_position)
    monkeypatch.setattr(history_router._db, "list_items", lambda *_args, **_kwargs: ([], 0))
    response = history_router.api_history_get(
        limit=10,
        anchor_id="anchor",
        trashed=False,
        starred=False,
        for_revision=False,
        for_share=False,
        actor={"id": "actor"},
    )
    assert calls == [(("actor", "anchor"), {"trashed": False, "starred": False, "for_revision": False, "for_share": False})]
    assert response.offset == 10


def test_history_anchor_get_uses_the_anchor_page_without_disclosing_an_inaccessible_anchor(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(db, "SessionLocal", sessions)
    db._ensure_permission_groups()
    owner = db.add_user("owner", "owner@example.test", "password-123", ["users"], None)
    other = db.add_user("other", "other@example.test", "password-123", ["users"], None)
    owner_headers = {"Authorization": f"Bearer {db.create_session(owner['id'])}"}
    other_headers = {"Authorization": f"Bearer {db.create_session(other['id'])}"}
    with sessions() as session:
        session.add_all(
            [
                HistoryRow(id="newer", user_id=owner["id"], at=2, history_visibility="normal"),
                HistoryRow(id="anchor", user_id=owner["id"], at=1, history_visibility="normal"),
                HistoryRow(id="other-only", user_id=other["id"], at=3, history_visibility="normal"),
            ]
        )
        session.commit()

    client = TestClient(api_module.app)
    anchored = client.get("/api/history?anchor_id=anchor&limit=1", headers=owner_headers)
    inaccessible = client.get("/api/history?anchor_id=anchor&limit=1", headers=other_headers)

    assert anchored.status_code == 200
    assert anchored.json()["offset"] == 1
    assert [item["id"] for item in anchored.json()["items"]] == ["anchor"]
    assert inaccessible.status_code == 200
    assert inaccessible.json()["offset"] == 0
    assert inaccessible.json()["total"] == 1
    assert [item["id"] for item in inaccessible.json()["items"]] == ["other-only"]
