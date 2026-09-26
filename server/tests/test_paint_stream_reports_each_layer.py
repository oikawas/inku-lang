"""`/api/paint/stream` reports each layer as it settles (SPEC §12.10).

The shared pipeline is replaced by a service whose views advance the way a real
execution does; the router, the compatibility projection and the NDJSON framing
are the production code.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from inku_server import pipeline_compat
from inku_server.api_core.deps import _current_user
from inku_server.api_core.routers import render

DDL = "黒い円を中心に置く。"


def _view(*, busy: bool, sketch=None, document=None, score=None, phase="authoring_started", result=None) -> dict:
    return {
        "execution_id": "execution-1", "variation_id": "variation-1",
        "authority": {"revision": "1"}, "busy": busy, "sketch": sketch,
        "document": {"source": document} if document else None,
        "delivery": {"score": score} if score else None,
        "phase": {"tag": phase}, "result": result,
    }


def _running(attempt: int) -> dict:
    return {**_view(busy=True), "provider_attempt": {
        "action": "generate_normalized_ddl", "attempt": attempt, "max_attempts": 4,
        "delay_ms": "0", "timeout_ms": "300000", "deadline_at": 1,
    }}


class _Service:
    def __init__(self, views: list[dict], *, refuse: HTTPException | None = None) -> None:
        self.views = iter(views)
        self.refuse = refuse
        self.last: dict | None = None
        self.commands: list[dict] = []

    def start(self, owner, kind, text, **kwargs):
        if self.refuse is not None:
            raise self.refuse
        self.last = next(self.views)
        return self.last

    def get(self, owner, variation_id):
        self.last = next(self.views, self.last)
        return self.last

    def execution(self, owner, execution_id):
        return SimpleNamespace(context={"host_options": {"stage1_model": "model-1", "stage2_model": "model-2"}})

    def command(self, owner, execution_id, command):
        self.commands.append(command)
        if command == {"tag": "cancel"}:
            self.last = {**self.last, "busy": False}
            return self.last
        assert command == {"tag": "perform"}
        self.last = {**self.last, "result": {"ddl": DDL, "svg": "<svg/>", "score": {"instructions": [{}]}}}
        return self.last


def _client(monkeypatch, service: _Service) -> TestClient:
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    app = FastAPI()
    app.include_router(render.router)
    app.dependency_overrides[_current_user] = lambda: {"id": "author-1"}
    return TestClient(app)


def _events(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line]


def test_the_stream_names_each_layer_in_order_before_the_drawing(monkeypatch) -> None:
    service = _Service([
        _view(busy=True, sketch={"state": "pending"}),
        _view(busy=True, sketch={"state": "supplemented", "text": "春の光"}),
        _view(busy=True, sketch={"state": "supplemented", "text": "春の光"}, document=DDL),
        _view(busy=False, sketch={"state": "supplemented", "text": "春の光"}, document=DDL,
              score={"instructions": [{}, {}]}, phase="score_ready"),
    ])
    response = _client(monkeypatch, service).post("/api/paint/stream", json={"description": "春の円"})
    assert response.status_code == 200
    events = _events(response)
    assert [event["event"] for event in events] == ["sketch", "stage1", "score", "done"]
    assert events[0]["sketch_state"] == "supplemented"
    assert events[1]["ddl"] == DDL
    assert events[1]["stage1_model"] == "model-1"
    assert events[2]["instruction_count"] == 2
    assert events[3]["svg"] == "<svg/>"
    assert events[3]["pipeline_variation_id"] == "variation-1"


def test_a_run_without_a_sketch_does_not_name_one(monkeypatch) -> None:
    service = _Service([
        _view(busy=True),
        _view(busy=False, document=DDL, score={"instructions": [{}]}, phase="score_ready"),
    ])
    response = _client(monkeypatch, service).post("/api/paint/stream", json={"description": "円"})
    assert [event["event"] for event in _events(response)] == ["stage1", "score", "done"]


def test_a_retry_is_reported_as_its_own_attempt(monkeypatch) -> None:
    # W4: a first attempt that timed out read as a slow answer.
    service = _Service([
        _running(1), _running(1), _running(2),
        _view(busy=False, document=DDL, score={"instructions": [{}]}, phase="score_ready"),
    ])
    events = _events(_client(monkeypatch, service).post("/api/paint/stream", json={"description": "円"}))
    assert [event["event"] for event in events] == ["attempt", "attempt", "stage1", "score", "attempt", "done"]
    assert [event["provider_attempt"] for event in events if event["event"] == "attempt"] == [
        {"action": "generate_normalized_ddl", "attempt": 1, "max_attempts": 4},
        {"action": "generate_normalized_ddl", "attempt": 2, "max_attempts": 4},
        None,
    ]


def test_a_reader_that_leaves_cancels_the_run(monkeypatch) -> None:
    # A stopped batch or a closed page left the run holding a pipeline worker
    # and calling the model through every retry.
    service = _Service([_running(1), _running(1)])
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    events = pipeline_compat.paint_events("author-1", {"description": "円"}, None)
    assert next(events)["event"] == "attempt"
    events.close()
    assert service.commands == [{"tag": "cancel"}]


def test_a_long_wait_still_writes_lines(monkeypatch) -> None:
    # A proxy drops a body that stays silent (Node's fetch after 300 s, one
    # Stage 1 attempt's limit), and a reader that left went unnoticed until
    # the next line.
    monkeypatch.setattr(pipeline_compat, "_WAIT_EVENT_SECONDS", 0)
    service = _Service([
        _view(busy=True), _view(busy=True),
        _view(busy=False, document=DDL, score={"instructions": [{}]}, phase="score_ready"),
    ])
    response = _client(monkeypatch, service).post("/api/paint/stream", json={"description": "円"})
    assert [event["event"] for event in _events(response)] == ["wait", "wait", "stage1", "score", "done"]


def test_a_refusal_before_any_layer_keeps_its_http_status(monkeypatch) -> None:
    service = _Service([], refuse=HTTPException(400, "description is only labels"))
    response = _client(monkeypatch, service).post("/api/paint/stream", json={"description": "01. [出典]"})
    assert response.status_code == 400


def test_a_patch_to_approve_after_the_first_layer_arrives_as_an_error_event(monkeypatch) -> None:
    service = _Service([
        _view(busy=True),
        _view(busy=False, document=DDL, phase="awaiting_patch_approval"),
    ])
    response = _client(monkeypatch, service).post("/api/paint/stream", json={"description": "円"})
    assert response.status_code == 200
    events = _events(response)
    assert [event["event"] for event in events] == ["stage1", "error"]
    assert events[1]["status"] == 409
    assert events[1]["detail"]["code"] == "pipeline_patch_approval_required"
