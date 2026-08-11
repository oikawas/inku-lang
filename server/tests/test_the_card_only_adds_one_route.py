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
ADDED_OPERATIONS = {f"POST {CARD_ROUTE}"}
ADDED_SCHEMAS = {"CardExportBody"}


def _before() -> dict:
    return json.loads(SURFACE_BEFORE_THE_CARD.read_text(encoding="utf-8"))


def test_the_route_count_is_the_branch_points_count_plus_one() -> None:
    before = _before()
    assert len(_api_routes()) == before["endpoint_count"] + len(ADDED_OPERATIONS)


def test_the_card_route_is_guarded_and_the_public_list_did_not_grow() -> None:
    """The card is somebody's own work, so it is not a public route."""
    assert len(PUBLIC) == 6
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

    before_operations = {
        f"{op['method']} {op['path']}": _stable(op) for op in before["operations"]
    }
    assert operations == before_operations, (
        "an operation that predates the card has changed. Adding a route is "
        "allowed; altering or losing one that was already there is not: "
        f"{sorted(set(operations) ^ set(before_operations)) or [k for k in operations if operations[k] != before_operations.get(k)]}"
    )
    assert schemas == before["schemas"], (
        "a schema that predates the card has changed: "
        f"{sorted(set(schemas) ^ set(before['schemas'])) or [n for n in schemas if schemas[n] != before['schemas'].get(n)]}"
    )


def test_the_card_route_declares_what_it_returns() -> None:
    """A route that exists but declares no response is a route that can lose one."""
    surface = current_surface()
    by_key = {f"{op['method']} {op['path']}": op for op in surface["operations"]}
    operation = by_key[f"POST {CARD_ROUTE}"]
    assert operation["responses"].get("200")
    body = json.loads(surface["schemas"]["CardExportBody"])
    assert set(body["properties"]) == {"id", "layout", "seal"}
