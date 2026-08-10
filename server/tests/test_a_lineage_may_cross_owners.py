"""Stage G: a variation may be made from someone else's work, and the chain holds.

Until now a lineage lived inside one account. `add_item` looked for the parent
among the caller's own nodes and refused anything else, so two people could not
appear in one chain. The author's ruling was to let the derivation cross owners
rather than copy the parent into the deriver's account -- the copy is tidier to
administer, and it throws away the thing that makes the feature interesting.

That makes the lineage response the most dangerous payload in the codebase. It
carries whole works: description, score, SVG. And it is the one payload no
surface gate watches -- `/api/lineage/{node_id}` and `/api/history/{item_id}/lineage`
declare no `response_model` and return a bare dict, so a field leaking out of a
node moves nothing in `api-surface-baseline.json`. Behaviour is the only guard
there is, which is why T-19 checks for the ABSENCE of four keys by name rather
than trusting a shape.

Three rules decide what comes back:

* A node an edge reaches is always present, readable or not. Dropping the
  unreadable ones would cut the chain and orphan the child.
* An unreadable node returns `id`, `state`, `at`, `deleted_at` and
  `redacted: "not_permitted"` -- and NOT `child_count`, which a tombstone does
  return. How often a work has been derived from is information about that work.
* An edge is visible when its CHILD is, never its parent. Following the parent
  would tell B that C exists.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)

REDACTED_KEYS = ("description_hash", "render_hash", "history", "child_count")


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
        "history_visibility": "normal",
        **lineage,
    }


class World:
    """Alice owns a work. Bob and Carol each derive from it, separately."""

    def __init__(self) -> None:
        self.circle = _org("cross")
        self.alice, self.alice_h, self.alice_t = _member("cross-alice", ["users"], self.circle)
        self.bob, self.bob_h, self.bob_t = _member("cross-bob", ["users"], self.circle)
        self.carol, self.carol_h, self.carol_t = _member("cross-carol", ["users"], self.circle)
        self.stranger, self.stranger_h, self.stranger_t = _member("cross-stranger", ["users"], _org("cross-out"))

        self.parent = db.add_item(_item(self.alice["id"], 1_000, "alice draws a pine"))
        self.parent_node = self.parent["lineage_node_id"]

    def share_with(self, user: dict, permission: str = "read") -> None:
        db.grant_history_acl(self.alice["id"], self.parent["id"], "user", user["id"], permission)

    def derive(self, user: dict, at: int, label: str) -> dict:
        return db.add_item(_item(
            user["id"], at, label,
            lineage_parent_node_id=self.parent_node,
            derivation_kind="description_edit",
        ))

    def teardown(self) -> None:
        for user, token in (
            (self.bob, self.bob_t), (self.carol, self.carol_t),
            (self.stranger, self.stranger_t), (self.alice, self.alice_t),
        ):
            db.delete_all(user["id"])
            db.delete_session(token)
        for user in (self.bob, self.carol, self.stranger, self.alice):
            db.delete_user(user["id"], cascade=True)


@pytest.fixture
def world():
    built = World()
    try:
        yield built
    finally:
        built.teardown()


def _node(graph: dict, node_id: str) -> dict:
    match = [node for node in graph["nodes"] if node["id"] == node_id]
    assert match, f"node {node_id} is missing from the lineage entirely"
    return match[0]


# --- T-17: a readable work may be a parent -----------------------------------


def test_t17_a_shared_work_can_be_derived_from(world) -> None:
    world.share_with(world.bob)
    child = world.derive(world.bob, 2_000, "bob varies it")
    assert child["lineage_parent_node_id"] == world.parent_node


def test_t17_the_child_inherits_the_parents_root(world) -> None:
    """The lineage keeps one root across the owner boundary rather than starting
    a second one, which is what makes the group span two accounts."""
    world.share_with(world.bob)
    child = world.derive(world.bob, 2_000, "bob varies it")
    with db.SessionLocal() as session:
        parent_row = session.get(db.LineageNodeRow, world.parent_node)
        child_row = session.get(db.LineageNodeRow, child["lineage_node_id"])
    assert child_row.root_node_id == (parent_row.root_node_id or parent_row.id)


# --- T-18: an unreadable one may not (control) -------------------------------


def test_t18_an_unreadable_work_cannot_be_a_parent(world) -> None:
    with pytest.raises(ValueError, match="lineage parent not found"):
        world.derive(world.stranger, 2_000, "a derivation nobody asked for")


# --- T-19: the redacted parent gives nothing away -----------------------------


def test_t19_an_unreadable_parent_carries_none_of_the_work(world) -> None:
    """The heaviest check in the contract, and the only guard on this payload."""
    world.share_with(world.bob)
    child = world.derive(world.bob, 2_000, "bob varies it")
    db.revoke_history_acl(world.alice["id"], world.parent["id"], "user", world.bob["id"])

    graph = db.get_lineage(world.bob["id"], child["lineage_node_id"], descendant_depth=5)
    assert graph is not None
    parent = _node(graph, world.parent_node)
    assert parent["redacted"] == "not_permitted"
    for key in REDACTED_KEYS:
        assert key not in parent, f"the redacted parent still carries `{key}`"


def test_t19_the_ancestor_query_does_not_reveal_it_either(world) -> None:
    """The same node reached through the recursive CTE rather than the ORM.

    Two code paths answer "who is above this node": `_ancestor_edge_ids`, which
    is raw SQL, and the ORM filters that hydrate what it returns. Perturbing one
    while the other still holds looks like a pass.
    """
    world.share_with(world.bob)
    child = world.derive(world.bob, 2_000, "bob varies it")
    grandchild = db.add_item(_item(
        world.bob["id"], 3_000, "bob varies it again",
        lineage_parent_node_id=child["lineage_node_id"],
        derivation_kind="description_edit",
    ))
    db.revoke_history_acl(world.alice["id"], world.parent["id"], "user", world.bob["id"])

    branch = db.get_lineage_branch(world.bob["id"], grandchild["lineage_node_id"])
    assert branch is not None
    parent = _node(branch, world.parent_node)
    assert parent["redacted"] == "not_permitted"
    for key in REDACTED_KEYS:
        assert key not in parent, f"the redacted ancestor still carries `{key}`"
    # And the chain is intact: root, child, grandchild.
    assert [node["id"] for node in branch["nodes"]][0] == world.parent_node


# --- T-20: deleted and withheld are different labels -------------------------


def test_t20_a_deleted_parent_and_a_withheld_one_are_labelled_apart(world) -> None:
    world.share_with(world.bob)
    child = world.derive(world.bob, 2_000, "bob varies it")
    db.revoke_history_acl(world.alice["id"], world.parent["id"], "user", world.bob["id"])
    withheld = _node(db.get_lineage(world.bob["id"], child["lineage_node_id"]), world.parent_node)

    # Now really delete it and look again.
    db.trash_items(world.alice["id"], [world.parent["id"]])
    db.delete_items(world.alice["id"], [world.parent["id"]], require_trashed=True)
    deleted = _node(db.get_lineage(world.bob["id"], child["lineage_node_id"]), world.parent_node)

    assert withheld["redacted"] == "not_permitted"
    assert deleted["redacted"] == "deleted"
    assert withheld["redacted"] != deleted["redacted"]


def test_a_readable_node_is_not_redacted_at_all(world) -> None:
    """The positive side: without it, `redacted` could be a constant."""
    world.share_with(world.bob)
    child = world.derive(world.bob, 2_000, "bob varies it")
    graph = db.get_lineage(world.bob["id"], child["lineage_node_id"], descendant_depth=5)
    parent = _node(graph, world.parent_node)
    assert parent["redacted"] is None
    assert "history" in parent and parent["history"]["id"] == world.parent["id"]


# --- T-21: an edge follows its child, never its parent (control) --------------


def test_t21_one_deriver_cannot_see_that_another_exists(world) -> None:
    world.share_with(world.bob)
    world.share_with(world.carol)
    bob_child = world.derive(world.bob, 2_000, "bob varies it")
    carol_child = world.derive(world.carol, 3_000, "carol varies it")

    graph = db.get_lineage(world.bob["id"], bob_child["lineage_node_id"], descendant_depth=5)
    node_ids = {node["id"] for node in graph["nodes"]}
    assert carol_child["lineage_node_id"] not in node_ids, "bob can see carol's derivation"

    # The positive half, in the same graph so that "nobody sees anything" cannot
    # pass: bob's OWN edge up to the parent is there, and it is the only one.
    children_reached = {edge["child_node_id"] for edge in graph["edges"]}
    assert children_reached == {bob_child["lineage_node_id"]}


def test_t21_even_the_parents_owner_does_not_see_the_derivations(world) -> None:
    """Following the child cuts both ways, and this is the surprising direction.

    Alice owns the work bob and carol derived from, and she still sees neither
    derivation: their works are theirs, and she was not given them. The rule has
    no exception for "but it came from mine" -- an exception there would tell
    alice exactly what following-the-parent was rejected for telling bob, only
    with better standing to ask.

    Measured rather than predicted: the contract states the rule and the case it
    protects (bob must not learn carol exists) and does not say what the parent's
    owner sees. This is what the rule produces.
    """
    world.share_with(world.bob)
    world.share_with(world.carol)
    bob_child = world.derive(world.bob, 2_000, "bob varies it")
    carol_child = world.derive(world.carol, 3_000, "carol varies it")

    graph = db.get_lineage(world.alice["id"], world.parent_node, descendant_depth=5)
    node_ids = {node["id"] for node in graph["nodes"]}
    assert bob_child["lineage_node_id"] not in node_ids
    assert carol_child["lineage_node_id"] not in node_ids
    assert node_ids == {world.parent_node}
    # She does still see her own node, in full.
    assert _node(graph, world.parent_node)["redacted"] is None


# --- T-22: the group spans owners, and each sees their own part ---------------


def test_t22_two_people_open_the_same_group_and_count_differently(world) -> None:
    world.share_with(world.bob)
    world.derive(world.bob, 2_000, "bob varies it")

    _alice_items, alice_total = db.list_lineage_group_items(world.alice["id"], world.parent_node, limit=100)
    _bob_items, bob_total = db.list_lineage_group_items(world.bob["id"], world.parent_node, limit=100)
    # alice: her own work. bob: the shared parent plus his derivation.
    assert alice_total == 1
    assert bob_total == 2
    assert alice_total != bob_total


# --- T-23: reading a parent is not permission to change it -------------------


def test_t23_a_deriver_cannot_star_or_trash_the_parent(world) -> None:
    world.share_with(world.bob)
    world.derive(world.bob, 2_000, "bob varies it")

    star = client.patch(
        f"/api/history/{world.parent['id']}/star", headers=world.bob_h, json={"starred": True}
    )
    assert star.status_code == 404, star.text
    trash = client.post("/api/history/trash", headers=world.bob_h, json={"ids": [world.parent["id"]]})
    assert trash.status_code == 200 and trash.json()["count"] == 0
    assert db.get_items(world.alice["id"], [world.parent["id"]]), "the parent was trashed after all"


def test_a_deriver_cannot_promote_the_parents_node(world) -> None:
    world.share_with(world.bob)
    world.derive(world.bob, 2_000, "bob varies it")
    assert db.promote_lineage_node(world.bob["id"], world.parent_node) is None
