"""History-row presentation projection owned by the persistence boundary."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

from .schema import HistoryRow


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
