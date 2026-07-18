"""T-3: RAW trace option invariants (v1.93).

The LLM is mocked. These pin the trace contract: no-trace responses are
unchanged, trace is response-only (never persisted), and score/render_hash are
invariant to include_trace.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import api as api_module
from inku_server import db
from inku_server.api import app
from inku_server.schema import Score

client = TestClient(app)

_FAKE_SCORE = {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}


@pytest.fixture
def auth():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"trace-{suffix}")
    user = db.add_user(
        username=f"trace-{suffix}",
        email=f"trace-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


def _mock_pipeline(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None),
    )
    fake = Score.model_validate(_FAKE_SCORE)
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake)


# invariant 1: no include_trace -> response unchanged, no trace key
def test_paint_without_trace_omits_trace(monkeypatch, auth):
    _mock_pipeline(monkeypatch)
    r = client.post("/api/paint", json={"text": "一滴の墨"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert "trace" not in body
    assert body["score"]["instructions"][0]["primitive"] == "circle"
    assert "<svg" in body["svg"]


def test_paint_with_trace_has_all_keys(monkeypatch, auth):
    _mock_pipeline(monkeypatch)
    r = client.post("/api/paint", json={"text": "一滴の墨", "include_trace": True}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    trace = body["trace"]
    for key in (
        "stage1_raw",
        "stage1_ddl",
        "plugin_expanded_ddl",
        "stage15_ddl",
        "stage2_raw_attempts",
        "score_pre_coerce",
        "coerce_branch_counts",
        "plugin_provenance",
        "plugin_warnings",
    ):
        assert key in trace, key
    # stage15 is the Stage 2 input, equal to the response ddl
    assert trace["stage15_ddl"] == body["ddl"]
    attempts = trace["stage2_raw_attempts"]
    assert isinstance(attempts, list) and len(attempts) == 1  # normal path: one attempt
    assert set(attempts[0]) >= {"attempt", "raw_text", "parse_ok", "fallback"}
    assert attempts[0]["fallback"] is False
    assert trace["score_pre_coerce"]["instructions"][0]["primitive"] == "circle"


def test_compose_with_trace_has_no_stage1(monkeypatch, auth):
    fake = Score.model_validate(_FAKE_SCORE)
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake)
    r = client.post("/api/compose", json={"ddl": "中心に円", "include_trace": True}, headers=auth)
    assert r.status_code == 200
    trace = r.json()["trace"]
    assert "stage1_raw" not in trace and "stage1_ddl" not in trace
    assert "stage15_ddl" in trace
    assert len(trace["stage2_raw_attempts"]) == 1


# invariant 2: trace is response-only, never persisted to history/DB
def test_trace_not_persisted_to_history(monkeypatch, auth):
    _mock_pipeline(monkeypatch)
    r = client.post(
        "/api/paint",
        json={"text": "一滴の墨", "include_trace": True, "save_history": True},
        headers=auth,
    )
    assert r.status_code == 200
    assert "trace" in r.json()
    hist = client.get("/api/history", headers=auth)
    assert hist.status_code == 200
    # trace-unique keys must never appear in persisted history.
    persisted = json.dumps(hist.json())
    assert "stage2_raw_attempts" not in persisted
    assert "score_pre_coerce" not in persisted
    for item in hist.json().get("items", []):
        assert "trace" not in item


# invariant 3 (and 4): score & render_hash invariant to include_trace
def test_score_and_render_hash_invariant_to_trace(monkeypatch, auth):
    _mock_pipeline(monkeypatch)
    base = {"text": "一滴の墨", "render_seed": 42}
    off = client.post("/api/paint", json=base, headers=auth).json()
    on = client.post("/api/paint", json={**base, "include_trace": True}, headers=auth).json()
    assert off["score"] == on["score"]
    assert off["ddl"] == on["ddl"]
    assert off["render_hash"] == on["render_hash"]
    assert "trace" not in off and "trace" in on


# invariant 5: auth boundary identical to paint/compose
def test_trace_requires_auth():
    assert client.post("/api/paint", json={"text": "x", "include_trace": True}).status_code in (401, 403)
    assert client.post("/api/compose", json={"ddl": "x", "include_trace": True}).status_code in (401, 403)
