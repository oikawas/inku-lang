"""The current user's endpoint passes and validates the page offset."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inku_server.api_core.routers import feedback


def test_current_user_unread_words_offset(monkeypatch):
    calls = []

    def read(user_id, *, limit, offset):
        calls.append((user_id, limit, offset))
        return [{"word": "second"}]

    monkeypatch.setattr(feedback._db, "list_unread_words", read)
    app = FastAPI()
    app.include_router(feedback.router)
    app.dependency_overrides[feedback._current_user] = lambda: {"id": "author"}
    client = TestClient(app)
    response = client.get("/api/feedback/unread-words", params={"limit": 1, "offset": 1})
    assert response.status_code == 200
    assert response.json() == [{"word": "second"}]
    assert calls == [("author", 1, 1)]
    assert client.get("/api/feedback/unread-words", params={"offset": -1}).status_code == 422
