"""Retry helpers for transient LLM API failures."""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def call_with_llm_retry(operation: Callable[[], T]) -> T:
    """Retry transient failures from LLM APIs.

    NVIDIA NIM is used here as a free development endpoint. It has no SLA, and
    can return transient 429/5xx connection errors or stall behind queueing.
    Permanent schema/prompt errors should still fail immediately.
    """

    attempts = max(1, int(os.getenv("INKU_LLM_RETRY_ATTEMPTS", "4")))
    base_delay = max(0.0, float(os.getenv("INKU_LLM_RETRY_BASE_DELAY", "2.0")))
    max_delay = max(base_delay, float(os.getenv("INKU_LLM_RETRY_MAX_DELAY", "20.0")))
    jitter = max(0.0, float(os.getenv("INKU_LLM_RETRY_JITTER", "0.25")))

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            if not _is_transient_error(exc) or attempt == attempts - 1:
                raise
            retry_after = _retry_after_seconds(exc)
            delay = retry_after if retry_after is not None else min(max_delay, base_delay * (2**attempt))
            if retry_after is None and jitter > 0:
                delay += random.uniform(0.0, jitter)
            if delay > 0:
                time.sleep(delay)

    raise RuntimeError("unreachable LLM retry state")


def _is_transient_error(exc: Exception) -> bool:
    if _is_rate_limit_error(exc):
        return True

    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if status_code in {408, 500, 502, 503, 504} or response_status in {408, 500, 502, 503, 504}:
        return _looks_transient_text(exc)

    return _looks_transient_text(exc)


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True

    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True

    text = str(exc).lower()
    return "429" in text and ("too many requests" in text or "rate" in text)


def _looks_transient_text(exc: Exception) -> bool:
    text = str(exc).lower()
    transient_markers = (
        "inference connection error",
        "connection error",
        "connection reset",
        "connection aborted",
        "temporarily unavailable",
        "service unavailable",
        "gateway",
        "bad gateway",
        "timeout",
        "timed out",
        "read timeout",
        "408",
        "500",
        "502",
        "503",
        "504",
    )
    permanent_markers = (
        "badrequest",
        "bad request",
        "invalid_request",
        "failed to compile",
        "json grammar",
        "schema",
        "authentication",
        "unauthorized",
        "forbidden",
        "not found",
    )
    if any(marker in text for marker in permanent_markers):
        return False
    return any(marker in text for marker in transient_markers)


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
