import json

import pytest

from inku_server import provider_wire

_OPENAI = {"id": "openai", "kind": "openai_compatible", "base_url": "https://api.openai.com/v1", "api_key": "k"}


def _body(model: str) -> dict:
    built = provider_wire.text_request(_OPENAI, model, system="s", text="t", images=[], temperature=0.35, max_tokens=320)
    return json.loads(built["body"])


# Chat Completions (Vision, the colophon, the demo instruction). The reasoning
# families take only the default temperature; those that can stop reasoning are
# asked to, and the rest reason "low" with 25,000 tokens of room
# (developers.openai.com reasoning and latest-model guides, 2026-10-13). The rule
# is the shared core's (provider_wire); these are the models it names.
@pytest.mark.parametrize(("model", "expected"), [
    ("gpt-4.1", {"max_completion_tokens": 320, "temperature": 0.35}),
    ("gpt-5.1", {"max_completion_tokens": 320, "reasoning_effort": "none"}),
    ("gpt-5.6-luna", {"max_completion_tokens": 320, "reasoning_effort": "none"}),
    ("gpt-6-luna", {"max_completion_tokens": 320, "reasoning_effort": "none"}),
    ("gpt-6-sol", {"max_completion_tokens": 320, "reasoning_effort": "none"}),
    ("gpt-6.1-sol", {"max_completion_tokens": 320 + 25000, "reasoning_effort": "low"}),
    ("gpt-6-astra", {"max_completion_tokens": 320 + 25000, "reasoning_effort": "low"}),
    ("gpt-5", {"max_completion_tokens": 320 + 25000, "reasoning_effort": "low"}),
    ("o3", {"max_completion_tokens": 320 + 25000, "reasoning_effort": "low"}),
])
def test_each_openai_model_gets_the_reasoning_it_takes(model, expected):
    body = _body(model)
    sampling = {key: body[key] for key in ("max_tokens", "max_completion_tokens", "temperature", "reasoning_effort")
                if key in body}
    assert sampling == expected


def test_vision_asks_gpt_6_1_sol_for_low_reasoning_and_no_temperature():
    body = _body("gpt-6.1-sol")
    assert body["reasoning_effort"] == "low" and body["max_completion_tokens"] == 320 + 25000
    assert "temperature" not in body
