"""Python host surface for the shared inku render core."""

from ._native import (
    core_api_version,
    default_color_map_json,
    pipeline_canvas_registry,
    pipeline_explain_plugin_diagnostics,
    pipeline_provider_attempt,
    pipeline_render_saved,
    pipeline_resolve_macro_catalog,
    pipeline_resolve_palette,
    pipeline_stage1_system_projection,
    pipeline_step,
    pipeline_version_report,
    render,
    render_engine_id,
    render_engine_version,
    render_with_resources,
    renderer_reference_json,
)

__all__ = (
    "core_api_version",
    "default_color_map_json",
    "pipeline_canvas_registry",
    "pipeline_explain_plugin_diagnostics",
    "pipeline_provider_attempt",
    "pipeline_render_saved",
    "pipeline_resolve_macro_catalog",
    "pipeline_resolve_palette",
    "pipeline_stage1_system_projection",
    "pipeline_step",
    "pipeline_version_report",
    "render",
    "render_engine_id",
    "render_engine_version",
    "render_with_resources",
    "renderer_reference_json",
)
