"""Phase 3 anti-drift: GET /api/saijiki and the web codegen snapshot both
derive from the saijiki table. Hardcoding either would diverge and fail here.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from inku_server import api as api_module
from inku_server import db, saijiki
from inku_server.api import app

client = TestClient(app)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATED_TS = _REPO_ROOT / "web" / "src" / "lib" / "saijiki.generated.ts"


def _load_codegen():
    path = _REPO_ROOT / "server" / "scripts" / "gen_saijiki_ts.py"
    spec = importlib.util.spec_from_file_location("gen_saijiki_ts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _auth():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"saij-{suffix}")
    user = db.add_user(
        username=f"saij-{suffix}",
        email=f"saij-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}, user, group, token


def test_api_saijiki_matches_table():
    headers, user, group, token = _auth()
    try:
        for lang in ("ja", "en"):
            response = client.get(f"/api/saijiki?lang={lang}", headers=headers)
            assert response.status_code == 200
            expected = json.loads(
                json.dumps(
                    {
                        "categories": saijiki.display_categories(lang),
                        "plugins": api_module._enabled_plugin_entries(),
                    }
                )
            )
            assert response.json() == expected
    finally:
        db.delete_session(token)
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])


def test_api_saijiki_requires_auth():
    assert client.get("/api/saijiki").status_code in (401, 403)


def test_generated_ts_matches_table():
    module = _load_codegen()
    assert module.render_ts() == _GENERATED_TS.read_text(encoding="utf-8")


def test_pruned_words_absent_from_display():
    words = {w for cat in saijiki.display_categories("ja") for w in cat["words"]}
    words |= {w for cat in saijiki.display_categories("en") for w in cat["words"]}
    # P0-3 (髪/hair), P0-2b (描く), P0-1a (彫る) removed from display; aida kept.
    assert "髪" not in words and "hair" not in words
    assert "描く" not in words and "彫る" not in words
    assert any(cat["key"] == "aida" for cat in saijiki.display_categories("ja"))
    # Weight enum still carries hair for replay/rh2 compatibility.
    from inku_server import schema
    from typing import get_args

    assert "hair" in get_args(schema.Weight)
