"""API endpoint tests.

Stage 2 composer を monkeypatch でバイパスし、FastAPI のスキーマ/配線のみ検証。
実 API 呼び出しは test_composer で gated 実行。
"""

from __future__ import annotations

import builtins
import logging
import sys
import time
import types
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from inku_server import db
from inku_server import api as api_module
from inku_server.api import app
from inku_server.schema import Score

client = TestClient(app)

EXPANSION_MARKERS = (
    "右半分の斜めの帯",
    "左下から右上へ",
    "波打つ軌跡に沿って",
    "左下の焦点から三つ",
    "黄金比の位置",
    "三分割の交点",
    "白銀比の位置",
    "正五角形の頂点",
    "対位法の反行",
    "倍音列",
    "輪唱のずれ",
    "一点透視法",
    "遠近法の奥行き",
    "素描の下線",
    "点描",
    "油絵の厚塗り",
    "水彩",
    "パッチワーク",
    "フレスコの下地",
    "水墨の濃淡",
)


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


def test_expired_session_is_rejected_and_deleted(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"expired-session-{suffix}")
    user = db.add_user(
        username=f"expired-session-{suffix}",
        email=f"expired-session-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    monkeypatch.setattr(db, "_SESSION_MAX_AGE_SECONDS", 1)
    token = db.create_session(user["id"])
    with db.SessionLocal() as session:
        row = session.get(db.UserSessionRow, db._hash_token(token))
        assert row is not None
        row.at = db._now_ms() - 2_000
        session.commit()

    assert db.get_session_user(token) is None
    with db.SessionLocal() as session:
        assert session.get(db.UserSessionRow, db._hash_token(token)) is None

    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_create_session_prunes_expired_sessions(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"session-prune-{suffix}")
    user = db.add_user(
        username=f"session-prune-{suffix}",
        email=f"session-prune-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    monkeypatch.setattr(db, "_SESSION_MAX_AGE_SECONDS", 1)
    old_token = db.create_session(user["id"])
    with db.SessionLocal() as session:
        row = session.get(db.UserSessionRow, db._hash_token(old_token))
        assert row is not None
        row.at = db._now_ms() - 2_000
        session.commit()

    new_token = db.create_session(user["id"])
    with db.SessionLocal() as session:
        assert session.get(db.UserSessionRow, db._hash_token(old_token)) is None
        assert session.get(db.UserSessionRow, db._hash_token(new_token)) is not None

    db.delete_session(new_token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_bootstrap_admin_password_requires_explicit_env(monkeypatch):
    monkeypatch.delenv("INKU_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN", raising=False)
    assert db._bootstrap_admin_password() is None


def test_bootstrap_admin_password_rejects_short_env(monkeypatch):
    monkeypatch.setenv("INKU_BOOTSTRAP_ADMIN_PASSWORD", "short")
    monkeypatch.delenv("INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN", raising=False)
    with pytest.raises(ValueError, match="at least 8 characters"):
        db._bootstrap_admin_password()


def test_bootstrap_admin_password_allows_explicit_env(monkeypatch):
    monkeypatch.setenv("INKU_BOOTSTRAP_ADMIN_PASSWORD", "secure-password")
    monkeypatch.delenv("INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN", raising=False)
    assert db._bootstrap_admin_password() == "secure-password"


def test_bootstrap_admin_password_allows_explicit_insecure_dev_flag(monkeypatch):
    monkeypatch.delenv("INKU_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN", "1")
    assert db._bootstrap_admin_password() == "inku-admin"


def test_api_main_disables_reload_by_default(monkeypatch):
    calls = []
    fake_uvicorn = types.SimpleNamespace(run=lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.delenv("INKU_SERVER_RELOAD", raising=False)
    monkeypatch.delenv("INKU_SERVER_HOST", raising=False)
    monkeypatch.delenv("INKU_SERVER_PORT", raising=False)

    api_module.main()

    assert calls == [(("inku_server.api:app",), {"host": "127.0.0.1", "port": 8100, "reload": False})]


def test_api_main_enables_reload_only_when_requested(monkeypatch):
    calls = []
    fake_uvicorn = types.SimpleNamespace(run=lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setenv("INKU_SERVER_RELOAD", "1")
    monkeypatch.setenv("INKU_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("INKU_SERVER_PORT", "18100")

    api_module.main()

    assert calls == [(("inku_server.api:app",), {"host": "0.0.0.0", "port": 18100, "reload": True})]


def test_migrate_columns_adds_missing_history_columns(tmp_path, monkeypatch):
    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with legacy_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE history (
                id VARCHAR PRIMARY KEY,
                at BIGINT NOT NULL,
                input TEXT NOT NULL DEFAULT '',
                ddl TEXT,
                score TEXT NOT NULL DEFAULT '{}',
                svg TEXT NOT NULL DEFAULT '',
                output_path TEXT,
                elapsed_ms INTEGER NOT NULL DEFAULT 0,
                stage1_model VARCHAR,
                stage2_model VARCHAR,
                tokens_in INTEGER,
                tokens_out INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE user_accounts (
                id VARCHAR PRIMARY KEY,
                username VARCHAR NOT NULL,
                email VARCHAR NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR NOT NULL,
                group_id VARCHAR,
                at BIGINT NOT NULL
            )
        """))

    monkeypatch.setattr(db, "engine", legacy_engine)
    db._migrate_columns()
    db._migrate_columns()

    columns = {col["name"] for col in inspect(legacy_engine).get_columns("history")}
    assert {"user_id", "catalog_id", "trashed", "starred"} <= columns
    user_columns = {col["name"] for col in inspect(legacy_engine).get_columns("user_accounts")}
    assert {"ui_theme", "batch_prompt_history", "demo_settings"} <= user_columns
    indexes = {idx["name"] for idx in inspect(legacy_engine).get_indexes("history")}
    assert {"ix_history_user_id", "ix_history_user_trashed_at", "ix_history_user_starred_trashed_at"} <= indexes
    with legacy_engine.connect() as conn:
        sqlite_objects = {
            row[0]
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"))
        }
    assert "history_fts" in sqlite_objects
    assert {"history_fts_ai", "history_fts_ad", "history_fts_au"} <= sqlite_objects


def test_migrate_columns_raises_when_history_inspection_fails(monkeypatch):
    class BadInspector:
        def get_columns(self, table_name: str):
            raise RuntimeError(f"cannot inspect {table_name}")

    monkeypatch.setattr(db, "inspect", lambda conn: BadInspector())
    with pytest.raises(RuntimeError, match="failed to inspect history table columns"):
        db._migrate_columns()


def test_current_user_theme_can_be_updated(auth_context):
    headers, _, _ = auth_context

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["ui_theme"] == "light"

    updated = client.patch("/api/auth/me/settings", headers=headers, json={"ui_theme": "dark"})
    assert updated.status_code == 200
    assert updated.json()["ui_theme"] == "dark"

    me_again = client.get("/api/auth/me", headers=headers)
    assert me_again.status_code == 200
    assert me_again.json()["ui_theme"] == "dark"

    invalid = client.patch("/api/auth/me/settings", headers=headers, json={"ui_theme": "sepia"})
    assert invalid.status_code == 400


def test_current_user_profile_can_be_updated(auth_context):
    headers, user, _ = auth_context
    next_email = f"profile-{uuid.uuid4().hex[:8]}@example.test"

    email_r = client.patch("/api/auth/me/profile", headers=headers, json={"email": next_email})
    assert email_r.status_code == 200
    assert email_r.json()["email"] == next_email

    missing_current_r = client.patch(
        "/api/auth/me/profile",
        headers=headers,
        json={"password": "password-456"},
    )
    assert missing_current_r.status_code == 400

    wrong_current_r = client.patch(
        "/api/auth/me/profile",
        headers=headers,
        json={"password": "password-456", "current_password": "wrong-password"},
    )
    assert wrong_current_r.status_code == 400

    password_r = client.patch(
        "/api/auth/me/profile",
        headers=headers,
        json={"password": "password-456", "current_password": "password-123"},
    )
    assert password_r.status_code == 200

    login_old = client.post("/api/auth/login", json={"username": user["username"], "password": "password-123"})
    assert login_old.status_code == 401
    login_new = client.post("/api/auth/login", json={"username": user["username"], "password": "password-456"})
    assert login_new.status_code == 200


def test_current_user_batch_prompt_history_is_persisted(auth_context):
    headers, user, group = auth_context
    other_user = db.add_user(
        username=f"api-batch-history-{uuid.uuid4().hex[:8]}",
        email=f"api-batch-history-{uuid.uuid4().hex[:8]}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    other_headers, other_token = _auth_headers(other_user)
    try:
        empty = client.get("/api/auth/me/batch-prompt-history", headers=headers)
        assert empty.status_code == 200
        assert empty.json() == {"items": []}

        body = {"items": ["  one\n two  ", "one\n two", "", "three"]}
        updated = client.put("/api/auth/me/batch-prompt-history", headers=headers, json=body)
        assert updated.status_code == 200
        assert updated.json() == {"items": ["one\n two", "three"]}

        persisted = client.get("/api/auth/me/batch-prompt-history", headers=headers)
        assert persisted.status_code == 200
        assert persisted.json() == {"items": ["one\n two", "three"]}

        isolated = client.get("/api/auth/me/batch-prompt-history", headers=other_headers)
        assert isolated.status_code == 200
        assert isolated.json() == {"items": []}

        too_long = "x" * 20_001
        invalid = client.put("/api/auth/me/batch-prompt-history", headers=headers, json={"items": [too_long]})
        assert invalid.status_code == 400
    finally:
        db.delete_session(other_token)
        db.delete_user(other_user["id"])


def test_current_user_demo_settings_are_persisted(auth_context):
    headers, _, _ = auth_context

    initial = client.get("/api/auth/me/demo-settings", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["save_db"] is False
    assert initial.json()["save_files"] is False
    assert initial.json()["interval_seconds"] == 30

    body = {
        "save_db": True,
        "save_files": False,
        "prompt_model": "meta/llama-3.3-70b-instruct",
        "seed_phrase": "短い冬の情景を生成",
        "interval_seconds": 45,
    }
    updated = client.put("/api/auth/me/demo-settings", headers=headers, json=body)
    assert updated.status_code == 200
    assert updated.json() == body

    persisted = client.get("/api/auth/me/demo-settings", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json() == body

    invalid = client.put("/api/auth/me/demo-settings", headers=headers, json={**body, "interval_seconds": 0})
    assert invalid.status_code == 422


def test_current_user_plugin_storage_is_persisted(auth_context):
    headers, user, group = auth_context
    other_user = db.add_user(
        username=f"api-plugin-storage-{uuid.uuid4().hex[:8]}",
        email=f"api-plugin-storage-{uuid.uuid4().hex[:8]}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    other_headers, other_token = _auth_headers(other_user)
    try:
        initial = client.get("/api/auth/me/plugin-storage", headers=headers)
        assert initial.status_code == 200
        assert initial.json() == {"storage": {}}

        updated = client.put(
            "/api/auth/me/plugin-storage/canvas-aspect",
            headers=headers,
            json={"value": {"selected": "golden"}},
        )
        assert updated.status_code == 200
        assert updated.json() == {"storage": {"canvas-aspect": {"selected": "golden"}}}

        persisted = client.get("/api/auth/me/plugin-storage", headers=headers)
        assert persisted.status_code == 200
        assert persisted.json() == {"storage": {"canvas-aspect": {"selected": "golden"}}}

        isolated = client.get("/api/auth/me/plugin-storage", headers=other_headers)
        assert isolated.status_code == 200
        assert isolated.json() == {"storage": {}}

        invalid = client.put("/api/auth/me/plugin-storage/bad id", headers=headers, json={"value": {}})
        assert invalid.status_code == 400
    finally:
        db.delete_session(other_token)
        db.delete_user(other_user["id"])


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


def test_compose_applies_canvas_aspect_plugin(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}
            ]
        }
    )
    monkeypatch.setattr(api_module, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/compose", json={"ddl": "横線", "canvas_aspect": "pillar"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["score"]["canvas"] == "pillar"
    assert 'viewBox="0 0 200 1000"' in data["svg"]


def test_compose_sanitizes_random_ddl_before_stage2(monkeypatch, auth_context):
    headers, _, _ = auth_context
    captured: dict[str, str] = {}

    def fake_compose(ddl: str, model=None):
        captured["ddl"] = ddl
        return Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2}]}
        )

    monkeypatch.setattr(api_module, "compose", fake_compose)
    r = client.post("/api/compose", json={"ddl": "赤い円をランダムに十二個散らす。"}, headers=headers)
    assert r.status_code == 200
    assert "赤い円を画面全体に点々と十二個散らす。" in captured["ddl"]
    assert any(marker in captured["ddl"] for marker in EXPANSION_MARKERS)


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


def test_compose_empty_instruction_result_is_retried(monkeypatch, auth_context):
    headers, _, _ = auth_context
    calls: list[str | None] = []

    def fake_compose(ddl: str, model=None, original_text=None, system_prompt=None, lang="ja"):
        calls.append(system_prompt)
        if len(calls) == 1:
            return Score(instructions=[])
        return Score.model_validate(
            {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}]}
        )

    monkeypatch.setattr(api_module, "compose", fake_compose)

    r = client.post("/api/compose", json={"ddl": "黒い線を引く。"}, headers=headers)

    assert r.status_code == 200
    assert len(calls) == 2
    assert calls[0] is None
    assert calls[1] is not None
    assert "空描画リトライ" in calls[1]


def test_compose_empty_instruction_result_uses_fallback_after_retry(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        api_module,
        "compose",
        lambda ddl, model=None, original_text=None, system_prompt=None, lang="ja": Score(instructions=[]),
    )

    r = client.post("/api/compose", json={"ddl": "黒い線を引く。"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["score"]["instructions"]
    assert data["score"]["instructions"][0]["primitive"] == "line"
    assert data["score"]["instructions"][0]["color_hint"] == "fallback from DDL"


def test_compose_fallback_preserves_arrangement_path(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        api_module,
        "compose",
        lambda ddl, model=None, original_text=None, system_prompt=None, lang="ja": Score(instructions=[]),
    )

    r = client.post(
        "/api/compose",
        json={"ddl": "赤い小さな楕円を波打つ軌跡に沿って二十一個散らす。"},
        headers=headers,
    )

    assert r.status_code == 200
    instruction = r.json()["score"]["instructions"][0]
    assert instruction["primitive"] == "ellipse"
    assert instruction["arrangement"]["layout"] == "scatter"
    assert instruction["arrangement"]["path"] == "wave"


def test_compose_fallback_preserves_line_arrangement_path(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        api_module,
        "compose",
        lambda ddl, model=None, original_text=None, system_prompt=None, lang="ja": Score(instructions=[]),
    )

    r = client.post(
        "/api/compose",
        json={"ddl": "青い細い縦線を上から下へ散らす。"},
        headers=headers,
    )

    assert r.status_code == 200
    instruction = r.json()["score"]["instructions"][0]
    assert instruction["primitive"] == "line"
    assert instruction["arrangement"]["layout"] == "vertical"
    assert instruction["arrangement"]["path"] == "top_to_bottom"


def test_compose_hard_timeout_uses_fallback(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setenv("INKU_STAGE2_HARD_TIMEOUT_SECONDS", "0.01")

    def slow_compose(ddl: str, model=None, original_text=None, system_prompt=None, lang="ja"):
        time.sleep(0.2)
        return Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
        )

    monkeypatch.setattr(api_module, "compose", slow_compose)

    r = client.post("/api/compose", json={"ddl": "黒い線を引く。"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["fallback_used"] is True
    assert data["retry_reasons"] == ["stage2_hard_timeout"]
    assert data["score"]["instructions"][0]["color_hint"] == "fallback from DDL"


def test_interpret_happy_path(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(api_module, "interpret_detail", lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None))
    r = client.post("/api/interpret", json={"text": "一滴の墨"}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"ddl": "中心に黒い円を置く。", "thinking": None}


def test_interpret_sanitizes_random_placement(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        api_module,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("赤い小さな円をランダムに十二個散らす。", None),
    )
    r = client.post("/api/interpret", json={"text": "赤い点を散らす"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["ddl"] == "赤い小さな円を画面全体に点々と十二個散らす。"


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
    assert "黒い円を置く。" in data["ddl"]
    assert "中心" not in data["ddl"]
    assert data["score"]["instructions"][0]["primitive"] == "circle"
    assert "<svg" in data["svg"]


def test_paint_stage1_hard_timeout_uses_fallback_ddl(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setenv("INKU_STAGE1_HARD_TIMEOUT_SECONDS", "0.01")

    def slow_interpret(text, model=None, include_thinking=False, system_prompt_prefix=None, lang="ja"):
        time.sleep(0.2)
        return "中心に黒い円を置く。", None, None, None

    captured: dict[str, str] = {}

    def fake_compose(ddl: str, model=None, original_text=None, system_prompt=None, lang="ja"):
        captured["ddl"] = ddl
        return Score.model_validate(
            {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}]}
        )

    monkeypatch.setattr(api_module, "interpret_detail", slow_interpret)
    monkeypatch.setattr(api_module, "compose", fake_compose)

    r = client.post("/api/paint", json={"text": "応答しない指示"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["interpret_fallback_used"] is True
    assert data["interpret_fallback_reasons"] == ["stage1_hard_timeout"]
    assert "斜めの線を三本" in data["ddl"]
    assert captured["ddl"] == data["ddl"]


def test_paint_sanitizes_stage1_before_compose(monkeypatch, auth_context):
    headers, _, _ = auth_context
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        api_module,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("赤い小さな円をランダムに十二個散らす。", None),
    )

    def fake_compose(ddl: str, model=None):
        captured["ddl"] = ddl
        return Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
        )

    monkeypatch.setattr(api_module, "compose", fake_compose)
    r = client.post("/api/paint", json={"text": "赤い点を散らす"}, headers=headers)
    assert r.status_code == 200
    assert "赤い小さな円を画面全体に点々と十二個散らす。" in r.json()["ddl"]
    assert any(marker in r.json()["ddl"] for marker in EXPANSION_MARKERS)
    assert r.json()["ddl"] == captured["ddl"]


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
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}]}
    )
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


def test_history_output_files_are_rebuildable_from_db(tmp_path):
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"artifact-{suffix}")
    user = db.add_user(
        username=f"artifact-{suffix}",
        email=f"artifact-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    headers, token = _auth_headers(user)
    item_id = str(uuid.uuid4())
    prefix = tmp_path / "outputs" / "sample"
    item = db.add_item({
        "id": item_id,
        "user_id": user["id"],
        "output_path": str(prefix),
        "input": "artifact source",
        "ddl": "中心に円",
        "score": {"instructions": []},
        "svg": "<svg><desc>from db</desc></svg>",
        "at": 1_700_000_000_000,
    })

    assert not (tmp_path / "outputs" / "sample_output.svg").exists()
    r = client.post("/api/history/rebuild-output-files", json={"ids": [item["id"]]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert (tmp_path / "outputs" / "sample_instruction.txt").read_text(encoding="utf-8") == "artifact source"
    assert (tmp_path / "outputs" / "sample_normalized.ddl").read_text(encoding="utf-8") == "中心に円"
    assert (tmp_path / "outputs" / "sample_score.json").exists()
    assert (tmp_path / "outputs" / "sample_output.svg").read_text(encoding="utf-8") == "<svg><desc>from db</desc></svg>"

    db.delete_items(user["id"], [item["id"]])
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_artifact_save_submit_skips_when_queue_is_full(monkeypatch, caplog):
    class FullSlots:
        def acquire(self, blocking: bool = True):
            assert blocking is False
            return False

    class FailingExecutor:
        def submit(self, *args, **kwargs):
            raise AssertionError("executor must not be called when artifact queue is full")

    monkeypatch.setattr(api_module, "_save_slots", FullSlots())
    monkeypatch.setattr(api_module, "_save_executor", FailingExecutor())
    caplog.set_level(logging.WARNING, logger=api_module.__name__)

    assert api_module._submit_history_artifact_save({"id": "history-full"}) is False
    assert "artifact save queue is full" in caplog.text


def test_artifact_save_submit_releases_slot_after_save(monkeypatch):
    class AvailableSlots:
        def __init__(self):
            self.released = 0

        def acquire(self, blocking: bool = True):
            assert blocking is False
            return True

        def release(self):
            self.released += 1

    class InlineExecutor:
        def submit(self, fn, item):
            fn(item)

    slots = AvailableSlots()
    saved = []
    monkeypatch.setattr(api_module, "_save_slots", slots)
    monkeypatch.setattr(api_module, "_save_executor", InlineExecutor())
    monkeypatch.setattr(api_module, "_save_history_artifacts", lambda item: saved.append(item["id"]))

    assert api_module._submit_history_artifact_save({"id": "history-ok"}) is True
    assert saved == ["history-ok"]
    assert slots.released == 1


def test_artifact_save_submit_releases_slot_when_executor_fails(monkeypatch, caplog):
    class AvailableSlots:
        def __init__(self):
            self.released = 0

        def acquire(self, blocking: bool = True):
            assert blocking is False
            return True

        def release(self):
            self.released += 1

    class FailingExecutor:
        def submit(self, *args, **kwargs):
            raise RuntimeError("executor closed")

    slots = AvailableSlots()
    monkeypatch.setattr(api_module, "_save_slots", slots)
    monkeypatch.setattr(api_module, "_save_executor", FailingExecutor())
    caplog.set_level(logging.ERROR, logger=api_module.__name__)

    assert api_module._submit_history_artifact_save({"id": "history-submit-fail"}) is False
    assert slots.released == 1
    assert "failed to submit artifact save job" in caplog.text


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
    assert data["plugins"]["enabled"] is True
    assert data["plugins"]["runtime_editable"] is False
    assert data["plugins"]["loaded"] == [{"name": "canvas-aspect", "version": "0.1.0", "status": "enabled"}]
    assert data["output_save"]["workers"] >= 1
    assert data["output_save"]["queue_limit"] >= data["output_save"]["workers"]
    assert {"submitted", "completed", "failed", "skipped"} <= set(data["output_save"])
    assert "source of truth" in data["output_save"]["note"]

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
    rename_r = client.patch(
        f"/api/user-groups/{group['id']}",
        json={"name": f"renamed-class-{suffix}"},
        headers=headers,
    )
    assert rename_r.status_code == 200
    assert rename_r.json()["name"] == f"renamed-class-{suffix}"
    group = rename_r.json()

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
    settings_r = client.patch("/api/auth/me/settings", json={"settings_tab": "users"}, headers=headers)
    assert settings_r.status_code == 200
    assert settings_r.json()["settings_tab"] == "users"
    bad_settings_r = client.patch("/api/auth/me/settings", json={"settings_tab": "connection"}, headers=headers)
    assert bad_settings_r.status_code == 400

    lead_headers, lead_token = _auth_headers(user)

    assert client.post("/api/user-groups", json={"name": f"blocked-{suffix}"}, headers=lead_headers).status_code == 403
    assert client.patch(
        f"/api/user-groups/{group['id']}",
        json={"name": f"blocked-rename-{suffix}"},
        headers=lead_headers,
    ).status_code == 403
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

    star_a = client.patch(f"/api/history/{item_a_second['id']}/star", json={"starred": True}, headers=headers_a)
    assert star_a.status_code == 200
    assert star_a.json()["starred"] is True
    starred_a = client.get("/api/history?starred=true", headers=headers_a)
    assert starred_a.status_code == 200
    assert starred_a.json()["total"] == 1
    assert starred_a.json()["items"][0]["id"] == item_a_second["id"]

    list_b = client.get("/api/history", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json()["total"] == 0

    star_b = client.patch(f"/api/history/{item_a_second['id']}/star", json={"starred": False}, headers=headers_b)
    assert star_b.status_code == 404

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
