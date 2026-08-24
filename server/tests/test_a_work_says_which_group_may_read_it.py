"""A work says which group may read it: the share bit and its destination.

Ledger I-191. Sharing already had two ways in -- the group scope a permission
group grants, and `history_acl`, one row per work per subject. Neither can say
"this bundle may be read": an ACL row's `history_id` is `NOT NULL` and points at
one work, so a condition over many works cannot be written as a row at all.

So the work carries the condition itself, in the shape a Unix file carries one:
an owner (`history.user_id`, already there), a group (`history.share_group_id`,
new) and the group's read bit (`history.for_share`, new). There is deliberately
no `other`: "anyone may read this" is publication and was not asked for.

The two columns are one mechanism and are tested as one. The bit alone is a
permission with no destination and the group alone is a destination nobody
opened, so every test below states both.

T-190  an old database gains the two columns and every existing row is closed
T-191  the listing reports the bit as a bool and the destination as str-or-None
T-192  the bit lets a peer in the named group read the work; before it, nothing
T-193  another organisation group is still shut out
T-194  a lineage node is reached by the bit, and its edge follows its child
T-195  a colophon is NOT reached by the bit -- the boundary of that decision
T-196  the bit widens reading only; writing is untouched
T-197  raising the bit without naming a group fills in the owner's own
T-198  only an admin may name a group that is not their own
T-199  dropping the bit closes the work and KEEPS the destination
T-200  `?for_share=true` selects the bundle, and both listing paths agree
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)


# --- T-190: the migration ----------------------------------------------------


def _create_pre_share_database(path: Path) -> None:
    """A history table as it stood before the two columns, with three rows."""
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE user_groups (
            id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL UNIQUE, at BIGINT NOT NULL
        );
        CREATE TABLE user_accounts (
            id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL UNIQUE,
            email VARCHAR NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            role VARCHAR NOT NULL, group_id VARCHAR, at BIGINT NOT NULL
        );
        CREATE TABLE history (
            id VARCHAR PRIMARY KEY, user_id VARCHAR, at BIGINT NOT NULL,
            input TEXT NOT NULL DEFAULT '', ddl TEXT, score TEXT NOT NULL DEFAULT '{}',
            svg TEXT NOT NULL DEFAULT '', output_path TEXT,
            elapsed_ms INTEGER NOT NULL DEFAULT 0,
            stage1_model VARCHAR, stage2_model VARCHAR, tokens_in INTEGER, tokens_out INTEGER,
            catalog_id VARCHAR, render_build_number VARCHAR, render_color_profile TEXT,
            render_engine_id VARCHAR, render_engine_version VARCHAR,
            render_color_catalog_id VARCHAR, render_color_catalog_name VARCHAR,
            render_color_catalog_sub VARCHAR, render_color_catalog TEXT, render_color_map TEXT,
            render_canvas_aspect VARCHAR, render_canvas_aspect_id VARCHAR,
            render_canvas_aspect_ratio FLOAT, instruction_lang_requested VARCHAR,
            instruction_lang_resolved VARCHAR, ui_lang VARCHAR, render_seed VARCHAR,
            composition_seed VARCHAR, interpretation_seed VARCHAR, render_hash VARCHAR,
            trashed INTEGER NOT NULL DEFAULT 0, starred INTEGER NOT NULL DEFAULT 0,
            for_revision INTEGER NOT NULL DEFAULT 0, note TEXT
        );
        INSERT INTO user_groups VALUES ('group-1', 'default', 1);
        INSERT INTO user_accounts (
            id, username, email, password_hash, role, group_id, at
        ) VALUES ('user-1', 'legacy', 'legacy@example.test', 'unused', 'user', 'group-1', 1);
        INSERT INTO history (id, user_id, at, input, ddl, score, svg, render_seed,
            render_build_number, render_engine_id, render_engine_version,
            render_color_catalog_id, starred, for_revision, note)
            VALUES ('history-1', 'user-1', 2, '松を描く', '松を置く。', '{"instructions": []}',
                '<svg/>', '7', '516', 'default', '3', 'default', 1, 0, 'a');
        INSERT INTO history (id, user_id, at, input, ddl, score, svg, render_seed,
            render_build_number, render_engine_id, render_engine_version,
            render_color_catalog_id, starred, for_revision, note)
            VALUES ('history-2', 'user-1', 3, '竹を描く', '竹を置く。', '{"instructions": []}',
                '<svg/>', '8', '516', 'default', '3', 'default', 0, 1, NULL);
        INSERT INTO history (id, user_id, at, input, ddl, score, svg, render_seed,
            render_build_number, render_engine_id, render_engine_version,
            render_color_catalog_id, starred, for_revision, note)
            VALUES ('history-3', 'user-1', 4, '梅を描く', '梅を置く。', '{"instructions": []}',
                '<svg/>', '9', '516', 'default', '3', 'default', 0, 0, 'c');
        """
    )
    connection.commit()
    connection.close()


