"""Process-wide mutable state shared by the render, history and settings routers."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import BoundedSemaphore, Condition, Lock
from fastapi import HTTPException


_SAVE_WORKERS = max(1, int(os.getenv("INKU_OUTPUT_SAVE_WORKERS", "2")))


_SAVE_QUEUE_LIMIT = max(_SAVE_WORKERS, int(os.getenv("INKU_OUTPUT_SAVE_QUEUE_LIMIT", "32")))


_save_executor = ThreadPoolExecutor(max_workers=_SAVE_WORKERS, thread_name_prefix="inku-save")


_save_slots = BoundedSemaphore(_SAVE_QUEUE_LIMIT)


_save_stats_lock = Lock()


_save_stats = {
    "submitted": 0,
    "completed": 0,
    "failed": 0,
    "skipped": 0,
}


# Baking a thumbnail is its own queue, not a share of the artifact save one.
# That one is gated by output_save_settings, which is off; a thumbnail is how
# the listing draws itself, so it must not ride on a switch that means
# something else.
_THUMB_WORKERS = max(1, int(os.getenv("INKU_THUMBNAIL_WORKERS", "2")))


_THUMB_QUEUE_LIMIT = max(_THUMB_WORKERS, int(os.getenv("INKU_THUMBNAIL_QUEUE_LIMIT", "64")))


_thumb_executor = ThreadPoolExecutor(max_workers=_THUMB_WORKERS, thread_name_prefix="inku-thumb")


_thumb_slots = BoundedSemaphore(_THUMB_QUEUE_LIMIT)


_thumb_stats_lock = Lock()


_thumb_stats = {
    "submitted": 0,
    "completed": 0,
    "failed": 0,
    "skipped": 0,
    "unavailable": 0,
}


# Counts of the model effects the shared pipeline performs (catalog selection,
# sketch, Stage 1, hole completion). The pipeline worker pool runs them; these
# counters only report what happened there.
_stage_stats_lock = Lock()


_stage_stats = {
    "submitted": 0,
    "completed": 0,
    "failed": 0,
    "timed_out": 0,
    "rejected": 0,
}


class _RenderCapacity:
    """描画スロット。上限は管理者設定で実行中に変更できるため、固定長の
    BoundedSemaphore ではなく上限と使用数を明示的に持つ。acquire は待たない
    (満杯なら即 False) 従来どおりの挙動。"""

    def __init__(self, limit: int) -> None:
        self._lock = Lock()
        self._limit = max(1, limit)
        self._active = 0

    @property
    def limit(self) -> int:
        with self._lock:
            return self._limit

    def set_limit(self, limit: int) -> None:
        with self._lock:
            self._limit = max(1, limit)

    def acquire(self) -> bool:
        with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)


_render_slots = _RenderCapacity(max(1, int(os.getenv("INKU_RENDER_CONCURRENCY", "2"))))


class _RenderTurns:
    """One render at a time for each account.

    One render can take gigabytes and seconds -- a single huge shape took
    1.34 GB and 9 s on 2026-09-26 -- and the slots above are shared. Taking
    turns keeps one account to one slot, so the rest stay free for everybody
    else. A second render from the same account waits for the first instead of
    being refused: the Web asks for four candidates at once and each is drawn.
    """

    def __init__(self) -> None:
        self._changed = Condition()
        self._rendering: set[str] = set()

    def acquire(self, owner: str, timeout: float) -> bool:
        with self._changed:
            if not self._changed.wait_for(lambda: owner not in self._rendering, timeout):
                return False
            self._rendering.add(owner)
            return True

    def release(self, owner: str) -> None:
        with self._changed:
            self._rendering.discard(owner)
            self._changed.notify_all()


_render_turns = _RenderTurns()
# How long a render waits for the same account's previous one. Past it, the
# answer is the 503 a full server gives, which the clients already retry.
_RENDER_TURN_WAIT_SECONDS = 30.0


@contextmanager
def _render_capacity(owner: str | None = None):
    if owner is not None and not _render_turns.acquire(owner, _RENDER_TURN_WAIT_SECONDS):
        raise HTTPException(status_code=503, detail="render capacity is full", headers={"Retry-After": "1"})
    try:
        if not _render_slots.acquire():
            raise HTTPException(status_code=503, detail="render capacity is full", headers={"Retry-After": "1"})
        try:
            yield
        finally:
            _render_slots.release()
    finally:
        if owner is not None:
            _render_turns.release(owner)


def _increment_save_stat(name: str) -> None:
    with _save_stats_lock:
        _save_stats[name] = _save_stats.get(name, 0) + 1


def _artifact_save_stats() -> dict[str, int]:
    with _save_stats_lock:
        return dict(_save_stats)


def _increment_thumb_stat(name: str) -> None:
    with _thumb_stats_lock:
        _thumb_stats[name] = _thumb_stats.get(name, 0) + 1


def _thumbnail_stats() -> dict[str, int]:
    with _thumb_stats_lock:
        return dict(_thumb_stats)


def _increment_stage_stat(name: str) -> None:
    with _stage_stats_lock:
        _stage_stats[name] = _stage_stats.get(name, 0) + 1


def _stage_execution_stats() -> dict[str, int]:
    with _stage_stats_lock:
        return dict(_stage_stats)
