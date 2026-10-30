"""Built-in Nature.leaves can be disabled, but not deleted."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.plugins import PLUGIN_PACKAGE_MANAGER

client = TestClient(app)


@pytest.fixture
def admin_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"plugin-admin-{suffix}")
    admin = db.add_user(username=f"plugin-admin-{suffix}", email=f"plugin-admin-{suffix}@example.test",
                        password="password-123", permission_groups=["admins"], group_id=group["id"])
    token = db.create_session(admin["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(admin["id"])
    db.delete_user_group(group["id"])


def test_bundled_package_is_in_settings_and_can_be_switched(admin_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "directory", tmp_path / "packages")
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "_signature", None)
    listed = client.get("/api/plugins", headers=admin_headers)
    assert listed.status_code == 200
    item = next(item for item in listed.json()["items"] if item["id"] == "Nature.leaves")
    assert item["kind"] == "package" and item["deletable"] is False
    assert len(item["entries"]) == 7
    status = client.get("/api/settings/status", headers=admin_headers)
    assert status.status_code == 200
    assert any(p["id"] == "Nature.leaves" for p in status.json()["plugins"]["loaded"])
    disabled = client.put("/api/plugins/Nature.leaves/enabled", headers=admin_headers,
                          json={"enabled": False})
    assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"
    assert PLUGIN_PACKAGE_MANAGER.is_enabled("Nature.leaves") is False
    assert not any(word["qualified_name"].startswith("Nature.") for word in
                   client.get("/api/saijiki", headers=admin_headers).json()["plugins"])
    assert client.put("/api/plugins/Nature.leaves/enabled", headers=admin_headers,
                      json={"enabled": True}).json()["status"] == "enabled"
    assert len([word for word in client.get("/api/saijiki", headers=admin_headers).json()["plugins"]
                if word["qualified_name"].startswith("Nature.")]) == 7
    assert client.delete("/api/plugins/Nature.leaves", headers=admin_headers).status_code == 409
    assert client.get("/api/plugins/Nature.leaves/export", headers=admin_headers).status_code == 404


def test_document_only_routes_are_retired(admin_headers):
    assert client.post("/api/plugins/validate", headers=admin_headers, json={"document": "x"}).status_code in {404, 405}
    assert client.post("/api/plugins/reload", headers=admin_headers).status_code in {404, 405}


def test_old_file_named_like_the_bundled_package_is_reported_separately(admin_headers, tmp_path, monkeypatch):
    directory = tmp_path / "packages"
    file = directory / "Nature.leaves" / "package.json"
    file.parent.mkdir(parents=True)
    file.write_text('{"schema":"inku.plugin-package.v1"}', encoding="utf-8")
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "directory", directory)
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "_signature", None)
    items = client.get("/api/plugins", headers=admin_headers).json()["items"]
    matching = [item for item in items if item["id"] == "Nature.leaves"]
    assert {item["status"] for item in matching} == {"enabled", "rejected"}
    assert all(item["deletable"] is False for item in matching)
    assert any("rewrite_as_v2" in reason for item in matching for reason in item["reasons"])