def test_t190_an_old_database_gains_two_closed_columns(tmp_path: Path) -> None:
    """Opening a database that predates the columns adds them and closes every row.

    Measured in a child process against a real file, not against the suite's own
    database: the migration is what runs on the production copy, and the only way
    to know it is additive is to hold the rows before and after. The three counts
    are read AFTER, so a migration that dropped and recreated the table -- which
    would also produce two correct columns -- is caught by the row count and by
    the untouched values beside them.
    """
    db_path = tmp_path / "pre-share.db"
    _create_pre_share_database(db_path)
    before = {
        "count": 3,
        "marks": [("history-1", 1, 0, "a"), ("history-2", 0, 1, None), ("history-3", 0, 0, "c")],
    }
    code = """
import json
from sqlalchemy import inspect, text
from inku_server import db
db.init_db()
# Twice: the first accepted legacy start records the registry; the second start
# must validate that registry without replaying ALTER or other legacy repairs.
db.init_db()
with db.SessionLocal() as session:
    rows = session.execute(text(
        "SELECT id, starred, for_revision, note, for_share, share_group_id"
        " FROM history ORDER BY id"
    )).all()
    payload = {
        'columns': sorted(c['name'] for c in inspect(db.engine).get_columns('history')),
        'indexes': sorted(i['name'] for i in inspect(db.engine).get_indexes('history')),
        'rows': [list(row) for row in rows],
    }
print(json.dumps(payload, ensure_ascii=False))
"""
    env = os.environ.copy()
    env["INKU_DB_URL"] = f"sqlite:///{db_path}"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])

    assert "for_share" in payload["columns"], "the bit was not added"
    assert "share_group_id" in payload["columns"], "the destination was not added"
    assert "ix_history_for_share_group" in payload["indexes"]

    rows = payload["rows"]
    assert len(rows) == before["count"], "the migration changed how many works there are"
    for row, (item_id, starred, for_revision, note) in zip(rows, before["marks"]):
        assert row[0] == item_id
        # Nothing beside the two new columns moved.
        assert (row[1], row[2], row[3]) == (starred, for_revision, note), item_id
        # Closed, and pointing nowhere. Not "open to the owner's own group": a
        # work nobody opened has no readers, and a backfill that named a group
        # would hand every stored work to everyone the day the column landed.
        assert row[4] == 0, f"{item_id} arrived shared"
        assert row[5] is None, f"{item_id} arrived with a destination"


# --- the world every behavioural test below is measured in -------------------


def _org(prefix: str) -> str:
    return db.add_user_group(f"{prefix}-{uuid.uuid4().hex[:8]}")["id"]


def _member(prefix: str, groups: list[str], group_id: str | None) -> tuple[dict, dict[str, str], str]:
    suffix = uuid.uuid4().hex[:8]
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        permission_groups=groups,
        group_id=group_id,
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token


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


class World:
    """Two organisations, four accounts, and one work owned by alice.

    bob shares alice's organisation and is the reader every test measures
    through: he is a plain `users` member, so nothing but the bit can reach him.
    carol is in the other organisation, which is what makes "the bit points
    somewhere" measurable rather than "the bit is up".
    """

    def __init__(self) -> None:
        self.circle_a = _org("share-a")
        self.circle_b = _org("share-b")
        self.alice, self.alice_h, self.alice_t = _member("share-alice", ["users"], self.circle_a)
        self.bob, self.bob_h, self.bob_t = _member("share-bob", ["users"], self.circle_a)
        self.carol, self.carol_h, self.carol_t = _member("share-carol", ["users"], self.circle_b)
        self.root, self.root_h, self.root_t = _member("share-root", ["admins"], self.circle_a)
        self.work = db.add_item(_item(self.alice["id"], 1_000, "alice draws a pine"))

    def teardown(self) -> None:
        for user, token in (
            (self.alice, self.alice_t), (self.bob, self.bob_t),
            (self.carol, self.carol_t), (self.root, self.root_t),
        ):
            db.delete_all(user["id"])
            db.delete_session(token)
            db.delete_user(user["id"], cascade=True)
        db.delete_user_group(self.circle_a)
        db.delete_user_group(self.circle_b)


