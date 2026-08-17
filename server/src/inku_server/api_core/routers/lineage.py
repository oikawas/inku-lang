"""Endpoints for the lineage group, moved out of api.py unchanged."""

from __future__ import annotations

import time
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from ...okugaki import generate_okugaki
from ... import db as _db
from ..common import _resolved_vision_model, _unexpected_http_error
from ..deps import _current_user
from ..models import HistoryItem, HistoryListResponse


router = APIRouter(dependencies=[Depends(_current_user)])


class HistoryLineageGroup(BaseModel):
    root_node_id: str
    representative: HistoryItem
    item_count: int
    starred_count: int
    for_revision_count: int
    latest_at: int


class HistoryLineageGroupListResponse(BaseModel):
    groups: list[HistoryLineageGroup]
    total: int
    offset: int
    limit: int


class OkugakiGenerateBody(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=200)
    language: str = Field(default="ja", pattern="^(ja|en)$")
    save: bool = True


class OkugakiItem(BaseModel):
    id: str | None = None
    target_node_id: str
    branch_snapshot: list[str]
    model: str
    at: int
    language: str
    body: str
    warnings: list[str] = Field(default_factory=list)
    fact_sheet: dict = Field(default_factory=dict)


@router.get("/api/history/lineage-groups", response_model=HistoryLineageGroupListResponse, response_model_exclude_none=True)
def api_history_lineage_groups(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=100),
    trashed: bool = Query(default=False),
    starred: bool = Query(default=False),
    for_revision: bool = Query(default=False),
    for_share: bool = Query(default=False),
    q: str = Query(default="", max_length=200),
    min_items: int = Query(default=1, ge=1, le=1000),
    actor: dict = Depends(_current_user),
) -> HistoryLineageGroupListResponse:
    groups, total = _db.list_lineage_groups(
        actor["id"], offset=offset, limit=limit, trashed=trashed, query_text=q, starred=starred,
        for_revision=for_revision, for_share=for_share, min_item_count=min_items,
    )
    return HistoryLineageGroupListResponse(groups=groups, total=total, offset=offset, limit=limit)


@router.get("/api/history/lineage-groups/{root_node_id}/items", response_model=HistoryListResponse, response_model_exclude_none=True)
def api_history_lineage_group_items(
    root_node_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=10_000),
    trashed: bool = Query(default=False),
    starred: bool = Query(default=False),
    for_revision: bool = Query(default=False),
    for_share: bool = Query(default=False),
    q: str = Query(default="", max_length=200),
    actor: dict = Depends(_current_user),
) -> HistoryListResponse:
    items, total = _db.list_lineage_group_items(
        actor["id"], root_node_id, offset=offset, limit=limit, trashed=trashed, query_text=q,
        starred=starred, for_revision=for_revision, for_share=for_share,
    )
    if total == 0:
        root = _db.get_lineage(actor["id"], root_node_id, descendant_depth=0, node_limit=1)
        if root is None:
            raise HTTPException(status_code=404, detail="lineage not found")
    return HistoryListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/api/history/{item_id}/lineage")
def api_history_lineage(
    item_id: str,
    descendant_depth: int = Query(default=2, ge=0, le=200),
    node_limit: int = Query(default=200, ge=1, le=200),
    actor: dict = Depends(_current_user),
) -> dict:
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
    return lineage


@router.get("/api/lineage/{node_id}")
def api_lineage(
    node_id: str,
    descendant_depth: int = Query(default=2, ge=0, le=200),
    node_limit: int = Query(default=200, ge=1, le=200),
    actor: dict = Depends(_current_user),
) -> dict:
    lineage = _db.get_lineage(actor["id"], node_id, descendant_depth=descendant_depth, node_limit=node_limit)
    if lineage is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    return lineage


@router.post("/api/lineage/{node_id}/promote", response_model=HistoryItem, response_model_exclude_none=True)
def api_lineage_promote(node_id: str, actor: dict = Depends(_current_user)) -> HistoryItem:
    item = _db.promote_lineage_node(actor["id"], node_id)
    if item is None:
        raise HTTPException(status_code=404, detail="lineage item not found")
    return HistoryItem(**item)


@router.get("/api/lineage/{node_id}/colophon", response_model=list[OkugakiItem], response_model_exclude_none=True)
def api_okugaki_list(node_id: str, actor: dict = Depends(_current_user)) -> list[OkugakiItem]:
    branch = _db.get_lineage_branch(actor["id"], node_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    return [OkugakiItem(**item) for item in _db.list_okugaki(actor["id"], node_id)]


@router.post("/api/lineage/{node_id}/colophon", response_model=OkugakiItem, response_model_exclude_none=True)
def api_okugaki_generate(
    node_id: str,
    body: OkugakiGenerateBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> OkugakiItem:
    if body.save and idempotency_key:
        existing = _db.get_okugaki_by_idempotency(actor["id"], idempotency_key)
        if existing is not None:
            return OkugakiItem(**existing)
    branch = _db.get_lineage_branch(actor["id"], node_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    at = int(time.time() * 1000)
    try:
        item = generate_okugaki(
            branch,
            model=_resolved_vision_model(body.model, actor),
            language=body.language,
            settings=_db.get_model_settings(),
            at=at,
        )
        if body.save:
            item = _db.add_okugaki(actor["id"], item, idempotency_key=idempotency_key)
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


@router.delete("/api/colophon/{colophon_id}")
def api_okugaki_delete(colophon_id: str, actor: dict = Depends(_current_user)) -> dict[str, bool]:
    if not _db.delete_okugaki(actor["id"], colophon_id):
        raise HTTPException(status_code=404, detail="colophon not found")
    return {"ok": True}
