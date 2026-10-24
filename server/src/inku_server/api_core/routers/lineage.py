"""Endpoints for the lineage group, moved out of api.py unchanged."""

from __future__ import annotations

import time
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pydantic import BaseModel, Field
from ...okugaki import generate_okugaki
from ... import db as _db
from ..common import _resolved_vision_model, _unexpected_http_error
from ..vision import chatgpt_vision_error, prepare_vision_settings
from ...chatgpt_store import ChatGPTError
from ..deps import _current_user
from ..models import HistoryItem, HistoryListResponse, json_seeds


router = APIRouter(dependencies=[Depends(_current_user)])


class HistoryLineageGroup(BaseModel):
    root_node_id: str = Field(description="Id of the root lineage node that the group is built around.")
    representative: HistoryItem = Field(description="The work shown for the group, as a history item.")
    item_count: int = Field(description="Number of works in the group.")
    starred_count: int = Field(description="Number of starred works in the group.")
    for_revision_count: int = Field(description="Number of works in the group marked for revision.")
    latest_at: int = Field(
        description="Save time of the newest work in the group, in milliseconds since the Unix epoch."
    )


class HistoryLineageGroupListResponse(BaseModel):
    groups: list[HistoryLineageGroup] = Field(description="The groups on this page.")
    total: int = Field(description="Number of groups that match the filters, across all pages.")
    offset: int = Field(description="Offset used for this page.")
    limit: int = Field(description="Maximum number of groups per page that was used.")


class OkugakiGenerateBody(BaseModel):
    model: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Vision model that reads the branch. Omit to use the caller's resolved default vision model.",
    )
    language: str = Field(
        default="ja", pattern="^(ja|en)$", description="Language of the entry: ja or en."
    )
    save: bool = Field(
        default=True,
        description="When true, the entry is stored and can be listed later. When false, it is generated and returned without being stored.",
    )


class OkugakiItem(BaseModel):
    id: str | None = Field(
        default=None, description="Id of the stored entry. None when the entry was not saved."
    )
    target_node_id: str = Field(description="Id of the lineage node the entry describes.")
    branch_snapshot: list[str] = Field(
        description="Ids of the lineage nodes on the branch, from the root to the target, as they were read."
    )
    model: str = Field(description="Vision model that wrote the entry.")
    at: int = Field(description="Time the entry was generated, in milliseconds since the Unix epoch.")
    language: str = Field(description="Language of the body: ja or en.")
    body: str = Field(description="Text of the entry.")
    warnings: list[str] = Field(
        default_factory=list, description="Warnings raised while generating the entry. Empty when there are none."
    )
    fact_sheet: dict = Field(
        default_factory=dict, description="Facts about the branch that the entry was written from, as a JSON object."
    )


@router.get(
    "/api/history/lineage-groups",
    response_model=HistoryLineageGroupListResponse,
    response_model_exclude_none=True,
    summary="List lineage groups of works",
)
def api_history_lineage_groups(
    offset: int = Query(default=0, ge=0, description="Number of groups to skip before the first one returned."),
    limit: int = Query(default=12, ge=1, le=100, description="Maximum number of groups to return, from 1 to 100."),
    trashed: bool = Query(default=False, description="When true, group the works in the trash instead of the live works."),
    starred: bool = Query(default=False, description="When true, count only starred works in each group."),
    for_revision: bool = Query(default=False, description="When true, count only works marked for revision in each group."),
    for_share: bool = Query(default=False, description="When true, count only works opened to a user group in each group."),
    q: str = Query(default="", max_length=200, description="Text to search the works for, up to 200 characters. Empty applies no text filter."),
    min_items: int = Query(default=1, ge=1, le=1000, description="Smallest number of works a group must hold to be listed, from 1 to 1000. A group that holds the anchor_id or include_id work is listed in any case."),
    anchor_id: str | None = Query(
        default=None,
        max_length=100,
        description="Id of a work to bring into view. When its group is found, offset moves to that group's position.",
    ),
    include_id: str | None = Query(
        default=None,
        max_length=100,
        description="Id of a work whose group is listed even when it has fewer works than min_items. Has an effect only when min_items is above 1. Ignored when anchor_id is sent.",
    ),
    include_svg: bool = Query(
        default=True,
        description="Send each representative work's whole SVG. Clients that draw from thumbnails send false.",
    ),
    actor: dict = Depends(_current_user),
) -> HistoryLineageGroupListResponse:
    """Return one page of lineage groups among the works the caller may read.

    Each group is built around a root node and carries its representative work
    and the counts of its works, starred works and works marked for revision.
    Returns the page with the total number of groups.
    """
    if anchor_id:
        position = _db.lineage_group_position(
            actor["id"], anchor_id, trashed=trashed, query_text=q, starred=starred,
            for_revision=for_revision, for_share=for_share, min_item_count=min_items,
        )
        if position is not None:
            offset = position
    # Emptied, not removed, as the listing does: svg_bytes says how large it is.
    groups, total = _db.list_lineage_groups(
        actor["id"], offset=offset, limit=limit, trashed=trashed, query_text=q, starred=starred,
        for_revision=for_revision, for_share=for_share, min_item_count=min_items, include_svg=include_svg,
        **({"include_item_id": anchor_id or include_id} if include_id or anchor_id else {}),
    )
    return HistoryLineageGroupListResponse(groups=groups, total=total, offset=offset, limit=limit)


