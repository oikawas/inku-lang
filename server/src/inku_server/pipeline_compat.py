"""Compatibility projections from the normal HTTP routes to PipelineService."""

from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .persistence.schema import HistoryRow


_POLL_SECONDS = 0.025


def _service():
    # Keep application startup lazy: importing the normal router must not load
    # the native bundle or require deployment policy before the first request.
    from .pipeline_runtime import get_service

    return get_service()


def _wait(owner: str, view: dict) -> dict:
    service = _service()
    while view.get("busy"):
        time.sleep(_POLL_SECONDS)
        view = service.get(owner, view["variation_id"])
    return view


def _interaction(view: dict) -> HTTPException:
    phase = view.get("phase") or {}
    code = (
        "pipeline_patch_approval_required"
        if phase.get("tag") == "awaiting_patch_approval"
        else "pipeline_author_action_required"
    )
    return HTTPException(
        409,
        {
            "code": code,
            "message": code.replace("_", " "),
            "current_view": view,
            "current_revision": (view.get("authority") or {}).get("revision"),
            "pipeline_variation_id": view.get("variation_id"),
            "pipeline_execution_id": view.get("execution_id"),
        },
    )


def _settled(owner: str, view: dict, *, perform: bool) -> dict:
    view = _wait(owner, view)
    if (view.get("phase") or {}).get("tag") == "awaiting_patch_approval":
        raise _interaction(view)
    if not perform:
        if view.get("document") is None:
            raise _interaction(view)
        return view
    if view.get("delivery") is None:
        raise _interaction(view)
    if view.get("result") is None:
        view = _wait(owner, _service().command(owner, view["execution_id"], {"tag": "perform"}))
    if view.get("result") is None:
        raise _interaction(view)
    return view


def _identity(view: dict) -> dict:
    return {
        "pipeline_variation_id": view["variation_id"],
        "pipeline_execution_id": view["execution_id"],
        "pipeline_revision": view["authority"]["revision"],
    }


def _options(data: dict[str, Any], *, save_history: bool) -> dict:
    aliases = {
        "model": "stage2_model",
        "stage1_model": "stage1_model",
        "stage2_model": "stage2_model",
        "instruction_lang": "instruction_lang",
        "ui_lang": "ui_lang",
        "catalog_id": "catalog_id",
        "catalog_mode": "catalog_mode",
        "canvas_aspect": "canvas_aspect",
        "render_seed": "render_seed",
        "composition_seed": "composition_seed",
        "wild": "wild",
        "variation_amplitude": "variation_amplitude",
        "variation_seed": "variation_seed",
        "interpretation_seed": "interpretation_seed",
        "seed_text": "seed_text",
        "history_input": "history_input",
        "history_at": "history_at",
        "history_source_text": "history_source_text",
        "history_display_label": "history_display_label",
        "batch_line_number": "batch_line_number",
        "batch_run_id": "batch_run_id",
        "history_visibility": "history_visibility",
        "lineage_parent_node_id": "lineage_parent_node_id",
        "derivation_kind": "derivation_kind",
        "derivation_metadata": "derivation_metadata",
        "save_artifacts": "save_artifacts",
        "count_generation": "count_generation",
    }
    options = {
        target: data[source]
        for source, target in aliases.items()
        if data.get(source) is not None
    }
    if data.get("sketch_text"):
        options["sketch_text"] = data["sketch_text"]
    elif data.get("sketch") is True:
        options["sketch"] = "on"
    options["save_history"] = save_history
    return options


def _history_replay(owner: str, key: str, data: dict[str, Any]) -> dict | None:
    """Return an exact previous paint without minting an orphan variation."""
    from . import db

    with Session(db.engine) as session:
        history_id = session.execute(
            select(HistoryRow.id).where(
                HistoryRow.user_id == owner,
                HistoryRow.idempotency_key == key,
            )
        ).scalar_one_or_none()
    if history_id is None:
        return None
    items = db.get_items(owner, [history_id])
    if not items:
        return None
    item = items[0]
    expected_input = data.get("history_input") or data["description"]
    expected_source = data.get("history_source_text") or data["description"]
    if item.get("input") != expected_input or item.get("source_text") != expected_source:
        raise HTTPException(
            409,
            {
                "code": "idempotency_conflict",
                "message": "The idempotency key belongs to a different drawing.",
            },
        )
    return {
        **item,
        "description": item.get("input", ""),
        "ddl": item.get("ddl") or "",
        "score": item.get("score") or {},
        "svg": item.get("svg") or "",
        "history_id": item["id"],
        "history_at": item.get("at"),
        "elapsed_stage1_ms": 0,
        "elapsed_stage2_ms": 0,
        "elapsed_total_ms": item.get("elapsed_ms") or 0,
        "tokens_in_stage1": None,
        "tokens_out_stage1": None,
        "tokens_in_stage2": item.get("tokens_in"),
        "tokens_out_stage2": item.get("tokens_out"),
    }


def interpret(owner: str, data: dict[str, Any]) -> dict:
    options = _options(data, save_history=False)
    if data.get("model") is not None:
        options["stage1_model"] = data["model"]
        options.pop("stage2_model", None)
    view = _settled(
        owner,
        _service().start(owner, "description", data["description"], options=options),
        perform=False,
    )
    context = _service().execution(owner, view["execution_id"]).context
    host_options = context.get("host_options", {})
    metrics = context.get("metrics", {})
    return {
        "ddl": view["document"]["source"],
        "thinking": None,
        "stage1_model": host_options.get("stage1_model"),
        "instruction_lang_requested": host_options.get("instruction_lang"),
        "instruction_lang_resolved": host_options.get("instruction_lang_resolved"),
        "ui_lang": host_options.get("ui_lang"),
        "tokens_in": None,
        "tokens_out": None,
        "elapsed_ms": metrics.get("stage1", 0),
        **_identity(view),
    }


def compose(owner: str, data: dict[str, Any]) -> dict:
    options = _options(data, save_history=False)
    # The old compose endpoint produced a candidate and never counted it as a
    # completed author drawing. Performance is needed for its SVG projection,
    # but it must keep that accounting contract.
    options["count_generation"] = False
    view = _settled(
        owner,
        _service().start(
            owner,
            "direct_ddl",
            data["ddl"],
            source_work={"description": data.get("description") or ""},
            canvas_aspect=data.get("canvas_aspect"),
            options=options,
        ),
        perform=True,
    )
    return {**view["result"], **_identity(view)}


def paint(owner: str, data: dict[str, Any], idempotency_key: str | None) -> dict:
    if idempotency_key:
        replay = _history_replay(owner, idempotency_key, data)
        if replay is not None:
            return replay
    options = _options(data, save_history=bool(data.get("save_history", False)))
    if idempotency_key:
        options["request_idempotency_key"] = idempotency_key
    view = _settled(
        owner,
        _service().start(
            owner,
            "description",
            data["description"],
            canvas_aspect=data.get("canvas_aspect"),
            options=options,
        ),
        perform=True,
    )
    return {**view["result"], **_identity(view)}
