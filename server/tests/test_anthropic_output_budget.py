import pytest

from inku_server.anthropic_request import anthropic_max_tokens


# Thinking with no `thinking` field: the Claude 5 models and Mythos Preview do,
# Claude 4.x does not (platform.claude.com/docs/en/build-with-claude/thinking).
@pytest.mark.parametrize(("model", "room"), [
    ("claude-opus-5-5", 8192),
    ("claude-sonnet-5-5", 8192),
    ("claude-haiku-5-5", 8192),
    ("claude-fable-5-1", 8192),
    ("claude-fable-5", 8192),
    ("claude-opus-5", 8192),
    ("claude-sonnet-5", 8192),
    ("claude-mythos-preview", 8192),
    ("claude-opus-4-7", 0),
    ("claude-sonnet-4-6", 0),
    ("claude-haiku-4-5-20251001", 0),
])
def test_a_model_that_thinks_unasked_gets_room_beside_the_answer(model, room):
    assert anthropic_max_tokens(model, 2048) == 2048 + room
