"""Synchronous callers share one asynchronous provider transport and deadline."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import httpx

from . import provider_wire
from .provider_rate_limits import ProviderRateBudget, estimate_input_tokens, retry_after_seconds

MAX_RESPONSE_BYTES = 32 * 1024 * 1024


class ProviderResponseTooLarge(ValueError):
    """The provider sent a body larger than the supported limit."""

    code = "provider_response_too_large"

    def __init__(self):
        super().__init__(self.code)


class _Runtime:
    def __init__(self):
        self._lock = threading.Lock()
        self._loop = None
        self._client = None

    def run(self, make_coroutine):
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                threading.Thread(target=self._loop.run_forever, name="provider-http", daemon=True).start()
            loop = self._loop
        return asyncio.run_coroutine_threadsafe(make_coroutine(), loop).result()

    def client(self):
        # Called only on the runtime's event loop.
        if self._client is None:
            self._client = httpx.AsyncClient(follow_redirects=False)
        return self._client


_runtime = _Runtime()


async def _post(client, url, *, headers, body, timeout, limit):
    async with client.stream("POST", url, headers=headers, content=body, timeout=timeout) as response:
        raw = bytearray()
        async for chunk in response.aiter_bytes():
            if len(raw) + len(chunk) > limit:
                if limit == MAX_RESPONSE_BYTES:
                    raise ProviderResponseTooLarge()
                raise ValueError("token count response limit exceeded")
            raw.extend(chunk)
        return httpx.Response(response.status_code, headers=response.headers, content=bytes(raw), request=response.request)


async def _send(built, connection, body, headers, timeout, client):
    limits = connection.get("rate_limits")
    budget = None
    if limits is not None:
        from . import db
        budget = ProviderRateBudget(db.engine)
    provider = str(connection["id"])
    kind = connection["kind"]
    reservation = None
    input_used = None
    try:
        async with asyncio.timeout(timeout):
            if budget is not None:
                input_tokens = estimate_input_tokens(kind, limits["tpm"], len(body))
                if input_tokens is None:
                    counted = await _post(client, built["count_tokens"]["url"], headers=headers,
                                          body=built["count_tokens"]["body"].encode("utf-8"), timeout=timeout, limit=16384)
                    if counted.status_code == 429:
                        budget.cool_down(provider, retry_after_seconds(counted.headers, counted.content, now=budget.clock()))
                    counted.raise_for_status()
                    input_tokens = estimate_input_tokens(kind, limits["tpm"], len(body), json.loads(counted.content))
                reservation = await budget.reserve(provider, kind, limits, input_tokens)
            response = await _post(client, built["url"], headers=headers, body=body, timeout=timeout, limit=MAX_RESPONSE_BYTES)
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


def send_text(connection: dict[str, Any], model_id: str, *, system: str, text: str, images: list[str],
              temperature: float, max_tokens: int, timeout: float,
              transport: httpx.BaseTransport | None = None) -> tuple[dict, httpx.Response, dict | None]:
    """Send once; admission, count and response share one overall deadline."""
    built = provider_wire.text_request_with_count(connection, model_id, system=system, text=text, images=images,
                                                  temperature=temperature, max_tokens=max_tokens)
    body = built["body"].encode("utf-8")
    headers = provider_wire.headers(built, str(connection.get("api_key") or ""))

    async def run():
        if transport is None:
            return await _send(built, connection, body, headers, timeout, _runtime.client())
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            return await _send(built, connection, body, headers, timeout, client)

    return _runtime.run(run)
