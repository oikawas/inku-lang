"""The render/history seam: turning a Score into SVG and persisting the artifacts."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from ..color_catalogs import DEFAULT_COLOR_CATALOG_ID, get_color_catalog, render_color_map_for_catalog
from ..coerce import coerce_score
from ..ddl_expander import VARIATION_AMPLITUDES
from ..interpreter import _sanitize_placement_words
from ..layer_versions import DDL_ENGINE_VERSION, DDL_VERSION
from ..limits import (
    LIMIT_FIELD_NAMES,
    Limits,
    limits_from_settings,
    normalize_limits,
    using_limits,
)
from ..plugins import canvas_aspect_ids, canvas_aspect_ratio_for_aspect, normalize_canvas_aspect_id
from ..render_engines import current_render_engine
from ..render_engines.default.determinism import new_render_seed
from ..render_engines.default.document import SVG_PROFILES
from ..schema import CanvasSpec, Score
from .. import db as _db
from .common import _build_number, _model_metadata
from .deps import _logger
from .state import _SAVE_QUEUE_LIMIT, _increment_save_stat, _render_capacity, _save_executor, _save_slots
from .thumbnails import submit_thumbnail_build as _submit_thumbnail_build


_SRGB_COLOR_PROFILE = {
    "id": "srgb",
    "name": "sRGB IEC61966-2.1",
    "standard": "IEC 61966-2-1:1999",
}


def _effective_limits() -> Limits:
    """Read the stored limits ONCE for this request.

    Every route that coerces a score calls this and passes the result down by
    name. `coerce_score`'s `limits=` defaults to DEFAULT_LIMITS, so a route that
    forgets would run at the defaults silently rather than fail -- which is why
    the count of routes that pass it is a stated number, not an assumption.
    """
    return limits_from_settings(_db.get_render_limit_settings())


def _limits_for_render(
    work: dict | None = None,
    requested: dict[str, int] | None = None,
) -> tuple[Limits, str]:
    """The limits this render runs under, and where they came from.

    Four sources, in the order they bind:

      request           the caller named them. Bounded element-wise by today's
                        settings below, so a caller cannot raise a ceiling the
                        administrator lowered.
      work              the work's own row recorded them. This is what makes a
                        redraw faithful: the row is already in hand for the
                        colors, and reading only the colors off it drew the old
                        work under today's numbers.
      work_unrecorded   a work is in hand but its row has none. Today's settings
                        draw it, and the caller is told so rather than left to
                        read `render_limits` and assume it replayed.
      settings          no work at all -- a new drawing.

    The work's own values are NOT bounded by today's settings: the server wrote
    them itself, and clamping them would make a lowered setting silently
    un-replay every work above it. `normalize_limits` still runs over them,
    because the row is TEXT that a missing key or a string can come out of.
    """
    settings_limits = _effective_limits()
    if requested is not None:
        # Element-wise, not "reject if any exceeds": rounding is how every other
        # limit reader answers a number it cannot honour (`normalize_limits`),
        # and a request naming one impossible field should not lose the other
        # eight. LIMIT_ABSOLUTE_MAX alone is not a bound anyone can afford --
        # 100,000 marks measured ~1.8 GB of SVG.
        asked = normalize_limits(requested)
        bounded = {
            name: min(asked[name], getattr(settings_limits, name))
            for name in LIMIT_FIELD_NAMES
        }
        return Limits(**bounded), LIMITS_SOURCE_REQUEST
    if work is not None:
        recorded = work.get("render_limits")
        if isinstance(recorded, dict) and recorded:
            return Limits(**normalize_limits(recorded)), LIMITS_SOURCE_WORK
        return settings_limits, LIMITS_SOURCE_WORK_UNRECORDED
    return settings_limits, LIMITS_SOURCE_SETTINGS


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


def _composition_seed(value: object) -> int | None:
    """Read a composition seed the way the rest of the server reads one.

    `is None`, never `or`: 0 is a seed the placement stage must honour, and
    db.py:1911 tests the same field the same way. A row written before the
    column held numbers can still carry a non-numeric string; that is not a
    seed, so it falls back to the performance seed instead of raising.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _render_score_svg(
    score_payload: dict,
    *,
    catalog_id: str | None,
    canvas_aspect: str | None = None,
    svg_profile: str | None = None,
    render_seed: int | None = None,
    composition_seed: int | None = None,
    wild: bool = False,
    work: dict | None = None,
    requested_limits: dict[str, int] | None = None,
) -> tuple[str, str, str, str]:
    """Render a Score to SVG.

    Returns the SVG, the catalog id that actually decided its colors, which
    source that id came from, and which source decided the limits.
    """
    # Site 1 of 5. `using_limits` covers Score.model_validate, whose count clamp
    # cannot take an argument; `limits=` covers coerce. Both come from one read.
    #
    # The work is already in hand here for its colors. Reading only the colors
    # off it and taking the limits from today's settings drew a stored work at
    # whatever ceiling the installation happens to hold now (ledger I-154).
    limits, limits_source = _limits_for_render(work, requested_limits)
    # This route redraws a stored Score and hands coerce no DDL, so no count is
    # read here today. The language still travels, and it comes off the work's
    # own row rather than from today's default: a caller that starts handing a
    # DDL over must not silently get the reading rules of the other language.
    lang = (work or {}).get("instruction_lang_resolved")
    with using_limits(limits):
        score = coerce_score(Score.model_validate(score_payload), limits=limits, lang=lang)
    # Three answers to "which paper", in the order they bind: the caller's
    # override, the paper the work was performed on, and the Score's own
    # declaration. The middle one is read off the work's row because the Score
    # now records what the composition was built for, which is not always the
    # paper the picture was drawn on.
    canvas = _validated_canvas_aspect_override(canvas_aspect)
    if canvas is None and work is not None:
        recorded = work.get("render_canvas_aspect_id") or work.get("render_canvas_aspect")
        if recorded is not None:
            canvas = normalize_canvas_aspect_id(str(recorded))
    render_metadata, resolved_catalog_id, color_source = _color_render_metadata(
        work=work, catalog_id=catalog_id
    )
    with _render_capacity():
        svg = current_render_engine().render(
            score,
            color_map=render_metadata["render_color_map"],
            catalog_id=render_metadata.get("render_color_catalog_id"),
            canvas_aspect=canvas,
            svg_profile=_validated_svg_profile(svg_profile),
            render_seed=render_seed,
            composition_seed=_composition_seed(composition_seed),
            wild=wild,
        ).svg
    return svg, resolved_catalog_id, color_source, limits_source


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


