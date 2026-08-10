"""What a member may SEE is decided by the permission groups they hold.

Stage B of the ACL work. Until now every work was visible to exactly one account,
its owner, and the rule was written 55 times across `db.py`. Stage A pulled those
into `_readable_by` / `_writable_by` / `_owned_by`; this is where the predicates
stop agreeing with each other:

    admins   read everything (orphan rows included), write everything
    leaders  read their ORGANISATION group, write only their own
    users    read their own, write their own

The organisation group, not the permission group: circle_a's leader sees circle_a
and not circle_b. A leader carrying no group_id sees only their own works, which
is the defence `delete_user` and `update_user` already apply to the same actor.

Two shapes here differ from what the contract predicted, both measured rather
than assumed:

* Refusing a write returns **404, not 403**, and the bulk routes return a count
  of 0 rather than any error at all. `/api/history/{id}/star` answers 404 when
  `set_item_starred` finds no row, and `/api/history/trash` and
  `/api/history/permanent-delete` answer `{"ok": true, "count": n}` whatever n
  is. Changing them to 403 would be an API-surface change, which belongs to
  Stage D, and 404 is the safer of the two anyway: 403 confirms the work exists
  to someone who may not see it.
* There is no `GET /api/history/{item_id}`. The routes that resolve a single
  named work are `/svg` and `/neighbors`, so those carry the "a single work
  answers 200" checks.

The suite shares one database across the whole run, so a listing assertion here
tests for the presence or absence of a specific id, never a total.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)


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


def _item(user_id: str, at: int, label: str) -> dict:
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
    }


class World:
    """Two organisations, one work each, and one reader of every kind."""

    def __init__(self) -> None:
        self.circle_a = _org("circle-a")
        self.circle_b = _org("circle-b")
        self.alice, self.alice_h, self.alice_t = _member("alice", ["users"], self.circle_a)
        # Same organisation as alice, and still a plain user: proves the
        # organisation scope reaches leaders only.
        self.carol, self.carol_h, self.carol_t = _member("carol", ["users"], self.circle_a)
        self.leader_a, self.leader_a_h, self.leader_a_t = _member("leader-a", ["leaders"], self.circle_a)
        self.bob, self.bob_h, self.bob_t = _member("bob", ["users"], self.circle_b)
        self.admin, self.admin_h, self.admin_t = _member("admin", ["admins"], None)

        # A word that appears in no other test's work, so a search for it has
        # exactly one right answer across the shared database.
        self.word = f"zephyrine{uuid.uuid4().hex[:8]}"
        self.alice_work = db.add_item(_item(self.alice["id"], 1_000, f"alice draws {self.word}"))
        self.bob_work = db.add_item(_item(self.bob["id"], 2_000, "bob draws a hill"))

    def teardown(self) -> None:
        for user, token in (
            (self.alice, self.alice_t), (self.carol, self.carol_t), (self.leader_a, self.leader_a_t),
            (self.bob, self.bob_t), (self.admin, self.admin_t),
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


# --- T-2: admins read everything --------------------------------------------


def test_t2_an_admin_sees_another_members_work_in_the_listing(world) -> None:
    assert world.alice_work["id"] in _listed_ids(world.admin_h)


def test_t2_an_admin_can_load_another_members_svg(world) -> None:
    response = client.get(f"/api/history/{world.alice_work['id']}/svg", headers=world.admin_h)
    assert response.status_code == 200, response.text


def test_t2_an_admin_can_resolve_another_members_work_by_id(world) -> None:
    response = client.get(f"/api/history/{world.alice_work['id']}/neighbors", headers=world.admin_h)
    assert response.status_code == 200, response.text


# --- T-3: leaders read their own organisation -------------------------------


def test_t3_a_leader_sees_their_organisations_work_in_the_listing(world) -> None:
    assert world.alice_work["id"] in _listed_ids(world.leader_a_h)


def test_t3_a_leader_can_load_their_organisations_svg(world) -> None:
    response = client.get(f"/api/history/{world.alice_work['id']}/svg", headers=world.leader_a_h)
    assert response.status_code == 200, response.text


# --- T-4: and not another organisation's (control) ---------------------------


def test_t4_a_leader_does_not_see_another_organisations_work_in_the_listing(world) -> None:
    assert world.bob_work["id"] not in _listed_ids(world.leader_a_h)


def test_t4_a_leader_cannot_load_another_organisations_svg(world) -> None:
    response = client.get(f"/api/history/{world.bob_work['id']}/svg", headers=world.leader_a_h)
    assert response.status_code == 404, response.text


# --- T-5: plain users read only their own (control) --------------------------


def test_t5_a_user_does_not_see_a_fellow_members_work_in_the_listing(world) -> None:
    """carol shares alice's organisation. The scope still stops at ownership."""
    assert world.alice_work["id"] not in _listed_ids(world.carol_h)


