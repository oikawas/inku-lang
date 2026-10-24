"""Endpoints for the feedback group, moved out of api.py unchanged."""

from __future__ import annotations

import time
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from ... import db as _db
from ..deps import _current_user


router = APIRouter(dependencies=[Depends(_current_user)])


class UnreadWordsBody(BaseModel):
    words: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="Words the user did not understand, up to 100. Each is trimmed, cut to 120 characters and de-duplicated; blank entries are dropped.",
    )
    context: str = Field(
        default="",
        max_length=1000,
        description="Text showing where the words were met, up to 1000 characters. Trimmed before it is stored; empty when omitted.",
    )


@router.post("/api/feedback/unread-words", summary="Record unread words")
def api_record_unread_words(body: UnreadWordsBody, actor: dict = Depends(_current_user)) -> dict:
    """Record the words the signed-in user did not understand, with their context.

    Nothing is stored when no word is left after trimming. Returns {"ok": true}.
    """
    _db.record_unread_words(actor["id"], body.words, body.context, at=int(time.time() * 1000))
    return {"ok": True}


@router.get("/api/feedback/unread-words", summary="List my unread words")
def api_my_unread_words(
    limit: int = Query(default=100, ge=1, le=500, description="Maximum number of entries to return, from 1 to 500."),
    actor: dict = Depends(_current_user),
) -> list[dict]:
    """List the unread words recorded for the signed-in user."""
    return _db.list_unread_words(actor["id"], limit=limit)


@router.get("/api/admin/unread-words", summary="List unread words of all users")
def api_admin_unread_words(
    limit: int = Query(default=500, ge=1, le=2000, description="Maximum number of entries to return, from 1 to 2000."),
    actor: dict = Depends(_current_user),
) -> list[dict]:
    """List the unread words recorded across all users. Only administrators may call it.

    Returns 403 when the caller is not in the admins permission group.
    """
    if not _db.has_permission_group(actor, "admins"):
        raise HTTPException(status_code=403, detail="admins permission group required")
    return _db.list_unread_words(None, limit=limit)
