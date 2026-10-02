"""Concrete SIWC boundary failures, with isolated storage and fixed HTTP mocks."""

import asyncio
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from inku_server import chatgpt_auth as auth
from inku_server import chatgpt_runtime as runtime
from inku_server import chatgpt_transfer as transfer
from inku_server.chatgpt_store import ChatGPTError, CredentialStore, canonical


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("INKU_CHATGPT_AUTH_DIR", str(tmp_path / "auth"))
    monkeypatch.setenv("INKU_DB_URL", "sqlite:///" + str(tmp_path / "fixture.db"))
    monkeypatch.setenv("INKU_CHATGPT_PLAN_ENABLED", "1")
    monkeypatch.setenv("INKU_DEVELOPER_MODE", "1")
    from inku_server import db
    monkeypatch.setattr(db, "get_user", lambda owner: {"id": owner, "username": "owner"} if owner == "owner" else None)
    monkeypatch.setattr(db, "single_user_mode_enabled", lambda: False)
    runtime.configure_startup("127.0.0.1", 8100, self_hosted=False)
    return CredentialStore()


def profile(**changes):
    return {"id": str(uuid.uuid4()), "issuer": auth.ISSUER, "sub": "subject", "client_id": "oaiapp_fixture",
            "email": "owner@example.test", "label": "owner", "state": "connected", "generation": 1,
            "refresh_owner": "runtime", "scopes": ["chatgpt.tokens.use.direct"], "expires_at": time.time() + 3600,
            "access_token": "fixture-access", "refresh_token": "fixture-refresh", "id_token": "fixture-id", "oidc_nonce": "nonce", "earliest_refresh_at": 0, **changes}


def seed(store, value):
    with store.lock("owner"):
        store.save_profile("owner", value)


def test_sealed_handoff_rejects_changed_owner_and_is_one_time(isolated, tmp_path, monkeypatch):
    remote_host = isolated.host_id()
    request = transfer.recipient("owner")
    monkeypatch.setenv("INKU_CHATGPT_AUTH_DIR", str(tmp_path / "mac"))
    mac = CredentialStore()
    mac_host = mac.host_id()
    value = profile()
    seed(mac, value)
    envelope = transfer.export_profile(request, value["id"])
    assert mac.profile("owner")["state"] == "exported"
    assert "refresh_token" not in mac.profile("owner")
    assert b"fixture-refresh" not in canonical(envelope)
    assert b"fixture-access" not in mac._path("owner").read_bytes()
    assert mac._path("owner").stat().st_mode & 0o077 == 0
    monkeypatch.setenv("INKU_CHATGPT_AUTH_DIR", str(isolated.root))
    async def verified(*_args):
        return {"sub": "subject"}
    monkeypatch.setattr(transfer, "validate_identity", verified)
    with pytest.raises(ChatGPTError):
        asyncio.run(transfer.import_profile({**envelope, "owner_id": "other"}))
    result = asyncio.run(transfer.import_profile(envelope))
    assert result["host_id"] == remote_host != mac_host
    assert isolated.profile("owner")["refresh_owner"] == "runtime"
    assert isolated.profile("owner")["refresh_token"] == "fixture-refresh"
    assert asyncio.run(transfer.import_profile(envelope))["replayed"]
    with pytest.raises(ChatGPTError):
        asyncio.run(transfer.import_profile({**envelope, "ciphertext": envelope["ciphertext"] + "A"}))
    path = isolated._path("owner")
    path.write_text('{"refresh_token":"plaintext"}')
    with pytest.raises(ChatGPTError, match="credentials_unavailable"):
        isolated.profile("owner")
    path.unlink()
    path.symlink_to(mac._path("owner"))
    with pytest.raises(ChatGPTError, match="storage_unsafe"):
        isolated.profile("owner")


