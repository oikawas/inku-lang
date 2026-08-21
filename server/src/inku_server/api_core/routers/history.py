"""Endpoints for the history group, moved out of api.py unchanged."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from ...animation_export import build_animation
from ...card_export import build_card
from ...feature_analysis import composition_distance
from ...coerce import coerce_score
from ...ddl_expander import FOCUS_IDS
from ...limits import limits_as_dict, using_limits
from ...schema import Score
from ...sketch import SketchDetail, normalize_sketch_grain, sketch_state_of
from ... import db as _db
from ... import thumbs_db as _thumbs_db
from ..common import _unexpected_http_error
from ..deps import _current_user
from ..models import HistoryItem, HistoryListResponse, HistoryPostBody
from ..rendering import _capture_history_coerce_observability, _effective_limits, _add_history_item, _render_metadata, _render_score_svg, _render_seed_from_text, _render_with_metadata, _resolved_catalog_id, _save_history_artifacts, _score_canvas_aspect_value, _score_with_canvas, _validated_canvas_aspect_override, _validated_svg_profile, _validated_variation_amplitude


router = APIRouter(dependencies=[Depends(_current_user)])


class HistoryIdsBody(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=1000)


class AnimationExportBody(BaseModel):
    ids: list[str] = Field(..., min_length=2, max_length=100)
    format: Literal["apng", "gif"] = "apng"
    pattern: Literal["cut", "crossfade", "fade_white", "slide"] = "cut"
    hold_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    resolution: Literal["1k", "4k", "8k"] = "1k"
    height_px: int | None = Field(default=None, ge=64, le=12000)


class HistoryStateResponse(BaseModel):
    """The listing's shape, without the listing.

    Three scalars, and every one of them earns its place: `total` catches a work
    appearing or being trashed, `newest_at` catches a new save, and `newest_id`
    separates two saves that landed in the same millisecond.
    """

    total: int
    newest_at: int | None = None
    newest_id: str | None = None


class CardExportBody(BaseModel):
    id: str
    layout: Literal["square", "portrait"] = "square"
    # On by default. A card that carries no mark of where it came from is the
    # honest option to offer, not the one to make people opt into.
    seal: bool = True


class HistoryStarBody(BaseModel):
    starred: bool = False
    note: str | None = None


class HistoryForRevisionBody(BaseModel):
    for_revision: bool = False


class HistoryForShareBody(BaseModel):
    """The permission bit and, optionally, where it points.

    Two keys rather than one because the destination has to be sayable without
    being compulsory: leaving it out means "my own organisation", which is what
    almost every caller wants, while naming it is how an administrator hands a
    work to another group.
    """

    for_share: bool = False
    share_group_id: str | None = None


class HistoryAclEntry(BaseModel):
    """One guest on one work's list."""

    subject_type: Literal["user", "org_group"]
    subject_id: str = Field(..., min_length=1, max_length=100)
    permission: Literal["read", "write"]


class HistoryAclEntryOut(HistoryAclEntry):
    id: str
    history_id: str
    at: int


class HistoryAclBody(BaseModel):
    """The whole list, not a patch.

    Sending the complete list is what makes revoking expressible: a subject the
    caller leaves out loses its access. A patch shape would need a separate
    delete verb, and a client that never learned it would never revoke anything.
    """

    entries: list[HistoryAclEntry] = Field(default_factory=list, max_length=200)


