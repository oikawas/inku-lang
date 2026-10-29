"""Endpoints for the plugins group, moved out of api.py unchanged."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field, model_validator
from ...plugins import PLUGIN_PACKAGE_MANAGER
from ...plugins.packages import (
    PluginPackage,
    PluginPackageError,
    Problem,
    data_url,
    package_core,
    parse_plugin_package,
)
from ..deps import _admin_user, _current_user


router = APIRouter(dependencies=[Depends(_current_user)])


class PluginEnabledBody(BaseModel):
    enabled: bool = Field(description="True to switch the plugin package on, False to switch it off.")


class PluginPackageCheckBody(BaseModel):
    document: str | None = Field(
        default=None, min_length=1, max_length=1_000_000,
        description="The full text of an inku.plugin-package.v2 JSON file, 1 to 1,000,000 characters. Send this or archive, not both.",
    )
    archive: str | None = Field(
        default=None, min_length=1, max_length=22_400_000,
        description="A zip as base64: package.json (an inku.plugin-package.v2 file) beside the PNG pictures its words name in preview, up to 16 MiB before encoding. Send this or document, not both.",
    )

    @model_validator(mode="after")
    def _one_of_the_two(self) -> "PluginPackageCheckBody":
        if (self.document is None) == (self.archive is None):
            raise ValueError("send exactly one of document and archive")
        return self


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
    kind is "package" for a bundled or installed package.
    has_definitions is true when the item gives definitions the drawing uses,
    whether or not it is switched on. Requires a signed-in user; responds 401
    when there is no valid session.
    """
    return {"items": PLUGIN_PACKAGE_MANAGER.status_items()}


def _taken_names(excluding: str) -> dict[str, str]:
    """Every visible name another installed plugin holds, mapped to that plugin."""
    return PLUGIN_PACKAGE_MANAGER.visible_names(excluding=excluding)


@dataclass(frozen=True)
class _Checked:
    package: PluginPackage | None
    text: str
    report: dict[str, object]
    pictures: dict[str, tuple[bytes, bytes]]


def _check(body: PluginPackageCheckBody, owner: str) -> _Checked:
    """Read, parse and check a package sent as a JSON file or as a zip.

    The report carries each word's picture as a data URL; the pictures
    themselves, at both scales, come back beside it for installing, with the
    package.json text to store.
    """
    from ...pipeline_compat import draw_plugin_example

    def refused(problems) -> _Checked:
        return _Checked(package=None, text="", pictures={},
                        report={"ok": False, "problems": [problem.as_dict() for problem in problems], "words": []})

    if body.archive is not None:
        try:
            base64.b64decode(body.archive, validate=True)
        except (binascii.Error, ValueError):
            return refused([Problem("", "not_base64")])
    payload = {"action": "check_start", "taken_names": _taken_names("")}
    payload["archive" if body.archive is not None else "document"] = body.archive if body.archive is not None else body.document
    started = package_core(payload)
    if started["outcome"] == "refused":
        return refused([Problem(**p) for p in started["problems"]])
    drawings = []
    for request in started["draw"]:
        drawing = draw_plugin_example(owner, request["ddl"], request["language"], started["imported"])
        drawings.append({"id": request["id"], "svg": drawing.svg, "marks": drawing.marks, "reasons": list(drawing.reasons)})
    finished = package_core({"action": "check_finish", "state": started["state"], "drawings": drawings})
    report = finished["report"]
    pictures = {key: (base64.b64decode(value["png"]), base64.b64decode(value["png_2x"]))
                for key, value in finished["pictures"].items()}
    package = parse_plugin_package(finished["text"], stored=True)
    for word, word_report in zip(package.words, report["words"], strict=True):
        word_report["preview_png"] = data_url(pictures[word.preview_key()][1]) if word.preview_key() in pictures else ""
    report["exists"] = PLUGIN_PACKAGE_MANAGER.has(package.id)
    return _Checked(package=package, text=finished["text"], report=report, pictures=pictures)

