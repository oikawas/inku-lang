"""Export the portable work-pack contract without rewriting stored artwork."""

from __future__ import annotations

import json
import time

from .persistence import access
from .persistence.migrations import MIGRATION_VERSION
from .persistence.schema import HistoryRow, LineageEdgeRow, LineageNodeRow, OkugakiRow

MAX_PACK = 256 * 1024 * 1024

# Server mappings for common fields whose logical names match their DB columns.
_HISTORY_FIELDS = (
    "id", "at", "input", "source_text", "ddl", "ddl_source_origin", "score", "svg",
    "elapsed_ms", "stage1_model", "stage2_model", "catalog_id", "render_engine_id",
    "render_engine_version", "render_color_catalog_id", "render_color_catalog_name",
    "render_color_catalog_sub", "render_color_profile", "render_color_map",
    "render_canvas_aspect", "render_canvas_aspect_id", "render_canvas_aspect_ratio",
    "render_seed", "render_wild", "composition_seed", "interpretation_seed",
    "variation_amplitude", "variation_seed", "seed_text", "instruction_lang_requested",
    "instruction_lang_resolved", "interpret_fallback", "compose_fallback", "sketch_text",
    "sketch_grain", "sketch_state", "render_limits", "render_hash", "description_hash",
    "starred", "trashed", "history_visibility", "lineage_node_id",
)
_NODE_FIELDS = ("id", "history_id", "state", "description_hash", "render_hash", "at", "deleted_at", "root_node_id")
_EDGE_FIELDS = ("id", "parent_node_id", "child_node_id", "derivation_kind", "metadata_json", "at")


def _encode_line(encode, request: dict) -> bytes | None:
    try:
        payload = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError) as error:
        raise ValueError("Work pack contains an invalid value") from error
    result = encode(payload)
    if result["error"] is not None:
        error = json.loads(result["error"])
        if request["kind"] == "annotation" and error["outcome"] == "omit":
            return None
        if error.get("code") == "too_large":
            raise ValueError("A work pack line exceeds 64 MiB")
        raise ValueError("Work pack contains an invalid value")
    return result["line"]


def export_workpack(session_factory, actor: dict, ids: list[str], *, app_version: str, build: int) -> bytes:
    from inku_render import pipeline_workpack_encode_line

    ids = list(dict.fromkeys(ids))
    if not ids:
        raise ValueError("No works selected")

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
            "history": [{name: getattr(row, name) for name in _HISTORY_FIELDS} for row in works],
            "lineage_node": [{name: getattr(row, name) for name in _NODE_FIELDS} for row in nodes],
            "lineage_edge": [{name: getattr(edge_by_child[node_id], name) for name in _EDGE_FIELDS}
                             for node_id in node_ids if node_id in edge_by_child],
            "annotation": [{"history_id": row.id, "note": row.note, "for_revision": row.for_revision} for row in works],
            "colophon": [{"id": row.id, "target_node_id": row.target_node_id, "branch_snapshot": row.branch_snapshot_json,
                          "model": row.model, "at": row.at, "language": row.language, "body": row.body,
                          "warnings_json": row.warnings_json, "fact_sheet_json": row.fact_sheet_json}
                         for node_id in node_ids for row in colophons if row.target_node_id == node_id],
        }
    counts = dict.fromkeys(rows_by_kind, 0)
    output = bytearray()
    for kind, rows in rows_by_kind.items():
        for row in rows:
            line = _encode_line(pipeline_workpack_encode_line, {"kind": kind, "record": row})
            if line is None:
                continue
            if len(output) + len(line) + 1 > MAX_PACK:
                raise ValueError("Work pack exceeds 256 MiB")
            output.extend(line)
            output.extend(b"\n")
            counts[kind] += 1
    header = _encode_line(pipeline_workpack_encode_line, {
        "kind": "header", "exported_at": int(time.time() * 1000), "counts": counts,
        "producer": {"host": "server", "app_version": app_version, "build": build, "schema_version": MIGRATION_VERSION},
    })
    assert header is not None
    if len(header) + 1 + len(output) > MAX_PACK:
        raise ValueError("Work pack exceeds 256 MiB")
    return header + b"\n" + output
