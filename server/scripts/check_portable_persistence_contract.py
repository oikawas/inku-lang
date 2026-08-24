#!/usr/bin/env python3
"""Verify the host-neutral persistence contract without opening a user database."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable


class ContractError(RuntimeError):
    """The declared portable contract does not match its source authorities."""


AFFINITIES = {"INTEGER", "REAL", "TEXT", "BLOB", "NUMERIC"}
CLASSIFICATIONS = {"required_common", "optional_common", "host_only"}
CONSTRAINT_STATUSES = {"enforced", "gap"}
CONSTRAINT_MECHANISMS = {"database", "application_transaction", "none"}
SERVER_AFFINITIES = {
    "BigInteger": "INTEGER",
    "Boolean": "INTEGER",
    "Float": "REAL",
    "Integer": "INTEGER",
    "LargeBinary": "BLOB",
    "String": "TEXT",
    "Text": "TEXT",
}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON authority: {path}") from exc


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return None


def _constant_bool(call: ast.Call, keyword: str, default: bool) -> bool:
    for item in call.keywords:
        if item.arg == keyword and isinstance(item.value, ast.Constant):
            return bool(item.value.value)
    return default


def parse_server_models(path: Path) -> dict[str, dict[str, Any]]:
    """Read SQLAlchemy model declarations as syntax, avoiding engine startup."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ContractError(f"cannot parse Server model authority: {path}") from exc

    models: dict[str, dict[str, Any]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        table_name: str | None = None
        columns: dict[str, dict[str, Any]] = {}
        unique_constraints: set[tuple[str, ...]] = set()
        checks: set[str] = set()
        for statement in node.body:
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                continue
            target = statement.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if target.id == "__tablename__" and isinstance(statement.value, ast.Constant):
                table_name = str(statement.value.value)
                continue
            if target.id == "__table_args__":
                for candidate in ast.walk(statement.value):
                    if not isinstance(candidate, ast.Call):
                        continue
                    name = _call_name(candidate.func)
                    string_args = tuple(
                        str(arg.value) for arg in candidate.args if isinstance(arg, ast.Constant)
                    )
                    if name == "UniqueConstraint" and string_args:
                        unique_constraints.add(string_args)
                    elif name == "CheckConstraint" and string_args:
                        checks.add(string_args[0])
                continue
            if not isinstance(statement.value, ast.Call) or _call_name(statement.value.func) != "Column":
                continue
            call = statement.value
            type_name = _call_name(call.args[0]) if call.args else None
            if type_name not in SERVER_AFFINITIES:
                raise ContractError(f"unsupported Server column type: {node.name}.{target.id}={type_name}")
            primary_key = _constant_bool(call, "primary_key", False)
            nullable = _constant_bool(call, "nullable", not primary_key)
            columns[target.id] = {
                "affinity": SERVER_AFFINITIES[type_name],
                "nullable": nullable,
                "primary_key": primary_key,
                "unique": _constant_bool(call, "unique", False),
            }
        if table_name is not None:
            models[node.name] = {
                "table": table_name,
                "columns": columns,
                "unique_constraints": unique_constraints,
                "checks": checks,
            }
    return models


def parse_room_schema(path: Path) -> dict[str, dict[str, Any]]:
    raw = _load_json(path)
    try:
        entities = raw["database"]["entities"]
    except (KeyError, TypeError) as exc:
        raise ContractError("Room schema has no database.entities array") from exc
    result: dict[str, dict[str, Any]] = {}
    for entity in entities:
        fields = {
            field["columnName"]: {
                "affinity": field["affinity"],
                "nullable": not bool(field.get("notNull")),
            }
            for field in entity["fields"]
        }
        result[entity["tableName"]] = {
            "columns": fields,
            "indices": entity.get("indices") or [],
            "create_sql": entity["createSql"],
        }
    return result


def _logical_fields(contract: dict[str, Any], record_name: str) -> dict[str, dict[str, Any]]:
    try:
        fields = contract["records"][record_name]["fields"]
    except (KeyError, TypeError) as exc:
        raise ContractError(f"missing logical record: {record_name}") from exc
    result: dict[str, dict[str, Any]] = {}
    for field in fields:
        name = field.get("name")
        if not isinstance(name, str) or not name or name in result:
            raise ContractError(f"duplicate or invalid field in {record_name}: {name!r}")
        if field.get("affinity") not in AFFINITIES:
            raise ContractError(f"invalid affinity for {record_name}.{name}")
        if field.get("classification") not in CLASSIFICATIONS:
            raise ContractError(f"invalid classification for {record_name}.{name}")
        if not isinstance(field.get("nullable"), bool):
            raise ContractError(f"nullable must be boolean for {record_name}.{name}")
        if not isinstance(field.get("encoding"), str) or not field["encoding"]:
            raise ContractError(f"missing encoding for {record_name}.{name}")
        result[name] = field
    return result


def _validate_contract_shape(contract: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    if contract.get("contract_version") != 1:
        raise ContractError("contract_version must be 1")
    if contract.get("physical_schema_identity_required") is not False:
        raise ContractError("physical schema identity must not be required")

    semantic_ids = [item.get("id") for item in contract.get("semantic_rules", [])]
    if not semantic_ids or any(not isinstance(item, str) or not item for item in semantic_ids):
        raise ContractError("semantic rule ids must be non-empty strings")
    if len(semantic_ids) != len(set(semantic_ids)):
        raise ContractError("semantic rule ids must be unique")

    constraint_keys = contract.get("constraint_keys")
    if (
        not isinstance(constraint_keys, list)
        or not constraint_keys
        or any(not isinstance(item, str) or not item for item in constraint_keys)
        or len(constraint_keys) != len(set(constraint_keys))
    ):
        raise ContractError("constraint keys must be a non-empty unique string list")

    records = {
        name: _logical_fields(contract, name)
        for name in ("history", "lineage_nodes", "lineage_edges")
    }
    for host_name, host in contract.get("hosts", {}).items():
        coverage = host.get("constraint_coverage")
        if not isinstance(coverage, dict) or set(coverage) != set(constraint_keys):
            raise ContractError(f"{host_name} constraint coverage is incomplete")
        for key, declaration in coverage.items():
            if declaration.get("status") not in CONSTRAINT_STATUSES:
                raise ContractError(f"invalid constraint status for {host_name}.{key}")
            if declaration.get("mechanism") not in CONSTRAINT_MECHANISMS:
                raise ContractError(f"invalid constraint mechanism for {host_name}.{key}")
            if not isinstance(declaration.get("authority"), str) or not declaration["authority"]:
                raise ContractError(f"missing constraint authority for {host_name}.{key}")
            if declaration["status"] == "enforced" and declaration["mechanism"] == "none":
                raise ContractError(f"enforced constraint has no mechanism for {host_name}.{key}")
            if declaration["status"] == "gap" and not declaration.get("target_stage"):
                raise ContractError(f"constraint gap has no target stage for {host_name}.{key}")
        for record_name, record in host.get("records", {}).items():
            if record_name not in records:
                raise ContractError(f"{host_name} maps unknown record {record_name}")
            unknown = set(record.get("fields", {})) - set(records[record_name])
            if unknown:
                raise ContractError(f"{host_name}.{record_name} maps unknown fields: {sorted(unknown)}")

    for record_name, fields in records.items():
        for field_name, field in fields.items():
            mapped_hosts = {
                host_name
                for host_name, host in contract["hosts"].items()
                if field_name in host["records"][record_name]["fields"]
            }
            if field["classification"] == "required_common" and mapped_hosts != {"server", "android"}:
                raise ContractError(
                    f"required field {record_name}.{field_name} is not mapped by both hosts"
                )
            if field["classification"] == "optional_common" and not mapped_hosts:
                raise ContractError(f"optional field {record_name}.{field_name} has no mapping")
    return records


def _validate_history_column_coverage(
    host_name: str,
    host: dict[str, Any],
    physical_columns: set[str],
) -> None:
    extensions = host.get("host_only_history_extensions")
    if not isinstance(extensions, list) or len(extensions) != len(set(extensions)):
        raise ContractError(f"{host_name} host-only history extensions must be a unique list")
    extension_set = set(extensions)
    unknown_extensions = extension_set - physical_columns
    if unknown_extensions:
        raise ContractError(
            f"{host_name} host-only history extensions are missing physically: "
            f"{sorted(unknown_extensions)}"
        )
    mappings = host["records"]["history"]["fields"].values()
    mapped_columns = {
        mapping["column"]
        for mapping in mappings
        if "column" in mapping and "related_record" not in mapping
    }
    unclassified = physical_columns - mapped_columns - extension_set
    if unclassified:
        raise ContractError(f"{host_name} history columns are unclassified: {sorted(unclassified)}")


def _check_physical_field(
    host_name: str,
    record_name: str,
    field_name: str,
    logical: dict[str, Any],
    mapping: dict[str, Any],
    table: dict[str, Any],
) -> None:
    column_name = mapping.get("column")
    if not isinstance(column_name, str) or column_name not in table["columns"]:
        raise ContractError(f"{host_name}.{record_name}.{field_name} has no physical column")
    physical = table["columns"][column_name]
    adapted = "adapter_encoding" in mapping or "json_path" in mapping
    if logical["affinity"] != physical["affinity"] and not adapted:
        raise ContractError(
            f"affinity mismatch for {host_name}.{record_name}.{field_name}: "
            f"{logical['affinity']} != {physical['affinity']}"
        )
    if not logical["nullable"] and physical["nullable"] and "json_path" not in mapping:
        raise ContractError(f"non-null logical field is nullable on {host_name}: {record_name}.{field_name}")
    if "json_path" in mapping and not mapping["json_path"].startswith("$."):
        raise ContractError(f"invalid JSON path for {host_name}.{record_name}.{field_name}")


def _validate_server(
    root: Path,
    contract: dict[str, Any],
    logical_records: dict[str, dict[str, dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    host = contract["hosts"]["server"]
    models = parse_server_models(root / host["source"])
    for record_name, mapping in host["records"].items():
        model_name = mapping["model"]
        if model_name not in models:
            raise ContractError(f"missing Server model: {model_name}")
        model = models[model_name]
        if model["table"] != mapping["table"]:
            raise ContractError(f"Server table mismatch for {model_name}")
        for field_name, physical_mapping in mapping["fields"].items():
            _check_physical_field(
                "server",
                record_name,
                field_name,
                logical_records[record_name][field_name],
                physical_mapping,
                model,
            )

    history = models[host["records"]["history"]["model"]]
    _validate_history_column_coverage("server", host, set(history["columns"]))
    if history["columns"]["render_hash"]["unique"]:
        raise ContractError("Server render_hash must remain non-unique")
    edge = models[host["records"]["lineage_edges"]["model"]]
    if ("child_node_id",) not in edge["unique_constraints"]:
        raise ContractError("Server lineage edge must have one primary parent")
    if "parent_node_id <> child_node_id" not in edge["checks"]:
        raise ContractError("Server lineage edge must reject self-edges")
    return models, {model["table"] for model in models.values()}


def _validate_android(
    root: Path,
    contract: dict[str, Any],
    logical_records: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    host = contract["hosts"]["android"]
    tables = parse_room_schema(root / host["source"])
    for record_name, mapping in host["records"].items():
        table_name = mapping["table"]
        if table_name not in tables:
            raise ContractError(f"missing Android Room table: {table_name}")
        table = tables[table_name]
        for field_name, physical_mapping in mapping["fields"].items():
            if "constant" in physical_mapping:
                if physical_mapping["constant"] is None and not logical_records[record_name][field_name]["nullable"]:
                    raise ContractError(f"null constant for non-null Android field {field_name}")
                continue
            if "related_record" in physical_mapping:
                related = physical_mapping["related_record"]
                if related not in host["records"]:
                    raise ContractError(f"unknown related Android record: {related}")
                related_table = tables[host["records"][related]["table"]]
                _check_physical_field(
                    "android",
                    related,
                    field_name,
                    logical_records[record_name][field_name],
                    physical_mapping,
                    related_table,
                )
                join = physical_mapping.get("join", "")
                left, separator, right = join.partition("=")
                if not separator or left not in table["columns"] or right not in related_table["columns"]:
                    raise ContractError(f"invalid related-record join for Android {field_name}")
                continue
            _check_physical_field(
                "android",
                record_name,
                field_name,
                logical_records[record_name][field_name],
                physical_mapping,
                table,
            )

    history = tables[host["records"]["history"]["table"]]
    _validate_history_column_coverage("android", host, set(history["columns"]))
    render_hash_indices = [
        index for index in history["indices"] if index.get("columnNames") == ["render_hash"]
    ]
    if not render_hash_indices or any(index.get("unique") for index in render_hash_indices):
        raise ContractError("Android render_hash index must exist and remain non-unique")
    edges = tables[host["records"]["lineage_edges"]["table"]]
    if not any(
        index.get("unique") and index.get("columnNames") == ["child_node_id"]
        for index in edges["indices"]
    ):
        raise ContractError("Android lineage edge must have one primary parent")
    return tables


def _insert_dict(connection: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    columns = list(row)
    placeholders = ", ".join("?" for _ in columns)
    names = ", ".join(columns)
    connection.execute(
        f"INSERT INTO {table} ({names}) VALUES ({placeholders})",  # noqa: S608 - table is internal
        [row[column] for column in columns],
    )


def validate_reference(root: Path, logical_records: dict[str, dict[str, dict[str, Any]]]) -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        (root / "persistence/reference/logical-projection-v1.sql").read_text(encoding="utf-8")
    )
    for record_name, logical_fields in logical_records.items():
        actual = {
            row[1]: {"affinity": row[2].upper(), "nullable": not bool(row[3])}
            for row in connection.execute(f"PRAGMA table_info({record_name})")  # noqa: S608
        }
        if set(actual) != set(logical_fields):
            raise ContractError(f"reference SQL fields differ for {record_name}")
        for field_name, field in logical_fields.items():
            if actual[field_name]["affinity"] != field["affinity"]:
                raise ContractError(f"reference affinity differs for {record_name}.{field_name}")
            if actual[field_name]["nullable"] != field["nullable"]:
                raise ContractError(f"reference NULL rule differs for {record_name}.{field_name}")

    minimal = _load_json(root / "persistence/fixtures/history-minimal.json")
    replay = _load_json(root / "persistence/fixtures/history-replay.json")
    lineage = _load_json(root / "persistence/fixtures/lineage.json")
    _insert_dict(connection, "history", minimal)
    for row in replay:
        _insert_dict(connection, "history", row)
    for row in lineage["nodes"]:
        _insert_dict(connection, "lineage_nodes", row)
    for row in lineage["edges"]:
        _insert_dict(connection, "lineage_edges", row)

    legacy = connection.execute(
        "SELECT compose_fallback, sketch_state FROM history WHERE id = ?",
        ("history-legacy-null",),
    ).fetchone()
    recorded = connection.execute(
        "SELECT compose_fallback, sketch_state FROM history WHERE id = ?",
        ("history-recorded-none",),
    ).fetchone()
    if legacy != (None, None) or recorded != ("none", "off"):
        raise ContractError("historical NULL fixture distinctions collapsed")

    duplicate_hash = dict(minimal, id="history-same-render-hash", lineage_node_id=None)
    _insert_dict(connection, "history", duplicate_hash)
    try:
        _insert_dict(connection, "history", minimal)
    except sqlite3.IntegrityError:
        pass
    else:
        raise ContractError("duplicate history primary key was accepted")

    _insert_dict(
        connection,
        "lineage_nodes",
        {"id": "node-other-parent", "state": "active", "at": 1787580004000},
    )
    try:
        _insert_dict(
            connection,
            "lineage_edges",
            {
                "id": "edge-second-parent",
                "parent_node_id": "node-other-parent",
                "child_node_id": "node-child",
                "derivation_kind": "replay",
                "metadata_json": "{}",
                "at": 1787580004000,
            },
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise ContractError("second primary parent was accepted")

    try:
        _insert_dict(
            connection,
            "lineage_edges",
            {
                "id": "edge-self",
                "parent_node_id": "node-other-parent",
                "child_node_id": "node-other-parent",
                "derivation_kind": "replay",
                "metadata_json": "{}",
                "at": 1787580005000,
            },
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise ContractError("self-edge was accepted")
    connection.close()


def canonical_schema_objects(
    rows: Iterable[dict[str, Any]], exclude_prefixes: Iterable[str]
) -> list[dict[str, str]]:
    prefixes = tuple(exclude_prefixes)
    normalized: list[dict[str, str]] = []
    for row in rows:
        name = str(row["name"])
        table_name = row.get("table", row.get("tbl_name"))
        if table_name is None:
            raise ContractError(f"schema object has no owning table: {name}")
        if name.startswith(prefixes):
            continue
        normalized.append(
            {
                "type": str(row["type"]).lower(),
                "name": name,
                "table": str(table_name),
                "sql": re.sub(r"\s+", " ", str(row.get("sql") or "")).strip(),
            }
        )
    return sorted(normalized, key=lambda item: (item["type"], item["name"], item["table"]))


def schema_fingerprint(rows: Iterable[dict[str, Any]], exclude_prefixes: Iterable[str]) -> str:
    payload = json.dumps(
        canonical_schema_objects(rows, exclude_prefixes),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fingerprint_evidence(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return only schema aggregates suitable for private production evidence."""
    contract = _load_json(root / "persistence/contract.json")
    fingerprint_contract = contract["legacy_server_fingerprint"]
    allowed_types = set(fingerprint_contract["object_types"])
    eligible = [row for row in rows if str(row.get("type", "")).lower() in allowed_types]
    normalized = canonical_schema_objects(
        eligible,
        fingerprint_contract["exclude_name_prefixes"],
    )
    models = parse_server_models(root / contract["hosts"]["server"]["source"])
    expected_tables = {model["table"] for model in models.values()}
    observed_tables = {row["name"] for row in normalized if row["type"] == "table"}
    return {
        "fingerprint": schema_fingerprint(
            eligible,
            fingerprint_contract["exclude_name_prefixes"],
        ),
        "objects": len(normalized),
        "expected_tables": len(expected_tables),
        "observed_tables": len(observed_tables),
        "missing_tables": len(expected_tables - observed_tables),
        "extra_tables": len(observed_tables - expected_tables),
    }


def run_checks(root: Path) -> dict[str, int]:
    contract = _load_json(root / "persistence/contract.json")
    logical_records = _validate_contract_shape(contract)
    models, server_tables = _validate_server(root, contract, logical_records)
    room_tables = _validate_android(root, contract, logical_records)
    validate_reference(root, logical_records)
    return {
        "logical_fields": sum(len(fields) for fields in logical_records.values()),
        "semantic_rules": len(contract["semantic_rules"]),
        "declared_gaps": sum(
            declaration["status"] == "gap"
            for host in contract["hosts"].values()
            for declaration in host["constraint_coverage"].values()
        ),
        "server_models": len(models),
        "server_tables": len(server_tables),
        "room_tables": len(room_tables),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fingerprint-stdin",
        action="store_true",
        help="read sqlite_master JSON from stdin and print schema aggregates only",
    )
    args = parser.parse_args()
    if args.fingerprint_stdin:
        try:
            rows = json.load(sys.stdin)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ContractError("fingerprint input must be a JSON array of schema objects")
            evidence = fingerprint_evidence(root, rows)
        except (ContractError, json.JSONDecodeError) as exc:
            print(f"portable persistence fingerprint: FAIL: {exc}")
            return 1
        print(
            "portable persistence fingerprint: "
            f"sha256={evidence['fingerprint']} objects={evidence['objects']} "
            f"expected_tables={evidence['expected_tables']} "
            f"observed_tables={evidence['observed_tables']} "
            f"missing_tables={evidence['missing_tables']} extra_tables={evidence['extra_tables']}"
        )
        return 1 if evidence["missing_tables"] or evidence["extra_tables"] else 0
    try:
        summary = run_checks(root)
    except ContractError as exc:
        print(f"portable persistence contract: FAIL: {exc}")
        return 1
    print(
        "portable persistence contract: OK "
        f"v1 fields={summary['logical_fields']} rules={summary['semantic_rules']} "
        f"declared_gaps={summary['declared_gaps']} "
        f"server_tables={summary['server_tables']} room_tables={summary['room_tables']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
