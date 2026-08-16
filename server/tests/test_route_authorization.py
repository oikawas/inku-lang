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

import pathlib
import re

import pytest
from fastapi.routing import APIRoute, iter_route_contexts

from inku_server.api import app

GUARDS = {"_current_user", "_admin_user", "_user_manager", "_session_token"}

# I-086: the reason each entry gives has to be one that was measured. The list
# used to say /api/color-catalogs was "needed to render the login screen"; the
# login screen was then measured and receives no catalog at all, so what kept
# the route public was the startup fetch running before anyone had logged in.
# What is left is only what logging in genuinely needs.
PUBLIC = {  # every entry needs a reason
    "/health",  # container liveness probe, returns no data
    "/api/info",  # build/version and developer_mode, read by the login screen
    "/api/auth/login",  # the login endpoint itself
}

# The count is part of the contract: a split that loses an endpoint is a
# regression that no per-route assertion would notice.
#   82 before the ACL work; +2 for GET/PUT /api/history/{item_id}/acl (stage D),
#   +2 for GET/PUT /api/settings/single-user (stage H), and +1 for
#   GET /api/auth/me/group-peers, which lets sharing offer names.
#   +5 for contract 2's thumbnails: GET /api/history/{item_id}/thumb, and
#   GET/PUT /api/settings/thumbnails with GET/POST of its rebuild.
#   +1 for contract 3's GET /api/history/state, which lets the strip ask
#   whether the listing changed without fetching the listing.
#   +1 for POST /api/history/export-card, the shareable one-sheet card.
#   The last two landed in the same cycle from two branches, and each had
#   written 93 on its own: the merged count is the base plus both, not either.
#   +1 for GET /api/saijiki/plugin-preview, which serves a plugin word's
#   artwork so the picture stays out of the saijiki payload the browser
#   asks for on every hydration.
EXPECTED_ROUTE_COUNT = 95


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


def test_only_stronger_admin_guards_remain_as_unused_route_arguments():
    """A route argument exists only when its value or stronger guard is needed."""
    import ast
    from pathlib import Path

    routers = Path(__file__).parents[1] / "src" / "inku_server" / "api_core" / "routers"
    unused: set[tuple[str, str, str]] = set()
    for path in routers.glob("*.py"):
        tree = ast.parse(path.read_text())
        for function in tree.body:
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_route = any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id.endswith("router")
                for decorator in function.decorator_list
            )
            if not is_route:
                continue
            defaults = zip(function.args.args[-len(function.args.defaults):], function.args.defaults)
            for argument, default in defaults:
                if not (
                    isinstance(default, ast.Call)
                    and isinstance(default.func, ast.Name)
                    and default.func.id == "Depends"
                    and default.args
                ):
                    continue
                used = any(
                    isinstance(node, ast.Name) and node.id == argument.arg
                    for statement in function.body
                    for node in ast.walk(statement)
                )
                if not used:
                    unused.add((path.name, function.name, ast.unparse(default.args[0])))

    assert unused == {
        ("plugins.py", "api_plugin_content", "_admin_user"),
        ("plugins.py", "api_plugin_create", "_admin_user"),
        ("plugins.py", "api_plugin_delete", "_admin_user"),
        ("plugins.py", "api_plugin_set_enabled", "_admin_user"),
        ("plugins.py", "api_plugin_update", "_admin_user"),
        ("plugins.py", "api_plugins_reload", "_admin_user"),
        ("plugins.py", "api_plugins_validate", "_admin_user"),
    }


# T-89: the published architecture note spells the allowlist out by hand, in two
# languages. A hand-copied list is a copy that goes stale the day the list moves
# -- and a reader who trusts it is told a route is public when it is not. Both
# files are read here so neither half can drift alone.
_DOCS = pathlib.Path(__file__).parents[2] / "docs" / "architecture"
_ALLOWLIST_DOCS = ("server-components.ja.md", "server-components.md")


def _documented_public_paths(text: str) -> set[str]:
    """Every `/...` path in the sentence that names the allowlist."""
    sentence = next(
        line for line in text.splitlines() if "test_route_authorization.py" in line
    )
    return set(re.findall(r"`(/[a-z0-9/_-]+)`", sentence))


@pytest.mark.skipif(not _DOCS.is_dir(), reason="docs/ is absent from this checkout")
@pytest.mark.parametrize("name", _ALLOWLIST_DOCS)
def test_the_published_allowlist_matches_the_one_the_gate_uses(name) -> None:
    documented = _documented_public_paths((_DOCS / name).read_text(encoding="utf-8"))
    assert documented == PUBLIC, (
        f"{name} lists {sorted(documented)}; the gate holds {sorted(PUBLIC)}"
    )
