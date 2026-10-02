"""Responses/SSE adapter for the four shared-pipeline effects; no retries."""

from __future__ import annotations

import asyncio
import json
import re
import time

import httpx

from .chatgpt_auth import RESOURCE, access_token, read_limited
from .chatgpt_runtime import check_session, guarded
from .chatgpt_store import ChatGPTError, CredentialStore, canonical

EFFECTS = {"generate_sketch", "select_description_catalog", "generate_normalized_ddl", "complete_visible_ddl_holes"}
PUBLIC_CODES = {
    "subscription_sharing_usage_limit_exceeded", "subscription_sharing_user_not_eligible",
    "subscription_sharing_unsupported_capability", "subscription_sharing_route_not_supported",
    "subscription_sharing_invalid_user", "chatpass_v2_scope_not_authorized",
    "chatpass_v2_invalid_authorization_context", "subscription_sharing_usage_unavailable",
    "subscription_sharing_user_unavailable",
}


class ResponseFailure(ChatGPTError):
    def __init__(self, code: str, *, status: int | None = None, request_id: str | None = None, param: str | None = None):
        temporary = code in {"subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable"} or (status is not None and status >= 500)
        super().__init__(code, failure="transport_unavailable" if temporary else "provider_rejected",
                         action="usage" if code == "subscription_sharing_usage_limit_exceeded" else "retry" if temporary else "diagnose")
        self.status = status
        self.request_id = safe_identifier(request_id)
        self.param = safe_identifier(param)


def safe_identifier(value) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:\[\]-]{1,160}", value) else None


def response_error(value: dict, status: int | None = None, request_id: str | None = None) -> ResponseFailure:
    error = value.get("error") or value.get("response", {}).get("error") or {}
    if not isinstance(error, dict):
        error = {}
    code = error.get("code")
    if code not in PUBLIC_CODES:
        code = "chatgpt_admission_rejected" if status in {401, 403} else "chatgpt_transport_unavailable" if status and status >= 500 else "chatgpt_response_failed"
    return ResponseFailure(code, status=status, request_id=request_id, param=error.get("param"))


def pause_quota(owner: str, profile_id: str, generation: int, deadline: float) -> None:
    store = CredentialStore()
    with store.lock("edit:" + owner, deadline):
        saved = store.read(owner)
        profile = saved["profiles"].get(profile_id)
        if profile and profile["generation"] == generation and profile["state"] != "quota":
            profile["state"] = "quota"
            profile.pop("catalog", None)
            store.write(owner, saved)


def request_body(model: str, prompt: dict) -> dict:
    return {"model": model, "store": False, "stream": True, "instructions": prompt["system"],
            "input": [{"role": "user", "content": prompt["message"]}],
            "tools": [{"type": "namespace", "name": "inku", "description": "Return data for the inku drawing pipeline.",
                       "tools": [{"type": "function", "name": "submit_pipeline_response", "description": "Return the requested drawing data.",
                                  "parameters": prompt["response_schema"], "strict": False}]}],
            "tool_choice": "required", "parallel_tool_calls": False}


class SSEDecoder:
    """Parse byte boundaries before UTF-8/JSON; cap wire, events and arguments separately."""

    def __init__(self, argument_limit: int):
        self.argument_limit = argument_limit
        self.event_limit = max(64 * 1024, argument_limit * 2 + 64 * 1024)
        self.wire_limit = max(1024 * 1024, argument_limit * 6 + 512 * 1024)
        self.wire_size = 0
        self.buffer = bytearray()
        self.items: dict[str, dict] = {}
        self.arguments: dict[str, str] = {}
        self.completed: str | None = None
        self.terminal = None

    def feed(self, chunk: bytes) -> None:
        self.wire_size += len(chunk)
        if self.wire_size > self.wire_limit:
            raise ChatGPTError("chatgpt_response_too_large")
        self.buffer.extend(chunk)
        while True:
            # CRLF and LF are both SSE line separators; a CR at the end of a
            # chunk remains untouched until the following byte arrives.
            match = re.search(rb"\r?\n\r?\n", self.buffer)
            if match is None:
                if len(self.buffer) > self.event_limit:
                    raise ChatGPTError("chatgpt_response_too_large")
                break
            raw = bytes(self.buffer[:match.start()])
            del self.buffer[:match.end()]
            if len(raw) > self.event_limit:
                raise ChatGPTError("chatgpt_response_too_large")
            data = b"\n".join(line[5:].lstrip(b" ") for line in raw.splitlines() if line.startswith(b"data:"))
            if data and data != b"[DONE]":
                self.event(json.loads(data.decode("utf-8")))

    def _function(self, item: dict) -> None:
        if item.get("type") != "function_call" or item.get("name") != "submit_pipeline_response" or item.get("namespace") != "inku":
            raise ChatGPTError("chatgpt_unexpected_tool")

    def event(self, event: dict) -> None:
        tag = event.get("type")
        if tag in {"error", "response.failed"}:
            self.terminal = event.get("response")
            raise response_error(event)
        if tag == "response.incomplete":
            raise ChatGPTError("chatgpt_response_incomplete", failure="transport_unavailable", action="retry")
        if "refusal" in str(tag):
            raise ChatGPTError("chatgpt_refused", action="edit")
        if self.terminal:
            raise ChatGPTError("chatgpt_response_invalid")
        if tag in {"response.output_item.added", "response.output_item.done"}:
            item = event["item"]
            if item.get("type") == "function_call":
                self._function(item)
                key = item["id"]
                if key not in self.items and self.items:
                    raise ChatGPTError("chatgpt_unexpected_tool")
                self.items[key] = item
            elif item.get("type") != "reasoning":
                raise ChatGPTError("chatgpt_unexpected_tool")
        elif tag == "response.function_call_arguments.delta":
            key = event["item_id"]
            if key not in self.items:
                raise ChatGPTError("chatgpt_response_invalid")
            value = self.arguments.get(key, "") + event["delta"]
            if len(value.encode()) > self.argument_limit:
                raise ChatGPTError("chatgpt_response_too_large")
            self.arguments[key] = value
        elif tag == "response.function_call_arguments.done":
            key = event["item_id"]
            if key not in self.items or (key in self.arguments and self.arguments[key] != event["arguments"]):
                raise ChatGPTError("chatgpt_response_invalid")
            if len(event["arguments"].encode()) > self.argument_limit:
                raise ChatGPTError("chatgpt_response_too_large")
            self.arguments[key] = event["arguments"]
        elif tag == "response.completed":
            response = event["response"]
            if response.get("status") != "completed":
                raise ChatGPTError("chatgpt_response_incomplete")
            output = response["output"]
            calls = [item for item in output if item.get("type") != "reasoning"]
            if len(calls) != 1:
                raise ChatGPTError("chatgpt_unexpected_tool")
            item = calls[0]
            self._function(item)
            arguments = item["arguments"]
            if item["id"] not in self.items or (self.arguments.get(item["id"], arguments) != arguments):
                raise ChatGPTError("chatgpt_response_invalid")
            if len(arguments.encode()) > self.argument_limit:
                raise ChatGPTError("chatgpt_response_too_large")
            if not isinstance(json.loads(arguments), dict):
                raise ChatGPTError("chatgpt_response_invalid")
            self.completed, self.terminal = arguments, response

    def finish(self) -> str:
        if self.buffer.strip() or self.completed is None:
            raise ChatGPTError("chatgpt_response_incomplete", failure="transport_unavailable", action="retry")
        return self.completed


