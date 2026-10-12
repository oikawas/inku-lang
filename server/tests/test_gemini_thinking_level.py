import pytest

from inku_server.gemini_request import gemini_max_output_tokens, gemini_thinking
from inku_server.vision_client import _request


# "minimal" only where the thinking-levels table (aistudio.google.com/docs/thinking,
# 2026-10-12) or draw's 2026-10-12 runs show it is taken; "low" otherwise, which
# the newer models and the -latest aliases need ("Thinking level MINIMAL is not
# supported for this model"); none for a model that refuses any level.
@pytest.mark.parametrize(("model", "level"), [
    ("gemini-3.8-flash", "low"),
    ("gemini-3.7-flash", "low"),
    ("gemini-flash-latest", "low"),
    ("gemini-pro-latest", "low"),
    ("gemini-3.1-pro-preview", "low"),
    ("gemini-3-pro-preview", "low"),
    ("gemini-2.5-pro", "low"),
    ("gemini-2.5-flash", "low"),
    ("gemini-3.6-flash", "minimal"),
    ("gemini-3.5-flash-lite", "minimal"),
    ("gemini-flash-lite-latest", "minimal"),
    ("gemini-3-flash-preview", "minimal"),
    ("gemini-3.1-flash-lite-image", "minimal"),
    ("models/gemini-3.6-flash", "minimal"),
    ("gemma-4-31b-it", "minimal"),
    ("gemini-2.5-flash-lite", None),
    ("gemini-2.5-flash-image", None),
])
def test_each_model_is_sent_a_thinking_level_it_takes(model, level):
    expected = {} if level is None else {"thinkingConfig": {"thinkingLevel": level}}
    assert gemini_thinking(model) == expected


# maxOutputTokens counts the thoughts: gemini-3.1-pro-preview thought 683 of 1,024.
@pytest.mark.parametrize(("model", "room"), [("gemini-3.1-pro-preview", 8192), ("gemini-3.5-flash-lite", 8192),
                                             ("gemma-4-31b-it", 8192), ("gemini-2.5-flash-lite", 0)])
def test_a_thinking_model_gets_room_beside_the_answer(model, room):
    assert gemini_max_output_tokens(model, 1024) == 1024 + room


def test_vision_sends_the_thinking_level_the_room_and_no_temperature():
    connection = {"kind": "gemini", "base_url": "https://generativelanguage.invalid", "api_key": "test-only"}
    _, _, body = _request(connection, "gemini-3.8-flash", system="s", text="t", images=[],
                          temperature=0.35, max_tokens=320)
    assert body["generationConfig"] == {"maxOutputTokens": 320 + 8192, "thinkingConfig": {"thinkingLevel": "low"}}
