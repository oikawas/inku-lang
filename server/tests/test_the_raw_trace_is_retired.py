"""The RAW trace left with the Python layers it recorded (2026-09-25).

`include_trace` and `trace` are gone from the request and response models, and
the whole-surface gate records that. What it cannot say is how an older client
that still sends the field is answered: it is drawn as if it had not asked.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app

client = TestClient(app)


@pytest.fixture
def auth():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"trace-{suffix}")
    user = db.add_user(
        username=f"trace-{suffix}",
        email=f"trace-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


def test_an_older_client_asking_for_the_trace_is_drawn_without_one(auth):
    composed = client.post(
        "/api/compose",
        json={"ddl": "中心に黒い円を置く。", "include_trace": True},
        headers=auth,
    )
    assert composed.status_code == 200, composed.text
    assert "trace" not in composed.json()
    assert "<svg" in composed.json()["svg"]
