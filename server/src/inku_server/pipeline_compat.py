"""Compatibility projections from the normal HTTP routes to PipelineService."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .persistence.schema import HistoryRow


_logger = logging.getLogger(__name__)
_POLL_SECONDS = 0.025
# While nothing settles, the stream still writes a line this often. The web
# server's proxy (Node's fetch) drops a body silent for 300 s, as long as one
# Stage 1 attempt may take; and a reader that has left is noticed only when a
# line is written, so this also bounds how long its run goes on.
_WAIT_EVENT_SECONDS = 10.0
# How often a plain request's wait asks whether its caller is still there.
_READER_CHECK_SECONDS = 1.0


def _service():
    # Keep application startup lazy: importing the normal router must not load
    # the native bundle or require deployment policy before the first request.
    from .pipeline_runtime import get_service

    return get_service()


def _wait(owner: str, view: dict, reader_left: Callable[[], bool] | None = None) -> dict:
    """Wait until the run needs no host work; `reader_left` says whether the caller has gone.

    A caller that stopped (the model comparison's stop, a CLI interrupted) used
    to leave the run going through every model retry.
    """
    service = _service()
    checked = time.monotonic()
    while view.get("busy"):
        time.sleep(_POLL_SECONDS)
        if reader_left is not None and time.monotonic() - checked >= _READER_CHECK_SECONDS:
            checked = time.monotonic()
            if reader_left():
                _end_abandoned_run(owner, view)
                raise HTTPException(499, "client closed request")
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


def _settled(owner: str, view: dict, *, perform: bool, reader_left: Callable[[], bool] | None = None) -> dict:
    view = _wait(owner, view, reader_left)
    if (view.get("phase") or {}).get("tag") == "awaiting_patch_approval":
        raise _interaction(view)
    if not perform:
        if view.get("document") is None:
            raise _interaction(view)
        return view
    if view.get("delivery") is None:
        raise _interaction(view)
    if view.get("result") is None:
        view = _wait(owner, _service().command(owner, view["execution_id"], {"tag": "perform"}), reader_left)
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
    # Limits the caller lowers for this drawing (ledger I-154); the host bounds
    # them by today's settings.
    if data.get("limits") is not None:
        options["limits"] = data["limits"]
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


def interpret(owner: str, data: dict[str, Any], reader_left: Callable[[], bool] | None = None) -> dict:
    options = _options(data, save_history=False)
    if data.get("model") is not None:
        options["stage1_model"] = data["model"]
        options.pop("stage2_model", None)
    view = _settled(
        owner,
        _service().start(owner, "description", data["description"], options=options),
        perform=False,
        reader_left=reader_left,
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


def compose(owner: str, data: dict[str, Any], reader_left: Callable[[], bool] | None = None) -> dict:
    options = _options(data, save_history=False)
    # The old compose endpoint produced a candidate and never counted it as a
    # completed author drawing. Performance is needed for its SVG projection,
    # but it must keep that accounting contract.
    options["count_generation"] = False
    if data.get("imported_plugins"):
        options["imported_plugins"] = data["imported_plugins"]
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
        reader_left=reader_left,
    )
    return {**view["result"], **_identity(view)}


def _start_paint(owner: str, data: dict[str, Any], idempotency_key: str | None) -> dict:
    options = _options(data, save_history=bool(data.get("save_history", False)))
    if idempotency_key:
        options["request_idempotency_key"] = idempotency_key
    return _service().start(
        owner,
        "description",
        data["description"],
        canvas_aspect=data.get("canvas_aspect"),
        options=options,
    )


def paint(
    owner: str, data: dict[str, Any], idempotency_key: str | None,
    reader_left: Callable[[], bool] | None = None,
) -> dict:
    if idempotency_key:
        replay = _history_replay(owner, idempotency_key, data)
        if replay is not None:
            return replay
    view = _settled(owner, _start_paint(owner, data, idempotency_key), perform=True, reader_left=reader_left)
    return {**view["result"], **_identity(view)}


_SKETCH_SETTLED = {"supplemented": "supplemented", "supplied": "supplemented",
                   "not_needed": "not_needed", "fallback": "fallback"}


def _progress(owner: str, view: dict, started: float, sent: set[str]) -> Iterator[dict]:
    """Each layer that has settled in this view and has not been reported yet,
    then the provider attempt when it has changed."""
    elapsed = int((time.monotonic() - started) * 1000)
    sketch = view.get("sketch") or {}
    if "sketch" not in sent and sketch.get("state") in _SKETCH_SETTLED:
        sent.add("sketch")
        yield {"event": "sketch", "sketch_state": _SKETCH_SETTLED[sketch["state"]],
               "grain": None, "fallback_used": sketch["state"] == "fallback",
               "tokens_in": None, "tokens_out": None, "elapsed_ms": elapsed}
    if "stage1" not in sent and view.get("document") is not None:
        sent.add("stage1")
        options = _service().execution(owner, view["execution_id"]).context.get("host_options", {})
        yield {"event": "stage1", "ddl": view["document"]["source"], "thinking": None,
               "stage1_model": options.get("stage1_model"), "stage2_model": options.get("stage2_model"),
               "tokens_in": None, "tokens_out": None, "elapsed_ms": elapsed}
    score = (view.get("delivery") or {}).get("score")
    if "score" not in sent and score is not None:
        sent.add("score")
        options = _service().execution(owner, view["execution_id"]).context.get("host_options", {})
        yield {"event": "score", "instruction_count": len(score.get("instructions") or []),
               "stage2_model": options.get("stage2_model"),
               "tokens_in": None, "tokens_out": None, "elapsed_ms": elapsed}
    # Each provider attempt as it begins, and its end once no other follows,
    # so a timed-out attempt reads as a retry rather than a slow answer.
    attempt = view.get("provider_attempt")
    running = f"attempt:{attempt['action']}:{attempt['attempt']}" if attempt else None
    reported = next((key for key in sent if key.startswith("attempt:")), None)
    if running != reported:
        sent.discard(reported)
        if running is not None:
            sent.add(running)
        shown = None if attempt is None else {key: attempt[key] for key in ("action", "attempt", "max_attempts")}
        yield {"event": "attempt", "provider_attempt": shown, "elapsed_ms": elapsed}


def paint_events(owner: str, data: dict[str, Any], idempotency_key: str | None) -> Iterator[dict]:
    """The same drawing as `paint`, reporting each layer as it settles (SPEC §12.10).

    Nothing runs until the first event is pulled, so a refusal before the
    execution starts (a label-only description, a full pool) is raised to the
    caller, which can still answer with that HTTP status.
    """
    if idempotency_key:
        replay = _history_replay(owner, idempotency_key, data)
        if replay is not None:
            yield {"event": "done", **replay}
            return
    started = time.monotonic()
    view = _start_paint(owner, data, idempotency_key)
    service = _service()
    sent: set[str] = set()
    last_line = time.monotonic()
    try:
        while True:
            for event in _progress(owner, view, started, sent):
                last_line = time.monotonic()
                yield event
            if not view.get("busy"):
                break
            if time.monotonic() - last_line >= _WAIT_EVENT_SECONDS:
                last_line = time.monotonic()
                yield {"event": "wait", "elapsed_ms": int((last_line - started) * 1000)}
            time.sleep(_POLL_SECONDS)
            view = service.get(owner, view["variation_id"])
        view = _settled(owner, view, perform=True)
        yield from _progress(owner, view, started, sent)
    except GeneratorExit:
        _end_abandoned_run(owner, view)
        raise
    yield {"event": "done", **view["result"], **_identity(view)}


def _end_abandoned_run(owner: str, view: dict) -> None:
    """Cancel the run of a stream whose reader has gone (a stop, a closed page).

    Otherwise the run kept a pipeline worker and went on calling the model
    through every retry, and a retry of the same request started a second run.
    Closing the stream must not raise, so a failure here is only logged.
    """
    try:
        service = _service()
        current = service.get(owner, view["variation_id"])
        if current.get("busy"):
            service.command(owner, current["execution_id"], {"tag": "cancel"})
    except Exception:  # noqa: BLE001
        _logger.warning("paint stream: could not cancel the abandoned run", exc_info=True)
