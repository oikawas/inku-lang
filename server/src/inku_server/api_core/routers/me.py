"""Endpoints for the me group, moved out of api.py unchanged."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ... import db as _db
from ..common import _unexpected_http_error
from ..deps import _admin_user, _current_user
from ..models import UserAccountItem


router = APIRouter(dependencies=[Depends(_current_user)])


class UserProfileUpdateBody(BaseModel):
    email: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=8)
    current_password: str | None = Field(default=None, min_length=1)


class UserSettingsBody(BaseModel):
    ui_theme: str | None = None
    ui_mode: str | None = None
    ui_custom: dict[str, bool] | None = None
    tooltips_enabled: bool | None = None
    download_folder_enabled: bool | None = None
    download_folder_name: str | None = None
    settings_tab: str | None = None
    model_settings: dict | None = None


class BatchPromptHistoryBody(BaseModel):
    items: list[str] = Field(default_factory=list)


class BatchPromptHistoryResponse(BaseModel):
    items: list[str] = Field(default_factory=list)


class ExportTemplateItem(BaseModel):
    id: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    y_px: int = Field(..., ge=64, le=12000)


class ExportTemplatesBody(BaseModel):
    templates: list[ExportTemplateItem] = Field(default_factory=list)


class PluginStorageBody(BaseModel):
    storage: dict = Field(default_factory=dict)


class PluginValueBody(BaseModel):
    value: dict = Field(default_factory=dict)


class DemoSettingsBody(BaseModel):
    save_db: bool = False
    save_files: bool = False
    prompt_provider: str = Field(default="nvidia", min_length=1)
    prompt_model: str = Field(default="google/gemma-4-31b-it", min_length=1)
    seed_phrase: str = Field(default="日本の四季を感じさせる文章を40語以内で生成", min_length=1, max_length=1000)
    interval_seconds: int = Field(default=30, ge=1, le=3600)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)


class GroupPeer(BaseModel):
    """A person the caller may name when sharing a work."""

    id: str
    username: str


@router.get("/api/auth/me/group-peers", response_model=list[GroupPeer])
def api_me_group_peers(actor: dict = Depends(_current_user)) -> list[GroupPeer]:
    """The caller's own organisation group, so sharing can offer names.

    Under `/api/auth/me/` rather than `/api/users/`, and behind `_current_user`
    rather than `_user_manager`, because that is what it is: a fact about the
    caller, not the member directory. The directory stays where it was -- one
    server's whole membership is a manager's to read, and this feature only
    needs the names inside one organisation.
    """
    return [GroupPeer(**peer) for peer in _db.list_group_peers(actor["id"])]


@router.get("/api/auth/me", response_model=UserAccountItem)
def api_auth_me(actor: dict = Depends(_current_user)) -> UserAccountItem:
    return UserAccountItem(**actor)


@router.patch("/api/auth/me/settings", response_model=UserAccountItem)
def api_auth_me_settings(body: UserSettingsBody, actor: dict = Depends(_current_user)) -> UserAccountItem:
    try:
        user = _db.update_user_settings(
            actor["id"],
            ui_theme=body.ui_theme,
            ui_mode=body.ui_mode,
            ui_custom=body.ui_custom,
            tooltips_enabled=body.tooltips_enabled,
            download_folder_enabled=body.download_folder_enabled,
            download_folder_name=body.download_folder_name,
            settings_tab=body.settings_tab,
            model_settings=body.model_settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@router.patch("/api/auth/me/profile", response_model=UserAccountItem)
def api_auth_me_profile(body: UserProfileUpdateBody, actor: dict = Depends(_current_user)) -> UserAccountItem:
    try:
        user = _db.update_current_user_profile(
            actor["id"],
            email=body.email,
            password=body.password,
            current_password=body.current_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("profile update", 409) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@router.get("/api/auth/me/batch-prompt-history", response_model=BatchPromptHistoryResponse)
def api_auth_me_batch_prompt_history(actor: dict = Depends(_current_user)) -> BatchPromptHistoryResponse:
    return BatchPromptHistoryResponse(items=_db.get_user_batch_prompt_history(actor["id"]))


@router.put("/api/auth/me/batch-prompt-history", response_model=BatchPromptHistoryResponse)
def api_auth_me_update_batch_prompt_history(
    body: BatchPromptHistoryBody,
    actor: dict = Depends(_current_user),
) -> BatchPromptHistoryResponse:
    try:
        items = _db.update_user_batch_prompt_history(actor["id"], body.items)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if items is None:
        raise HTTPException(status_code=404, detail="user not found")
    return BatchPromptHistoryResponse(items=items)


@router.get("/api/auth/me/export-templates", response_model=ExportTemplatesBody)
def api_auth_me_export_templates(actor: dict = Depends(_current_user)) -> ExportTemplatesBody:
    return ExportTemplatesBody(templates=_db.get_user_export_templates(actor["id"]))


@router.put("/api/auth/me/export-templates", response_model=ExportTemplatesBody)
def api_auth_me_update_export_templates(
    body: ExportTemplatesBody,
    actor: dict = Depends(_current_user),
) -> ExportTemplatesBody:
    try:
        templates = _db.update_user_export_templates(
            actor["id"],
            [item.model_dump() for item in body.templates],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if templates is None:
        raise HTTPException(status_code=404, detail="user not found")
    return ExportTemplatesBody(templates=templates)


@router.get("/api/auth/me/plugin-storage", response_model=PluginStorageBody)
def api_auth_me_plugin_storage(actor: dict = Depends(_current_user)) -> PluginStorageBody:
    return PluginStorageBody(storage=_db.get_user_plugin_storage(actor["id"]))


@router.put("/api/auth/me/plugin-storage", response_model=PluginStorageBody)
def api_auth_me_update_plugin_storage(
    body: PluginStorageBody,
    actor: dict = Depends(_admin_user),
) -> PluginStorageBody:
    try:
        storage = _db.update_user_plugin_storage(actor["id"], body.storage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if storage is None:
        raise HTTPException(status_code=404, detail="user not found")
    return PluginStorageBody(storage=storage)


@router.put("/api/auth/me/plugin-storage/{plugin_id}", response_model=PluginStorageBody)
def api_auth_me_update_plugin_value(
    plugin_id: str,
    body: PluginValueBody,
    actor: dict = Depends(_admin_user),
) -> PluginStorageBody:
    try:
        storage = _db.update_user_plugin_value(actor["id"], plugin_id, body.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if storage is None:
        raise HTTPException(status_code=404, detail="user not found")
    return PluginStorageBody(storage=storage)


@router.get("/api/auth/me/demo-settings", response_model=DemoSettingsBody)
def api_auth_me_demo_settings(actor: dict = Depends(_current_user)) -> DemoSettingsBody:
    return DemoSettingsBody(**_db.get_user_demo_settings(actor["id"]))


@router.put("/api/auth/me/demo-settings", response_model=DemoSettingsBody)
def api_auth_me_update_demo_settings(
    body: DemoSettingsBody,
    actor: dict = Depends(_current_user),
) -> DemoSettingsBody:
    try:
        settings = _db.update_user_demo_settings(actor["id"], body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if settings is None:
        raise HTTPException(status_code=404, detail="user not found")
    return DemoSettingsBody(**settings)
