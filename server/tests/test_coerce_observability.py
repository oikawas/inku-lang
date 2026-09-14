from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import uuid

from sqlalchemy import create_engine, inspect, text

from inku_server import db
from inku_server.api_core.rendering import _add_history_item
from inku_server.api_core.models import HistoryPostBody
from inku_server.api_core.routers.history import api_history_post
from inku_server.limits import DEFAULT_LIMITS
from inku_server.saved_score_compat import coerce_saved_score
from inku_server.schema import Score


ANALYZER = Path(__file__).parents[1] / "scripts" / "analyze_coerce_trace.py"


def _actor():
    db.init_db()
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"coerce-observability-{suffix}")
    user = db.add_user(
        username=f"coerce-observability-{suffix}",
        email=f"coerce-observability-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    return user, group


def test_t316_legacy_migration_keeps_observation_unrecorded_and_private(tmp_path, monkeypatch):
    from inku_server.coerce.observability import INTERNAL_HISTORY_COLUMNS

    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with legacy.begin() as conn:
        conn.execute(text("CREATE TABLE history (id VARCHAR PRIMARY KEY, at BIGINT NOT NULL, input TEXT NOT NULL DEFAULT '', ddl TEXT, score TEXT NOT NULL DEFAULT '{}', svg TEXT NOT NULL DEFAULT '', output_path TEXT, elapsed_ms INTEGER NOT NULL DEFAULT 0)"))
        conn.execute(text("CREATE TABLE user_accounts (id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL, email VARCHAR NOT NULL, password_hash TEXT NOT NULL, role VARCHAR NOT NULL, group_id VARCHAR, at BIGINT NOT NULL)"))
        conn.execute(text("INSERT INTO history (id, at, input, score, svg) VALUES ('old', 1, 'old', '{}', '')"))
    monkeypatch.setattr(db, "engine", legacy)
    db._migrate_columns()
    columns = {column["name"] for column in inspect(legacy).get_columns("history")}
    assert set(INTERNAL_HISTORY_COLUMNS) <= columns
    assert inspect(legacy).has_table("coerce_trace_catalogs")
    assert not inspect(legacy).has_table("history_fts")
    with legacy.connect() as conn:
        old = conn.execute(text("SELECT score_pre_coerce, coerce_trace_version, coerce_catalog_digest, coerce_trace FROM history WHERE id = 'old'")).one()
    assert old == (None, None, None, None)


def test_t320_migrated_legacy_row_stays_unobserved_not_complete_zero(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy-unobserved.db"
    legacy = create_engine(f"sqlite:///{legacy_path}", future=True)
    with legacy.begin() as conn:
        conn.execute(text("CREATE TABLE history (id VARCHAR PRIMARY KEY, at BIGINT NOT NULL, input TEXT NOT NULL DEFAULT '', ddl TEXT, score TEXT NOT NULL DEFAULT '{}', svg TEXT NOT NULL DEFAULT '', output_path TEXT, elapsed_ms INTEGER NOT NULL DEFAULT 0)"))
        conn.execute(text("CREATE TABLE user_accounts (id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL, email VARCHAR NOT NULL, password_hash TEXT NOT NULL, role VARCHAR NOT NULL, group_id VARCHAR, at BIGINT NOT NULL)"))
        conn.execute(text("INSERT INTO history (id, at, input, score, svg) VALUES ('old', 1, 'old', '{}', '')"))
    monkeypatch.setattr(db, "engine", legacy)
    db._migrate_columns()
    result = subprocess.run(
        [sys.executable, str(ANALYZER), "--db", str(legacy_path), "--json"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(result.stdout)["global_coverage"] == {
        "total": 1,
        "observed": 0,
        "complete": 0,
        "incomplete": 0,
        "unobserved": 1,
    }


def test_t317_save_captures_hidden_trace_non_save_writes_nothing_and_replay_is_immutable():
    from inku_server.api_core.rendering import _capture_history_coerce_observability

    actor, group = _actor()
    try:
        score = Score.model_validate({"background": "white", "instructions": []})
        trace = _capture_history_coerce_observability(score, lang="en")
        post = coerce_saved_score(
            score,
            limits=DEFAULT_LIMITS,
            lang="en",
            trace=trace,
        )
        stored = _add_history_item(
            actor=actor, input_text="night", ddl="night", expanded_ddl="night", score=post,
            svg="<svg/>", at=1, save_artifacts=False, idempotency_key="i331-replay",
            coerce_observability=trace.persistable(),
        )
        replay = _add_history_item(
            actor=actor, input_text="changed", ddl="changed", expanded_ddl="changed", score=score,
            svg="<svg changed/>", at=2, save_artifacts=False, idempotency_key="i331-replay",
            coerce_observability={"complete": False},
        )
        assert replay["id"] == stored["id"]
        with db.SessionLocal() as session:
            row = session.get(db.HistoryRow, stored["id"])
            assert row.score_pre_coerce == json.dumps(score.model_dump(by_alias=True), ensure_ascii=False)
            assert row.coerce_trace_version == 1
            assert row.coerce_catalog_digest
            assert json.loads(row.coerce_trace)["complete"] is True
        assert "coerce_trace" not in db.get_items(actor["id"], [stored["id"]])[0]
    finally:
        db.delete_items(actor["id"], [stored["id"]] if "stored" in locals() else [])
        db.delete_user(actor["id"])
        db.delete_user_group(group["id"])

def test_t316_history_api_output_stays_public_while_private_trace_is_saved(monkeypatch):
    from inku_server.api_core import rendering

    monkeypatch.setattr(rendering, "_submit_thumbnail_build", lambda _item: None)
    actor, group = _actor()
    saved = None
    try:
        body = HistoryPostBody(
            input="three hundred squares",
            ddl="Place three hundred squares in the upper right.",
            score={
                "background": "white",
                "instructions": [
                    {
                        "primitive": "circle",
                        "center": [0.23, 0.67],
                        "radius": 0.04,
                        "arrangement": {"count": 7, "layout": "scatter"},
                    }
                ],
            },
            at=4,
            save_artifacts=False,
        )
        saved = api_history_post(body, idempotency_key=None, actor=actor)
        public = saved.model_dump()
        assert len(public["score"]["instructions"]) == 1
        instruction = public["score"]["instructions"][0]
        assert instruction["primitive"] == "circle"
        assert instruction["center"] == [0.23, 0.67]
        assert instruction["radius"] == 0.04
        assert instruction["arrangement"]["count"] == 7
        assert saved.svg.startswith("<svg")
        assert not set(public) & {
            "score_pre_coerce",
            "coerce_trace_version",
            "coerce_catalog_digest",
            "coerce_trace",
        }
        with db.SessionLocal() as session:
            row = session.get(db.HistoryRow, saved.id)
            assert row is not None
            assert row.score_pre_coerce is not None
            assert row.coerce_trace is not None
    finally:
        db.delete_items(actor["id"], [saved.id] if saved is not None else [])
        db.delete_user(actor["id"])
        db.delete_user_group(group["id"])


def test_t317_history_api_persists_private_capture_without_a_public_trace_field():
    actor, group = _actor()
    saved = None
    try:
        saved = api_history_post(
            HistoryPostBody(
                input="night",
                score={"background": "white", "instructions": []},
                at=3,
                save_artifacts=False,
            ),
            idempotency_key=None,
            actor=actor,
        )
        with db.SessionLocal() as session:
            row = session.get(db.HistoryRow, saved.id)
            assert row is not None
            assert row.score_pre_coerce is not None
            assert row.coerce_trace_version == 1
            assert row.coerce_catalog_digest is not None
            assert json.loads(row.coerce_trace)["complete"] is True
        assert "coerce_trace" not in saved.model_dump()
    finally:
        db.delete_items(actor["id"], [saved.id] if saved is not None else [])
        db.delete_user(actor["id"])
        db.delete_user_group(group["id"])