def _base_render_metadata(canvas_aspect: str | None) -> dict:
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
    return metadata


def _render_metadata(catalog_id: str | None, *, canvas_aspect: str | None = None) -> dict:
    catalog = get_color_catalog(catalog_id)
    color_map = render_color_map_for_catalog(catalog_id)
    if catalog is None or color_map is None:
        raise HTTPException(status_code=422, detail=f"unsupported color catalog: {catalog_id}")
    metadata = _base_render_metadata(canvas_aspect)
    metadata.update({
        "render_color_catalog_id": str(catalog["id"]),
        "render_color_catalog_name": str(catalog["name"]),
        "render_color_catalog_sub": str(catalog["sub"]),
    })
    metadata["render_color_map"] = color_map
    return metadata


def _render_with_metadata(score: Score, render_metadata: dict, *, svg_profile: str | None = None) -> tuple[str, dict]:
    effective_seed = int(render_metadata.get("render_seed") or new_render_seed())
    # The two seeds are read differently on purpose: an absent performance seed
    # is drawn fresh, while an absent composition seed means "the placement
    # follows the performance seed" and 0 means the seed 0.
    composition_seed = _composition_seed(render_metadata.get("composition_seed"))
    wild = bool(render_metadata.get("render_wild"))
    render_metadata = {**render_metadata, "render_seed": effective_seed, "render_wild": wild}
    with _render_capacity():
        result = current_render_engine().render(
            score,
            color_map=render_metadata["render_color_map"],
            catalog_id=render_metadata.get("render_color_catalog_id"),
            # The paper performed on, from the one place that records it. When
            # the metadata names none, the Score's own declaration stands.
            canvas_aspect=render_metadata.get("render_canvas_aspect_id"),
            svg_profile=_validated_svg_profile(svg_profile),
            render_seed=effective_seed,
            composition_seed=composition_seed,
            wild=wild,
        )
    return result.svg, {**render_metadata, **result.metadata}


