"""The bundled v2 package serves each word's original PNG at both scales."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.plugins import PLUGIN_PACKAGE_MANAGER

client = TestClient(app)


@pytest.fixture
def auth_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "directory", tmp_path / "packages")
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"preview-{suffix}")
    user = db.add_user(username=f"preview-{suffix}", email=f"preview-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_every_bundled_word_has_both_pictures(auth_headers):
    words = client.get("/api/saijiki?lang=ja", headers=auth_headers).json()["plugins"]
    assert len([word for word in words if word["qualified_name"].startswith("Nature.")]) == 7
    for word in words:
        if not word["qualified_name"].startswith("Nature."):
            continue
        assert word["preview_url"] and word["preview_url_2x"]
        assert not {"aliases", "fires_on_ja", "fires_on_en"} & word.keys()
        assert word["written_ja"].startswith("｛")
        assert not any(isinstance(value, str) and value.startswith("data:") for value in word.values())
        one = client.get(word["preview_url"], headers=auth_headers)
        two = client.get(word["preview_url_2x"], headers=auth_headers)
        assert one.status_code == two.status_code == 200
        assert one.headers["content-type"] == two.headers["content-type"] == "image/png"
        assert one.content != two.content


def test_preview_route_refuses_unknown_name_and_scale(auth_headers):
    assert client.get("/api/saijiki/plugin-preview?name=Nope.Nope", headers=auth_headers).status_code == 404
    assert client.get("/api/saijiki/plugin-preview?name=Nature.YoungLeaves&scale=3",
                      headers=auth_headers).status_code == 422
    assert client.get("/api/saijiki/plugin-preview?name=Nature.YoungLeaves").status_code == 401
