"""Database maintenance is explicit and preserves durable authoring data."""

import hashlib
import json
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.api_core.deps import _admin_user
from inku_server.api_core.routers.settings import router
from inku_server.persistence.schema import Base, HistoryRow, PipelineCandidateExecutionRow, PipelineHistoryLinkRow, ProviderObservationRow


def test_vacuum_requires_admin_and_blocks_writes(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'vacuum.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(db, "database_info", lambda: {"file_size_bytes": (tmp_path / 'vacuum.db').stat().st_size})
    observed = []
    @event.listens_for(engine, "before_cursor_execute")
    def inspect(_conn, _cursor, statement, *_):
        if statement.strip().upper() == "VACUUM":
            observed.append(client.post('/write').status_code)
    app = FastAPI()
    from inku_server.security import DbWriteLockMiddleware
    app.add_middleware(DbWriteLockMiddleware, is_locked=lambda: db.database_write_block_reason() is not None,
                       exempt_paths=frozenset())
    @app.post('/write')
    def write():
        return {"ok": True}
    app.include_router(router)
    def denied():
        raise HTTPException(403, "forbidden")
    app.dependency_overrides[_admin_user] = denied
    client = TestClient(app)
    assert client.post('/api/settings/database/vacuum').status_code == 403
    app.dependency_overrides[_admin_user] = lambda: {"id": "admin"}
    response = client.post('/api/settings/database/vacuum')
    assert response.status_code == 200
    assert response.json()["before_bytes"] > 0 and response.json()["after_bytes"] > 0
    assert observed == [503] and not db.db_restoring()
    assert client.post('/write').status_code == 200
    engine.dispose()


def test_retention_default_keeps_everything_and_prunes_only_old_idle(tmp_path, monkeypatch):
    path = tmp_path / "canonical.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(db, "PERSISTENCE_CONFIG", SimpleNamespace(canonical_url=f"sqlite:///{path}"))
    monkeypatch.setattr(db, "database_write_block_reason", lambda: None)
    monkeypatch.delenv("INKU_AUTONOMOUS_RUNS_DB_URL", raising=False)
    old = db._now_ms() - 3 * 86400000
    from inku_server.autonomous_refine import RunStore, AutonomousRunRow
    runs = RunStore(f"sqlite:///{tmp_path / 'canonical-autonomous-runs.db'}")
    for run_id, state in (("done", "done"), ("running", "running")):
        runs.save({"id": run_id, "owner_id": "u", "history_id": "work", "state": state,
                   "settings": {}, "turns": [], "created_at": old})
    with runs._sessions.begin() as session:
        for row in session.query(AutonomousRunRow).all():
            row.updated_at = old
    def execution(name, action, updated):
        data = json.dumps({"snapshot": {"action": action}}).encode()
        return PipelineCandidateExecutionRow(owner_id="u", execution_id=name, variation_id="v", sequence="0",
            state_bytes=data, state_digest=hashlib.sha256(data).hexdigest(), created_at=old, updated_at=updated)
    with db.SessionLocal.begin() as session:
        session.add(HistoryRow(id="work", at=1, input="", svg="<svg/>"))
        session.add(PipelineHistoryLinkRow(owner_id="u", history_id="work", variation_id="v", revision="1",
            ddl_digest="digest", fork_context_bytes=b"data", fork_context_digest="digest"))
        session.add_all([execution("old-idle", None, old), execution("old-busy", {"tag": "work"}, old),
                         execution("new-idle", None, db._now_ms())])
        for execution_id in ("old-idle", "old-busy"):
            session.add(ProviderObservationRow(owner_id="u", execution_id=execution_id, action_id="a", request_digest="d",
                action_tag="action", stage="stage1", provider_id="p", model="m", attempt=1, timeout_ms=1,
                request_body="{}", outcome="completed", capture_complete=False, created_at=old, updated_at=old))
    assert db.database_maintenance_settings()["retention_days"] is None
    assert db.prune_execution_records(None) == {"executions": 0, "observations": 0, "autonomous": 0}
    assert db.prune_execution_records(1) == {"executions": 1, "observations": 1, "autonomous": 1}
    with db.SessionLocal() as session:
        assert set(session.scalars(select(PipelineCandidateExecutionRow.execution_id))) == {"old-busy", "new-idle"}
        assert session.get(HistoryRow, "work") and session.get(PipelineHistoryLinkRow, ("u", "work"))
        assert set(session.scalars(select(ProviderObservationRow.execution_id))) == {"old-busy"}
    assert runs.get("u", "done") is None and runs.get("u", "running") is not None
    runs.engine.dispose()
    engine.dispose()
