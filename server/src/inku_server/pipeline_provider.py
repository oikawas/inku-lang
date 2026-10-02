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
from urllib.parse import quote

import httpx

from .api_core.common import _is_qualified_model_id
from .model_settings import connection_for, provider_for_model
from .provider_limits import provider_slot
from .openai_request import openai_sampling
from .provider_refusal import provider_error as _provider_error
from .provider_observation import ProviderObservationError, ProviderObservationStore
from .provider_rate_limits import ProviderRateBudget, RateAccountingUnavailable, RateLimitUnavailable, retry_after_seconds

_logger = logging.getLogger(__name__)

def _json_object_in(text: str) -> dict[str, Any]:
    """The object an answer given as text carries, fenced or not; the core checks its shape."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise TypeError("provider answered without the response object")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise TypeError("provider answered without the response object")
    return value




_GEMINI_JSON_SCHEMA_KEYS = {
    "$anchor",
    "$defs",
    "$id",
    "$ref",
    "additionalProperties",
    "anyOf",
    "description",
    "enum",
    "format",
    "items",
    "maxItems",
    "maximum",
    "minItems",
    "minimum",
    "oneOf",
    "prefixItems",
    "properties",
    "propertyOrdering",
    "required",
    "title",
    "type",
}


def _merge_gemini_variant_values(values: list[Any]) -> Any | None:
    first = values[0]
    if all(value == first for value in values[1:]):
        return first
    if not all(isinstance(value, dict) for value in values):
        return None
    keys = list(first)
    if not all(list(value) == keys for value in values[1:]):
        return None
    if keys == ["enum"] and all(
        isinstance(value["enum"], list) and len(value["enum"]) == 1
        for value in values
    ):
        return {"enum": [value["enum"][0] for value in values]}
    merged = {}
    for key in keys:
        value = _merge_gemini_variant_values([item[key] for item in values])
        if value is None:
            return None
        merged[key] = value
    return merged


def _compact_gemini_hole_variants(schema: dict[str, Any]) -> None:
    properties = schema.get("properties") or {}
    collection = properties.get("results") or properties.get("edits") or {}
    items = collection.get("items") or {}
    variants = items.get("oneOf")
    if not isinstance(variants, list) or not variants:
        return
    merged = _merge_gemini_variant_values(variants)
    if isinstance(merged, dict) and merged.get("type") == "object":
        # Gemini receives a bounded, flat enum schema. The shared core still
        # validates each returned hole/range/digest tuple against the full
        # response schema and compiler lock before accepting a patch.
        collection["items"] = merged
        return

    # The v3 result variants require either `replacement` or `reason`. Gemini's
    # function schema cannot express that disjunction compactly, so the
    # transport permits both optional fields while Rust retains the exact
    # one-of validation after the response returns.
    if not all(isinstance(variant, dict) for variant in variants):
        return
    variant_properties = [variant.get("properties") for variant in variants]
    if not all(isinstance(value, dict) for value in variant_properties):
        return
    shared_required = set(variants[0].get("required") or [])
    for variant in variants[1:]:
        shared_required.intersection_update(variant.get("required") or [])
    merged_properties = {}
    for name in sorted(set().union(*(value.keys() for value in variant_properties))):
        candidates = [value[name] for value in variant_properties if name in value]
        merged_value = _merge_gemini_variant_values(candidates)
        if merged_value is None:
            return
        merged_properties[name] = merged_value
    collection["items"] = {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(shared_required),
        "properties": merged_properties,
    }


def _gemini_json_schema(
    schema: dict[str, Any], *, compact_hole_edits: bool = False
) -> dict[str, Any]:
    """Project core JSON Schema into Gemini's supported transport subset."""

    def project(value: Any, *, named_schemas: bool = False) -> Any:
        if isinstance(value, list):
            return [project(item) for item in value]
        if not isinstance(value, dict):
            return value
        if named_schemas:
            return {name: project(item) for name, item in value.items()}
        projected = {}
        for key, item in value.items():
            if key == "const":
                projected["enum"] = [item]
            elif key in _GEMINI_JSON_SCHEMA_KEYS:
                projected[key] = project(item, named_schemas=key in {"$defs", "properties"})
        return projected

    result = project(schema)
    if not isinstance(result, dict) or result.get("type") != "object":
        raise ValueError("Gemini function schema must describe an object")
    if compact_hole_edits:
        _compact_gemini_hole_variants(result)
    return result


