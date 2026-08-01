"""Endpoints for the feedback group, moved out of api.py unchanged."""

from __future__ import annotations

import time
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from ... import db as _db
from ..deps import _current_user


router = APIRouter(dependencies=[Depends(_current_user)])


class UnreadWordsBody(BaseModel):
    words: list[str] = Field(default_factory=list, max_length=100)
    context: str = Field(default="", max_length=1000)


@router.post("/api/feedback/unread-words")
def api_record_unread_words(body: UnreadWordsBody, actor: dict = Depends(_current_user)) -> dict:
    _db.record_unread_words(actor["id"], body.words, body.context, at=int(time.time() * 1000))
    return {"ok": True}


@router.get("/api/feedback/unread-words")
def api_my_unread_words(limit: int = Query(default=100, ge=1, le=500), actor: dict = Depends(_current_user)) -> list[dict]:
    return _db.list_unread_words(actor["id"], limit=limit)


@router.get("/api/admin/unread-words")
def api_admin_unread_words(limit: int = Query(default=500, ge=1, le=2000), actor: dict = Depends(_current_user)) -> list[dict]:
    if actor.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return _db.list_unread_words(None, limit=limit)
