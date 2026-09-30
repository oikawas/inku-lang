"""The one-time Saijiki v2 migration leaves a saved work readable, and runs once.

A work's instructions are bound to its frozen fork context by digests; when the
migration rewrites the instructions, the Server must still read the work back
(the author, 2026-09-30: written by hand while the service is stopped).
"""

from __future__ import annotations

import hashlib
import json

import inku_render
import pytest
from sqlalchemy import create_engine

from inku_server.persistence import schema
from inku_server.persistence.saijiki_migration import MigrationAlreadyWritten, migrate_once
from inku_server.persistence.variation_authority import VariationAuthorityStore


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_a_migrated_work_still_reads_and_a_second_run_refuses(tmp_path):
    path = tmp_path / "inku.db"
    engine = create_engine(f"sqlite:///{path}", future=True)
    schema.Base.metadata.create_all(engine)
    ddl = "薄墨の円を置く。"
    digest = hashlib.sha256(ddl.encode("utf-8")).hexdigest()
    context = _canonical({
        "protocol_version": "inku.pipeline-history-fork-context.v1", "variation_id": "v", "revision": "1",
        "ddl_digest": digest, "config": {"definitions": []}, "host_options": {},
        "macro_catalog": {"definition_locks": []},
    })
    document = {"source": ddl, "language": "ja", "macro_locks": []}
    with engine.begin() as connection:
        connection.execute(schema.UserAccountRow.__table__.insert().values(
            id="u", username="u", email="u@example.test", password_hash="-", role="user", at=1))
        connection.execute(schema.HistoryRow.__table__.insert().values(
            id="h", user_id="u", at=1, input="description", ddl=ddl, score="{}", svg="<svg/>", elapsed_ms=0))
        connection.execute(schema.PipelineHistoryLinkRow.__table__.insert().values(
            owner_id="u", history_id="h", variation_id="v", revision="1", ddl_digest=digest,
            fork_context_bytes=context, fork_context_digest=hashlib.sha256(context).hexdigest()))
        connection.execute(schema.VariationAuthorityRow.__table__.insert().values(
            owner_id="u", variation_id="v", protocol_version="inku.variation-authority.v1", revision="1",
            origin="user_authored_ddl", authority="ddl_authoritative", source=ddl,
            document_json=_canonical(document).decode(), ddl_digest=digest, authority_digest="0" * 64,
            updated_at=1))
        connection.execute(schema.PipelineCandidateExecutionRow.__table__.insert().values(
            owner_id="u", execution_id="e", variation_id="v", sequence="1", state_bytes=b"{}",
            state_digest="-", created_at=1, updated_at=1))
    engine.dispose()

    report = migrate_once(path, inku_render.pipeline_migrate_saijiki_v1)

    assert report["refused_records"] == []
    engine = create_engine(f"sqlite:///{path}", future=True)
    linked = VariationAuthorityStore(engine).read_linked_history("u", "h")
    assert linked is not None and linked.history.source == "薄い刷きの円を置く。"
    with engine.connect() as connection:
        source, document_json, ddl_digest = connection.exec_driver_sql(
            "SELECT source, document_json, ddl_digest FROM variation_authority").one()
        executions = connection.exec_driver_sql("SELECT COUNT(*) FROM pipeline_candidate_executions").scalar()
        history = connection.exec_driver_sql("SELECT input, score, svg FROM history").one()
    assert json.loads(document_json)["saijiki"] == "inku.saijiki.v2"
    assert ddl_digest == hashlib.sha256(source.encode("utf-8")).hexdigest()
    assert executions == 0
    assert tuple(history) == ("description", "{}", "<svg/>")
    engine.dispose()

    with pytest.raises(MigrationAlreadyWritten):
        migrate_once(path, inku_render.pipeline_migrate_saijiki_v1)