def _resolved_catalog_id(catalog_id: str | None) -> str:
    catalog = get_color_catalog(catalog_id)
    if catalog is None:
        raise HTTPException(status_code=422, detail=f"unsupported color catalog: {catalog_id}")
    return str(catalog["id"])


# What decided the colors of one render. Reported so that a caller which asked
# for a work's own colors can tell whether it got them: a work saved before the
# snapshot existed still draws, but from today's definition, and the two are
# not the same picture.
COLOR_SOURCE_SNAPSHOT = "snapshot"
COLOR_SOURCE_CATALOG = "catalog"
# /api/render-svg answers with the picture itself, so these ride in headers.
# The id is here too because a caller that sent a work reference did NOT decide
# the catalog -- the work did -- and cannot otherwise learn which one drew it.
COLOR_SOURCE_HEADER = "X-Inku-Color-Source"
COLOR_CATALOG_ID_HEADER = "X-Inku-Color-Catalog-Id"

# What decided the limits of one render, reported for the reason the color
# source is. `render_limits` says which numbers were used; it does not say
# whether they came off the work's own row or off today's settings, and a work
# redrawn under a smaller ceiling than the one it was drawn under is a different
# picture. Only this tells the two apart.
LIMITS_SOURCE_REQUEST = "request"
LIMITS_SOURCE_WORK = "work"
# The work is in hand but its row records no limits: drawn before they were
# recorded. It draws at today's settings, which is NOT the same answer as
# "nobody named a work" -- that one had nothing else to draw at.
LIMITS_SOURCE_WORK_UNRECORDED = "work_unrecorded"
LIMITS_SOURCE_SETTINGS = "settings"
# /api/render-svg answers with the picture itself, so this rides in a header.
LIMITS_SOURCE_HEADER = "X-Inku-Limits-Source"


def _work_for_color_snapshot(actor: dict, work_id: str) -> dict:
    """The work whose colors are being asked for.

    Read under the caller's own user id, so a work_id naming someone else's
    work is indistinguishable here from one naming nothing at all: both leave
    `get_items` empty and answer 404. That is the authorization point for this
    key -- there is no second path to a stored snapshot.
    """
    items = _db.get_items(actor["id"], [work_id])
    if not items:
        raise HTTPException(status_code=404, detail="unknown work")
    return items[0]


def _snapshot_render_metadata(item: dict, *, canvas_aspect: str | None = None) -> dict | None:
    """Render metadata built from what the work recorded, not from the catalog.

    Returns None when the row carries no snapshot; the caller then falls to the
    current definition and says so. The catalog id is carried through unchanged
    because it is not only a nameplate: the renderer hashes it into the seed
    that picks each chromatic work color (`_WORK_COLOR_SEED_FIELDS`), so a work
    redrawn under a different id gets a different assignment out of the very
    same map.
    """
    color_map = item.get("render_color_map")
    if not isinstance(color_map, dict) or not color_map:
        return None
    drawn_with = item.get("render_color_catalog_id") or item.get("catalog_id") or DEFAULT_COLOR_CATALOG_ID
    catalog = get_color_catalog(drawn_with)
    metadata = _base_render_metadata(canvas_aspect)
    metadata.update({
        "render_color_catalog_id": str(drawn_with),
        "render_color_catalog_name": str(
            item.get("render_color_catalog_name") or (catalog["name"] if catalog else drawn_with)
        ),
        "render_color_catalog_sub": str(
            item.get("render_color_catalog_sub") or (catalog["sub"] if catalog else "")
        ),
    })
    metadata["render_color_map"] = {str(key): str(value) for key, value in color_map.items()}
    return metadata


