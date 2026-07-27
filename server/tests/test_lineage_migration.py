from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from inku_server.identity import description_hash


def _create_v175_database(path: Path) -> None:
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
            catalog_id VARCHAR, render_build_number VARCHAR, render_color_profile TEXT,
            render_engine_id VARCHAR, render_engine_version VARCHAR,
            render_color_catalog_id VARCHAR, render_color_catalog_name VARCHAR,
            render_color_catalog_sub VARCHAR, render_color_catalog TEXT, render_color_map TEXT,
            render_canvas_aspect VARCHAR, render_canvas_aspect_id VARCHAR,
            render_canvas_aspect_ratio FLOAT, instruction_lang_requested VARCHAR,
            instruction_lang_resolved VARCHAR, ui_lang VARCHAR, render_seed VARCHAR,
            composition_seed VARCHAR, interpretation_seed VARCHAR, render_hash VARCHAR,
            trashed INTEGER NOT NULL DEFAULT 0, starred INTEGER NOT NULL DEFAULT 0, note TEXT
        );
        INSERT INTO user_groups VALUES ('group-1', 'default', 1);
        INSERT INTO user_accounts (
            id, username, email, password_hash, role, group_id, at
        ) VALUES ('user-1', 'legacy', 'legacy@example.test', 'unused', 'user', 'group-1', 1);
        INSERT INTO history (
            id, user_id, at, input, ddl, score, svg, render_seed,
            render_build_number, render_engine_id, render_engine_version,
            render_color_catalog_id
        ) VALUES (
            'history-1', 'user-1', 2, '#1 作者が意図した本文', '円を置く。',
            '{"instructions": []}', '<svg/>', '7', '516', 'default', '3', 'default'
        );
        """
    )
    connection.commit()
    connection.close()


def test_v175_sqlite_migration_is_additive_idempotent_and_does_not_infer_edges(tmp_path: Path):
    db_path = tmp_path / "v175.db"
    _create_v175_database(db_path)
    code = """
import json
from sqlalchemy import inspect
from inku_server import db

db.init_db()
with db.SessionLocal() as session:
    first_node = session.query(db.LineageNodeRow).one().id
db.init_db()
with db.SessionLocal() as session:
    row = session.get(db.HistoryRow, 'history-1')
    payload = {
        'columns': sorted(column['name'] for column in inspect(db.engine).get_columns('history')),
        'lineage_columns': sorted(column['name'] for column in inspect(db.engine).get_columns('lineage_nodes')),
        'source_text': row.source_text,
        'description_hash': row.description_hash,
        'lineage_node_id': row.lineage_node_id,
        'first_node': first_node,
        'root_node_id': session.query(db.LineageNodeRow).one().root_node_id,
        'node_count': session.query(db.LineageNodeRow).count(),
        'edge_count': session.query(db.LineageEdgeRow).count(),
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
    required = {
        "source_text",
        "display_label",
        "batch_line_number",
        "batch_run_id",
        "description_hash",
        "history_visibility",
        "lineage_node_id",
    }
    assert required.issubset(payload["columns"])
    assert payload["source_text"] == "#1 作者が意図した本文"
    assert payload["description_hash"] == description_hash("#1 作者が意図した本文")
    assert payload["lineage_node_id"] == payload["first_node"]
    assert "root_node_id" in payload["lineage_columns"]
    assert payload["root_node_id"] == payload["first_node"]
    assert payload["node_count"] == 1
    assert payload["edge_count"] == 0
