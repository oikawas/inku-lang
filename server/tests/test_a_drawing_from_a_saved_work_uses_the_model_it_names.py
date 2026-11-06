"""A drawing forked from a saved work is drawn with the model the request names.

The layout options (`/api/compose` with `work_id`) send the model of the input
panel's tab as `model`, which reads as Stage 2 only. The fork starts from the
saved work's record, which holds both Stage 1 and Stage 2, and the one drawing
model was taken as "Stage 1, else Stage 2" of the merged choices -- so the
saved work's Stage 1 came first, and the work was drawn and recorded with the
parent's model whatever the request named (2026-11-06, the author: the DDL
editor and the layout options draw with the input panel's conditions).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app

client = TestClient(app)

PARENT_MODEL = "nvidia:google/gemma-4-31b-it"
NAMED_MODEL = "nvidia:poolside/laguna-xs-2.1"


@pytest.fixture
def author():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"fork-model-{suffix}")
    user = db.add_user(
        username=f"fork-model-{suffix}",
        email=f"fork-model-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


def test_a_fork_of_a_saved_work_is_drawn_with_the_named_model(author):
    saved = client.post(
        "/api/history",
        json={
            "input": "円",
            "ddl": "中心に黒い円を置く。",
            "score": {"instructions": [{"primitive": "ellipse", "at": {"region": [0.4, 0.4, 0.6, 0.6]}}]},
            "at": 1_785_000_000_000,
            "stage1_model": PARENT_MODEL,
            "stage2_model": PARENT_MODEL,
        },
        headers=author,
    )
    assert saved.status_code == 200, saved.text

    composed = client.post(
        "/api/compose",
        json={"ddl": "中心に黒い円を置く。", "work_id": saved.json()["id"], "model": NAMED_MODEL},
        headers=author,
    )
    assert composed.status_code == 200, composed.text
    # The compose answer carries only Stage 2; one model draws both stages.
    assert composed.json()["stage2_model"] == NAMED_MODEL


def test_a_fork_that_names_no_model_keeps_the_saved_works(author):
    saved = client.post(
        "/api/history",
        json={
            "input": "円",
            "ddl": "中心に黒い円を置く。",
            "score": {"instructions": [{"primitive": "ellipse", "at": {"region": [0.4, 0.4, 0.6, 0.6]}}]},
            "at": 1_785_000_000_001,
            "stage1_model": NAMED_MODEL,
            "stage2_model": NAMED_MODEL,
        },
        headers=author,
    )
    assert saved.status_code == 200, saved.text

    composed = client.post(
        "/api/compose",
        json={"ddl": "中心に黒い円を置く。", "work_id": saved.json()["id"]},
        headers=author,
    )
    assert composed.status_code == 200, composed.text
    assert composed.json()["stage2_model"] == NAMED_MODEL
