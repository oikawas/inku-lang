"""The render/history seam: turning a Score into SVG and persisting the artifacts."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from ..color_catalogs import get_color_catalog, render_color_map_for_catalog
from ..coerce import coerce_score
from ..ddl_expander import VARIATION_AMPLITUDES
from ..interpreter import _sanitize_placement_words
from ..layer_versions import DDL_ENGINE_VERSION, DDL_VERSION
from ..plugins import canvas_aspect_ids, canvas_aspect_ratio_for_aspect, normalize_canvas_aspect_id
from ..renderer import SVG_PROFILES, new_render_seed
from ..render_engines import current_render_engine
from ..schema import CanvasSpec, Score
from .. import db as _db
from .common import _build_number, _model_metadata
from .deps import _logger
from .state import _SAVE_QUEUE_LIMIT, _increment_save_stat, _render_capacity, _save_executor, _save_slots


_SRGB_COLOR_PROFILE = {
    "id": "srgb",
    "name": "sRGB IEC61966-2.1",
    "standard": "IEC 61966-2-1:1999",
}


def _output_save_settings() -> dict:
    return _db.get_output_save_settings()


def _current_output_dir() -> Path:
    return Path(_output_save_settings()["output_dir"])


def _output_prefix(user_id: str, item_id: str, at_ms: int) -> Path:
    dt = datetime.fromtimestamp(at_ms / 1000, tz=timezone.utc).astimezone()
    date_dir = _current_output_dir() / user_id / dt.strftime("%Y-%m-%d")
    return date_dir / (dt.strftime("%Y%m%d_%H%M%S") + "_" + item_id[:8])


def _save_output_files(
    prefix: Path,
    input_text: str,
    ddl: str | None,
    score: dict,
    svg: str,
    render_metadata: dict | None = None,
    model_metadata: dict | None = None,
) -> None:
    try:
        prefix.parent.mkdir(parents=True, exist_ok=True)
        if input_text:
            Path(f"{prefix}_instruction.txt").write_text(input_text, encoding="utf-8")
        if ddl:
            Path(f"{prefix}_normalized.ddl").write_text(ddl, encoding="utf-8")
        score_payload = {"score": score, **(model_metadata or {}), **(render_metadata or {})}
        Path(f"{prefix}_score.json").write_text(json.dumps(score_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        svg_bytes = svg.encode("utf-8")
        Path(f"{prefix}_output.svg").write_bytes(svg_bytes)
    except Exception:
        _logger.exception("failed to save output files: prefix=%s", prefix)
        return

    from inku_analysis.rasterizer import RasterizerUnavailable, svg_to_png

    try:
        png_bytes = svg_to_png(svg, width=int(_output_save_settings()["png_size"]))
        Path(f"{prefix}_output.png").write_bytes(png_bytes)
    except RasterizerUnavailable:
        _logger.warning("no SVG rasterizer is installed; skipped PNG output: prefix=%s", prefix)
    except Exception:
        _logger.exception("failed to save PNG output: prefix=%s", prefix)


def _render_hash_metadata(
    *,
    input_text: str,
    ddl: str | None,
    score: Score | dict,
    svg: str,
    catalog_id: str | None,
    render_metadata: dict | None,
) -> dict[str, str]:
    score_payload = score.model_dump(by_alias=True) if isinstance(score, Score) else score
    item = {
        "input": input_text,
        "ddl": _sanitize_placement_words(ddl) if ddl else ddl,
        "score": score_payload,
        "svg": svg,
        "catalog_id": catalog_id,
        **(render_metadata or {}),
    }
    render_hash = _db.render_hash_for_item(item)
    return {
        "render_hash": render_hash,
        "render_hash_short": _db.render_hash_short(render_hash) or "",
    }


def _resolved_tenkei(requested: str | None, actor: dict, lineage_parent_node_id: str | None) -> str:
    """添景水準の解決 (v1.97): 明示値 > 派生元作品からの継承 > auto。

    継承をサーバー側で解決することで、AI 自律推敲・CLI・全クライアントの派生生成が
    系統の水準を無指定のまま維持する（作者裁定 2026-07-19: 親作品から継承）。
    """
    if requested:
        return requested
    if lineage_parent_node_id:
        inherited = _db.tenkei_for_node(actor["id"], lineage_parent_node_id)
        if inherited in {"none", "sparse", "auto"}:
            return inherited
    return "auto"


def _validated_variation_amplitude(value: str | None) -> str | None:
    """変奏 (v2.0): 未指定・未知の強度は None にして変奏なしへ戻す。

    変奏は系譜継承しない（作者裁定 2026-07-20）。明示された作品だけが
    (強度, seed) を持ち、未指定の派生は変奏前と同じ展開になる。
    """
    if value in VARIATION_AMPLITUDES:
        return value
    return None


def _validated_svg_profile(svg_profile: str | None) -> str:
    profile = (svg_profile or "display").strip().lower()
    if profile not in SVG_PROFILES:
        raise HTTPException(status_code=422, detail=f"unsupported svg profile: {svg_profile}")
    return profile


def _render_score_svg(
    score_payload: dict,
    *,
    catalog_id: str | None,
    canvas_aspect: str | None = None,
    svg_profile: str | None = None,
    render_seed: int | None = None,
    wild: bool = False,
) -> str:
    score = coerce_score(Score.model_validate(score_payload))
    canvas = _validated_canvas_aspect_override(canvas_aspect)
    if canvas is not None:
        score = _score_with_canvas(score, canvas)
    render_metadata = _render_metadata(_resolved_catalog_id(catalog_id))
    with _render_capacity():
        return current_render_engine().render(
            score,
            color_map=render_metadata["render_color_map"],
            catalog_id=render_metadata.get("render_color_catalog_id"),
            svg_profile=_validated_svg_profile(svg_profile),
            render_seed=render_seed,
            wild=wild,
        ).svg


def _history_output_prefix(item: dict) -> Path:
    output_path = item.get("output_path")
    if output_path:
        return Path(output_path)
    return _output_prefix(item["user_id"], item["id"], item["at"])


def _history_render_metadata(item: dict) -> dict | None:
    if isinstance(item.get("render_metadata"), dict):
        metadata = dict(item["render_metadata"])
        if metadata.get("render_canvas_aspect_id") is None and metadata.get("render_canvas_aspect") is not None:
            canvas_aspect_id = normalize_canvas_aspect_id(metadata.get("render_canvas_aspect"))
            metadata["render_canvas_aspect_id"] = canvas_aspect_id
            metadata.setdefault("render_canvas_aspect", canvas_aspect_id)
            metadata.setdefault("render_canvas_aspect_ratio", canvas_aspect_ratio_for_aspect(canvas_aspect_id))
        if item.get("render_hash") is not None:
            metadata["render_hash"] = item["render_hash"]
            metadata["render_hash_short"] = item.get("render_hash_short") or _db.render_hash_short(item.get("render_hash"))
        return metadata
    keys = (
        "stage1_prompt_digest",
        "stage1_prompt_base_digest",
        "stage2_prompt_digest",
        "ddl_version",
        "ddl_engine_version",
        "render_build_number",
        "render_color_profile",
        "render_engine_id",
        "render_engine_version",
        "render_canvas_aspect",
        "render_canvas_aspect_id",
        "render_canvas_aspect_ratio",
        "render_hash",
        "render_hash_short",
        "render_color_catalog_id",
        "render_color_catalog_name",
        "render_color_catalog_sub",
        "render_color_map",
    )
    metadata = {key: item[key] for key in keys if item.get(key) is not None}
    return metadata or None


def _history_model_metadata(item: dict) -> dict | None:
    metadata = _model_metadata(
        stage1_model=item.get("stage1_model"),
        stage2_model=item.get("stage2_model"),
    )
    return metadata or None


def _save_history_artifacts(item: dict) -> None:
    _save_output_files(
        _history_output_prefix(item),
        item.get("input", ""),
        item.get("ddl"),
        item.get("score", {}),
        item.get("svg", ""),
        _history_render_metadata(item),
        _history_model_metadata(item),
    )


def _run_history_artifact_save(item: dict) -> None:
    try:
        _save_history_artifacts(item)
        _increment_save_stat("completed")
    except Exception:
        _increment_save_stat("failed")
        _logger.exception("unexpected artifact save failure: history_id=%s", item.get("id"))
    finally:
        _save_slots.release()


def _submit_history_artifact_save(item: dict) -> bool:
    if not _output_save_settings()["enabled"]:
        _increment_save_stat("skipped")
        return False
    if not _save_slots.acquire(blocking=False):
        _increment_save_stat("skipped")
        _logger.warning(
            "artifact save queue is full; skipped background save: history_id=%s queue_limit=%s",
            item.get("id"),
            _SAVE_QUEUE_LIMIT,
        )
        return False
    _increment_save_stat("submitted")
    try:
        _save_executor.submit(_run_history_artifact_save, item)
    except Exception:
        _increment_save_stat("failed")
        _save_slots.release()
        _logger.exception("failed to submit artifact save job: history_id=%s", item.get("id"))
        return False
    return True


def _score_canvas_aspect_value(score: Score) -> str:
    if isinstance(score.canvas, CanvasSpec):
        return score.canvas.aspect
    return str(score.canvas or "square")


def _render_metadata(catalog_id: str | None, *, canvas_aspect: str | None = None) -> dict:
    catalog = get_color_catalog(catalog_id)
    color_map = render_color_map_for_catalog(catalog_id)
    if catalog is None or color_map is None:
        raise HTTPException(status_code=422, detail=f"unsupported color catalog: {catalog_id}")
    metadata = {
        "ddl_version": DDL_VERSION,
        "ddl_engine_version": DDL_ENGINE_VERSION,
        "render_build_number": _build_number(),
        "render_color_profile": dict(_SRGB_COLOR_PROFILE),
    }
    if canvas_aspect is not None:
        canvas_aspect_id = normalize_canvas_aspect_id(canvas_aspect)
        metadata["render_canvas_aspect"] = canvas_aspect_id
        metadata["render_canvas_aspect_id"] = canvas_aspect_id
        metadata["render_canvas_aspect_ratio"] = canvas_aspect_ratio_for_aspect(canvas_aspect_id)
    metadata.update({
        "render_color_catalog_id": str(catalog["id"]),
        "render_color_catalog_name": str(catalog["name"]),
        "render_color_catalog_sub": str(catalog["sub"]),
    })
    metadata["render_color_map"] = color_map
    return metadata


def _render_with_metadata(score: Score, render_metadata: dict, *, svg_profile: str | None = None) -> tuple[str, dict]:
    effective_seed = int(render_metadata.get("render_seed") or new_render_seed())
    wild = bool(render_metadata.get("render_wild"))
    render_metadata = {**render_metadata, "render_seed": effective_seed, "render_wild": wild}
    with _render_capacity():
        result = current_render_engine().render(
            score,
            color_map=render_metadata["render_color_map"],
            catalog_id=render_metadata.get("render_color_catalog_id"),
            svg_profile=_validated_svg_profile(svg_profile),
            render_seed=effective_seed,
            wild=wild,
        )
    return result.svg, {**render_metadata, **result.metadata}


def _resolved_catalog_id(catalog_id: str | None) -> str:
    catalog = get_color_catalog(catalog_id)
    if catalog is None:
        raise HTTPException(status_code=422, detail=f"unsupported color catalog: {catalog_id}")
    return str(catalog["id"])


def _validated_canvas_aspect(value: str | None) -> str:
    if value is None:
        return normalize_canvas_aspect_id(None)
    if value not in canvas_aspect_ids():
        raise HTTPException(status_code=422, detail=f"unsupported canvas aspect: {value}")
    return value


def _render_seed_from_text(seed_text: str | None, render_seed: int | None) -> tuple[int | None, str | None]:
    normalized = (seed_text or "").strip()
    if not normalized:
        return render_seed, None
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False), normalized


def _validated_canvas_aspect_override(value: str | None) -> str | None:
    if value is None:
        return None
    return _validated_canvas_aspect(value)


def _score_with_canvas(score: Score, canvas_aspect: str) -> Score:
    data = score.model_dump(by_alias=True)
    existing = data.get("canvas")
    if isinstance(existing, dict) and existing.get("ground") is not None:
        existing["aspect"] = canvas_aspect
    else:
        data["canvas"] = canvas_aspect
    return Score.model_validate(data)


def _add_history_item(
    *,
    actor: dict,
    input_text: str,
    ddl: str | None,
    score: Score,
    svg: str,
    at: int,
    expanded_ddl: str | None = None,
    interpret_fallback: str | None = None,
    elapsed_ms: int = 0,
    stage1_model: str | None = None,
    stage2_model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    catalog_id: str | None = None,
    save_artifacts: bool = True,
    render_metadata: dict | None = None,
    source_text: str | None = None,
    display_label: str | None = None,
    batch_line_number: int | None = None,
    batch_run_id: str | None = None,
    history_visibility: str = "normal",
    lineage_parent_node_id: str | None = None,
    derivation_kind: str | None = None,
    derivation_metadata: dict[str, object] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    item_id = str(uuid.uuid4())
    score_dict = score.model_dump(by_alias=True)
    prefix = _output_prefix(actor["id"], item_id, at)
    metadata = dict(render_metadata or {})
    metadata.setdefault("ddl_version", DDL_VERSION)
    metadata.setdefault("ddl_engine_version", DDL_ENGINE_VERSION)
    if not metadata.get("render_hash"):
        metadata.update(
            _render_hash_metadata(
                input_text=input_text,
                ddl=ddl,
                score=score_dict,
                svg=svg,
                catalog_id=catalog_id,
                render_metadata=metadata,
            )
        )
    try:
        item_dict = _db.add_item({
        "id": item_id,
        "user_id": actor["id"],
        "output_path": str(prefix),
        "input": input_text,
        "ddl": _sanitize_placement_words(ddl) if ddl else ddl,
        "expanded_ddl": _sanitize_placement_words(expanded_ddl) if expanded_ddl else expanded_ddl,
        "interpret_fallback": interpret_fallback,
        "score": score_dict,
        "svg": svg,
        "at": at,
        "elapsed_ms": elapsed_ms,
        "stage1_model": stage1_model,
        "stage2_model": stage2_model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
"catalog_id": catalog_id,
"source_text": source_text if source_text is not None else input_text,
"display_label": display_label,
"batch_line_number": batch_line_number,
"batch_run_id": batch_run_id,
"history_visibility": history_visibility,
"lineage_parent_node_id": lineage_parent_node_id,
"derivation_kind": derivation_kind,
"derivation_metadata": derivation_metadata or {},
"idempotency_key": idempotency_key,
**metadata,
    })
    except ValueError as exc:
        status_code = 404 if str(exc) == "lineage parent not found" else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if save_artifacts:
        item_dict.update(metadata)
        item_dict["render_metadata"] = metadata
        _submit_history_artifact_save(item_dict)
    else:
        item_dict.update(metadata)
    return item_dict
