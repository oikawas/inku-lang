"""The AI refinement's runs (2026-10-21): the Server takes the moves and keeps the children.

The shared core decides the tries, the gate and the record
(``test_autonomous_refine_core.py`` holds its table). These tests guard what the
Server adds around it, one failure each (the stage 3 plan's checks): a run that
does not stop as the core says, a laws child that loses the basis the next laws
move reads, a sentence added twice down a lineage, a stop that leaves the
drawing going, a run left "running" by a restart, and an owner with two runs.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import autonomous_refine, db, pipeline_compat, pipeline_product
from inku_server.api import app
from inku_server.api_core.routers import render
from inku_server.autonomous_refine import AutonomousRunner, RunStore
from inku_server.pipeline_api import laws_records_of
from inku_server.pipeline_runtime import get_service
from .test_a_composed_description_takes_the_laws_a_reader_chose import DESCRIPTION, LAWS, PLAN, READING

client = TestClient(app)

MODEL = "nvidia:poolside/laguna-xs-2.1"
# The circle moves from the golden section's upper left crossing (the parent's
# B1) to the thirds' lower right one, and the dots recede; B1 and B21 are left
# out, as the move asks. An answer names two or three laws.
MOVED = {"main_layer": 1, "main_law": "B3", "description_counts": [1],
         "laws": {"B3": {"targets": [{"layer": 1, "at": "point_lr"}]}, "B15": {"layers": [2]}},
         "reason": "円を三分割の右下の交点へ移し、点を遠くに置く。"}
SENTENCE = "廃駅のホームに時刻表だけが残る。"


@pytest.fixture
def author():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"auto-{suffix}")
    user = db.add_user(username=f"auto-{suffix}", email=f"auto-{suffix}@example.test", password="password-123",
                       permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    yield {"user": db.get_user(user["id"]), "headers": {"Authorization": f"Bearer {token}"}}
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


@pytest.fixture
def answers(monkeypatch):
    """Every model stage answered from a queue per action (the last answer repeats); the
    color stage is refused, so a run commits the document its laws printed. A saved
    child's files and thumbnail are not baked: nothing here reads them."""
    from inku_server.api_core import rendering, thumbnails

    monkeypatch.setattr(rendering, "_submit_history_artifact_save", lambda _item: None)
    monkeypatch.setattr(thumbnails, "submit_thumbnail_build", lambda _item: None)
    queues = {"generate_normalized_ddl": [PLAN], "read_composition": [READING], "choose_laws": [LAWS]}
    replies = {"generate_normalized_ddl": "normalized_ddl_generated", "read_composition": "composition_read",
               "choose_laws": "laws_chosen"}
    sent: list[str] = []

    class Provider:
        def __init__(self, _options, **_kwargs):
            pass

        def __call__(self, action):
            import json

            sent.append(action["tag"])
            if action["tag"] == "choose_colors":
                return {"tag": "provider_failed", "identity": action["identity"],
                        "failure": "provider_rejected", "elapsed_ms": "0"}
            queue = queues[action["tag"]]
            answer = queue.pop(0) if len(queue) > 1 else queue[0]
            return {"tag": replies[action["tag"]], "identity": action["identity"],
                    "response": json.dumps(answer, ensure_ascii=False), "elapsed_ms": "1"}

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", Provider)
    return {"queues": queues, "sent": sent}


def _laws_work(author) -> dict:
    painted = client.post("/api/paint", json={"description": DESCRIPTION, "stage1_model": MODEL,
                                              "save_history": True}, headers=author["headers"])
    assert painted.status_code == 200, painted.text
    return painted.json()


def _run(owner: str, *, moves: int = 3, kinds=("laws", "juxtaposition")) -> dict:
    return {"id": uuid.uuid4().hex, "owner_id": owner, "history_id": "start", "state": "running",
            "stop_reason": None, "turns": [], "current": None, "last_kept_history_id": None, "error": None,
            "settings": {"moves": moves, "kinds": list(kinds), "note": None, "model": MODEL, "language": "ja",
                         "wild": None},
            "created_at": 1}


@pytest.fixture
def runner(tmp_path):
    return AutonomousRunner(RunStore(f"sqlite:///{tmp_path / 'runs.db'}"), max_workers=1)


