"""Persistence owner for lineage graph reads and node promotion."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, text

from . import access
from .schema import HistoryRow, LineageEdgeRow, LineageNodeRow


@dataclass(frozen=True)
class LineageStore:
    """Lineage operations with runtime-owned compatibility dependencies."""

    session_factory: Callable[[], object]
    actor_of_fn: Callable[[str], dict]
    row_to_dict_fn: Callable[[HistoryRow], dict]

    def _lineage_edge_to_dict(self, row: LineageEdgeRow) -> dict:
        try:
            metadata = json.loads(row.metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        return {
            "id": row.id,
            "parent_node_id": row.parent_node_id,
            "child_node_id": row.child_node_id,
            "derivation_kind": row.derivation_kind,
            "metadata": metadata if isinstance(metadata, dict) else {},
            "at": row.at,
        }

    def _ancestor_edge_ids(self, session, actor: dict, focus_node_id: str, limit: int) -> list[str]:
        if limit <= 0:
            return []
        node_visible, params = access._readable_node_sql(actor)
        visible = f"child_node_id IN (SELECT n.id FROM lineage_nodes n WHERE {node_visible})"
        step_visible = f"edge.{visible}"
        return list(session.execute(
            text(
                f"""
            WITH RECURSIVE ancestor_edges(id, parent_node_id, child_node_id) AS (
                SELECT id, parent_node_id, child_node_id
                FROM lineage_edges
                WHERE {visible} AND child_node_id = :focus_node_id
                UNION
                SELECT edge.id, edge.parent_node_id, edge.child_node_id
                FROM lineage_edges edge
                JOIN ancestor_edges ancestor
                  ON edge.child_node_id = ancestor.parent_node_id
                WHERE {step_visible}
            )
            SELECT id FROM ancestor_edges LIMIT :limit
            """
            ),
            {**params, "focus_node_id": focus_node_id, "limit": limit},
        ).scalars())

    def _descendant_edge_ids(
        self,
        session,
        actor: dict,
        focus_node_id: str,
        depth: int,
        limit: int,
    ) -> list[str]:
        if depth <= 0 or limit <= 0:
            return []
        node_visible, params = access._readable_node_sql(actor)
        seed_visible = f"child_node_id IN (SELECT n.id FROM lineage_nodes n WHERE {node_visible})"
        step_visible = f"edge.{seed_visible}"
        return list(session.execute(
            text(
                f"""
            WITH RECURSIVE descendant_edges(id, parent_node_id, child_node_id, depth) AS (
                SELECT id, parent_node_id, child_node_id, 1
                FROM lineage_edges
                WHERE {seed_visible} AND parent_node_id = :focus_node_id
                UNION ALL
                SELECT edge.id, edge.parent_node_id, edge.child_node_id, descendant.depth + 1
                FROM lineage_edges edge
                JOIN descendant_edges descendant
                  ON edge.parent_node_id = descendant.child_node_id
                WHERE {step_visible} AND descendant.depth < :depth
            )
            SELECT id
            FROM descendant_edges
            ORDER BY depth ASC, id ASC
            LIMIT :limit
            """
            ),
            {
                **params,
                "focus_node_id": focus_node_id,
                "depth": depth,
                "limit": limit,
            },
        ).scalars())

    def _lineage_node_payload(
        self,
        node: LineageNodeRow,
        readable: bool,
        child_counts: dict,
        history_by_id: dict,
        generations: dict,
    ) -> dict:
        """One node as the lineage answer carries it.

        Three states, told apart by `redacted`, because "gone" and "not yours" mean
        different things to whoever is looking: a deleted parent is never coming
        back, an unreadable one comes back the moment its owner says so. Rendered
        the same way -- dashed card, dashed arrow -- but labelled differently, so
        nobody stops asking.

        A redacted node withholds one thing a tombstone does not: `child_count`. How
        many times somebody else's work has been derived from is itself information
        about that work, and a tombstone has no owner left to keep it from.
        """
        payload = {
            "id": node.id,
            "state": node.state,
            "at": node.at,
            "deleted_at": node.deleted_at,
        }
        if node.state == "tombstone":
            payload["redacted"] = "deleted"
            payload["child_count"] = int(child_counts.get(node.id, 0))
            return payload
        if not readable:
            payload["redacted"] = "not_permitted"
            return payload
        payload["redacted"] = None
        payload["child_count"] = int(child_counts.get(node.id, 0))
        payload["description_hash"] = node.description_hash
        payload["render_hash"] = node.render_hash
        history = history_by_id.get(node.history_id or "")
        if history is not None:
            payload["history"] = self.row_to_dict_fn(history)
            payload["history"]["lineage_generation"] = generations.get(node.id)
        return payload

    def _lineage_generations(self, session, actor: dict, node_ids: list[str]) -> dict[str, int]:
        """Compute generations (root=1, +1 per primary-parent edge) for the nodes.

        This has the same semantics as the history-list side
        (`_rows_to_dicts_with_lineage`). `lineage_generation` is calculated rather
        than stored in a database column, so this remains its single source of truth
        when it is included in lineage responses.
        """
        memo: dict[str, int] = {}

        def resolve(node_id: str) -> int:
            if node_id in memo:
                return memo[node_id]
            chain: list[str] = []
            seen: set[str] = set()
            current = node_id
            while current not in memo:
                if current in seen:
                    break  # cycle guard: treat the repeated node as a root
                seen.add(current)
                chain.append(current)
                edge = session.query(LineageEdgeRow).filter(
                    access._readable_edge(actor),
                    LineageEdgeRow.child_node_id == current,
                ).first()
                if edge is None:
                    break
                current = edge.parent_node_id
            base = memo.get(current, 0)
            for offset, nid in enumerate(reversed(chain), start=1):
                memo[nid] = base + offset
            return memo[node_id]

        for node_id in node_ids:
            resolve(node_id)
        return memo

    def get_lineage(
        self,
        user_id: str,
        focus_node_id: str,
        descendant_depth: int = 2,
        node_limit: int = 200,
    ) -> dict | None:
        descendant_depth = max(0, min(descendant_depth, 200))
        node_limit = max(1, min(node_limit, 200))
        actor = self.actor_of_fn(user_id)
        with self.session_factory() as session:
            focus = session.query(LineageNodeRow).filter(
                LineageNodeRow.id == focus_node_id,
                access._readable_node(actor),
            ).first()
            if focus is None:
                return None

            ancestor_ids = self._ancestor_edge_ids(session, actor, focus.id, node_limit - 1)
            remaining = max(0, node_limit - 1 - len(ancestor_ids))
            descendant_ids = self._descendant_edge_ids(
                session,
                actor,
                focus.id,
                descendant_depth,
                remaining,
            )
            selected_edge_ids = list(dict.fromkeys([*ancestor_ids, *descendant_ids]))
            selected_edges = (
                session.query(LineageEdgeRow)
                .filter(
                    access._readable_edge(actor),
                    LineageEdgeRow.id.in_(selected_edge_ids),
                )
                .all()
                if selected_edge_ids
                else []
            )
            edges = {edge.id: edge for edge in selected_edges}
            node_ids = {focus.id}
            for edge in selected_edges:
                node_ids.add(edge.parent_node_id)
                node_ids.add(edge.child_node_id)

            # Every node an edge reaches, readable or not. A lineage may now cross
            # owners, so dropping the ones the caller cannot read would cut the chain
            # and the child would appear to have no parent at all. They come back
            # redacted instead -- present, connected, empty.
            nodes = session.query(LineageNodeRow).filter(LineageNodeRow.id.in_(node_ids)).all()
            readable_ids = {
                node_id for node_id, in
                session.query(LineageNodeRow.id).filter(
                    access._readable_node(actor), LineageNodeRow.id.in_(node_ids)
                )
            }
            history_ids = [node.history_id for node in nodes if node.history_id and node.id in readable_ids]
            history_by_id = {
                row.id: row
                for row in session.query(HistoryRow).filter(
                    access._readable_by(actor, HistoryRow.user_id, HistoryRow.id),
                    HistoryRow.id.in_(history_ids),
                ).all()
            }
            child_counts = dict(
                session.query(LineageEdgeRow.parent_node_id, func.count(LineageEdgeRow.id))
                .filter(
                    access._readable_edge(actor),
                    LineageEdgeRow.parent_node_id.in_(node_ids),
                )
                .group_by(LineageEdgeRow.parent_node_id)
                .all()
            )
            generations = self._lineage_generations(session, actor, sorted(readable_ids))
            node_payloads = [
                self._lineage_node_payload(node, node.id in readable_ids, child_counts, history_by_id, generations)
                for node in nodes
            ]
            return {
                "focus_node_id": focus.id,
                "nodes": sorted(node_payloads, key=lambda item: (item["at"], item["id"])),
                "edges": [
                    self._lineage_edge_to_dict(edge)
                    for edge in sorted(edges.values(), key=lambda item: (item.at, item.id))
                ],
            }

    def promote_lineage_node(self, user_id: str, node_id: str) -> dict | None:
        actor = self.actor_of_fn(user_id)
        with self.session_factory() as session:
            node = session.query(LineageNodeRow).filter(
                LineageNodeRow.id == node_id,
                access._writable_by(actor, LineageNodeRow.user_id, LineageNodeRow.history_id),
                LineageNodeRow.state == "lineage_only",
            ).first()
            if node is None or not node.history_id:
                return None
            row = session.query(HistoryRow).filter(
                HistoryRow.id == node.history_id,
                access._writable_by(actor, HistoryRow.user_id, HistoryRow.id),
            ).first()
            if row is None:
                return None
            node.state = "active"
            row.history_visibility = "normal"
            session.commit()
            session.refresh(row)
            return self.row_to_dict_fn(row)

    def get_lineage_branch(self, user_id: str, target_node_id: str) -> dict | None:
        """Return the single primary-parent path from root through target."""
        actor = self.actor_of_fn(user_id)
        with self.session_factory() as session:
            target = session.query(LineageNodeRow).filter(
                LineageNodeRow.id == target_node_id,
                access._readable_node(actor),
            ).first()
            if target is None:
                return None
            reversed_nodes = [target]
            reversed_edges: list[LineageEdgeRow] = []
            seen = {target.id}
            current = target
            while True:
                edge = session.query(LineageEdgeRow).filter(
                    access._readable_edge(actor),
                    LineageEdgeRow.child_node_id == current.id,
                ).first()
                if edge is None or edge.parent_node_id in seen:
                    break
                # Walk into the parent whether or not it can be read: the branch is
                # the path from the root, and stopping at the first unreadable
                # ancestor would silently shorten it.
                parent = session.get(LineageNodeRow, edge.parent_node_id)
                if parent is None:
                    break
                reversed_edges.append(edge)
                reversed_nodes.append(parent)
                seen.add(parent.id)
                current = parent
            nodes = list(reversed(reversed_nodes))
            edges = list(reversed(reversed_edges))
            node_ids = [node.id for node in nodes]
            readable_ids = {
                node_id for node_id, in
                session.query(LineageNodeRow.id).filter(
                    access._readable_node(actor), LineageNodeRow.id.in_(node_ids)
                )
            }
            history_ids = [node.history_id for node in nodes if node.history_id and node.id in readable_ids]
            histories = {
                row.id: row
                for row in session.query(HistoryRow).filter(
                    access._readable_by(actor, HistoryRow.user_id, HistoryRow.id),
                    HistoryRow.id.in_(history_ids),
                ).all()
            } if history_ids else {}
            child_counts = dict(
                session.query(LineageEdgeRow.parent_node_id, func.count(LineageEdgeRow.id))
                .filter(
                    access._readable_edge(actor),
                    LineageEdgeRow.parent_node_id.in_(node_ids),
                )
                .group_by(LineageEdgeRow.parent_node_id)
                .all()
            )
            generations = self._lineage_generations(session, actor, sorted(readable_ids))
            payload_nodes = [
                self._lineage_node_payload(node, node.id in readable_ids, child_counts, histories, generations)
                for node in nodes
            ]
            return {
                "target_node_id": target.id,
                "nodes": payload_nodes,
                "edges": [self._lineage_edge_to_dict(edge) for edge in edges],
            }
