"""The thinking level and output budget a Gemini generateContent request carries."""

from __future__ import annotations

import re
from typing import Any

# Sent no level: gemini-2.5-flash-lite thinks only when a level is sent, and a
# model the Models API lists without `thinking` refuses one ("Thinking level is
# not supported for this model" from gemini-2.5-flash-image, draw, 2026-10-12).
_NO_LEVEL = re.compile(r"^(?:gemini-2\.5-flash-(?:lite|image)(?:-|$)|antigravity-)")
# "minimal" goes only to the models known to take it: those the thinking-levels
# table lists it for (aistudio.google.com/docs/thinking, read 2026-10-12) and
# the ids that answered with it in draw's 2026-10-12 runs. Every other model is
# sent "low", which each thinking model in that table takes but
# gemini-3.1-flash-lite-image, listed here. Sending "minimal" by default was
# refused by every newer model and by the -latest aliases ("Thinking level
# MINIMAL is not supported for this model": gemini-3.7-flash, gemini-flash-latest,
# gemini-pro-latest), and an alias moves to whichever model is newest.
_MINIMAL = frozenset({
    "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest",
    "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview",
    "gemini-3.1-flash-image", "gemini-3.1-flash-image-preview", "gemini-3.1-flash-lite-image",
    "gemini-robotics-er-2-preview", "nano-banana-pro-preview", "gemini-nano-banana-2.1",
})
# maxOutputTokens counts the thought tokens: gemini-3.1-pro-preview thought 683
# and wrote 337 of a 1,024 budget before MAX_TOKENS, and gemini-3-pro-image
# thought 317 of 320 and wrote nothing (draw, 2026-10-12).
THINKING_ROOM_TOKENS = 8192


def _level(model: str) -> str | None:
    name = model.removeprefix("models/")
    if _NO_LEVEL.match(name):
        return None
    return "minimal" if name in _MINIMAL or name.startswith("gemma-") else "low"


def gemini_thinking(model: str) -> dict[str, Any]:
    """The generationConfig fields that keep a model's thinking to its lowest level."""
    level = _level(model)
    return {} if level is None else {"thinkingConfig": {"thinkingLevel": level}}


def gemini_max_output_tokens(model: str, answer_tokens: int) -> int:
    """The answer's own budget, plus room for the thinking a model still does at its lowest level."""
    return answer_tokens + (0 if _level(model) is None else THINKING_ROOM_TOKENS)


def gemini_output_limit_record(data: dict[str, Any]) -> dict[str, Any] | None:
    """What a response cut off at maxOutputTokens spent its budget on; None when it was not cut off."""
    candidates = data.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict) else {}
    if first.get("finishReason") != "MAX_TOKENS":
        return None
    usage = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
    content = first.get("content") if isinstance(first.get("content"), dict) else {}
    parts = [part for part in content.get("parts") or [] if isinstance(part, dict)]
    return {
        "finish_reason": "MAX_TOKENS",
        "output_tokens": usage.get("candidatesTokenCount"),
        "thought_tokens": usage.get("thoughtsTokenCount"),
        "has_text": any(part.get("text") and not part.get("thought") for part in parts),
        "has_function_call": any("functionCall" in part for part in parts),
    }