async def catalog(owner: str, profile_id: str, generation: int, deadline: float, cancel=None, *, force: bool = False, _wire_held: bool = False) -> list[dict]:
    def check():
        return check_session(owner, profile_id, generation, cancel)
    if not _wire_held:
        with CredentialStore().lock("wire:" + owner + ":" + profile_id, deadline, check):
            return await catalog(owner, profile_id, generation, deadline, cancel, force=force, _wire_held=True)
    profile = check()
    cache = profile.get("catalog")
    if not force and cache and cache["expires_at"] > time.time():
        return cache["models"]
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
    models = [{"id": entry["slug"], "label": entry["display_name"], "purposes": ["llm"], "enabled": True}
              for entry in value["models"] if entry.get("visibility") == "list"
              and isinstance(entry.get("slug"), str) and isinstance(entry.get("display_name"), str)]
    store = CredentialStore()
    with store.lock("edit:" + owner, deadline, check):
        profile = check()
        profile["catalog"] = {"expires_at": time.time() + 300, "models": models}
        # The caller holds the edit lock; atomic write preserves other accounts.
        saved = store.read(owner)
        saved["profiles"][profile_id] = profile
        store.write(owner, saved)
    return models


async def request(owner: str, profile_id: str, generation: int, model: str, action: dict, deadline: float,
                  limit: int, cancel=None, observation=None) -> str:
    if action["tag"] not in EFFECTS:
        raise ChatGPTError("chatgpt_operation_not_supported")
    def check():
        return check_session(owner, profile_id, generation, cancel)
    store = CredentialStore()
    with store.lock("wire:" + owner + ":" + profile_id, deadline, check):
        try:
            models = await catalog(owner, profile_id, generation, deadline, cancel, _wire_held=True)
            if not any(entry["id"] == model for entry in models):
                raise ChatGPTError("chatgpt_model_not_offered", action="models")
            token = await access_token(owner, profile_id, generation, deadline, cancel)
            body = request_body(model, action["payload"]["prompt"])
            if observation:
                capture, execution = observation
                truncated = capture.request(owner, execution, action, "stage2" if action["tag"] == "complete_visible_ddl_holes" else "stage1", "chatgpt", model, canonical(body))
                if truncated:
                    raise ChatGPTError("chatgpt_observation_incomplete")
            decoder = SSEDecoder(limit)
            raw = bytearray()
            status = 0
            try:
                async with httpx.AsyncClient(follow_redirects=False) as client:
                    check()
                    stream = client.stream("POST", RESOURCE + "/responses", json=body, headers={"Authorization": "Bearer " + token},
                                           timeout=max(0.001, deadline - time.monotonic()))
                    response = await guarded(stream.__aenter__(), check, deadline)
                    status = response.status_code
                    try:
                        if not response.is_success:
                            content = await read_limited(response, check, deadline, 64 * 1024)
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
                if observation and status:
                    capture.response(owner, execution, action, status=status, raw=bytes(raw), truncated=decoder.completed is None,
                                     decoded=decoder.terminal)
        except ResponseFailure as error:
            if error.code == "subscription_sharing_usage_limit_exceeded":
                pause_quota(owner, profile_id, generation, deadline)
            raise


def pin(owner: str) -> tuple[str, int]:
    from .chatgpt_runtime import check_owner
    check_owner(owner)
    profile = CredentialStore().profile(owner)
    check_session(owner, profile["id"], profile["generation"])
    return profile["id"], profile["generation"]


def offered(owner: str, model: str, *, profile_id: str | None = None, generation: int | None = None) -> bool:
    try:
        if profile_id is None or generation is None:
            profile_id, generation = pin(owner)
        models = asyncio.run(catalog(owner, profile_id, generation, time.monotonic() + 15))
        return any(entry["id"] == model for entry in models)
    except (ChatGPTError, httpx.HTTPError, TimeoutError, ValueError, KeyError):
        return False
