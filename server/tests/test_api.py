"""API endpoint tests.

Stage 2 composer を monkeypatch でバイパスし、FastAPI のスキーマ/配線のみ検証。
実 API 呼び出しは test_composer で gated 実行。
"""

from __future__ import annotations

import asyncio
import builtins
import importlib.metadata
import json
from datetime import datetime, timezone
import logging
import os
import sys
import time
import types
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from inku_server import db
from inku_server import api as api_module
from inku_server.api_core import common as api_common
from inku_server.api_core import rendering as api_rendering
from inku_server.api_core import state as api_state
from inku_server.api_core.routers import history as history_routes
from inku_server.api_core.routers import public as public_routes
from inku_server.api_core.routers import render as render_routes
from inku_server.api_core.routers import settings as settings_routes
from inku_server.api import app
from inku_server.ddl_expander import FOCUS_IDS, focus_word
from inku_server.model_settings import (
    connection_for,
    default_model_settings,
    model_provider_catalog,
    normalize_model_settings,
    update_model_settings,
)
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
    "前の線を切る",
    "前の線に沿って",
    "前の形に触れない",
    "画面全体へ三本",
    "上から下への縦の帯",
    "左から右への横の帯",
    "右下の焦点から外へ",
    "右下の焦点から放射状に",
    "右下の焦点から三つ",
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_resolved_stage_models_qualify_current_user_provider():
    actor = {
        "model_settings": {
            "stage1_provider": "openai",
            "stage1_model": "gpt-5.2",
            "stage2_provider": "anthropic",
            "stage2_model": "claude-sonnet-4-6",
            "vision_provider": "nvidia",
            "vision_model": "meta/llama-3.2-90b-vision-instruct",
        }
    }

    assert render_routes._resolved_stage1_model(None, actor) == "openai:gpt-5.2"
    assert render_routes._resolved_stage1_model("gpt-5.2", actor) == "openai:gpt-5.2"
    assert render_routes._resolved_stage2_model(None, actor) == "anthropic:claude-sonnet-4-6"
    assert render_routes._resolved_stage2_model("claude-sonnet-4-6", actor) == "anthropic:claude-sonnet-4-6"
    assert api_common._resolved_vision_model(None, actor) == "nvidia:meta/llama-3.2-90b-vision-instruct"
    assert api_common._resolved_vision_model("openai:gpt-4.1", actor) == "openai:gpt-4.1"
    # A reference qualified by a provider other than this actor's stage is left
    # alone. It used to say "ovms:qwen-api", which passed for the wrong reason once
    # ovms was withdrawn: an unqualified reference that is not the stage's own model
    # is also returned unchanged, so the assertion held without rule 1 running.
    assert render_routes._resolved_stage1_model("gemini:gemini-2.5-pro", actor) == "gemini:gemini-2.5-pro"
    assert render_routes._resolved_stage1_model("qwen-api", actor) == "qwen-api"


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
        permission_groups=["users"],
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


def test_info_reports_version_build_number_and_developer_mode(monkeypatch):
    monkeypatch.delenv("INKU_DEVELOPER_MODE", raising=False)
    r = client.get("/api/info")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "inku-server"
    # version is the application version and comes from web/APP_VERSION, the
    # single source the UI reads too; release_version is the installed
    # distribution and lags while releases are on hold. Track both against their
    # own source rather than a literal.
    assert data["version"] == (REPO_ROOT / "web" / "APP_VERSION").read_text(encoding="utf-8").strip()
    assert data["release_version"] == importlib.metadata.version("inku-server")
    assert data["build_number"]
    assert data["developer_mode"] is False
    assert data["render_engine_id"] == "default"
    assert data["render_engine_version"] == "32"
    assert data["ddl_version"] == "3"
    assert data["ddl_engine_version"] == "15"

    monkeypatch.setenv("INKU_DEVELOPER_MODE", "1")
    enabled = client.get("/api/info")
    assert enabled.json()["developer_mode"] is True


def test_info_reads_current_render_engine_at_request_time(monkeypatch):
    engine = types.SimpleNamespace(id="test-engine", version="test-version")
    monkeypatch.setattr(public_routes, "current_render_engine", lambda: engine)

    r = client.get("/api/info")

    assert r.status_code == 200
    assert r.json()["render_engine_id"] == "test-engine"
    assert r.json()["render_engine_version"] == "test-version"


def test_color_catalogs_are_served_by_api():
    r = client.get("/api/color-catalogs")
    assert r.status_code == 200
    data = r.json()
    assert data["default_catalog_id"] == "default"
    catalogs = {catalog["id"]: catalog for catalog in data["catalogs"]}
    assert catalogs["default"]["sub"] == "neutral baseline"
    assert catalogs["default"]["sub_ja"] == "ニュートラルな基準値"
    assert catalogs["vivid_material"]["map"]["green"] == "#008f39"
    assert any(color["name"] == "Fresh Green" for color in catalogs["vivid_material"]["palette"])
    assert any(color["name_ja"] == "新鮮な緑" for color in catalogs["vivid_material"]["palette"])


def test_generation_apis_require_auth():
    assert client.post("/api/compose", json={"ddl": "中心に円"}).status_code == 401
    assert client.post("/api/interpret", json={"description": "一滴の墨"}).status_code == 401
    assert client.post("/api/paint", json={"description": "一滴の墨"}).status_code == 401


