"""Direct ownership and branch checks for persistence lineage operations."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import lineage
from inku_server.persistence.schema import HistoryRow, LineageNodeRow


class FakeScalars:
    def __init__(self, values: list[str]) -> None:
        self.values = values

    def scalars(self) -> list[str]:
        return self.values


class FakeQuery:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.filters: list[tuple[object, ...]] = []

    def filter(self, *clauses: object) -> FakeQuery:
        self.filters.append(clauses)
        return self

    def group_by(self, *columns: object) -> FakeQuery:
        return self

    def first(self) -> object | None:
        return self.outcome

    def all(self) -> list[object]:
        assert isinstance(self.outcome, list)
        return self.outcome

    def __iter__(self):
        assert isinstance(self.outcome, list)
        return iter(self.outcome)


class SequentialSession:
    def __init__(
        self,
        outcomes: list[object],
        *,
        get_results: dict[tuple[object, object], object] | None = None,
    ) -> None:
        self.outcomes = list(outcomes)
        self.get_results = dict(get_results or {})
        self.queries: list[tuple[tuple[object, ...], FakeQuery]] = []
        self.execute_calls: list[tuple[object, dict]] = []
        self.entered = False
        self.exited = False
        self.commit_calls = 0
        self.refresh_calls: list[object] = []

    def __enter__(self) -> SequentialSession:
        self.entered = True
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.exited = True
        return False

    def query(self, *models: object) -> FakeQuery:
        assert self.outcomes, f"unexpected query for {models}"
        query = FakeQuery(self.outcomes.pop(0))
        self.queries.append((models, query))
        return query

    def get(self, model: object, key: object) -> object | None:
        return self.get_results.get((model, key))

    def execute(self, statement: object, params: dict) -> FakeScalars:
        self.execute_calls.append((statement, params))
        outcome = self.outcomes.pop(0)
        assert isinstance(outcome, list)
        return FakeScalars(outcome)

    def commit(self) -> None:
        self.commit_calls += 1

    def refresh(self, row: object) -> None:
        self.refresh_calls.append(row)


def _store(
    session: SequentialSession,
    *,
    actor_of=None,
    row_to_dict=None,
) -> lineage.LineageStore:
    return lineage.LineageStore(
        session_factory=lambda: session,
        actor_of_fn=actor_of or (lambda user_id: {"id": user_id}),
        row_to_dict_fn=row_to_dict or (lambda row: {"id": row.id}),
    )


def _node(node_id: str, at: int, **overrides: object) -> SimpleNamespace:
    values = {
        "id": node_id,
        "state": "active",
        "at": at,
        "deleted_at": None,
        "description_hash": f"description:{node_id}",
        "render_hash": f"render:{node_id}",
        "history_id": f"history:{node_id}",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _edge(edge_id: str, parent: str, child: str, at: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=edge_id,
        parent_node_id=parent,
        child_node_id=child,
        derivation_kind="revision",
        metadata_json='{"reason":"test"}',
        at=at,
    )


def test_persistence_lineage_owns_exact_imports_and_db_keeps_eight_facades() -> None:
    source = Path(lineage.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    actual_imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            actual_imports.append(
                ("import", 0, "", tuple((name.name, name.asname) for name in node.names))
            )
        elif isinstance(node, ast.ImportFrom):
            actual_imports.append(
                (
                    "from",
                    node.level,
                    node.module or "",
                    tuple((name.name, name.asname) for name in node.names),
                )
            )
    assert actual_imports == [
        ("from", 0, "__future__", (("annotations", None),)),
        ("import", 0, "", (("json", None),)),
        ("from", 0, "collections.abc", (("Callable", None),)),
        ("from", 0, "dataclasses", (("dataclass", None),)),
        ("from", 0, "sqlalchemy", (("func", None), ("or_", None), ("text", None))),
        ("from", 1, "", (("access", None),)),
        (
            "from",
            1,
            "schema",
            (("HistoryRow", None), ("LineageEdgeRow", None), ("LineageNodeRow", None)),
        ),
    ]
    assert lineage.LineageStore.__dataclass_params__.frozen is True

    facade_names = (
        "_lineage_edge_to_dict",
        "_ancestor_edge_ids",
        "_descendant_edge_ids",
        "_lineage_node_payload",
        "_lineage_generations",
        "get_lineage",
        "promote_lineage_node",
        "get_lineage_branch",
    )
    store_tree = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LineageStore"
    )
    assert facade_names == tuple(
        node.name for node in store_tree.body if isinstance(node, ast.FunctionDef) and node.name != "__init__"
    )
    for name in facade_names:
        function_source = inspect.getsource(getattr(db, name))
        function = ast.parse(function_source).body[0]
        assert isinstance(function, ast.FunctionDef)
        assert len(function.body) in {1, 2}
        assert isinstance(function.body[-1], ast.Return)
        assert "_lineage.LineageStore(" in function_source
        assert "session.query" not in function_source
        assert "json.loads" not in function_source


def test_db_facades_keep_exact_signatures_and_resolve_dependencies_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signatures = {
        name: inspect.signature(getattr(db, name))
        for name in (
            "_lineage_edge_to_dict",
            "_ancestor_edge_ids",
            "_descendant_edge_ids",
            "_lineage_node_payload",
            "_lineage_generations",
            "get_lineage",
            "promote_lineage_node",
            "get_lineage_branch",
        )
    }
    assert {name: str(signature) for name, signature in signatures.items()} == {
        "_lineage_edge_to_dict": "(row: 'LineageEdgeRow') -> 'dict'",
        "_ancestor_edge_ids": "(session, actor: 'dict', focus_node_id: 'str', limit: 'int') -> 'list[str]'",
        "_descendant_edge_ids": "(session, actor: 'dict', focus_node_id: 'str', depth: 'int', limit: 'int') -> 'list[str]'",
        "_lineage_node_payload": "(node: 'LineageNodeRow', readable: 'bool', child_counts: 'dict', history_by_id: 'dict', generations: 'dict') -> 'dict'",
        "_lineage_generations": "(session, actor: 'dict', node_ids: 'list[str]') -> 'dict[str, int]'",
        "get_lineage": "(user_id: 'str', focus_node_id: 'str', descendant_depth: 'int' = 2, node_limit: 'int' = 200) -> 'dict | None'",
        "promote_lineage_node": "(user_id: 'str', node_id: 'str') -> 'dict | None'",
        "get_lineage_branch": "(user_id: 'str', target_node_id: 'str') -> 'dict | None'",
    }

    dependencies = {
        "session_factory": object(),
        "actor_of_fn": object(),
        "row_to_dict_fn": object(),
    }
    initializations: list[dict[str, object]] = []
    calls: list[tuple[str, tuple[object, ...]]] = []

    class RecordingStore:
        def __init__(self, **values: object) -> None:
            initializations.append(values)

        def __getattr__(self, name: str):
            def call(*args: object) -> str:
                calls.append((name, args))
                return name

            return call

    monkeypatch.setattr(db._lineage, "LineageStore", RecordingStore)
    monkeypatch.setattr(db, "SessionLocal", dependencies["session_factory"])
    monkeypatch.setattr(db, "_actor_of", dependencies["actor_of_fn"])
    monkeypatch.setattr(db, "_row_to_dict", dependencies["row_to_dict_fn"])

    row = object()
    session = object()
    actor = {"id": "actor"}
    assert db._lineage_edge_to_dict(row) == "_lineage_edge_to_dict"
    assert db._ancestor_edge_ids(session, actor, "focus", 3) == "_ancestor_edge_ids"
    assert db._descendant_edge_ids(session, actor, "focus", 2, 3) == "_descendant_edge_ids"
    assert db._lineage_node_payload(row, True, {}, {}, {}) == "_lineage_node_payload"
    assert db._lineage_generations(session, actor, ["node"]) == "_lineage_generations"
    assert db.get_lineage("user", "focus", 4, 5) == "get_lineage"
    assert db.promote_lineage_node("user", "node") == "promote_lineage_node"
    assert db.get_lineage_branch("user", "target") == "get_lineage_branch"
    assert initializations == [dependencies] * 8
    assert [name for name, _ in calls] == list(signatures)


def test_edge_metadata_and_node_redaction_payloads_are_exact() -> None:
    store = _store(SequentialSession([]), row_to_dict=lambda row: {"projected": row.id})
    edge = _edge("edge", "parent", "child", 10)
    assert store._lineage_edge_to_dict(edge) == {
        "id": "edge",
        "parent_node_id": "parent",
        "child_node_id": "child",
        "derivation_kind": "revision",
        "metadata": {"reason": "test"},
        "at": 10,
    }
    edge.metadata_json = "not-json"
    assert store._lineage_edge_to_dict(edge)["metadata"] == {}
    edge.metadata_json = "[1, 2]"
    assert store._lineage_edge_to_dict(edge)["metadata"] == {}

    tombstone = _node("gone", 1, state="tombstone", deleted_at=20)
    assert store._lineage_node_payload(tombstone, False, {"gone": 4}, {}, {}) == {
        "id": "gone",
        "state": "tombstone",
        "at": 1,
        "deleted_at": 20,
        "redacted": "deleted",
        "child_count": 4,
    }
    withheld = _node("hidden", 2)
    assert store._lineage_node_payload(withheld, False, {"hidden": 9}, {}, {}) == {
        "id": "hidden",
        "state": "active",
        "at": 2,
        "deleted_at": None,
        "redacted": "not_permitted",
    }
    readable = _node("shown", 3)
    history = SimpleNamespace(id="history:shown")
    assert store._lineage_node_payload(
        readable,
        True,
        {"shown": 2},
        {"history:shown": history},
        {"shown": 7},
    ) == {
        "id": "shown",
        "state": "active",
        "at": 3,
        "deleted_at": None,
        "redacted": None,
        "child_count": 2,
        "description_hash": "description:shown",
        "render_hash": "render:shown",
        "history": {"projected": "history:shown", "lineage_generation": 7},
    }


def test_recursive_ctes_keep_predicate_binds_union_depth_order_and_early_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predicate_calls: list[dict] = []

    def readable_node_sql(actor: dict) -> tuple[str, dict]:
        predicate_calls.append(actor)
        return "n.user_id = :acl_owner_id", {"acl_owner_id": actor["id"]}

    monkeypatch.setattr(lineage.access, "_readable_node_sql", readable_node_sql)
    actor = {"id": "user"}
    session = SequentialSession([["ancestor"], ["descendant"]])
    store = _store(session)
    assert store._ancestor_edge_ids(session, actor, "focus", 8) == ["ancestor"]
    assert store._descendant_edge_ids(session, actor, "focus", 6, 7) == ["descendant"]
    ancestor_sql = str(session.execute_calls[0][0])
    descendant_sql = str(session.execute_calls[1][0])
    assert "WITH RECURSIVE ancestor_edges" in ancestor_sql
    assert "\n                UNION\n" in ancestor_sql
    assert "UNION ALL" not in ancestor_sql
    assert "SELECT id FROM ancestor_edges LIMIT :limit" in ancestor_sql
    assert session.execute_calls[0][1] == {
        "acl_owner_id": "user",
        "focus_node_id": "focus",
        "limit": 8,
    }
    assert "WITH RECURSIVE descendant_edges" in descendant_sql
    assert "UNION ALL" in descendant_sql
    assert "descendant.depth < :depth" in descendant_sql
    assert "ORDER BY depth ASC, id ASC\n            LIMIT :limit" in descendant_sql
    assert session.execute_calls[1][1] == {
        "acl_owner_id": "user",
        "focus_node_id": "focus",
        "depth": 6,
        "limit": 7,
    }
    assert predicate_calls == [actor, actor]

    early = SequentialSession([])
    assert store._ancestor_edge_ids(early, actor, "focus", 0) == []
    assert store._descendant_edge_ids(early, actor, "focus", 0, 9) == []
    assert store._descendant_edge_ids(early, actor, "focus", 9, 0) == []
    assert predicate_calls == [actor, actor]


def test_generation_follows_primary_edges_and_stops_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predicate_calls: list[dict] = []
    monkeypatch.setattr(
        lineage.access,
        "_readable_edge",
        lambda actor: predicate_calls.append(actor) or object(),
    )
    actor = {"id": "user"}
    chain = SequentialSession(
        [
            SimpleNamespace(parent_node_id="middle"),
            SimpleNamespace(parent_node_id="root"),
            None,
        ]
    )
    assert _store(chain)._lineage_generations(chain, actor, ["leaf"]) == {
        "root": 1,
        "middle": 2,
        "leaf": 3,
    }
    cycle = SequentialSession(
        [SimpleNamespace(parent_node_id="b"), SimpleNamespace(parent_node_id="a")]
    )
    assert _store(cycle)._lineage_generations(cycle, actor, ["a"]) == {"b": 1, "a": 2}
    assert predicate_calls == [actor] * 5


def test_graph_clamps_budget_deduplicates_and_sorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = {"id": "user"}
    focus = _node("focus", 2)
    parent = _node("parent", 1)
    child = _node("child", 3)
    later_edge = _edge("edge-2", "parent", "focus", 2)
    earlier_edge = _edge("edge-1", "focus", "child", 1)
    history = SimpleNamespace(id="history:focus")
    session = SequentialSession(
        [
            focus,
            [later_edge, earlier_edge],
            [focus, child, parent],
            [("focus",), ("child",), ("parent",)],
            [history],
            [("focus", 1)],
        ]
    )
    store = _store(session, actor_of=lambda user_id: actor)
    helper_calls: list[tuple] = []
    monkeypatch.setattr(
        lineage.LineageStore,
        "_ancestor_edge_ids",
        lambda self, active_session, active_actor, node_id, limit: (
            helper_calls.append(("ancestor", node_id, limit)) or ["edge-2", "edge-1"]
        ),
    )
    monkeypatch.setattr(
        lineage.LineageStore,
        "_descendant_edge_ids",
        lambda self, active_session, active_actor, node_id, depth, limit: (
            helper_calls.append(("descendant", node_id, depth, limit))
            or ["edge-1", "edge-3"]
        ),
    )
    monkeypatch.setattr(
        lineage.LineageStore,
        "_lineage_generations",
        lambda self, active_session, active_actor, node_ids: {
            node_id: index for index, node_id in enumerate(node_ids, start=1)
        },
    )
    monkeypatch.setattr(lineage.access, "_readable_node", lambda active_actor: object())
    monkeypatch.setattr(lineage.access, "_readable_edge", lambda active_actor: object())
    monkeypatch.setattr(lineage.access, "_readable_by", lambda *args: object())

    result = store.get_lineage("user", "focus", descendant_depth=999, node_limit=999)
    assert result is not None
    assert helper_calls == [
        ("ancestor", "focus", 199),
        ("descendant", "focus", 200, 197),
    ]
    selected_filter = session.queries[1][1].filters[0][1]
    assert list(selected_filter.right.value) == ["edge-2", "edge-1", "edge-3"]
    assert [node["id"] for node in result["nodes"]] == ["parent", "focus", "child"]
    assert [edge["id"] for edge in result["edges"]] == ["edge-1", "edge-2"]


def test_branch_keeps_unreadable_ancestor_topology_and_withholds_child_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _node("parent", 1)
    target = _node("target", 2)
    edge = _edge("edge", "parent", "target", 1)
    history = SimpleNamespace(id="history:target")
    session = SequentialSession(
        [target, edge, None, [("target",)], [history], [("parent", 5)]],
        get_results={(LineageNodeRow, "parent"): parent},
    )
    monkeypatch.setattr(lineage.access, "_readable_node", lambda actor: object())
    monkeypatch.setattr(lineage.access, "_readable_edge", lambda actor: object())
    monkeypatch.setattr(lineage.access, "_readable_by", lambda *args: object())
    monkeypatch.setattr(
        lineage.LineageStore,
        "_lineage_generations",
        lambda self, active_session, actor, node_ids: {"target": 2},
    )
    result = _store(session).get_lineage_branch("user", "target")
    assert result is not None
    assert result["target_node_id"] == "target"
    assert [node["id"] for node in result["nodes"]] == ["parent", "target"]
    assert result["nodes"][0] == {
        "id": "parent",
        "state": "active",
        "at": 1,
        "deleted_at": None,
        "redacted": "not_permitted",
    }
    assert result["nodes"][1]["history"]["lineage_generation"] == 2
    assert [item["id"] for item in result["edges"]] == ["edge"]


@pytest.mark.parametrize(
    ("outcomes", "writable_count"),
    [
        ([None], 1),
        ([_node("node", 1, history_id=None)], 1),
        ([_node("node", 1), None], 2),
    ],
)
def test_promotion_none_paths_do_not_write(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[object],
    writable_count: int,
) -> None:
    writable_calls: list[tuple] = []
    monkeypatch.setattr(
        lineage.access,
        "_writable_by",
        lambda *args: writable_calls.append(args) or object(),
    )
    session = SequentialSession(outcomes)
    assert _store(session).promote_lineage_node("user", "node") is None
    assert len(writable_calls) == writable_count
    assert session.commit_calls == 0
    assert session.refresh_calls == []


def test_promotion_requires_both_writable_gates_then_commits_refreshes_and_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node = _node("node", 1)
    row = SimpleNamespace(id="history:node", history_visibility="lineage_only")
    writable_calls: list[tuple] = []
    monkeypatch.setattr(
        lineage.access,
        "_writable_by",
        lambda *args: writable_calls.append(args) or object(),
    )
    session = SequentialSession([node, row])
    result = _store(session, row_to_dict=lambda item: {"projected": item.id}).promote_lineage_node(
        "user", "node"
    )
    assert result == {"projected": "history:node"}
    assert len(writable_calls) == 2
    assert writable_calls[0][1:] == (
        LineageNodeRow.user_id,
        LineageNodeRow.history_id,
    )
    assert writable_calls[1][1:] == (HistoryRow.user_id, HistoryRow.id)
    assert node.state == "active"
    assert row.history_visibility == "normal"
    assert session.commit_calls == 1
    assert session.refresh_calls == [row]
