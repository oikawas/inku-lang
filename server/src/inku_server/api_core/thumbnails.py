"""Baking the listing's thumbnails.

A thumbnail is a rasterization of a work's stored SVG, nothing more: the engine
is not run, no Score is re-read, and the picture is the one that was saved. A
work drawn by engine 2 becomes a PNG of the engine 2 picture.

Baking is off the request path. Rasterizing one work measured 0.50 s on 21 of
today's works, which is half a second nobody should wait for after pressing
draw, so a save submits the job and returns.
"""
from __future__ import annotations

import logging
import multiprocessing
import time
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from threading import Lock

from .. import db as _db
from .. import thumbs_db as _thumbs
from .state import _increment_thumb_stat, _thumb_executor, _thumb_slots

_logger = logging.getLogger("inku.thumbs")

#: How many works the rebuild reads from the canonical DB at a time. One SVG is
#: about a megabyte; the whole table at once is what this change exists to stop.
_REBUILD_BATCH = 32


def active_scales() -> tuple[int, ...]:
    """The scales that should exist for every work, given today's settings."""
    return (1, 2) if _db.get_thumbnail_settings()["hidpi"] else (1,)


def bake(svg: str, scale: int) -> bytes | None:
    """Rasterize one SVG. None when this installation has no rasterizer.

    Only the width is given, so the height follows the SVG's own viewBox and a
    work keeps its proportions -- a wide work becomes a wide thumbnail.
    """
    if not svg:
        return None
    from inku_analysis.rasterizer import RasterizerUnavailable, svg_to_png

    try:
        return svg_to_png(svg, width=_thumbs.width_for_scale(scale))
    except RasterizerUnavailable:
        # Not an error: a thumbnail is an optimization, and the listing falls
        # back to the SVG it already has when one is missing.
        _logger.warning("no SVG rasterizer is installed; skipped thumbnail")
        return None


def build_one(history_id: str, svg: str, render_hash: str | None, scale: int) -> bool:
    """Bake and store one thumbnail. False when nothing was written."""
    png = bake(svg, scale)
    if png is None:
        return False
    _thumbs.put_thumb(history_id, scale, png, render_hash)
    return True


def _run_thumbnail_build(item: dict) -> None:
    try:
        history_id = str(item.get("id") or "")
        svg = str(item.get("svg") or "")
        render_hash = item.get("render_hash")
        wrote = False
        for scale in active_scales():
            wrote = build_one(history_id, svg, render_hash, scale) or wrote
        _increment_thumb_stat("completed" if wrote else "unavailable")
    except Exception:
        _increment_thumb_stat("failed")
        _logger.exception("failed to build thumbnail: history_id=%s", item.get("id"))
    finally:
        _thumb_slots.release()


def submit_thumbnail_build(item: dict) -> bool:
    """Queue a freshly saved work for baking. Never blocks the caller.

    Deliberately not gated on output_save_settings: that switch governs writing
    a second copy of the artifacts to disk and has been off since 2026-05-04,
    while a thumbnail is how the listing draws. Reading it here would tie two
    unrelated decisions to one switch.
    """
    if not item.get("id") or not item.get("svg"):
        return False
    if not _thumb_slots.acquire(blocking=False):
        _increment_thumb_stat("skipped")
        _logger.warning("thumbnail queue is full; skipped: history_id=%s", item.get("id"))
        return False
    _increment_thumb_stat("submitted")
    try:
        _thumb_executor.submit(_run_thumbnail_build, item)
    except Exception:
        _increment_thumb_stat("failed")
        _thumb_slots.release()
        _logger.exception("failed to submit thumbnail job: history_id=%s", item.get("id"))
        return False
    return True


# ── Rebuild ─────────────────────────────────────────────────────────────────
# A production operation, not a one-off script: an administrator runs it from
# the settings screen while the server is serving.


def stale_targets(scales: tuple[int, ...]) -> list[tuple[str, str | None, int]]:
    """Works needing a thumbnail at each scale, and why they need one.

    Two cases, and only two: nothing stored at that scale, or something stored
    that was baked from a different SVG than the work holds now.
    """
    works = _db.history_render_hashes()
    targets: list[tuple[str, str | None, int]] = []
    for scale in scales:
        stored = _thumbs.stored_hashes(scale)
        for history_id, render_hash in works:
            if history_id not in stored or stored[history_id] != render_hash:
                targets.append((history_id, render_hash, scale))
    return targets