def test_callback_wrong_state_does_not_consume_and_oidc_nonce_is_checked(isolated, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), "kid": "fixture", "use": "sig"}
    issued_calls = []
    nonce = {"value": ""}
    def handle(request):
        assert request.url.host == "auth.openai.com"
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"issuer": auth.ISSUER, "jwks_uri": auth.ISSUER + "/jwks", "id_token_signing_alg_values_supported": ["RS256"]})
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [jwk]})
        issued_calls.append(parse_qs(request.content.decode()))
        token = jwt.encode({"iss": auth.ISSUER, "aud": "oaiapp_fixture", "sub": "subject", "exp": time.time() + 300,
                            "nonce": nonce["value"], "email": "owner@example.test"}, key, algorithm="RS256", headers={"kid": "fixture"})
        return httpx.Response(200, json={"token_type": "Bearer", "expires_in": 3600, "scope": "openid chatgpt.tokens.use.direct",
                                        "access_token": "fixture-access", "refresh_token": "fixture-refresh", "id_token": token})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    coordinator = auth.AuthorizationAttempts()
    started = coordinator.begin("owner", None, False, lambda: runtime.check_owner("owner"))
    params = parse_qs(urlsplit(started["authorization_url"]).query)
    nonce["value"] = params["nonce"][0]
    callback = params["redirect_uri"][0]
    with httpx.Client() as client:
        assert client.get(callback, params={"state": "wrong", "code": "fixture-code", "client_id": "oaiapp_fixture"}).status_code == 400
        assert coordinator.public("owner", started["attempt_id"])["status"] == "pending"
        assert issued_calls == []
        assert client.get(callback, params={"state": params["state"][0], "code": "fixture-code", "client_id": "oaiapp_fixture"}).status_code == 200
    assert issued_calls[0]["client_id"] == ["oaiapp_fixture"]
    assert issued_calls[0]["redirect_uri"] == [callback]
    assert "id_token_hint" not in params
    assert isolated.profile("owner")["sub"] == "subject"
    async def bad_nonce():
        async with real_client(transport=httpx.MockTransport(handle)) as client:
            token = isolated.profile("owner")["id_token"]
            await auth.validate_identity(client, token, "oaiapp_fixture", "different", lambda: None, time.monotonic() + 5)
    with pytest.raises(ChatGPTError, match="identity_invalid"):
        asyncio.run(bad_nonce())


def test_refresh_serializes_across_threads_and_signout_invalidates_late_result(isolated, monkeypatch):
    value = profile(expires_at=0)
    seed(isolated, value)
    other = profile(sub="another-subject")
    seed(isolated, other)
    calls = []
    real_client = httpx.AsyncClient
    def handle(request):
        calls.append(request)
        body = parse_qs(request.content.decode())
        assert "scope" not in body and body["client_id"] == ["oaiapp_fixture"]
        time.sleep(0.05)
        return httpx.Response(200, json={"token_type": "Bearer", "expires_in": 3600, "access_token": "rotated", "refresh_token": "rotated-refresh"})
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    def refresh():
        return asyncio.run(auth.access_token("owner", value["id"], 1, time.monotonic() + 5))
    with ThreadPoolExecutor(2) as pool:
        results = [future.result() for future in [pool.submit(refresh), pool.submit(refresh)]]
    assert results == ["rotated", "rotated"] and len(calls) == 1
    assert isolated.profile("owner")["scopes"] == value["scopes"]
    assert isolated.read("owner")["active"] == other["id"]
    started = threading.Event()
    async def late(request):
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"issuer": auth.ISSUER, "jwks_uri": auth.ISSUER + "/jwks", "revocation_endpoint": auth.ISSUER + "/revoke"})
        if request.url.path == "/revoke":
            return httpx.Response(200)
        started.set()
        await asyncio.sleep(1)
        return httpx.Response(200, json={"token_type": "Bearer", "expires_in": 3600, "access_token": "late", "refresh_token": "late-refresh"})
    expired = isolated.profile("owner", value["id"])
    expired["expires_at"] = 0
    seed(isolated, expired)
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(late), **kwargs))
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(refresh)
        assert started.wait(2)
        result = asyncio.run(auth.sign_out("owner", value["id"]))
        assert result["revocation_confirmed"]
        with pytest.raises(ChatGPTError):
            future.result(timeout=2)
    assert isolated.profile("owner")["state"] == "signed_out"
    assert "access_token" not in isolated.profile("owner")


