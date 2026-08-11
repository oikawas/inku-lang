"""T-6: the card endpoint asks who is calling, and only hands over their own work.

Measured through the app rather than by reading the decorator: a guard that is
declared but not reached is the failure this is here to catch.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app

client = TestClient(app)

WORK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" '
    'viewBox="0 0 600 600"><rect width="600" height="600" fill="#efe9dc"/></svg>'
)


def _user(prefix: str) -> tuple[dict, dict[str, str], str]:
    suffix = uuid.uuid4().hex[:8]
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=None,
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token


def _work(user_id: str, label: str) -> dict:
    return db.add_item(
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "at": 1_000,
            "input": label,
            "source_text": label,
            "ddl": "背景を白で塗る。",
            "score": {"canvas": "square", "instructions": []},
            "svg": WORK_SVG,
            "render_seed": 917364821,
            "history_visibility": "normal",
        }
    )


@pytest.fixture
def world():
    owner, owner_headers, owner_token = _user("card-owner")
    stranger, stranger_headers, stranger_token = _user("card-stranger")
    work = _work(owner["id"], "夕立のあと、濡れた石の匂いだけが残っている")
    try:
        yield {
            "owner_headers": owner_headers,
            "stranger_headers": stranger_headers,
            "work_id": work["id"],
        }
    finally:
        for token in (owner_token, stranger_token):
            db.delete_session(token)
        for user in (owner, stranger):
            db.delete_user(user["id"], cascade=True)


def test_the_card_route_refuses_a_caller_it_cannot_identify(world):
    anonymous = client.post(
        "/api/history/export-card", json={"id": world["work_id"]}
    )
    assert anonymous.status_code in (401, 403)

    identified = client.post(
        "/api/history/export-card",
        json={"id": world["work_id"]},
        headers=world["owner_headers"],
    )
    assert identified.status_code == 200
    assert identified.headers["content-type"] == "image/png"
    assert identified.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_somebody_elses_work_is_not_found(world):
    response = client.post(
        "/api/history/export-card",
        json={"id": world["work_id"]},
        headers=world["stranger_headers"],
    )
    assert response.status_code == 404
