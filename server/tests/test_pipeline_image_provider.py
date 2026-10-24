"""Image effects keep ordered references, Vision admission and digest-only capture."""

import asyncio
import base64
from contextlib import nullcontext
import hashlib
import json
import time

import httpx
import pytest

from inku_server import chatgpt_provider, provider_wire
from inku_server.chatgpt_store import ChatGPTError
from inku_server.pipeline_provider import ProviderOptions, SingleAttemptProvider, provider_stage_record


def _image(value: bytes, media_type="image/jpeg"):
    return "data:" + media_type + ";base64," + base64.b64encode(value).decode(), {
        "media_type": media_type, "byte_len": len(value), "sha256": hashlib.sha256(value).hexdigest(),
        "width": 20, "height": 10,
    }


ORIGINAL, ORIGINAL_REF = _image(b"original-image-private-bytes")
DRAWING, DRAWING_REF = _image(b"review-image-private-bytes", "image/png")


def _action(tag, refs):
    return {"tag": tag, "timeout_ms": "2000",
            "identity": {"action_id": "image-a", "attempt": 1, "request_digest": "digest"},
            "payload": {"prompt": {"system": "observe image", "message": "write DDL", "action_name": tag,
                                     "response_schema": {"type": "object", "properties": {"normalized_ddl": {"type": "string"}}},
                                     "images": refs}}}


class Capture:
    def __init__(self):
        self.requests, self.responses, self.outcomes = [], [], []

    def request(self, *args):
        self.requests.append(args)
        return False

    def response(self, *args, **kwargs):
        self.responses.append((args, kwargs))

    def outcome(self, *args, **kwargs):
        self.outcomes.append((args, kwargs))


def _fixture_provider(monkeypatch, reply, *, images, capture=None):
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", lambda *args, **kwargs: ("fixture", "sight"))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "fixture", "kind": "openai_compatible", "base_url": "https://provider.invalid/v1",
        "api_key": "fixture", "requires_api_key": True,
    })
    return SingleAttemptProvider(ProviderOptions({}, "fixture:sight", "fixture:sight", 8192, 16384),
                                 transport=httpx.MockTransport(reply), images=images,
                                 observation=(capture, "owner", "execution") if capture else None)


@pytest.mark.parametrize("tag,result_tag,images,refs", [
    ("select_image_catalog", "image_catalog_selected", [ORIGINAL], [ORIGINAL_REF]),
    ("write_image_ddl", "image_ddl_written", [ORIGINAL], [ORIGINAL_REF]),
    ("review_image_ddl", "image_ddl_reviewed", [ORIGINAL, DRAWING], [ORIGINAL_REF, DRAWING_REF]),
])
def test_image_effects_send_ordered_images_with_structured_response_and_digest_capture(monkeypatch, tag, result_tag, images, refs):
    # Failure: an image action is unsupported, drops/reorders attachments, or persists the request/response bytes.
    seen = []
    raw = json.dumps({"choices": [{"message": {"tool_calls": [{"type": "function", "function": {
        "name": "submit_pipeline_response", "arguments": '{"normalized_ddl":"墨を置く。"}',
    }}]}}]}, ensure_ascii=False).encode()

    def reply(request):
        seen.append(request.content)
        return httpx.Response(200, content=raw)

    capture = Capture()
    action = _action(tag, refs)
    result = _fixture_provider(monkeypatch, reply, images=images, capture=capture)(action)
    assert result["tag"] == result_tag
    assert result["response"] == '{"normalized_ddl":"墨を置く。"}'
    assert provider_stage_record(tag) == "image"
    body = json.loads(seen[0])
    assert body["messages"][1]["content"] == [{"type": "text", "text": "write DDL"}] + [
        {"type": "image_url", "image_url": {"url": image}} for image in images]
    assert body["tools"][0]["function"]["parameters"] == action["payload"]["prompt"]["response_schema"]
    assert capture.requests[0][3] == "image"
    assert json.loads(capture.requests[0][-1]) == {"capture": "digest_only", "byte_len": len(seen[0]),
                                                 "sha256": hashlib.sha256(seen[0]).hexdigest()}
    assert json.loads(capture.responses[0][1]["raw"]) == {"capture": "digest_only", "byte_len": len(raw),
                                                        "sha256": hashlib.sha256(raw).hexdigest()}
    assert capture.outcomes[0][1]["capture_complete"] is True