def test_login_uses_httponly_session_cookie():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"cookie-auth-{suffix}")
    user = db.add_user(
        username=f"cookie-auth-{suffix}",
        email=f"cookie-auth-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
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
        permission_groups=["users"],
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
        permission_groups=["users"],
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


def test_bootstrap_admin_password_treats_blank_env_as_unset(monkeypatch):
    # Compose passes "" for an unfilled variable; that must not fail startup.
    monkeypatch.setenv("INKU_BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.delenv("INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN", raising=False)
    assert db._bootstrap_admin_password() is None


def test_bootstrap_admin_password_blank_env_still_honors_insecure_flag(monkeypatch):
    monkeypatch.setenv("INKU_BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setenv("INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN", "1")
    assert db._bootstrap_admin_password() == "inku-admin"


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
        # One account that predates every settings column. Without a row here the
        # migrations below are only checked for the columns they add, not for the
        # values existing accounts end up carrying.
        conn.execute(text("""
            INSERT INTO user_accounts (id, username, email, password_hash, role, group_id, at)
            VALUES ('u-legacy', 'legacy', 'legacy@example.com', 'x', 'user', NULL, 0)
        """))

    monkeypatch.setattr(db, "engine", legacy_engine)
    db._migrate_columns()
    db._migrate_columns()

    columns = {col["name"] for col in inspect(legacy_engine).get_columns("history")}
    assert {
        "user_id",
        "catalog_id",
        "render_build_number",
        "render_color_profile",
        "render_engine_id",
        "render_engine_version",
        "render_color_catalog_id",
        "render_color_catalog_name",
        "render_color_catalog_sub",
        "render_color_catalog",
        "render_color_map",
        "render_canvas_aspect",
        "render_canvas_aspect_id",
        "render_canvas_aspect_ratio",
        "render_hash",
        "trashed",
        "starred",
    } <= columns
    user_columns = {col["name"] for col in inspect(legacy_engine).get_columns("user_accounts")}
    assert {"ui_theme", "ui_mode", "ui_custom", "tooltips_enabled", "model_settings", "batch_prompt_history", "demo_settings", "export_templates"} <= user_columns
    # An account that existed before the column keeps the visible side of every
    # setting the migration backfills. Asserting only that the column arrived
    # leaves the default free to flip: turning tooltips off for every existing
    # account passed all 118 tests before this line was added.
    with legacy_engine.connect() as conn:
        migrated = conn.execute(text(
            "SELECT ui_theme, ui_mode, tooltips_enabled FROM user_accounts WHERE id = 'u-legacy'"
        )).one()
    assert migrated.ui_theme == "light"
    assert migrated.ui_mode == "simple"
    assert bool(migrated.tooltips_enabled) is True
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
    assert me.json()["ui_theme"] == "dark"

    # The patch has to ask for the theme the default is *not*, or the assertion
    # holds whether or not the write happened. Build 744 made dark the default
    # and left this test patching dark onto dark, which passed with the store
    # commented out.
    updated = client.patch("/api/auth/me/settings", headers=headers, json={"ui_theme": "light"})
    assert updated.status_code == 200
    assert updated.json()["ui_theme"] == "light"

    me_again = client.get("/api/auth/me", headers=headers)
    assert me_again.status_code == 200
    assert me_again.json()["ui_theme"] == "light"

    back = client.patch("/api/auth/me/settings", headers=headers, json={"ui_theme": "dark"})
    assert back.status_code == 200
    assert back.json()["ui_theme"] == "dark"

    invalid = client.patch("/api/auth/me/settings", headers=headers, json={"ui_theme": "sepia"})
    assert invalid.status_code == 400


def test_current_user_ui_mode_and_custom_visibility_are_persisted(auth_context):
    headers, _, _ = auth_context

    initial = client.get("/api/auth/me", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["ui_mode"] == "simple"
    assert initial.json()["ui_custom"] == {}
    assert initial.json()["tooltips_enabled"] is True

    tooltips_off = client.patch("/api/auth/me/settings", headers=headers, json={"tooltips_enabled": False})
    assert tooltips_off.status_code == 200
    assert tooltips_off.json()["tooltips_enabled"] is False


    custom = {
        "input_modes": True,
        "drawing_settings": False,
        "ddl_tools": True,
        "detail_status": False,
        "work_tools": True,
        "history": False,
        "auxiliary": True,
    }
    updated = client.patch(
        "/api/auth/me/settings",
        headers=headers,
        json={"ui_mode": "custom", "ui_custom": custom},
    )
    assert updated.status_code == 200
    assert updated.json()["ui_mode"] == "custom"
    assert updated.json()["ui_custom"] == custom

    persisted = client.get("/api/auth/me", headers=headers)
    assert persisted.json()["ui_mode"] == "custom"
    assert persisted.json()["ui_custom"] == custom

    reset = client.patch(
        "/api/auth/me/settings",
        headers=headers,
        json={"ui_mode": "simple", "ui_custom": {}},
    )
    assert reset.status_code == 200
    assert reset.json()["ui_mode"] == "simple"
    assert reset.json()["ui_custom"] == {}

    assert client.patch(
        "/api/auth/me/settings", headers=headers, json={"ui_mode": "expert"}
    ).status_code == 400
    assert client.patch(
        "/api/auth/me/settings", headers=headers, json={"ui_custom": {"unknown": True}}
    ).status_code == 400


def test_current_user_model_selection_is_persisted(auth_context):
    headers, _, _ = auth_context
    updated = client.patch(
        "/api/auth/me/settings",
        headers=headers,
        json={
            "model_settings": {
                "stage1_provider": "openai",
                "stage1_model": "openai:gpt-5.1-mini",
                "stage2_provider": "gemini",
                "stage2_model": "gemini:gemini-2.5-flash",
                "vision_provider": "nvidia",
                "vision_model": "meta/llama-3.2-90b-vision-instruct",
                "okugaki_model": "openai:gpt-4.1-mini",
            }
        },
    )
    assert updated.status_code == 200
    assert updated.json()["model_settings"]["stage1_provider"] == "openai"
    assert updated.json()["model_settings"]["stage2_model"] == "gemini:gemini-2.5-flash"
    assert updated.json()["model_settings"]["vision_model"] == "meta/llama-3.2-90b-vision-instruct"
    # v2.9.1: okugaki is stored as a (provider, model) pair like every other
    # stage. A single qualified string sent by an older client is still read;
    # it is split on the way in and written back as the pair.
    assert updated.json()["model_settings"]["okugaki_provider"] == "openai"
    assert updated.json()["model_settings"]["okugaki_model"] == "gpt-4.1-mini"
    assert updated.json()["model_settings"]["model_inspection_selected_models"] == []

    comparison_models = [
        "nvidia:google/gemma-4-31b-it",
        "nvidia:google/gemma-4-31b-it",
        "",
        123,
        "openai:gpt-5.1",
        "gemini:gemini-2.5-pro",
        "anthropic:claude-sonnet-4-6",
        "ollama:llama3.2",
    ]
    selected = client.patch(
        "/api/auth/me/settings",
        headers=headers,
        json={"model_settings": {"model_inspection_selected_models": comparison_models}},
    )
    assert selected.status_code == 200
    assert selected.json()["model_settings"]["model_inspection_selected_models"] == [
        "nvidia:google/gemma-4-31b-it",
        "openai:gpt-5.1",
        "gemini:gemini-2.5-pro",
        "anthropic:claude-sonnet-4-6",
    ]

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["model_settings"]["stage1_model"] == "openai:gpt-5.1-mini"
    assert me.json()["model_settings"]["vision_provider"] == "nvidia"
    assert me.json()["model_settings"]["okugaki_provider"] == "openai"
    assert me.json()["model_settings"]["okugaki_model"] == "gpt-4.1-mini"
    assert me.json()["model_settings"]["model_inspection_selected_models"] == [
        "nvidia:google/gemma-4-31b-it",
        "openai:gpt-5.1",
        "gemini:gemini-2.5-pro",
        "anthropic:claude-sonnet-4-6",
    ]


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
        permission_groups=["users"],
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


def test_current_user_instruction_caption_setting_is_persisted(auth_context):
    headers, _, _ = auth_context
    updated = client.patch("/api/auth/me/settings", headers=headers, json={"model_settings": {"instruction_caption_visible": False}})
    assert updated.status_code == 200
    assert updated.json()["model_settings"]["instruction_caption_visible"] is False
    current = client.get("/api/auth/me", headers=headers)
    assert current.status_code == 200
    assert current.json()["model_settings"]["instruction_caption_visible"] is False


def test_current_user_demo_settings_are_persisted(auth_context):
    headers, _, _ = auth_context

    initial = client.get("/api/auth/me/demo-settings", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["save_db"] is False
    assert initial.json()["save_files"] is False
    # The demo no longer carries a catalog mode of its own: it draws with the
    # user's own catalog choice, "from the description" included.
    assert "catalog_mode" not in initial.json()
    assert initial.json()["interval_seconds"] == 30
    assert initial.json()["timeout_seconds"] == 3600

    body = {
        "save_db": True,
        "save_files": False,
        "prompt_provider": "nvidia",
        "prompt_model": "meta/llama-3.3-70b-instruct",
        "seed_phrase": "短い冬の情景を生成",
        "interval_seconds": 45,
        "timeout_seconds": 7200,
    }
    updated = client.put("/api/auth/me/demo-settings", headers=headers, json=body)
    assert updated.status_code == 200
    assert updated.json() == body

    # A client still sending the retired mode is accepted and does not get it back.
    legacy = client.put("/api/auth/me/demo-settings", headers=headers, json={**body, "catalog_mode": "auto"})
    assert legacy.status_code == 200
    assert legacy.json() == body

    persisted = client.get("/api/auth/me/demo-settings", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json() == body

    # v2.9.1: the demo prompt model is a pair too. A client that still sends one
    # qualified string is read, and the pair comes back.
    legacy = client.put(
        "/api/auth/me/demo-settings",
        headers=headers,
        json={**body, "prompt_provider": "nvidia", "prompt_model": "ollama:gpt-oss:20b"},
    )
    assert legacy.status_code == 200
    assert legacy.json()["prompt_provider"] == "ollama"
    assert legacy.json()["prompt_model"] == "gpt-oss:20b"

    invalid = client.put("/api/auth/me/demo-settings", headers=headers, json={**body, "interval_seconds": 0})
    assert invalid.status_code == 422
    too_short = client.put("/api/auth/me/demo-settings", headers=headers, json={**body, "timeout_seconds": 59})
    assert too_short.status_code == 422
    too_long = client.put("/api/auth/me/demo-settings", headers=headers, json={**body, "timeout_seconds": 86401})
    assert too_long.status_code == 422


def test_current_user_plugin_storage_is_persisted(auth_context):
    headers, user, group = auth_context
    admin = db.add_user(
        username=f"api-plugin-admin-{uuid.uuid4().hex[:8]}",
        email=f"api-plugin-admin-{uuid.uuid4().hex[:8]}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    admin_headers, admin_token = _auth_headers(admin)
    other_user = db.add_user(
        username=f"api-plugin-storage-{uuid.uuid4().hex[:8]}",
        email=f"api-plugin-storage-{uuid.uuid4().hex[:8]}@example.test",
        password="password-123",
        permission_groups=["users"],
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
        assert updated.status_code == 403

        updated = client.put(
            "/api/auth/me/plugin-storage/canvas-aspect",
            headers=admin_headers,
            json={"value": {"selected": "golden"}},
        )
        assert updated.status_code == 200
        assert updated.json() == {"storage": {"canvas-aspect": {"selected": "golden"}}}

        persisted = client.get("/api/auth/me/plugin-storage", headers=admin_headers)
        assert persisted.status_code == 200
        assert persisted.json() == {"storage": {"canvas-aspect": {"selected": "golden"}}}

        isolated = client.get("/api/auth/me/plugin-storage", headers=other_headers)
        assert isolated.status_code == 200
        assert isolated.json() == {"storage": {}}

        invalid = client.put("/api/auth/me/plugin-storage/bad id", headers=admin_headers, json={"value": {}})
        assert invalid.status_code == 400
    finally:
        db.delete_session(admin_token)
        db.delete_session(other_token)
        db.delete_user(admin["id"])
        db.delete_user(other_user["id"])


def test_current_user_export_templates_are_persisted(auth_context):
    headers, _, _ = auth_context

    initial = client.get("/api/auth/me/export-templates", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["templates"] == [
        {"id": "png-1080", "name": "PNG 1080px", "description": "PNG / Y軸 1080px", "y_px": 1080},
        {"id": "png-2160", "name": "PNG 2160px", "description": "PNG / Y軸 2160px", "y_px": 2160},
        {"id": "png-4320", "name": "PNG 4320px", "description": "PNG / Y軸 4320px", "y_px": 4320},
    ]

    body = {
        "templates": [
            {"id": "custom", "name": "Poster", "description": "Tall poster", "y_px": 3000},
        ]
    }
    updated = client.put("/api/auth/me/export-templates", headers=headers, json=body)
    assert updated.status_code == 200
    assert updated.json() == body

    persisted = client.get("/api/auth/me/export-templates", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json() == body

    invalid = client.put(
        "/api/auth/me/export-templates",
        headers=headers,
        json={"templates": [{"id": "bad", "name": "Bad", "description": "", "y_px": 10}]},
    )
    assert invalid.status_code == 422


def test_compose_happy_path(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2}
            ]
        }
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/compose", json={"ddl": "中心に円"}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["score"]["instructions"][0]["primitive"] == "circle"
    assert "<svg" in data["svg"]
    assert "<circle" in data["svg"]
    assert data["render_hash"].startswith("rh3:")
    assert len(data["render_hash"]) == 68
    assert data["render_hash_short"] == data["render_hash"][-4:].upper()
    assert data["instruction_lang_requested"] == "auto"
    assert data["instruction_lang_resolved"] == "ja"


def test_compose_reports_relation_drop_during_auto_repair(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "color": "black",
                    "from": [0.2, 0.5],
                    "to": [0.8, 0.5],
                    "relation": {"type": "along", "gap": "narrow"},
                }
            ]
        }
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/compose", json={"ddl": "前の線に沿う線"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["coerce_relation_input_count"] == 1
    assert data["coerce_relation_output_count"] == 0
    assert data["coerce_relation_dropped_count"] == 1
    assert data["coerce_relation_drop_rate"] == 1.0
    assert data["coerce_warnings"] == ["relation dropped during coerce validation"]
    assert "relation" not in data["score"]["instructions"][0]


def test_compose_resolves_english_instruction_language(monkeypatch, auth_context):
    headers, _, _ = auth_context
    captured: dict[str, str] = {}

    def fake_compose(ddl: str, model=None, original_description=None, system_prompt=None, lang="ja", **kwargs):
        captured["lang"] = lang
        return Score.model_validate(
            {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}]}
        )

    monkeypatch.setattr(render_routes, "compose", fake_compose)

    r = client.post(
        "/api/compose",
        json={"ddl": "one blue diagonal line", "instruction_lang": "auto", "ui_lang": "ja"},
        headers=headers,
    )

    assert r.status_code == 200
    data = r.json()
    assert captured["lang"] == "en"
    assert data["instruction_lang_requested"] == "auto"
    assert data["instruction_lang_resolved"] == "en"
    assert data["ui_lang"] == "ja"


def test_compose_uses_ui_language_when_text_has_no_language_signal(monkeypatch, auth_context):
    headers, _, _ = auth_context
    captured: dict[str, str] = {}

    def fake_compose(ddl: str, model=None, original_description=None, system_prompt=None, lang="ja", **kwargs):
        captured["lang"] = lang
        return Score.model_validate(
            {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}]}
        )

    monkeypatch.setattr(render_routes, "compose", fake_compose)
    r = client.post(
        "/api/compose",
        json={"ddl": "12345", "instruction_lang": "auto", "ui_lang": "en"},
        headers=headers,
    )

    assert r.status_code == 200
    assert captured["lang"] == "en"
    assert r.json()["instruction_lang_resolved"] == "en"


def test_language_metadata_does_not_change_render_hash():
    item = {
        "input": "one black line",
        "ddl": "Draw one black line.",
        "score": {
            "instructions": [
                {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "color": "black"}
            ]
        },
        "svg": "<svg><line x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\" /></svg>",
        "render_build_number": "402",
        "render_engine_id": "default",
        "render_engine_version": "1",
        "render_canvas_aspect": "square",
        "render_canvas_aspect_id": "square",
        "render_canvas_aspect_ratio": 1.0,
        "render_color_catalog_id": "default",
        "render_color_catalog_name": "inku Default",
        "render_color_catalog_sub": "neutral baseline",
        "render_color_map": {"black": "#111111"},
    }
    with_language = {
        **item,
        "instruction_lang_requested": "auto",
        "instruction_lang_resolved": "en",
        "ui_lang": "ja",
    }

    assert db.render_hash_for_item(with_language) == db.render_hash_for_item(item)


def test_render_hash_v3_uses_saved_score_and_render_conditions_not_svg_or_text():
    base = {
        "input": "one black line",
        "ddl": "Draw one black line.",
        "score": {
            "instructions": [
                {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "color": "black"}
            ]
        },
        "svg": "<svg><line x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\" /></svg>",
        "render_seed": 7,
        "composition_seed": 2,
        "render_build_number": "449",
        "render_engine_id": "default",
        "render_engine_version": "2",
        "render_color_catalog_id": "default",
    }

    same_edition = {
        **base,
        "input": "changed input text",
        "ddl": "Changed DDL.",
        "svg": "<svg><path d=\"M0 0L1 1\" /></svg>",
    }

    render_hash = db.render_hash_for_item(base)
    assert render_hash.startswith("rh3:")
    assert len(render_hash) == 68
    assert db.render_hash_for_item(same_edition) == render_hash


def test_render_hash_v3_changes_with_render_seed_but_not_composition_seed():
    base = {
        "score": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]},
        "render_seed": 7,
        "composition_seed": 2,
        "render_build_number": "449",
        "render_engine_id": "default",
        "render_engine_version": "2",
        "render_color_catalog_id": "default",
    }

    assert db.render_hash_for_item({**base, "render_seed": 8}) != db.render_hash_for_item(base)
    assert db.render_hash_for_item({**base, "composition_seed": 3}) == db.render_hash_for_item(base)


def test_legacy_render_hash_short_remains_display_compatible():
    legacy = "a" * 60 + "1b2c"
    assert db.render_hash_short(legacy) == "1B2C"


def test_compose_applies_canvas_aspect_plugin(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}
            ]
        }
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/compose", json={"ddl": "横線", "canvas_aspect": "pillar"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    # Contract the-composition-knows-what-paper-it-is-on (2026-08-13): the Score
    # keeps what Stage 2 declared -- here nothing, so the default stands -- and
    # the requested paper reaches the picture through render_canvas_aspect*
    # instead of by overwriting the declaration.
    assert data["score"]["canvas"] == "square"
    assert data["render_canvas_aspect_id"] == "pillar"
    assert 'viewBox="0 0 200 1000"' in data["svg"]


def test_compose_canvas_aspect_override_preserves_ground(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {"material": "paper", "tone": "off_white", "grain": "fine"},
            },
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}
            ],
        }
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/compose", json={"ddl": "横線", "canvas_aspect": "pillar"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    # The declaration and its ground both survive the override -- see the note
    # in test_compose_applies_canvas_aspect_plugin.
    assert data["score"]["canvas"]["aspect"] == "square"
    assert data["score"]["canvas"]["ground"]["material"] == "paper"
    assert data["render_canvas_aspect_id"] == "pillar"
    assert 'viewBox="0 0 200 1000"' in data["svg"]


def test_compose_accepts_byobu_canvas_with_multiline_ddl(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}
            ]
        }
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post(
        "/api/compose",
        json={"ddl": "背景を白で塗りつぶす。\n青い横線を一本引く。", "canvas_aspect": "byobu"},
        headers=headers,
    )

    assert r.status_code == 200
    data = r.json()
    assert data["score"]["canvas"] == "square"
    assert data["render_canvas_aspect_id"] == "byobu"
    assert 'viewBox="0 0 2200 1000"' in data["svg"]


def test_score_canvas_accepts_future_plugin_id():
    score = Score.model_validate(
        {
            "canvas": "future-plugin-canvas",
            "instructions": [
                {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}
            ],
        }
    )

    assert score.canvas == "future-plugin-canvas"


def test_compose_sanitizes_random_ddl_before_stage2(monkeypatch, auth_context):
    headers, _, _ = auth_context
    captured: dict[str, str] = {}

    def fake_compose(ddl: str, model=None):
        captured["ddl"] = ddl
        return Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2}]}
        )

    monkeypatch.setattr(render_routes, "compose", fake_compose)
    r = client.post("/api/compose", json={"ddl": "赤い円をランダムに十二個散らす。"}, headers=headers)
    assert r.status_code == 200
    assert "赤い円を画面全体に点々と十二個散らす。" in captured["ddl"]
    # Stage 1.5 reframes and stops: the candidate sentences it used to append
    # were staffage and went away with the level (v2.11.0), so what reaches
    # Stage 2 is the sanitized DDL and nothing the author did not write.
    assert not any(marker in captured["ddl"] for marker in EXPANSION_MARKERS)


def test_compose_empty_ddl_rejected(auth_context):
    headers, _, _ = auth_context
    r = client.post("/api/compose", json={"ddl": ""}, headers=headers)
    assert r.status_code == 422


def test_compose_composer_failure_returns_502(monkeypatch, auth_context):
    headers, _, _ = auth_context
    def boom(ddl: str, model=None):
        raise RuntimeError("haiku unavailable")

    monkeypatch.setattr(render_routes, "compose", boom)
    r = client.post("/api/compose", json={"ddl": "中心に円"}, headers=headers)
    assert r.status_code == 502
    assert r.json()["detail"] == "compose failed"
    assert "haiku unavailable" not in r.text


def test_compose_empty_instruction_result_is_retried(monkeypatch, auth_context):
    headers, _, _ = auth_context
    calls: list[str | None] = []

    def fake_compose(ddl: str, model=None, original_description=None, system_prompt=None, lang="ja", **kwargs):
        calls.append(system_prompt)
        if len(calls) == 1:
            return Score(instructions=[])
        return Score.model_validate(
            {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}]}
        )

    monkeypatch.setattr(render_routes, "compose", fake_compose)

    r = client.post("/api/compose", json={"ddl": "黒い線を引く。"}, headers=headers)

    assert r.status_code == 200
    assert len(calls) == 2
    assert calls[0] is None
    assert calls[1] is not None
    assert "空描画リトライ" in calls[1]
    assert "空配列は禁止" in calls[1]
    assert "Score.presence" not in calls[1]


