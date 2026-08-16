"""T-80 / T-82: the three routes that left the public list are guarded, and say so.

I-086. `test_route_authorization.py` walks the dependency tree and says the
guard is wired; that is a statement about the app object, not about what a
client without a session gets back. A guard that was declared but never reached
-- a router included twice, once without its dependency, or a route whose
decorator moved while the allowlist did not -- would keep that file green and
still answer 200 to a stranger.

So ask over HTTP, both ways, and read the surface the server publishes rather
than the file that records it: `api-surface-baseline.json` is regenerated
whenever the surface legitimately changes, so on its own it cannot say the
arguments are there today.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app

from .test_api_surface import current_surface

client = TestClient(app)

# The three routes I-086 moved, with a key each response has to keep carrying.
# Naming a key is what separates "the guard lets me in" from "the guard lets me
# in and the route still answers what it used to": a route that had quietly
# become an empty 200 would pass a status-only check.
MOVED_ROUTES = [
    ("/api/prompts", ("stage1_system", "stage2_system")),
    ("/api/color-catalogs", ("default_catalog_id",)),
    ("/api/auth/config", ("local_enabled",)),
]

GUARD_PARAMS = {"cookie:inku_session:opt", "header:authorization:opt"}


@pytest.fixture
def headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"public-list-{suffix}")
    user = db.add_user(
        username=f"public-list-{suffix}",
        email=f"public-list-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


@pytest.mark.parametrize("path,_keys", MOVED_ROUTES, ids=lambda v: v if isinstance(v, str) else "")
def test_t80_a_stranger_is_turned_away(path, _keys) -> None:
    assert client.get(path).status_code == 401, path


@pytest.mark.parametrize("path,keys", MOVED_ROUTES, ids=lambda v: v if isinstance(v, str) else "")
def test_t80_a_session_is_let_in_and_the_answer_is_unchanged(path, keys, headers) -> None:
    response = client.get(path, headers=headers)
    assert response.status_code == 200, path
    body = response.json()
    for key in keys:
        assert key in body, f"{path} no longer answers {key}"


@pytest.mark.parametrize("path,_keys", MOVED_ROUTES, ids=lambda v: v if isinstance(v, str) else "")
def test_t82_the_published_surface_shows_the_guard(path, _keys) -> None:
    """Read the live OpenAPI, not the recorded one."""
    operations = {
        (op["method"], op["path"]): op for op in current_surface()["operations"]
    }
    params = set(operations[("GET", path)]["params"])
    assert GUARD_PARAMS <= params, f"{path} publishes {sorted(params)}"
