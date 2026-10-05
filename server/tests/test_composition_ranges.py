"""The display reads the core's table; older wheels keep the complete DDL."""

import json
from copy import deepcopy
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from inku_server import pipeline_runtime
from inku_server.api_core.deps import _current_user
from inku_server.api_core.routers import render
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_candidate import CandidateExecution, PipelineBinding
from inku_server.pipeline_defaults import default_manifest


def test_the_chosen_place_compiles_without_diagnostics_in_both_languages():
    binding = PipelineBinding()
    config = default_manifest(binding)["pipeline"]
    engine = create_engine("sqlite:///:memory:")
    store = VariationAuthorityStore(engine)
    store.install_schema()

    def no_provider(_action):
        raise AssertionError("complete numeric DDL requested a provider")

    try:
        for language, source in (
            ("ja", "指定の範囲（横0〜0.5、縦0〜2/3）に、赤い円を置く。"),
            ("en", "A red circle at the chosen place (horizontal 0 to 0.5, vertical 0 to 2/3)."),
        ):
            selected = deepcopy(config)
            selected["language"] = language
            run = CandidateExecution(binding, store, owner_id="range-name-follow", config=selected, provider=no_provider)
            run.start_new({"tag": "direct_ddl", "source": source})
            run.run_effect()
            snapshot = run.snapshot()
            assert snapshot["phase"]["tag"] == "score_ready", snapshot
            assert snapshot["action"] is None
            assert snapshot["document"]["source"] == source
            delivery = snapshot["delivery"]
            assert delivery["upstream_diagnostics"] == []
            assert delivery["downstream_diagnostics"] == []
            instructions = delivery["score"]["instructions"]
            assert len(instructions) == 1
            assert instructions[0]["primitive"] == "circle"
            assert instructions[0]["color"] == "red"
            print(f"chosen_place[{language}]: Score commands=1, diagnostics=0, provider_calls=0")
    finally:
        engine.dispose()


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
