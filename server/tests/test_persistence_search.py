"""Direct ownership and behavior tests for persistence-owned history search."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence import history
from inku_server.persistence import search
from inku_server.persistence.schema import HistoryRow


def _expected_fts_match_query(search: str) -> str:
    raise NotImplementedError


def _expected_is_render_hash_suffix_search(search: str) -> bool:
    raise NotImplementedError


def _expected_history_search_clause(search: str):
    raise NotImplementedError


def _expected_use_history_fts(search: str) -> bool:
    raise NotImplementedError


def _expected_list_items_with_fts(
    session,
    actor: dict,
    offset: int,
    limit: int,
    trashed: bool,
    search: str,
    starred: bool,
    for_revision: bool = False,
    for_share: bool = False,
) -> tuple[list[dict], int]:
    raise NotImplementedError


def _expected_list_items(
    user_id: str,
    offset: int = 0,
    limit: int = 10,
    trashed: bool = False,
    query_text: str = "",
    starred: bool = False,
    for_revision: bool = False,
    for_share: bool = False,
    include_svg: bool = True,
    canvas_search: bool = False,
) -> tuple[list[dict], int]:
    raise NotImplementedError


class _Result:
    def __init__(self, *, scalar=None, rows=(), query=None) -> None:
        self._scalar = scalar
        self._rows = list(rows)
        self._query = query

    def order_by(self, *clauses):
        self._query.order_by(*clauses)
        return self

    def offset(self, value: int):
        self._query.offset(value)
        return self

    def limit(self, value: int):
        self._query.limit(value)
        return self

    def scalar(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _HydrationQuery:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.filters = []

    def filter(self, *clauses):
        self.filters.extend(clauses)
        return self

    def order_by(self, *clauses):
        self.ordering = clauses
        return self

    def all(self):
        return list(self.rows)


class _FtsSession:
    def __init__(self, *, total: int, ids: list[str], rows) -> None:
        self.results = [_Result(scalar=total), _Result(rows=[(item_id,) for item_id in ids])]
        self.execute_calls = []
        self.hydration_query = _HydrationQuery(rows)

    def execute(self, statement, params):
        self.execute_calls.append((statement, dict(params)))
        return self.results.pop(0)

    def query(self, model):
        assert model is HistoryRow
        return self.hydration_query


class _OrmQuery:
    def __init__(self, rows, total: int) -> None:
        self.rows = list(rows)
        self.total = total
        self.filter_calls = []
        self.ordering = ()
        self.offset_value = None
        self.limit_value = None

    def filter(self, *clauses):
        self.filter_calls.append(clauses)
        return self

    def with_entities(self, *entities):
        assert entities
        if entities == (HistoryRow.id,):
            # The page is chosen by id; its rows are read afterwards.
            return _Result(rows=[(row.id,) for row in self.rows], query=self)
        return _Result(scalar=self.total)

    def order_by(self, *clauses):
        self.ordering = clauses
        return self

    def offset(self, value: int):
        self.offset_value = value
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def all(self):
        return list(self.rows)


class _OrmSession:
    def __init__(self, query: _OrmQuery) -> None:
        self.orm_query = query
        self.hydration_query = _HydrationQuery(query.rows)
        self.queries = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def query(self, model):
        assert model is HistoryRow
        self.queries += 1
        return self.orm_query if self.queries == 1 else self.hydration_query


def _service(**overrides):
    dependencies = {
        "fts_enabled": True,
        "dialect_name": "sqlite",
        "session_factory": lambda: None,
        "actor_of": lambda user_id: {"id": user_id},
        "readable_by": lambda actor, user_id, item_id: user_id == actor["id"],
        "readable_sql": lambda actor, user_id, item_id: ("1 = 1", {}),
        "rows_to_dicts_with_lineage": lambda session, rows, actor: rows,
    }
    dependencies.update(overrides)
    return search.HistorySearchService(**dependencies)


def _sql(statement) -> str:
    return " ".join(str(statement).split())


def test_persistence_search_owns_implementation_and_db_keeps_exact_facades() -> None:
    owner_source = inspect.getsource(search)
    assert "inku_server.db" not in owner_source
    assert "from .. import db" not in owner_source
    assert "from inku_server import db" not in owner_source
    assert "from .schema import HistoryRow" in owner_source

    expected = {
        "_fts_match_query": _expected_fts_match_query,
        "_is_render_hash_suffix_search": _expected_is_render_hash_suffix_search,
        "_history_search_clause": _expected_history_search_clause,
        "_use_history_fts": _expected_use_history_fts,
        "_list_items_with_fts": _expected_list_items_with_fts,
        "list_items": _expected_list_items,
    }
    for name, reference in expected.items():
        facade = getattr(db, name)
        assert inspect.signature(facade) == inspect.signature(reference), name
        source = inspect.getsource(facade)
        assert "HistoryRow." not in source, name
        assert "SELECT " not in source, name
        assert "_history_search" in source, name

    assert db._WHOLE_RENDER_HASH is search._WHOLE_RENDER_HASH
    group_owner_source = inspect.getsource(history.HistoryLineageGroupReader)
    assert group_owner_source.count("self.history_search_clause_fn(search)") == 2
    assert "_history_search_clause" in inspect.getsource(db._history_lineage_group_reader)


def test_db_facade_resolves_every_replaceable_dependency_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = []

    class _ProbeService:
        def __init__(self, **dependencies) -> None:
            self.dependencies = dependencies
            constructed.append(dependencies)

        def use_history_fts(self, search_text: str):
            return ("use", search_text, self.dependencies)

        def list_items_with_fts(self, *args, **kwargs):
            return ("fts", args, kwargs, self.dependencies)

        def list_items(self, *args, **kwargs):
            return ("orm", args, kwargs, self.dependencies)

    first = {name: object() for name in (
        "session_factory",
        "actor_of",
        "readable_by",
        "readable_sql",
        "rows_to_dicts_with_lineage",
    )}
    first_sql_calls: list[tuple[object, ...]] = []
    first_sql_result = object()

    def first_readable_sql(*args: object) -> object:
        first_sql_calls.append(args)
        return first_sql_result

    first["readable_sql"] = first_readable_sql
    monkeypatch.setattr(db, "_HistorySearchService", _ProbeService)
    monkeypatch.setattr(db, "_HISTORY_FTS_ENABLED", True)
    monkeypatch.setattr(db, "engine", SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
    monkeypatch.setattr(db, "SessionLocal", first["session_factory"])
    monkeypatch.setattr(db, "_actor_of", first["actor_of"])
    monkeypatch.setattr(db, "_readable_by", first["readable_by"])
    monkeypatch.setattr(db, "_readable_sql", first["readable_sql"])
    monkeypatch.setattr(db, "_rows_to_dicts_with_lineage", first["rows_to_dicts_with_lineage"])

    assert db._use_history_fts("first")[0:2] == ("use", "first")
    assert db._list_items_with_fts(object(), {"id": "actor"}, 1, 2, False, "q", True)[0] == "fts"
    assert db.list_items("user", 3, 4, True, " q ", True, True, True)[0] == "orm"
    for dependencies in constructed:
        readable_sql = dependencies.pop("readable_sql")
        expected = {
            "fts_enabled": True,
            "dialect_name": "sqlite",
            **first,
        }
        expected.pop("readable_sql")
        assert dependencies == expected
        assert readable_sql("actor", "owner", "history") is first_sql_result
    assert first_sql_calls == [("actor", "owner", "history")] * len(constructed)

    second = {name: object() for name in first}
    second_sql_calls: list[tuple[object, ...]] = []
    second_sql_result = object()

    def second_readable_sql(*args: object) -> object:
        second_sql_calls.append(args)
        return second_sql_result

    second["readable_sql"] = second_readable_sql
    monkeypatch.setattr(db, "_HISTORY_FTS_ENABLED", False)
    monkeypatch.setattr(db, "engine", SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    monkeypatch.setattr(db, "SessionLocal", second["session_factory"])
    monkeypatch.setattr(db, "_actor_of", second["actor_of"])
    monkeypatch.setattr(db, "_readable_by", second["readable_by"])
    monkeypatch.setattr(db, "_readable_sql", second["readable_sql"])
    monkeypatch.setattr(db, "_rows_to_dicts_with_lineage", second["rows_to_dicts_with_lineage"])

    assert db._use_history_fts("second")[0:2] == ("use", "second")
    readable_sql = constructed[-1].pop("readable_sql")
    expected = {
        "fts_enabled": False,
        "dialect_name": "postgresql",
        **second,
    }
    expected.pop("readable_sql")
    assert constructed[-1] == expected
    assert readable_sql("actor-2", "owner-2", "history-2") is second_sql_result
    assert second_sql_calls == [("actor-2", "owner-2", "history-2")]


def test_quote_hash_clause_and_fts_selection_behavior_remains_exact() -> None:
    assert search._fts_match_query('quiet "circle"') == '"quiet ""circle"""'

    bare_hash = "a" * 64
    for value in ("A1b2", bare_hash, "rh3:" + bare_hash, "future9:" + bare_hash.upper()):
        assert search._is_render_hash_suffix_search(value)
    for value in ("a-b2", "円abc", "a" * 63, "g" * 64, "rh3:" + "a" * 63):
        assert not search._is_render_hash_suffix_search(value)

    normal = search._history_search_clause("needle")
    normal_sql = _sql(normal)
    for field in ("history.input", "history.ddl", "history.stage1_model", "history.stage2_model", "history.catalog_id"):
        assert field in normal_sql
    assert "history.render_hash" not in normal_sql
    assert set(normal.compile().params.values()) == {"%needle%"}

    suffix = search._history_search_clause("A1b2")
    assert "history.render_hash" in _sql(suffix)
    assert set(suffix.compile().params.values()) == {"%A1b2%", "%A1b2", "A1b2%", "%:A1b2%"}

    assert not _service(fts_enabled=True, dialect_name="sqlite").use_history_fts("abc")
    assert _service(fts_enabled=True, dialect_name="sqlite").use_history_fts("quiet")
    assert not _service(fts_enabled=False, dialect_name="sqlite").use_history_fts("abc")
    assert not _service(fts_enabled=True, dialect_name="postgresql").use_history_fts("abc")
    assert not _service(fts_enabled=True, dialect_name="sqlite").use_history_fts("ab")
    assert not _service(fts_enabled=True, dialect_name="sqlite").use_history_fts("A1b2")
    assert not _service(fts_enabled=True, dialect_name="sqlite").use_history_fts("rh3:abcde")
    assert not _service(fts_enabled=True, dialect_name="sqlite").use_history_fts("12345678-")
    assert _service(fts_enabled=True, dialect_name="sqlite").use_history_fts("1234-5678")