def stream_bytes(*, failed=False):
    arguments = json.dumps({"ddl": "赤い円を置く。"}, ensure_ascii=False)
    item = {"type": "function_call", "id": "fc_fixture", "call_id": "call_fixture", "name": "submit_pipeline_response", "namespace": "inku"}
    events = [{"type": "response.output_item.added", "item": {**item, "arguments": ""}},
              {"type": "response.function_call_arguments.delta", "item_id": item["id"], "delta": arguments},
              {"type": "response.function_call_arguments.done", "item_id": item["id"], "arguments": arguments}]
    events.append({"type": "response.failed", "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}}} if failed else
                  {"type": "response.completed", "response": {"status": "completed", "output": [{**item, "arguments": arguments}], "usage": {"input_tokens": 3}}})
    return b"".join(b"data: " + canonical(event) + b"\r\n\r\n" for event in events), arguments


def test_sse_split_utf8_requires_completed_and_rejects_late_quota():
    from inku_server.chatgpt_provider import SSEDecoder
    wire, arguments = stream_bytes()
    decoder = SSEDecoder(len(arguments.encode()))
    for byte in wire:
        decoder.feed(bytes([byte]))
    assert decoder.finish() == arguments
    failed, _ = stream_bytes(failed=True)
    with pytest.raises(ChatGPTError, match="subscription_sharing_usage_limit_exceeded"):
        SSEDecoder(1024).feed(failed)
    prefix = wire[:wire.rfind(b"data: ")]
    incomplete = SSEDecoder(1024)
    incomplete.feed(prefix)
    with pytest.raises(ChatGPTError, match="response_incomplete"):
        incomplete.finish()
    with pytest.raises(ChatGPTError, match="response_too_large"):
        SSEDecoder(4).feed(wire)


@pytest.mark.parametrize("developer,single,allowed", [(False, False, False), (True, False, True), (False, True, True), (True, True, True)])
def test_mode_or_and_fixed_owner_precede_any_http(isolated, monkeypatch, developer, single, allowed):
    from inku_server import db
    monkeypatch.setenv("INKU_DEVELOPER_MODE", "1" if developer else "0")
    monkeypatch.setattr(db, "single_user_mode_enabled", lambda: single)
    monkeypatch.setattr(db, "single_user_account", lambda: {"id": "owner"})
    assert runtime.availability()[0] is allowed
    if allowed:
        runtime.check_owner("owner")
    else:
        with pytest.raises(ChatGPTError, match="mode_not_allowed"):
            runtime.check_owner("owner")
    monkeypatch.setattr(db, "get_user", lambda owner: {"id": owner})
    if single:
        with pytest.raises(ChatGPTError, match="owner_not_allowed"):
            runtime.check_owner("other")


def test_reserved_provider_and_admin_cannot_bypass_operation(isolated, monkeypatch):
    from inku_server import db, model_settings
    from inku_server.api_core.common import _model_offered_to
    settings = model_settings.default_model_settings()
    assert model_settings.provider_for_model("chatgpt:model", stage="stage1", settings=settings) == ("chatgpt", "model")
    assert model_settings.qualify_model_ref("nvidia", "chatgpt:model", settings) == "chatgpt:model"
    monkeypatch.setattr(db, "has_permission_group", lambda *_args: True)
    assert not _model_offered_to({"id": "owner"}, "chatgpt:model", stage="stage1", purpose="llm", settings=settings)
    assert _model_offered_to({"id": "owner"}, "openai:gpt-4.1", stage="stage1", purpose="llm", settings=settings)
    assert "chatgpt" not in model_settings.update_model_settings(settings, {"providers": {"chatgpt": {"base_url": "https://other.invalid"}}})["providers"]


def test_four_effect_tags_and_quota_blocks_fallback_http(isolated, monkeypatch):
    from inku_server.chatgpt_provider import EFFECTS
    from inku_server.pipeline_provider import ProviderOptions, SingleAttemptProvider
    from inku_server.model_settings import default_model_settings
    value = profile(catalog={"expires_at": time.time() + 300, "models": [{"id": "model", "label": "Model"}]})
    seed(isolated, value)
    calls = []
    quota = {"value": False}
    real_client = httpx.AsyncClient
    def handle(request):
        calls.append(request)
        assert str(request.url) == auth.RESOURCE + "/responses"
        body = json.loads(request.content)
        assert set(body) == {"model", "store", "stream", "instructions", "input", "tools", "tool_choice", "parallel_tool_calls"}
        assert body["store"] is False and body["stream"] is True and body["instructions"] == "Rust system"
        assert body["tools"][0]["tools"][0]["parameters"] == {"type": "object"}
        wire, _ = stream_bytes(failed=quota["value"])
        return httpx.Response(200, content=wire, headers={"content-type": "text/event-stream"})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    transport = SingleAttemptProvider(ProviderOptions(settings=default_model_settings(), stage1_model="chatgpt:model", stage2_model="chatgpt:model",
                                      max_tokens=1, max_response_bytes=4096, chatgpt_owner="owner", chatgpt_profile=value["id"], chatgpt_generation=1))
    action = {"tag": "generate_normalized_ddl", "identity": {"action_id": "fixture", "attempt": "1"}, "timeout_ms": "5000",
              "payload": {"prompt": {"system": "Rust system", "message": "Rust message", "response_schema": {"type": "object"}}}}
    for tag in sorted(EFFECTS):
        result = transport({**action, "tag": tag})
        assert result["tag"] != "provider_failed" and result["identity"] == action["identity"]
    quota["value"] = True
    assert transport(action)["failure"] == "provider_rejected"
    before = len(calls)
    for tag in sorted(EFFECTS):
        assert transport({**action, "tag": tag})["failure"] == "provider_rejected"
        assert transport.chatgpt_failure_detail["action"] == "usage"
    assert len(calls) == before


def test_runtime_cancel_closes_blocked_stream_and_releases_slot(isolated, monkeypatch):
    from inku_server.chatgpt_provider import request
    value = profile(catalog={"expires_at": time.time() + 300, "models": [{"id": "model"}]})
    seed(isolated, value)
    runtime.begin_execution("owner", "execution")
    cancel = runtime.execution_cancel("owner", "execution")
    closed = threading.Event()
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            cancel.set()
            await asyncio.sleep(3)
            yield b""
        async def aclose(self):
            closed.set()
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, stream=Slow())), **kwargs))
    action = {"tag": "generate_normalized_ddl", "payload": {"prompt": {"system": "Rust", "message": "Rust", "response_schema": {"type": "object"}}}}
    with pytest.raises(ChatGPTError, match="cancelled"):
        asyncio.run(request("owner", value["id"], 1, "model", action, time.monotonic() + 5, 1024, cancel))
    assert closed.is_set()
    with isolated.lock("wire:owner:" + value["id"], time.monotonic() + 1):
        pass
    wire, _ = stream_bytes()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=wire)), **kwargs))
    from types import SimpleNamespace
    from inku_server.pipeline_api import PipelineService
    service = PipelineService.__new__(PipelineService)
    service._jobs = {}
    service._drain = lambda _run: asyncio.run(request("owner", value["id"], 1, "model", action, time.monotonic() + 5, 1024,
                                                     runtime.execution_cancel("owner", "execution")))
    with ThreadPoolExecutor(max_workers=1) as pool:
        service._pool = pool
        run = SimpleNamespace(context={"host_options": {"chatgpt_profile": value["id"]}}, view=lambda: {"busy": True})
        service._schedule(("owner", "execution"), run)
        assert json.loads(service._jobs[("owner", "execution")].result())
    assert cancel.is_set() and not runtime.execution_cancel("owner", "execution").is_set()
    runtime.retire_execution("owner", "execution")


