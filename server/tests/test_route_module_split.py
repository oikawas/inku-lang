"""Every endpoint's body has left api.py.

The I-088 ruling forbids line counts as an acceptance gate, so this asks the
live app instead: route.endpoint keeps the module that defined it, so a route
still answering "inku_server.api" has not been split out.

Enumerate through `iter_route_contexts`: fastapi 0.141 stopped flattening
included routers into `app.routes`, so the previous `isinstance(r, APIRoute)`
scan over `app.routes` matched nothing and this gate passed on an empty list
(measured 2026-08-02).  Assert the route count too -- an empty enumeration must
fail loudly rather than read as "every endpoint has moved".
"""

from fastapi.routing import APIRoute, iter_route_contexts

from inku_server.api import app


def _api_routes() -> list:
    return [
        ctx
        for ctx in iter_route_contexts(app.routes)
        if isinstance(ctx.original_route, APIRoute)
    ]


def test_the_enumeration_still_sees_the_routes():
    # Without this, a routing change upstream turns the gate below into a no-op.
    assert len(_api_routes()) > 50


def test_no_endpoint_is_still_defined_in_api_module():
    left = sorted(
        f"{sorted(r.methods)[0]} {r.path}"
        for r in _api_routes()
        if r.endpoint.__module__ == "inku_server.api"
    )
    assert left == [], f"{len(left)} endpoints still live in api.py: {left[:10]}"
