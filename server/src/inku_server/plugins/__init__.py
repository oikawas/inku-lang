"""Plugin registry and hook helpers.

System and user plugins live in separate directories. This package re-exports
the stable hook API used by API, renderer, and UI clients.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

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


def plugin_status_items() -> list[dict[str, object]]:
    system: list[dict[str, object]] = [
        {
            "name": CANVAS_ASPECT_PLUGIN_ID,
            "namespace": "system",
            "version": "0.1.0",
            "status": "enabled",
            "entries": [],
            "reasons": [],
        }
    ]
    return system + [item.as_dict() for item in DOCUMENT_PLUGIN_MANAGER.items()]


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
    "validate_plugin_document",
]
