"""Retired variation is historical metadata, never a new authoring request."""

from copy import deepcopy
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError


def test_retired_requests_results_and_seed_route_leave_history_readable():
    from inku_server.api_core.models import HistoryItem, HistoryPostBody
    from inku_server.api_core.routers import render
    from inku_server.autonomous_refine import ALLOWED_KINDS
    from inku_server.pipeline_product import RunOptions

    retired = {"focus", "variation_amplitude", "variation_seed", "variation_moved_axes"}
    for model in (HistoryPostBody, render.PaintRequest, render.ComposeRequest,
                  render.PaintResponse, render.ComposeResponse, RunOptions):
        assert not retired.intersection(model.model_fields), model.__name__
    with pytest.raises(ValidationError):
        RunOptions.model_validate({"variation_seed": 7})
    assert set(ALLOWED_KINDS) == {"touch_change", "layout_change", "reinterpretation", "catalog_change"}
    app = FastAPI()
    app.include_router(render.router)
    with TestClient(app) as client:
        assert client.post("/api/variation/seeds", json={"amplitude": "small"}).status_code == 404
    old = HistoryItem.model_validate({
        "id": "old-work", "input": "old prose", "ddl": "old DDL", "score": {}, "at": 1,
        "focus": "upper_right", "variation_amplitude": "small", "variation_seed": 7,
        "pipeline_variation_id": "work-authority",
    })
    assert old.focus == "upper_right" and old.variation_amplitude == "small" and old.variation_seed == 7
    assert old.pipeline_variation_id == "work-authority"
    new = HistoryPostBody.model_validate(old.model_dump())
    assert not retired.intersection(new.model_dump())


def test_prepare_drops_only_retired_execution_options_and_preserves_saved_config(monkeypatch):
    from inku_server import db
    from inku_server.api_core import common
    from inku_server.pipeline_defaults import default_manifest
    from inku_server.pipeline_product import ProductPipelineEffects

    binding = SimpleNamespace(
        canvas_registry={"registry": {"schema": "fixture", "formats": []}, "digest": "fixture"},
        resolve_palette=lambda _request: json.dumps({"schema": "fixture-palette"}).encode(),
    )
    manifest = default_manifest(binding)
    assert "stage15_variation" not in manifest["pipeline"]["compiler"]
    saved = deepcopy(manifest["pipeline"])
    saved["compiler"]["stage15_variation"] = {"amplitude": "large", "seed": "7"}
    work = {
        "saved_config": saved,
        "host_options": {"variation_amplitude": "large", "variation_seed": "7"},
        "metadata": {"variation_seed": "7", "variation_amplitude": "large", "focus": "upper_right"},
    }
    before = deepcopy(work)
    monkeypatch.setattr(db, "get_user", lambda _owner: {"id": "author"})
    monkeypatch.setattr(db, "get_model_settings", lambda: {})
    monkeypatch.setattr(common, "_model_offered_to", lambda *_args, **_kwargs: True)
    effects = ProductPipelineEffects(binding, manifest)
    config, context = effects.prepare("author", "direct_ddl", "one circle", {
        "instruction_lang": "en", "stage1_model": "openai:fixture", "render_seed": 17,
    }, work)
    assert "stage15_variation" not in config["compiler"]
    assert not {"variation_seed", "variation_amplitude"}.intersection(context["host_options"])
    assert context["host_options"]["render_seed"] == "17"
    assert context["host_options"]["stage1_model"] == context["host_options"]["stage2_model"]
    assert work == before
