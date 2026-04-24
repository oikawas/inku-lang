"""API endpoint tests.

Stage 2 composer を monkeypatch でバイパスし、FastAPI のスキーマ/配線のみ検証。
実 API 呼び出しは test_composer で gated 実行。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from inku_server import api as api_module
from inku_server.api import app
from inku_server.schema import Score

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_compose_happy_path(monkeypatch):
    fake_score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2}
            ]
        }
    )
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/compose", json={"ddl": "中心に円"})
    assert r.status_code == 200
    data = r.json()
    assert data["score"]["instructions"][0]["primitive"] == "circle"
    assert "<svg" in data["svg"]
    assert "<circle" in data["svg"]


def test_compose_empty_ddl_rejected():
    r = client.post("/api/compose", json={"ddl": ""})
    assert r.status_code == 422


def test_compose_composer_failure_returns_502(monkeypatch):
    def boom(ddl: str, model=None):
        raise RuntimeError("haiku unavailable")

    monkeypatch.setattr(api_module, "compose", boom)
    r = client.post("/api/compose", json={"ddl": "中心に円"})
    assert r.status_code == 502
    assert "haiku unavailable" in r.json()["detail"]


def test_interpret_happy_path(monkeypatch):
    monkeypatch.setattr(api_module, "interpret_detail", lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None))
    r = client.post("/api/interpret", json={"text": "一滴の墨"})
    assert r.status_code == 200
    assert r.json() == {"ddl": "中心に黒い円を置く。", "thinking": None}


def test_interpret_empty_rejected():
    r = client.post("/api/interpret", json={"text": ""})
    assert r.status_code == 422


def test_paint_pipeline(monkeypatch):
    monkeypatch.setattr(api_module, "interpret_detail", lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None))
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/paint", json={"text": "一滴の墨"})
    assert r.status_code == 200
    data = r.json()
    assert data["text"] == "一滴の墨"
    assert data["ddl"] == "中心に黒い円を置く。"
    assert data["score"]["instructions"][0]["primitive"] == "circle"
    assert "<svg" in data["svg"]


def test_cors_allows_localhost(monkeypatch):
    fake_score = Score(instructions=[])
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake_score)

    r = client.post(
        "/api/compose",
        json={"ddl": "something"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
