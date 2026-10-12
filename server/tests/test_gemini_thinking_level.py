import pytest

from inku_server.gemini_request import gemini_thinking
from inku_server.vision_client import _request


# The thinking-levels table (aistudio.google.com/docs/thinking, 2026-10-12):
# a model is sent the lowest level it lists, or none when it thinks only on request.
@pytest.mark.parametrize(("model", "level"), [
    ("gemini-3.8-flash", "low"),
    ("gemini-3.6-flash", "minimal"),
    ("gemini-3.5-flash-lite", "minimal"),
    ("gemini-3.1-pro-preview", "low"),
    ("gemini-3-flash-preview", "minimal"),
    ("gemini-3-pro-preview", "low"),
    ("gemini-2.5-pro", "low"),
    ("gemini-2.5-flash", "low"),
    ("gemini-2.5-flash-lite", None),
    ("gemma-4-31b-it", "minimal"),
])
def test_each_model_is_sent_its_lowest_thinking_level(model, level):
    expected = {} if level is None else {"thinkingConfig": {"thinkingLevel": level}}
    assert gemini_thinking(model) == expected


def test_vision_sends_the_model_its_lowest_thinking_level():
    connection = {"kind": "gemini", "base_url": "https://generativelanguage.invalid", "api_key": "test-only"}
    _, _, body = _request(connection, "gemini-3.8-flash", system="s", text="t", images=[],
                          temperature=0.0, max_tokens=64)
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
