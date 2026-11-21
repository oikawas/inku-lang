"""Responses/SSE adapter for shared-pipeline effects; no retries.

The bodies, the reading of the stream, the failure codes and the model list are
the shared core's (provider_wire). This module holds the token, the
registration's locks, cancellation, the pause on a usage limit and the
observation records.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from contextlib import ExitStack

import httpx

from .chatgpt_auth import access_token, auth_policy, read_limited, run_flow
from .chatgpt_runtime import check_session, guarded, session_checker
from .chatgpt_store import ChatGPTError, CredentialStore
from .chatgpt_models import offered as model_offered, publication
from . import provider_wire

logger = logging.getLogger(__name__)
wire_wait_logger = logger.getChild("wire_wait")
# Record successful waits at INFO even when the root logger defaults to WARNING.
wire_wait_logger.setLevel(logging.INFO)

# The codes a stored diagnostic may keep (pipeline_candidate) and the next
# actions it may name: the shared core's lists, which classify the failures.
_CONSTANTS = auth_policy("constants")
PUBLIC_CODES = frozenset(_CONSTANTS["public_codes"])
FAILURE_ACTIONS = frozenset(_CONSTANTS["failure_actions"])


class ResponseFailure(ChatGPTError):
    """A failure the ChatGPT backend reported, as the shared core classified it."""

    def __init__(self, answer: dict):
        super().__init__(answer["code"], failure=answer["failure"], action=answer["action"], diagnostic=answer.get("diagnostic"))
        self.status = answer.get("status")
        self.request_id = answer.get("request_id")
        self.param = answer.get("param")


def safe_identifier(value) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:\[\]-]{1,160}", value) else None


def response_error(value=None, status: int | None = None, request_id: str | None = None, *, body: str | None = None) -> ResponseFailure:
    # The shared core reads an HTTP error body, a response.failed event and a
    # stream's `error` event alike (provider_wire), so a usage limit sent any
    # of those ways still pauses the plan. An HTTP error passes its text as
    # received (`body`); text that is not JSON is read by its status alone.
    return ResponseFailure(provider_wire.chatgpt_error(value, status, request_id, body=body))


def transport_error(kind: str) -> ChatGPTError:
    """A failure of the transport itself (`timeout`, `unavailable`, `too_large`), as the shared core names it."""
    named = provider_wire.chatgpt_transport(kind)
    return ChatGPTError(named["code"], failure=named["failure"], action=named["action"])


def _text(content: bytes) -> str:
    # As received: the core reads text that is not JSON (or not UTF-8) as such.
    return content.decode("utf-8-sig", errors="replace")


def pause_quota(owner: str, profile_id: str, generation: int, deadline: float) -> None:
    """The core's `pause` procedure: the registration read again under the edit lock.

    Called outside an event loop (a send calls it through a thread).
    """
    asyncio.run(run_flow("pause", {"profile_id": profile_id, "generation": generation,
                                   "deadline": time.time() + (deadline - time.monotonic())},
                         owner, store=CredentialStore()))


class SSEDecoder:
    """The stream, received whole and read once by the shared core (provider_wire).

    Only the wire as a whole is bounded here, as it arrives; the core holds each
    event and the arguments to their limits and reads the events in order, so
    the answer is the one an incremental reader gave however the bytes came.
    """

    mode = "pipeline"

    def __init__(self, argument_limit: int):
        self.argument_limit = argument_limit
        limits = provider_wire.chatgpt_limits(argument_limit)
        self.wire_limit, self.event_limit = limits["wire_limit"], limits["event_limit"]
        self.wire = bytearray()
        self.completed = False
        self.terminal = None

    def feed(self, chunk: bytes) -> None:
        self.wire.extend(chunk)
        if len(self.wire) > self.wire_limit:
            raise transport_error("too_large")

    def finish(self, *, status: int | None = None, request_id: str | None = None) -> str:
        answer = provider_wire.chatgpt_stream(self.mode, self.argument_limit, bytes(self.wire), status=status, request_id=request_id)
        self.completed, self.terminal = answer["completed"], answer["terminal"]
        if answer["outcome"] == "answer":
            return answer["text"]
        if answer.get("reported"):
            raise ResponseFailure(answer)
        if answer.get("tool_shapes") is not None:
            # Tool metadata explains protocol failures without logging text or arguments.
            logger.warning("chatgpt_tool_shape %s streamed_calls=%d finalized_calls=%d",
                           json.dumps(answer["tool_shapes"], separators=(",", ":")),
                           answer["streamed_calls"], answer["finalized_calls"])
        raise ChatGPTError(answer["code"], failure=answer["failure"], action=answer["action"], diagnostic=answer.get("diagnostic"))


class TextSSEDecoder(SSEDecoder):
    """Vision accepts completed assistant text, never partial text or tool calls."""

    mode = "text"


class _AdmissionCatalogAvailable(Exception):
    def __init__(self, profile: dict, models: list[dict]):
        self.profile = profile
        self.models = models


async def catalog(owner: str, profile_id: str, generation: int, deadline: float, cancel=None, *,
                  force: bool = False, _wire_held: bool = False, _admission: bool = False) -> list[dict]:
    # The core's `catalog` procedure: a current list is local data; a refresh
    # takes the wire slot inference holds (a send passes it held), refreshes the
    # token, asks for the list, pauses the plan on a usage limit, and keeps the
    # list in the registration read again under the edit lock.
    check = session_checker(owner, profile_id, generation, cancel, validate=check_session)
    check()

    def use_saved_catalog():
        # The core already asked for a refresh. Only actual wire contention
        # permits this admission to use the last list for the pinned profile.
        profile = check(force=True)
        saved = profile.get("catalog")
        if isinstance(saved, dict) and isinstance(saved.get("models"), list):
            raise _AdmissionCatalogAvailable(profile, saved["models"])

    try:
        listed = await run_flow("catalog", {"profile_id": profile_id, "generation": generation, "force": force,
                                            "deadline": time.time() + (deadline - time.monotonic())},
                                owner, store=CredentialStore(), check=check, held=("wire",) if _wire_held else (),
                                on_wire_busy=use_saved_catalog if _admission else None)
    except _AdmissionCatalogAvailable as saved:
        return publication(saved.profile, saved.models)["models"]
    return publication(check(), listed["models"])["models"]


async def request(owner: str, profile_id: str, generation: int, model: str, action: dict, deadline: float | None,
                  limit: int, cancel=None, observation=None, *, purpose: str = "llm",
                  transport: httpx.AsyncBaseTransport | None = None, images: list[str] | None = None,
                  usage: list | None = None, on_bytes=None, on_wire_wait_finished=None,
                  on_request_saved=None) -> str:
    image_effect = auth_policy("operation", purpose=purpose, tag=action["tag"])["image_effect"]

    def capture_body(body: bytes) -> bytes:
        return provider_wire.observation_digest(body) if image_effect else body

    prompt = action["payload"]["prompt"]
    # Validate image references before catalog refresh or any other HTTP call.
    built = (provider_wire.chatgpt_request(model, prompt, limit, images=images) if image_effect else None)
    check = session_checker(owner, profile_id, generation, cancel, validate=check_session)
    store = CredentialStore()
    with ExitStack() as stack:
        wait_started = time.monotonic()
        try:
            stack.enter_context(store.lock("wire:" + owner + ":" + profile_id, deadline, check))
        finally:
            wait_finished = time.monotonic()
            if deadline is None:
                wire_wait_logger.info("chatgpt_wire_wait action_id=%s attempt=%s wait_ms=%d",
                                      action["identity"]["action_id"], action["identity"]["attempt"],
                                      max(0, int((wait_finished - wait_started) * 1000)))
                if on_wire_wait_finished is not None:
                    on_wire_wait_finished(wait_finished)
        if deadline is None:
            # Pipeline attempts start their budget when the communication lock is acquired.
            deadline = wait_finished + int(action["timeout_ms"]) / 1000
        try:
            models = await catalog(owner, profile_id, generation, deadline, cancel, _wire_held=True)
            if not model_offered(models, model, purpose):
                raise ChatGPTError("chatgpt_model_not_offered")
            token = await access_token(owner, profile_id, generation, deadline, cancel)
            # The shared core writes the body (provider_wire); the observation
            # keeps its canonical form, as it did.
            if built is None:
                built = (provider_wire.chatgpt_vision_request(model, **prompt, answer_limit=limit) if action["tag"] == "vision"
                         else provider_wire.chatgpt_request(model, prompt, limit, images=images))
            if observation:
                from .pipeline_provider import provider_stage_record
                capture, execution = observation
                truncated = capture.request(owner, execution, action, provider_stage_record(action["tag"]), "chatgpt", model,
                                            capture_body(built["canonical"].encode()))
                if on_request_saved is not None:
                    on_request_saved(truncated)
                if truncated:
                    raise ChatGPTError("chatgpt_observation_incomplete")
            decoder = TextSSEDecoder(limit) if action["tag"] == "vision" else SSEDecoder(limit)
            raw = bytearray()
            status = 0
            try:
                client_options = {"follow_redirects": False}
                if transport is not None:
                    client_options["transport"] = transport
                async with httpx.AsyncClient(**client_options) as client:
                    check()
                    # Where it goes, its headers and the error limit are the shared core's (step 4, 2026-11-14).
                    stream = client.stream(built["method"], built["url"], content=built["body"].encode("utf-8"),
                                           headers=provider_wire.headers(built, token),
                                           timeout=max(0.001, deadline - time.monotonic()))
                    response = await guarded(stream.__aenter__(), check, deadline)
                    status = response.status_code
                    request_id = response.headers.get(built["request_id_header"])
                    try:
                        if not response.is_success:
                            content = await read_limited(response, check, deadline, built["error_limit"])
                            if observation and image_effect:
                                raw.extend(content)
                            raise response_error(status=status, request_id=request_id,
                                                 body=_text(content))
                        async def consume():
                            received = 0
                            reported = 0
                            async for chunk in response.aiter_bytes():
                                if observation:
                                    raw.extend(chunk[:max(0, decoder.wire_limit + 1 - len(raw))])
                                decoder.feed(chunk)
                                received += len(chunk)
                                if on_bytes is not None and received // 4096 > reported // 4096:
                                    reported = received
                                    on_bytes(received)
                            return decoder.finish(status=status, request_id=request_id)
                        try:
                            answer = await guarded(consume(), check, deadline)
                        except (TimeoutError, httpx.TransportError) as error:
                            kind = "timeout" if isinstance(error, (TimeoutError, httpx.TimeoutException)) else "unavailable"
                            failure = transport_error(kind)
                            partial = provider_wire.chatgpt_stream(
                                decoder.mode, decoder.argument_limit, bytes(decoder.wire),
                                status=status, request_id=request_id,
                            ).get("diagnostic", {})
                            failure.diagnostic = {key: partial[key] for key in ("status", "request_id", "event_count", "last_event") if key in partial}
                            raise failure from None
                        check(force=True)
                        return answer
                    finally:
                        await stream.__aexit__(None, None, None)
            finally:
                # The terminal response carries usage whether or not its answer was read.
                if usage is not None and isinstance(decoder.terminal, dict):
                    usage.append(provider_wire.usage("openai_responses", json.dumps(decoder.terminal).encode("utf-8")))
                if observation and status:
                    capture.response(owner, execution, action, status=status, raw=capture_body(bytes(raw)), truncated=not decoder.completed,
                                     decoded=None if image_effect else decoder.terminal)
        except ResponseFailure as error:
            if image_effect:
                error.request_id, error.param = safe_identifier(error.request_id), safe_identifier(error.param)
            if auth_policy("quota_failure", code=error.code)["pause"]:
                await asyncio.to_thread(pause_quota, owner, profile_id, generation, deadline)
            raise


async def request_vision(owner: str, profile_id: str, generation: int, model: str, *,
                         system: str, text: str, images: list[str], deadline: float,
                         transport: httpx.AsyncBaseTransport | None = None) -> str:
    action = {"tag": "vision", "payload": {"prompt": {"system": system, "text": text, "images": images}}}
    return await request(owner, profile_id, generation, model, action, deadline, 512 * 1024,
                         purpose="vision", transport=transport)


def pin(owner: str) -> tuple[str, int]:
    from .chatgpt_runtime import check_owner
    check_owner(owner)
    profile = CredentialStore().profile(owner)
    check_session(owner, profile["id"], profile["generation"])
    return profile["id"], profile["generation"]


def offered(owner: str, model: str, *, profile_id: str | None = None, generation: int | None = None, purpose: str = "llm") -> bool:
    try:
        if profile_id is None or generation is None:
            profile_id, generation = pin(owner)
        models = asyncio.run(catalog(owner, profile_id, generation, time.monotonic() + 15, _admission=True))
        return model_offered(models, model, purpose)
    except (TimeoutError, httpx.TimeoutException):
        # Unable to check is not evidence that a model is absent. Preserve
        # explicit registration/provider refusals; let the host report them.
        raise transport_error("timeout") from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise transport_error("unavailable") from None