@pytest.fixture
def world():
    built = World()
    try:
        yield built
    finally:
        built.teardown()


def _listed_ids(headers: dict[str, str], **params) -> list[str]:
    response = client.get("/api/history", headers=headers, params={"limit": 100, **params})
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def _open_to(owner_id: str, item_id: str, group_id: str | None = None) -> dict | None:
    return db.set_item_for_share(owner_id, item_id, True, group_id)


# --- T-191: the two keys on the wire ----------------------------------------


def test_t191_the_listing_reports_a_bool_and_a_destination(world) -> None:
    """`for_share` is a bool and `share_group_id` is a str or None.

    Read from what `_row_to_dict` builds rather than from the HTTP body: the
    response model declares `for_share: bool`, so pydantic would coerce a stored
    `1` on the way out and the wire could not tell a bool from an integer. The
    stored value is where the mistake lives -- SQLite hands a TEXT flag back as
    `"0"`, and `bool("0")` is True.
    """
    items, _total = db.list_items(world.alice["id"], limit=100)
    item = next(entry for entry in items if entry["id"] == world.work["id"])
    assert item["for_share"] is False, f"closed work reported {item['for_share']!r}"
    assert item["share_group_id"] is None

    _open_to(world.alice["id"], world.work["id"])
    items, _total = db.list_items(world.alice["id"], limit=100)
    item = next(entry for entry in items if entry["id"] == world.work["id"])
    assert item["for_share"] is True, f"open work reported {item['for_share']!r}"
    assert item["share_group_id"] == world.circle_a
    assert isinstance(item["share_group_id"], str)


# --- T-192 / T-193: who the bit reaches -------------------------------------


def test_t192_a_peer_in_the_named_group_reads_the_work_only_once_it_is_open(world) -> None:
    """The same work and the same reader, measured before and after.

    Before matters as much as after: a listing that showed bob the work all
    along would satisfy "he can see it" without the bit existing at all.
    """
    assert world.work["id"] not in _listed_ids(world.bob_h)
    _open_to(world.alice["id"], world.work["id"])
    assert world.work["id"] in _listed_ids(world.bob_h)
    # And the whole work, not only its row in the listing.
    response = client.get(f"/api/history/{world.work['id']}/svg", headers=world.bob_h)
    assert response.status_code == 200, response.text


def test_t193_another_organisation_is_still_shut_out(world) -> None:
    """The destination is half the mechanism, so it is measured on its own.

    carol is a plain member of the OTHER organisation. If the bit alone decided,
    she would be reading a work opened to a group she is not in.
    """
    _open_to(world.alice["id"], world.work["id"])
    assert world.work["id"] in _listed_ids(world.bob_h), "the setup did not open the work"
    assert world.work["id"] not in _listed_ids(world.carol_h)
    response = client.get(f"/api/history/{world.work['id']}/svg", headers=world.carol_h)
    assert response.status_code == 404, response.text


# --- T-194 / T-195: how far the bit travels ---------------------------------


def test_t194_the_lineage_node_is_reached_and_its_edge_follows(world) -> None:
    """Ruling (2) A: the bit is placed where the ACL clause is, so every caller
    that hands over a work id gets it. The lineage node is such a caller, and the
    edge follows its child, so a derivation appears with the node it belongs to.
    """
    child = db.add_item(_item(
        world.alice["id"], 1_100, "alice revises the pine",
        lineage_parent_node_id=world.work["lineage_node_id"],
        derivation_kind="description_edit",
    ))
    assert child["lineage_node_id"]

    before = client.get(f"/api/history/{child['id']}/lineage", headers=world.bob_h)
    assert before.status_code == 404, "bob reached the lineage before anything was opened"

    _open_to(world.alice["id"], world.work["id"])
    _open_to(world.alice["id"], child["id"])
    after = client.get(f"/api/history/{child['id']}/lineage", headers=world.bob_h)
    assert after.status_code == 200, after.text
    graph = after.json()
    node_ids = {node["id"] for node in graph["nodes"]}
    assert {world.work["lineage_node_id"], child["lineage_node_id"]} <= node_ids
    # The edge is not opened by anything of its own -- it has no work id to carry
    # a bit -- so its arrival proves it came through its child.
    assert any(
        edge["child_node_id"] == child["lineage_node_id"]
        and edge["parent_node_id"] == world.work["lineage_node_id"]
        for edge in graph["edges"]
    ), graph["edges"]


