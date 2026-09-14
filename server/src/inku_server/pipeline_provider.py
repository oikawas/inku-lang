"""Single-attempt provider transport for effects emitted by shared Rust.

The caller selects credentials/models; Rust owns prompts, response validation,
retries and fallback. No legacy interpreter/composer decisions run here.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .api_core.common import _is_qualified_model_id
from .model_settings import connection_for, provider_for_model
from .provider_limits import provider_slot


@dataclass(frozen=True)
class ProviderOptions:
    settings: dict[str, Any]
    stage1_model: str
    stage2_model: str
    max_tokens: int
    max_response_bytes: int


def resolved_stage_model(model: str | None, actor: dict | None, *, stage: str) -> str:
    """Resolve a request model against the actor's selected stage provider."""
    settings = (actor or {}).get("model_settings") or {}
    provider_key = "stage1_provider" if stage == "stage1" else "stage2_provider"
    model_key = "stage1_model" if stage == "stage1" else "stage2_model"
    default_model = "google/gemma-4-31b-it"
    provider = str(settings.get(provider_key, "nvidia") or "nvidia")
    model_id = str(settings.get(model_key, default_model) or default_model)
    if model:
        requested = str(model).strip()
        if _is_qualified_model_id(requested):
            return requested
        if requested == model_id:
            return f"{provider}:{requested}"
        return requested
    return model_id if _is_qualified_model_id(model_id) else f"{provider}:{model_id}"


class SingleAttemptProvider:
    def __init__(self, options: ProviderOptions, *, transport: httpx.AsyncBaseTransport | None = None):
        if options.max_tokens <= 0 or options.max_response_bytes <= 0:
            raise ValueError("positive provider limits required")
        self.options = options
        self.transport = transport

    def __call__(self, action: dict) -> dict:
        tags = {
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
            if connection["requires_api_key"] and not connection.get("api_key"):
                raise ValueError("provider credentials unavailable")
            with provider_slot(provider_id, timeout=timeout):
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError
                response = asyncio.run(self._request(
                    connection, model, action["payload"]["prompt"], remaining
                ))
        except (TimeoutError, httpx.TimeoutException):
            failure = "transport_timeout"
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            failure = "rate_limited" if status == 429 else (
                "transport_unavailable" if status >= 500 else "provider_rejected"
            )
        except httpx.TransportError:
            failure = "transport_unavailable"
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            failure = "malformed_payload"
        except ValueError:
            failure = "provider_rejected"
        elapsed = str(max(0, int((time.monotonic() - started) * 1000)))
        if failure is not None:
            return {"tag": "provider_failed", "identity": identity, "failure": failure, "elapsed_ms": elapsed}
        return {"tag": tags[action["tag"]], "identity": identity, "response": response, "elapsed_ms": elapsed}

    async def _request(self, connection: dict, model: str, prompt: dict, timeout: float) -> str:
        base = connection["base_url"].rstrip("/")
        key = connection.get("api_key") or ""
        headers = {"Content-Type": "application/json"}
        kind = connection["kind"]
        response_name = "submit_pipeline_response"
        if kind == "openai_compatible":
            url = base + "/chat/completions"
            headers["Authorization"] = "Bearer " + (key or "none")
            body = {"model": model, "max_tokens": self.options.max_tokens, "stream": False,
                    "temperature": 0.3 if prompt["action_name"] == "generate_normalized_ddl" else 0.0,
                    "messages": [{"role": "system", "content": prompt["system"]},
                                 {"role": "user", "content": prompt["message"]}]}
            # Preserve the established provider-specific structured-output
            # transport, using the schema owned by the shared core verbatim.
            if connection["id"] == "ollama":
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
                    "messages": [{"role": "user", "content": prompt["message"]}]}
        elif kind == "gemini":
            url = base + "/v1beta/models/" + quote(model, safe="") + ":generateContent"
            headers["x-goog-api-key"] = key
            body = {"systemInstruction": {"parts": [{"text": prompt["system"]}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt["message"]}]}],
                    "generationConfig": {"maxOutputTokens": self.options.max_tokens}}
        else:
            raise ValueError("unsupported provider kind")
        # asyncio's deadline covers connect, body streaming and decoding as one
        # attempt. HTTPX performs no retries; redirects are not followed.
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(timeout=timeout, transport=self.transport, follow_redirects=False) as client:
                async with client.stream("POST", url, headers=headers, json=body) as result:
                    result.raise_for_status()
                    raw = bytearray()
                    async for chunk in result.aiter_bytes():
                        if len(raw) + len(chunk) > self.options.max_response_bytes:
                            raise ValueError("provider response limit exceeded")
                        raw.extend(chunk)
                data = json.loads(raw)
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
                    text = "\n".join(block["text"] for block in data["content"] if block["type"] == "text")
                else:
                    text = "\n".join(part["text"] for part in data["candidates"][0]["content"]["parts"] if "text" in part)
                if not isinstance(text, str) or not text:
                    raise TypeError("provider returned no text")
                return text
