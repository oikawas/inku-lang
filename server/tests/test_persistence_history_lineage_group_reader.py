"""Direct ownership coverage for grouped history lineage reads."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import history


def _reader_or_skip():
    reader = getattr(history, "HistoryLineageGroupReader", None)
    if reader is None:
        pytest.skip("production group reader is intentionally absent during fail-first")
    return reader


def test_persistence_history_owns_group_reader_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = getattr(history, "HistoryLineageGroupReader", None)
    assert reader is not None, "HistoryLineageGroupReader must own grouped history reads"
    assert is_dataclass(reader) and reader.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        reader(None, None, None, None).session_factory = None

    for name in ("list_lineage_groups", "list_lineage_group_items"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[tuple[object, ...], str, tuple[object, ...]]] = []

    class RecordingReader:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def __getattr__(self, name: str):
            def call(*args: object):
                calls.append((self.dependencies, name, args))
                return "sentinel"

            return call

    monkeypatch.setattr(db._history, "HistoryLineageGroupReader", RecordingReader)
    dependencies = (object(), object(), object(), object())
    for name, dependency in zip(
        ("SessionLocal", "_actor_of", "_rows_to_dicts_with_lineage", "_history_search_clause"),
        dependencies,
        strict=True,
    ):
        monkeypatch.setattr(db, name, dependency)

    assert db.list_lineage_groups("user", 1, 2, True, "q", True, True, True, 3) == "sentinel"
    assert db.list_lineage_group_items("user", "root", 4, 5, True, "q", True, True, True) == "sentinel"
    assert calls == [
        (dependencies, "list_lineage_groups", ("user", 1, 2, True, "q", True, True, True, 3)),
        (dependencies, "list_lineage_group_items", ("user", "root", 4, 5, True, "q", True, True, True)),
    ]


def test_group_reader_keeps_query_and_projection_invariants() -> None:
    reader = _reader_or_skip()
    source = inspect.getsource(reader)
    for marker in (
        "access._readable_by(actor, HistoryRow.user_id, HistoryRow.id)",
        "access._readable_node(actor)",
        'HistoryRow.history_visibility == "normal"',
        "func.coalesce(LineageNodeRow.root_node_id, LineageNodeRow.id)",
        "grouped.having(func.count(HistoryRow.id) >= min_item_count)",
        "session.query(func.count()).select_from(aggregates)",
        "HistoryRow.at.desc(), HistoryRow.id.asc()",
        "self.history_search_clause_fn(search)",
        "self.rows_to_dicts_with_lineage_fn(session, rows, actor)",
    ):
        assert marker in source
    owner_source = inspect.getsource(history)
    assert "inku_server.db" not in owner_source
    assert "from .. import db" not in owner_source


def test_group_reader_propagates_dependency_exceptions() -> None:
    reader = _reader_or_skip()

    class ActorError(RuntimeError):
        pass

    def actor_of(_user_id: str) -> dict:
        raise ActorError("actor failed")

    service = reader(lambda: None, actor_of, lambda *_args: [], lambda _search: None)
    with pytest.raises(ActorError, match="actor failed"):
        service.list_lineage_groups("user")
    with pytest.raises(ActorError, match="actor failed"):
        service.list_lineage_group_items("user", "root")
