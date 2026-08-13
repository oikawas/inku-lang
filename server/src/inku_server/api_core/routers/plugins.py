"""Endpoints for the plugins group, moved out of api.py unchanged."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ...plugins import (
    DOCUMENT_PLUGIN_MANAGER,
    PluginFormatError,
    plugin_item_with_fires_on,
    validate_plugin_document,
)
from ..deps import _admin_user, _current_user


router = APIRouter(dependencies=[Depends(_current_user)])


class PluginValidateBody(BaseModel):
    document: str = Field(..., min_length=1, max_length=500_000)


class PluginCreateBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=500_000)
    filename: str | None = Field(default=None, max_length=200)


class PluginUpdateBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=500_000)


class PluginEnabledBody(BaseModel):
    enabled: bool


@router.get("/api/plugins")
def api_plugins() -> dict[str, object]:
    # Entries carry `fires_on_*` so an editor can say which plain word a wrong
    # qualified name would have fired ("Nature.菖蒲" -> 下草).
    return {
        "items": [
            plugin_item_with_fires_on(item.as_dict())
            for item in DOCUMENT_PLUGIN_MANAGER.items()
        ]
    }


@router.post("/api/plugins/validate")
def api_plugins_validate(
    body: PluginValidateBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    try:
        document = validate_plugin_document(body.document)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    return {
        "valid": True,
        "namespace": document.manifest.namespace,
        "name": document.manifest.name,
        "version": document.manifest.version,
        "entries": len(document.entries),
    }


@router.post("/api/plugins/reload")
def api_plugins_reload(actor: dict = Depends(_admin_user)) -> dict[str, object]:
    items = DOCUMENT_PLUGIN_MANAGER.reload(force=True)
    return {"items": [item.as_dict() for item in items]}


@router.get("/api/plugins/{plugin_id}/content")
def api_plugin_content(plugin_id: str, actor: dict = Depends(_admin_user)) -> dict[str, object]:
    try:
        content = DOCUMENT_PLUGIN_MANAGER.content(plugin_id)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return {"id": plugin_id, "path": plugin_id, "content": content, "editable": True}


@router.post("/api/plugins", status_code=201)
def api_plugin_create(
    body: PluginCreateBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    try:
        item = DOCUMENT_PLUGIN_MANAGER.create(body.content, filename=body.filename)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"plugin file already exists: {exc}") from None
    return item.as_dict()


@router.put("/api/plugins/{plugin_id}")
def api_plugin_update(
    plugin_id: str,
    body: PluginUpdateBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    try:
        item = DOCUMENT_PLUGIN_MANAGER.update(plugin_id, body.content)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return item.as_dict()


@router.delete("/api/plugins/{plugin_id}")
def api_plugin_delete(plugin_id: str, actor: dict = Depends(_admin_user)) -> dict[str, object]:
    try:
        DOCUMENT_PLUGIN_MANAGER.delete(plugin_id)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return {"ok": True}


@router.put("/api/plugins/{plugin_id}/enabled")
def api_plugin_set_enabled(
    plugin_id: str,
    body: PluginEnabledBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    try:
        item = DOCUMENT_PLUGIN_MANAGER.set_enabled(plugin_id, body.enabled)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return item.as_dict()
