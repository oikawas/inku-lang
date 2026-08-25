import json
from pathlib import Path

from scripts.check_portable_persistence_contract import (
    canonical_schema_objects,
    fingerprint_evidence,
    parse_server_models,
    run_checks,
    schema_fingerprint,
)


ROOT = Path(__file__).resolve().parents[2]


def test_current_host_definitions_satisfy_the_portable_contract():
    summary = run_checks(ROOT)

    assert summary["logical_fields"] == 57
    assert summary["semantic_rules"] == 12
    assert summary["declared_gaps"] == 0
    assert summary["server_tables"] >= 3
    assert summary["room_tables"] == 9


def test_physical_names_are_mappings_not_portable_authority():
    contract = json.loads((ROOT / "persistence/contract.json").read_text(encoding="utf-8"))
    server = contract["hosts"]["server"]["records"]["history"]
    android = contract["hosts"]["android"]["records"]["history"]

    assert server["table"] == "history"
    assert android["table"] == "history_items"
    assert contract["hosts"]["android"]["source"] == (
        "android/app/schemas/app.inku.mobile.data.db.InkuDatabase/10.json"
    )
    assert server["fields"]["input"]["column"] == "input"
    assert android["fields"]["input"]["column"] == "original_input"
    assert android["fields"]["render_engine_id"]["json_path"] == "$.render_engine_id"
    assert "compose_fallback" not in android["fields"]


def test_current_constraints_are_enforced_by_real_host_authorities():
    contract = json.loads((ROOT / "persistence/contract.json").read_text(encoding="utf-8"))
    server = contract["hosts"]["server"]["constraint_coverage"]
    android = contract["hosts"]["android"]["constraint_coverage"]

    assert all(item["status"] == "enforced" for item in server.values())
    assert all(item["status"] == "enforced" for item in android.values())
    assert android["history.lineage_node_id.unique"] == {
        "status": "enforced",
        "mechanism": "database",
        "authority": "index_history_items_lineage_node_id",
    }
    assert android["lineage_nodes.history_id.unique"] == {
        "status": "enforced",
        "mechanism": "database",
        "authority": "index_lineage_nodes_history_id",
    }
    assert android["lineage_edges.no_self_edge"] == {
        "status": "enforced",
        "mechanism": "database",
        "authority": "ck_lineage_no_self_edge_insert and ck_lineage_no_self_edge_update",
    }


def test_schema_fingerprint_is_order_insensitive_and_materially_sensitive():
    rows = [
        {"type": "table", "name": "history", "table": "history", "sql": "CREATE  TABLE history (id TEXT)"},
        {"type": "index", "name": "ix_history_id", "table": "history", "sql": "CREATE INDEX ix_history_id ON history (id)"},
        {"type": "table", "name": "history_fts_data", "table": "history_fts_data", "sql": "derived"},
    ]
    prefixes = ["sqlite_", "history_fts"]

    assert canonical_schema_objects(rows, prefixes) == canonical_schema_objects(reversed(rows), prefixes)
    assert schema_fingerprint(rows, prefixes) == schema_fingerprint(reversed(rows), prefixes)

    changed = [dict(row) for row in rows]
    changed[0]["sql"] = "CREATE TABLE history (id TEXT, at INTEGER)"
    assert schema_fingerprint(rows, prefixes) != schema_fingerprint(changed, prefixes)

    sqlite_master_names = [dict(row, tbl_name=row["table"]) for row in rows]
    for row in sqlite_master_names:
        del row["table"]
    assert schema_fingerprint(rows, prefixes) == schema_fingerprint(sqlite_master_names, prefixes)


def test_fingerprint_never_reads_row_values():
    rows = [{"type": "table", "name": "history", "table": "history", "sql": "CREATE TABLE history (id TEXT)"}]

    normalized = canonical_schema_objects(rows, [])

    assert set(normalized[0]) == {"type", "name", "table", "sql"}


def test_fingerprint_evidence_reports_only_digest_and_counts():
    contract = json.loads((ROOT / "persistence/contract.json").read_text(encoding="utf-8"))
    server = contract["hosts"]["server"]
    models = parse_server_models(ROOT / server["source"])
    rows = [
        {
            "type": "table",
            "name": model["table"],
            "table": model["table"],
            "sql": f"CREATE TABLE {model['table']} (id TEXT)",
        }
        for model in models.values()
    ]

    evidence = fingerprint_evidence(ROOT, rows)

    assert set(evidence) == {
        "fingerprint",
        "objects",
        "expected_tables",
        "observed_tables",
        "missing_tables",
        "extra_tables",
    }
    assert len(evidence["fingerprint"]) == 64
    assert evidence["missing_tables"] == 0
    assert evidence["extra_tables"] == 0
