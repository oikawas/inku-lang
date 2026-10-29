"""The saved-work name migration runs on an isolated SQLite test database."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import inku_render
import pytest
from sqlalchemy import create_engine

from inku_server.persistence import schema
from inku_server.persistence.plugin_name_migration import (
    MigrationAlreadyWritten, census, migrate_once,
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _saved_database(path):
    root = Path(__file__).resolve().parents[2]
    definition = json.loads((root / "core/crates/inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json").read_text())[
        "entries"][0]["definition"]
    catalog = json.loads(inku_render.pipeline_resolve_macro_catalog(json.dumps({
        "maximum_entries": 1, "canonical": [{"source_id": "test", "definition_json": json.dumps(definition),
                                                "summary": "leaves"}],
    }).encode()))
    entry = catalog["entries"][0]
    lock = {"qualified_name": entry["qualified_name"], "version": entry["version"],
            "digest": entry["digest"]}
    source = "Nature.若葉。"
    digest = _digest(source)
    context = _canonical({"ddl_digest": digest, "config": {"definitions": [definition]},
                          "macro_catalog": {"definition_locks": [lock]}}).encode()
    document = _canonical({"source": source, "language": "ja", "macro_locks": [
        {**lock, "digest": "sha256:" + lock["digest"]}]})
    engine = create_engine(f"sqlite:///{path}", future=True)
    schema.Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(schema.UserAccountRow.__table__.insert().values(
            id="u", username="u", email="u@example.test", password_hash="-", role="user", at=1))
        connection.execute(schema.HistoryRow.__table__.insert().values(
            id="h", user_id="u", at=1, input="description", ddl=source,
            score="{}", svg="<svg/>", elapsed_ms=0))
        connection.execute(schema.PipelineHistoryLinkRow.__table__.insert().values(
            owner_id="u", history_id="h", variation_id="v", revision="1", ddl_digest=digest,
            fork_context_bytes=context, fork_context_digest=hashlib.sha256(context).hexdigest()))
        connection.execute(schema.VariationAuthorityRow.__table__.insert().values(
            owner_id="u", variation_id="v", protocol_version="inku.variation-authority.v1",
            revision="1", origin="user_authored_ddl", authority="ddl_authoritative", source=source,
            document_json=document, ddl_digest=digest, authority_digest="0" * 64, updated_at=1))
        connection.execute(schema.VariationAuthorityActionRow.__table__.insert().values(
            owner_id="u", action_id="a", variation_id="v", request_digest="0" * 64,
            action_fingerprint="0" * 64, context_fingerprint="0" * 64, ddl_digest=digest,
            revision="1", authority_digest="0" * 64, committed_at=1))
    engine.dispose()


def test_census_is_read_only_and_write_keeps_score_and_refuses_second_run(tmp_path):
    path = tmp_path / "saved.db"
    _saved_database(path)
    before = path.read_bytes()
    report = census(path, inku_render.pipeline_migrate_plugin_names)
    assert report["counts"]["changed"] == 2
    assert path.read_bytes() == before
    written = migrate_once(path, inku_render.pipeline_migrate_plugin_names)
    assert written["counts"]["changed"] == 2
    assert Path(written["snapshot"]).is_file()
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        ddl, score, svg = connection.exec_driver_sql("SELECT ddl,score,svg FROM history").one()
        assert (ddl, score, svg) == ("｛若葉｝。", "{}", "<svg/>")
        source, document, digest = connection.exec_driver_sql(
            "SELECT source,document_json,ddl_digest FROM variation_authority").one()
        assert source == json.loads(document)["source"] == ddl
        assert digest == _digest(ddl)
        assert connection.exec_driver_sql("SELECT ddl_digest FROM variation_authority_actions").scalar_one() == digest
        link_digest, context_bytes, context_digest = connection.exec_driver_sql(
            "SELECT ddl_digest,fork_context_bytes,fork_context_digest FROM pipeline_history_links").one()
        assert link_digest == digest == json.loads(context_bytes)["ddl_digest"]
        assert context_digest == hashlib.sha256(context_bytes).hexdigest()
    engine.dispose()
    with pytest.raises(MigrationAlreadyWritten):
        migrate_once(path, inku_render.pipeline_migrate_plugin_names)


def test_core_failure_rolls_back_and_keeps_snapshot(tmp_path):
    path = tmp_path / "saved.db"
    _saved_database(path)

    def fail(_unit):
        raise RuntimeError("test failure")

    with pytest.raises(Exception):
        migrate_once(path, fail, timeout=1)
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT ddl FROM history").scalar_one() == "Nature.若葉。"
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM app_settings WHERE key='plugin_names_v2_saved_records'").scalar_one() == 0
    engine.dispose()
    assert list((tmp_path / "migration-backups").glob("*.db"))
