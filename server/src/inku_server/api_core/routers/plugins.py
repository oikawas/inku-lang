"""Endpoints for the plugins group, moved out of api.py unchanged."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from ...plugins import (
    DOCUMENT_PLUGIN_MANAGER,
    PLUGIN_PACKAGE_MANAGER,
    PluginFormatError,
    plugin_has_definitions,
    plugin_item_with_fires_on,
    validate_plugin_document,
)
from ...plugins.packages import (
    PluginPackage,
    PluginPackageError,
    check_package,
    data_url,
    parse_plugin_package,
    preview_pngs,
    uploaded_preview_pngs,
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


class PluginPackageCheckBody(BaseModel):
    document: str = Field(
        ..., min_length=1, max_length=1_000_000,
        description="The full text of an inku.plugin-package.v1 JSON file, 1 to 1,000,000 characters.",
    )


class PluginPackageInstallBody(PluginPackageCheckBody):
    replace: bool = Field(
        default=False,
        description="True to replace an installed package with the same id. Without it a package whose id is already installed is refused with 409.",
    )


class PluginPreviewBody(BaseModel):
    png_base64: str = Field(
        ..., min_length=1, max_length=3_000_000,
        description="The replacement picture as base64-encoded PNG bytes, up to 2 MB before encoding. It is fitted to the Saijiki frame at both scales.",
    )


@router.get("/api/plugins", summary="List plugin packages")
def api_plugins() -> dict[str, object]:
    """List every installed plugin package with its status, entries and reasons.

    Each item's id is the value to pass as plugin_id to the other plugin routes.
    kind is "document" for a plugin document in the server's plugin directory
    and "package" for a package an administrator installed from the Web.
    has_definitions is true when the item gives definitions the drawing uses,
    whether or not it is switched on. Requires a signed-in user; responds 401
    when there is no valid session.
    """
    # Entries carry `fires_on_*` so an editor can say which plain word a wrong
    # qualified name would have fired ("Nature.菖蒲" -> 下草).
    return {
        "items": [
            {**plugin_item_with_fires_on(item.as_dict()), "kind": "document",
             "has_definitions": plugin_has_definitions(item.path),
             "deletable": not plugin_has_definitions(item.path)}
            for item in DOCUMENT_PLUGIN_MANAGER.items()
        ] + PLUGIN_PACKAGE_MANAGER.status_items()
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


def _taken_names(excluding: str) -> dict[str, str]:
    """Every visible name another installed plugin holds, mapped to that plugin."""
    from ...macro_catalog import _installed_plugin_names

    packages = PLUGIN_PACKAGE_MANAGER.visible_names()
    enabled, disabled = _installed_plugin_names()
    taken = {name: "plugin document" for name in [*enabled, *disabled] if name not in packages}
    taken.update(PLUGIN_PACKAGE_MANAGER.visible_names(excluding=excluding))
    return taken


def _check(text: str, owner: str) -> tuple[PluginPackage | None, dict[str, object], dict[str, tuple[bytes, bytes]]]:
    """Parse and check a package.

    The report carries each word's picture as a data URL; the pictures
    themselves, at both scales, come back beside it for installing.
    """
    from ...pipeline_compat import draw_plugin_example
    from ...pipeline_runtime import get_binding

    try:
        package = parse_plugin_package(text)
    except PluginPackageError as exc:
        return None, {"ok": False, "problems": [problem.as_dict() for problem in exc.problems], "words": []}, {}
    report = check_package(
        package,
        binding=get_binding(),
        draw_example=lambda ddl, language, imported: draw_plugin_example(owner, ddl, language, imported),
        taken_names=_taken_names(package.id),
    )
    pictures = {}
    for word, word_report in zip(package.words, report["words"], strict=True):
        svg = word_report.pop("preview_svg", "")
        if svg:
            pictures[word.preview_key()] = preview_pngs(svg)
            word_report["preview_png"] = data_url(pictures[word.preview_key()][1])
    report["exists"] = PLUGIN_PACKAGE_MANAGER.has(package.id)
    return package, report, pictures


@router.post("/api/plugins/packages/validate", summary="Check a plugin package without installing it")
def api_plugin_package_validate(
    body: PluginPackageCheckBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Check an inku.plugin-package.v1 file the way installing it would, and install nothing.

    The file's own shape is checked first, then each word's definition by the
    shared core, then each word's Japanese and English example is drawn. ok is
    true only when every step passed. problems lists what is wrong with the
    file as a whole; each word in words lists its own problems and, when its
    example drew, the picture the Saijiki would show as a PNG data URL. exists
    is true when a package with the same id is installed. Each problem has a
    path in the file, a code and an optional detail. Requires an administrator;
    responds 403 otherwise.
    """
    _package, report, _pictures = _check(body.document, actor["id"])
    return report


