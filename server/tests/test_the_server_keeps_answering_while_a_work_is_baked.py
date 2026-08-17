"""Contract I-284: a save's bake leaves this process, so the API keeps answering.

resvg_py holds the GIL for the whole rasterization, so while a saved work baked
in this process nothing else in it ran. Measured 2026-08-17 on a work with
18,874 filter references: one request waited 4,245 ms during the save, against
243 ms for the same work rendered without a bake. The median barely moved --
that 16x belongs to the drawing, which is plain Python and yields -- so what
these gates watch for is one request being held, not the average.

The rebuild already worked this way (I-211); its last line said the save path
was out of scope and still baked in threads. This closes that line.

T-215 the round trip still works        T-219 lives in the thumbnail contract
T-216 the rasterizing leaves            T-220 another thread keeps running
T-217 the writing does not              T-221 closing the app closes the pool
T-218 a broken pool is rebuilt          T-222 tests bake in this process
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server import thumbs_db
from inku_server.api import _lifespan, app
from inku_server.api_core import thumbnails

client = TestClient(app)


#: What the module held before any fixture ran. A pool built at import is
#: already there when a test replaces the factory, so the replacement never
#: reaches the thing that bakes -- which is what T-222 asserts is not the case.
_POOL_AT_IMPORT = thumbnails._bake_pool


SQUARE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">'
    '<rect width="1000" height="1000" fill="#8d7f73"/></svg>'
)


def _heavy_svg(marks: int = 600) -> str:
    """An SVG whose bake lasts long enough to watch another thread run.

    600 blurred strokes rasterize in about 0.8 s at 256 px on this Mac
    (measured 2026-08-17: 200 marks 0.34 s, 500 marks 0.67 s, 1000 marks
    1.19 s). Long enough to count turns against, short enough for a suite.
    """
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">',
        '<defs><filter id="b"><feGaussianBlur stdDeviation="3"/></filter></defs>',
    ]
    for index in range(marks):
        x = (index * 37) % 1000
        y = (index * 53) % 1000
        parts.append(
            f'<path d="M{x} {y} q 40 -60 80 0 t 80 0" fill="none" stroke="#3a3a3a" '
            f'stroke-width="6" filter="url(#b)" opacity="0.6"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


@pytest.fixture
def owner():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"bake-owner-{suffix}")
    user = db.add_user(
        username=f"bake-owner-{suffix}",
        email=f"bake-owner-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield user, {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


@pytest.fixture(autouse=True)
def _thumb_store():
    thumbs_db.init_thumbs_db()
    yield


def _stored_work(user: dict, svg: str = SQUARE_SVG) -> dict:
    """A saved work, without going through the render path."""
    return db.add_item({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "input": "bake gate",
        "ddl": None,
        "score": {"instructions": []},
        "svg": svg,
        "at": int(time.time() * 1000),
    })


def _wait_for_thumbnail(history_id: str, timeout: float = 60.0) -> dict:
    """Block until the bake has landed in the store, or say it never did."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = thumbs_db.get_thumb(history_id, 1)
        if row is not None:
            return row
        time.sleep(0.02)
    raise AssertionError(f"no thumbnail was ever written for {history_id}")


def _bake(user: dict, svg: str = SQUARE_SVG) -> dict:
    """Put one work through the production entry point and wait for its picture."""
    item = _stored_work(user, svg)
    assert thumbnails.submit_thumbnail_build(item), "the work was not accepted for baking"
    _wait_for_thumbnail(item["id"])
    return item


# ── T-215 ───────────────────────────────────────────────────────────────────
def test_a_saved_work_still_ends_up_with_its_thumbnail(owner):
    """The round trip, through the route rather than the function."""
    user, headers = owner

    response = client.post(
        "/api/history",
        headers=headers,
        json={"input": "a baked work", "ddl": None, "score": {"instructions": []},
              "at": int(time.time() * 1000)},
    )
    assert response.status_code == 200
    item = response.json()
    _wait_for_thumbnail(item["id"])

    served = client.get(f"/api/history/{item['id']}/thumb", headers=headers)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content[:8] == b"\x89PNG\r\n\x1a\n"


