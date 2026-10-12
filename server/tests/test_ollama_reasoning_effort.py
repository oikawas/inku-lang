import json
import types

import pytest

from inku_server.openai_request import openai_sampling
from inku_server.vision_client import _request


def _connection(provider_id):
    base = {"ollama": "http://localhost:11434/v1", "ollama-cloud": "https://ollama.com/v1"}.get(
        provider_id, "https://integrate.api.nvidia.com/v1")
    return {"id": provider_id, "kind": "openai_compatible", "base_url": base, "api_key": "test-only"}


# gpt-oss lists only low, medium and high, so "none" fell back to its default
# and reasoned through 2,048 tokens on Ollama Cloud (draw, 2026-10-12).
@pytest.mark.parametrize(("provider_id", "model", "expected"), [
    ("ollama-cloud", "gemma4:31b", {"max_tokens": 2048, "temperature": 0.3, "reasoning_effort": "none"}),
    ("ollama-cloud", "gpt-oss:20b", {"max_tokens": 2048 + 8192, "temperature": 0.3, "reasoning_effort": "low"}),
    ("ollama-cloud", "gpt-oss:120b", {"max_tokens": 2048 + 8192, "temperature": 0.3, "reasoning_effort": "low"}),
    ("ollama", "gpt-oss:20b", {"max_tokens": 2048 + 8192, "temperature": 0.3, "reasoning_effort": "low"}),
    ("nvidia", "openai/gpt-oss-120b", {"max_tokens": 2048, "temperature": 0.3}),
])
def test_ollama_is_asked_for_the_least_thinking_its_model_takes(provider_id, model, expected):
    assert openai_sampling(_connection(provider_id), model, max_tokens=2048, temperature=0.3) == expected


def test_vision_asks_ollama_cloud_for_no_thinking():
    _, _, body = _request(_connection("ollama-cloud"), "gemma4:31b", system="s", text="t", images=[],
                          temperature=0.35, max_tokens=320)
    assert body["reasoning_effort"] == "none" and body["max_tokens"] == 320


def test_demo_asks_ollama_cloud_gpt_oss_for_its_lowest_level(monkeypatch):
    from inku_server.api_core.routers import public

    monkeypatch.setattr(public._db, "get_model_settings", lambda: {})
    monkeypatch.setattr(public, "provider_for_model", lambda *args, **kwargs: ("ollama-cloud", "gpt-oss:20b"))
    monkeypatch.setattr(public, "connection_for", lambda *args: _connection("ollama-cloud"))
    sent = []

    class Completions:
        def create(self, **kwargs):
            sent.append(kwargs)
            message = types.SimpleNamespace(content="a pond at dusk")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=Completions())))
    assert public._generate_demo_instruction("pond", model=None, lang="en") == "a pond at dusk"
    assert sent[0]["reasoning_effort"] == "low" and sent[0]["max_tokens"] == 180 + 8192
