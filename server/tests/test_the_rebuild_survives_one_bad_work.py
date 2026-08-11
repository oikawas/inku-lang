"""The rebuild bakes in child processes and one bad work does not end the run.

Two defects, measured in production on 2026-08-11 at v2.12.4 / Build 882:

I-210 -- a rebuild of 2,917 works stopped at 481 and reported `running: False`
with `failed: 0` and a `finished_at`. One work raised inside `pool.map`, the
exception came out at the consuming side, the outer `except` logged it, and the
`finally` marked the run finished. Nothing in the status said 2,436 works had
never been attempted, and the listing shows nothing for a work with neither a
thumbnail nor an SVG on the wire.

I-211 -- the `workers` knob did nothing, because `resvg_py` holds the GIL for
the whole rasterization. Twelve bakes took 10.08 / 10.36 / 11.49 s at 1 / 2 / 6
threads, and the eight-core server ran one core at 99.4% with seven idle. The
project's own "six ways, about eight times" came from `rasterize_batch`, which
runs one child process per file.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

import pytest

from inku_server import db
from inku_server import thumbs_db
from inku_server.api import app as _app  # noqa: F401  -- importing it creates the schema
from inku_server.api_core import thumbnails

SQUARE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">'
    '<rect width="1000" height="1000" fill="#8d7f73"/></svg>'
)


def _make_user(prefix: str) -> tuple[dict, dict]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"{prefix}-{suffix}")
    user = db.add_user(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    return user, group


@pytest.fixture
def works():
    thumbs_db.init_thumbs_db()
    user, group = _make_user("rebuild-gate")
    made = [
        db.add_item({
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "input": "rebuild gate",
            "ddl": None,
            "score": {"instructions": []},
            "svg": SQUARE_SVG,
            "at": int(time.time() * 1000),
        })
        for _ in range(4)
    ]
    yield made
    db.delete_user(user["id"], cascade=True)
    db.delete_user_group(group["id"])


def _targets_for(works: list[dict]) -> list[tuple[str, str | None, int]]:
    """Only these works, so another test's leftovers cannot change the counts."""
    mine = {work["id"] for work in works}
    return [target for target in thumbnails.stale_targets((1,)) if target[0] in mine]


# ── T-R1 ────────────────────────────────────────────────────────────────────
def test_one_work_that_cannot_be_baked_does_not_end_the_run(works, monkeypatch, rebuild_in_process):
    targets = _targets_for(works)
    assert len(targets) == 4, "the four works must all need a thumbnail for this to measure anything"
    doomed = targets[1][0]

    # Perturbing the rasterizer, not the test: the point is a work whose bake
    # raises where the rebuild calls it, exactly as the production failure did.
    real = thumbnails.svg_to_png if hasattr(thumbnails, "svg_to_png") else None
    assert real is None, "svg_to_png is imported inside the worker; keep it that way"

    from inku_analysis import rasterizer

    original = rasterizer.svg_to_png
    order = {work["id"]: n for n, work in enumerate(works)}

    def sometimes_raises(svg, *, width=None, height=None):
        # The doomed work is told apart by its position in the batch, since the
        # SVG is identical; the pool call carries no id, so the count does.
        sometimes_raises.seen += 1
        if sometimes_raises.seen == order[doomed] + 1:
            raise RuntimeError("this work cannot be rasterized")
        return original(svg, width=width, height=height)

    sometimes_raises.seen = 0
    monkeypatch.setattr(rasterizer, "svg_to_png", sometimes_raises)
    # In-process, so the perturbation is visible: the gate below measures the
    # guard around each result, which is where the run used to die.

    thumbnails._rebuild.begin(len(targets), 2)
    thumbnails._rebuild_worker(targets, 2)
    progress = thumbnails.rebuild_progress()

    assert progress["done"] == 4, "every target must be attempted, not just the ones before the bad one"
    assert progress["failed"] == 1, "the work that raised is counted, once"
    assert progress["built"] == 3, "the other three are baked"
    stored = thumbs_db.stored_hashes(1)
    for work in works:
        if work["id"] == doomed:
            assert work["id"] not in stored
        else:
            assert work["id"] in stored, "a work after the bad one must still be baked"


# ── T-R2 ────────────────────────────────────────────────────────────────────
def test_a_run_that_stops_short_says_so():
    progress = thumbnails.RebuildProgress()
    assert progress.begin(10, 2)
    for _ in range(4):
        progress.record(True)
    progress.end()

    snapshot = progress.snapshot()
    assert snapshot["running"] is False
    assert snapshot["failed"] == 0, "the shape the production failure had: nothing looked wrong"
    assert snapshot["ended_short"] is True, (
        "a run that stopped with work left has to say so; `failed: 0` and "
        "`running: False` are what a complete run looks like too"
    )

    whole = thumbnails.RebuildProgress()
    assert whole.begin(3, 1)
    for _ in range(3):
        whole.record(True)
    whole.end()
    assert whole.snapshot()["ended_short"] is False, "a run that finished must not be flagged"


