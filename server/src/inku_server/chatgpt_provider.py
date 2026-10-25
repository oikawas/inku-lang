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

import httpx

from .chatgpt_auth import RESOURCE, access_token, read_limited
from .chatgpt_runtime import check_session, guarded
from .chatgpt_store import ChatGPTError, CredentialStore
from .chatgpt_models import publication
from . import provider_wire

logger = logging.getLogger(__name__)

EFFECTS = {"generate_sketch", "select_description_catalog", "generate_normalized_ddl", "read_composition", "choose_laws",
           "choose_colors", "complete_visible_ddl_holes", "read_description", "write_description_ddl"}
# The codes a stored diagnostic may keep (pipeline_candidate). The shared core
# classifies failures with the same list.
PUBLIC_CODES = {
    "subscription_sharing_usage_limit_exceeded", "subscription_sharing_user_not_eligible",
    "subscription_sharing_unsupported_capability", "subscription_sharing_route_not_supported",
    "subscription_sharing_invalid_user", "chatpass_v2_scope_not_authorized",
    "chatpass_v2_invalid_authorization_context", "subscription_sharing_usage_unavailable",
    "subscription_sharing_user_unavailable",
}


class ResponseFailure(ChatGPTError):
    """A failure the ChatGPT backend reported, as the shared core classified it."""

    def __init__(self, answer: dict):
        super().__init__(answer["code"], failure=answer["failure"], action=answer["action"])
        self.status = answer.get("status")
        self.request_id = answer.get("request_id")
        self.param = answer.get("param")


def safe_identifier(value) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:\[\]-]{1,160}", value) else None


def response_error(value, status: int | None = None, request_id: str | None = None) -> ResponseFailure:
    # The shared core reads an HTTP error body, a response.failed event and a
    # stream's `error` event alike (provider_wire), so a usage limit sent any
    # of those ways still pauses the plan.
    return ResponseFailure(provider_wire.chatgpt_error(value, status, request_id))


def pause_quota(owner: str, profile_id: str, generation: int, deadline: float) -> None:
    store = CredentialStore()
    with store.lock("edit:" + owner, deadline):
        saved = store.read(owner)
        profile = saved["profiles"].get(profile_id)
        if profile and profile["generation"] == generation and profile["state"] != "quota":
            profile["state"] = "quota"
            profile.pop("catalog", None)
            store.write(owner, saved)


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
            raise ChatGPTError("chatgpt_response_too_large")

    def finish(self) -> str:
        answer = provider_wire.chatgpt_stream(self.mode, self.argument_limit, bytes(self.wire))
        self.completed, self.terminal = answer["completed"], answer["terminal"]
        if answer["outcome"] == "answer":
            return answer["text"]
        if answer["outcome"] == "malformed":
            # As the stream's own decoding failed: bytes that were not UTF-8
            # raised a ValueError, other shapes a TypeError or KeyError.
            raise (ValueError if answer["kind"] == "utf8" else TypeError)(f"chatgpt stream is malformed: {answer['kind']}")
        if answer.get("reported"):
            raise ResponseFailure(answer)
        if answer.get("tool_shapes") is not None:
            # Tool metadata explains protocol failures without logging text or arguments.
            logger.warning("chatgpt_tool_shape %s streamed_calls=%d finalized_calls=%d",
                           json.dumps(answer["tool_shapes"], separators=(",", ":")),
                           answer["streamed_calls"], answer["finalized_calls"])
        raise ChatGPTError(answer["code"], failure=answer["failure"], action=answer["action"])


class TextSSEDecoder(SSEDecoder):
    """Vision accepts completed assistant text, never partial text or tool calls."""

    mode = "text"