def test_compose_empty_instruction_result_uses_fallback_after_retry(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "compose",
        lambda ddl, model=None, original_description=None, system_prompt=None, lang="ja": Score(instructions=[]),
    )

    r = client.post("/api/compose", json={"ddl": "黒い線を引く。"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["score"]["instructions"]
    assert data["score"]["instructions"][0]["primitive"] == "line"
    assert data["score"]["instructions"][0]["note"].startswith("fallback from DDL")


def test_compose_can_skip_auto_repair(monkeypatch, auth_context):
    headers, _, _ = auth_context

    def fake_compose(ddl: str, model=None, original_description=None, system_prompt=None, lang="ja", **kwargs):
        return Score.model_validate(
            {"instructions": [{"primitive": "line", "from": [0.5, 0.0], "to": [0.5, 1.0], "color": "green"}]}
        )

    monkeypatch.setattr(render_routes, "compose", fake_compose)

    r = client.post(
        "/api/compose",
        json={"ddl": "震えるペンの緑の直線を300本、上から下に引く。", "auto_repair": False},
        headers=headers,
    )

    assert r.status_code == 200
    instructions = r.json()["score"]["instructions"]
    assert [ins["primitive"] for ins in instructions] == ["line"]
    assert not any("composition anchor restored" in (ins.get("note") or "") for ins in instructions)


def test_compose_fallback_preserves_arrangement_path(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "compose",
        lambda ddl, model=None, original_description=None, system_prompt=None, lang="ja": Score(instructions=[]),
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
        render_routes,
        "compose",
        lambda ddl, model=None, original_description=None, system_prompt=None, lang="ja": Score(instructions=[]),
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


def test_compose_fallback_clusters_large_counts_and_palette(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "compose",
        lambda ddl, model=None, original_description=None, system_prompt=None, lang="ja": Score(instructions=[]),
    )

    r = client.post(
        "/api/compose",
        json={"ddl": "春の赤い小さな楕円を波打つ軌跡に沿って三百個散らす。"},
        headers=headers,
    )

    assert r.status_code == 200
    arrangement = r.json()["score"]["instructions"][0]["arrangement"]
    assert arrangement["count"] <= 120
    assert arrangement["density"] == "high"
    assert arrangement["cluster_count"] == 9
    assert arrangement["preserve_space"] is True
    # Until ddl-engine 10 the fallback read `春` as a tone and built
    # ["red","green","white"], so 100 of the 300 ellipses were the red the
    # description actually named and 200 were colors it did not. The tone
    # palette still runs -- this is a one-color description, so the cycle it
    # produced is reduced at the exit to the named red and every member takes it.
    assert arrangement["color_cycle"] == ["red"]
    assert r.json()["score"]["instructions"][0]["color"] == "red"


def test_compose_fallback_uses_triangle_for_mountain(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "compose",
        lambda ddl, model=None, original_description=None, system_prompt=None, lang="ja": Score(instructions=[]),
    )

    r = client.post("/api/compose", json={"ddl": "緑の山を二つ並べる。"}, headers=headers)

    assert r.status_code == 200
    instruction = r.json()["score"]["instructions"][0]
    assert instruction["primitive"] == "triangle"
    assert instruction["arrangement"]["count"] == 2


def test_compose_fallback_adds_negative_space_support_for_paper_trace(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "compose",
        lambda ddl, model=None, original_description=None, system_prompt=None, lang="ja": Score(instructions=[]),
    )

    r = client.post(
        "/api/compose",
        json={"ddl": "新聞紙が迷うように回っている。灰色の四角を右下に置く。"},
        headers=headers,
    )

    assert r.status_code == 200
    instructions = r.json()["score"]["instructions"]
    assert len(instructions) >= 2
    assert instructions[0]["arrangement"]["preserve_space"] is True
    assert instructions[0]["arrangement"]["fade"] == "outward"
    assert any("fallback negative space support" in (ins.get("note") or "") for ins in instructions)


def test_compose_hard_timeout_uses_fallback(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setenv("INKU_STAGE2_HARD_TIMEOUT_SECONDS", "0.01")

    def slow_compose(ddl: str, model=None, original_description=None, system_prompt=None, lang="ja"):
        time.sleep(0.2)
        return Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
        )

    monkeypatch.setattr(render_routes, "compose", slow_compose)

    r = client.post("/api/compose", json={"ddl": "黒い線を引く。"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["fallback_used"] is True
    assert data["retry_reasons"] == ["stage2_hard_timeout"]
    assert data["score"]["instructions"][0]["note"].startswith("fallback from DDL")


def test_compose_retry_reason_only_retries_empty_instructions():
    assert render_routes._compose_retry_reason(Score(instructions=[]), tokens_out=10, elapsed_ms=1) == "empty_instructions"
    score = Score.model_validate(
        {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "color": "black"}]}
    )
    assert render_routes._compose_retry_reason(score, tokens_out=999999, elapsed_ms=999999) == "none"


def test_stage1_fallback_does_not_treat_dawn_as_night():
    ddl = render_routes._fallback_ddl_from_text("夜明けの湖で、最初の光が水のしわをほどく。", lang="ja")

    assert ddl.startswith("背景を白で埋める。")
    assert "背景を黒" not in ddl


def test_stage_timeout_keeps_capacity_bound_until_worker_finishes(monkeypatch):
    executor = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(render_routes, "_stage_executor", executor)
    monkeypatch.setattr(render_routes, "_stage_slots", api_state.BoundedSemaphore(1))
    monkeypatch.setattr(
        api_state,
        "_stage_stats",
        {"submitted": 0, "completed": 0, "failed": 0, "timed_out": 0, "rejected": 0},
    )

    def slow_operation():
        time.sleep(0.12)
        return "late"

    try:
        with pytest.raises(render_routes.StageHardTimeoutError):
            render_routes._run_with_hard_timeout("stage-test", 0.01, slow_operation)
        with pytest.raises(render_routes.StageHardTimeoutError):
            render_routes._run_with_hard_timeout("stage-test", 0.01, lambda: "blocked")

        time.sleep(0.14)
        assert render_routes._run_with_hard_timeout("stage-test", 0.05, lambda: "ok") == "ok"
        assert api_state._stage_stats["timed_out"] == 1
        assert api_state._stage_stats["rejected"] == 1
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def test_interpret_happy_path(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(render_routes, "interpret_detail", lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None))
    r = client.post("/api/interpret", json={"description": "一滴の墨"}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {
        "ddl": "中心に黒い円を置く。",
        "thinking": None,
        "instruction_lang_requested": "auto",
        "instruction_lang_resolved": "ja",
        "ui_lang": None,
    }


def test_interpret_sanitizes_random_placement(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("赤い小さな円をランダムに十二個散らす。", None),
    )
    r = client.post("/api/interpret", json={"description": "赤い点を散らす"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["ddl"] == "赤い小さな円を画面全体に点々と十二個散らす。"


def test_interpret_empty_rejected(auth_context):
    headers, _, _ = auth_context
    r = client.post("/api/interpret", json={"description": ""}, headers=headers)
    assert r.status_code == 422


def _capturing_interpret(seen: list[str]):
    def fake_interpret(text, *args, **kwargs):
        seen.append(text)
        return ("中心に黒い円を置く。", None)

    return fake_interpret


def test_interpret_reads_the_description_when_no_stage1_input(monkeypatch, auth_context):
    """A client that injects no context sends only the description, and Stage 1 reads it."""
    headers, _, _ = auth_context
    seen: list[str] = []
    monkeypatch.setattr(render_routes, "interpret_detail", _capturing_interpret(seen))
    r = client.post("/api/interpret", json={"description": "一滴の墨"}, headers=headers)
    assert r.status_code == 200
    assert seen == ["一滴の墨"]


def test_interpret_reads_the_stage1_input_when_it_is_sent(monkeypatch, auth_context):
    """The augmented text is what Stage 1 reads; the description stays the author's own."""
    headers, _, _ = auth_context
    seen: list[str] = []
    monkeypatch.setattr(render_routes, "interpret_detail", _capturing_interpret(seen))
    r = client.post(
        "/api/interpret",
        json={"description": "一滴の墨", "stage1_input": "一滴の墨\n\n感情: 静か"},
        headers=headers,
    )
    assert r.status_code == 200
    assert seen == ["一滴の墨\n\n感情: 静か"]


def test_paint_keeps_the_augmented_text_out_of_the_history(monkeypatch, auth_context):
    """What is saved is the description, not the string Stage 1 was handed."""
    headers, user, _ = auth_context
    seen: list[str] = []
    monkeypatch.setattr(render_routes, "interpret_detail", _capturing_interpret(seen))
    monkeypatch.setattr(
        render_routes,
        "compose",
        lambda ddl, model=None: Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
        ),
    )

    r = client.post(
        "/api/paint",
        json={
            "description": "一滴の墨",
            "stage1_input": "一滴の墨\n\n感情: 静か",
            "save_history": True,
        },
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert seen == ["一滴の墨\n\n感情: 静か"]

    history = client.get("/api/history", headers=headers).json()
    item = next(entry for entry in history["items"] if entry["id"] == data["history_id"])
    assert item["input"] == "一滴の墨"

    db.delete_items(user["id"], [data["history_id"]])


def test_compose_hands_coerce_the_ddl_alone_over_http(monkeypatch, auth_context):
    """旧名 `test_compose_uses_original_text_for_coerce_suppression`。

    契約 description-propagation-cut (2026-08-04) で裏返した表明。旧版は
    「記述が coerce の分岐を抑える」ことを instruction 数で表明していた。
    その経路が本契約の切る対象であり、いま記述は coerce へ届かない。
    表明は同じ入口 (HTTP) で、coerce が受け取る文字列そのものへ移した。
    """
    headers, _, _ = auth_context
    seen: list[str] = []

    def fake_compose(ddl: str, model=None, system_prompt=None, lang="ja", **kwargs):
        return Score.model_validate(
            {"instructions": [{"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5], "color": "black"}]}
        )

    real_coerce = render_routes.coerce_score

    def recording_coerce(score, *, ddl="", **kwargs):
        seen.append(ddl)
        return real_coerce(score, ddl=ddl, **kwargs)

    monkeypatch.setattr(render_routes, "compose", fake_compose)
    monkeypatch.setattr(render_routes, "coerce_score", recording_coerce)

    r = client.post(
        "/api/compose",
        json={
            "ddl": "黒い線を置く。",
            "description": "白い余白に、黒い線だけを残す。",
        },
        headers=headers,
    )

    assert r.status_code == 200
    assert seen == ["黒い線を置く。"]
    assert "白い余白" not in seen[0]
    instructions = r.json()["score"]["instructions"]
    assert instructions[0]["primitive"] == "line"
    assert r.json()["render_build_number"]
    assert r.json()["render_color_profile"] == {
        "id": "srgb",
        "name": "sRGB IEC61966-2.1",
        "standard": "IEC 61966-2-1:1999",
    }
    assert r.json()["render_engine_id"] == "default"
    assert r.json()["render_engine_version"] == "32"
    assert r.json()["ddl_version"] == "3"
    assert r.json()["ddl_engine_version"] == "15"
    assert r.json()["render_canvas_aspect"] == "square"
    assert r.json()["render_canvas_aspect_id"] == "square"
    assert r.json()["render_canvas_aspect_ratio"] == 1.0
    assert r.json()["render_color_catalog_id"] == "default"
    assert r.json()["render_color_catalog_name"] == "inku Default"
    assert "render_color_catalog" not in r.json()
    assert r.json()["render_color_map"]["black"] == "#111111"


def test_paint_pipeline(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(render_routes, "interpret_detail", lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None))
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/paint", json={"description": "一滴の墨"}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["description"] == "一滴の墨"
    assert "黒い円を置く。" in data["ddl"]
    assert "中心" not in data["ddl"]
    assert data["score"]["instructions"][0]["primitive"] == "circle"
    assert "<svg" in data["svg"]
    assert data["stage1_model"] == "nvidia:google/gemma-4-31b-it"
    assert data["stage2_model"] == "nvidia:google/gemma-4-31b-it"
    assert data["render_build_number"]
    assert data["render_color_profile"] == {
        "id": "srgb",
        "name": "sRGB IEC61966-2.1",
        "standard": "IEC 61966-2-1:1999",
    }
    assert data["render_engine_id"] == "default"
    assert data["render_engine_version"] == "32"
    assert data["ddl_version"] == "3"
    assert data["ddl_engine_version"] == "15"
    assert data["render_canvas_aspect"] == "square"
    assert data["render_canvas_aspect_id"] == "square"
    assert data["render_canvas_aspect_ratio"] == 1.0
    assert data["render_color_catalog_id"] == "default"
    assert data["render_color_catalog_name"] == "inku Default"
    assert "render_color_catalog" not in data
    assert data["render_color_map"]["black"] == "#111111"
    assert data["user_generation_count"] == 1

    skipped_count = client.post(
        "/api/paint",
        json={"description": "一滴の墨", "count_generation": False},
        headers=headers,
    )
    assert skipped_count.status_code == 200
    assert skipped_count.json().get("user_generation_count") is None

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["image_generation_count"] == 1


def test_paint_prompt_digests_round_trip_without_changing_rh3(
    monkeypatch, auth_context
):
    headers, user, _ = auth_context

    def fake_interpret(text: str, prompt_metadata=None, **kwargs):
        prompt_metadata.update(
            {
                "stage1_prompt_digest": "1111111111111111",
                "stage1_prompt_base_digest": "2222222222222222",
            }
        )
        return "黒い円を置く。", None, 1, 2

    fake_score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.1,
                }
            ]
        }
    )

    def fake_compose(ddl: str, prompt_metadata=None, **kwargs):
        prompt_metadata["stage2_prompt_digest"] = "3333333333333333"
        return fake_score, 3, 4

    monkeypatch.setattr(render_routes, "interpret_detail", fake_interpret)
    monkeypatch.setattr(render_routes, "compose", fake_compose)

    response = client.post(
        "/api/paint",
        json={
            "description": "一滴の墨",
            "save_history": True,
            "save_artifacts": False,
            "count_generation": False,
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stage1_prompt_digest"] == "1111111111111111"
    assert data["stage1_prompt_base_digest"] == "2222222222222222"
    assert data["stage2_prompt_digest"] == "3333333333333333"

    history = client.get("/api/history", headers=headers).json()["items"]
    item = next(entry for entry in history if entry["id"] == data["history_id"])
    assert item["stage1_prompt_digest"] == "1111111111111111"
    assert item["stage1_prompt_base_digest"] == "2222222222222222"
    assert item["stage2_prompt_digest"] == "3333333333333333"

    without_digests = {
        key: value
        for key, value in item.items()
        if key
        not in {
            "stage1_prompt_digest",
            "stage1_prompt_base_digest",
            "stage2_prompt_digest",
        }
    }
    assert db.render_hash_for_item(item) == db.render_hash_for_item(without_digests)

    db.delete_items(user["id"], [data["history_id"]])


def _stream_events(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_paint_stream_emits_stage1_before_done(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None),
    )
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/paint/stream", json={"description": "一滴の墨"}, headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")

    events = _stream_events(r)
    assert [e["event"] for e in events] == ["stage1", "done"]

    stage1 = events[0]
    assert "黒い円を置く。" in stage1["ddl"]
    assert stage1["stage1_model"] == "nvidia:google/gemma-4-31b-it"
    assert stage1["stage2_model"] == "nvidia:google/gemma-4-31b-it"
    assert stage1["elapsed_ms"] >= 0
    assert stage1["interpret_fallback_used"] is False

    # The done event carries the Stage 2 DDL, which may rewrite the Stage 1 text.
    done = events[1]
    assert "黒い円を置く。" in done["ddl"]
    assert done["score"]["instructions"][0]["primitive"] == "circle"
    assert "<svg" in done["svg"]
    assert done["render_canvas_aspect_id"] == "square"


def test_paint_stream_matches_paint_response_shape(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("黒い円を置く。", None),
    )
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    payload = {"description": "一滴の墨", "save_history": False, "count_generation": False}
    plain = client.post("/api/paint", json=payload, headers=headers)
    streamed = _stream_events(
        client.post("/api/paint/stream", json=payload, headers=headers)
    )[-1]
    assert plain.status_code == 200

    volatile = {"elapsed_stage1_ms", "elapsed_stage2_ms", "elapsed_total_ms", "event"}
    assert set(streamed) - volatile == set(plain.json()) - volatile


def test_paint_stream_reports_compose_failure_as_error_event(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("黒い円を置く。", None),
    )

    def fail_compose(*args, **kwargs):
        raise RuntimeError("compose failed for test")

    monkeypatch.setattr(render_routes, "compose", fail_compose)

    r = client.post("/api/paint/stream", json={"description": "壊れる描画"}, headers=headers)
    assert r.status_code == 200

    events = _stream_events(r)
    assert [e["event"] for e in events] == ["stage1", "error"]
    assert events[1]["status"] == 502


def test_paint_records_input_and_expanded_ddl_separately(monkeypatch, auth_context):
    headers, user, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None),
    )
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post(
        "/api/paint", json={"description": "一滴の墨", "save_history": True}, headers=headers
    )
    assert r.status_code == 200
    data = r.json()
    # ddl は Stage 2 に渡った展開後、source_ddl は展開前の入力側。
    assert data["source_ddl"] == "中心に黒い円を置く。"
    assert data["ddl"] != data["source_ddl"]

    listing = client.get(
        "/api/history", params={"anchor_id": data["history_id"], "limit": 100}, headers=headers
    ).json()
    saved = next(item for item in listing["items"] if item["id"] == data["history_id"])
    assert saved["ddl"] == data["source_ddl"]
    assert saved["expanded_ddl"] == data["ddl"]
    db.delete_items(user["id"], [data["history_id"]])


def _stub_stages(monkeypatch):
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None),
    )
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)


def test_focus_is_no_longer_an_api_input_but_is_still_recorded(monkeypatch, auth_context):
    """v2.0: 焦点は外部入力から外れ、展開層が決めた結果だけが記録される。"""
    headers, _, _ = auth_context
    _stub_stages(monkeypatch)

    default = client.post("/api/paint", json={"description": "一滴の墨"}, headers=headers).json()
    # 送っても無視される（機構は残るが口は閉じた）。
    sent = client.post(
        "/api/paint", json={"description": "一滴の墨", "focus": "lower_right"}, headers=headers
    ).json()
    assert sent["ddl"] == default["ddl"]

    # history.focus の供給源は展開層。変奏なしでも既定のハッシュ選択が載る。
    assert default["focus"] in FOCUS_IDS
    assert focus_word(default["focus"], lang="ja") in default["ddl"]


def test_variation_needs_both_amplitude_and_seed(monkeypatch, auth_context):
    headers, _, _ = auth_context
    _stub_stages(monkeypatch)
    body = {"description": "一滴の墨"}
    default = client.post("/api/paint", json=body, headers=headers).json()

    for partial in ({"variation_amplitude": "large"}, {"variation_seed": 7}):
        response = client.post("/api/paint", json={**body, **partial}, headers=headers).json()
        assert response["ddl"] == default["ddl"]
        assert response["variation_moved_axes"] == []

    unknown = client.post(
        "/api/paint",
        json={**body, "variation_amplitude": "huge", "variation_seed": 7},
        headers=headers,
    ).json()
    assert unknown["ddl"] == default["ddl"]


def test_variation_moves_the_expansion_and_reports_the_axes(monkeypatch, auth_context):
    headers, _, _ = auth_context
    _stub_stages(monkeypatch)
    body = {"description": "一滴の墨"}
    default = client.post("/api/paint", json=body, headers=headers).json()

    varied = client.post(
        "/api/paint",
        json={**body, "variation_amplitude": "large", "variation_seed": 7},
        headers=headers,
    ).json()
    assert varied["ddl"] != default["ddl"]
    assert varied["variation_amplitude"] == "large"
    assert varied["variation_seed"] == 7
    assert varied["variation_moved_axes"]
    for entry in varied["variation_moved_axes"]:
        assert set(entry) == {"axis", "from", "to"}
        assert entry["from"] != entry["to"]

    # 同じ (強度, seed) は同じ展開を再現する。
    replay = client.post(
        "/api/paint",
        json={**body, "variation_amplitude": "large", "variation_seed": 7},
        headers=headers,
    ).json()
    assert replay["ddl"] == varied["ddl"]
    assert replay["variation_moved_axes"] == varied["variation_moved_axes"]


def test_history_records_the_focus_the_expander_landed_on(monkeypatch, auth_context):
    """v2.0: focus 推敲を外しても history.focus は NULL にならない。

    moved_axes は列を持たず決定的に再計算するので、その入力である焦点と
    (強度, seed) が保存されていることが再現の前提になる。
    """
    headers, user, _ = auth_context
    _stub_stages(monkeypatch)

    response = client.post(
        "/api/paint",
        json={
            "description": "一滴の墨",
            "save_history": True,
            "variation_amplitude": "large",
            "variation_seed": 11,
        },
        headers=headers,
    ).json()
    listing = client.get(
        "/api/history",
        params={"anchor_id": response["history_id"], "limit": 100},
        headers=headers,
    ).json()
    saved = next(item for item in listing["items"] if item["id"] == response["history_id"])
    assert saved["focus"] == response["focus"]
    assert saved["focus"] in FOCUS_IDS
    assert saved["variation_amplitude"] == "large"
    assert str(saved["variation_seed"]) == "11"
    db.delete_items(user["id"], [response["history_id"]])


def test_variation_seeds_are_allocated_server_side(auth_context):
    headers, _, _ = auth_context
    response = client.post(
        "/api/variation/seeds", json={"amplitude": "medium", "count": 4}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["amplitude"] == "medium"
    assert len(body["seeds"]) == 4
    assert len(set(body["seeds"])) == 4
    assert all(seed > 0 for seed in body["seeds"])

    rejected = client.post(
        "/api/variation/seeds", json={"amplitude": "huge"}, headers=headers
    )
    assert rejected.status_code == 422


def test_compose_returns_source_ddl(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post("/api/compose", json={"ddl": "中心に黒い円を置く。"}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["source_ddl"] == "中心に黒い円を置く。"
    assert data["ddl"] != data["source_ddl"]


def test_empty_stage1_output_falls_back_instead_of_drawing_nothing(monkeypatch, auth_context):
    headers, user, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("   ", None),
    )
    captured = {}

    def fake_compose(ddl, model=None):
        captured["ddl"] = ddl
        return Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
        )

    monkeypatch.setattr(render_routes, "compose", fake_compose)

    r = client.post(
        "/api/paint", json={"description": "空を返すモデル", "save_history": True}, headers=headers
    )
    assert r.status_code == 200
    data = r.json()
    assert data["interpret_fallback_used"] is True
    assert data["interpret_fallback_reasons"] == ["stage1_empty_output"]

    # フォールバックで描かれたことを作品に残し、UI がバッジを出せるようにする。
    listing = client.get(
        "/api/history", params={"anchor_id": data["history_id"], "limit": 100}, headers=headers
    ).json()
    saved = next(item for item in listing["items"] if item["id"] == data["history_id"])
    assert saved["interpret_fallback"] == "stage1_empty_output"
    db.delete_items(user["id"], [data["history_id"]])
    # 記述を持たない作品が保存されないよう、決定的フォールバック DDL で描画する。
    assert data["source_ddl"].strip()
    assert data["ddl"].strip()
    assert captured["ddl"].strip()


class _FakeProviderError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_provider_end_of_life_is_reported_as_a_typed_error(monkeypatch, auth_context):
    headers, _, _ = auth_context

    def gone(*args, **kwargs):
        raise _FakeProviderError(
            "Error code: 410 - The model 'x' has reached its end of life.", 410
        )

    monkeypatch.setattr(render_routes, "interpret_detail", gone)

    r = client.post("/api/paint", json={"description": "提供終了モデル"}, headers=headers)
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["code"] == "model_gone"
    assert detail["stage"] == "interpret"
    assert detail["provider_status"] == 410
    # 原文をそのまま渡し、UI が併記できるようにする。
    assert "end of life" in detail["message"]


def test_provider_auth_and_rate_limit_are_distinguished(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("黒い円を置く。", None),
    )

    for status, expected in ((401, "provider_auth"), (429, "provider_rate_limit"), (500, "provider_error")):
        def failing(*args, _status=status, **kwargs):
            raise _FakeProviderError(f"boom {_status}", _status)

        monkeypatch.setattr(render_routes, "compose", failing)
        r = client.post("/api/paint", json={"description": "失敗する描画"}, headers=headers)
        assert r.status_code == 502
        detail = r.json()["detail"]
        assert detail["code"] == expected
        assert detail["stage"] == "compose"
        assert detail["provider_status"] == status

    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)


def test_retired_models_are_marked_eol_in_the_catalog():
    from inku_server.model_settings import default_model_settings

    nvidia = default_model_settings()["providers"]["nvidia"]["models"]
    retired = [model for model in nvidia if model.get("eol")]
    assert any(model["id"] == "qwen/qwen3.5-122b-a10b" for model in retired)
    assert all(model.get("eol_date") for model in retired)


def test_fetch_models_keeps_retired_models_as_eol(monkeypatch):
    """取得ボタンを押しても、過去の作品が参照するモデルの情報を落とさない。"""
    monkeypatch.setenv("INKU_DEVELOPER_MODE", "1")
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"fetch-models-{suffix}")
    admin = db.add_user(
        username=f"fetch-models-admin-{suffix}",
        email=f"fetch-models-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    admin_headers, admin_token = _auth_headers(admin)

    # 提供元は gemma しか返さない状況を作る。
    monkeypatch.setattr(
        settings_routes,
        "_fetch_provider_model_list",
        lambda provider_id, settings: [{"id": "google/gemma-4-31b-it", "label": "google/gemma-4-31b-it"}],
    )
    r = client.post("/api/settings/models/nvidia/fetch-models", headers=admin_headers)
    assert r.status_code == 200

    models = {
        model["id"]: model
        for provider in r.json()["catalog"]
        if provider["id"] == "nvidia"
        for model in provider["models"]
    }
    # 提供が続くモデルは EOL 印が付かず、整えたラベルと評価が残る。
    assert models["google/gemma-4-31b-it"].get("eol") is not True
    assert models["google/gemma-4-31b-it"]["label"] == "Google Gemma 4 31B Instruct"
    assert models["google/gemma-4-31b-it"]["recommendation_llm"] == 4
    # 提供が消えたモデルは一覧から消えず、EOL として日付付きで残る。
    retired = models["mistralai/mistral-medium-3.5-128b"]
    assert retired["eol"] is True
    assert retired["eol_date"]
    assert retired["comment_ja"]

    # 共有 DB を元の一覧へ戻す（他テストがカタログ件数を前提にしているため）。
    db.update_model_settings(default_model_settings())
    db.delete_session(admin_token)
    db.delete_user(admin["id"])
    db.delete_user_group(group["id"])


def test_paint_stream_requires_auth():
    assert client.post("/api/paint/stream", json={"description": "一滴の墨"}).status_code == 401


def test_generation_count_increment_is_atomic_under_concurrency():
    suffix = uuid.uuid4().hex[:8]
    user = db.add_user(
        username=f"counter-{suffix}",
        email=f"counter-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=None,
    )
    try:
        count = 40
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = [
                future.result()
                for future in as_completed(
                    [executor.submit(db.increment_user_generation_count, user["id"]) for _ in range(count)]
                )
            ]

        assert all(isinstance(result, int) for result in results)
        assert db.get_user(user["id"])["image_generation_count"] == count
    finally:
        db.delete_user(user["id"])


def test_paint_stage1_hard_timeout_uses_fallback_ddl(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setenv("INKU_STAGE1_HARD_TIMEOUT_SECONDS", "0.01")

    def slow_interpret(text, model=None, include_thinking=False, system_prompt_prefix=None, lang="ja"):
        time.sleep(0.2)
        return "中心に黒い円を置く。", None, None, None

    captured: dict[str, str] = {}

    def fake_compose(ddl: str, model=None, original_description=None, system_prompt=None, lang="ja", **kwargs):
        captured["ddl"] = ddl
        return Score.model_validate(
            {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}]}
        )

    monkeypatch.setattr(render_routes, "interpret_detail", slow_interpret)
    monkeypatch.setattr(render_routes, "compose", fake_compose)

    r = client.post("/api/paint", json={"description": "応答しない指示"}, headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["interpret_fallback_used"] is True
    assert data["interpret_fallback_reasons"] == ["stage1_hard_timeout"]
    assert "斜めの線を三本" in data["ddl"]
    assert captured["ddl"] == data["ddl"]


def test_failed_paint_does_not_increment_generation_count(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(render_routes, "interpret_detail", lambda text, model=None, include_thinking=False: ("黒い円を置く。", None))

    def fail_compose(*args, **kwargs):
        raise RuntimeError("compose failed for test")

    monkeypatch.setattr(render_routes, "compose", fail_compose)

    r = client.post("/api/paint", json={"description": "壊れる描画"}, headers=headers)
    assert r.status_code == 502

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["image_generation_count"] == 0


def test_paint_sanitizes_stage1_before_compose(monkeypatch, auth_context):
    headers, _, _ = auth_context
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("赤い小さな円をランダムに十二個散らす。", None),
    )

    def fake_compose(ddl: str, model=None):
        captured["ddl"] = ddl
        return Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
        )

    monkeypatch.setattr(render_routes, "compose", fake_compose)
    r = client.post("/api/paint", json={"description": "赤い点を散らす"}, headers=headers)
    assert r.status_code == 200
    assert "赤い小さな円を画面全体に点々と十二個散らす。" in r.json()["ddl"]
    # Same as the compose route: no appended candidate sentence (v2.11.0).
    assert not any(marker in r.json()["ddl"] for marker in EXPANSION_MARKERS)
    assert r.json()["ddl"] == captured["ddl"]


