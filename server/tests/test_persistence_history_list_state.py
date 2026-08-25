from __future__ import annotations

import ast
import inspect
import re

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.api_core.routers import history as history_router
from inku_server.persistence import history
from inku_server.persistence.schema import Base, HistoryAclRow, HistoryRow


def test_history_list_state_reader_is_owned_by_history_persistence_module():
    reader = getattr(history, "HistoryListStateReader", None)
    assert reader is not None
    assert reader.__dataclass_params__.frozen
    assert inspect.signature(reader.list_state) == inspect.Signature(
        [
            inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("user_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation="str"),
            inspect.Parameter(
                "trashed", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=False, annotation="bool"
            ),
        ],
        return_annotation="tuple[int, int | None, str | None]",
    )
    db_source = inspect.getsource(db)
    db_tree = ast.parse(db_source)
    facade = next(node for node in db_tree.body if isinstance(node, ast.FunctionDef) and node.name == "list_state")
    assert inspect.signature(db.list_state) == inspect.Signature(
        [
            inspect.Parameter("user_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation="str"),
            inspect.Parameter(
                "trashed", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=False, annotation="bool"
            ),
        ],
        return_annotation="tuple[int, int | None, str | None]",
    )
    assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)
    delegation = facade.body[0].value
    assert isinstance(delegation, ast.Call) and not delegation.keywords
    assert [ast.unparse(arg) for arg in delegation.args] == ["user_id", "trashed"]
    assert isinstance(delegation.func, ast.Attribute) and delegation.func.attr == "list_state"
    owner = delegation.func.value
    assert isinstance(owner, ast.Call) and not owner.keywords
    assert isinstance(owner.func, ast.Attribute)
    assert isinstance(owner.func.value, ast.Name) and owner.func.value.id == "_history"
    assert owner.func.attr == "HistoryListStateReader"
    assert [ast.unparse(arg) for arg in owner.args] == ["SessionLocal", "_actor_of"]

    history_source = inspect.getsource(history)
    history_tree = ast.parse(history_source)
    imports = [node for node in ast.walk(history_tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    forbidden_import_parts = {"db", "renderer", "rendering", "render_engines", "config", "engine", "search", "lineage"}
    for imported in imports:
        if isinstance(imported, ast.ImportFrom):
            assert imported.level <= 1
            names = [imported.module or "", *(alias.name for alias in imported.names)]
        else:
            names = [alias.name for alias in imported.names]
        assert not any(set(name.split(".")) & forbidden_import_parts for name in names)

    reader_node = next(
        node for node in history_tree.body if isinstance(node, ast.ClassDef) and node.name == "HistoryListStateReader"
    )
    owner_method = next(
        node for node in reader_node.body if isinstance(node, ast.FunctionDef) and node.name == "list_state"
    )
    readable_calls = [
        node
        for node in ast.walk(owner_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "access"
        and node.func.attr == "_readable_by"
    ]
    assert len(readable_calls) == 1
    assert [ast.unparse(arg) for arg in readable_calls[0].args] == [
        "actor",
        "HistoryRow.user_id",
        "HistoryRow.id",
    ]


def test_db_list_state_resolves_its_dependencies_at_each_call(monkeypatch) -> None:
    calls = []

    class Reader:
        def __init__(self, session_factory, actor_of_fn) -> None:
            calls.append((session_factory, actor_of_fn))

        def list_state(self, user_id: str, trashed: bool = False):
            return (1, 2, f"{user_id}-{trashed}")

    first_session_factory = object()
    second_session_factory = object()
    first_actor_of = object()
    second_actor_of = object()
    monkeypatch.setattr(db._history, "HistoryListStateReader", Reader)
    monkeypatch.setattr(db, "SessionLocal", first_session_factory)
    monkeypatch.setattr(db, "_actor_of", first_actor_of)
    assert db.list_state("first") == (1, 2, "first-False")
    monkeypatch.setattr(db, "SessionLocal", second_session_factory)
    monkeypatch.setattr(db, "_actor_of", second_actor_of)
    assert db.list_state("second", trashed=True) == (1, 2, "second-True")
    assert calls == [(first_session_factory, first_actor_of), (second_session_factory, second_actor_of)]


def test_history_list_state_reader_filters_and_projects_only_state_columns() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        session.add_all(
            [
                HistoryRow(id="b", user_id="owner", at=10, trashed=0, history_visibility="normal"),
                HistoryRow(id="a", user_id="owner", at=10, trashed=0, history_visibility="normal"),
                HistoryRow(id="trash", user_id="owner", at=11, trashed=1, history_visibility="normal"),
                HistoryRow(id="hidden", user_id="owner", at=12, trashed=0, history_visibility="lineage_only"),
                HistoryRow(id="other", user_id="other", at=13, trashed=0, history_visibility="normal"),
                HistoryRow(id="granted", user_id="other", at=14, trashed=0, history_visibility="normal"),
                HistoryAclRow(
                    id="grant",
                    history_id="granted",
                    subject_type="user",
                    subject_id="recipient",
                    permission="read",
                    at=15,
                ),
            ]
        )
        session.commit()

    select_lists: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_select(_connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            match = re.match(r"\s*SELECT\s+(.*?)\s+FROM\s+history\b", statement, flags=re.IGNORECASE | re.DOTALL)
            assert match is not None
            select_lists.append(re.sub(r"\s+AS\s+\w+", "", match.group(1), flags=re.IGNORECASE).lower())

    reader = history.HistoryListStateReader(
        session_factory,
        lambda user_id: {"id": user_id, "permission_groups": [], "group_id": None},
    )
    assert reader.list_state("owner") == (2, 10, "a")
    assert reader.list_state("owner", trashed=True) == (1, 11, "trash")
    assert reader.list_state("nobody") == (0, None, None)
    assert reader.list_state("recipient") == (1, 14, "granted")
    assert select_lists == ["count(history.id)", "history.id, history.at"] * 4


def test_history_state_router_remains_a_single_delegating_boundary(monkeypatch) -> None:
    calls = []

    def list_state(user_id: str):
        calls.append(user_id)
        return 3, 4, "newest"

    monkeypatch.setattr(history_router._db, "list_state", list_state)
    response = history_router.api_history_state({"id": "actor"})
    assert calls == ["actor"]
    assert response.total == 3
    assert response.newest_at == 4
    assert response.newest_id == "newest"
