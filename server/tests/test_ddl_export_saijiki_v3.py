"""Portable v2 exports are migrated with their actual plugin definitions."""

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from inku_server.api import app
from inku_server import db
from inku_server.ddl_export import build_ddl_export, migrate_v2_export


def test_export_records_its_saijiki_and_old_export_moves_its_text():
    assert build_ddl_export("黒い円。", "ja")["saijiki"] == "inku.saijiki.v3"
    result = migrate_v2_export("黒い太筆の線を引く。", "ja", [])
    assert result == {"ddl": "黒い太いガッシュの線を引く。", "plugins": [], "edits": 1}


def test_export_migration_keeps_plugin_note_and_definition():
    root = Path(__file__).resolve().parents[2]
    package = json.loads((root / "core/crates/inku-ddl/assets/nature-leaves-v2/package.json").read_text())
    definition = package["words"][0]["definition"]
    result = migrate_v2_export("｛若葉｝。", "ja", [{"definition": definition, "note": "note"}])
    assert result["plugins"][0]["definition"] == definition
    assert result["plugins"][0]["note"] == "note"


def test_old_plugin_tool_is_migrated_before_building_its_document_lock():
    root = Path(__file__).resolve().parents[2]
    package = json.loads((root / "core/crates/inku-ddl/assets/nature-leaves-v2/package.json").read_text())
    definition = package["words"][0]["definition"]
    fields = definition["components"]["leaf_form"]["body"][0]["fields"]
    fields["touch"] = {"expr": "semantic_ref", "category": "touch", "id": "brush_thick"}
    result = migrate_v2_export("｛若葉｝。", "ja", [{"definition": definition, "note": "old"}])
    migrated = result["plugins"][0]["definition"]["components"]["leaf_form"]["body"][0]["fields"]
    assert migrated["touch"]["id"] == "gouache"
    assert result["plugins"][0]["note"] == "old"


def test_migration_route_requires_authentication():
    response = TestClient(app).post("/api/ddl-export/migrate-v2", json={"ddl": "x", "language": "ja"})
    assert response.status_code in (401, 403)


def test_authenticated_migration_route_returns_new_text():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"ddl-v3-{suffix}")
    user = db.add_user(username=f"ddl-v3-{suffix}", email=f"ddl-v3-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    try:
        response = TestClient(app).post("/api/ddl-export/migrate-v2",
            headers={"Authorization": f"Bearer {token}"},
            json={"ddl": "黒い太筆の線を引く。", "language": "ja", "plugins": []})
        assert response.status_code == 200
        assert response.json() == {"ddl": "黒い太いガッシュの線を引く。", "plugins": [], "edits": 1}
    finally:
        db.delete_session(token)
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])
