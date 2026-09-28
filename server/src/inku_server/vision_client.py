"""One text answer about images, from any provider kind the settings know.

The colophon and the Vision advice of autonomous refinement both ask a Vision
model a question with images attached. They used to speak only the
OpenAI-compatible dialect, so a Vision model published through the Gemini or
Anthropic API was offered and then refused at the point of use. The request
shapes follow the pipeline transport (pipeline_provider.py): the same endpoints,
the same header for the key, the model id as one quoted path segment.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx

from .openai_request import openai_sampling


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
        return base + "/v1/messages", headers, {
            "model": model_id, "temperature": temperature, "max_tokens": max_tokens, "system": system,
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
            # Minimal thinking, as the pipeline asks: a thinking model otherwise
            # spends the small output budget before it writes the answer.
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                                 "thinkingConfig": {"thinkingLevel": "minimal"}},
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
    response.raise_for_status()
    return _answer(str(connection.get("kind")), response.json()).strip()
