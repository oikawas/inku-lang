"""The AI refinement's chunk move (まとまりの手, 2026-10-27): the Server sends what the shared core asks for.

The core chooses, applies and checks the move (``chunk_moves.rs``; its own tests and the shared table cover them).
These guard what the Server adds around it, one failure each: a chunk child dropped by the gate or kept without its
move on its edge, a rewrite that loses its new title or carries the picture, a turn that keeps a child it could not
use, a next turn that does not see the moves its lineage took, and a chunk run that starts mixed with other moves
or without its direction.
"""

from __future__ import annotations

import json
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import autonomous_refine, db, pipeline_product
from inku_server.api import app
from inku_server.autonomous_refine import AutonomousRunner, RunStore
from inku_server.pipeline_compat import _settled
from inku_server.pipeline_runtime import get_service

client = TestClient(app)

MODEL = "nvidia:poolside/laguna-xs-2.1"
DIRECTION = "具象から抽象へ寄せる。"
TITLED = ("画面比1:1。\n背景を白で埋める。\n\n「灯台」\n"
          "画面の横0.6、縦0.4の位置に、幅0.1、高さ0.3の白の塗りの四角を1個置く。\n"
          "画面の横0.6、縦0.22の位置に、直径0.08の黄の塗りの円を1個置く。\n\n「波の筋」\n"
          "画面の横0.1、縦0.8から横0.9、縦0.8まで、灰の細い線を1本引く。")


@pytest.fixture
def author():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"chunk-{suffix}")
    user = db.add_user(username=f"chunk-{suffix}", email=f"chunk-{suffix}@example.test", password="password-123",
                       permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    yield {"user": db.get_user(user["id"]), "headers": {"Authorization": f"Bearer {token}"}}
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


@pytest.fixture
def answers(monkeypatch):
    """The chunk move's requests answered from a queue, each with what was sent. A saved child's files and
    thumbnail are not baked: nothing here reads them."""
    from inku_server.api_core import rendering, thumbnails

    monkeypatch.setattr(rendering, "_submit_history_artifact_save", lambda _item: None)
    monkeypatch.setattr(thumbnails, "submit_thumbnail_build", lambda _item: None)
    queue: list = []
    sent: list[dict] = []

    class Provider:
        def __init__(self, _options, **kwargs):
            self.images = kwargs.get("images")

        def __call__(self, action):
            sent.append({"tag": action["tag"], "images": len(self.images or []),
                         "message": json.loads(action["payload"]["prompt"]["message"])})
            answer = queue.pop(0)
            return {"tag": "normalized_ddl_generated", "identity": action["identity"],
                    "response": answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False),
                    "elapsed_ms": "1"}

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", Provider)
    return {"queue": queue, "sent": sent}


def _titled_work(owner: str) -> str:
    view = get_service().start(owner, "direct_ddl", TITLED, options={
        "stage1_model": MODEL, "stage2_model": MODEL, "instruction_lang": "ja"})
    return _settled(owner, view, perform=True)["result"]["history_id"]


def _chunk_run(owner: str, *, moves: int = 3) -> dict:
    return {"id": uuid.uuid4().hex, "owner_id": owner, "history_id": "start", "state": "running",
            "stop_reason": None, "turns": [], "current": None, "last_kept_history_id": None, "error": None,
            "settings": {"moves": moves, "kinds": ["chunks"], "note": DIRECTION, "model": MODEL, "language": "ja",
                         "wild": None},
            "created_at": 1}


STEP = {"turn": 1, "attempt": 1, "kind": "chunks", "note": DIRECTION}


def test_a_chunk_child_is_kept_with_its_move_whatever_the_gate(author, answers):
    """Failure: the gate drops a chunk move's child, or the child keeps no move on its edge."""
    owner = author["user"]["id"]
    runner = autonomous_refine.get_runner()
    parent = runner._work(owner, _titled_work(owner), chunks=True)
    assert parent["facts"]["chunks"] == 2
    answers["queue"][:] = [{"move": "place", "targets": [1], "at": "center", "reason": "灯台を中心に据える"}]
    taken = runner._chunks(_chunk_run(owner), parent, STEP, threading.Event())
    assert taken["outcome"] == "kept", taken
    assert (taken["move"], taken["targets"]) == ("place", ["灯台"])
    # The choose request carries the parent's picture.
    assert [(item["tag"], item["images"]) for item in answers["sent"]] == [("generate_normalized_ddl", 1)]
    assert answers["sent"][0]["message"]["units"][0]["title"] == "灯台"
    child = db.get_items(owner, [taken["history_id"]])[0]
    assert child["derivation_kind"] == "chunk_move"
    assert child["history_visibility"] == "lineage_only"
    assert child["description_locked"] is True
    assert "「灯台」\n画面の横0.5、縦0.535の位置に" in child["ddl"]
    ai_move = child["derivation_metadata"]["ai_move"]
    assert ai_move["kind"] == "chunks"
    assert ai_move["visible"]["gate"] is False
    assert ai_move["visible"]["share"] == taken["share"]
    assert ai_move["chunks"]["move"] == "place" and ai_move["chunks"]["params"] == {"at": "center"}
    assert ai_move["note"] == DIRECTION

    # The next turn starts from the child and is shown the move its lineage took.
    answers["queue"][:] = [{"move": "omit", "targets": [2], "reason": "波を消して灯台だけを残す"}]
    again = runner._chunks(_chunk_run(owner), runner._work(owner, taken["history_id"], chunks=True),
                           {**STEP, "turn": 2}, threading.Event())
    assert again["outcome"] == "kept", again
    shown = answers["sent"][-1]["message"]
    assert shown["history"] == [{"generation": 1, "move": "place", "targets": ["灯台"],
                                 "reason": "灯台を中心に据える", "applied": True}]
    assert shown["generation"] == 2


