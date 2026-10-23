"""A saved work fitted into another paper (DDL 26): its Score is drawn in a frame of its ratio, and saved as a child."""

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.color_catalogs import render_color_map_for_catalog
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_candidate import CandidateExecution, PipelineBinding
from inku_server.pipeline_defaults import default_manifest
from inku_server.pipeline_product import ProductPipelineEffects


def test_a_saved_work_is_fitted_from_its_score_and_saved_as_a_child(monkeypatch):
    from inku_server.api_core import common, rendering

    monkeypatch.setattr(rendering, "_submit_thumbnail_build", lambda _item: None)
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"fit-{suffix}")
    user = db.add_user(username=f"fit-{suffix}", email=f"fit-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    try:
        binding = PipelineBinding()
        effects = ProductPipelineEffects(binding, default_manifest(binding))
        # A work saved before DDL 26: no declaration, drawn on the 16:9 paper.
        source = "赤い円を置く。"
        with monkeypatch.context() as preparation:
            preparation.setattr(common, "_model_offered_to", lambda *args, **kwargs: True)
            config, context = effects.prepare(user["id"], "direct_ddl", source,
                {"instruction_lang": "ja", "catalog_id": "default", "render_seed": 77, "composition_seed": 17,
                 "canvas_aspect": "hd_monitor"}, None)
        context.update(description="a red circle", committed_description="a red circle", derivation_kind="new")
        run = CandidateExecution(binding, VariationAuthorityStore(db.engine), owner_id=user["id"],
            config=config, context=context, provider=lambda _action: pytest.fail("a fit called a provider"))
        run.start_new({"tag": "direct_ddl", "source": source})
        run.run_effect()
        snapshot = run.snapshot()
        assert snapshot["phase"]["tag"] == "score_ready"
        score = snapshot["delivery"]["score"]
        assert score["canvas"] == "hd_monitor"
        initial = {"id": str(uuid.uuid4()), "user_id": user["id"], "at": 1, "input": "a red circle",
                   "ddl": source, "score": score, "svg": "<svg/>", "render_color_map": render_color_map_for_catalog("default"),
                   "catalog_id": "default", "render_color_catalog_id": "default", "instruction_lang_resolved": "ja",
                   "render_seed": 77, "composition_seed": 17, "render_canvas_aspect_id": "hd_monitor"}
        from inku_server.pipeline_runtime import get_service
        baseline = get_service().replay_for(user["id"], {"score": score, "render_seed": 77,
            "composition_seed": 17, "canvas_aspect": "hd_monitor"}, initial)
        parent = db.add_item({**initial, **baseline})

        fitted = client.post("/api/render-canvas-fit", json={"work_id": parent["id"], "canvas_aspect": "square"},
                             headers=headers)
        assert fitted.status_code == 200, fitted.text
        fitted = fitted.json()
        assert fitted["score"]["canvas"] == {"aspect": "square", "ground": None,
                                             "declared_ratio": {"width_units": 16, "height_units": 9}, "fit": "contain"}
        # Nothing else of the Score changes, its version included.
        assert {k: v for k, v in fitted["score"].items() if k != "canvas"} == {
            k: v for k, v in score.items() if k != "canvas"}
        assert fitted["render_canvas_aspect_id"] == "square"
        assert 'id="inku_fitted_frame"' in fitted["svg"]
        assert fitted["derivation_metadata"]["to_canvas_aspect"] == "square"
        # The work's own paper is no fit.
        same = client.post("/api/render-canvas-fit", json={"work_id": parent["id"], "canvas_aspect": "hd_monitor"},
                           headers=headers)
        assert same.status_code == 422, same.text

        save = client.post("/api/history", json={
            "input": "untrusted replacement", "ddl": "untrusted replacement", "score": {}, "at": 2,
            "render_seed": 999, "save_artifacts": False,
            "lineage_parent_node_id": parent["lineage_node_id"], "derivation_kind": "canvas_fit",
            "derivation_metadata": {"to_canvas_aspect": "square"},
        }, headers=headers)
        assert save.status_code == 200, save.text
        child = save.json()
        assert child["input"] == parent["input"] and child["ddl"] == source
        assert child["score"] == fitted["score"] and child["svg"] == fitted["svg"]
        assert child["render_canvas_aspect_id"] == "square"
        replay = client.post("/api/render-score", json={"work_id": child["id"], "score": child["score"],
            "render_seed": child["render_seed"], "composition_seed": child["composition_seed"]}, headers=headers)
        assert replay.status_code == 200, replay.text
        assert replay.json()["svg"] == child["svg"]
    finally:
        db.delete_session(token)
        db.delete_user(user["id"], cascade=True)
        db.delete_user_group(group["id"])