class RebuildProgress:
    """What a running rebuild has done so far, safe to read from a request."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.running = False
        self.total = 0
        self.done = 0
        self.built = 0
        self.failed = 0
        self.started_at: int | None = None
        self.finished_at: int | None = None
        self.workers = 0
        #: True when a run stopped with work left. Reported rather than inferred:
        #: `done < total` is only readable while the numbers of one run are still
        #: on show, and a reader who sees `running: False, failed: 0` otherwise
        #: has no way to tell a finished run from an abandoned one.
        self.ended_short = False

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "total": self.total,
                "done": self.done,
                "remaining": max(0, self.total - self.done),
                "built": self.built,
                "failed": self.failed,
                "ended_short": self.ended_short,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "workers": self.workers,
            }

    def begin(self, total: int, workers: int) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.total = total
            self.done = 0
            self.built = 0
            self.failed = 0
            self.started_at = int(time.time() * 1000)
            self.finished_at = None
            self.workers = workers
            self.ended_short = False
            return True

    def record(self, built: bool) -> None:
        with self._lock:
            self.done += 1
            if built:
                self.built += 1
            else:
                self.failed += 1

    def end(self) -> None:
        with self._lock:
            self.running = False
            self.finished_at = int(time.time() * 1000)
            self.ended_short = self.done < self.total


_rebuild = RebuildProgress()


def rebuild_progress() -> dict:
    return _rebuild.snapshot()


def _offer(pool: ProcessPoolExecutor, svg: str, scale: int) -> "Future[bytes] | None":
    """Hand one bake to the pool. Never raises; None means it was not accepted.

    Handing work over can fail as readily as doing it: once a child has been
    killed -- the first thing that happens when a container's memory is capped
    -- the pool is broken and every later submit raises. Outside this guard that
    ended the run, which is the shape I-210 was about, only reached through the
    other side of the same pool.
    """
    from inku_analysis.rasterizer import svg_to_png

    if not svg:
        return None
    try:
        return pool.submit(svg_to_png, svg, width=_thumbs.width_for_scale(scale))
    except Exception:
        _logger.exception("could not hand a thumbnail to the pool: scale=%s", scale)
        return None


def _store_result(history_id: str, render_hash: str | None, scale: int, future: "Future[bytes]") -> bool:
    """Take one bake back from a child and write it here. Never raises.

    A work that cannot be baked is one work: the rebuild has 2,917 of them and
    the run has to survive the bad one. Before this guard existed, a single
    raised work ended the whole run -- and because the caller marked the run
    finished either way, the status said `failed: 0` with 2,436 works never
    attempted.
    """
    from inku_analysis.rasterizer import RasterizerUnavailable

    try:
        png = future.result()
    except RasterizerUnavailable:
        # Not an error: a thumbnail is an optimization, and the listing falls
        # back to the SVG it already has when one is missing.
        _logger.warning("no SVG rasterizer is installed; skipped thumbnail")
        return False
    except Exception:
        _logger.exception("failed to bake thumbnail: history_id=%s scale=%s", history_id, scale)
        return False
    if not png:
        return False
    _thumbs.put_thumb(history_id, scale, png, render_hash)
    return True


def _rebuild_worker(targets: list[tuple[str, str | None, int]], workers: int) -> None:
    """Bake every target, keeping the old thumbnail readable until each is done.

    Nothing is deleted first. put_thumb() replaces a row in place, so a work
    that already has a thumbnail keeps serving it for the whole rebuild and
    swaps to the new one the moment it exists -- and because the ETag is made
    from the source hash, the swap is visible to a client that had cached it.

    The rasterizing happens in child processes and the storing happens here.
    Threads cannot do this work in parallel: resvg_py holds the GIL for the
    whole rasterization, so a pool of six threads finished twelve bakes in
    11.49 s against one thread's 10.08 s -- and on the eight-core server one
    core sat at 99.4% while seven were idle. Only the CPU crosses to a child;
    the SQLite writes stay in this process, where there is one connection and
    one writer.
    """
    try:
        by_id: dict[str, list[tuple[str | None, int]]] = {}
        for history_id, render_hash, scale in targets:
            by_id.setdefault(history_id, []).append((render_hash, scale))
        ids = list(by_id)
        # spawn, not fork: this runs inside a threaded uvicorn process, and a
        # forked child inherits its locks. The child imports the rasterizer and
        # nothing of the server -- which is why svg_to_png is what crosses, with
        # the scale already resolved to a width on this side.
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=max(1, workers), mp_context=context) as pool:
            for start in range(0, len(ids), _REBUILD_BATCH):
                batch = ids[start:start + _REBUILD_BATCH]
                svgs = _db.history_svgs(batch)
                pending: list[tuple[str, str | None, int, "Future[bytes] | None"]] = []
                for history_id in batch:
                    svg = svgs.get(history_id, "")
                    for render_hash, scale in by_id[history_id]:
                        pending.append(
                            (history_id, render_hash, scale, _offer(pool, svg, scale))
                        )
                for history_id, render_hash, scale, future in pending:
                    built = (
                        _store_result(history_id, render_hash, scale, future)
                        if future is not None
                        else False
                    )
                    _rebuild.record(built)
    except Exception:
        _logger.exception("thumbnail rebuild failed")
    finally:
        _rebuild.end()


def start_rebuild() -> dict:
    """Begin a rebuild in the background. Returns the progress to report back.

    The parallelism comes from the stored setting rather than from the caller:
    nothing here reads the core count -- in a container the host's count is the
    wrong answer -- so the administrator enters it once and every rebuild uses
    the same number.
    """
    _thumbs.init_thumbs_db()
    settings = _db.get_thumbnail_settings()
    workers = int(settings["workers"])
    scales = active_scales()
    targets = stale_targets(scales)
    if not _rebuild.begin(len(targets), workers):
        return {"started": False, **_rebuild.snapshot()}
    if not targets:
        _rebuild.end()
        return {"started": True, **_rebuild.snapshot()}
    ThreadPoolExecutor(max_workers=1, thread_name_prefix="inku-rebuild-run").submit(
        _rebuild_worker, targets, workers
    )
    return {"started": True, **_rebuild.snapshot()}


def drop_hidpi() -> int:
    """Delete every scale-2 thumbnail, leaving scale 1 untouched."""
    return _thumbs.delete_scale(2)