def _color_render_metadata(
    *,
    work: dict | None,
    catalog_id: str | None,
    canvas_aspect: str | None = None,
) -> tuple[dict, str, str]:
    """The colors this render will use, and where they came from.

    With no work reference this is the path every drawing took before: the id
    picks today's definition, and an id today's build does not know is a 422.
    With one, the work's own snapshot wins and `_resolved_catalog_id` is never
    reached -- which is what lets a retired or since-renamed id still draw.
    """
    if work is not None:
        snapshot = _snapshot_render_metadata(work, canvas_aspect=canvas_aspect)
        if snapshot is not None:
            return snapshot, str(snapshot["render_color_catalog_id"]), COLOR_SOURCE_SNAPSHOT
        # A work with no snapshot falls to the current definition rather than
        # 422: refusing here would leave exactly the works that predate the
        # snapshot unable to be redrawn at all.
        resolved = _resolved_catalog_id(catalog_id) if get_color_catalog(catalog_id) else DEFAULT_COLOR_CATALOG_ID
        return _render_metadata(resolved, canvas_aspect=canvas_aspect), resolved, COLOR_SOURCE_CATALOG
    resolved = _resolved_catalog_id(catalog_id)
    return _render_metadata(resolved, canvas_aspect=canvas_aspect), resolved, COLOR_SOURCE_CATALOG


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


# The word a writer uses to say Stage 2 held. A value rather than NULL on
# purpose: NULL already means "this row predates the column", and one field
# cannot carry both readings at once.
COMPOSE_FALLBACK_NONE = "none"


def compose_fallback_value(*, fallback_used: bool, reasons: list[str] | None) -> str:
    """What to record about Stage 2 for a work being saved now.

    Always a string, never None: a writer that knows the answer says so either
    way, so a reader can tell a work whose compose held from one drawn before
    anybody wrote this down. The reason is the first the stage gave, which is
    the same shape Stage 1's column already uses.
    """
    if not fallback_used:
        return COMPOSE_FALLBACK_NONE
    for reason in reasons or []:
        if reason:
            return reason
    return "stage2_fallback"


def _capture_history_coerce_observability(
    score: Score,
    *,
    ddl: str | None,
    lang: str | None,
    auto_repair: bool,
    include_trace: bool,
):
    """Create a private capture independent of the public trace response flag."""
    from ..coerce.observability import capture_context

    trace = capture_context(score, ddl=ddl, lang=lang)
    if not auto_repair:
        trace.mark_not_executed("auto_repair_off")
    return trace


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
    compose_fallback: str | None = None,
    elapsed_ms: int = 0,
    stage1_model: str | None = None,
    stage2_model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    catalog_id: str | None = None,
    catalog_mode: str | None = None,
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
    sketch_text: str | None = None,
    sketch_grain: str | None = None,
    sketch_state: str | None = None,
    coerce_observability: dict | None = None,
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
        "compose_fallback": compose_fallback,
        "score": score_dict,
        "svg": svg,
        "at": at,
        "elapsed_ms": elapsed_ms,
        "stage1_model": stage1_model,
        "stage2_model": stage2_model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
"catalog_id": catalog_id,
"catalog_mode": catalog_mode,
"source_text": source_text if source_text is not None else input_text,
"display_label": display_label,
"batch_line_number": batch_line_number,
"batch_run_id": batch_run_id,
"history_visibility": history_visibility,
"lineage_parent_node_id": lineage_parent_node_id,
"derivation_kind": derivation_kind,
"derivation_metadata": derivation_metadata or {},
"idempotency_key": idempotency_key,
"sketch_text": sketch_text,
"sketch_grain": sketch_grain,
"sketch_state": sketch_state,
"score_pre_coerce": (coerce_observability or {}).get("score_pre_coerce"),
"coerce_trace_version": (coerce_observability or {}).get("trace_version"),
"coerce_catalog_digest": (coerce_observability or {}).get("catalog_digest"),
"coerce_trace": {
    key: value
    for key, value in (coerce_observability or {}).items()
    if key not in {"score_pre_coerce", "trace_version", "catalog_digest", "catalog_snapshot"}
} if coerce_observability else None,
"coerce_catalog_snapshot": (coerce_observability or {}).get("catalog_snapshot"),
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
    # Unconditional, unlike the artifact save above: the listing draws from
    # thumbnails whether or not this installation also keeps files on disk.
    _submit_thumbnail_build(item_dict)
    return item_dict
