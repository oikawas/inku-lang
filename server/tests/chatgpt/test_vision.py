"""Personal Vision admission and completed Responses text, without images or live HTTP."""

import asyncio
import json
import time

import httpx
import pytest
from fastapi import HTTPException

from inku_server import chatgpt_runtime as runtime
from inku_server.chatgpt_provider import TextSSEDecoder
from inku_server.chatgpt_store import ChatGPTError, CredentialStore
from inku_server.model_settings import default_model_settings
from inku_server.vision_client import vision_connection, vision_text
from inku_server.api_core.vision import prepare_vision_settings

IMAGE = "data:image/png;base64,iVBORw0KGgo="


@pytest.fixture
def personal(tmp_path, monkeypatch):
    from inku_server import db
    monkeypatch.setenv("INKU_CHATGPT_AUTH_DIR", str(tmp_path / "auth"))
    monkeypatch.setenv("INKU_CHATGPT_PLAN_ENABLED", "1")
    monkeypatch.setenv("INKU_DEVELOPER_MODE", "1")
    monkeypatch.setattr(db, "get_user", lambda owner: {"id": owner})
    monkeypatch.setattr(db, "single_user_mode_enabled", lambda: False)
    monkeypatch.setattr(runtime, "_startup", runtime._startup)
    runtime.configure_startup("127.0.0.1", 8100, self_hosted=False)
    store = CredentialStore()
    profile = {"id": "fixture-a", "issuer": "https://auth.openai.com", "sub": "fixture-sub",
               "client_id": "fixture-client", "state": "connected", "generation": 1,
               "refresh_owner": "runtime", "scopes": ["chatgpt.tokens.use.direct"],
               "expires_at": time.time() + 3600, "earliest_refresh_at": 0,
               "access_token": "fixture-a-token", "published_models": ["sight"],
               "catalog": {"expires_at": time.time() + 300,
                           "models": [{"id": "sight", "label": "Sight", "purposes": ["llm"]}]}}
    store.save_profile("owner", profile)
    return store, default_model_settings()


def event(value):
    return b"data: " + json.dumps(value, ensure_ascii=False).encode() + b"\n\n"


def completed(text="墨色が", second="右へ寄った"):
    return event({"type": "response.completed", "response": {"status": "completed", "output": [
        {"id": "message", "type": "message", "role": "assistant", "status": "completed", "content": [
            {"type": "output_text", "text": text}, {"type": "output_text", "text": second}]}]}})


def change_profile(store, **changes):
    with store.lock("edit:owner"):
        saved = store.read("owner")
        saved["profiles"]["fixture-a"].update(changes)
        store.write("owner", saved)


def test_pinned_vision_sends_images_without_tools_and_reads_only_completed_text(personal):
    # Failure: the shared Vision client speaks chat completions or switches to the newly active registration.
    store, settings = personal
    pinned = prepare_vision_settings({"id": "owner"}, "chatgpt:sight", settings)
    second = {**store.profile("owner"), "id": "fixture-b", "sub": "other-sub", "access_token": "fixture-b-token"}
    store.save_profile("owner", second)
    sent = []
    def reply(request):
        sent.append(request)
        return httpx.Response(200, content=completed(), headers={"content-type": "text/event-stream"})
    answer = vision_text(vision_connection("chatgpt", pinned), "sight", system="observe", text="what changed?",
                         images=[IMAGE, IMAGE], temperature=0.35, max_tokens=260, transport=httpx.MockTransport(reply))
    assert answer == "墨色が右へ寄った"
    assert len(sent) == 1 and str(sent[0].url) == "https://api.openai.com/v1/responses"
    assert sent[0].headers["authorization"] == "Bearer fixture-a-token"
    assert json.loads(sent[0].content) == {
        "model": "sight", "store": False, "stream": True, "instructions": "observe", "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "what changed?"},
                                          {"type": "input_image", "image_url": IMAGE},
                                          {"type": "input_image", "image_url": IMAGE}]}]}
    assert "chatgpt_profile_id" not in settings