@router.get("/api/history", response_model=HistoryListResponse, response_model_exclude_none=True)
def api_history_get(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    trashed: bool = Query(default=False),
    starred: bool = Query(default=False),
    for_revision: bool = Query(default=False),
    for_share: bool = Query(default=False),
    q: str = Query(default="", max_length=200),
    anchor_id: str | None = Query(default=None, max_length=100),
    include_svg: bool = Query(
        default=True,
        description="Send each work's whole SVG. Clients that draw from thumbnails send false.",
    ),
    actor: dict = Depends(_current_user),
) -> HistoryListResponse:
    if anchor_id:
        position = _db.item_position(
            actor["id"], anchor_id, trashed=trashed, starred=starred,
            for_revision=for_revision, for_share=for_share,
        )
        if position is not None:
            offset = (position // limit) * limit
    items, total = _db.list_items(
        actor["id"],
        offset=offset,
        limit=limit,
        trashed=trashed,
        query_text=q,
        starred=starred,
        for_revision=for_revision,
        for_share=for_share,
    )
    # How heavy each work is, counted here because this is the last place the
    # picture is in hand: below, `include_svg=false` empties the key, and a
    # client that measured what it received would be measuring the emptying.
    # UTF-8 bytes, the same quantity measureSvgWeight().bytes counts on the page
    # and measure() counts in no-git-sync/scripts/svg_weight.py.
    items = [{**item, "svg_bytes": len((item.get("svg") or "").encode("utf-8")) } for item in items]
    if not include_svg:
        # Emptied, not removed. A client that has never heard of this flag still
        # finds the key where it has always been, holding a string; taking the
        # key away would make "no picture asked for" and "old server" the same
        # shape on the wire. Twenty-one works cost 23.5 MB with the pictures and
        # 163 KB without them, measured on the production database.
        items = [{**item, "svg": ""} for item in items]
    return HistoryListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/api/history/state", response_model=HistoryStateResponse)
def api_history_state(actor: dict = Depends(_current_user)) -> HistoryStateResponse:
    """What a poller needs to decide whether to ask for the listing at all.

    The client that draws the strip refetches every twelve seconds so a work
    saved in another window appears. Nearly every one of those rounds finds
    nothing changed and rebuilds no part of the page, so asking the question
    here -- a few hundred bytes -- and fetching the listing only when the answer
    moves is the whole point of this route.

    `newest_id` is not redundant beside `newest_at`: two works saved inside one
    millisecond share an `at`, and without the id the second one would never be
    noticed.
    """
    total, newest_at, newest_id = _db.list_state(actor["id"])
    return HistoryStateResponse(total=total, newest_at=newest_at, newest_id=newest_id)


@router.post("/api/history/export-animation")
def api_history_export_animation(
    body: AnimationExportBody,
    actor: dict = Depends(_current_user),
) -> Response:
    ids = list(dict.fromkeys(body.ids))
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="at least two distinct works are required")
    items = _db.get_items(actor["id"], ids)
    if len(items) != len(ids):
        raise HTTPException(status_code=404, detail="one or more history items were not found")
    svgs = [str(item.get("svg") or "") for item in items]
    if any(not svg for svg in svgs):
        raise HTTPException(status_code=409, detail="one or more works have no saved SVG")
    try:
        payload = build_animation(
            svgs,
            output_format=body.format,
            pattern=body.pattern,
            hold_seconds=body.hold_seconds,
            resolution=body.resolution,
            height_px=body.height_px,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    extension = "png" if body.format == "apng" else "gif"
    media_type = "image/apng" if body.format == "apng" else "image/gif"
    filename = f"inku-animation-{timestamp}.{extension}"
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": "attachment; filename=\"" + filename + "\"",
            "Cache-Control": "no-store",
        },
    )


