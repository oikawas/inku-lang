"""One work, one guest list: the explicit grants that sit beside the group scope.

Stage C. The permission group decides a default -- an admin reaches everything,
a leader their organisation -- and `history_acl` is the exception to it, named
per work and per subject.

The two mechanisms are kept apart deliberately (contract §1-1 ④). A new work has
no ACL rows at all; a leader who can see it sees it through the group scope, not
through a grant. Were they one mechanism, a change that broke either would be
absorbed by the other and no perturbation could tell them apart.

Two rights, `read` and `write`, with `delete` inside `write`. A `write` grant
satisfies a read -- someone trusted to change a work can obviously see it -- but
never the other way round, which is what T-7 measures.

Grants are made by the owner and by admins only. Not by everyone who can read:
a leader reads their organisation's works, and if reading were enough to grant,
they could pass any of them outside the organisation and the scope would stop
meaning anything.
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
    def __init__(self) -> None:
        self.circle_a = _org("acl-a")
        self.circle_b = _org("acl-b")
        self.alice, self.alice_h, self.alice_t = _member("acl-alice", ["users"], self.circle_a)
        self.bob, self.bob_h, self.bob_t = _member("acl-bob", ["users"], self.circle_b)
        self.leader_a, self.leader_a_h, self.leader_a_t = _member("acl-leader", ["leaders"], self.circle_a)
        self.work = db.add_item(_item(self.alice["id"], 1_000, "alice draws a pine"))

    def teardown(self) -> None:
        for user, token in (
            (self.alice, self.alice_t), (self.bob, self.bob_t), (self.leader_a, self.leader_a_t),
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


def _acl_rows(item_id: str) -> list[dict]:
    with db.SessionLocal() as session:
        return [
            db._acl_to_dict(row)
            for row in session.query(db.HistoryAclRow).filter(db.HistoryAclRow.history_id == item_id).all()
        ]


# --- T-6: an explicit read grant, and taking it away again -------------------


def test_t6_a_named_reader_sees_nothing_before_the_grant(world) -> None:
    assert world.work["id"] not in _listed_ids(world.bob_h)


def test_t6_a_named_reader_sees_the_work_after_the_grant(world) -> None:
    db.grant_history_acl(world.alice["id"], world.work["id"], "user", world.bob["id"], "read")
    assert world.work["id"] in _listed_ids(world.bob_h)
    response = client.get(f"/api/history/{world.work['id']}/svg", headers=world.bob_h)
    assert response.status_code == 200, response.text


def test_t6_revoking_the_grant_takes_the_work_away_again(world) -> None:
    db.grant_history_acl(world.alice["id"], world.work["id"], "user", world.bob["id"], "read")
    assert world.work["id"] in _listed_ids(world.bob_h)
    db.revoke_history_acl(world.alice["id"], world.work["id"], "user", world.bob["id"])
    assert _acl_rows(world.work["id"]) == [], "the revoked row is still in the table"
    assert world.work["id"] not in _listed_ids(world.bob_h)


# --- T-7: read is not write --------------------------------------------------


def test_t7_a_read_grant_does_not_allow_starring(world) -> None:
    db.grant_history_acl(world.alice["id"], world.work["id"], "user", world.bob["id"], "read")
    response = client.patch(
        f"/api/history/{world.work['id']}/star", headers=world.bob_h, json={"starred": True}
    )
    assert response.status_code == 404, response.text


def test_t7_a_read_grant_does_not_allow_trashing(world) -> None:
    db.grant_history_acl(world.alice["id"], world.work["id"], "user", world.bob["id"], "read")
    response = client.post("/api/history/trash", headers=world.bob_h, json={"ids": [world.work["id"]]})
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 0
    assert world.work["id"] in _listed_ids(world.alice_h)


def test_a_write_grant_does_allow_it(world) -> None:
    """The positive side of T-7: without it, "read cannot write" would also pass
    on an implementation where nobody can write anything."""
    db.grant_history_acl(world.alice["id"], world.work["id"], "user", world.bob["id"], "write")
    response = client.patch(
        f"/api/history/{world.work['id']}/star", headers=world.bob_h, json={"starred": True}
    )
    assert response.status_code == 200, response.text
    # And a write grant satisfies a read, so the work is visible too.
    assert world.work["id"] in _listed_ids(world.bob_h)


# --- T-9: an organisation group can be the subject ---------------------------


def test_t9_a_grant_to_an_organisation_reaches_its_members(world) -> None:
    assert world.work["id"] not in _listed_ids(world.bob_h)
    db.grant_history_acl(world.alice["id"], world.work["id"], "org_group", world.circle_b, "read")
    assert world.work["id"] in _listed_ids(world.bob_h)


# --- who may hand a work to someone else -------------------------------------


def test_a_leader_who_can_read_a_work_cannot_share_it(world) -> None:
    assert db.list_history_acl(world.leader_a["id"], world.work["id"]) is None
    assert db.grant_history_acl(
        world.leader_a["id"], world.work["id"], "user", world.bob["id"], "read"
    ) is None
    assert _acl_rows(world.work["id"]) == []


# --- T-12 / T-13: nothing outlives what it referred to ------------------------


def test_t12_deleting_a_user_leaves_no_acl_row_in_either_direction(world) -> None:
    other, _headers, other_token = _member("acl-doomed", ["users"], world.circle_b)
    other_work = db.add_item(_item(other["id"], 2_000, "a work that will be deleted"))
    # A grant naming the doomed account, on someone else's work...
    db.grant_history_acl(world.alice["id"], world.work["id"], "user", other["id"], "read")
    # ...and a grant on the doomed account's own work.
    db.grant_history_acl(other["id"], other_work["id"], "user", world.bob["id"], "read")
    assert _acl_rows(world.work["id"]) and _acl_rows(other_work["id"])

    db.delete_session(other_token)
    db.delete_user(other["id"], cascade=True)

    assert _acl_rows(other_work["id"]) == [], "grants on the deleted account's works survived"
    assert _acl_rows(world.work["id"]) == [], "grants naming the deleted account survived"


def test_t13_deleting_an_organisation_leaves_no_acl_row(world) -> None:
    doomed_group = _org("acl-doomed-group")
    db.grant_history_acl(world.alice["id"], world.work["id"], "org_group", doomed_group, "read")
    assert _acl_rows(world.work["id"])
    db.delete_user_group(doomed_group)
    assert _acl_rows(world.work["id"]) == []


def test_deleting_a_work_takes_its_guest_list_with_it(world) -> None:
    db.grant_history_acl(world.alice["id"], world.work["id"], "user", world.bob["id"], "read")
    assert _acl_rows(world.work["id"])
    db.trash_items(world.alice["id"], [world.work["id"]])
    db.delete_items(world.alice["id"], [world.work["id"]], require_trashed=True)
    assert _acl_rows(world.work["id"]) == []


# --- stage D: the same list over HTTP ----------------------------------------


def test_the_owner_reads_and_writes_the_guest_list_over_http(world) -> None:
    item_id = world.work["id"]
    empty = client.get(f"/api/history/{item_id}/acl", headers=world.alice_h)
    assert empty.status_code == 200, empty.text
    assert empty.json() == []

    put = client.put(
        f"/api/history/{item_id}/acl",
        headers=world.alice_h,
        json={"entries": [
            {"subject_type": "user", "subject_id": world.bob["id"], "permission": "read"}
        ]},
    )
    assert put.status_code == 200, put.text
    assert [(e["subject_id"], e["permission"]) for e in put.json()] == [(world.bob["id"], "read")]
    assert item_id in _listed_ids(world.bob_h)

    # An empty list is a revocation, not a no-op.
    cleared = client.put(f"/api/history/{item_id}/acl", headers=world.alice_h, json={"entries": []})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == []
    assert item_id not in _listed_ids(world.bob_h)


def test_a_stranger_gets_the_same_answer_as_for_a_work_that_does_not_exist(world) -> None:
    """404 rather than 403: a 403 confirms the work exists."""
    missing = client.get(f"/api/history/{uuid.uuid4()}/acl", headers=world.bob_h)
    unreadable = client.get(f"/api/history/{world.work['id']}/acl", headers=world.bob_h)
    assert missing.status_code == unreadable.status_code == 404
    assert missing.json() == unreadable.json()


def test_the_http_route_refuses_a_permission_it_does_not_know(world) -> None:
    response = client.put(
        f"/api/history/{world.work['id']}/acl",
        headers=world.alice_h,
        json={"entries": [
            {"subject_type": "user", "subject_id": world.bob["id"], "permission": "delete"}
        ]},
    )
    assert response.status_code == 422, response.text
    assert _acl_rows(world.work["id"]) == []


# --- the default is empty ----------------------------------------------------


def test_a_new_work_has_no_guest_list(world) -> None:
    """Contract §1-1 ④. The leader below can read the work, and it is the group
    scope that lets them -- there is no row here to credit it to."""
    assert db.list_history_acl(world.alice["id"], world.work["id"]) == []
    assert world.work["id"] in _listed_ids(world.leader_a_h)
