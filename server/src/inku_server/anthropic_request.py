"""The output budget an Anthropic Messages request carries, and what a cut-off answer looked like."""

from __future__ import annotations

import re
from typing import Any

# The Claude 5 models and Mythos Preview think adaptively when a request sends
# no `thinking` field; Claude 4.x does not (per-model table,
# platform.claude.com/docs/en/build-with-claude/thinking, read 2026-10-13).
# Their thinking counts toward max_tokens, so the answer's budget alone was
# spent before the answer: Sonnet 5 thought 2,047-2,048 of a 2,048 drawing
# budget, and a 320-token Vision advice JSON was cut (draw, 2026-10-12).
# Thinking is left on rather than disabled: Opus 5.5, Sonnet 5.5 and Fable
# refuse "disabled", and with it off Haiku 5.5 can skip the tool call it needs
# and Opus 5 can write a tool call as text.
_THINKS_BY_DEFAULT = re.compile(r"^claude-(?:(?:opus|sonnet|haiku|fable|mythos)-5(?:-|$)|mythos-preview(?:-|$))")
THINKING_ROOM_TOKENS = 8192


def anthropic_max_tokens(model: str, answer_tokens: int) -> int:
    """The answer's own budget, plus room for the thinking a model does unasked."""
    return answer_tokens + (THINKING_ROOM_TOKENS if _THINKS_BY_DEFAULT.match(model) else 0)


def output_limit_record(data: dict[str, Any]) -> dict[str, Any] | None:
    """What a response cut off at max_tokens spent its budget on; None when it was not cut off."""
    if data.get("stop_reason") != "max_tokens":
        return None
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    blocks = [block for block in data.get("content") or [] if isinstance(block, dict)]
    return {
        "stop_reason": "max_tokens",
        "output_tokens": usage.get("output_tokens"),
        "thinking_blocks": sum(1 for block in blocks if block.get("type") in {"thinking", "redacted_thinking"}),
        "has_text": any(block.get("type") == "text" and block.get("text") for block in blocks),
        "has_tool_use": any(block.get("type") == "tool_use" for block in blocks),
    }