def test_identifier_prefixes_find_sqlite_history_without_losing_text_or_visibility(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'search.sqlite3'}")
    HistoryRow.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    digest = "abcde" + "0" * 55 + "a1b2"
    ids = [f"12345678-1234-4000-8000-{number:012d}" for number in range(1, 5)]
    text_id = "beef1234-1111-4000-8000-000000000001"
    with sessions() as session:
        session.add_all([
            HistoryRow(id=ids[index], user_id="reader" if index < 3 else "other", at=index + 1,
                input="quiet circle", ddl="draw shapes", stage1_model="model-blue", stage2_model="artist",
                catalog_id="sea_stone", render_hash=prefix + digest, score="{}", svg="<svg/>")
            for index, prefix in enumerate(("rh3:", "rh2:", "", "rh3:"))
        ])
        session.add(HistoryRow(id=text_id, user_id="reader", at=5, input="a cabed phrase", score="{}", svg="<svg/>"))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("CREATE VIRTUAL TABLE history_fts USING fts5(input, ddl, stage1_model, stage2_model, catalog_id, tokenize='trigram')"))
        connection.execute(text("INSERT INTO history_fts(rowid, input, ddl, stage1_model, stage2_model, catalog_id) SELECT rowid, input, ddl, stage1_model, stage2_model, catalog_id FROM history"))
    service = _service(
        session_factory=sessions,
        readable_sql=lambda actor, owner, history_id: (f"{owner} = :reader", {"reader": actor["id"]}),
        rows_to_dicts_with_lineage=lambda session, rows, actor: [{"id": row.id} for row in rows],
    )
    try:
        # The FTS index has no hashes or ids: this exact prefix used to return zero.
        with sessions() as session:
            assert service.list_items_with_fts(session, {"id": "reader"}, 0, 10, False, "abcde", False) == ([], 0)
        cases = (
            ("abcde", set(ids[:3])), ("ABCDE", set(ids[:3])),
            ("rh3:abcde", {ids[0]}), ("RH2:ABCDE", {ids[1]}), ("rh3:a", {ids[0]}),
            (digest, set(ids[:3])), ("rh3:" + digest, {ids[0]}), ("a1b2", set(ids[:3])),
            (ids[0], {ids[0]}), (ids[0].upper(), {ids[0]}), ("12345678", set(ids[:3])),
            ("12345678-", set(ids[:3])), ("12345678-1234-4", set(ids[:3])), ("1", set(ids[:3])),
            ("cabed", {text_id}), ("quiet", set(ids[:3])), ("draw shapes", set(ids[:3])),
            ("model-blue", set(ids[:3])), ("artist", set(ids[:3])), ("sea_stone", set(ids[:3])),
        )
        for query, expected in cases:
            items, total = service.list_items("reader", query_text=query)
            assert {item["id"] for item in items} == expected, query
            assert total == len(expected), query
        assert service.list_items("reader", query_text="abcde", offset=1, limit=1) == ([{"id": ids[1]}], 3)
        assert service.list_items("other", query_text="abcde") == ([{"id": ids[3]}], 1)
    finally:
        engine.dispose()