@pytest.mark.parametrize("images,refs", [
    (None, [ORIGINAL_REF]),
    ([ORIGINAL], []),
    ([DRAWING, ORIGINAL], [ORIGINAL_REF, DRAWING_REF]),
    ([ORIGINAL], [{**ORIGINAL_REF, "sha256": "0" * 64}]),
    ([ORIGINAL], [{**ORIGINAL_REF, "byte_len": 1}]),
    ([ORIGINAL], [{**ORIGINAL_REF, "media_type": "image/png"}]),
])
def test_image_reference_mismatch_is_rejected_before_http(monkeypatch, images, refs):
    # Failure: the wrong private image reaches HTTP despite the core's ordered image references.
    def unexpected(_request):
        pytest.fail("mismatched image reached HTTP")

    result = _fixture_provider(monkeypatch, unexpected, images=images)(_action("write_image_ddl", refs))
    assert result["tag"] == "provider_failed" and result["failure"] == "provider_rejected"


@pytest.mark.parametrize("observed", [False, True])
def test_image_rejection_never_logs_or_captures_echoed_image_or_svg(monkeypatch, caplog, observed):
    # Failure: a provider rejection echoes the attachment or SVG into developer records or logs.
    private = ORIGINAL + "<svg>private-review-svg</svg>"
    raw = json.dumps({"error": {"message": private, "param": private, "code": private}}).encode()
    capture = Capture() if observed else None
    provider = _fixture_provider(monkeypatch, lambda _request: httpx.Response(400, content=raw),
                                 images=[ORIGINAL], capture=capture)
    with caplog.at_level("WARNING", logger="inku_server.pipeline_provider"):
        assert provider(_action("write_image_ddl", [ORIGINAL_REF]))["failure"] == "provider_rejected"
    assert ORIGINAL not in caplog.text and "private-review-svg" not in caplog.text
    if capture:
        assert capture.responses[0][1]["raw"] == provider_wire.observation_digest(raw)
        assert ORIGINAL not in repr(capture.__dict__) and "private-review-svg" not in repr(capture.__dict__)


def _chatgpt(monkeypatch, purposes):
    class Store:
        def lock(self, *args):
            return nullcontext()

    monkeypatch.setattr(chatgpt_provider, "CredentialStore", Store)
    monkeypatch.setattr(chatgpt_provider, "check_session", lambda *args: {})

    async def catalog(*args, **kwargs):
        return [{"id": "sight", "enabled": True, "purposes": purposes}]

    async def token(*args):
        return "fixture-token"

    monkeypatch.setattr(chatgpt_provider, "catalog", catalog)
    monkeypatch.setattr(chatgpt_provider, "access_token", token)


def _event(value):
    return b"data: " + json.dumps(value, ensure_ascii=False).encode() + b"\n\n"


def test_chatgpt_image_effect_uses_vision_admission_structured_request_and_decoder(monkeypatch):
    # Failure: purpose=vision uses the plain-text Vision path, loses its tool schema, or captures private bodies.
    _chatgpt(monkeypatch, ["vision"])
    action = _action("review_image_ddl", [ORIGINAL_REF, DRAWING_REF])
    call = {"id": "call", "type": "function_call", "name": "submit_pipeline_response", "namespace": "inku",
            "arguments": '{"normalized_ddl":"墨を置く。"}', "status": "completed"}
    raw = _event({"type": "response.output_item.added", "item": call})
    raw += _event({"type": "response.completed", "response": {"status": "completed", "output": [call]}})
    seen = []

    def reply(request):
        seen.append(request.content)
        return httpx.Response(200, content=raw)

    capture = Capture()
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", lambda *args, **kwargs: ("chatgpt", "sight"))
    provider = SingleAttemptProvider(ProviderOptions({}, "chatgpt:sight", "chatgpt:sight", 8192, 16384,
                                                    chatgpt_owner="owner", chatgpt_profile="profile", chatgpt_generation=1),
                                     transport=httpx.MockTransport(reply), images=[ORIGINAL, DRAWING],
                                     observation=(capture, "owner", "execution"))
    result = provider(action)
    assert result["tag"] == "image_ddl_reviewed" and result["response"] == call["arguments"]
    body = json.loads(seen[0])
    assert body["tool_choice"] == "required" and body["tools"][0]["type"] == "namespace"
    assert body["input"][0]["content"] == [{"type": "input_text", "text": "write DDL"},
                                           {"type": "input_image", "image_url": ORIGINAL},
                                           {"type": "input_image", "image_url": DRAWING}]
    canonical = provider_wire.chatgpt_request("sight", action["payload"]["prompt"], 16384,
                                             images=[ORIGINAL, DRAWING])["canonical"].encode()
    assert capture.requests[0][-1] == provider_wire.observation_digest(canonical)
    assert capture.responses[0][1]["raw"] == provider_wire.observation_digest(raw)
    assert capture.responses[0][1]["decoded"] is None


