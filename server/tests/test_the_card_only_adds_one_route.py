"""T-7: the card added one route to the API and moved nothing that was there.

`api-surface-baseline.json` is REGENERATED whenever the surface legitimately
changes, so on its own it cannot tell an intended addition from collateral
damage -- the moment this branch landed, whatever the code now produces became
the record of what it "always" was. A count is not enough either: 82/82/82 held
steady on an earlier branch while seven response fields quietly went missing.

So the surface as it stood at this branch's starting point (`2f98dbc8`) is kept
beside it as a second, frozen file, and the check is a set difference. The
expected totals are read out of that file rather than written here, because a
concurrent branch moves the same three numbers and an absolute copied into this
file would go stale the day either one merges.
"""

from __future__ import annotations

import json
import pathlib

from .test_api_surface import _stable, current_surface
from .test_route_authorization import PUBLIC, _api_routes, _guard_names

# Frozen: never regenerated. See the module docstring.
SURFACE_BEFORE_THE_CARD = (
    pathlib.Path(__file__).parent / "data" / "api-surface-before-the-card.json"
)

CARD_ROUTE = "/api/history/export-card"
# The frozen file predates both the card and contract 3, which landed in the
# same cycle from another branch. Whatever arrived beside the card is declared
# here by name, the way test_the_acl_only_adds_to_the_api_surface.py does it:
# the check stays a set difference, so an undeclared route still fails.
ADDED_OPERATIONS = {
    f"POST {CARD_ROUTE}",
    "GET /api/history/state",
    # v2.14: the saijiki preview serves a plugin word's artwork from its own
    # route, so the picture stays out of the payload the browser asks for on
    # every hydration. Declared by name, as the docstring above requires.
    "GET /api/saijiki/plugin-preview",
}
ADDED_SCHEMAS = {"CardExportBody", "HistoryStateResponse"}

# Schemas that predate the card and are declared to change, with exactly what
# may move in them -- the mechanism test_the_acl_only_adds_to_the_api_surface.py
# uses, mirrored here for the same reason. Any OTHER movement in a declared
# schema, and any movement at all in an undeclared one, still fails.
CHANGED_SCHEMAS = {
    # [I-257]: a work records how its color catalog was asked for, beside the id
    # it resolved to. `auto` reads each description anew, so the resolved id
    # cannot say whether the author chose a catalog or let the server read the
    # words -- which is what the batch resume needs to put back.
    # 2026-08-17: the strip prints a work's file size, and the listing that
    # fills it asks for `include_svg=false` -- so the weight has to ride
    # separately from the picture it is the weight of.
    "HistoryItem": {"added": {"catalog_mode", "svg_bytes"}, "removed": set()},
    # 2026-08-17: the reader chooses which two facts the history strip prints
    # under each thumbnail. It is an account setting, so it rides on the account
    # it belongs to and on the PATCH that changes it.
    "UserAccountItem": {"added": {"history_strip_fields"}, "removed": set()},
    "UserSettingsBody": {"added": {"history_strip_fields"}, "removed": set()},
    "HistoryPostBody": {"added": {"catalog_mode"}, "removed": set()},
    # v2.14: whether a plugin expands is decided by prose. A work authored
    # straight in DDL has no description and must not be given one to make one
    # expand, so the prose rides in its own optional key. Callers that never
    # send it are unaffected.
    "ComposeRequest": {"added": {"fires_on"}, "removed": set()},
    # I-143: one arrangement may repeat a contiguous Score instruction unit.
    "Arrangement": {"added": {"group_size"}, "removed": set()},
    # ddl-engine 18: a fill is a surface word like the other eight, so the
    # `texture` enum gains `solid`. Nothing gains a property, which is why the
    # enum is named below rather than left to the property-set comparison.
    "SurfaceSpec": {"added": set(), "removed": set()},
    # ddl-engine 19 / render-engine 34: the ground is a support you can name, so
    # the `material` enum gains `canvas` and `drawing_paper`. Nothing gains a
    # property, which is why the enum is named below.
    "CanvasGroundSpec": {"added": set(), "removed": set()},
    # I-154: a work is redrawn under the limits it was drawn under. Three
    # requests gain the key that names limits for one render, and three
    # responses gain the key that says which of the four sources decided them --
    # `render_limits` alone cannot tell a faithful replay from today's settings.
    "PaintRequest": {"added": {"limits"}, "removed": set()},
    "RenderSvgRequest": {"added": {"limits"}, "removed": set()},
    "RenderScoreRequest": {"added": {"limits"}, "removed": set()},
    "PaintResponse": {"added": {"render_limits_source"}, "removed": set()},
    "ComposeResponse": {"added": {"render_limits_source"}, "removed": set()},
    "RenderScoreResponse": {"added": {"render_limits_source"}, "removed": set()},
    # I-132: the limits panel converts the total into the weight of a work, so
    # the settings response carries the measured cost of one mark. One key, and
    # a second one arriving here is still red.
    "RenderLimitsStatus": {"added": {"bytes_per_mark"}, "removed": set()},
}

