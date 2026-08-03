"""A trashed work must not reach the endpoints that act on a work (I-094).

`get_items` filtered on owner and id alone, so an id sent straight to the
export endpoints put a trashed work into the output. The trash view could reach
this too: its export buttons are not gated on the view, so selecting trashed
works and asking for an animation went through.

These are written against the endpoints, because that is where the leak was
visible; the last one pins the layer itself, so a caller added later inherits
the exclusion instead of having to remember it.
"""

from __future__ import annotations

from inku_server import db
from inku_server.api_core.routers import history as history_routes

from .test_api import auth_context, client  # noqa: F401

ANIMATION_REQUEST = {
    "format": "gif",
    "pattern": "slide",
    "hold_seconds": 2.5,
    "resolution": "4k",
    "height_px": 300,
}


def _saved(headers, index: int) -> str:
    response = client.post(
        "/api/history",
        json={
            "input": f"trash probe {index}",
            "ddl": "中心に円",
            "score": {"instructions": []},
            "svg": f'<svg data-frame="{index}"></svg>',
            "at": 1_700_000_000_000 + index,
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["id"]


def _export_animation(headers, ids: list[str]):
    return client.post(
        "/api/history/export-animation",
        json={"ids": ids, **ANIMATION_REQUEST},
        headers=headers,
    )


def test_a_trashed_work_is_not_exported_as_animation(auth_context, monkeypatch):  # noqa: F811
    headers, user, _group = auth_context
    ids = [_saved(headers, index) for index in range(2)]
    monkeypatch.setattr(history_routes, "build_animation", lambda svgs, **options: b"GIF89a")
    try:
        assert _export_animation(headers, ids).status_code == 200

        trashed = client.post("/api/history/trash", json={"ids": ids}, headers=headers)
        assert trashed.json()["count"] == 2

        assert _export_animation(headers, ids).status_code == 404
    finally:
        db.delete_items(user["id"], ids)


def test_a_trashed_work_is_not_served_or_rebuilt(auth_context):  # noqa: F811
    headers, user, _group = auth_context
    item_id = _saved(headers, 7)
    try:
        assert client.get(f"/api/history/{item_id}/svg", headers=headers).status_code == 200

        trashed = client.post("/api/history/trash", json={"ids": [item_id]}, headers=headers)
        assert trashed.json()["count"] == 1

        assert client.get(f"/api/history/{item_id}/svg", headers=headers).status_code == 404
        assert client.get(f"/api/history/{item_id}/neighbors", headers=headers).status_code == 404
        assert client.get(f"/api/history/{item_id}/lineage", headers=headers).status_code == 404

        rebuilt = client.post("/api/history/rebuild-output-files", json={"ids": [item_id]}, headers=headers)
        assert rebuilt.status_code == 200
        assert rebuilt.json()["count"] == 0

        # The trash view keeps its own listing; this change must not empty it.
        listing = client.get("/api/history?offset=0&limit=100&trashed=true", headers=headers)
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
    finally:
        db.delete_items(user["id"], [item_id])


def test_get_items_itself_skips_the_trash(auth_context):  # noqa: F811
    headers, user, _group = auth_context
    kept, binned = _saved(headers, 11), _saved(headers, 12)
    try:
        trashed = client.post("/api/history/trash", json={"ids": [binned]}, headers=headers)
        assert trashed.json()["count"] == 1

        returned = [item["id"] for item in db.get_items(user["id"], [kept, binned])]
        assert returned == [kept]
    finally:
        db.delete_items(user["id"], [kept, binned])
