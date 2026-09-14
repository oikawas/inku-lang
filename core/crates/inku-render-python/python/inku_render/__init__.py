"""Python host surface for the shared inku render core."""

from ._native import (
    core_api_version,
    default_color_map_json,
    pipeline_canvas_registry,
    pipeline_render_saved,
    pipeline_resolve_macro_catalog,
    pipeline_resolve_palette,
    pipeline_step,
    pipeline_version_report,
    renderer_reference_json,
    render,
    render_with_resources,
    render_engine_id,
    render_engine_version,
)

__all__ = (
    "core_api_version",
    "default_color_map_json",
    "pipeline_canvas_registry",
    "pipeline_render_saved",
    "pipeline_resolve_macro_catalog",
    "pipeline_resolve_palette",
    "pipeline_step",
    "pipeline_version_report",
    "renderer_reference_json",
    "render",
    "render_with_resources",
    "render_engine_id",
    "render_engine_version",
)
