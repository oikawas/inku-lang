"""Process-wide mutable state shared by the render, history and settings routers."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
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


_STAGE_WORKERS = max(1, int(os.getenv("INKU_STAGE_WORKERS", "4")))


_STAGE_QUEUE_LIMIT = max(_STAGE_WORKERS, int(os.getenv("INKU_STAGE_QUEUE_LIMIT", str(_STAGE_WORKERS * 2))))


_stage_executor = ThreadPoolExecutor(max_workers=_STAGE_WORKERS, thread_name_prefix="inku-stage")


_stage_slots = BoundedSemaphore(_STAGE_QUEUE_LIMIT)


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


@contextmanager
def _render_capacity():
    if not _render_slots.acquire():
        raise HTTPException(status_code=503, detail="render capacity is full", headers={"Retry-After": "1"})
    try:
        yield
    finally:
        _render_slots.release()


def _increment_save_stat(name: str) -> None:
    with _save_stats_lock:
        _save_stats[name] = _save_stats.get(name, 0) + 1


def _artifact_save_stats() -> dict[str, int]:
    with _save_stats_lock:
        return dict(_save_stats)


def _increment_stage_stat(name: str) -> None:
    with _stage_stats_lock:
        _stage_stats[name] = _stage_stats.get(name, 0) + 1


def _stage_execution_stats() -> dict[str, int]:
    with _stage_stats_lock:
        return dict(_stage_stats)
