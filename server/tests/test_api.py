"""API endpoint tests.

Stage 2 composer を monkeypatch でバイパスし、FastAPI のスキーマ/配線のみ検証。
実 API 呼び出しは test_composer で gated 実行。
"""

from __future__ import annotations

import builtins
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server import api as api_module
from inku_server.api import app
from inku_server.schema import Score

client = TestClient(app)


def _auth_headers(user: dict) -> tuple[dict[str, str], str]:
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}, token


@pytest.fixture
def auth_context():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"api-auth-{suffix}")
    user = db.add_user(
        username=f"api-auth-{suffix}",
        email=f"api-auth-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    headers, token = _auth_headers(user)
    yield headers, user, group
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_generation_apis_require_auth():
    assert client.post("/api/compose", json={"ddl": "中心に円"}).status_code == 401
    assert client.post("/api/interpret", json={"text": "一滴の墨"}).status_code == 401
    assert client.post("/api/paint", json={"text": "一滴の墨"}).status_code == 401


def test_login_uses_httponly_session_cookie():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"cookie-auth-{suffix}")
    user = db.add_user(
        username=f"cookie-auth-{suffix}",
        email=f"cookie-auth-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    local_client = TestClient(app)

    login_r = local_client.post(
        "/api/auth/login",
        json={"username": user["username"], "password": "password-123"},
    )
    assert login_r.status_code == 200
    assert "token" not in login_r.json()
    set_cookie = login_r.headers["set-cookie"]
    assert "inku_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    me_r = local_client.get("/api/auth/me")
    assert me_r.status_code == 200
    assert me_r.json()["username"] == user["username"]

    logout_r = local_client.post("/api/auth/logout")
    assert logout_r.status_code == 200
    assert "inku_session=" in logout_r.headers["set-cookie"]
    assert local_client.get("/api/auth/me").status_code == 401

    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_compose_happy_path(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2}
            ]
        }
    )
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/compose", json={"ddl": "中心に円"}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["score"]["instructions"][0]["primitive"] == "circle"
    assert "<svg" in data["svg"]
    assert "<circle" in data["svg"]


def test_compose_empty_ddl_rejected(auth_context):
    headers, _, _ = auth_context
    r = client.post("/api/compose", json={"ddl": ""}, headers=headers)
    assert r.status_code == 422


def test_compose_composer_failure_returns_502(monkeypatch, auth_context):
    headers, _, _ = auth_context
    def boom(ddl: str, model=None):
        raise RuntimeError("haiku unavailable")

    monkeypatch.setattr(api_module, "compose", boom)
    r = client.post("/api/compose", json={"ddl": "中心に円"}, headers=headers)
    assert r.status_code == 502
    assert "haiku unavailable" in r.json()["detail"]


def test_interpret_happy_path(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(api_module, "interpret_detail", lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None))
    r = client.post("/api/interpret", json={"text": "一滴の墨"}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"ddl": "中心に黒い円を置く。", "thinking": None}


def test_interpret_empty_rejected(auth_context):
    headers, _, _ = auth_context
    r = client.post("/api/interpret", json={"text": ""}, headers=headers)
    assert r.status_code == 422


def test_paint_pipeline(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(api_module, "interpret_detail", lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None))
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/paint", json={"text": "一滴の墨"}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["text"] == "一滴の墨"
    assert data["ddl"] == "中心に黒い円を置く。"
    assert data["score"]["instructions"][0]["primitive"] == "circle"
    assert "<svg" in data["svg"]


