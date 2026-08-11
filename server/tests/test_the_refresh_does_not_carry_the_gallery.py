"""Contract 3, the server half: asking whether the listing changed is cheap.

The strip refreshes every twelve seconds so a work saved in another window turns
up. It used to answer that by fetching the whole listing -- 23.5 MB with the
drawings, 163 KB without them, measured on the production database -- and in
nearly every round it rebuilt no part of the page because nothing had changed.
`GET /api/history/state` is the cheap question that replaces it.

What is measured here is the question itself: that it is small (T-4), that it
sees what the listing sees and no more (T-5), that it can tell two works apart
inside one millisecond (T-3), and that adding it moved nothing else on the API
surface (T-10). Whether the client actually asks it before fetching is a client
decision and is measured next door, in
`web/src/lib/the-refresh-does-not-carry-the-gallery.test.ts`.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app

from .test_the_acl_only_adds_to_the_api_surface import ADDED_OPERATIONS


client = TestClient(app)

SAME_MILLISECOND = 1_700_000_000_000


def _member(prefix: str) -> tuple[dict, dict[str, str], str]:
    suffix = uuid.uuid4().hex[:8]
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=None,
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token


def _item(user_id: str, at: int, label: str, item_id: str) -> dict:
    return {
        # The id is chosen rather than generated: the listing orders by
        # `at DESC, id ASC`, so with a shared `at` it is the id that decides
        # which work comes first, and a random one would decide it by coin toss.
        "id": item_id,
        "user_id": user_id,
        "at": at,
        # Distinct text per work on purpose. Two works that render identically
        # share a render hash, and the second one replaces the first row rather
        # than adding to it -- the count would not move and the test would be
        # measuring the wrong thing.
        "input": label,
        "source_text": label,
        "ddl": f"背景を白で塗る。{label}",
        "score": {"canvas": "square", "instructions": []},
        "svg": f"<svg xmlns='http://www.w3.org/2000/svg'><title>{label}</title></svg>",
        "history_visibility": "normal",
    }


class World:
    def __init__(self) -> None:
        self.owner, self.owner_h, self.owner_t = _member("state-owner")
        self.stranger, self.stranger_h, self.stranger_t = _member("state-stranger")

    def teardown(self) -> None:
        for user, token in ((self.owner, self.owner_t), (self.stranger, self.stranger_t)):
            db.delete_all(user["id"])
            db.delete_session(token)
            db.delete_user(user["id"], cascade=True)


@pytest.fixture
def world():
    built = World()
    try:
        yield built
    finally:
        built.teardown()


def _state(headers: dict[str, str]):
    response = client.get("/api/history/state", headers=headers)
    assert response.status_code == 200, response.text
    return response.json(), response


def _listed(headers: dict[str, str]) -> list[dict]:
    response = client.get(
        "/api/history", headers=headers, params={"limit": 100, "include_svg": False}
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --- T-3: two works inside one millisecond ----------------------------------


def test_t3_the_newest_work_is_the_one_the_listing_shows_first(world) -> None:
    db.add_item(_item(world.owner["id"], SAME_MILLISECOND, "pine", "ffff0000-" + "0" * 4 + "-4000-8000-" + "0" * 12))
    state, _ = _state(world.owner_h)
    assert state["newest_id"] == _listed(world.owner_h)[0]["id"]
    assert state["newest_at"] == SAME_MILLISECOND


def test_t3_a_second_save_in_the_same_millisecond_is_noticed(world) -> None:
    late = "ffff0000-" + "0" * 4 + "-4000-8000-" + "0" * 12
    early = "0000ffff-" + "0" * 4 + "-4000-8000-" + "0" * 12
    db.add_item(_item(world.owner["id"], SAME_MILLISECOND, "pine", late))
    before, _ = _state(world.owner_h)

    # Same `at` to the millisecond, and a lower id, so it becomes the listing's
    # first row. This is the case `newest_at` alone cannot see.
    db.add_item(_item(world.owner["id"], SAME_MILLISECOND, "bamboo", early))
    after, _ = _state(world.owner_h)

    assert after["newest_at"] == before["newest_at"], "the two saves share a millisecond"
    assert after["newest_id"] != before["newest_id"], (
        "the second save inside the same millisecond went unnoticed"
    )
    assert after["newest_id"] == _listed(world.owner_h)[0]["id"]


# --- T-4: the question is small ---------------------------------------------


def test_t4_the_answer_stays_under_a_kilobyte(world) -> None:
    for index in range(25):
        item = _item(
            world.owner["id"], SAME_MILLISECOND + index, f"work {index}", str(uuid.uuid4())
        )
        # A drawing the size of a real one. Measured on the development database
        # on 2026-08-11: 83 saved works, the average `svg` 4,219 bytes and the
        # largest 47,480. A fixture with a sixty-byte picture would keep this
        # under a kilobyte even if the route sent the whole drawing, and the
        # check would prove nothing about the size of anything.
        item["svg"] = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1618 1618'>"
            + "".join(
                f"<path d='M{i} {i}c40 {i} 80 {i % 97} 120 {i % 53}' stroke='#1a1a1a'/>"
                for i in range(60)
            )
            + "</svg>"
        )
        db.add_item(item)
    state, response = _state(world.owner_h)
    assert state["total"] >= 25
    # Bytes on the wire, not "it felt quick". The whole point of the route is
    # its size: the listing it replaces is 163 KB for twenty-one works.
    assert len(response.content) < 1024, (
        f"the state answer is {len(response.content)} bytes; it must stay under 1 KB"
    )


# --- T-5: it sees exactly what the listing sees ------------------------------


def test_t5_a_stranger_s_work_does_not_move_the_count(world) -> None:
    before, _ = _state(world.stranger_h)
    db.add_item(_item(world.owner["id"], SAME_MILLISECOND, "a work nobody shared", str(uuid.uuid4())))
    after, _ = _state(world.stranger_h)

    assert after["total"] == before["total"], (
        "somebody else's private work moved the stranger's count, so the "
        "stranger's client would fetch the whole listing for nothing"
    )
    assert after["newest_id"] == before["newest_id"]


def test_t5_the_count_agrees_with_the_listing_the_caller_can_see(world) -> None:
    db.add_item(_item(world.owner["id"], SAME_MILLISECOND, "owned", str(uuid.uuid4())))
    db.add_item(_item(world.stranger["id"], SAME_MILLISECOND + 1, "stranger's", str(uuid.uuid4())))
    for headers in (world.owner_h, world.stranger_h):
        state, _ = _state(headers)
        assert state["total"] == len(_listed(headers))


def test_t5_a_shared_work_reaches_the_count_the_same_way_the_listing_does(world) -> None:
    work = db.add_item(_item(world.owner["id"], SAME_MILLISECOND, "shared later", str(uuid.uuid4())))
    before, _ = _state(world.stranger_h)
    db.grant_history_acl(world.owner["id"], work["id"], "user", world.stranger["id"], "read")
    after, _ = _state(world.stranger_h)

    assert after["total"] == before["total"] + 1
    assert after["total"] == len(_listed(world.stranger_h))


def test_t5_a_trashed_work_leaves_the_count(world) -> None:
    work = db.add_item(_item(world.owner["id"], SAME_MILLISECOND, "thrown away", str(uuid.uuid4())))
    before, _ = _state(world.owner_h)
    db.trash_items(world.owner["id"], [work["id"]])
    after, _ = _state(world.owner_h)

    assert after["total"] == before["total"] - 1
    assert after["total"] == len(_listed(world.owner_h))


# --- T-10: the route is declared, not merely present -------------------------


def test_t10_the_new_route_is_named_in_what_this_branch_may_add() -> None:
    """A route the surface guard has not been told about is not allowed in.

    Naming it here is what separates "contract 3 added its route" from "some
    route appeared". The guard next door checks that nothing else moved with it;
    this checks that the name is on the list at all, which is the thing a
    forgetful implementation drops.
    """
    assert "GET /api/history/state" in ADDED_OPERATIONS