def test_t195_a_colophon_is_not_reached_by_the_bit(world) -> None:
    """The boundary of ruling (2) A, and the only place it can be measured.

    `list_okugaki` is the one `_readable_by` caller that hands over no work id,
    so the bit cannot reach it. That is the ruling, not an oversight: a colophon
    is written ABOUT a work by whoever wrote it, and opening the work does not
    hand over someone else's writing about it.
    """
    _open_to(world.alice["id"], world.work["id"])
    assert world.work["id"] in _listed_ids(world.bob_h), "the setup did not open the work"

    node_id = world.work["lineage_node_id"]
    db.add_okugaki(world.alice["id"], {
        "target_node_id": node_id,
        "branch_snapshot": [node_id],
        "model": "test-model",
        "at": 1_500,
        "language": "ja",
        "body": "alice writes about her own pine.",
        "warnings": [],
        "fact_sheet": {},
    })
    assert len(db.list_okugaki(world.alice["id"], node_id)) == 1, "the setup wrote no colophon"
    assert db.list_okugaki(world.bob["id"], node_id) == [], (
        "the share bit reached a colophon; it is placed on the branch that takes "
        "a work id, and list_okugaki hands none over"
    )


# --- T-196: reading only -----------------------------------------------------


def test_t196_the_bit_does_not_widen_writing(world) -> None:
    """`_writable_by` is a separate, narrower test and the bit is not in it.

    Starring is the cheapest write there is. If it succeeds, everyone the bundle
    reaches can also edit, trash and revise everything in it.
    """
    _open_to(world.alice["id"], world.work["id"])
    assert world.work["id"] in _listed_ids(world.bob_h), "the setup did not open the work"
    response = client.patch(
        f"/api/history/{world.work['id']}/star", headers=world.bob_h, json={"starred": True}
    )
    assert response.status_code == 404, response.text
    with db.SessionLocal() as session:
        assert session.get(db.HistoryRow, world.work["id"]).starred == 0


# --- T-197 / T-198 / T-199: raising and dropping the bit ---------------------


