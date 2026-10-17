"""Linux native gate: a support change draws and saves the parent with only its ground changed."""

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


def test_ground_variant_render_save_and_replay(monkeypatch):
    from inku_server.api_core import common, rendering

    monkeypatch.setattr(rendering, "_submit_thumbnail_build", lambda _item: None)
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"ground-{suffix}")
    user = db.add_user(username=f"ground-{suffix}", email=f"ground-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    try:
        binding = PipelineBinding()
        effects = ProductPipelineEffects(binding, default_manifest(binding))
        source = "Nature.青葉。"
        with monkeypatch.context() as preparation:
            preparation.setattr(common, "_model_offered_to", lambda *args, **kwargs: True)
            config, context = effects.prepare(user["id"], "direct_ddl", source,
                {"instruction_lang": "ja", "catalog_id": "default", "render_seed": 77, "composition_seed": 17}, None)
        context.update(description="saved leaves", committed_description="saved leaves", derivation_kind="new")
        run = CandidateExecution(binding, VariationAuthorityStore(db.engine), owner_id=user["id"],
            config=config, context=context, provider=lambda _action: pytest.fail("ground change called a provider"))
        run.start_new({"tag": "direct_ddl", "source": source})
        run.run_effect()
        snapshot = run.snapshot()
        assert snapshot["phase"]["tag"] == "score_ready"
        score = snapshot["delivery"]["score"]
        initial = {"id": str(uuid.uuid4()), "user_id": user["id"], "at": 1, "input": "saved leaves",
                   "ddl": source, "score": score, "svg": "<svg/>", "render_color_map": render_color_map_for_catalog("default"),
                   "catalog_id": "default", "render_color_catalog_id": "default", "instruction_lang_resolved": "ja",
                   "render_seed": 77, "composition_seed": 17, "render_canvas_aspect_id": "hd_monitor"}
        from inku_server.pipeline_runtime import get_service
        baseline = get_service().replay_for(user["id"], {"score": score, "render_seed": 77,
            "composition_seed": 17, "canvas_aspect": "hd_monitor"}, initial)
        parent = db.add_item({**initial, **baseline})

        plan = client.post("/api/ground-variants/plan", json={"work_id": parent["id"]}, headers=headers)
        assert plan.status_code == 200, plan.text
        assert plan.json()["current"] == "plain"
        assert [entry["material"] for entry in plan.json()["entries"]] == [
            "paper", "washi", "ink_wash", "charcoal_ground", "canvas", "drawing_paper", "mezzotint"]
        selected = client.post("/api/render-ground-variant", json={"work_id": parent["id"], "material": "washi"}, headers=headers)
        assert selected.status_code == 200, selected.text
        selected = selected.json()
        assert selected["ddl"] == "和紙。\n" + source
        assert selected["score"]["canvas"]["ground"]["material"] == "washi"
        assert {k: v for k, v in selected["score"].items() if k != "canvas"} == {k: v for k, v in score.items() if k != "canvas"}
        assert selected["render_seed"] == "77" and selected["composition_seed"] == "17"
        assert selected["render_canvas_aspect_id"] == "hd_monitor"
        assert selected["svg"] != parent["svg"]

        save = client.post("/api/history", json={
            "input": "untrusted replacement", "ddl": "untrusted replacement", "score": {}, "at": 2,
            "render_seed": 999, "save_artifacts": False,
            "lineage_parent_node_id": parent["lineage_node_id"], "derivation_kind": "ground_change",
            "derivation_metadata": {"ground_material": "washi"},
        }, headers=headers)
        assert save.status_code == 200, save.text
        child = save.json()
        assert child["input"] == parent["input"] and child["ddl"] == selected["ddl"]
        assert child["score"] == selected["score"] and child["svg"] == selected["svg"]
        assert child["derivation_metadata"] == {"ground_material": "washi", "parent_ground_material": "plain"}
        replay = client.post("/api/render-score", json={"work_id": child["id"], "score": child["score"],
            "render_seed": child["render_seed"], "composition_seed": child["composition_seed"]}, headers=headers)
        assert replay.status_code == 200, replay.text
        assert replay.json()["svg"] == selected["svg"]

        again = client.post("/api/ground-variants/plan", json={"work_id": child["id"]}, headers=headers).json()
        assert again["current"] == "washi" and len(again["entries"]) == 6
        same = client.post("/api/render-ground-variant", json={"work_id": child["id"], "material": "washi"}, headers=headers)
        assert same.status_code == 422
    finally:
        db.delete_session(token)
        db.delete_user(user["id"], cascade=True)
        db.delete_user_group(group["id"])
