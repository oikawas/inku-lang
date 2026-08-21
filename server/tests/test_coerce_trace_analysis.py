from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from inku_server.coerce import coerce_score
from inku_server.schema import Score


SCRIPT = Path(__file__).parents[1] / "scripts" / "analyze_coerce_trace.py"


def _make_db(path: Path, *, count: int = 4) -> str:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE history (
            id TEXT PRIMARY KEY,
            score_pre_coerce TEXT,
            coerce_trace_version INTEGER,
            coerce_catalog_digest TEXT,
            coerce_trace TEXT
        );
        CREATE TABLE coerce_trace_catalogs (
            digest TEXT PRIMARY KEY,
            trace_version INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL
        );
    """)
    digest_a = "a" * 64
    digest_b = "b" * 64
    snapshot = {"trace_version": 1, "markers": [{"marker": "night", "system": "night", "language": "en", "decision_site": "background", "match_mode": "word"}, {"marker": "night", "system": "edge_light", "language": "en", "decision_site": "edge", "match_mode": "word"}], "branches": ["with_background_dominance_governor"]}
    payload = json.dumps(snapshot, separators=(",", ":"))
    conn.executemany("INSERT INTO coerce_trace_catalogs VALUES (?, 1, ?)", [(digest_a, payload), (digest_b, payload)])
    rows = []
    for index in range(count):
        digest = digest_a if index < count - 1 else digest_b
        trace = {"complete": index % 3 != 1, "executed": index % 3 == 0, "disabled": False, "marker_events": [{"marker": "night", "system": "night", "language": "en", "decision_site": "background", "match_mode": "word"}, {"marker": "night", "system": "edge_light", "language": "en", "decision_site": "edge", "match_mode": "word"}], "branch_events": [{"branch": "with_background_dominance_governor", "change_count": 1, "changed_fields": [{"path": "/background", "effect": "replace"}]}]}
        rows.append((str(index), "{}", 1, digest, json.dumps(trace)))
    conn.executemany("INSERT INTO history VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return digest_a


def test_t321_cli_is_read_only_and_groups_catalog_versions(tmp_path):
    db_path = tmp_path / "trace.db"
    digest = _make_db(db_path)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    result = subprocess.run([sys.executable, str(SCRIPT), "--db", str(db_path), "--json"], check=True, text=True, capture_output=True)
    after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    data = json.loads(result.stdout)
    assert before == after
    assert set(data["groups"]) == {digest, "b" * 64}
    coverage = data["groups"][digest]["coverage"]
    assert coverage["incomplete"] == 1
    assert coverage["complete"] == 2
    assert data["groups"][digest]["historical_marker_measurement_eligible"] is True
    assert data["groups"][digest]["current_code_replay_eligible"] is False


def test_t322_cli_preserves_overlap_and_marks_co_matched_ambiguous(tmp_path):
    db_path = tmp_path / "trace.db"
    digest = _make_db(db_path)
    result = subprocess.run([sys.executable, str(SCRIPT), "--db", str(db_path), "--json", "--catalog-digest", digest], check=True, text=True, capture_output=True)
    marker = json.loads(result.stdout)["groups"][digest]["markers"]["night"]
    assert marker["membership_count"] == 2
    assert marker["matched_work"] == 2
    assert marker["unique_attributed"] == 0
    assert marker["ambiguous"] == 2


def _persist_trace_db(path: Path, traces: list[dict], snapshot: dict) -> str:
    from inku_server.coerce.observability import catalog_digest

    digest = catalog_digest(snapshot)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE history (
            id TEXT PRIMARY KEY,
            score_pre_coerce TEXT,
            coerce_trace_version INTEGER,
            coerce_catalog_digest TEXT,
            coerce_trace TEXT
        );
        CREATE TABLE coerce_trace_catalogs (
            digest TEXT PRIMARY KEY,
            trace_version INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL
        );
    """)
    conn.execute(
        "INSERT INTO coerce_trace_catalogs VALUES (?, ?, ?)",
        (digest, snapshot["trace_version"], json.dumps(snapshot, separators=(",", ":"))),
    )
    conn.executemany(
        "INSERT INTO history VALUES (?, ?, ?, ?, ?)",
        [
            (str(index), "{}", trace["trace_version"], digest, json.dumps(trace))
            for index, trace in enumerate(traces)
        ],
    )
    conn.commit()
    conn.close()
    return digest


