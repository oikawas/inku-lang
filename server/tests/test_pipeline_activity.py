"""Live activity must not disclose another owner's runs or claim batch idleness."""

import json
import runpy
import threading
from types import SimpleNamespace

import pytest
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from inku_server import db
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.persistence.schema import AppSettingRow
from inku_server.pipeline_api import PipelineService, pipeline_router
from inku_server.pipeline_candidate import PipelineBinding
from inku_server.autonomous_refine import AutonomousRunner, RunStore


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
    runner = AutonomousRunner(RunStore(f"sqlite:///{tmp_path / 'runs.db'}"))
    def actor(x_owner: str = Header(...)):
        return {"id": x_owner}
    app.include_router(pipeline_router(service, actor, autonomous_runner_for=lambda: runner))
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
        runner.close()
        engine.dispose()


@pytest.fixture
def activity_host(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'activity.db'}")
    AppSettingRow.__table__.create(engine)
    runner = AutonomousRunner(RunStore(f"sqlite:///{tmp_path / 'autonomous.db'}"))
    entries = []
    service = SimpleNamespace(store=SimpleNamespace(engine=engine), activity=lambda owner: [
        {key: value for key, value in row.items() if key != "owner"}
        for row in entries if owner is None or row["owner"] == owner])
    app = FastAPI()
    def actor(x_owner: str = Header(...)):
        return {"id": x_owner}
    app.include_router(pipeline_router(lambda: service, actor, autonomous_runner_for=lambda: runner))
    monkeypatch.setattr(db, "has_permission_group", lambda actor, group: actor["id"] == "admin" and group == "admins")
    with TestClient(app) as client:
        yield client, runner, entries
    runner.close()
    engine.dispose()


def _autonomous(run_id="run-1", owner="alice", created_at=1):
    return {"id": run_id, "owner_id": owner, "history_id": "work-1", "state": "running",
            "settings": {"kinds": ["laws"], "moves": 5, "note": "private note", "model": "private model", "language": "ja", "wild": True},
            "turns": [{"attempts": [{"attempt": 1, "outcome": "kept"}]}], "current": None, "created_at": created_at}


def test_activity_lists_between_moves_for_owner_and_admin(activity_host):
    client, runner, _ = activity_host
    runner.store.save(_autonomous())
    runner.store.save(_autonomous("run-2", "bob", 2))
    mine = client.get('/api/pipeline/activity', headers={'X-Owner': 'alice'}).json()
    assert [run["run_id"] for run in mine["autonomous_runs"]] == ["run-1"]
    assert mine["autonomous_runs"][0]["current"] is None
    theirs = client.get('/api/pipeline/activity', headers={'X-Owner': 'bob'}).json()
    assert [run["run_id"] for run in theirs["autonomous_runs"]] == ["run-2"]
    assert client.get('/api/pipeline/activity?all_users=true', headers={'X-Owner': 'bob'}).status_code == 403
    all_runs = client.get('/api/pipeline/activity?all_users=true', headers={'X-Owner': 'admin'}).json()["autonomous_runs"]
    assert [run["run_id"] for run in all_runs] == ["run-2", "run-1"]


def test_activity_marks_only_the_inflight_child_and_clears_it(activity_host, monkeypatch):
    from inku_server import pipeline_compat
    client, runner, entries = activity_host
    run = _autonomous()
    run["current"] = {"turn": 2, "attempt": 1, "kind": "laws"}
    runner.store.save(run)
    entered, release = threading.Event(), threading.Event()
    def settled(_owner, view, **_kwargs):
        entered.set()
        assert release.wait(5)
        return view
    monkeypatch.setattr(pipeline_compat, "_settled", settled)
    entries.extend([{"owner": "alice", "execution_id": "child"}, {"owner": "alice", "execution_id": "normal"}])
    thread = threading.Thread(target=lambda: runner._settle("alice", lambda: {"execution_id": "child"}, threading.Event(), run_id="run-1"))
    thread.start()
    try:
        assert entered.wait(5)
        activity = client.get('/api/pipeline/activity', headers={'X-Owner': 'alice'}).json()
        assert [(item["execution_id"], item["autonomous_run_id"]) for item in activity["executions"]] == [("child", "run-1"), ("normal", None)]
        assert activity["autonomous_runs"][0]["current"] == run["current"]
    finally:
        release.set()
        thread.join(5)
    assert runner.activity("alice")[1] == {}
    for error in (RuntimeError("failed"), HTTPException(499, detail="stopped")):
        def failed(_owner, _view, **_kwargs):
            raise error
        monkeypatch.setattr(pipeline_compat, "_settled", failed)
        with pytest.raises(Exception):
            runner._settle("alice", lambda: {"execution_id": "child"}, threading.Event(), run_id="run-1")
        assert runner.activity("alice")[1] == {}


@pytest.mark.parametrize("state", ["done", "stopped", "failed", "interrupted"])
def test_activity_omits_finished_runs_and_their_child_marks(activity_host, state):
    client, runner, entries = activity_host
    run = _autonomous()
    runner.store.save(run)
    runner._children["child"] = run["id"]
    entries.append({"owner": "alice", "execution_id": "child"})
    run["state"] = state
    runner.store.save(run)
    result = client.get('/api/pipeline/activity', headers={'X-Owner': 'alice'}).json()
    assert result["autonomous_runs"] == []
    assert result["executions"][0]["autonomous_run_id"] is None


def test_activity_never_exposes_run_private_settings_or_owner(activity_host):
    client, runner, _ = activity_host
    run = _autonomous()
    run["current"] = {"turn": 2, "attempt": 3, "kind": "laws", "note": "private current"}
    runner.store.save(run)
    result = client.get('/api/pipeline/activity?all_users=true', headers={'X-Owner': 'admin'}).json()["autonomous_runs"][0]
    assert set(result) == {"run_id", "history_id", "kinds", "moves", "turns_taken", "current", "stopping", "created_at", "updated_at"}
    assert result["current"] == {"turn": 2, "attempt": 3, "kind": "laws"}
    assert result["turns_taken"] == 1
    assert "private" not in json.dumps(result)
    run["turns"].append({"attempts": [{"attempt": 1, "outcome": "failed"}]})
    runner.store.save(run)
    assert client.get('/api/pipeline/activity', headers={'X-Owner': 'alice'}).json()["autonomous_runs"][0]["turns_taken"] == 1
