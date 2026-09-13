"""Transport boundary only: exact prompt, no host retry, one whole-attempt deadline."""

import asyncio
import json

import httpx

from inku_server.pipeline_provider import ProviderOptions, SingleAttemptProvider


def test_single_attempt_preserves_core_prompt_and_reports_rate_limit_and_deadline(monkeypatch):
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", lambda *args, **kwargs: ("fixture", "fixture-model"))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "fixture", "kind": "openai_compatible", "base_url": "https://provider.invalid/v1",
        "api_key": "test-only", "requires_api_key": True,
    })
    seen = []

    async def request(value):
        seen.append(value)
        if len(seen) == 2:
            return httpx.Response(429, json={"error": "fixture rate limit"})
        if len(seen) == 3:
            await asyncio.sleep(0.2)
        return httpx.Response(200, json={"choices": [{"message": {"content": ' {"normalized_ddl":"keep these bytes"} '}}]})

    provider = SingleAttemptProvider(
        ProviderOptions({}, "fixture-model", "fixture-model", 256, 8192),
        transport=httpx.MockTransport(request),
    )
    action = {
        "tag": "generate_normalized_ddl", "identity": {"action_id": "a", "attempt": 1, "request_digest": "b"},
        "timeout_ms": "1000", "payload": {"prompt": {"system": "exact bounded system", "message": "exact visible input"}},
    }
    result = provider(action)
    assert result["tag"] == "normalized_ddl_generated"
    assert result["identity"] == action["identity"]
    assert result["response"] == ' {"normalized_ddl":"keep these bytes"} '
    assert json.loads(seen[0].content)["messages"] == [
        {"role": "system", "content": "exact bounded system"}, {"role": "user", "content": "exact visible input"},
    ]
    assert provider(action)["failure"] == "rate_limited"
    assert len(seen) == 2  # The host has not retried the rejected attempt.
    assert provider({**action, "timeout_ms": "20"})["failure"] == "transport_timeout"
    assert len(seen) == 3
