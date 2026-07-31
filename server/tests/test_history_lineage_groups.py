from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)


def _item(user_id: str, at: int, label: str, **lineage) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "at": at,
        "input": label,
        "source_text": label,
        "ddl": "背景を白で塗る。",
        "score": {"canvas": "square", "instructions": []},
        "svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
        "history_visibility": lineage.pop("history_visibility", "normal"),
        **lineage,
    }


def _user(prefix: str) -> tuple[dict, dict[str, str], str, str]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"{prefix}-group-{suffix}")
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token, group["id"]


def _cleanup(user: dict, token: str, group_id: str) -> None:
    db.delete_all(user["id"])
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group_id)


def test_history_groups_page_by_lineage_and_exclude_hidden_items():
    user, headers, token, group_id = _user("lineage-groups")
    try:
        root = db.add_item(_item(user["id"], 1000, "root"))
        child = db.add_item(_item(
            user["id"],
            3000,
            "child",
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="touch_change",
        ))
        db.add_item(_item(
            user["id"],
            3500,
            "hidden",
            history_visibility="lineage_only",
            lineage_parent_node_id=child["lineage_node_id"],
            derivation_kind="layout_change",
        ))
        independent = db.add_item(_item(user["id"], 2000, "independent"))
        with db.SessionLocal() as session:
            session.query(db.HistoryRow).filter(db.HistoryRow.id == child["id"]).update(
                {db.HistoryRow.render_hash: "rh3:" + "b" * 60 + "Cd34"}
            )
            session.commit()

        response = client.get("/api/history/lineage-groups?limit=1", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["groups"]) == 1
        first = data["groups"][0]
        assert first["root_node_id"] == root["lineage_node_id"]
        assert first["item_count"] == 2
        assert first["representative"]["id"] == child["id"]
        assert first["latest_at"] == 3000

        second_page = client.get("/api/history/lineage-groups?offset=1&limit=1", headers=headers).json()
        assert second_page["groups"][0]["root_node_id"] == independent["lineage_node_id"]

        members = client.get(
            f"/api/history/lineage-groups/{root['lineage_node_id']}/items",
            headers=headers,
        )
        assert members.status_code == 200
        assert [item["id"] for item in members.json()["items"]] == [child["id"], root["id"]]
        assert all(item["lineage_root_node_id"] == root["lineage_node_id"] for item in members.json()["items"])

        searched_groups = client.get(
            "/api/history/lineage-groups?q=cd34",
            headers=headers,
        ).json()
        assert searched_groups["total"] == 1
        assert searched_groups["groups"][0]["representative"]["id"] == child["id"]

        searched_members = client.get(
            f"/api/history/lineage-groups/{root['lineage_node_id']}/items?q=CD34",
            headers=headers,
        ).json()
        assert searched_members["total"] == 1
        assert searched_members["items"][0]["id"] == child["id"]
    finally:
        _cleanup(user, token, group_id)


def test_history_group_filters_and_user_isolation():
    owner, owner_headers, owner_token, owner_group = _user("lineage-owner")
    other, other_headers, other_token, other_group = _user("lineage-other")
    try:
        root = db.add_item(_item(owner["id"], 1000, "winter root"))
        child = db.add_item(_item(
            owner["id"],
            2000,
            "summer child",
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="catalog_change",
        ))
        db.set_item_starred(owner["id"], child["id"], True)

        starred = client.get("/api/history/lineage-groups?starred=true", headers=owner_headers).json()
        assert starred["total"] == 1
        assert starred["groups"][0]["item_count"] == 1
        assert starred["groups"][0]["starred_count"] == 1

        searched = client.get("/api/history/lineage-groups?q=summer", headers=owner_headers).json()
        assert searched["total"] == 1
        assert searched["groups"][0]["representative"]["id"] == child["id"]

        db.trash_items(owner["id"], [child["id"]])
        active = client.get("/api/history/lineage-groups", headers=owner_headers).json()
        trashed = client.get("/api/history/lineage-groups?trashed=true", headers=owner_headers).json()
        assert active["groups"][0]["item_count"] == 1
        assert active["groups"][0]["representative"]["id"] == root["id"]
        assert trashed["groups"][0]["item_count"] == 1
        assert trashed["groups"][0]["representative"]["id"] == child["id"]

        assert client.get(
            f"/api/history/lineage-groups/{root['lineage_node_id']}/items",
            headers=other_headers,
        ).status_code == 404
    finally:
        _cleanup(owner, owner_token, owner_group)
        _cleanup(other, other_token, other_group)
