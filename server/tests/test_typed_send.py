"""What the Server keeps of the AI refinement's chunk moves (removed on 2026-11-13) for the thesis-handle work.

One failure each: a typed send that shares an execution key across callers, so that one owner's logout
cancels the next send too; and a composition record read from a work that keeps none.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from inku_server import chatgpt_runtime, pipeline_runtime
from inku_server.composition_record import composition_of
from inku_server.typed_send import SendStopped, send_typed

REQUEST = {"system": "s", "text": "t", "response_schema": {}}


def test_a_send_uses_the_callers_key_and_an_owner_logout_does_not_poison_the_next_send(monkeypatch):
    seen = []

    def provider(owner, context, _images):
        seen.append((owner, context["execution_id"]))
        event = chatgpt_runtime.execution_cancel(owner, context["execution_id"])
        return lambda action: ({"tag": "normalized_ddl_generated", "response": "ok"} if not event.is_set()
                               else {"tag": "provider_failed", "failure": "chatgpt_cancelled"})

    monkeypatch.setattr(pipeline_runtime, "get_service", lambda: SimpleNamespace(provider_with_context=provider))
    context = {"host_options": {"chatgpt_profile": "profile"}}

    def send(key):
        return send_typed("owner", context, REQUEST, execution_id=key, prompt_id="inku.test.v1",
                          action_id=f"{key}-1", language="ja")

    try:
        assert send("thesis:first") == ("ok", None)
        chatgpt_runtime.cancel_owner("owner")
        assert chatgpt_runtime.execution_cancel(*seen[0]).is_set()
        assert send("thesis:second") == ("ok", None)
        assert seen == [("owner", "thesis:first"), ("owner", "thesis:second")]
        assert ("owner", "") not in chatgpt_runtime._cancels
    finally:
        for owner, key in seen:
            chatgpt_runtime.retire_execution(owner, key)


def test_a_send_is_sent_as_stage_one_with_its_prompt_named_and_stops_when_asked(monkeypatch):
    actions = []
    stop = threading.Event()

    def provider(_owner, _context, images):
        assert images is None

        def perform(action):
            actions.append(action)
            stop.set()
            return {"tag": "normalized_ddl_generated", "response": "late"}
        return perform

    monkeypatch.setattr(pipeline_runtime, "get_service", lambda: SimpleNamespace(provider_with_context=provider))
    try:
        with pytest.raises(SendStopped):
            send_typed("owner", {}, REQUEST, execution_id="thesis:stop", prompt_id="inku.test.v1",
                       action_id="thesis-1", language="en", stop=stop)
    finally:
        chatgpt_runtime.retire_execution("owner", "thesis:stop")
    (action,) = actions
    assert action["tag"] == "generate_normalized_ddl"
    prompt = action["payload"]["prompt"]
    assert (prompt["prompt_id"], prompt["instruction_language"]) == ("inku.test.v1", "en")
    assert prompt["prompt_digest"] == f"sha256:{action['identity']['request_digest']}"


def test_the_composition_record_reads_only_a_work_that_keeps_one():
    kept = {"description_ddl": {"composition": {"things": ["月", None], "answer": {"things": [{"name": "月"}]}}}}
    assert composition_of(kept) == {"owners": ["月", None], "things": [{"name": "月"}]}
    assert composition_of({"description_ddl": {"composition": {"things": ["月"]}}}) is None
    assert composition_of({"description_ddl": None}) is None
    assert composition_of({}) is None
