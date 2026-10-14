"""Linux native gate: saving an arrangement must replay its selected colors."""

import uuid
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.color_arrangements import ColorArrangements, normalized_hex
from inku_server.color_catalogs import render_color_map_for_catalog
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_candidate import CandidateExecution, PipelineBinding
from inku_server.pipeline_defaults import default_manifest
from inku_server.pipeline_product import ProductPipelineEffects


def test_retired_catalog_arrangement_render_save_and_replay(monkeypatch):
    from inku_server.api_core import rendering

    monkeypatch.setattr(rendering, "_submit_thumbnail_build", lambda _item: None)
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"arrange-{suffix}")
    user = db.add_user(username=f"arrange-{suffix}", email=f"arrange-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    try:
        binding = PipelineBinding()
        effects = ProductPipelineEffects(binding, default_manifest(binding))
        source = "Nature.青葉。"
        config, context = effects.prepare(user["id"], "direct_ddl", source,
            {"instruction_lang": "ja", "catalog_id": "default", "render_seed": 77, "composition_seed": 17}, None)
        context.update(description="saved leaves", committed_description="saved leaves", derivation_kind="new")
        run = CandidateExecution(binding, VariationAuthorityStore(db.engine), owner_id=user["id"],
            config=config, context=context, provider=lambda _action: pytest.fail("recolor called a provider"))
        run.start_new({"tag": "direct_ddl", "source": source})
        run.run_effect()
        snapshot = run.snapshot()
        assert snapshot["phase"]["tag"] == "score_ready"
        score = snapshot["delivery"]["score"]
        assert score["version"] in {"0.10.0", "0.11.0", "0.12.0", "0.13.0"}
        colors = render_color_map_for_catalog("default")
        retired = "retired-arrangement-fixture"
        initial = {"id": str(uuid.uuid4()), "user_id": user["id"], "at": 1, "input": "saved leaves",
                   "ddl": source, "score": score, "svg": "<svg/>", "render_color_map": colors,
                   "catalog_id": retired, "render_color_catalog_id": retired,
                   "render_color_catalog_name": "Retired palette", "render_color_catalog_sub": "saved",
                   "render_seed": 77, "composition_seed": 17, "render_wild": True,
                   "render_canvas_aspect_id": "hd_monitor"}
        from inku_server.pipeline_runtime import get_service
        baseline = get_service().replay_for(user["id"], {"score": score, "render_seed": 77,
            "composition_seed": 17, "wild": True, "canvas_aspect": "hd_monitor"}, initial)
        parent = db.add_item({**initial, **baseline})
        plan_response = client.post("/api/color-arrangements/plan", json={"work_id": parent["id"]}, headers=headers)
        assert plan_response.status_code == 200, plan_response.text
        plan = plan_response.json()
        assert len(plan["entries"]) == 8
        index = plan["entries"][0]["index"]
        selected_response = client.post("/api/render-color-arrangement", json={"work_id": parent["id"], "index": index}, headers=headers)
        assert selected_response.status_code == 200, selected_response.text
        selected = selected_response.json()
        assert selected["render_color_source"] == "color_arrangement"
        assert selected["render_color_catalog_id"] == retired
        assert selected["render_seed"] == 77 and selected["composition_seed"] == 17
        assert selected["render_wild"] is True
        assert selected["render_canvas_aspect_id"] == "hd_monitor"
        substitution = ColorArrangements.from_saved(parent["svg"], colors).substitution(index)
        before, after = ElementTree.fromstring(parent["svg"]), ElementTree.fromstring(selected["svg"])
        assert len(list(before.iter())) == len(list(after.iter()))
        changed = False
        for left, right in zip(before.iter(), after.iter(), strict=True):
            assert left.tag == right.tag
            assert left.text == right.text and left.tail == right.tail
            expected = {key: substitution.get(normalized_hex(value), value) for key, value in left.attrib.items()}
            assert right.attrib == expected
            changed |= left.attrib != right.attrib
        assert changed
        save = client.post("/api/history", json={
            "input": "untrusted replacement", "ddl": "untrusted replacement", "score": {}, "at": 2,
            "catalog_id": "untrusted catalog", "render_color_map": {"black": "#000000"},
            "render_seed": 999, "render_wild": False, "save_artifacts": False,
            "lineage_parent_node_id": parent["lineage_node_id"], "derivation_kind": "color_arrangement_change",
            "derivation_metadata": {"color_arrangement_index": index},
        }, headers=headers)
        assert save.status_code == 200, save.text
        child = save.json()
        assert child["input"] == parent["input"] and child["ddl"] == parent["ddl"]
        assert child["score"] == score
        assert child["svg"] == selected["svg"]
        assert child["render_color_map"] == selected["render_color_map"]
        assert child["render_limits"] == selected["render_limits"]
        replay = client.post("/api/render-score", json={"work_id": child["id"], "score": child["score"],
            "render_seed": child["render_seed"], "composition_seed": child["composition_seed"], "wild": child["render_wild"]}, headers=headers)
        assert replay.status_code == 200, replay.text
        assert replay.json()["svg"] == selected["svg"]
        assert replay.json()["render_color_map"] == selected["render_color_map"]
    finally:
        db.delete_session(token)
        db.delete_user(user["id"], cascade=True)
        db.delete_user_group(group["id"])
