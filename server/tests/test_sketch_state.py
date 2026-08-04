"""写生の状態 (sketch_state) acceptance -- contract tasks/sketch-state-is-recorded.md.

T-1 (the five states), T-2 (the writer census), T-3 (NULL is not "off"),
T-4 (a failed layer is recorded), T-5 (the migration keeps the rows),
T-7 (the state is read back out).

Every state gate here runs a real paint or compose and reads what the
production path handed the writer. Calling the derivation function alone would
pass while no route used it: an unconsumed probe is a vacuous gate. The one
exception is marked, and says why.
"""

from __future__ import annotations

import ast
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

# Importing the app is what creates the schema for the test database.
from inku_server.api import app as _app  # noqa: F401
from inku_server.api_core.routers import render as render_routes
from inku_server.schema import Score
from inku_server.sketch import SKETCH_STATES, SketchDetail, sketch_state_of


SRC = Path(__file__).parents[1] / "src" / "inku_server"

DESCRIPTION = "ひさかたの光のどけき春の日にしづ心なく花の散るらむ"

SCORE = Score.model_validate(
    {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
)


@pytest.fixture
def wired(monkeypatch):
    """Replace every model call, leaving the wiring untouched."""

    def fake_sketch(text, *, model=None, lang="ja", grain="fine"):
        return f"[{grain}] 円がある。円は黒い。", 11, 22

    def fake_interpret(text, **kwargs):
        return "黒い円を中心に置く。", None, 3, 4

    class FakeExpansion:
        ddl = "黒い円を中心に置く。"
        provenance: list = []
        warnings: list = []
        instructions: list = []

    monkeypatch.setattr(render_routes, "sketch_from_life", fake_sketch)
    monkeypatch.setattr(render_routes, "interpret_detail", fake_interpret)
    monkeypatch.setattr(
        render_routes.DOCUMENT_PLUGIN_MANAGER, "expand", lambda ddl, **kwargs: FakeExpansion()
    )
    monkeypatch.setattr(
        render_routes, "expand_intermediate_for_lang", lambda ddl, **kwargs: ddl
    )
    monkeypatch.setattr(render_routes, "compose", lambda ddl, **kwargs: (SCORE, 5, 6))
    monkeypatch.setattr(render_routes, "coerce_score", lambda score, **kwargs: score)


@pytest.fixture
def saved(monkeypatch):
    """Everything the paint route handed the history writer."""
    captured: dict = {}

    def fake_add(**kwargs):
        captured.update(kwargs)
        return {
            "id": "h1",
            "description_hash": None,
            "lineage_node_id": None,
            "lineage_parent_node_id": None,
            "derivation_kind": None,
        }

    monkeypatch.setattr(render_routes, "_add_history_item", fake_add)
    return captured


def paint(**overrides):
    body = {
        "description": DESCRIPTION,
        "sketch": True,
        "instruction_lang": "ja",
        "save_history": True,
        "save_artifacts": False,
        "count_generation": False,
    }
    body.update(overrides)
    return render_routes.PaintRequest(**body)


def run_paint(req):
    for event in render_routes._paint_events(req, None, {"id": "test-user"}):
        if event["event"] == "done":
            return event["response"]
    raise AssertionError("the paint produced no result")


# --------------------------------------------------------------------- T-1

def test_t1_the_layer_ran_fine(wired, saved):
    response = run_paint(paint())

    assert response.sketch_state == "fine"
    assert saved["sketch_state"] == "fine"
    assert saved["sketch_text"]


def test_t1_the_layer_ran_coarse(wired, saved):
    response = run_paint(paint(sketch_grain="coarse"))

    assert response.sketch_state == "coarse"
    assert saved["sketch_state"] == "coarse"
    assert saved["sketch_text"]


def test_t1_the_layer_was_switched_off(wired, saved):
    response = run_paint(paint(sketch=False))

    # "off" is a choice the author made, and the prose column stays empty: the
    # two together are what tell this apart from a work that predates the layer.
    assert response.sketch_state == "off"
    assert saved["sketch_state"] == "off"
    assert saved["sketch_text"] is None


def test_t1_a_work_authored_straight_in_ddl_is_not_applicable(wired):
    # The route that begins at Stage 2 with no description: the layer has
    # nothing to read, so it neither ran nor was refused.
    req = render_routes.ComposeRequest(ddl="黒い円を中心に置く。", instruction_lang="ja")
    response = render_routes.api_compose(req, {"id": "test-user"})

    assert response.sketch_state == "not_applicable"
    assert response.sketch_text is None


def test_t1_the_layer_failed(wired, saved, monkeypatch):
    def boom(text, **kwargs):
        raise RuntimeError("the provider is down")

    monkeypatch.setattr(render_routes, "sketch_from_life", boom)
    response = run_paint(paint())

    assert response.sketch_state == "fallback"
    assert saved["sketch_state"] == "fallback"


def test_t1_a_compose_that_carries_prose_records_its_grain(wired):
    req = render_routes.ComposeRequest(
        ddl="黒い円を中心に置く。",
        description=DESCRIPTION,
        sketch_text="白い花びらが幾つも落ちる。",
        sketch_grain="coarse",
        instruction_lang="ja",
    )
    response = render_routes.api_compose(req, {"id": "test-user"})

    assert response.sketch_state == "coarse"


def test_t1_a_compose_with_a_description_and_no_prose_is_off(wired):
    req = render_routes.ComposeRequest(
        ddl="黒い円を中心に置く。", description=DESCRIPTION, instruction_lang="ja"
    )
    response = render_routes.api_compose(req, {"id": "test-user"})

    assert response.sketch_state == "off"


def test_t1_the_derivation_names_a_state_for_every_caller():
    # Direct, and marked as such: this is the one combination no route can
    # reach today -- a caller that asks for the layer on a route that does not
    # run it. It is here so a future route cannot record a wiring failure as a
    # choice the author made.
    assert (
        sketch_state_of(None, requested=True, has_description=True) == "not_applicable"
    )
    assert sketch_state_of(None, requested=False, has_description=True) == "off"
    assert sketch_state_of(None, requested=False, has_description=False) == "not_applicable"
    assert (
        sketch_state_of(SketchDetail(text="x", grain="coarse"), requested=True, has_description=True)
        == "coarse"
    )
    assert (
        sketch_state_of(
            SketchDetail(text="x", grain="fine", fallback_used=True),
            requested=True,
            has_description=True,
        )
        == "fallback"
    )


# --------------------------------------------------------------------- T-2

def _sketch_write_sites() -> list[tuple[str, str]]:
    """Every place in the server that writes sketch_text alongside a work.

    Counted from the syntax, not from line numbers: main moves. Three shapes
    write one -- a keyword argument, a dict literal, and the parameter list of
    the helper the two save routes share.
    """
    sites: list[tuple[str, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = str(path.relative_to(SRC))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                names = {kw.arg for kw in node.keywords if kw.arg}
                if "sketch_text" in names:
                    func = node.func
                    label = getattr(func, "id", None) or getattr(func, "attr", None) or "?"
                    sites.append((f"{rel}:{label}(kwargs)", "sketch_state" in names))
            elif isinstance(node, ast.Dict):
                keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
                if "sketch_text" in keys:
                    kind = (
                        "migration table"
                        if any(
                            isinstance(v, ast.Constant)
                            and isinstance(v.value, str)
                            and "ALTER TABLE" in v.value
                            for v in node.values
                        )
                        else "dict"
                    )
                    sites.append((f"{rel}:{kind}", "sketch_state" in keys))
            elif isinstance(node, ast.FunctionDef):
                args = node.args
                names = {a.arg for a in args.args + args.kwonlyargs}
                if "sketch_text" in names:
                    sites.append((f"{rel}:def {node.name}", "sketch_state" in names))
    return sites


def test_t2_every_writer_of_the_prose_also_writes_the_state():
    sites = _sketch_write_sites()
    missing = [where for where, has_state in sites if not has_state]

    assert not missing, f"these carry sketch_text but not sketch_state: {missing}"
    # The count is part of the claim. A new writer changes it, and whoever adds
    # one has to come here and say which kind it is: adding a column and fixing
    # one writer is the failure this gate exists to catch.
    assert len(sites) == 8, f"expected 8 sites, saw {len(sites)}: {[s for s, _ in sites]}"

    labels = {where for where, _ in sites}
    # Three saves: the paint route, the client save route, and the floor both
    # land on. Then the helper the two routes share, the dict it builds, the
    # table that declares the column, and the two responses that carry the state
    # back to a client that saves for itself.
    assert "api_core/routers/render.py:_add_history_item(kwargs)" in labels
    assert "api_core/routers/history.py:_add_history_item(kwargs)" in labels
    assert "db.py:HistoryRow(kwargs)" in labels
    assert "api_core/rendering.py:def _add_history_item" in labels
    assert "api_core/rendering.py:dict" in labels
    assert "db.py:migration table" in labels
    assert "api_core/routers/render.py:ComposeResponse(kwargs)" in labels
    assert "api_core/routers/render.py:PaintResponse(kwargs)" in labels


def test_t2_the_client_save_route_names_a_state_when_the_client_does_not():
    from inku_server.api_core.models import HistoryPostBody
    from inku_server.api_core.routers.history import _derived_sketch_state

    assert "sketch_state" in HistoryPostBody.model_fields

    base = {"input": DESCRIPTION, "score": {"instructions": []}, "at": 1}
    # A client that says nothing still gets a state. NULL would claim the work
    # was drawn before the column existed, which is a lie about a row written
    # today.
    assert _derived_sketch_state(HistoryPostBody(**base)) == "off"
    assert (
        _derived_sketch_state(
            HistoryPostBody(**base, sketch_text="円がある。", sketch_grain="coarse")
        )
        == "coarse"
    )
    assert _derived_sketch_state(HistoryPostBody(**{**base, "input": ""})) == "not_applicable"


def test_t2_an_unknown_state_from_a_client_is_refused():
    from pydantic import ValidationError

    from inku_server.api_core.models import HistoryPostBody

    with pytest.raises(ValidationError):
        HistoryPostBody(
            input=DESCRIPTION, score={"instructions": []}, at=1, sketch_state="sketched"
        )


# --------------------------------------------------------------------- T-3

def test_t3_the_migration_adds_no_default_and_fills_nothing():
    from inku_server.db import _HISTORY_COLUMN_MIGRATIONS

    statement = _HISTORY_COLUMN_MIGRATIONS["sketch_state"]
    assert statement == "ALTER TABLE history ADD COLUMN sketch_state VARCHAR"
    # Both halves matter: a DEFAULT would write "off" into every existing row,
    # and an UPDATE would guess. Either erases the distinction the column adds.
    assert "DEFAULT" not in statement.upper()
    assert "UPDATE" not in statement.upper()


def test_t3_the_column_holds_exactly_the_five_states_and_nothing_else():
    assert SKETCH_STATES == ("fine", "coarse", "fallback", "off", "not_applicable")
    # NULL is a sixth reading and is not one of these: it belongs to the rows,
    # not to the vocabulary.
    assert None not in SKETCH_STATES


def test_t3_a_row_without_a_state_reads_back_as_absent_not_as_off():
    from inku_server import db

    class Row:
        pass

    row = Row()
    for name in db.HistoryRow.__table__.columns.keys():
        setattr(row, name, None)
    row.id, row.at, row.input, row.score, row.svg = "x", 1, "", "{}", ""
    row.elapsed_ms, row.trashed, row.starred, row.for_revision = 0, 0, 0, 0

    item = db._row_to_dict(row)
    assert "sketch_state" not in item

    row.sketch_state = "off"
    assert db._row_to_dict(row)["sketch_state"] == "off"


# ----------------------------------------------------------------- T-4 / T-5

def test_t4_a_failed_layer_is_recorded_and_leaves_no_prose(wired, saved, monkeypatch):
    def boom(text, **kwargs):
        raise RuntimeError("the provider is down")

    monkeypatch.setattr(render_routes, "sketch_from_life", boom)
    response = run_paint(paint(sketch_grain="coarse"))

    # Information that has never been recorded before: until this column, a
    # layer that ran and lost was written down exactly like a layer that never
    # ran at all, so nobody could count how often 0.5 falls over in production.
    assert saved["sketch_state"] == "fallback"
    assert saved["sketch_text"] is None
    assert saved["sketch_grain"] is None
    assert response.sketch_fallback_used is True


ROWS_BEFORE = 2172  # production, measured 2026-08-04


def _create_pre_column_database(path: Path, rows: int) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE user_groups (
            id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL UNIQUE, at BIGINT NOT NULL
        );
        CREATE TABLE user_accounts (
            id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL UNIQUE,
            email VARCHAR NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            role VARCHAR NOT NULL, group_id VARCHAR, ui_theme VARCHAR NOT NULL DEFAULT 'light',
            settings_tab VARCHAR NOT NULL DEFAULT 'db', model_settings TEXT NOT NULL DEFAULT '{}',
            image_generation_count INTEGER NOT NULL DEFAULT 0,
            batch_prompt_history TEXT NOT NULL DEFAULT '[]', demo_settings TEXT NOT NULL DEFAULT '{}',
            export_templates TEXT NOT NULL DEFAULT '[]', plugin_storage TEXT NOT NULL DEFAULT '{}',
            at BIGINT NOT NULL
        );
        CREATE TABLE history (
            id VARCHAR PRIMARY KEY, user_id VARCHAR, at BIGINT NOT NULL,
            input TEXT NOT NULL DEFAULT '', ddl TEXT, score TEXT NOT NULL DEFAULT '{}',
            svg TEXT NOT NULL DEFAULT '', output_path TEXT, elapsed_ms INTEGER NOT NULL DEFAULT 0,
            stage1_model VARCHAR, stage2_model VARCHAR, tokens_in INTEGER, tokens_out INTEGER,
            catalog_id VARCHAR, render_build_number VARCHAR, render_hash VARCHAR,
            sketch_text TEXT, sketch_grain VARCHAR,
            trashed INTEGER NOT NULL DEFAULT 0, starred INTEGER NOT NULL DEFAULT 0, note TEXT
        );
        INSERT INTO user_groups VALUES ('group-1', 'default', 1);
        INSERT INTO user_accounts (
            id, username, email, password_hash, role, group_id, at
        ) VALUES ('user-1', 'legacy', 'legacy@example.test', 'unused', 'user', 'group-1', 1);
        """
    )
    connection.executemany(
        "INSERT INTO history (id, user_id, at, input, ddl, score, svg, sketch_text, sketch_grain)"
        " VALUES (?, 'user-1', ?, ?, '円を置く。', '{\"instructions\": []}', '<svg/>', ?, ?)",
        [
            (
                f"history-{i}",
                i + 2,
                f"作品 {i}",
                "円がある。" if i % 100 == 0 else None,
                "fine" if i % 100 == 0 else None,
            )
            for i in range(rows)
        ],
    )
    connection.commit()
    connection.close()


def test_t5_the_migration_keeps_every_row_and_leaves_them_null(tmp_path: Path):
    db_path = tmp_path / "pre-sketch-state.db"
    _create_pre_column_database(db_path, ROWS_BEFORE)

    with sqlite3.connect(db_path) as probe:
        before = probe.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        prose_before = probe.execute(
            "SELECT COUNT(*) FROM history WHERE sketch_text IS NOT NULL"
        ).fetchone()[0]
    assert before == ROWS_BEFORE

    code = """
import json
from sqlalchemy import inspect
from inku_server import db

db.init_db()
db.init_db()
with db.SessionLocal() as session:
    payload = {
        'rows': session.query(db.HistoryRow).count(),
        'null_state': session.query(db.HistoryRow)
            .filter(db.HistoryRow.sketch_state.is_(None)).count(),
        'prose': session.query(db.HistoryRow)
            .filter(db.HistoryRow.sketch_text.isnot(None)).count(),
        'columns': sorted(c['name'] for c in inspect(db.engine).get_columns('history')),
        'first_input': session.get(db.HistoryRow, 'history-0').input,
    }
print(json.dumps(payload, ensure_ascii=False))
"""
    env = os.environ.copy()
    env["INKU_DB_URL"] = f"sqlite:///{db_path}"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])

    # Counted before and counted after, not compared against a frozen number:
    # the production table grows every week, so a fixed figure fails for the
    # wrong reason.
    assert payload["rows"] == before
    assert payload["null_state"] == before
    assert payload["prose"] == prose_before
    assert "sketch_state" in payload["columns"]
    assert payload["first_input"] == "作品 0"


# --------------------------------------------------------------------- T-7

def test_t7_the_state_is_read_back_out_of_a_saved_work():
    from inku_server import db
    from inku_server.api_core.models import HistoryItem

    row = db.HistoryRow(
        id="sketch-state-read", user_id="u", at=1, input=DESCRIPTION,
        score="{}", svg="", elapsed_ms=0, trashed=0, starred=0, for_revision=0,
        sketch_text="円がある。", sketch_grain="fine", sketch_state="fine",
    )
    item = db._row_to_dict(row)

    assert item["sketch_state"] == "fine"
    # And it survives the response model, which is where a field that nobody
    # declared quietly disappears.
    assert HistoryItem(**{**item, "score": {}}).sketch_state == "fine"
