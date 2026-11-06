import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

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


def test_slow_budget_database_does_not_block_another_send(monkeypatch):
    entered = Event()
    release = Event()

    class SlowBudget(text_provider.ProviderRateBudget):
        def _change(self, provider, modify):
            entered.set()
            if not release.wait(10):
                raise TimeoutError("test budget was not released")
            return 0

    monkeypatch.setattr(text_provider, "ProviderRateBudget", SlowBudget)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": "answer"}}],
    }))
    slow_connection = {**CONNECTION, "rate_limits": {"rpm": 0, "tpm": 0, "rpd": 0}}

    def ask(connection):
        return text_provider.send_text(connection, "model", system="system", text="hello", images=[],
                                       temperature=0, max_tokens=10, timeout=10, transport=transport)

    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(ask, slow_connection)
        try:
            assert entered.wait(3), "the slow database call did not start"
            fast = pool.submit(ask, CONNECTION)
            assert fast.result(timeout=3)[1].status_code == 200
            assert not slow.done(), "the first request must still be waiting on the database"
        finally:
            release.set()
        assert slow.result(timeout=3)[1].status_code == 200


def test_cancelling_a_pending_admission_reconciles_a_late_commit():
    entered = Event()
    release = Event()
    settled = []

    class SlowBudget(text_provider.ProviderRateBudget):
        def _change(self, provider, modify):
            entered.set()
            assert release.wait(5)
            return 0

        def settle(self, provider, token, input_tokens):
            settled.append((provider, token, input_tokens))

    async def check():
        budget = SlowBudget(None)
        task = asyncio.create_task(budget.reserve("slow", "openai_compatible", {"rpm": 0, "tpm": 0, "rpd": 0}, 0))
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(settled) == 1
        assert settled[0][0] == "slow" and settled[0][2] == 0

    asyncio.run(check())