@pytest.mark.parametrize("changes", [
    {"published_models": []}, {"model_purposes": {"sight": ["llm"]}},
    {"catalog": {"expires_at": time.time() + 300, "models": []}},
])
def test_vision_withdrawal_is_refused_before_responses_post(personal, changes):
    # Failure: unpublished, unknown, or LLM-only models still reach the personal account.
    store, settings = personal
    pinned = prepare_vision_settings({"id": "owner"}, "chatgpt:sight", settings)
    change_profile(store, **changes)
    def unexpected(_request):
        pytest.fail("withheld model sent a provider request")
    with pytest.raises(ChatGPTError, match="chatgpt_model_not_offered"):
        vision_text(vision_connection("chatgpt", pinned), "sight", system="observe", text="question",
                    images=[IMAGE], temperature=0.35, max_tokens=260, transport=httpx.MockTransport(unexpected))
    with pytest.raises(HTTPException) as refused:
        prepare_vision_settings({"id": "owner"}, "chatgpt:sight", settings)
    assert refused.value.detail["code"] == "chatgpt_model_not_offered"


def test_generation_change_during_stream_never_returns_an_answer(personal):
    # Failure: a completed HTTP answer escapes the registration generation guard.
    store, settings = personal
    pinned = prepare_vision_settings({"id": "owner"}, "chatgpt:sight", settings)
    def changed(_request):
        change_profile(store, generation=2)
        return httpx.Response(200, content=completed())
    with pytest.raises(ChatGPTError, match="chatgpt_session_changed"):
        vision_text(vision_connection("chatgpt", pinned), "sight", system="observe", text="question",
                    images=[IMAGE], temperature=0.35, max_tokens=260, transport=httpx.MockTransport(changed))


def test_shared_transport_keeps_drawing_tool_response(personal):
    # Failure: adding plain-text Vision mode changes the required tool result of ordinary drawing.
    from inku_server.chatgpt_provider import request
    _store, _settings = personal
    call = {"id": "call", "type": "function_call", "name": "submit_pipeline_response", "namespace": "inku",
            "arguments": '{"fixture":true}', "status": "completed"}
    def reply(sent):
        body = json.loads(sent.content)
        assert body["tool_choice"] == "required" and body["tools"][0]["type"] == "namespace"
        wire = event({"type": "response.output_item.added", "item": call})
        wire += event({"type": "response.completed", "response": {"status": "completed", "output": [call]}})
        return httpx.Response(200, content=wire)
    action = {"tag": "generate_sketch", "payload": {"prompt": {"system": "fixture", "message": "words",
                                                               "response_schema": {"type": "object"}}}}
    answer = asyncio.run(request("owner", "fixture-a", 1, "sight", action, time.monotonic() + 10, 1024,
                                 transport=httpx.MockTransport(reply)))
    assert json.loads(answer) == {"fixture": True}


def test_malformed_personal_catalog_keeps_classified_error(personal, monkeypatch):
    # Failure: a malformed upstream catalog becomes an unclassified HTTP 500 at Vision admission.
    from inku_server import chatgpt_provider
    async def malformed(*_args, **_kwargs):
        raise ValueError("fixture malformed JSON")
    monkeypatch.setattr(chatgpt_provider, "catalog", malformed)
    with pytest.raises(HTTPException) as refused:
        prepare_vision_settings({"id": "owner"}, "chatgpt:sight", personal[1])
    assert refused.value.detail == {"code": "chatgpt_response_invalid", "action": "diagnose"}


