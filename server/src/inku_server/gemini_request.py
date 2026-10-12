"""The thinking level a Gemini generateContent request carries."""

from __future__ import annotations

import re
from typing import Any

# The lowest level each model takes, from the thinking-levels table
# (aistudio.google.com/docs/thinking, read 2026-10-12). A level the model does
# not list is refused, and the newer models dropped "minimal": the Pro models
# and gemini-3.8-flash start at "low", as do gemini-2.5-pro and -flash.
# gemini-2.5-flash-lite thinks only when a level is sent, so it is sent none.
# Every other model (gemini-3.5-flash-lite, gemini-3.6-flash,
# gemini-3-flash-preview, Gemma 4) takes "minimal".
_LOWEST_LEVEL: tuple[tuple[re.Pattern[str], str | None], ...] = (
    (re.compile(r"^gemini-2\.5-flash-lite(?:-|$)"), None),
    (re.compile(r"^gemini-2\.5-flash(?:-|$)"), "low"),
    (re.compile(r"^gemini-[\d.]+-pro(?:-|$)"), "low"),
    (re.compile(r"^gemini-3\.8-flash(?:-|$)"), "low"),
)


def gemini_thinking(model: str) -> dict[str, Any]:
    """The generationConfig fields that keep a model's thinking to its lowest level.

    A thinking model otherwise spends the small output budget before it writes
    the answer, since maxOutputTokens counts the thought tokens.
    """
    name = model.removeprefix("models/")
    level = "minimal"
    for pattern, lowest in _LOWEST_LEVEL:
        if pattern.match(name):
            level = lowest
            break
    return {} if level is None else {"thinkingConfig": {"thinkingLevel": level}}