# ── T-R3 ────────────────────────────────────────────────────────────────────
def test_the_rasterizing_leaves_this_process_and_the_writing_does_not(works, monkeypatch):
    targets = _targets_for(works)
    assert targets, "nothing to bake means nothing is being measured"

    kinds: list[type] = []
    stores: list[str] = []
    real_pool = thumbnails.ProcessPoolExecutor

    class Recording(real_pool):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            kinds.append(real_pool)
            super().__init__(*args, **kwargs)

        def submit(self, fn, /, *args, **kwargs):
            # What crosses to a child must not be able to reach the database:
            # SQLite has one writer here, and the storing stays on this side.
            assert fn.__module__ == "inku_analysis.rasterizer", (
                f"the pool was handed {fn.__module__}.{fn.__name__}; only the "
                "rasterizing may leave this process"
            )
            return super().submit(fn, *args, **kwargs)

    original_put = thumbs_db.put_thumb

    def recording_put(history_id, scale, png, render_hash):
        stores.append(history_id)
        return original_put(history_id, scale, png, render_hash)

    monkeypatch.setattr(thumbnails, "ProcessPoolExecutor", Recording)
    monkeypatch.setattr(thumbs_db, "put_thumb", recording_put)
    monkeypatch.setattr(thumbnails._thumbs, "put_thumb", recording_put)

    thumbnails._rebuild.begin(len(targets), 2)
    thumbnails._rebuild_worker(targets, 2)

    assert kinds == [ProcessPoolExecutor], (
        "the bakes have to run in child processes: resvg_py holds the GIL, so a "
        "thread pool finished twelve bakes in 11.49 s against one thread's 10.08 s"
    )
    assert sorted(stores) == sorted(work["id"] for work in works), (
        "every thumbnail must be written from this process"
    )


# ── T-R4 ────────────────────────────────────────────────────────────────────
def test_a_broken_pool_does_not_end_the_run(works, monkeypatch, rebuild_in_process):
    """The other side of the same pool.

    A killed child -- the first thing a memory-capped container does -- breaks
    the pool, and then handing over the next work raises just as taking a result
    back does. The guard on the taking side was I-210; this is the offering one.
    """
    targets = _targets_for(works)
    assert len(targets) == 4

    from inku_analysis import rasterizer

    original = rasterizer.svg_to_png
    state = {"handed": 0}

    class BreaksAfterOne(thumbnails.ProcessPoolExecutor):
        def submit(self, fn, /, *args, **kwargs):
            state["handed"] += 1
            if state["handed"] > 1:
                raise BrokenProcessPool("a child was killed")
            return super().submit(fn, *args, **kwargs)

    monkeypatch.setattr(rasterizer, "svg_to_png", original)
    monkeypatch.setattr(thumbnails, "ProcessPoolExecutor", BreaksAfterOne)

    thumbnails._rebuild.begin(len(targets), 2)
    thumbnails._rebuild_worker(targets, 2)
    progress = thumbnails.rebuild_progress()

    assert progress["done"] == 4, "a broken pool must not leave works unattempted"
    assert progress["built"] == 1, "only the work handed over before the break is baked"
    assert progress["failed"] == 3, "the three that could not be handed over are counted"
    assert progress["ended_short"] is False, "the run reached the end of its list"


# ── T-S1 ────────────────────────────────────────────────────────────────────
def test_the_parallelism_comes_from_the_stored_setting(works, monkeypatch, rebuild_in_process):
    asked: list[int] = []
    real_pool = thumbnails.ProcessPoolExecutor

    class Recording(real_pool):
        def __init__(self, *args, max_workers=None, **kwargs):
            asked.append(max_workers)
            super().__init__(*args, max_workers=max_workers, **kwargs)

    monkeypatch.setattr(thumbnails, "ProcessPoolExecutor", Recording)
    before = db.get_thumbnail_settings()
    try:
        db.update_thumbnail_settings(before["hidpi"], 7)
        thumbnails.start_rebuild()
        for _ in range(200):
            if not thumbnails.rebuild_progress()["running"]:
                break
            time.sleep(0.05)
    finally:
        db.update_thumbnail_settings(before["hidpi"], before["workers"])

    assert asked == [7], f"the pool was built with {asked}, not the stored 7"
    assert thumbnails.rebuild_progress()["workers"] == 7


# ── T-S2 ────────────────────────────────────────────────────────────────────
def test_the_rebuild_request_carries_no_parallelism():
    """One place decides it. The request is not a second one."""
    from fastapi.testclient import TestClient

    from inku_server.api import app
    from inku_server.api_core.routers import settings as settings_router

    assert not hasattr(settings_router, "ThumbnailRebuildBody"), (
        "the request body is gone; a second place to set the parallelism is not"
    )
    spec = TestClient(app).app.openapi()
    operation = spec["paths"]["/api/settings/thumbnails/rebuild"]["post"]
    assert "requestBody" not in operation, (
        "the rebuild endpoint must take no body, so no caller can name a worker count"
    )
    put = spec["paths"]["/api/settings/thumbnails"]["put"]
    schema = put["requestBody"]["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]
    assert "workers" in spec["components"]["schemas"][schema]["properties"], (
        "the setting is where it is entered"
    )
