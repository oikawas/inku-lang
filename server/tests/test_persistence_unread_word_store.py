"""Direct ownership and transaction coverage for unread-word persistence."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import importlib
import importlib.util
import inspect
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence.schema import UnreadWordRow

feedback = (
    importlib.import_module("inku_server.persistence.feedback")
    if importlib.util.find_spec("inku_server.persistence.feedback") is not None
    else None
)


def _store_or_skip():
    if feedback is None:
        pytest.skip("production feedback module is intentionally absent during fail-first")
    store = getattr(feedback, "UnreadWordStore", None)
    if store is None:
        pytest.skip("production unread-word owner is intentionally absent during fail-first")
    return store


def _row(
    word: str,
    user_id: str,
    frequency: int,
    first_at: int,
    last_at: int,
    context: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        word=word,
        user_id=user_id,
        frequency=frequency,
        first_at=first_at,
        last_at=last_at,
        context=context,
    )


def test_persistence_feedback_owns_store_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert feedback is not None, "persistence.feedback must own unread-word persistence"
    store = getattr(feedback, "UnreadWordStore", None)
    assert store is not None, "UnreadWordStore must own unread-word persistence"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).session_factory = None

    for name in ("record_unread_words", "list_unread_words"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[object, str, tuple[object, ...], dict[str, object]]] = []

    class RecordingStore:
        def __init__(self, session_factory: object) -> None:
            self.session_factory = session_factory

        def __getattr__(self, name: str):
            def call(*args: object, **kwargs: object):
                calls.append((self.session_factory, name, args, kwargs))
                return "sentinel"

            return call

    monkeypatch.setattr(db._feedback, "UnreadWordStore", RecordingStore)
    session_factory = object()
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    assert db.record_unread_words("user", ["word"], "context", at=10) == "sentinel"
    assert db.list_unread_words("user", limit=7) == "sentinel"
    assert calls == [
        (session_factory, "record_unread_words", ("user", ["word"], "context"), {"at": 10}),
        (session_factory, "list_unread_words", ("user",), {"limit": 7}),
    ]


def test_record_normalizes_and_uses_one_atomic_upsert_per_api_sized_batch(
    tmp_path,
) -> None:
    store_type = _store_or_skip()

    def fail_if_opened() -> None:
        raise AssertionError("empty normalized words must not open a session")

    store_type(fail_if_opened).record_unread_words("user", ["", "   "], "context", at=1)

    engine = create_engine(f"sqlite:///{tmp_path / 'unread.sqlite'}")
    UnreadWordRow.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_statement(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("SELECT", "INSERT", "UPDATE")):
            statements.append(" ".join(statement.split()))

    store = store_type(factory)
    context = "c" * 1005
    long_word = "a" * 125
    store.record_unread_words(
        "user",
        [f" {long_word} ", f"{long_word}suffix"],
        context,
        at=9,
    )
    assert len(statements) == 1
    assert statements[0].startswith("INSERT INTO unread_words")
    assert "ON CONFLICT (user_id, word, context) DO UPDATE" in statements[0]

    statements.clear()
    store.record_unread_words("user", [long_word], context, at=10)
    assert len(statements) == 1

    with factory() as session:
        row = session.scalars(select(UnreadWordRow)).one()
        assert row.word == "a" * 120
        assert row.context == "c" * 1000
        assert (row.frequency, row.first_at, row.last_at) == (2, 9, 10)


def test_list_preserves_filter_aggregation_order_contexts_user_count_and_limit() -> None:
    store_type = _store_or_skip()
    rows = [
        _row("alpha", "u1", 2, 5, 10, "c1"),
        _row("alpha", "u2", 3, 2, 9, "c2"),
        _row("alpha", "u1", 1, 4, 12, "c1"),
        _row("alpha", "u3", 1, 3, 8, "c3"),
        _row("alpha", "u4", 1, 1, 7, "c4"),
        _row("beta", "u1", 8, 6, 20, ""),
    ]

    class Query:
        def __init__(self) -> None:
            self.filters = 0

        def filter(self, *_conditions: object) -> Query:
            self.filters += 1
            return self

        def all(self) -> list[object]:
            return rows

    class Session:
        def __init__(self) -> None:
            self.query_object = Query()

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            return self.query_object

    sessions: list[Session] = []

    def session_factory() -> Session:
        session = Session()
        sessions.append(session)
        return session

    store = store_type(session_factory)
    assert store.list_unread_words(None, limit=1) == [
        {
            "word": "beta",
            "frequency": 8,
            "first_at": 6,
            "last_at": 20,
            "contexts": [],
            "context": "",
            "user_count": 1,
        }
    ]
    assert sessions[0].query_object.filters == 0

    user_items = store.list_unread_words("u1")
    assert sessions[1].query_object.filters == 1
    assert [item["word"] for item in user_items] == ["beta", "alpha"]
    alpha = user_items[1]
    assert alpha == {
        "word": "alpha",
        "frequency": 8,
        "first_at": 1,
        "last_at": 12,
        "contexts": ["c1", "c2", "c3"],
        "context": "c1",
    }


def test_record_and_list_exceptions_propagate() -> None:
    store_type = _store_or_skip()

    class Query:
        def filter(self, *_conditions: object) -> Query:
            return self

        def first(self) -> None:
            return None

        def all(self) -> list[object]:
            raise RuntimeError("query failed")

    class Session:
        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            return Query()

        def execute(self, _statement: object) -> None:
            return None

        def commit(self) -> None:
            raise RuntimeError("commit failed")

    store = store_type(Session)
    with pytest.raises(RuntimeError, match="commit failed"):
        store.record_unread_words("user", ["word"], "context", at=10)
    with pytest.raises(RuntimeError, match="query failed"):
        store.list_unread_words()
