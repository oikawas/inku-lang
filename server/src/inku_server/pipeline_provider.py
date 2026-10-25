"""Single-attempt provider transport for effects emitted by shared Rust.

The caller selects credentials/models; Rust owns prompts, response validation,
retries and fallback. No legacy interpreter/composer decisions run here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .api_core.common import _is_qualified_model_id
from .model_settings import connection_for, provider_for_model
from .provider_limits import provider_slot
from . import provider_wire
from .provider_observation import ProviderObservationError, ProviderObservationStore
from .provider_rate_limits import ProviderRateBudget, RateAccountingUnavailable, RateLimitUnavailable, retry_after_seconds
from .chatgpt_store import ChatGPTError

_logger = logging.getLogger(__name__)

def provider_stage_record(tag: str) -> str:
    """The stage a provider action is timed and recorded under.

    Hole completion is Stage 2. The composition reading, the laws stage and the
    color stage are recorded apart from Stage 1, whose model they use, so no
    time hides another.
    """
    if tag == "complete_visible_ddl_holes":
        return "stage2"
    if tag == "read_composition":
        return "composition"
    if tag == "choose_laws":
        return "laws"
    if tag == "choose_colors":
        return "colors"
    if tag in provider_wire.READ_AND_DRAW_EFFECTS:
        return "read_and_draw"
    if tag in provider_wire.IMAGE_EFFECTS:
        return "image"
    return "stage1"


@dataclass(frozen=True)
class ProviderOptions:
    settings: dict[str, Any]
    stage1_model: str
    stage2_model: str
    max_tokens: int
    max_response_bytes: int
    chatgpt_owner: str | None = None
    chatgpt_profile: str | None = None
    chatgpt_generation: int | None = None
    chatgpt_cancel: Any = None


def resolved_drawing_model(model: str | None, actor: dict | None) -> str:
    """Keep explicit references for the common provider resolver.

    One model draws both stages (2026-09-30), so this reads the Stage 1 keys; a
    stored Stage 2 choice that still differs is not consulted.
    """
    settings = (actor or {}).get("model_settings") or {}
    default_model = "google/gemma-4-31b-it"
    provider = str(settings.get("stage1_provider", "nvidia") or "nvidia")
    model_id = str(settings.get("stage1_model", default_model) or default_model)
    if model:
        return str(model).strip()
    return model_id if _is_qualified_model_id(model_id) else f"{provider}:{model_id}"


class SingleAttemptProvider:
    def __init__(self, options: ProviderOptions, *, transport: httpx.AsyncBaseTransport | None = None,
                 observation: tuple[ProviderObservationStore, str, str] | None = None,
                 rate_budget: ProviderRateBudget | None = None, images: list[str] | None = None):
        if options.max_tokens <= 0 or options.max_response_bytes <= 0:
            raise ValueError("positive provider limits required")
        self.options = options
        self.transport = transport
        self.observation = observation
        self.rate_budget = rate_budget
        self.images = list(images) if images is not None else None
        self.failure_detail: str | None = None
        self._observation_truncated = False

    def __call__(self, action: dict) -> dict:
        self.failure_detail = None
        self.chatgpt_failure_detail = None
        self._observation_truncated = False
        self._refusal: dict[str, Any] = {}
        self._target: tuple[str, str] = ("", "")
        # What this send used, as the response reported it; None when it reported nothing.
        self.usage: dict | None = None
        chatgpt_usage: list = []
        tags = {
            "generate_sketch": "sketch_generated",
            "select_description_catalog": "description_catalog_selected",
            "generate_normalized_ddl": "normalized_ddl_generated",
            "read_composition": "composition_read",
            "choose_laws": "laws_chosen",
            "choose_colors": "colors_chosen",
            "complete_visible_ddl_holes": "visible_ddl_hole_patch_generated",
            "select_image_catalog": "image_catalog_selected",
            "write_image_ddl": "image_ddl_written",
            "review_image_ddl": "image_ddl_reviewed",
            "read_description": "description_read",
            "write_description_ddl": "description_ddl_written",
            "review_description_ddl": "description_ddl_reviewed",
        }
        if action["tag"] not in tags:
            raise ValueError("unsupported provider effect")
        started = time.monotonic()
        timeout = int(action["timeout_ms"]) / 1000
        identity = dict(action["identity"])
        failure = None
        response = None
        try:
            if timeout <= 0:
                raise TimeoutError
            stage = "stage2" if action["tag"] == "complete_visible_ddl_holes" else "stage1"
            model_ref = self.options.stage2_model if stage == "stage2" else self.options.stage1_model
            provider_id, model = provider_for_model(model_ref, stage=stage, settings=self.options.settings)
            self._target = (provider_id, model)
            if provider_id == "chatgpt":
                from .chatgpt_provider import request
                if not self.options.chatgpt_owner or not self.options.chatgpt_profile or self.options.chatgpt_generation is None:
                    raise ChatGPTError("chatgpt_profile_required")
                response = asyncio.run(request(
                    self.options.chatgpt_owner, self.options.chatgpt_profile, self.options.chatgpt_generation,
                    model, action, started + timeout, self.options.max_response_bytes, self.options.chatgpt_cancel,
                    (self.observation[0], self.observation[2]) if self.observation else None,
                    purpose="vision" if action["tag"] in provider_wire.IMAGE_EFFECTS else "llm",
                    images=self.images, transport=self.transport, usage=chatgpt_usage,
                ))
            else:
                connection = connection_for(provider_id, self.options.settings)
                if connection["requires_api_key"] and not connection.get("api_key"):
                    self.failure_detail = "credentials_unavailable"
                    raise ValueError("provider credentials unavailable")
                with provider_slot(provider_id, timeout=timeout):
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise TimeoutError
                    response = asyncio.run(self._request(
                        connection, model, action, action["payload"]["prompt"], remaining
                    ))
        except ChatGPTError as error:
            failure = error.failure
            self.chatgpt_failure_detail = {"code": error.code, "action": error.action,
                                          "request_id": getattr(error, "request_id", None), "param": getattr(error, "param", None),
                                          "status": getattr(error, "status", None)}
            self._observation_truncated = error.code in {"chatgpt_response_incomplete", "chatgpt_response_too_large", "chatgpt_cancelled"}
        except (TimeoutError, httpx.TimeoutException):
            failure = "rate_limited" if self.failure_detail == "rate_limit_wait" else "transport_timeout"
        except RateLimitUnavailable:
            self.failure_detail = "rate_limit_wait"
            failure = "rate_limited"
        except RateAccountingUnavailable:
            _logger.warning("provider_rate_accounting_unavailable provider=%s", self._target[0])
            failure = "transport_unavailable"
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            failure = "rate_limited" if status == 429 else (
                "transport_unavailable" if status >= 500 else "provider_rejected"
            )
            # The pipeline records only the failure class; this line is where the
            # provider's own reason survives (a 400 for a field, a 403 for access).
            _logger.warning("provider_http_error %s", json.dumps({
                "action": action["tag"], "provider": self._target[0], "model": self._target[1],
                "status": status, **self._refusal,
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        except httpx.TransportError:
            failure = "transport_unavailable"
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            failure = "malformed_payload"
        except ProviderObservationError:
            self.failure_detail = "observation_incomplete"
            self._observation_truncated = True
            failure = "provider_rejected"
        except ValueError:
            failure = "provider_rejected"
        if chatgpt_usage:
            self.usage = chatgpt_usage[-1]
        elapsed_int = max(0, int((time.monotonic() - started) * 1000))
        if self.observation is not None:
            store, owner_id, execution_id = self.observation
            try:
                store.outcome(owner_id, execution_id, action, failure=failure, elapsed_ms=elapsed_int,
                              capture_complete=not self._observation_truncated)
            except ProviderObservationError:
                self.failure_detail = "observation_incomplete"
                failure = "provider_rejected"
        elapsed = str(elapsed_int)
        if failure is not None:
            return {"tag": "provider_failed", "identity": identity, "failure": failure, "elapsed_ms": elapsed}
        return {"tag": tags[action["tag"]], "identity": identity, "response": response, "elapsed_ms": elapsed}

    async def _request(self, connection: dict, model: str, action: dict, prompt: dict, timeout: float) -> str:
        # The shared core writes the body for the connection's dialect, byte for
        # byte as this transport wrote it (provider_wire), and names the header
        # the key goes under; a request it cannot build is a ValueError.
        built = provider_wire.pipeline_request(connection, model, prompt, self.options.max_tokens, images=self.images)
        url = built["url"]
        headers = provider_wire.headers(built, connection.get("api_key") or "")
        kind = connection["kind"]
        body_bytes = built["body"].encode("utf-8")
        image_effect = action["tag"] in provider_wire.IMAGE_EFFECTS

        def capture_body(body: bytes) -> bytes:
            return provider_wire.observation_digest(body) if image_effect else body

        def refusal(body: bytes) -> dict:
            # A provider may echo any input in its rejection, including images.
            return {} if image_effect else provider_wire.refusal(body)
        if self.observation is not None:
            store, owner_id, execution_id = self.observation
            # The durable request record is the send authorization: a failed
            # insert must leave this method before it reaches HTTPX.
            request_truncated = store.request(
                owner_id, execution_id, action, provider_stage_record(action["tag"]),
                str(connection["id"]), model, capture_body(body_bytes),
            )
            self._observation_truncated = request_truncated
            if request_truncated:
                raise ProviderObservationError("request_capture_truncated")
        # asyncio's deadline covers connect, body streaming and decoding as one
        # attempt. HTTPX performs no retries; redirects are not followed.
        raw = bytearray()
        response_status: int | None = None
        budget = self.rate_budget
        limits = connection.get("rate_limits")
        if limits is not None and budget is None:
            from . import db
            budget = ProviderRateBudget(db.engine)
        reservation = None
        input_used = None
        refused_raw = b""
        try:
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(timeout=timeout, transport=self.transport, follow_redirects=False) as client:
                    if budget is not None and limits is not None:
                        input_tokens = len(body_bytes) + 128 if limits["tpm"] else 0
                        if kind == "gemini" and limits["tpm"]:
                            # Count the exact system, content and function schema,
                            # rather than guessing Japanese tokens from characters.
                            count_raw = bytearray()
                            async with client.stream("POST", built["count_tokens"]["url"], headers=headers,
                                                     content=built["count_tokens"]["body"].encode("utf-8")) as counted:
                                async for chunk in counted.aiter_bytes():
                                    if len(count_raw) + len(chunk) > min(16384, self.options.max_response_bytes):
                                        raise ValueError("token count response limit exceeded")
                                    count_raw.extend(chunk)
                                if counted.status_code >= 400:
                                    refused_raw = bytes(count_raw)
                                    self._refusal = {**refusal(refused_raw), "operation": "count_tokens"}
                                    counted.raise_for_status()
                            count_data = json.loads(count_raw)
                            if not isinstance(count_data, dict):
                                raise TypeError("token count response is not an object")
                            count = count_data.get("totalTokens")
                            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                                raise RateLimitUnavailable("input token count is unavailable")
                            input_tokens = (count * 11 + 9) // 10
                        self.failure_detail = "rate_limit_wait"
                        reservation = await budget.reserve(str(connection["id"]), kind, limits, input_tokens)
                        self.failure_detail = None
                    async with client.stream("POST", url, headers=headers, content=body_bytes) as result:
                        response_status = result.status_code
                    # Preserve legacy behavior when capture is disabled: a
                    # status error is classified before reading its body.
                        if self.observation is None:
                            if result.status_code >= 400:
                                # Read a bounded refusal so the log can say why.
                                refused_raw = bytes((await result.aread())[:16384])
                                self._refusal = refusal(refused_raw)
                            result.raise_for_status()
                        async for chunk in result.aiter_bytes():
                            if len(raw) + len(chunk) > self.options.max_response_bytes:
                                raw.extend(chunk[:max(0, self.options.max_response_bytes - len(raw))])
                                if self.observation is not None:
                                    store, owner_id, execution_id = self.observation
                                    store.response(owner_id, execution_id, action, status=result.status_code, raw=capture_body(bytes(raw)), truncated=True)
                                self._observation_truncated = True
                                raise ValueError("provider response limit exceeded")
                            raw.extend(chunk)
                        if self.observation is not None:
                            store, owner_id, execution_id = self.observation
                            store.response(owner_id, execution_id, action, status=result.status_code, raw=capture_body(bytes(raw)))
                            if result.status_code >= 400:
                                refused_raw = bytes(raw[:16384])
                                self._refusal = refusal(refused_raw)
                            result.raise_for_status()
            read = provider_wire.read_pipeline(built["format"], response_status, bytes(raw))
            # A cut or malformed answer still used what it reports.
            self.usage = provider_wire.usage(built["format"], bytes(raw))
            if read.get("input_tokens") is not None:
                input_used = read["input_tokens"]
        except httpx.HTTPStatusError as error:
            if budget is not None and error.response.status_code == 429:
                budget.cool_down(str(connection["id"]), retry_after_seconds(
                    error.response.headers, refused_raw, now=budget.clock(),
                ))
            raise
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError):
            if self.observation is not None and response_status is not None:
                store, owner_id, execution_id = self.observation
                store.response(owner_id, execution_id, action, status=response_status, raw=capture_body(bytes(raw)), truncated=True)
                self._observation_truncated = True
            raise
        finally:
            if budget is not None and reservation is not None:
                budget.settle(str(connection["id"]), reservation, input_used if input_used is not None
                              else (None if limits["tpm"] else 0))
        # A response stopped at the output limit is cut off whatever it holds:
        # a tool input or JSON text that ends there is not the whole answer.
        if read["outcome"] == "cut":
            self.failure_detail = "output_limit_reached"
            _logger.warning("provider_output_limit %s", json.dumps({
                "action": action["tag"], "provider": connection["id"], "model": model,
                "max_tokens": built["output_budget"], **({} if image_effect else read["cut"]),
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            raise TypeError("provider output reached its token limit")
        if read["outcome"] != "answer":
            raise TypeError(read.get("detail") or "provider returned no text")
        return read["text"]
