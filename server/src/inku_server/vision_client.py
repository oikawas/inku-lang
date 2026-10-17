"""One text answer about images, from any provider kind the settings know.

The colophon and the Vision advice of autonomous refinement both ask a Vision
model a question with images attached. They used to speak only the
OpenAI-compatible dialect, so a Vision model published through the Gemini or
Anthropic API was offered and then refused at the point of use. The request
shapes follow the pipeline transport (pipeline_provider.py): the same endpoints,
the same header for the key, the model id as one quoted path segment. The
shared core writes those requests and reads their answers (provider_wire).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import httpx

from . import provider_wire
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
        raise ChatGPTError("chatgpt_model_not_offered")


def vision_text(connection: dict[str, Any], model_id: str, *, system: str, text: str, images: list[str],
                temperature: float, max_tokens: int, transport: httpx.BaseTransport | None = None) -> str:
    """Ask once and return the answer's text, stripped. A timeout is a TimeoutError."""
    if connection.get("kind") == "chatgpt_responses":
        from .chatgpt_provider import request_vision
        # Every image must be a base64 data URL; the core refuses any other
        # before a token or the model list is asked for.
        provider_wire.chatgpt_vision_request(model_id, system=system, text=text, images=images, answer_limit=512 * 1024)
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
            raise ChatGPTError("chatgpt_transport_unavailable") from None
        except (ValueError, KeyError, TypeError):
            raise ChatGPTError("chatgpt_response_invalid") from None
    if connection.get("requires_api_key") and not connection.get("api_key"):
        raise ValueError(f"{connection.get('id')} API key is not configured")
    built = provider_wire.text_request(connection, model_id, system=system, text=text, images=images,
                                       temperature=temperature, max_tokens=max_tokens)
    timeout = float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "180"))
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=False) as client:
            response = client.post(built["url"], headers=provider_wire.headers(built, str(connection.get("api_key") or "")),
                                   content=built["body"].encode("utf-8"))
    except httpx.TimeoutException as exc:
        raise TimeoutError("Vision provider timed out") from exc
    if response.status_code >= 400:
        # The same line the pipeline writes, so a refusal here says why too.
        _logger.warning("provider_http_error %s", json.dumps({
            "action": "vision", "provider": connection.get("id"), "model": model_id,
            "status": response.status_code, **provider_wire.refusal(response.content[:16384]),
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    response.raise_for_status()
    read = provider_wire.read_text(built["format"], response.status_code, response.content)
    if read["outcome"] != "answer":
        detail = read.get("detail") or "provider returned an unexpected answer"
        raise (ValueError if detail == "provider response is not JSON" else TypeError)(detail)
    if read.get("cut") is not None:
        # Returned as it is: a cut colophon is still prose, and cut advice JSON
        # fails where it is parsed. This line says the budget, not the image, ran out.
        _logger.warning("provider_output_limit %s", json.dumps({
            "action": "vision", "provider": connection.get("id"), "model": model_id,
            "max_tokens": built["output_budget"], **read["cut"],
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return read["text"]
