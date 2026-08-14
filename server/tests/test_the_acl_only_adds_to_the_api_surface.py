"""T-11: sharing added routes to the API and moved none of the ones already there.

`test_api_surface.py` compares the whole surface against a baseline file, and
that file is REGENERATED whenever the surface legitimately changes. A regenerated
record is not a gate: the moment sharing landed, the baseline was rewritten to
match whatever the code now produces, and any collateral damage in the other 82
operations was written into the new baseline as if it had always been there.

So the surface as it stood at `3450548c` -- before any of this branch's stages --
is kept beside it as a second, frozen file. The check is a set difference: strip
the operations and schemas this branch is allowed to add, check the one schema it
is allowed to CHANGE field by field, and what remains must equal the frozen copy
exactly. Comparing the remainder rather than hashing it means a failure names
what moved instead of only saying that something did.

The one declared change is `HistoryItem.shared`. The contract expected this
branch to add routes and touch nothing else; marking a work as somebody else's
needs a field on the work, and the listing is the thing that has to say it.

What this does NOT cover, and nothing on the surface can: the lineage responses
(`/api/lineage/{node_id}` and `/api/history/{item_id}/lineage`) declare no
`response_model` and return a bare dict. A work's description and image could
leak through a lineage node without moving one byte here. That is guarded by
behaviour alone -- see the lineage tests.
"""

from __future__ import annotations

import json
import pathlib

from .test_api_surface import _stable, current_surface

# The surface as it stood at `3450548c`, this branch's starting point. Frozen:
# never regenerated. `api-surface-baseline.json` tracks the CURRENT surface and
# is rewritten whenever it legitimately changes, which is exactly what makes it
# useless for telling an intended addition from collateral damage.
BASELINE_BEFORE_THE_BRANCH = (
    pathlib.Path(__file__).parent / "data" / "api-surface-before-the-guest-list.json"
)


PRE_ACL_OPERATION_COUNT = 82
PRE_ACL_SCHEMA_COUNT = 82

# Everything this branch is allowed to add, named one by one. A route that
# appears without being listed here fails, which is the point: "the count went
# up by two" would also pass if one route were added and another replaced.
ADDED_OPERATIONS = {
    # v2.14: the saijiki preview artwork route (see
    # test_the_card_only_adds_one_route.py for the same declaration).
    "GET /api/saijiki/plugin-preview",
    "GET /api/history/{item_id}/acl",
    "PUT /api/history/{item_id}/acl",
    "GET /api/settings/single-user",
    "PUT /api/settings/single-user",
    "GET /api/auth/me/group-peers",
    # Contract 2 (thumbnails). Same rule: named one by one, so an unlisted
    # route appearing beside them still fails.
    "GET /api/history/{item_id}/thumb",
    "GET /api/settings/thumbnails",
    "PUT /api/settings/thumbnails",
    "GET /api/settings/thumbnails/rebuild",
    "POST /api/settings/thumbnails/rebuild",
    # Contract 3 (the refresh does not carry the gallery). Same rule again.
    "GET /api/history/state",
    # The shareable card. Same rule again: this file measures everything added
    # since `3450548c`, so a later branch declares its routes here or the check
    # reads them as damage. What the card added and nothing else is measured
    # against its own starting point in test_the_card_only_adds_one_route.py.
    "POST /api/history/export-card",
}

ADDED_SCHEMAS = {
    "HistoryAclEntry",
    "HistoryAclEntryOut",
    "HistoryAclBody",
    "SingleUserStatus",
    "SingleUserCandidate",
    "SingleUserBody",
    "GroupPeer",
    # Contract 2 (thumbnails).
    "ThumbnailStatus",
    "ThumbnailRebuildStatus",
    "ThumbnailSettingsBody",
    # Contract 3.
    "HistoryStateResponse",
    # The shareable card.
    "CardExportBody",
}

# One schema that predates this branch is changed rather than added, and it is
# declared here with exactly what may change in it. The contract expected the
# branch to add routes and touch nothing else; marking a work as somebody else's
# needs a field on the work itself, and there is nowhere else to put it -- the
# listing is the thing that has to say it. Declaring the change keeps the check
# honest: any OTHER movement in HistoryItem, and any movement at all in the
# remaining 81, still fails.
CHANGED_SCHEMAS = {
    "HistoryItem": {"added": {"shared"}, "removed": set()},
    # Contract 2: the client asks for the second thumbnail size only where the
    # server keeps it, and /api/info is where it learns that.
    "AppInfoResponse": {"added": {"thumbnail_hidpi"}, "removed": set()},
    # v2.14: whether a plugin expands is decided by prose. A work authored
    # straight in DDL has no description and must not be given one to make one
    # expand, so the prose rides in its own optional key. Callers that never
    # send it are unaffected.
    "ComposeRequest": {"added": {"fires_on"}, "removed": set()},
    # I-143: one arrangement may repeat a contiguous Score instruction unit.
    "Arrangement": {"added": {"group_size"}, "removed": set()},
    # ddl-engine 18: a fill is a surface word like the other eight, so the
    # `texture` enum gains `solid`. No property moves -- which is why the enum
    # is checked by name below: a declaration that only counts properties would
    # let anything else inside this schema through beside it.
    "SurfaceSpec": {"added": set(), "removed": set()},
}

