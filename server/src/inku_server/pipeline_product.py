"""Server settings, provider and history effects for the shared pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
import uuid
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from .color_catalogs import color_catalogs, get_color_catalog, render_color_map_for_catalog
from .macro_catalog import explain_plugin_diagnostics, resolve_new_work_macro_catalog
from .pipeline_candidate import CandidateHostError, PipelineBinding, _bytes
from .pipeline_provider import ProviderOptions, SingleAttemptProvider, resolved_stage_model
from .pipeline_settings import PipelineSettings, select_canvas
from .persistence.variation_authority import VariationAuthorityStore
from .provider_observation import ProviderObservationStore


_logger = logging.getLogger(__name__)


def _apply_developer_options(config: dict, options: dict, *, developer_mode: bool) -> None:
    requested = any(options.get(name) is True for name in (
        "developer_disable_llm_retries", "developer_capture_provider_io",
    ))
    if requested and not developer_mode:
        raise CandidateHostError("developer_mode_required")
    if options.get("developer_disable_llm_retries") is True:
        for name in ("catalog_retry", "stage1_retry", "hole_retry"):
            config[name]["max_attempts"] = 1


def _safe_compiler_log_atom(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return None
    allowed = "_-:."
    return value if all(character.isascii() and (character.isalnum() or character in allowed) for character in value) else None


def _compiler_diagnostic_log_projection(channel: str, diagnostic: object) -> dict:
    if not isinstance(diagnostic, dict):
        return {"channel": channel, "kind": None, "issue_id": None, "actual_action": None}
    reason = diagnostic.get("reason")
    disposition = diagnostic.get("disposition")
    kind = diagnostic.get("issue_kind")
    if kind is None and isinstance(reason, dict):
        kind = reason.get("type", reason.get("kind"))
    return {
        "channel": channel,
        "kind": _safe_compiler_log_atom(kind),
        "issue_id": _safe_compiler_log_atom(diagnostic.get("issue_id")),
        "actual_action": _safe_compiler_log_atom(
            disposition.get("kind") if isinstance(disposition, dict) else None
        ),
    }


def _resource_omission_log_projection(diagnostic: object) -> dict:
    if not isinstance(diagnostic, dict):
        return {"channel": "resource_omissions", "kind": None, "issue_id": None, "actual_action": None}
    cause = diagnostic.get("cause")
    reason = cause.get("reason") if isinstance(cause, dict) else None
    kind = reason.get("kind") if isinstance(reason, dict) else None
    return {
        "channel": "resource_omissions",
        "kind": _safe_compiler_log_atom(kind),
        "issue_id": None,
        "actual_action": (
            "partially_executed"
            if isinstance(diagnostic.get("partial_execution"), dict)
            else "omitted"
        ),
    }


class ImportedPlugin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: dict
    summary: str = Field(default="", max_length=8192)


class RunOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage1_model: str | None = None
    stage2_model: str | None = None
    instruction_lang: Literal["auto", "ja", "en"] | None = None
    ui_lang: str | None = None
    catalog_id: str | None = None
    catalog_mode: Literal["fixed", "auto", "random"] | None = None
    canvas_aspect: str | None = None
    render_seed: int | str | None = None
    composition_seed: int | str | None = None
    wild: bool | None = None
    # The sketch before Stage 1: off (the default) or on, when the author asks
    # to draw with a sketch. A sketch text the author edited is used as it
    # stands, without a request.
    sketch: Literal["off", "on"] | None = None
    sketch_text: str | None = Field(default=None, max_length=100_000)
    variation_amplitude: Literal["small", "medium", "large"] | None = None
    variation_seed: int | str | None = None
    interpretation_seed: str | None = None
    seed_text: str | None = None
    history_display_label: str | None = None
    batch_line_number: int | None = None
    batch_run_id: str | None = None
    history_visibility: Literal["normal", "lineage_only"] | None = None
    lineage_parent_node_id: str | None = None
    derivation_kind: str | None = None
    derivation_metadata: dict = Field(default_factory=dict)
    count_generation: bool | None = None
    save_history: bool = True
    save_artifacts: bool | None = None
    history_input: str | None = None
    history_source_text: str | None = None
    history_at: int | None = None
    request_idempotency_key: str | None = Field(default=None, max_length=200)
    developer_disable_llm_retries: StrictBool | None = None
    developer_capture_provider_io: StrictBool | None = None
    # Plugin definitions carried by an imported DDL export. They are used for
    # this new work only and are never installed.
    imported_plugins: list[ImportedPlugin] | None = Field(default=None, max_length=64)
    # Render limits the caller asks this drawing to run under (ledger I-154).
    # They are bounded by today's settings and never kept as a host option.
    limits: dict[str, int] | None = None


def sketch_request_for(kind: str, options: dict) -> dict:
    """The sketch request of one operation. It is never inherited from a parent."""
    if kind != "description":
        return {"mode": "off"}
    text = (options.get("sketch_text") or "").strip()
    if text:
        return {"mode": "supplied", "text": text}
    return {"mode": options.get("sketch") or "off"}


def sketch_result(record: dict | None) -> dict:
    """Saved sketch columns from what the sketch did in this run."""
    if record is None:
        return {"sketch_text": None, "sketch_grain": None, "sketch_state": "off"}
    state = record.get("state")
    if state in {"supplemented", "supplied"} and record.get("text"):
        return {"sketch_text": record["text"], "sketch_grain": None, "sketch_state": "supplemented"}
    if state == "not_needed":
        return {"sketch_text": None, "sketch_grain": None, "sketch_state": "not_needed"}
    return {"sketch_text": None, "sketch_grain": None, "sketch_state": "fallback"}


# The provider actions whose system prompt the prompt tab shows, by the name
# the tab gives each stage.
_SYSTEM_PROMPT_STAGES = {"generate_normalized_ddl": "stage1", "complete_visible_ddl_holes": "stage2"}


def record_system_prompt(context: dict, action: dict) -> None:
    """Keep the system prompt this action sends, as it is sent.

    The last attempt of a stage replaces an earlier one, so a retry that
    carried compiler feedback is what the work shows. The record lives in the
    execution's saved context and is read only by its owner.
    """
    stage = _SYSTEM_PROMPT_STAGES.get(action["tag"])
    prompt = (action.get("payload") or {}).get("prompt")
    # A record for the reader: an action without a prompt draws as before.
    if stage is None or not isinstance(prompt, dict):
        return
    context.setdefault("system_prompts", {})[stage] = {
        "system": prompt["system"],
        "prompt_id": prompt["prompt_id"],
        "prompt_digest": prompt["prompt_digest"],
        "instruction_language": prompt["instruction_language"],
        "attempt": int(action["identity"]["attempt"]),
    }


class ProductPipelineEffects:
    def __init__(self, binding: PipelineBinding, manifest: dict):
        from . import db
        self.binding, self.manifest = binding, deepcopy(manifest)
        self.settings = PipelineSettings(binding, manifest,
                                         admin_limits_for=lambda owner: db.get_render_limit_settings(),
                                         plugin_storage_for=db.get_user_plugin_storage)

    def prepare(self, owner: str, kind: str, text: str, options: dict, work: dict | None) -> tuple[dict, dict]:
        from . import db
        from .api_core.common import _env_flag, _model_offered_to, _resolve_instruction_lang
        from .api_core.rendering import _render_seed_from_text

        try:
            options = RunOptions.model_validate(options).model_dump(exclude_unset=True)
        except ValidationError as error:
            raise CandidateHostError("invalid_authoring_options") from error
        requested_limits = options.pop("limits", None)
        previous = deepcopy((work or {}).get("host_options", {}))
        metadata = (work or {}).get("metadata", {})
        for name in ("stage1_model", "stage2_model", "catalog_id", "catalog_mode", "composition_seed", "render_seed",
                     "instruction_lang_requested", "ui_lang"):
            if metadata.get(name) is not None:
                previous["instruction_lang" if name == "instruction_lang_requested" else name] = metadata[name]
        if metadata.get("render_wild") is not None:
            previous["wild"] = str(metadata["render_wild"]).lower() in {"true", "1"}
        imported_plugins = options.pop("imported_plugins", None)
        if imported_plugins and work and "saved_config" in work:
            raise CandidateHostError("imported_plugins_require_new_work")
        selected = {**previous, **options}
        # Request save metadata belongs to this operation, not to its parent.
        for key in ("request_idempotency_key", "history_at", "history_input", "history_source_text"):
            if key not in options:
                selected.pop(key, None)
        if "lineage_parent_node_id" not in options and (work or {}).get("result", {}).get("lineage_node_id"):
            selected["lineage_parent_node_id"] = work["result"]["lineage_node_id"]
        config = self.settings.config_for(owner, work, requested_limits)
        _apply_developer_options(config, options, developer_mode=_env_flag("INKU_DEVELOPER_MODE"))
        language = _resolve_instruction_lang(text, selected.get("instruction_lang") or "auto", ui_lang=selected.get("ui_lang"))
        config["language"] = language
        if work and "saved_config" in work:
            catalog_context = deepcopy(work.get("macro_catalog", {}))
        else:
            catalog = resolve_new_work_macro_catalog(self.binding, config, imported_plugins or ())
            config["definitions"] = catalog["definitions"]
            config["macro_summaries"] = catalog["macro_summaries"]
            catalog_context = {"definition_locks": catalog["definition_locks"],
                               "diagnostics": catalog["diagnostics"]}
        if selected.get("canvas_aspect") is not None:
            config = select_canvas(config, self.binding.canvas_registry, selected["canvas_aspect"])
        seed, seed_text = _render_seed_from_text(selected.get("seed_text"), selected.get("render_seed"))
        seed = secrets.randbits(63) if seed is None else int(seed)
        composition_seed = selected.get("composition_seed")
        config["compiler"]["composition_seed"] = None if composition_seed is None else str(int(composition_seed))
        # Stage 1.5 variation applies only when this operation explicitly asks
        # for it; deriving a work does not inherit a previous variation request.
        amplitude, variation_seed = options.get("variation_amplitude"), options.get("variation_seed")
        config["compiler"]["stage15_variation"] = None
        if (amplitude is None) != (variation_seed is None):
            raise CandidateHostError("variation_pair_required")
        if amplitude is not None:
            config["compiler"]["stage15_variation"] = {"amplitude": amplitude, "seed": str(int(variation_seed))}
        catalogs = color_catalogs()
        catalog_id = selected.get("catalog_id") or config["compiler"]["host"]["resolved_catalog_id"]
        mode = selected.get("catalog_mode") or "fixed"
        if mode == "random":
            catalog_id = secrets.choice([entry["id"] for entry in catalogs if entry["id"] != catalog_id])
        if get_color_catalog(catalog_id) is None:
            raise CandidateHostError("unknown_color_catalog")
        template_host = config["compiler"]["host"]
        resolved = {}
        color_maps = {}
        if self.binding.resolve_palette is None:
            raise CandidateHostError("binding_palette_unavailable")
        for catalog in catalogs:
            identity = catalog["id"]
            color_map = render_color_map_for_catalog(identity)
            color_maps[identity] = color_map
            palette = json.loads(self.binding.resolve_palette(_bytes({
                "color_map": color_map, "catalog_id": identity, "render_seed": str(seed),
                "background": template_host["background"],
            })))
            if "error" in palette:
                raise CandidateHostError(palette["error"])
            resolved[identity] = {**template_host, "resolved_catalog_id": identity, "catalog_mode": "explicit", "palette": palette}
        config["compiler"]["host"] = resolved[catalog_id]
        if catalog_id == "default":
            config["compiler"]["host"]["catalog_mode"] = "default"
        config["catalogs"] = [{"prompt": {"catalog_id": entry["id"], "label": entry["name"],
                                          "description": entry["sub_ja" if language == "ja" else "sub"]},
                               "resolved": resolved[entry["id"]]} for entry in catalogs] if mode == "auto" else []
        actor = db.get_user(owner)
        selected.update(
            stage1_model=resolved_stage_model(selected.get("stage1_model"), actor, stage="stage1"),
            stage2_model=resolved_stage_model(selected.get("stage2_model"), actor, stage="stage2"),
            render_seed=str(seed), seed_text=seed_text, catalog_mode=mode,
            instruction_lang=selected.get("instruction_lang") or "auto",
            instruction_lang_resolved=language, catalog_id=catalog_id,
        )
        # Refused before anything runs rather than when the stage calls out. A
        # description is read by Stage 1; hand-written DDL reaches only Stage 2,
        # which completes its holes.
        model_settings = db.get_model_settings()
        for stage in ("stage1", "stage2") if kind == "description" else ("stage2",):
            if not _model_offered_to(
                actor, selected[f"{stage}_model"], stage=stage, purpose="llm", settings=model_settings
            ):
                raise CandidateHostError("model_not_offered")
        selected["developer_disable_llm_retries"] = options.get("developer_disable_llm_retries") is True
        selected["developer_capture_provider_io"] = options.get("developer_capture_provider_io") is True
        # Present from the start, so a work whose stage never called a model
        # reads as "not sent" and one drawn before the record as "not recorded".
        return config, {"host_options": selected, "color_maps": color_maps, "macro_catalog": catalog_context,
                        "system_prompts": {},
                        "render_limits_source": self.settings.limits_source(work, requested_limits),
                        "auto_catalog": kind == "description" and mode == "auto",
                        "sketch_request": sketch_request_for(kind, options), "metrics": {}}

    def provider_for(self, owner: str, context: dict):
        from . import db
        from .api_core.state import _increment_stage_stat
        options = context.get("host_options", {})
        configured = self.manifest["provider"]
        def perform(action):
            stage = "stage2" if action["tag"] == "complete_visible_ddl_holes" else "stage1"
            transport = SingleAttemptProvider(ProviderOptions(
                settings=db.get_model_settings(), stage1_model=options.get("stage1_model", configured["stage1_model"]),
                stage2_model=options.get("stage2_model", configured["stage2_model"]),
                max_tokens=configured.get("stage1_max_tokens", configured["max_tokens"]) if stage == "stage1" else configured["max_tokens"],
                max_response_bytes=self.manifest["pipeline"]["prompt_limits"]["max_response_bytes"],
            ), observation=(
                ProviderObservationStore(
                    db.engine,
                    limit=max(16 * 1024 * 1024, self.manifest["pipeline"]["prompt_limits"]["max_response_bytes"]),
                ),
                owner,
                context["execution_id"],
            ) if options.get("developer_capture_provider_io") is True else None)
            record_system_prompt(context, action)
            _increment_stage_stat("submitted")
            result = transport(action)
            if result["tag"] != "provider_failed":
                _increment_stage_stat("completed")
            elif result["failure"] == "transport_timeout":
                _increment_stage_stat("timed_out")
            else:
                _increment_stage_stat("failed")
            metrics = context.setdefault("metrics", {})
            metrics[stage] = metrics.get(stage, 0) + int(result["elapsed_ms"])
            if result["tag"] == "provider_failed":
                context["provider_failure"] = {
                    "failure": result["failure"],
                    "stage": stage,
                    "attempt": int(action["identity"]["attempt"]),
                    "elapsed_ms": int(result["elapsed_ms"]),
                }
                detail = getattr(transport, "failure_detail", None)
                if result["failure"] == "provider_rejected" and detail in {"credentials_unavailable", "observation_incomplete"}:
                    context["provider_failure"]["detail"] = detail
            else:
                context.pop("provider_failure", None)
            return result
        return perform

    def provider_observations(self, owner: str, execution_id: str) -> list[dict]:
        from . import db
        return ProviderObservationStore(db.engine, limit=16 * 1024 * 1024).read_execution(owner, execution_id)

    def render_options(self, snapshot: dict, context: dict, command: dict) -> dict:
        if set(command) != {"tag"}:
            raise CandidateHostError("unsupported_performance_option")
        if snapshot.get("delivery") is None or snapshot["delivery"].get("score") is None:
            raise CandidateHostError("score_not_ready")
        render = self.settings.render_for(snapshot)
        host = snapshot["delivery"]["compiler_options"]["host"]
        options = context["host_options"]
        render["options"]["resolved_color_map"] = context["color_maps"][host["resolved_catalog_id"]]
        render["options"]["render_seed"] = options["render_seed"]
        render["options"]["wild"] = options.get("wild") is True
        context["performance_options"] = deepcopy(render["options"])
        return render

    def save_result(self, owner: str, snapshot: dict, context: dict, rendered: dict) -> dict:
        from . import db
        from .api_core.common import _build_number
        from .api_core.rendering import _output_prefix, _submit_history_artifact_save, _SRGB_COLOR_PROFILE
        from .api_core.thumbnails import submit_thumbnail_build
        from .layer_versions import DDL_ENGINE_VERSION, DDL_VERSION

        score = snapshot["delivery"]["score"]
        document = snapshot["document"]
        settings = context["host_options"]
        performance = context["performance_options"]
        compiler = snapshot["delivery"]["compiler_options"]
        catalog_id = compiler["host"]["resolved_catalog_id"]
        catalog = get_color_catalog(catalog_id)
        metrics = context.get("metrics", {})
        render_metadata = rendered["metadata"]
        registry = self.binding.canvas_registry
        canvas = next(entry for entry in registry["registry"]["formats"] if entry["id"] == performance["canvas_aspect_id"])
        maxima = compiler["operational_resource_budget"]["maximum"]
        limits = {"max_expanded_primitives": maxima["primitive_marks"],
                  "max_expanded_per_instruction": maxima["maximum_per_template_primitive_marks"],
                  "schema_count_max": maxima["maximum_resolved_count"], "max_instructions": maxima["object_templates"]}
        result = {
            "description": context["committed_description"], "ddl": document["source"], "source_ddl": document["source"],
            "score": score, "svg": rendered["svg"], "stage1_model": settings["stage1_model"], "stage2_model": settings["stage2_model"],
            "elapsed_stage1_ms": metrics.get("stage1", 0), "elapsed_stage2_ms": metrics.get("stage2", 0),
            "elapsed_total_ms": sum(metrics.values()), "tokens_in_stage1": None, "tokens_out_stage1": None,
            "tokens_in_stage2": None, "tokens_out_stage2": None, "thinking": None,
            **sketch_result(snapshot.get("sketch")),
            "ddl_version": DDL_VERSION, "ddl_engine_version": DDL_ENGINE_VERSION,
            "render_build_number": _build_number(), "render_engine_id": render_metadata["render_engine_id"],
            "render_engine_version": render_metadata["render_engine_version"], "catalog_id": catalog_id,
            "render_color_catalog_id": catalog_id, "render_color_catalog_name": catalog["name"],
            "render_color_catalog_sub": catalog["sub"], "render_color_map": performance["resolved_color_map"],
            "render_color_profile": dict(_SRGB_COLOR_PROFILE),
            "render_canvas_aspect": canvas["id"], "render_canvas_aspect_id": canvas["id"],
            "render_canvas_aspect_ratio": canvas["width_units"] / canvas["height_units"],
            "render_seed": int(settings["render_seed"]), "render_wild": performance["wild"],
            "composition_seed": None if compiler["composition_seed"] is None else int(compiler["composition_seed"]),
            "instruction_lang_requested": settings["instruction_lang"], "instruction_lang_resolved": settings["instruction_lang_resolved"],
            "ui_lang": settings.get("ui_lang"), "render_limits": limits,
            "render_limits_source": context.get("render_limits_source"),
            "pipeline_variation_id": snapshot["variation_id"], "pipeline_revision": snapshot["authority"]["revision"],
        }
        result["render_hash"] = db.render_hash_for_item({**result, "input": result["description"]})
        result["render_hash_short"] = db.render_hash_short(result["render_hash"])
        result["render_diagnostics"] = render_metadata.get("execution")
        result["resource_execution"] = render_metadata.get("resource_execution")
        pipeline_diagnostics = {
            "upstream_diagnostics": snapshot["delivery"]["upstream_diagnostics"],
            "downstream_diagnostics": snapshot["delivery"]["downstream_diagnostics"],
            "resource_omissions": snapshot["delivery"]["resource_omissions"],
            "relation_omissions": snapshot["delivery"]["relation_omissions"],
            "render_diagnostics": result["render_diagnostics"],
            "resource_execution": result["resource_execution"],
        }
        work_plugins = [
            f"{item['namespace']}.{heading}"
            for item in (snapshot.get("config") or {}).get("definitions") or []
            if isinstance(item, dict) and isinstance(item.get("namespace"), str) and isinstance(item.get("heading"), str)
            for heading in (item["heading"], *[alias for alias in item.get("aliases") or [] if isinstance(alias, str)])
        ]
        pipeline_diagnostics["plugin_diagnostics"] = explain_plugin_diagnostics(
            self.binding, document["source"], pipeline_diagnostics["upstream_diagnostics"], work_plugins
        )
        result["compiler_outcome"] = snapshot["delivery"]["outcome"]
        result["pipeline_diagnostics"] = pipeline_diagnostics
        compiler_channels = ("upstream_diagnostics", "downstream_diagnostics")
        _logger.info(
            "pipeline_compiler_outcome %s",
            json.dumps(
                {
                    "execution_id": snapshot["execution_id"],
                    "variation_id": snapshot["variation_id"],
                    "revision": snapshot["authority"]["revision"],
                    "source_digest": snapshot["delivery"]["source_digest"],
                    "compiler_outcome": result["compiler_outcome"],
                    "diagnostic_counts": {
                        key: len(pipeline_diagnostics[key])
                        for key in (
                            "upstream_diagnostics",
                            "downstream_diagnostics",
                            "resource_omissions",
                            "relation_omissions",
                        )
                    },
                    "diagnostics": [
                        _compiler_diagnostic_log_projection(channel, diagnostic)
                        for channel in compiler_channels
                        for diagnostic in pipeline_diagnostics[channel]
                    ] + [
                        _resource_omission_log_projection(diagnostic)
                        for diagnostic in pipeline_diagnostics["resource_omissions"]
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        if settings.get("save_history") is False:
            if settings.get("count_generation") is not False:
                result["user_generation_count"] = db.increment_user_generation_count(owner)
            return result
        idempotency = settings.get("request_idempotency_key") or "pipeline:" + hashlib.sha256(_bytes({
            "variation": snapshot["variation_id"], "revision": snapshot["authority"]["revision"], "render": result["render_hash"],
        })).hexdigest()
        at = settings.get("history_at")
        if at is None:
            at = int(time.time() * 1000)
        item_id = str(uuid.uuid4())
        parent = settings.get("lineage_parent_node_id")
        if parent is None and context.get("parent_legacy_history_id"):
            items = db.get_items(owner, [context["parent_legacy_history_id"]])
            parent = items[0].get("lineage_node_id") if items else None
        item = db.add_item({
            **result, "id": item_id, "user_id": owner, "at": at,
            "input": settings.get("history_input") if settings.get("history_input") is not None else result["description"],
            "output_path": str(_output_prefix(owner, item_id, at)),
            "source_text": settings.get("history_source_text") if settings.get("history_source_text") is not None else result["description"],
            "elapsed_ms": result["elapsed_total_ms"], "idempotency_key": idempotency,
            "catalog_mode": settings["catalog_mode"], "display_label": settings.get("history_display_label"),
            "batch_line_number": settings.get("batch_line_number"), "batch_run_id": settings.get("batch_run_id"),
            "history_visibility": settings.get("history_visibility") or "normal", "lineage_parent_node_id": parent,
            "derivation_kind": (settings.get("derivation_kind") or ("ddl_edit" if context.get("derivation_kind") in {"legacy_ddl_fork", "variation_ddl_fork"} else "description_edit")) if parent else None,
            "derivation_metadata": settings.get("derivation_metadata", {}),
        })
        store = VariationAuthorityStore(db.engine)
        if item.get("_idempotent_replay"):
            link = store.history_link(owner, item["id"])
            if link is None or link["variation_id"] != snapshot["variation_id"] or link["revision"] != snapshot["authority"]["revision"]:
                raise CandidateHostError("idempotency_conflict")
        store.link_history(owner, item["id"], snapshot["variation_id"],
                           snapshot["authority"]["revision"], snapshot["delivery"]["source_digest"],
                           snapshot=snapshot, context=context,
                           pipeline_diagnostics=pipeline_diagnostics)
        result.update({"history_id": item["id"], "history_at": item["at"],
                       **{key: item.get(key) for key in ("lineage_node_id", "lineage_parent_node_id", "derivation_kind", "description_hash")}})
        if not item.get("_idempotent_replay"):
            if settings.get("save_artifacts") is not False:
                _submit_history_artifact_save(item)
                submit_thumbnail_build(item)
            if settings.get("count_generation") is not False:
                result["user_generation_count"] = db.increment_user_generation_count(owner)
        return result

    def replay(self, owner: str, request: dict, work: dict | None) -> dict:
        """Perform raw compact Score; the route has already authorized work access."""
        from . import db
        from .api_core.common import _build_number
        from .api_core.rendering import _limits_for_render, _render_seed_from_text, _SRGB_COLOR_PROFILE
        from .api_core.state import _render_capacity
        from .layer_versions import DDL_ENGINE_VERSION, DDL_VERSION
        from .limits import LIMIT_FIELD_NAMES

        if self.binding.render_saved is None:
            raise CandidateHostError("binding_saved_performance_unavailable")
        # Only a server-owned history link attests a stored policy. Arbitrary
        # request Score and manually imported history cannot grant themselves
        # a larger resource budget.
        if work and work.get("pipeline_variation_id"):
            policy = deepcopy(work["score"]["resource_policy"])
        else:
            compiler = self.settings.config_for(owner, None)["compiler"]
            policy = {"hard_policy": compiler["hard_resource_policy"],
                      "operational_budget": compiler["operational_resource_budget"]}
        limits, limits_source = _limits_for_render(work, request.get("limits"))
        four_limits = {name: getattr(limits, name) for name in LIMIT_FIELD_NAMES}
        mapping = {"primitive_marks": "max_expanded_primitives",
                   "maximum_per_template_primitive_marks": "max_expanded_per_instruction",
                   "maximum_resolved_count": "schema_count_max", "object_templates": "max_instructions"}
        maximum = policy["operational_budget"]["maximum"]
        maximum.update({field: four_limits[name] for field, name in mapping.items()})
        score = request["score"]
        canvas = score.get("canvas", "square")
        canvas = canvas.get("aspect", "square") if isinstance(canvas, dict) else canvas
        canvas = request.get("canvas_aspect") or (work or {}).get("render_canvas_aspect_id") or canvas
        registry = self.binding.canvas_registry
        entry = next((entry for entry in registry["registry"]["formats"] if entry["id"] == canvas), None)
        if entry is None:
            raise CandidateHostError("unknown_canvas_format")
        snapshot_colors = (work or {}).get("render_color_map")
        catalog_id = ((work or {}).get("render_color_catalog_id") or (work or {}).get("catalog_id")) if snapshot_colors else request.get("catalog_id")
        catalog_id = catalog_id or "default"
        catalog = get_color_catalog(catalog_id)
        if not snapshot_colors and catalog is None:
            raise CandidateHostError("unknown_color_catalog")
        colors = deepcopy(snapshot_colors) if snapshot_colors else render_color_map_for_catalog(catalog_id)
        seed, seed_text = _render_seed_from_text(request.get("seed_text"), request.get("render_seed"))
        seed = secrets.randbits(63) if seed is None else seed
        composition_seed = request.get("composition_seed")
        options = deepcopy(self.manifest["render"]["options"])
        height = options["canvas"]["height"]
        options.update(resolved_color_map=colors, catalog_id=catalog_id,
                       canvas={"width": round(height * entry["width_units"] / entry["height_units"]), "height": height},
                       canvas_aspect_id=canvas, render_seed=seed, composition_seed=composition_seed,
                       wild=request.get("wild", False), svg_profile=request.get("svg_profile", "display"),
                       error_policy="omit_and_continue")
        payload = {"request": {"score": score, "options": options}, "hard_policy": policy["hard_policy"],
                   "operational_budget": policy["operational_budget"], "clip": self.manifest["render"]["clip"]}
        with _render_capacity():
            rendered = json.loads(self.binding.render_saved(_bytes(payload)))
        if "error" in rendered:
            raise CandidateHostError(rendered["error"])
        metadata = rendered["metadata"]
        result = {"score": score, "svg": rendered["svg"], "catalog_id": catalog_id,
                  "ddl_version": DDL_VERSION, "ddl_engine_version": DDL_ENGINE_VERSION,
                  "render_build_number": _build_number(), "render_color_profile": dict(_SRGB_COLOR_PROFILE),
                  "render_engine_id": metadata["render_engine_id"], "render_engine_version": metadata["render_engine_version"],
                  "render_color_catalog_id": catalog_id,
                  "render_color_catalog_name": (work or {}).get("render_color_catalog_name") or (catalog or {}).get("name", catalog_id),
                  "render_color_catalog_sub": (work or {}).get("render_color_catalog_sub") or (catalog or {}).get("sub", ""),
                  "render_color_map": colors, "render_color_source": "snapshot" if snapshot_colors else "catalog",
                  "render_canvas_aspect": canvas, "render_canvas_aspect_id": canvas,
                  "render_canvas_aspect_ratio": entry["width_units"] / entry["height_units"],
                  "render_seed": seed, "composition_seed": composition_seed, "render_wild": options["wild"],
                  "seed_text": seed_text, "render_limits": four_limits, "render_limits_source": limits_source,
                  "render_diagnostics": metadata.get("execution"), "resource_execution": metadata.get("resource_execution")}
        result["render_hash"] = db.render_hash_for_item(result)
        result["render_hash_short"] = db.render_hash_short(result["render_hash"])
        return result
