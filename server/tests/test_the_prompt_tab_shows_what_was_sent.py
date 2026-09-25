"""The prompt tab shows the system prompts a work actually sent (2026-09-25).

The tab once showed a prompt rebuilt from the Python layers, presented as the
one sent; it left with those layers. The shared pipeline builds each system
prompt per work -- installed plugins, the sketch note and compiler feedback
join Stage 1, and relation grammar joins Stage 2 only when the DDL needs it --
so the host keeps the one it sent, on the execution, for its owner to read.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db, pipeline_product
from inku_server.api import app
from inku_server.pipeline_product import record_system_prompt

client = TestClient(app)

DDL = "中心に黒い円を置く。"


@pytest.fixture
def author():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"prompt-tab-{suffix}")
    user = db.add_user(
        username=f"prompt-tab-{suffix}",
        email=f"prompt-tab-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


@pytest.fixture
def sent(monkeypatch):
    """Stage 1 answering one fixed drawing, keeping each action it was sent."""
    actions: list[dict] = []

    class Stage1:
        def __init__(self, _options, **_kwargs):
            pass

        def __call__(self, action):
            actions.append(action)
            return {
                "tag": "normalized_ddl_generated",
                "identity": action["identity"],
                "response": json.dumps({"normalized_ddl": DDL}),
                "elapsed_ms": "3",
            }

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", Stage1)
    return actions


def _system_prompts(headers: dict[str, str], variation_id: str):
    return client.get(f"/api/pipeline/variations/{variation_id}/system-prompts", headers=headers)


def test_a_drawing_shows_the_stage_1_system_prompt_it_sent(author, sent):
    painted = client.post("/api/paint", json={"description": "一滴の墨"}, headers=author)
    assert painted.status_code == 200, painted.text

    response = _system_prompts(author, painted.json()["pipeline_variation_id"])
    assert response.status_code == 200, response.text
    body = response.json()
    prompt = sent[-1]["payload"]["prompt"]
    assert body["recorded"] is True
    assert body["stage1"] == {
        "system": prompt["system"],
        "prompt_id": prompt["prompt_id"],
        "prompt_digest": prompt["prompt_digest"],
        "instruction_language": prompt["instruction_language"],
        "attempt": 1,
    }
    # No hole was left, so Stage 2 never called a model.
    assert body["stage2"] is None


def _action(tag: str, attempt: int, system: str) -> dict:
    return {
        "tag": tag,
        "identity": {"action_id": "a", "attempt": str(attempt), "request_digest": "d"},
        "payload": {
            "prompt": {
                "system": system,
                "prompt_id": f"{tag}-prompt",
                "prompt_digest": f"digest-{attempt}",
                "instruction_language": "ja",
            }
        },
    }


def test_the_last_attempt_of_each_stage_is_kept_and_other_actions_are_not():
    context: dict = {"system_prompts": {}}
    record_system_prompt(context, _action("generate_normalized_ddl", 1, "first"))
    record_system_prompt(context, _action("generate_normalized_ddl", 2, "with feedback"))
    record_system_prompt(context, _action("complete_visible_ddl_holes", 1, "holes"))
    record_system_prompt(context, _action("generate_sketch", 1, "sketch"))

    assert context["system_prompts"]["stage1"]["system"] == "with feedback"
    assert context["system_prompts"]["stage1"]["attempt"] == 2
    assert context["system_prompts"]["stage2"]["system"] == "holes"
    assert set(context["system_prompts"]) == {"stage1", "stage2"}
