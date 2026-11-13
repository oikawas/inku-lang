"""Sending one typed request the shared core built: a system prompt, a message and the answer's JSON schema.

The shared core's JSON entries (``chunk_moves_json`` and the like) build a
request and check its answer; the host only sends it. This is how the Server
sends one, as the AI refinement's chunk moves sent theirs (``autonomous_refine.py``,
removed on 2026-11-13; the author kept what the thesis-handle work uses):

- under the action the ordinary drawing's Stage 1 sends as
  (``generate_normalized_ddl``, which ``pipeline_provider.py`` reads as
  ``normalized_ddl_generated``), with five minutes to answer;
- with the request's digest (system, message, schema and action) as its
  identity, and the prompt's id, digest and language for the pipeline's record
  of a sent system prompt (the provider body leaves them out);
- once more, a moment later, after a failure that may pass;
- under an execution key the caller owns: the caller retires it
  (``chatgpt_runtime.retire_execution``) when it is done, and cancels it
  (``cancel_execution``) to stop a send that is out.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

#: What a typed request is sent as: the ordinary drawing's Stage 1 action.
TYPED_SEND_ACTION = "generate_normalized_ddl"
#: How long one request may take.
TYPED_SEND_TIMEOUT_MS = 300_000
#: The failures after which a request is sent once more, a moment later.
TRANSIENT_FAILURES = frozenset({"rate_limited", "transport_timeout", "transport_unavailable"})
RESEND_SECONDS = 2.0


class SendStopped(Exception):
    """The caller's stop was set before the answer was taken."""


def _prompt(request: dict[str, Any]) -> dict[str, Any]:
    return {"system": request["system"], "message": request["text"],
            "response_schema": request["response_schema"], "action_name": TYPED_SEND_ACTION}


def typed_request_digest(request: dict[str, Any]) -> str:
    """The digest ``send_typed`` sends ``request`` under (and records as its prompt's digest)."""
    prompt = _prompt(request)
    return "sha256:" + hashlib.sha256(json.dumps(prompt, ensure_ascii=False, sort_keys=True,
                                                 separators=(",", ":")).encode("utf-8")).hexdigest()


def send_typed(owner: str, context: dict[str, Any], request: dict[str, Any], *, execution_id: str,
               prompt_id: str, action_id: str, language: str,
               stop: threading.Event | None = None) -> tuple[str | None, str | None]:
    """Send ``request`` (``system``, ``text``, ``response_schema``) under ``context``'s provider:
    the answer's text and no failure, or no text and the failure."""
    from .chatgpt_runtime import execution_cancel
    from .pipeline_runtime import get_service

    stop = stop if stop is not None else threading.Event()
    prompt = _prompt(request)
    digest = typed_request_digest(request).removeprefix("sha256:")
    prompt.update(prompt_id=prompt_id, prompt_digest=f"sha256:{digest}", instruction_language=language)
    execution_cancel(owner, execution_id, chatgpt=bool(context.get("host_options", {}).get("chatgpt_profile")))
    perform = get_service().provider_with_context(owner, {**context, "execution_id": execution_id}, None)
    failure = None
    for attempt in (1, 2):
        if stop.is_set():
            raise SendStopped
        action = {"tag": TYPED_SEND_ACTION, "timeout_ms": str(TYPED_SEND_TIMEOUT_MS), "payload": {"prompt": prompt},
                  "identity": {"action_id": action_id, "attempt": attempt, "request_digest": digest}}
        result = perform(action)
        if stop.is_set():
            raise SendStopped
        if result["tag"] != "provider_failed":
            return str(result.get("response") or ""), None
        failure = str(result.get("failure") or "provider_failed")
        if failure not in TRANSIENT_FAILURES or stop.wait(RESEND_SECONDS):
            break
    return None, failure
