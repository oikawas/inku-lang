"""Linux native gate: a touch change draws and saves the parent with only its tools changed."""

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.color_catalogs import render_color_map_for_catalog
from inku_server.tool_variants import TOOLS
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_candidate import CandidateExecution, PipelineBinding
from inku_server.pipeline_defaults import default_manifest
from inku_server.pipeline_product import ProductPipelineEffects


def test_tool_variant_render_save_and_replay(monkeypatch):
    from inku_server.api_core import common, rendering

    monkeypatch.setattr(rendering, "_submit_thumbnail_build", lambda _item: None)
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"tool-{suffix}")
    user = db.add_user(username=f"tool-{suffix}", email=f"tool-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    try:
        binding = PipelineBinding()
        effects = ProductPipelineEffects(binding, default_manifest(binding))
        source = "背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。"
        with monkeypatch.context() as preparation:
            preparation.setattr(common, "_model_offered_to", lambda *args, **kwargs: True)
            config, context = effects.prepare(user["id"], "direct_ddl", source,
                {"instruction_lang": "ja", "catalog_id": "default", "render_seed": 77, "composition_seed": 17}, None)
        context.update(description="saved leaves", committed_description="saved leaves", derivation_kind="new")
        run = CandidateExecution(binding, VariationAuthorityStore(db.engine), owner_id=user["id"],
            config=config, context=context, provider=lambda _action: pytest.fail("touch change called a provider"))
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

        weights = lambda value: {i["arrangement"]["resolved"]["owner"]["instruction_index"]: i.get("weight")
                                 for i in value["instructions"]}
        assert weights(score) == {0: "brush_thin", 1: "pen"}

        plan = client.post("/api/tool-variants/plan", json={"work_id": parent["id"]}, headers=headers)
        assert plan.status_code == 200, plan.text
        plan = plan.json()
        assert plan["mode"] == "uniform" and plan["sentences"] == [{"index": 0, "tool": "brush_thin"}, {"index": 1, "tool": "pen"}]
        assert len(plan["entries"]) == 4 and set(plan["tools"]) == set(TOOLS)
        for entry in plan["entries"]:
            tool = entry["tools"]["0"]
            assert entry["tools"] == {"0": tool, "1": tool}
            word = plan["tools"][tool]["ja"]
            assert entry["ddl"] == f"背景を白で埋める。\n青の{word}の線を3個引く。\n赤の大きな{word}の円を1個置く。"

        per = client.post("/api/tool-variants/plan", json={"work_id": parent["id"], "mode": "per_sentence"}, headers=headers).json()
        assert len(per["entries"]) == 4
        assert all(entry["tools"]["0"] != "brush_thin" and entry["tools"]["1"] != "pen" for entry in per["entries"])

        asked = {"0": "chalk", "1": "oil_paint"}
        selected = client.post("/api/render-tool-variant", json={"work_id": parent["id"], "mode": "per_sentence", "tools": asked}, headers=headers)
        assert selected.status_code == 200, selected.text
        selected = selected.json()
        assert selected["ddl"] == "背景を白で埋める。\n青のチョークの線を3個引く。\n赤の大きな油彩の円を1個置く。"
        assert weights(selected["score"]) == {0: "chalk", 1: "oil_paint"}
        strip = lambda value: [{k: v for k, v in i.items() if k != "weight"} for i in value["instructions"]]
        assert strip(selected["score"]) == strip(score)
        assert {k: v for k, v in selected["score"].items() if k != "instructions"} == {k: v for k, v in score.items() if k != "instructions"}
        assert selected["render_seed"] == "77" and selected["composition_seed"] == "17"
        assert selected["svg"] != parent["svg"]
        unchanged = client.post("/api/render-tool-variant", json={"work_id": parent["id"], "tools": {"0": "brush_thin"}}, headers=headers)
        assert unchanged.status_code == 422

        save = client.post("/api/history", json={
            "input": "untrusted replacement", "ddl": "untrusted replacement", "score": {}, "at": 2,
            "render_seed": 999, "save_artifacts": False,
            "lineage_parent_node_id": parent["lineage_node_id"], "derivation_kind": "tool_change",
            "derivation_metadata": {"tool_mode": "per_sentence", "tools": asked},
        }, headers=headers)
        assert save.status_code == 200, save.text
        child = save.json()
        assert child["input"] == parent["input"] and child["ddl"] == selected["ddl"]
        assert child["score"] == selected["score"] and child["svg"] == selected["svg"]
        assert child["derivation_metadata"] == {"tool_mode": "per_sentence", "tools": asked, "changes": [
            {"index": 0, "from": "brush_thin", "to": "chalk"}, {"index": 1, "from": "pen", "to": "oil_paint"}]}
        replay = client.post("/api/render-score", json={"work_id": child["id"], "score": child["score"],
            "render_seed": child["render_seed"], "composition_seed": child["composition_seed"]}, headers=headers)
        assert replay.status_code == 200, replay.text
        assert replay.json()["svg"] == selected["svg"]

        again = client.post("/api/tool-variants/plan", json={"work_id": child["id"]}, headers=headers).json()
        assert again["sentences"] == [{"index": 0, "tool": "chalk"}, {"index": 1, "tool": "oil_paint"}]
    finally:
        db.delete_session(token)
        db.delete_user(user["id"], cascade=True)
        db.delete_user_group(group["id"])