@dataclass(frozen=True)
class ProviderOptions:
    settings: dict[str, Any]
    stage1_model: str
    stage2_model: str
    max_tokens: int
    max_response_bytes: int


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
                 rate_budget: ProviderRateBudget | None = None):
        if options.max_tokens <= 0 or options.max_response_bytes <= 0:
            raise ValueError("positive provider limits required")
        self.options = options
        self.transport = transport
        self.observation = observation
        self.rate_budget = rate_budget
        self.failure_detail: str | None = None
        self._observation_truncated = False

    def __call__(self, action: dict) -> dict:
        self.failure_detail = None
        self._observation_truncated = False
        self._refusal: dict[str, Any] = {}
        self._target: tuple[str, str] = ("", "")
        tags = {
            "generate_sketch": "sketch_generated",
            "select_description_catalog": "description_catalog_selected",
            "generate_normalized_ddl": "normalized_ddl_generated",
            "complete_visible_ddl_holes": "visible_ddl_hole_patch_generated",
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
            connection = connection_for(provider_id, self.options.settings)
            self._target = (provider_id, model)
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
        base = connection["base_url"].rstrip("/")
        key = connection.get("api_key") or ""
        headers = {"Content-Type": "application/json"}
        kind = connection["kind"]
        response_name = "submit_pipeline_response"
        if kind == "openai_compatible":
            url = base + "/chat/completions"
            headers["Authorization"] = "Bearer " + (key or "none")
            body = {"model": model, "stream": False,
                    **openai_sampling(connection, model, max_tokens=self.options.max_tokens,
                                      temperature=0.3 if prompt["action_name"] == "generate_normalized_ddl" else 0.0),
                    "messages": [{"role": "system", "content": prompt["system"]},
                                 {"role": "user", "content": prompt["message"]}]}
            # Preserve the established provider-specific structured-output
            # transport, using the schema owned by the shared core verbatim.
            # Gemma 4 on mlx-vlm loops on thought-channel markers when given
            # the forced function tool (2026-10-02). Its grammar-constrained
            # JSON output accepts the same core schema without a tool template.
            if connection["id"] == "ollama" or connection.get("api_profile") == "mlx":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": response_name, "schema": prompt["response_schema"], "strict": True},
                }
            else:
                body["tools"] = [{"type": "function", "function": {
                    "name": response_name, "description": "Submit the requested pipeline response.",
                    "parameters": prompt["response_schema"],
                }}]
                body["tool_choice"] = {"type": "function", "function": {"name": response_name}}
            if connection["id"] in {"ollama", "ollama-cloud"}:
                body["reasoning_effort"] = "none"
        elif kind == "anthropic":
            url = base + "/v1/messages"
            headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
            body = {"model": model, "max_tokens": self.options.max_tokens,
                    "system": prompt["system"],
                    "messages": [{"role": "user", "content": prompt["message"]}],
                    "tools": [{
                        "name": response_name,
                        "description": "Submit the requested pipeline response.",
                        "input_schema": prompt["response_schema"],
                    }],
                    # Left to the model: claude-opus-5-5 refuses a forced tool
                    # ("tool_choice: type \"tool\" and \"any\" are not supported
                    # for this model", Pentala 2026-09-28). With one tool the
                    # models call it; an answer given as text is read below.
                    "tool_choice": {"type": "auto"}}
        elif kind == "gemini":
            url = base + "/v1beta/models/" + quote(model, safe="") + ":generateContent"
            headers["x-goog-api-key"] = key
            body = {"systemInstruction": {"parts": [{"text": prompt["system"]}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt["message"]}]}],
                    "generationConfig": {
                        "maxOutputTokens": self.options.max_tokens,
                        "thinkingConfig": {"thinkingLevel": "minimal"},
                    },
                    "tools": [{"functionDeclarations": [{
                        "name": response_name,
                        "description": "Submit the requested pipeline response.",
                        "parametersJsonSchema": _gemini_json_schema(
                            prompt["response_schema"],
                            compact_hole_edits=(
                                prompt["action_name"] == "complete_visible_ddl_holes"
                            ),
                        ),
                    }]}],
                    "toolConfig": {"functionCallingConfig": {
                        "mode": "ANY", "allowedFunctionNames": [response_name],
                    }}}
        else:
            raise ValueError("unsupported provider kind")
        body_bytes = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if self.observation is not None:
            store, owner_id, execution_id = self.observation
            # The durable request record is the send authorization: a failed
            # insert must leave this method before it reaches HTTPX.
            request_truncated = store.request(
                owner_id, execution_id, action,
                "stage2" if action["tag"] == "complete_visible_ddl_holes" else "stage1",
                str(connection["id"]), model, body_bytes,
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
                            async with client.stream("POST", url.removesuffix(":generateContent") + ":countTokens",
                                                     headers=headers, json={"generateContentRequest": {
                                                         "model": "models/" + model, **body,
                                                     }}) as counted:
                                async for chunk in counted.aiter_bytes():
                                    if len(count_raw) + len(chunk) > min(16384, self.options.max_response_bytes):
                                        raise ValueError("token count response limit exceeded")
                                    count_raw.extend(chunk)
                                if counted.status_code >= 400:
                                    refused_raw = bytes(count_raw)
                                    self._refusal = {**_provider_error(refused_raw), "operation": "count_tokens"}
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
                                self._refusal = _provider_error(refused_raw)
                            result.raise_for_status()
                        async for chunk in result.aiter_bytes():
                            if len(raw) + len(chunk) > self.options.max_response_bytes:
                                raw.extend(chunk[:max(0, self.options.max_response_bytes - len(raw))])
                                if self.observation is not None:
                                    store, owner_id, execution_id = self.observation
                                    store.response(owner_id, execution_id, action, status=result.status_code, raw=bytes(raw), truncated=True)
                                self._observation_truncated = True
                                raise ValueError("provider response limit exceeded")
                            raw.extend(chunk)
                        if self.observation is not None:
                            store, owner_id, execution_id = self.observation
                            store.response(owner_id, execution_id, action, status=result.status_code, raw=bytes(raw))
                            if result.status_code >= 400:
                                refused_raw = bytes(raw[:16384])
                                self._refusal = _provider_error(refused_raw)
                            result.raise_for_status()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError("provider response is not an object")
            usage = data.get("usageMetadata", {}) if kind == "gemini" else data.get("usage", {})
            if not isinstance(usage, dict):
                usage = {}
            used = usage.get("promptTokenCount") if kind == "gemini" else usage.get(
                "input_tokens" if kind == "anthropic" else "prompt_tokens")
            if isinstance(used, int) and not isinstance(used, bool) and used >= 0:
                input_used = used
        except httpx.HTTPStatusError as error:
            if budget is not None and error.response.status_code == 429:
                budget.cool_down(str(connection["id"]), retry_after_seconds(
                    error.response.headers, refused_raw, now=budget.clock(),
                ))
            raise
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError):
            if self.observation is not None and response_status is not None:
                store, owner_id, execution_id = self.observation
                store.response(owner_id, execution_id, action, status=response_status, raw=bytes(raw), truncated=True)
                self._observation_truncated = True
            raise
        finally:
            if budget is not None and reservation is not None:
                budget.settle(str(connection["id"]), reservation, input_used if input_used is not None
                              else (None if limits["tpm"] else 0))
        if kind == "openai_compatible":
            message = data["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            if calls:
                if len(calls) != 1 or calls[0]["function"]["name"] != response_name:
                    raise TypeError("provider returned an unexpected tool call")
                text = calls[0]["function"]["arguments"]
            else:
                text = message.get("content")
        elif kind == "anthropic":
            calls = [block for block in data["content"] if block.get("type") == "tool_use"]
            if calls:
                if len(calls) != 1 or calls[0].get("name") != response_name:
                    raise TypeError("provider returned an unexpected tool call")
                arguments = calls[0].get("input")
                if not isinstance(arguments, dict):
                    raise TypeError("provider returned invalid tool input")
            else:
                arguments = _json_object_in("\n".join(
                    str(block.get("text", "")) for block in data["content"] if block.get("type") == "text"
                ))
            text = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
        elif kind == "gemini":
            calls = [part["functionCall"] for part in data["candidates"][0]["content"]["parts"] if "functionCall" in part]
            if len(calls) != 1 or calls[0]["name"] != response_name:
                raise TypeError("provider returned an unexpected function call")
            arguments = calls[0].get("args")
            if not isinstance(arguments, dict):
                raise TypeError("provider returned invalid function arguments")
            text = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
        else:
            text = "\n".join(part["text"] for part in data["candidates"][0]["content"]["parts"] if "text" in part)
        if not isinstance(text, str) or not text:
            raise TypeError("provider returned no text")
        return text
