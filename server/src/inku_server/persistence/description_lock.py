"""Which works are held by their DDL rather than by their description.

A work whose DDL was edited no longer follows its description: drawing it again
from the description would throw the edits away. Such a work is
"description-locked". It is locked when

- its authoring variation is DDL-authoritative, or
- it was made by a DDL edit (`ddl_edit`, which also covers works saved before
  the pipeline kept an authority), or
- it was derived from a locked work by an operation that keeps the parent's DDL
  (touch, color, layout, variation, replay and the like).

A work derived by reading the description again is not locked: that is where
the lineage went back to the words. The kinds below are those readings.

A `replay` is judged by its DDL, not by its kind or its variation. The Describe
tab saved an unchanged description drawn again as a replay, though it read the
words again: a replay whose DDL differs from its parent's is such a reading.
One whose DDL is the parent's is the parent's DDL drawn again; drawing from DDL
starts a DDL-authoritative variation, but no edit was made, so it is held
exactly when its parent is.
"""

from __future__ import annotations

from collections.abc import Iterable

from .ddl_source import LEGACY_EXPANDED_ORIGIN
from .schema import HistoryRow, LineageEdgeRow, LineageNodeRow, PipelineHistoryLinkRow, VariationAuthorityRow

# Derivations that draw from the description again. A child made this way
# follows its words, whatever its parent was.
DESCRIPTION_READING_KINDS = frozenset({
    "reinterpretation",
    "description_edit",
    "sketch_grain_change",
    "model_comparison",
    "language_comparison",
    "canvas_aspect_change",
})

_MAX_DEPTH = 256


def locked_history_ids(session, history_ids: Iterable[str]) -> set[str]:
    """The subset of `history_ids` that is description-locked."""
    starts = [history_id for history_id in dict.fromkeys(history_ids) if history_id]
    if not starts:
        return set()
    node_of_history: dict[str, str] = {}
    history_of_node: dict[str, str | None] = {}
    for node in session.query(LineageNodeRow).filter(LineageNodeRow.history_id.in_(starts)).all():
        node_of_history[node.history_id] = node.id
        history_of_node[node.id] = node.history_id
    edge_of_child: dict[str, tuple[str, str]] = {}
    frontier = set(node_of_history.values())
    for _ in range(_MAX_DEPTH):
        if not frontier:
            break
        edges = session.query(LineageEdgeRow).filter(LineageEdgeRow.child_node_id.in_(frontier)).all()
        parents: set[str] = set()
        for edge in edges:
            edge_of_child[edge.child_node_id] = (edge.parent_node_id, edge.derivation_kind)
            if edge.derivation_kind not in DESCRIPTION_READING_KINDS and edge.derivation_kind != "ddl_edit":
                parents.add(edge.parent_node_id)
        unseen = parents - history_of_node.keys()
        if unseen:
            for node in session.query(LineageNodeRow).filter(LineageNodeRow.id.in_(unseen)).all():
                history_of_node[node.id] = node.history_id
        frontier = {parent for parent in parents if parent not in edge_of_child}
    histories = list({*starts, *(history for history in history_of_node.values() if history)})
    ddl_authoritative = _ddl_authoritative_histories(session, histories)
    ddl_of_history = _ddl_of_histories(session, [
        history_of_node.get(node) for node in {
            node for child, (parent, kind) in edge_of_child.items() if kind == "replay" for node in (child, parent)
        }
    ])

    def same_ddl(child: str, parent: str) -> bool | None:
        child_ddl = ddl_of_history.get(history_of_node.get(child) or "")
        parent_ddl = ddl_of_history.get(history_of_node.get(parent) or "")
        if not child_ddl or not parent_ddl:
            return None
        return child_ddl == parent_ddl

    def locked(node_id: str) -> bool:
        seen: set[str] = set()
        current: str | None = node_id
        while current is not None and current not in seen:
            seen.add(current)
            edge = edge_of_child.get(current)
            if edge is not None and edge[1] == "replay":
                same = same_ddl(current, edge[0])
                if same is False:
                    return False
                if same is True:
                    current = edge[0]
                    continue
            if history_of_node.get(current) in ddl_authoritative:
                return True
            if edge is None:
                return False
            parent, kind = edge
            if kind == "ddl_edit":
                return True
            if kind in DESCRIPTION_READING_KINDS:
                return False
            current = parent
        return False

    return {history_id for history_id, node_id in node_of_history.items() if locked(node_id)} | {
        history_id for history_id in starts if history_id not in node_of_history and history_id in ddl_authoritative
    }


def _ddl_of_histories(session, history_ids: list[str | None]) -> dict[str, str]:
    """Each work's DDL, spacing aside, for telling a replay from a reading."""
    wanted = [history_id for history_id in history_ids if history_id]
    if not wanted:
        return {}
    rows = session.query(
        HistoryRow.id, HistoryRow.ddl, HistoryRow.ddl_source_origin,
    ).filter(HistoryRow.id.in_(wanted)).all()
    # A transferred expanded text says nothing about the historical input DDL.
    return {
        row.id: " ".join(row.ddl.split()) for row in rows
        if row.ddl and row.ddl_source_origin != LEGACY_EXPANDED_ORIGIN
    }


def _ddl_authoritative_histories(session, history_ids: list[str]) -> set[str]:
    if not history_ids:
        return set()
    links = session.query(PipelineHistoryLinkRow).filter(PipelineHistoryLinkRow.history_id.in_(history_ids)).all()
    if not links:
        return set()
    variations = {
        (row.owner_id, row.variation_id): row.authority
        for row in session.query(VariationAuthorityRow).filter(
            VariationAuthorityRow.variation_id.in_({link.variation_id for link in links})
        ).all()
    }
    return {
        link.history_id for link in links
        if variations.get((link.owner_id, link.variation_id)) == "ddl_authoritative"
    }


def node_is_locked(session, node_id: str) -> bool:
    """Whether the work at a lineage node is description-locked."""
    node = session.query(LineageNodeRow).filter(LineageNodeRow.id == node_id).first()
    if node is None or not node.history_id:
        return False
    return node.history_id in locked_history_ids(session, [node.history_id])
