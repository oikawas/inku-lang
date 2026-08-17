"""Baking the listing's thumbnails.

A thumbnail is a rasterization of a work's stored SVG, nothing more: the engine
is not run, no Score is re-read, and the picture is the one that was saved. A
work drawn by engine 2 becomes a PNG of the engine 2 picture.

Baking is off the request path. Rasterizing one work measured 0.50 s on 21 of
today's works, which is half a second nobody should wait for after pressing
draw, so a save submits the job and returns.

Off the request path is not the same as out of the way. resvg_py holds the GIL
for the whole rasterization, so while a save baked here nothing else in this
process ran: one request waited 4,245 ms during the save of a work with 18,874
filter references, against 243 ms for the same work rendered without a bake
(measured 2026-08-17, ledger I-284). Both paths therefore bake in a child and
write in this process -- the save through the resident pool below, the rebuild
through one it makes and drops per run.
"""
from __future__ import annotations

import logging
import multiprocessing
import time
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from threading import Lock

from .. import db as _db
from .. import thumbs_db as _thumbs
from .state import _THUMB_WORKERS, _increment_thumb_stat, _thumb_executor, _thumb_slots

_logger = logging.getLogger("inku.thumbs")

#: How many works the rebuild reads from the canonical DB at a time. One SVG is
#: about a megabyte; the whole table at once is what this change exists to stop.
_REBUILD_BATCH = 32

#: The pool that bakes freshly saved works. Built on first use and kept.
#:
#: ⚠ Deliberately not built at import. A test replaces the factory below to bake
#: in this process instead of spawning a child per save, and a pool that already
#: exists when the replacement happens is the one that answers.
_bake_pool: "ProcessPoolExecutor | None" = None

_bake_pool_lock = Lock()

#: True once the application has folded the pool. Without it, a save arriving
#: during shutdown would rebuild the pool that was just closed, through the
#: broken-pool recovery below.
_bake_pool_closed = False


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
    """Bake and store one thumbnail here, in this process.

    False when nothing was written. Neither production path calls this: it holds
    the GIL for the length of the bake, which is what I-284 moved the save off.
    It stays as the in-process form the gates arrange a single bake with, and as
    what a perturbation puts back to show that the child pool is load-bearing.
    """
    png = bake(svg, scale)
    if png is None:
        return False
    _thumbs.put_thumb(history_id, scale, png, render_hash)
    return True


# ── Baking in a child ───────────────────────────────────────────────────────
# Both the save path and the rebuild bake this way: only the rasterizing crosses
# to a child process, and the storing stays here, where SQLite has one
# connection and one writer.


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


def _new_bake_pool() -> ProcessPoolExecutor:
    """The pool a save's bake goes to.

    spawn, not fork: this runs inside a threaded uvicorn process, and a forked
    child inherits its locks. The child imports the rasterizer and nothing of
    the server -- which is why svg_to_png is what crosses, with the scale
    already resolved to a width on this side.

    INKU_THUMBNAIL_WORKERS decides the width of it, and only starts meaning
    something here: while the bake ran in threads, resvg_py held the GIL for the
    whole rasterization, so any number of them finished one at a time (I-211).
    """
    context = multiprocessing.get_context("spawn")
    return ProcessPoolExecutor(max_workers=max(1, _THUMB_WORKERS), mp_context=context)


def _bake_pool_now() -> "ProcessPoolExecutor | None":
    """The living pool, built on first use. None once the app has folded it."""
    global _bake_pool

    with _bake_pool_lock:
        if _bake_pool_closed:
            return None
        if _bake_pool is None:
            _bake_pool = _new_bake_pool()
        return _bake_pool


def _discard_bake_pool(broken: ProcessPoolExecutor) -> None:
    """Drop a pool that can no longer take work, if it is still the current one."""
    global _bake_pool

    with _bake_pool_lock:
        if _bake_pool is broken:
            _bake_pool = None
    broken.shutdown(wait=False)


def shutdown_bake_pool() -> None:
    """Stop the children that bake saved works, and do not start more.

    The rebuild's pool lives inside one `with` and closes itself. This one
    outlives every request, so something has to close it: children left running
    outlive the server that spawned them.

    Not `cancel_futures=True`. A cancelled future raises CancelledError, which
    has been a BaseException since Python 3.8, so the `except Exception` in
    _store_result -- shared with the rebuild -- would not catch it. The bakes
    already handed over are short; letting them finish costs less than widening
    a guard two callers depend on.
    """
    global _bake_pool, _bake_pool_closed

    with _bake_pool_lock:
        pool, _bake_pool = _bake_pool, None
        _bake_pool_closed = True
    if pool is not None:
        pool.shutdown(wait=False)


def _offer_a_saved_work(svg: str, scale: int) -> "Future[bytes] | None":
    """Hand one save's bake over, rebuilding the pool once if it is broken.

    The rebuild makes and drops its pool inside a single run, so a killed child
    costs that run and no more. A resident pool has no such end: without this,
    the first killed child would leave every later save without a thumbnail for
    the life of the process.
    """
    pool = _bake_pool_now()
    if pool is None:
        return None
    future = _offer(pool, svg, scale)
    if future is not None:
        return future
    _discard_bake_pool(pool)
    fresh = _bake_pool_now()
    return _offer(fresh, svg, scale) if fresh is not None else None


def _bake_in_a_child(history_id: str, svg: str, render_hash: str | None, scale: int) -> bool | None:
    """Bake one scale in a child and write the result here.

    True when a thumbnail was written, False when there was none to write, and
    None when the pool could not take the work even after being rebuilt.
    """
    if not svg:
        return False
    future = _offer_a_saved_work(svg, scale)
    if future is None:
        return None
    return _store_result(history_id, render_hash, scale, future)


def _run_thumbnail_build(item: dict) -> None:
    try:
        history_id = str(item.get("id") or "")
        svg = str(item.get("svg") or "")
        render_hash = item.get("render_hash")
        wrote = False
        broken = False
        for scale in active_scales():
            written = _bake_in_a_child(history_id, svg, render_hash, scale)
            if written is None:
                broken = True
                break
            wrote = written or wrote
        # One count per work, never two: a work the pool would not take is
        # `failed`, and one that produced nothing to store is `unavailable`.
        if broken:
            _increment_thumb_stat("failed")
        else:
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
