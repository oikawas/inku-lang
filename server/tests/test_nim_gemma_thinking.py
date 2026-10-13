import types

import pytest

from inku_server.openai_request import openai_sampling
from inku_server.vision_client import _request

_NIM = {"id": "nvidia", "kind": "openai_compatible", "base_url": "https://integrate.api.nvidia.com/v1", "api_key": "k"}
_MLX = {"id": "mac-models", "kind": "openai_compatible", "base_url": "http://127.0.0.1:8080/v1", "api_key": "k",
        "api_profile": "mlx"}


# NIM's hosted Gemma 4 defaults chat_template_kwargs to {"enable_thinking": true}
# (docs.api.nvidia.com, google-gemma-4-31b-it); other NIM models do not take it.
@pytest.mark.parametrize(("model", "kwargs"), [
    ("google/gemma-4-31b-it", {"chat_template_kwargs": {"enable_thinking": False}}),
    ("meta/llama-3.2-90b-vision-instruct", {}),
    ("google/gemma-3n-e4b-it", {}),
])
def test_nim_turns_off_only_gemma_4s_thinking(model, kwargs):
    assert openai_sampling(_NIM, model, max_tokens=2048, temperature=0.3) == {
        "max_tokens": 2048, "temperature": 0.3, **kwargs}


def test_vision_carries_nims_chat_template_switch():
    _, _, body = _request(_NIM, "google/gemma-4-31b-it", system="s", text="t", images=[],
                          temperature=0.35, max_tokens=320)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


class _StrictCompletions:
    """The SDK's create() names its fields and takes no others."""

    def __init__(self, sent):
        self.sent = sent

    def create(self, *, model, messages, max_tokens=None, max_completion_tokens=None, temperature=None,
               top_p=None, reasoning_effort=None, extra_body=None):
        self.sent.append({"max_tokens": max_tokens, "temperature": temperature, "top_p": top_p,
                          "reasoning_effort": reasoning_effort, "extra_body": extra_body})
        message = types.SimpleNamespace(content="a pond at dusk")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


@pytest.mark.parametrize(("provider", "connection", "model", "extra"), [
    ("nvidia", _NIM, "google/gemma-4-31b-it", {"chat_template_kwargs": {"enable_thinking": False}}),
    # MLX's own fields once reached create() as keywords it does not take.
    ("mac-models", _MLX, "mlx-community/gemma-4-e4b-it-4bit", {"enable_thinking": False, "top_k": 64}),
])
def test_demo_sends_a_servers_own_fields_in_the_body(monkeypatch, provider, connection, model, extra):
    from inku_server.api_core.routers import public

    monkeypatch.setattr(public._db, "get_model_settings", lambda: {})
    monkeypatch.setattr(public, "provider_for_model", lambda *args, **kwargs: (provider, model))
    monkeypatch.setattr(public, "connection_for", lambda *args: connection)
    sent = []
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_StrictCompletions(sent))))
    assert public._generate_demo_instruction("pond", model=None, lang="en") == "a pond at dusk"
    assert sent[0]["extra_body"] == extra and sent[0]["max_tokens"] == 180
