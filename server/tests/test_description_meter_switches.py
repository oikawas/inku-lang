"""Each language's description meter can be turned off in Settings > Other (server).

Both are on until an admin turns one off. Every signed-in page reads the
switches from /api/client-config; a count asked for while its language is off
is refused.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.persistence.settings import normalize_description_meter_settings

client = TestClient(app)


@pytest.fixture
def member_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"meter-{suffix}")
    user = db.add_user(
        username=f"meter-{suffix}",
        email=f"meter-{suffix}@example.test",
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
def japanese_off():
    before = db.get_description_meter_settings()
    db.update_description_meter_settings(False, before["english"])
    yield
    db.update_description_meter_settings(before["japanese"], before["english"])


def test_both_are_on_until_turned_off():
    assert normalize_description_meter_settings(None) == {"japanese": True, "english": True}
    assert normalize_description_meter_settings({"japanese": False}) == {"japanese": False, "english": True}
    assert normalize_description_meter_settings({"english": "no"}) == {"japanese": True, "english": True}


def test_a_page_reads_the_switch_and_the_count_is_refused(member_headers, japanese_off):
    config = client.get("/api/client-config", headers=member_headers).json()
    assert config["description_meter"] == {"japanese": False, "english": True}
    refused = client.post("/api/description/mora", json={"text": "古池や"}, headers=member_headers)
    assert refused.status_code == 409
    counted = client.post("/api/description/syllables", json={"text": "An old pond"}, headers=member_headers)
    assert counted.status_code == 200
