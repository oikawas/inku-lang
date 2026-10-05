"""The display reads the core's table; older wheels keep the complete DDL."""

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inku_server import pipeline_runtime
from inku_server.api_core.deps import _current_user
from inku_server.api_core.routers import render


def _app():
    app = FastAPI()
    app.include_router(render.router)
    return app


def test_the_authenticated_range_table_preserves_the_core_words_and_fractions(monkeypatch):
    calls = []
    table = {
        "schema": "inku.composition-ranges.v1",
        "ranges": [{
            "key": "cell-22", "words": {"ja": "右下", "en": "bottom right"},
            "bounds": [[2, 3], [2, 3], [1, 1], [1, 1]], "corner": False,
        }],
    }

    def native():
        calls.append(True)
        return json.dumps(table, ensure_ascii=False)

    def no_service():
        raise AssertionError("display started the service")

    monkeypatch.setattr(pipeline_runtime, "get_binding", lambda: SimpleNamespace(composition_ranges=native))
    monkeypatch.setattr(pipeline_runtime, "get_service", no_service)
    monkeypatch.setattr(render._db, "single_user_mode_enabled", lambda: False)
    app = _app()
    with TestClient(app) as client:
        assert client.get("/api/composition/ranges").status_code == 401
        assert not calls
        app.dependency_overrides[_current_user] = lambda: {"id": "author"}
        response = client.get("/api/composition/ranges")
    assert response.status_code == 200, response.text
    assert response.json() == table
    assert calls == [True]


def test_an_older_binding_returns_an_empty_table(monkeypatch):
    monkeypatch.setattr(pipeline_runtime, "get_binding", lambda: SimpleNamespace())
    app = _app()
    app.dependency_overrides[_current_user] = lambda: {"id": "author"}
    with TestClient(app) as client:
        response = client.get("/api/composition/ranges")
    assert response.status_code == 200, response.text
    assert response.json() == {"schema": "inku.composition-ranges.v1", "ranges": []}
