import json

import httpx
import pytest

from inku_server import provider_wire

_NIM = {"id": "nvidia", "kind": "openai_compatible", "base_url": "https://integrate.api.nvidia.com/v1", "api_key": "k"}
_MLX = {"id": "mac-models", "kind": "openai_compatible", "base_url": "http://127.0.0.1:8080/v1", "api_key": "k",
        "api_profile": "mlx"}


def _sampling(connection: dict, model: str, *, max_tokens: int, temperature: float) -> dict:
    """The length and sampling fields the shared core writes for a chat request."""
    built = provider_wire.text_request(connection, model, system="s", text="t", images=[], temperature=temperature,
                                       max_tokens=max_tokens)
    return {key: value for key, value in json.loads(built["body"]).items() if key not in {"model", "stream", "messages"}}


# NIM's hosted Gemma 4 defaults chat_template_kwargs to {"enable_thinking": true}
# (docs.api.nvidia.com, google-gemma-4-31b-it); other NIM models do not take it.
@pytest.mark.parametrize(("model", "kwargs"), [
    ("google/gemma-4-31b-it", {"chat_template_kwargs": {"enable_thinking": False}}),
    ("meta/llama-3.2-90b-vision-instruct", {}),
    ("google/gemma-3n-e4b-it", {}),
])
def test_nim_turns_off_only_gemma_4s_thinking(model, kwargs):
    assert _sampling(_NIM, model, max_tokens=2048, temperature=0.3) == {
        "max_tokens": 2048, "temperature": 0.3, **kwargs}


def test_vision_carries_nims_chat_template_switch():
    built = provider_wire.text_request(_NIM, "google/gemma-4-31b-it", system="s", text="t",
                                       images=["data:image/png;base64,AAAA"], temperature=0.35, max_tokens=320)
    assert json.loads(built["body"])["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.parametrize(("provider", "connection", "model", "extra"), [
    ("nvidia", _NIM, "google/gemma-4-31b-it", {"chat_template_kwargs": {"enable_thinking": False}}),
    # MLX's own fields once reached the SDK's create() as keywords it did not take.
    ("mac-models", _MLX, "mlx-community/gemma-4-e4b-it-4bit", {"enable_thinking": False, "top_k": 64}),
])
def test_demo_sends_a_servers_own_fields_in_the_body(monkeypatch, provider, connection, model, extra):
    from inku_server.api_core.routers import public

    monkeypatch.setattr(public._db, "get_model_settings", lambda: {})
    monkeypatch.setattr(public, "provider_for_model", lambda *args, **kwargs: (provider, model))
    monkeypatch.setattr(public, "connection_for", lambda *args: connection)
    sent = []

    def answer(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "a pond at dusk"}}]})

    assert public._generate_demo_instruction("pond", model=None, lang="en",
                                             transport=httpx.MockTransport(answer)) == "a pond at dusk"
    assert {key: sent[0][key] for key in extra} == extra and sent[0]["max_tokens"] == 180
