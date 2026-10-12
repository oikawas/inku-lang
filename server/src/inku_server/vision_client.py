"""One text answer about images, from any provider kind the settings know.

The colophon and the Vision advice of autonomous refinement both ask a Vision
model a question with images attached. They used to speak only the
OpenAI-compatible dialect, so a Vision model published through the Gemini or
Anthropic API was offered and then refused at the point of use. The request
shapes follow the pipeline transport (pipeline_provider.py): the same endpoints,
the same header for the key, the model id as one quoted path segment.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any
from urllib.parse import quote

import httpx

from .anthropic_request import anthropic_max_tokens, output_limit_record
from .gemini_request import gemini_max_output_tokens, gemini_output_limit_record, gemini_thinking
from .openai_request import openai_output_limit_record, openai_sampling
from .provider_refusal import provider_error
from .chatgpt_store import ChatGPTError
from .model_settings import connection_for

_logger = logging.getLogger(__name__)


def vision_connection(provider: str, settings: dict[str, Any]) -> dict[str, Any]:
    if provider != "chatgpt":
        return connection_for(provider, settings)
    try:
        return {"id": "chatgpt", "kind": "chatgpt_responses", "base_url": "https://api.openai.com/v1",
                "owner_id": settings["chatgpt_owner_id"], "profile_id": settings["chatgpt_profile_id"],
                "generation": settings["chatgpt_generation"]}
    except KeyError:
        raise ChatGPTError("chatgpt_not_connected") from None


def check_vision_access(connection: dict[str, Any], model_id: str) -> None:
    """Even a cached reading belongs to the pinned owner's currently offered model."""
    if connection.get("kind") != "chatgpt_responses":
        return
    from .chatgpt_runtime import check_session
    from .chatgpt_models import publication
    profile = check_session(connection["owner_id"], connection["profile_id"], connection["generation"])
    if not any(model["id"] == model_id and model["enabled"] and "vision" in model["purposes"]
               for model in publication(profile)["models"]):
        raise ChatGPTError("chatgpt_model_not_offered", action="models")


def _image_parts(image: str) -> tuple[str, str]:
    """(media type, base64 data) of a `data:` URL."""
    head, _, data = image.partition(",")
    if not head.startswith("data:") or ";base64" not in head or not data:
        raise ValueError("Vision images must be base64 data URLs")
    return head[len("data:"):].split(";", 1)[0] or "image/png", data


def _request(connection: dict[str, Any], model_id: str, *, system: str, text: str, images: list[str],
             temperature: float, max_tokens: int) -> tuple[str, dict[str, str], dict[str, Any]]:
    base = str(connection["base_url"]).rstrip("/")
    key = str(connection.get("api_key") or "")
    headers = {"Content-Type": "application/json"}
    kind = connection.get("kind")
    if kind == "openai_compatible":
        headers["Authorization"] = "Bearer " + (key or "none")
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        content.extend({"type": "image_url", "image_url": {"url": image}} for image in images)
        return base + "/chat/completions", headers, {
            "model": model_id, "stream": False,
            **openai_sampling(connection, model_id, max_tokens=max_tokens, temperature=temperature),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        }
    if kind == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        blocks: list[dict[str, Any]] = []
        for image in images:
            media_type, data = _image_parts(image)
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
        blocks.append({"type": "text", "text": text})
        # No temperature, as the pipeline sends Anthropic: the colophon with
        # claude-sonnet-5 was refused 400 while one was sent (2026-09-28).
        return base + "/v1/messages", headers, {
            "model": model_id, "max_tokens": anthropic_max_tokens(model_id, max_tokens), "system": system,
            "messages": [{"role": "user", "content": blocks}],
        }
    if kind == "gemini":
        headers["x-goog-api-key"] = key
        parts: list[dict[str, Any]] = [{"text": text}]
        for image in images:
            media_type, data = _image_parts(image)
            parts.append({"inlineData": {"mimeType": media_type, "data": data}})
        return base + "/v1beta/models/" + quote(model_id, safe="") + ":generateContent", headers, {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            # The lowest thinking level and no temperature, as the pipeline asks:
            # Gemini 3 is tuned for its default of 1.0 and below it can loop
            # (Gemini 3 developer guide), and Gemma 4's model card samples at 1.0.
            "generationConfig": {"maxOutputTokens": gemini_max_output_tokens(model_id, max_tokens),
                                 **gemini_thinking(model_id)},
        }
    raise ValueError(f"unsupported provider kind for Vision: {kind}")


def _answer(kind: str, data: dict[str, Any]) -> str:
    if kind == "openai_compatible":
        return str(data["choices"][0]["message"].get("content") or "")
    if kind == "anthropic":
        return "\n".join(str(block.get("text", "")) for block in data.get("content", []) if block.get("type") == "text")
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "\n".join(str(part["text"]) for part in parts if "text" in part and not part.get("thought"))


def vision_text(connection: dict[str, Any], model_id: str, *, system: str, text: str, images: list[str],
                temperature: float, max_tokens: int, transport: httpx.BaseTransport | None = None) -> str:
    """Ask once and return the answer's text, stripped. A timeout is a TimeoutError."""
    if connection.get("kind") == "chatgpt_responses":
        from .chatgpt_provider import request_vision
        for image in images:
            _image_parts(image)
        try:
            return asyncio.run(request_vision(
                connection["owner_id"], connection["profile_id"], connection["generation"], model_id,
                system=system, text=text, images=images,
                deadline=time.monotonic() + float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "180")),
                transport=transport,
            )).strip()
        except ChatGPTError:
            raise
        except (httpx.HTTPError, TimeoutError):
            raise ChatGPTError("chatgpt_transport_unavailable", failure="transport_unavailable", action="retry") from None
        except (ValueError, KeyError, TypeError):
            raise ChatGPTError("chatgpt_response_invalid", action="diagnose") from None
    if connection.get("requires_api_key") and not connection.get("api_key"):
        raise ValueError(f"{connection.get('id')} API key is not configured")
    url, headers, body = _request(connection, model_id, system=system, text=text, images=images,
                                  temperature=temperature, max_tokens=max_tokens)
    timeout = float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "180"))
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=False) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise TimeoutError("Vision provider timed out") from exc
    if response.status_code >= 400:
        # The same line the pipeline writes, so a refusal here says why too.
        _logger.warning("provider_http_error %s", json.dumps({
            "action": "vision", "provider": connection.get("id"), "model": model_id,
            "status": response.status_code, **provider_error(response.content[:16384]),
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    response.raise_for_status()
    data = response.json()
    kind = connection.get("kind")
    cut = (output_limit_record(data) if kind == "anthropic"
           else gemini_output_limit_record(data) if kind == "gemini"
           else openai_output_limit_record(data) if kind == "openai_compatible" else None)
    if cut is not None:
        # Returned as it is: a cut colophon is still prose, and cut advice JSON
        # fails where it is parsed. This line says the budget, not the image, ran out.
        _logger.warning("provider_output_limit %s", json.dumps({
            "action": "vision", "provider": connection.get("id"), "model": model_id,
            "max_tokens": (body["generationConfig"]["maxOutputTokens"] if kind == "gemini"
                           else body.get("max_tokens", body.get("max_completion_tokens"))),
            **cut,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return _answer(str(connection.get("kind")), data).strip()
