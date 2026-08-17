"""作曲フォールバックの記録 acceptance -- contract a-work-drawn-by-a-fallback-says-so.md.

T-230 (the save round trip), T-231 (the migration), T-234 (the sender census),
T-241 (the three states), T-242 (the paint route writes it itself, added by the
author's ruling of 2026-08-17 -- the route that saves a drawn work is the only
writer that knows whether Stage 2 fell, because the flag reaches a client only
in the response, after the row is already written).

The census reads the two client trees. They are present here and in the test
container alike (`testbox.sh` excludes only build output), and the test says so
rather than skipping: a gate that goes quiet when it cannot find its subject
reports green for the one reason that should be loud.
"""

from __future__ import annotations

import ast
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.api_core.models import HistoryItem, HistoryPostBody
from inku_server.api_core.rendering import COMPOSE_FALLBACK_NONE, compose_fallback_value
from inku_server.api_core.routers import render as render_routes
from inku_server.schema import Score

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).parents[1] / "src" / "inku_server"

client = TestClient(app)

SCORE = {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}


@pytest.fixture
def auth_context():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"compose-fallback-{suffix}")
    user = db.add_user(
        username=f"compose-fallback-{suffix}",
        email=f"compose-fallback-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}, user
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def _save(headers: dict, **overrides) -> dict:
    body = {"input": "作曲が落ちた作品", "score": SCORE, "at": 1, "save_artifacts": False}
    body.update(overrides)
    response = client.post("/api/history", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _read_back(headers: dict, history_id: str) -> dict:
    listing = client.get(
        "/api/history", params={"anchor_id": history_id, "limit": 100}, headers=headers
    ).json()
    return next(item for item in listing["items"] if item["id"] == history_id)


# --------------------------------------------------------------------- T-230

def test_t230_a_client_saved_reason_comes_back_out(auth_context):
    headers, user = auth_context
    saved = _save(headers, compose_fallback="stage2_hard_timeout")

    # Read through the listing, not off the object the POST returned: the round
    # trip is the claim, and a value that never reached a column would still be
    # echoed by the response model.
    assert _read_back(headers, saved["id"])["compose_fallback"] == "stage2_hard_timeout"
    db.delete_items(user["id"], [saved["id"]])


def test_t230_the_field_is_declared_on_the_body_and_on_the_item():
    assert "compose_fallback" in HistoryPostBody.model_fields
    # HistoryItem inherits the body, so this is the response model too. Declared
    # explicitly all the same: a field nobody declares is a field the response
    # model drops without a word.
    assert "compose_fallback" in HistoryItem.model_fields
    assert HistoryItem(**{"input": "x", "score": {}, "at": 1, "id": "i"}).compose_fallback is None


# --------------------------------------------------------------------- T-231

def test_t231_the_migration_has_no_default_and_no_backfill():
    from inku_server.db import _HISTORY_COLUMN_MIGRATIONS

    statement = _HISTORY_COLUMN_MIGRATIONS["compose_fallback"]
    assert statement == "ALTER TABLE history ADD COLUMN compose_fallback VARCHAR"
    # A DEFAULT would write "none" into all 3,459 existing rows and claim their
    # compose stage held; an UPDATE would guess the same thing louder.
    assert "DEFAULT" not in statement.upper()
    assert "UPDATE" not in statement.upper()


ROWS_BEFORE = 3459  # production, measured 2026-08-17


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
            interpret_fallback VARCHAR,
            trashed INTEGER NOT NULL DEFAULT 0, starred INTEGER NOT NULL DEFAULT 0, note TEXT
        );
        INSERT INTO user_groups VALUES ('group-1', 'default', 1);
        INSERT INTO user_accounts (
            id, username, email, password_hash, role, group_id, at
        ) VALUES ('user-1', 'legacy', 'legacy@example.test', 'unused', 'user', 'group-1', 1);
        """
    )
    connection.executemany(
        "INSERT INTO history (id, user_id, at, input, ddl, score, svg, interpret_fallback)"
        " VALUES (?, 'user-1', ?, ?, '円を置く。', '{\"instructions\": []}', '<svg/>', ?)",
        [
            (f"history-{i}", i + 2, f"作品 {i}", "stage1_hard_timeout" if i % 100 == 0 else None)
            for i in range(rows)
        ],
    )
    connection.commit()
    connection.close()


def test_t231_the_migration_adds_the_column_and_keeps_every_row(tmp_path: Path):
    db_path = tmp_path / "pre-compose-fallback.db"
    _create_pre_column_database(db_path, ROWS_BEFORE)

    with sqlite3.connect(db_path) as probe:
        before = probe.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        stage1_before = probe.execute(
            "SELECT COUNT(*) FROM history WHERE interpret_fallback IS NOT NULL"
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
        'null_compose': session.query(db.HistoryRow)
            .filter(db.HistoryRow.compose_fallback.is_(None)).count(),
        'stage1': session.query(db.HistoryRow)
            .filter(db.HistoryRow.interpret_fallback.isnot(None)).count(),
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

    assert "compose_fallback" in payload["columns"]
    assert payload["rows"] == before
    # Every one of them, still NULL. Backfilling is the failure this counts.
    assert payload["null_compose"] == before
    assert payload["stage1"] == stage1_before
    assert payload["first_input"] == "作品 0"


# --------------------------------------------------------------------- T-234

def _client_senders() -> dict[str, str]:
    """The two client trees that POST a drawn work to /api/history."""
    web = REPO_ROOT / "web" / "src" / "routes" / "+page.svelte"
    cli = REPO_ROOT / "cli" / "src" / "inku_cli" / "cli.py"
    # Named, and asserted rather than skipped: a census that cannot see its
    # subjects has to say so, not pass.
    assert web.is_file(), f"the web sender is not where the census looks: {web}"
    assert cli.is_file(), f"the cli sender is not where the census looks: {cli}"
    return {"web": web.read_text(encoding="utf-8"), "cli": cli.read_text(encoding="utf-8")}


def test_t234_every_sender_that_saves_a_drawn_work_stacks_the_key(auth_context):
    headers, user = auth_context
    sources = _client_senders()

    # Two senders, and the count is part of the claim: a third client that
    # learns to save would have to come here and be counted.
    assert sorted(sources) == ["cli", "web"]
    silent = [name for name, text in sources.items() if "compose_fallback" not in text]
    assert not silent, f"these save a drawn work without saying what compose did: {silent}"
    # Each of them writes the value either way, not only when it fell.
    for name, text in sources.items():
        assert "composeFallbackValue" in text or "_compose_fallback_value" in text, (
            f"{name} names the key but does not send an effective value"
        )

    # And the far end stores what they send. Dropping the assignment in the save
    # route leaves both senders correct and the column empty, which is the same
    # silence from the reader's side.
    saved = _save(headers, compose_fallback=COMPOSE_FALLBACK_NONE)
    assert _read_back(headers, saved["id"])["compose_fallback"] == COMPOSE_FALLBACK_NONE
    db.delete_items(user["id"], [saved["id"]])


# --------------------------------------------------------------------- T-241

def test_t241_the_three_states_are_told_apart():
    def item(value: str | None) -> dict:
        row = db.HistoryRow(
            id="compose-fallback-read", user_id="u", at=1, input="x",
            score="{}", svg="", elapsed_ms=0, trashed=0, starred=0, for_revision=0,
            compose_fallback=value,
        )
        return db._row_to_dict(row)

    # Fell: the reason is carried as written.
    assert item("stage2_hard_timeout")["compose_fallback"] == "stage2_hard_timeout"
    # Held: a value, so a reader knows somebody looked.
    assert item(COMPOSE_FALLBACK_NONE)["compose_fallback"] == COMPOSE_FALLBACK_NONE
    # Unrecorded: no key at all. Not None -- a null would read as "held" to
    # anything that only asks whether the key is falsy.
    assert "compose_fallback" not in item(None)


# --------------------------------------------------------------------- T-242

def test_t242_the_paint_route_writes_the_reason_when_compose_fell(monkeypatch):
    captured = _capture_saved_work(monkeypatch, fallback_used=True, reasons=["stage2_hard_timeout"])
    assert captured["compose_fallback"] == "stage2_hard_timeout"


def test_t242_the_paint_route_writes_none_when_compose_held(monkeypatch):
    captured = _capture_saved_work(monkeypatch, fallback_used=False, reasons=[])
    # The route knows the answer either way, and says it either way. Left to
    # NULL, every work drawn through the ordinary path would be indistinguishable
    # from the 3,459 drawn before the column.
    assert captured["compose_fallback"] == COMPOSE_FALLBACK_NONE


def test_t242_the_value_is_derived_in_one_place():
    assert compose_fallback_value(fallback_used=False, reasons=["ignored"]) == COMPOSE_FALLBACK_NONE
    assert compose_fallback_value(fallback_used=True, reasons=[]) == "stage2_fallback"
    assert compose_fallback_value(fallback_used=True, reasons=None) == "stage2_fallback"
    assert compose_fallback_value(fallback_used=True, reasons=["a", "b"]) == "a"


def test_t242_every_server_writer_of_a_work_also_writes_the_compose_state():
    """Counted from the syntax, because main moves and line numbers do not survive it."""
    sites: list[tuple[str, bool]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = str(path.relative_to(SRC))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                names = {kw.arg for kw in node.keywords if kw.arg}
                if "interpret_fallback" in names:
                    label = getattr(node.func, "id", None) or getattr(node.func, "attr", None) or "?"
                    sites.append((f"{rel}:{label}(kwargs)", "compose_fallback" in names))
            elif isinstance(node, ast.Dict):
                keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
                if "interpret_fallback" in keys:
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
                    sites.append((f"{rel}:{kind}", "compose_fallback" in keys))
            elif isinstance(node, ast.FunctionDef):
                names = {a.arg for a in node.args.args + node.args.kwonlyargs}
                if "interpret_fallback" in names:
                    sites.append((f"{rel}:def {node.name}", "compose_fallback" in names))

    missing = [where for where, has_compose in sites if not has_compose]
    assert not missing, f"these carry Stage 1's record but not Stage 2's: {missing}"
    labels = {where for where, _ in sites}
    # The paint route, the client save route, the floor both land on, the helper
    # they share, the dict it builds, the row the importer rebuilds, and the
    # table that declares the column.
    assert "api_core/routers/render.py:_add_history_item(kwargs)" in labels
    assert "api_core/routers/history.py:_add_history_item(kwargs)" in labels
    assert "api_core/rendering.py:def _add_history_item" in labels
    assert "api_core/rendering.py:dict" in labels
    assert "db.py:HistoryRow(kwargs)" in labels
    assert "db.py:migration table" in labels
    # The count is part of the claim, for the same reason the sketch census
    # keeps one: a new writer has to be named here rather than added quietly.
    assert len(sites) == 6, f"expected 6 sites, saw {len(sites)}: {sorted(labels)}"


def _capture_saved_work(monkeypatch, *, fallback_used: bool, reasons: list[str]) -> dict:
    """Run a real paint and return everything the route handed the history writer."""
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

    score = Score.model_validate(SCORE)

    # The product's own dataclass, not a stand-in: a hand-written double drifts
    # from the real one and the route would then be tested against a shape it
    # never receives.
    detail = render_routes.ComposeDetail(
        score=score,
        ddl="黒い円を中心に置く。",
        source_ddl="黒い円を中心に置く。",
        tokens_in=5,
        tokens_out=6,
        retry_count=len(reasons),
        retry_reasons=list(reasons),
        fallback_used=fallback_used,
    )

    monkeypatch.setattr(render_routes, "_add_history_item", fake_add)
    monkeypatch.setattr(
        render_routes, "interpret_detail", lambda text, **kwargs: ("黒い円を中心に置く。", None, 3, 4)
    )
    # The stage itself is replaced, not the flag: the route reads the detail
    # object the composer hands back, and that is the wiring under test.
    monkeypatch.setattr(
        render_routes, "_call_compose_detail", lambda ddl, **kwargs: detail
    )
    monkeypatch.setattr(render_routes, "coerce_score", lambda score, **kwargs: score)

    request = render_routes.PaintRequest(
        description="作曲が落ちる記述",
        sketch=False,
        instruction_lang="ja",
        save_history=True,
        save_artifacts=False,
        count_generation=False,
    )
    for event in render_routes._paint_events(request, None, {"id": "test-user"}):
        if event["event"] == "done":
            break
    assert captured, "the paint route saved nothing"
    return captured