def test_t322_actual_persisted_catalog_preserves_same_marker_memberships(tmp_path):
    from inku_server.coerce.observability import catalog_snapshot

    snapshot = catalog_snapshot()
    memberships = [event for event in snapshot["markers"] if event["marker"] == "right half"]
    assert len({event["system"] for event in memberships}) > 1
    trace = {
        "complete": True,
        "executed": True,
        "disabled": False,
        "marker_events": memberships,
        "branch_events": [],
        "trace_version": snapshot["trace_version"],
    }
    path = tmp_path / "actual-catalog.db"
    digest = _persist_trace_db(path, [trace], snapshot)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(path), "--json", "--catalog-digest", digest],
        check=True,
        text=True,
        capture_output=True,
    )
    marker = json.loads(result.stdout)["groups"][digest]["markers"]["right half"]
    assert marker == {
        "membership_count": len(memberships),
        "matched_work": 1,
        "unique_attributed": 0,
        "ambiguous": 1,
    }


def test_t321_actual_captured_trace_aggregates_changed_paths_and_effects(tmp_path):
    from inku_server.coerce.observability import capture_context

    score = Score.model_validate({"background": "white", "instructions": [{"primitive": "circle", "color": "white", "center": [0.5, 0.5], "radius": 0.1}]})
    trace = capture_context(score, ddl="blue", lang="en")
    coerce_score(score, ddl="blue", lang="en", trace=trace)
    persisted = trace.persistable()
    expected_effects: dict[str, int] = {}
    for branch in persisted["branch_events"]:
        for field in branch["changed_fields"]:
            key = f"{field['path']}:{field['effect']}"
            expected_effects[key] = expected_effects.get(key, 0) + 1
    assert expected_effects
    path = tmp_path / "actual-effects.db"
    digest = _persist_trace_db(path, [persisted], persisted["catalog_snapshot"])
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(path), "--json"],
        check=True,
        text=True,
        capture_output=True,
    )
    group = json.loads(result.stdout)["groups"][digest]
    assert group["effects"] == expected_effects


def test_t321_actual_incomplete_trace_is_excluded_from_complete_denominator(tmp_path):
    from inku_server.coerce.observability import capture_context

    score = Score.model_validate({"background": "white", "instructions": []})
    complete = capture_context(score, ddl="night", lang="en")
    coerce_score(score, ddl="night", lang="en", trace=complete)
    incomplete = capture_context(score, ddl="night", lang="en")
    complete_trace = complete.persistable()
    incomplete_trace = incomplete.persistable()
    assert incomplete_trace["complete"] is False
    path = tmp_path / "incomplete-denominator.db"
    digest = _persist_trace_db(
        path,
        [complete_trace, incomplete_trace],
        complete_trace["catalog_snapshot"],
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(path), "--json"],
        check=True,
        text=True,
        capture_output=True,
    )
    coverage = json.loads(result.stdout)["groups"][digest]["coverage"]
    assert coverage["observed"] == 2
    assert coverage["complete"] == 1
    assert coverage["incomplete"] == 1


