import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from inku_server.persistence.schema import Base, HistoryRow, LineageNodeRow, LineageEdgeRow, OkugakiRow
from inku_server.workpack_export import export_workpack


@pytest.fixture
def pack_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    fixture = Path(__file__).resolve().parents[2] / "persistence/fixtures/workpack-minimal.inkupack"
    records = [json.loads(line) for line in fixture.read_text().splitlines()]
    classes = {"history": HistoryRow, "lineage_node": LineageNodeRow, "lineage_edge": LineageEdgeRow}
    with factory.begin() as session:
        for record in records[1:]:
            row = dict(record)
            kind = row.pop("kind")
            if kind in classes:
                row["user_id"] = "owner"
                if kind == "history":
                    row["elapsed_ms"] = row["elapsed_ms"] or 0
                    row["render_wild"] = {"work-0": "1", "work-1": "0", "work-2": None}[row["id"]]
                session.add(classes[kind](**row))
            elif kind == "annotation":
                pass
            elif kind == "colophon":
                for key in ("generated_body", "adopted_body", "signature"):
                    row.pop(key, None)
                row["branch_snapshot_json"] = row.pop("branch_snapshot")
                session.add(OkugakiRow(user_id="owner", **row))
        session.flush()
        annotation = next(row for row in records if row.get("kind") == "annotation")
        work = session.get(HistoryRow, annotation["history_id"])
        work.note, work.for_revision = annotation["note"], annotation["for_revision"]
        session.add(HistoryRow(id="other", user_id="other", at=1, input="", score="{}", svg="<svg/>", elapsed_ms=0))
        session.add(HistoryRow(id="trash", user_id="owner", at=1, input="", score="{}", svg="<svg/>", elapsed_ms=0, trashed=1))
    yield factory, records
    engine.dispose()


def test_fixture_records_and_rejections(pack_db):
    factory, fixture = pack_db
    actor = {"id": "owner", "permission_groups": []}
    data = export_workpack(factory, actor, ["work-0", "work-1", "work-2", "work-1"], app_version="test", build=1)
    if target := os.getenv("INKU_WORKPACK_EVIDENCE"):
        Path(target).write_bytes(data)
    records = [json.loads(line) for line in data.splitlines()]
    assert records[0]["counts"] == fixture[0]["counts"]
    assert [row["kind"] for row in records[1:]] == [row["kind"] for row in fixture[1:]]
    for actual, expected in zip(records[1:], fixture[1:]):
        expected = {k: v for k, v in expected.items() if k not in ("generated_body", "adopted_body", "signature")}
        if expected["kind"] == "history":
            expected["elapsed_ms"] = 0
            expected["render_wild"] = {"work-0": 1, "work-1": 0, "work-2": None}[expected["id"]]
        assert actual == expected
    assert records[1]["render_seed"] == "18446744073709551615"
    assert records[1]["score"] == fixture[1]["score"]
    for rejected in ("trash", "other", "missing"):
        with pytest.raises(LookupError):
            export_workpack(factory, actor, ["work-0", rejected], app_version="test", build=1)
    with factory.begin() as session:
        session.add(OkugakiRow(id="private-colophon", user_id="other", target_node_id="node-0", at=1,
                                model="model", language="ja", body="private"))
    private_check = export_workpack(factory, actor, ["work-0"], app_version="test", build=1)
    assert b"private-colophon" not in private_check


def test_route_returns_attachment(pack_db, monkeypatch):
    from inku_server.api_core.routers import history
    from inku_server.api_core.deps import _current_user

    factory, _ = pack_db
    monkeypatch.setattr(history._db, "SessionLocal", factory)
    app = FastAPI()
    app.include_router(history.router)
    app.dependency_overrides[_current_user] = lambda: {"id": "owner", "permission_groups": []}
    response = TestClient(app).post("/api/history/export-workpack", json={"ids": ["work-0"]})
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('.inkupack"')
    assert json.loads(response.content.splitlines()[0])["counts"]["history"] == 1


def test_export_matches_legacy_fixture_bytes(pack_db, monkeypatch):
    from inku_server import workpack_export

    factory, _ = pack_db
    # Timestamp and SHA-256 from the pre-core fixture export on 2026-11-20.
    monkeypatch.setattr(workpack_export.time, "time", lambda: 1795132150.761)
    with factory.begin() as session:
        session.get(HistoryRow, "work-0").note = " \t "
        annotated = session.get(HistoryRow, "work-1")
        annotated.note = " \t" + annotated.note + "\n "
    data = export_workpack(factory, {"id": "owner", "permission_groups": []},
                           ["work-0", "work-1", "work-2"], app_version="test", build=1)
    assert hashlib.sha256(data).hexdigest() == "aa0c6918c9252d46ebf8cf3b823d65df6c1f3788f3917f287652621578522eb7"


def test_limits_and_nonfinite_values_are_refused(pack_db, monkeypatch):
    import inku_render
    from inku_server import workpack_export

    factory, _ = pack_db
    actor = {"id": "owner", "permission_groups": []}
    with monkeypatch.context() as patch:
        patch.setattr(inku_render, "pipeline_workpack_encode_line", lambda _: {
            "line": None, "error": b'{"outcome":"refused","code":"too_large","reason":"too_large"}',
        })
        with pytest.raises(ValueError, match="64 MiB"):
            export_workpack(factory, actor, ["work-0"], app_version="test", build=1)
    monkeypatch.setattr(workpack_export, "MAX_PACK", 32)
    with pytest.raises(ValueError, match="256 MiB"):
        export_workpack(factory, actor, ["work-0"], app_version="test", build=1)
    monkeypatch.setattr(workpack_export, "MAX_PACK", 256 * 1024 * 1024)
    with factory.begin() as session:
        session.get(HistoryRow, "work-0").render_canvas_aspect_ratio = float("inf")
    with pytest.raises(ValueError, match="invalid value"):
        export_workpack(factory, actor, ["work-0"], app_version="test", build=1)
