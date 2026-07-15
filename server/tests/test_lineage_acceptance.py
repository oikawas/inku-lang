from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.identity import description_hash


client = TestClient(app)


def _user(prefix: str = "lineage-accept") -> dict:
    suffix = uuid.uuid4().hex[:10]
    group = db.list_user_groups()[0]
    return db.add_user(
        f"{prefix}-{suffix}",
        f"{prefix}-{suffix}@example.test",
        "lineage-test-password",
        "user",
        group["id"],
    )


def _item(user_id: str, source: str, at: int, **extra) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "input": extra.pop("input", source),
        "source_text": source,
        "ddl": "中心に黒い円を置く。",
        "score": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]},
        "svg": "<svg/>",
        "at": at,
        "render_seed": extra.pop("render_seed", 1),
        "render_build_number": "516",
        "render_engine_id": "default",
        "render_engine_version": "3",
        "render_color_catalog_id": "default",
        **extra,
    }


def _cleanup(*users: dict) -> None:
    for user in users:
        db.delete_all(user["id"])
        assert db.delete_user(user["id"])


def test_dh1_normalization_boundaries_and_labels_do_not_change_identity():
    assert description_hash("e\u0301\r\n墨") == description_hash("  é\n墨  ")
    base = description_hash("赤い円\n青い線")
    assert base != description_hash("赤い 円\n青い線")
    assert base != description_hash("赤い円。\n青い線")
    assert base != description_hash("赤い円 青い線")
    assert base != description_hash("赤い円\n青い糸")
    assert description_hash("#1 赤い円") != description_hash("赤い円")

    user = _user()
    try:
        first = db.add_item(_item(user["id"], "同じ本文", 100, input="#1 同じ本文", display_label="#1"))
        second = db.add_item(_item(user["id"], "同じ本文", 101, input="#9 同じ本文", display_label="#9"))
        legacy = db.add_item(_item(user["id"], "#1 同じ本文", 102))
        assert first["description_hash"] == second["description_hash"]
        assert legacy["description_hash"] != first["description_hash"]
        assert first["render_hash"] == second["render_hash"]
        assert len({first["id"], second["id"]}) == 2
        assert len({first["lineage_node_id"], second["lineage_node_id"]}) == 2
    finally:
        _cleanup(user)


def test_all_derivation_kinds_siblings_and_history_provenance():
    user = _user()
    kinds = sorted(db.LINEAGE_DERIVATION_KINDS)
    try:
        root = db.add_item(_item(user["id"], "起点", 200))
        children = []
        for index, kind in enumerate(kinds, start=1):
            children.append(db.add_item(_item(
                user["id"],
                "起点",
                200 + index,
                lineage_parent_node_id=root["lineage_node_id"],
                derivation_kind=kind,
                derivation_metadata={"mode": kind, "seed": index},
            )))

        items, total = db.list_items(user["id"], limit=100)
        assert total == len(kinds) + 1
        by_id = {item["id"]: item for item in items}
        for child, kind in zip(children, kinds, strict=True):
            listed = by_id[child["id"]]
            assert listed["lineage_parent_node_id"] == root["lineage_node_id"]
            assert listed["derivation_kind"] == kind
            assert listed["derivation_metadata"]["mode"] == kind

        graph = db.get_lineage(user["id"], root["lineage_node_id"], descendant_depth=1)
        assert graph is not None
        assert len(graph["edges"]) == len(kinds)
        assert {edge["child_node_id"] for edge in graph["edges"]} == {
            child["lineage_node_id"] for child in children
        }
    finally:
        _cleanup(user)


