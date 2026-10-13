"""The fields OpenAI's own API takes differently from other OpenAI-compatible servers."""

from __future__ import annotations

import re
from typing import Any

import httpx

# OpenAI's reasoning families answer 400 to any temperature but the default;
# the GPT-6 guide removes temperature and top_p whenever reasoning is not none.
_OPENAI_REASONING = re.compile(r"^(gpt-5|gpt-6|o\d)")
# gpt-5.1 and later 5.x, GPT-6 Sol and GPT-6 Luna take reasoning_effort "none";
# GPT-6 Astra, GPT-6.1 Sol, gpt-5 itself and the o-series do not (reasoning and
# latest-model guides, developers.openai.com, read 2026-10-13).
_OPENAI_REASONING_OFF = re.compile(r"^(gpt-5\.\d|gpt-6-(?:sol|luna)(?:-|$))")
# Reasoning counts toward the output limit, and OpenAI recommends reserving at
# least 25,000 tokens for reasoning and output; a model that cannot stop is
# asked for its lowest level ("low": GPT-6 Astra and 6.1 Sol take nothing lower).
OPENAI_REASONING_ROOM_TOKENS = 25000
OPENAI_API_HOST = "api.openai.com"
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
    models that can stop reasoning (gpt-5.1 and later, GPT-6 Sol and Luna) are
    asked not to. That also keeps a short answer from being spent on reasoning
    before it is written; the models that cannot stop are asked for their
    lowest level, with room for it. Other
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
    if not is_openai_api(connection):
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
    if not _OPENAI_REASONING.match(model):
        fields["temperature"] = temperature
    elif _OPENAI_REASONING_OFF.match(model):
        fields["reasoning_effort"] = "none"
    else:
        fields.update(max_completion_tokens=max_tokens + OPENAI_REASONING_ROOM_TOKENS, reasoning_effort="low")
    return fields


def is_openai_api(connection: dict) -> bool:
    """Whether the connection is OpenAI's own API rather than another OpenAI-compatible server."""
    return httpx.URL(str(connection["base_url"])).host == OPENAI_API_HOST


def openai_responses_body(connection: dict, model: str, prompt: dict, *, response_name: str,
                          max_tokens: int, temperature: float) -> dict[str, Any]:
    """A pipeline request to OpenAI's Responses API, the one function tool required.

    Chat Completions takes no function tools from GPT-6 Astra and GPT-6.1 Sol,
    and from GPT-6 Sol and Luna only without reasoning; Responses takes them from
    every model (latest-model guide). The fields follow openai_sampling, renamed
    for Responses; the request is not stored, as Chat Completions' were not.
    """
    sampling = openai_sampling(connection, model, max_tokens=max_tokens, temperature=temperature)
    body: dict[str, Any] = {
        "model": model, "store": False, "instructions": prompt["system"],
        "input": [{"role": "user", "content": prompt["message"]}],
        "tools": [{"type": "function", "name": response_name, "description": "Submit the requested pipeline response.",
                   "parameters": prompt["response_schema"], "strict": False}],
        "tool_choice": "required", "parallel_tool_calls": False,
        "max_output_tokens": sampling["max_completion_tokens"],
    }
    if "temperature" in sampling:
        body["temperature"] = sampling["temperature"]
    if "reasoning_effort" in sampling:
        body["reasoning"] = {"effort": sampling["reasoning_effort"]}
    return body


def openai_responses_answer(data: dict[str, Any], response_name: str) -> str:
    """The one function call's arguments, or the output text a model answered with instead."""
    if data.get("status") != "completed":
        raise TypeError("provider response did not complete")
    output = [item for item in data["output"] if isinstance(item, dict)]
    calls = [item for item in output if item.get("type") == "function_call"]
    if calls:
        if len(calls) != 1 or calls[0].get("name") != response_name or not isinstance(calls[0].get("arguments"), str):
            raise TypeError("provider returned an unexpected tool call")
        return calls[0]["arguments"]
    return "".join(str(part.get("text", "")) for item in output if item.get("type") == "message"
                   for part in item.get("content") or [] if isinstance(part, dict) and part.get("type") == "output_text")


def openai_responses_output_limit_record(data: dict[str, Any]) -> dict[str, Any] | None:
    """What a Responses answer cut off at max_output_tokens spent its budget on; None when it was not cut off."""
    details = data.get("incomplete_details") if isinstance(data.get("incomplete_details"), dict) else {}
    if data.get("status") != "incomplete" or details.get("reason") != "max_output_tokens":
        return None
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    usage_details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
    output = [item for item in data.get("output") or [] if isinstance(item, dict)]
    return {
        "incomplete_reason": "max_output_tokens",
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": usage_details.get("reasoning_tokens"),
        "has_text": any(item.get("type") == "message" for item in output),
        "has_function_call": any(item.get("type") == "function_call" for item in output),
    }


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
