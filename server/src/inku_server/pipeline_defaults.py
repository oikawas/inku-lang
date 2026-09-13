"""Installation defaults for the shared pipeline, separate from core semantics."""

from __future__ import annotations

import json
import os
from copy import deepcopy

from .color_catalogs import render_color_map_for_catalog
from .limits import DEFAULT_LIMITS
from .pipeline_candidate import PipelineBinding, _bytes
from .plugins.system.canvas_aspect import CANVAS_BASE_PX


# New works use the adopted structural bounds. Existing saved configurations
# retain their own bounds, just as they retain the four older render limits.
ADDITIONAL_RESOURCE_LIMITS = {
    "logical_objects": 4096,
    "template_nodes": 128,
    "anchor_instances": 4096,
    "transform_instances": 4096,
    "placement_instances": 64,
    "fill_instances": 64,
}


def default_manifest(binding: PipelineBinding) -> dict:
    registry = binding.canvas_registry
    palette = json.loads(binding.resolve_palette(_bytes({
        "color_map": render_color_map_for_catalog("default"), "catalog_id": "default",
        "render_seed": None, "background": "white",
    })))
    budget = {"maximum": {
        **ADDITIONAL_RESOURCE_LIMITS,
        "primitive_marks": DEFAULT_LIMITS.max_expanded_primitives,
        "maximum_per_template_primitive_marks": DEFAULT_LIMITS.max_expanded_per_instruction,
        "maximum_resolved_count": DEFAULT_LIMITS.schema_count_max,
        "object_templates": DEFAULT_LIMITS.max_instructions,
    }}
    # The existing outer stage deadline remains the total bound. Core alone
    # decides which transient failures merit another attempt inside that bound.
    timeout_ms = max(1, int(float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "120")) * 1000))
    retry = {"max_attempts": max(1, int(os.getenv("INKU_LLM_RETRY_ATTEMPTS", "4"))),
             "attempt_timeout_ms": str(timeout_ms), "total_timeout_ms": str(timeout_ms),
             "retry_delay_ms": str(max(0, int(float(os.getenv("INKU_LLM_RETRY_BASE_DELAY", "2")) * 1000)))}
    return {
        "schema": "inku.pipeline-host.v1",
        "pipeline": {
            "envelope_limits": {"max_input_bytes": 16 * 1024 * 1024,
                                "max_snapshot_bytes": 32 * 1024 * 1024,
                                "max_output_bytes": 64 * 1024 * 1024},
            "language": "en",
            "compiler": {
                "host": {"canvas_format_id": "square", "canvas_format_registry_id": registry["registry"]["schema"],
                         "canvas_format_registry_digest": registry["digest"], "resolved_catalog_id": "default",
                         "catalog_mode": "default", "background": "white", "palette": palette},
                "composition_seed": None,
                "macro_expansion_limits": {"max_invocations": "64", "max_depth": "16",
                                           "max_evaluation_steps": "8192", "max_nodes_per_invocation": "128",
                                           "max_total_nodes": "128"},
                "stage15_variation": None, "error_policy": "omit_and_continue",
                "hard_resource_policy": {"identity": "installation-default.v1", "budget": deepcopy(budget)},
                "operational_resource_budget": deepcopy(budget),
            },
            "definitions": [], "macro_summaries": [], "catalogs": [],
            "prompt_limits": {"max_catalog_entries": 64, "max_summary_bytes": 8192,
                              "max_catalog_serialized_bytes": 1024 * 1024,
                              "max_source_bytes": 400_000, "max_response_bytes": 1024 * 1024},
            "catalog_retry": deepcopy(retry), "stage1_retry": deepcopy(retry), "hole_retry": deepcopy(retry),
        },
        "render": {
            "options": {"canvas": {"width": CANVAS_BASE_PX, "height": CANVAS_BASE_PX}, "svg_profile": "display"},
            "clip": {"tolerance_pixels": 0.1, "max_nodes": "50000", "max_path_elements": "200000",
                     "max_flattened_points": "200000", "max_work": "10000000", "max_output_vertices": "200000"},
        },
        "provider": {"stage1_model": "nvidia:google/gemma-4-31b-it", "stage2_model": "nvidia:google/gemma-4-31b-it",
                     "max_tokens": 2048, "stage1_max_tokens": 1024},
        "host_limits": {"max_workers": 4, "max_effect_steps": 32, "max_retained_runs": 8},
    }
