"""Direct ownership coverage for the history reads grouped by description."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import history


def test_persistence_history_owns_description_reader_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = history.HistoryDescriptionGroupReader
    assert is_dataclass(reader) and reader.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        reader(None, None, None, None, None).session_factory = None

    for name in ("list_description_groups", "list_description_group_items", "description_group_position"):
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

    monkeypatch.setattr(db._history, "HistoryDescriptionGroupReader", RecordingReader)
    dependencies = (object(), object(), object(), object(), object())
    for name, dependency in zip(
        (
            "SessionLocal", "_actor_of", "_rows_to_dicts_with_lineage", "_history_search_clause",
            "description_group_key",
        ),
        dependencies,
        strict=True,
    ):
        monkeypatch.setattr(db, name, dependency)

    assert db.list_description_groups("user", 1, 2, True, "q", True, True, True, 3) == "sentinel"
    assert db.list_description_group_items("user", "dg1:key", 4, 5, True, "q", True, True, True) == "sentinel"
    assert db.description_group_position("user", "item", True, "q", True, True, True, 2) == "sentinel"
    assert calls == [
        (dependencies, "list_description_groups", ("user", 1, 2, True, "q", True, True, True, 3, True)),
        (dependencies, "list_description_group_items", ("user", "dg1:key", 4, 5, True, "q", True, True, True, True)),
        (dependencies, "description_group_position", ("user", "item", True, "q", True, True, True, 2)),
    ]


def test_description_reader_keeps_the_lineage_visibility_and_excludes_pictures() -> None:
    reader = history.HistoryDescriptionGroupReader
    assert reader._visible_query is history.HistoryLineageGroupReader._visible_query
    source = inspect.getsource(reader)
    for marker in (
        "self._visible_query(session, actor, trashed, query_text, starred, for_revision, for_share)",
        ".filter(HistoryRow.image_provenance.is_(None))",
        "HistoryRow.at.desc(), HistoryRow.id.asc()",
        "self.rows_to_dicts_with_lineage_fn(session, query.all(), actor)",
        "_DESCRIPTION_GROUP_KEYS",
    ):
        assert marker in source
    assert "inku_server.db" not in inspect.getsource(history)


def test_description_reader_keys_each_description_hash_once() -> None:
    made: list[str] = []

    def key_of(text: str) -> str:
        made.append(text)
        return "dg1:" + ("a" * 64 if text else "")

    class Row:
        def __init__(self, id_: str, description_hash: str | None) -> None:
            self.id = id_
            self.description_hash = description_hash

    class Session:
        def query(self, *_columns):
            return self

        def filter(self, clause):
            ids = clause.right.value
            return [(history_id, f"text-{history_id}", "") for history_id in ids]

    unique = "dh1:test-" + inspect.currentframe().f_code.co_name
    service = history.HistoryDescriptionGroupReader(None, None, None, None, key_of)
    first = service._keys_for(Session(), [Row("a", unique), Row("b", None)])
    second = service._keys_for(Session(), [Row("c", unique), Row("d", None)])
    assert first == {"a": "dg1:" + "a" * 64, "b": "dg1:" + "a" * 64}
    assert second == {"c": "dg1:" + "a" * 64, "d": "dg1:" + "a" * 64}
    # The hash is keyed once; a row without one is keyed from its text each time.
    assert made == ["text-a", "text-b", "text-d"]
    history._DESCRIPTION_GROUP_KEYS.pop(unique, None)


def test_description_reader_propagates_dependency_exceptions() -> None:
    class ActorError(RuntimeError):
        pass

    def actor_of(_user_id: str) -> dict:
        raise ActorError("actor failed")

    service = history.HistoryDescriptionGroupReader(
        lambda: None, actor_of, lambda *_args: [], lambda _search: None, lambda _text: ""
    )
    with pytest.raises(ActorError, match="actor failed"):
        service.list_description_groups("user")
    with pytest.raises(ActorError, match="actor failed"):
        service.list_description_group_items("user", "dg1:key")
    with pytest.raises(ActorError, match="actor failed"):
        service.description_group_position("user", "item")
