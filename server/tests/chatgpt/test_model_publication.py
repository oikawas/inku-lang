"""Account-local publication and the reported Stage 1 tool-shape failure."""

import json
import asyncio
import time
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from inku_server.chatgpt_provider import SSEDecoder
from inku_server.chatgpt_store import ChatGPTError, canonical


def test_personal_publication_routes_offer_only_saved_models_and_reject_stale_or_other_owner(tmp_path, monkeypatch):
    from inku_server import chatgpt_auth as auth, chatgpt_runtime as runtime, db
    from inku_server.api_core.deps import _current_user
    from inku_server.api_core.routers import chatgpt, public
    from inku_server.chatgpt_provider import offered, request
    from inku_server.chatgpt_store import CredentialStore
    from inku_server.model_settings import default_model_settings

    monkeypatch.setenv("INKU_CHATGPT_AUTH_DIR", str(tmp_path / "auth"))
    monkeypatch.setenv("INKU_CHATGPT_PLAN_ENABLED", "1")
    monkeypatch.setenv("INKU_DEVELOPER_MODE", "1")
    monkeypatch.setattr(db, "get_user", lambda owner: {"id": owner})
    monkeypatch.setattr(db, "single_user_mode_enabled", lambda: False)
    monkeypatch.setattr(runtime, "_startup", runtime._startup)
    runtime.configure_startup("127.0.0.1", 8100, self_hosted=False)
    shared_settings = default_model_settings()
    monkeypatch.setattr(public._db, "get_model_settings", lambda: shared_settings)
    profile = {"id": str(uuid.uuid4()), "issuer": auth.ISSUER, "sub": "fixture-sub", "client_id": "fixture-client",
               "state": "connected", "generation": 1, "refresh_owner": "runtime", "scopes": ["chatgpt.tokens.use.direct"],
               "expires_at": time.time() + 3600, "earliest_refresh_at": 0, "access_token": "fixture-access"}
    store = CredentialStore()
    store.save_profile("owner", profile)
    calls = []
    switch_during_fetch = False
    real_client = httpx.AsyncClient
    def handle(req):
        calls.append(str(req.url))
        assert req.method == "GET" and str(req.url) == auth.RESOURCE + "/models"
        if switch_during_fetch:
            with store.lock("edit:owner", time.monotonic() + 5):
                saved = store.read("owner")
                saved["active"] = profile["id"]
                store.write("owner", saved)
        return httpx.Response(200, json={"models": [
            {"slug": "luna", "display_name": "Luna", "visibility": "list"},
            {"slug": "hidden", "display_name": "Hidden", "visibility": "hide"},
            {"slug": "other", "display_name": "Other", "visibility": "list"},
        ]})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    actor = {"id": "owner"}
    app = FastAPI()
    app.include_router(chatgpt.router)
    app.dependency_overrides[_current_user] = lambda: actor
    with TestClient(app) as client:
        assert client.get("/api/me/chatgpt/models/settings").json()["models"] == []
        assert calls == []
        fetched = client.post("/api/me/chatgpt/models/refresh").json()
        assert [model["id"] for model in fetched["models"]] == ["luna", "other"]
        assert fetched["enabled_models"] == {"luna": False, "other": False}
        assert public.api_models(actor).drawing_catalog[-1]["models"] == []
        body = {"profile_id": profile["id"], "generation": 1, "published_models": ["luna"]}
        assert client.put("/api/me/chatgpt/models/settings", json=body).json()["enabled_models"] == {"luna": True, "other": False}
        drawing = public.api_models(actor)
        assert [entry["id"] for entry in drawing.drawing_catalog[-1]["models"]] == ["luna"]
        assert all(provider["id"] != "chatgpt" for provider in drawing.llm_catalog + drawing.vision_catalog)
        assert "chatgpt" not in shared_settings["providers"]
        assert offered("owner", "luna") and not offered("owner", "other")
        action = {"tag": "generate_normalized_ddl", "payload": {"prompt": {}}}
        with pytest.raises(ChatGPTError, match="model_not_offered"):
            asyncio.run(request("owner", profile["id"], 1, "other", action, time.monotonic() + 5, 4096))
        assert len(calls) == 1
        assert client.put("/api/me/chatgpt/models/settings", json={**body, "published_models": ["hidden"]}).status_code == 403
        actor = {"id": "other-owner"}
        assert client.get("/api/me/chatgpt/models/settings").status_code == 403
        assert client.put("/api/me/chatgpt/models/settings", json=body).status_code == 403
        actor = {"id": "owner"}
        # The refresh/reauthorization snapshot predates the later publication save.
        store.save_profile("owner", {**profile, "generation": 2}, expected_generation=1)
        assert store.profile("owner")["published_models"] == ["luna"]
        assert client.put("/api/me/chatgpt/models/settings", json=body).status_code == 403
        store.save_profile("owner", {**profile, "id": str(uuid.uuid4())})
        assert client.put("/api/me/chatgpt/models/settings", json={**body, "generation": 2}).status_code == 403
        assert len(calls) == 1
        switch_during_fetch = True
        late = client.post("/api/me/chatgpt/models/refresh")
        assert late.status_code == 403 and late.json()["detail"]["code"] == "chatgpt_session_changed"
        assert len(calls) == 2


def test_completed_function_with_assistant_message_is_accepted_without_using_text():
    arguments = json.dumps({"ddl": "赤い円を置く。"}, ensure_ascii=False)
    call = {"type": "function_call", "id": "fc_fixture", "call_id": "call_fixture",
            "name": "submit_pipeline_response", "namespace": "inku", "arguments": arguments}
    message = {"type": "message", "id": "msg_fixture", "role": "assistant",
               "content": [{"type": "output_text", "text": "Supplementary text is not pipeline data."}]}
    decoder = SSEDecoder(4096)
    for event in [
        {"type": "response.output_item.added", "item": {**message, "content": []}},
        {"type": "response.output_item.done", "item": message},
        {"type": "response.output_item.added", "item": {**call, "arguments": ""}},
        {"type": "response.function_call_arguments.delta", "item_id": call["id"], "delta": arguments},
        {"type": "response.completed", "response": {"status": "completed", "output": [message, call]}},
    ]:
        decoder.feed(b"data: " + canonical(event) + b"\n\n")
    assert decoder.finish() == arguments
    with pytest.raises(ChatGPTError, match="unexpected_tool") as rejected:
        SSEDecoder(4096).event({"type": "response.completed", "response": {"status": "completed", "output": [message]}})
    assert rejected.value.action == "diagnose"
    with pytest.raises(ChatGPTError, match="refused"):
        SSEDecoder(4096).event({"type": "response.completed", "response": {"status": "completed", "output": [
            {**message, "content": [{"type": "refusal", "refusal": "Not pipeline data."}]}, call,
        ]}})
    with pytest.raises(ChatGPTError, match="unexpected_tool"):
        SSEDecoder(4096).event({"type": "response.output_item.added", "item": {**call, "namespace": "other"}})
