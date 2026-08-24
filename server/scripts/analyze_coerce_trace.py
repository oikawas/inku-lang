from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


def _json_object(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _empty_marker() -> dict[str, int]:
    return {
        "membership_count": 0,
        "matched_work": 0,
        "unique_attributed": 0,
        "ambiguous": 0,
    }


def _empty_system() -> dict[str, int]:
    return {
        "membership_count": 0,
        "matched_work": 0,
        "unique_attributed": 0,
        "ambiguous": 0,
    }


def _empty_branch() -> dict[str, int]:
    return {"changed_work": 0, "change_count": 0}


def _row_is_observed(row: sqlite3.Row) -> bool:
    return (
        row["score_pre_coerce"] is not None
        and row["coerce_trace_version"] is not None
        and row["coerce_catalog_digest"] is not None
        and _json_object(row["coerce_trace"]) is not None
    )


def _catalog_groups(
    conn: sqlite3.Connection,
    *,
    digest_selector: str | None,
    trace_version_selector: int | None,
) -> dict[str, tuple[int, dict[str, Any]]]:
    required_columns = {"digest", "trace_version", "snapshot_json"}
    if not required_columns <= _table_columns(conn, "coerce_trace_catalogs"):
        # Read-only preflight is intentionally useful before startup migration.
        # Some accepted Stage 0 databases already have the observation columns
        # on history but not the catalog table that gives their digests meaning.
        # Treat that state as having no analyzable groups; never create or repair
        # schema from an inspection tool.
        return {}
    groups: dict[str, tuple[int, dict[str, Any]]] = {}
    for digest, trace_version, snapshot_raw in conn.execute(
        "SELECT digest, trace_version, snapshot_json FROM coerce_trace_catalogs"
    ):
        snapshot = _json_object(snapshot_raw)
        if snapshot is None:
            continue
        if digest_selector is not None and digest != digest_selector:
            continue
        if trace_version_selector is not None and trace_version != trace_version_selector:
            continue
        groups[digest] = (trace_version, snapshot)
    return groups


def _aggregate_group(
    digest: str,
    trace_version: int,
    snapshot: dict[str, Any],
    rows: list[sqlite3.Row],
    *,
    has_score: bool,
) -> dict[str, Any]:
    marker_map: defaultdict[str, dict[str, int]] = defaultdict(_empty_marker)
    system_map: defaultdict[str, dict[str, int]] = defaultdict(_empty_system)
    marker_memberships: defaultdict[str, set[str]] = defaultdict(set)
    for event in snapshot.get("markers", []):
        if not isinstance(event, dict):
            continue
        marker = event.get("marker")
        system = event.get("system")
        if not isinstance(marker, str) or not isinstance(system, str):
            continue
        marker_map[marker]["membership_count"] += 1
        system_map[system]["membership_count"] += 1
        marker_memberships[marker].add(system)

    observed = [row for row in rows if _row_is_observed(row)]
    parsed = [(row, _json_object(row["coerce_trace"])) for row in observed]
    complete = [(row, trace) for row, trace in parsed if trace and trace.get("complete") is True]
    incomplete = len(observed) - len(complete)
    branch_map: defaultdict[str, dict[str, int]] = defaultdict(_empty_branch)
    effect_map: defaultdict[str, int] = defaultdict(int)
    matched_systems: defaultdict[str, set[str]] = defaultdict(set)
    changed_branches: set[str] = set()

    for row, trace in complete:
        marker_events = [event for event in trace.get("marker_events", []) if isinstance(event, dict)]
        words = {event.get("marker") for event in marker_events if isinstance(event.get("marker"), str)}
        for word in words:
            marker_map[word]["matched_work"] += 1
            if len(words) == 1 and marker_map[word]["membership_count"] == 1:
                marker_map[word]["unique_attributed"] += 1
            else:
                marker_map[word]["ambiguous"] += 1
        for event in marker_events:
            marker = event.get("marker")
            system = event.get("system")
            if not isinstance(marker, str) or not isinstance(system, str):
                continue
            matched_systems[system].add(str(row["id"]))
            if len(words) == 1 and marker_map[marker]["membership_count"] == 1:
                system_map[system]["unique_attributed"] += 1
            else:
                system_map[system]["ambiguous"] += 1
        seen_branches: set[str] = set()
        for event in trace.get("branch_events", []):
            if not isinstance(event, dict) or not isinstance(event.get("branch"), str):
                continue
            branch = event["branch"]
            changed_branches.add(branch)
            if branch not in seen_branches:
                branch_map[branch]["changed_work"] += 1
                seen_branches.add(branch)
            branch_map[branch]["change_count"] += int(event.get("change_count", 0) or 0)
            for effect in event.get("changed_fields", []):
                if not isinstance(effect, dict):
                    continue
                path = effect.get("path")
                kind = effect.get("effect")
                if isinstance(path, str) and isinstance(kind, str):
                    effect_map[f"{path}:{kind}"] += 1

    for system, work_ids in matched_systems.items():
        system_map[system]["matched_work"] = len(work_ids)

    snapshot_branches = [branch for branch in snapshot.get("branches", []) if isinstance(branch, str)]
    pre_post_coverage = sum(
        1
        for row, _ in complete
        if row["score_pre_coerce"] is not None
        and (not has_score or row["score"] is not None)
    )
    return {
        "trace_version": trace_version,
        "coverage": {
            "total": len(rows),
            "observed": len(observed),
            "complete": len(complete),
            "incomplete": incomplete,
            "unobserved": len(rows) - len(observed),
            "executed": sum(bool(trace.get("executed")) for _, trace in complete),
            "disabled": sum(bool(trace.get("disabled")) for _, trace in complete),
        },
        "catalog_population": {
            "marker_count": len(marker_map),
            "system_count": len(system_map),
            "membership_count": sum(data["membership_count"] for data in marker_map.values()),
        },
        "markers": dict(marker_map),
        "systems": dict(system_map),
        "branches": dict(branch_map),
        "effects": dict(effect_map),
        "zero_markers": sorted(
            marker for marker, data in marker_map.items() if not data["matched_work"]
        ),
        "zero_systems": sorted(
            system for system, data in system_map.items() if not data["matched_work"]
        ),
        "zero_branches": sorted(set(snapshot_branches) - changed_branches),
        "overlap": {
            "overlapping_marker_count": sum(
                len(systems) > 1 for systems in marker_memberships.values()
            ),
            "overlapping_markers": {
                marker: sorted(systems)
                for marker, systems in marker_memberships.items()
                if len(systems) > 1
            },
        },
        "pre_post_coverage": pre_post_coverage,
        "historical_marker_measurement_eligible": bool(complete),
        # The database can establish that historical observation is complete,
        # but it cannot prove that today's code reproduces an old catalog.
        "current_code_replay_eligible": False,
    }


def analyze(
    conn: sqlite3.Connection,
    selected: str | None = None,
    trace_version: int | None = None,
) -> dict[str, Any]:
    history_columns = _table_columns(conn, "history")
    required = {
        "id", "score_pre_coerce", "coerce_trace_version",
        "coerce_catalog_digest", "coerce_trace",
    }
    if not required <= history_columns:
        total = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        return {
            "groups": {},
            "global_coverage": {
                "total": total, "observed": 0, "complete": 0,
                "incomplete": 0, "unobserved": total,
            },
        }
    score_sql = "score" if "score" in history_columns else "NULL AS score"
    rows = conn.execute(
        "SELECT id, score_pre_coerce, coerce_trace_version, "
        f"coerce_catalog_digest, coerce_trace, {score_sql} FROM history"
    ).fetchall()
    catalogs = _catalog_groups(
        conn,
        digest_selector=selected,
        trace_version_selector=trace_version,
    )
    grouped_rows: defaultdict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        digest = row["coerce_catalog_digest"]
        if not isinstance(digest, str) or digest not in catalogs:
            continue
        grouped_rows[digest].append(row)
    groups = {
        digest: _aggregate_group(
            digest,
            catalog_trace_version,
            snapshot,
            grouped_rows[digest],
            has_score="score" in history_columns,
        )
        for digest, (catalog_trace_version, snapshot) in catalogs.items()
    }
    observed = [row for row in rows if _row_is_observed(row)]
    complete = [row for row in observed if (_json_object(row["coerce_trace"]) or {}).get("complete") is True]
    return {
        "groups": groups,
        "global_coverage": {
            "total": len(rows),
            "observed": len(observed),
            "complete": len(complete),
            "incomplete": len(observed) - len(complete),
            "unobserved": len(rows) - len(observed),
        },
    }


def _readonly_connection(db_path: str) -> sqlite3.Connection:
    path = Path(db_path).expanduser().resolve()
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate versioned coerce observations without modifying SQLite.",
        epilog=(
            "Marker co-occurrence is not causal attribution. Determining whether a "
            "marker was necessary requires a separate counterfactual replay using the "
            "saved pre-coerce Score, expanded DDL, and catalog snapshot."
        ),
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--catalog-digest")
    parser.add_argument("--trace-version", type=int)
    args = parser.parse_args()
    with _readonly_connection(args.db) as conn:
        conn.row_factory = sqlite3.Row
        result = analyze(conn, args.catalog_digest, args.trace_version)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