@router.post("/api/plugins/packages/validate", summary="Check a plugin package without installing it")
def api_plugin_package_validate(
    body: PluginPackageCheckBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Check an inku.plugin-package.v2 file, or a zip holding one, the way installing it would, and install nothing.

    The file's own shape is checked first, then each word's definition by the
    shared core, then each word's Japanese and English example is drawn. ok is
    true only when every step passed. problems lists what is wrong with the
    file as a whole; each word in words lists its own problems and the picture
    the Saijiki would show as a PNG data URL: the one the word names in its zip
    (preview_source "file"), or else the one its example drew ("drawn"). exists
    is true when a package with the same id is installed. Each problem has a
    path in the file, a code and an optional detail. Requires an administrator;
    responds 403 otherwise.
    """
    return _check(body, actor["id"]).report


@router.post("/api/plugins/packages", summary="Install a plugin package")
def api_plugin_package_install(
    body: PluginPackageInstallBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Check an inku.plugin-package.v2 file, or a zip holding one, and install it when every check passes.

    Installed words are used by every new work, are shown in the Saijiki with
    the picture they name in their zip or else the one drawn from their
    Japanese example, and are offered to Stage 1 through their notes.
    Saved works keep drawing with the definitions they saved. Requires an
    administrator; responds 403 otherwise. Responds 422 with the check report
    as detail when a check fails, and 409 when a package with the same id is
    installed and replace is false.
    """
    checked = _check(body, actor["id"])
    package, report = checked.package, checked.report
    if package is None or not report["ok"]:
        raise HTTPException(status_code=422, detail=report)
    if package.id == "Nature.leaves":
        raise HTTPException(status_code=409, detail={"code": "bundled_package_id", "id": package.id})
    if report["exists"] and not body.replace:
        raise HTTPException(status_code=409, detail={"code": "package_exists", "id": package.id})
    PLUGIN_PACKAGE_MANAGER.install(checked.text, package, checked.pictures)
    return next(item for item in PLUGIN_PACKAGE_MANAGER.status_items() if item["id"] == package.id)


@router.get("/api/plugins/{plugin_id}/export", summary="Export a plugin package as a zip")
def api_plugin_package_export(
    plugin_id: Annotated[str, Path(description="Identifier of a package installed from the Web, as the id field of GET /api/plugins.")],
    actor: dict = Depends(_admin_user),
) -> Response:
    """Return an installed package as a zip that another server can add as it is.

    The zip holds package.json, with each word's preview naming the picture
    the Saijiki shows now (an administrator's replacement where there is one),
    beside those pictures. Requires an administrator; responds 403 otherwise,
    and 404 when no package installed from the Web has this identifier.
    """
    try:
        name, data = PLUGIN_PACKAGE_MANAGER.export(plugin_id)
    except (FileNotFoundError, PluginPackageError):
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


@router.delete("/api/plugins/{plugin_id}", summary="Delete a plugin package")
def api_plugin_delete(
    plugin_id: Annotated[str, Path(description="Identifier of the plugin to delete, as the id field of GET /api/plugins.")],
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    """Delete a package installed from the Web.

    Saved works keep drawing with the definitions they saved. Requires an
    administrator; responds 403 otherwise. Responds 409 for the built-in
    Nature.leaves package, which can be switched off instead,
    404 when no plugin has this identifier, and 422 when the
    identifier is not a valid plugin file name.
    """
    if plugin_id == "Nature.leaves":
        raise HTTPException(status_code=409, detail="a package the drawing uses cannot be deleted; switch it off instead")
    try:
        PLUGIN_PACKAGE_MANAGER.delete(plugin_id)
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
        PLUGIN_PACKAGE_MANAGER.set_enabled(plugin_id, body.enabled)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return next(item for item in PLUGIN_PACKAGE_MANAGER.status_items() if item["id"] == plugin_id)


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
    result = package_core({"action": "fit_picture", "png": base64.b64encode(data).decode("ascii")})
    if result["outcome"] == "refused":
        raise HTTPException(status_code=422, detail=result["problems"])
    pictures = (base64.b64decode(result["png"]), base64.b64decode(result["png_2x"]))
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
