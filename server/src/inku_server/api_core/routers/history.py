"""Endpoints for the history group, moved out of api.py unchanged."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field, ValidationError
from ...animation_export import build_animation, build_layer_animation
from ...card_export import build_card
from ...limits import limits_as_dict
from ...saved_score_compat import coerce_saved_score
from ...schema import Score
from ...sketch import SketchDetail, normalize_sketch_grain, sketch_state_of
from ... import db as _db
from ... import thumbs_db as _thumbs_db
from ..common import DESCRIPTION_LOCKED_DETAIL, _unexpected_http_error
from ...persistence.description_lock import DESCRIPTION_READING_KINDS
from ...persistence.schema import LineageNodeRow
from ...persistence.variation_authority import LAWS_RECORD_KEYS
from ..deps import _current_user
from ..models import HistoryItem, HistoryListResponse, HistoryPostBody
from ..rendering import _COMPACT_SCORE_VERSIONS, _capture_history_coerce_observability, _effective_limits, _add_history_item, _output_save_settings, _render_metadata, _render_score_svg, _render_with_metadata, _resolved_catalog_id, _save_history_artifacts, _score_canvas_aspect_value, _score_with_canvas, _validated_canvas_aspect_override, _validated_svg_profile


router = APIRouter(dependencies=[Depends(_current_user)])


class HistoryIdsBody(BaseModel):
    ids: list[str] = Field(
        default_factory=list,
        max_length=1000,
        description="Ids of the works to act on. Ids that are not found for the caller are skipped. Empty by default.",
    )


class AnimationExportBody(BaseModel):
    ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Ids of the works to animate, in playing order. One id makes a layer animation of that work; several make a sequence. Duplicates are removed, keeping the first.",
    )
    format: Literal["apng", "gif"] = Field(default="apng", description="File format of the animation: apng or gif.")
    pattern: Literal["cut", "crossfade", "fade_white", "slide"] = Field(
        default="cut",
        description="Transition between works in a sequence: cut, crossfade, fade_white or slide. Not used for a single work.",
    )
    hold_seconds: float = Field(
        default=1.0, ge=0.1, le=30.0, description="Seconds each frame is held, from 0.1 to 30."
    )
    resolution: Literal["1k", "4k", "8k"] = Field(
        default="1k", description="Frame height of the animation: 1k is 1080 px, 4k is 2160 px, 8k is 4320 px. Not used when height_px is set."
    )
    height_px: int | None = Field(
        default=None,
        ge=64,
        le=12000,
        description="Height of each frame in pixels, from 64 to 12000. Omit to use the height of the chosen resolution.",
    )
    layer_frame_count: int = Field(
        default=12,
        ge=2,
        le=120,
        description="Number of frames in a layer animation of a single work, from 2 to 120. Not used for a sequence.",
    )
    replay: Literal["restart", "reverse", "once"] = Field(
        default="restart",
        description="How a layer animation plays: restart (loop from the start), reverse (loop back and forth) or once (play one time). Not used for a sequence.",
    )


class HistoryStateResponse(BaseModel):
    """The listing's shape, without the listing.

    Three scalars, and every one of them earns its place: `total` catches a work
    appearing or being trashed, `newest_at` catches a new save, and `newest_id`
    separates two saves that landed in the same millisecond.
    """

    total: int = Field(description="Number of works the caller may read, in the live listing.")
    newest_at: int | None = Field(
        default=None,
        description="Save time of the newest work, in milliseconds since the Unix epoch. None when there are no works.",
    )
    newest_id: str | None = Field(
        default=None,
        description="Id of the newest work. None when there are no works.",
    )


class CardExportBody(BaseModel):
    id: str = Field(description="Id of the work to put on the card.")
    layout: Literal["square", "portrait"] = Field(
        default="square", description="Card layout: square or portrait."
    )
    # On by default. A card that carries no mark of where it came from is the
    # honest option to offer, not the one to make people opt into.
    seal: bool = Field(
        default=True,
        description="When true, the card carries a seal that marks where the work came from. Set false to leave the seal off.",
    )
    # The bitmap's height in pixels; absent keeps the layout's own size.
    height: int | None = Field(
        default=None,
        ge=256,
        le=4096,
        description="Height of the card's bitmap in pixels, from 256 to 4096. Omit to keep the layout's own size.",
    )


class HistoryStarBody(BaseModel):
    starred: bool = Field(default=False, description="True to star the work, false to remove the star.")
    note: str | None = Field(
        default=None, description="Note for the work, up to 240 characters. Leave it out to keep the current note; send an empty string to clear it."
    )


class HistoryForRevisionBody(BaseModel):
    for_revision: bool = Field(
        default=False,
        description="True to mark the work for revision, false to clear the mark.",
    )


class HistoryForShareBody(BaseModel):
    """Whether a work is open to a user group, and optionally which group."""

    for_share: bool = Field(
        default=False,
        description="True to open the work to a user group, false to close it again.",
    )
    share_group_id: str | None = Field(
        default=None,
        description="Id of the user group to open the work to. Omit to keep the group the work already has, or the owner's group if it has none. Naming a group other than your own needs administrator rights.",
    )


class HistoryAclEntry(BaseModel):
    """One guest on one work's list."""

    subject_type: Literal["user", "org_group"] = Field(
        description="Kind of guest: user for one person, or org_group for a user group."
    )
    subject_id: str = Field(
        ..., min_length=1, max_length=100, description="Id of the guest user or user group."
    )
    permission: Literal["read", "write"] = Field(
        description="What the guest may do with the work: read or write."
    )


