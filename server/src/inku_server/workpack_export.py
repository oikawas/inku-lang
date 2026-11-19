"""Export the portable work-pack contract without rewriting stored artwork."""

from __future__ import annotations

import json
import time
from itertools import chain
from pathlib import Path

from .persistence import access
from .persistence.migrations import MIGRATION_VERSION
from .persistence.schema import HistoryRow, LineageEdgeRow, LineageNodeRow, OkugakiRow

MAX_LINE = 64 * 1024 * 1024
MAX_PACK = 256 * 1024 * 1024


def export_workpack(session_factory, actor: dict, ids: list[str], *, app_version: str, build: int) -> bytes:
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise ValueError("No works selected")
    contract = json.loads((Path(__file__).resolve().parents[3] / "persistence" / "contract.json").read_text(encoding="utf-8"))
    mappings = contract["hosts"]["server"]["records"]

    def common(record, row):
        fields = contract["records"][record]["fields"]
        result = {}
        for field in fields:
            if field["classification"] not in ("required_common", "optional_common"):
                continue
            name = field["name"]
            value = getattr(row, mappings[record]["fields"][name]["column"])
            if name == "render_wild" and value is not None:
                if value not in ("0", "1"):
                    raise ValueError("Invalid recorded stroke limit")
                value = int(value)
            result[name] = value
        return result

    with session_factory() as session:
        rows = session.query(HistoryRow).filter(
            access._readable_by(actor, HistoryRow.user_id, HistoryRow.id),
            HistoryRow.id.in_(ids), HistoryRow.trashed == 0,
        ).all()
        by_id = {row.id: row for row in rows}
        if len(by_id) != len(ids):
            raise LookupError("One or more works are unavailable or in the trash")
        works = [by_id[item_id] for item_id in ids]
        node_ids = list(dict.fromkeys(row.lineage_node_id for row in works if row.lineage_node_id))
        nodes_by_id = {row.id: row for row in session.query(LineageNodeRow).filter(LineageNodeRow.id.in_(node_ids)).all()}
        nodes = [nodes_by_id[node_id] for node_id in node_ids if node_id in nodes_by_id]
        node_ids = [node.id for node in nodes]
        edges = session.query(LineageEdgeRow).filter(
            LineageEdgeRow.child_node_id.in_(node_ids), LineageEdgeRow.parent_node_id.in_(node_ids)
        ).all()
        edge_by_child = {edge.child_node_id: edge for edge in edges}
        # A readable work does not itself grant access to another user's colophon.
        colophons = session.query(OkugakiRow).filter(
            OkugakiRow.target_node_id.in_(node_ids), access._readable_by(actor, OkugakiRow.user_id)
        ).order_by(OkugakiRow.at, OkugakiRow.id).all()
        rows_by_kind = {
            "history": [common("history", row) for row in works],
            "lineage_node": [common("lineage_nodes", row) for row in nodes],
            "lineage_edge": [common("lineage_edges", edge_by_child[node_id]) for node_id in node_ids if node_id in edge_by_child],
            "annotation": [{"history_id": row.id, "note": (row.note or "").strip() or None, "for_revision": int(row.for_revision == 1)}
                           for row in works if (row.note or "").strip() or row.for_revision == 1],
            "colophon": [{"id": row.id, "target_node_id": row.target_node_id, "branch_snapshot": row.branch_snapshot_json,
                          "model": row.model, "at": row.at, "language": row.language, "body": row.body,
                          "warnings_json": row.warnings_json, "fact_sheet_json": row.fact_sheet_json}
                         for node_id in node_ids for row in colophons if row.target_node_id == node_id],
        }
    header = {"format": "inku.workpack", "format_version": 1, "persistence_contract_version": 2,
              "exported_at": int(time.time() * 1000), "producer": {"host": "server", "app_version": app_version,
              "build": build, "schema_version": MIGRATION_VERSION}, "counts": {k: len(v) for k, v in rows_by_kind.items()}}
    output = bytearray()
    for record in chain((header,), ({"kind": kind, **row} for kind, rows in rows_by_kind.items() for row in rows)):
        try:
            line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (ValueError, UnicodeError) as error:
            raise ValueError("Work pack contains an invalid value") from error
        if len(line) > MAX_LINE:
            raise ValueError("A work pack line exceeds 64 MiB")
        if len(output) + len(line) + 1 > MAX_PACK:
            raise ValueError("Work pack exceeds 256 MiB")
        output.extend(line + b"\n")
    return bytes(output)
