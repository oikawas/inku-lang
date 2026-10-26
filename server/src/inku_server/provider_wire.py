"""Provider request bodies and the reading of their answers, from the shared core.

How a prompt becomes a request body for each provider dialect (the thinking
level a model takes, the room left for thinking it does unasked, whether a
temperature may be sent, the tool's shape, the order a schema's properties are
written in) and how the answer is taken back out of the response were written
in Server, Android and Swift alike, and every provider change landed three
times. The rules now live in the shared core
(``inku-pipeline/src/provider_wire.rs``), which writes the bodies byte for byte
as Server wrote them; ``server/tests/data/provider-wire-cases.json`` holds the
rows every host checks. This module carries a request to the core and its
answer back. The key never reaches the core: it is added here under the header
the core names.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
from functools import lru_cache
from types import ModuleType
from typing import Any

# A refusal body is read only this far.
_REFUSAL_READ_BYTES = 16384
# The effects that send an image. Read and draw's review sends its drawing.
IMAGE_EFFECTS = frozenset({"select_image_catalog", "write_image_ddl", "review_image_ddl", "review_description_ddl"})
# Read and draw's requests (SPEC §12.6.7), recorded apart from Stage 1 and the
# image tab: the reading, the composition and laws when they are on, the
# writing and the review.
READ_AND_DRAW_EFFECTS = frozenset({"read_description", "compose_description", "write_description_ddl",
                                   "review_description_ddl"})


def observation_digest(body: bytes) -> bytes:
    """Image transport observations retain only the body's digest and size."""
    return json.dumps({"capture": "digest_only", "sha256": hashlib.sha256(body).hexdigest(),
                       "byte_len": len(body)}, separators=(",", ":")).encode("ascii")


class ProviderWireRefused(ValueError):
    """The core built no request; ``detail`` says why, as Server's ValueError did."""

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@lru_cache(maxsize=1)
def _native() -> ModuleType:
    return importlib.import_module("inku_render")


def _ask(action: str, **fields: Any) -> dict:
    # NaN passes: an error body json.loads read may hold one, and the core reads it as Python does.
    request = json.dumps({"action": action, **fields}, ensure_ascii=False).encode("utf-8")
    answer = json.loads(_native().pipeline_provider_wire(request))
    if "error" in answer:
        raise RuntimeError(f"provider wire request failed: {answer['error']}")
    if answer.get("outcome") == "refused":
        raise ProviderWireRefused(str(answer.get("reason")), str(answer.get("detail")))
    return answer


def _connection(connection: dict) -> dict:
    return {"id": str(connection.get("id") or ""), "kind": str(connection.get("kind") or ""),
            "api_profile": str(connection.get("api_profile") or ""), "base_url": str(connection.get("base_url") or "")}


def pipeline_request(connection: dict, model: str, prompt: dict, max_tokens: int, *, images: list[str] | None = None) -> dict:
    """The request for one pipeline effect: url, headers, auth, format, output_budget, body."""
    return _ask("pipeline_request", connection=_connection(connection), model=model,
                prompt={key: prompt[key] for key in ("system", "message", "response_schema", "action_name", "images") if key in prompt},
                max_tokens=max_tokens, **({"images": list(images)} if images is not None else {}))


def text_request(connection: dict, model: str, *, system: str, text: str, images: list[str],
                 temperature: float, max_tokens: int) -> dict:
    """The request for one text answer, with images when there are any."""
    return _ask("text_request", connection=_connection(connection), model=model, system=system, text=text,
                images=list(images), temperature=temperature, max_tokens=max_tokens)


def chatgpt_request(model: str, prompt: dict, answer_limit: int, *, images: list[str] | None = None) -> dict:
    """The ChatGPT plan's body for one pipeline effect: body, canonical, wire_limit, event_limit."""
    return _ask("chatgpt_request", model=model, answer_limit=answer_limit,
                prompt={key: prompt[key] for key in ("system", "message", "response_schema", "action_name", "images") if key in prompt},
                **({"images": list(images)} if images is not None else {}))


def chatgpt_vision_request(model: str, *, system: str, text: str, images: list[str], answer_limit: int) -> dict:
    """The ChatGPT plan's Vision body; an image that is not a base64 data URL is refused."""
    return _ask("chatgpt_vision_request", model=model, system=system, text=text, images=list(images),
                answer_limit=answer_limit)


def chatgpt_limits(answer_limit: int) -> dict:
    """The stream and event limits for an answer limit."""
    return _ask("chatgpt_limits", answer_limit=answer_limit)


def chatgpt_stream(mode: str, answer_limit: int, wire: bytes) -> dict:
    """The whole stream read once: ``answer`` with ``text``, ``failed`` or ``malformed``, with ``terminal``."""
    return _ask("chatgpt_stream", mode=mode, answer_limit=answer_limit,
                wire_base64=base64.b64encode(wire).decode("ascii"))


def chatgpt_error(value: Any, status: int | None, request_id: str | None) -> dict:
    """What an HTTP error from the ChatGPT backend says: code, failure, action, status, request_id, param."""
    return _ask("chatgpt_error", value=value, status=status, request_id=request_id)


@lru_cache(maxsize=256)
def chatgpt_failure(code: str, temporary: bool | None = None) -> dict:
    """The pipeline failure and next action the core's table gives a code."""
    return _ask("chatgpt_failure", code=code, temporary=temporary)


def chatgpt_catalog(value: Any) -> dict:
    """The models the backend lists for the subscriber: ``ok`` with ``models``, or ``malformed``."""
    return _ask("chatgpt_catalog", value=value)


def headers(request: dict, key: str) -> dict[str, str]:
    """The headers to send: the core's plain ones and the key under the header it names."""
    auth = request["auth"]
    return {**request["headers"], auth["header"]: auth["prefix"] + (key or auth["missing"])}


def _body_text(raw: bytes) -> str:
    # json.loads read bytes as UTF-8 and dropped a byte order mark; bytes that
    # are not UTF-8 raise UnicodeDecodeError, a ValueError, as they did there.
    return raw.decode("utf-8-sig")


def refusal(raw: bytes) -> dict[str, Any]:
    """What a refusal says, without anything that could carry a key."""
    try:
        text = raw[:_REFUSAL_READ_BYTES].decode("utf-8")
    except UnicodeDecodeError:
        return {}
    return _ask("pipeline_response", format="openai_chat", status=400, body=text)["refusal"]


def read_pipeline(format_name: str, status: int, raw: bytes) -> dict:
    """The answer to a pipeline response: ``answer`` with ``text``, ``cut`` with its record, or ``malformed``."""
    return _ask("pipeline_response", format=format_name, status=status, body=_body_text(raw))


def usage(format_name: str, raw: bytes) -> dict | None:
    """The tokens one send used: ``input_tokens`` (cache included), ``output_tokens``
    (thinking included) and ``cached_input_tokens``, or None when it reports none."""
    try:
        body = _body_text(raw)
    except UnicodeDecodeError:
        return None
    return _ask("usage", format=format_name, body=body)["usage"]


def read_text(format_name: str, status: int, raw: bytes) -> dict:
    """The answer to a text response: ``answer`` with ``text`` (and ``cut`` when it was cut off), or ``malformed``."""
    return _ask("text_response", format=format_name, status=status, body=_body_text(raw))
