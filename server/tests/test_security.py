from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inku_server.api import app as inku_app
from inku_server.api_core.routers.auth import _LOGIN_RATE_ATTEMPTS, _login_rate_limiter
from inku_server.security import (
    ConcurrencyLimitMiddleware,
    RequestBodyLimitMiddleware,
    SlidingWindowRateLimiter,
)


def test_request_body_limit_rejects_declared_oversize_body() -> None:
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=8)

    @app.post("/echo")
    async def echo() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).post("/echo", content=b"123456789")

    assert response.status_code == 413
    assert response.json() == {"detail": "request body is too large"}


def test_request_body_limit_allows_body_at_limit() -> None:
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=8)

    @app.post("/echo")
    async def echo() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).post("/echo", content=b"12345678")

    assert response.status_code == 200


def test_request_body_limit_rejects_chunked_oversize_body() -> None:
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=8)

    @app.post("/echo")
    async def echo() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).post("/echo", content=iter((b"1234", b"56789")))

    assert response.status_code == 413


def test_sliding_window_rate_limiter_limits_and_resets() -> None:
    limiter = SlidingWindowRateLimiter(attempts=2, window_seconds=60)

    assert limiter.check("client", now=1).allowed
    assert limiter.check("client", now=2).allowed
    blocked = limiter.check("client", now=3)
    assert not blocked.allowed
    assert blocked.retry_after > 0

    limiter.reset("client")
    assert limiter.check("client", now=4).allowed


def test_concurrency_limit_rejects_when_capacity_is_occupied() -> None:
    inner = FastAPI()

    @inner.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    limited = ConcurrencyLimitMiddleware(inner, max_requests=1)
    assert limited._slots.acquire(blocking=False)
    try:
        response = TestClient(limited).get("/health")
        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
    finally:
        limited._slots.release()


def test_sliding_window_rate_limiter_expires_old_attempts() -> None:
    limiter = SlidingWindowRateLimiter(attempts=1, window_seconds=10)

    assert limiter.check("client", now=1).allowed
    assert not limiter.check("client", now=5).allowed
    assert limiter.check("client", now=11).allowed


def test_login_endpoint_rate_limits_repeated_failures() -> None:
    username = f"missing-{uuid.uuid4().hex}"
    rate_key = f"testclient:{username}"
    client = TestClient(inku_app)
    try:
        for _ in range(_LOGIN_RATE_ATTEMPTS):
            response = client.post(
                "/api/auth/login",
                json={"username": username, "password": "incorrect-password"},
            )
            assert response.status_code == 401
        blocked = client.post(
            "/api/auth/login",
            json={"username": username, "password": "incorrect-password"},
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
    finally:
        _login_rate_limiter.reset(rate_key)


def test_a_redis_connection_failure_does_not_log_the_password(monkeypatch, caplog) -> None:
    from inku_server import security

    monkeypatch.setattr(security, "_REDIS_CLIENT", None)
    monkeypatch.setattr(security, "_REDIS_INITIALIZED", False)
    # Port 1 refuses at once, and with redis-py absent the import fails instead:
    # either way the connection fails and the warning is written.
    monkeypatch.setenv("INKU_REDIS_URL", "redis://:s3cret-pass@127.0.0.1:1/0")
    with caplog.at_level("WARNING", logger="inku_server.security"):
        assert security._get_redis_client() is None
    assert "Failed to connect to Redis at redis://127.0.0.1:1/0" in caplog.text
    assert "s3cret-pass" not in caplog.text


def test_another_site_cannot_have_the_browser_change_anything() -> None:
    """Single-user mode takes every request without credentials as the owner's,
    and a POST with no body leaves the browser without a CORS preflight."""
    client = TestClient(inku_app)
    elsewhere = {"Sec-Fetch-Site": "cross-site", "Origin": "https://elsewhere.example"}
    local_page = {"Sec-Fetch-Site": "cross-site", "Origin": "http://localhost:5173"}

    refused = client.post("/api/auth/logout", headers=elsewhere)

    assert (refused.status_code, refused.json()) == (403, {"detail": "cross-site request refused"})
    # Only that is refused. An origin the CORS policy admits, and a client that
    # sends no such header (the CLI, the Android app), reach the route, which
    # here asks for a session.
    assert client.post("/api/auth/logout", headers=local_page).status_code == 401
    assert client.post("/api/auth/logout").status_code == 401
