"""`min_items` drops one-work lineages, in the page and in the count alike.

The thumbnail tab in lineage mode shows the works of a lineage side by side, so
a lineage holding a single work has nothing to show as a lineage. The filter has
to run in the query rather than on the returned page: throwing the one-work
groups away afterwards would leave short pages and a `total` that disagrees with
what the page holds.
"""

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
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token, group["id"]


def _cleanup(user: dict, token: str, group_id: str) -> None:
    db.delete_all(user["id"])
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group_id)


def test_min_items_drops_one_work_lineages_from_page_and_total():
    user, headers, token, group_id = _user("lineage-min-items")
    try:
        # A lineage of two works.
        pair_root = db.add_item(_item(user["id"], 1000, "pair root"))
        pair_child = db.add_item(_item(
            user["id"],
            2000,
            "pair child",
            lineage_parent_node_id=pair_root["lineage_node_id"],
            derivation_kind="touch_change",
        ))

        # A lineage of one work.
        alone = db.add_item(_item(user["id"], 3000, "alone"))

        # A row from before root nodes stored their own id: its root_node_id is
        # NULL and the query has to reach it through coalesce(). Reading only the
        # freshly created rows would miss a filter that works on new data and
        # drops the older shape.
        legacy_root = db.add_item(_item(user["id"], 4000, "legacy root"))
        legacy_child = db.add_item(_item(
            user["id"],
            5000,
            "legacy child",
            lineage_parent_node_id=legacy_root["lineage_node_id"],
            derivation_kind="touch_change",
        ))
        with db.SessionLocal() as session:
            session.query(db.LineageNodeRow).filter(
                db.LineageNodeRow.id == legacy_root["lineage_node_id"]
            ).update({db.LineageNodeRow.root_node_id: None})
            session.commit()

        unfiltered = client.get("/api/history/lineage-groups", headers=headers).json()
        assert unfiltered["total"] == 3, "the default still lists every lineage"
        assert {group["root_node_id"] for group in unfiltered["groups"]} == {
            pair_root["lineage_node_id"],
            alone["lineage_node_id"],
            legacy_root["lineage_node_id"],
        }

        filtered = client.get("/api/history/lineage-groups?min_items=2", headers=headers).json()
        roots = {group["root_node_id"] for group in filtered["groups"]}
        assert alone["lineage_node_id"] not in roots, "a one-work lineage reached the page"
        assert roots == {pair_root["lineage_node_id"], legacy_root["lineage_node_id"]}
        assert filtered["total"] == 2, "total still counts the one-work lineage"
        assert all(group["item_count"] >= 2 for group in filtered["groups"])

        # The members of both surviving lineages are still reachable.
        for root_id, expected in (
            (pair_root["lineage_node_id"], {pair_root["id"], pair_child["id"]}),
            (legacy_root["lineage_node_id"], {legacy_root["id"], legacy_child["id"]}),
        ):
            members = client.get(
                f"/api/history/lineage-groups/{root_id}/items", headers=headers
            ).json()
            assert {item["id"] for item in members["items"]} == expected
    finally:
        _cleanup(user, token, group_id)


def test_min_items_keeps_the_page_full_and_the_offset_honest():
    """Paging over the filtered set must not be thinned by the dropped groups."""
    user, headers, token, group_id = _user("lineage-min-page")
    try:
        roots = []
        for index in range(3):
            root = db.add_item(_item(user["id"], 1000 + index * 100, f"pair {index}"))
            db.add_item(_item(
                user["id"],
                1050 + index * 100,
                f"pair {index} child",
                lineage_parent_node_id=root["lineage_node_id"],
                derivation_kind="touch_change",
            ))
            roots.append(root["lineage_node_id"])
            # A one-work lineage between every pair, so an unfiltered page of two
            # would hold one of each.
            db.add_item(_item(user["id"], 1080 + index * 100, f"alone {index}"))

        first = client.get(
            "/api/history/lineage-groups?min_items=2&limit=2", headers=headers
        ).json()
        assert first["total"] == 3
        assert len(first["groups"]) == 2, "the page was thinned by the dropped groups"

        second = client.get(
            "/api/history/lineage-groups?min_items=2&limit=2&offset=2", headers=headers
        ).json()
        assert len(second["groups"]) == 1
        seen = [group["root_node_id"] for group in first["groups"] + second["groups"]]
        assert sorted(seen) == sorted(roots), "paging skipped or repeated a lineage"
    finally:
        _cleanup(user, token, group_id)


def test_min_items_combines_with_the_starred_filter():
    user, headers, token, group_id = _user("lineage-min-starred")
    try:
        root = db.add_item(_item(user["id"], 1000, "root"))
        child = db.add_item(_item(
            user["id"],
            2000,
            "child",
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="touch_change",
        ))
        db.set_item_starred(user["id"], child["id"], True)

        # Only one work of the lineage is starred, so under starred=true the
        # lineage holds a single work and min_items=2 must drop it.
        both = client.get(
            "/api/history/lineage-groups?starred=true&min_items=2", headers=headers
        ).json()
        assert both["total"] == 0
        assert both["groups"] == []

        starred_only = client.get(
            "/api/history/lineage-groups?starred=true", headers=headers
        ).json()
        assert starred_only["total"] == 1
        assert starred_only["groups"][0]["item_count"] == 1
    finally:
        _cleanup(user, token, group_id)
