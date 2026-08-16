"""Bounded Vision advice for user-initiated autonomous refinement."""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Callable

from inku_analysis.rasterizer import svg_to_png

from .model_settings import connection_for, provider_for_model

ALLOWED_KINDS = ("reinterpretation", "catalog_change", "layout_change", "touch_change", "variation")


def _png_data_url(svg: str) -> str:
    png = svg_to_png(svg, width=768, height=768)
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _system_prompt(language: str) -> str:
    if language == "en":
        return (
            "You are a visual adviser in a bounded artwork-refinement loop. Observe only visible facts and "
            "alignment with the supplied instruction. Never score, rank, accept, reject, praise, or condemn. "
            "Suggest one concrete direction to try next without claiming it is better. Return JSON only with "
            "observation, next_direction, and suggested_kind."
        )
    return (
        "あなたは世代数を限定した作品推敲ループの視覚的助言者です。画像に見える事実と、与えられた指示との対応だけを観察してください。"
        "点数、順位、合否、称賛、否定を行わず、より良いと断定せずに次に試す具体的な方向を一つ提案してください。"
        "observation、next_direction、suggested_kindを持つJSONだけを返してください。"
    )


def _vision_chat(
    *, model: str, language: str, payload: dict[str, Any], image: str, settings: dict[str, Any]
) -> str:
    provider, model_id = provider_for_model(model, stage="stage1", settings=settings)
    connection = connection_for(provider, settings)
    if connection.get("kind") != "openai_compatible":
        raise ValueError("Vision autonomous refinement currently requires an OpenAI-compatible provider")
    if connection.get("requires_api_key") and not connection.get("api_key"):
        raise ValueError(f"{provider} API key is not configured")
    from openai import OpenAI

    instruction = (
        ("Observe this generation and return bounded refinement advice. Context:\n" if language == "en" else
         "この世代を観察し、限定された推敲助言を返してください。文脈:\n")
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )
    client = OpenAI(
        base_url=connection["base_url"],
        api_key=connection.get("api_key") or "none",
        timeout=float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "180")),
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": _system_prompt(language)},
            {"role": "user", "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": image}},
            ]},
        ],
        temperature=0.35,
        max_tokens=320,
    )
    return (response.choices[0].message.content or "").strip()


def _json_body(raw: str) -> str:
    """The object an advice answer carries, with whatever a chat model wrapped it in.

    One rule, not two: take the first brace to the last. That covers a ``` fence
    and prose either side of the object alike, so there is no second path whose
    removal changes nothing. It guesses at no content -- what comes out still has
    to parse, and an answer with no braces in it is handed on untouched, so it
    fails exactly where it failed before.

    This replaces a fence strip written as `\\s` inside a raw string, which asks
    for a literal backslash followed by zero or more 's' and so matched nothing.
    A vision model fences its answer by default, which meant the whole path
    returned "invalid refinement advice JSON" rather than degrading.
    """
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return text
    return text[start : end + 1]


def _parse_json(raw: str) -> dict[str, Any]:
    clean = _json_body(raw)
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise ValueError("Vision model returned invalid refinement advice JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Vision model returned invalid refinement advice")
    return parsed


def vision_refine_advice(
    *,
    svg: str,
    instruction: str,
    direction: str,
    enabled_kinds: list[str],
    model: str,
    language: str,
    settings: dict[str, Any],
    reader: Callable[..., str] | None = None,
) -> dict[str, str]:
    kinds = [kind for kind in enabled_kinds if kind in ALLOWED_KINDS]
    if not kinds:
        raise ValueError("At least one refinement kind is required")
    payload = {
        "instruction": instruction,
        "user_direction": direction,
        "allowed_suggested_kinds": kinds,
        "constraints": {
            "no_score": True,
            "no_ranking": True,
            "no_accept_reject": True,
            "human_makes_final_choice": True,
        },
    }
    read = reader or _vision_chat
    parsed = _parse_json(read(
        model=model,
        language=language,
        payload=payload,
        image=_png_data_url(svg),
        settings=settings,
    ))
    observation = str(parsed.get("observation") or "").strip()
    next_direction = str(parsed.get("next_direction") or "").strip()
    suggested_kind = str(parsed.get("suggested_kind") or "").strip()
    if not observation or not next_direction:
        raise ValueError("Vision model returned empty refinement advice")
    if suggested_kind not in kinds:
        suggested_kind = kinds[0]
    return {
        "observation": observation[:2000],
        "next_direction": next_direction[:2000],
        "suggested_kind": suggested_kind,
        "model": model,
    }
