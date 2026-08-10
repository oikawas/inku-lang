"""T-11: sharing added routes to the API and moved none of the ones already there.

`test_api_surface.py` compares the whole surface against a baseline file, and
that file is REGENERATED whenever the surface legitimately changes. A regenerated
record is not a gate: the moment sharing landed, the baseline was rewritten to
match whatever the code now produces, and any collateral damage in the other 82
operations was written into the new baseline as if it had always been there.

So the pre-ACL surface is frozen here as a digest, by hand, from the baseline as
it stood at `3450548c` -- before any of this branch's stages. The check is a set
difference: strip the operations and schemas this branch is allowed to add, and
what remains must hash to exactly what was there before.

What this does NOT cover, and nothing on the surface can: the lineage responses
(`/api/lineage/{node_id}` and `/api/history/{item_id}/lineage`) declare no
`response_model` and return a bare dict. A work's description and image could
leak through a lineage node without moving one byte here. That is guarded by
behaviour alone -- see the lineage tests.
"""

from __future__ import annotations

import hashlib
import json

from .test_api_surface import _stable, current_surface


# The 82 operations and 82 schemas as of `3450548c`, the branch point. Measured
# once from the then-current baseline file; never regenerated.
PRE_ACL_DIGEST = "9fdae3d3a725dcf7692fd00983c9f5ef51a6a414075b3841890c8a7ba3651d04"
PRE_ACL_OPERATION_COUNT = 82
PRE_ACL_SCHEMA_COUNT = 82

# Everything this branch is allowed to add, named one by one. A route that
# appears without being listed here fails, which is the point: "the count went
# up by two" would also pass if one route were added and another replaced.
ADDED_OPERATIONS = {
    "GET /api/history/{item_id}/acl",
    "PUT /api/history/{item_id}/acl",
    "GET /api/settings/single-user",
    "PUT /api/settings/single-user",
}

ADDED_SCHEMAS = {
    "HistoryAclEntry",
    "HistoryAclEntryOut",
    "HistoryAclBody",
    "SingleUserStatus",
    "SingleUserCandidate",
    "SingleUserBody",
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

    assert len(operations) == PRE_ACL_OPERATION_COUNT
    assert len(schemas) == PRE_ACL_SCHEMA_COUNT

    digest = hashlib.sha256(
        _stable({"operations": operations, "schemas": schemas}).encode()
    ).hexdigest()
    assert digest == PRE_ACL_DIGEST, (
        "an operation or schema that predates this branch has changed. "
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
