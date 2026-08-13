"""[I-157]: a redraw of a saved work is that work's performance, not another one.

`GET /api/history/{id}/svg` returns the stored picture for the `display`
profile and redraws from the Score for every other one. It read `wild` and
`composition_seed` off the row and left `render_seed` behind, so the marks
landed where the saved work put them and every stroke was drawn by a different
hand -- the same score, played again.

What this file does *not* claim is that the export equals the stored SVG.
Principle 7 says the engine only moves forward and the past version is not
kept, so a redraw under a later engine is a different print and is meant to be.
The claim is narrower and is the whole of the ruling (author, 2026-08-13,
option A): what separates the export from the saved picture is the engine
having moved on, and nothing else. A seed left behind was a second difference
on top of that one, and it was being read as the engine's.

T-1 (the export is the row's own performance seed), T-2 (and its own placement
seed, which was already true -- the control that says T-1 is not passing for
the wrong reason), T-3 (an export is deterministic, so a difference between two
of them is a difference in the seeds), T-4 (the display profile still returns
the stored bytes untouched).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.api_core.rendering import _render_score_svg

client = TestClient(app)

RENDER_SEED = 4242
OTHER_RENDER_SEED = 9191
COMPOSITION_SEED = 777


def _score(weight: str = "pen") -> dict:
    """A scatter drawn with a live hand.

    `pen` and not `rotring`: the machine tool has no hand amplitude, so the
    performance seed would have nothing left to move and T-1 would pass over an
    export that still dropped it.
    """
    return {
        "instructions": [
            {
                "primitive": "circle",
                "center": [0.5, 0.5],
                "radius": 0.04,
                "weight": weight,
                "arrangement": {"count": 12, "layout": "scatter", "jitter": 0.12, "margin": 0.1},
            }
        ]
    }


@pytest.fixture
def auth_context():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"i157-{suffix}")
    user = db.add_user(
        username=f"i157-{suffix}",
        email=f"i157-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}, user
    db.delete_session(token)


def _save(headers: dict, *, render_seed: int | None, composition_seed: int | None, at: int) -> str:
    saved = client.post(
        "/api/history",
        json={
            # No `svg`: this route always renders its own, so what is stored is
            # the server's picture at these seeds and not anything sent here.
            "score": _score(),
            "input": "twelve circles",
            "at": at,
            "render_seed": render_seed,
            "composition_seed": composition_seed,
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    return saved.json()["id"]


def _export(headers: dict, item_id: str, profile: str = "editable") -> str:
    response = client.get(
        f"/api/history/{item_id}/svg", params={"profile": profile}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.text


# T-1 ---------------------------------------------------------------------
def test_the_export_uses_the_performance_seed_the_row_carries(auth_context):
    """Two works, one score, one placement seed, different performance seeds.

    Nothing else differs, so an export that still left `render_seed` behind
    would hand back two identical files.
    """
    auth_headers, _ = auth_context
    a = _save(auth_headers, render_seed=RENDER_SEED, composition_seed=COMPOSITION_SEED, at=1_770_000_000_001)
    b = _save(auth_headers, render_seed=OTHER_RENDER_SEED, composition_seed=COMPOSITION_SEED, at=1_770_000_000_002)
    assert _export(auth_headers, a) != _export(auth_headers, b)

    # And it is the row's value that arrives, not merely some value: the export
    # matches a render asked for those two seeds by name.
    expected, _, _ = _render_score_svg(
        _score(),
        catalog_id=None,
        svg_profile="editable",
        render_seed=RENDER_SEED,
        composition_seed=COMPOSITION_SEED,
    )
    assert _export(auth_headers, a) == expected


# T-2 ---------------------------------------------------------------------
def test_the_export_still_uses_the_placement_seed_the_row_carries(auth_context):
    """The control for T-1.

    The placement seed already reached this route (engine 23) and must still.
    An export that had started ignoring both seeds would fail here as well, so
    the two checks together say which seed is which rather than that some seed
    got through.
    """
    auth_headers, _ = auth_context
    a = _save(auth_headers, render_seed=RENDER_SEED, composition_seed=COMPOSITION_SEED, at=1_770_000_000_003)
    b = _save(auth_headers, render_seed=RENDER_SEED, composition_seed=COMPOSITION_SEED + 1, at=1_770_000_000_004)
    assert _export(auth_headers, a) != _export(auth_headers, b)


# T-3 ---------------------------------------------------------------------
def test_an_export_is_the_same_file_twice(auth_context):
    """What makes the two comparisons above mean anything.

    If a redraw were non-deterministic, T-1 and T-2 would be measuring noise
    and would pass whatever the route sent.
    """
    auth_headers, _ = auth_context
    item_id = _save(
        auth_headers, render_seed=RENDER_SEED, composition_seed=COMPOSITION_SEED, at=1_770_000_000_005
    )
    assert _export(auth_headers, item_id) == _export(auth_headers, item_id)


# T-4 ---------------------------------------------------------------------
def test_the_display_profile_still_hands_back_the_stored_picture(auth_context):
    """The stored SVG is the work (principle 7); this route must not redraw it.

    The change above is to the redrawing branch only. Written straight to the
    row so the stored bytes are a sentinel nothing could have produced: saving
    over HTTP always renders, so a work saved that way would match a redraw and
    this check would pass over a route that had started redrawing for
    `display` too.
    """
    auth_headers, user = auth_context
    stored = "<svg><desc>this print, not another one</desc></svg>"
    item = db.add_item({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "output_path": None,
        "input": "twelve circles",
        "score": _score(),
        "svg": stored,
        "at": 1_770_000_000_006,
        "render_seed": RENDER_SEED,
        "composition_seed": COMPOSITION_SEED,
    })
    assert _export(auth_headers, item["id"], profile="display") == stored
    # And the other profile does redraw the same row -- the two branches are
    # both live, so this is not a route that ignores the profile.
    assert _export(auth_headers, item["id"]) != stored