SURFACE_TEXTURE_ENUM_ADDED = {"solid"}
GROUND_MATERIAL_ENUM_ADDED = {"canvas", "drawing_paper"}
# I-136: `cluster_count` lost its static `maximum` for the reason `count` never
# had one -- a bound no setting can reach is a second copy of the setting. It is
# a change INSIDE a property, so the property-set comparison above sees nothing
# and the declaration would excuse the whole schema. Named here instead.
CLUSTER_COUNT_BOUND_REMOVED = 12.0

# Operations that predate the card and are declared to change, with exactly what
# may move in them -- the same mechanism as CHANGED_SCHEMAS above, and the same
# one test_the_acl_only_adds_to_the_api_surface.py uses. Any OTHER movement in a
# declared operation, and any movement at all in an undeclared one, still fails.
#
# I-086: three routes that were public moved behind the guard, so each gains the
# two arguments the guard reads. The two that carried no parameter at all also
# gain a 422, because a route with nothing to validate has no validation error
# to describe -- every already-guarded route in the frozen file carries both.
# The 200 of each is compared as before, so a route that quietly stopped
# describing what it returns is still red.
CHANGED_OPERATIONS = {
    "GET /api/prompts": {
        "added_params": {"cookie:inku_session:opt", "header:authorization:opt"},
        "removed_params": set(),
    },
    "GET /api/color-catalogs": {
        "added_params": {"cookie:inku_session:opt", "header:authorization:opt"},
        "removed_params": set(),
        "added_responses": {"422"},
    },
    "GET /api/auth/config": {
        "added_params": {"cookie:inku_session:opt", "header:authorization:opt"},
        "removed_params": set(),
        "added_responses": {"422"},
    },
}


def _before() -> dict:
    return json.loads(SURFACE_BEFORE_THE_CARD.read_text(encoding="utf-8"))


def test_the_route_count_is_the_branch_points_count_plus_one() -> None:
    before = _before()
    assert len(_api_routes()) == before["endpoint_count"] + len(ADDED_OPERATIONS)


def test_the_card_route_is_guarded_and_the_public_list_did_not_grow() -> None:
    """The card is somebody's own work, so it is not a public route."""
    assert len(PUBLIC) == 3
    assert CARD_ROUTE not in PUBLIC

    card_routes = [context for context in _api_routes() if context.route.path == CARD_ROUTE]
    assert len(card_routes) == 1
    assert _guard_names(card_routes[0].route.dependant) & {"_current_user"}