@router.get(
    "/api/history/lineage-groups/{root_node_id}/items",
    response_model=HistoryListResponse,
    response_model_exclude_none=True,
    summary="List the works of a lineage group",
)
def api_history_lineage_group_items(
    root_node_id: Annotated[str, Path(description="Id of the root node of the lineage group.")],
    offset: int = Query(default=0, ge=0, description="Number of works to skip before the first one returned."),
    limit: int = Query(default=100, ge=1, le=10_000, description="Maximum number of works to return, from 1 to 10,000."),
    trashed: bool = Query(default=False, description="When true, list works in the trash instead of the live works."),
    starred: bool = Query(default=False, description="When true, list only starred works."),
    for_revision: bool = Query(default=False, description="When true, list only works marked for revision."),
    for_share: bool = Query(default=False, description="When true, list only works opened to a user group."),
    q: str = Query(default="", max_length=200, description="Text to search the works for, up to 200 characters. Empty applies no text filter."),
    include_svg: bool = Query(
        default=True,
        description="Send each work's whole SVG. Clients that draw from thumbnails send false.",
    ),
    actor: dict = Depends(_current_user),
) -> HistoryListResponse:
    """Return one page of the works in one lineage group.

    Returns 404 when the group has no matching works and its root node is not
    found for the caller.
    """
    # Emptied, not removed, as the listing does when asked the same: the key
    # keeps its place and its type, and svg_bytes says how large the work is.
    items, total = _db.list_lineage_group_items(
        actor["id"], root_node_id, offset=offset, limit=limit, trashed=trashed, query_text=q,
        starred=starred, for_revision=for_revision, for_share=for_share, include_svg=include_svg,
    )
    if total == 0:
        root = _db.get_lineage(actor["id"], root_node_id, descendant_depth=0, node_limit=1)
        if root is None:
            raise HTTPException(status_code=404, detail="lineage not found")
    return HistoryListResponse(items=items, total=total, offset=offset, limit=limit)


def _with_json_seeds(lineage: dict) -> dict:
    # These answers leave without a model, so their works' seeds are made
    # strings here, as HistoryItem sends them. Each work also says whether its
    # DDL holds it, as a history item does.
    locked = _db.description_locked_history_ids(
        [node["history"]["id"] for node in lineage.get("nodes", []) if node.get("history")]
    )
    return {**lineage, "nodes": [
        {**node, "history": {**json_seeds(node["history"]), "description_locked": node["history"]["id"] in locked}}
        if node.get("history") else node
        for node in lineage.get("nodes", [])
    ]}


@router.get("/api/history/{item_id}/lineage", summary="Get the lineage of a work")
def api_history_lineage(
    item_id: Annotated[str, Path(description="Id of the work.")],
    descendant_depth: int = Query(default=2, ge=0, le=200, description="Number of generations of descendants to include, from 0 to 200."),
    node_limit: int = Query(default=200, ge=1, le=200, description="Largest number of lineage edges to return, from 1 to 200, counted outward from the work's node."),
    actor: dict = Depends(_current_user),
) -> dict:
    """Return the lineage graph of one work, starting from its lineage node.

    The result lists the nodes and their edges, and marks each work that has a
    description lock. Returns 404 when the work is not found, has no lineage
    node, or its lineage cannot be read.
    """
    items = _db.get_items(actor["id"], [item_id])
    if not items or not items[0].get("lineage_node_id"):
        raise HTTPException(status_code=404, detail="history item not found")
    lineage = _db.get_lineage(
        actor["id"],
        items[0]["lineage_node_id"],
        descendant_depth=descendant_depth,
        node_limit=node_limit,
    )
    if lineage is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    return _with_json_seeds(lineage)


