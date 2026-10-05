"""A drawn description is composed from a reading of it (2026-10-02).

Stage 1 places a layer only where the description states its place. The shared
pipeline then asks for a reading of the description and places the other layers
on numeric ranges of the thirds grid. The reading is sent
with Stage 1's model and timed apart from it.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db, pipeline_product
from inku_server.api import app

client = TestClient(app)

DESCRIPTION = "赤い円がひとつ浮かび、下に黒い点が散らばる"


def _layer(action: str, shape: str, count: int, position: str, size: str, color: str) -> dict:
    return {
        "action": action, "angle": "unspecified", "bleeding": "unspecified", "color": color,
        "continuity": "unspecified", "count": count, "handling": "dense",
        "line_up_direction": "unspecified", "motion_amplitude": "unspecified",
        "motion_quality": "unspecified", "position": position, "proportion": "unspecified",
        "shape": shape, "size": size, "surface": "empty" if shape == "point" else "flat",
        "thinness": "unspecified", "tool": "pen",
    }


PLAN = {"ground": "paper", "background": "white", "plugins": [], "layers": [
    _layer("fill", "square", 1, "unspecified", "large", "gray"),
    _layer("place", "circle", 1, "center", "small", "red"),
    _layer("scatter", "point", 12, "bottom", "very_small", "black"),
]}

READING = {
    "thesis": "ひとつの円が点の床の上に浮かぶ",
    "roles": ["field", "focal", "scattered"],
    "relations": [{"type": "above", "layers": [1, 2], "side": "unspecified", "toward": "unspecified"}],
    "tension": {"motion": "still", "focus": "unspecified", "vertical": "unspecified",
                "balance": "unspecified", "symmetry": "unspecified", "void": "unspecified"},
    "stated_places": [{"layer": 2, "words": "下に", "place": "bottom"}],
}


@pytest.fixture
def author():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"composition-{suffix}")
    user = db.add_user(
        username=f"composition-{suffix}",
        email=f"composition-{suffix}@example.test",
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
    """Stage 1 answering one plan and the reader one reading, keeping each action."""
    actions: list[dict] = []
    answers = {
        "generate_normalized_ddl": ("normalized_ddl_generated", PLAN, "3"),
        "read_composition": ("composition_read", READING, "5"),
    }

    class Provider:
        def __init__(self, _options, **_kwargs):
            pass

        def __call__(self, action):
            actions.append(action)
            tag, answer, elapsed = answers[action["tag"]]
            return {"tag": tag, "identity": action["identity"],
                    "response": json.dumps(answer, ensure_ascii=False), "elapsed_ms": elapsed}

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", Provider)
    return actions


def test_a_description_is_composed_from_its_reading(author, sent):
    table = client.get("/api/composition/ranges", headers=author)
    assert table.status_code == 200, table.text
    assert table.json()["schema"] == "inku.composition-ranges.v1"
    assert len(table.json()["ranges"]) == 32
    painted = client.post("/api/paint", json={"description": DESCRIPTION}, headers=author)
    assert painted.status_code == 200, painted.text
    assert [action["tag"] for action in sent] == ["generate_normalized_ddl", "read_composition"]
    reading = sent[1]["payload"]["prompt"]
    assert reading["message"].startswith("記述:\n" + DESCRIPTION + "\n")
    assert "〔下絵が付けた場所: 下〕" in reading["message"]

    body = painted.json()
    layers = body["ddl"].splitlines()[-3:]
    # The field and the circle are placed by the composition; the dots keep the
    # place the description states.
    assert "（横" in layers[0], body["ddl"]
    assert "（横" in layers[1], body["ddl"]
    assert layers[2].startswith("下に、"), body["ddl"]
    assert body["elapsed_stage1_ms"] == 3
    assert body["elapsed_total_ms"] == 8
