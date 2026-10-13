"""The prompt tab shows the system prompts a work actually sent (2026-09-25).

The tab once showed a prompt rebuilt from the Python layers, presented as the
one sent; it left with those layers. The shared pipeline builds each system
prompt per work -- installed plugins, the sketch note and compiler feedback
join Stage 1, and relation grammar joins Stage 2 only when the DDL needs it --
so the host keeps the one it sent, on the execution, for its owner to read.
The sketch and the composition reading joined the tab on 2026-10-13, with what
they were given; `stages` tells a stage that called no model from one drawn
before its record began.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db, pipeline_product
from inku_server.api import app
from inku_server.pipeline_product import record_system_prompt, system_prompts_view

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
    # No hole was left, so Stage 2 never called a model; nor did a sketch or a
    # reading. The execution kept every stage, so each reads as not sent.
    assert body["stage2"] is None
    assert body["sketch"] is None and body["composition"] is None
    assert body["stages"] == ["sketch", "stage1", "composition", "stage2"]


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
                "message": f"{tag} message",
            }
        },
    }


def test_the_last_attempt_of_each_stage_is_kept_and_other_actions_are_not():
    context: dict = {"system_prompts": {}}
    record_system_prompt(context, _action("generate_sketch", 1, "sketch"))
    record_system_prompt(context, _action("select_description_catalog", 1, "catalog"))
    record_system_prompt(context, _action("generate_normalized_ddl", 1, "first"))
    record_system_prompt(context, _action("generate_normalized_ddl", 2, "with feedback"))
    record_system_prompt(context, _action("read_composition", 1, "reading"))
    record_system_prompt(context, _action("complete_visible_ddl_holes", 1, "holes"))

    prompts = context["system_prompts"]
    assert prompts["stage1"]["system"] == "with feedback"
    assert prompts["stage1"]["attempt"] == 2
    assert prompts["stage2"]["system"] == "holes"
    assert prompts["sketch"]["system"] == "sketch"
    assert prompts["composition"]["system"] == "reading"
    # The catalog choice is not shown.
    assert set(prompts) == {"sketch", "stage1", "composition", "stage2"}
    # The sketch and the reading keep what they were given; Stage 1 and Stage 2 as before.
    assert prompts["sketch"]["message"] == "generate_sketch message"
    assert prompts["composition"]["message"] == "read_composition message"
    assert set(prompts["stage1"]) == set(prompts["stage2"]) == {
        "system", "prompt_id", "prompt_digest", "instruction_language", "attempt"
    }


def test_a_prompt_without_a_message_is_kept_without_one():
    action = _action("read_composition", 1, "reading")
    del action["payload"]["prompt"]["message"]
    context: dict = {"system_prompts": {}}
    record_system_prompt(context, action)
    assert context["system_prompts"]["composition"]["system"] == "reading"
    assert "message" not in context["system_prompts"]["composition"]


def test_an_execution_from_before_the_sketch_and_the_reading_kept_stage_1_and_stage_2():
    kept = {"stage1": {"system": "planner"}, "stage2": None}
    # Saved before 2026-10-13: no list of stages.
    assert system_prompts_view({"system_prompts": kept}) == {
        "recorded": True,
        "stages": ["stage1", "stage2"],
        "sketch": None,
        "stage1": {"system": "planner"},
        "composition": None,
        "stage2": None,
    }
    # Saved before the record began at all.
    assert system_prompts_view({})["recorded"] is False
    assert system_prompts_view({})["stages"] == []
