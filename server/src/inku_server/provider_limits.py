"""Hold a provider to the number of requests it will actually take at once.

Written for Ollama Cloud, whose free tier is limited by concurrency rather than
by volume: eight simultaneous requests returned 429 while only 7.6% of the
weekly allowance had been spent (measured 2026-07-27). Sending more does not
buy throughput there, it buys refusals.

The limit belongs to the provider, so it is read from the provider definition
and is not exposed as a setting. Providers without one are not slowed down: they
pass through with no lock taken at all.

Only the request itself is held inside the slot. A drawing that runs Stage 1 and
Stage 2 releases the slot between them, so a queue of drawings interleaves
rather than serialising end to end.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from .model_settings import provider_concurrency_limit

_lock = threading.Lock()
# provider id -> (limit it was built for, semaphore). The limit is compiled in, but
# keeping it alongside means a changed definition rebuilds instead of silently
# enforcing the old number.
_semaphores: dict[str, tuple[int, threading.BoundedSemaphore]] = {}


def _semaphore_for(provider_id: str, limit: int) -> threading.BoundedSemaphore:
    with _lock:
        cached = _semaphores.get(provider_id)
        if cached is None or cached[0] != limit:
            cached = (limit, threading.BoundedSemaphore(limit))
            _semaphores[provider_id] = cached
        return cached[1]


@contextmanager
def provider_slot(provider_id: str | None) -> Iterator[None]:
    """Wait for a free slot on this provider, or pass straight through."""
    limit = provider_concurrency_limit(str(provider_id or ""))
    if limit <= 0:
        yield
        return
    # Released on the same object it was taken from, so a definition changing
    # mid-flight cannot push a BoundedSemaphore past its ceiling.
    semaphore = _semaphore_for(str(provider_id), limit)
    semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()
