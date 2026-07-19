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


def _second_plugin_text() -> str:
    return (
        _fixture_text()
        .replace("name: twin-arcs", "name: twin-arcs-b")
        .replace("## 語: 双弧", "## 語: 二重弧")
        .replace("surface_ja: 双弧", "surface_ja: 二重弧")
        .replace("fires_on_ja: 双弧", "fires_on_ja: 二重弧")
        .replace("surface_en: twin arcs", "surface_en: twin arcs b")
        .replace("fires_on_en: twin arcs", "fires_on_en: twin arcs b")
    )


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
        role="admin",
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
        role="user",
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


def test_manager_disable_excludes_from_documents_and_vocabulary(tmp_path):
    manager = PluginDocumentManager(directory=tmp_path)
    (tmp_path / FIXTURE.name).write_text(_fixture_text(), encoding="utf-8")

    items = manager.reload(force=True)
    assert [item.status for item in items] == ["enabled"]
    assert manager.prompt_vocabulary("ja")

    item = manager.set_enabled(FIXTURE.name, False)
    assert item.status == "disabled"
    assert item.enabled is False
    assert manager.documents() == ()
    assert manager.prompt_vocabulary("ja") == ()
    assert (tmp_path / ".plugin-state.json").is_file()

    item = manager.set_enabled(FIXTURE.name, True)
    assert item.status == "enabled"
    assert item.enabled is True
    assert len(manager.documents()) == 1


def test_manager_create_derives_filename_and_rejects_collision(tmp_path):
    manager = PluginDocumentManager(directory=tmp_path)
    item = manager.create(_fixture_text())
    assert item.path == "sketch-twin-arcs.inku-plugin.md"
    assert (tmp_path / item.path).is_file()

    with pytest.raises(FileExistsError):
        manager.create(_fixture_text())


def test_manager_update_reverts_on_cross_file_rejection(tmp_path):
    manager = PluginDocumentManager(directory=tmp_path)
    manager.create(_fixture_text())
    second = manager.create(_second_plugin_text())
    original = manager.content(second.path)

    # 二つ目を一つ目と同一 identity へ書き換え → reload 拒否 → 巻き戻し
    with pytest.raises(PluginFormatError):
        manager.update(second.path, _fixture_text())
    assert manager.content(second.path) == original
    assert {item.status for item in manager.items()} == {"enabled"}


def test_manager_rejects_unsafe_plugin_id(tmp_path):
    manager = PluginDocumentManager(directory=tmp_path)
    for bad in ("evil.md", "../x.inku-plugin.md", ".plugin-state.json", ""):
        with pytest.raises((PluginFormatError, FileNotFoundError)):
            manager.content(bad)


# --- API level ---


def test_api_plugin_crud_cycle(plugin_dir, admin_headers):
    created = client.post(
        "/api/plugins", headers=admin_headers, json={"content": _fixture_text()}
    )
    assert created.status_code == 201
    item = created.json()
    plugin_id = item["id"]
    assert plugin_id == "sketch-twin-arcs.inku-plugin.md"
    assert item["enabled"] is True
    assert item["status"] == "enabled"

    listed = client.get("/api/plugins", headers=admin_headers)
    assert listed.status_code == 200
    ids = {entry["id"] for entry in listed.json()["items"]}
    assert plugin_id in ids

    content = client.get(f"/api/plugins/{plugin_id}/content", headers=admin_headers)
    assert content.status_code == 200
    assert content.json()["content"] == _fixture_text()
    assert content.json()["editable"] is True

    updated = client.put(
        f"/api/plugins/{plugin_id}",
        headers=admin_headers,
        json={"content": _fixture_text().replace("version: 0.1.0", "version: 0.1.1")},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == "0.1.1"

    disabled = client.put(
        f"/api/plugins/{plugin_id}/enabled",
        headers=admin_headers,
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["enabled"] is False

    enabled = client.put(
        f"/api/plugins/{plugin_id}/enabled",
        headers=admin_headers,
        json={"enabled": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["status"] == "enabled"

    deleted = client.delete(f"/api/plugins/{plugin_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert (
        client.get(f"/api/plugins/{plugin_id}/content", headers=admin_headers).status_code
        == 404
    )


def test_api_plugin_create_conflict_and_invalid(plugin_dir, admin_headers):
    first = client.post(
        "/api/plugins", headers=admin_headers, json={"content": _fixture_text()}
    )
    assert first.status_code == 201

    conflict = client.post(
        "/api/plugins", headers=admin_headers, json={"content": _fixture_text()}
    )
    assert conflict.status_code == 409

    invalid = client.post(
        "/api/plugins", headers=admin_headers, json={"content": "not a plugin document"}
    )
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)


def test_api_plugin_unsafe_id_and_missing(plugin_dir, admin_headers):
    assert (
        client.get("/api/plugins/evil.md/content", headers=admin_headers).status_code == 422
    )
    assert (
        client.get(
            "/api/plugins/missing.inku-plugin.md/content", headers=admin_headers
        ).status_code
        == 404
    )
    assert (
        client.put(
            "/api/plugins/missing.inku-plugin.md/enabled",
            headers=admin_headers,
            json={"enabled": False},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            "/api/plugins/missing.inku-plugin.md", headers=admin_headers
        ).status_code
        == 404
    )


def test_api_plugin_admin_only(plugin_dir, admin_headers, user_headers):
    created = client.post(
        "/api/plugins", headers=admin_headers, json={"content": _fixture_text()}
    )
    plugin_id = created.json()["id"]

    assert (
        client.get(f"/api/plugins/{plugin_id}/content", headers=user_headers).status_code
        == 403
    )
    assert (
        client.post(
            "/api/plugins", headers=user_headers, json={"content": _fixture_text()}
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/plugins/{plugin_id}",
            headers=user_headers,
            json={"content": _fixture_text()},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/plugins/{plugin_id}/enabled",
            headers=user_headers,
            json={"enabled": False},
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/plugins/{plugin_id}", headers=user_headers).status_code == 403
    )
