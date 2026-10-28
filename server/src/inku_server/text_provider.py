"""One synchronous text send sharing the pipeline's provider admission state."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from . import provider_wire
from .provider_rate_limits import ProviderRateBudget, estimate_input_tokens, retry_after_seconds


async def _reserve(budget, provider, kind, limits, tokens, remaining):
    async with asyncio.timeout(remaining):
        return await budget.reserve(provider, kind, limits, tokens)


def send_text(connection: dict[str, Any], model_id: str, *, system: str, text: str, images: list[str],
              temperature: float, max_tokens: int, timeout: float,
              transport: httpx.BaseTransport | None = None) -> tuple[dict, httpx.Response, dict | None]:
    """Send once; DB accounting and countTokens use the same policy as pipeline sends."""
    built = provider_wire.text_request_with_count(connection, model_id, system=system, text=text, images=images,
                                                  temperature=temperature, max_tokens=max_tokens)
    body = built["body"].encode("utf-8")
    headers = provider_wire.headers(built, str(connection.get("api_key") or ""))
    limits = connection.get("rate_limits")
    budget = None
    if limits is not None:
        from . import db
        budget = ProviderRateBudget(db.engine)
    provider = str(connection["id"])
    kind = connection["kind"]
    deadline = time.monotonic() + timeout
    reservation = None
    input_used = None
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=False) as client:
            if budget is not None:
                input_tokens = estimate_input_tokens(kind, limits["tpm"], len(body))
                if input_tokens is None:
                    count_raw = bytearray()
                    with client.stream("POST", built["count_tokens"]["url"], headers=headers,
                                       content=built["count_tokens"]["body"].encode("utf-8")) as counted:
                        for chunk in counted.iter_bytes():
                            if len(count_raw) + len(chunk) > 16384:
                                raise ValueError("token count response limit exceeded")
                            count_raw.extend(chunk)
                        if counted.status_code == 429:
                            budget.cool_down(provider, retry_after_seconds(counted.headers, bytes(count_raw), now=budget.clock()))
                        counted.raise_for_status()
                    input_tokens = estimate_input_tokens(kind, limits["tpm"], len(body), json.loads(count_raw))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("provider admission timed out")
                reservation = asyncio.run(_reserve(budget, provider, kind, limits, input_tokens, remaining))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("provider request timed out")
            response = client.post(built["url"], headers=headers, content=body, timeout=remaining)
            if budget is not None and response.status_code == 429:
                budget.cool_down(provider, retry_after_seconds(response.headers, response.content[:16384], now=budget.clock()))
            read = None
            if response.is_success:
                read = provider_wire.read_text_with_usage(built["format"], response.status_code, response.content)
                input_used = read.get("input_tokens")
            return built, response, read
    finally:
        if budget is not None and reservation is not None:
            budget.settle(provider, reservation, input_used if input_used is not None else (None if limits["tpm"] else 0))
