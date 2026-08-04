"""The colour catalogue choice is per user, and "auto" is one of its values.

Drawing needs a session -- every render route sits behind `_current_user` -- so
the choice belongs to the account, not to the browser.  `auto` shares the slot
with a catalogue id because the modal offers it as one more choice; the server
has to accept it there and refuse anything that is not a catalogue that still
exists.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.color_catalogs import DEFAULT_COLOR_CATALOG_ID, color_catalog_ids
from inku_server.model_settings import (
    default_user_model_settings,
    normalize_user_model_settings,
    update_user_model_settings,
)

client = TestClient(app)


@pytest.fixture
def auth_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"catalog-{suffix}")
    user = db.add_user(
        username=f"catalog-{suffix}",
        email=f"catalog-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def test_a_user_who_has_never_chosen_draws_with_the_default():
    assert default_user_model_settings()["color_catalog_id"] == DEFAULT_COLOR_CATALOG_ID


def test_auto_is_accepted_although_it_is_not_a_catalog():
    assert "auto" not in color_catalog_ids()
    assert normalize_user_model_settings({"color_catalog_id": "auto"})["color_catalog_id"] == "auto"
    assert update_user_model_settings({}, {"color_catalog_id": "auto"})["color_catalog_id"] == "auto"


def test_a_catalog_that_still_exists_is_kept():
    for catalog_id in color_catalog_ids():
        assert normalize_user_model_settings({"color_catalog_id": catalog_id})["color_catalog_id"] == catalog_id


@pytest.mark.parametrize(
    "stored",
    [
        "desert_mineral",  # retired in render engine 18
        "japanese",  # renamed away in 2026-05
        "",
        "   ",
        None,
        7,
        ["ink_season"],
    ],
)
def test_anything_that_is_not_a_live_catalog_falls_back(stored):
    # Storing a retired id would only answer 422 on the next drawing.
    assert normalize_user_model_settings({"color_catalog_id": stored})["color_catalog_id"] == DEFAULT_COLOR_CATALOG_ID


def test_the_choice_survives_a_round_trip_through_the_api(auth_headers):
    patched = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"color_catalog_id": "auto"}},
    )
    assert patched.status_code == 200
    assert patched.json()["model_settings"]["color_catalog_id"] == "auto"

    current = client.get("/api/auth/me", headers=auth_headers)
    assert current.status_code == 200
    assert current.json()["model_settings"]["color_catalog_id"] == "auto"

    # And a second user is not handed the first one's choice.
    back = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"color_catalog_id": "ink_season"}},
    )
    assert back.status_code == 200
    assert back.json()["model_settings"]["color_catalog_id"] == "ink_season"


def test_patching_another_setting_does_not_clear_the_choice(auth_headers):
    client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"color_catalog_id": "auto"}},
    )
    other = client.patch(
        "/api/auth/me/settings",
        headers=auth_headers,
        json={"model_settings": {"instruction_caption_visible": False}},
    )
    assert other.status_code == 200
    assert other.json()["model_settings"]["color_catalog_id"] == "auto"
