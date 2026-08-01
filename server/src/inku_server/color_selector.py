"""Choose one color catalog by reading the description (Stage 1's model).

A catalog is only the color map the renderer paints with -- `interpreter.py` and
`composer.py` never mention one -- so this reads the raw description and nothing
downstream of it.  The normalized DDL was measured as the other candidate and
rejected: it answered `default` for 52 of 60 descriptions, because normalization
drops the subject (stage 0, 2026-08-01).

The call matches Stage 1's condition on purpose: same provider resolution, same
model, `temperature=0.3`.  No new role is added to `model_settings` -- whichever
model Stage 1 is set to is the one that reads the description here.
"""

from __future__ import annotations

import os
import re

from .color_catalogs import color_catalog_ids, color_catalogs
from .llm_retry import call_with_llm_retry
from .model_settings import connection_for, provider_for_model
from .provider_limits import provider_slot

MAX_TOKENS = 200
TEMPERATURE = 0.3

_JSON_ID_PATTERN = re.compile(r'"catalog_id"\s*:\s*"([A-Za-z0-9_]+)"')


def _current_model_settings() -> dict:
    from . import db as _db

    return _db.get_model_settings()


def build_catalog_card() -> str:
    """The card the model reads, generated from color_catalogs().

    Never hand-written: a catalog added to the module has to reach the prompt
    without a second edit.
    """
    lines = [
        "You choose one color catalog for a drawing, by reading its description.",
        "Read what the description is about -- its subject, its light, its season,",
        "its material -- and pick the catalog whose colors belong to it.",
        "",
        "Catalogs:",
    ]
    for catalog in color_catalogs():
        palette = ", ".join(
            str(entry.get("name_ja") or entry["name"]) for entry in catalog["palette"]
        )
        lines.append(
            f"- {catalog['id']}: {catalog['name']} -- {catalog['sub']}"
            f" / {catalog.get('sub_ja', '')} [{palette}]"
        )
    lines += [
        "",
        'Answer with JSON only: {"catalog_id": "<one id from the list>"}',
        "No other text.",
    ]
    return "\n".join(lines)


def _extract_catalog_id(raw: str) -> str | None:
    """Pull the answer out of the reply. Extraction only -- it does not judge.

    The JSON value is taken verbatim so that a wrong id arrives at the allowlist
    instead of being quietly discarded here; the allowlist in select_catalog_id
    is the single place a name is accepted or refused.
    """
    match = _JSON_ID_PATTERN.search(raw)
    if match:
        return match.group(1)
    # Some models answer with the bare id, so look for one. Longest first, or
    # `ink_season` would be found inside a reply naming `ink_season_x`.
    for candidate in sorted(color_catalog_ids(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(candidate)}\b", raw):
            return candidate
    return None


def _ask_model(text: str) -> str:
    settings = _current_model_settings()
    provider, model_id = provider_for_model(None, stage="stage1", settings=settings)
    connection = connection_for(provider, settings)
    system_prompt = build_catalog_card()

    if connection.get("kind") == "anthropic":
        from .interpreter import _interpret_anthropic

        answer, _, _ = _interpret_anthropic(
            text, model=model_id, system_prompt=system_prompt, settings=settings
        )
        return answer
    if connection.get("kind") == "gemini":
        from .interpreter import _interpret_gemini

        answer, _, _ = _interpret_gemini(
            text, model=model_id, system_prompt=system_prompt, settings=settings
        )
        return answer

    from openai import OpenAI

    client = OpenAI(
        base_url=connection["base_url"],
        api_key=connection.get("api_key") or "none",
        timeout=float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "120")),
        max_retries=0,
    )
    # Four of these in flight answered 429 to 120 of 160 calls during stage 0.
    # The slot and the retry are the two mechanisms the other stages already use.
    with provider_slot(provider):
        response = call_with_llm_retry(
            lambda: client.chat.completions.create(
                model=model_id,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                stream=False,
            )
        )
    return (response.choices[0].message.content or "").strip()


def select_catalog_id(source_text: str, *, fallback_id: str) -> str:
    """Choose one catalog by reading the description.

    Returns `fallback_id` when the call fails, comes back empty, or names an id
    that is not in the catalog list.  A model answering "ink_ink_season" was
    measured once in 60 calls, so the allowlist is not decoration.

    The fallback is the id the caller asked for, never `default`: a description
    that could not be read leaves the choice where it already was.
    """
    text = (source_text or "").strip()
    if not text:
        return fallback_id
    try:
        raw = _ask_model(text)
    except Exception:  # a provider failure must not fail the drawing
        return fallback_id
    candidate = _extract_catalog_id(raw)
    if candidate in color_catalog_ids():
        return str(candidate)
    return fallback_id
