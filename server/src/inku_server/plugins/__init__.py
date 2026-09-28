"""Plugin registry and hook helpers.

System and user plugins live in separate directories. This package re-exports
the stable hook API used by API, renderer, and UI clients.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from .system.canvas_aspect import (
    CANVAS_ASPECT_PLUGIN_ID,
    CANVAS_ASPECTS,
    DEFAULT_CANVAS_ASPECT_ID,
    CanvasAspect,
    CanvasSize,
    canvas_aspect_ids,
    canvas_aspect_ratio_for_aspect,
    canvas_size_for_aspect,
    normalize_canvas_aspect_id,
)
from .document_format import (
    DOCUMENT_PLUGIN_MANAGER,
    PluginFormatError,
    parse_plugin_document,
    validate_plugin_document,
)


def plugin_fires_on_index() -> dict[str, dict[str, list[str]]]:
    """Firing phrases per qualified name, read from the loaded documents.

    The list endpoints hand out entry dicts built by the loader, which carry
    surfaces and notes but not `fires_on`. Joining here keeps the loader's
    entry shape untouched while letting the clients tell a wrong qualified
    name ("Nature.菖蒲") from a name that does not exist at all.
    """
    index: dict[str, dict[str, list[str]]] = {}
    for document in DOCUMENT_PLUGIN_MANAGER.documents():
        namespace = document.manifest.namespace
        for entry in document.entries:
            index[entry.qualified_name(namespace)] = {
                "ja": list(entry.fires_on.get("ja", ())),
                "en": list(entry.fires_on.get("en", ())),
            }
    return index


def entries_with_fires_on(entries: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Copy entry dicts with `fires_on_ja` / `fires_on_en` added.

    Adds keys only: every key the loader wrote is carried through unchanged.
    """
    index = plugin_fires_on_index()
    enriched: list[dict[str, object]] = []
    for entry in entries:
        merged = dict(entry)
        fires = index.get(str(entry.get("qualified_name", "")), {})
        merged["fires_on_ja"] = list(fires.get("ja", ()))
        merged["fires_on_en"] = list(fires.get("en", ()))
        enriched.append(merged)
    return enriched


def plugin_item_with_fires_on(item: dict[str, object]) -> dict[str, object]:
    """An `as_dict()` item whose entries carry the firing phrases."""
    entries = item.get("entries")
    if not isinstance(entries, list):
        return item
    return {**item, "entries": entries_with_fires_on(entries)}


# The documents that switch a package bundled with the shared core on and off.
# Its definitions live in the core; the document gives its words, notes and
# previews. Any other document is legacy Markdown: nothing reads its prose as
# a definition, so its words are omitted from drawing with a warning.
_BUNDLED_DOCUMENTS = {
    Path(__file__).resolve().parents[3] / "plugins" / "nature-leaves.inku-plugin.md": "Nature.leaves",
}


def bundled_package_for(source_path: str | Path | None) -> str | None:
    """The bundled package a plugin document switches, or None for legacy Markdown."""
    if not source_path:
        return None
    return _BUNDLED_DOCUMENTS.get(Path(source_path).resolve())


def plugin_has_definitions(plugin_id: str) -> bool:
    """Whether the installed document switches definitions the drawing uses (I-703)."""
    return bundled_package_for(DOCUMENT_PLUGIN_MANAGER.directory / plugin_id) is not None


def plugin_status_items() -> list[dict[str, object]]:
    return [
        {**item.as_dict(), "has_definitions": plugin_has_definitions(item.path)}
        for item in DOCUMENT_PLUGIN_MANAGER.items()
    ]


__all__ = [
    "CANVAS_ASPECT_PLUGIN_ID",
    "CANVAS_ASPECTS",
    "DEFAULT_CANVAS_ASPECT_ID",
    "CanvasAspect",
    "CanvasSize",
    "canvas_aspect_ids",
    "canvas_aspect_ratio_for_aspect",
    "canvas_size_for_aspect",
    "normalize_canvas_aspect_id",
    "DOCUMENT_PLUGIN_MANAGER",
    "PluginFormatError",
    "entries_with_fires_on",
    "parse_plugin_document",
    "plugin_fires_on_index",
    "plugin_item_with_fires_on",
    "plugin_status_items",
    "bundled_package_for",
    "plugin_has_definitions",
    "validate_plugin_document",
]
