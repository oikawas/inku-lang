"""The batch's sketch/DDL/catalog requests share its saved provider quota."""

import json
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import httpx
import pytest
from sqlalchemy import create_engine, select

from inku_server.model_settings import connection_for, public_model_settings, update_model_settings
from inku_server.persistence.schema import AppSettingRow
from inku_server.pipeline_provider import ProviderOptions, SingleAttemptProvider
import inku_render
from inku_server.provider_rate_limits import ProviderRateBudget, RateLimitUnavailable, RateAccountingUnavailable, _replace_state, estimate_input_tokens, retry_after_seconds


def test_core_admission_matches_shared_cases_and_preserves_json():
    cases = json.loads((Path(__file__).parent / "data/provider-admission-cases.json").read_text())["cases"]
    for case in cases:
        actual = json.loads(inku_render.pipeline_provider_admission(json.dumps(case["request"]).encode()))
        assert actual == case["expected"], case["name"]
        if "state" in actual:
            old = case["request"]["state"]
            _replace_state(old, actual)
            assert json.dumps(old, separators=(",", ":")) == json.dumps(case["expected"]["state"], separators=(",", ":")), case["name"]


def test_overflow_refuses_corrupt_state(tmp_path):
    state = {"events": [{"id": "a", "at": 1000.0, "tokens": 2**64 - 1}], "day": "1970-01-01", "daily": 0, "not_before": 0}
    request = {"action": "admit", "state": state, "now": 1001.0, "kind": "openai", "limits": {"rpm": 0, "tpm": 0, "rpd": 0}, "id": "b", "input_tokens": 1}
    assert json.loads(inku_render.pipeline_provider_admission(json.dumps(request).encode())) == {"error": "corrupt_state"}
    engine = create_engine(f"sqlite:///{tmp_path / 'corrupt.db'}")
    AppSettingRow.__table__.create(engine)
    raw = json.dumps(state, separators=(",", ":"))
    with engine.begin() as connection:
        connection.execute(AppSettingRow.__table__.insert().values(key="provider_rate_usage:p", value=raw, at=0))
    with pytest.raises(RateAccountingUnavailable):
        asyncio.run(ProviderRateBudget(engine, clock=lambda: 1001.0).reserve("p", "openai", request["limits"], 1))
    with engine.connect() as connection:
        assert connection.execute(select(AppSettingRow.value)).scalar_one() == raw


def test_large_integer_count_is_estimated_exactly_and_rejected_by_budget():
    count = 2**64
    estimate = estimate_input_tokens("gemini", 16000, 100, {"totalTokens": count})
    assert estimate == (count * 11 + 9) // 10
    with pytest.raises(RateLimitUnavailable, match="request exceeds the configured input-token budget"):
        asyncio.run(ProviderRateBudget(None).reserve("fixture", "gemini", {"rpm": 0, "tpm": 16000, "rpd": 0}, estimate))


@pytest.mark.parametrize("payload", [{"totalTokens": -1}, {"totalTokens": True}, {"totalTokens": 1.0}, {}, [], None])
def test_invalid_count_refuses_before_generation(payload, monkeypatch):
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", lambda *args, **kwargs: ("gemini", "m"))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "gemini", "kind": "gemini", "base_url": "https://provider.invalid",
        "api_key": "fixture-only", "requires_api_key": True,
        "rate_limits": {"rpm": 30, "tpm": 16000, "rpd": 10},
    })
    calls = []
    async def request(value):
        calls.append(value.url.path)
        return httpx.Response(200, content=json.dumps(payload).encode())
    class Budget:
        async def reserve(self, *args):
            pytest.fail("an invalid count must not reserve or send")
    provider = SingleAttemptProvider(ProviderOptions({}, "gemini:m", "gemini:m", 2048, 8192),
                                     transport=httpx.MockTransport(request), rate_budget=Budget())
    action = {"tag": "generate_normalized_ddl", "identity": {"action_id": "a", "attempt": 1, "request_digest": "b"},
              "timeout_ms": "120000", "payload": {"prompt": {"system": "s", "message": "m",
              "action_name": "generate_normalized_ddl", "response_schema": {"type": "object", "properties": {}}}}}
    assert provider(action)["failure"] == ("rate_limited" if isinstance(payload, dict) else "malformed_payload")
    assert len(calls) == 1 and calls[0].endswith(":countTokens")


