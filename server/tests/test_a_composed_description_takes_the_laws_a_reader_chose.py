"""A composed description takes the laws a reader chose for it (stage B-5, 2026-10-20).

After the composition places the layers, the shared pipeline asks a reader for
the laws the work uses and prints the layers they change in numbers before the
commit (SPEC 12.6.4). The Server's runs carry the stage by default. Its request
is sent with Stage 1's model, timed apart from Stage 1 and kept for the prompt
tab with what it was given.
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

# The circle goes to the golden section's upper left crossing; the dots keep
# their hand.
LAWS = {"main_layer": 1, "main_law": "B1", "description_counts": [1],
        "laws": {"B1": {"targets": [{"layer": 1, "at": "point_ul"}]},
                 "B21": {"targets": [{"layer": 2, "hand": "still"}]}},
        "reason": "円を黄金分割の左上の交点に置く。"}


@pytest.fixture
def author():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"laws-{suffix}")
    user = db.add_user(
        username=f"laws-{suffix}",
        email=f"laws-{suffix}@example.test",
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
    """Stage 1, the reader and the laws stage each answering once, keeping each
    action. The color stage after the laws (a default) is refused once, so the
    run commits the document the laws printed."""
    actions: list[dict] = []
    answers = {
        "generate_normalized_ddl": ("normalized_ddl_generated", PLAN, "3"),
        "read_composition": ("composition_read", READING, "5"),
        "choose_laws": ("laws_chosen", LAWS, "7"),
    }

    class Provider:
        def __init__(self, _options, **_kwargs):
            pass

        def __call__(self, action):
            actions.append(action)
            if action["tag"] == "choose_colors":
                return {"tag": "provider_failed", "identity": action["identity"],
                        "failure": "provider_rejected", "elapsed_ms": "0"}
            tag, answer, elapsed = answers[action["tag"]]
            return {"tag": tag, "identity": action["identity"],
                    "response": json.dumps(answer, ensure_ascii=False), "elapsed_ms": elapsed}

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", Provider)
    return actions


def test_a_composed_description_is_printed_with_the_laws_its_reader_chose(author, sent):
    painted = client.post("/api/paint", json={
        "description": DESCRIPTION, "stage1_model": "nvidia:poolside/laguna-xs-2.1",
    }, headers=author)
    assert painted.status_code == 200, painted.text
    assert [action["tag"] for action in sent] == [
        "generate_normalized_ddl", "read_composition", "choose_laws", "choose_colors",
    ]
    laws = sent[2]["payload"]["prompt"]
    assert DESCRIPTION in laws["message"]

    body = painted.json()
    layers = body["ddl"].splitlines()[-3:]
    # The circle stands at the crossing the laws chose, written in numbers; the
    # field keeps the composition's range and the dots the place the
    # description states.
    assert layers[1] == "画面の横0.381966、縦0.381966の位置に、赤のペンの濃い塗りの小さな円を1個置く。", body["ddl"]
    assert "（横" in layers[0], body["ddl"]
    assert layers[2].startswith("下に、"), body["ddl"]
    # Stage 1's time is its own; the reading's and the laws' join only the total.
    assert body["elapsed_stage1_ms"] == 3
    assert body["elapsed_total_ms"] == 15

    prompts = client.get(f"/api/pipeline/variations/{body['pipeline_variation_id']}/system-prompts", headers=author)
    assert prompts.status_code == 200, prompts.text
    kept = prompts.json()
    assert kept["stages"] == ["sketch", "stage1", "composition", "laws", "colors", "stage2"]
    assert kept["laws"]["system"] == laws["system"]
    assert kept["laws"]["message"] == laws["message"]