def test_a_rewrite_keeps_its_new_title_and_sends_no_picture(author, answers):
    """Failure: a simplify loses the title its writer gave, or its request carries the picture."""
    owner = author["user"]["id"]
    runner = autonomous_refine.get_runner()
    parent = runner._work(owner, _titled_work(owner), chunks=True)
    answers["queue"][:] = [
        {"move": "simplify", "targets": [1], "reason": "灯台を一つの面に"},
        {"title": "白い縦の面",
         "sentences": ["画面の横0.6、縦0.38の位置に、幅0.1、高さ0.34の白の塗りの四角を1個置く。"]},
    ]
    taken = runner._chunks(_chunk_run(owner), parent, STEP, threading.Event())
    assert taken["outcome"] == "kept", taken
    assert taken["title"] == "白い縦の面"
    assert [item["images"] for item in answers["sent"]] == [1, 0]
    assert answers["sent"][1]["message"]["limits"]["max_sentences"] == 1
    child = db.get_items(owner, [taken["history_id"]])[0]
    assert "\n「白い縦の面」\n画面の横0.6、縦0.38" in child["ddl"]
    assert child["derivation_metadata"]["ai_move"]["chunks"]["title"] == "白い縦の面"


def test_a_turn_that_cannot_use_its_answers_keeps_nothing(author, answers):
    """Failure: an answer that cannot be used is drawn, or asked for more than once again."""
    owner = author["user"]["id"]
    runner = autonomous_refine.get_runner()
    parent = runner._work(owner, _titled_work(owner), chunks=True)
    answers["queue"][:] = ["読めない答え", {}]
    taken = runner._chunks(_chunk_run(owner), parent, STEP, threading.Event())
    assert (taken["outcome"], taken["reason"]) == ("failed", "move が選択肢に無い: None")
    assert len(answers["sent"]) == 2
    assert answers["sent"][1]["message"]["asked_again"] == "答えが JSON のオブジェクトでない"
    assert not answers["queue"]


@pytest.fixture
def runner(tmp_path):
    return AutonomousRunner(RunStore(f"sqlite:///{tmp_path / 'runs.db'}"), max_workers=1)


def test_a_chunk_run_stops_after_two_turns_that_keep_nothing(runner, monkeypatch):
    """Failure: a chunk try that keeps nothing is tried again in its turn, or the run never stops."""
    taken: list[int] = []

    def work(_owner, history_id, *, chunks=False):
        return {"id": history_id, "item": {"svg": "<svg/>"},
                "facts": {"description_locked": False, "ddl_work": False, "laws": [], "chunks": 2}}

    def chunks(run, parent, step, stop):
        taken.append(step["turn"])
        return {"kind": "chunks", "outcome": "failed", "reason": "skipped"}

    monkeypatch.setattr(runner, "_work", work)
    monkeypatch.setattr(runner, "_chunks", chunks)
    monkeypatch.setattr(autonomous_refine.AutonomousRunner, "_show_last_kept", staticmethod(lambda run: None))
    run = _chunk_run("owner", moves=5)
    runner.store.save(run)
    runner._drive(run, {"id": "owner"}, runner._work("owner", "start", chunks=True), threading.Event())
    ended = runner.get("owner", run["id"])
    assert (ended["state"], ended["stop_reason"]) == ("done", "stalled")
    assert taken == [1, 2]


def test_a_chunk_run_runs_alone_and_needs_its_direction(author):
    """Failure: a chunk run starts mixed with other moves, or with no direction to move toward."""
    body = {"history_id": "missing", "kinds": ["chunks", "laws"], "note": DIRECTION}
    mixed = client.post("/api/refine/autonomous", json=body, headers=author["headers"])
    assert mixed.status_code == 422 and mixed.json()["detail"]["code"] == "autonomous_chunks_alone"
    blank = client.post("/api/refine/autonomous", json={**body, "kinds": ["chunks"], "note": "  "},
                        headers=author["headers"])
    assert blank.status_code == 422 and blank.json()["detail"]["code"] == "autonomous_note_required"
