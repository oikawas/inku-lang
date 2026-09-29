"""Whether the generation-information drawer follows the history strip is per user.

With it on, choosing another work from the history strip while the drawer is
open keeps the drawer open and shows that work's information; with it off, the
press outside closes the drawer as it always did.  It is a view preference of
the account, stored in `model_settings` like the describe panel's folds (see
test_user_describe_panel_folds.py).
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

FIELD = "generation_info_follows_selection"


@pytest.fixture
def auth_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"geninfo-{suffix}")
    user = db.add_user(
        username=f"geninfo-{suffix}",
        email=f"geninfo-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_it_is_on_for_a_user_who_never_chose():
    assert default_user_model_settings()[FIELD] is True
    assert normalize_user_model_settings({})[FIELD] is True


@pytest.mark.parametrize("value", [True, False])
def test_a_stored_choice_is_kept(value):
    assert normalize_user_model_settings({FIELD: value})[FIELD] is value


def test_patching_another_setting_does_not_turn_it_back_on():
    off = update_user_model_settings({}, {FIELD: False})
    later = update_user_model_settings(off, {"sketch_open": False})
    assert later[FIELD] is False


def test_the_choice_survives_a_round_trip_through_the_api(auth_headers):
    patched = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {FIELD: False}},
    )
    assert patched.status_code == 200
    assert patched.json()["model_settings"][FIELD] is False

    current = client.get("/api/auth/me", headers=auth_headers)
    assert current.status_code == 200
    assert current.json()["model_settings"][FIELD] is False

    back = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {FIELD: True}},
    )
    assert back.status_code == 200
    assert back.json()["model_settings"][FIELD] is True
