"""The fields OpenAI's own API takes differently from other OpenAI-compatible servers."""

from __future__ import annotations

import re
from typing import Any

import httpx

# OpenAI's reasoning families answer 400 to any temperature but the default.
_OPENAI_FIXED_TEMPERATURE = re.compile(r"^(gpt-5|o\d)")


def openai_sampling(connection: dict, model: str, *, max_tokens: int, temperature: float) -> dict[str, Any]:
    """The length and temperature fields an OpenAI-compatible chat request carries.

    OpenAI's own API refuses `max_tokens` for the gpt-5 and o-series models and
    asks for `max_completion_tokens`, which every chat model there accepts; the
    reasoning families also refuse a temperature other than the default. Other
    OpenAI-compatible servers (NVIDIA, Ollama and the like) keep the fields
    they have always been sent.
    """
    if httpx.URL(str(connection["base_url"])).host != "api.openai.com":
        return {"max_tokens": max_tokens, "temperature": temperature}
    fields: dict[str, Any] = {"max_completion_tokens": max_tokens}
    if not _OPENAI_FIXED_TEMPERATURE.match(model):
        fields["temperature"] = temperature
    return fields
