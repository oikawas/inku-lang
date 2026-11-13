"""The library's "by description": works grouped by their description key."""

from __future__ import annotations

import json
import pathlib
import uuid

from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.description_labels import description_group_key


client = TestClient(app)
CASES = json.loads(
    (pathlib.Path(__file__).parent / "data" / "description-group-cases.json").read_text(encoding="utf-8")
)
POEM = CASES["groups"][0]


def _item(user_id: str, at: int, text: str, **extra) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "at": at,
        "input": text,
        "source_text": text,
        "ddl": "背景を白で塗る。",
        "score": {"canvas": "square", "instructions": []},
        "svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
        "history_visibility": "normal",
        **extra,
    }


def _user(prefix: str) -> tuple[dict, dict[str, str], str, str]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"{prefix}-group-{suffix}")
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token, group["id"]


def _cleanup(user: dict, token: str, group_id: str) -> None:
    db._history.HistoryOwnedDataPurgeWriter(db.SessionLocal, db._owner_actor, db._delete_acl_for_histories).delete_all(user["id"])
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group_id)


def test_shared_cases_key_alike_through_the_server():
    for group in CASES["groups"]:
        keys = {description_group_key(text) for text in group["texts"]}
        assert len(keys) == 1, group["why"]
        if "key" in group:
            assert keys == {group["key"]}
    assert len({description_group_key(group["texts"][0]) for group in CASES["groups"]}) == len(CASES["groups"])
    assert all(description_group_key(text) == "" for text in CASES["empty"])
    assert description_group_key(None) == ""


def test_numbered_and_sourced_copies_of_one_description_form_one_group():
    user, headers, token, group_id = _user("description-groups")
    try:
        texts = POEM["texts"]
        poem_works = [db.add_item(_item(user["id"], 1000 + index, text)) for index, text in enumerate(texts[:4])]
        child = db.add_item(_item(
            user["id"], 5000, texts[4],
            lineage_parent_node_id=poem_works[0]["lineage_node_id"], derivation_kind="touch_change",
        ))
        other = db.add_item(_item(user["id"], 4000, "3羽の鳥が飛ぶ"))
        other_numbered = db.add_item(_item(user["id"], 3000, "#2 3羽の鳥が飛ぶ"))
        lone = db.add_item(_item(user["id"], 6000, "花の色はうつりにけりな"))
        db.add_item(_item(user["id"], 7000, "[出典だけ]"))
        db.add_item(_item(
            user["id"], 8000, texts[0], image_provenance="photo.png", image_ddl={"instructions": []},
        ))
        # A row saved before description_hash existed is keyed from its text.
        with db.SessionLocal() as session:
            session.query(db.HistoryRow).filter(db.HistoryRow.id == poem_works[1]["id"]).update(
                {db.HistoryRow.description_hash: None}
            )
            session.query(db.HistoryRow).filter(db.HistoryRow.id == other["id"]).update(
                {db.HistoryRow.render_hash: "rh3:" + "b" * 60 + "Cd34"}
            )
            session.commit()

        response = client.get("/api/history/description-groups", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert (data["total"], data["offset"], data["limit"]) == (3, 0, 12)
        assert [group["item_count"] for group in data["groups"]] == [1, 5, 2]
        lone_group, poem_group, bird_group = data["groups"]
        assert lone_group["representative"]["id"] == lone["id"]
        assert poem_group["key"] == POEM["key"]
        assert poem_group["representative"]["id"] == child["id"]
        assert poem_group["latest_at"] == 5000
        assert bird_group["representative"]["id"] == other["id"]
        assert set(poem_group) == {"key", "representative", "item_count", "starred_count", "for_revision_count", "latest_at"}

        # Two or more works, and the work in view keeps its group and is brought into view.
        several = client.get("/api/history/description-groups?min_items=2", headers=headers).json()
        assert [group["key"] for group in several["groups"]] == [poem_group["key"], bird_group["key"]]
        anchored = client.get(
            f"/api/history/description-groups?min_items=2&limit=1&anchor_id={lone['id']}", headers=headers
        ).json()
        assert (anchored["total"], anchored["offset"]) == (3, 0)
        assert anchored["groups"][0]["key"] == lone_group["key"]
        anchored_bird = client.get(
            f"/api/history/description-groups?limit=1&anchor_id={other_numbered['id']}", headers=headers
        ).json()
        assert anchored_bird["offset"] == 2 and anchored_bird["groups"][0]["key"] == bird_group["key"]
        included = client.get(
            f"/api/history/description-groups?min_items=2&include_id={lone['id']}", headers=headers
        ).json()
        assert included["total"] == 3

        # Marks and search narrow the works before they are grouped.
        db.set_item_starred(user["id"], poem_works[2]["id"], True)
        starred = client.get("/api/history/description-groups?starred=true", headers=headers).json()
        assert [(group["key"], group["item_count"]) for group in starred["groups"]] == [(poem_group["key"], 1)]
        counted = client.get("/api/history/description-groups", headers=headers).json()
        assert counted["groups"][1]["starred_count"] == 1
        searched = client.get("/api/history/description-groups?q=cd34", headers=headers).json()
        assert searched["total"] == 1 and searched["groups"][0]["representative"]["id"] == other["id"]

        thumbnails = client.get("/api/history/description-groups?include_svg=false", headers=headers).json()
        assert thumbnails["groups"][0]["representative"]["svg"] == ""
        assert thumbnails["groups"][0]["representative"]["svg_bytes"] == len("<svg xmlns='http://www.w3.org/2000/svg'/>")

        members = client.get(f"/api/history/description-groups/{poem_group['key']}/items", headers=headers)
        assert members.status_code == 200
        body = members.json()
        assert body["total"] == 5
        # Newest first; the picture's work with the same words is not a member.
        assert [item["id"] for item in body["items"]] == [child["id"]] + [work["id"] for work in reversed(poem_works)]
        paged = client.get(
            f"/api/history/description-groups/{poem_group['key']}/items?offset=1&limit=2&include_svg=false",
            headers=headers,
        ).json()
        assert [item["id"] for item in paged["items"]] == [poem_works[3]["id"], poem_works[2]["id"]]
        assert paged["items"][0]["svg"] == ""
        searched_members = client.get(
            f"/api/history/description-groups/{bird_group['key']}/items?q=CD34", headers=headers
        ).json()
        assert [item["id"] for item in searched_members["items"]] == [other["id"]]

        unknown = client.get(f"/api/history/description-groups/dg1:{'0' * 64}/items", headers=headers)
        assert unknown.status_code == 200 and unknown.json()["total"] == 0
        malformed = client.get("/api/history/description-groups/not-a-key/items", headers=headers)
        assert malformed.status_code == 422
    finally:
        _cleanup(user, token, group_id)


def test_description_groups_need_a_session_and_show_only_readable_works():
    assert client.get("/api/history/description-groups").status_code == 401
    owner, _owner_headers, owner_token, owner_group = _user("description-owner")
    viewer, viewer_headers, viewer_token, viewer_group = _user("description-viewer")
    try:
        db.add_item(_item(owner["id"], 1000, POEM["texts"][0]))
        listed = client.get("/api/history/description-groups", headers=viewer_headers).json()
        assert listed["total"] == 0
        members = client.get(f"/api/history/description-groups/{POEM['key']}/items", headers=viewer_headers).json()
        assert members["total"] == 0
    finally:
        _cleanup(owner, owner_token, owner_group)
        _cleanup(viewer, viewer_token, viewer_group)
