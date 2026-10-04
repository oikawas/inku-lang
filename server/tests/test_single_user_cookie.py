"""A host-wide cookie must not close a single-user installation's own entry."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_single_user_cookie_keeps_fixed_owner_and_explicit_auth_boundaries(monkeypatch):
    from inku_server import db
    from inku_server.api_core.routers import me
    from inku_server.security import CrossSiteWriteGuardMiddleware

    owner = {
        "id": "fixture-fixed-owner", "username": "owner", "email": "owner@example.test",
        "permission_groups": ["admins"], "permission_group_labels": ["Administrators"], "at": 1,
    }
    other = {**owner, "id": "fixture-other-owner", "username": "other"}
    mode = {"enabled": True}
    pin = {"user": owner}
    writes = []
    monkeypatch.setattr(db, "single_user_mode_enabled", lambda: mode["enabled"])
    monkeypatch.setattr(db, "single_user_account", lambda: pin["user"])
    monkeypatch.setattr(db, "get_session_user", lambda token: other if token == "fixture-valid-other" else None)

    def update_settings(user_id, **settings):
        writes.append(user_id)
        return {**owner, **{key: value for key, value in settings.items() if value is not None}}

    monkeypatch.setattr(db, "update_user_settings", update_settings)
    app = FastAPI()
    app.include_router(me.router)
    app.add_middleware(CrossSiteWriteGuardMiddleware, origin_allowed=lambda origin: origin == "http://testserver")
    invalid_cookie = {"Cookie": "inku_session=fixture-invalid"}
    other_cookie = {"Cookie": "inku_session=fixture-valid-other"}
    with TestClient(app) as client:
        # This is the reported 401, through the real route and dependencies.
        answer = client.get("/api/auth/me", headers=invalid_cookie)
        assert answer.status_code == 200, answer.text
        assert answer.json()["id"] == owner["id"]
        assert "set-cookie" not in answer.headers
        # A valid cookie from another port must not change the pinned owner
        # either; downstream personal ChatGPT routes receive this same actor.
        answer = client.get("/api/auth/me", headers=other_cookie)
        assert answer.status_code == 200 and answer.json()["id"] == owner["id"]
        assert "set-cookie" not in answer.headers
        rejected = client.get("/api/auth/me", headers={**invalid_cookie, "Authorization": "Bearer fixture-invalid"})
        assert rejected.status_code == 401
        explicit = client.get("/api/auth/me", headers={**invalid_cookie, "Authorization": "Bearer fixture-valid-other"})
        assert explicit.status_code == 200 and explicit.json()["id"] == other["id"]

        cross_site = client.patch("/api/auth/me/settings", json={"ui_mode": "full"}, headers={
            **invalid_cookie, "Sec-Fetch-Site": "cross-site", "Origin": "https://other.example.test",
        })
        assert cross_site.status_code == 403 and writes == []
        same_origin = client.patch("/api/auth/me/settings", json={"ui_mode": "full"}, headers={
            **invalid_cookie, "Sec-Fetch-Site": "same-origin", "Origin": "http://testserver",
        })
        assert same_origin.status_code == 200 and writes == [owner["id"]]

        pin["user"] = None
        assert client.get("/api/auth/me", headers=invalid_cookie).status_code == 401
        pin["user"] = owner
        mode["enabled"] = False
        assert client.get("/api/auth/me", headers=invalid_cookie).status_code == 401
        signed_in = client.get("/api/auth/me", headers=other_cookie)
        assert signed_in.status_code == 200 and signed_in.json()["id"] == other["id"]
