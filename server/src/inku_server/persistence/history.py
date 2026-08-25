"""History-row presentation projection owned by the persistence boundary."""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy.exc import IntegrityError

from .schema import CoerceTraceCatalogRow, HistoryRow, LineageEdgeRow, LineageNodeRow


LINEAGE_DERIVATION_KINDS = {
    "touch_change",
    "layout_change",
    "catalog_change",
    "reinterpretation",
    "model_comparison",
    "language_comparison",
    "ddl_edit",
    "description_edit",
    "replay",
    "render_engine_change",
    "age_change",
    "hacho_change",
    "renga_reply",
    "external_seed_change",
    "canvas_aspect_change",
    "variation",  # Stage 1.5 variation, renamed from hensou in v2.8.0.
    # Sketching (Stage 0.5, v2.10). Fires when the grain differs from the parent's,
    # which includes switching the layer on or off (the grain is fine, coarse
    # or absent). The web client has sent this since v2.9.37; until v2.11.3 the
    # server did not know the name and the whole save was lost ([I-137]).
    "sketch_grain_change",
}


@dataclass(frozen=True)
class HistoryWriter:
    session_factory: Callable[[], object]
    actor_of_fn: Callable[[str], dict]
    owned_by_fn: Callable[[dict, object], object]
    readable_node_fn: Callable[[dict], object]
    row_to_dict_fn: Callable[[HistoryRow], dict]
    render_hash_for_item_fn: Callable[[dict], str]
    description_hash_fn: Callable[[str], str]
    normalize_canvas_aspect_id_fn: Callable[[str], str]
    canvas_aspect_ratio_for_aspect_fn: Callable[[str], float]
    canonical_json_fn: Callable[[dict], str]

    def add_item(self, item: dict) -> dict:
        canvas_aspect_id = item.get("render_canvas_aspect_id") or item.get("render_canvas_aspect")
        if canvas_aspect_id is not None:
            canvas_aspect_id = self.normalize_canvas_aspect_id_fn(canvas_aspect_id)
            item.setdefault("render_canvas_aspect", canvas_aspect_id)
            item["render_canvas_aspect_id"] = canvas_aspect_id
            item.setdefault(
                "render_canvas_aspect_ratio",
                self.canvas_aspect_ratio_for_aspect_fn(canvas_aspect_id),
            )
        render_hash = self.render_hash_for_item_fn(item)
        source_text = item.get("source_text")
        if source_text is None:
            source_text = item.get("input", "")
        desc_hash = self.description_hash_fn(source_text)
        visibility = item.get("history_visibility") or "normal"
        if visibility not in {"normal", "lineage_only"}:
            raise ValueError("invalid history visibility")
        parent_node_id = item.get("lineage_parent_node_id")
        derivation_kind = item.get("derivation_kind")
        derivation_metadata = item.get("derivation_metadata") or {}
        if parent_node_id and derivation_kind not in LINEAGE_DERIVATION_KINDS:
            raise ValueError("invalid lineage derivation kind")
        if not parent_node_id and derivation_kind:
            raise ValueError("lineage parent is required for a derivation")
        if not isinstance(derivation_metadata, dict):
            raise ValueError("lineage derivation metadata must be an object")

        node_id = str(uuid.uuid4())
        row = HistoryRow(
            id=item["id"], user_id=item["user_id"], at=item["at"], input=item.get("input", ""),
            ddl=item.get("ddl"), expanded_ddl=item.get("expanded_ddl"),
            score=json.dumps(item.get("score", {})), svg=item.get("svg", ""),
            output_path=item.get("output_path"), elapsed_ms=item.get("elapsed_ms", 0),
            stage1_model=item.get("stage1_model"), stage2_model=item.get("stage2_model"),
            stage1_prompt_digest=item.get("stage1_prompt_digest"),
            stage1_prompt_base_digest=item.get("stage1_prompt_base_digest"),
            stage2_prompt_digest=item.get("stage2_prompt_digest"),
            tokens_in=item.get("tokens_in"), tokens_out=item.get("tokens_out"), catalog_id=item.get("catalog_id"),
            catalog_mode=item.get("catalog_mode"),
            ddl_version=item.get("ddl_version"), ddl_engine_version=item.get("ddl_engine_version"),
            render_build_number=item.get("render_build_number"),
            render_color_profile=json.dumps(item.get("render_color_profile"), ensure_ascii=False) if item.get("render_color_profile") is not None else None,
            render_engine_id=item.get("render_engine_id"), render_engine_version=item.get("render_engine_version"),
            render_color_catalog_id=item.get("render_color_catalog_id"),
            render_color_catalog_name=item.get("render_color_catalog_name"),
            render_color_catalog_sub=item.get("render_color_catalog_sub"),
            render_color_map=json.dumps(item.get("render_color_map"), ensure_ascii=False) if item.get("render_color_map") is not None else None,
            render_canvas_aspect=item.get("render_canvas_aspect"),
            render_canvas_aspect_id=item.get("render_canvas_aspect_id") or item.get("render_canvas_aspect"),
            render_canvas_aspect_ratio=item.get("render_canvas_aspect_ratio"),
            instruction_lang_requested=item.get("instruction_lang_requested"),
            instruction_lang_resolved=item.get("instruction_lang_resolved"), ui_lang=item.get("ui_lang"),
            render_seed=str(item.get("render_seed")) if item.get("render_seed") is not None else None,
            render_wild=("1" if item.get("render_wild") else "0") if item.get("render_wild") is not None else None,
            composition_seed=str(item.get("composition_seed")) if item.get("composition_seed") is not None else None,
            tenkei=item.get("tenkei"), focus=item.get("focus"),
            variation_amplitude=item.get("variation_amplitude"),
            variation_seed=str(item.get("variation_seed")) if item.get("variation_seed") is not None else None,
            interpret_fallback=item.get("interpret_fallback"),
            # Carried through, never derived: an absent key means the writer said
            # nothing, and guessing "none" here would put a claim in the row that
            # nobody made.
            compose_fallback=item.get("compose_fallback"),
            interpretation_seed=str(item.get("interpretation_seed")) if item.get("interpretation_seed") is not None else None,
            seed_text=item.get("seed_text"),
            sketch_text=item.get("sketch_text"),
            sketch_grain=item.get("sketch_grain"),
            # Carried through, never derived here: an import restores what the
            # exporting database recorded, and an old export legitimately has none.
            sketch_state=item.get("sketch_state"),
            render_limits=json.dumps(item.get("render_limits"), ensure_ascii=False, sort_keys=True) if isinstance(item.get("render_limits"), dict) else None,
            # A new work is closed, and the destination stays NULL rather than being
            # filled with the author's group: a work nobody opened has no readers, and
            # writing the group here would make "closed" and "open to my own group"
            # look the same in the table.
            render_hash=render_hash, trashed=0, starred=0, for_revision=0, for_share=0, note=item.get("note"),
            score_pre_coerce=json.dumps(item.get("score_pre_coerce"), ensure_ascii=False) if item.get("score_pre_coerce") is not None else None,
            coerce_trace_version=item.get("coerce_trace_version"), coerce_catalog_digest=item.get("coerce_catalog_digest"),
            coerce_trace=json.dumps(item.get("coerce_trace"), ensure_ascii=False) if item.get("coerce_trace") is not None else None,
            source_text=source_text, display_label=item.get("display_label"),
            batch_line_number=item.get("batch_line_number"), batch_run_id=item.get("batch_run_id"),
            description_hash=desc_hash, history_visibility=visibility, lineage_node_id=node_id,
        )
        node = LineageNodeRow(
            id=node_id, user_id=item["user_id"], history_id=item["id"],
            state="lineage_only" if visibility == "lineage_only" else "active",
            description_hash=desc_hash, render_hash=render_hash, at=item["at"],
            root_node_id=node_id,
        )
        actor = self.actor_of_fn(item["user_id"])
        with self.session_factory() as session:
            idempotency_key = item.get("idempotency_key")
            if idempotency_key:
                existing = session.query(HistoryRow).filter(
                    self.owned_by_fn(actor, HistoryRow.user_id),
                    HistoryRow.idempotency_key == idempotency_key,
                ).first()
                if existing is not None:
                    result = self.row_to_dict_fn(existing)
                    result["_idempotent_replay"] = True
                    return result
            if parent_node_id:
                parent = session.query(LineageNodeRow).filter(
                    LineageNodeRow.id == parent_node_id,
                    self.readable_node_fn(actor),
                    LineageNodeRow.state != "tombstone",
                ).first()
                if parent is None:
                    raise ValueError("lineage parent not found")
                node.root_node_id = parent.root_node_id or parent.id
            row.idempotency_key = idempotency_key
            if item.get("coerce_catalog_digest") and item.get("coerce_catalog_snapshot") is not None:
                digest = item["coerce_catalog_digest"]
                trace_version = item.get("coerce_trace_version") or 1
                snapshot_json = json.dumps(
                    item["coerce_catalog_snapshot"], ensure_ascii=False, separators=(",", ":")
                )
                if sha256(snapshot_json.encode("utf-8")).hexdigest() != digest:
                    raise ValueError("coerce catalog digest does not match its snapshot bytes")
                catalog = session.get(CoerceTraceCatalogRow, digest)
                if catalog is None:
                    session.add(
                        CoerceTraceCatalogRow(
                            digest=digest,
                            trace_version=trace_version,
                            snapshot_json=snapshot_json,
                        )
                    )
                elif (
                    catalog.trace_version != trace_version
                    or catalog.snapshot_json != snapshot_json
                ):
                    raise ValueError("coerce catalog digest does not match its immutable snapshot")
            session.add(row)
            session.add(node)
            # SQLite foreign-key enforcement requires the new child node to exist
            # before its edge is inserted. Both writes remain in one transaction.
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                if not idempotency_key:
                    raise
                existing = session.query(HistoryRow).filter(
                    self.owned_by_fn(actor, HistoryRow.user_id),
                    HistoryRow.idempotency_key == idempotency_key,
                ).first()
                if existing is None:
                    raise
                result = self.row_to_dict_fn(existing)
                result["_idempotent_replay"] = True
                return result
            if parent_node_id:
                session.add(LineageEdgeRow(
                    id=str(uuid.uuid4()), user_id=item["user_id"], parent_node_id=parent_node_id,
                    child_node_id=node_id, derivation_kind=derivation_kind,
                    metadata_json=self.canonical_json_fn(derivation_metadata), at=item["at"],
                ))
            session.commit()
            session.refresh(row)
            result = self.row_to_dict_fn(row)
            if parent_node_id:
                result["lineage_parent_node_id"] = parent_node_id
                result["derivation_kind"] = derivation_kind
                result["derivation_metadata"] = derivation_metadata
            return result


