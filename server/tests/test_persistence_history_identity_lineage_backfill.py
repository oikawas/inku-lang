"""Direct ownership coverage for legacy history identity/lineage repair."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from types import SimpleNamespace

import pytest
from sqlalchemy import or_

from inku_server import db
from inku_server.persistence import lineage
from inku_server.persistence.schema import HistoryRow, LineageEdgeRow, LineageNodeRow


class _Query:
    def __init__(self, session: _Session, model):
        self.session = session
        self.model = model

    def filter(self, *criteria):
        self.session.events.append(("filter", self.model))
        if self.model is HistoryRow:
            self.session.history_filter = criteria
        return self

    def first(self):
        self.session.events.append(("first", self.model))
        self.session.lookup_events.append(("history",))
        return self.session.node_history_matches.pop(0)

    def all(self):
        self.session.events.append(("all", self.model))
        if self.model is HistoryRow:
            return self.session.rows
        if self.model is LineageNodeRow:
            return self.session.nodes
        if self.model is LineageEdgeRow:
            return self.session.edges
        raise AssertionError(f"unexpected model: {self.model}")


class _Session:
    def __init__(
        self,
        *,
        rows=None,
        nodes=None,
        edges=None,
        nodes_by_id=None,
        node_history_matches=None,
    ):
        self.rows = list(rows or [])
        self.nodes = list(nodes or [])
        self.edges = list(edges or [])
        self.nodes_by_id = dict(nodes_by_id or {})
        self.node_history_matches = list(node_history_matches or [])
        self.events = []
        self.lookup_events = []
        self.history_filter = None
        self.added = []
        self.added_payloads = []

    def __enter__(self):
        self.events.append(("enter",))
        return self

    def __exit__(self, *_args):
        self.events.append(("exit",))
        return False

    def query(self, model):
        self.events.append(("query", model))
        return _Query(self, model)

    def get(self, model, item_id):
        self.events.append(("get", model))
        self.lookup_events.append(("get", item_id))
        return self.nodes_by_id.get(item_id)

    def add(self, node):
        self.events.append(("add",))
        self.added.append(node)
        self.added_payloads.append({
            "id": node.id,
            "user_id": node.user_id,
            "history_id": node.history_id,
            "state": node.state,
            "description_hash": node.description_hash,
            "render_hash": node.render_hash,
            "at": node.at,
            "root_node_id": node.root_node_id,
        })
        self.nodes.append(node)

    def flush(self):
        self.events.append(("flush",))

    def commit(self):
        self.events.append(("commit",))


def _event_names(session: _Session) -> list[str]:
    return [event[0] for event in session.events]


def _row(row_id: str, **overrides):
    values = {
        "id": row_id,
        "user_id": "user-id",
        "at": 10,
        "input": f"input-{row_id}",
        "source_text": None,
        "description_hash": None,
        "history_visibility": None,
        "lineage_node_id": None,
        "render_hash": f"rh3:{row_id}",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _node(node_id: str, root_node_id=None):
    return SimpleNamespace(id=node_id, root_node_id=root_node_id)


def _edge(child_node_id: str, parent_node_id: str):
    return SimpleNamespace(child_node_id=child_node_id, parent_node_id=parent_node_id)


def _backfill_or_fail():
    backfill_type = getattr(lineage, "HistoryIdentityLineageBackfill", None)
    assert backfill_type is not None
    return backfill_type


def test_owned_backfill_preserves_candidate_fill_lookup_create_and_commit() -> None:
    backfill_type = _backfill_or_fail()
    assert is_dataclass(backfill_type) and backfill_type.__dataclass_params__.frozen

    direct_node = _node("direct", "direct")
    history_node = _node("by-history", "by-history")
    direct = _row("direct-row", lineage_node_id="direct")
    by_history = _row(
        "history-row",
        source_text="kept-source",
        description_hash="kept-hash",
        history_visibility="lineage_only",
        lineage_node_id="missing",
    )
    created = _row("created-row", history_visibility="lineage_only")
    unowned = _row("unowned-row", user_id=None)
    session = _Session(
        rows=[direct, by_history, created, unowned],
        nodes=[direct_node, history_node],
        nodes_by_id={"direct": direct_node},
        node_history_matches=[history_node, None, None],
    )
    hashed = []

    def description_hash(value):
        hashed.append(value)
        return f"hash:{value}"

    backfill = backfill_type(lambda: session, description_hash, lambda: "new-node")
    with pytest.raises(FrozenInstanceError):
        backfill.session_factory = None
    assert backfill.backfill() is None

    expected_filter = or_(
        HistoryRow.source_text.is_(None),
        HistoryRow.description_hash.is_(None),
        HistoryRow.lineage_node_id.is_(None),
    )
    assert len(session.history_filter) == 1
    assert session.history_filter[0].compare(expected_filter)
    assert hashed == ["input-direct-row", "kept-source", "input-created-row", "input-unowned-row"]
    assert direct.source_text == "input-direct-row"
    assert direct.description_hash == "hash:input-direct-row"
    assert direct.history_visibility == "normal"
    assert by_history.source_text == "kept-source"
    assert by_history.description_hash == "kept-hash"
    assert by_history.lineage_node_id == "by-history"
    assert unowned.lineage_node_id is None
    assert session.lookup_events == [
        ("get", "direct"),
        ("get", "missing"),
        ("history",),
        ("history",),
        ("history",),
    ]

    assert len(session.added) == 1
    new_node = session.added[0]
    assert session.added_payloads == [{
        "id": "new-node",
        "user_id": "user-id",
        "history_id": "created-row",
        "state": "lineage_only",
        "description_hash": "hash:input-created-row",
        "render_hash": "rh3:created-row",
        "at": 10,
        "root_node_id": None,
    }]
    assert new_node.root_node_id == "new-node"
    assert created.lineage_node_id == "new-node"
    assert _event_names(session).count("flush") == 1
    assert _event_names(session).count("commit") == 1
    assert session.events.index(("flush",)) < session.events.index(("all", LineageNodeRow))
    assert _event_names(session)[-1] == "exit"


def test_borrowed_backfill_preserves_root_missing_parent_cycle_and_duplicate_child() -> None:
    root = _node("root", "root")
    parent = _node("parent")
    child = _node("child")
    missing_parent = _node("missing-parent")
    cycle_a = _node("cycle-a")
    cycle_b = _node("cycle-b")
    duplicate = _node("duplicate")
    first_parent = _node("first-parent", "first-parent")
    last_parent = _node("last-parent", "last-parent")
    session = _Session(
        nodes=[
            root,
            parent,
            child,
            missing_parent,
            cycle_a,
            cycle_b,
            duplicate,
            first_parent,
            last_parent,
        ],
        edges=[
            _edge("parent", "root"),
            _edge("child", "parent"),
            _edge("missing-parent", "absent"),
            _edge("cycle-a", "cycle-b"),
            _edge("cycle-b", "cycle-a"),
            _edge("duplicate", "first-parent"),
            _edge("duplicate", "last-parent"),
        ],
    )
    backfill = _backfill_or_fail()(
        lambda: pytest.fail("borrowed session must be reused"),
        lambda value: f"hash:{value}",
        lambda: pytest.fail("no node should be created"),
    )

    assert backfill.backfill(session) is None
    assert parent.root_node_id == "root"
    assert child.root_node_id == "root"
    assert missing_parent.root_node_id == "missing-parent"
    assert cycle_a.root_node_id == "cycle-a"
    assert cycle_b.root_node_id == "cycle-b"
    assert duplicate.root_node_id == "last-parent"
    assert _event_names(session).count("flush") == 2
    assert "commit" not in _event_names(session)


def test_unchanged_borrowed_backfill_only_performs_pre_root_flush() -> None:
    node = _node("node", "node")
    session = _Session(nodes=[node])
    backfill = _backfill_or_fail()(
        lambda: pytest.fail("borrowed session must be reused"),
        lambda value: f"hash:{value}",
        lambda: pytest.fail("no node should be created"),
    )

    assert backfill.backfill(session) is None
    assert _event_names(session).count("flush") == 1
    assert "commit" not in _event_names(session)


def test_db_backfill_facade_constructs_and_delegates_at_call_time(monkeypatch) -> None:
    created = []
    calls = []
    session_factory = object()
    hash_fn = object()
    uuid_fn = object()
    session = object()
    result = object()

    class Recording:
        def __init__(self, *args):
            created.append(args)

        def backfill(self, received=None):
            calls.append(received)
            return result

    monkeypatch.setattr(lineage, "HistoryIdentityLineageBackfill", Recording, raising=False)
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    monkeypatch.setattr(db, "description_hash", hash_fn)
    monkeypatch.setattr(db.uuid, "uuid4", uuid_fn)

    assert db._backfill_history_identity_and_lineage(session) is result
    assert created == [(session_factory, hash_fn, uuid_fn)]
    assert calls == [session]
