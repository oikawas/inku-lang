"""Whether each foldable section of the describe panel is open is per user.

写生 (Stage 0.5) and 展開後 (Stage 2 input) can both be folded away.  Neither
has anything to show without a session, so the fold belongs to the account
rather than to the browser -- the same reason the colour catalogue does (see
test_user_color_catalog_setting.py).

The two defaults differ and must not be collapsed into one: the sketch prose
was on screen before it could be folded, so an account that has never folded it
keeps seeing it; the expanded DDL has always started folded.
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

FOLD_FIELDS = ("sketch_open", "ddl_expanded_open")


@pytest.fixture
def auth_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"folds-{suffix}")
    user = db.add_user(
        username=f"folds-{suffix}",
        email=f"folds-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_a_user_who_has_never_folded_anything_gets_each_default():
    default = default_user_model_settings()
    assert default["sketch_open"] is True
    assert default["ddl_expanded_open"] is False
    # One shared default would silently change one of the two sections.
    assert default["sketch_open"] != default["ddl_expanded_open"]


def test_an_absent_field_is_not_a_fold():
    clean = normalize_user_model_settings({})
    assert clean["sketch_open"] is True
    assert clean["ddl_expanded_open"] is False


@pytest.mark.parametrize("field", FOLD_FIELDS)
@pytest.mark.parametrize("value", [True, False])
def test_a_stored_fold_is_kept(field, value):
    assert normalize_user_model_settings({field: value})[field] is value


@pytest.mark.parametrize("field", FOLD_FIELDS)
def test_each_field_moves_only_its_own_section(field):
    other = next(f for f in FOLD_FIELDS if f != field)
    default = default_user_model_settings()
    patched = update_user_model_settings({}, {field: not default[field]})
    assert patched[field] is (not default[field])
    assert patched[other] is default[other]


def test_the_fold_survives_a_round_trip_through_the_api(auth_headers):
    patched = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"sketch_open": False, "ddl_expanded_open": True}},
    )
    assert patched.status_code == 200
    assert patched.json()["model_settings"]["sketch_open"] is False
    assert patched.json()["model_settings"]["ddl_expanded_open"] is True

    current = client.get("/api/auth/me", headers=auth_headers)
    assert current.status_code == 200
    assert current.json()["model_settings"]["sketch_open"] is False
    assert current.json()["model_settings"]["ddl_expanded_open"] is True


def test_unfolding_again_is_stored_too(auth_headers):
    # A fold that could only be set and never cleared would read as working
    # for one turn and then stick.
    client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"sketch_open": False}},
    )
    back = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"sketch_open": True}},
    )
    assert back.status_code == 200
    assert back.json()["model_settings"]["sketch_open"] is True


def test_patching_another_setting_does_not_unfold(auth_headers):
    client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"sketch_open": False, "ddl_expanded_open": True}},
    )
    other = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"color_catalog_id": "default"}},
    )
    assert other.status_code == 200
    assert other.json()["model_settings"]["sketch_open"] is False
    assert other.json()["model_settings"]["ddl_expanded_open"] is True