def render_hash_short(render_hash: str | None) -> str | None:
    return render_hash[-4:].upper() if render_hash else None


def row_to_dict(
    row: HistoryRow,
    *,
    logger: logging.Logger,
    render_hash_short_fn: Callable[[str | None], str | None],
    normalize_canvas_aspect_id_fn: Callable[[str], str],
    canvas_aspect_ratio_for_aspect_fn: Callable[[str], float],
) -> dict:
    data_warnings: list[str] = []
    try:
        score = json.loads(row.score) if row.score else {}
    except (json.JSONDecodeError, TypeError):
        score = {}
        data_warnings.append("score_json_invalid")
        logger.error("history score JSON is corrupt: history_id=%s", row.id)
    if not isinstance(score, dict):
        score = {}
        data_warnings.append("score_json_not_object")
        logger.error("history score JSON is not an object: history_id=%s", row.id)
    item = {
        "id":           row.id,
        "user_id":      row.user_id,
        "at":           row.at,
        "input":        row.input,
        "ddl":          row.ddl,
        "expanded_ddl": row.expanded_ddl,
        "score":        score,
        "svg":          row.svg,
        "output_path":  row.output_path,
        "elapsed_ms":   row.elapsed_ms,
        "stage1_model": row.stage1_model,
        "stage2_model": row.stage2_model,
        "tokens_in":    row.tokens_in,
        "tokens_out":   row.tokens_out,
        "catalog_id":   row.catalog_id,
        "catalog_mode": row.catalog_mode,
        "render_hash":  row.render_hash,
        "render_hash_short": render_hash_short_fn(row.render_hash),
        "trashed":      bool(row.trashed),
        "starred":      bool(row.starred),
        "for_revision": bool(row.for_revision),
        # bool(), not the stored integer: a client reading `0`/`1` as truth is
        # reading a value SQLite is free to hand back as a string, and `bool("0")`
        # is True. The two keys always ride together -- the bit says whether the
        # work is open, the group says to whom, and either alone is unreadable.
        "for_share":    bool(row.for_share),
        "share_group_id": row.share_group_id,
    "note":         row.note,
    "source_text": row.source_text if row.source_text is not None else row.input,
    "display_label": row.display_label,
    "batch_line_number": row.batch_line_number,
    "batch_run_id": row.batch_run_id,
    "description_hash": row.description_hash,
    "history_visibility": row.history_visibility or "normal",
    "lineage_node_id": row.lineage_node_id,
}
    if data_warnings:
        item["data_warnings"] = data_warnings
    if row.stage1_prompt_digest is not None:
        item["stage1_prompt_digest"] = row.stage1_prompt_digest
    if row.stage1_prompt_base_digest is not None:
        item["stage1_prompt_base_digest"] = row.stage1_prompt_base_digest
    if row.stage2_prompt_digest is not None:
        item["stage2_prompt_digest"] = row.stage2_prompt_digest
    if row.ddl_version is not None:
        item["ddl_version"] = row.ddl_version
    if row.ddl_engine_version is not None:
        item["ddl_engine_version"] = row.ddl_engine_version
    if row.render_build_number is not None:
        item["render_build_number"] = row.render_build_number
    if row.render_color_profile is not None:
        try:
            item["render_color_profile"] = json.loads(row.render_color_profile)
        except json.JSONDecodeError:
            item["render_color_profile"] = None
    if row.render_engine_id is not None:
        item["render_engine_id"] = row.render_engine_id
    if row.render_engine_version is not None:
        item["render_engine_version"] = row.render_engine_version
    if row.render_color_catalog_id is not None:
        item["render_color_catalog_id"] = row.render_color_catalog_id
    if row.render_color_catalog_name is not None:
        item["render_color_catalog_name"] = row.render_color_catalog_name
    if row.render_color_catalog_sub is not None:
        item["render_color_catalog_sub"] = row.render_color_catalog_sub
    if row.render_color_catalog is not None:
        try:
            legacy_catalog = json.loads(row.render_color_catalog)
        except json.JSONDecodeError:
            legacy_catalog = None
        if isinstance(legacy_catalog, dict):
            item.setdefault("render_color_catalog_id", legacy_catalog.get("id"))
            item.setdefault("render_color_catalog_name", legacy_catalog.get("name"))
            item.setdefault("render_color_catalog_sub", legacy_catalog.get("sub"))
    if row.render_color_map is not None:
        try:
            item["render_color_map"] = json.loads(row.render_color_map)
        except json.JSONDecodeError:
            item["render_color_map"] = None
    if row.render_canvas_aspect is not None:
        item["render_canvas_aspect"] = row.render_canvas_aspect
    canvas_aspect_id = row.render_canvas_aspect_id or row.render_canvas_aspect
    if canvas_aspect_id is not None:
        normalized_canvas_aspect_id = normalize_canvas_aspect_id_fn(canvas_aspect_id)
        item["render_canvas_aspect_id"] = normalized_canvas_aspect_id
        item.setdefault("render_canvas_aspect", normalized_canvas_aspect_id)
        item["render_canvas_aspect_ratio"] = (
            row.render_canvas_aspect_ratio
            if row.render_canvas_aspect_ratio is not None
            else canvas_aspect_ratio_for_aspect_fn(normalized_canvas_aspect_id)
        )
    if row.instruction_lang_requested is not None:
        item["instruction_lang_requested"] = row.instruction_lang_requested
    if row.instruction_lang_resolved is not None:
        item["instruction_lang_resolved"] = row.instruction_lang_resolved
    if row.ui_lang is not None:
        item["ui_lang"] = row.ui_lang
    if row.render_seed is not None:
        try:
            item["render_seed"] = int(row.render_seed)
        except ValueError:
            item["render_seed"] = row.render_seed
    if row.render_wild is not None:
        item["render_wild"] = row.render_wild == "1"
    if row.composition_seed is not None:
        try:
            item["composition_seed"] = int(row.composition_seed)
        except ValueError:
            item["composition_seed"] = row.composition_seed
    if row.tenkei is not None:
        item["tenkei"] = row.tenkei
    if row.focus is not None:
        item["focus"] = row.focus
    if row.variation_amplitude is not None:
        item["variation_amplitude"] = row.variation_amplitude
    if row.variation_seed is not None:
        item["variation_seed"] = row.variation_seed
    if row.interpret_fallback is not None:
        item["interpret_fallback"] = row.interpret_fallback
    # Absent, not null: no key means the work was drawn before the column
    # existed, and "none" means a writer said the stage held. A reader that got
    # NULL for both could not tell an unrecorded work from a sound one.
    if row.compose_fallback is not None:
        item["compose_fallback"] = row.compose_fallback
    if row.interpretation_seed is not None:
        item["interpretation_seed"] = row.interpretation_seed
    if row.seed_text is not None:
        item["seed_text"] = row.seed_text
    if row.sketch_text is not None:
        item["sketch_text"] = row.sketch_text
    if row.sketch_grain is not None:
        item["sketch_grain"] = row.sketch_grain
    # Absent, not null: a reader that receives no key is looking at a work drawn
    # before the column existed, and that is not the same as "off".
    if row.sketch_state is not None:
        item["sketch_state"] = row.sketch_state
    # Absent, not null, for the same reason: no key means "drawn before the
    # limits were recorded", which is not "drawn at the defaults".
    if row.render_limits is not None:
        try:
            stored = json.loads(row.render_limits)
        except json.JSONDecodeError:
            stored = None
        if isinstance(stored, dict):
            item["render_limits"] = stored
    return item