@router.post("/api/history/export-card")
def api_history_export_card(
    body: CardExportBody,
    actor: dict = Depends(_current_user),
) -> Response:
    items = _db.get_items(actor["id"], [body.id])
    if not items:
        raise HTTPException(status_code=404, detail="history item not found")
    item = items[0]
    svg = str(item.get("svg") or "")
    if not svg:
        raise HTTPException(status_code=409, detail="this work has no saved SVG")
    try:
        payload = build_card(
            svg,
            # The headnote is the description the author typed; ja.ts calls the
            # canvas overlay of this same text 詞書.
            headnote=str(item.get("input") or ""),
            # The seed that fixes the performance, so the tail identifies this
            # picture rather than the variation it was drawn under.
            seed=item.get("render_seed"),
            layout=body.layout,
            seal=body.seal,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"inku-card-{timestamp}.png"
    return Response(
        content=payload,
        media_type="image/png",
        headers={
            "Content-Disposition": "attachment; filename=\"" + filename + "\"",
            "Cache-Control": "no-store",
        },
    )


@router.get("/api/history/{item_id}/neighbors", response_model=list[HistoryItem], response_model_exclude_none=True)
def api_history_neighbors(item_id: str, actor: dict = Depends(_current_user)) -> list[HistoryItem]:
    focus = _db.get_items(actor["id"], [item_id])
    if not focus:
        raise HTTPException(status_code=404, detail="history item not found")
    candidates = _db.list_neighbor_candidates(actor["id"], item_id)
    ranked = sorted(
        candidates,
        key=lambda item: (composition_distance(focus[0].get("score") or {}, item.get("score") or {}), -int(item.get("at") or 0)),
    )[:3]
    return [HistoryItem(**item) for item in _db.get_items(actor["id"], [item["id"] for item in ranked])]


# A year, and immutable: a saved work's SVG never changes, so neither does the
# picture baked from it. `v` exists for the case that is not covered by that --
# a rebuild bakes a work again, and a browser told `immutable` would never ask.
# Clients pass the work's render_hash there, so a rebuilt thumbnail arrives
# under a URL the cache has not seen. The server ignores its value; answering
# 404 for a mismatch would blank the listing for the length of a rebuild.
_THUMB_CACHE_CONTROL = "private, max-age=31536000, immutable"


def _thumb_etag(row: dict) -> str:
    # The source hash identifies the picture; the scale distinguishes the two
    # sizes baked from it. built_at only stands in for works saved before the
    # render hash existed.
    source = row.get("source_render_hash") or f"built-{row.get('built_at')}"
    return f'"{source}-{row.get("scale")}"'


@router.get("/api/history/{item_id}/thumb")
def api_history_thumb(
    item_id: str,
    request: Request,
    scale: int = Query(default=1, ge=1, le=2),
    v: str = Query(default="", max_length=100, description="Cache key; the work's render hash. Not read."),
    actor: dict = Depends(_current_user),
) -> Response:
    """The listing's picture of one work, as a PNG.

    Nothing is drawn here. The bytes were baked from the SVG this work has been
    holding since it was saved; if none were, the answer is 404 and the client
    draws the SVG itself.
    """
    # The listing's own rule, not a second one: get_items() applies the same
    # visibility and sharing checks, and answers with nothing -- so, 404 -- for
    # a work this caller may not see.
    if not _db.get_items(actor["id"], [item_id]):
        raise HTTPException(status_code=404, detail="history item not found")
    row = _thumbs_db.get_thumb(item_id, scale)
    if row is None:
        raise HTTPException(status_code=404, detail="thumbnail not found")
    etag = _thumb_etag(row)
    headers = {"ETag": etag, "Cache-Control": _THUMB_CACHE_CONTROL}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=row["png"], media_type="image/png", headers=headers)


@router.get("/api/history/{item_id}/svg")
def api_history_svg(
    item_id: str,
    profile: str = Query(default="display", description="SVG output profile: display / editable / compat"),
    actor: dict = Depends(_current_user),
) -> Response:
    svg_profile = _validated_svg_profile(profile)
    items = _db.get_items(actor["id"], [item_id])
    if not items:
        raise HTTPException(status_code=404, detail="history item not found")
    item = items[0]
    if svg_profile == "display":
        svg = item.get("svg", "")
    else:
        try:
            # The work is already in hand here, so it supplies its own colors:
            # this redraw is the same work, and re-resolving the id would give
            # it today's definition instead of the one it was drawn with.
            svg, _, _, _ = _render_score_svg(
                item.get("score", {}),
                catalog_id=item.get("catalog_id") or item.get("render_color_catalog_id"),
                svg_profile=svg_profile,
                # Both seeds off the row, not one. `wild` and `composition_seed`
                # were read here and `render_seed` was not, so the marks landed
                # where the saved work put them and every stroke was drawn by a
                # different hand. What separates this export from the saved
                # picture is the engine having moved on (principle 7); a seed
                # left behind put a second difference on top of that one.
                render_seed=item.get("render_seed"),
                composition_seed=item.get("composition_seed"),
                wild=bool(item.get("render_wild")),
                work=item,
            )
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _unexpected_http_error("history svg render", 422) from e
    return Response(content=svg, media_type="image/svg+xml; charset=utf-8")