def test_chatgpt_image_effect_requires_vision_and_matching_references_before_http(monkeypatch):
    # Failure: LLM-only admission or mismatched image bytes reach a personal Responses endpoint.
    _chatgpt(monkeypatch, ["llm"])
    action = _action("write_image_ddl", [ORIGINAL_REF])

    def unexpected(_request):
        pytest.fail("unadmitted image reached HTTP")

    async def invoke(images):
        return await chatgpt_provider.request("owner", "profile", 1, "sight", action, time.monotonic() + 5,
                                              8192, purpose="vision", images=images,
                                              transport=httpx.MockTransport(unexpected))

    with pytest.raises(ChatGPTError, match="chatgpt_model_not_offered"):
        asyncio.run(invoke([ORIGINAL]))

    async def unexpected_catalog(*args, **kwargs):
        pytest.fail("image mismatch reached catalog refresh")

    monkeypatch.setattr(chatgpt_provider, "catalog", unexpected_catalog)
    with pytest.raises(provider_wire.ProviderWireRefused, match="images do not match the prompt"):
        asyncio.run(invoke([DRAWING]))


def test_chatgpt_image_rejection_keeps_only_safe_diagnostic_and_digest(monkeypatch, caplog):
    # Failure: a personal provider echoes image/SVG bytes into its recorded error fields or response capture.
    _chatgpt(monkeypatch, ["vision"])
    private = ORIGINAL + "<svg>private-review-svg</svg>"
    raw = json.dumps({"error": {"message": private, "param": private, "code": private}}).encode()
    capture = Capture()
    action = _action("write_image_ddl", [ORIGINAL_REF])

    async def invoke():
        return await chatgpt_provider.request("owner", "profile", 1, "sight", action, time.monotonic() + 5,
                                              8192, purpose="vision", images=[ORIGINAL], observation=(capture, "execution"),
                                              transport=httpx.MockTransport(lambda _request: httpx.Response(
                                                  400, content=raw, headers={"x-request-id": private})))

    with pytest.raises(chatgpt_provider.ResponseFailure) as refused:
        asyncio.run(invoke())
    assert (refused.value.code, refused.value.param, refused.value.request_id) == ("chatgpt_response_failed", None, None)
    assert capture.responses[0][1]["raw"] == provider_wire.observation_digest(raw)
    assert ORIGINAL not in repr(capture.__dict__) and "private-review-svg" not in repr(capture.__dict__)
    assert ORIGINAL not in caplog.text and "private-review-svg" not in caplog.text


def test_non_image_wire_omits_images_and_keeps_existing_bytes(monkeypatch):
    # Failure: adding optional image arguments changes an ordinary pipeline request's native wire input.
    asked = []
    monkeypatch.setattr(provider_wire, "_ask", lambda action, **fields: asked.append((action, fields)) or {})
    prompt = {"system": "words", "message": "words", "response_schema": {"type": "object"}}
    provider_wire.pipeline_request({"id": "fixture"}, "model", prompt, 256)
    provider_wire.chatgpt_request("model", prompt, 8192)
    assert all("images" not in fields and fields["prompt"] == prompt for _, fields in asked)
