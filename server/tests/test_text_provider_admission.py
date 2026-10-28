import asyncio
import json

import httpx
import pytest
from sqlalchemy import create_engine, select

from inku_server import db, text_provider
from inku_server.api_core.routers import public
from inku_server.persistence.schema import AppSettingRow
from inku_server.provider_rate_limits import ProviderRateBudget, RateLimitUnavailable
from inku_server.vision_client import vision_text


@pytest.fixture
def accounting(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'usage.db'}")
    AppSettingRow.__table__.create(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(text_provider, "ProviderRateBudget", lambda engine: ProviderRateBudget(engine, clock=lambda: 1000.0))
    def read():
        with engine.connect() as c:
            return json.loads(c.execute(select(AppSettingRow.value)).scalar_one())
    return read


def connection(tpm=16000, rpd=10):
    return {"id": "gemini", "kind": "gemini", "base_url": "https://provider.invalid", "api_key": "test",
            "rate_limits": {"rpm": 0, "tpm": tpm, "rpd": rpd}}


def ask(conn, transport):
    return vision_text(conn, "gemini-test", system="system", text="hello", images=[],
                       temperature=0.0, max_tokens=100, transport=transport)


def test_vision_counts_and_settles_and_shares_daily_limit(accounting):
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": 100})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "answer"}]}}],
                                         "usageMetadata": {"promptTokenCount": 11}})
    transport = httpx.MockTransport(respond)
    assert ask(connection(rpd=1), transport) == "answer"
    state = accounting()
    assert state["daily"] == 1 and state["events"][0]["tokens"] == 11
    with pytest.raises(RateLimitUnavailable):
        asyncio.run(ProviderRateBudget(db.engine, clock=lambda: 1000.0).reserve(
            "gemini", "gemini", connection(rpd=1)["rate_limits"], 10))
    with pytest.raises(RateLimitUnavailable):
        ask(connection(rpd=1), transport)
    assert accounting() == state
    assert sum(path.endswith(":countTokens") for path in calls) == 2
    assert sum(path.endswith(":generateContent") for path in calls) == 1


@pytest.mark.parametrize("on_count", [True, False])
def test_429_sets_shared_cooldown(accounting, on_count):
    def respond(request):
        if on_count or request.url.path.endswith(":generateContent"):
            return httpx.Response(429, headers={"retry-after": "90"}, json={})
        return httpx.Response(200, json={"totalTokens": 10})
    with pytest.raises(httpx.HTTPStatusError):
        ask(connection(), httpx.MockTransport(respond))
    assert accounting()["not_before"] == 1090.0


def test_missing_usage_waits_but_disabled_tpm_does_not_count(accounting):
    calls = []
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "answer"}]}}]})
    assert ask(connection(tpm=0), httpx.MockTransport(respond)) == "answer"
    assert len(calls) == 1 and calls[0].endswith(":generateContent")
    assert accounting()["events"][0]["tokens"] == 0
    assert accounting()["not_before"] == 0


def test_missing_usage_preserves_estimate_and_waits(accounting):
    def respond(request):
        if request.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": 100})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "answer"}]}}]})
    assert ask(connection(), httpx.MockTransport(respond)) == "answer"
    assert accounting()["events"][0]["tokens"] == 110
    assert accounting()["not_before"] == 1062


@pytest.mark.parametrize("payload, error", [([], TypeError), (None, TypeError),
                                           ({"totalTokens": -1}, RateLimitUnavailable),
                                           ({"totalTokens": True}, RateLimitUnavailable)])
def test_invalid_count_does_not_generate(accounting, payload, error):
    calls = []
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=payload) if payload is not None else httpx.Response(200, content=b"null")
    with pytest.raises(error):
        ask(connection(), httpx.MockTransport(respond))
    assert len(calls) == 1 and calls[0].endswith(":countTokens")


def test_demo_uses_same_admission(accounting, monkeypatch):
    monkeypatch.setattr(public._db, "get_model_settings", lambda: {})
    monkeypatch.setattr(public, "provider_for_model", lambda *a, **kw: ("gemini", "m"))
    monkeypatch.setattr(public, "connection_for", lambda *a: connection())
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": 20})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "demo"}]}}],
                                         "usageMetadata": {"promptTokenCount": 7}})
    assert public._generate_demo_instruction("pond", model=None, lang="en", transport=httpx.MockTransport(respond)) == "demo"
    assert len(calls) == 2 and accounting()["events"][0]["tokens"] == 7
