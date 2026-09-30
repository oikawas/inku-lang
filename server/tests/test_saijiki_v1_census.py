"""Counting the Saijiki v1 migration reads every kind of saved record and writes none.

Before the saved records are written over, an isolated copy of the production
database is counted (the author, 2026-09-30): how many records the core would
change, leave, or refuse, and which words it would replace.
"""

from __future__ import annotations

import json
import sqlite3

import inku_render

from inku_server.persistence.saijiki_migration import census


def _database(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE variation_authority (
            owner_id TEXT, variation_id TEXT, revision TEXT, document_json TEXT, ddl_digest TEXT);
        CREATE TABLE pipeline_history_links (
            owner_id TEXT, history_id TEXT, variation_id TEXT, fork_context_bytes BLOB, fork_context_digest TEXT);
        CREATE TABLE pipeline_candidate_executions (
            owner_id TEXT, execution_id TEXT, variation_id TEXT, state_bytes BLOB);
        CREATE TABLE history (id TEXT, ddl TEXT, expanded_ddl TEXT, instruction_lang_resolved TEXT);
        """
    )
    v1 = {"source": "薄墨の円を置く。", "language": "ja", "macro_locks": []}
    current = {**v1, "source": "薄い刷きの円を置く。", "saijiki": "inku.saijiki.v2"}
    connection.executemany(
        "INSERT INTO variation_authority VALUES (?, ?, '1', ?, '')",
        [("u", "old", json.dumps(v1, ensure_ascii=False)), ("u", "new", json.dumps(current, ensure_ascii=False))],
    )
    wrapper = {"snapshot": {"document": v1, "config": {}}, "context": {}, "rendered": None}
    connection.execute(
        "INSERT INTO pipeline_candidate_executions VALUES ('u', 'e1', 'old', ?)",
        (json.dumps(wrapper, ensure_ascii=False).encode(),),
    )
    connection.executemany(
        "INSERT INTO history VALUES (?, ?, NULL, 'ja')",
        [("h1", "中央に赤い震える点の円を置く。"), ("h2", "点を置く。")],
    )
    connection.commit()
    return connection


def test_the_census_counts_each_kind_of_record(tmp_path):
    path = tmp_path / "copy.db"
    _database(path).close()
    before = path.read_bytes()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    report = census(connection, inku_render.pipeline_migrate_saijiki_v1)
    connection.close()

    variations = report["variation_documents"]
    assert (variations["rows"], variations["current"], variations["v1"]) == (2, 1, 1)
    assert variations["changed"] == 1
    assert "薄墨 -> 薄い刷き" in report["edits"]
    assert report["executions"]["discarded"] == 1
    history = report["history"]
    assert (history["ddl_present"], history["changed"], history["unchanged"]) == (2, 1, 1)
    assert report["refused_records"] == []
    # Counting writes nothing.
    assert path.read_bytes() == before
