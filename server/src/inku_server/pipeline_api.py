"""Authoring API for the shared Rust pipeline and its durable host state."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from typing import Callable, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .description_labels import pipeline_description, source_labels
from .pipeline_candidate import CandidateExecution, CandidateHostError, PipelineBinding
from .pipeline_settings import select_canvas
from .persistence.variation_authority import (
    LAWS_RECORD_KEYS,
    ExecutionSnapshotConflict,
    VariationAuthorityAdapterError,
)


_RECORD_OPTIONS = frozenset({
    "history_display_label", "batch_line_number", "batch_run_id", "history_visibility",
    "lineage_parent_node_id", "derivation_kind", "derivation_metadata", "count_generation",
    "save_history", "save_artifacts", "history_input", "history_source_text", "history_at",
    "request_idempotency_key",
})

_LABEL_ONLY_DESCRIPTION = "description is only labels"
# How far a description fork walks up past variations stopped before their
# first save to find the parent it names (2026-10-13).
_UNSAVED_PARENT_STEPS = 8


_logger = logging.getLogger(__name__)


def _drawn_description(text: str) -> str:
    """The description every model stage reads: the author's labels cut away.

    The work keeps the text as written; only what reaches the shared core loses
    its leading numbers and bracketed comments. A description that was nothing
    but labels would hand the core an empty prompt, so it is refused here.
    """
    drawn = pipeline_description(text)
    if text.strip() and not drawn.strip():
        raise HTTPException(400, _LABEL_ONLY_DESCRIPTION)
    return drawn


DESCRIPTION_LOCKED = {
    "code": "description_locked",
    "message": "This work is held by its edited DDL. Start a new variation from its description as it stands, then change the words there.",
}


def _rewords(text: str, description: str) -> bool:
    """Whether the words read differ, labels and spacing aside (the stored
    description may keep the labels the page strips before showing it)."""
    def read(value: str) -> str:
        return " ".join(pipeline_description(str(value)).split())
    return read(text) != read(description)


def _route_fields(context: dict, text: str) -> dict:
    """What a description run adds for read and draw (SPEC §12.6.7): the route
    and the labels' words, which only the reading reads. The stages add nothing,
    so their request is the one they always sent."""
    if context.get("host_options", {}).get("route") != "read_and_draw":
        return {}
    return {"route": "read_and_draw", "source_labels": source_labels(text)}


def _refuse_if_locked(history_id: str) -> None:
    from . import db

    if db.history_description_locked(history_id):
        raise HTTPException(409, DESCRIPTION_LOCKED)


class NewVariationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["description", "direct_ddl", "image"] = Field(
        description="What the work starts from: description (the author's description), direct_ddl (DDL source written by the author), or image (a prepared image, which needs image_id).",
    )
    text: str = Field(
        description="For description, the description text. For direct_ddl, the DDL source. For image, the source note kept with the work; it is not drawn.",
    )
    image_id: str | None = Field(
        default=None,
        description="ID returned by POST /api/pipeline/images. Required when kind is image and refused when kind is anything else.",
    )
    canvas_format_id: str | None = Field(
        default=None,
        description="ID of the canvas format to draw on, from GET /api/pipeline/canvas-formats. Give it or canvas_aspect, not both with different values (refused with 422).",
    )
    canvas_aspect: str | None = Field(
        default=None,
        description="Canvas aspect to draw on, as an alternative to canvas_format_id. The value image picks the registered format nearest the prepared image's aspect ratio.",
    )
    options: dict = Field(
        default={},
        description="Run options for the work (for example stage1_model, catalog_id, render_seed, wild and sketch). Keys left out take the account's settings. Unknown or invalid keys are refused with 422.",
    )

    @model_validator(mode="after")
    def image_only(self):
        if (self.kind == "image") != bool(self.image_id):
            raise ValueError("an image run requires its prepared image only")
        return self


class ForkDescriptionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(
        description="Authority revision of the variation the caller last read. A different saved revision is refused with 409 (authority_conflict).",
    )
    description: str = Field(
        description="The description the new work starts from. It may differ from the variation's description; words changed on a variation whose DDL holds the work are refused with 409 (description_locked).",
    )
    options: dict = Field(
        default={},
        description="Run options for the new work, with the same keys as the options of POST /api/pipeline/variations. Keys left out take the account's settings.",
    )


class LinkedHistoryForkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["description", "direct_ddl"] = Field(
        description="What the fork starts from: description (a new description) or direct_ddl (a new DDL source).",
    )
    text: str = Field(
        description="The new description when kind is description, or the new DDL source when kind is direct_ddl. Changed words of a description are refused with 409 (description_locked) when the saved work's DDL holds it.",
    )
    options: dict = Field(
        default={},
        description="Run options for the new work, with the same keys as the options of POST /api/pipeline/variations. Keys left out take the account's settings.",
    )


class CompletionRangeStatesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(description="DDL source whose completion range states are read.")
    history_id: str | None = Field(
        default=None,
        description="ID of a saved work whose completion ranges are read. Give exactly one of history_id and execution_id.",
    )
    execution_id: str | None = Field(
        default=None,
        description="ID of an execution whose completion ranges are read. Give exactly one of history_id and execution_id.",
    )

    @model_validator(mode="after")
    def one_work(self):
        if bool(self.history_id) == bool(self.execution_id):
            raise ValueError("choose one saved work or execution")
        return self


class AuthorDdlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(
        description="Authority revision of the execution the caller last read. A different saved revision is refused with 409 (authority_conflict).",
    )
    source: str = Field(description="The edited DDL source to commit.")
    options: dict = Field(
        default={},
        description="Run options for the edited DDL, with the same keys as the options of POST /api/pipeline/variations. When they leave the run's settings unchanged, the source is committed to the same variation; otherwise a new direct-DDL variation is started.",
    )


class PreparedImageView(BaseModel):
    image_id: str = Field(description="ID to pass as image_id when starting an image variation. It stays valid for 15 minutes.")
    thumbnail: str = Field(description="JPEG thumbnail as a data URL, fitting within 256 by 256 pixels.")
    original_width: int = Field(description="Width of the uploaded image in pixels, after its EXIF orientation is applied.")
    original_height: int = Field(description="Height of the uploaded image in pixels, after its EXIF orientation is applied.")
    width: int = Field(description="Width in pixels of the image as sent to the model, after the core's size limit for model input is applied.")
    height: int = Field(description="Height in pixels of the image as sent to the model, after the core's size limit for model input is applied.")
    nearest_format_id: str = Field(description="ID of the registered canvas format whose aspect ratio is nearest the image's.")


class PipelineService:
    """One server worker; persisted snapshots survive worker replacement.

    config_for supplies trusted resolved options, including explicit budgets.
    provider_for supplies credentials/transport outside the Rust snapshot.
    These callbacks never receive an untrusted client policy or snapshot.
    """

    def __init__(
        self, binding: PipelineBinding, store, *,
        config_for: Callable[[str, dict | None], dict],
        provider_for: Callable[[str], Callable[[dict], dict]],
        render_for: Callable[[dict], dict] | None,
        max_workers: int, max_effect_steps: int, max_retained_runs: int,
        auto_catalog: bool = False,
        prepare_for: Callable[[str, str, str, dict, dict | None], tuple[dict, dict]] | None = None,
        provider_with_context: Callable[[str, dict], Callable[[dict], dict]] | None = None,
        render_with_context: Callable[[dict, dict, dict], dict] | None = None,
        project_result: Callable[[str, dict, dict, dict], dict] | None = None,
        replay_for: Callable[[str, dict, dict | None], dict] | None = None,
        provider_observations: Callable[[str, str], list[dict]] | None = None,
        reading_config_for: Callable[[str, str, dict | None], dict] | None = None,
        image_provider_with_context: Callable[[str, dict, list[str]], Callable[[dict], dict]] | None = None,
        image_review_options: Callable[[dict, dict], dict] | None = None,
    ):
        if max_workers <= 0 or max_effect_steps <= 0 or max_retained_runs < max_workers:
            raise ValueError("explicit positive pipeline host limits required")
        self.binding, self.store = binding, store
        self.config_for, self.provider_for, self.render_for = config_for, provider_for, render_for
        self.max_workers = max_workers
        self.max_effect_steps = max_effect_steps
        self.max_retained_runs = max_retained_runs
        self.auto_catalog = auto_catalog
        self.prepare_for, self.provider_with_context = prepare_for, provider_with_context
        self.render_with_context, self.project_result = render_with_context, project_result
        self.replay_for = replay_for
        self.provider_observations = provider_observations
        self.reading_config_for = reading_config_for
        self.image_provider_with_context = image_provider_with_context
        self.image_review_options = image_review_options
        from .pipeline_images import PendingImages
        self._images = PendingImages(max_retained_runs)
        self._runs: dict[tuple[str, str], CandidateExecution] = {}
        self._jobs: dict[tuple[str, str], Future] = {}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="inku-pipeline")

    def close(self) -> None:
        from .chatgpt_runtime import stop
        stop()
        with self._lock:
            for run in self._runs.values():
                if run.view()["busy"]:
                    run.command({"tag": "cancel"})
        self._pool.shutdown(wait=True, cancel_futures=True)
        self._images.clear()
        for run in self._runs.values():
            run.image_data.clear()

    def _host(self, owner: str, config: dict, context: dict) -> CandidateExecution:
        def provider(action):
            if action["tag"] == "draw_image_review":
                return self._image_review(run, action)
            references = (action.get("payload", {}).get("prompt") or {}).get("images") or []
            if references:
                try:
                    images = [run.image_data[reference["sha256"]] for reference in references]
                except KeyError:
                    self._stop_missing_image(run)
                    return None
                if self.image_provider_with_context is not None:
                    return self.image_provider_with_context(owner, run.context, images)(action)
            transport = self.provider_with_context(owner, run.context) if self.provider_with_context else self.provider_for(owner)
            return transport(action)

        def save(previous, snapshot, host_context, rendered):
            if rendered is None:
                host_context.pop("result", None)
                host_context.pop("render_digest", None)
            elif self.project_result is not None:
                projection = rendered
                if snapshot.get("completion_ranges") is not None:
                    projection = {"rendered": rendered, "completion_ranges": snapshot["completion_ranges"]}
                digest = hashlib.sha256(json.dumps(projection, sort_keys=True).encode()).hexdigest()
                if digest != host_context.get("render_digest"):
                    host_context["result"] = self.project_result(owner, snapshot, host_context, rendered)
                    host_context["render_digest"] = digest
            state_bytes = json.dumps(
                {"snapshot": snapshot, "context": host_context, "rendered": rendered},
                ensure_ascii=False, allow_nan=False, separators=(",", ":"),
            ).encode()
            if previous is None:
                self.store.create_execution(owner, snapshot["execution_id"], snapshot["variation_id"], snapshot["sequence"], state_bytes)
            else:
                self.store.compare_and_set_execution(
                    owner, snapshot["execution_id"], expected_sequence=previous["sequence"],
                    next_sequence=snapshot["sequence"], state_bytes=state_bytes,
                )
        run = CandidateExecution(
            self.binding, self.store, owner_id=owner, config=config,
            provider=provider,
            allow_render=self.render_for is not None or self.render_with_context is not None,
            context=context, save_snapshot=save,
            on_render_refusal=lambda snapshot, detail: self.store.record_render_refusal(
                owner, snapshot["execution_id"], expected_sequence=snapshot["sequence"], detail=detail,
            ),
        )
        return run

    def prepare_image(self, owner: str, raw: bytes) -> dict:
        from .pipeline_images import prepare_image
        return self._images.add(owner, prepare_image(self.binding, raw))

    @staticmethod
    def _stop_missing_image(run: CandidateExecution) -> None:
        run.command({"tag": "cancel"}, context_updates={"image_failure": {
            "code": "image_missing", "message": "The worker no longer has the image. Select it again.",
        }})
        run.image_data.clear()

    def _image_review(self, run: CandidateExecution, action: dict) -> dict:
        from .pipeline_images import review_drawing
        result = {"tag": "image_review_undrawn", "identity": action["identity"]}
        if self.image_review_options is None:
            return result
        try:
            snapshot = run.snapshot()
            drawing = review_drawing(self.binding, snapshot, self.image_review_options(snapshot, run.context), owner=run.owner_id)
            if drawing is not None:
                reference, data_url = drawing
                run.image_data[reference["sha256"]] = data_url
                return {"tag": "image_review_drawn", "identity": action["identity"], "drawing": reference}
        except Exception:
            # Neither an SVG nor an input image can enter this diagnostic.
            _logger.warning("pipeline_image_review_undrawn execution_id=%s", run.view()["execution_id"])
        return result

    def start(self, owner: str, kind: str, text: str, *, parent: dict | None = None, source_work: dict | None = None,
              canvas_format_id: str | None = None, canvas_aspect: str | None = None,
              options: dict | None = None, prepared: tuple[dict, dict] | None = None,
              direction: dict | None = None, image_id: str | None = None) -> dict:
        """Start from a description, direct DDL, transient image, or `saved_laws`:
        the laws stage again on a saved work's DDL (`text`), with the records
        `source_work` keeps and the refinement's `direction` (the AI
        refinement's laws move, 2026-10-21)."""
        description = text if kind == "description" else (source_work or {}).get("description", "")
        drawn = "" if kind == "image" else (_drawn_description(text) if kind == "description" else text)
        context = {"description": description, "committed_description": description, "parent": parent, "derivation_kind": "new"}
        if kind == "image":
            if parent is not None or source_work is not None or not image_id:
                raise CandidateHostError("invalid_image_start")
            context["image_provenance"] = text
        elif source_work and kind != "description":
            metadata = source_work.get("metadata", {})
            for name in ("image_provenance", "image_ddl"):
                value = source_work.get(name, metadata.get(name))
                if value is not None:
                    context[name] = deepcopy(value)
        if parent:
            if parent["kind"] == "legacy_history":
                context.update(parent_legacy_history_id=parent["id"], derivation_kind="legacy_description_fork" if kind == "description" else "legacy_ddl_fork")
            else:
                context.update(
                    parent_variation_id=parent["id"],
                    derivation_kind=(
                        "description_fork"
                        if kind == "description"
                        else "variation_ddl_fork"
                    ),
                )
        with self._lock:
            self._reserve_run()
            image = self._images.get(owner, image_id) if kind == "image" else None
            if prepared is not None:
                config, resolved_context = prepared
                context.update(resolved_context)
            elif self.prepare_for:
                config, resolved_context = self.prepare_for(owner, kind, drawn, options or {}, source_work)
                context.update(resolved_context)
            else:
                config = self.config_for(owner, source_work)
            if canvas_format_id is not None and canvas_aspect is not None and canvas_format_id != canvas_aspect:
                raise CandidateHostError("canvas_alias_conflict")
            selected = canvas_format_id if canvas_format_id is not None else canvas_aspect
            if selected == "image" and image is not None:
                selected = image.nearest_format_id
            if selected is not None:
                config = select_canvas(config, self.binding.canvas_registry, selected)
            run = self._host(owner, config, context)
            if image is not None:
                from .pipeline_images import image_data_url
                run.image_data[image.reference["sha256"]] = image_data_url(image.jpeg, "image/jpeg")
                authoring = {"tag": "image", "image": image.authoring_input(),
                             "auto_catalog": context.get("auto_catalog", False)}
            elif kind == "description":
                authoring = {"tag": "description", "description": drawn, "auto_catalog": context.get("auto_catalog", self.auto_catalog),
                             **_route_fields(context, text)}
            elif kind == "saved_laws":
                authoring = {"tag": "saved_laws", "source": text,
                             "description": pipeline_description(description), "direction": deepcopy(direction or {})}
            else:
                authoring = {"tag": "direct_ddl", "source": text}
                if parent is None and source_work is None:
                    # A new work's DDL declares the paper it is drawn on; a
                    # DDL from a saved work is drawn as written (DDL 26).
                    authoring["declare_canvas"] = True
            for record in ("completion_ranges", "laws_layers", "laws_basis"):
                if kind != "description" and source_work and source_work.get(record) is not None:
                    authoring[record] = deepcopy(source_work[record])
            sketch = context.get("sketch_request") or {"mode": "off"}
            if kind == "description" and sketch["mode"] != "off":
                authoring["sketch"] = sketch
            run.start_new(authoring)
            if image is not None:
                self._images.consume(owner, image_id)
            run.context["execution_id"] = run.view()["execution_id"]
            key = (owner, run.view()["execution_id"])
            self._runs[key] = run
            self._schedule(key, run)
        return run.view()

    def author_ddl(self, owner: str, execution_id: str, body: AuthorDdlBody) -> dict:
        run = self.execution(owner, execution_id)
        previous = run.view()
        persisted = self.store.read(owner, previous["variation_id"])
        if (
            previous["authority"]["revision"] != body.expected_revision
            or persisted is None
            or persisted["authority"]["revision"] != body.expected_revision
        ):
            raise CandidateHostError("authority_conflict")
        if previous["busy"]:
            raise CandidateHostError("stale_result")
        context = deepcopy(run.context)
        source_work = {
            **previous,
            "saved_config": deepcopy(run.config),
            "host_options": context.get("host_options", {}),
            "macro_catalog": context.get("macro_catalog", {}),
        }
        if self.prepare_for is None:
            if body.options:
                raise CandidateHostError("unsupported_authoring_options")
            prepared = (run.config, {"host_options": source_work["host_options"]})
        else:
            prepared = self.prepare_for(owner, "direct_ddl", body.source, body.options, source_work)
        config, resolved = prepared
        selected_options = resolved.get("host_options", {})
        old_options = source_work["host_options"]
        def runtime_options(options):
            return {key: value for key, value in options.items() if key not in _RECORD_OPTIONS}

        same_settings = config == run.config and runtime_options(selected_options) == runtime_options(old_options)
        changed_source = previous["document"] is not None and previous["document"]["source"] != body.source
        if same_settings and (changed_source or selected_options == old_options):
            run.command({
                "tag": "commit_user_ddl", "expected_revision": body.expected_revision,
                "source": body.source,
            }, context_updates={"host_options": selected_options})
            with self._lock:
                self._schedule((owner, execution_id), run)
            return run.view()
        # A changed performance configuration is a new edition, just like a
        # DDL fork from saved history. The original source and authority stay
        # intact; the new direct-DDL variation starts with DDL authority.
        if run.snapshot().get("completion_ranges") is not None:
            source_work["completion_ranges"] = run.snapshot()["completion_ranges"]
        if run.snapshot().get("laws_layers") is not None:
            source_work["laws_layers"] = run.snapshot()["laws_layers"]
        if run.snapshot().get("laws_basis") is not None:
            source_work["laws_basis"] = run.snapshot()["laws_basis"]
        return self.start(
            owner, "direct_ddl", body.source,
            parent={"kind": "variation", "id": previous["variation_id"]},
            source_work=source_work, prepared=prepared,
        )

    def _reserve_run(self) -> None:
        if len(self._runs) < self.max_retained_runs:
            return
        for key, run in list(self._runs.items()):
            job = self._jobs.get(key)
            if not run.view()["busy"] and (job is None or job.done()):
                from .chatgpt_runtime import retire_execution
                retire_execution(*key)
                run.image_data.clear()
                del self._runs[key]
                self._jobs.pop(key, None)
                return
        from .api_core.state import _increment_stage_stat

        _increment_stage_stat("rejected")
        raise HTTPException(429, {"code": "pipeline_capacity_reached", "message": "All authoring workers are busy."})

    def _schedule(self, key, run) -> None:
        current = self._jobs.get(key)
        if current is not None and not current.done():
            return
        if run.view()["busy"]:
            if run.context.get("host_options", {}).get("chatgpt_profile"):
                from .chatgpt_runtime import begin_execution
                begin_execution(*key)
            job = self._pool.submit(self._drain, run)
            job.add_done_callback(lambda done, key=key: self._log_job_failure(key, done))
            self._jobs[key] = job

    @staticmethod
    def _log_job_failure(key: tuple[str, str], job: Future) -> None:
        # A failed job answers the client 503 "could not finish" and nothing
        # else; without this line the exception that stopped it was lost.
        error = None if job.cancelled() else job.exception()
        if error is not None:
            _logger.error("pipeline_job_failed execution_id=%s", key[1], exc_info=error)

    def _render_payload(
        self, run: CandidateExecution, command: dict
    ) -> dict | None:
        if self.render_with_context is not None:
            return {
                "tag": "render",
                **self.render_with_context(
                    run.snapshot(), run.context, command
                ),
            }
        if self.render_for is not None and set(command) == {"tag"}:
            return {"tag": "render", **self.render_for(run.snapshot())}
        return None

    def _drain(self, run: CandidateExecution) -> None:
        try:
            self._drain_steps(run)
        finally:
            # An unsuccessful host job is not allowed to retain source pixels.
            if not run.view()["busy"] or run.context.get("image_provenance") is not None:
                run.image_data.clear()

    def _drain_steps(self, run: CandidateExecution) -> None:
        # This is a host work cap, never a replacement retry policy.
        for _ in range(self.max_effect_steps):
            view = run.view()
            if not view["busy"]:
                run.image_data.clear()
                return
            snapshot = run.snapshot()
            action = snapshot.get("action") or {}
            delivery = snapshot.get("delivery") or {}
            if (
                action.get("tag") == "complete_visible_ddl_holes"
                and delivery.get("score") is not None
                and view["rendered"] is None
            ):
                payload = self._render_payload(run, {"tag": "perform"})
                if payload is not None:
                    # Persist the acknowledged source's safe performance before
                    # bounded provider I/O can fail or produce a declined patch.
                    run.command(payload)
            run.run_effect()
        if run.view()["busy"]:
            raise CandidateHostError("pipeline_effect_limit")
        run.image_data.clear()

    def execution(self, owner: str, execution_id: str) -> CandidateExecution:
        key = (owner, execution_id)
        with self._lock:
            run = self._runs.get(key)
            if run is None:
                record = self.store.read_execution(owner, execution_id)
                if record is None:
                    raise HTTPException(404, "variation_not_found")
                self._reserve_run()
                saved = json.loads(record.state_bytes)
                run = self._host(owner, saved["snapshot"]["config"], saved["context"])
                run.restore(saved["snapshot"], rendered=saved["rendered"])
                run.context["execution_id"] = execution_id
                self._runs[key] = run
                if (run.snapshot().get("image_ddl") is not None
                        and (run.snapshot().get("action") or {}).get("tag") in {
                            "select_image_catalog", "write_image_ddl", "draw_image_review", "review_image_ddl",
                        }):
                    self._stop_missing_image(run)
                self._schedule(key, run)
            return run

    def completion_range_states(self, owner: str, body: CompletionRangeStatesBody) -> dict:
        """Read this owner's trusted inputs without starting or resuming work."""
        if body.history_id:
            linked = self.store.read_linked_history(owner, body.history_id)
            if linked is None:
                if self.store.read_legacy_history(owner, body.history_id) is None:
                    raise HTTPException(404, "history_not_found")
                config, record = None, None
            else:
                config, record = linked.saved_config, linked.completion_ranges
        else:
            with self._lock:
                run = self._runs.get((owner, body.execution_id))
            if run is not None:
                snapshot = run.snapshot()
            else:
                saved = self.store.read_execution(owner, body.execution_id)
                if saved is None:
                    raise HTTPException(404, "variation_not_found")
                snapshot = json.loads(saved.state_bytes)["snapshot"]
            config, record = snapshot["config"], snapshot.get("completion_ranges")
        states = getattr(self.binding, "completion_range_states", None)
        if record is None or states is None:
            return {"schema": "inku.completion-range-states.v1", "ranges": []}
        request = {"config": config, "source": body.source, "completion_ranges": record}
        return json.loads(states(json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")))

    def retouch(self, owner: str, history_id: str, source: str, tools: dict[int, str]) -> dict:
        """Ask the shared core to write other tools into a saved work's instructions.

        A work the shared pipeline drew reads with its saved config; an older work
        with the config a drawing of it would take, less the drawing's checks.
        Nothing is started. An empty `tools` reads the sentences whose tool can change.
        """
        native = getattr(self.binding, "retouch", None)
        config = self.retouch_config(owner, history_id, source) if native is not None else None
        if config is None:
            return {"outcome": "unchanged", "reason": "binding_unavailable"}
        request = {"config": config, "source": source, "tools": {str(index): tool for index, tool in tools.items()}}
        return json.loads(native(json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")))

    def retouch_config(self, owner: str, history_id: str, source: str) -> dict | None:
        """The config a saved work's instructions are read with for a touch change.

        A work the shared pipeline drew reads with its saved config; an older work
        with the config a drawing of it would take. ``None`` when no config can be made.
        """
        linked = self.store.read_linked_history(owner, history_id)
        if linked is not None:
            return linked.saved_config
        work = self.store.read_legacy_history(owner, history_id)
        if work is None:
            raise HTTPException(404, "history_not_found")
        if self.reading_config_for is None:
            return None
        return self.reading_config_for(owner, source, asdict(work))

    def provider_capture_status(self, owner: str, execution_id: str) -> dict:
        """Read saved state only; transcript inspection must not resume work."""
        record = self.store.read_execution(owner, execution_id)
        if record is None:
            raise HTTPException(404, "variation_not_found")
        saved = json.loads(record.state_bytes)
        requested = bool(saved.get("context", {}).get("host_options", {}).get("developer_capture_provider_io"))
        observations = self.provider_observations(owner, execution_id) if requested and self.provider_observations else []
        return {"capture_enabled": requested, "observations": observations}

    def system_prompts(self, owner: str, variation_id: str) -> dict:
        """The system prompts this variation actually sent: the sketch, Stage 1,
        the composition reading, the laws stage, the color stage and Stage 2,
        with what the sketch, the reading, the laws stage and the color stage
        were given.

        Read from saved state only. `recorded` is false for an execution saved
        before the record existed, `stages` names the stages it kept, and a kept
        stage that never called a model is null.
        """
        from .pipeline_product import system_prompts_view

        record = self.store.read_latest_execution_for_variation(owner, variation_id)
        if record is None:
            raise HTTPException(404, "variation_not_found")
        return system_prompts_view(json.loads(record.state_bytes).get("context", {}))

    def get(self, owner: str, variation_id: str) -> dict:
        record = self.store.read_latest_execution_for_variation(owner, variation_id)
        if record is None:
            raise HTTPException(404, "variation_not_found")
        execution_id = record.execution_id
        run = self.execution(owner, execution_id)
        if run.context.get("svg_refusal") is not None:
            raise HTTPException(422, run.context["svg_refusal"])
        job = self._jobs.get((owner, execution_id))
        if job is not None and job.done() and job.exception() is not None:
            error = job.exception()
            if isinstance(error, HTTPException) and isinstance(error.detail, dict) and error.detail.get("code") == "svg_limit_binding_unavailable":
                raise error
            raise HTTPException(503, {"code": "pipeline_effect_failed", "message": "The authoring operation could not finish."})
        return run.view()

    def command(self, owner: str, execution_id: str, payload: dict) -> dict:
        if payload.get("tag") == "cancel":
            from .chatgpt_runtime import cancel_execution
            cancel_execution(owner, execution_id)
        run = self.execution(owner, execution_id)
        if payload.get("tag") == "perform":
            payload = self._render_payload(run, payload)
            if payload is None:
                raise HTTPException(422, "performance_unavailable")
        elif payload.get("tag") == "render":
            # A client cannot choose policy, canvas, catalog or palette through
            # the render command. The trusted host resolves these consistently.
            raise HTTPException(422, "unsupported_author_action")
        context_updates = None
        if payload.get("tag") == "generate_from_description":
            payload = {**payload, "auto_catalog": run.context.get("auto_catalog", self.auto_catalog)}
            written = payload["description"] if isinstance(payload.get("description"), str) else run.context.get("description", "")
            payload.update(_route_fields(run.context, written))
            if isinstance(payload.get("description"), str):
                context_updates = {"description": payload["description"]}
                payload["description"] = _drawn_description(payload["description"])
            sketch = run.context.get("sketch_request") or {"mode": "off"}
            if sketch["mode"] != "off":
                payload["sketch"] = sketch
        run.command(payload, context_updates=context_updates)
        with self._lock:
            self._schedule((owner, execution_id), run)
        return run.view()

    def legacy(self, owner: str, history_id: str) -> dict:
        link = self.store.history_link(owner, history_id)
        if link is not None:
            raise HTTPException(409, {"code": "managed_history", "message": "Open this work through its saved variation.", **link})
        work = self.store.read_legacy_history(owner, history_id)
        if work is None:
            raise HTTPException(404, "history_not_found")
        return legacy_source_work(self.store, owner, work)

    def fork_legacy(self, owner: str, history_id: str, kind: str, text: str, **choices) -> dict:
        work = self.legacy(owner, history_id)
        if kind == "description" and _rewords(text, work["description"]):
            _refuse_if_locked(history_id)
        return self.start(owner, kind, text, parent={"kind": "legacy_history", "id": history_id}, source_work=work, **choices)

    def ddl_export(self, owner: str, history_id: str) -> dict:
        """The work's visible DDL with the plugin definitions it names."""
        from .api_core.common import _build_number
        from .ddl_export import build_ddl_export

        try:
            linked = self.store.read_linked_history(owner, history_id)
        except VariationAuthorityAdapterError:
            linked = None
        history = linked.history if linked is not None else self.store.read_legacy_history(owner, history_id)
        if history is None:
            raise HTTPException(404, "history_not_found")
        config = linked.saved_config if linked is not None else {}
        language = history.metadata.get("instruction_lang_resolved") or config.get("language") or "ja"
        return build_ddl_export(
            history.source or "",
            str(language),
            config.get("definitions") or [],
            config.get("macro_summaries") or [],
            {"build_number": _build_number(), "render_engine_version": history.metadata.get("render_engine_version")},
        )

    def fork_description(self, owner: str, variation_id: str, body: ForkDescriptionBody) -> dict:
        previous = self.get(owner, variation_id)
        if previous["authority"]["revision"] != body.expected_revision:
            raise HTTPException(409, "authority_conflict")
        # A variation its DDL holds starts a new one from its description as it
        # stands; the words are changed afterwards, in the variation that follows them.
        # Once drawn, the saved work decides: a DDL drawn again unedited is held
        # only if its parent was (persistence/description_lock.py).
        if previous["authority"]["authority"] == "ddl_authoritative" and _rewords(body.description, previous.get("description", "")):
            drawn = (previous.get("result") or {}).get("history_id")
            if drawn:
                _refuse_if_locked(drawn)
            else:
                raise HTTPException(409, DESCRIPTION_LOCKED)
        source_run = self.execution(owner, previous["execution_id"])
        source_work = {**previous, "saved_config": source_run.config,
                       "host_options": source_run.context.get("host_options", {}),
                       "macro_catalog": source_run.context.get("macro_catalog", {})}
        return self.start(owner, "description", body.description,
                          parent=self._fork_parent(owner, variation_id), source_work=source_work, options=body.options)

    def _fork_parent(self, owner: str, variation_id: str) -> dict | None:
        """The parent a description fork from `variation_id` names (2026-10-13).

        A variation stopped before its first save has no saved authority, so
        naming it failed the fork's own first save after its Stage 1 call. Its
        own parent stands in, and that one's, until a saved variation, a legacy
        history, or none."""
        parent: dict | None = {"kind": "variation", "id": variation_id}
        for _ in range(_UNSAVED_PARENT_STEPS):
            if parent is None or parent.get("kind") != "variation" or self.store.read(owner, parent["id"]) is not None:
                return parent
            record = self.store.read_latest_execution_for_variation(owner, parent["id"])
            if record is None:
                return None
            parent = json.loads(record.state_bytes).get("context", {}).get("parent")
        return None

    def fork_linked_history(
        self, owner: str, history_id: str, body: LinkedHistoryForkBody
    ) -> dict:
        try:
            linked = self.store.read_linked_history(owner, history_id)
        except VariationAuthorityAdapterError as error:
            raise CandidateHostError("linked_history_context_unavailable") from error
        if linked is None:
            raise HTTPException(404, "pipeline_history_not_found")
        source_work = linked_source_work(linked)
        if body.kind == "description" and _rewords(body.text, source_work["description"]):
            _refuse_if_locked(history_id)
        return self.start(
            owner,
            body.kind,
            body.text,
            parent={"kind": "variation", "id": linked.variation_id},
            source_work=source_work,
            options=body.options,
        )


def linked_source_work(linked) -> dict:
    """The saved work a fork of a managed history starts from: its exact
    history, with the config and host context frozen when it was drawn."""
    history = asdict(linked.history)
    return {
        **history,
        "saved_config": linked.saved_config,
        "host_options": linked.host_options,
        "macro_catalog": linked.macro_catalog,
        **({"completion_ranges": linked.completion_ranges} if linked.completion_ranges is not None else {}),
        **({"laws_layers": linked.laws_layers} if linked.laws_layers is not None else {}),
        **({"laws_basis": linked.laws_basis} if linked.laws_basis is not None else {}),
        "result": {"lineage_node_id": history["metadata"].get("lineage_node_id")},
    }


def saved_work_parent(store, owner: str, history_id: str) -> tuple[dict, dict]:
    """The parent relation and saved work a direct-DDL fork of one history takes.

    A work the shared pipeline drew forks from its variation with the saved
    config; an older work forks from its history row, whose metadata carries
    its seeds and limits. Another owner's work reads as no work at all.
    """
    try:
        linked = store.read_linked_history(owner, history_id)
    except VariationAuthorityAdapterError as error:
        raise CandidateHostError("linked_history_context_unavailable") from error
    if linked is not None:
        return {"kind": "variation", "id": linked.variation_id}, linked_source_work(linked)
    work = store.read_legacy_history(owner, history_id)
    if work is None:
        raise HTTPException(404, "history_not_found")
    return {"kind": "legacy_history", "id": history_id}, legacy_source_work(store, owner, work)


def legacy_source_work(store, owner: str, work) -> dict:
    """An older work as a fork reads it: its history row, and the laws records a
    work drawn from its parent without a run keeps on its lineage edge, which
    "change the layout" and a direct-DDL fork take as a linked work's (2026-10-20)."""
    return {**asdict(work), **store.read_derived_laws_records(owner, work.history_id)}


def laws_records_of(store, owner: str, history_id: str) -> dict[str, object]:
    """The laws records of one saved work, linked or drawn from its parent without
    a run, by key. A context that cannot be read gives none: the child is then
    saved as before, without them."""
    try:
        linked = store.read_linked_history(owner, history_id)
    except VariationAuthorityAdapterError:
        return {}
    if linked is not None:
        return {key: getattr(linked, key) for key in LAWS_RECORD_KEYS if getattr(linked, key) is not None}
    return store.read_derived_laws_records(owner, history_id)


def pipeline_router(service: PipelineService | Callable[[], PipelineService], actor_dependency: Callable,
                    *, binding_for: Callable[[], PipelineBinding] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/pipeline")

    def current_service() -> PipelineService:
        return service if isinstance(service, PipelineService) else service()

    @router.get("/canvas-formats", summary="List canvas formats")
    def canvas_formats(actor: dict = Depends(actor_dependency)):
        """List the canvas formats (paper sizes and aspect ratios) the pipeline offers, as the registry of the shared pipeline binding reports them. Requires a signed-in user."""
        return (binding_for() if binding_for else current_service().binding).canvas_registry

    @router.post("/completion-range-states", summary="Read completion range states")
    def completion_range_states(body: CompletionRangeStatesBody, actor: dict = Depends(actor_dependency)):
        """Read the states of the completion ranges of a DDL source, taken from a saved work or an execution. Nothing is started or resumed; the result has an empty ranges list when the work has no completion ranges. Requires a signed-in user; returns 404 (variation_not_found or history_not_found) when the work or execution is not found."""
        return current_service().completion_range_states(actor["id"], body)

    @router.get("/history/{history_id}", summary="Read a work's variation link")
    def history_link(history_id: str = Path(description="ID of the saved work."), actor: dict = Depends(actor_dependency)):
        """Return the variation link of a saved work: its owner, history ID, variation ID, revision and DDL digest. Requires a signed-in user; returns 404 (pipeline_history_not_found) when the work is not linked to a variation."""
        link = current_service().store.history_link(actor["id"], history_id)
        if link is None:
            raise HTTPException(404, "pipeline_history_not_found")
        return link

    @router.get("/history/{history_id}/ddl-export", summary="Export a work's DDL")
    def ddl_export(history_id: str = Path(description="ID of the saved work to export."), actor: dict = Depends(actor_dependency)):
        """Return the work's visible DDL together with the plugin definitions it names, for export. Requires a signed-in user; returns 404 (history_not_found) when the caller has no such work."""
        return current_service().ddl_export(actor["id"], history_id)

    @router.post("/history/{history_id}/fork", summary="Fork a linked work")
    def fork_linked_history(
        body: LinkedHistoryForkBody,
        history_id: str = Path(description="ID of the saved work to fork from."),
        actor: dict = Depends(actor_dependency),
    ):
        """Start a new variation from a saved work that is linked to a variation, as a description fork or a direct-DDL fork, and return its state. Requires a signed-in user; returns 404 (pipeline_history_not_found) when the work is not linked, and 409 (description_locked) when a changed description would reword a work whose DDL holds it."""
        return current_service().fork_linked_history(actor["id"], history_id, body)

    @router.post("/variations", summary="Start a variation")
    def start(body: NewVariationBody, actor: dict = Depends(actor_dependency)):
        """Start a new variation from a description, DDL source or prepared image and return its state. The run continues in the background; read its progress with GET /api/pipeline/variations/{variation_id}. Requires a signed-in user; returns 400 for a description made only of labels, 422 for invalid options, canvas or image choices, and 429 when all authoring workers are busy."""
        return current_service().start(actor["id"], body.kind, body.text, image_id=body.image_id, canvas_format_id=body.canvas_format_id, canvas_aspect=body.canvas_aspect, options=body.options)

    @router.post("/images", response_model=PreparedImageView, summary="Upload an image for an image variation", openapi_extra={
        "requestBody": {"required": True, "content": {
            "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
        }},
    })
    async def prepare_image(request: Request, actor: dict = Depends(actor_dependency)):
        """Prepare an image file sent as the raw request body (application/octet-stream), for use as image_id when starting an image variation. The accepted formats are JPEG, PNG, GIF and TIFF, up to 32 MiB; the result gives the image ID, which stays valid for 15 minutes. Returns 413 (image_too_large) for an upload that is too large and 422 (image_invalid) for a file that is not an accepted image."""
        from .pipeline_images import IMAGE_UPLOAD_MAX_BYTES
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > IMAGE_UPLOAD_MAX_BYTES:
                raise HTTPException(413, {"code": "image_too_large", "message": "The image file is too large."})
            raw.extend(chunk)
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(current_service().prepare_image, actor["id"], bytes(raw))

    @router.get("/variations/{variation_id}", summary="Read a variation")
    def get(variation_id: str = Path(description="ID of the variation."), actor: dict = Depends(actor_dependency)):
        """Return the state of a variation's latest execution: its stage, authority revision, result and performance. Requires a signed-in user; returns 404 (variation_not_found) when no execution exists, 422 when the drawing was refused, and 503 (pipeline_effect_failed) when the last operation could not finish."""
        return current_service().get(actor["id"], variation_id)

    @router.get("/variations/{variation_id}/system-prompts", summary="Read a variation's system prompts")
    def system_prompts(variation_id: str = Path(description="ID of the variation."), actor: dict = Depends(actor_dependency)):
        """Return the system prompts that the variation's latest saved execution sent to its models, read from saved state only, with the stages it kept. Requires a signed-in user; returns 404 (variation_not_found) when no execution exists."""
        return current_service().system_prompts(actor["id"], variation_id)

    @router.post("/variations/{variation_id}/fork-description", summary="Fork a variation's description")
    def fork(body: ForkDescriptionBody, variation_id: str = Path(description="ID of the variation to fork from."), actor: dict = Depends(actor_dependency)):
        """Start a new description variation from a variation, with the description given in the body, and return its state. Requires a signed-in user; returns 409 (authority_conflict) when expected_revision is stale and 409 (description_locked) when the words change on a variation whose DDL holds the work."""
        return current_service().fork_description(actor["id"], variation_id, body)

    @router.post("/executions/{execution_id}/commands", summary="Send a command to an execution")
    def command(body: dict, execution_id: str = Path(description="ID of the execution."), actor: dict = Depends(actor_dependency)):
        """Send an author action to an execution and return its state. The accepted tags are perform (draw the saved score), commit_user_ddl, generate_from_description, complete_holes, approve_patch, decline_patch and cancel. Requires a signed-in user; returns 409 (authority_conflict, description_locked or stale_result) when the execution changed, 422 (unsupported_author_action or performance_unavailable) for an action it cannot take, and 403 or 503 for provider refusals."""
        try:
            return current_service().command(actor["id"], execution_id, body)
        except CandidateHostError as error:
            code = str(error)
            detail = {"code": code, "message": code.replace("_", " ")}
            if code in {"authority_conflict", "description_locked", "stale_result"}:
                detail["current_view"] = current_service().execution(actor["id"], execution_id).view()
                detail["current_revision"] = detail["current_view"]["authority"]["revision"]
            raise HTTPException(_host_error_status(code), detail) from None

    @router.post("/executions/{execution_id}/author-ddl", summary="Commit an edited DDL")
    def author_ddl(body: AuthorDdlBody, execution_id: str = Path(description="ID of the execution being edited."), actor: dict = Depends(actor_dependency)):
        """Save an edited DDL source for an execution and return its state. When the run's settings are unchanged, the source is committed to the same variation; otherwise a new direct-DDL variation is started and returned. Requires a signed-in user; returns 409 (authority_conflict) when the revision is stale and 409 (stale_result) while the execution is still busy."""
        try:
            return current_service().author_ddl(actor["id"], execution_id, body)
        except CandidateHostError as error:
            code = str(error)
            detail = {"code": code, "message": code.replace("_", " ")}
            if code in {"authority_conflict", "description_locked", "stale_result"}:
                detail["current_view"] = current_service().execution(actor["id"], execution_id).view()
                detail["current_revision"] = detail["current_view"]["authority"]["revision"]
            raise HTTPException(_host_error_status(code), detail) from None

    @router.get("/executions/{execution_id}/provider-observations", summary="Read an execution's provider observations")
    def provider_observations(execution_id: str = Path(description="ID of the execution."), actor: dict = Depends(actor_dependency)):
        """Return the captured provider exchanges of an execution. Available only when developer mode is enabled; returns 404 (developer_provider_observations_not_available) otherwise. When the execution was not run with provider I/O capture, returns capture_enabled false and an empty observations list. Requires a signed-in user."""
        from .api_core.common import _env_flag
        if not _env_flag("INKU_DEVELOPER_MODE") or current_service().provider_observations is None:
            raise HTTPException(404, "developer_provider_observations_not_available")
        # Read through the service so the owner is always the authenticated
        # actor; the client never supplies a filesystem or artifact path.
        return current_service().provider_capture_status(actor["id"], execution_id)

    @router.get("/legacy/{history_id}", summary="Read an older work")
    def legacy(history_id: str = Path(description="ID of the older work, one that is not linked to a variation."), actor: dict = Depends(actor_dependency)):
        """Return the description, source and SVG of an older work that is not linked to a variation. Requires a signed-in user; returns 409 (managed_history) for a work that opens through its variation instead, and 404 (history_not_found) when the caller has no such work."""
        work = current_service().legacy(actor["id"], history_id)
        return {key: work[key] for key in ("history_id", "description", "source", "svg")}

    @router.post("/legacy/{history_id}/fork", summary="Fork an older work")
    def fork_legacy(body: NewVariationBody, history_id: str = Path(description="ID of the older work to fork from, one that is not linked to a variation."), actor: dict = Depends(actor_dependency)):
        """Start a new variation from an older work that is not linked to a variation, as a description or DDL fork, and return its state. Requires a signed-in user; returns 404 (history_not_found) when the work does not exist and 409 (description_locked) when a changed description would reword a work whose DDL holds it."""
        return current_service().fork_legacy(actor["id"], history_id, body.kind, body.text, canvas_format_id=body.canvas_format_id, canvas_aspect=body.canvas_aspect, options=body.options)

    return router


def _host_error_status(code: str) -> int:
    if code == "image_too_large":
        return 413
    if code == "image_model_not_vision":
        return 403
    if code.startswith("chatgpt_"):
        return 503 if code in {"chatgpt_transport_unavailable", "chatgpt_auth_unavailable", "chatgpt_refresh_not_ready"} else 403
    if code == "model_not_offered":
        return 403
    # A saved record the retired Saijiki (v1) wrote is refused until the one-time
    # migration moves it: a state of the record, like a lock, not a bad request.
    return 409 if code in {"authority_conflict", "description_locked", "stale_result", "saijiki_migration_required"} else 422


def register_pipeline_errors(app: FastAPI) -> None:
    @app.exception_handler(CandidateHostError)
    async def candidate_error(request, error):
        code = str(error)
        return JSONResponse(status_code=_host_error_status(code), content={"detail": {"code": code, "message": code.replace("_", " ")}})

    @app.exception_handler(ExecutionSnapshotConflict)
    async def snapshot_conflict(request, error):
        return JSONResponse(status_code=409, content={"detail": {"code": "execution_conflict", "message": "The saved authoring state has changed."}})
