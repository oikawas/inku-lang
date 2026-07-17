from __future__ import annotations

import uuid

from inku_server import db
from inku_server.identity import canonicalize_description, description_hash


def _user() -> dict:
    suffix = uuid.uuid4().hex[:10]
    groups = db.list_user_groups()
    return db.add_user(
        f"lineage-{suffix}",
        f"lineage-{suffix}@example.test",
        "lineage-test-password",
        "user",
        groups[0]["id"] if groups else None,
    )


def _item(user_id: str, text: str, at: int, **extra) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "input": text,
        "source_text": text,
        "ddl": "中心に黒い円を置く。",
        "score": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]},
        "svg": "<svg/>",
        "at": at,
        "render_seed": 1,
        "render_build_number": "516",
        "render_engine_id": "default",
        "render_engine_version": "3",
        "render_color_catalog_id": "default",
        **extra,
    }


def test_description_hash_uses_conservative_canonicalization():
    assert canonicalize_description("  cafe\u0301\r\n墨  ") == "café\n墨"
    assert description_hash(" cafe\u0301\r\n墨 ") == description_hash("café\n墨")
    assert description_hash("赤い 円") != description_hash("赤い円")
    assert description_hash("赤い円。") != description_hash("赤い円")


def test_lineage_records_explicit_derivation_and_tombstone():
    user = _user()
    try:
        root = db.add_item(_item(user["id"], "一滴の墨", 1000))
        child = db.add_item(_item(
            user["id"],
            "一滴の墨",
            1001,
            render_seed=2,
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="touch_variation",
            derivation_metadata={"render_seed_from": 1, "render_seed_to": 2},
        ))

        assert root["description_hash"] == child["description_hash"]
        assert root["render_hash"] != child["render_hash"]
        lineage = db.get_lineage(user["id"], child["lineage_node_id"])
        assert lineage is not None
        assert {node["id"] for node in lineage["nodes"]} == {
            root["lineage_node_id"],
            child["lineage_node_id"],
        }
        assert lineage["edges"][0]["derivation_kind"] == "touch_variation"
        assert next(node for node in lineage["nodes"] if node["id"] == root["lineage_node_id"])["child_count"] == 1
        assert next(node for node in lineage["nodes"] if node["id"] == child["lineage_node_id"])["child_count"] == 0

        sibling = db.add_item(_item(
            user["id"],
            "\u5225\u306e\u5b50",
            1002,
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="layout_variation",
        ))
        partial = db.get_lineage(user["id"], child["lineage_node_id"], descendant_depth=0)
        assert partial is not None
        assert sibling["lineage_node_id"] not in {node["id"] for node in partial["nodes"]}
        assert next(node for node in partial["nodes"] if node["id"] == root["lineage_node_id"])["child_count"] == 2

        assert db.delete_items(user["id"], [root["id"]]) == 1
        after_delete = db.get_lineage(user["id"], child["lineage_node_id"])
        assert after_delete is not None
        tombstone = next(node for node in after_delete["nodes"] if node["id"] == root["lineage_node_id"])
        assert tombstone["state"] == "tombstone"
        assert "description_hash" not in tombstone
        assert "render_hash" not in tombstone
        assert "history" not in tombstone
        assert after_delete["edges"][0]["metadata"] == {}
    finally:
        db.delete_all(user["id"])
        assert db.delete_user(user["id"])


def test_history_lineage_metadata_reports_full_generation_depth():
    user = _user()
    try:
        root = db.add_item(_item(user["id"], "根", 1500))
        child = db.add_item(_item(
            user["id"],
            "枝",
            1501,
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="description_edit",
        ))
        grandchild = db.add_item(_item(
            user["id"],
            "葉",
            1502,
            lineage_parent_node_id=child["lineage_node_id"],
            derivation_kind="description_edit",
        ))

        items, total = db.list_items(user["id"])
        assert total == 3
        by_id = {item["id"]: item for item in items}
        assert by_id[root["id"]]["lineage_generation"] == 1
        assert by_id[child["id"]]["lineage_generation"] == 2
        assert by_id[grandchild["id"]]["lineage_generation"] == 3
        assert {item["lineage_state"] for item in items} == {"active"}
    finally:
        db.delete_all(user["id"])
        assert db.delete_user(user["id"])


def test_lineage_only_history_is_hidden_and_can_be_promoted():
    user = _user()
    try:
        hidden = db.add_item(_item(
            user["id"],
            "中間候補",
            2000,
            history_visibility="lineage_only",
        ))
        items, total = db.list_items(user["id"])
        assert items == []
        assert total == 0

        promoted = db.promote_lineage_node(user["id"], hidden["lineage_node_id"])
        assert promoted is not None
        items, total = db.list_items(user["id"])
        assert total == 1
        assert items[0]["id"] == hidden["id"]
        assert items[0]["history_visibility"] == "normal"
    finally:
        db.delete_all(user["id"])
        assert db.delete_user(user["id"])


def test_lineage_rejects_cross_user_parent():
    first = _user()
    second = _user()
    try:
        root = db.add_item(_item(first["id"], "第一", 3000))
        try:
            db.add_item(_item(
                second["id"],
                "第二",
                3001,
                lineage_parent_node_id=root["lineage_node_id"],
                derivation_kind="description_edit",
            ))
        except ValueError as exc:
            assert "parent not found" in str(exc)
        else:
            raise AssertionError("cross-user lineage parent must be rejected")
    finally:
        for user in (first, second):
            db.delete_all(user["id"])
            assert db.delete_user(user["id"])
