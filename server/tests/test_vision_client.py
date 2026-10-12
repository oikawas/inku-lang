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


def _ask(kind: str, answer: dict, base_url: str = "https://provider.example", model: str = "gemma-4-31b-it"):
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=answer)

    text = vision_text(
        {"id": kind, "kind": kind, "base_url": base_url, "api_key": "k", "requires_api_key": True},
        model,
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
    # As the pipeline sends Anthropic; the colophon was refused 400 while one was sent.
    assert "temperature" not in body
    assert body["messages"][0]["content"][0] == {
        "type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="},
    }


def test_anthropic_vision_leaves_room_for_thinking_and_says_when_it_ran_out(caplog):
    # Haiku 5.5 thinks unasked; 320 tokens of advice JSON were cut (draw, 2026-10-12).
    cut = {"stop_reason": "max_tokens", "usage": {"output_tokens": 8452},
           "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": '{"observation": "A ci'}]}
    with caplog.at_level("WARNING", logger="inku_server.vision_client"):
        text, _request, body = _ask("anthropic", cut, model="claude-haiku-5-5")
    assert body["max_tokens"] == 260 + 8192
    assert text == '{"observation": "A ci'
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("provider_output_limit "))
    assert json.loads(line.split(" ", 1)[1]) == {
        "action": "vision", "provider": "anthropic", "model": "claude-haiku-5-5", "max_tokens": 8452,
        "stop_reason": "max_tokens", "output_tokens": 8452, "thinking_blocks": 1, "has_text": True, "has_tool_use": False,
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


def test_a_refusal_is_logged_with_its_reason(caplog):
    def refuse(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"type": "error", "error": {
            "type": "invalid_request_error", "message": "temperature is not supported",
        }})

    connection = {"id": "anthropic", "kind": "anthropic", "base_url": "https://a.example", "api_key": "k",
                  "requires_api_key": True}
    with caplog.at_level("WARNING", logger="inku_server.vision_client"), pytest.raises(httpx.HTTPStatusError):
        vision_text(connection, "claude-sonnet-5", system="s", text="t", images=[IMAGE], temperature=0.35,
                    max_tokens=260, transport=httpx.MockTransport(refuse))
    logged = json.loads(caplog.records[-1].getMessage().split(" ", 1)[1])
    assert logged == {"action": "vision", "provider": "anthropic", "model": "claude-sonnet-5", "status": 400,
                      "type": "invalid_request_error", "message": "temperature is not supported"}
