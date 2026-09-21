"""Focused durable developer provider-transcript boundary checks."""

import json

import httpx
from sqlalchemy import create_engine

from inku_server.persistence.schema import Base
from inku_server.pipeline_provider import ProviderOptions, SingleAttemptProvider
from inku_server.provider_observation import ProviderObservationError, ProviderObservationStore


def _action() -> dict:
    return {
        "tag": "generate_normalized_ddl",
        "timeout_ms": "1000",
        "identity": {"action_id": "action-1", "attempt": 1, "request_digest": "request-1"},
    }


def test_provider_observation_keeps_error_raw_private_and_marks_completed_failure(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'provider-observation.db'}")
    Base.metadata.create_all(engine)
    store = ProviderObservationStore(engine, limit=1024)
    action = _action()

    assert store.request("owner", "execution", action, "stage1", "gemini", "google/gemma-4-31b-it", b'{"contents":[]}') is False
    store.response("owner", "execution", action, status=429, raw=b'{"error":"rate limited"}')
    store.outcome("owner", "execution", action, failure="rate_limited", elapsed_ms=7, capture_complete=True)

    saved = store.read_execution("owner", "execution")
    assert saved == [{
        "execution_id": "execution", "action_id": "action-1", "request_digest": "request-1", "action_tag": "generate_normalized_ddl",
        "stage": "stage1", "provider_id": "gemini", "model": "google/gemma-4-31b-it",
        "attempt": 1, "timeout_ms": 1000, "request_body": '{"contents":[]}',
        "request_truncated": False, "response_body": '{"error":"rate limited"}',
        "response_truncated": False, "http_status": 429, "usage_json": None,
        "outcome": "completed", "capture_complete": True, "failure": "rate_limited",
        "elapsed_ms": 7, "created_at": saved[0]["created_at"], "updated_at": saved[0]["updated_at"],
    }]
    assert store.read_execution("other-owner", "execution") == []
    engine.dispose()


def test_provider_observation_marks_a_cut_body_incomplete(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'provider-observation-cut.db'}")
    Base.metadata.create_all(engine)
    store = ProviderObservationStore(engine, limit=4)
    action = _action()

    assert store.request("owner", "execution", action, "stage1", "gemini", "model", b'{}') is False
    store.response("owner", "execution", action, status=500, raw=b'{"error":"cut"}', truncated=True)
    store.outcome("owner", "execution", action, failure="transport_unavailable", elapsed_ms=3, capture_complete=False)

    saved = store.read_execution("owner", "execution")[0]
    assert saved["http_status"] == 500
    assert saved["response_body"] == '{"er'
    assert saved["response_truncated"] is True
    assert saved["capture_complete"] is False
    engine.dispose()


def test_transport_captures_429_raw_without_secrets_and_stops_when_prewrite_fails(tmp_path, monkeypatch) -> None:
    import inku_server.pipeline_provider as provider_module

    engine = create_engine(f"sqlite:///{tmp_path / 'provider-transport.db'}")
    Base.metadata.create_all(engine)
    store = ProviderObservationStore(engine, limit=1024)
    action = {**_action(), "payload": {"prompt": {
        "action_name": "generate_normalized_ddl", "system": "system", "message": "message",
        "response_schema": {"type": "object", "properties": {}},
    }}}
    sent: list[bytes] = []
    transport = httpx.MockTransport(lambda request: (
        sent.append(request.content) or httpx.Response(429, content=b'{"error":"rate limited"}')
    ))
    monkeypatch.setattr(provider_module, "provider_for_model", lambda *_args, **_kwargs: ("fixture", "model"))
    monkeypatch.setattr(provider_module, "connection_for", lambda *_args, **_kwargs: {
        "id": "fixture", "kind": "gemini", "base_url": "https://key-in-url.example/?token=secret",
        "api_key": "secret", "requires_api_key": False,
    })
    options = ProviderOptions(settings={}, stage1_model="fixture:model", stage2_model="fixture:model", max_tokens=8, max_response_bytes=1024)
    result = SingleAttemptProvider(options, transport=transport, observation=(store, "owner", "execution"))(action)

    assert result["failure"] == "rate_limited"
    assert json.loads(sent[0])["contents"][0]["parts"][0]["text"] == "message"
    saved = store.read_execution("owner", "execution")[0]
    assert saved["http_status"] == 429
    assert saved["response_body"] == '{"error":"rate limited"}'
    assert saved["capture_complete"] is True
    assert "secret" not in json.dumps(saved)

    class FailingStore:
        def request(self, *_args, **_kwargs):
            raise ProviderObservationError("request_save_failed")

        def outcome(self, *_args, **_kwargs):
            return None

    sent.clear()
    failed = SingleAttemptProvider(options, transport=transport, observation=(FailingStore(), "owner", "other"))
    assert failed(action)["failure"] == "provider_rejected"
    assert sent == []
    engine.dispose()
