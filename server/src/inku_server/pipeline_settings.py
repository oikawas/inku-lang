"""Trusted host selections and legacy settings aliases.

The manifest supplies explicit policies, catalogs and locked definitions. This
adapter selects them and preserves saved budgets; only Rust interprets DDL.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Callable

from .limits import normalize_limits
from .pipeline_candidate import CandidateHostError, PipelineBinding


def select_canvas(config: dict, registry: dict | None, format_id: str) -> dict:
    if registry is None:
        raise CandidateHostError("binding_canvas_registry_unavailable")
    if format_id not in {item["id"] for item in registry["registry"]["formats"]}:
        raise CandidateHostError("unknown_canvas_format")
    selected = deepcopy(config)
    hosts = [selected["compiler"]["host"], *(entry["resolved"] for entry in selected["catalogs"])]
    for host in hosts:
        host.update(canvas_format_id=format_id,
                    canvas_format_registry_id=registry["registry"]["schema"],
                    canvas_format_registry_digest=registry["digest"])
    return selected


class PipelineSettings:
    def __init__(self, binding: PipelineBinding, manifest: dict, *,
                 admin_limits_for: Callable[[str], dict],
                 plugin_storage_for: Callable[[str], dict]):
        if manifest.get("schema") != "inku.pipeline-host.v1":
            raise CandidateHostError("pipeline_manifest_mismatch")
        self.binding, self.manifest = binding, deepcopy(manifest)
        self.admin_limits_for, self.plugin_storage_for = admin_limits_for, plugin_storage_for

    def config_for(self, owner: str, work: dict | None) -> dict:
        if work and "saved_config" in work:
            # A derived edition inherits the full saved policy/definition lock.
            return deepcopy(work["saved_config"])
        config = deepcopy(self.manifest["pipeline"])
        metadata = (work or {}).get("metadata", {})
        saved_limits = metadata.get("render_limits")
        if isinstance(saved_limits, str):
            saved_limits = json.loads(saved_limits)
        limits = normalize_limits(saved_limits if saved_limits is not None else self.admin_limits_for(owner))
        compiler = config["compiler"]
        # Only the four existing settings are translated. The six additional
        # structural dimensions must be supplied explicitly by the manifest.
        mapping = {
            "primitive_marks": "max_expanded_primitives",
            "maximum_per_template_primitive_marks": "max_expanded_per_instruction",
            "maximum_resolved_count": "schema_count_max",
            "object_templates": "max_instructions",
        }
        for budget in (compiler["hard_resource_policy"]["budget"], compiler["operational_resource_budget"]):
            maximum = budget["maximum"]
            for field in ("logical_objects", "template_nodes", "anchor_instances", "transform_instances", "placement_instances", "fill_instances"):
                if field not in maximum:
                    raise CandidateHostError("explicit_structural_budget_required")
            maximum.update({field: limits[setting] for field, setting in mapping.items()})
        policy_bytes = json.dumps(compiler["hard_resource_policy"]["budget"], sort_keys=True, separators=(",", ":")).encode()
        compiler["hard_resource_policy"]["identity"] = "host-settings:" + hashlib.sha256(policy_bytes).hexdigest()
        storage = self.plugin_storage_for(owner).get("canvas-aspect", {})
        selected = metadata.get("render_canvas_aspect_id") or metadata.get("render_canvas_aspect")
        if selected is None:
            selected = "square" if storage.get("enabled") is False else storage.get("selected", "square")
            registry = self.binding.canvas_registry
            if registry is not None and selected not in {entry["id"] for entry in registry["registry"]["formats"]}:
                selected = "square"
        return select_canvas(config, self.binding.canvas_registry, selected)

    def render_for(self, snapshot: dict) -> dict:
        render = deepcopy(self.manifest["render"])
        compiler = snapshot["delivery"]["compiler_options"]
        host = compiler["host"]
        options = render["options"]
        options["catalog_id"] = host["resolved_catalog_id"]
        if host["resolved_catalog_id"] in self.manifest.get("render_color_maps", {}):
            options["resolved_color_map"] = deepcopy(self.manifest["render_color_maps"][host["resolved_catalog_id"]])
        options["canvas_aspect_id"] = host["canvas_format_id"]
        options["composition_seed"] = compiler["composition_seed"]
        options["error_policy"] = compiler["error_policy"]
        registry = self.binding.canvas_registry
        if registry is None:
            raise CandidateHostError("binding_canvas_registry_unavailable")
        entry = next(item for item in registry["registry"]["formats"] if item["id"] == host["canvas_format_id"])
        height = options["canvas"]["height"]
        options["canvas"] = {"width": round(height * entry["width_units"] / entry["height_units"]), "height": height}
        return render
