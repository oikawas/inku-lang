"""Retry helpers for transient LLM API failures."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def call_with_llm_retry(operation: Callable[[], T]) -> T:
    """Retry transient rate-limit failures from OpenAI-compatible APIs."""

    attempts = max(1, int(os.getenv("INKU_LLM_RETRY_ATTEMPTS", "4")))
    base_delay = max(0.0, float(os.getenv("INKU_LLM_RETRY_BASE_DELAY", "2.0")))
    max_delay = max(base_delay, float(os.getenv("INKU_LLM_RETRY_MAX_DELAY", "20.0")))

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt == attempts - 1:
                raise
            retry_after = _retry_after_seconds(exc)
            delay = retry_after if retry_after is not None else min(max_delay, base_delay * (2**attempt))
            if delay > 0:
                time.sleep(delay)

    raise RuntimeError("unreachable LLM retry state")


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True

    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True

    text = str(exc).lower()
    return "429" in text and ("too many requests" in text or "rate" in text)


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None

    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None

    try:
        return max(0.0, float(value))
    except ValueError:
        return None