def test_the_surface_gained_exactly_the_card_and_nothing_else() -> None:
    before = _before()
    surface = current_surface()

    operations = {f"{op['method']} {op['path']}": _stable(op) for op in surface["operations"]}
    schemas = dict(surface["schemas"])

    assert set(operations) - {
        f"{op['method']} {op['path']}" for op in before["operations"]
    } == ADDED_OPERATIONS
    assert set(schemas) - set(before["schemas"]) == ADDED_SCHEMAS

    for key in ADDED_OPERATIONS:
        operations.pop(key)
    for name in ADDED_SCHEMAS:
        schemas.pop(name)
    # The declared changes, checked field by field before being set aside.
    for name, expected in CHANGED_SCHEMAS.items():
        was_body = json.loads(before["schemas"][name])
        now_body = json.loads(schemas.pop(name))
        was = set(was_body["properties"])
        now = set(now_body["properties"])
        assert now - was == expected["added"], f"{name} gained {sorted(now - was)}"
        assert was - now == expected["removed"], f"{name} lost {sorted(was - now)}"
        if name == "SurfaceSpec":
            # Changed inside a property rather than by gaining one, so the
            # comparison above sees nothing. Name the movement or the
            # declaration excuses the whole schema.
            was_enum = set(was_body["properties"]["texture"]["enum"])
            now_enum = set(now_body["properties"]["texture"]["enum"])
            assert now_enum - was_enum == SURFACE_TEXTURE_ENUM_ADDED
            assert was_enum - now_enum == set()
        if name == "CanvasGroundSpec":
            # Same reason as `SurfaceSpec`: the movement is inside a property.
            was_enum = set(was_body["properties"]["material"]["enum"])
            now_enum = set(now_body["properties"]["material"]["enum"])
            assert now_enum - was_enum == GROUND_MATERIAL_ENUM_ADDED
            assert was_enum - now_enum == set()
        if name == "Arrangement":
            # Same reason again: `cluster_count` gave up a bound rather than a
            # property. Name what left, and name that nothing else did, or the
            # `group_size` declaration above would cover the whole schema.
            def _integer_branch(body: dict) -> dict:
                branches = body["properties"]["cluster_count"]["anyOf"]
                return next(b for b in branches if b.get("type") == "integer")

            was_branch = _integer_branch(was_body)
            now_branch = _integer_branch(now_body)
            assert was_branch.pop("maximum") == CLUSTER_COUNT_BOUND_REMOVED
            assert "maximum" not in now_branch, "the bound comes from limits now"
            assert was_branch == now_branch, "nothing else in the bound may move"

    # The declared operation changes, checked argument by argument and response
    # by response before being set aside.
    before_ops = {f"{op['method']} {op['path']}": op for op in before["operations"]}
    for key, expected_delta in CHANGED_OPERATIONS.items():
        before_params = set(before_ops[key]["params"])
        after_op = next(
            op for op in surface["operations"] if f"{op['method']} {op['path']}" == key
        )
        after_params = set(after_op["params"])
        assert after_params - before_params == expected_delta["added_params"], key
        assert before_params - after_params == expected_delta["removed_params"], key
        before_responses = dict(before_ops[key]["responses"])
        after_responses = dict(after_op["responses"])
        added_responses = expected_delta.get("added_responses", set())
        removed_responses = expected_delta.get("removed_responses", set())
        assert set(after_responses) - set(before_responses) == added_responses, key
        assert set(before_responses) - set(after_responses) == removed_responses, key
        # Everything else about the operation must still match byte for byte --
        # including the body of every response that was already described.
        for code in added_responses:
            after_responses.pop(code)
        for code in removed_responses:
            before_responses.pop(code)
        assert _stable(
            {**after_op, "params": sorted(before_params), "responses": after_responses}
        ) == _stable({**before_ops[key], "responses": before_responses}), key
        operations.pop(key)

    before_operations = {
        key: _stable(op) for key, op in before_ops.items() if key not in CHANGED_OPERATIONS
    }
    assert operations == before_operations, (
        "an operation that predates the card has changed. Adding a route is "
        "allowed; altering or losing one that was already there is not: "
        f"{sorted(set(operations) ^ set(before_operations)) or [k for k in operations if operations[k] != before_operations.get(k)]}"
    )
    before_schemas = {
        name: body for name, body in before["schemas"].items() if name not in CHANGED_SCHEMAS
    }
    assert schemas == before_schemas, (
        "a schema that predates the card has changed: "
        f"{sorted(set(schemas) ^ set(before_schemas)) or [n for n in schemas if schemas[n] != before_schemas.get(n)]}"
    )


def test_the_card_route_declares_what_it_returns() -> None:
    """A route that exists but declares no response is a route that can lose one."""
    surface = current_surface()
    by_key = {f"{op['method']} {op['path']}": op for op in surface["operations"]}
    operation = by_key[f"POST {CARD_ROUTE}"]
    assert operation["responses"].get("200")
    body = json.loads(surface["schemas"]["CardExportBody"])
    assert set(body["properties"]) == {"id", "layout", "seal"}