class HistoryAclEntryOut(HistoryAclEntry):
    id: str = Field(description="Id of this access entry.")
    history_id: str = Field(description="Id of the work the entry applies to.")
    at: int = Field(description="Time the entry was recorded, in milliseconds since the Unix epoch.")


class HistoryAclBody(BaseModel):
    """The whole list, not a patch.

    Sending the complete list is what makes revoking expressible: a subject the
    caller leaves out loses its access. A patch shape would need a separate
    delete verb, and a client that never learned it would never revoke anything.
    """

    entries: list[HistoryAclEntry] = Field(
        default_factory=list,
        max_length=200,
        description="The complete guest list for the work. An empty list removes every guest.",
    )


@router.get(
    "/api/history",
    response_model=HistoryListResponse,
    response_model_exclude_none=True,
    summary="List history items",
)
def api_history_get(
    offset: int = Query(default=0, ge=0, description="Number of works to skip before the first one returned."),
    limit: int = Query(default=10, ge=1, le=100, description="Maximum number of works to return, from 1 to 100."),
    trashed: bool = Query(default=False, description="When true, list works in the trash instead of the live works."),
    starred: bool = Query(default=False, description="When true, list only starred works."),
    for_revision: bool = Query(default=False, description="When true, list only works marked for revision."),
    for_share: bool = Query(default=False, description="When true, list only works opened to a user group."),
    q: str = Query(default="", max_length=200, description="Text to search the works for, up to 200 characters. Empty applies no text filter."),
    canvas_search: bool = Query(default=False, description="When true, the q text is searched in canvas search mode."),
    anchor_id: str | None = Query(
        default=None,
        max_length=100,
        description="Id of a work to bring into view. When it is found, offset moves to the page that holds it. Ignored when canvas_search is true and q is not empty.",
    ),
    include_svg: bool = Query(
        default=True,
        description="Send each work's whole SVG. Clients that draw from thumbnails send false.",
    ),
    actor: dict = Depends(_current_user),
) -> HistoryListResponse:
    """Return one page of the works the caller may read: their own, those shared with them, and those opened to their user group.

    The filters narrow that set.

    The works come with their total count, the offset and the limit that were
    used. When anchor_id names a work that is found, the offset is moved to the
    page that holds it. Each work carries svg_bytes, its SVG size in bytes;
    without include_svg, the svg key is sent as an empty string.
    """
    if anchor_id and not (canvas_search and q.strip()):
        position = _db.item_position(
            actor["id"], anchor_id, trashed=trashed, starred=starred,
            for_revision=for_revision, for_share=for_share,
            **({"query_text": q} if q.strip() else {}),
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
        include_svg=include_svg,
        **({"canvas_search": True} if canvas_search else {}),
    )
    # When the picture is present, count it here. When it is withheld,
    # persistence already measured its UTF-8 byte length in SQLite without
    # materializing the SVG; a client must not mistake the empty transport key
    # for the saved work's size.
    if include_svg:
        items = [{**item, "svg_bytes": len((item.get("svg") or "").encode("utf-8")) } for item in items]
    else:
        # Emptied, not removed. A client that has never heard of this flag still
        # finds the key where it has always been, holding a string; taking the
        # key away would make "no picture asked for" and "old server" the same
        # shape on the wire. Twenty-one works cost 23.5 MB with the pictures and
        # 163 KB without them, measured on the production database.
        items = [{**item, "svg": ""} for item in items]
    return HistoryListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/api/history/state", response_model=HistoryStateResponse, summary="Get the history listing state")
def api_history_state(actor: dict = Depends(_current_user)) -> HistoryStateResponse:
    """Return how many works the listing holds and which is newest, without the works themselves.

    A client can poll this and fetch the listing only when the answer changes.
    `newest_id` tells apart two works saved in the same millisecond, which share
    `newest_at`.
    """
    total, newest_at, newest_id = _db.list_state(actor["id"])
    return HistoryStateResponse(total=total, newest_at=newest_at, newest_id=newest_id)