# ── T-216 ───────────────────────────────────────────────────────────────────
@pytest.mark.child_bake_pool
def test_the_rasterizing_of_a_saved_work_leaves_this_process(owner, monkeypatch):
    """Set the way the rebuild's own gate is set: watch what gets built and sent."""
    user, _ = owner
    kinds: list[type] = []
    crossed: list[str] = []
    real_pool = thumbnails.ProcessPoolExecutor

    class Recording(real_pool):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            kinds.append(real_pool)
            super().__init__(*args, **kwargs)

        def submit(self, fn, /, *args, **kwargs):
            crossed.append(f"{fn.__module__}.{fn.__name__}")
            return super().submit(fn, *args, **kwargs)

    monkeypatch.setattr(thumbnails, "ProcessPoolExecutor", Recording)

    _bake(user)

    assert kinds == [ProcessPoolExecutor], (
        "a save's bake has to run in a child process: resvg_py holds the GIL for "
        "the whole rasterization, and one request waited 4,245 ms behind one"
    )
    assert crossed == ["inku_analysis.rasterizer.svg_to_png"], (
        f"the pool was handed {crossed}; only the rasterizing may leave this "
        "process, and it must not be able to reach the database"
    )


# ── T-217 ───────────────────────────────────────────────────────────────────
@pytest.mark.child_bake_pool
def test_the_writing_of_a_saved_work_stays_in_this_process(owner, monkeypatch):
    """The other half of T-216: SQLite has one connection and one writer here.

    Asserting the pid alone would not measure the child at all -- baking in a
    thread of this process writes from this pid too. So this also asks that the
    bytes came back from the pool.
    """
    user, _ = owner
    handed_over: list[object] = []
    writing_pids: list[int] = []
    real_pool = thumbnails.ProcessPoolExecutor
    original_put = thumbs_db.put_thumb

    class Counting(real_pool):  # type: ignore[misc, valid-type]
        def submit(self, fn, /, *args, **kwargs):
            future = super().submit(fn, *args, **kwargs)
            handed_over.append(future)
            return future

    def recording_put(history_id, scale, png, render_hash):
        writing_pids.append(os.getpid())
        return original_put(history_id, scale, png, render_hash)

    monkeypatch.setattr(thumbnails, "ProcessPoolExecutor", Counting)
    monkeypatch.setattr(thumbs_db, "put_thumb", recording_put)
    monkeypatch.setattr(thumbnails._thumbs, "put_thumb", recording_put)

    _bake(user)

    assert handed_over, (
        "the pool was never asked to bake, so nothing crossed to a child and "
        "there is no claim left to make about where the writing happened"
    )
    assert writing_pids == [os.getpid()], (
        f"the thumbnail was written from {writing_pids} rather than from this "
        f"process ({os.getpid()})"
    )


# ── T-218 ───────────────────────────────────────────────────────────────────
def test_a_broken_pool_is_rebuilt_for_the_works_that_follow(owner):
    """A killed child breaks the pool for good, and this pool is not per-run.

    The rebuild makes and drops its pool inside one run, so that failure ends
    with the run. A resident pool would carry it for the life of the process:
    every later save would go without a thumbnail.
    """
    user, _ = owner
    _bake(user)

    broken = thumbnails._bake_pool
    assert broken is not None, "no pool was built, so nothing is being broken"
    broken.shutdown(wait=True)  # what a killed child leaves behind: submit raises

    first_after = _bake(user)
    second_after = _bake(user)

    assert thumbnails._bake_pool is not broken, "the dead pool is still the current one"
    assert thumbs_db.get_thumb(first_after["id"], 1) is not None
    assert thumbs_db.get_thumb(second_after["id"], 1) is not None


# ── T-220 ───────────────────────────────────────────────────────────────────
#: Turns of the plain-Python loop between two asks of the stopping condition.
#: Asking every turn would measure the asking.
_SPIN_BLOCK = 2000


