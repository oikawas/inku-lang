"""Keep the per-user sketch fold while retiring the expanded DDL setting."""

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


def test_a_user_who_has_never_folded_anything_sees_the_sketch():
    default = default_user_model_settings()
    assert default["sketch_open"] is True
    assert "ddl_expanded_open" not in default


def test_an_absent_field_is_not_a_fold():
    clean = normalize_user_model_settings({})
    assert clean["sketch_open"] is True
    assert "ddl_expanded_open" not in clean


@pytest.mark.parametrize("value", [True, False])
def test_a_stored_fold_is_kept(value):
    assert normalize_user_model_settings({"sketch_open": value})["sketch_open"] is value


def test_a_retired_fold_is_ignored_without_resetting_current_settings():
    stored = {"sketch_open": False, "ddl_expanded_open": True, "color_catalog_id": "auto"}
    clean = normalize_user_model_settings(stored)
    assert clean["sketch_open"] is False
    assert clean["color_catalog_id"] == "auto"
    assert "ddl_expanded_open" not in clean
    patched = update_user_model_settings(stored, {"ddl_expanded_open": False})
    assert patched["sketch_open"] is False
    assert patched["color_catalog_id"] == "auto"
    assert "ddl_expanded_open" not in patched


def test_the_fold_survives_a_round_trip_through_the_api(auth_headers):
    patched = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"sketch_open": False, "ddl_expanded_open": True}},
    )
    assert patched.status_code == 200
    assert patched.json()["model_settings"]["sketch_open"] is False
    assert "ddl_expanded_open" not in patched.json()["model_settings"]

    current = client.get("/api/auth/me", headers=auth_headers)
    assert current.status_code == 200
    assert current.json()["model_settings"]["sketch_open"] is False
    assert "ddl_expanded_open" not in current.json()["model_settings"]


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
    assert "ddl_expanded_open" not in other.json()["model_settings"]
