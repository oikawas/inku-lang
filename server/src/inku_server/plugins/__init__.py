"""System canvas settings and v2 plugin packages."""

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
from .packages import PLUGIN_PACKAGE_MANAGER


def plugin_status_items() -> list[dict[str, object]]:
    return PLUGIN_PACKAGE_MANAGER.status_items()


__all__ = [
    "CANVAS_ASPECT_PLUGIN_ID", "CANVAS_ASPECTS", "DEFAULT_CANVAS_ASPECT_ID",
    "CanvasAspect", "CanvasSize", "canvas_aspect_ids",
    "canvas_aspect_ratio_for_aspect", "canvas_size_for_aspect",
    "normalize_canvas_aspect_id", "PLUGIN_PACKAGE_MANAGER", "plugin_status_items",
]
