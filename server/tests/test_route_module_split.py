"""Every endpoint's body has left api.py.

The I-088 ruling forbids line counts as an acceptance gate, so this asks the
live app instead: include_router copies the route onto app.routes, but
route.endpoint keeps the module that defined it.  A route still answering
"inku_server.api" has not been split out.
"""

from fastapi.routing import APIRoute

from inku_server.api import app


def test_no_endpoint_is_still_defined_in_api_module():
    left = sorted(
        f"{sorted(r.methods)[0]} {r.path}"
        for r in app.routes
        if isinstance(r, APIRoute) and r.endpoint.__module__ == "inku_server.api"
    )
    assert left == [], f"{len(left)} endpoints still live in api.py: {left[:10]}"