@router.post("/api/plugins/packages", summary="Install a plugin package")
def api_plugin_package_install(
    body: PluginPackageInstallBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Check an inku.plugin-package.v1 file and install it when every check passes.

    Installed words are used by every new work, are shown in the Saijiki with
    the picture drawn from their Japanese example, and are offered to Stage 1
    through their summaries. Saved works keep drawing with the definitions
    they saved. Requires an administrator; responds 403 otherwise. Responds 422
    with the check report as detail when a check fails, and 409 when a
    package with the same id is installed and replace is false.
    """
    package, report, pictures = _check(body.document, actor["id"])
    if package is None or not report["ok"]:
        raise HTTPException(status_code=422, detail=report)
    if report["exists"] and not body.replace:
        raise HTTPException(status_code=409, detail={"code": "package_exists", "id": package.id})
    PLUGIN_PACKAGE_MANAGER.install(body.document, package, pictures)
    return next(item for item in PLUGIN_PACKAGE_MANAGER.status_items() if item["id"] == package.id)


@router.delete("/api/plugins/{plugin_id}", summary="Delete a plugin document")
def api_plugin_delete(
    plugin_id: Annotated[str, Path(description="Identifier of the plugin to delete, as the id field of GET /api/plugins.")],
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Delete a package installed from the Web, or a plugin document that does not switch bundled definitions.

    Saved works keep drawing with the definitions they saved. Requires an
    administrator; responds 403 otherwise. Responds 409 when the document
    switches definitions bundled with the server, which can be switched off
    instead, 404 when no plugin has this identifier, and 422 when the
    identifier is not a valid plugin file name.
    """
    if PLUGIN_PACKAGE_MANAGER.names_a_package(plugin_id):
        try:
            PLUGIN_PACKAGE_MANAGER.delete(plugin_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="plugin not found") from None
        return {"ok": True}
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
    if PLUGIN_PACKAGE_MANAGER.names_a_package(plugin_id):
        try:
            PLUGIN_PACKAGE_MANAGER.set_enabled(plugin_id, body.enabled)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="plugin not found") from None
        return next(item for item in PLUGIN_PACKAGE_MANAGER.status_items() if item["id"] == plugin_id)
    try:
        item = DOCUMENT_PLUGIN_MANAGER.set_enabled(plugin_id, body.enabled)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return item.as_dict()


@router.put("/api/plugins/{plugin_id}/words/{heading}/preview", summary="Replace a package word's Saijiki picture")
def api_plugin_preview_replace(
    plugin_id: Annotated[str, Path(description="Identifier of a package installed from the Web, as the id field of GET /api/plugins.")],
    heading: Annotated[str, Path(description="The word's heading, as in its definition (not an alias).")],
    body: PluginPreviewBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Show an administrator's own PNG for one word in the Saijiki instead of the picture drawn from its example.

    The picture is fitted to the Saijiki frame at both scales; replacing the
    package later keeps it. Requires an administrator; responds 403 otherwise.
    Responds 404 when no installed package has this word, and 422 when the
    data is not a PNG or is too large.
    """
    try:
        data = base64.b64decode(body.png_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail=[{"path": "image", "code": "not_base64", "detail": ""}]) from None
    try:
        pictures = uploaded_preview_pngs(data)
    except PluginPackageError as exc:
        raise HTTPException(status_code=422, detail=[problem.as_dict() for problem in exc.problems]) from exc
    return _set_preview(plugin_id, heading, pictures)


@router.delete("/api/plugins/{plugin_id}/words/{heading}/preview", summary="Go back to a package word's drawn picture")
def api_plugin_preview_reset(
    plugin_id: Annotated[str, Path(description="Identifier of a package installed from the Web, as the id field of GET /api/plugins.")],
    heading: Annotated[str, Path(description="The word's heading, as in its definition (not an alias).")],
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Remove an administrator's picture so the Saijiki shows the one drawn from the word's example again.

    Requires an administrator; responds 403 otherwise. Responds 404 when no
    installed package has this word.
    """
    return _set_preview(plugin_id, heading, None)


def _set_preview(plugin_id: str, heading: str, pictures: tuple[bytes, bytes] | None) -> dict[str, object]:
    if not PLUGIN_PACKAGE_MANAGER.has(plugin_id):
        raise HTTPException(status_code=404, detail="plugin not found")
    try:
        PLUGIN_PACKAGE_MANAGER.set_custom_preview(plugin_id, heading, pictures)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="word not found") from None
    return next(item for item in PLUGIN_PACKAGE_MANAGER.status_items() if item["id"] == plugin_id)
