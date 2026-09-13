"""Authoring API for the shared Rust pipeline and its durable host state."""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import asdict
from typing import Callable, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .pipeline_candidate import CandidateExecution, CandidateHostError, PipelineBinding
from .pipeline_settings import select_canvas
from .persistence.variation_authority import (
    ExecutionSnapshotConflict,
    VariationAuthorityAdapterError,
)
from .security import ConcurrencyLimitMiddleware, RequestBodyLimitMiddleware


_RECORD_OPTIONS = frozenset({
    "history_display_label", "batch_line_number", "batch_run_id", "history_visibility",
    "lineage_parent_node_id", "derivation_kind", "derivation_metadata", "count_generation",
    "save_history", "save_artifacts", "history_input", "history_source_text", "history_at",
    "request_idempotency_key",
})


class NewVariationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["description", "direct_ddl"]
    text: str
    canvas_format_id: str | None = None
    canvas_aspect: str | None = None
    options: dict = {}


class ForkDescriptionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str
    description: str
    options: dict = {}


class LinkedHistoryForkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["description", "direct_ddl"]
    text: str
    options: dict = {}


class AuthorDdlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str
    source: str
    options: dict = {}


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
    ):
        if max_workers <= 0 or max_effect_steps <= 0 or max_retained_runs < max_workers:
            raise ValueError("explicit positive pipeline host limits required")
        self.binding, self.store = binding, store
        self.config_for, self.provider_for, self.render_for = config_for, provider_for, render_for
        self.max_effect_steps = max_effect_steps
        self.max_retained_runs = max_retained_runs
        self.auto_catalog = auto_catalog
        self.prepare_for, self.provider_with_context = prepare_for, provider_with_context
        self.render_with_context, self.project_result = render_with_context, project_result
        self.replay_for = replay_for
        self._runs: dict[tuple[str, str], CandidateExecution] = {}
        self._jobs: dict[tuple[str, str], Future] = {}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="inku-pipeline")

    def close(self) -> None:
        with self._lock:
            for run in self._runs.values():
                if run.view()["busy"]:
                    run.command({"tag": "cancel"})
        self._pool.shutdown(wait=True, cancel_futures=True)

    def _host(self, owner: str, config: dict, context: dict) -> CandidateExecution:
        def provider(action):
            transport = self.provider_with_context(owner, run.context) if self.provider_with_context else self.provider_for(owner)
            return transport(action)

        def save(previous, snapshot, host_context, rendered):
            if rendered is None:
                host_context.pop("result", None)
                host_context.pop("render_digest", None)
            elif self.project_result is not None:
                digest = hashlib.sha256(json.dumps(rendered, sort_keys=True).encode()).hexdigest()
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
        )
        return run

    def start(self, owner: str, kind: str, text: str, *, parent: dict | None = None, source_work: dict | None = None,
              canvas_format_id: str | None = None, canvas_aspect: str | None = None,
              options: dict | None = None, prepared: tuple[dict, dict] | None = None) -> dict:
        description = text if kind == "description" else (source_work or {}).get("description", "")
        context = {"description": description, "committed_description": description, "parent": parent, "derivation_kind": "new"}
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
            if prepared is not None:
                config, resolved_context = prepared
                context.update(resolved_context)
            elif self.prepare_for:
                config, resolved_context = self.prepare_for(owner, kind, text, options or {}, source_work)
                context.update(resolved_context)
            else:
                config = self.config_for(owner, source_work)
            if canvas_format_id is not None and canvas_aspect is not None and canvas_format_id != canvas_aspect:
                raise CandidateHostError("canvas_alias_conflict")
            selected = canvas_format_id if canvas_format_id is not None else canvas_aspect
            if selected is not None:
                config = select_canvas(config, self.binding.canvas_registry, selected)
            run = self._host(owner, config, context)
            authoring = {"tag": "description", "description": text, "auto_catalog": context.get("auto_catalog", self.auto_catalog)} if kind == "description" else {"tag": "direct_ddl", "source": text}
            run.start_new(authoring)
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
                del self._runs[key]
                self._jobs.pop(key, None)
                return
        raise HTTPException(429, {"code": "pipeline_capacity_reached", "message": "All authoring workers are busy."})

    def _schedule(self, key, run) -> None:
        current = self._jobs.get(key)
        if current is not None and not current.done():
            return
        if run.view()["busy"]:
            self._jobs[key] = self._pool.submit(self._drain, run)

    def _drain(self, run: CandidateExecution) -> None:
        # This is a host work cap, never a replacement retry policy.
        for _ in range(self.max_effect_steps):
            if not run.view()["busy"]:
                return
            run.run_effect()
        if run.view()["busy"]:
            raise CandidateHostError("pipeline_effect_limit")

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
                self._runs[key] = run
                self._schedule(key, run)
            return run

    def get(self, owner: str, variation_id: str) -> dict:
        record = self.store.read_latest_execution_for_variation(owner, variation_id)
        if record is None:
            raise HTTPException(404, "variation_not_found")
        execution_id = record.execution_id
        run = self.execution(owner, execution_id)
        job = self._jobs.get((owner, execution_id))
        if job is not None and job.done() and job.exception() is not None:
            raise HTTPException(503, {"code": "pipeline_effect_failed", "message": "The authoring operation could not finish."})
        return run.view()

    def command(self, owner: str, execution_id: str, payload: dict) -> dict:
        run = self.execution(owner, execution_id)
        if payload.get("tag") == "perform":
            if self.render_with_context is not None:
                payload = {"tag": "render", **self.render_with_context(run.snapshot(), run.context, payload)}
            elif self.render_for is not None and set(payload) == {"tag"}:
                payload = {"tag": "render", **self.render_for(run.snapshot())}
            else:
                raise HTTPException(422, "performance_unavailable")
        elif payload.get("tag") == "render":
            # A client cannot choose policy, canvas, catalog or palette through
            # the render command. The trusted host resolves these consistently.
            raise HTTPException(422, "unsupported_author_action")
        elif payload.get("tag") == "generate_from_description":
            payload = {**payload, "auto_catalog": run.context.get("auto_catalog", self.auto_catalog)}
        run.command(payload)
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
        return asdict(work)

    def fork_legacy(self, owner: str, history_id: str, kind: str, text: str, **choices) -> dict:
        work = self.legacy(owner, history_id)
        return self.start(owner, kind, text, parent={"kind": "legacy_history", "id": history_id}, source_work=work, **choices)

    def fork_description(self, owner: str, variation_id: str, body: ForkDescriptionBody) -> dict:
        previous = self.get(owner, variation_id)
        if previous["authority"]["revision"] != body.expected_revision:
            raise HTTPException(409, "authority_conflict")
        source_run = self.execution(owner, previous["execution_id"])
        source_work = {**previous, "saved_config": source_run.config,
                       "host_options": source_run.context.get("host_options", {}),
                       "macro_catalog": source_run.context.get("macro_catalog", {})}
        return self.start(owner, "description", body.description,
                          parent={"kind": "variation", "id": variation_id}, source_work=source_work, options=body.options)

    def fork_linked_history(
        self, owner: str, history_id: str, body: LinkedHistoryForkBody
    ) -> dict:
        try:
            linked = self.store.read_linked_history(owner, history_id)
        except VariationAuthorityAdapterError as error:
            raise CandidateHostError("linked_history_context_unavailable") from error
        if linked is None:
            raise HTTPException(404, "pipeline_history_not_found")
        history = asdict(linked.history)
        lineage_node_id = history["metadata"].get("lineage_node_id")
        source_work = {
            **history,
            "saved_config": linked.saved_config,
            "host_options": linked.host_options,
            "macro_catalog": linked.macro_catalog,
            "result": {"lineage_node_id": lineage_node_id},
        }
        return self.start(
            owner,
            body.kind,
            body.text,
            parent={"kind": "variation", "id": linked.variation_id},
            source_work=source_work,
            options=body.options,
        )