def test_canvas_search_matches_exact_uuid_description_substrings_and_hash_edges(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'canvas-search.sqlite3'}")
    HistoryRow.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    wanted = "12345678-1234-4123-8123-123456789abc"
    digest = "abcde" + "0" * 50 + "fedcba123"
    description_digest = "beef1" + "3" * 50 + "12abcdef9"
    shadow = "87654321-4321-4321-8321-123456789abc"
    literal_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    with sessions() as session:
        session.add_all([
            HistoryRow(id=wanted, user_id="reader", at=1, input="窓辺の青い円をひとつ", score="{}", svg="<svg/>",
                render_hash="rh3:" + digest, description_hash="dh1:" + description_digest),
            HistoryRow(id=shadow, user_id="reader", at=2, input=wanted, score="{}", svg="<svg/>",
                render_hash="rh3:" + "1" * 20 + "abcde" + "2" * 39),
            HistoryRow(id=literal_id, user_id="reader", at=3, input="100% scale_/value", score="{}", svg="<svg/>"),
            HistoryRow(id="metadata-only", user_id="reader", at=4, input="unrelated words", ddl="窓辺の青い円", score="{}", svg="<svg/>"),
            HistoryRow(id="source-text", user_id="reader", at=4, input="display label", source_text="川辺の赤い線", score="{}", svg="<svg/>"),
            HistoryRow(id="other-owner", user_id="other", at=5, input="窓辺の青い円", render_hash="rh3:" + digest, score="{}", svg="<svg/>"),
            HistoryRow(id="trashed", user_id="reader", at=6, input="窓辺の青い円", render_hash="rh3:" + digest, trashed=1, score="{}", svg="<svg/>"),
            HistoryRow(id="lineage-only", user_id="reader", at=7, input="窓辺の青い円", render_hash="rh3:" + digest, history_visibility="lineage_only", score="{}", svg="<svg/>"),
        ])
        session.commit()
    # No FTS table exists: canvas description substrings must use the literal clause.
    service = _service(session_factory=sessions,
        rows_to_dicts_with_lineage=lambda session, rows, actor, **kwargs: [{"id": row.id} for row in rows])
    try:
        for query, expected in (
            (wanted, {wanted}), (wanted.upper(), {wanted}),
            (wanted[:8], {shadow}), ("青い円", {wanted}),
            ("ABCDE", {wanted}), ("rh3:abcde", {wanted}), ("cba123", {wanted}),
            (digest, {wanted}), ("rh3:" + digest, {wanted}), ("000000", set()),
            ("beef1", {wanted}), ("abcdef9", {wanted}), (description_digest, {wanted}),
            ("dh1:" + description_digest, {wanted}), ("%", {literal_id}),
            ("_", {literal_id}), ("/", {literal_id}),
            ("赤い線", {"source-text"}), ("display label", set()),
        ):
            items, total = service.list_items("reader", query_text=query, canvas_search=True, include_svg=False)
            assert {item["id"] for item in items} == expected, query
            assert total == len(expected), query
    finally:
        engine.dispose()


