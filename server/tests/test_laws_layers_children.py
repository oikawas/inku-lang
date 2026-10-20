"""Native gate: a laws work's children drawn without a run keep its laws record (2026-10-20).

Changing the color arrangement, the support or the touches, and redrawing, draw the child from its
parent and save it without a run, so nothing linked the child to its parent's laws record. "Change
the layout" then read the laws' numeric sentences without the record and refused the child
(`unsupported_sentence`, seen on 5173 Build 1292). The child now keeps the record on its lineage
edge (a redraw of a linked work, in its link), a touch written into a recorded sentence is written
into the record too, and a sender cannot name a record.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.color_catalogs import render_color_map_for_catalog
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import saved_work_parent
from inku_server.pipeline_candidate import CandidateExecution, PipelineBinding
from inku_server.pipeline_defaults import default_manifest
from inku_server.pipeline_product import ProductPipelineEffects

RECORDED = "画面の横0.618034、縦0.618034の位置に、灰の細い細筆の程よい空の縦長の小さな楕円を1個置く。"
SOURCE = f"背景を白で埋める。\n{RECORDED}\n上半分（横0〜1、縦0〜1/2）に、青の細筆の線を3個並べる。"
LAWS = {"schema": "inku.laws-layers.v1", "layers": [{"sentences": [RECORDED], "kind": "laws", "laws": ["B1"]}]}
DIAGNOSTICS = {"upstream_diagnostics": [], "downstream_diagnostics": [],
               "resource_omissions": [], "relation_omissions": [],
               "render_diagnostics": None, "resource_execution": None}


def test_children_drawn_from_a_laws_work_keep_its_record(monkeypatch):
    from inku_server.api_core import common, rendering

    monkeypatch.setattr(rendering, "_submit_thumbnail_build", lambda _item: None)
    # "Change the layout" draws through a run, which asks for the user's model; none is called.
    monkeypatch.setattr(common, "_model_offered_to", lambda *args, **kwargs: True)
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"laws-{suffix}")
    user = db.add_user(username=f"laws-{suffix}", email=f"laws-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    token = db.create_session(user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    store = VariationAuthorityStore(db.engine)
    try:
        binding = PipelineBinding()
        effects = ProductPipelineEffects(binding, default_manifest(binding))
        config, context = effects.prepare(user["id"], "direct_ddl", SOURCE,
            {"instruction_lang": "ja", "catalog_id": "default", "render_seed": 77, "composition_seed": 17}, None)
        context.update(description="a grey ellipse", committed_description="a grey ellipse", derivation_kind="new")
        run = CandidateExecution(binding, store, owner_id=user["id"], config=config, context=context,
                                 provider=lambda _action: pytest.fail("no model is asked"))
        # A direct-DDL run takes a record as a fork of a laws work does, and keeps it.
        run.start_new({"tag": "direct_ddl", "source": SOURCE, "laws_layers": LAWS})
        run.run_effect()
        snapshot = run.snapshot()
        assert snapshot["phase"]["tag"] == "score_ready"
        assert snapshot["laws_layers"] == LAWS
        source, score = snapshot["document"]["source"], snapshot["delivery"]["score"]
        initial = {"id": str(uuid.uuid4()), "user_id": user["id"], "at": 1, "input": "a grey ellipse",
                   "ddl": source, "score": score, "svg": "<svg/>", "render_color_map": render_color_map_for_catalog("default"),
                   "catalog_id": "default", "render_color_catalog_id": "default", "instruction_lang_resolved": "ja",
                   "render_seed": 77, "composition_seed": 17, "render_canvas_aspect_id": "hd_monitor"}
        from inku_server.pipeline_runtime import get_service
        baseline = get_service().replay_for(user["id"], {"score": score, "render_seed": 77,
            "composition_seed": 17, "canvas_aspect": "hd_monitor"}, initial)
        parent = db.add_item({**initial, **baseline})
        store.link_history(user["id"], parent["id"], snapshot["variation_id"], snapshot["authority"]["revision"],
                           snapshot["delivery"]["source_digest"], snapshot=snapshot, context=context,
                           pipeline_diagnostics=DIAGNOSTICS)
        assert store.read_linked_history(user["id"], parent["id"]).laws_layers == LAWS

        def record_of(work_id):
            return saved_work_parent(store, user["id"], work_id)[1].get("laws_layers")

        def save(parent_node, kind, metadata, at):
            saved = client.post("/api/history", json={
                "input": "", "score": {}, "at": at, "save_artifacts": False,
                "lineage_parent_node_id": parent_node, "derivation_kind": kind, "derivation_metadata": metadata,
            }, headers=headers)
            assert saved.status_code == 200, saved.text
            return saved.json()

        def redraw(work, at):
            preview = client.post("/api/render-score", json={
                "input": work["input"], "ddl": work["ddl"], "score": work["score"], "canvas_aspect": "hd_monitor",
                "render_seed": 77, "composition_seed": 17, "work_id": work["id"], "replay_saved_work": True,
            }, headers=headers)
            assert preview.status_code == 200, preview.text
            saved = client.post("/api/history", json={
                "input": work["input"], "score": work["score"], "at": at, "save_artifacts": False,
                "lineage_parent_node_id": work["lineage_node_id"], "derivation_kind": "replay",
                "replay_work_id": work["id"], "replay_render_hash": preview.json()["render_hash"],
                "replay_svg_sha256": preview.json()["svg_sha256"],
            }, headers=headers)
            assert saved.status_code == 200, saved.text
            return saved.json()

        # The child 5173 refused: the same instructions, and now the record.
        colored = save(parent["lineage_node_id"], "color_arrangement_change", {"color_arrangement_index": 0}, 2)
        assert colored["ddl"] == source and record_of(colored["id"]) == LAWS
        layout = client.post("/api/compose", json={"work_id": colored["id"], "ddl": colored["ddl"],
                             "recompose_mode": "principled"}, headers=headers)
        assert layout.status_code == 200, layout.text
        recomposition = layout.json()["recomposition"]
        assert recomposition.get("reason") != "unsupported_sentence", recomposition
        assert all(move["layer"] != 0 for move in recomposition["moves"]), recomposition

        grounded = save(parent["lineage_node_id"], "ground_change", {"ground_material": "washi"}, 3)
        assert RECORDED in grounded["ddl"] and record_of(grounded["id"]) == LAWS

        # The touch written into the recorded sentence is written into the record.
        touched = save(parent["lineage_node_id"], "tool_change", {"tool_mode": "per_sentence", "tools": {"0": "chalk"}}, 4)
        rewritten = RECORDED.replace("細筆", "チョーク")
        assert rewritten in touched["ddl"]
        assert record_of(touched["id"]) == {**LAWS, "layers": [{**LAWS["layers"][0], "sentences": [rewritten]}]}

        # A child of such a child reads the record on its parent's edge.
        regrounded = save(colored["lineage_node_id"], "ground_change", {"ground_material": "washi"}, 5)
        assert record_of(regrounded["id"]) == LAWS

        # A redraw keeps it: in its link for a linked work, on its edge for the others.
        assert store.read_linked_history(user["id"], redraw(parent, 6)["id"]).laws_layers == LAWS
        assert record_of(redraw(colored, 7)["id"]) == LAWS

        # A sender cannot name one, even on a kind whose edge carries it.
        named = client.post("/api/history", json={
            "input": "", "ddl": source, "score": score, "at": 8, "save_artifacts": False,
            "render_seed": 77, "composition_seed": 17, "catalog_id": "default",
            "lineage_parent_node_id": parent["lineage_node_id"], "derivation_kind": "replay",
            "derivation_metadata": {"laws_layers": LAWS},
        }, headers=headers)
        assert named.status_code == 200, named.text
        assert "laws_layers" not in named.json()["derivation_metadata"]
        assert record_of(named.json()["id"]) is None
    finally:
        db.delete_session(token)
        db.delete_user(user["id"], cascade=True)
        db.delete_user_group(group["id"])
