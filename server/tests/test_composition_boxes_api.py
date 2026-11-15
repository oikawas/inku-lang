"""Linux native gate: a work's chunks come back with the record's thing, their lines and their boxes."""

import uuid

from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app

TITLED = ("画面比1:1。\n背景を青で埋める。\n\n「大海の」\n"
          "画面の横0.12、縦0.24から横0.89、縦0.32まで、白の水彩の細いゆるやかに波打つ線を1本引く。")
UNTITLED = ("画面比1:1。\n"
            "画面の横0.12、縦0.24から横0.89、縦0.32まで、白の水彩の細いゆるやかに波打つ線を1本引く。\n"
            "画面の横0.58、縦0.69から横0.72、縦0.58まで、紫の鉛筆の細い線を1本引く。")
RECORD = {"owners": [1, 2], "things": [
    {"thing": 1, "what": "海", "role": "main", "kind": "object", "quote": "大海の"},
    {"thing": 2, "what": "岩", "role": "sub", "kind": "object", "quote": ""},
]}


def _user(name: str) -> tuple[dict, dict]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"{name}-{suffix}")
    user = db.add_user(username=f"{name}-{suffix}", email=f"{name}-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    return user, group


def _work(user: dict, ddl: str, score_canvas: object = "square") -> dict:
    return db.add_item({
        "id": str(uuid.uuid4()), "user_id": user["id"], "at": 1, "input": "大海の磯もとどろに", "ddl": ddl,
        "score": {"canvas": score_canvas, "instructions": []}, "svg": "<svg/>", "catalog_id": "default",
        "instruction_lang_resolved": "ja", "render_canvas_aspect_id": "square",
    })


def test_composition_boxes_tie_chunks_to_things_lines_and_boxes(monkeypatch):
    owner, owner_group = _user("boxes")
    other, other_group = _user("boxes-other")
    token, other_token = db.create_session(owner["id"]), db.create_session(other["id"])
    client = TestClient(app)
    try:
        titled = _work(owner, TITLED)
        path = f"/api/history/{titled['id']}/composition-boxes"
        answer = client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert answer.status_code == 200, answer.text
        units = answer.json()["units"]
        assert answer.json()["free_lines"] is False
        places = units[0].pop("places")
        assert units == [{"title": "大海の", "thing": None, "lines": [3, 4], "sentences": 1,
                          "unplaced": 0, "box": [0.12, 0.24, 0.89, 0.32]}]
        # The line (0.77 wide) reaches the top third, stops short of the golden
        # left line, and the core names every place (step 3).
        assert len(places) == 9 and places["third_top"] == "ok" and places["golden_ul"] == "clamped"

        # Someone else's work cannot be read.
        assert client.get(path, headers={"Authorization": f"Bearer {other_token}"}).status_code == 404

        # Untitled instructions are titled from the work's own record; the lines are the saved DDL's.
        untitled = _work(owner, UNTITLED)
        read = db.get_items
        monkeypatch.setattr(db, "get_items", lambda user_id, ids: [
            {**item, "description_ddl": {"composition": {"things": RECORD["owners"],
                                                          "answer": {"things": RECORD["things"]}}}}
            if item["id"] == untitled["id"] else item for item in read(user_id, ids)])
        units = client.get(f"/api/history/{untitled['id']}/composition-boxes",
                           headers={"Authorization": f"Bearer {token}"}).json()["units"]
        assert [(unit["title"], unit["thing"], unit["lines"]) for unit in units] == [
            ("大海の", 1, [1]), ("岩", 2, [2])]

        # A work fitted onto another paper keeps its chunks and lines, but no box.
        fitted = _work(owner, TITLED, {"aspect": "square", "fit": "contain",
                                       "declared_ratio": {"width_units": 16, "height_units": 9}})
        units = client.get(f"/api/history/{fitted['id']}/composition-boxes",
                           headers={"Authorization": f"Bearer {token}"}).json()["units"]
        assert [(unit["lines"], unit["box"]) for unit in units] == [([3, 4], None)]
        assert set(units[0]["places"].values()) == {"fitted"}
    finally:
        for session in (token, other_token):
            db.delete_session(session)
        for user, group in ((owner, owner_group), (other, other_group)):
            db.delete_user(user["id"], cascade=True)
            db.delete_user_group(group["id"])


def test_a_child_without_a_record_is_titled_from_the_ancestors_record(monkeypatch):
    owner, group = _user("boxes-child")
    token = db.create_session(owner["id"])
    client = TestClient(app)
    try:
        parent, child = _work(owner, UNTITLED), _work(owner, UNTITLED)
        # The ancestor keeps the record; the child names it as its inherited one (step 1d).
        read = db.get_items
        monkeypatch.setattr(db, "get_items", lambda user_id, ids: [
            {**item, "composition_inherited": {"history_id": parent["id"]}} if item["id"] == child["id"] else item
            if item["id"] != parent["id"] else
            {**item, "description_ddl": {"composition": {"things": RECORD["owners"],
                                                          "answer": {"things": RECORD["things"]}}}}
            for item in read(user_id, ids)])
        units = client.get(f"/api/history/{child['id']}/composition-boxes",
                           headers={"Authorization": f"Bearer {token}"}).json()["units"]
        assert [(unit["title"], unit["thing"], unit["lines"]) for unit in units] == [
            ("大海の", 1, [1]), ("岩", 2, [2])]
    finally:
        db.delete_session(token)
        db.delete_user(owner["id"], cascade=True)
        db.delete_user_group(group["id"])


def test_a_chunk_moves_to_a_place_and_only_its_numbers_change():
    owner, group = _user("chunk-place")
    other, other_group = _user("chunk-place-other")
    token, other_token = db.create_session(owner["id"]), db.create_session(other["id"])
    client = TestClient(app)
    try:
        work = _work(owner, TITLED)
        path = f"/api/history/{work['id']}/chunk-place"
        headers = {"Authorization": f"Bearer {token}"}
        answer = client.post(path, json={"chunk": "大海の", "at": "third_top"}, headers=headers)
        assert answer.status_code == 200, answer.text
        body = answer.json()
        parent, child = TITLED.split("\n"), body["ddl"].split("\n")
        assert [index for index in range(len(parent)) if parent[index] != child[index]] == [4]
        assert child[4] == "画面の横0.12、縦0.293333から横0.89、縦0.373333まで、白の水彩の細いゆるやかに波打つ線を1本引く。"
        assert body["place"] == {"title": "大海の", "thing": None, "at": "third_top", "at_from": None,
                                 "from": [0.505, 0.28], "to": [0.505, 1 / 3], "clamped": False}
        # A reason comes back for a place the chunk cannot take, and for an unknown chunk.
        unknown = client.post(path, json={"chunk": "月", "at": "center"}, headers=headers)
        assert (unknown.status_code, unknown.json()["detail"]) == (422, "no_chunk")
        assert client.post(path, json={"chunk": "大海の", "at": "keep"}, headers=headers).status_code == 422
        assert client.post(path, json={"chunk": "大海の", "at": "center"},
                           headers={"Authorization": f"Bearer {other_token}"}).status_code == 404
        fitted = _work(owner, TITLED, {"aspect": "square", "fit": "contain",
                                       "declared_ratio": {"width_units": 16, "height_units": 9}})
        refused = client.post(f"/api/history/{fitted['id']}/chunk-place", json={"chunk": "大海の", "at": "center"},
                              headers=headers)
        assert (refused.status_code, refused.json()["detail"]) == (422, "fitted")
    finally:
        for session in (token, other_token):
            db.delete_session(session)
        for user, user_group in ((owner, group), (other, other_group)):
            db.delete_user(user["id"], cascade=True)
            db.delete_user_group(user_group["id"])