def test_failed_initial_exchange_retains_issued_client_for_explicit_retry(isolated, monkeypatch):
    real_client = httpx.AsyncClient
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(400, json={"error": "invalid_grant"})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    coordinator = auth.AuthorizationAttempts()
    remote_host = "urn:uuid:" + str(uuid.uuid4())
    start = coordinator.begin("owner", None, False, lambda: runtime.check_owner("owner"), registration_host_id=remote_host)
    params = parse_qs(urlsplit(start["authorization_url"]).query)
    assert params["ext_agent_host_id"] == [remote_host]
    with httpx.Client() as client:
        assert client.get(params["redirect_uri"][0], params={"state": params["state"][0], "code": "expired", "client_id": "oaiapp_issued"}).status_code == 400
    assert len(calls) == 1
    pending = isolated.public_state("owner")["pending_registrations"]
    assert pending == [{"id": start["profile_id"], "client_id": "oaiapp_issued"}]
    again = coordinator.begin("owner", start["profile_id"], False, lambda: runtime.check_owner("owner"), registration_host_id=remote_host)
    assert parse_qs(urlsplit(again["authorization_url"]).query)["client_id"] == ["oaiapp_issued"]
    coordinator.stop("owner")


def test_identity_json_limit_closes_stream_before_reading_the_whole_body(isolated):
    class Large(httpx.AsyncByteStream):
        read = 0
        closed = False
        async def __aiter__(self):
            for _ in range(100):
                self.read += 1
                yield b"x" * (16 * 1024)
        async def aclose(self):
            self.closed = True
    body = Large()
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, stream=body))) as client:
            await auth.auth_json(client, "GET", auth.ISSUER + "/jwks", lambda: None, time.monotonic() + 5)
    with pytest.raises(ChatGPTError, match="too_large"):
        asyncio.run(run())
    assert body.closed and body.read == 65


