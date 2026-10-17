import json

import httpx

from inku_server.api_core.routers import public


def _route(monkeypatch, provider, model):
    monkeypatch.setattr(public._db, "get_model_settings", lambda: {})
    monkeypatch.setattr(public, "provider_for_model", lambda *args, **kwargs: (provider, model))
    monkeypatch.setattr(public, "connection_for", lambda *args: {
        "id": provider, "kind": provider, "base_url": "https://provider.invalid", "api_key": "test-only",
    })


def _answering(sent: list, answer: dict) -> httpx.MockTransport:
    def respond(request):
        sent.append(request)
        return httpx.Response(200, json=answer)

    return httpx.MockTransport(respond)


def test_gemini_demo_takes_the_answer_not_gemmas_thoughts(monkeypatch):
    _route(monkeypatch, "gemini", "gemma-4-31b-it")
    sent = []
    transport = _answering(sent, {"candidates": [{"content": {"parts": [
        {"text": "The user wants a pond scene...", "thought": True}, {"text": "a pond at dusk"},
    ]}}]})
    assert public._generate_demo_instruction("pond", model=None, lang="en", transport=transport) == "a pond at dusk"
    assert json.loads(sent[0].content)["generationConfig"] == {
        "maxOutputTokens": 180 + 8192, "thinkingConfig": {"thinkingLevel": "minimal"}}
    # The key travels in a header, the model id as one quoted path segment.
    assert sent[0].headers["x-goog-api-key"] == "test-only"
    assert str(sent[0].url) == "https://provider.invalid/v1beta/models/gemma-4-31b-it:generateContent"


def test_claude_demo_sends_no_temperature_and_room_to_think(monkeypatch):
    _route(monkeypatch, "anthropic", "claude-sonnet-5")
    sent = []
    transport = _answering(sent, {"content": [{"type": "text", "text": "a pond at dusk"}]})
    assert public._generate_demo_instruction("pond", model=None, lang="en", transport=transport) == "a pond at dusk"
    body = json.loads(sent[0].content)
    assert "temperature" not in body and body["max_tokens"] == 180 + 8192
    assert body["messages"] == [{"role": "user", "content": "pond"}]
