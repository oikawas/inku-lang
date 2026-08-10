"""Endpoints for the users group, moved out of api.py unchanged."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from ... import db as _db
from ..common import _unexpected_http_error
from ..deps import _user_manager
from ..models import UserAccountItem


router = APIRouter(dependencies=[Depends(_user_manager)])


class UserGroupItem(BaseModel):
    id: str
    name: str
    at: int


class UserGroupCreateBody(BaseModel):
    name: str = Field(..., min_length=1, description="ユーザーグループ名")


class UserGroupUpdateBody(BaseModel):
    name: str = Field(..., min_length=1, description="ユーザーグループ名")


class UserAccountCreateBody(BaseModel):
    username: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)
    permission_groups: list[str] = Field(default_factory=lambda: ["users"])
    group_id: str | None = None


class UserAccountUpdateBody(BaseModel):
    username: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=8)
    permission_groups: list[str] | None = None
    group_id: str | None = None


@router.get("/api/user-groups", response_model=list[UserGroupItem])
def api_user_groups_list(actor: dict = Depends(_user_manager)) -> list[UserGroupItem]:
    groups = _db.list_user_groups()
    if not _db.has_permission_group(actor, "admins"):
        groups = [group for group in groups if group["id"] == actor.get("group_id")]
    return [UserGroupItem(**group) for group in groups]


@router.post("/api/user-groups", response_model=UserGroupItem)
def api_user_groups_create(body: UserGroupCreateBody, actor: dict = Depends(_user_manager)) -> UserGroupItem:
    if not _db.has_permission_group(actor, "admins"):
        raise HTTPException(status_code=403, detail="only administrators can create groups")
    try:
        return UserGroupItem(**_db.add_user_group(body.name))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("group create", 409) from e


@router.patch("/api/user-groups/{group_id}", response_model=UserGroupItem)
def api_user_groups_update(
    group_id: str,
    body: UserGroupUpdateBody,
    actor: dict = Depends(_user_manager),
) -> UserGroupItem:
    if not _db.has_permission_group(actor, "admins"):
        raise HTTPException(status_code=403, detail="only administrators can update groups")
    try:
        group = _db.update_user_group(group_id, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("group update", 409) from e
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    return UserGroupItem(**group)


@router.delete("/api/user-groups/{group_id}")
def api_user_groups_delete(group_id: str, actor: dict = Depends(_user_manager)) -> dict[str, bool]:
    if not _db.has_permission_group(actor, "admins"):
        raise HTTPException(status_code=403, detail="only administrators can delete groups")
    try:
        found = _db.delete_user_group(group_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail="group not found")
    return {"ok": True}


@router.get("/api/users", response_model=list[UserAccountItem])
def api_users_list(actor: dict = Depends(_user_manager)) -> list[UserAccountItem]:
    return [UserAccountItem(**user) for user in _db.list_users_for_actor(actor)]


@router.post("/api/users", response_model=UserAccountItem)
def api_users_create(body: UserAccountCreateBody, actor: dict = Depends(_user_manager)) -> UserAccountItem:
    if not _db.has_permission_group(actor, "admins"):
        if set(body.permission_groups) != {"users"} or body.group_id != actor.get("group_id"):
            raise HTTPException(status_code=403, detail="leaders can create members only in their own group")
    try:
        user = _db.add_user(
            username=body.username,
            email=body.email,
            password=body.password,
            permission_groups=body.permission_groups,
            group_id=body.group_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("user create", 409) from e
    return UserAccountItem(**user)


@router.patch("/api/users/{user_id}", response_model=UserAccountItem)
def api_users_update(
    user_id: str,
    body: UserAccountUpdateBody,
    actor: dict = Depends(_user_manager),
) -> UserAccountItem:
    if not _db.has_permission_group(actor, "admins"):
        if body.permission_groups is not None and set(body.permission_groups) != {"users"}:
            raise HTTPException(status_code=403, detail="leaders cannot change permission groups")
        if body.group_id is not None and body.group_id != actor.get("group_id"):
            raise HTTPException(status_code=403, detail="leaders cannot move members outside their group")
    try:
        user = _db.update_user(user_id, actor=actor, **body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("user update", 409) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@router.delete("/api/users/{user_id}")
def api_users_delete(
    user_id: str,
    cascade: bool = Query(default=False),
    actor: dict = Depends(_user_manager),
) -> dict[str, bool]:
    try:
        found = _db.delete_user(user_id, cascade=cascade, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True}
