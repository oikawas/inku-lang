"""The composition's theses to choose from (step 4 of the thesis handle, 2026-11-14).

The shared core builds the request that asks for four theses for a work's
description and checks the answer (``composition_theses.rs``, action
``request`` and ``answer``); the Server sends it under the work's connection
with the model the author chose (``typed_send.py``) and asks once more with the
core's problems when the first answer is refused. The author then draws the
description with one thesis fixed (``RunOptions.composition_thesis``, with
``composition_thesis_source="proposed"`` and the digest returned here).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException

from .description_labels import pipeline_description
from .pipeline_candidate import CandidateHostError
from .typed_send import SendStopped, send_typed, typed_request_digest

#: The prompt id the core names for the request.
THESES_PROMPT_ID = "inku.description-theses-prompt.v1"


class ThesesRefused(Exception):
    """The request could not be made, sent or answered; ``code`` says why."""

    def __init__(self, status: int, code: str, **detail: Any) -> None:
        super().__init__(code)
        self.status, self.code, self.detail = status, code, detail


def _core(request: dict) -> dict:
    from inku_render import _native as native

    return json.loads(native.pipeline_composition_theses(json.dumps(request, ensure_ascii=False).encode("utf-8")))


def current_thesis(item: dict) -> str | None:
    """The work's thesis: its own composition's, or the one it keeps from an ancestor."""
    for record in ((item.get("description_ddl") or {}).get("composition") or {},
                   item.get("composition_inherited") or {}):
        thesis = (record.get("answer") or {}).get("thesis")
        if isinstance(thesis, str) and thesis.strip():
            return thesis.strip()
    return None


def propose_theses(owner: str, item: dict, model: str) -> dict:
    """Four theses for ``item``'s description, drawn up by ``model`` under the work's connection,
    with the digest of the request whose answer gave them."""
    from .pipeline_api import saved_work_parent
    from .pipeline_runtime import get_service
    from .chatgpt_runtime import retire_execution

    description = pipeline_description(item.get("source_text") or item.get("input") or "").strip()
    record = item.get("description_ddl") or {}
    if not description or not record:
        # Only a read-and-draw work keeps the record a thesis is drawn with.
        raise ThesesRefused(422, "not_a_read_and_draw_work")
    language = item.get("instruction_lang_resolved") or "ja"
    if language not in ("ja", "en"):
        language = "ja"
    ask: dict[str, Any] = {"action": "request", "description": description, "language": language}
    if isinstance(record.get("reading"), dict):
        ask["reading"] = record["reading"]
    thesis = current_thesis(item)
    if thesis is not None:
        ask["current_thesis"] = thesis
    service = get_service()
    options = {"stage1_model": model, "stage2_model": model, "catalog_mode": "fixed", "ui_lang": language}
    try:
        _, source_work = saved_work_parent(service.store, owner, item["id"])
        _, context = service.prepare_for(owner, "direct_ddl", str(item.get("ddl") or ""), options, source_work)
    except CandidateHostError as error:
        raise ThesesRefused(422, str(error)) from error
    execution_id = f"theses:{uuid.uuid4().hex}"
    try:
        for attempt in (1, 2):
            made = _core(ask)
            if made.get("outcome") != "ok":
                raise ThesesRefused(422, str(made.get("reason") or made.get("error") or "invalid_request"))
            request = made["request"]
            try:
                text, failure = send_typed(owner, context, request, execution_id=execution_id,
                                           prompt_id=THESES_PROMPT_ID, action_id=f"{execution_id}-{attempt}",
                                           language=language)
            except SendStopped as error:
                raise ThesesRefused(409, "stopped") from error
            if failure is not None:
                raise ThesesRefused(502, "provider_failed", failure=failure)
            checked = _core({"action": "answer", "answer": text or "", "language": language,
                             **({"current_thesis": thesis} if thesis is not None else {})})
            if checked.get("outcome") == "ok":
                return {"theses": checked["theses"], "prompt_digest": typed_request_digest(request), "model": model,
                        "current_thesis": thesis}
            problems = list(checked.get("problems") or [checked.get("detail") or "invalid_answer"])
            ask["feedback"] = {"rejected_answer": text or "", "problems": problems}
        raise ThesesRefused(502, "invalid_answer", problems=problems)
    finally:
        retire_execution(owner, execution_id)


def propose_theses_http(owner: str, item: dict, model: str) -> dict:
    """``propose_theses`` with its refusals as HTTP errors."""
    try:
        return propose_theses(owner, item, model)
    except ThesesRefused as error:
        raise HTTPException(error.status, {"code": error.code, **error.detail}) from error
