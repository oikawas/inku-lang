"""The warning before painting from a picture is turned on and off in Settings > Other (server).

It is on until an admin turns it off. Every signed-in page reads the switch
from /api/client-config; only an administrator may change it.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.persistence.settings import normalize_image_upload_notice_settings

client = TestClient(app)


@pytest.fixture
def member_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"notice-{suffix}")
    user = db.add_user(
        username=f"notice-{suffix}",
        email=f"notice-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


@pytest.fixture
def notice_restored():
    before = db.get_image_upload_notice_settings()
    yield
    db.update_image_upload_notice_settings(before["enabled"])


def test_it_is_on_until_turned_off():
    assert normalize_image_upload_notice_settings(None) == {"enabled": True}
    assert normalize_image_upload_notice_settings({"enabled": False}) == {"enabled": False}
    assert normalize_image_upload_notice_settings({"enabled": "no"}) == {"enabled": True}


def test_a_page_reads_the_switch_an_admin_turned_off(member_headers, notice_restored):
    db.update_image_upload_notice_settings(False)
    config = client.get("/api/client-config", headers=member_headers).json()
    assert config["image_upload_notice"] == {"enabled": False}
    db.update_image_upload_notice_settings(True)
    config = client.get("/api/client-config", headers=member_headers).json()
    assert config["image_upload_notice"] == {"enabled": True}


def test_a_member_cannot_turn_it_off(member_headers, notice_restored):
    db.update_image_upload_notice_settings(True)
    refused = client.put("/api/settings/image-upload-notice", json={"enabled": False}, headers=member_headers)
    assert refused.status_code == 403
    assert db.get_image_upload_notice_settings() == {"enabled": True}
