"""The saved-record adapter handles old and unified text columns explicitly."""

from __future__ import annotations

import json
import sqlite3

import pytest

from inku_server.persistence.saijiki_migration import BlankListInvalid, _plan


def _database(*, old: bool):
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE variation_authority (
            owner_id TEXT, variation_id TEXT, revision TEXT, document_json TEXT, ddl_digest TEXT);
        CREATE TABLE pipeline_history_links (
            owner_id TEXT, history_id TEXT, variation_id TEXT, fork_context_bytes BLOB, fork_context_digest TEXT);
        CREATE TABLE pipeline_candidate_executions (
            owner_id TEXT, execution_id TEXT, variation_id TEXT, state_bytes BLOB);
        CREATE TABLE history (id TEXT, ddl TEXT, instruction_lang_resolved TEXT, input TEXT, score TEXT, svg TEXT);
    """)
    if old:
        connection.execute("ALTER TABLE history ADD COLUMN expanded_ddl TEXT")
    else:
        connection.execute("ALTER TABLE history ADD COLUMN ddl_source_origin TEXT")
    connection.execute("INSERT INTO history(id,ddl,instruction_lang_resolved,input,score,svg) "
                       "VALUES ('h','old','ja','description','{}','<svg/>')")
    if old:
        connection.execute("UPDATE history SET expanded_ddl='historical blank target'")
    else:
        connection.execute("UPDATE history SET ddl_source_origin='legacy_expanded'")
    return connection


class SavedUnitCore:
    """Only adapter projection is under test; no compiler or worker runs."""

    def __init__(self):
        self.answers = {}

    def ask(self, _kind, units):
        for unit in units:
            document = json.loads(unit)["document"]
            self.answers[unit] = {"document": {
                "document": {**document, "source": "new", "saijiki": "inku.saijiki.v2"},
                "edits": [{"original": "old", "replacement": "new"}],
            }}

    def report(self):
        return {}


@pytest.mark.parametrize("old", [True, False], ids=["old-backup", "unified-schema"])
def test_saijiki_updates_only_columns_that_exist_and_keeps_blank_meaning(old):
    connection = _database(old=old)
    plan = _plan(connection, SavedUnitCore(), sample=None, history_ids=None,
                 blank={"h:expanded_ddl"} if old else set())
    for sql, args in plan.statements:
        connection.execute(sql, args)

    assert connection.execute("SELECT ddl,input,score,svg FROM history").fetchone() == (
        "new", "description", "{}", "<svg/>",
    )
    if old:
        assert connection.execute("SELECT expanded_ddl FROM history").fetchone() == (None,)
        assert [item["id"] for item in plan.report["blanked_records"]] == ["h:expanded_ddl"]
    else:
        assert connection.execute("SELECT ddl_source_origin FROM history").fetchone() == ("legacy_expanded",)
        assert all("expanded_ddl" not in sql for sql, _ in plan.statements)
        with pytest.raises(BlankListInvalid, match="not a history text in this schema"):
            _plan(connection, SavedUnitCore(), sample=None, history_ids=None, blank={"h:expanded_ddl"})
    connection.close()