def test_fts_execution_preserves_visibility_filters_order_and_hydration() -> None:
    rows = [SimpleNamespace(id="first"), SimpleNamespace(id="second")]
    session = _FtsSession(total=4, ids=["second", "first"], rows=rows)
    hydration_calls = []

    def _readable_sql(actor, user_id, item_id):
        assert actor == {"id": "reader"}
        assert (user_id, item_id) == ("h.user_id", "h.id")
        return "h.user_id = :viewer", {"viewer": "reader"}

    def _hydrate(given_session, given_rows, actor):
        hydration_calls.append((given_session, list(given_rows), actor))
        return [{"id": "first"}, {"id": "second"}]

    items, total = _service(
        readable_sql=_readable_sql,
        rows_to_dicts_with_lineage=_hydrate,
    ).list_items_with_fts(
        session,
        {"id": "reader"},
        offset=7,
        limit=9,
        trashed=True,
        search='quiet "circle"',
        starred=True,
        for_revision=True,
        for_share=True,
    )

    assert items == [{"id": "second"}, {"id": "first"}]
    assert total == 4
    assert hydration_calls == [(session, rows, {"id": "reader"})]
    assert len(session.execute_calls) == 2
    count_sql = _sql(session.execute_calls[0][0])
    list_sql = _sql(session.execute_calls[1][0])
    for sql in (count_sql, list_sql):
        assert "h.user_id = :viewer" in sql
        assert "h.trashed = :trashed" in sql
        assert "h.history_visibility = 'normal'" in sql
        assert "AND h.starred = 1" in sql
        assert "AND h.for_revision = 1" in sql
        assert "AND h.for_share = 1" in sql
        assert "history_fts MATCH :match" in sql
    assert "ORDER BY h.at DESC, h.id ASC LIMIT :limit OFFSET :offset" in list_sql
    expected_params = {
        "viewer": "reader",
        "trashed": 1,
        "match": '"quiet ""circle"""',
        "limit": 9,
        "offset": 7,
    }
    assert session.execute_calls[0][1] == expected_params
    assert session.execute_calls[1][1] == expected_params

    empty = _FtsSession(total=6, ids=[], rows=[])
    hydrated = []
    assert _service(
        rows_to_dicts_with_lineage=lambda *args: hydrated.append(args),
    ).list_items_with_fts(empty, {"id": "reader"}, 0, 10, False, "quiet", False) == ([], 6)
    assert hydrated == []