def test_disabled_tpm_skips_gemini_count_and_reserves_zero(monkeypatch):
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", lambda *args, **kwargs: ("gemini", "m"))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "gemini", "kind": "gemini", "base_url": "https://provider.invalid",
        "api_key": "fixture-only", "requires_api_key": True,
        "rate_limits": {"rpm": 0, "tpm": 0, "rpd": 0},
    })
    calls, reservations = [], []
    async def request(value):
        calls.append(value.url.path)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"functionCall": {
            "name": "submit_pipeline_response", "args": {"normalized_ddl": "fixture"},
        }}]}}]})
    class Budget:
        async def reserve(self, provider, kind, limits, tokens):
            reservations.append(tokens)
            return "fixture"
        def settle(self, *args):
            pass
    provider = SingleAttemptProvider(ProviderOptions({}, "gemini:m", "gemini:m", 2048, 8192),
                                     transport=httpx.MockTransport(request), rate_budget=Budget())
    action = {"tag": "generate_normalized_ddl", "identity": {"action_id": "a", "attempt": 1, "request_digest": "b"},
              "timeout_ms": "120000", "payload": {"prompt": {"system": "s", "message": "m",
              "action_name": "generate_normalized_ddl", "response_schema": {"type": "object", "properties": {}}}}}
    assert provider(action)["tag"] != "provider_failed"
    assert reservations == [0]
    assert len(calls) == 1 and calls[0].endswith(":generateContent")


def test_retry_info_accepts_json_byte_encodings():
    body = '{"error":{"details":[{"@type":"type.googleapis.com/google.rpc.RetryInfo","retryDelay":"91s"}]}}'
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-16-be", "utf-32", "utf-32-be"):
        assert retry_after_seconds({}, body.encode(encoding), now=0) == 91


def test_db_json_matches_original_sequence(tmp_path, monkeypatch):
    fixture = json.loads((Path(__file__).parent / "data/provider-admission-sequence.json").read_text())
    engine = create_engine(f"sqlite:///{tmp_path / 'sequence.db'}")
    AppSettingRow.__table__.create(engine)
    now = [0.0]

    class Paused(Exception):
        pass

    async def wait(seconds):
        raise Paused(seconds)

    budget = ProviderRateBudget(engine, clock=lambda: now[0], sleep=wait)
    for step in fixture["steps"]:
        now[0] = step["now"]
        status = "ok"
        try:
            if step["action"] == "reserve":
                monkeypatch.setattr("inku_server.provider_rate_limits.uuid.uuid4", lambda: type("Id", (), {"hex": step["id"]})())
                asyncio.run(budget.reserve("fixture", "gemini", fixture["limits"], step["value"]))
            elif step["action"] == "settle":
                budget.settle("fixture", "id0", step["value"])
            elif step["action"] == "pause":
                budget.cool_down("fixture", step["value"])
        except Paused as error:
            status = "wait:" + str(error.args[0])
        assert status == step["status"]
        with engine.connect() as connection:
            assert connection.execute(select(AppSettingRow.value)).scalar_one() == step["json"]