def _count_turns_until(done, ceiling: float) -> tuple[int, float]:
    """Turn a plain Python loop and count, until `done(elapsed)` says stop."""
    turns = 0
    started = time.monotonic()
    while True:
        for _ in range(_SPIN_BLOCK):
            turns += 1
        elapsed = time.monotonic() - started
        if done(elapsed) or elapsed > ceiling:
            return turns, elapsed


@pytest.mark.child_bake_pool
def test_another_thread_keeps_running_while_a_work_bakes(owner, monkeypatch):
    """The whole point of the change, measured as turns rather than as seconds.

    Seconds do not survive a change of machine -- they moved 40% between rounds
    on this one -- so the gate compares two windows measured back to back in
    this test: turns taken while a child bakes, against turns taken with nothing
    running at all. On 2026-08-17 the starting tree gave 486 turns during a
    9.00 s in-process bake against 32,674 during 9.51 s of plain Python, a ratio
    of 1/67. A tenth is therefore far below what a child pool gives and far
    above what holding the GIL gives.
    """
    user, _ = owner
    baked = Event()
    original_put = thumbs_db.put_thumb

    def signalling_put(history_id, scale, png, render_hash):
        original_put(history_id, scale, png, render_hash)
        baked.set()

    monkeypatch.setattr(thumbnails._thumbs, "put_thumb", signalling_put)

    # Warm the pool first: the first bake pays for a spawn, and a spawn is not
    # a bake. What is being measured is the rasterizing.
    _bake(user)
    baked.clear()

    heavy = _stored_work(user, _heavy_svg())
    assert thumbnails.submit_thumbnail_build(heavy)
    turns_while_baking, baking_seconds = _count_turns_until(lambda _: baked.is_set(), 60.0)
    assert baked.is_set(), "the bake never finished, so nothing was measured"

    turns_when_idle, _ = _count_turns_until(lambda elapsed: elapsed >= baking_seconds, 60.0)

    assert turns_while_baking * 10 >= turns_when_idle, (
        f"this thread took {turns_while_baking:,} turns while a work baked and "
        f"{turns_when_idle:,} turns in the same {baking_seconds:.2f}s with nothing "
        "running: the bake is holding the interpreter, which is what a save "
        "stopped doing"
    )


# ── T-221 ───────────────────────────────────────────────────────────────────
def test_closing_the_application_closes_the_baking_pool(owner, monkeypatch):
    """Children that outlive the server are the server's fault."""
    monkeypatch.setenv("INKU_DB_BACKUP_SCHEDULER", "0")
    user, _ = owner
    _bake(user)

    pool = thumbnails._bake_pool
    assert pool is not None, "no pool was built, so nothing is being closed"

    async def open_and_close() -> None:
        async with _lifespan(app):
            pass

    asyncio.run(open_and_close())

    assert thumbnails._bake_pool is None, "the pool survived the application"
    with pytest.raises(RuntimeError):
        pool.submit(len, "the closed pool must not take work")


# ── T-222 ───────────────────────────────────────────────────────────────────
def test_the_suite_bakes_in_this_process_by_default(owner):
    """Otherwise every test that saves spawns a child, and patches miss the bake.

    Two claims, because either alone is satisfiable while the mechanism is
    broken: that the pool is not built until it is asked for -- a pool built at
    import is there before any replacement -- and that the pool a save actually
    used in this suite is not a process pool.
    """
    user, headers = owner
    assert _POOL_AT_IMPORT is None, (
        "the baking pool existed at import; a test that replaces the factory "
        "cannot reach a pool that was already built"
    )

    response = client.post(
        "/api/history",
        headers=headers,
        json={"input": "a work saved in a test", "ddl": None,
              "score": {"instructions": []}, "at": int(time.time() * 1000)},
    )
    assert response.status_code == 200
    _wait_for_thumbnail(response.json()["id"])

    pool = thumbnails._bake_pool
    assert pool is not None, "the save path never built a pool, so it never baked"
    assert not isinstance(pool, ProcessPoolExecutor), (
        "a test that saves spawned a child process; the default has to be an "
        "in-process pool, or a patched svg_to_png never reaches the bake"
    )
