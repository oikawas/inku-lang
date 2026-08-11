"""Contract 2: the listing carries a picture of the work, not the work.

GET /api/history used to return every listed work's whole SVG -- 23.5 MB and
1.8 s for the 21 works the strip shows, most of it spent escaping 22 million
characters into one JSON document. These are the gates for the thumbnail store
that replaces it.

The one thing that must not happen is the picture changing. A thumbnail is a
rasterization of the SVG the work has been holding since it was saved: the
engine is not run, so a work drawn by engine 2 becomes a PNG of the engine 2
picture and not of what engine 29 would draw from the same Score today.
"""

from __future__ import annotations

import ast
import pathlib
import struct
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server import thumbs_db
from inku_server.api import app
from inku_server.api_core import thumbnails

client = TestClient(app)


SQUARE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">'
    '<rect width="1000" height="1000" fill="#8d7f73"/></svg>'
)
WIDE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2160 919">'
    '<rect width="2160" height="919" fill="#8d7f73"/></svg>'
)
#: A picture no Score in these tests could produce, used to tell "rasterized the
#: stored SVG" apart from "drew the work again".
IMPOSTOR_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">'
    '<rect width="1000" height="1000" fill="#ff0000"/></svg>'
)


def png_size(png: bytes) -> tuple[int, int]:
    """Width and height out of the IHDR chunk."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    return width, height


def rasterize(svg: str, width: int) -> bytes:
    from inku_analysis.rasterizer import svg_to_png

    return svg_to_png(svg, width=width)


def _auth_headers(user: dict) -> tuple[dict[str, str], str]:
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}, token


def _make_user(prefix: str, permission_groups: list[str] | None = None):
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"{prefix}-{suffix}")
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        permission_groups=permission_groups or ["users"],
        group_id=group["id"],
    )
    headers, token = _auth_headers(user)
    return user, group, headers, token


@pytest.fixture
def owner():
    user, group, headers, token = _make_user("thumb-owner")
    yield user, headers
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


@pytest.fixture
def stranger():
    user, group, headers, token = _make_user("thumb-stranger")
    yield user, headers
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


@pytest.fixture
def admin_headers():
    user, group, headers, token = _make_user("thumb-admin", ["admins"])
    yield headers
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


def save_work(user: dict, svg: str = SQUARE_SVG) -> dict:
    """A stored work, without going through the render path."""
    return db.add_item({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "input": "thumbnail gate",
        "ddl": None,
        "score": {"instructions": []},
        "svg": svg,
        "at": int(time.time() * 1000),
    })


def bake_for(item: dict, scale: int = 1) -> None:
    thumbnails.build_one(item["id"], item["svg"], item.get("render_hash"), scale)


@pytest.fixture(autouse=True)
def _thumb_store():
    thumbs_db.init_thumbs_db()
    yield


# ── T-1 ─────────────────────────────────────────────────────────────────────
def test_the_thumbnail_is_the_stored_picture_and_baking_is_repeatable(owner):
    user, _ = owner
    item = save_work(user)

    # The stored SVG is replaced with one that no Score here could draw. An
    # implementation that re-rendered from the Score would produce the original
    # picture; rasterizing is the only way to arrive at this one.
    with db.engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(
            text("UPDATE history SET svg = :svg WHERE id = :id"),
            {"svg": IMPOSTOR_SVG, "id": item["id"]},
        )
    stored = db.history_svgs([item["id"]])[item["id"]]
    assert stored == IMPOSTOR_SVG

    first = thumbnails.bake(stored, 1)
    second = thumbnails.bake(stored, 1)
    assert first == second, "the same SVG must rasterize to the same bytes"
    assert first == rasterize(IMPOSTOR_SVG, 256)


def test_baking_never_runs_the_engine(owner, monkeypatch):
    user, _ = owner
    item = save_work(user, IMPOSTOR_SVG)

    def refuse(*args, **kwargs):
        raise AssertionError("the engine was run to make a thumbnail")

    monkeypatch.setattr("inku_server.renderer.render", refuse)
    monkeypatch.setattr("inku_server.api_core.rendering._render_score_svg", refuse)

    assert thumbnails.build_one(item["id"], item["svg"], item.get("render_hash"), 1)
    row = thumbs_db.get_thumb(item["id"], 1)
    assert row is not None
    assert row["png"] == rasterize(IMPOSTOR_SVG, 256)


# ── T-2 ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "svg,view_w,view_h",
    [(SQUARE_SVG, 1000, 1000), (WIDE_SVG, 2160, 919)],
)
def test_the_thumbnail_keeps_the_works_proportions(svg, view_w, view_h):
    width, height = png_size(thumbnails.bake(svg, 1))
    assert width == 256
    # Only the width is given to the rasterizer, so the height follows the
    # viewBox. Rounding is to the nearest pixel, hence the tolerance of one.
    assert abs(height - round(256 * view_h / view_w)) <= 1
    assert height != width or view_h == view_w


# ── T-3 ─────────────────────────────────────────────────────────────────────
def test_scale_one_is_256_and_scale_two_is_512():
    assert thumbs_db.width_for_scale(1) == 256
    assert thumbs_db.width_for_scale(2) == 512
    assert png_size(thumbnails.bake(SQUARE_SVG, 1))[0] == 256
    assert png_size(thumbnails.bake(SQUARE_SVG, 2))[0] == 512


# ── T-4 ─────────────────────────────────────────────────────────────────────
def test_saving_a_work_does_not_wait_for_its_thumbnail(owner, monkeypatch):
    """Baking measured 0.50 s a work. A save must not have grown by that."""
    user, headers = owner
    slow = 1.0

    def slow_bake(svg, scale):
        time.sleep(slow)
        return rasterize(svg, thumbs_db.width_for_scale(scale))

    monkeypatch.setattr(thumbnails, "bake", slow_bake)

    started = time.monotonic()
    response = client.post(
        "/api/history",
        headers=headers,
        json={"input": "a slow bake", "ddl": None, "score": {"instructions": []}, "at": int(time.time() * 1000)},
    )
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < slow / 2, f"the save waited {elapsed:.2f}s for a {slow:.2f}s bake"


# ── T-5 ─────────────────────────────────────────────────────────────────────
def test_the_thumbnail_is_served_as_a_png_that_may_be_cached(owner):
    user, headers = owner
    item = save_work(user)
    bake_for(item)

    response = client.get(f"/api/history/{item['id']}/thumb", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == rasterize(SQUARE_SVG, 256)
    etag = response.headers["etag"]
    assert etag
    assert "immutable" in response.headers["cache-control"]

    again = client.get(
        f"/api/history/{item['id']}/thumb",
        headers={**headers, "If-None-Match": etag},
    )
    assert again.status_code == 304
    assert again.headers["etag"] == etag

    # The ETag names the picture, so the two sizes of one work do not share one.
    bake_for(item, 2)
    hidpi = client.get(f"/api/history/{item['id']}/thumb?scale=2", headers=headers)
    assert hidpi.status_code == 200
    assert hidpi.headers["etag"] != etag


# ── T-6 ─────────────────────────────────────────────────────────────────────
def test_a_work_with_no_thumbnail_answers_404(owner):
    user, headers = owner
    item = save_work(user)

    response = client.get(f"/api/history/{item['id']}/thumb", headers=headers)
    assert response.status_code == 404
    assert response.content != b""


# ── T-7 ─────────────────────────────────────────────────────────────────────
def test_a_strangers_work_is_not_reachable(owner, stranger):
    user, _ = owner
    _, stranger_headers = stranger
    item = save_work(user)
    bake_for(item)

    response = client.get(f"/api/history/{item['id']}/thumb", headers=stranger_headers)
    # 404 rather than 403, the same answer the rest of the history group gives:
    # saying "forbidden" would confirm the work exists.
    assert response.status_code == 404


def test_the_thumbnail_needs_a_session_at_all(owner):
    user, _ = owner
    item = save_work(user)
    bake_for(item)

    assert client.get(f"/api/history/{item['id']}/thumb").status_code == 401


# ── T-8 ─────────────────────────────────────────────────────────────────────
def test_a_thumbnail_baked_from_a_different_svg_is_stale(owner):
    user, _ = owner
    item = save_work(user)
    bake_for(item)
    assert not [t for t in thumbnails.stale_targets((1,)) if t[0] == item["id"]]

    # The work's SVG moves on; the stored thumbnail was baked from the old one.
    thumbs_db.put_thumb(item["id"], 1, b"stale bytes", "a-different-hash")
    stale = [t for t in thumbnails.stale_targets((1,)) if t[0] == item["id"]]
    assert stale, "a thumbnail whose source hash disagrees must be rebuilt"

    thumbs_db.delete_for_history([item["id"]])
    missing = [t for t in thumbnails.stale_targets((1,)) if t[0] == item["id"]]
    assert missing, "a work with no thumbnail at all must be rebuilt"


# ── T-9 ─────────────────────────────────────────────────────────────────────
def test_the_old_thumbnail_is_served_while_it_is_being_rebuilt(owner, monkeypatch, rebuild_in_process):
    user, headers = owner
    item = save_work(user)
    bake_for(item)
    original = thumbs_db.get_thumb(item["id"], 1)["png"]
    # Make it stale so the rebuild has something to do for this work.
    thumbs_db.put_thumb(item["id"], 1, original, "a-different-hash")

    holding = threading.Event()
    released = threading.Event()

    # The rebuild rasterizes in child processes now, which monkeypatch cannot
    # reach; the rebuild_in_process fixture runs it here so this bake can be
    # held open. Bind the real one first -- `rasterize` below looks the name up
    # at call time, so calling it after the patch would call this back.
    from inku_analysis import rasterizer

    real_svg_to_png = rasterizer.svg_to_png

    def blocking_bake(svg, *, width=None, height=None):
        holding.set()
        released.wait(timeout=10)
        return real_svg_to_png(svg, width=width, height=height)

    monkeypatch.setattr(rasterizer, "svg_to_png", blocking_bake)
    # Only this work. What is being watched is that a rebuild replaces rather
    # than clears, which one work shows; enumerating every work in the test
    # database would bake all of them behind a blocking rasterizer.
    monkeypatch.setattr(
        thumbnails._db, "history_render_hashes", lambda: [(item["id"], item["render_hash"])]
    )
    # The parallelism is the stored setting's now, not the caller's.
    db.update_thumbnail_settings(db.get_thumbnail_settings()['hidpi'], 1)
    thumbnails.start_rebuild()
    assert holding.wait(timeout=10), "the rebuild never started baking"

    try:
        during = client.get(f"/api/history/{item['id']}/thumb", headers=headers)
        assert during.status_code == 200, "a rebuild must not blank a thumbnail"
        assert during.content == original
    finally:
        released.set()
        for _ in range(100):
            if not thumbnails.rebuild_progress()["running"]:
                break
            time.sleep(0.05)

    after = client.get(f"/api/history/{item['id']}/thumb", headers=headers)
    assert after.status_code == 200
    assert thumbs_db.get_thumb(item["id"], 1)["source_render_hash"] == item["render_hash"]


# ── T-10 ────────────────────────────────────────────────────────────────────
def test_hidpi_adds_the_second_size_and_turning_it_off_removes_only_that(owner, admin_headers):
    user, _ = owner
    item = save_work(user)

    assert thumbnails.active_scales() == (1,)
    db.update_thumbnail_settings(True, db.get_thumbnail_settings()['workers'])
    assert thumbnails.active_scales() == (1, 2)

    bake_for(item, 1)
    bake_for(item, 2)
    assert thumbs_db.get_thumb(item["id"], 2) is not None
    # The second size has to actually be larger, or HiDPI is a switch that
    # doubles the stored bytes and changes nothing on screen.
    one = png_size(thumbs_db.get_thumb(item["id"], 1)["png"])
    two = png_size(thumbs_db.get_thumb(item["id"], 2)["png"])
    assert two[0] == one[0] * 2 and two[1] == one[1] * 2

    off = client.put("/api/settings/thumbnails", headers=admin_headers, json={"hidpi": False})
    assert off.status_code == 200
    assert off.json()["hidpi"] is False
    assert thumbs_db.get_thumb(item["id"], 2) is None, "turning HiDPI off must drop scale 2"
    assert thumbs_db.get_thumb(item["id"], 1) is not None, "scale 1 is what the listing draws"


# ── T-11 ────────────────────────────────────────────────────────────────────
def test_losing_the_thumbnail_store_leaves_the_canonical_db_whole(owner):
    user, headers = owner
    item = save_work(user, IMPOSTOR_SVG)
    bake_for(item)

    # What "delete thumbs.db" amounts to for a store that is already open.
    thumbs_db.Base.metadata.drop_all(thumbs_db.engine)
    thumbs_db.init_thumbs_db()

    listing = client.get("/api/history?limit=10", headers=headers)
    assert listing.status_code == 200
    mine = [it for it in listing.json()["items"] if it["id"] == item["id"]]
    assert mine, "the work is still listed"
    assert mine[0]["svg"] == IMPOSTOR_SVG, "and the listing can still draw it itself"
    assert client.get(f"/api/history/{item['id']}/thumb", headers=headers).status_code == 404


# ── T-13 ────────────────────────────────────────────────────────────────────
def test_the_listing_still_carries_the_drawings_by_default(owner):
    user, headers = owner
    item = save_work(user, IMPOSTOR_SVG)

    listing = client.get("/api/history?limit=10", headers=headers)
    assert listing.status_code == 200
    mine = [it for it in listing.json()["items"] if it["id"] == item["id"]]
    assert mine and mine[0]["svg"] == IMPOSTOR_SVG, (
        "a caller that writes nothing must get what it always got"
    )


# ── T-14 ────────────────────────────────────────────────────────────────────
def test_asking_without_the_drawings_empties_the_key_but_keeps_it(owner):
    user, headers = owner
    item = save_work(user, IMPOSTOR_SVG)

    listing = client.get("/api/history?limit=10&include_svg=false", headers=headers)
    assert listing.status_code == 200
    mine = [it for it in listing.json()["items"] if it["id"] == item["id"]]
    assert mine
    # The key stays. Removing it would make "no picture asked for" and "a server
    # too old to have been asked" the same shape on the wire.
    assert "svg" in mine[0]
    assert mine[0]["svg"] == ""

    # Nothing else about the work is withheld: the client still needs the
    # metadata to draw the listing and to name the thumbnail's source.
    assert mine[0]["id"] == item["id"]
    assert "render_hash" in mine[0]


def test_the_listing_shrinks_by_the_weight_of_the_drawings(owner):
    user, headers = owner
    for _ in range(3):
        save_work(user, IMPOSTOR_SVG)

    with_svg = client.get("/api/history?limit=100", headers=headers)
    without = client.get("/api/history?limit=100&include_svg=false", headers=headers)
    assert with_svg.status_code == 200 and without.status_code == 200
    assert len(without.content) < len(with_svg.content), (
        "the flag has to actually take the pictures off the wire"
    )


# ── T-15 ────────────────────────────────────────────────────────────────────
# The command line reads the listing's `svg` and writes it to a file, then
# rasterizes that file (`cli.py`, the export path). An empty string is not an
# error there: it writes a 0-byte drawing and a blank PNG and reports success.
# So the senders that never name `include_svg` are the ones that would break in
# silence, and what protects them is the server's default -- which is exactly
# what this pair of assertions binds together.
#
# Keyed to the DIRECTORY, matching `test_cli_sender_census.py`: `cli/` is not on
# the pentala sync path, so the whole tree is absent on the deployed server.
CLI_TREE = pathlib.Path(__file__).resolve().parents[2] / "cli"
CLI_SOURCE = CLI_TREE / "src/inku_cli/cli.py"

cli_tree_only = pytest.mark.skipif(
    not CLI_TREE.is_dir(),
    reason="cli/ is not synced to the server; this gate runs where the tree exists",
)


def _history_senders() -> list[set[str]]:
    """The literal query keys of every `GET /api/history` call in the CLI.

    Read as text and parsed with `ast` rather than imported: the CLI lives in
    its own virtualenv, and what is being checked is which literal keys each
    sender names.
    """
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    senders: list[set[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "request"):
            continue
        args = [a for a in node.args if isinstance(a, ast.Constant)]
        if len(args) < 2 or args[0].value != "GET" or args[1].value != "/api/history":
            continue
        query = next(
            (kw.value for kw in node.keywords if kw.arg == "query"),
            None,
        )
        keys: set[str] = set()
        if isinstance(query, ast.Dict):
            keys = {k.value for k in query.keys if isinstance(k, ast.Constant)}
        senders.append(keys)
    return senders


@cli_tree_only
def test_the_command_line_still_receives_the_drawings_it_never_asks_for(owner):
    user, headers = owner
    item = save_work(user, IMPOSTOR_SVG)

    senders = _history_senders()
    assert senders, "found no GET /api/history sender in the CLI; the parse is wrong"
    quiet = [keys for keys in senders if "include_svg" not in keys]
    # If this ever becomes empty the gate has stopped measuring anything, and the
    # census below is where the change has to be argued instead.
    assert quiet, (
        "every CLI sender now names include_svg; this gate is vacuous -- move it "
        "or state which sender is relied upon to stay quiet"
    )

    # What a quiet sender puts on the wire, and what it must get back.
    listing = client.get("/api/history?limit=100", headers=headers)
    assert listing.status_code == 200
    mine = [it for it in listing.json()["items"] if it["id"] == item["id"]]
    assert mine and mine[0]["svg"] == IMPOSTOR_SVG, (
        f"{len(quiet)} CLI sender(s) name no include_svg and would write an empty "
        "drawing without saying so"
    )
