"""T-3: RAW trace option invariants (v1.93).

The model is mocked. These pin the trace contract: no-trace responses are
unchanged, trace is response-only (never persisted), and score/render_hash are
invariant to include_trace.

The trace recorded the Python layers -- Stage 1 raw text, the plugin-expanded
and Stage 1.5 DDL, the Stage 2 attempts, the Score before coercion -- and it
left with them (2026-09-14). The shared pipeline returns no trace, so the key
list and the compose shape are no longer pinned here; the invariants below
still hold, and hold for any trace the shared pipeline comes to return.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db, pipeline_product
from inku_server.api import app

client = TestClient(app)

DDL = "中心に黒い円を置く。"


@pytest.fixture
def auth():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"trace-{suffix}")
    user = db.add_user(
        username=f"trace-{suffix}",
        email=f"trace-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


class _Stage1:
    """Stage 1 answering one fixed drawing, so the shared pipeline needs no model."""

    def __init__(self, _options, **_kwargs):
        pass

    def __call__(self, action):
        assert action["tag"] == "generate_normalized_ddl", action["tag"]
        return {
            "tag": "normalized_ddl_generated",
            "identity": action["identity"],
            "response": json.dumps({"normalized_ddl": DDL}),
            "elapsed_ms": "3",
        }


def _mock_pipeline(monkeypatch):
    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", _Stage1)


# invariant 1: no include_trace -> response unchanged, no trace key
def test_paint_without_trace_omits_trace(monkeypatch, auth):
    _mock_pipeline(monkeypatch)
    r = client.post("/api/paint", json={"description": "一滴の墨"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert "trace" not in body
    assert body["ddl"] == DDL
    assert "<svg" in body["svg"]


# invariant 2: trace is response-only, never persisted to history/DB
def test_trace_not_persisted_to_history(monkeypatch, auth):
    _mock_pipeline(monkeypatch)
    r = client.post(
        "/api/paint",
        json={"description": "一滴の墨", "include_trace": True, "save_history": True},
        headers=auth,
    )
    assert r.status_code == 200
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
    base = {"description": "一滴の墨", "render_seed": 42, "composition_seed": 7}
    off = client.post("/api/paint", json=base, headers=auth).json()
    on = client.post("/api/paint", json={**base, "include_trace": True}, headers=auth).json()
    assert off["score"] == on["score"]
    assert off["ddl"] == on["ddl"]
    assert off["render_hash"] == on["render_hash"]
    assert "trace" not in off


# invariant 5: auth boundary identical to paint/compose
def test_trace_requires_auth():
    assert client.post("/api/paint", json={"description": "x", "include_trace": True}).status_code in (401, 403)
    assert client.post("/api/compose", json={"ddl": "x", "include_trace": True}).status_code in (401, 403)