def _make_3486_simulation(path: Path, *, observed: bool) -> None:
    conn = sqlite3.connect(path)
    if observed:
        conn.executescript("""
            CREATE TABLE history (id TEXT PRIMARY KEY, score TEXT, score_pre_coerce TEXT, coerce_trace_version INTEGER, coerce_catalog_digest TEXT, coerce_trace TEXT);
            CREATE TABLE coerce_trace_catalogs (digest TEXT PRIMARY KEY, trace_version INTEGER NOT NULL, snapshot_json TEXT NOT NULL);
        """)
    else:
        conn.execute("CREATE TABLE history (id TEXT PRIMARY KEY, score TEXT)")
    systems = [f"system-{index:02d}" for index in range(69)]
    markers = [{"system": system, "marker": f"marker-{index:02d}", "language": "en", "decision_site": system, "match_mode": "word"} for index, system in enumerate(systems)]
    markers.extend([
        {"system": "presence_center_right_half", "marker": "right half", "language": "en", "decision_site": "presence", "match_mode": "word"},
        {"system": "fallback_place_right_half", "marker": "right half", "language": "en", "decision_site": "fallback", "match_mode": "word"},
        {"system": "zero-marker", "marker": "never-fired", "language": "en", "decision_site": "zero", "match_mode": "word"},
    ])
    snapshot = json.dumps({"trace_version": 1, "markers": markers, "branches": ["changed", "zero-branch"]}, separators=(",", ":"))
    digest_a, digest_b = "a" * 64, "b" * 64
    if observed:
        conn.executemany("INSERT INTO coerce_trace_catalogs VALUES (?, 1, ?)", [(digest_a, snapshot), (digest_b, snapshot)])
    score = json.dumps({"background": "white", "instructions": [], "padding": "x" * 3070}, separators=(",", ":"))
    rows = []
    for index in range(3486):
        if not observed:
            rows.append((str(index), score))
            continue
        digest = digest_a if index < 3000 else digest_b
        if index % 97 == 0:
            rows.append((str(index), score, None, None, None, None))
            continue
        trace = {"complete": index % 11 != 0, "executed": index % 3 == 0, "disabled": index % 3 == 2, "marker_events": ([markers[0], markers[-3], markers[-2]] if index % 5 == 0 else []), "branch_events": ([{"branch": "changed", "change_count": 1, "changed_fields": [{"path": "/background", "effect": "replace"}]}] if index % 7 == 0 else [])}
        rows.append((str(index), score, score, 1, digest, json.dumps(trace, separators=(",", ":"))))
    if observed:
        conn.executemany("INSERT INTO history VALUES (?, ?, ?, ?, ?, ?)", rows)
    else:
        conn.executemany("INSERT INTO history VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def test_t323_real_3486_row_sqlite_simulation_stays_under_storage_budget(tmp_path):
    baseline = tmp_path / "baseline.db"
    observed = tmp_path / "observed.db"
    _make_3486_simulation(baseline, observed=False)
    _make_3486_simulation(observed, observed=True)
    growth = observed.stat().st_size - baseline.stat().st_size
    assert growth <= 20 * 1024 * 1024
    assert growth / 3486 <= 6 * 1024
    result = subprocess.run([sys.executable, str(SCRIPT), "--db", str(observed), "--json"], check=True, text=True, capture_output=True)
    groups = json.loads(result.stdout)["groups"]
    data = json.loads(result.stdout)
    groups = data["groups"]
    assert data["global_coverage"] == {
        "total": 3486,
        "observed": 3450,
        "complete": 3137,
        "incomplete": 313,
        "unobserved": 36,
    }
    assert sum(group["coverage"]["total"] for group in groups.values()) == 3450
    with sqlite3.connect(observed) as conn:
        average_pre_score_bytes = conn.execute(
            "SELECT AVG(LENGTH(score_pre_coerce)) FROM history "
            "WHERE score_pre_coerce IS NOT NULL"
        ).fetchone()[0]
    assert 3_100 <= average_pre_score_bytes <= 3_200
    assert len(groups) == 2
    assert sum(group["coverage"]["incomplete"] for group in groups.values()) > 0
    assert all(group["catalog_population"]["system_count"] == 72 for group in groups.values())
    assert all("never-fired" in group["zero_markers"] for group in groups.values())
    assert all("zero-branch" in group["zero_branches"] for group in groups.values())
