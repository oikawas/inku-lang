"""Persisted drawing choices and legacy user canvas migration."""

import json
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from inku_server import db
from inku_server.api import app
from inku_server.model_settings import user_settings_with_legacy_canvas
from inku_server.persistence import migrations
from inku_server.persistence.schema import UserAccountRow


@pytest.fixture
def user():
    suffix = uuid.uuid4().hex[:10]
    account = db.add_user(username=f"draw-{suffix}", email=f"{suffix}@example.test",
                          password="password-123", permission_groups=["users"], group_id=None)
    token = db.create_session(account["id"])
    yield account["id"], {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(account["id"], cascade=True)


def test_user_canvas_migration_and_non_admin_patch_get(user):
    user_id, headers = user
    with db.SessionLocal() as session:
        row = session.get(UserAccountRow, user_id)
        row.model_settings = json.dumps({"stage1_provider": "openai", "stage1_model": "gpt-test"})
        row.plugin_storage = json.dumps({"canvas-aspect": {"enabled": True, "selected": "a4"}})
        session.commit()
    client = TestClient(app)
    current = client.get("/api/auth/me", headers=headers).json()["model_settings"]["draw_defaults"]
    assert current["describe"]["canvas_aspect"] == current["batch_text"]["canvas_aspect"] == "a4"
    assert current["image"]["canvas_aspect"] == "image"
    assert current["describe"]["models"]["stage1"] == "openai:gpt-test"
    other_patch = client.patch("/api/auth/me/settings", headers=headers,
                               json={"model_settings": {"color_catalog_id": "auto"}})
    assert other_patch.status_code == 200
    with db.SessionLocal() as session:
        stored = json.loads(session.get(UserAccountRow, user_id).model_settings)
        assert stored["draw_defaults"]["describe"]["canvas_aspect"] == "a4"
    current["describe"]["canvas_aspect"] = "square"
    response = client.patch("/api/auth/me/settings", headers=headers,
                            json={"model_settings": {"draw_defaults": current}})
    assert response.status_code == 200
    assert client.get("/api/auth/me", headers=headers).json()["model_settings"]["draw_defaults"] == current
    assert client.put("/api/auth/me/plugin-storage/canvas-aspect", headers=headers,
                      json={"value": {"selected": "a4"}}).status_code == 403
    assert user_settings_with_legacy_canvas({}, {"canvas-aspect": {"enabled": False, "selected": "a4"}})["draw_defaults"]["describe"]["canvas_aspect"] == "square"
    assert user_settings_with_legacy_canvas({}, {"canvas-aspect": {"selected": "invalid"}})["draw_defaults"]["describe"]["canvas_aspect"] == "square"


def test_history_options_raw_flags_list_and_one_work(user):
    user_id, headers = user
    base = {"user_id": user_id, "at": 1, "input": "text", "note": "test data", "score": {}, "svg": "<svg/>"}
    new = db.add_item({**base, "id": "new", "draw_route": "read_and_draw", "sketch_requested": "1",
                       "composition_requested": "1", "render_wild": False,
                       "stage1_model": "openai:one", "stage2_model": "openai:one",
                       "catalog_id": "default", "catalog_mode": "fixed", "render_canvas_aspect_id": "a4"})
    old = db.add_item({**base, "id": "old"})
    image = db.add_item({**base, "id": "image", "image_ddl": {}, "stage1_model": "openai:vision",
                         "render_wild": True})
    assert new["draw_options"] == {"route": "read_and_draw", "sketch": "on", "composition": "on", "wild": "off",
                                   "catalog": {"id": "default", "mode": "fixed"}, "canvas_aspect": "a4",
                                   "models": {"stage1": "openai:one", "stage2": "openai:one"}}
    assert all(value is None for value in old["draw_options"].values())
    assert image["draw_options"]["models"] == {"vision": "openai:vision"}
    assert image["draw_options"]["wild"] == "on"
    assert image["draw_options"]["route"] is image["draw_options"]["sketch"] is image["draw_options"]["composition"] is None
    client = TestClient(app)
    listing = client.get("/api/history", headers=headers)
    assert listing.status_code == 200
    items = {item["id"]: item for item in listing.json()["items"]}
    for item in (new, old, image):
        assert items[item["id"]]["draw_options"] == item["draw_options"]
    lineage = client.get("/api/history/new/lineage?descendant_depth=0", headers=headers)
    assert lineage.status_code == 200
    assert next(node["history"] for node in lineage.json()["nodes"] if node.get("history"))["draw_options"] == new["draw_options"]
    updated = client.patch("/api/history/new/star", headers=headers, json={"starred": True})
    assert updated.status_code == 200 and updated.json()["draw_options"] == new["draw_options"]


def test_v6_upgrade_keeps_old_rows_null_and_snapshot(tmp_path):
    path = tmp_path / "v6.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE history (id TEXT PRIMARY KEY, ddl TEXT, ddl_source_origin TEXT, image_provenance TEXT, image_ddl TEXT)")
        connection.exec_driver_sql("INSERT INTO history(id, ddl) VALUES ('old', 'preserved')")
        connection.exec_driver_sql(migrations._REGISTRY_DDL)
        connection.exec_driver_sql("INSERT INTO schema_migrations VALUES (?, ?, ?, 1)",
                                   (migrations._V6_VERSION, migrations._V6_NAME, migrations._V6_CHECKSUM))
    def no_op(_):
        return None
    outcome = migrations.ensure_current_schema(engine=engine, database_path=path, create_schema=no_op,
                                               seed_fresh=no_op, apply_legacy=no_op)
    assert outcome.mode == "registered_upgrade" and outcome.snapshot.path.is_file()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT ddl, draw_route, sketch_requested, composition_requested FROM history").fetchone() == ("preserved", None, None, None)
    with sqlite3.connect(outcome.snapshot.path) as original:
        assert "draw_route" not in {row[1] for row in original.execute("PRAGMA table_info(history)")}
    assert migrations.ensure_current_schema(engine=engine, database_path=path, create_schema=no_op,
                                            seed_fresh=no_op, apply_legacy=no_op).mode == "current"
    engine.dispose()
