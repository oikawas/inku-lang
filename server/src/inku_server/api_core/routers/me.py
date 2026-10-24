"""Endpoints for the me group, moved out of api.py unchanged."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from ... import db as _db
from ..common import _unexpected_http_error
from ..deps import _admin_user, _current_user, _session_token
from ..models import UserAccountItem


router = APIRouter(dependencies=[Depends(_current_user)])


class UserProfileUpdateBody(BaseModel):
    email: str | None = Field(
        default=None,
        min_length=1,
        description="New email address. Null or omitted leaves it unchanged. A whitespace-only value is rejected with 400.",
    )
    password: str | None = Field(
        default=None,
        min_length=8,
        description=(
            "New password, at least 8 characters. Null or omitted leaves the password unchanged. "
            "Changing it requires current_password and signs out the account's other sessions."
        ),
    )
    current_password: str | None = Field(
        default=None,
        min_length=1,
        description="The current password. Required when password is set; a wrong value is rejected with 400.",
    )


class UserSettingsBody(BaseModel):
    ui_theme: str | None = Field(
        default=None,
        description="Interface theme, `light` or `dark`. Null or omitted leaves it unchanged; other values are rejected with 400.",
    )
    ui_mode: str | None = Field(
        default=None,
        description="Interface mode, `simple`, `full` or `custom`. Null or omitted leaves it unchanged; other values are rejected with 400.",
    )
    ui_custom: dict[str, bool] | None = Field(
        default=None,
        description=(
            "Custom interface switches, as a map from area name to true or false. Accepted keys are input_modes, "
            "drawing_settings, ddl_tools, detail_status, work_tools, history and auxiliary. Null or omitted leaves it unchanged."
        ),
    )
    tooltips_enabled: bool | None = Field(
        default=None,
        description="Whether tooltips are shown. Null or omitted leaves it unchanged.",
    )
    download_folder_enabled: bool | None = Field(
        default=None,
        description="Whether downloads are saved into a named folder. Null or omitted leaves it unchanged.",
    )
    download_folder_name: str | None = Field(
        default=None,
        description="Name of the download folder, up to 240 characters. Null or omitted leaves it unchanged.",
    )
    settings_tab: str | None = Field(
        default=None,
        description=(
            "Settings tab to open by default: chatgpt, models, db, plugins, users, export, demo, misc, "
            "server_misc, logs or limits. Null or omitted leaves it unchanged; other values are rejected with 400."
        ),
    )
    model_settings: dict | None = Field(
        default=None,
        description="Model settings for the account. Null or omitted leaves them unchanged.",
    )
    history_strip_fields: list[str] | None = Field(
        default=None,
        description=(
            "Fields printed under each history thumbnail, in display order. Allowed values are generation, model, "
            "engine_version and bytes, at most three, with no repeats. An empty list hides them all. "
            "Null or omitted leaves it unchanged; an invalid list is rejected with 400."
        ),
    )


class BatchPromptHistoryBody(BaseModel):
    items: list[str] = Field(
        default_factory=list,
        description=(
            "Batch prompts to store, replacing the saved list. Each item is trimmed, and blank or repeated items "
            "are dropped. Only the first 50 are kept, and an item longer than 20,000 characters among them is rejected with 400."
        ),
    )


class BatchPromptHistoryResponse(BaseModel):
    items: list[str] = Field(
        default_factory=list,
        description="The saved batch prompts after normalization, in the order they are kept.",
    )


class ExportTemplateItem(BaseModel):
    id: str = Field(
        ...,
        min_length=1,
        max_length=80,
        description="Template identifier, 1 to 80 characters. A repeated id in the same list is dropped.",
    )
    name: str = Field(..., min_length=1, max_length=80, description="Display name, 1 to 80 characters.")
    description: str = Field(
        default="",
        max_length=240,
        description="Optional note about the template, up to 240 characters. Defaults to an empty string.",
    )
    y_px: int = Field(
        ...,
        ge=64,
        le=12000,
        description="Height of the exported image in pixels, from 64 to 12000.",
    )


class ExportTemplatesBody(BaseModel):
    templates: list[ExportTemplateItem] = Field(
        default_factory=list,
        description=(
            "Export templates. At most 20 are kept, and repeated ids are dropped. "
            "An empty list gives the three built-in PNG templates (1080, 2160 and 4320 px)."
        ),
    )


class PluginStorageBody(BaseModel):
    storage: dict = Field(
        default_factory=dict,
        description=(
            "Saved plugin data, keyed by plugin id. A plugin id is 1 to 80 characters of letters, digits, "
            "hyphens, underscores or dots, and each value must be an object. The whole map is limited to 20,000 bytes of JSON."
        ),
    )


class PluginValueBody(BaseModel):
    value: dict = Field(
        default_factory=dict,
        description="The data object to store for one plugin. It replaces that plugin's saved data. The whole saved map, including other plugins, must stay within 20,000 bytes of JSON.",
    )


class DemoSettingsBody(BaseModel):
    save_db: bool = Field(default=False, description="Whether demo runs save their results to the database. Defaults to false.")
    save_files: bool = Field(default=False, description="Whether demo runs save their result files. Defaults to false.")
    prompt_provider: str = Field(
        default="nvidia",
        min_length=1,
        description="Provider of the prompt model used by demo runs, such as `nvidia`. Must not be blank.",
    )
    prompt_model: str = Field(
        default="google/gemma-4-31b-it",
        min_length=1,
        description=(
            "Prompt model used by demo runs. If the value carries a provider prefix, that prefix is used as the provider."
        ),
    )
    seed_phrase: str = Field(
        default="日本の四季を感じさせる文章を40語以内で生成",
        min_length=1,
        max_length=1000,
        description="Seed text that the demo prompt is built from, 1 to 1,000 characters.",
    )
    interval_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
        description="Seconds between demo runs, from 1 to 3600. Defaults to 30.",
    )
    timeout_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Time limit in seconds for a demo run, from 60 to 86400. Defaults to 3600.",
    )


class GroupPeer(BaseModel):
    """A person the caller may name when sharing a work."""

    id: str = Field(description="Account id of a member of the caller's user group.")
    username: str = Field(description="Sign-in name of that member.")


@router.get("/api/auth/me/group-peers", response_model=list[GroupPeer], summary="List user group members for sharing")
def api_me_group_peers(actor: dict = Depends(_current_user)) -> list[GroupPeer]:
    """List the members of the caller's own user group, so a work can be shared by name.

    Any signed-in user may call it. It lists only the caller's user group; the
    whole account list stays with GET /api/users.
    """
    return [GroupPeer(**peer) for peer in _db.list_group_peers(actor["id"])]


@router.get("/api/auth/me", response_model=UserAccountItem, summary="Get the signed-in account")
def api_auth_me(actor: dict = Depends(_current_user)) -> UserAccountItem:
    """Return the account of the signed-in user, with its permission groups and user group.

    Requires a valid session; a missing or unknown session is rejected with 401.
    """
    return UserAccountItem(**actor)


@router.patch("/api/auth/me/settings", response_model=UserAccountItem, summary="Update display settings")
def api_auth_me_settings(body: UserSettingsBody, actor: dict = Depends(_current_user)) -> UserAccountItem:
    """Update the signed-in user's interface and display settings, leaving omitted fields unchanged.

    Returns the updated account. An invalid value is rejected with 400.
    """
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
            history_strip_fields=body.history_strip_fields,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@router.patch("/api/auth/me/profile", response_model=UserAccountItem, summary="Update own email or password")
def api_auth_me_profile(
    body: UserProfileUpdateBody,
    actor: dict = Depends(_current_user),
    token: str = Depends(_session_token),
) -> UserAccountItem:
    """Change the signed-in user's email address and, with the current password, the password.

    A password change signs out the account's other sessions and keeps the session that made the
    request. Returns the updated account. An invalid value or a wrong current password is rejected
    with 400, and an unexpected failure returns 409.
    """
    try:
        user = _db.update_current_user_profile(
            actor["id"],
            email=body.email,
            password=body.password,
            current_password=body.current_password,
            keep_session_token=token,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("profile update", 409) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@router.get(
    "/api/auth/me/batch-prompt-history",
    response_model=BatchPromptHistoryResponse,
    summary="Get batch prompt history",
)
def api_auth_me_batch_prompt_history(actor: dict = Depends(_current_user)) -> BatchPromptHistoryResponse:
    """Return the batch prompts saved for the signed-in user."""
    return BatchPromptHistoryResponse(items=_db.get_user_batch_prompt_history(actor["id"]))


@router.put(
    "/api/auth/me/batch-prompt-history",
    response_model=BatchPromptHistoryResponse,
    summary="Replace batch prompt history",
)
def api_auth_me_update_batch_prompt_history(
    body: BatchPromptHistoryBody,
    actor: dict = Depends(_current_user),
) -> BatchPromptHistoryResponse:
    """Replace the signed-in user's saved batch prompts with the list sent, after normalization.

    Returns the stored list. An item that is too long is rejected with 400.
    """
    try:
        items = _db.update_user_batch_prompt_history(actor["id"], body.items)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if items is None:
        raise HTTPException(status_code=404, detail="user not found")
    return BatchPromptHistoryResponse(items=items)


@router.get("/api/auth/me/export-templates", response_model=ExportTemplatesBody, summary="Get export templates")
def api_auth_me_export_templates(actor: dict = Depends(_current_user)) -> ExportTemplatesBody:
    """Return the export templates saved for the signed-in user."""
    return ExportTemplatesBody(templates=_db.get_user_export_templates(actor["id"]))


@router.put("/api/auth/me/export-templates", response_model=ExportTemplatesBody, summary="Replace export templates")
def api_auth_me_update_export_templates(
    body: ExportTemplatesBody,
    actor: dict = Depends(_current_user),
) -> ExportTemplatesBody:
    """Replace the signed-in user's export templates with the list sent, after normalization.

    Returns the stored list. An invalid template is rejected with 400.
    """
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


@router.get("/api/auth/me/plugin-storage", response_model=PluginStorageBody, summary="Get plugin storage")
def api_auth_me_plugin_storage(actor: dict = Depends(_current_user)) -> PluginStorageBody:
    """Return the plugin data saved for the signed-in user, keyed by plugin id."""
    return PluginStorageBody(storage=_db.get_user_plugin_storage(actor["id"]))


@router.put("/api/auth/me/plugin-storage", response_model=PluginStorageBody, summary="Replace all plugin storage")
def api_auth_me_update_plugin_storage(
    body: PluginStorageBody,
    actor: dict = Depends(_admin_user),
) -> PluginStorageBody:
    """Replace all plugin data saved for the signed-in administrator with the map sent.

    Requires an administrator. Invalid plugin ids, values or total size are rejected with 400.
    """
    try:
        storage = _db.update_user_plugin_storage(actor["id"], body.storage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if storage is None:
        raise HTTPException(status_code=404, detail="user not found")
    return PluginStorageBody(storage=storage)


@router.put(
    "/api/auth/me/plugin-storage/{plugin_id}",
    response_model=PluginStorageBody,
    summary="Replace one plugin's data",
)
def api_auth_me_update_plugin_value(
    plugin_id: Annotated[
        str,
        Path(description="Plugin id whose saved data is replaced. Up to 80 characters of letters, digits, hyphens, underscores or dots."),
    ],
    body: PluginValueBody,
    actor: dict = Depends(_admin_user),
) -> PluginStorageBody:
    """Replace the saved data of one plugin for the signed-in administrator, leaving other plugins unchanged.

    Requires an administrator. Returns the whole stored map. An invalid plugin id, value or total
    size is rejected with 400.
    """
    try:
        storage = _db.update_user_plugin_value(actor["id"], plugin_id, body.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if storage is None:
        raise HTTPException(status_code=404, detail="user not found")
    return PluginStorageBody(storage=storage)


@router.get("/api/auth/me/demo-settings", response_model=DemoSettingsBody, summary="Get demo settings")
def api_auth_me_demo_settings(actor: dict = Depends(_current_user)) -> DemoSettingsBody:
    """Return the demo run settings saved for the signed-in user."""
    return DemoSettingsBody(**_db.get_user_demo_settings(actor["id"]))


@router.put("/api/auth/me/demo-settings", response_model=DemoSettingsBody, summary="Replace demo settings")
def api_auth_me_update_demo_settings(
    body: DemoSettingsBody,
    actor: dict = Depends(_current_user),
) -> DemoSettingsBody:
    """Save the demo run settings for the signed-in user and return them after normalization.

    Invalid values are rejected with 400.
    """
    try:
        settings = _db.update_user_demo_settings(actor["id"], body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if settings is None:
        raise HTTPException(status_code=404, detail="user not found")
    return DemoSettingsBody(**settings)