def test_paint_can_save_server_generated_history(monkeypatch, auth_context):
    headers, user, _ = auth_context
    monkeypatch.setattr(api_module, "interpret_detail", lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None))
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake_score)

    r = client.post(
        "/api/paint",
        json={
            "text": "一滴の墨\n\n感情: 静か",
            "original_text": "一滴の墨",
            "save_history": True,
            "history_input": "一滴の墨",
            "history_at": 1_700_000_000_000,
            "catalog_id": "sample",
        },
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["history_id"]
    assert data["history_at"] == 1_700_000_000_000

    history = client.get("/api/history", headers=headers).json()
    assert history["total"] == 1
    item = history["items"][0]
    assert item["id"] == data["history_id"]
    assert item["input"] == "一滴の墨"
    assert item["catalog_id"] == "sample"
    assert item["svg"] == data["svg"]

    db.delete_items(user["id"], [data["history_id"]])


def test_cors_allows_localhost(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score(instructions=[])
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake_score)

    r = client.post(
        "/api/compose",
        json={"ddl": "something"},
        headers={**headers, "Origin": "http://localhost:5173"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_save_output_files_logs_missing_png_dependency(tmp_path, monkeypatch, caplog):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cairosvg":
            raise ImportError("missing cairosvg")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    caplog.set_level(logging.WARNING, logger=api_module.__name__)

    prefix = tmp_path / "out" / "sample"
    api_module._save_output_files(
        prefix,
        "input text",
        "normalized ddl",
        {"instructions": []},
        "<svg></svg>",
    )

    assert (tmp_path / "out" / "sample_instruction.txt").read_text(encoding="utf-8") == "input text"
    assert (tmp_path / "out" / "sample_normalized.ddl").read_text(encoding="utf-8") == "normalized ddl"
    assert (tmp_path / "out" / "sample_score.json").exists()
    assert (tmp_path / "out" / "sample_output.svg").read_text(encoding="utf-8") == "<svg></svg>"
    assert not (tmp_path / "out" / "sample_output.png").exists()
    assert "skipped PNG output" in caplog.text


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

    user_headers, user_token = _auth_headers(user)
    assert client.get("/api/settings/status", headers=user_headers).status_code == 403

    admin_headers, admin_token = _auth_headers(admin)
    r = client.get("/api/settings/status", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["database"]["backend"]
    assert data["database"]["runtime_editable"] is False
    assert "INKU_DB_URL" in data["database"]["note"]
    assert data["plugins"]["enabled"] is False
    assert data["plugins"]["runtime_editable"] is False
    assert data["plugins"]["loaded"] == []

    db.delete_session(admin_token)
    db.delete_session(user_token)
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
    headers, token = _auth_headers(admin)

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

    lead_headers, lead_token = _auth_headers(user)

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

    db.delete_session(lead_token)
    assert client.delete(f"/api/users/{user['id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/user-groups/{group['id']}", headers=headers).status_code == 200
    db.delete_session(token)
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

    headers_a, token_a = _auth_headers(user_a)
    headers_b, token_b = _auth_headers(user_b)

    payload = {
        "input": "user scoped drawing",
        "ddl": "中心に円",
        "score": {"instructions": []},
        "svg": "<svg><script>alert(1)</script></svg>",
        "at": 1_700_000_000_000,
    }
    post_a = client.post("/api/history", json=payload, headers=headers_a)
    assert post_a.status_code == 200
    item_a = post_a.json()
    assert item_a["svg"] != payload["svg"]
    assert "<script" not in item_a["svg"]
    assert "<svg" in item_a["svg"]
    post_a_second = client.post(
        "/api/history",
        json={**payload, "input": "blue crayon search target", "ddl": "青い線", "at": payload["at"] + 1},
        headers=headers_a,
    )
    assert post_a_second.status_code == 200
    item_a_second = post_a_second.json()

    list_a = client.get("/api/history", headers=headers_a)
    assert list_a.status_code == 200
    assert list_a.json()["total"] == 2
    assert list_a.json()["items"][0]["id"] == item_a_second["id"]

    page_a = client.get("/api/history?offset=1&limit=1", headers=headers_a)
    assert page_a.status_code == 200
    assert page_a.json()["total"] == 2
    assert page_a.json()["items"][0]["id"] == item_a["id"]

    search_a = client.get("/api/history?q=crayon", headers=headers_a)
    assert search_a.status_code == 200
    assert search_a.json()["total"] == 1
    assert search_a.json()["items"][0]["id"] == item_a_second["id"]

    list_b = client.get("/api/history", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json()["total"] == 0

    trash_b = client.post("/api/history/trash", json={"ids": [item_a["id"]]}, headers=headers_b)
    assert trash_b.status_code == 200
    assert trash_b.json()["count"] == 0

    trash_a = client.post("/api/history/trash", json={"ids": [item_a["id"]]}, headers=headers_a)
    assert trash_a.status_code == 200
    assert trash_a.json()["count"] == 1

    db.delete_items(user_a["id"], [item_a["id"], item_a_second["id"]])
    db.delete_session(token_a)
    db.delete_session(token_b)
    db.delete_user(user_a["id"])
    db.delete_user(user_b["id"])
    db.delete_user_group(group["id"])
