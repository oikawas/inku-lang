"""The account changes that used to lock a server out, or fail to lock one person out.

Each test runs on a database of its own: "the last administrator" only means
something when the test decides how many administrators there are.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.api import app
from inku_server.persistence.schema import Base


client = TestClient(app)


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'accounts.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine, autocommit=False, autoflush=False))
    db._ensure_permission_groups()


def _bearer(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {db.create_session(user['id'])}"}


def test_the_last_administrator_cannot_be_demoted_or_deleted(fresh_db) -> None:
    """Nothing in the product could give `admins` back afterwards."""
    admin = db.add_user("only-admin", "only@example.test", "password-1", ["admins"], None)
    headers = _bearer(admin)

    demoted = client.patch(f"/api/users/{admin['id']}", json={"permission_groups": ["users"]}, headers=headers)
    deleted = client.delete(f"/api/users/{admin['id']}", headers=headers)

    assert (demoted.status_code, deleted.status_code) == (409, 409)
    assert demoted.json()["detail"] == "the last administrator cannot be removed"
    assert db.has_permission_group(db.get_user(admin["id"]), "admins")

    db.add_user("second-admin", "second@example.test", "password-2", ["admins"], None)
    moved = client.patch(f"/api/users/{admin['id']}", json={"permission_groups": ["users"]}, headers=headers)
    assert moved.status_code == 200


def test_local_sign_in_cannot_be_turned_off(fresh_db) -> None:
    """The Google switch signs nobody in, so this was every account locked out."""
    admin = db.add_user("auth-admin", "auth@example.test", "password-1", ["admins"], None)
    before = db.get_auth_settings()

    response = client.put(
        "/api/auth/config",
        json={"google_enabled": True, "local_enabled": False},
        headers=_bearer(admin),
    )

    assert response.status_code == 409
    assert db.get_auth_settings() == before


def test_a_new_password_signs_the_account_out_elsewhere(fresh_db) -> None:
    admin = db.add_user("reset-admin", "reset@example.test", "password-1", ["admins"], None)
    member = db.add_user("member", "member@example.test", "password-2", ["users"], None)
    stolen = db.create_session(member["id"])

    reset = client.patch(f"/api/users/{member['id']}", json={"password": "password-3"}, headers=_bearer(admin))
    assert reset.status_code == 200
    assert db.get_session_user(stolen) is None

    here, elsewhere = db.create_session(member["id"]), db.create_session(member["id"])
    changed = client.patch(
        "/api/auth/me/profile",
        json={"password": "password-4", "current_password": "password-3"},
        headers={"Authorization": f"Bearer {here}"},
    )
    assert changed.status_code == 200
    assert db.get_session_user(here) is not None
    assert db.get_session_user(elsewhere) is None
