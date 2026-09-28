"""User plugin management (v1.96): manager CRUD/enabled + admin API contract."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.plugins import DOCUMENT_PLUGIN_MANAGER
from inku_server.plugins.document_format import (
    PluginDocumentManager,
    PluginFormatError,
)

client = TestClient(app)

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "minimal-arcs.inku-plugin.md"


def _fixture_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _auth_headers(user: dict) -> dict[str, str]:
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"plugin-admin-{suffix}")
    admin = db.add_user(
        username=f"plugin-admin-{suffix}",
        email=f"plugin-admin-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    return _auth_headers(admin)


@pytest.fixture
def user_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"plugin-user-{suffix}")
    user = db.add_user(
        username=f"plugin-user-{suffix}",
        email=f"plugin-user-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    return _auth_headers(user)


@pytest.fixture
def plugin_dir(tmp_path):
    original = DOCUMENT_PLUGIN_MANAGER.directory
    DOCUMENT_PLUGIN_MANAGER.directory = tmp_path
    DOCUMENT_PLUGIN_MANAGER.reload(force=True)
    yield tmp_path
    DOCUMENT_PLUGIN_MANAGER.directory = original
    DOCUMENT_PLUGIN_MANAGER.reload(force=True)


# --- manager level ---


def test_manager_disable_excludes_from_documents(tmp_path):
    manager = PluginDocumentManager(directory=tmp_path)
    (tmp_path / FIXTURE.name).write_text(_fixture_text(), encoding="utf-8")

    items = manager.reload(force=True)
    assert [item.status for item in items] == ["enabled"]

    item = manager.set_enabled(FIXTURE.name, False)
    assert item.status == "disabled"
    assert item.enabled is False
    assert manager.documents() == ()
    assert (tmp_path / ".plugin-state.json").is_file()

    item = manager.set_enabled(FIXTURE.name, True)
    assert item.status == "enabled"
    assert item.enabled is True
    assert len(manager.documents()) == 1


def test_manager_rejects_unsafe_plugin_id(tmp_path):
    manager = PluginDocumentManager(directory=tmp_path)
    for bad in ("evil.md", "../x.inku-plugin.md", ".plugin-state.json", ""):
        with pytest.raises((PluginFormatError, FileNotFoundError)):
            manager.delete(bad)


# --- API level ---


def _install(plugin_dir) -> str:
    (plugin_dir / FIXTURE.name).write_text(_fixture_text(), encoding="utf-8")
    DOCUMENT_PLUGIN_MANAGER.reload(force=True)
    return FIXTURE.name


def test_api_plugin_list_toggle_and_delete_legacy(plugin_dir, admin_headers):
    """Legacy Markdown is listed as not drawn from, can be switched and deleted."""
    plugin_id = _install(plugin_dir)
    listed = client.get("/api/plugins", headers=admin_headers)
    assert listed.status_code == 200
    item = next(entry for entry in listed.json()["items"] if entry["id"] == plugin_id)
    assert item["has_definitions"] is False
    assert item["entries"]

    disabled = client.put(f"/api/plugins/{plugin_id}/enabled", headers=admin_headers, json={"enabled": False})
    assert disabled.status_code == 200 and disabled.json()["enabled"] is False
    enabled = client.put(f"/api/plugins/{plugin_id}/enabled", headers=admin_headers, json={"enabled": True})
    assert enabled.status_code == 200 and enabled.json()["status"] == "enabled"

    deleted = client.delete(f"/api/plugins/{plugin_id}", headers=admin_headers)
    assert deleted.status_code == 200 and deleted.json() == {"ok": True}
    assert not (plugin_dir / plugin_id).exists()


def test_api_a_package_the_drawing_uses_is_switched_not_deleted(plugin_dir, admin_headers, monkeypatch):
    plugin_id = _install(plugin_dir)
    import inku_server.plugins as plugins_module

    monkeypatch.setitem(plugins_module._BUNDLED_DOCUMENTS, (plugin_dir / plugin_id).resolve(), "Sketch.twin-arcs")
    listed = client.get("/api/plugins", headers=admin_headers)
    item = next(entry for entry in listed.json()["items"] if entry["id"] == plugin_id)
    assert item["has_definitions"] is True
    # The settings screen reads the same mark from the settings status.
    status = client.get("/api/settings/status", headers=admin_headers)
    assert status.status_code == 200
    loaded = status.json()["plugins"]["loaded"]
    assert next(entry for entry in loaded if entry["id"] == plugin_id)["has_definitions"] is True

    refused = client.delete(f"/api/plugins/{plugin_id}", headers=admin_headers)
    assert refused.status_code == 409
    assert (plugin_dir / plugin_id).is_file()


def test_api_plugin_documents_are_not_written_through_the_api(plugin_dir, admin_headers):
    """Writing a document that nothing draws from is gone with its screen (I-703)."""
    plugin_id = _install(plugin_dir)
    assert client.post("/api/plugins", headers=admin_headers, json={"content": _fixture_text()}).status_code == 405
    assert client.put(f"/api/plugins/{plugin_id}", headers=admin_headers, json={"content": _fixture_text()}).status_code == 405
    assert client.get(f"/api/plugins/{plugin_id}/content", headers=admin_headers).status_code == 404


def test_api_plugin_unsafe_id_and_missing(plugin_dir, admin_headers):
    assert client.put(
        "/api/plugins/missing.inku-plugin.md/enabled", headers=admin_headers, json={"enabled": False}
    ).status_code == 404
    assert client.delete("/api/plugins/missing.inku-plugin.md", headers=admin_headers).status_code == 404


def test_api_plugin_admin_only(plugin_dir, admin_headers, user_headers):
    plugin_id = _install(plugin_dir)
    assert client.put(
        f"/api/plugins/{plugin_id}/enabled", headers=user_headers, json={"enabled": False}
    ).status_code == 403
    assert client.delete(f"/api/plugins/{plugin_id}", headers=user_headers).status_code == 403
