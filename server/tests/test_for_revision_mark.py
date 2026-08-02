"""The revision mark is a second mark, independent of the star.

`starred` says "I like this one"; `for_revision` says "I mean to work on this
one again". A work can carry either, both or neither, so the two columns must
not read each other -- and the filters must combine as AND, because a filter
that quietly widened to OR would show works the author did not ask for.
"""

from __future__ import annotations

import sqlite3
import uuid

from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)


def _item(user_id: str, at: int, label: str, **extra) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "at": at,
        "input": label,
        "source_text": label,
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


def test_mark_is_raised_and_dropped_through_the_api():
    user, headers, token, group_id = _user("for-revision-toggle")
    try:
        item = db.add_item(_item(user["id"], 1000, "work"))
        assert item["for_revision"] is False, "a new work starts unmarked"

        raised = client.patch(
            f"/api/history/{item['id']}/for-revision",
            json={"for_revision": True},
            headers=headers,
        )
        assert raised.status_code == 200
        assert raised.json()["for_revision"] is True

        dropped = client.patch(
            f"/api/history/{item['id']}/for-revision",
            json={"for_revision": False},
            headers=headers,
        )
        assert dropped.status_code == 200
        assert dropped.json()["for_revision"] is False

        missing = client.patch(
            f"/api/history/{uuid.uuid4()}/for-revision",
            json={"for_revision": True},
            headers=headers,
        )
        assert missing.status_code == 404
    finally:
        _cleanup(user, token, group_id)


def test_the_two_marks_do_not_move_each_other():
    user, headers, token, group_id = _user("for-revision-independent")
    try:
        item = db.add_item(_item(user["id"], 1000, "work"))

        starred = db.set_item_starred(user["id"], item["id"], True)
        assert starred["starred"] is True
        assert starred["for_revision"] is False, "starring raised the revision mark"

        marked = db.set_item_for_revision(user["id"], item["id"], True)
        assert marked["for_revision"] is True
        assert marked["starred"] is True, "marking dropped the star"

        unstarred = db.set_item_starred(user["id"], item["id"], False)
        assert unstarred["starred"] is False
        assert unstarred["for_revision"] is True, "unstarring dropped the revision mark"

        unmarked = db.set_item_for_revision(user["id"], item["id"], False)
        assert unmarked["for_revision"] is False
        assert unmarked["starred"] is False
    finally:
        _cleanup(user, token, group_id)


def test_the_filter_selects_only_marked_works():
    user, headers, token, group_id = _user("for-revision-filter")
    try:
        plain = db.add_item(_item(user["id"], 1000, "plain"))
        marked = db.add_item(_item(user["id"], 2000, "marked"))
        db.set_item_for_revision(user["id"], marked["id"], True)

        everything = client.get("/api/history?limit=100", headers=headers).json()
        assert everything["total"] == 2

        filtered = client.get("/api/history?limit=100&for_revision=true", headers=headers).json()
        assert filtered["total"] == 1
        assert [item["id"] for item in filtered["items"]] == [marked["id"]]
        assert plain["id"] not in {item["id"] for item in filtered["items"]}
    finally:
        _cleanup(user, token, group_id)


def test_the_two_filters_combine_as_and():
    user, headers, token, group_id = _user("for-revision-and")
    try:
        star_only = db.add_item(_item(user["id"], 1000, "star only"))
        mark_only = db.add_item(_item(user["id"], 2000, "mark only"))
        both = db.add_item(_item(user["id"], 3000, "both"))
        db.add_item(_item(user["id"], 4000, "neither"))
        db.set_item_starred(user["id"], star_only["id"], True)
        db.set_item_starred(user["id"], both["id"], True)
        db.set_item_for_revision(user["id"], mark_only["id"], True)
        db.set_item_for_revision(user["id"], both["id"], True)

        starred_only = client.get("/api/history?limit=100&starred=true", headers=headers).json()
        assert {item["id"] for item in starred_only["items"]} == {star_only["id"], both["id"]}

        marked_only = client.get(
            "/api/history?limit=100&for_revision=true", headers=headers
        ).json()
        assert {item["id"] for item in marked_only["items"]} == {mark_only["id"], both["id"]}

        combined = client.get(
            "/api/history?limit=100&starred=true&for_revision=true", headers=headers
        ).json()
        assert combined["total"] == 1, "the two filters widened to OR"
        assert [item["id"] for item in combined["items"]] == [both["id"]]
    finally:
        _cleanup(user, token, group_id)


def test_a_row_from_before_the_column_reads_as_unmarked(tmp_path):
    """A history row written before the column existed must survive the migration.

    Exercised against the real migration statement rather than a freshly created
    row: the column arrives by ALTER TABLE, and a row that predates it is only
    correct because that statement carries NOT NULL DEFAULT 0.
    """
    database = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE history (
            id VARCHAR PRIMARY KEY, user_id VARCHAR, at BIGINT NOT NULL,
            trashed INTEGER NOT NULL DEFAULT 0, starred INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO history (id, user_id, at, trashed, starred)
        VALUES ('old-row', 'user-1', 1000, 0, 1);
        """
    )
    connection.commit()
    before = [row[1] for row in connection.execute("PRAGMA table_info(history)")]
    assert "for_revision" not in before

    connection.execute(db._HISTORY_COLUMN_MIGRATIONS["for_revision"])
    connection.commit()

    after = [row[1] for row in connection.execute("PRAGMA table_info(history)")]
    assert "for_revision" in after
    value = connection.execute(
        "SELECT for_revision FROM history WHERE id = 'old-row'"
    ).fetchone()[0]
    assert value == 0, "a row from before the column did not come back unmarked"
    # The star it already carried is untouched.
    starred = connection.execute(
        "SELECT starred FROM history WHERE id = 'old-row'"
    ).fetchone()[0]
    assert starred == 1
    connection.close()


def test_lineage_groups_count_the_mark_beside_the_star():
    user, headers, token, group_id = _user("for-revision-lineage")
    try:
        root = db.add_item(_item(user["id"], 1000, "root"))
        child = db.add_item(_item(
            user["id"],
            2000,
            "child",
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="touch_change",
        ))
        db.set_item_starred(user["id"], root["id"], True)
        db.set_item_for_revision(user["id"], child["id"], True)

        groups = client.get("/api/history/lineage-groups", headers=headers).json()
        assert len(groups["groups"]) == 1
        group = groups["groups"][0]
        assert group["item_count"] == 2
        assert group["starred_count"] == 1
        assert group["for_revision_count"] == 1
    finally:
        _cleanup(user, token, group_id)
