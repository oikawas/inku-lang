"""A replay child saves the authorized source's exact current performance."""

import json
import uuid
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.persistence.schema import HistoryRow
from inku_server.api import app
from inku_server.color_catalogs import render_color_map_for_catalog
from inku_server.limits import DEFAULT_LIMITS, limits_as_dict
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_candidate import CandidateExecution, PipelineBinding
from inku_server.pipeline_defaults import default_manifest
from inku_server.pipeline_product import ProductPipelineEffects


def test_replay_child_matches_preview_and_rejects_unbound_source(monkeypatch):
    from inku_server.api_core import common, rendering

    monkeypatch.setattr(rendering, "_submit_thumbnail_build", lambda _item: None)
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"replay-{suffix}")
    user = db.add_user(username=f"replay-{suffix}", email=f"replay-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    other = db.add_user(username=f"other-{suffix}", email=f"other-{suffix}@example.test",
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
                {"instruction_lang": "ja", "catalog_id": "default", "render_seed": 0}, None)
        execution = CandidateExecution(binding, VariationAuthorityStore(db.engine), owner_id=user["id"],
            config=config, context=context, provider=lambda _action: pytest.fail("replay called a provider"))
        execution.start_new({"tag": "direct_ddl", "source": source})
        execution.run_effect()
        snapshot = execution.snapshot()
        assert snapshot["phase"]["tag"] == "score_ready"
        compact = snapshot["delivery"]["score"]
        flat = {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
        wide_seed = (1 << 127) - 1
        limits = {**limits_as_dict(DEFAULT_LIMITS), "represented_count_max": 31}
        cases = [(compact, 0), (flat, wide_seed), (flat, None)]
        for index, (score, seed) in enumerate(cases):
            initial = {
                "id": str(uuid.uuid4()), "user_id": user["id"], "at": index + 1,
                "input": "saved leaves", "ddl": source, "source_text": "original description",
                "score": score, "svg": "<svg>old saved picture</svg>",
                "render_color_map": render_color_map_for_catalog("default"),
                "catalog_id": "retired-replay-palette", "render_color_catalog_id": "retired-replay-palette",
                "render_color_catalog_name": "Recorded palette", "render_color_catalog_sub": "saved",
                "render_seed": seed, "composition_seed": wide_seed, "interpretation_seed": "reading",
                "render_wild": True, "render_limits": limits, "render_canvas_aspect_id": "square",
                "stage1_model": "recorded-model", "stage1_prompt_digest": "recorded-prompt",
                "sketch_text": "recorded sketch", "sketch_state": "fine",
            }
            parent = db.add_item(initial)
            # Only a work saved before 2026-09-14 holds a prompt digest; seed one.
            with db.SessionLocal() as session:
                session.query(HistoryRow).filter_by(id=parent["id"]).update({"stage1_prompt_digest": "recorded-prompt"})
                session.commit()
            parent = db.get_items(user["id"], [parent["id"]])[0]
            preview_response = client.post("/api/render-score", json={
                "work_id": parent["id"], "score": parent["score"], "input": parent["input"], "ddl": parent["ddl"],
                "render_seed": seed if seed is not None else 0, "composition_seed": wide_seed,
                "wild": True, "interpretation_seed": "reading",
            }, headers=headers)
            assert preview_response.status_code == 200, preview_response.text
            preview = preview_response.json()
            assert preview["svg_sha256"] == sha256(preview["svg"].encode()).hexdigest()
            payload = {
                "input": "untrusted input", "ddl": "untrusted DDL", "score": {}, "svg": "<svg>untrusted</svg>",
                "at": 10 + index, "save_artifacts": False, "catalog_id": "untrusted palette",
                "render_seed": 999, "composition_seed": 999, "render_wild": False,
                "render_color_map": {"black": "#123456"}, "history_visibility": "lineage_only",
                "lineage_parent_node_id": parent["lineage_node_id"], "derivation_kind": "replay",
                "replay_work_id": parent["id"], "replay_render_hash": preview["render_hash"],
                "replay_svg_sha256": preview["svg_sha256"],
            }
            save_headers = {**headers, "Idempotency-Key": f"replay-{suffix}-{index}"}
            saved = client.post("/api/history", json=payload, headers=save_headers)
            assert saved.status_code == 200, saved.text
            child = saved.json()
            assert child["id"] != parent["id"]
            assert child["svg"] == preview["svg"]
            for key in ("score", "render_seed", "composition_seed", "render_wild", "render_color_map",
                        "render_limits", "render_hash", "render_engine_version"):
                assert child[key] == preview[key], key
            assert child["render_seed"] == str(seed if seed is not None else 0)
            assert child["composition_seed"] == str(wide_seed)
            for key in ("input", "ddl", "source_text", "stage1_model", "sketch_text"):
                assert child[key] == parent[key], key
            # The retired prompt digests stay on the parent and are not copied on.
            assert parent["stage1_prompt_digest"] == "recorded-prompt"
            assert child.get("stage1_prompt_digest") is None
            assert child["interpretation_seed"] == "reading"
            assert child["history_visibility"] == "normal"
            assert child["lineage_parent_node_id"] == parent["lineage_node_id"]
            assert child["derivation_kind"] == "replay"
            assert db.get_items(user["id"], [parent["id"]])[0] == parent
            repeated = client.post("/api/history", json=payload, headers=save_headers)
            assert repeated.status_code == 200, repeated.text
            assert repeated.json()["id"] == child["id"]
            lineage = db.get_lineage(user["id"], child["lineage_node_id"])
            assert len(lineage["edges"]) == 1
            if index == 0:
                before = db.list_state(user["id"])
                for field, wrong in (("replay_render_hash", "rh3:" + "0" * 64),
                                     ("replay_svg_sha256", "0" * 64)):
                    rejected = client.post("/api/history", json={**payload, field: wrong}, headers=headers)
                    assert rejected.status_code == 409, rejected.text
                mismatch = client.post("/api/history", json={**payload, "lineage_parent_node_id": "wrong"}, headers=headers)
                assert mismatch.status_code == 422, mismatch.text
                foreign = db.add_item({**initial, "id": str(uuid.uuid4()), "user_id": other["id"]})
                denied = client.post("/api/history", json={**payload, "replay_work_id": foreign["id"],
                    "lineage_parent_node_id": foreign["lineage_node_id"]}, headers=headers)
                assert denied.status_code == 404, denied.text
                assert db.list_state(user["id"]) == before
    finally:
        db.delete_session(token)
        db.delete_user(user["id"], cascade=True)
        db.delete_user(other["id"], cascade=True)
        db.delete_user_group(group["id"])


def test_managed_replay_child_replays_its_inherited_saved_policy(monkeypatch):
    from inku_server.api_core import common, rendering

    monkeypatch.setattr(rendering, "_submit_thumbnail_build", lambda _item: None)
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"managed-{suffix}")
    user = db.add_user(username=f"managed-{suffix}", email=f"managed-{suffix}@example.test",
                       password="password-123", permission_groups=["users"], group_id=group["id"])
    guest = db.add_user(username=f"guest-{suffix}", email=f"guest-{suffix}@example.test",
                        password="password-123", permission_groups=["users"], group_id=group["id"])
    token, guest_token = db.create_session(user["id"]), db.create_session(guest["id"])
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(app)
    try:
        binding = PipelineBinding()
        effects = ProductPipelineEffects(binding, default_manifest(binding))
        source = "Nature.青葉。"
        with monkeypatch.context() as preparation:
            preparation.setattr(common, "_model_offered_to", lambda *args, **kwargs: True)
            config, context = effects.prepare(user["id"], "direct_ddl", source,
                {"instruction_lang": "ja", "catalog_id": "default", "render_seed": 0}, None)
        store = VariationAuthorityStore(db.engine)
        execution = CandidateExecution(binding, store, owner_id=user["id"], config=config,
            context=context, provider=lambda _action: pytest.fail("replay called a provider"))
        execution.start_new({"tag": "direct_ddl", "source": source})
        execution.run_effect()
        snapshot = execution.snapshot()
        assert snapshot["phase"]["tag"] == "score_ready"
        parent = db.add_item({
            "id": str(uuid.uuid4()), "user_id": user["id"], "at": 1, "input": "managed leaves",
            "ddl": source, "score": snapshot["delivery"]["score"], "svg": "<svg/>",
            "render_seed": 0, "seed_text": "   ", "render_wild": True, "composition_seed": 17,
            "render_color_map": render_color_map_for_catalog("default"),
            "render_color_catalog_id": "default", "render_limits": limits_as_dict(DEFAULT_LIMITS),
        })
        store.link_history(user["id"], parent["id"], snapshot["variation_id"],
            snapshot["authority"]["revision"], snapshot["delivery"]["source_digest"],
            snapshot=snapshot, context=context, pipeline_diagnostics={
                **{key: snapshot["delivery"][key] for key in (
                    "upstream_diagnostics", "downstream_diagnostics", "resource_omissions", "relation_omissions",
                )}, "render_diagnostics": None, "resource_execution": None,
            })
        parent = db.get_items(user["id"], [parent["id"]])[0]
        request = {"work_id": parent["id"], "score": parent["score"], "render_seed": 0,
                   "composition_seed": 17, "wild": True}
        # JavaScript JSON.stringify emits whole-valued floats as integers.
        browser_score = json.loads(json.dumps(parent["score"]), parse_float=lambda text:
            int(float(text)) if float(text).is_integer() else float(text))
        assert json.dumps(browser_score, sort_keys=True) != json.dumps(parent["score"], sort_keys=True)
        browser_request = {**request, "score": browser_score}
        response = client.post("/api/render-score", json=browser_request, headers=headers)
        assert response.status_code == 200, response.text
        browser_preview = response.json()
        assert browser_preview["render_seed"] == "0"
        payload = {"input": "ignored", "score": {}, "at": 2, "save_artifacts": False,
            "derivation_kind": "replay", "lineage_parent_node_id": parent["lineage_node_id"],
            "replay_work_id": parent["id"], "replay_render_hash": browser_preview["render_hash"],
            "replay_svg_sha256": browser_preview["svg_sha256"]}
        before = db.list_state(user["id"])
        incompatible = client.post("/api/history", json=payload, headers=headers)
        assert incompatible.status_code == 409, incompatible.text
        assert db.list_state(user["id"]) == before
        response = client.post("/api/render-score", json={**browser_request, "replay_saved_work": True}, headers=headers)
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["score"] == parent["score"]
        assert json.dumps(preview["score"], sort_keys=True) == json.dumps(parent["score"], sort_keys=True)
        assert preview["render_seed"] == "0" and preview["composition_seed"] == "17"
        assert preview["render_wild"] is True and preview["render_canvas_aspect_id"] == "square"
        payload.update(replay_render_hash=preview["render_hash"], replay_svg_sha256=preview["svg_sha256"])
        for field, wrong in (("replay_render_hash", "rh3:" + "0" * 64), ("replay_svg_sha256", "0" * 64)):
            modified = client.post("/api/history", json={**payload, field: wrong}, headers=headers)
            assert modified.status_code == 409, modified.text
        assert db.list_state(user["id"]) == before
        saved = client.post("/api/history", json=payload, headers=headers)
        assert saved.status_code == 200, saved.text
        child = saved.json()
        assert child["svg"] == preview["svg"]
        assert child["lineage_parent_node_id"] == parent["lineage_node_id"]
        assert db.get_items(user["id"], [parent["id"]])[0] == parent
        assert child["pipeline_variation_id"] == parent["pipeline_variation_id"]
        assert child["pipeline_revision"] == parent["pipeline_revision"]
        assert child["pipeline_diagnostics"]["render_diagnostics"] == preview["render_diagnostics"]
        replay = client.post("/api/render-score", json={**request, "work_id": child["id"],
            "score": child["score"]}, headers=headers)
        assert replay.status_code == 200, replay.text
        assert replay.json()["svg"] == child["svg"] == preview["svg"]
        db.grant_history_acl(user["id"], parent["id"], "user", guest["id"], "read")
        assert db.get_items(guest["id"], [parent["id"]])
        before = db.list_state(guest["id"])
        rejected = client.post("/api/history", json=payload,
            headers={"Authorization": f"Bearer {guest_token}"})
        assert rejected.status_code == 409, rejected.text
        assert db.list_state(guest["id"]) == before
    finally:
        db.delete_session(token)
        db.delete_session(guest_token)
        db.delete_user(user["id"], cascade=True)
        db.delete_user(guest["id"], cascade=True)
        db.delete_user_group(group["id"])