def test_batch_admission_counts_all_stages_waits_on_tpm_and_429_and_keeps_daily_usage(tmp_path, monkeypatch):
    settings = update_model_settings({}, {"providers": {"gemini": {
        "api_key": "fixture-only", "rate_limits": {"rpm": 30, "tpm": 16_000, "rpd": 5},
    }}})
    limits = public_model_settings(settings)["providers"]["gemini"]["rate_limits"]
    assert limits == {"rpm": 30, "tpm": 16_000, "rpd": 5}
    assert connection_for("gemini", settings)["rate_limits"] == limits
    # Editing a name or a single quota must not erase the other quota values.
    settings = update_model_settings(settings, {"providers": {"gemini": {"label": "Gemini", "rate_limits": {"rpm": 30}}}})
    assert connection_for("gemini", settings)["rate_limits"] == limits
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", lambda *args, **kwargs: ("gemini", "gemma-4-31b-it"))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "gemini", "kind": "gemini", "base_url": "https://provider.invalid",
        "api_key": "fixture-only", "requires_api_key": True, "rate_limits": limits,
    })
    database_url = f"sqlite:///{tmp_path / 'quota.db'}"
    engine = create_engine(database_url)
    AppSettingRow.__table__.create(engine)
    start = datetime(2026, 10, 2, 7, 40, tzinfo=timezone.utc).timestamp()
    now = [start]
    waits, sends, bodies = [], [], []
    omit_usage = [False]

    async def wait(seconds):
        waits.append(seconds)
        now[0] += seconds

    async def request(value):
        body = json.loads(value.content)
        if value.url.path.endswith(":countTokens"):
            full = body["generateContentRequest"]
            assert full["model"] == "models/gemma-4-31b-it"
            assert full["systemInstruction"]["parts"][0]["text"] == "exact system"
            assert full["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"]["type"] == "object"
            return httpx.Response(200, json={"totalTokens": 4500})
        sends.append(now[0])
        bodies.append(body)
        if len(sends) == 4:
            return httpx.Response(429, headers={"Retry-After": "65"}, json={"error": {
                "status": "RESOURCE_EXHAUSTED", "details": [{
                    "@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "90s",
                }],
            }})
        return httpx.Response(200, json={
            **({} if omit_usage[0] else {"usageMetadata": {"promptTokenCount": 4500}}),
            "candidates": [{"content": {"parts": [{"functionCall": {
                "name": "submit_pipeline_response", "args": {"normalized_ddl": "same bytes"},
            }}]}}],
        })

    def provider(current_engine):
        return SingleAttemptProvider(
            ProviderOptions(settings, "gemini:m", "gemini:m", 2048, 8192),
            transport=httpx.MockTransport(request),
            rate_budget=ProviderRateBudget(current_engine, clock=lambda: now[0], sleep=wait),
        )

    def action(tag="generate_normalized_ddl", attempt=1):
        return {"tag": tag, "identity": {"action_id": "a", "attempt": attempt, "request_digest": "b"},
                "timeout_ms": "120000", "payload": {"prompt": {
                    "system": "exact system", "message": "若葉の下を、黄色い蝶がふたつ渡っていった。",
                    "action_name": tag, "response_schema": {"type": "object", "properties": {}},
                }}}

    for tag in ("generate_sketch", "generate_normalized_ddl", "select_description_catalog"):
        assert provider(engine)(action(tag))["tag"] != "provider_failed"
    assert sends == [start, start, start]
    # The fourth request exceeds the 14,400-input-token admission budget.
    assert provider(engine)(action())["failure"] == "rate_limited"
    assert sends[-1] == start + 62 and waits == [62]
    # A fresh provider/DB connection must inherit the refusal's 90-second wait.
    engine.dispose()
    engine = create_engine(database_url)
    assert provider(engine)(action(attempt=2))["tag"] == "normalized_ddl_generated"
    assert sends[-1] == start + 152 and waits == [62, 90]
    assert len(sends) == 5  # No transport-owned retry was inserted.
    assert all(body["contents"][0]["parts"][0]["text"] == action()["payload"]["prompt"]["message"] for body in bodies)
    # The daily cap includes the known 429 and survives reconnection.
    assert provider(engine)(action())["failure"] == "rate_limited"
    assert len(sends) == 5
    now[0] = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc).timestamp()
    assert provider(engine)(action())["failure"] == "rate_limited"  # Still the same Pacific day.
    now[0] = datetime(2026, 10, 3, 7, 0, tzinfo=timezone.utc).timestamp()
    assert provider(engine)(action())["tag"] == "normalized_ddl_generated"
    assert len(sends) == 6
    with engine.connect() as connection:
        state = json.loads(connection.execute(select(AppSettingRow.value)).scalar_one())
    assert state["daily"] == 1 and state["day"] == "2026-10-03"
    assert "fixture-only" not in json.dumps(state)
    # Turning all three values off must not pace a local/custom endpoint even
    # when it omits usage; missing usage matters only to an enabled TPM cap.
    limits.update(rpm=0, tpm=0, rpd=0)
    omit_usage[0] = True
    assert provider(engine)(action())["tag"] == "normalized_ddl_generated"
    assert provider(engine)(action())["tag"] == "normalized_ddl_generated"
    assert waits == [62, 90] and sends[-1] == sends[-2]
    engine.dispose()


def test_independent_workers_cannot_both_take_the_last_daily_request(tmp_path):
    url = f"sqlite:///{tmp_path / 'concurrent-quota.db'}"
    engines = [create_engine(url), create_engine(url)]
    AppSettingRow.__table__.create(engines[0])
    gate = Barrier(2)

    def reserve(engine):
        gate.wait(timeout=5)
        try:
            return asyncio.run(ProviderRateBudget(engine).reserve("same-provider", "gemini", {
                "rpm": 0, "tpm": 0, "rpd": 1,
            }, 0))
        except RateLimitUnavailable:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, engines))
    assert sum(value is not None for value in results) == 1
    for engine in engines:
        engine.dispose()