def test_paint_random_catalog_excludes_current_and_uses_effective_map(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(
        render_routes,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None),
    )
    fake_score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.1,
                    "color": "black",
                }
            ]
        }
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)
    captured_candidates: list[str] = []

    def choose_first(candidates: list[str]) -> str:
        captured_candidates.extend(candidates)
        return candidates[0]

    monkeypatch.setattr(render_routes.secrets, "choice", choose_first)

    response = client.post(
        "/api/paint",
        json={
            "description": "一滴の墨",
            "catalog_id": "ink_season",
            "catalog_mode": "random",
            "count_generation": False,
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert captured_candidates
    assert "ink_season" not in captured_candidates
    assert data["render_color_catalog_id"] == captured_candidates[0]
    assert data["render_color_catalog_id"] != "ink_season"
    assert data["catalog_id"] == data["render_color_catalog_id"]
    assert data["render_color_map"] == api_module._catalog_render_color_map(data["render_color_catalog_id"])


def test_paint_can_save_server_generated_history(monkeypatch, auth_context):
    headers, user, _ = auth_context
    monkeypatch.setattr(render_routes, "interpret_detail", lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None))
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post(
        "/api/paint",
        json={
            "description": "一滴の墨",
            "stage1_input": "一滴の墨\n\n感情: 静か",
            "save_history": True,
            "history_input": "一滴の墨",
            "history_at": 1_700_000_000_000,
            "catalog_id": "vivid_material",
            "canvas_aspect": "wide",
            "render_seed": 123,
            "composition_seed": 4,
            "interpretation_seed": "interp-test-seed",
        },
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["history_id"]
    assert data["history_at"] == 1_700_000_000_000
    assert data["render_hash"].startswith("rh3:")
    assert len(data["render_hash"]) == 68
    assert data["render_hash_short"] == data["render_hash"][-4:].upper()
    assert data["render_color_catalog_id"] == "vivid_material"
    assert data["render_color_catalog_name"] == "Vivid Material"
    assert data["render_color_map"]["green"] == "#008f39"
    assert data["render_canvas_aspect"] == "wide"
    assert data["render_canvas_aspect_id"] == "wide"
    assert data["render_canvas_aspect_ratio"] == 2.35
    assert data["render_seed"] == 123
    assert data["composition_seed"] == 4
    assert data["interpretation_seed"] == "interp-test-seed"

    history = client.get("/api/history", headers=headers).json()
    assert history["total"] == 1
    item = history["items"][0]
    assert item["id"] == data["history_id"]
    assert item["render_hash"] == data["render_hash"]
    assert item["render_hash_short"] == data["render_hash_short"]
    assert item["input"] == "一滴の墨"
    assert item["catalog_id"] == "vivid_material"
    assert item["render_build_number"] == data["render_build_number"]
    assert item["render_color_profile"]["id"] == "srgb"
    assert item["render_engine_id"] == "default"
    assert item["render_engine_version"] == "32"
    assert item["ddl_version"] == "3"
    assert item["ddl_engine_version"] == "15"
    assert item["render_canvas_aspect"] == "wide"
    assert item["render_canvas_aspect_id"] == "wide"
    assert item["render_canvas_aspect_ratio"] == 2.35
    assert item["render_color_catalog_id"] == "vivid_material"
    assert item["render_color_catalog_name"] == "Vivid Material"
    assert "render_color_catalog" not in item
    assert item["render_color_map"]["green"] == "#008f39"
    assert item["render_seed"] == 123
    assert item["composition_seed"] == 4
    assert item["interpretation_seed"] == "interp-test-seed"
    assert item["svg"] == data["svg"]

    db.delete_items(user["id"], [data["history_id"]])


def test_render_score_changes_only_catalog_metadata_and_colors(auth_context):
    headers, _, _ = auth_context
    payload = {
        "input": "緑の円",
        "ddl": "中央に緑の円を置く。",
        "score": {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.1,
                    "color": "green",
                }
            ]
        },
        "catalog_id": "vivid_material",
        "canvas_aspect": "square",
        "render_seed": 123,
        "composition_seed": 456,
        "interpretation_seed": "reading-seed",
    }

    response = client.post("/api/render-score", json=payload, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["catalog_id"] == "vivid_material"
    assert data["render_color_catalog_id"] == "vivid_material"
    assert data["render_color_catalog_name"] == "Vivid Material"
    assert data["render_color_map"]["green"] == "#008f39"
    assert data["render_canvas_aspect_id"] == "square"
    assert data["render_seed"] == 123
    assert data["composition_seed"] == 456
    assert data["interpretation_seed"] == "reading-seed"
    assert data["score"]["instructions"][0]["primitive"] == "circle"
    assert data["score"]["instructions"][0]["center"] == [0.5, 0.5]
    assert data["score"]["instructions"][0]["radius"] == 0.1
    assert data["score"]["instructions"][0]["color"] == "green"
    assert data["render_hash"].startswith("rh3:")
    assert data["render_hash_short"]

    alternate = client.post(
        "/api/render-score",
        json={**payload, "catalog_id": "ink_season"},
        headers=headers,
    )
    assert alternate.status_code == 200
    alternate_data = alternate.json()
    assert alternate_data["score"] == data["score"]
    assert alternate_data["render_seed"] == data["render_seed"]
    assert alternate_data["composition_seed"] == data["composition_seed"]
    assert alternate_data["interpretation_seed"] == data["interpretation_seed"]
    assert alternate_data["render_color_catalog_id"] == "ink_season"
    assert alternate_data["render_hash"] != data["render_hash"]
    assert alternate_data["svg"] != data["svg"]


def _h16_coerce_input() -> tuple[dict, str]:
    cases = json.loads(
        (REPO_ROOT / "server/tests/golden/coerce_golden.json").read_text(encoding="utf-8")
    )
    case = cases["cases"]["H-16"]["input"]
    return case["score"], case["ddl"]


def test_render_score_hands_ddl_to_coerce(auth_context):
    headers, _, _ = auth_context
    score, ddl = _h16_coerce_input()

    without_ddl = client.post(
        "/api/render-score",
        json={"score": score, "render_seed": 123},
        headers=headers,
    )
    with_ddl = client.post(
        "/api/render-score",
        json={"score": score, "ddl": ddl, "render_seed": 123},
        headers=headers,
    )

    assert without_ddl.status_code == 200
    assert with_ddl.status_code == 200
    assert len(without_ddl.json()["score"]["instructions"]) == 1
    assert len(with_ddl.json()["score"]["instructions"]) == 4


def test_render_score_passes_the_request_ddl_at_the_coerce_call_site(
    auth_context, monkeypatch
):
    headers, _, _ = auth_context
    score, ddl = _h16_coerce_input()
    seen: list[str | None] = []
    original = render_routes.coerce_score

    def recording_coerce(score_value, *args, ddl=None, **kwargs):
        seen.append(ddl)
        return original(score_value, *args, ddl=ddl, **kwargs)

    monkeypatch.setattr(render_routes, "coerce_score", recording_coerce)

    response = client.post(
        "/api/render-score",
        json={"score": score, "ddl": ddl, "render_seed": 123},
        headers=headers,
    )

    assert response.status_code == 200
    assert seen == [ddl]


def test_render_score_empty_ddl_draws_the_same_svg_as_no_ddl(auth_context):
    headers, _, _ = auth_context
    score, _ = _h16_coerce_input()
    payload = {"score": score, "render_seed": 123}

    absent = client.post("/api/render-score", json=payload, headers=headers)
    empty = client.post(
        "/api/render-score", json={**payload, "ddl": ""}, headers=headers
    )

    assert absent.status_code == 200
    assert empty.status_code == 200
    assert empty.json()["score"] == absent.json()["score"]
    assert empty.json()["svg"] == absent.json()["svg"]


def test_render_score_without_ddl_matches_the_old_render_svg_drawing(auth_context):
    headers, _, _ = auth_context
    score, _ = _h16_coerce_input()
    payload = {
        "score": score,
        "catalog_id": "default",
        "canvas_aspect": "square",
        "svg_profile": "display",
        "render_seed": 123,
        "composition_seed": 456,
    }

    old_endpoint = client.post("/api/render-svg", json=payload, headers=headers)
    named_endpoint = client.post("/api/render-score", json=payload, headers=headers)

    assert old_endpoint.status_code == 200
    assert named_endpoint.status_code == 200
    assert named_endpoint.json()["svg"] == old_endpoint.text


def test_render_score_keeps_the_requested_svg_profile(auth_context):
    headers, _, _ = auth_context

    response = client.post(
        "/api/render-score",
        json={
            "score": {
                "instructions": [
                    {
                        "primitive": "line",
                        "from": [0.0, 0.5],
                        "to": [1.0, 0.5],
                        "weight": "pencil",
                    }
                ]
            },
            "svg_profile": "editable",
            "render_seed": 123,
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert 'id="layer_10_content"' in response.json()["svg"]
    assert 'id="mark_000_000_line"' in response.json()["svg"]


def test_render_svg_endpoint_generates_editable_profile(auth_context):
    headers, _, _ = auth_context
    r = client.post(
        "/api/render-svg",
        json={
            "svg_profile": "editable",
            "score": {
                "instructions": [
                    {"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5], "weight": "pencil"}
                ]
            },
        },
        headers=headers,
    )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert 'id="layer_10_content"' in r.text
    assert 'id="mark_000_000_line"' in r.text
    assert "filter=" not in r.text


def test_history_svg_endpoint_keeps_display_svg_and_regenerates_editable(auth_context):
    headers, user, _ = auth_context
    item = db.add_item({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "output_path": None,
        "input": "editable svg",
        "ddl": "線",
        "score": {"instructions": [{"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}]},
        "svg": "<svg><desc>stored display</desc></svg>",
        "at": 1_700_000_000_001,
    })

    display = client.get(f"/api/history/{item['id']}/svg?profile=display", headers=headers)
    editable = client.get(f"/api/history/{item['id']}/svg?profile=editable", headers=headers)

    assert display.status_code == 200
    assert display.text == "<svg><desc>stored display</desc></svg>"
    assert editable.status_code == 200
    assert "<title>inku render (editable SVG)</title>" in editable.text
    assert 'id="layer_10_content"' in editable.text

    db.delete_items(user["id"], [item["id"]])


def test_paint_resolves_catalog_id_on_server(monkeypatch, auth_context):
    headers, _, _ = auth_context
    monkeypatch.setattr(render_routes, "interpret_detail", lambda text, model=None, include_thinking=False: ("緑の円を置く。", None))
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1, "color": "green"}]}
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

    r = client.post(
        "/api/paint",
        json={"description": "緑の円", "catalog_id": "vivid_material"},
        headers=headers,
    )

    assert r.status_code == 200
    data = r.json()
    assert data["catalog_id"] == "vivid_material"
    assert data["render_color_catalog_id"] == "vivid_material"
    assert data["render_color_map"]["green"] == "#008f39"
    assert data["render_color_map"]["palette:Fresh Green"] == "#008f39"
    assert "#008f39" in data["svg"]


def test_paint_rejects_unknown_catalog_id(auth_context):
    headers, _, _ = auth_context
    r = client.post("/api/paint", json={"description": "緑の円", "catalog_id": "missing"}, headers=headers)
    assert r.status_code == 422
    assert "unsupported color catalog" in r.json()["detail"]


def test_cors_allows_localhost(monkeypatch, auth_context):
    headers, _, _ = auth_context
    fake_score = Score.model_validate(
        {"instructions": [{"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}]}
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, model=None: fake_score)

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
        if name == "resvg_py":
            raise ImportError(f"missing {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    caplog.set_level(logging.WARNING, logger=api_module.__name__)

    prefix = tmp_path / "out" / "sample"
    api_rendering._save_output_files(
        prefix,
        "input text",
        "normalized ddl",
        {"instructions": []},
        "<svg></svg>",
        {
            "render_build_number": "260",
            "render_color_profile": {
                "id": "srgb",
                "name": "sRGB IEC61966-2.1",
                "standard": "IEC 61966-2-1:1999",
            },
            "render_engine_id": "default",
            "render_engine_version": "2",
            "render_color_catalog_id": "default",
            "render_color_catalog_name": "inku Default",
            "render_color_catalog_sub": "neutral baseline",
            "render_color_map": {"black": "#111111"},
            "render_canvas_aspect": "square",
            "render_canvas_aspect_id": "square",
            "render_canvas_aspect_ratio": 1.0,
            "render_hash": "a" * 64,
            "render_hash_short": "AAAA",
            "stage1_prompt_digest": "1111111111111111",
            "stage1_prompt_base_digest": "2222222222222222",
            "stage2_prompt_digest": "3333333333333333",
        },
        {
            "stage1_model": "stage1",
            "stage2_model": "stage2",
        },
    )

    assert (tmp_path / "out" / "sample_instruction.txt").read_text(encoding="utf-8") == "input text"
    assert (tmp_path / "out" / "sample_normalized.ddl").read_text(encoding="utf-8") == "normalized ddl"
    saved_score = json.loads((tmp_path / "out" / "sample_score.json").read_text(encoding="utf-8"))
    assert saved_score["stage1_model"] == "stage1"
    assert saved_score["stage2_model"] == "stage2"
    assert saved_score["render_build_number"] == "260"
    assert saved_score["render_color_profile"]["id"] == "srgb"
    assert saved_score["render_engine_id"] == "default"
    assert saved_score["render_engine_version"] == "2"
    assert saved_score["render_color_catalog_id"] == "default"
    assert saved_score["render_color_catalog_name"] == "inku Default"
    assert "render_color_catalog" not in saved_score
    assert saved_score["render_color_map"]["black"] == "#111111"
    assert saved_score["render_canvas_aspect"] == "square"
    assert saved_score["render_canvas_aspect_id"] == "square"
    assert saved_score["render_canvas_aspect_ratio"] == 1.0
    assert saved_score["render_hash"] == "a" * 64
    assert saved_score["render_hash_short"] == "AAAA"
    assert saved_score["stage1_prompt_digest"] == "1111111111111111"
    assert saved_score["stage1_prompt_base_digest"] == "2222222222222222"
    assert saved_score["stage2_prompt_digest"] == "3333333333333333"
    assert saved_score["score"] == {"instructions": []}
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
        permission_groups=["users"],
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
    saved_score = json.loads((tmp_path / "outputs" / "sample_score.json").read_text(encoding="utf-8"))
    assert saved_score["render_hash"] == item["render_hash"]
    assert saved_score["render_hash_short"] == item["render_hash_short"]
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

    monkeypatch.setattr(api_rendering, "_save_slots", FullSlots())
    monkeypatch.setattr(api_rendering, "_save_executor", FailingExecutor())
    caplog.set_level(logging.WARNING, logger=api_module.__name__)

    assert api_rendering._submit_history_artifact_save({"id": "history-full"}) is False
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
    monkeypatch.setattr(api_rendering, "_save_slots", slots)
    monkeypatch.setattr(api_rendering, "_save_executor", InlineExecutor())
    monkeypatch.setattr(api_rendering, "_save_history_artifacts", lambda item: saved.append(item["id"]))

    assert api_rendering._submit_history_artifact_save({"id": "history-ok"}) is True
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
    monkeypatch.setattr(api_rendering, "_save_slots", slots)
    monkeypatch.setattr(api_rendering, "_save_executor", FailingExecutor())
    caplog.set_level(logging.ERROR, logger=api_module.__name__)

    assert api_rendering._submit_history_artifact_save({"id": "history-submit-fail"}) is False
    assert slots.released == 1
    assert "failed to submit artifact save job" in caplog.text


def test_settings_status_is_admin_only(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_BACKUP_DIR", tmp_path / "db-backups")
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"settings-{suffix}")
    admin = db.add_user(
        username=f"settings-admin-{suffix}",
        email=f"settings-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    user = db.add_user(
        username=f"settings-user-{suffix}",
        email=f"settings-user-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
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
    assert "file_size_bytes" in data["database"]
    assert data["database"]["runtime_editable"] is False
    assert "INKU_DB_URL" in data["database"]["note"]
    assert data["db_backup"]["supported"] is True
    assert data["db_backup"]["interval_days"] == 7
    assert data["db_backup"]["max_generations"] == 4
    assert data["plugins"]["enabled"] is True
    assert data["plugins"]["runtime_editable"] is True
    assert data["plugins"]["loaded"][0] == {
        "name": "canvas-aspect",
        "namespace": "system",
        "version": "0.1.0",
        "status": "enabled",
        "entries": [],
        "reasons": [],
    }
    assert data["output_save"]["workers"] >= 1
    assert data["output_save"]["queue_limit"] >= data["output_save"]["workers"]
    assert data["output_save"]["enabled"] is True
    assert data["output_save"]["output_dir"]
    assert data["output_save"]["png_size"] > 0
    assert {"submitted", "completed", "failed", "skipped"} <= set(data["output_save"])
    assert "source of truth" in data["output_save"]["note"]
    assert data["log_retention"]["enabled"] is True
    assert data["log_retention"]["retention_days"] == 90
    assert data["log_retention"]["rotate"] == "daily"
    assert data["log_retention"]["compress"] is True
    # The screen used to hand out a systemd drop-in and a logrotate snippet; it
    # now names the directory the application writes to itself (ledger I-167).
    assert data["log_retention"]["log_dir"]
    assert isinstance(data["log_retention"]["files"], list)
    assert "the application executes it" in data["log_retention"]["note"]
    assert data["stage_execution"]["workers"] >= 1
    assert data["stage_execution"]["queue_limit"] >= data["stage_execution"]["workers"]
    assert {"submitted", "completed", "failed", "timed_out", "rejected"} <= set(data["stage_execution"])
    assert "bounded executor" in data["stage_execution"]["note"]

    db.delete_session(admin_token)
    db.delete_session(user_token)
    db.delete_user(admin["id"])
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_db_backup_settings_and_manual_run_are_admin_only(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_BACKUP_DIR", tmp_path / "db-backups")
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"db-backup-{suffix}")
    user = db.add_user(
        username=f"db-backup-user-{suffix}",
        email=f"db-backup-user-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    admin = db.add_user(
        username=f"db-backup-admin-{suffix}",
        email=f"db-backup-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    user_headers, user_token = _auth_headers(user)
    admin_headers, admin_token = _auth_headers(admin)
    try:
        assert client.put(
            "/api/settings/db-backup",
            headers=user_headers,
            json={"interval_days": 3, "max_generations": 2},
        ).status_code == 403

        settings_r = client.put(
            "/api/settings/db-backup",
            headers=admin_headers,
            json={"interval_days": 3, "max_generations": 2},
        )
        assert settings_r.status_code == 200
        assert settings_r.json()["interval_days"] == 3
        assert settings_r.json()["max_generations"] == 2

        run_r = client.post("/api/settings/db-backup/run", headers=admin_headers)
        assert run_r.status_code == 200
        data = run_r.json()
        assert data["manual"] is True
        assert data["size_bytes"] > 0
        assert (tmp_path / "db-backups" / "manual").exists()
    finally:
        db.delete_session(admin_token)
        db.delete_session(user_token)
        db.delete_user(admin["id"])
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])


def test_reading_the_settings_panel_does_not_write_a_backup(tmp_path, monkeypatch):
    """The reload button reads; the scheduler writes.

    last_auto_backup_at = 0 makes a copy due right now, so a status read that
    still carried the old ensure_scheduled_db_backup() call would leave a file
    behind and fail here.
    """
    monkeypatch.setattr(db, "_DB_BACKUP_DIR", tmp_path / "db-backups")
    settings = db.get_db_backup_settings()
    settings["last_auto_backup_at"] = 0
    db._write_app_setting(db._DB_BACKUP_SETTINGS_KEY, settings)
    assert db.next_scheduled_db_backup_at() == 0  # i.e. due

    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"db-readonly-{suffix}")
    admin = db.add_user(
        username=f"db-readonly-admin-{suffix}",
        email=f"db-readonly-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    admin_headers, admin_token = _auth_headers(admin)
    try:
        assert client.get("/api/settings/status", headers=admin_headers).status_code == 200
        auto_dir = tmp_path / "db-backups" / "auto"
        assert not auto_dir.exists() or list(auto_dir.glob("*.db")) == []
    finally:
        db.delete_session(admin_token)
        db.delete_user(admin["id"])
        db.delete_user_group(group["id"])


def test_lifespan_starts_and_cancels_the_backup_scheduler(monkeypatch):
    """Without this the hour and minute would be settings nothing ever reads.

    The old code only checked whether a backup was due inside GET
    /api/settings/status, so the schedule fired when an admin opened the panel.
    """
    ran: list[str] = []

    async def fake_loop() -> None:
        ran.append("start")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            ran.append("cancelled")
            raise

    monkeypatch.setattr(api_module, "_db_backup_scheduler_loop", fake_loop)

    async def drive() -> None:
        async with api_module._lifespan(app):
            await asyncio.sleep(0)

    asyncio.run(drive())
    assert ran == ["start", "cancelled"]

    ran.clear()
    monkeypatch.setenv("INKU_DB_BACKUP_SCHEDULER", "0")
    asyncio.run(drive())
    assert ran == []


def test_db_backup_scheduler_loop_asks_the_due_check_each_tick(monkeypatch):
    calls: list[int] = []

    def fake_due_check() -> None:
        calls.append(len(calls))
        return None

    monkeypatch.setattr(api_module._db, "ensure_scheduled_db_backup", fake_due_check)

    async def stop_on_second_tick(_seconds: float) -> None:
        if len(calls) >= 2:
            raise asyncio.CancelledError
    monkeypatch.setattr(api_module.asyncio, "sleep", stop_on_second_tick)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(api_module._db_backup_scheduler_loop())
    assert calls == [0, 1]


def test_db_backup_scheduler_loop_survives_a_failing_backup(monkeypatch, caplog):
    calls: list[int] = []

    def boom() -> None:
        calls.append(len(calls))
        raise OSError("disk went away")

    monkeypatch.setattr(api_module._db, "ensure_scheduled_db_backup", boom)

    async def stop_on_second_tick(_seconds: float) -> None:
        if len(calls) >= 2:
            raise asyncio.CancelledError
    monkeypatch.setattr(api_module.asyncio, "sleep", stop_on_second_tick)

    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        asyncio.run(api_module._db_backup_scheduler_loop())
    assert calls == [0, 1]
    assert "scheduled DB backup failed" in caplog.text


def test_db_backup_schedule_time_round_trips_and_moves_the_due_moment(tmp_path, monkeypatch):
    """The stored hour and minute must be the ones that decide when a copy is due.

    Both values are deliberately away from the 3:00 default, so a regression that
    drops the write and falls back to the default fails instead of passing.
    """
    monkeypatch.setattr(db, "_DB_BACKUP_DIR", tmp_path / "db-backups")
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"db-schedule-{suffix}")
    admin = db.add_user(
        username=f"db-schedule-admin-{suffix}",
        email=f"db-schedule-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    admin_headers, admin_token = _auth_headers(admin)
    try:
        saved = client.put(
            "/api/settings/db-backup",
            headers=admin_headers,
            json={"interval_days": 3, "max_generations": 2, "backup_hour": 22, "backup_minute": 45},
        )
        assert saved.status_code == 200
        assert saved.json()["backup_hour"] == 22
        assert saved.json()["backup_minute"] == 45

        last = datetime(2026, 7, 20, 9, 15)
        db.update_db_backup_settings(3, 2, 22, 45)
        settings = db.get_db_backup_settings()
        settings["last_auto_backup_at"] = int(last.timestamp() * 1000)

        due = db.next_scheduled_db_backup_at(settings)
        assert datetime.fromtimestamp(due / 1000) == datetime(2026, 7, 23, 22, 45)

        # The same interval with a different time of day must land elsewhere.
        settings["backup_hour"] = 4
        settings["backup_minute"] = 5
        assert datetime.fromtimestamp(db.next_scheduled_db_backup_at(settings) / 1000) == datetime(2026, 7, 23, 4, 5)

        for bad in ({"backup_hour": 24}, {"backup_minute": 60}, {"backup_hour": -1}):
            body = {"interval_days": 3, "max_generations": 2, **bad}
            assert client.put("/api/settings/db-backup", headers=admin_headers, json=body).status_code == 422
    finally:
        db.delete_session(admin_token)
        db.delete_user(admin["id"])
        db.delete_user_group(group["id"])


def test_scheduled_db_backup_waits_for_the_configured_time(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_BACKUP_DIR", tmp_path / "db-backups")
    db.update_db_backup_settings(1, 4, 22, 45)
    settings = db.get_db_backup_settings()
    settings["last_auto_backup_at"] = int(datetime(2026, 7, 20, 22, 45).timestamp() * 1000)
    db._write_app_setting(db._DB_BACKUP_SETTINGS_KEY, settings)
    auto_dir = tmp_path / "db-backups" / "auto"

    # One minute before the configured time on the due day: nothing is written.
    monkeypatch.setattr(db, "_now_ms", lambda: int(datetime(2026, 7, 21, 22, 44).timestamp() * 1000))
    assert db.ensure_scheduled_db_backup() is None
    assert not auto_dir.exists() or list(auto_dir.glob("*.db")) == []

    # One minute after it, the copy is taken.
    monkeypatch.setattr(db, "_now_ms", lambda: int(datetime(2026, 7, 21, 22, 46).timestamp() * 1000))
    assert db.ensure_scheduled_db_backup() is not None
    assert len(list(auto_dir.glob("inku-auto-*.db"))) == 1


def test_db_backup_listing_numbers_generations_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_BACKUP_DIR", tmp_path / "db-backups")
    auto_dir = tmp_path / "db-backups" / "auto"
    manual_dir = tmp_path / "db-backups" / "manual"
    auto_dir.mkdir(parents=True)
    manual_dir.mkdir(parents=True)
    written = {}
    for name, mtime, payload in (
        ("inku-auto-20260720-030000.db", 1_000, b"a"),
        ("inku-auto-20260721-030000.db", 2_000, b"bb"),
        ("inku-auto-20260722-030000.db", 3_000, b"ccc"),
    ):
        path = auto_dir / name
        path.write_bytes(payload)
        os.utime(path, (mtime, mtime))
        written[name] = len(payload)
    manual = manual_dir / "inku-manual-20260719-120000.db"
    manual.write_bytes(b"dddd")
    os.utime(manual, (2_500, 2_500))

    listing = db.list_db_backups()
    assert listing["total_count"] == 4
    assert listing["total_size_bytes"] == sum(written.values()) + 4

    names = [entry["name"] for entry in listing["entries"]]
    assert names[0] == "inku-auto-20260722-030000.db"
    # The manual copy sits between the automatic ones by time, but it is outside
    # the numbering, and it must not shift the generations either.
    assert [entry["generation"] for entry in listing["entries"]] == [1, None, 2, 3]
    assert [entry["kind"] for entry in listing["entries"]] == ["auto", "manual", "auto", "auto"]


def test_user_management_crud():
    suffix = uuid.uuid4().hex[:8]
    admin_group = db.add_user_group(f"admins-{suffix}")
    admin = db.add_user(
        username=f"admin-{suffix}",
        email=f"admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
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
            "permission_groups": ["users"],
            "group_id": group["id"],
        },
        headers=headers,
    )
    assert user_r.status_code == 200
    user = user_r.json()
    assert user["group_id"] == group["id"]
    assert user["permission_groups"] == ["users"]
    assert "password" not in user
    assert "password_hash" not in user

    blocked = client.delete(f"/api/user-groups/{group['id']}", headers=headers)
    assert blocked.status_code == 409

    patch_r = client.patch(
        f"/api/users/{user['id']}",
        json={"permission_groups": ["leaders"], "password": "password-456"},
        headers=headers,
    )
    assert patch_r.status_code == 200
    assert patch_r.json()["permission_groups"] == ["leaders"]
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
            "permission_groups": ["admins"],
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
            "permission_groups": ["users"],
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
        permission_groups=["users"],
        group_id=group["id"],
    )
    user_b = db.add_user(
        username=f"history-b-{suffix}",
        email=f"history-b-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
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
        "derivation_metadata": {"seed_text": "夕立"},
    }
    post_a = client.post("/api/history", json=payload, headers=headers_a)
    assert post_a.status_code == 200
    item_a = post_a.json()
    assert item_a["svg"] != payload["svg"]
    assert "<script" not in item_a["svg"]
    assert "<svg" in item_a["svg"]
    assert item_a["seed_text"] == "夕立"
    assert item_a["render_seed"] == api_rendering._render_seed_from_text("夕立", None)[0]
    post_a_second = client.post(
        "/api/history",
        json={**payload, "input": "blue crayon search target", "ddl": "青い線", "at": payload["at"] + 1},
        headers=headers_a,
    )
    assert post_a_second.status_code == 200
    item_a_second = post_a_second.json()
    with db.SessionLocal() as session:
        session.query(db.HistoryRow).filter(db.HistoryRow.id == item_a_second["id"]).update(
            {db.HistoryRow.render_hash: "rh3:" + "a" * 60 + "Ab12"}
        )
        # The same four characters, but in the middle of the hash. The search reads the
        # last four, so this row must stay out of the result -- a substring match finds it.
        session.query(db.HistoryRow).filter(db.HistoryRow.id == item_a["id"]).update(
            {db.HistoryRow.render_hash: "rh3:" + "ab12" + "c" * 60}
        )
        session.commit()

    list_a = client.get("/api/history", headers=headers_a)
    assert list_a.status_code == 200
    assert list_a.json()["total"] == 2
    assert list_a.json()["items"][0]["id"] == item_a_second["id"]

    page_a = client.get("/api/history?offset=1&limit=1", headers=headers_a)
    assert page_a.status_code == 200
    assert page_a.json()["total"] == 2
    assert page_a.json()["items"][0]["id"] == item_a["id"]

    anchored_a = client.get(f"/api/history?anchor_id={item_a['id']}&limit=1", headers=headers_a)
    assert anchored_a.status_code == 200
    assert anchored_a.json()["offset"] == 1
    assert anchored_a.json()["items"][0]["id"] == item_a["id"]

    anchored_other_user = client.get(f"/api/history?anchor_id={item_a['id']}&limit=1", headers=headers_b)
    assert anchored_other_user.status_code == 200
    assert anchored_other_user.json()["total"] == 0
    assert anchored_other_user.json()["items"] == []

    search_a = client.get("/api/history?q=crayon", headers=headers_a)
    assert search_a.status_code == 200
    assert search_a.json()["total"] == 1
    assert search_a.json()["items"][0]["id"] == item_a_second["id"]

    hash_search_a = client.get("/api/history?q=ab12", headers=headers_a)
    assert hash_search_a.status_code == 200
    assert hash_search_a.json()["total"] == 1
    assert hash_search_a.json()["items"][0]["id"] == item_a_second["id"]

    four_character_description_search_a = client.get("/api/history?q=blue", headers=headers_a)
    assert four_character_description_search_a.status_code == 200
    assert four_character_description_search_a.json()["total"] == 1
    assert four_character_description_search_a.json()["items"][0]["id"] == item_a_second["id"]

    short_hash_search_a = client.get("/api/history?q=b12", headers=headers_a)
    assert short_hash_search_a.status_code == 200
    assert short_hash_search_a.json()["total"] == 0

    long_hash_search_a = client.get("/api/history?q=aab12", headers=headers_a)
    assert long_hash_search_a.status_code == 200
    assert long_hash_search_a.json()["total"] == 0

    punctuated_hash_search_a = client.get("/api/history?q=ab-2", headers=headers_a)
    assert punctuated_hash_search_a.status_code == 200
    assert punctuated_hash_search_a.json()["total"] == 0

    star_a = client.patch(
        "/api/history/{}/star".format(item_a_second["id"]),
        json={"starred": True, "note": "quiet hinge"},
        headers=headers_a,
    )
    assert star_a.status_code == 200
    assert star_a.json()["starred"] is True
    assert star_a.json()["note"] == "quiet hinge"
    starred_a = client.get("/api/history?starred=true", headers=headers_a)
    assert starred_a.status_code == 200
    assert starred_a.json()["total"] == 1
    assert starred_a.json()["items"][0]["id"] == item_a_second["id"]

    unstar_a = client.patch(
        "/api/history/{}/star".format(item_a_second["id"]),
        json={"starred": False},
        headers=headers_a,
    )
    assert unstar_a.status_code == 200
    assert unstar_a.json()["starred"] is False
    assert unstar_a.json()["note"] == "quiet hinge"

    update_note_a = client.patch(
        "/api/history/{}/star".format(item_a_second["id"]),
        json={"starred": False, "note": "lineage comment"},
        headers=headers_a,
    )
    assert update_note_a.status_code == 200
    assert update_note_a.json()["starred"] is False
    assert update_note_a.json()["note"] == "lineage comment"

    restar_a = client.patch(
        "/api/history/{}/star".format(item_a_second["id"]),
        json={"starred": True},
        headers=headers_a,
    )
    assert restar_a.status_code == 200
    assert restar_a.json()["note"] == "lineage comment"

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


def test_history_neighbors_returns_ranked_items():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"neighbors-{suffix}")
    user = db.add_user(
        username=f"neighbors-{suffix}",
        email=f"neighbors-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    headers, token = _auth_headers(user)
    item_ids: list[str] = []
    try:
        base_at = 1_700_000_000_000
        for index in range(5):
            score = {
                "instructions": [
                    {
                        "primitive": "circle",
                        "center": [0.1 * index + 0.1, 0.5],
                        "radius": 0.1,
                    }
                ]
            }
            r = client.post(
                "/api/history",
                json={
                    "input": f"neighbors item {index}",
                    "ddl": "中心に円",
                    "score": score,
                    "svg": "<svg></svg>",
                    "at": base_at + index,
                },
                headers=headers,
            )
            assert r.status_code == 200
            item_ids.append(r.json()["id"])

        r = client.get(f"/api/history/{item_ids[0]}/neighbors", headers=headers)
        assert r.status_code == 200
        neighbors = r.json()
        assert len(neighbors) == 3
        assert item_ids[0] not in [item["id"] for item in neighbors]

        with db.SessionLocal() as session:
            session.query(db.HistoryRow).filter(db.HistoryRow.id == item_ids[1]).update(
                {db.HistoryRow.score: "{not json"}, synchronize_session=False
            )
            session.query(db.HistoryRow).filter(db.HistoryRow.id == item_ids[2]).update(
                {db.HistoryRow.score: ""}, synchronize_session=False
            )
            session.commit()

        r = client.get(f"/api/history/{item_ids[0]}/neighbors", headers=headers)
        assert r.status_code == 200
        assert len(r.json()) == 3
    finally:
        db.delete_items(user["id"], item_ids)
        db.delete_session(token)
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])


def test_history_animation_export_returns_404_for_a_missing_work(auth_context):
    headers, _user, _group = auth_context
    response = client.post(
        "/api/history/export-animation",
        json={"ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "one or more history items were not found"}


def test_history_animation_export_returns_409_for_a_work_without_saved_svg(auth_context):
    headers, user, _group = auth_context
    item_ids: list[str] = []
    try:
        for index in range(2):
            response = client.post(
                "/api/history",
                json={
                    "input": f"animation missing svg {index}",
                    "ddl": "中心に円",
                    "score": {"instructions": []},
                    "svg": "<svg></svg>",
                    "at": 1_700_000_100_000 + index,
                },
                headers=headers,
            )
            assert response.status_code == 200
            item_ids.append(response.json()["id"])

        with db.SessionLocal() as session:
            session.query(db.HistoryRow).filter(db.HistoryRow.id == item_ids[1]).update(
                {db.HistoryRow.svg: ""}, synchronize_session=False
            )
            session.commit()

        response = client.post(
            "/api/history/export-animation",
            json={"ids": item_ids},
            headers=headers,
        )

        assert response.status_code == 409
        assert response.json() == {"detail": "one or more works have no saved SVG"}
    finally:
        db.delete_items(user["id"], item_ids)


def test_history_animation_export_preserves_requested_order(auth_context, monkeypatch):
    headers, user, _group = auth_context
    item_ids: list[str] = []
    try:
        for index in range(2):
            response = client.post(
                "/api/history",
                json={
                    "input": f"animation item {index}",
                    "ddl": "中心に円",
                    "score": {"instructions": []},
                    "svg": f"<svg data-frame=\"{index}\"></svg>",
                    "at": 1_700_000_000_000 + index,
                },
                headers=headers,
            )
            assert response.status_code == 200
            item_ids.append(response.json()["id"])

        expected_svgs = [item["svg"] for item in db.get_items(user["id"], list(reversed(item_ids)))]
        captured: dict = {}

        def fake_build(svgs, **options):
            captured["svgs"] = svgs
            captured["options"] = options
            return b"GIF89a"

        monkeypatch.setattr(history_routes, "build_animation", fake_build)
        response = client.post(
            "/api/history/export-animation",
            json={
                "ids": list(reversed(item_ids)),
                "format": "gif",
                "pattern": "slide",
                "hold_seconds": 2.5,
                "resolution": "4k",
                "height_px": 300,
            },
            headers=headers,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/gif"
        assert response.headers["content-disposition"].endswith(".gif\"")
        assert response.content == b"GIF89a"
        assert captured["svgs"] == expected_svgs
        assert captured["options"] == {
            "output_format": "gif",
            "pattern": "slide",
            "hold_seconds": 2.5,
            "resolution": "4k",
            "height_px": 300,
        }
    finally:
        db.delete_items(user["id"], item_ids)


def test_output_save_settings_are_admin_only(tmp_path):
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"output-save-{suffix}")
    user = db.add_user(
        username=f"output-save-user-{suffix}",
        email=f"output-save-user-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    admin = db.add_user(
        username=f"output-save-admin-{suffix}",
        email=f"output-save-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    user_headers, user_token = _auth_headers(user)
    admin_headers, admin_token = _auth_headers(admin)
    try:
        output_dir = tmp_path / "outputs"
        assert client.put(
            "/api/settings/output-save",
            headers=user_headers,
            json={"enabled": False, "output_dir": str(output_dir), "png_size": 1080},
        ).status_code == 403

        settings_r = client.put(
            "/api/settings/output-save",
            headers=admin_headers,
            json={"enabled": False, "output_dir": str(output_dir), "png_size": 1080},
        )
        assert settings_r.status_code == 200
        data = settings_r.json()
        assert data["enabled"] is False
        assert data["output_dir"] == str(output_dir)
        assert data["png_size"] == 1080

        status_r = client.get("/api/settings/status", headers=admin_headers)
        assert status_r.status_code == 200
        assert status_r.json()["output_save"]["enabled"] is False

        bad_r = client.put(
            "/api/settings/output-save",
            headers=admin_headers,
            json={"enabled": True, "output_dir": "relative/out", "png_size": 2160},
        )
        assert bad_r.status_code == 400

        bad_size_r = client.put(
            "/api/settings/output-save",
            headers=admin_headers,
            json={"enabled": True, "output_dir": str(output_dir), "png_size": 1440},
        )
        assert bad_size_r.status_code == 400
    finally:
        db.update_output_save_settings(True, str(Path.home() / ".local" / "share" / "inku" / "outputs"), 2160)
        db.delete_session(admin_token)
        db.delete_session(user_token)
        db.delete_user(admin["id"])
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])


def test_render_concurrency_settings_are_admin_only():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"render-concurrency-{suffix}")
    user = db.add_user(
        username=f"render-concurrency-user-{suffix}",
        email=f"render-concurrency-user-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    admin = db.add_user(
        username=f"render-concurrency-admin-{suffix}",
        email=f"render-concurrency-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    user_headers, user_token = _auth_headers(user)
    admin_headers, admin_token = _auth_headers(admin)
    baseline = db.get_render_concurrency_settings()
    try:
        assert client.put(
            "/api/settings/render-concurrency",
            headers=user_headers,
            json={"server_limit": 3, "client_limit": 3},
        ).status_code == 403

        r = client.put(
            "/api/settings/render-concurrency",
            headers=admin_headers,
            json={"server_limit": 5, "client_limit": 3},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["server_limit"] == 5
        assert data["client_limit"] == 3
        assert data["min_limit"] == db.RENDER_CONCURRENCY_MIN
        assert data["max_limit"] == db.RENDER_CONCURRENCY_MAX

        # The running server honours the new limit, not the import-time default.
        from inku_server.api_core.state import _render_slots

        assert _render_slots.limit == 5

        status_r = client.get("/api/settings/status", headers=admin_headers)
        assert status_r.status_code == 200
        assert status_r.json()["render_concurrency"]["server_limit"] == 5

        # Every authenticated client reads the advisory fan-out limit.
        config_r = client.get("/api/client-config", headers=user_headers)
        assert config_r.status_code == 200
        assert config_r.json()["render_fanout_limit"] == 3
        assert client.get("/api/client-config").status_code == 401

        for payload in ({"server_limit": 0, "client_limit": 3}, {"server_limit": 3, "client_limit": 99}):
            assert client.put(
                "/api/settings/render-concurrency",
                headers=admin_headers,
                json=payload,
            ).status_code == 400
    finally:
        from inku_server.api_core.state import _render_slots as _slots

        db.update_render_concurrency_settings(int(baseline["server_limit"]), int(baseline["client_limit"]))
        _slots.set_limit(int(baseline["server_limit"]))
        db.delete_session(admin_token)
        db.delete_session(user_token)
        db.delete_user(admin["id"])
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])


def test_log_retention_settings_are_admin_only():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"log-retention-{suffix}")
    user = db.add_user(
        username=f"log-retention-user-{suffix}",
        email=f"log-retention-user-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    admin = db.add_user(
        username=f"log-retention-admin-{suffix}",
        email=f"log-retention-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    user_headers, user_token = _auth_headers(user)
    admin_headers, admin_token = _auth_headers(admin)
    try:
        payload = {"enabled": True, "retention_days": 30, "rotate": "weekly", "compress": False}
        assert client.put("/api/settings/log-retention", headers=user_headers, json=payload).status_code == 403

        settings_r = client.put("/api/settings/log-retention", headers=admin_headers, json=payload)
        assert settings_r.status_code == 200
        data = settings_r.json()
        assert data["enabled"] is True
        assert data["retention_days"] == 30
        assert data["rotate"] == "weekly"
        assert data["compress"] is False
        # The stored policy is applied in process now, so the response describes
        # where it landed instead of what the operator should paste.
        assert data["log_dir"]
        assert "systemd" not in data

        status_r = client.get("/api/settings/status", headers=admin_headers)
        assert status_r.status_code == 200
        assert status_r.json()["log_retention"]["retention_days"] == 30

        bad_r = client.put(
            "/api/settings/log-retention",
            headers=admin_headers,
            json={"enabled": True, "retention_days": 0, "rotate": "daily", "compress": True},
        )
        assert bad_r.status_code == 422

        bad_rotate_r = client.put(
            "/api/settings/log-retention",
            headers=admin_headers,
            json={"enabled": True, "retention_days": 90, "rotate": "hourly", "compress": True},
        )
        assert bad_rotate_r.status_code == 422
    finally:
        db.update_log_retention_settings(True, 90, "daily", True)
        db.delete_session(admin_token)
        db.delete_session(user_token)
        db.delete_user(admin["id"])
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])


def test_models_hide_nvidia_outside_developer_mode(monkeypatch, auth_context):
    monkeypatch.delenv("INKU_DEVELOPER_MODE", raising=False)
    headers, _, _ = auth_context

    response = client.get("/api/models", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert all(provider["id"] != "nvidia" for provider in data["catalog"])
    assert all(provider["id"] != "nvidia" for provider in data["llm_catalog"])
    assert all(provider["id"] != "nvidia" for provider in data["vision_catalog"])

    settings = default_model_settings()
    assert "nvidia" in settings["providers"]
    assert all(
        provider["id"] != "nvidia"
        for provider in model_provider_catalog(settings, include_developer=False)
    )
    assert any(
        provider["id"] == "nvidia"
        for provider in model_provider_catalog(settings, include_developer=True)
    )


def test_verified_nvidia_model_metadata_and_purpose_catalogs():
    settings = default_model_settings()
    nvidia_models = settings["providers"]["nvidia"]["models"]
    assert len(nvidia_models) == 44

    gemma = next(model for model in nvidia_models if model["id"] == "google/gemma-4-31b-it")
    assert gemma["purposes"] == ["llm", "vision"]
    # v1.98: 推奨度は用途ごと。旧 recommendation_level は用途別の値が無いときだけ読む。
    assert gemma["recommendation_llm"] == 4
    assert gemma["recommendation_vision"] == 5
    assert gemma["speed_class"] == "medium"
    assert gemma["speed_label"] == "昼 221s / 夕 114s / 深夜 199s"
    assert "スキーマ違反なし" in gemma["comment_ja"]

    llm_nvidia = next(provider for provider in model_provider_catalog(settings, purpose="llm") if provider["id"] == "nvidia")
    vision_nvidia = next(provider for provider in model_provider_catalog(settings, purpose="vision") if provider["id"] == "nvidia")
    assert len(llm_nvidia["models"]) == 40
    assert len(vision_nvidia["models"]) == 10

    normalized = normalize_model_settings({
        "model_catalog_version": settings["model_catalog_version"],
        "providers": {
            "nvidia": {
                "models": [{
                    "id": "google/gemma-4-31b-it",
                    "label": "Gemma custom label",
                    "purposes": ["vision"],
                    "recommendation_level": 2,
                    "speed_class": "medium",
                    "speed_label": "再計測 約30秒",
                    "comment_ja": "管理者による再評価",
                    "comment_en": "Administrator override",
                }],
            },
        },
    })
    normalized_models = normalized["providers"]["nvidia"]["models"]
    assert len(normalized_models) == 44
    overridden = next(model for model in normalized_models if model["id"] == "google/gemma-4-31b-it")
    assert overridden["label"] == "Gemma custom label"
    assert overridden["purposes"] == ["vision"]
    # 上書きは vision 側だけに効く。LLM 側は組み込みカタログの値が残るが、purposes が
    # vision のみなので LLM の一覧には出ない。
    assert overridden["recommendation_vision"] == 2
    assert overridden["recommendation_llm"] == 4
    assert overridden["speed_label"] == "再計測 約30秒"
    assert overridden["comment_en"] == "Administrator override"

    legacy = normalize_model_settings({
        "providers": {
            "nvidia": {
                "models": [{
                    "id": "google/gemma-4-31b-it",
                    "label": "Legacy stored label",
                    "purposes": ["llm"],
                }],
            },
        },
    })
    legacy_gemma = next(model for model in legacy["providers"]["nvidia"]["models"] if model["id"] == "google/gemma-4-31b-it")
    assert legacy_gemma["label"] == "Legacy stored label"
    assert legacy_gemma["purposes"] == ["llm", "vision"]
    assert legacy_gemma["recommendation_llm"] == 4
    assert legacy_gemma["speed_label"] == "昼 221s / 夕 114s / 深夜 199s"


def test_model_settings_store_keys_server_side(monkeypatch):
    monkeypatch.setenv("INKU_SECRET_KEY", "test-secret-for-model-settings")
    monkeypatch.setenv("INKU_DEVELOPER_MODE", "1")
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"model-settings-admins-{suffix}")
    admin = db.add_user(
        username=f"model-settings-admin-{suffix}",
        email=f"model-settings-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    headers, token = _auth_headers(admin)
    r = client.get("/api/settings/models", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert any(provider["id"] == "openai" for provider in data["catalog"])
    assert next(provider for provider in data["catalog"] if provider["id"] == "openai")["label"] == "OpenAI API Platform"
    assert next(provider for provider in data["catalog"] if provider["id"] == "anthropic")["label"] == "Claude API"
    assert next(provider for provider in data["catalog"] if provider["id"] == "gemini")["label"] == "Gemini API"

    r = client.put(
        "/api/settings/models",
        headers=headers,
        json={
            "providers": {
                "openai": {
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-test-secret",
                    "memo": "Team contract renews in April.",
                    "enabled_models": {"gpt-5.1": False},
                },
                "gemini": {"base_url": "https://generativelanguage.googleapis.com", "api_key": "gemini-secret"},
            },
        },
    )
    assert r.status_code == 200
    settings = r.json()["settings"]
    assert settings["providers"]["openai"]["api_key_set"] is True
    assert settings["providers"]["openai"]["api_key_hint"] == "sk-t...cret"
    assert settings["providers"]["openai"]["enabled_models"]["gpt-5.1"] is False
    assert "sk-test-secret" not in json.dumps(settings)
    assert next(provider for provider in r.json()["catalog"] if provider["id"] == "openai")["memo"] == "Team contract renews in April."

    saved = db.get_model_settings()
    assert saved["providers"]["openai"]["api_key"].startswith("enc:v1:")
    assert "sk-test-secret" not in json.dumps(saved)
    assert connection_for("openai", saved)["api_key"] == "sk-test-secret"
    assert saved["providers"]["openai"]["memo"] == "Team contract renews in April."
    assert saved["providers"]["openai"]["enabled_models"]["gpt-5.1"] is False

    r = client.put(
        "/api/settings/models",
        headers=headers,
        json={"providers": {"openai": {"base_url": "http://127.0.0.1:18000/v3"}}},
    )
    assert r.status_code == 200
    assert r.json()["settings"]["providers"]["openai"]["base_url"] == "https://api.openai.com/v1"

    public_models = client.get("/api/models", headers=headers)
    assert public_models.status_code == 200
    openai_catalog = next(provider for provider in public_models.json()["catalog"] if provider["id"] == "openai")
    assert "memo" not in openai_catalog
    assert all(model["id"] != "gpt-5.1" for model in openai_catalog["models"])
    nvidia_llm = next(provider for provider in public_models.json()["llm_catalog"] if provider["id"] == "nvidia")
    nvidia_vision = next(provider for provider in public_models.json()["vision_catalog"] if provider["id"] == "nvidia")
    assert len(nvidia_llm["models"]) == 40
    assert len(nvidia_vision["models"]) == 10
    assert all("llm" in model["purposes"] for model in nvidia_llm["models"])
    assert all("vision" in model["purposes"] for model in nvidia_vision["models"])

    r = client.put(
        "/api/settings/models",
        headers=headers,
        json={
            "providers": {
                "custom-openai": {
                    "label": "Custom OpenAI Compatible",
                    "kind": "openai_compatible",
                    "base_url": "http://127.0.0.1:9999/v1",
                    "default_base_url": "http://127.0.0.1:9999/v1",
                    "requires_api_key": False,
                    "models": [{"id": "local-model", "label": "Local Model"}],
                    "enabled_models": {"local-model": True},
                }
            }
        },
    )
    assert r.status_code == 200
    assert any(provider["id"] == "custom-openai" for provider in r.json()["catalog"])

    r = client.put(
        "/api/settings/models",
        headers=headers,
        json={"providers": {"custom-openai": {"delete": True}}},
    )
    assert r.status_code == 200
    assert all(provider["id"] != "custom-openai" for provider in r.json()["catalog"])

    r = client.put(
        "/api/settings/models",
        headers=headers,
        json={"providers": {"openai": {"base_url": "https://api.openai.com/v1", "clear_api_key": True}}},
    )
    assert r.status_code == 200
    assert r.json()["settings"]["providers"]["openai"]["api_key_set"] is False
    db.update_model_settings(default_model_settings())
    db.delete_session(token)
    db.delete_user(admin["id"])
    db.delete_user_group(group["id"])


def test_model_settings_fetch_models_from_provider(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"model-fetch-admins-{suffix}")
    admin = db.add_user(
        username=f"model-fetch-admin-{suffix}",
        email=f"model-fetch-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    headers, token = _auth_headers(admin)
    db.update_model_settings(update_model_settings(default_model_settings(), {
        "providers": {
            "openai": {
                "models": [
                    {"id": "fetched-model", "label": "Previous Fetched Model"},
                    {"id": "removed-model", "label": "Removed Model"},
                ],
                "enabled_models": {"fetched-model": True, "removed-model": True},
            }
        }
    }))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({
                "data": [
                    {"id": "fetched-model", "display_name": "Fetched Model"},
                    {"id": "new-fetched-model", "display_name": "New Fetched Model"},
                    {"id": "fetched-model", "display_name": "Fetched Model Duplicate"},
                ]
            }).encode()

    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    r = client.post("/api/settings/models/openai/fetch-models", headers=headers)
    assert r.status_code == 200
    assert seen["url"] == "https://api.openai.com/v1/models"
    openai_catalog = next(provider for provider in r.json()["catalog"] if provider["id"] == "openai")
    # v1.98: 提供元から消えたモデルは削除せず EOL として末尾に残す。
    today = datetime.now(timezone.utc).date().isoformat()
    assert openai_catalog["models"] == [
        {"id": "fetched-model", "label": "Fetched Model", "purposes": ["llm"], "enabled": True},
        {"id": "new-fetched-model", "label": "New Fetched Model", "purposes": ["llm"], "enabled": False},
        {
            "id": "removed-model",
            "label": "Removed Model",
            "purposes": ["llm"],
            "enabled": False,
            "eol": True,
            "eol_date": today,
        },
    ]

    class NewFakeResponse(FakeResponse):
        def read(self):
            return json.dumps({"data": [{"id": "new-model", "display_name": "New Model"}]}).encode()

    def new_fake_urlopen(req, timeout=0):
        return NewFakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", new_fake_urlopen)
    r = client.post("/api/settings/models/openai/fetch-models", headers=headers)
    assert r.status_code == 200
    openai_catalog = next(provider for provider in r.json()["catalog"] if provider["id"] == "openai")
    assert openai_catalog["models"] == [
        {"id": "new-model", "label": "New Model", "purposes": ["llm"], "enabled": False},
        {"id": "fetched-model", "label": "Fetched Model", "purposes": ["llm"], "enabled": False, "eol": True, "eol_date": today},
        {"id": "new-fetched-model", "label": "New Fetched Model", "purposes": ["llm"], "enabled": False, "eol": True, "eol_date": today},
        {"id": "removed-model", "label": "Removed Model", "purposes": ["llm"], "enabled": False, "eol": True, "eol_date": today},
    ]

    db.update_model_settings(default_model_settings())
    db.delete_session(token)
    db.delete_user(admin["id"])
    db.delete_user_group(group["id"])


def test_render_svg_forwards_wild_to_the_renderer(auth_context, monkeypatch):
    """The wild flag reaches the renderer from the request, both ways (not vacuous)."""
    headers, _user, _group = auth_context
    import inku_server.render_engines.default as default_engine

    captured: dict = {}

    def fake_render_svg(
        score, *, color_map=None, catalog_id=None, canvas_aspect=None, svg_profile=None,
        render_seed=None, composition_seed=None, wild=False
    ):
        captured["wild"] = wild
        return '<svg xmlns="http://www.w3.org/2000/svg"></svg>'

    monkeypatch.setattr(default_engine, "render_svg", fake_render_svg)
    score = {
        "version": "0.1.0",
        "background": "white",
        "instructions": [
            {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "weight": "pen", "color": "black"}
        ],
    }
    r_on = client.post("/api/render-svg", json={"score": score, "wild": True}, headers=headers)
    assert r_on.status_code == 200
    assert captured["wild"] is True

    r_off = client.post("/api/render-svg", json={"score": score, "wild": False}, headers=headers)
    assert r_off.status_code == 200
    assert captured["wild"] is False