def test_t197_raising_the_bit_without_a_destination_fills_in_the_owners_own(world) -> None:
    """The rule a new file follows: it takes the group of whoever made it."""
    response = client.patch(
        f"/api/history/{world.work['id']}/for-share",
        headers=world.alice_h,
        json={"for_share": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["for_share"] is True
    assert body["share_group_id"] == world.circle_a, "the destination was left empty"
    # And it is the destination that decides, so the peer is now in.
    assert world.work["id"] in _listed_ids(world.bob_h)


def test_t197_an_owner_with_no_group_cannot_open_a_work_at_all(world) -> None:
    """The other half of the same rule: no group to fall back on, no permission.

    A NULL destination with the bit up would be a permission with no reader, and
    a clause matching it would hand the work to every account that also has no
    group.
    """
    loner, loner_h, loner_t = _member("share-loner", ["users"], None)
    try:
        work = db.add_item(_item(loner["id"], 1_200, "a work by nobody's member"))
        response = client.patch(
            f"/api/history/{work['id']}/for-share", headers=loner_h, json={"for_share": True}
        )
        assert response.status_code == 400, response.text
        with db.SessionLocal() as session:
            row = session.get(db.HistoryRow, work["id"])
            assert row.for_share == 0 and row.share_group_id is None
    finally:
        db.delete_all(loner["id"])
        db.delete_session(loner_t)
        db.delete_user(loner["id"], cascade=True)


def test_t198_only_an_admin_may_name_a_group_that_is_not_their_own(world) -> None:
    """Named with the same tool `_writable_by` uses to widen for an admin.

    Both directions, because "nobody may name another group" would also pass on
    an implementation where naming a group never works at all.
    """
    refused = client.patch(
        f"/api/history/{world.work['id']}/for-share",
        headers=world.alice_h,
        json={"for_share": True, "share_group_id": world.circle_b},
    )
    assert refused.status_code == 403, refused.text
    with db.SessionLocal() as session:
        assert session.get(db.HistoryRow, world.work["id"]).for_share == 0

    allowed = client.patch(
        f"/api/history/{world.work['id']}/for-share",
        headers=world.root_h,
        json={"for_share": True, "share_group_id": world.circle_b},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["share_group_id"] == world.circle_b
    # And the destination is where the work went: carol reads it, bob does not.
    assert world.work["id"] in _listed_ids(world.carol_h)
    assert world.work["id"] not in _listed_ids(world.bob_h)


def test_t198_a_destination_that_does_not_exist_is_refused(world) -> None:
    response = client.patch(
        f"/api/history/{world.work['id']}/for-share",
        headers=world.root_h,
        json={"for_share": True, "share_group_id": "no-such-group"},
    )
    assert response.status_code == 400, response.text


def test_t199_dropping_the_bit_closes_the_work_and_keeps_the_destination(world) -> None:
    """`chmod g-r` does not forget the group, and neither does this.

    Keeping it is what makes raising the bit again mean the same thing it meant
    before; clearing it would silently re-aim the work at whatever group the
    owner happens to be in the next time.
    """
    opened = client.patch(
        f"/api/history/{world.work['id']}/for-share",
        headers=world.root_h,
        json={"for_share": True, "share_group_id": world.circle_b},
    )
    assert opened.status_code == 200, opened.text
    assert world.work["id"] in _listed_ids(world.carol_h)

    closed = client.patch(
        f"/api/history/{world.work['id']}/for-share",
        headers=world.alice_h,
        json={"for_share": False},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["for_share"] is False
    assert closed.json()["share_group_id"] == world.circle_b, "the destination was forgotten"
    assert world.work["id"] not in _listed_ids(world.carol_h)

    reopened = client.patch(
        f"/api/history/{world.work['id']}/for-share",
        headers=world.alice_h,
        json={"for_share": True},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["share_group_id"] == world.circle_b, (
        "raising the bit again re-aimed the work at the owner's own group"
    )
    assert world.work["id"] in _listed_ids(world.carol_h)


# --- T-200: the bundle can be asked for -------------------------------------


def test_t200_the_filter_selects_the_bundle_down_both_listing_paths(world) -> None:
    """`?for_share=true` returns the open works and only those, twice over.

    The listing has two implementations -- a SQLAlchemy query, and raw SQL over
    the full-text index that `q` switches on -- and they have to agree. The
    population deliberately mixes bob's own works with alice's, because the raw
    SQL path's share clause is only reachable through somebody ELSE's work: on
    one's own, the owner test alone already lets the row through and the clause
    has nothing to decide.
    """
    marker = f"kigo{uuid.uuid4().hex[:8]}"
    alice_open = db.add_item(_item(world.alice["id"], 2_000, f"{marker} alice opens a plum"))
    alice_shut = db.add_item(_item(world.alice["id"], 2_001, f"{marker} alice keeps a bamboo"))
    bob_open = db.add_item(_item(world.bob["id"], 2_002, f"{marker} bob opens a pine"))
    bob_shut = db.add_item(_item(world.bob["id"], 2_003, f"{marker} bob keeps a willow"))
    _open_to(world.alice["id"], alice_open["id"])
    _open_to(world.bob["id"], bob_open["id"])

    expected = {alice_open["id"], bob_open["id"]}
    orm_path = set(_listed_ids(world.bob_h, for_share="true"))
    search_path = set(_listed_ids(world.bob_h, for_share="true", q=marker))

    assert orm_path & {alice_shut["id"], bob_shut["id"]} == set(), "a closed work was in the bundle"
    assert expected <= orm_path, f"the bundle is missing {sorted(expected - orm_path)}"
    assert search_path == orm_path & set(_listed_ids(world.bob_h, q=marker)), (
        "the two listing paths disagree about the bundle: "
        f"query={sorted(orm_path)} search={sorted(search_path)}"
    )
    assert expected <= search_path, f"the search path is missing {sorted(expected - search_path)}"
