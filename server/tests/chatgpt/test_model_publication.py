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
        assert all(model["purposes"] == ["llm", "vision"] for model in fetched["models"])
        assert public.api_models(actor).drawing_catalog[-1]["models"] == []
        body = {"profile_id": profile["id"], "generation": 1, "published_models": ["luna"]}
        assert client.put("/api/me/chatgpt/models/settings", json=body).json()["enabled_models"] == {"luna": True, "other": False}
        drawing = public.api_models(actor)
        assert [entry["id"] for entry in drawing.drawing_catalog[-1]["models"]] == ["luna"]
        assert [entry["id"] for entry in drawing.vision_catalog[-1]["models"]] == ["luna"]
        assert all(provider["id"] != "chatgpt" for provider in drawing.catalog + drawing.llm_catalog)
        assert "chatgpt" not in shared_settings["providers"]
        assert offered("owner", "luna") and not offered("owner", "other")
        action = {"tag": "generate_normalized_ddl", "payload": {"prompt": {}}}
        with pytest.raises(ChatGPTError, match="model_not_offered"):
            asyncio.run(request("owner", profile["id"], 1, "other", action, time.monotonic() + 5, 4096))
        assert len(calls) == 1
        assert client.put("/api/me/chatgpt/models/settings", json={**body, "published_models": ["hidden"]}).status_code == 403
        invalid = client.put("/api/me/chatgpt/models/settings", json={**body, "model_purposes": {"luna": []}})
        assert invalid.status_code == 403 and invalid.json()["detail"]["code"] == "chatgpt_model_not_offered"
        assert client.put("/api/me/chatgpt/models/settings", json={**body, "model_purposes": {"hidden": ["vision"]}}).status_code == 403
        assert client.put("/api/me/chatgpt/models/settings", json={**body, "model_purposes": {"luna": ["audio"]}}).status_code == 422
        assert store.profile("owner").get("model_purposes", {}) == {}
        vision_only = {**body, "model_purposes": {"luna": ["vision"], "other": []}}
        published = client.put("/api/me/chatgpt/models/settings", json=vision_only).json()
        assert [(model["id"], model["purposes"], model["enabled"]) for model in published["models"]] == [
            ("luna", ["vision"], True), ("other", [], False),
        ]
        assert client.get("/api/me/chatgpt/models/settings").json() == published
        drawing = public.api_models(actor)
        assert drawing.drawing_catalog[-1]["models"] == []
        assert [entry["id"] for entry in drawing.vision_catalog[-1]["models"]] == ["luna"]
        assert drawing.vision_catalog[-1]["id"] == "chatgpt"
        assert drawing.vision_catalog[-1]["kind"] == "chatgpt_responses"
        assert not offered("owner", "luna") and offered("owner", "luna", purpose="vision")
        assert not offered("owner", "other", purpose="vision")
        assert client.put("/api/me/chatgpt/models/settings", json=body).json() == published
        # Assessments are shared model settings (the author, 2026-10-13): administration
        # writes them and every subscriber's publication reads them; the personal
        # route no longer takes them.
        assert client.put("/api/me/chatgpt/models/settings", json={**body, "model_metadata": {"luna": {"comment_ja": "本人"}}}).status_code == 422
        shared_settings["chatgpt_models"] = [{"id": "luna", "recommendation_vision": 3, "speed_vision_seconds": 6.5,
                                              "comment_ja": "共通の評価", "comment_en": "Shared assessment"}]
        assessed = client.get("/api/me/chatgpt/models/settings").json()
        luna = assessed["models"][0]
        assert (luna["recommendation_vision"], luna["speed_vision_seconds"], luna["comment_ja"]) == (3, 6.5, "共通の評価")
        assert luna["purposes"] == ["vision"] and assessed["enabled_models"] == published["enabled_models"]
        assert public.api_models(actor).vision_catalog[-1]["models"][0]["comment_en"] == "Shared assessment"
        assert client.post("/api/me/chatgpt/models/refresh").json()["models"][0]["comment_ja"] == "共通の評価"
        assert store.profile("owner")["catalog"]["models"][0] == {"id": "luna", "label": "Luna", "purposes": ["llm", "vision"]}
        assert store.profile("owner").get("model_metadata", {}) == {}
        # A purpose measured without a response leaves the publication and cannot be published.
        shared_settings["chatgpt_models"] = [{"id": "luna", "unsupported_purposes": ["vision"]}]
        silent = client.get("/api/me/chatgpt/models/settings").json()
        assert (silent["models"][0]["purposes"], silent["enabled_models"]["luna"]) == ([], False)
        assert public.api_models(actor).vision_catalog[-1]["models"] == []
        assert client.put("/api/me/chatgpt/models/settings", json=vision_only).status_code == 403
        shared_settings.pop("chatgpt_models")
        actor = {"id": "other-owner"}
        assert client.get("/api/me/chatgpt/models/settings").status_code == 403
        assert client.put("/api/me/chatgpt/models/settings", json=body).status_code == 403
        actor = {"id": "owner"}
        # The refresh/reauthorization snapshot predates the later publication save.
        store.save_profile("owner", {**profile, "generation": 2, "catalog": store.profile("owner")["catalog"]}, expected_generation=1)
        assert store.profile("owner")["published_models"] == ["luna"]
        assert store.profile("owner")["model_purposes"] == {"luna": ["vision"], "other": []}
        assert client.put("/api/me/chatgpt/models/settings", json=body).status_code == 403
        other_profile = {**profile, "id": str(uuid.uuid4())}
        store.save_profile("owner", other_profile)
        assert client.put("/api/me/chatgpt/models/settings", json={**body, "generation": 2}).status_code == 403
        assert len(calls) == 2
        switch_during_fetch = True
        late = client.post("/api/me/chatgpt/models/refresh")
        assert late.status_code == 403 and late.json()["detail"]["code"] == "chatgpt_session_changed"
        assert len(calls) == 3