async def catalog(owner: str, profile_id: str, generation: int, deadline: float, cancel=None, *, force: bool = False, _wire_held: bool = False) -> list[dict]:
    def check():
        return check_session(owner, profile_id, generation, cancel)
    profile = check()
    cache = profile.get("catalog")
    if not force and cache and cache["expires_at"] > time.time():
        return publication(profile, cache["models"])["models"]
    # A current, validated catalog is local data. Only a refresh needs the
    # wire slot held by inference; recheck both session and cache after waiting.
    if not _wire_held:
        with CredentialStore().lock("wire:" + owner + ":" + profile_id, deadline, check):
            return await catalog(owner, profile_id, generation, deadline, cancel, force=force, _wire_held=True)
    token = await access_token(owner, profile_id, generation, deadline, cancel)
    async with httpx.AsyncClient(follow_redirects=False) as client:
        stream = client.stream("GET", RESOURCE + "/models", headers={"Authorization": "Bearer " + token},
                               timeout=max(0.001, deadline - time.monotonic()))
        response = await guarded(stream.__aenter__(), check, deadline)
        try:
            content = await read_limited(response, check, deadline, 1024 * 1024)
        finally:
            await stream.__aexit__(None, None, None)
    value = json.loads(content)
    if not response.is_success:
        error = response_error(value, response.status_code, response.headers.get("x-request-id"))
        if error.code == "subscription_sharing_usage_limit_exceeded":
            pause_quota(owner, profile_id, generation, deadline)
        raise error
    listed = provider_wire.chatgpt_catalog(value)
    if listed["outcome"] != "ok":
        raise KeyError("models")
    models = listed["models"]
    store = CredentialStore()
    with store.lock("edit:" + owner, deadline, check):
        profile = check()
        profile["catalog"] = {"expires_at": time.time() + 300, "models": models}
        # The caller holds the edit lock; atomic write preserves other accounts.
        saved = store.read(owner)
        saved["profiles"][profile_id] = profile
        store.write(owner, saved)
    return publication(profile, models)["models"]


async def request(owner: str, profile_id: str, generation: int, model: str, action: dict, deadline: float,
                  limit: int, cancel=None, observation=None, *, purpose: str = "llm",
                  transport: httpx.AsyncBaseTransport | None = None, images: list[str] | None = None,
                  usage: list | None = None) -> str:
    image_effect = action["tag"] in provider_wire.IMAGE_EFFECTS
    if (purpose == "llm" and action["tag"] not in EFFECTS) or (purpose == "vision" and action["tag"] != "vision" and not image_effect) or purpose not in {"llm", "vision"}:
        raise ChatGPTError("chatgpt_operation_not_supported")

    def capture_body(body: bytes) -> bytes:
        return provider_wire.observation_digest(body) if image_effect else body

    prompt = action["payload"]["prompt"]
    # Validate image references before catalog refresh or any other HTTP call.
    built = (provider_wire.chatgpt_request(model, prompt, limit, images=images) if image_effect else None)
    def check():
        return check_session(owner, profile_id, generation, cancel)
    store = CredentialStore()
    with store.lock("wire:" + owner + ":" + profile_id, deadline, check):
        try:
            models = await catalog(owner, profile_id, generation, deadline, cancel, _wire_held=True)
            if not any(entry["id"] == model and entry["enabled"] and purpose in entry["purposes"] for entry in models):
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
                    stream = client.stream("POST", RESOURCE + "/responses", content=built["body"].encode("utf-8"),
                                           headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                                           timeout=max(0.001, deadline - time.monotonic()))
                    response = await guarded(stream.__aenter__(), check, deadline)
                    status = response.status_code
                    try:
                        if not response.is_success:
                            content = await read_limited(response, check, deadline, 64 * 1024)
                            if observation and image_effect:
                                raw.extend(content)
                            raise response_error(json.loads(content), status, response.headers.get("x-request-id"))
                        iterator = response.aiter_bytes()
                        while True:
                            try:
                                chunk = await guarded(anext(iterator), check, deadline)
                            except StopAsyncIteration:
                                break
                            if observation:
                                raw.extend(chunk[:max(0, decoder.wire_limit + 1 - len(raw))])
                            decoder.feed(chunk)
                        check()
                        return decoder.finish()
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
            if error.code == "subscription_sharing_usage_limit_exceeded":
                pause_quota(owner, profile_id, generation, deadline)
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
        models = asyncio.run(catalog(owner, profile_id, generation, time.monotonic() + 15))
        return any(entry["id"] == model and entry["enabled"] and purpose in entry["purposes"] for entry in models)
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
        # Unable to check is not evidence that a model is absent. Preserve
        # explicit registration/provider refusals; let the host report them.
        raise ChatGPTError("chatgpt_transport_unavailable") from None
