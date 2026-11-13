"""Linux native gate: a work's chunks come back with the record's thing, their lines and their boxes."""

import uuid

from fastapi.testclient import TestClient

from inku_server import composition_record, db
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
        assert answer.json() == {"units": [{"title": "大海の", "thing": None, "lines": [3, 4], "sentences": 1,
                                            "unplaced": 0, "box": [0.12, 0.24, 0.89, 0.32]}]}

        # Someone else's work cannot be read.
        assert client.get(path, headers={"Authorization": f"Bearer {other_token}"}).status_code == 404

        # Untitled instructions are titled from the work's own record; the lines are the saved DDL's.
        monkeypatch.setattr(composition_record, "composition_of", lambda item: RECORD)
        untitled = _work(owner, UNTITLED)
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
    finally:
        for session in (token, other_token):
            db.delete_session(session)
        for user, group in ((owner, owner_group), (other, other_group)):
            db.delete_user(user["id"], cascade=True)
            db.delete_user_group(group["id"])