def pipeline_router(service: PipelineService | Callable[[], PipelineService], actor_dependency: Callable,
                    *, binding_for: Callable[[], PipelineBinding] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/pipeline")

    def current_service() -> PipelineService:
        return service if isinstance(service, PipelineService) else service()

    @router.get("/canvas-formats")
    def canvas_formats(actor: dict = Depends(actor_dependency)):
        return (binding_for() if binding_for else current_service().binding).canvas_registry

    @router.get("/history/{history_id}")
    def history_link(history_id: str, actor: dict = Depends(actor_dependency)):
        link = current_service().store.history_link(actor["id"], history_id)
        if link is None:
            raise HTTPException(404, "pipeline_history_not_found")
        return link

    @router.post("/history/{history_id}/fork")
    def fork_linked_history(
        history_id: str,
        body: LinkedHistoryForkBody,
        actor: dict = Depends(actor_dependency),
    ):
        return current_service().fork_linked_history(actor["id"], history_id, body)

    @router.post("/variations")
    def start(body: NewVariationBody, actor: dict = Depends(actor_dependency)):
        return current_service().start(actor["id"], body.kind, body.text, canvas_format_id=body.canvas_format_id, canvas_aspect=body.canvas_aspect, options=body.options)

    @router.get("/variations/{variation_id}")
    def get(variation_id: str, actor: dict = Depends(actor_dependency)):
        return current_service().get(actor["id"], variation_id)

    @router.post("/variations/{variation_id}/fork-description")
    def fork(variation_id: str, body: ForkDescriptionBody, actor: dict = Depends(actor_dependency)):
        return current_service().fork_description(actor["id"], variation_id, body)

    @router.post("/executions/{execution_id}/commands")
    def command(execution_id: str, body: dict, actor: dict = Depends(actor_dependency)):
        try:
            return current_service().command(actor["id"], execution_id, body)
        except CandidateHostError as error:
            code = str(error)
            detail = {"code": code, "message": code.replace("_", " ")}
            if code in {"authority_conflict", "description_locked", "stale_result"}:
                detail["current_view"] = current_service().execution(actor["id"], execution_id).view()
                detail["current_revision"] = detail["current_view"]["authority"]["revision"]
            raise HTTPException(_host_error_status(code), detail) from None

    @router.post("/executions/{execution_id}/author-ddl")
    def author_ddl(execution_id: str, body: AuthorDdlBody, actor: dict = Depends(actor_dependency)):
        try:
            return current_service().author_ddl(actor["id"], execution_id, body)
        except CandidateHostError as error:
            code = str(error)
            detail = {"code": code, "message": code.replace("_", " ")}
            if code in {"authority_conflict", "description_locked", "stale_result"}:
                detail["current_view"] = current_service().execution(actor["id"], execution_id).view()
                detail["current_revision"] = detail["current_view"]["authority"]["revision"]
            raise HTTPException(_host_error_status(code), detail) from None

    @router.get("/legacy/{history_id}")
    def legacy(history_id: str, actor: dict = Depends(actor_dependency)):
        work = current_service().legacy(actor["id"], history_id)
        return {key: work[key] for key in ("history_id", "description", "source", "svg")}

    @router.post("/legacy/{history_id}/fork")
    def fork_legacy(history_id: str, body: NewVariationBody, actor: dict = Depends(actor_dependency)):
        return current_service().fork_legacy(actor["id"], history_id, body.kind, body.text, canvas_format_id=body.canvas_format_id, canvas_aspect=body.canvas_aspect, options=body.options)

    return router


def _host_error_status(code: str) -> int:
    return 409 if code in {"authority_conflict", "description_locked", "stale_result"} else 422


def register_pipeline_errors(app: FastAPI) -> None:
    @app.exception_handler(CandidateHostError)
    async def candidate_error(request, error):
        code = str(error)
        return JSONResponse(status_code=_host_error_status(code), content={"detail": {"code": code, "message": code.replace("_", " ")}})

    @app.exception_handler(ExecutionSnapshotConflict)
    async def snapshot_conflict(request, error):
        return JSONResponse(status_code=409, content={"detail": {"code": "execution_conflict", "message": "The saved authoring state has changed."}})


def create_acceptance_app(service: PipelineService, *, actor_dependency: Callable, max_body_bytes: int, max_requests: int) -> FastAPI:
    """Isolated API fixture; production registers the same router on api.app."""
    @asynccontextmanager
    async def lifespan(app):
        yield
        service.close()

    app = FastAPI(title="inku pipeline test fixture", lifespan=lifespan)
    register_pipeline_errors(app)

    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=max_body_bytes)
    app.add_middleware(ConcurrencyLimitMiddleware, max_requests=max_requests)
    app.include_router(pipeline_router(service, actor_dependency))
    return app