@router.get("/api/lineage/{node_id}", summary="Get the lineage of a node")
def api_lineage(
    node_id: Annotated[str, Path(description="Id of the lineage node.")],
    descendant_depth: int = Query(default=2, ge=0, le=200, description="Number of generations of descendants to include, from 0 to 200."),
    node_limit: int = Query(default=200, ge=1, le=200, description="Largest number of lineage edges to return, from 1 to 200, counted outward from the work's node."),
    include_svg: bool = Query(
        default=True,
        description="Send each work's whole SVG. Clients that draw from thumbnails send false.",
    ),
    actor: dict = Depends(_current_user),
) -> dict:
    """Return the lineage graph starting from one lineage node.

    The result lists the nodes and their edges, and marks each work that has a
    description lock. Returns 404 when the lineage is not found for the caller.
    """
    # Emptied, not removed, as the listing does: svg_bytes says how large it is.
    lineage = _db.get_lineage(
        actor["id"], node_id, descendant_depth=descendant_depth, node_limit=node_limit, include_svg=include_svg
    )
    if lineage is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    return _with_json_seeds(lineage)


@router.post("/api/lineage/{node_id}/promote", response_model=HistoryItem, response_model_exclude_none=True, summary="Promote a lineage node to a work")
def api_lineage_promote(
    node_id: Annotated[str, Path(description="Id of the lineage node to promote.")],
    actor: dict = Depends(_current_user),
) -> HistoryItem:
    """Turn a lineage-only node into a saved work in the caller's history.

    Returns the work, now visible in the caller's history. Returns 404 when the node is not found, is not
    writable by the caller, or is not lineage-only.
    """
    item = _db.promote_lineage_node(actor["id"], node_id)
    if item is None:
        raise HTTPException(status_code=404, detail="lineage item not found")
    return HistoryItem(**item)


@router.get("/api/lineage/{node_id}/colophon", response_model=list[OkugakiItem], response_model_exclude_none=True, summary="List the colophon entries of a lineage")
def api_okugaki_list(
    node_id: Annotated[str, Path(description="Id of the lineage node at the end of the branch.")],
    actor: dict = Depends(_current_user),
) -> list[OkugakiItem]:
    """List the saved colophon entries for the branch that ends at one lineage node.

    Returns 404 when the lineage is not found for the caller.
    """
    branch = _db.get_lineage_branch(actor["id"], node_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    return [OkugakiItem(**item) for item in _db.list_okugaki(actor["id"], node_id)]


@router.post("/api/lineage/{node_id}/colophon", response_model=OkugakiItem, response_model_exclude_none=True, summary="Generate a colophon entry for a lineage")
def api_okugaki_generate(
    node_id: Annotated[str, Path(description="Id of the lineage node at the end of the branch.")],
    body: OkugakiGenerateBody,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=200,
        description="Key that makes a repeated request return the entry saved earlier instead of generating another. Used only when save is true.",
    ),
    actor: dict = Depends(_current_user),
) -> OkugakiItem:
    """Read the branch that ends at one lineage node with a vision model and write a colophon entry for it.

    Each generation is read on its own, so an earlier reading never contains
    information from a later one. When save is true the entry is stored and
    returned. Returns 404 when the lineage is not found, 422 when the input is
    rejected, 504 when the model times out, 403 or 503 when the vision provider
    refuses or cannot be reached, and 502 for other unexpected failures.
    """
    if body.save and idempotency_key:
        existing = _db.get_okugaki_by_idempotency(actor["id"], idempotency_key)
        if existing is not None:
            return OkugakiItem(**existing)
    branch = _db.get_lineage_branch(actor["id"], node_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    at = int(time.time() * 1000)
    model = _resolved_vision_model(body.model, actor)
    settings = prepare_vision_settings(actor, model, _db.get_model_settings())
    try:
        item = generate_okugaki(
            branch,
            model=model,
            language=body.language,
            settings=settings,
            at=at,
        )
        if body.save:
            item = _db.add_okugaki(actor["id"], item, idempotency_key=idempotency_key)
    except ChatGPTError as exc:
        raise chatgpt_vision_error(exc) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError as exc:
        detail = (
            "Visionモデルがタイムアウトしました。完了済みの世代所見は一時保存されています。再度追記してください。"
            if body.language == "ja"
            else "The Vision model timed out. Completed generation readings are cached temporarily; retry the append."
        )
        raise HTTPException(status_code=504, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        raise _unexpected_http_error("okugaki generation", 502) from exc
    return OkugakiItem(**item)


@router.delete("/api/colophon/{colophon_id}", summary="Delete a colophon entry")
def api_okugaki_delete(
    colophon_id: Annotated[str, Path(description="Id of the colophon entry to delete.")],
    actor: dict = Depends(_current_user),
) -> dict[str, bool]:
    """Delete one colophon entry. Its owner and administrators may delete it. Returns 404 when the entry is not found or the caller may not change it.

    Returns {"ok": true}. Returns 404 when the entry is not found for the caller.
    """
    if not _db.delete_okugaki(actor["id"], colophon_id):
        raise HTTPException(status_code=404, detail="colophon not found")
    return {"ok": True}
