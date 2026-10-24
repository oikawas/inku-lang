"""Endpoints for the plugins group, moved out of api.py unchanged."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from ...plugins import (
    DOCUMENT_PLUGIN_MANAGER,
    PluginFormatError,
    plugin_has_definitions,
    plugin_item_with_fires_on,
    validate_plugin_document,
)
from ..deps import _admin_user, _current_user


router = APIRouter(dependencies=[Depends(_current_user)])


class PluginValidateBody(BaseModel):
    document: str = Field(
        ..., min_length=1, max_length=500_000,
        description="The full text of the plugin document to check, 1 to 500,000 characters.",
    )


class PluginEnabledBody(BaseModel):
    enabled: bool = Field(description="True to switch the plugin package on, False to switch it off.")


@router.get("/api/plugins", summary="List plugin packages")
def api_plugins() -> dict[str, object]:
    """List every installed plugin package with its status, entries and reasons.

    Each item's id is the value to pass as plugin_id to the other plugin routes.
    has_definitions is true when the package switches definitions bundled with
    the server, whether or not it is switched on. Requires a signed-in user;
    responds 401 when there is no valid session.
    """
    # Entries carry `fires_on_*` so an editor can say which plain word a wrong
    # qualified name would have fired ("Nature.菖蒲" -> 下草).
    return {
        "items": [
            {**plugin_item_with_fires_on(item.as_dict()), "has_definitions": plugin_has_definitions(item.path)}
            for item in DOCUMENT_PLUGIN_MANAGER.items()
        ]
    }


@router.post("/api/plugins/validate", summary="Validate a plugin document")
def api_plugins_validate(
    body: PluginValidateBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Check the text of a plugin document and report its namespace, name, version and entry count.

    Requires an administrator; responds 403 otherwise. Responds 422 with the list
    of reasons when the document is not a valid plugin document.
    """
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


@router.post("/api/plugins/reload", summary="Reload plugin packages")
def api_plugins_reload(actor: dict = Depends(_admin_user)) -> dict[str, object]:
    """Reload every plugin package from disk and return the resulting items.

    The reload is forced, so the files are read again even when they have not
    changed. Requires an administrator; responds 403 otherwise.
    """
    items = DOCUMENT_PLUGIN_MANAGER.reload(force=True)
    return {"items": [item.as_dict() for item in items]}


@router.delete("/api/plugins/{plugin_id}", summary="Delete a plugin document")
def api_plugin_delete(
    plugin_id: Annotated[str, Path(description="Identifier of the plugin to delete, as the id field of GET /api/plugins.")],
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Delete a plugin document that does not switch bundled definitions.

    Requires an administrator; responds 403 otherwise. Responds 409 when the
    document switches definitions bundled with the server, which can be
    switched off instead, 404 when no plugin has this identifier, and 422 when
    the identifier is not a valid plugin file name.
    """
    # A package the drawing uses is switched off, not deleted: removing its
    # document would also remove its words and previews from the Saijiki.
    # Only legacy Markdown, which nothing draws from, can be removed here.
    if plugin_has_definitions(plugin_id):
        raise HTTPException(status_code=409, detail="a package the drawing uses cannot be deleted; switch it off instead")
    try:
        DOCUMENT_PLUGIN_MANAGER.delete(plugin_id)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return {"ok": True}


@router.put("/api/plugins/{plugin_id}/enabled", summary="Switch a plugin on or off")
def api_plugin_set_enabled(
    plugin_id: Annotated[str, Path(description="Identifier of the plugin package, as the id field of GET /api/plugins.")],
    body: PluginEnabledBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Switch a plugin package on or off and return the updated item.

    Requires an administrator; responds 403 otherwise. Responds 404 when no
    plugin has this identifier, and 422 when the identifier is not a valid
    plugin file name. A package with format errors is still switched; its item
    carries the status and the reasons.
    """
    try:
        item = DOCUMENT_PLUGIN_MANAGER.set_enabled(plugin_id, body.enabled)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return item.as_dict()