@router.post("/api/history/export-animation", summary="Export works as an animation")
def api_history_export_animation(
    body: AnimationExportBody,
    actor: dict = Depends(_current_user),
) -> Response:
    """Build an APNG or GIF animation from the saved SVGs of the works sent.

    One work makes a layer animation; several make a sequence joined by the
    chosen transition. The file is returned as an attachment. Returns 404 when
    any id is not found for the caller, 409 when a work has no saved SVG, and
    400 when the animation cannot be built from the settings sent.
    """
    ids = list(dict.fromkeys(body.ids))
    items = _db.get_items(actor["id"], ids)
    if len(items) != len(ids):
        raise HTTPException(status_code=404, detail="one or more history items were not found")
    svgs = [str(item.get("svg") or "") for item in items]
    if any(not svg for svg in svgs):
        raise HTTPException(status_code=409, detail="one or more works have no saved SVG")
    try:
        if len(ids) == 1:
            payload = build_layer_animation(
                svgs[0],
                output_format=body.format,
                frame_count=body.layer_frame_count,
                replay=body.replay,
                hold_seconds=body.hold_seconds,
                resolution=body.resolution,
                height_px=body.height_px,
            )
        else:
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


@router.post("/api/history/export-card", summary="Export a work as a card")
def api_history_export_card(
    body: CardExportBody,
    actor: dict = Depends(_current_user),
) -> Response:
    """Build a PNG card for one work from its saved SVG.

    The card uses the work's description as its headnote and its render seed to
    identify the picture. The PNG is returned as an attachment. Returns 404 when
    the work is not found for the caller, 409 when it has no saved SVG, and 400
    when the card cannot be built from the settings sent.
    """
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
            pixel_height=body.height,
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


@router.get("/api/history/{item_id}/thumb", summary="Get a work's thumbnail")
def api_history_thumb(
    item_id: Annotated[str, Path(description="Id of the work.")],
    request: Request,
    scale: int = Query(default=1, ge=1, le=2, description="Thumbnail size: 1 for the standard size, 2 for the double size."),
    v: str = Query(default="", max_length=100, description="Cache key; the work's render hash. Not read."),
    actor: dict = Depends(_current_user),
) -> Response:
    """The listing's picture of one work, as a PNG.

    Nothing is drawn here. The bytes were baked from the SVG this work has been
    holding since it was saved; if none were, the answer is 404 and the client
    draws the SVG itself.
    """
    # This uses the listing's visibility rule without materializing the work.
    # A thumbnail page asks once per image; loading every SVG and lineage just
    # to answer the permission question made those requests compete with their
    # own PNG transfer.
    if not _db.can_read_history_item(actor["id"], item_id):
        raise HTTPException(status_code=404, detail="history item not found")
    row = _thumbs_db.get_thumb(item_id, scale)
    if row is None:
        raise HTTPException(status_code=404, detail="thumbnail not found")
    etag = _thumb_etag(row)
    headers = {"ETag": etag, "Cache-Control": _THUMB_CACHE_CONTROL}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=row["png"], media_type="image/png", headers=headers)