def test_orm_listing_preserves_visibility_filters_search_page_and_hydration() -> None:
    rows = [SimpleNamespace(id="a"), SimpleNamespace(id="b")]
    query = _OrmQuery(rows, total=5)
    session = _OrmSession(query)
    actor = {"id": "reader"}
    visible = HistoryRow.user_id == "visible-owner"
    readability_calls = []
    hydration_calls = []

    def _readable_by(given_actor, user_id, item_id):
        readability_calls.append((given_actor, user_id, item_id))
        return visible

    def _hydrate(given_session, given_rows, given_actor):
        hydration_calls.append((given_session, list(given_rows), given_actor))
        return [{"id": row.id} for row in given_rows]

    items, total = _service(
        fts_enabled=False,
        session_factory=lambda: session,
        actor_of=lambda user_id: actor if user_id == "reader" else None,
        readable_by=_readable_by,
        rows_to_dicts_with_lineage=_hydrate,
    ).list_items(
        "reader",
        offset=3,
        limit=8,
        trashed=False,
        query_text="  needle  ",
        starred=True,
        for_revision=True,
        for_share=True,
    )

    assert items == [{"id": "a"}, {"id": "b"}]
    assert total == 5
    assert readability_calls == [(actor, HistoryRow.user_id, HistoryRow.id)]
    assert hydration_calls == [(session, rows, actor)]
    assert query.offset_value == 3
    assert query.limit_value == 8
    # The page's ids are sorted without the `at` index; the rows keep the plain order.
    assert [_sql(clause) for clause in query.ordering] == ["history.at + :at_1 DESC", "history.id ASC"]
    # Only the page's rows are read, in the page's order.
    hydration = session.hydration_query
    assert [_sql(clause) for clause in hydration.filters] == ["history.id IN (__[POSTCOMPILE_id_1])"]
    assert hydration.filters[0].right.value == ["a", "b"]
    assert [_sql(clause) for clause in hydration.ordering] == ["history.at DESC", "history.id ASC"]

    filters = [_sql(clause) for call in query.filter_calls for clause in call]
    assert _sql(visible) in filters
    assert any("history.trashed" in clause for clause in filters)
    assert any("history.history_visibility" in clause for clause in filters)
    assert any("history.starred" in clause for clause in filters)
    assert any("history.for_revision" in clause for clause in filters)
    assert any("history.for_share" in clause for clause in filters)
    search_filters = [clause for clause in query.filter_calls[-1] if "history.input" in _sql(clause)]
    assert len(search_filters) == 1
    assert set(search_filters[0].compile().params.values()) == {"%needle%"}
