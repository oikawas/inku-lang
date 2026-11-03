import pytest
import threading
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import create_engine

from inku_server.persistence import batch_runs
from inku_server.persistence.batch_runs import BatchRuns
from inku_server.persistence.schema import AppSettingRow


def test_expired_batch_can_resume_only_after_active_draw_finishes_and_fences_old_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'batch.db'}")
    AppSettingRow.__table__.create(engine)
    clock = [1000.0]
    monkeypatch.setattr(batch_runs.time, "time", lambda: clock[0])
    registry = BatchRuns(engine)
    body = {"run_id": "run-1", "kind": "web", "total": 3, "prompt": "one\ntwo\nthree", "conditions": {}}
    first = registry.start("alice", body, set())["lease"]
    registry.update("alice", "run-1", first, 1, "running")
    assert registry.list("bob", set()) == []
    clock[0] += 91
    assert registry.list("alice", {"run-1"})[0]["state"] == "uncertain"
    with pytest.raises(HTTPException) as blocked:
        registry.start("alice", body, {"run-1"})
    assert blocked.value.status_code == 409
    assert registry.list("alice", set())[0]["state"] == "lease_expired"
    second = registry.start("alice", body, set())["lease"]
    assert first != second
    with pytest.raises(HTTPException):
        registry.require("alice", "run-1", first)
    with pytest.raises(HTTPException):
        registry.update("alice", "run-1", first, 2, "running")
    registry.require("alice", "run-1", second)
    from inku_server.pipeline_compat import _start_batch_guarded
    service = SimpleNamespace(_lock=threading.RLock(), store=SimpleNamespace(engine=engine))
    with pytest.raises(HTTPException):
        _start_batch_guarded(service, "alice", {"batch_run_id": "run-1", "batch_lease": first}, lambda: {"started": True})
    assert _start_batch_guarded(service, "alice", {"batch_run_id": "run-1", "batch_lease": second}, lambda: {"started": True}) == {"started": True}
    registry.update("alice", "run-1", second, 3, "completed")
    assert registry.list("alice", set())[0]["state"] == "completed"
    with pytest.raises(HTTPException):
        registry.start("alice", body, set())
    engine.dispose()


def test_finished_with_failures_is_durable_validated_and_resumable(tmp_path, monkeypatch):
    from inku_server.pipeline_api import BatchUpdateBody

    engine = create_engine(f"sqlite:///{tmp_path / 'finished.db'}")
    AppSettingRow.__table__.create(engine)
    clock = [1000.0]
    monkeypatch.setattr(batch_runs.time, "time", lambda: clock[0])
    registry = BatchRuns(engine)
    body = {"run_id": "run-1", "kind": "web", "total": 3, "prompt": "one\ntwo\nthree", "conditions": {}}
    lease = registry.start("alice", body, set())["lease"]
    assert BatchUpdateBody(lease=lease, completed=2, state="finished_with_failures").state == "finished_with_failures"
    with pytest.raises(HTTPException) as full:
        registry.update("alice", "run-1", lease, 3, "finished_with_failures")
    assert (full.value.status_code, full.value.detail) == (422, "batch_has_no_failures")
    registry.update("alice", "run-1", lease, 2, "finished_with_failures")
    clock[0] += 1000
    assert registry.list("alice", set())[0]["state"] == "finished_with_failures"
    assert registry.list("alice", {"run-1"})[0]["state"] == "uncertain"
    resumed = registry.start("alice", body, set())["lease"]
    assert registry.list("alice", set())[0]["completed"] == 2
    registry.update("alice", "run-1", resumed, 3, "running")
    with pytest.raises(HTTPException) as previous_full:
        registry.update("alice", "run-1", resumed, 2, "finished_with_failures")
    assert previous_full.value.detail == "batch_has_no_failures"
    registry.update("alice", "run-1", resumed, 3, "completed")
    engine.dispose()
