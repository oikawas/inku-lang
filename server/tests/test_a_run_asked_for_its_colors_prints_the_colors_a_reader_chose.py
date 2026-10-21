"""A run asked for its colors prints the colors a reader chose (2026-10-20).

After the laws stage the shared pipeline can ask a reader for the color laws
the work uses, and prints the colors they change before the commit. The color
stage is a default; in developer mode the option `developer_colors_stage`
also gives it to a run whose configuration has none. The run carries the seed the work is
drawn with, so that the stage's estimate of the drawing lays a scatter's
marks where the picture does, and the catalog's names of the nine paints the
request shows. The request is sent with Stage 1's model, timed apart from
Stage 1 and kept for the prompt tab with what it was given.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db, pipeline_product
from inku_server.api import app
from inku_server.persistence.variation_authority import VariationAuthorityStore

client = TestClient(app)

# No color words, so the reader may recolor every layer.
DESCRIPTION = "円がひとつ浮かび、下に点が散らばる"


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

# The circle goes to the golden section's upper left crossing.
LAWS = {"main_layer": 1, "main_law": "B1", "description_counts": [{"layer": 1, "words": "円がひとつ"}],
        "laws": {"B1": {"targets": [{"layer": 1, "at": "point_ul"}]},
                 "B21": {"targets": [{"layer": 2, "hand": "still"}]}},
        "reason": "円を黄金分割の左上の交点に置く。"}

# The circle, the laws' main layer, takes the blue.
COLORS = {"main_law": "D5", "laws": {"D5": {"hue": "blue"}}, "reason": "青を軸に近い色でまとめる。"}


@pytest.fixture
def author():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"colors-{suffix}")
    user = db.add_user(
        username=f"colors-{suffix}",
        email=f"colors-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield user["id"], {"Authorization": f"Bearer {token}"}
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


@pytest.fixture
def sent(monkeypatch):
    """Stage 1, the reader, the laws and the colors each answering once, keeping each action."""
    actions: list[dict] = []
    answers = {
        "generate_normalized_ddl": ("normalized_ddl_generated", PLAN, "3"),
        "read_composition": ("composition_read", READING, "5"),
        "choose_laws": ("laws_chosen", LAWS, "7"),
        "choose_colors": ("colors_chosen", COLORS, "11"),
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


def _start(headers: dict[str, str], options: dict):
    return client.post("/api/pipeline/variations", json={
        "kind": "description", "text": DESCRIPTION, "canvas_format_id": "square",
        "options": {"stage1_model": "nvidia:poolside/laguna-xs-2.1", "instruction_lang": "ja",
                    "catalog_id": "default", "catalog_mode": "fixed", "render_seed": "7", **options},
    }, headers=headers)


def _settled(headers: dict[str, str], view: dict) -> dict:
    deadline = time.monotonic() + 60
    while view["busy"]:
        assert time.monotonic() < deadline, "the run did not settle"
        time.sleep(0.05)
        response = client.get(f"/api/pipeline/variations/{view['variation_id']}", headers=headers)
        assert response.status_code == 200, response.text
        view = response.json()
    return view


def test_a_run_asked_for_its_colors_prints_the_colors_its_reader_chose(author, sent, monkeypatch):
    owner, headers = author
    monkeypatch.setenv("INKU_DEVELOPER_MODE", "1")
    started = _start(headers, {"developer_colors_stage": True})
    assert started.status_code == 200, started.text
    view = _settled(headers, started.json())
    assert [action["tag"] for action in sent] == [
        "generate_normalized_ddl", "read_composition", "choose_laws", "choose_colors",
    ]
    colors = sent[3]["payload"]["prompt"]
    assert DESCRIPTION in colors["message"]
    # The color table names the paint each of the nine colors draws.
    assert '"name":"black","paint":"黒"' in colors["message"], colors["message"]
    # The circle the laws placed is printed in the blue.
    assert "画面の横0.381966、縦0.381966の位置に、青のペンの濃い塗りの小さな円を1個置く。" in \
        view["document"]["source"].splitlines(), view["document"]["source"]

    state = json.loads(VariationAuthorityStore(db.engine).read_execution(owner, view["execution_id"]).state_bytes)
    # The estimate draws with the work's seed; the colors are timed apart from Stage 1.
    assert state["snapshot"]["config"]["colors"] == {"render_seed": "7"}
    assert state["context"]["metrics"] == {"stage1": 3, "composition": 5, "laws": 7, "colors": 11}

    prompts = client.get(f"/api/pipeline/variations/{view['variation_id']}/system-prompts", headers=headers)
    assert prompts.status_code == 200, prompts.text
    kept = prompts.json()
    assert kept["stages"] == ["sketch", "stage1", "composition", "laws", "colors", "stage2"]
    assert kept["colors"]["system"] == colors["system"]
    assert kept["colors"]["message"] == colors["message"]
