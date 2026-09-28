"""A Vision question reaches every provider kind the settings can publish a Vision model through.

The colophon and the Vision advice spoke only the OpenAI-compatible dialect, so a
Vision model published through the Gemini API (`gemini:gemma-4-31b-it`) was
offered and then refused with "okugaki currently requires an OpenAI-compatible
vision provider".
"""

from __future__ import annotations

import json

import httpx
import pytest

from inku_server.vision_client import vision_text

IMAGE = "data:image/png;base64,iVBORw0KGgo="


def _ask(kind: str, answer: dict, base_url: str = "https://provider.example"):
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=answer)

    text = vision_text(
        {"id": kind, "kind": kind, "base_url": base_url, "api_key": "k", "requires_api_key": True},
        "gemma-4-31b-it",
        system="observe",
        text="what changed?",
        images=[IMAGE],
        temperature=0.35,
        max_tokens=260,
        transport=httpx.MockTransport(handler),
    )
    return text, sent[0], json.loads(sent[0].content)


def test_gemini_sends_the_image_inline_and_reads_the_answer_parts():
    text, request, body = _ask("gemini", {"candidates": [{"content": {"parts": [
        {"text": "thinking", "thought": True}, {"text": " 円が右へ寄った "},
    ]}}]})
    assert text == "円が右へ寄った"
    assert request.url.path == "/v1beta/models/gemma-4-31b-it:generateContent"
    assert request.headers["x-goog-api-key"] == "k"
    assert body["systemInstruction"] == {"parts": [{"text": "observe"}]}
    assert body["contents"][0]["parts"] == [
        {"text": "what changed?"}, {"inlineData": {"mimeType": "image/png", "data": "iVBORw0KGgo="}},
    ]
    assert body["generationConfig"]["maxOutputTokens"] == 260


def test_anthropic_sends_a_base64_image_block():
    text, request, body = _ask("anthropic", {"content": [{"type": "text", "text": "A circle."}]})
    assert text == "A circle."
    assert request.url.path == "/v1/messages"
    assert request.headers["x-api-key"] == "k"
    assert body["system"] == "observe"
    assert body["messages"][0]["content"][0] == {
        "type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="},
    }


def test_openai_compatible_keeps_its_image_url_parts():
    text, request, body = _ask("openai_compatible", {"choices": [{"message": {"content": "A circle."}}]},
                               base_url="https://provider.example/v1")
    assert text == "A circle."
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer k"
    assert body["messages"][1]["content"][1] == {"type": "image_url", "image_url": {"url": IMAGE}}


def test_a_timeout_is_a_timeout_and_a_missing_key_is_said_before_sending():
    def slow(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    connection = {"id": "gemini", "kind": "gemini", "base_url": "https://g.example", "api_key": "k", "requires_api_key": True}
    with pytest.raises(TimeoutError):
        vision_text(connection, "m", system="s", text="t", images=[IMAGE], temperature=0, max_tokens=1,
                    transport=httpx.MockTransport(slow))
    with pytest.raises(ValueError, match="gemini API key is not configured"):
        vision_text({**connection, "api_key": ""}, "m", system="s", text="t", images=[IMAGE], temperature=0,
                    max_tokens=1)
