from __future__ import annotations

import inspect

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.api_core.routers import history as history_router
from inku_server.persistence import history
from inku_server.persistence.schema import Base, HistoryRow


def test_history_list_state_reader_is_owned_by_history_persistence_module():
    reader = getattr(history, "HistoryListStateReader", None)
    assert reader is not None
    assert reader.__dataclass_params__.frozen
    assert tuple(inspect.signature(reader.list_state).parameters) == ("self", "user_id", "trashed")
    assert tuple(inspect.signature(db.list_state).parameters) == ("user_id", "trashed")
    source = inspect.getsource(reader.list_state)
    assert "access._readable_by" in source
    assert "HistoryRow.id, HistoryRow.at" in source
    assert "HistoryRow.at.desc(), HistoryRow.id.asc()" in source
    assert "from .. import db" not in inspect.getsource(history)


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
            ]
        )
        session.commit()

    selects: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_select(_connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement.lower())

    reader = history.HistoryListStateReader(session_factory, lambda user_id: {"id": user_id})
    assert reader.list_state("owner") == (2, 10, "a")
    assert reader.list_state("owner", trashed=True) == (1, 11, "trash")
    assert reader.list_state("nobody") == (0, None, None)
    assert len(selects) == 6
    assert all("history.svg" not in statement for statement in selects)
    assert all("history.score" not in statement for statement in selects)
    assert all("history.ddl" not in statement for statement in selects)
    assert all("history.input" not in statement for statement in selects)
    assert all("lineage_" not in statement for statement in selects)


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