def test_old_catalog_purposes_do_not_override_unset_profile_choices():
    from inku_server.chatgpt_models import publication

    profile = {"id": "fixture-profile", "generation": 1, "published_models": ["fixture-model"],
               "catalog": {"models": [{"id": "fixture-model", "label": "Fixture", "purposes": ["llm"]}]}}
    assert publication(profile)["models"] == [
        {"id": "fixture-model", "label": "Fixture", "purposes": ["llm", "vision"],
         "enabled": True, "labels": ["unmeasured"], "fold": "unmeasured"},
    ]


def test_chatgpt_model_admission_limits_operations_and_passes_the_runtime_profile_pin(monkeypatch):
    from inku_server import chatgpt_provider
    from inku_server.api_core.common import _model_offered_to
    from inku_server.model_settings import default_model_settings

    calls = []
    monkeypatch.setattr(chatgpt_provider, "offered", lambda *args, **kwargs: calls.append((args, kwargs)) or True)
    settings = {**default_model_settings(), "chatgpt_profile_id": "fixture-profile", "chatgpt_generation": 7}
    assert _model_offered_to({"id": "owner"}, "chatgpt:luna", stage="stage1", purpose="vision", settings=settings, operation="vision")
    assert calls == [(("owner", "luna"), {"purpose": "vision", "profile_id": "fixture-profile", "generation": 7})]
    assert _model_offered_to({"id": "owner"}, "chatgpt:luna", stage="stage1", purpose="llm", settings=settings, operation="pipeline")
    assert calls[-1][1]["purpose"] == "llm"
    for operation, purpose in ((None, "vision"), ("pipeline", "vision"), ("vision", "llm"), ("demo", "llm")):
        assert not _model_offered_to({"id": "owner"}, "chatgpt:luna", stage="stage1", purpose=purpose, settings=settings, operation=operation)
    assert not _model_offered_to(None, "chatgpt:luna", stage="stage1", purpose="vision", settings=settings, operation="vision")
    assert len(calls) == 2
    assert _model_offered_to({"id": "owner"}, "chatgpt:luna", stage="stage1", purpose="vision", settings=default_model_settings(), operation="vision")
    assert calls[-1][1] == {"purpose": "vision", "profile_id": None, "generation": None}


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


def test_finalized_streamed_call_survives_an_empty_terminal_output_but_not_an_unfinished_or_failed_response():
    arguments = canonical({"normalized_ddl": "赤い円を置く。"}).decode()
    call = {"type": "function_call", "id": "fc_fixture", "call_id": "call_fixture",
            "name": "submit_pipeline_response", "namespace": "inku", "arguments": arguments, "status": "completed"}
    events = [
        {"type": "response.output_item.added", "item": {**call, "arguments": "", "status": "in_progress"}},
        {"type": "response.function_call_arguments.delta", "item_id": call["id"], "delta": arguments},
        {"type": "response.function_call_arguments.done", "item_id": call["id"], "arguments": arguments},
        {"type": "response.output_item.done", "item": call},
    ]
    for response in ({"status": "completed", "output": []}, {"status": "completed", "output": None}, {"status": "completed"}):
        decoder = SSEDecoder(4096)
        for event in [*events, {"type": "response.completed", "response": response}]:
            decoder.feed(b"data: " + canonical(event) + b"\n\n")
        assert decoder.finish() == arguments
    unfinished = SSEDecoder(4096)
    for event in events[:-1]:
        unfinished.event(event)
    with pytest.raises(ChatGPTError, match="unexpected_tool"):
        unfinished.event({"type": "response.completed", "response": {"status": "completed", "output": []}})
    failed = SSEDecoder(4096)
    for event in events:
        failed.event(event)
    with pytest.raises(ChatGPTError, match="response_failed"):
        failed.event({"type": "response.failed", "response": {"status": "failed", "error": {"code": "unknown"}}})
    mismatched = SSEDecoder(4096)
    for event in events:
        mismatched.event(event)
    with pytest.raises(ChatGPTError, match="response_invalid"):
        mismatched.event({"type": "response.completed", "response": {"status": "completed", "output": [
            {**call, "arguments": "{}"},
        ]}})