@router.get("/api/history/{item_id}/svg", summary="Get a work's SVG")
def api_history_svg(
    item_id: Annotated[str, Path(description="Id of the work.")],
    profile: str = Query(default="display", description="SVG output profile: display / editable / compat / live"),
    actor: dict = Depends(_current_user),
) -> Response:
    """Return the SVG of one work in the requested profile.

    The display profile returns the SVG saved with the work. Other profiles are
    drawn again from the work's saved score. Returns 404 when the work is not
    found for the caller and 422 when the redraw fails.
    """
    svg_profile = _validated_svg_profile(profile)
    items = _db.get_items(actor["id"], [item_id])
    if not items:
        raise HTTPException(status_code=404, detail="history item not found")
    item = items[0]
    score = item.get("score") or {}
    if svg_profile == "display":
        svg = item.get("svg", "")
    elif score.get("version") in _COMPACT_SCORE_VERSIONS:
        # The plain render below cannot carry a compact Score's resource
        # policy, and the core refuses such a Score without one
        # (InvalidCompactPerformance). The shared replay reads the policy,
        # colors, paper and limits off the work itself, as /api/render-svg
        # does, and a refusal reaches the app's handler with its reason.
        from ...pipeline_runtime import get_service

        svg = get_service().replay_for(
            actor["id"],
            {
                "score": score,
                "svg_profile": svg_profile,
                "catalog_id": item.get("catalog_id") or item.get("render_color_catalog_id"),
                "render_seed": item.get("render_seed"),
                "composition_seed": item.get("composition_seed"),
                "wild": bool(item.get("render_wild")),
            },
            item,
        )["svg"]
    else:
        try:
            # The work is already in hand here, so it supplies its own colors:
            # this redraw is the same work, and re-resolving the id would give
            # it today's definition instead of the one it was drawn with.
            svg, _, _, _ = _render_score_svg(
                score,
                owner=actor["id"],
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


def _invalid_score_detail(error: ValidationError) -> str:
    """Where a sent Score is wrong, in one line: the first three places."""
    problems = [
        f"{'.'.join(str(part) for part in item['loc']) or 'score'}: {item['msg']}"
        for item in error.errors(include_url=False)
    ]
    more = f" (+{len(problems) - 3} more)" if len(problems) > 3 else ""
    return f"score is invalid: {'; '.join(problems[:3])}{more}"


def _parent_laws_records(owner_id: str, parent_node_id: str) -> dict:
    """The laws records of the owner's work at one lineage node, or none."""
    from ...persistence.variation_authority import VariationAuthorityStore
    from ...pipeline_api import laws_records_of

    with _db.SessionLocal() as session:
        node = session.get(LineageNodeRow, parent_node_id)
        parent_id = node.history_id if node else None
    return laws_records_of(VariationAuthorityStore(_db.engine), owner_id, parent_id) if parent_id else {}


@router.post("/api/history", response_model=HistoryItem, response_model_exclude_none=True, summary="Save a work to history")
def api_history_post(
    body: HistoryPostBody,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=200,
        description="Key that makes a repeated save return the work saved earlier instead of saving it again. Omit to save on every call.",
    ),
    actor: dict = Depends(_current_user),
) -> HistoryItem:
    """Save a work into the caller's history and return it.

    The body may carry a score that is checked, coerced and drawn on the server,
    a replay of a saved work, or a child of a lineage node. Returns 404 when a
    named lineage node or parent is not found, 409 when the parent's description
    is locked or a replay preview has changed, and 422 when the score or the
    replay request is invalid.
    """
    replay_link = None
    # A sender never names a laws record: the Server writes them only on the edges
    # of the children it draws from their parent (color arrangement, support,
    # touches, redraw) and of a layout or catalog change child, and reads them only
    # there (2026-10-20).
    if any(key in body.derivation_metadata for key in LAWS_RECORD_KEYS):
        body = body.model_copy(update={"derivation_metadata": {
            key: value for key, value in body.derivation_metadata.items() if key not in LAWS_RECORD_KEYS}})
    if body.derivation_kind in ("layout_change", "catalog_change") and body.lineage_parent_node_id:
        # "Change the layout" keeps the layers the laws placed, and the screen saves
        # its child as drawn: the child keeps its parent's records, so that the
        # layout can change again. A catalog change draws the parent's Score in
        # another catalog with the same instructions, so its child keeps them for
        # the layout and the laws move (2026-10-21; until then it kept none, and
        # both answered unsupported_sentence on 5173 Build 1303). The core reads
        # each only while the child's instructions still match it (2026-10-20).
        body = body.model_copy(update={"derivation_metadata": {
            **body.derivation_metadata, **_parent_laws_records(actor["id"], body.lineage_parent_node_id)}})
    # A work read again from the description (model or language comparison
    # and the like) cannot descend from a work its DDL holds.
    if (
        body.lineage_parent_node_id
        and body.derivation_kind in DESCRIPTION_READING_KINDS
        and _db.lineage_node_description_locked(body.lineage_parent_node_id)
    ):
        raise HTTPException(status_code=409, detail=DESCRIPTION_LOCKED_DETAIL)
    replay_save = any(value is not None for value in (
        body.replay_work_id, body.replay_render_hash, body.replay_svg_sha256,
    ))
    if not replay_save:
        render_seed = body.render_seed
    if replay_save:
        from .render import _render_authorized_score, _saved_work_replay_request
        from ..rendering import _work_for_color_snapshot

        if not all((body.replay_work_id, body.replay_render_hash, body.replay_svg_sha256)) or body.derivation_kind != "replay":
            raise HTTPException(status_code=422, detail="replay save requires a source work and preview hashes")
        parent = _work_for_color_snapshot(actor, body.replay_work_id)
        if not body.lineage_parent_node_id or body.lineage_parent_node_id != parent.get("lineage_node_id"):
            raise HTTPException(status_code=422, detail="replay parent must match the source work")
        if parent.get("pipeline_variation_id"):
            from ...persistence.schema import VariationAuthorityActionRow
            from ...persistence.variation_authority import VariationAuthorityAdapterError, VariationAuthorityStore

            store = VariationAuthorityStore(_db.engine)
            try:
                linked = store.read_linked_history(actor["id"], parent["id"])
            except VariationAuthorityAdapterError as error:
                raise HTTPException(status_code=409, detail="saved source authority is unavailable") from error
            if linked is None:
                raise HTTPException(status_code=409, detail="managed replay requires the source owner's saved authority")
            with _db.SessionLocal() as session:
                acknowledged = session.query(VariationAuthorityActionRow.action_id).filter(
                    VariationAuthorityActionRow.owner_id == actor["id"],
                    VariationAuthorityActionRow.variation_id == linked.variation_id,
                    VariationAuthorityActionRow.revision == linked.revision,
                    VariationAuthorityActionRow.ddl_digest == linked.ddl_digest,
                ).first()
            if acknowledged is None:
                raise HTTPException(status_code=409, detail="saved source authority is unavailable")
            replay_link = (store, linked)
        replay_request = _saved_work_replay_request(parent)
        provisional_seed = parent.get("render_seed") is None
        replayed = _render_authorized_score(replay_request, actor, parent).model_dump(exclude_none=True, by_alias=True)
        if replayed["render_hash"] != body.replay_render_hash or replayed["svg_sha256"] != body.replay_svg_sha256:
            raise HTTPException(status_code=409, detail="replay preview changed; redraw before saving")
        inherited = {key: parent.get(key) for key in (
            "input", "ddl", "ddl_source_origin", "source_text", "interpret_fallback", "compose_fallback",
            "catalog_mode", "stage1_model", "stage2_model", "stage1_prompt_digest",
            "stage1_prompt_base_digest", "stage2_prompt_digest", "instruction_lang_requested",
            "instruction_lang_resolved", "ui_lang", "sketch_text", "sketch_grain", "sketch_state",
            "elapsed_ms", "tokens_in", "tokens_out", "display_label", "batch_line_number", "batch_run_id",
        )}
        inherited.update(input=inherited["input"] or "", history_visibility="normal", count_generation=False)
        body = body.model_copy(update=inherited)
        score, svg, catalog_id = replayed["score"], replayed["svg"], replayed["catalog_id"]
        coerce_observability = None
        render_metadata = {
            **{key: value for key, value in replayed.items() if key not in {"score", "svg", "catalog_id"}},
            **{key: parent.get(key) for key in (
                "stage1_prompt_digest", "stage1_prompt_base_digest", "stage2_prompt_digest",
                "instruction_lang_requested", "instruction_lang_resolved", "ui_lang", "interpretation_seed",
            )},
        }
        replay_record = {}
        if replay_link is None:
            # A linked source gives its records through the link below; a work drawn
            # from its parent without a run gives the ones on its own edge.
            from ...persistence.variation_authority import VariationAuthorityStore

            replay_record = VariationAuthorityStore(_db.engine).read_derived_laws_records(actor["id"], parent["id"])
        body = body.model_copy(update={"derivation_metadata": {
            "replay_work_id": parent["id"], "replay_render_hash": replayed["render_hash"],
            "replay_svg_sha256": replayed["svg_sha256"],
            "provisional_render_seed": provisional_seed, **replay_record,
        }})
        if replay_link is not None:
            diagnostics = dict(linked.pipeline_diagnostics or {
                "upstream_diagnostics": [], "downstream_diagnostics": [],
                "resource_omissions": [], "relation_omissions": [],
            })
            diagnostics.update(render_diagnostics=replayed.get("render_diagnostics"),
                               resource_execution=replayed.get("resource_execution"))
            diagnostics.pop("render_warnings", None)
            if replayed.get("render_warnings"):
                diagnostics["render_warnings"] = replayed["render_warnings"]
    elif body.derivation_kind in ("color_arrangement_change", "ground_change", "tool_change", "canvas_fit"):
        from .render import (
            _render_canvas_fit_for_work, _render_color_arrangement_for_work, _render_ground_variant_for_work,
            _render_tool_variant_for_work,
        )
        from ..rendering import _work_for_color_snapshot

        if body.derivation_kind == "color_arrangement_change":
            index = body.derivation_metadata.get("color_arrangement_index")
            if type(index) is not int or index < 0 or not body.lineage_parent_node_id:
                raise HTTPException(status_code=422, detail="color arrangement requires a parent and valid index")
        elif body.derivation_kind == "canvas_fit":
            paper = body.derivation_metadata.get("to_canvas_aspect")
            if not isinstance(paper, str) or not body.lineage_parent_node_id:
                raise HTTPException(status_code=422, detail="canvas fit requires a parent and a paper")
        elif body.derivation_kind == "ground_change":
            material = body.derivation_metadata.get("ground_material")
            if not isinstance(material, str) or not body.lineage_parent_node_id:
                raise HTTPException(status_code=422, detail="ground change requires a parent and a ground material")
        else:
            tool_mode = body.derivation_metadata.get("tool_mode")
            tools = body.derivation_metadata.get("tools")
            if (tool_mode not in ("uniform", "per_sentence") or not isinstance(tools, dict)
                    or not all(isinstance(key, str) and isinstance(value, str) for key, value in tools.items())
                    or not body.lineage_parent_node_id):
                raise HTTPException(status_code=422, detail="touch change requires a parent, a mode and the tools")
        with _db.SessionLocal() as session:
            node = session.get(LineageNodeRow, body.lineage_parent_node_id)
            parent_id = node.history_id if node else None
        if not parent_id:
            raise HTTPException(status_code=404, detail="unknown work")
        parent = _work_for_color_snapshot(actor, parent_id)
        from ...persistence.variation_authority import VariationAuthorityStore
        from ...pipeline_api import laws_records_of

        # The child is drawn without a run, so nothing links it: it keeps the
        # parent's laws records on its edge, which "change the layout" and the
        # laws move read (2026-10-20).
        laws_records = laws_records_of(VariationAuthorityStore(_db.engine), actor["id"], parent_id)
        if body.derivation_kind == "color_arrangement_change":
            replayed = _render_color_arrangement_for_work(actor, parent, index, laws_records).model_dump(exclude_none=True, by_alias=True)
        elif body.derivation_kind == "canvas_fit":
            replayed = _render_canvas_fit_for_work(actor, parent, paper, laws_records).model_dump(exclude_none=True, by_alias=True)
        elif body.derivation_kind == "ground_change":
            replayed = _render_ground_variant_for_work(actor, parent, material, laws_records).model_dump(exclude_none=True, by_alias=True)
        else:
            replayed = _render_tool_variant_for_work(actor, parent, tool_mode, tools, laws_records).model_dump(exclude_none=True, by_alias=True)
        # Only the parent and the server-derived index decide this child. Sent
        # Score, map, seeds and limits cannot rewrite the work being recolored.
        inherited = {key: parent.get(key) for key in (
            "input", "ddl", "ddl_source_origin", "source_text", "interpret_fallback", "compose_fallback",
            "catalog_mode", "stage1_model", "stage2_model", "stage1_prompt_digest",
            "stage1_prompt_base_digest", "stage2_prompt_digest", "instruction_lang_requested",
            "instruction_lang_resolved", "sketch_text", "sketch_grain", "sketch_state",
        )}
        inherited["input"] = inherited["input"] or ""
        if body.derivation_kind in ("ground_change", "tool_change"):
            # The child's instructions name the ground or the tools it is drawn with.
            inherited["ddl"] = replayed["ddl"]
        # The record is the shared core's, rebuilt from the parent (2026-10-17).
        inherited["derivation_metadata"] = replayed["derivation_metadata"]
        body = body.model_copy(update=inherited)
        score = replayed["score"]
        svg = replayed["svg"]
        catalog_id = replayed["catalog_id"]
        coerce_observability = None
        render_metadata = {
            **{key: value for key, value in replayed.items() if key not in {"score", "svg", "catalog_id", "derivation_metadata", "ddl"}},
            **{key: body.model_dump()[key] for key in (
                "stage1_prompt_digest", "stage1_prompt_base_digest", "stage2_prompt_digest",
                "instruction_lang_requested", "instruction_lang_resolved", "ui_lang",
            )},
        }
    elif isinstance(body.score, dict) and body.score.get("version") in _COMPACT_SCORE_VERSIONS:
        # A compact Score (0.10 and later, every work the app makes now) is
        # drawn only through the shared replay with its resource policy, as
        # /api/render-score and a saved work's SVG are. The plain render below
        # refuses it with InvalidCompactPerformance, so saving a refinement
        # option of such a work answered 422. It is kept as sent: it is what a
        # later redraw replays, and there is nothing to coerce.
        from ... import pipeline_runtime

        catalog_id = _resolved_catalog_id(body.catalog_id)
        replayed = pipeline_runtime.get_service().replay_for(actor["id"], {
            "score": body.score,
            "catalog_id": catalog_id,
            "canvas_aspect": _validated_canvas_aspect_override(body.canvas_aspect),
            "render_seed": render_seed,
            "composition_seed": body.composition_seed,
            "wild": bool(body.render_wild),
        }, None)
        score = body.score
        svg = replayed["svg"]
        coerce_observability = None
        render_metadata = {
            **{key: value for key, value in replayed.items() if key not in {"score", "svg", "catalog_id"}},
            "stage1_prompt_digest": body.stage1_prompt_digest,
            "stage1_prompt_base_digest": body.stage1_prompt_base_digest,
            "stage2_prompt_digest": body.stage2_prompt_digest,
            "instruction_lang_requested": body.instruction_lang_requested,
            "instruction_lang_resolved": body.instruction_lang_resolved,
            "ui_lang": body.ui_lang,
        }
    else:
        # A Score that does not validate is the sender's to fix: say where, the way a
        # malformed body is answered. It used to fall into the handler below, which
        # answered "history score render failed" and logged a traceback as if the
        # server had broken.
        try:
            # Site 2 of 5.
            limits = _effective_limits()
            pre_coerce_score = Score.model_validate(body.score)
            coerce_observability = _capture_history_coerce_observability(
                pre_coerce_score,
                lang=body.instruction_lang_resolved,
            )
            score = coerce_saved_score(
                pre_coerce_score,
                limits=limits,
                lang=body.instruction_lang_resolved,
                trace=coerce_observability,
            )
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=_invalid_score_detail(e)) from e
        try:
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
                # What actually governed this work. Without it a per-install setting
                # would make the same description a different work with nothing on
                # the row to say why.
                "render_limits": limits_as_dict(limits),
            }
            svg, render_metadata = _render_with_metadata(score, render_metadata, owner=actor["id"])
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _unexpected_http_error("history score render", 422) from e
    item_dict = _add_history_item(
        actor=actor,
        input_text=body.input,
        ddl=body.ddl,
        ddl_source_origin=body.ddl_source_origin,
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
        image_provenance=body.image_provenance,
        image_ddl=body.image_ddl,
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
        coerce_observability=coerce_observability.persistable() if coerce_observability else None,
    )
    if replay_link is not None:
        store, linked = replay_link
        # Reuse the source's exact immutable authoring revision. Only this
        # performance's renderer diagnostics are replaced by the fresh render.
        store.link_history(actor["id"], item_dict["id"], linked.variation_id, linked.revision,
            linked.ddl_digest, snapshot={
                "variation_id": linked.variation_id, "authority": {"revision": linked.revision},
                "document": {"source": body.ddl}, "delivery": {"source_digest": linked.ddl_digest},
                "config": linked.saved_config, "completion_ranges": linked.completion_ranges,
                # The same instructions, so the source's laws records hold (2026-10-20).
                "laws_layers": linked.laws_layers, "laws_basis": linked.laws_basis,
            }, context={"host_options": linked.host_options, "macro_catalog": linked.macro_catalog},
            pipeline_diagnostics=diagnostics)
        item_dict = _db.get_items(actor["id"], [item_dict["id"]])[0]
    if body.count_generation and not item_dict.get("_idempotent_replay"):
        if _db.increment_user_generation_count(actor["id"]) is None:
            raise HTTPException(status_code=404, detail="user not found")
    return HistoryItem(**item_dict)