def _fake_moves(runner, monkeypatch, outcome: dict[str, str]) -> list[str]:
    """Moves that send nothing: each try ends as `outcome` says for its kind, and a
    kept child of a laws move is held by its DDL."""
    taken: list[str] = []

    def work(_owner, history_id):
        return {"id": history_id, "item": {"svg": "<svg/>"},
                "facts": {"description_locked": history_id.startswith("laws"), "ddl_work": False, "laws": []}}

    def move(kind):
        def take(run, *args):
            taken.append(kind)
            child = f"{kind}-{len(taken)}"
            result = outcome[kind]
            fields = {"share": 0.5 if result == "kept" else 0.1} if result in {"kept", "not_visible"} else {}
            return {"kind": kind, "outcome": result, "history_id": child if fields else None, **fields}
        return take

    monkeypatch.setattr(runner, "_work", work)
    monkeypatch.setattr(runner, "_laws", move("laws"))
    monkeypatch.setattr(runner, "_juxtaposition", move("juxtaposition"))
    monkeypatch.setattr(autonomous_refine.AutonomousRunner, "_show_last_kept", staticmethod(lambda run: None))
    return taken


@pytest.mark.parametrize(("outcome", "state", "reason", "turns"), [
    ({"laws": "kept", "juxtaposition": "kept"}, "done", "moves_done", 3),
    ({"laws": "not_visible", "juxtaposition": "not_visible"}, "done", "stalled", 2),
    ({"laws": "unavailable", "juxtaposition": "unavailable"}, "done", "nothing_available", 1),
])
def test_a_run_stops_where_the_core_says(runner, monkeypatch, outcome, state, reason, turns):
    """Failure: a run that draws past its moves, or never stops."""
    taken = _fake_moves(runner, monkeypatch, outcome)
    run = _run("owner")
    runner.store.save(run)
    runner._drive(run, {"id": "owner"}, runner._work("owner", "start"), threading.Event())
    ended = runner.get("owner", run["id"])
    assert (ended["state"], ended["stop_reason"], len(ended["turns"])) == (state, reason, turns)
    assert len(taken) <= 2 * run["settings"]["moves"]
    if reason == "moves_done":
        # Each turn kept one child, and the next turn started from it.
        assert [len([a for a in turn["attempts"] if a["outcome"] == "kept"]) for turn in ended["turns"]] == [1, 1, 1]
        assert ended["last_kept_history_id"] == ended["turns"][-1]["attempts"][-1]["history_id"]
        assert ended["turns"][0]["attempts"][0]["kind"] == "juxtaposition"


def test_a_laws_child_keeps_the_basis_the_next_laws_move_reads(author, answers):
    """Failure: the laws move's child keeps no basis, so the next laws move stops at
    `laws_without_basis`; or the child carries no move record."""
    owner = author["user"]["id"]
    parent_id = _laws_work(author)["history_id"]
    store = get_service().store
    assert laws_records_of(store, owner, parent_id)["laws_basis"]["main_law"] == "B1"
    answers["queues"]["choose_laws"][:] = [MOVED]
    runner = autonomous_refine.get_runner()
    run = _run(owner, kinds=("laws",))
    parent = runner._work(owner, parent_id)
    assert parent["facts"]["main_law"] == "B1" and set(parent["facts"]["laws"]) == {"B1", "B21"}
    step = {"turn": 1, "attempt": 1, "kind": "laws", "direction": {"exclude": ["B1", "B21"], "cards": "invite"}}
    taken = runner._laws(run, parent, step, threading.Event())
    assert taken["outcome"] in {"kept", "not_visible"}, taken
    assert taken["main_law"] == "B3"
    child = db.get_items(owner, [taken["history_id"]])[0]
    assert child["derivation_kind"] == "laws_change"
    assert child["history_visibility"] == "lineage_only"
    assert child["description_locked"] is True
    assert child["derivation_metadata"]["ai_move"]["kind"] == "laws"
    assert child["derivation_metadata"]["ai_move"]["visible"]["share"] == taken["share"]
    assert child["derivation_metadata"]["ai_move"]["laws"]["excluded"] == ["B1", "B21"]
    basis = laws_records_of(store, owner, taken["history_id"])["laws_basis"]
    assert basis["main_law"] == "B3"
    # The next laws move starts from the child's own basis.
    answers["queues"]["choose_laws"][:] = [LAWS]
    again = runner._laws(run, runner._work(owner, taken["history_id"]),
                         {**step, "turn": 2, "direction": {"exclude": ["B3"], "cards": "invite"}}, threading.Event())
    assert again["outcome"] in {"kept", "not_visible"}, again
    assert again["main_law"] == "B1"


