"""The server calls a model with its own credentials, so the models an
administrator switches off -- or that no provider lists -- are refused to the
other members, not only left out of their menus."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.api_core.routers import public
from inku_server.model_settings import default_model_settings, model_is_offered, update_model_settings


client = TestClient(app)


def _bearer(groups: list[str]) -> dict[str, str]:
    name = f"model-{uuid.uuid4().hex[:8]}"
    user = db.add_user(name, f"{name}@example.test", "password-1", groups, None)
    return {"Authorization": f"Bearer {db.create_session(user['id'])}"}


def test_a_member_cannot_name_a_model_no_provider_offers(monkeypatch) -> None:
    member, admin = _bearer(["users"]), _bearer(["admins"])
    unlisted = "openai:gpt-nobody-listed"

    started = client.post(
        "/api/pipeline/variations",
        json={"kind": "description", "text": "a pond at dusk", "options": {"stage1_model": unlisted}},
        headers=member,
    )
    assert started.status_code == 403
    assert started.json()["detail"]["code"] == "model_not_offered"

    monkeypatch.setattr(public, "_generate_demo_instruction", lambda *_args, **_kwargs: "a pond at dusk")
    asked = {"seed_phrase": "pond", "model": unlisted}
    refused = client.post("/api/demo/instruction", json=asked, headers=member)
    assert (refused.status_code, refused.json()["detail"]) == (403, "model is not offered on this server")
    # Administrators choose what to offer, and try a model before offering it.
    assert client.post("/api/demo/instruction", json=asked, headers=admin).status_code == 200


def test_switching_a_model_off_withholds_it_and_developer_mode_does_not() -> None:
    # The built-in Stage default sits with a provider only developer mode shows.
    settings = default_model_settings()
    assert model_is_offered("nvidia", "google/gemma-4-31b-it", settings, purpose="llm")

    switched_off = update_model_settings(
        settings, {"providers": {"nvidia": {"enabled_models": {"google/gemma-4-31b-it": False}}}}
    )
    assert not model_is_offered("nvidia", "google/gemma-4-31b-it", switched_off, purpose="llm")