def test_catalog_quota_also_blocks_later_catalog_and_inference(isolated, monkeypatch):
    from inku_server.chatgpt_provider import catalog, request
    value = profile()
    seed(isolated, value)
    calls = []
    real_client = httpx.AsyncClient
    def handle(req):
        calls.append(req)
        return httpx.Response(429, json={"error": {"code": "subscription_sharing_usage_limit_exceeded"}})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    with pytest.raises(ChatGPTError, match="usage_limit_exceeded"):
        asyncio.run(catalog("owner", value["id"], 1, time.monotonic() + 5))
    with pytest.raises(ChatGPTError, match="quota"):
        asyncio.run(catalog("owner", value["id"], 1, time.monotonic() + 5, force=True))
    with pytest.raises(ChatGPTError, match="quota"):
        asyncio.run(request("owner", value["id"], 1, "model", {"tag": "generate_sketch"}, time.monotonic() + 5, 1024))
    assert len(calls) == 1


def test_self_hosted_http_state_has_no_secrets_and_authorize_returns_only_helper(isolated, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from inku_server.api_core.routers import chatgpt
    value = profile()
    seed(isolated, value)
    runtime.configure_startup("0.0.0.0", 8100, self_hosted=True)
    app = FastAPI()
    app.include_router(chatgpt.router)
    app.dependency_overrides[chatgpt._current_user] = lambda: {"id": "owner"}
    with TestClient(app) as client:
        state = client.get("/api/me/chatgpt")
        assert state.status_code == 200 and state.json()["profiles"][0]["id"] == value["id"]
        assert all(secret not in state.text for secret in ("fixture-access", "fixture-refresh", "fixture-id", "authorization_url"))
        assert client.post("/api/me/chatgpt/authorize", json={}).json() == {"status": "local_authorization_required", "action": "local_helper"}
        assert client.post("/api/me/chatgpt/authorize", json={"token": "untrusted"}).status_code == 422
        monkeypatch.setenv("INKU_DEVELOPER_MODE", "0")
        assert client.get("/api/me/chatgpt").json()["profiles"] == []
        assert client.post("/api/me/chatgpt/authorize", json={}).status_code == 403


def test_pipeline_reprojection_keeps_safe_quota_only_for_the_same_action(isolated):
    from types import SimpleNamespace
    from inku_server.pipeline_candidate import CandidateExecution
    def step(snapshot, _input):
        saved = json.loads(snapshot)
        saved.update(sequence="1", action=None, phase={"tag": "failed", "reason": "stage1_failed"})
        return canonical({"kind": "output", "payload": {"result": {"snapshot": saved, "rendered": None,
                          "events": [{"tag": "failed", "payload": {"reason": "provider_rejected"}}]}}})
    snapshot = {"execution_id": "execution", "variation_id": "variation", "sequence": "0", "authority": {"revision": "0"},
                "document": None, "delivery": None, "action": {"tag": "generate_normalized_ddl", "identity": {"attempt": "1", "action_id": "current"}}}
    for source_id in ("current", "older"):
        run = CandidateExecution(SimpleNamespace(step=step), None, owner_id="owner", config={"envelope_limits": {
            "max_snapshot_bytes": 4096, "max_input_bytes": 4096, "max_output_bytes": 4096}}, provider=lambda _action: {},
            context={"provider_failure": {"failure": "provider_rejected", "stage": "stage1", "attempt": 1, "action_id": source_id,
                     "chatgpt": {"code": "subscription_sharing_usage_limit_exceeded", "action": "usage", "status": 429,
                                 "request_id": "req_fixture", "param": "raw secret text", "message": "never public"}}})
        run.restore(snapshot)
        run._advance({"tag": "effect_result", "result": {"elapsed_ms": "1"}})
        diagnostic = run.context["provider_failure"]
        if source_id == "older":
            assert "chatgpt" not in diagnostic
        else:
            assert diagnostic["chatgpt"]["action"] == "usage" and diagnostic["chatgpt"]["request_id"] == "req_fixture"
            assert diagnostic["chatgpt"]["param"] is None and "never public" not in str(diagnostic)