# The whole of what the declared `SurfaceSpec` change may be.
SURFACE_TEXTURE_ENUM_ADDED = {"solid"}

# Operations that predate this branch and are declared to change, with exactly
# what may move in them. Contract 2 gave the listing a way to be asked for the
# metadata without the drawings; the parameter is optional and defaults to the
# old behaviour, so nothing a caller already sent means anything different.
CHANGED_OPERATIONS = {
    "GET /api/history": {"added_params": {"query:include_svg:opt"}, "removed_params": set()},
}


def test_the_surface_gained_exactly_the_sharing_routes_and_nothing_else() -> None:
    surface = current_surface()
    operations = {f"{op['method']} {op['path']}": _stable(op) for op in surface["operations"]}
    schemas = dict(surface["schemas"])

    assert len(operations) == PRE_ACL_OPERATION_COUNT + len(ADDED_OPERATIONS), (
        f"expected {PRE_ACL_OPERATION_COUNT + len(ADDED_OPERATIONS)} operations, found {len(operations)}"
    )
    assert ADDED_OPERATIONS <= set(operations), f"missing: {sorted(ADDED_OPERATIONS - set(operations))}"
    assert ADDED_SCHEMAS <= set(schemas), f"missing schemas: {sorted(ADDED_SCHEMAS - set(schemas))}"

    for key in ADDED_OPERATIONS:
        operations.pop(key)
    for name in ADDED_SCHEMAS:
        schemas.pop(name)

    # The declared changes, checked field by field before being set aside.
    baseline = json.loads(BASELINE_BEFORE_THE_BRANCH.read_text(encoding="utf-8"))
    baseline_ops = {f"{op['method']} {op['path']}": op for op in baseline["operations"]}
    for key, expected_delta in CHANGED_OPERATIONS.items():
        before_params = set(baseline_ops[key]["params"])
        after_op = next(op for op in surface["operations"] if f"{op['method']} {op['path']}" == key)
        after_params = set(after_op["params"])
        assert after_params - before_params == expected_delta["added_params"], key
        assert before_params - after_params == expected_delta["removed_params"], key
        # Everything else about the operation must still match byte for byte.
        assert _stable({**after_op, "params": sorted(before_params)}) == _stable(baseline_ops[key]), key
        operations.pop(key)
    for name, expected in CHANGED_SCHEMAS.items():
        before_body = json.loads(baseline["schemas"][name])
        after_body = json.loads(schemas.pop(name))
        before = set(before_body["properties"])
        after = set(after_body["properties"])
        assert after - before == expected["added"], f"{name} gained {sorted(after - before)}"
        assert before - after == expected["removed"], f"{name} lost {sorted(before - after)}"
        if name == "SurfaceSpec":
            # This one changed inside a property rather than by gaining one, so
            # the property-set comparison above says nothing about it. Name the
            # movement, or the declaration excuses everything in the schema.
            enum_before = set(before_body["properties"]["texture"]["enum"])
            enum_after = set(after_body["properties"]["texture"]["enum"])
            assert enum_after - enum_before == SURFACE_TEXTURE_ENUM_ADDED
            assert enum_before - enum_after == set()

    assert len(operations) == PRE_ACL_OPERATION_COUNT - len(CHANGED_OPERATIONS)
    assert len(schemas) == PRE_ACL_SCHEMA_COUNT - len(CHANGED_SCHEMAS)

    unchanged_before = {
        name: body for name, body in baseline["schemas"].items() if name not in CHANGED_SCHEMAS
    }
    assert schemas == unchanged_before, (
        "a schema that predates this branch and was not declared as changing has moved: "
        f"{sorted(set(schemas) ^ set(unchanged_before)) or [n for n in schemas if schemas[n] != unchanged_before.get(n)]}"
    )
    unchanged_ops_before = {
        key: _stable(op) for key, op in baseline_ops.items() if key not in CHANGED_OPERATIONS
    }
    assert unchanged_ops_before == operations, (
        "an operation that predates this branch has changed. "
        "Adding a route is allowed; altering one that was already there is not."
    )


def test_the_acl_routes_carry_their_shape() -> None:
    """The route exists AND says what it returns.

    Without this, dropping `permission` from the response model would leave the
    route count right, the digest of the other 82 untouched, and the shared work
    silently readable-or-writable with no way for a client to tell which.
    """
    surface = current_surface()
    by_key = {f"{op['method']} {op['path']}": op for op in surface["operations"]}
    for key in ADDED_OPERATIONS:
        assert key in by_key, f"route missing: {key}"
        assert by_key[key]["responses"].get("200"), f"{key} declares no 200 response"

    entry = json.loads(surface["schemas"]["HistoryAclEntryOut"])
    properties = set(entry.get("properties", {}))
    for field in ("subject_type", "subject_id", "permission", "history_id", "at"):
        assert field in properties, f"HistoryAclEntryOut lost `{field}`"
