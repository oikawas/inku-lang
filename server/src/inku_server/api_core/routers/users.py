"""Endpoints for the users group, moved out of api.py unchanged."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from ... import db as _db
from ...persistence.accounts import LastAdministratorError
from ..common import _unexpected_http_error
from ..deps import _user_manager
from ..models import UserAccountItem


router = APIRouter(dependencies=[Depends(_user_manager)])


class UserGroupItem(BaseModel):
    id: str = Field(description="Id of the user group.")
    name: str = Field(description="Display name of the user group.")
    at: int = Field(description="Creation or last rename time of the user group, in milliseconds since the Unix epoch.")


class UserGroupCreateBody(BaseModel):
    name: str = Field(..., min_length=1, description="ユーザーグループ名")


class UserGroupUpdateBody(BaseModel):
    name: str = Field(..., min_length=1, description="ユーザーグループ名")


class UserAccountCreateBody(BaseModel):
    username: str = Field(..., min_length=1, description="Username of the new account.")
    email: str = Field(..., min_length=1, description="Email address of the new account.")
    password: str = Field(..., min_length=8, description="Initial password, at least 8 characters.")
    permission_groups: list[str] = Field(
        default_factory=lambda: ["users"],
        description="Permission groups of the new account, such as `users`, `leaders` or `admins`. Defaults to `users`.",
    )
    group_id: str | None = Field(
        default=None,
        description="Id of the user group the new account joins. Null or omitted leaves the account without a user group.",
    )


class UserAccountUpdateBody(BaseModel):
    username: str | None = Field(default=None, min_length=1, description="New username. Null or omitted leaves it unchanged.")
    email: str | None = Field(default=None, min_length=1, description="New email address. Null or omitted leaves it unchanged.")
    password: str | None = Field(default=None, min_length=8, description="New password, at least 8 characters. Null or omitted leaves it unchanged.")
    permission_groups: list[str] | None = Field(
        default=None,
        description="Replacement list of permission groups. Null or omitted leaves them unchanged.",
    )
    group_id: str | None = Field(
        default=None,
        description=(
            "Id of the user group to move the account into. Omitting the field leaves it unchanged; "
            "sending null removes the account from its user group. Only an administrator may send "
            "a value other than their own user group, null included."
        ),
    )


@router.get("/api/user-groups", response_model=list[UserGroupItem], summary="List user groups")
def api_user_groups_list(actor: dict = Depends(_user_manager)) -> list[UserGroupItem]:
    """Return the user groups the caller may see.

    Administrators see every user group. Other user managers see only their own user group.
    Requires a user manager.
    """
    groups = _db.list_user_groups()
    if not _db.has_permission_group(actor, "admins"):
        groups = [group for group in groups if group["id"] == actor.get("group_id")]
    return [UserGroupItem(**group) for group in groups]


@router.post("/api/user-groups", response_model=UserGroupItem, summary="Create a user group")
def api_user_groups_create(body: UserGroupCreateBody, actor: dict = Depends(_user_manager)) -> UserGroupItem:
    """Create a user group with the given name. Only administrators may create groups.

    Returns 403 for other user managers, 400 when the name is invalid, and 409 on an unexpected
    failure.
    """
    if not _db.has_permission_group(actor, "admins"):
        raise HTTPException(status_code=403, detail="only administrators can create groups")
    try:
        return UserGroupItem(**_db.add_user_group(body.name))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("group create", 409) from e


@router.patch("/api/user-groups/{group_id}", response_model=UserGroupItem, summary="Rename a user group")
def api_user_groups_update(
    group_id: Annotated[str, Path(description="Id of the user group to rename.")],
    body: UserGroupUpdateBody,
    actor: dict = Depends(_user_manager),
) -> UserGroupItem:
    """Rename a user group. Only administrators may rename groups.

    Returns 403 for other user managers, 400 when the name is invalid, 404 when the group does not
    exist, and 409 on an unexpected failure.
    """
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


@router.delete("/api/user-groups/{group_id}", summary="Delete a user group")
def api_user_groups_delete(
    group_id: Annotated[str, Path(description="Id of the user group to delete.")],
    actor: dict = Depends(_user_manager),
) -> dict[str, bool]:
    """Delete a user group. Only administrators may delete groups.

    Returns `{"ok": true}` on success. Returns 403 for other user managers, 404 when the group does
    not exist, and 409 when the server refuses the deletion.
    """
    if not _db.has_permission_group(actor, "admins"):
        raise HTTPException(status_code=403, detail="only administrators can delete groups")
    try:
        found = _db.delete_user_group(group_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail="group not found")
    return {"ok": True}


@router.get("/api/users", response_model=list[UserAccountItem], summary="List user accounts")
def api_users_list(actor: dict = Depends(_user_manager)) -> list[UserAccountItem]:
    """Return the user accounts the caller may see.

    Administrators see every account. A leader sees only the accounts in their own user group.
    Requires a user manager.
    """
    return [UserAccountItem(**user) for user in _db.list_users_for_actor(actor)]


@router.post("/api/users", response_model=UserAccountItem, summary="Create a user account")
def api_users_create(body: UserAccountCreateBody, actor: dict = Depends(_user_manager)) -> UserAccountItem:
    """Create a user account.

    A leader who is not an administrator may only create members with the `users` permission group
    in their own user group; other requests return 403. Returns 400 when a value is invalid and 409
    on an unexpected failure.
    """
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


@router.patch("/api/users/{user_id}", response_model=UserAccountItem, summary="Update a user account")
def api_users_update(
    user_id: Annotated[str, Path(description="Id of the user account to update.")],
    body: UserAccountUpdateBody,
    actor: dict = Depends(_user_manager),
) -> UserAccountItem:
    """Update a user account. Only the fields sent are changed.

    A leader who is not an administrator cannot give an account any permission group other than
    `users`, nor move it to another user group or out of its group with `group_id: null`; those
    requests return 403. Returns 409 when the
    change would leave the server without an administrator, 400 when a value is invalid, and 404
    when the account does not exist or a leader may not change it.
    """
    if not _db.has_permission_group(actor, "admins"):
        if body.permission_groups is not None and set(body.permission_groups) != {"users"}:
            raise HTTPException(status_code=403, detail="leaders cannot change permission groups")
        # A sent null clears the group, so it is a move like any other value.
        if "group_id" in body.model_fields_set and body.group_id != actor.get("group_id"):
            raise HTTPException(status_code=403, detail="leaders cannot move members outside their group")
    try:
        user = _db.update_user(user_id, actor=actor, **body.model_dump(exclude_unset=True))
    except LastAdministratorError as e:
        # A conflict with the server's state, not a malformed request: the
        # same change succeeds once another account holds `admins`.
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("user update", 409) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@router.delete("/api/users/{user_id}", summary="Delete a user account")
def api_users_delete(
    user_id: Annotated[str, Path(description="Id of the user account to delete.")],
    cascade: bool = Query(
        default=False,
        description=(
            "When true, the account's history and lineage nodes are deleted with it. "
            "When false, deletion is refused with 409 while the account still has history."
        ),
    ),
    actor: dict = Depends(_user_manager),
) -> dict[str, bool]:
    """Delete a user account. Returns `{"ok": true}` on success.

    A leader who is not an administrator may only delete accounts in their own user group. Returns
    409 when the account has history and `cascade` is false, and 404 when the account does not exist
    or the caller may not delete it.
    """
    try:
        found = _db.delete_user(user_id, cascade=cascade, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True}
