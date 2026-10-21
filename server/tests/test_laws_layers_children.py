"""Native gate: a laws work's children drawn without a run keep its laws record (2026-10-20).

Changing the color arrangement, the support or the touches, and redrawing, draw the child from its
parent and save it without a run, so nothing linked the child to its parent's laws record. "Change
the layout" then read the laws' numeric sentences without the record and refused the child
(`unsupported_sentence`, seen on 5173 Build 1292). The child now keeps the record on its lineage
edge (a redraw of a linked work, in its link), a touch written into a recorded sentence is written
into the record too, and a sender cannot name a record. A catalog change child, which the screen
saves as drawn with its parent's instructions, keeps the records too (2026-10-21; until then it
kept none, and its layout and laws move answered `unsupported_sentence` on 5173 Build 1303).

The basis of the laws (the composed document and answer they were applied by) goes the same way,
so that the AI refinement's laws move reads it from any of them; a direct-DDL run gives it back
as it came (2026-10-20).
"""

import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.color_catalogs import color_catalogs, render_color_map_for_catalog
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import saved_work_parent
from inku_server.pipeline_candidate import CandidateExecution, PipelineBinding
from inku_server.pipeline_defaults import default_manifest
from inku_server.pipeline_product import ProductPipelineEffects

RECORDED = "画面の横0.618034、縦0.618034の位置に、灰の細い細筆の程よい空の縦長の小さな楕円を1個置く。"
SOURCE = f"背景を白で埋める。\n{RECORDED}\n上半分（横0〜1、縦0〜1/2）に、青の細筆の線を3個並べる。"
LAWS = {"schema": "inku.laws-layers.v1", "layers": [{"sentences": [RECORDED], "kind": "laws", "laws": ["B1"]}]}
BASIS = {"schema": "inku.laws-basis.v1",
         "composed": SOURCE.replace("画面の横0.618034、縦0.618034の位置に", "画面の中ほどに"),
         "committed_digest": hashlib.sha256(SOURCE.encode()).hexdigest(), "main_layer": 0, "main_law": "B1",
         "laws": {"B1": {"targets": [{"layer": 0, "at": "point_lr"}]}}, "reason": "The grey ellipse leads."}
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
        # A direct-DDL run takes the records as a fork of a laws work does, and keeps them.
        run.start_new({"tag": "direct_ddl", "source": SOURCE, "laws_layers": LAWS, "laws_basis": BASIS})
        run.run_effect()
        snapshot = run.snapshot()
        assert snapshot["phase"]["tag"] == "score_ready"
        assert (snapshot["laws_layers"], snapshot["laws_basis"]) == (LAWS, BASIS)
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

        def basis_of(work_id):
            return saved_work_parent(store, user["id"], work_id)[1].get("laws_basis")

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
        assert colored["ddl"] == source and record_of(colored["id"]) == LAWS and basis_of(colored["id"]) == BASIS
        layout = client.post("/api/compose", json={"work_id": colored["id"], "ddl": colored["ddl"],
                             "recompose_mode": "principled"}, headers=headers)
        assert layout.status_code == 200, layout.text
        recomposition = layout.json()["recomposition"]
        assert recomposition.get("reason") != "unsupported_sentence", recomposition
        assert all(move["layer"] != 0 for move in recomposition["moves"]), recomposition

        # The layout child is saved as sent, as the screen saves it, and keeps the
        # parent's records on its edge, so that the layout can change again.
        laid = client.post("/api/history", json={
            "input": "", "ddl": layout.json()["ddl"], "score": layout.json()["score"], "at": 9,
            "save_artifacts": False, "render_seed": 77, "composition_seed": 17, "catalog_id": "default",
            "lineage_parent_node_id": colored["lineage_node_id"], "derivation_kind": "layout_change",
            "derivation_metadata": {"composition_seed": 17, "recompose_mode": "principled"},
        }, headers=headers)
        assert laid.status_code == 200, laid.text
        assert record_of(laid.json()["id"]) == LAWS and basis_of(laid.json()["id"]) == BASIS
        again = client.post("/api/compose", json={"work_id": laid.json()["id"], "ddl": laid.json()["ddl"],
                            "recompose_mode": "principled"}, headers=headers)
        assert again.status_code == 200, again.text
        assert again.json()["recomposition"].get("reason") != "unsupported_sentence", again.json()["recomposition"]

        # The basis keeps the parent's digest, by which the laws move stops on the new DDL.
        grounded = save(parent["lineage_node_id"], "ground_change", {"ground_material": "washi"}, 3)
        assert RECORDED in grounded["ddl"] and record_of(grounded["id"]) == LAWS and basis_of(grounded["id"]) == BASIS

        # The touch written into the recorded sentence is written into the record.
        touched = save(parent["lineage_node_id"], "tool_change", {"tool_mode": "per_sentence", "tools": {"0": "chalk"}}, 4)
        rewritten = RECORDED.replace("細筆", "チョーク")
        assert rewritten in touched["ddl"]
        assert record_of(touched["id"]) == {**LAWS, "layers": [{**LAWS["layers"][0], "sentences": [rewritten]}]}
        assert basis_of(touched["id"]) == BASIS

        # A child of such a child reads the records on its parent's edge.
        regrounded = save(colored["lineage_node_id"], "ground_change", {"ground_material": "washi"}, 5)
        assert record_of(regrounded["id"]) == LAWS and basis_of(regrounded["id"]) == BASIS

        # A redraw keeps them: in its link for a linked work, on its edge for the others.
        relinked = store.read_linked_history(user["id"], redraw(parent, 6)["id"])
        assert (relinked.laws_layers, relinked.laws_basis) == (LAWS, BASIS)
        redrawn = redraw(colored, 7)
        assert record_of(redrawn["id"]) == LAWS and basis_of(redrawn["id"]) == BASIS

        # A catalog change draws the parent's Score in another catalog, as the screen does
        # (/api/render-score, then the save with that Score). The instructions are the same,
        # so the parent's records hold, in place of any the sender names.
        other = next(entry["id"] for entry in color_catalogs() if entry["id"] != "default")
        recolored = client.post("/api/render-score", json={
            "input": "a grey ellipse", "ddl": source, "score": score, "canvas_aspect": "hd_monitor",
            "render_seed": 77, "composition_seed": 17, "catalog_id": other,
        }, headers=headers)
        assert recolored.status_code == 200, recolored.text
        cataloged = client.post("/api/history", json={
            "input": "a grey ellipse", "ddl": source, "score": recolored.json()["score"], "at": 10,
            "save_artifacts": False, "render_seed": 77, "composition_seed": 17, "catalog_id": other,
            "lineage_parent_node_id": parent["lineage_node_id"], "derivation_kind": "catalog_change",
            "derivation_metadata": {"catalog_id_from": "default", "catalog_id_to": other,
                                    "laws_layers": {**LAWS, "layers": []}},
        }, headers=headers)
        assert cataloged.status_code == 200, cataloged.text
        assert record_of(cataloged.json()["id"]) == LAWS and basis_of(cataloged.json()["id"]) == BASIS
        recataloged = client.post("/api/compose", json={"work_id": cataloged.json()["id"],
                                  "ddl": cataloged.json()["ddl"], "recompose_mode": "principled"}, headers=headers)
        assert recataloged.status_code == 200, recataloged.text
        recomposition = recataloged.json()["recomposition"]
        assert recomposition.get("reason") != "unsupported_sentence", recomposition
        assert all(move["layer"] != 0 for move in recomposition["moves"]), recomposition

        # A sender cannot name one, even on a kind whose edge carries it.
        named = client.post("/api/history", json={
            "input": "", "ddl": source, "score": score, "at": 8, "save_artifacts": False,
            "render_seed": 77, "composition_seed": 17, "catalog_id": "default",
            "lineage_parent_node_id": parent["lineage_node_id"], "derivation_kind": "replay",
            "derivation_metadata": {"laws_layers": LAWS, "laws_basis": BASIS},
        }, headers=headers)
        assert named.status_code == 200, named.text
        assert not {"laws_layers", "laws_basis"} & set(named.json()["derivation_metadata"])
        assert record_of(named.json()["id"]) is None and basis_of(named.json()["id"]) is None
    finally:
        db.delete_session(token)
        db.delete_user(user["id"], cascade=True)
        db.delete_user_group(group["id"])