def test_text_decoder_requires_completion_and_refuses_partial_refusal_tool_and_byte_overflow():
    # Failure: partial text, refusal, tool output, or an oversized multibyte answer is accepted as Vision advice.
    partial = TextSSEDecoder(64)
    partial.feed(event({"type": "response.output_text.delta", "delta": "墨"}))
    with pytest.raises(ChatGPTError, match="chatgpt_response_incomplete"):
        partial.finish()
    for wire, code in [
        (event({"type": "response.incomplete"}), "chatgpt_response_incomplete"),
        (event({"type": "response.refusal.done"}), "chatgpt_refused"),
        (event({"type": "response.output_item.added", "item": {"type": "function_call"}}), "chatgpt_unexpected_tool"),
        (completed("墨", "墨"), "chatgpt_response_too_large"),
    ]:
        with pytest.raises(ChatGPTError, match=code):
            TextSSEDecoder(3).feed(wire)
    final = TextSSEDecoder(3)
    wire = completed("墨", "")
    for byte in wire:
        final.feed(bytes([byte]))
    assert final.finish() == "墨"
    item = {"id": "message", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": "墨"}]}
    fallback = TextSSEDecoder(3)
    fallback.feed(event({"type": "response.output_item.done", "item": item}))
    fallback.feed(event({"type": "response.completed", "response": {"status": "completed", "output": []}}))
    assert fallback.finish() == "墨"


@pytest.mark.parametrize("route", ["refine", "colophon"])
def test_vision_routes_carry_owner_pin_and_preserve_chatgpt_error(personal, monkeypatch, route):
    # Failure: the route loses owner/profile/generation or turns the classified refusal into a generic 502.
    from inku_server.api_core.routers import render, lineage
    _store, settings = personal
    monkeypatch.setattr(render._db, "get_model_settings", lambda: settings)
    monkeypatch.setattr(render._db, "get_items", lambda *_: [{"svg": "<svg/>"}])
    monkeypatch.setattr(lineage._db, "get_lineage_branch", lambda *_: {})
    def refuse(*_args, **kwargs):
        assert kwargs["settings"]["chatgpt_owner_id"] == "owner"
        assert kwargs["settings"]["chatgpt_profile_id"] == "fixture-a"
        assert kwargs["settings"]["chatgpt_generation"] == 1
        raise ChatGPTError("chatgpt_session_changed")
    monkeypatch.setattr(render, "vision_refine_advice", refuse)
    monkeypatch.setattr(lineage, "generate_okugaki", refuse)
    with pytest.raises(HTTPException) as refused:
        if route == "refine":
            render.api_vision_refine_advice(render.VisionRefineAdviceBody(history_id="fixture", model="chatgpt:sight",
                instruction="fixture", enabled_kinds=["layout_change"]), {"id": "owner"})
        else:
            lineage.api_okugaki_generate("fixture", lineage.OkugakiGenerateBody(model="chatgpt:sight", save=False), None, {"id": "owner"})
    assert refused.value.status_code == 403
    assert refused.value.detail == {"code": "chatgpt_session_changed", "action": "reconnect"}


def test_colophon_cache_is_profile_bound_and_cannot_bypass_withdrawal(personal, monkeypatch):
    # Failure: a cached response is borrowed from another registration or bypasses a withdrawn Vision purpose.
    from inku_server import okugaki
    store, settings = personal
    pinned = prepare_vision_settings({"id": "owner"}, "chatgpt:sight", settings)
    calls = []
    monkeypatch.setattr(okugaki, "vision_text", lambda *args, **kwargs: calls.append(args[0]["profile_id"]) or "visible facts")
    kwargs = {"model": "chatgpt:sight", "language": "ja", "request": {"fixture": "personal-cache-unique"}, "images": [IMAGE]}
    assert okugaki._vision_chat(**kwargs, settings=pinned) == "visible facts"
    assert okugaki._vision_chat(**kwargs, settings=pinned) == "visible facts"
    assert calls == ["fixture-a"]
    second = {**store.profile("owner"), "id": "fixture-b", "sub": "other-sub"}
    store.save_profile("owner", second)
    another = prepare_vision_settings({"id": "owner"}, "chatgpt:sight", settings)
    assert okugaki._vision_chat(**kwargs, settings=another) == "visible facts"
    assert calls == ["fixture-a", "fixture-b"]
    change_profile(store, model_purposes={"sight": ["llm"]})
    with pytest.raises(ChatGPTError, match="chatgpt_model_not_offered"):
        okugaki._vision_chat(**kwargs, settings=pinned)
    assert calls == ["fixture-a", "fixture-b"]