@router.delete("/api/history", summary="Permanently delete all trashed works")
def api_history_delete(
    x_inku_confirm: str | None = Header(
        default=None,
        alias="X-Inku-Confirm",
        description="Must be permanent-delete-trash to confirm emptying the trash. Any other value, or none, is refused with 409.",
    ),
    actor: dict = Depends(_current_user),
) -> dict[str, int | bool]:
    """Permanently delete every work in the caller's trash.

    Returns the number of works deleted. Returns 409 when the X-Inku-Confirm
    header does not carry the confirmation value.
    """
    if x_inku_confirm != "permanent-delete-trash":
        raise HTTPException(
            status_code=409,
            detail="X-Inku-Confirm: permanent-delete-trash is required",
        )
    count = _db.delete_all_trashed_items(actor["id"])
    return {"ok": True, "count": count}


@router.post("/api/history/trash", summary="Move works to the trash")
def api_history_trash(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    """Move the works named in the body to the trash. Only works the caller may change are moved; others are skipped.

    Returns {"ok": true, "count": n}, where n is the number of works moved.
    """
    count = _db.trash_items(actor["id"], body.ids)
    return {"ok": True, "count": count}


@router.post("/api/history/restore", summary="Restore works from the trash")
def api_history_restore(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    """Move the trashed works named in the body back to history. Only works the caller may change are moved; others are skipped.

    Returns {"ok": true, "count": n}, where n is the number of works restored.
    """
    count = _db.restore_items(actor["id"], body.ids)
    return {"ok": True, "count": count}


@router.patch(
    "/api/history/{item_id}/star",
    response_model=HistoryItem,
    response_model_exclude_none=True,
    summary="Set the star and note of a work",
)
def api_history_star(
    item_id: Annotated[str, Path(description="Id of the work.")],
    body: HistoryStarBody,
    actor: dict = Depends(_current_user),
) -> HistoryItem:
    """Set or clear the star of one work and set its note.

    Returns the updated work. Returns 404 when the work is not found or the
    caller may not write it.
    """
    item = _db.set_item_starred(actor["id"], item_id, body.starred, body.note)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    return HistoryItem(**item)


@router.patch(
    "/api/history/{item_id}/for-revision",
    response_model=HistoryItem,
    response_model_exclude_none=True,
    summary="Set the for-revision mark of a work",
)
def api_history_for_revision(
    item_id: Annotated[str, Path(description="Id of the work.")], body: HistoryForRevisionBody, actor: dict = Depends(_current_user)
) -> HistoryItem:
    """Mark or unmark one work for revision.

    Returns the updated work. Returns 404 when the work is not found for the caller.
    """
    item = _db.set_item_for_revision(actor["id"], item_id, body.for_revision)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    return HistoryItem(**item)


@router.patch(
    "/api/history/{item_id}/for-share",
    response_model=HistoryItem,
    response_model_exclude_none=True,
    summary="Set the share state of a work",
)
def api_history_for_share(
    item_id: Annotated[str, Path(description="Id of the work.")], body: HistoryForShareBody, actor: dict = Depends(_current_user)
) -> HistoryItem:
    """Open one work to a user group, or close it again.

    Returns the updated work. Returns 404 when the work is not found or the
    caller may not change it, and 403 when the caller names a user group other
    than their own without administrator rights.
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


@router.get("/api/history/{item_id}/acl", response_model=list[HistoryAclEntryOut], summary="List the guests of a work")
def api_history_acl_get(item_id: Annotated[str, Path(description="Id of the work.")], actor: dict = Depends(_current_user)) -> list[HistoryAclEntryOut]:
    """List the guest entries on one work.

    Returns 404 when the work is not found for the caller, which includes a
    work the caller may not see.
    """
    entries = _db.list_history_acl(actor["id"], item_id)
    if entries is None:
        # 404 rather than 403 throughout: telling a caller who may not see a work
        # that it exists is itself a disclosure.
        raise HTTPException(status_code=404, detail="history item not found")
    return [HistoryAclEntryOut(**entry) for entry in entries]


@router.put("/api/history/{item_id}/acl", response_model=list[HistoryAclEntryOut], summary="Replace the guest list of a work")
def api_history_acl_put(
    item_id: Annotated[str, Path(description="Id of the work.")], body: HistoryAclBody, actor: dict = Depends(_current_user)
) -> list[HistoryAclEntryOut]:
    """Replace the whole guest list of one work with the entries sent.

    A subject left out of the list loses its access. Returns the new list.
    Returns 404 when the work is not found for the caller and 400 when an entry
    is invalid.
    """
    try:
        entries = _db.replace_history_acl(actor["id"], item_id, [e.model_dump() for e in body.entries])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if entries is None:
        raise HTTPException(status_code=404, detail="history item not found")
    return [HistoryAclEntryOut(**entry) for entry in entries]


# The files are written inside the request, each work's PNG rasterized there
# too, so a request holds a worker for as long as its works take. The 1,000 the
# other bulk actions share made that minutes for anyone who asked; a client
# with more works asks again.
_REBUILD_OUTPUT_FILES_MAX = 50


@router.post("/api/history/rebuild-output-files", summary="Rebuild output files for works")
def api_history_rebuild_output_files(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    """Write the output files again for the works named in the body.

    Accepts at most 50 ids per request. Returns {"ok": true, "count": n}, where n
    is the number of works found. Returns 409 when output file saving is switched
    off and 422 when more than 50 ids are sent.
    """
    # Saving files is the administrator's switch; this route used to write them
    # with the switch off.
    if not _output_save_settings()["enabled"]:
        raise HTTPException(status_code=409, detail="output file saving is disabled")
    if len(body.ids) > _REBUILD_OUTPUT_FILES_MAX:
        raise HTTPException(status_code=422, detail=f"at most {_REBUILD_OUTPUT_FILES_MAX} works per request")
    items = _db.get_items(actor["id"], body.ids)
    for item in items:
        _save_history_artifacts(item)
    return {"ok": True, "count": len(items)}


@router.post("/api/history/permanent-delete", summary="Permanently delete trashed works")
def api_history_permanent_delete(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    """Permanently delete the works named in the body, which must already be in the trash.

    Returns {"ok": true, "count": n}, where n is the number of works deleted.
    """
    count = _db.delete_items(actor["id"], body.ids, require_trashed=True)
    return {"ok": True, "count": count}