def test_a_juxtaposition_leaves_out_what_its_lineage_added(author, answers, monkeypatch):
    """Failure: a run adds the same sentence twice down one lineage."""
    owner = author["user"]["id"]
    parent_id = _laws_work(author)["history_id"]
    asked: list[list[str]] = []

    def offer(_actor, work, exclude):
        asked.append(list(exclude))
        return {"svg": work["svg"], "description": DESCRIPTION, "lineage": [], "candidates": [], "written": DESCRIPTION}

    def choices(_offer, *, model, settings, language):
        return {"model": model, "candidates": 12, "choices": [
            {"sentence": f"{SENTENCE}{n}", "reason": "r", "history_ids": ["h"], "rank": n, "position": 0.5,
             "joined": f"{DESCRIPTION}{SENTENCE}{n}"} for n in range(1, 5)]}

    monkeypatch.setattr(render, "juxtaposition_offer", offer)
    monkeypatch.setattr(render, "juxtaposition_settings", lambda _actor, model: (model, {}))
    monkeypatch.setattr(render, "juxtaposition_choices", choices)
    runner = autonomous_refine.get_runner()
    run = _run(owner, kinds=("juxtaposition",))
    parent = runner._work(owner, parent_id)
    step = {"turn": 1, "attempt": 1, "kind": "juxtaposition", "rank": 1, "reuse": False, "exclude": ["前の一文。"]}
    taken = runner._juxtaposition(run, author["user"], parent, step, threading.Event(), {})
    assert asked == [["前の一文。"]]
    assert taken["outcome"] in {"kept", "not_visible"}, taken
    assert taken["sentence"] == f"{SENTENCE}1"
    child = db.get_items(owner, [taken["history_id"]])[0]
    assert child["derivation_kind"] == "description_edit"
    metadata = child["derivation_metadata"]
    assert metadata["juxtaposition"]["sentence"] == f"{SENTENCE}1"
    assert metadata["ai_move"]["kind"] == "juxtaposition"
    # The lineage of the child names the sentence, so the next juxtaposition leaves it out.
    _texts, added = render._juxtaposition_lineage(author["user"], child)
    assert f"{SENTENCE}1" in added


def test_a_stop_cancels_the_drawing_under_way(runner, monkeypatch):
    """Failure: a stopped run goes on drawing (and calling the model) to the end."""
    commands: list[dict] = []

    class Service:
        def get(self, _owner, _variation):
            return {"busy": True, "variation_id": "v", "execution_id": "e"}

        def command(self, _owner, _execution, payload):
            commands.append(payload)
            return {"busy": False}

    monkeypatch.setattr(pipeline_compat, "_service", lambda: Service())
    stop = threading.Event()
    stop.set()
    with pytest.raises(autonomous_refine._Stopped):
        runner._settle("owner", lambda: {"busy": True, "variation_id": "v", "execution_id": "e"}, stop)
    assert commands == [{"tag": "cancel"}]


def test_a_run_cut_off_by_a_restart_reads_as_interrupted(runner, monkeypatch):
    """Failure: a run the Server was taking stays "running" after a restart, and its
    last kept child never reaches the history."""
    promoted: list[tuple[str, str]] = []
    monkeypatch.setattr(autonomous_refine._db, "get_items", lambda owner, ids: [{"lineage_node_id": f"node-{ids[0]}"}])
    monkeypatch.setattr(autonomous_refine._db, "promote_lineage_node", lambda owner, node: promoted.append((owner, node)))
    run = {**_run("owner"), "last_kept_history_id": "child", "current": {"turn": 2, "attempt": 1, "kind": "laws"}}
    runner.store.save(run)
    runner.recover()
    cut = runner.get("owner", run["id"])
    assert (cut["state"], cut["stop_reason"], cut["current"]) == ("interrupted", "interrupted", None)
    assert promoted == [("owner", "node-child")]


def test_an_owner_takes_one_run_at_a_time(author, monkeypatch):
    """Failure: a second run of the same owner starts beside the first."""
    runner = autonomous_refine.get_runner()
    started = threading.Event()

    def work(_owner, history_id):
        return {"id": history_id, "item": {"svg": "<svg/>"},
                "facts": {"description_locked": False, "ddl_work": False, "laws": []}}

    def wait(run, actor, parent, step, stop, answers):
        started.set()
        stop.wait(10)
        raise autonomous_refine._Stopped

    monkeypatch.setattr(runner, "_work", work)
    monkeypatch.setattr(runner, "_juxtaposition", wait)
    body = {"history_id": "start", "moves": 2, "kinds": ["juxtaposition"], "model": MODEL}
    first = client.post("/api/refine/autonomous", json=body, headers=author["headers"])
    assert first.status_code == 200, first.text
    run_id = first.json()["id"]
    assert started.wait(10)
    second = client.post("/api/refine/autonomous", json=body, headers=author["headers"])
    assert second.status_code == 409
    assert second.json()["detail"]["run_id"] == run_id
    listed = client.get("/api/refine/autonomous", params={"history_id": "start"}, headers=author["headers"])
    assert [run["id"] for run in listed.json()["runs"]] == [run_id]
    stopped = client.post(f"/api/refine/autonomous/{run_id}/stop", headers=author["headers"])
    assert stopped.status_code == 200 and stopped.json()["stopping"] is True
    for _ in range(200):
        state = client.get(f"/api/refine/autonomous/{run_id}", headers=author["headers"]).json()["state"]
        if state != "running":
            break
        time.sleep(0.05)
    assert state == "stopped"
