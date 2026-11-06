"""Shared ancestor traversal for history and lineage projections."""

from sqlalchemy import literal, select

from . import access
from .schema import LineageEdgeRow, LineageNodeRow


def ancestors(session, node_ids, actor=None):
    if not node_ids:
        return {}, {}, set()
    path = select(LineageNodeRow.id.label("id")).where(LineageNodeRow.id.in_(node_ids)).cte("ancestors", recursive=True)
    path = path.union(select(LineageEdgeRow.parent_node_id).join(path, LineageEdgeRow.child_node_id == path.c.id))
    visible = literal(True) if actor is None else access._readable_edge(actor)
    rows = (session.query(LineageNodeRow, LineageEdgeRow, visible.label("readable"))
            .outerjoin(LineageEdgeRow, LineageEdgeRow.child_node_id == LineageNodeRow.id)
            .filter(LineageNodeRow.id.in_(select(path.c.id))).all())
    nodes = {node.id: node for node, _, _ in rows}
    edges = {edge.child_node_id: edge for _, edge, _ in rows if edge is not None}
    readable = {edge.id for _, edge, allowed in rows if edge is not None and allowed}
    return nodes, edges, readable


def generations(node_ids, edges, readable):
    memo = {}
    for node_id in node_ids:
        chain, seen, current = [], set(), node_id
        while current not in memo:
            if current in seen:
                break
            seen.add(current)
            chain.append(current)
            edge = edges.get(current)
            if edge is None or edge.id not in readable:
                break
            current = edge.parent_node_id
        base = memo.get(current, 0)
        for offset, node in enumerate(reversed(chain), 1):
            memo[node] = base + offset
    return memo
