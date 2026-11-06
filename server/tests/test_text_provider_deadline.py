import asyncio

import httpx
import pytest

from inku_server import text_provider


CONNECTION = {"id": "test", "kind": "openai_compatible", "base_url": "https://example.invalid/v1", "api_key": "test"}


def send(transport, timeout=1):
    return text_provider.send_text(CONNECTION, "model", system="system", text="hello", images=[],
                                   temperature=0, max_tokens=10, timeout=timeout, transport=transport)


def test_total_deadline_stops_a_slow_response():
    async def handler(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, json={})
    with pytest.raises(TimeoutError):
        send(httpx.MockTransport(handler), timeout=0.01)


def test_response_size_limit_has_a_reason(monkeypatch):
    monkeypatch.setattr(text_provider, "MAX_RESPONSE_BYTES", 16)
    with pytest.raises(text_provider.ProviderResponseTooLarge, match="provider_response_too_large"):
        send(httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 17)))


def test_default_client_is_reused():
    async def clients():
        return text_provider._runtime.client(), text_provider._runtime.client()
    first, second = text_provider._runtime.run(clients)
    assert first is second
