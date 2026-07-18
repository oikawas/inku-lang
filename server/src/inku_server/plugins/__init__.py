"""Plugin registry and hook helpers.

System and user plugins live in separate directories. This package re-exports
the stable hook API used by API, renderer, and UI clients.
"""

from __future__ import annotations

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
    "parse_plugin_document",
    "plugin_status_items",
    "validate_plugin_document",
]
