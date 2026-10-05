"""Retry a broken pool once without rasterizing or starting child processes."""
from __future__ import annotations

import base64
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from types import SimpleNamespace

import pytest

from inku_server import thumbs_db
from inku_server.api_core import thumbnails

# A fixed 1x1 PNG returned by the pool model; no rasterizer runs in these gates.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+a4XcAAAAASUVORK5CYII="
)
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>'


def arrange_pools(monkeypatch, failures: list[str | None]):
    pools = []
    offers = []

    def never_rasterize(*args, **kwargs):
        raise AssertionError("the pool model must not rasterize")

    monkeypatch.setattr("inku_analysis.rasterizer.svg_to_png", never_rasterize)

    class Pool:
        def __init__(self, *args, **kwargs):
            assert len(pools) < len(failures), "a third pool exceeds this work's retry budget"
            self.failure = failures[len(pools)]
            self.shutdowns = []
            pools.append(self)

        def submit(self, fn, svg, *, width):
            assert fn is never_rasterize
            assert svg == SVG
            assert width == 256
            offers.append(self)
            if self.failure == "submit":
                raise BrokenProcessPool("the child died before accepting the bake")
            future = Future()
            if self.failure == "result":
                future.set_exception(BrokenProcessPool("the child died after accepting the bake"))
            else:
                future.set_result(PNG)
            return future

        def shutdown(self, wait=True):
            self.shutdowns.append(wait)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.shutdown()

    monkeypatch.setattr(thumbnails, "_new_bake_pool", Pool)
    monkeypatch.setattr(thumbnails, "ProcessPoolExecutor", Pool)
    monkeypatch.setattr(thumbnails, "_rebuild", thumbnails.RebuildProgress())
    thumbs_db.init_thumbs_db()
    return pools, offers


@pytest.mark.parametrize("path", ["save", "rebuild"])
@pytest.mark.parametrize("first_failure", ["submit", "result"])
@pytest.mark.parametrize("retry_breaks", [False, True], ids=["recovers", "fails-twice"])
def test_a_broken_thumbnail_pool_retries_the_same_work_once(
    monkeypatch, caplog, path, first_failure, retry_breaks
):
    pools, offers = arrange_pools(
        monkeypatch, [first_failure, "result" if retry_breaks else None]
    )
    history_id = f"thumb-retry-{path}-{first_failure}-{retry_breaks}"
    stats = []
    releases = []
    if path == "save":
        monkeypatch.setattr(thumbnails, "active_scales", lambda: (1,))
        monkeypatch.setattr(thumbnails, "_increment_thumb_stat", stats.append)
        monkeypatch.setattr(thumbnails, "_thumb_slots", SimpleNamespace(release=lambda: releases.append(1)))
        thumbnails._run_thumbnail_build({"id": history_id, "svg": SVG, "render_hash": "source-hash"})
        assert stats == ["failed" if retry_breaks else "completed"]
        assert releases == [1]
    else:
        monkeypatch.setattr(thumbnails._db, "history_svgs", lambda ids: {history_id: SVG})
        assert thumbnails._rebuild.begin(1, 2)
        thumbnails._rebuild_worker([(history_id, "source-hash", 1)], 2)
        progress = thumbnails.rebuild_progress()
        assert progress["done"] == 1
        assert progress["failed"] == int(retry_breaks)
        assert progress["built"] == int(not retry_breaks)
        assert progress["running"] is False
        assert progress["ended_short"] is False

    assert len(pools) == 2
    assert offers == [pools[0], pools[1]], "only the original attempt and one retry"
    assert pools[0].shutdowns, "the broken pool must be retired"
    row = thumbs_db.get_thumb(history_id, 1)
    if retry_breaks:
        assert row is None
        assert sum(
            "failed to bake thumbnail after pool retry" in record.getMessage()
            for record in caplog.records
        ) == 1
    else:
        assert row is not None
        assert row["png"] == PNG
        assert row["source_render_hash"] == "source-hash"


def test_rebuild_reuses_the_fresh_pool_for_other_futures_from_the_broken_batch(monkeypatch):
    pools, offers = arrange_pools(monkeypatch, ["result", None])
    ids = ["thumb-retry-batch-first", "thumb-retry-batch-second"]
    monkeypatch.setattr(thumbnails._db, "history_svgs", lambda batch: dict.fromkeys(batch, SVG))
    assert thumbnails._rebuild.begin(2, 2)
    thumbnails._rebuild_worker([(history_id, "batch-hash", 1) for history_id in ids], 2)

    assert len(pools) == 2
    assert offers == [pools[0], pools[0], pools[1], pools[1]]
    progress = thumbnails.rebuild_progress()
    assert (progress["done"], progress["built"], progress["failed"]) == (2, 2, 0)
    assert progress["ended_short"] is False
    for history_id in ids:
        row = thumbs_db.get_thumb(history_id, 1)
        assert row is not None
        assert row["png"] == PNG
