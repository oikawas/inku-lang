"""The fields OpenAI's own API takes differently from other OpenAI-compatible servers."""

from __future__ import annotations

import re
from typing import Any

import httpx

# OpenAI's reasoning families answer 400 to any temperature but the default.
_OPENAI_FIXED_TEMPERATURE = re.compile(r"^(gpt-5|o\d)")
# gpt-5.1 and later take reasoning_effort "none"; gpt-5 itself and the o-series do not.
_OPENAI_REASONING_OFF = re.compile(r"^gpt-5\.\d")
_GEMMA4 = re.compile(r"^gemma[-_]?4(?:[-_]|$)", re.IGNORECASE)
# Ollama turns reasoning_effort into its think setting: "none" turns thinking
# off where a model allows it, and a name a model does not list falls back to
# that model's default (OpenAI compatibility, docs.ollama.com). gpt-oss lists
# only low, medium and high, so on Ollama Cloud gpt-oss:20b and :120b reasoned
# at their default through the whole 2,048-token budget and answered nothing
# (draw, 2026-10-12). It is sent its lowest level, with room for the reasoning
# that max_tokens also counts.
_OLLAMA_LEVELS_ONLY = re.compile(r"^gpt-oss(?:[:-]|$)")
OLLAMA_THINKING_ROOM_TOKENS = 8192


def openai_sampling(connection: dict, model: str, *, max_tokens: int, temperature: float) -> dict[str, Any]:
    """The length and temperature fields an OpenAI-compatible chat request carries.

    OpenAI's own API refuses `max_tokens` for the gpt-5 and o-series models and
    asks for `max_completion_tokens`, which every chat model there accepts; the
    reasoning families also refuse a temperature other than the default, and
    gpt-5.6 refuses function tools in /v1/chat/completions while it reasons
    ("set reasoning_effort to 'none'", seen on Pentala 2026-09-28), so the
    gpt-5.1-and-later models are asked not to reason. That also keeps a short
    answer from being spent on reasoning before it is written. Other
    OpenAI-compatible servers (NVIDIA, Ollama and the like) keep the fields
    they have always been sent. The explicit MLX profile also disables thinking
    in the model's chat template so the answer has the full output budget.
    Gemma 4 on MLX uses its model card's sampling settings: the generic low
    temperature made a constrained work plan repeat layers until truncation.
    Ollama, local and cloud, is asked for no thinking, or for gpt-oss, which
    cannot stop, the lowest level and room for it. Gemma 4 on NVIDIA NIM thinks
    unless its chat template is told not to: the hosted API's
    chat_template_kwargs defaults to {"enable_thinking": true}
    (docs.api.nvidia.com, google-gemma-4-31b-it, read 2026-10-13), so it is
    turned off there as it is on MLX.
    """
    if httpx.URL(str(connection["base_url"])).host != "api.openai.com":
        fields = {"max_tokens": max_tokens, "temperature": temperature}
        if connection.get("api_profile") == "mlx":
            fields["enable_thinking"] = False
            if _GEMMA4.match(model.rsplit("/", 1)[-1]):
                fields.update(temperature=1.0, top_p=0.95, top_k=64)
        if connection.get("id") == "nvidia" and _GEMMA4.match(model.rsplit("/", 1)[-1]):
            fields["chat_template_kwargs"] = {"enable_thinking": False}
        if connection.get("id") in {"ollama", "ollama-cloud"}:
            if _OLLAMA_LEVELS_ONLY.match(model):
                fields.update(max_tokens=max_tokens + OLLAMA_THINKING_ROOM_TOKENS, reasoning_effort="low")
            else:
                fields["reasoning_effort"] = "none"
        return fields
    fields: dict[str, Any] = {"max_completion_tokens": max_tokens}
    if not _OPENAI_FIXED_TEMPERATURE.match(model):
        fields["temperature"] = temperature
    if _OPENAI_REASONING_OFF.match(model):
        fields["reasoning_effort"] = "none"
    return fields


def openai_output_limit_record(data: dict[str, Any]) -> dict[str, Any] | None:
    """What a chat completion cut off at its token limit spent its budget on; None when it was not cut off."""
    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    if first.get("finish_reason") != "length":
        return None
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    return {
        "finish_reason": "length",
        "output_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
        "has_reasoning": bool(message.get("reasoning") or message.get("reasoning_content")),
        "has_text": bool(message.get("content")),
        "has_tool_call": bool(message.get("tool_calls")),
    }
