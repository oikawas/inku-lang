"""The shared default for provider request deadlines."""

import os

DEFAULT_REQUEST_TIMEOUT_SECONDS = 120


def request_timeout_seconds() -> float:
    return float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_REQUEST_TIMEOUT_SECONDS)))
