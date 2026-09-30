"""While an administrator locks writes, every write is refused, and the lock can still be lifted.

The lock holds the saved records still while a copy of the database is
counted (2026-09-30). Its own switch, and signing in and out, must pass, or a
locked server could never be unlocked.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inku_server.security import DB_WRITE_LOCKED_DETAIL, DbWriteLockMiddleware


def _client(state: dict) -> TestClient:
    app = FastAPI()

    def is_locked() -> bool:
        if state.get("unreadable"):
            raise RuntimeError("the lock cannot be read")
        return state["locked"]

    app.add_middleware(DbWriteLockMiddleware, is_locked=is_locked,
                       exempt_paths=frozenset({"/api/settings/db-write-lock", "/api/auth/login", "/api/auth/logout"}))

    @app.put("/api/settings/db-write-lock")
    def switch(body: dict) -> dict:
        state["locked"] = body["locked"]
        return {"locked": state["locked"]}

    @app.post("/api/auth/login")
    def login() -> dict:
        return {"ok": True}

    @app.post("/api/pipeline/variations")
    def write() -> dict:
        return {"ok": True}

    @app.get("/api/history")
    def read() -> dict:
        return {"ok": True}

    return TestClient(app)


def test_a_locked_server_refuses_writes_and_can_still_be_unlocked():
    state = {"locked": True}
    client = _client(state)

    refused = client.post("/api/pipeline/variations")
    assert (refused.status_code, refused.json()["detail"]) == (503, DB_WRITE_LOCKED_DETAIL)
    assert client.get("/api/history").status_code == 200
    assert client.post("/api/auth/login").status_code == 200

    assert client.put("/api/settings/db-write-lock", json={"locked": False}).json() == {"locked": False}
    assert client.post("/api/pipeline/variations").status_code == 200

    # A lock that cannot be read refuses writes, but never its own switch.
    state["unreadable"] = True
    assert client.post("/api/pipeline/variations").status_code == 503
    assert client.put("/api/settings/db-write-lock", json={"locked": False}).status_code == 200
