"""Small application-level guards that also work in container deployments."""

from __future__ import annotations

import os
import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from threading import BoundedSemaphore, Lock
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_logger = logging.getLogger(__name__)

# Redis shared pool
_REDIS_CLIENT = None
_REDIS_INITIALIZED = False


def _get_redis_client():
    global _REDIS_CLIENT, _REDIS_INITIALIZED
    if _REDIS_INITIALIZED:
        return _REDIS_CLIENT

    _REDIS_INITIALIZED = True
    redis_url = os.getenv("INKU_REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis
        client = redis.from_url(redis_url, decode_responses=True)
        client.ping()
        _REDIS_CLIENT = client
        _logger.info("Connected to Redis for distributed rate limiting.")
    except Exception as e:
        _logger.warning(
            f"Failed to connect to Redis at {redis_url}: {e}. "
            "Falling back to in-memory rate limiter."
        )
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


class RequestBodyLimitMiddleware:
    """Reject oversized request bodies, including chunked requests."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max(1, max_bytes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send)
                return

        received = 0
        messages: list[Message] = []
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break

        message_index = 0

        async def replay_receive() -> Message:
            nonlocal message_index
            if message_index < len(messages):
                message = messages[message_index]
                message_index += 1
                return message
            # The buffered body is exhausted; fall through to the real channel so
            # http.disconnect still reaches the app. Returning a synthetic empty
            # http.request here would hang any streaming response, which waits
            # for a disconnect message.
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {"detail": "request body is too large"},
            status_code=413,
        )
        await response(scope, receive, send)


class ConcurrencyLimitMiddleware:
    """Reject excess in-flight requests before buffering their bodies."""

    def __init__(self, app: ASGIApp, *, max_requests: int) -> None:
        self.app = app
        self._slots = BoundedSemaphore(max(1, max_requests))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not self._slots.acquire(blocking=False):
            response = JSONResponse(
                {"detail": "server request capacity is full"},
                status_code=503,
                headers={"Retry-After": "1"},
            )
            await response(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self._slots.release()


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int = 0


class SlidingWindowRateLimiter:
    """Bounded in-process or distributed limiter.

    Uses Redis if INKU_REDIS_URL is set and redis-py is installed,
    falling back to in-memory deque otherwise.
    """

    def __init__(self, *, attempts: int, window_seconds: int, max_keys: int = 10_000) -> None:
        self.attempts = max(1, attempts)
        self.window_seconds = max(1, window_seconds)
        self.max_keys = max(100, max_keys)
        self._entries: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def check(self, key: str, *, now: float | None = None) -> RateLimitResult:
        redis_client = _get_redis_client()
        if redis_client is not None:
            try:
                redis_key = f"ratelimit:{key}"
                now_timestamp = time.time() if now is None else now
                clear_before = now_timestamp - self.window_seconds

                pipe = redis_client.pipeline()
                pipe.zremrangebyscore(redis_key, 0, clear_before)
                pipe.zcard(redis_key)
                pipe.zadd(redis_key, {str(now_timestamp): now_timestamp})
                pipe.expire(redis_key, self.window_seconds)
                results = pipe.execute()

                count = results[1]
                if count >= self.attempts:
                    oldest_items = redis_client.zrange(redis_key, 0, 0, withscores=True)
                    if oldest_items:
                        oldest = oldest_items[0][1]
                        retry_after = max(1, int(self.window_seconds - (now_timestamp - oldest)))
                    else:
                        retry_after = self.window_seconds
                    return RateLimitResult(False, retry_after)
                return RateLimitResult(True)
            except Exception as e:
                _logger.error(f"Redis rate limiting error: {e}. Falling back to in-memory check.")

        # In-memory fallback
        timestamp = time.monotonic() if now is None else now
        cutoff = timestamp - self.window_seconds
        with self._lock:
            attempts = self._entries.pop(key, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.attempts:
                self._entries[key] = attempts
                retry_after = max(1, int(self.window_seconds - (timestamp - attempts[0])))
                return RateLimitResult(False, retry_after)
            attempts.append(timestamp)
            self._entries[key] = attempts
            while len(self._entries) > self.max_keys:
                self._entries.popitem(last=False)
            return RateLimitResult(True)

    def reset(self, key: str) -> None:
        redis_client = _get_redis_client()
        if redis_client is not None:
            try:
                redis_client.delete(f"ratelimit:{key}")
                return
            except Exception as e:
                _logger.error(f"Failed to reset Redis rate limit for {key}: {e}")

        with self._lock:
            self._entries.pop(key, None)
