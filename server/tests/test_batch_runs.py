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
