from __future__ import annotations

import pytest

from inku_server import llm_retry


class RateLimitError(Exception):
    status_code = 429


class PermanentError(Exception):
    status_code = 500


class InferenceConnectionError(Exception):
    status_code = 500


def test_llm_retry_retries_rate_limit(monkeypatch):
    calls = 0
    delays: list[float] = []

    monkeypatch.setenv("INKU_LLM_RETRY_ATTEMPTS", "3")
    monkeypatch.setenv("INKU_LLM_RETRY_BASE_DELAY", "0.5")
    monkeypatch.setenv("INKU_LLM_RETRY_JITTER", "0")
    monkeypatch.setattr(llm_retry.time, "sleep", delays.append)

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RateLimitError("Error code: 429 - Too Many Requests")
        return "ok"

    assert llm_retry.call_with_llm_retry(operation) == "ok"
    assert calls == 3
    assert delays == [0.5, 1.0]


def test_llm_retry_retries_inference_connection_error(monkeypatch):
    calls = 0
    delays: list[float] = []

    monkeypatch.setenv("INKU_LLM_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("INKU_LLM_RETRY_BASE_DELAY", "0.5")
    monkeypatch.setenv("INKU_LLM_RETRY_JITTER", "0")
    monkeypatch.setattr(llm_retry.time, "sleep", delays.append)

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise InferenceConnectionError("Inference connection error while making inference request")
        return "ok"

    assert llm_retry.call_with_llm_retry(operation) == "ok"
    assert calls == 2
    assert delays == [0.5]


def test_llm_retry_does_not_retry_permanent_error(monkeypatch):
    calls = 0

    monkeypatch.setenv("INKU_LLM_RETRY_ATTEMPTS", "3")
    monkeypatch.setattr(llm_retry.time, "sleep", lambda delay: None)

    def operation() -> str:
        nonlocal calls
        calls += 1
        raise PermanentError("server error")

    with pytest.raises(PermanentError):
        llm_retry.call_with_llm_retry(operation)
    assert calls == 1


def test_llm_retry_does_not_retry_schema_bad_request(monkeypatch):
    calls = 0

    monkeypatch.setenv("INKU_LLM_RETRY_ATTEMPTS", "3")
    monkeypatch.setattr(llm_retry.time, "sleep", lambda delay: None)

    def operation() -> str:
        nonlocal calls
        calls += 1
        raise PermanentError("Failed to compile json grammar: Cannot find field $defs")

    with pytest.raises(PermanentError):
        llm_retry.call_with_llm_retry(operation)
    assert calls == 1