def test_t5_a_user_cannot_load_a_fellow_members_svg(world) -> None:
    response = client.get(f"/api/history/{world.alice_work['id']}/svg", headers=world.carol_h)
    assert response.status_code == 404, response.text


def test_t5_a_user_cannot_resolve_a_fellow_members_work_by_id(world) -> None:
    response = client.get(f"/api/history/{world.alice_work['id']}/neighbors", headers=world.carol_h)
    assert response.status_code == 404, response.text


# --- T-8: reading an organisation's work is not permission to change it ------


def test_t8_a_leader_cannot_star_a_work_they_can_read(world) -> None:
    response = client.patch(
        f"/api/history/{world.alice_work['id']}/star",
        headers=world.leader_a_h,
        json={"starred": True},
    )
    assert response.status_code == 404, response.text


def test_t8_a_leader_cannot_trash_a_work_they_can_read(world) -> None:
    response = client.post(
        "/api/history/trash", headers=world.leader_a_h, json={"ids": [world.alice_work["id"]]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 0
    # And the work really is still out of the trash, not merely uncounted.
    assert world.alice_work["id"] in _listed_ids(world.alice_h)


def test_t8_a_leader_cannot_permanently_delete_a_work_they_can_read(world) -> None:
    db.trash_items(world.alice["id"], [world.alice_work["id"]])
    response = client.post(
        "/api/history/permanent-delete",
        headers=world.leader_a_h,
        json={"ids": [world.alice_work["id"]]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 0
    # Still in alice's trash, so it was not deleted -- only left uncounted.
    assert world.alice_work["id"] in _listed_ids(world.alice_h, trashed=True)


# --- T-16: lineage and colophon follow the same scope ------------------------


def test_t16_lineage_of_an_unreadable_work_is_not_found(world) -> None:
    response = client.get(f"/api/history/{world.alice_work['id']}/lineage", headers=world.carol_h)
    assert response.status_code == 404, response.text


def test_t16_colophon_of_an_unreadable_node_is_not_found(world) -> None:
    node_id = world.alice_work["lineage_node_id"]
    assert node_id, "the work under test has no lineage node"
    response = client.get(f"/api/lineage/{node_id}/colophon", headers=world.carol_h)
    assert response.status_code == 404, response.text


# --- the full-text search path, which raw SQL reaches separately -------------


def test_the_search_path_widens_with_the_scope(world) -> None:
    """The listing and the search are two different queries.

    `list_items` filters through `_readable_by`, but a search long enough to use
    FTS leaves the ORM entirely and runs raw SQL, where a SQLAlchemy expression
    cannot go. Miss that one and the failure is not a leak but a hole: the
    listing shows an organisation's works and searching for one of them returns
    nothing. The contract's own list of raw-SQL filters did not include it.
    """
    assert db._use_history_fts(world.word), "this search would not reach the FTS path"
    assert world.alice_work["id"] in _listed_ids(world.admin_h, q=world.word)
    assert world.alice_work["id"] in _listed_ids(world.leader_a_h, q=world.word)
    assert world.alice_work["id"] not in _listed_ids(world.carol_h, q=world.word)
