import ast
import inspect
import textwrap
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence import history
from inku_server.persistence.schema import Base, HistoryRow


def test_neighbor_candidates_owner_exists_before_facade_delegation() -> None:
    assert getattr(history, "HistoryNeighborCandidateReader", None) is not None


def _reader_with_rows(rows: list[HistoryRow]) -> history.HistoryNeighborCandidateReader:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        session.add_all(rows)
        session.commit()
    return history.HistoryNeighborCandidateReader(
        sessions,
        lambda user_id: {"id": user_id, "permission_groups": [], "group_id": None},
        history._neighbor_score,
    )


def _row(item_id: str, at: int, score: str | None, **kwargs) -> HistoryRow:
    return HistoryRow(
        id=item_id,
        user_id=kwargs.pop("user_id", "reader"),
        at=at,
        input="",
        score=score,
        svg="",
        **kwargs,
    )


def test_neighbor_candidates_owner_and_facades_keep_their_boundaries(monkeypatch) -> None:
    assert str(inspect.signature(db._neighbor_score)) == "(raw: 'str | None') -> 'dict'"
    assert str(inspect.signature(db.list_neighbor_candidates)) == "(user_id: 'str', item_id: 'str', *, limit: 'int' = 10000) -> 'list[dict]'"
    assert getattr(history.HistoryNeighborCandidateReader, "__dataclass_params__").frozen
    owner_source = inspect.getsource(history.HistoryNeighborCandidateReader.list_neighbor_candidates)

    observed = {}

    def actor_of(user_id: str) -> dict:
        return {"id": f"current-{user_id}"}

    def decoder(raw: str | None) -> dict:
        return {"raw": raw}

    class Reader:
        def __init__(self, session_factory, actor_of_fn, score_decode_fn) -> None:
            observed.update(session_factory=session_factory, actor_of_fn=actor_of_fn, score_decode_fn=score_decode_fn)

        def list_neighbor_candidates(self, user_id, item_id, *, limit):
            return [{"id": user_id, "at": limit, "score": {"item": item_id}}]

    factory = object()
    monkeypatch.setattr(db, "SessionLocal", factory)
    monkeypatch.setattr(db, "_actor_of", actor_of)
    monkeypatch.setattr(db._history, "_neighbor_score", decoder)
    monkeypatch.setattr(db._history, "HistoryNeighborCandidateReader", Reader)

    assert db._neighbor_score("score") == {"raw": "score"}
    assert db.list_neighbor_candidates("reader", "focus", limit=7) == [
        {"id": "reader", "at": 7, "score": {"item": "focus"}}
    ]
    assert observed == {"session_factory": factory, "actor_of_fn": actor_of, "score_decode_fn": decoder}

    owner_tree = ast.parse(textwrap.dedent(owner_source))
    calls = [node for node in ast.walk(owner_tree) if isinstance(node, ast.Call)]
    readable_calls = [
        node for node in calls
        if isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "access"
        and node.func.attr == "_readable_by"
    ]
    assert len(readable_calls) == 1
    query_call = next(
        node for node in calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "query"
    )
    assert [ast.unparse(column) for column in query_call.args] == [
        "HistoryRow.id",
        "HistoryRow.at",
        "HistoryRow.score",
    ]
    assert "HistoryRow.svg" not in owner_source
    assert "HistoryRow.lineage_" not in owner_source

    history_tree = ast.parse(Path(history.__file__).read_text(encoding="utf-8"))
    imported_parts = {
        part
        for node in ast.walk(history_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for imported in ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
        + [alias.name for alias in node.names]
        for part in imported.split(".")
    }
    assert not {
        "api_core", "config", "db", "engine", "lineage", "render", "render_engines", "renderer", "router", "search",
    } & imported_parts

    db_owner_source = inspect.getsource(db.list_neighbor_candidates)
    assert "session.query" not in db_owner_source
    assert "_history.HistoryNeighborCandidateReader" in db_owner_source

    router_source = Path(db.__file__).with_name("api_core").joinpath("routers/history.py").read_text(encoding="utf-8")
    router_tree = ast.parse(router_source)
    router_function = next(
        node for node in router_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "api_history_neighbors"
    )
    router_body = ast.unparse(router_function)
    assert router_body.count("_db.get_items") == 2
    assert "composition_distance" in router_body
    assert "[:3]" in router_body
    ranked_assignment = next(
        node for node in router_function.body
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "ranked" for target in node.targets)
    )
    assert isinstance(ranked_assignment.value, ast.Subscript)
    assert isinstance(ranked_assignment.value.value, ast.Call)
    key_lambda = next(
        keyword.value for keyword in ranked_assignment.value.value.keywords
        if keyword.arg == "key" and isinstance(keyword.value, ast.Lambda)
    )
    assert isinstance(key_lambda.body, ast.Tuple)
    tie_break = key_lambda.body.elts[1]
    assert isinstance(tie_break, ast.UnaryOp)
    assert isinstance(tie_break.op, ast.USub)
    assert isinstance(tie_break.operand, ast.Call)
    assert isinstance(tie_break.operand.func, ast.Name)
    assert tie_break.operand.func.id == "int"
    assert len(tie_break.operand.args) == 1
    at_or_zero = tie_break.operand.args[0]
    assert isinstance(at_or_zero, ast.BoolOp)
    assert isinstance(at_or_zero.op, ast.Or)
    assert len(at_or_zero.values) == 2
    item_at = at_or_zero.values[0]
    assert isinstance(item_at, ast.Call)
    assert isinstance(item_at.func, ast.Attribute)
    assert isinstance(item_at.func.value, ast.Name)
    assert item_at.func.value.id == "item"
    assert item_at.func.attr == "get"
    assert len(item_at.args) == 1
    assert isinstance(item_at.args[0], ast.Constant)
    assert item_at.args[0].value == "at"
    assert isinstance(at_or_zero.values[1], ast.Constant)
    assert at_or_zero.values[1].value == 0


def test_neighbor_candidates_filter_order_limit_and_score_fallbacks() -> None:
    reader = _reader_with_rows([
        _row("focus", 90, '{"ignored": true}'),
        _row("newer", 80, '{"canvas": "square"}'),
        _row("tie-a", 70, ""),
        _row("tie-b", 70, "not-json"),
        _row("type-error", 60, None),
        _row("array", 50, "[]"),
        _row("other-user", 100, '{"hidden": true}', user_id="other"),
        _row("trashed", 100, '{"hidden": true}', trashed=1),
        _row("lineage-only", 100, '{"hidden": true}', history_visibility="lineage_only"),
    ])

    assert reader.list_neighbor_candidates("reader", "focus", limit=10) == [
        {"id": "newer", "at": 80, "score": {"canvas": "square"}},
        {"id": "tie-a", "at": 70, "score": {}},
        {"id": "tie-b", "at": 70, "score": {}},
        {"id": "type-error", "at": 60, "score": {}},
        {"id": "array", "at": 50, "score": {}},
    ]
    assert reader.list_neighbor_candidates("reader", "focus", limit=2) == [
        {"id": "newer", "at": 80, "score": {"canvas": "square"}},
        {"id": "tie-a", "at": 70, "score": {}},
    ]


def test_neighbor_score_keeps_all_original_fallbacks() -> None:
    assert history._neighbor_score('{"ok": 1}') == {"ok": 1}
    assert history._neighbor_score("") == {}
    assert history._neighbor_score("not-json") == {}
    assert history._neighbor_score(None) == {}
    assert history._neighbor_score(1) == {}  # type: ignore[arg-type]
    assert history._neighbor_score("[]") == {}
