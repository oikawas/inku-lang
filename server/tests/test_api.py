"""API endpoint tests.

Stage 2 composer を monkeypatch でバイパスし、FastAPI のスキーマ/配線のみ検証。
実 API 呼び出しは test_composer で gated 実行。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from inku_server import db
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


def test_settings_status_is_admin_only():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"settings-{suffix}")
    admin = db.add_user(
        username=f"settings-admin-{suffix}",
        email=f"settings-admin-{suffix}@example.test",
        password="password-123",
        role="admin",
        group_id=group["id"],
    )
    user = db.add_user(
        username=f"settings-user-{suffix}",
        email=f"settings-user-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )

    assert client.get("/api/settings/status").status_code == 401

    user_token = client.post(
        "/api/auth/login",
        json={"username": user["username"], "password": "password-123"},
    ).json()["token"]
    assert client.get("/api/settings/status", headers={"Authorization": f"Bearer {user_token}"}).status_code == 403

    admin_token = client.post(
        "/api/auth/login",
        json={"username": admin["username"], "password": "password-123"},
    ).json()["token"]
    r = client.get("/api/settings/status", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["database"]["backend"]
    assert data["database"]["runtime_editable"] is False
    assert "INKU_DB_URL" in data["database"]["note"]
    assert data["plugins"]["enabled"] is False
    assert data["plugins"]["runtime_editable"] is False
    assert data["plugins"]["loaded"] == []

    db.delete_user(admin["id"])
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_user_management_crud():
    suffix = uuid.uuid4().hex[:8]
    admin_group = db.add_user_group(f"admins-{suffix}")
    admin = db.add_user(
        username=f"admin-{suffix}",
        email=f"admin-{suffix}@example.test",
        password="password-123",
        role="admin",
        group_id=admin_group["id"],
    )
    login_r = client.post(
        "/api/auth/login",
        json={"username": admin["username"], "password": "password-123"},
    )
    assert login_r.status_code == 200
    token = login_r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    group_r = client.post("/api/user-groups", json={"name": f"class-{suffix}"}, headers=headers)
    assert group_r.status_code == 200
    group = group_r.json()

    user_r = client.post(
        "/api/users",
        json={
            "username": f"student-{suffix}",
            "email": f"student-{suffix}@example.test",
            "password": "password-123",
            "role": "user",
            "group_id": group["id"],
        },
        headers=headers,
    )
    assert user_r.status_code == 200
    user = user_r.json()
    assert user["group_id"] == group["id"]
    assert user["role"] == "user"
    assert "password" not in user
    assert "password_hash" not in user

    blocked = client.delete(f"/api/user-groups/{group['id']}", headers=headers)
    assert blocked.status_code == 409

    patch_r = client.patch(
        f"/api/users/{user['id']}",
        json={"role": "group_lead", "password": "password-456"},
        headers=headers,
    )
    assert patch_r.status_code == 200
    assert patch_r.json()["role"] == "group_lead"

    lead_login_r = client.post(
        "/api/auth/login",
        json={"username": user["username"], "password": "password-456"},
    )
    assert lead_login_r.status_code == 200
    lead_headers = {"Authorization": f"Bearer {lead_login_r.json()['token']}"}

    assert client.post("/api/user-groups", json={"name": f"blocked-{suffix}"}, headers=lead_headers).status_code == 403
    blocked_admin_r = client.post(
        "/api/users",
        json={
            "username": f"blocked-admin-{suffix}",
            "email": f"blocked-admin-{suffix}@example.test",
            "password": "password-123",
            "role": "admin",
            "group_id": group["id"],
        },
        headers=lead_headers,
    )
    assert blocked_admin_r.status_code == 403

    lead_student_r = client.post(
        "/api/users",
        json={
            "username": f"lead-student-{suffix}",
            "email": f"lead-student-{suffix}@example.test",
            "password": "password-123",
            "role": "user",
            "group_id": group["id"],
        },
        headers=lead_headers,
    )
    assert lead_student_r.status_code == 200
    assert client.delete(f"/api/users/{lead_student_r.json()['id']}", headers=lead_headers).status_code == 200

    assert client.delete(f"/api/users/{user['id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/user-groups/{group['id']}", headers=headers).status_code == 200
    db.delete_user(admin["id"])
    db.delete_user_group(admin_group["id"])


def test_history_is_scoped_to_authenticated_user():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"history-{suffix}")
    user_a = db.add_user(
        username=f"history-a-{suffix}",
        email=f"history-a-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    user_b = db.add_user(
        username=f"history-b-{suffix}",
        email=f"history-b-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )

    unauthenticated = client.get("/api/history")
    assert unauthenticated.status_code == 401

    token_a = client.post(
        "/api/auth/login",
        json={"username": user_a["username"], "password": "password-123"},
    ).json()["token"]
    token_b = client.post(
        "/api/auth/login",
        json={"username": user_b["username"], "password": "password-123"},
    ).json()["token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    payload = {
        "input": "user scoped drawing",
        "ddl": "中心に円",
        "score": {"instructions": []},
        "svg": "<svg></svg>",
        "at": 1_700_000_000_000,
    }
    post_a = client.post("/api/history", json=payload, headers=headers_a)
    assert post_a.status_code == 200
    item_a = post_a.json()

    list_a = client.get("/api/history", headers=headers_a)
    assert list_a.status_code == 200
    assert list_a.json()["total"] == 1
    assert list_a.json()["items"][0]["id"] == item_a["id"]

    list_b = client.get("/api/history", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json()["total"] == 0

    trash_b = client.post("/api/history/trash", json={"ids": [item_a["id"]]}, headers=headers_b)
    assert trash_b.status_code == 200
    assert trash_b.json()["count"] == 0

    trash_a = client.post("/api/history/trash", json={"ids": [item_a["id"]]}, headers=headers_a)
    assert trash_a.status_code == 200
    assert trash_a.json()["count"] == 1

    db.delete_items(user_a["id"], [item_a["id"]])
    db.delete_user(user_a["id"])
    db.delete_user(user_b["id"])
    db.delete_user_group(group["id"])
