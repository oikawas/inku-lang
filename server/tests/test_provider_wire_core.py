"""A provider request's bytes and the reading of its answer are the shared core's rule.

The rows in data/provider-wire-cases.json were written by the transport Server
used to hold (pipeline_provider.py with openai_request.py, anthropic_request.py,
gemini_request.py, schema_order.py and provider_refusal.py, and vision_client.py),
each body as it was sent, and the ChatGPT plan rows by chatgpt_provider.py.
Android and Swift read the same file. Each check
below goes through every row and says how many it compared.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter

import httpx
import pytest

from inku_server import provider_wire
from inku_server.pipeline_provider import ProviderOptions, SingleAttemptProvider

CASES = json.loads((pathlib.Path(__file__).parent / "data" / "provider-wire-cases.json").read_text(encoding="utf-8"))
# What httpx adds to every request, which the rows leave out.
_CLIENT_HEADERS = {"host", "content-length", "accept", "accept-encoding", "connection", "user-agent"}


def _built(row: dict) -> dict:
    request = row["request"]
    if request["action"] == "pipeline_request":
        return provider_wire.pipeline_request(request["connection"], request["model"], request["prompt"],
                                              request["max_tokens"])
    return provider_wire.text_request(request["connection"], request["model"], system=request["system"],
                                      text=request["text"], images=request["images"],
                                      temperature=request["temperature"], max_tokens=request["max_tokens"])


@pytest.mark.parametrize(("section", "rows"), [("requests", 246), ("text_requests", 81)])
def test_every_shared_request_is_written_as_server_wrote_it(section, rows):
    compared = 0
    for row in CASES[section]:
        expect = row["expect"]
        if expect["outcome"] == "refused":
            with pytest.raises(provider_wire.ProviderWireRefused) as refused:
                _built(row)
            assert (refused.value.reason, refused.value.detail) == (expect["reason"], expect["detail"]), row["why"]
        else:
            built = _built(row)
            assert built["url"] == expect["url"], row["why"]
            assert built["body"] == expect["body"], row["why"]
            sent = {name.lower(): value for name, value in provider_wire.headers(built, "KEY").items()}
            assert sent == expect["headers"], row["why"]
        compared += 1
    assert compared == rows


def test_the_pipeline_transport_sends_the_bytes_server_sent(monkeypatch):
    """Every pipeline row the core can build, sent through SingleAttemptProvider."""
    compared = 0
    for row in CASES["requests"]:
        if row["expect"]["outcome"] != "ok":
            continue
        request = row["request"]
        connection = {**request["connection"], "api_key": "KEY", "requires_api_key": True, "rate_limits": None}
        monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model",
                            lambda *args, **kwargs: (connection["id"], request["model"]))
        monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: connection)
        sent = []

        def refuse(value: httpx.Request) -> httpx.Response:
            sent.append(value)
            return httpx.Response(503, json={})

        provider = SingleAttemptProvider(ProviderOptions({}, "m", "m", request["max_tokens"], 8192),
                                         transport=httpx.MockTransport(refuse))
        action = {"tag": "generate_sketch", "timeout_ms": "5000", "identity": {"attempt": "1"},
                  "payload": {"prompt": request["prompt"]}}
        assert provider(action)["failure"] == "transport_unavailable", row["why"]
        assert sent[0].content.decode("utf-8") == row["expect"]["body"], row["why"]
        assert str(sent[0].url) == row["expect"]["url"], row["why"]
        headers = {name: value for name, value in sent[0].headers.items() if name not in _CLIENT_HEADERS}
        assert headers == row["expect"]["headers"], row["why"]
        compared += 1
    assert compared == 221


def test_every_shared_response_is_read_as_server_read_it():
    compared = 0
    for row in CASES["responses"]:
        request, expect = row["request"], row["expect"]
        read = provider_wire.read_pipeline if request["action"] == "pipeline_response" else provider_wire.read_text
        answer = read(request["format"], request["status"], request["body"].encode("utf-8"))
        for name, value in expect.items():
            assert answer.get(name) == value, (row["why"], name, answer)
        if expect["outcome"] == "http_error" and request["status"] >= 400:
            # The transport asks for the refusal alone, from the body it read.
            assert provider_wire.refusal(request["body"].encode("utf-8")) == expect["refusal"], row["why"]
        compared += 1
    assert compared == 97



def test_every_shared_chatgpt_row_goes_through_servers_transport_as_it_did():
    """The ChatGPT plan rows, read here as the transport reads them.

    The rows are chatgpt_provider.py at product fedfdbc7 with step 5's identifier
    checks; their failures and model lists follow step 5's one table and rule.
    """
    import base64

    from inku_server.chatgpt_provider import ResponseFailure, SSEDecoder, TextSSEDecoder, response_error
    from inku_server.chatgpt_store import ChatGPTError

    compared = Counter()
    for row in CASES["chatgpt"]:
        request, expect = row["request"], row["expect"]
        action = request["action"]
        if action in {"chatgpt_request", "chatgpt_vision_request"}:
            if expect["outcome"] == "refused":
                with pytest.raises(provider_wire.ProviderWireRefused, match=expect["detail"]):
                    provider_wire.chatgpt_vision_request(request["model"], system=request["system"], text=request["text"],
                                                         images=request["images"], answer_limit=request["answer_limit"])
            else:
                built = (provider_wire.chatgpt_request(request["model"], request["prompt"], request["answer_limit"])
                         if action == "chatgpt_request" else
                         provider_wire.chatgpt_vision_request(request["model"], system=request["system"], text=request["text"],
                                                              images=request["images"], answer_limit=request["answer_limit"]))
                assert (built["body"], built["canonical"]) == (expect["body"], expect["canonical"]), row["why"]
        elif action == "chatgpt_stream":
            decoder = (TextSSEDecoder if request["mode"] == "text" else SSEDecoder)(request["answer_limit"])
            decoder.feed(base64.b64decode(request["wire_base64"]))
            if expect["outcome"] == "answer":
                assert decoder.finish() == expect["text"], row["why"]
            elif expect["outcome"] == "malformed":
                with pytest.raises(ValueError if expect["kind"] == "utf8" else TypeError):
                    decoder.finish()
            else:
                with pytest.raises(ChatGPTError) as raised:
                    decoder.finish()
                assert (raised.value.code, raised.value.failure, raised.value.action) == (
                    expect["code"], expect["failure"], expect["action"]), row["why"]
                assert isinstance(raised.value, ResponseFailure) is bool(expect.get("reported")), row["why"]
            assert (decoder.completed, decoder.terminal) == (expect["completed"], expect["terminal"]), row["why"]
        elif action == "chatgpt_error":
            failure = response_error(request["value"], request["status"], request["request_id"])
            assert (failure.code, failure.failure, failure.action, failure.status, failure.request_id, failure.param) == (
                expect["code"], expect["failure"], expect["action"], expect["status"], expect["request_id"], expect["param"]), row["why"]
        elif action == "chatgpt_failure":
            # A code Server raises itself takes the same table.
            error = ChatGPTError(request["code"]) if "temporary" not in request else None
            named = provider_wire.chatgpt_failure(request["code"], request.get("temporary"))
            assert (named["failure"], named["action"]) == (expect["failure"], expect["action"]), row["why"]
            if error is not None:
                assert (error.failure, error.action) == (expect["failure"], expect["action"]), row["why"]
        else:
            assert {key: value for key, value in provider_wire.chatgpt_catalog(request["value"]).items()
                    if key != "schema"} == expect, row["why"]
        compared[action] += 1
    assert dict(compared) == {"chatgpt_request": 8, "chatgpt_vision_request": 8, "chatgpt_stream": 57,
                              "chatgpt_error": 9, "chatgpt_catalog": 5, "chatgpt_failure": 75}