def _derived_sketch_state(body: HistoryPostBody) -> str:
    """Name the state for a client that saved a drawing without naming one.

    Read off the same two fields the row already carries, through the one
    derivation function, so this writer cannot mean something different by
    "off" than the paint route does.
    """
    prose = (body.sketch_text or "").strip()
    detail = (
        SketchDetail(text=prose, grain=normalize_sketch_grain(body.sketch_grain))
        if prose
        else None
    )
    return sketch_state_of(
        detail,
        requested=False,
        has_description=bool((body.input or "").strip()),
    )


@router.post("/api/history", response_model=HistoryItem, response_model_exclude_none=True)
def api_history_post(
    body: HistoryPostBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> HistoryItem:
    metadata_seed_text = body.derivation_metadata.get("seed_text")
    requested_seed_text = body.seed_text
    if requested_seed_text is None and isinstance(metadata_seed_text, str):
        requested_seed_text = metadata_seed_text
    render_seed, seed_text = _render_seed_from_text(requested_seed_text, body.render_seed)
    try:
        # Site 2 of 5.
        limits = _effective_limits()
        pre_coerce_score = Score.model_validate(body.score)
        coerce_observability = _capture_history_coerce_observability(
            pre_coerce_score,
            ddl=None,
            lang=body.instruction_lang_resolved,
            auto_repair=True,
            include_trace=False,
        )
        with using_limits(limits):
            score = coerce_score(
                pre_coerce_score,
                limits=limits,
                lang=body.instruction_lang_resolved,
                trace=coerce_observability,
            )
        catalog_id = _resolved_catalog_id(body.catalog_id)
        canvas_aspect = _validated_canvas_aspect_override(body.canvas_aspect)
        if canvas_aspect is not None:
            score = _score_with_canvas(score, canvas_aspect)
        render_metadata = {
            **_render_metadata(catalog_id, canvas_aspect=_score_canvas_aspect_value(score)),
            "stage1_prompt_digest": body.stage1_prompt_digest,
            "stage1_prompt_base_digest": body.stage1_prompt_base_digest,
            "stage2_prompt_digest": body.stage2_prompt_digest,
            "instruction_lang_requested": body.instruction_lang_requested,
            "instruction_lang_resolved": body.instruction_lang_resolved,
            "ui_lang": body.ui_lang,
            "render_seed": render_seed,
            "composition_seed": body.composition_seed,
            "focus": body.focus if body.focus in FOCUS_IDS else None,
            "variation_amplitude": _validated_variation_amplitude(body.variation_amplitude),
            "variation_seed": body.variation_seed,
            "seed_text": seed_text,
            "interpretation_seed": body.interpretation_seed,
            # What actually governed this work. Without it a per-install setting
            # would make the same description a different work with nothing on
            # the row to say why.
            "render_limits": limits_as_dict(limits),
        }
        svg, render_metadata = _render_with_metadata(score, render_metadata)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("history score render", 422) from e
    item_dict = _add_history_item(
        actor=actor,
        input_text=body.input,
        ddl=body.ddl,
        expanded_ddl=body.expanded_ddl,
        interpret_fallback=body.interpret_fallback,
        # Taken as the sender wrote it, including "none". Deriving it here is
        # not possible: this route never ran Stage 2, so only the client that
        # holds the paint response knows whether it fell.
        compose_fallback=body.compose_fallback,
        score=score,
        svg=svg,
        at=body.at,
        elapsed_ms=body.elapsed_ms,
        stage1_model=body.stage1_model,
        stage2_model=body.stage2_model,
        tokens_in=body.tokens_in,
        tokens_out=body.tokens_out,
        catalog_id=None if catalog_id == "default" else catalog_id,
        catalog_mode=body.catalog_mode,
        save_artifacts=body.save_artifacts,
        render_metadata=render_metadata,
        source_text=body.source_text,
        display_label=body.display_label,
        batch_line_number=body.batch_line_number,
        batch_run_id=body.batch_run_id,
        history_visibility=body.history_visibility,
        lineage_parent_node_id=body.lineage_parent_node_id,
        derivation_kind=body.derivation_kind,
        derivation_metadata=body.derivation_metadata,
        idempotency_key=idempotency_key,
        sketch_text=body.sketch_text,
        sketch_grain=body.sketch_grain,
        # The client knows its own path and may name the state (the field is
        # pattern-checked, so an unknown value is already a 422). A client that
        # says nothing still gets a state: leaving NULL here would record every
        # work this endpoint saves as older than the column.
        sketch_state=body.sketch_state or _derived_sketch_state(body),
        coerce_observability=coerce_observability.persistable(),
    )
    if body.count_generation and not item_dict.get("_idempotent_replay"):
        if _db.increment_user_generation_count(actor["id"]) is None:
            raise HTTPException(status_code=404, detail="user not found")
    return HistoryItem(**item_dict)


@router.delete("/api/history")
def api_history_delete(
    x_inku_confirm: str | None = Header(default=None, alias="X-Inku-Confirm"),
    actor: dict = Depends(_current_user),
) -> dict[str, int | bool]:
    if x_inku_confirm != "permanent-delete-trash":
        raise HTTPException(
            status_code=409,
            detail="X-Inku-Confirm: permanent-delete-trash is required",
        )
    count = _db.delete_all_trashed_items(actor["id"])
    return {"ok": True, "count": count}


@router.post("/api/history/trash")
def api_history_trash(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.trash_items(actor["id"], body.ids)
    return {"ok": True, "count": count}


@router.post("/api/history/restore")
def api_history_restore(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.restore_items(actor["id"], body.ids)
    return {"ok": True, "count": count}


@router.patch("/api/history/{item_id}/star", response_model=HistoryItem, response_model_exclude_none=True)
def api_history_star(item_id: str, body: HistoryStarBody, actor: dict = Depends(_current_user)) -> HistoryItem:
    item = _db.set_item_starred(actor["id"], item_id, body.starred, body.note)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    return HistoryItem(**item)


@router.patch("/api/history/{item_id}/for-revision", response_model=HistoryItem, response_model_exclude_none=True)
def api_history_for_revision(
    item_id: str, body: HistoryForRevisionBody, actor: dict = Depends(_current_user)
) -> HistoryItem:
    item = _db.set_item_for_revision(actor["id"], item_id, body.for_revision)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    return HistoryItem(**item)


@router.patch("/api/history/{item_id}/for-share", response_model=HistoryItem, response_model_exclude_none=True)
def api_history_for_share(
    item_id: str, body: HistoryForShareBody, actor: dict = Depends(_current_user)
) -> HistoryItem:
    """Open one work to an organisation group, or close it again.

    404, not 403, when the caller may not write the work: the same rule the ACL
    routes follow, because saying "that exists but is not yours" discloses it.
    403 is kept for the one case where the caller may write the work and is
    still refused -- naming a group that is not their own.
    """
    try:
        item = _db.set_item_for_share(actor["id"], item_id, body.for_share, body.share_group_id)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    return HistoryItem(**item)


@router.get("/api/history/{item_id}/acl", response_model=list[HistoryAclEntryOut])
def api_history_acl_get(item_id: str, actor: dict = Depends(_current_user)) -> list[HistoryAclEntryOut]:
    entries = _db.list_history_acl(actor["id"], item_id)
    if entries is None:
        # 404 rather than 403 throughout: telling a caller who may not see a work
        # that it exists is itself a disclosure.
        raise HTTPException(status_code=404, detail="history item not found")
    return [HistoryAclEntryOut(**entry) for entry in entries]


@router.put("/api/history/{item_id}/acl", response_model=list[HistoryAclEntryOut])
def api_history_acl_put(
    item_id: str, body: HistoryAclBody, actor: dict = Depends(_current_user)
) -> list[HistoryAclEntryOut]:
    try:
        entries = _db.replace_history_acl(actor["id"], item_id, [e.model_dump() for e in body.entries])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if entries is None:
        raise HTTPException(status_code=404, detail="history item not found")
    return [HistoryAclEntryOut(**entry) for entry in entries]


@router.post("/api/history/rebuild-output-files")
def api_history_rebuild_output_files(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    items = _db.get_items(actor["id"], body.ids)
    for item in items:
        _save_history_artifacts(item)
    return {"ok": True, "count": len(items)}


@router.post("/api/history/permanent-delete")
def api_history_permanent_delete(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.delete_items(actor["id"], body.ids, require_trashed=True)
    return {"ok": True, "count": count}
