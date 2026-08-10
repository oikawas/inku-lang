"""Every endpoint is either behind an authorization guard or on the public list.

The gate walks the live app, not the source text.  A regex over api.py would
stop working the moment routes move into routers -- which is exactly what the
module split does.  Router-level dependencies DO appear in route.dependant
(verified 2026-08-01), so the split does not have to keep per-route guards.

Enumerate through `iter_route_contexts`, not `app.routes` directly: fastapi
0.141 stopped flattening included routers into `app.routes` and puts an opaque
`_IncludedRouter` wrapper there instead, so `isinstance(r, APIRoute)` over
`app.routes` silently yields nothing (measured 2026-08-02: 81 -> 0).  A gate that
enumerates zero routes stays green while checking nothing.
"""

from fastapi.routing import APIRoute, iter_route_contexts

from inku_server.api import app

GUARDS = {"_current_user", "_admin_user", "_user_manager", "_session_token"}

PUBLIC = {  # every entry needs a reason
    "/health",  # liveness probe, no data
    "/api/info",  # build/version banner shown before login
    "/api/color-catalogs",  # catalog list, needed to render the login screen
    "/api/auth/config",  # tells the client whether login is required at all
    "/api/auth/login",  # the login endpoint itself
    "/api/prompts",  # ledger I-086: keeping it public is still undecided
}

# The count is part of the contract: a split that loses an endpoint is a
# regression that no per-route assertion would notice.
#   82 before the ACL work; +2 for GET/PUT /api/history/{item_id}/acl (stage D),
#   +2 for GET/PUT /api/settings/single-user (stage H), and +1 for
#   GET /api/auth/me/group-peers, which lets sharing offer names.
EXPECTED_ROUTE_COUNT = 87


def _guard_names(dependant, seen=None) -> set[str]:
    """Names of every callable in a route's dependency tree.

    Walks sub-dependencies too: _admin_user is itself built on _current_user,
    and a router-level guard arrives the same way a per-route one does.
    """
    if seen is None:
        seen = set()
    names: set[str] = set()
    for dep in dependant.dependencies:
        if dep.call is not None:
            names.add(getattr(dep.call, "__name__", ""))
        if id(dep) not in seen:
            seen.add(id(dep))
            names |= _guard_names(dep, seen)
    return names


def _api_routes() -> list:
    # RouteContext forwards .path and .dependant to the effective route.
    return [
        ctx
        for ctx in iter_route_contexts(app.routes)
        if isinstance(ctx.original_route, APIRoute)
    ]


def test_endpoint_count_is_unchanged():
    assert len(_api_routes()) == EXPECTED_ROUTE_COUNT


def test_every_route_is_guarded_or_listed_public():
    unguarded = {r.path for r in _api_routes() if not (_guard_names(r.dependant) & GUARDS)}
    assert unguarded == PUBLIC


def test_public_list_names_only_real_routes():
    # Keeps the allowlist from going stale: a removed or renamed path would
    # otherwise sit in PUBLIC forever and silently widen it.
    paths = {r.path for r in _api_routes()}
    assert PUBLIC <= paths
