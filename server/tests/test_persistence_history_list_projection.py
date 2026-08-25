"""Direct ownership checks for the lineage-aware history list projection."""

from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import history
from inku_server.persistence.schema import LineageEdgeRow, LineageNodeRow


class _Query:
    def __init__(self, session: "_ProjectionSession", model: type) -> None:
        self._session = session
        self._model = model
        self._filters: tuple[object, ...] = ()

    def filter(self, *filters: object) -> "_Query":
        self._filters = filters
        return self

    def all(self) -> list[SimpleNamespace]:
        self._session.calls.append((self._model, self._filters))
        if self._model is LineageNodeRow:
            return self._session.nodes
        return self._session.edge_batches.pop(0)


class _ProjectionSession:
    def __init__(
        self,
        nodes: list[SimpleNamespace],
        edge_batches: list[list[SimpleNamespace]],
    ) -> None:
        self.nodes = nodes
        self.edge_batches = edge_batches
        self.calls: list[tuple[type, tuple[object, ...]]] = []

    def query(self, model: type) -> _Query:
        return _Query(self, model)


def _row(row_id: str, user_id: str, node_id: str | None) -> SimpleNamespace:
    return SimpleNamespace(id=row_id, user_id=user_id, lineage_node_id=node_id)


def _node(node_id: str, user_id: str, root_id: str | None, state: str = "active") -> SimpleNamespace:
    return SimpleNamespace(id=node_id, user_id=user_id, root_node_id=root_id, state=state)


def _edge(child_id: str, parent_id: str, user_id: str, kind: str = "touch_change") -> SimpleNamespace:
    return SimpleNamespace(
        child_node_id=child_id,
        parent_node_id=parent_id,
        user_id=user_id,
        derivation_kind=kind,
    )


def _in_filter_values(filters: tuple[object, ...], column_name: str) -> set[str]:
    for criterion in filters:
        left = getattr(criterion, "left", None)
        if getattr(left, "name", None) == column_name:
            return set(criterion.right.value)
    raise AssertionError(f"missing IN filter for {column_name}")


def test_history_list_projector_is_the_frozen_sole_owner_and_db_is_a_facade(monkeypatch):
    assert is_dataclass(history.HistoryListProjector)
    projector = history.HistoryListProjector(lambda row: {"id": row.id}, lambda edge: {"metadata": {}})
    with pytest.raises(FrozenInstanceError):
        projector.row_to_dict_fn = lambda row: {"id": row.id}

    signature = inspect.signature(db._rows_to_dicts_with_lineage)
    assert list(signature.parameters) == ["session", "rows", "actor"]
    assert signature.parameters["actor"].default is None
    facade_source = inspect.getsource(db._rows_to_dicts_with_lineage)
    assert "HistoryListProjector" in facade_source
    assert "session.query" not in facade_source
    owner_source = inspect.getsource(history.HistoryListProjector.rows_to_dicts_with_lineage)
    assert "session.query" in owner_source
    assert "from inku_server import db" not in inspect.getsource(history)
    assert "from . import lineage" not in inspect.getsource(history)

    projected: list[str] = []
    monkeypatch.setattr(db, "_row_to_dict", lambda row: projected.append(row.id) or {"id": row.id})
    row = _row("ordinary", "owner", None)

    assert db._rows_to_dicts_with_lineage(_ProjectionSession([], []), [row]) == [{"id": "ordinary"}]
    edge = _edge("node", "parent", "owner")
    lineage_row = _row("lineage", "owner", "node")
    edge_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        db,
        "_lineage_edge_to_dict",
        lambda value: edge_calls.append(("first", value.child_node_id)) or {"metadata": {"call": "first"}},
    )
    first = db._rows_to_dicts_with_lineage(
        _ProjectionSession([_node("node", "owner", None)], [[edge], [edge], []]),
        [lineage_row],
    )
    monkeypatch.setattr(
        db,
        "_lineage_edge_to_dict",
        lambda value: edge_calls.append(("second", value.child_node_id)) or {"metadata": {"call": "second"}},
    )
    second = db._rows_to_dicts_with_lineage(
        _ProjectionSession([_node("node", "owner", None)], [[edge], [edge], []]),
        [lineage_row],
    )

    assert first[0]["derivation_metadata"] == {"call": "first"}
    assert second[0]["derivation_metadata"] == {"call": "second"}
    assert edge_calls == [("first", "node"), ("second", "node")]
    assert projected == ["ordinary", "lineage", "lineage"]


