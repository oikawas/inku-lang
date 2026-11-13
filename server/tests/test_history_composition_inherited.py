"""A child that keeps no composition record shows its ancestor's (step 1d, 2026-11-13).

The Server walks up the derivations that keep the parent's DDL and adds the
first record it meets as `composition_inherited`: the answer and the requested
form only, never the targets, the colors or each sentence's thing.
"""

from __future__ import annotations

import uuid

from inku_server import db
from tests.test_read_and_draw import _start, _wait, composed, host  # noqa: F401  (fixtures)


def _child(parent: dict, kind: str, ddl: str) -> dict:
    return db.add_item({
        "id": str(uuid.uuid4()), "user_id": "owner", "at": parent["at"] + 1, "input": parent["input"], "ddl": ddl,
        "score": {}, "svg": "<svg/>", "lineage_parent_node_id": parent["lineage_node_id"], "derivation_kind": kind,
    })


def _item(history_id: str) -> dict:
    return db.get_items("owner", [history_id])[0]


def test_a_child_that_keeps_the_ddl_shows_its_ancestors_composition(host, composed):
    client, service, _, _ = host
    view = _wait(service, _start(client, composition="on", composition_form="one_corner")["execution_id"])
    done = service.command("owner", view["execution_id"], {"tag": "perform"})
    parent = _item(done["result"]["history_id"])
    record = parent["description_ddl"]["composition"]
    assert "composition_inherited" not in parent

    touched = _child(parent, "tool_change", parent["ddl"] + "\n")
    expected = {"history_id": parent["id"], "at": parent["at"], "via": ["tool_change"],
                "answer": record["answer"], "requested_form": "one_corner"}
    assert _item(touched["id"])["composition_inherited"] == expected

    # Two generations: the colors of the touched child still show the first record.
    recolored = _child(_item(touched["id"]), "color_arrangement_change", parent["ddl"])
    assert _item(recolored["id"])["composition_inherited"] == {
        **expected, "via": ["color_arrangement_change", "tool_change"]}

    # A replay of the same DDL (spacing aside) is the parent drawn again; another DDL is a new drawing.
    same = _child(parent, "replay", "  " + parent["ddl"].replace("\n", "\n  "))
    assert _item(same["id"])["composition_inherited"] == {**expected, "via": ["replay"]}
    other = _child(parent, "replay", "背景を白で埋める。")
    assert "composition_inherited" not in _item(other["id"])

    # Another model reads the description again: no inherited record, and nothing past an edit.
    assert "composition_inherited" not in _item(_child(parent, "model_comparison", parent["ddl"])["id"])
    edited = _child(parent, "ddl_edit", parent["ddl"])
    assert "composition_inherited" not in _item(_child(_item(edited["id"]), "tool_change", parent["ddl"])["id"])

    # The listing, one page for all of them, gives the same field.
    items, _ = db.list_items("owner", limit=50, include_svg=False)
    listed = {item["id"]: item for item in items}
    assert listed[touched["id"]]["composition_inherited"] == expected
    assert "composition_inherited" not in listed[parent["id"]]