def test_lineage_only_trash_restore_tombstone_and_limits():
    user = _user()
    try:
        root = db.add_item(_item(user["id"], "根", 300))
        hidden = db.add_item(_item(
            user["id"],
            "中間",
            301,
            history_visibility="lineage_only",
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="layout_variation",
        ))
        child = db.add_item(_item(
            user["id"],
            "子",
            302,
            lineage_parent_node_id=hidden["lineage_node_id"],
            derivation_kind="description_edit",
        ))
        items, total = db.list_items(user["id"], limit=100)
        assert total == 2
        assert hidden["id"] not in {item["id"] for item in items}

        assert db.trash_items(user["id"], [child["id"]]) == 1
        trashed, trashed_total = db.list_items(user["id"], trashed=True, limit=100)
        assert trashed_total == 1 and trashed[0]["id"] == child["id"]
        assert db.restore_items(user["id"], [child["id"]]) == 1

        assert db.delete_items(user["id"], [hidden["id"]]) == 1
        graph = db.get_lineage(user["id"], child["lineage_node_id"], descendant_depth=5)
        assert graph is not None
        tombstone = next(node for node in graph["nodes"] if node["id"] == hidden["lineage_node_id"])
        assert tombstone == {
            "id": hidden["lineage_node_id"],
            "state": "tombstone",
            "at": 301,
            "deleted_at": tombstone["deleted_at"],
            "child_count": 1,
        }
        assert len(graph["edges"]) == 2
        assert all(edge["metadata"] == {} for edge in graph["edges"])

        limited = db.get_lineage(user["id"], root["lineage_node_id"], descendant_depth=5, node_limit=2)
        assert limited is not None
        assert len(limited["nodes"]) <= 2
    finally:
        _cleanup(user)



def test_failed_history_insert_leaves_no_orphan_node_or_edge():
    user = _user()
    try:
        root = db.add_item(_item(user["id"], "起点", 350))
        with db.SessionLocal() as session:
            nodes_before = session.query(db.LineageNodeRow).filter_by(user_id=user["id"]).count()
            edges_before = session.query(db.LineageEdgeRow).filter_by(user_id=user["id"]).count()
        duplicate = _item(
            user["id"],
            "失敗する子",
            351,
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="touch_variation",
        )
        duplicate["id"] = root["id"]
        try:
            db.add_item(duplicate)
        except Exception:  # the database's integrity error type is backend-specific
            pass
        else:
            raise AssertionError("duplicate history id must fail")
        with db.SessionLocal() as session:
            assert session.query(db.LineageNodeRow).filter_by(user_id=user["id"]).count() == nodes_before
            assert session.query(db.LineageEdgeRow).filter_by(user_id=user["id"]).count() == edges_before
    finally:
        _cleanup(user)

def test_lineage_api_hides_other_users_and_tombstone_content():
    first = _user("lineage-owner")
    second = _user("lineage-viewer")
    first_token = db.create_session(first["id"])
    second_token = db.create_session(second["id"])
    try:
        root = db.add_item(_item(first["id"], "秘密の本文", 400))
        child = db.add_item(_item(
            first["id"],
            "公開されない子",
            401,
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="description_edit",
        ))
        other_headers = {"Authorization": f"Bearer {second_token}"}
        assert client.get(f"/api/lineage/{root['lineage_node_id']}", headers=other_headers).status_code == 404
        assert client.get(f"/api/history/{root['id']}/lineage", headers=other_headers).status_code == 404
        rejected = client.post(
            "/api/history",
            headers=other_headers,
            json={
                "input": "他人の親を参照",
                "source_text": "他人の親を参照",
                "ddl": "円を置く。",
                "score": {"instructions": []},
                "svg": "<svg/>",
                "at": 402,
                "lineage_parent_node_id": root["lineage_node_id"],
                "derivation_kind": "description_edit",
                "save_artifacts": False,
            },
        )
        assert rejected.status_code == 404

        assert db.delete_items(first["id"], [root["id"]]) == 1
        owner_headers = {"Authorization": f"Bearer {first_token}"}
        response = client.get(f"/api/lineage/{child['lineage_node_id']}", headers=owner_headers)
        assert response.status_code == 200
        tombstone = next(node for node in response.json()["nodes"] if node["id"] == root["lineage_node_id"])
        forbidden = {"history", "description_hash", "render_hash", "input", "ddl", "score", "svg"}
        assert forbidden.isdisjoint(tombstone)
    finally:
        db.delete_session(first_token)
        db.delete_session(second_token)
        _cleanup(first, second)
