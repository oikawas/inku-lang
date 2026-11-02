"""Live activity must not disclose another owner's runs or claim batch idleness."""

import json
import runpy
import threading
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from inku_server import db
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.persistence.schema import AppSettingRow
from inku_server.pipeline_api import PipelineService, pipeline_router
from inku_server.pipeline_candidate import PipelineBinding


def test_activity_observes_running_batch_and_enforces_scope(tmp_path, monkeypatch):
    config = runpy.run_path(str(Path(__file__).with_name("test_pipeline_candidate.py")))["_fixture_config"]()
    engine = create_engine(f"sqlite:///{tmp_path / 'activity.db'}")
    store = VariationAuthorityStore(engine)
    store.install_schema()
    AppSettingRow.__table__.create(engine)
    started, release = threading.Event(), threading.Event()

    def provider(action):
        started.set()
        assert release.wait(5)
        return {"tag": "normalized_ddl_generated", "identity": action["identity"],
                "response": json.dumps({"normalized_ddl": "place one black circle at center."}), "elapsed_ms": "1"}

    service = PipelineService(PipelineBinding(), store, config_for=lambda *_: config,
        provider_for=lambda _: provider, render_for=None, max_workers=1, max_effect_steps=16,
        max_retained_runs=4, prepare_for=lambda _owner, _kind, _text, options, _source:
        (config, {"host_options": options}))
    app = FastAPI()
    def actor(x_owner: str = Header(...)):
        return {"id": x_owner}
    app.include_router(pipeline_router(service, actor))
    monkeypatch.setattr(db, "has_permission_group", lambda actor, group: actor["id"] == "admin" and group == "admins")
    try:
        with TestClient(app) as client:
            response = client.post("/api/pipeline/variations", headers={"X-Owner": "alice"}, json={
                "kind": "description", "text": "One quiet black circle",
                "options": {"batch_run_id": "batch-1", "batch_line_number": 2},
            })
            assert response.status_code == 200, response.text
            assert started.wait(5)
            mine = client.get("/api/pipeline/activity", headers={"X-Owner": "alice"}).json()
            assert mine["scope"] == "current_user" and mine["batch_waiting_known"] is False
            assert [(row["batch_run_id"], row["batch_line_number"], row["state"]) for row in mine["executions"]] == [("batch-1", 2, "running")]
            assert mine["render_slots_active"] is None
            assert client.get("/api/pipeline/activity", headers={"X-Owner": "bob"}).json()["executions"] == []
            assert client.get("/api/pipeline/activity?all_users=true", headers={"X-Owner": "bob"}).status_code == 403
            global_view = client.get("/api/pipeline/activity?all_users=true", headers={"X-Owner": "admin"}).json()
            assert len(global_view["executions"]) == 1
            assert isinstance(global_view["render_slots_active"], int)
            run = service.execution("alice", response.json()["execution_id"])
            release.set()
            service._jobs[("alice", response.json()["execution_id"])].result(timeout=5)
            assert client.get("/api/pipeline/activity", headers={"X-Owner": "alice"}).json()["executions"] == []
            with run._track_render():
                assert client.get("/api/pipeline/activity", headers={"X-Owner": "alice"}).json()["executions"][0]["state"] == "rendering"
            response = client.post("/api/pipeline/batches", headers={"X-Owner": "alice"}, json={
                "run_id": "tracked", "kind": "web", "total": 2, "prompt": "first\nsecond", "conditions": {},
            })
            assert response.status_code == 200
            lease = response.json()["lease"]
            status = client.get("/api/pipeline/activity", headers={"X-Owner": "alice"}).json()["batches"]
            assert status[0]["total"] == 2 and status[0]["state"] == "running"
            assert "prompt" not in status[0] and "lease" not in status[0]
            assert client.get("/api/pipeline/batches", headers={"X-Owner": "bob"}).json()["batches"] == []
            heartbeat = client.post("/api/pipeline/batches/tracked/heartbeat", headers={"X-Owner": "alice"},
                                    json={"lease": lease, "completed": 1, "state": "running"})
            assert heartbeat.status_code == 200
            assert client.get("/api/pipeline/batches", headers={"X-Owner": "alice"}).json()["batches"][0]["completed"] == 1
    finally:
        release.set()
        service.close()
        engine.dispose()
