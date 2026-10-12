import io
import json
import types

from inku_server.api_core.routers import public


def _route(monkeypatch, provider, model):
    monkeypatch.setattr(public._db, "get_model_settings", lambda: {})
    monkeypatch.setattr(public, "provider_for_model", lambda *args, **kwargs: (provider, model))
    monkeypatch.setattr(public, "connection_for", lambda *args: {
        "id": provider, "kind": provider, "base_url": "https://provider.invalid", "api_key": "test-only",
    })


def test_gemini_demo_takes_the_answer_not_gemmas_thoughts(monkeypatch):
    _route(monkeypatch, "gemini", "gemma-4-31b-it")
    sent = []

    def urlopen(request, timeout):
        sent.append(json.loads(request.data))
        return io.BytesIO(json.dumps({"candidates": [{"content": {"parts": [
            {"text": "The user wants a pond scene...", "thought": True}, {"text": "a pond at dusk"},
        ]}}]}).encode())

    monkeypatch.setattr(public.urllib.request, "urlopen", urlopen)
    assert public._generate_demo_instruction("pond", model=None, lang="en") == "a pond at dusk"
    assert sent[0]["generationConfig"] == {"maxOutputTokens": 180 + 8192, "thinkingConfig": {"thinkingLevel": "minimal"}}


def test_claude_demo_sends_no_temperature_and_room_to_think(monkeypatch):
    _route(monkeypatch, "anthropic", "claude-sonnet-5")
    sent = []

    class Messages:
        def create(self, **kwargs):
            sent.append(kwargs)
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="a pond at dusk")])

    monkeypatch.setattr("anthropic.Anthropic", lambda **kwargs: types.SimpleNamespace(messages=Messages()))
    assert public._generate_demo_instruction("pond", model=None, lang="en") == "a pond at dusk"
    assert "temperature" not in sent[0] and sent[0]["max_tokens"] == 180 + 8192
