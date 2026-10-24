"""A leader who is not an administrator cannot take a member out of their user group.

The route checked `group_id` only when it was not None, so a leader who sent
`"group_id": null` passed, and the store then cleared the member's group
(found while writing the API reference, 2026-10-24). Sending null is a move
like any other: only an administrator may make it.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app

client = TestClient(app)


def _headers(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {db.create_session(user['id'])}"}


def _world() -> tuple[dict, dict, dict, dict]:
    suffix = uuid.uuid4().hex[:8]
    admin_group = db.add_user_group(f"admins-{suffix}")
    group = db.add_user_group(f"class-{suffix}")
    admin = db.add_user(
        username=f"admin-{suffix}", email=f"admin-{suffix}@example.test", password="password-123",
        permission_groups=["admins"], group_id=admin_group["id"],
    )
    leader = db.add_user(
        username=f"leader-{suffix}", email=f"leader-{suffix}@example.test", password="password-123",
        permission_groups=["leaders"], group_id=group["id"],
    )
    member = db.add_user(
        username=f"member-{suffix}", email=f"member-{suffix}@example.test", password="password-123",
        permission_groups=["users"], group_id=group["id"],
    )
    return admin, leader, member, group


def _group_of(user_id: str) -> str | None:
    return next(user for user in db.list_users() if user["id"] == user_id)["group_id"]


def test_a_leader_cannot_clear_a_members_group() -> None:
    _, leader, member, group = _world()

    response = client.patch(f"/api/users/{member['id']}", json={"group_id": None}, headers=_headers(leader))

    assert response.status_code == 403
    assert _group_of(member["id"]) == group["id"]


def test_a_leader_may_still_name_their_own_group() -> None:
    _, leader, member, group = _world()

    response = client.patch(f"/api/users/{member['id']}", json={"group_id": group["id"]}, headers=_headers(leader))

    assert response.status_code == 200
    assert _group_of(member["id"]) == group["id"]


def test_an_administrator_may_clear_a_members_group() -> None:
    admin, _, member, _ = _world()

    response = client.patch(f"/api/users/{member['id']}", json={"group_id": None}, headers=_headers(admin))

    assert response.status_code == 200
    assert _group_of(member["id"]) is None
