"""Direct ownership checks for the persistence history projection."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import history


class RecordingLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def error(self, message: str, *args: object) -> None:
        self.calls.append((message, args))


def _row(**overrides: object) -> SimpleNamespace:
    values = {
        "id": "history-1", "user_id": "user-1", "at": "2026-08-25T00:00:00Z",
        "input": "input", "ddl": "ddl", "expanded_ddl": "expanded", "score": '{"ok": true}',
        "svg": "<svg/>", "output_path": "/tmp/output.svg", "elapsed_ms": 12,
        "stage1_model": "stage-1", "stage2_model": "stage-2", "tokens_in": 3,
        "tokens_out": 5, "catalog_id": "catalog", "catalog_mode": "fixed",
        "render_hash": "rh3:abcD", "trashed": 0, "starred": 1, "for_revision": 0,
        "for_share": 1, "share_group_id": "group-1", "note": "note", "source_text": None,
        "display_label": "label", "batch_line_number": 4, "batch_run_id": "batch-1",
        "description_hash": "dh1:abc", "history_visibility": None, "lineage_node_id": "node-1",
        "stage1_prompt_digest": None, "stage1_prompt_base_digest": None,
        "stage2_prompt_digest": None, "ddl_version": None, "ddl_engine_version": None,
        "render_build_number": None, "render_color_profile": None, "render_engine_id": None,
        "render_engine_version": None, "render_color_catalog_id": None,
        "render_color_catalog_name": None, "render_color_catalog_sub": None,
        "render_color_catalog": None, "render_color_map": None, "render_canvas_aspect": None,
        "render_canvas_aspect_id": None, "render_canvas_aspect_ratio": None,
        "instruction_lang_requested": None, "instruction_lang_resolved": None, "ui_lang": None,
        "render_seed": None, "render_wild": None, "composition_seed": None, "tenkei": None,
        "focus": None, "variation_amplitude": None, "variation_seed": None,
        "interpret_fallback": None, "compose_fallback": None, "interpretation_seed": None,
        "seed_text": None, "sketch_text": None, "sketch_grain": None, "sketch_state": None,
        "render_limits": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_persistence_history_owns_projection_and_db_keeps_thin_facades() -> None:
    history_source = Path(history.__file__).read_text()
    imports = [
        node.module or ""
        for node in ast.walk(ast.parse(history_source))
        if isinstance(node, ast.ImportFrom)
    ]
    assert all("db" not in module for module in imports)
    assert "create_sqlite_engine" not in history_source
    assert "session" not in history_source.lower()
    assert inspect.signature(db.render_hash_short) == inspect.Signature(
        [inspect.Parameter("render_hash", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation="str | None")],
        return_annotation="str | None",
    )
    assert inspect.signature(db._row_to_dict) == inspect.Signature(
        [inspect.Parameter("row", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation="HistoryRow")],
        return_annotation="dict",
    )
    assert "return _history.render_hash_short(render_hash)" in inspect.getsource(db.render_hash_short)
    facade_source = inspect.getsource(db._row_to_dict)
    assert "return _history.row_to_dict(" in facade_source
    assert "json.loads" not in facade_source


def test_db_facade_resolves_every_projection_dependency_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = RecordingLogger()
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(db, "_logger", logger)
    monkeypatch.setattr(db, "render_hash_short", lambda value: f"short:{value}")
    monkeypatch.setattr(
        db,
        "normalize_canvas_aspect_id",
        lambda value: calls.append(("normalize", value)) or "normalized",
    )
    monkeypatch.setattr(
        db,
        "canvas_aspect_ratio_for_aspect",
        lambda value: calls.append(("ratio", value)) or 1.25,
    )

    item = db._row_to_dict(
        _row(score=object(), render_canvas_aspect="portrait", render_canvas_aspect_ratio=None)
    )

    assert item["render_hash_short"] == "short:rh3:abcD"
    assert item["render_canvas_aspect_id"] == "normalized"
    assert item["render_canvas_aspect_ratio"] == 1.25
    assert item["data_warnings"] == ["score_json_invalid"]
    assert logger.calls == [("history score JSON is corrupt: history_id=%s", ("history-1",))]
    assert calls == [("normalize", "portrait"), ("ratio", "normalized")]


def test_history_projection_preserves_base_optional_and_legacy_branches() -> None:
    logger = RecordingLogger()
    item = history.row_to_dict(
        _row(
            score="[]", render_color_profile="{", render_color_map="{",
            render_color_catalog='{"id": "legacy", "name": "Legacy", "sub": "sub"}',
            render_canvas_aspect="landscape", render_seed="not-an-int", composition_seed="42",
            render_wild="not-1", compose_fallback="none", render_limits="[]",
        ),
        logger=logger,
        render_hash_short_fn=history.render_hash_short,
        normalize_canvas_aspect_id_fn=lambda value: f"normalized:{value}",
        canvas_aspect_ratio_for_aspect_fn=lambda value: 1.5,
    )

    assert history.render_hash_short("rh3:abcD") == "ABCD"
    assert history.render_hash_short("") is None
    assert item["score"] == {}
    assert item["data_warnings"] == ["score_json_not_object"]
    assert logger.calls == [("history score JSON is not an object: history_id=%s", ("history-1",))]
    assert item["source_text"] == "input"
    assert item["history_visibility"] == "normal"
    assert item["trashed"] is False and item["starred"] is True
    assert item["for_share"] is True and item["share_group_id"] == "group-1"
    assert item["render_color_profile"] is None and item["render_color_map"] is None
    assert item["render_color_catalog_id"] == "legacy"
    assert item["render_color_catalog_name"] == "Legacy"
    assert item["render_color_catalog_sub"] == "sub"
    assert item["render_canvas_aspect"] == "landscape"
    assert item["render_canvas_aspect_id"] == "normalized:landscape"
    assert item["render_canvas_aspect_ratio"] == 1.5
    assert item["render_seed"] == "not-an-int" and item["composition_seed"] == 42
    assert item["render_wild"] is False and item["compose_fallback"] == "none"
    assert "sketch_state" not in item and "render_limits" not in item


def test_history_projection_preserves_snapshot_precedence_and_render_limit_rules() -> None:
    logger = RecordingLogger()
    item = history.row_to_dict(
        _row(
            render_color_catalog_id="current", render_color_catalog_name="Current",
            render_color_catalog='{"id": "legacy", "name": "Legacy", "sub": "legacy-sub"}',
            render_canvas_aspect_id="square", render_canvas_aspect_ratio=2.0,
            render_seed="7", composition_seed="raw", render_wild="1", sketch_state="off",
            render_limits='{"max": 2}',
        ),
        logger=logger,
        render_hash_short_fn=history.render_hash_short,
        normalize_canvas_aspect_id_fn=lambda value: f"normalized:{value}",
        canvas_aspect_ratio_for_aspect_fn=lambda value: pytest.fail("ratio fallback used"),
    )

    assert logger.calls == []
    assert item["render_color_catalog_id"] == "current"
    assert item["render_color_catalog_name"] == "Current"
    assert item["render_color_catalog_sub"] == "legacy-sub"
    assert item["render_canvas_aspect"] == "normalized:square"
    assert item["render_canvas_aspect_id"] == "normalized:square"
    assert item["render_canvas_aspect_ratio"] == 2.0
    assert item["render_seed"] == 7 and item["composition_seed"] == "raw"
    assert item["render_wild"] is True and item["sketch_state"] == "off"
    assert item["render_limits"] == {"max": 2}