def test_projector_keeps_order_shared_markers_and_no_node_fast_path():
    rows = [_row("mine", "owner", None), _row("shared", "peer", None)]
    session = _ProjectionSession([], [])
    projector = history.HistoryListProjector(
        lambda row: {"id": row.id},
        lambda edge: {"metadata": {"unreachable": True}},
    )

    assert projector.rows_to_dicts_with_lineage(session, rows, actor={"id": "owner"}) == [
        {"id": "mine"},
        {"id": "shared", "shared": True},
    ]
    assert projector.rows_to_dicts_with_lineage(_ProjectionSession([], []), rows) == [
        {"id": "mine"},
        {"id": "shared"},
    ]
    assert session.calls == []


def test_projector_preserves_queries_generation_owner_gates_and_provenance():
    rows = [
        _row("child-work", "owner", "child"),
        _row("root-work", "owner", "root"),
        _row("mismatch-work", "owner", "mismatch"),
    ]
    child_edge = _edge("child", "parent", "owner", "description_edit")
    mismatch_edge = _edge("mismatch", "untrusted-parent", "other")
    parent_edge = _edge("parent", "root", "owner")
    session = _ProjectionSession(
        [
            _node("child", "owner", "root"),
            _node("root", "owner", None, "lineage_only"),
            _node("mismatch", "other", "mismatch-root"),
        ],
        [
            [child_edge, mismatch_edge],
            [child_edge, mismatch_edge],
            [parent_edge],
            [],
        ],
    )
    edge_calls: list[str] = []
    projector = history.HistoryListProjector(
        lambda row: {"id": row.id},
        lambda edge: edge_calls.append(edge.child_node_id) or {"metadata": {"edge": edge.child_node_id}},
    )

    items = projector.rows_to_dicts_with_lineage(session, rows, actor={"id": "owner"})

    assert [item["id"] for item in items] == ["child-work", "root-work", "mismatch-work"]
    assert items[0] == {
        "id": "child-work",
        "lineage_root_node_id": "root",
        "lineage_generation": 3,
        "lineage_state": "active",
        "lineage_parent_node_id": "parent",
        "derivation_kind": "description_edit",
        "derivation_metadata": {"edge": "child"},
    }
    assert items[1] == {
        "id": "root-work",
        "lineage_root_node_id": "root",
        "lineage_generation": 1,
        "lineage_state": "lineage_only",
    }
    assert items[2] == {"id": "mismatch-work"}
    assert edge_calls == ["child"]
    assert [model for model, _ in session.calls] == [
        LineageNodeRow,
        LineageEdgeRow,
        LineageEdgeRow,
        LineageEdgeRow,
        LineageEdgeRow,
    ]
    assert _in_filter_values(session.calls[0][1], "id") == {"child", "root", "mismatch"}
    assert _in_filter_values(session.calls[1][1], "user_id") == {"owner"}
    assert _in_filter_values(session.calls[1][1], "child_node_id") == {"child", "root", "mismatch"}
    assert _in_filter_values(session.calls[2][1], "user_id") == {"owner"}
    assert _in_filter_values(session.calls[2][1], "child_node_id") == {"child", "root", "mismatch"}
    assert _in_filter_values(session.calls[3][1], "user_id") == {"owner"}
    assert _in_filter_values(session.calls[3][1], "child_node_id") == {"parent", "untrusted-parent"}
    assert _in_filter_values(session.calls[4][1], "user_id") == {"owner"}
    assert _in_filter_values(session.calls[4][1], "child_node_id") == {"root"}


def test_projector_stops_on_missing_parents_and_cycles_without_attaching_missing_data():
    missing = _row("missing-work", "owner", "missing")
    cycle = _row("cycle-work", "owner", "cycle")
    cycle_edge = _edge("cycle", "cycle-parent", "owner")
    session = _ProjectionSession(
        [_node("cycle", "owner", None)],
        [
            [cycle_edge],
            [cycle_edge],
            [_edge("cycle-parent", "cycle", "owner")],
        ],
    )
    projector = history.HistoryListProjector(
        lambda row: {"id": row.id},
        lambda edge: {"metadata": {"kind": edge.derivation_kind}},
    )

    items = projector.rows_to_dicts_with_lineage(session, [missing, cycle])

    assert items[0] == {"id": "missing-work"}
    assert items[1] == {
        "id": "cycle-work",
        "lineage_root_node_id": "cycle",
        "lineage_generation": 2,
        "lineage_state": "active",
        "lineage_parent_node_id": "cycle-parent",
        "derivation_kind": "touch_change",
        "derivation_metadata": {"kind": "touch_change"},
    }
    assert len(session.calls) == 4
