"""Whether the generation information shows each stage's tokens is per user.

Off, it shows the work's total alone; on, the stages' rows follow it.  It is a
view preference of the account, stored in `model_settings` like the drawer's
follow choice (see test_user_generation_info_follows_selection.py).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.model_settings import (
    default_user_model_settings,
    normalize_user_model_settings,
    update_user_model_settings,
)

client = TestClient(app)

FIELD = "generation_info_token_detail"


@pytest.fixture
def auth_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"tokens-{suffix}")
    user = db.add_user(
        username=f"tokens-{suffix}",
        email=f"tokens-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_the_total_alone_is_shown_to_a_user_who_never_chose():
    assert default_user_model_settings()[FIELD] is False
    assert normalize_user_model_settings({})[FIELD] is False


def test_patching_another_setting_keeps_the_detail():
    on = update_user_model_settings({}, {FIELD: True})
    later = update_user_model_settings(on, {"sketch_open": False})
    assert later[FIELD] is True


def test_the_choice_survives_a_round_trip_through_the_api(auth_headers):
    patched = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {FIELD: True}},
    )
    assert patched.status_code == 200
    assert patched.json()["model_settings"][FIELD] is True

    current = client.get("/api/auth/me", headers=auth_headers)
    assert current.status_code == 200
    assert current.json()["model_settings"][FIELD] is True
