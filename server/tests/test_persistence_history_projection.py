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
    values: dict[str, object] = {
        "id": "history-1",
        "user_id": "user-1",
        "at": "2026-08-25T00:00:00Z",
        "input": "input",
        "ddl": "ddl",
        "expanded_ddl": "expanded",
        "score": '{"ok": true}',
        "svg": "<svg/>",
        "output_path": "/tmp/output.svg",
        "elapsed_ms": 12,
        "stage1_model": "stage-1",
        "stage2_model": "stage-2",
        "tokens_in": 3,
        "tokens_out": 5,
        "catalog_id": "catalog",
        "catalog_mode": "fixed",
        "render_hash": "rh3:abcD",
        "trashed": 0,
        "starred": 1,
        "for_revision": 0,
        "for_share": 1,
        "share_group_id": "group-1",
        "note": "note",
        "source_text": None,
        "display_label": "label",
        "batch_line_number": 4,
        "batch_run_id": "batch-1",
        "description_hash": "dh1:abc",
        "history_visibility": None,
        "lineage_node_id": "node-1",
        "stage1_prompt_digest": None,
        "stage1_prompt_base_digest": None,
        "stage2_prompt_digest": None,
        "ddl_version": None,
        "ddl_engine_version": None,
        "render_build_number": None,
        "render_color_profile": None,
        "render_engine_id": None,
        "render_engine_version": None,
        "render_color_catalog_id": None,
        "render_color_catalog_name": None,
        "render_color_catalog_sub": None,
        "render_color_catalog": None,
        "render_color_map": None,
        "render_canvas_aspect": None,
        "render_canvas_aspect_id": None,
        "render_canvas_aspect_ratio": None,
        "instruction_lang_requested": None,
        "instruction_lang_resolved": None,
        "ui_lang": None,
        "render_seed": None,
        "render_wild": None,
        "composition_seed": None,
        "tenkei": None,
        "focus": None,
        "variation_amplitude": None,
        "variation_seed": None,
        "interpret_fallback": None,
        "compose_fallback": None,
        "interpretation_seed": None,
        "seed_text": None,
        "sketch_text": None,
        "sketch_grain": None,
        "sketch_state": None,
        "render_limits": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _project(row: SimpleNamespace, logger: RecordingLogger | None = None) -> tuple[dict, RecordingLogger]:
    active_logger = logger or RecordingLogger()
    return (
        history.row_to_dict(
            row,
            logger=active_logger,
            render_hash_short_fn=history.render_hash_short,
            normalize_canvas_aspect_id_fn=lambda value: f"normalized:{value}",
            canvas_aspect_ratio_for_aspect_fn=lambda value: 1.5,
        ),
        active_logger,
    )


def test_persistence_history_owns_projection_and_db_keeps_thin_facades() -> None:
    source = Path(history.__file__).read_text()
    tree = ast.parse(source)
    actual_imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            actual_imports.append(
                ("import", 0, "", tuple((name.name, name.asname) for name in node.names))
            )
        elif isinstance(node, ast.ImportFrom):
            actual_imports.append(
                (
                    "from",
                    node.level,
                    node.module or "",
                    tuple((name.name, name.asname) for name in node.names),
                )
            )

    assert actual_imports == [
        ("from", 0, "__future__", (("annotations", None),)),
        ("import", 0, "", (("json", None),)),
        ("import", 0, "", (("logging", None),)),
        ("import", 0, "", (("uuid", None),)),
        ("from", 0, "collections.abc", (("Callable", None),)),
        ("from", 0, "dataclasses", (("dataclass", None),)),
        ("from", 0, "hashlib", (("sha256", None),)),
        ("from", 0, "sqlalchemy.exc", (("IntegrityError", None),)),
        (
            "from",
            1,
            "schema",
            (
                ("CoerceTraceCatalogRow", None),
                ("HistoryRow", None),
                ("LineageEdgeRow", None),
                ("LineageNodeRow", None),
            ),
        ),
    ]
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


def test_history_projection_full_valid_row_is_exact_and_ordered() -> None:
    item, logger = _project(
        _row(
            source_text="source text",
            history_visibility="restricted",
            stage1_prompt_digest="stage1",
            stage1_prompt_base_digest="stage1-base",
            stage2_prompt_digest="stage2",
            ddl_version=3,
            ddl_engine_version=20,
            render_build_number=985,
            render_color_profile='{"profile": "warm"}',
            render_engine_id="default",
            render_engine_version="41",
            render_color_catalog_id="current-id",
            render_color_catalog_name="Current",
            render_color_catalog_sub="current-sub",
            render_color_catalog='{"id": "legacy-id", "name": "Legacy", "sub": "legacy-sub"}',
            render_color_map='{"black": "#111"}',
            render_canvas_aspect="source-aspect",
            render_canvas_aspect_id="portrait",
            render_canvas_aspect_ratio=1.25,
            instruction_lang_requested="ja",
            instruction_lang_resolved="en",
            ui_lang="ja",
            render_seed="19",
            render_wild="1",
            composition_seed="23",
            tenkei="tenkei",
            focus="focus",
            variation_amplitude="high",
            variation_seed="variation-seed",
            interpret_fallback="fallback",
            compose_fallback="none",
            interpretation_seed="interpretation-seed",
            seed_text="seed text",
            sketch_text="sketch text",
            sketch_grain="fine",
            sketch_state="off",
            render_limits='{"objects": 8}',
        )
    )
    expected = {
        "id": "history-1",
        "user_id": "user-1",
        "at": "2026-08-25T00:00:00Z",
        "input": "input",
        "ddl": "ddl",
        "expanded_ddl": "expanded",
        "score": {"ok": True},
        "svg": "<svg/>",
        "output_path": "/tmp/output.svg",
        "elapsed_ms": 12,
        "stage1_model": "stage-1",
        "stage2_model": "stage-2",
        "tokens_in": 3,
        "tokens_out": 5,
        "catalog_id": "catalog",
        "catalog_mode": "fixed",
        "render_hash": "rh3:abcD",
        "render_hash_short": "ABCD",
        "trashed": False,
        "starred": True,
        "for_revision": False,
        "for_share": True,
        "share_group_id": "group-1",
        "note": "note",
        "source_text": "source text",
        "display_label": "label",
        "batch_line_number": 4,
        "batch_run_id": "batch-1",
        "description_hash": "dh1:abc",
        "history_visibility": "restricted",
        "lineage_node_id": "node-1",
        "stage1_prompt_digest": "stage1",
        "stage1_prompt_base_digest": "stage1-base",
        "stage2_prompt_digest": "stage2",
        "ddl_version": 3,
        "ddl_engine_version": 20,
        "render_build_number": 985,
        "render_color_profile": {"profile": "warm"},
        "render_engine_id": "default",
        "render_engine_version": "41",
        "render_color_catalog_id": "current-id",
        "render_color_catalog_name": "Current",
        "render_color_catalog_sub": "current-sub",
        "render_color_map": {"black": "#111"},
        "render_canvas_aspect": "source-aspect",
        "render_canvas_aspect_id": "normalized:portrait",
        "render_canvas_aspect_ratio": 1.25,
        "instruction_lang_requested": "ja",
        "instruction_lang_resolved": "en",
        "ui_lang": "ja",
        "render_seed": 19,
        "render_wild": True,
        "composition_seed": 23,
        "tenkei": "tenkei",
        "focus": "focus",
        "variation_amplitude": "high",
        "variation_seed": "variation-seed",
        "interpret_fallback": "fallback",
        "compose_fallback": "none",
        "interpretation_seed": "interpretation-seed",
        "seed_text": "seed text",
        "sketch_text": "sketch text",
        "sketch_grain": "fine",
        "sketch_state": "off",
        "render_limits": {"objects": 8},
    }

    assert logger.calls == []
    assert item == expected
    assert list(item) == list(expected)


def test_history_projection_absence_row_has_exact_base_key_set() -> None:
    item, logger = _project(_row())

    assert logger.calls == []
    assert list(item) == [
        "id",
        "user_id",
        "at",
        "input",
        "ddl",
        "expanded_ddl",
        "score",
        "svg",
        "output_path",
        "elapsed_ms",
        "stage1_model",
        "stage2_model",
        "tokens_in",
        "tokens_out",
        "catalog_id",
        "catalog_mode",
        "render_hash",
        "render_hash_short",
        "trashed",
        "starred",
        "for_revision",
        "for_share",
        "share_group_id",
        "note",
        "source_text",
        "display_label",
        "batch_line_number",
        "batch_run_id",
        "description_hash",
        "history_visibility",
        "lineage_node_id",
    ]
    assert item["source_text"] == "input"
    assert item["history_visibility"] == "normal"


@pytest.mark.parametrize(
    ("score", "warning", "message"),
    [
        ("{", "score_json_invalid", "history score JSON is corrupt: history_id=%s"),
        (object(), "score_json_invalid", "history score JSON is corrupt: history_id=%s"),
        ("[]", "score_json_not_object", "history score JSON is not an object: history_id=%s"),
    ],
)
def test_score_json_boundaries_preserve_warning_and_logger(
    score: object,
    warning: str,
    message: str,
) -> None:
    item, logger = _project(_row(score=score))

    assert item["score"] == {}
    assert item["data_warnings"] == [warning]
    assert logger.calls == [(message, ("history-1",))]


@pytest.mark.parametrize(
    ("field", "invalid_key", "non_object_value"),
    [
        ("render_color_profile", "render_color_profile", []),
        ("render_color_catalog", None, []),
        ("render_color_map", "render_color_map", []),
        ("render_limits", None, []),
    ],
)
def test_optional_json_families_keep_their_exception_and_object_boundaries(
    field: str,
    invalid_key: str | None,
    non_object_value: list[object],
) -> None:
    invalid_item, invalid_logger = _project(_row(**{field: "{"}))
    non_object_item, non_object_logger = _project(_row(**{field: "[]"}))

    assert invalid_logger.calls == []
    assert non_object_logger.calls == []
    if invalid_key is None:
        assert field not in invalid_item
        assert field not in non_object_item
    else:
        assert invalid_item[invalid_key] is None
        assert non_object_item[invalid_key] == non_object_value
    with pytest.raises(TypeError):
        _project(_row(**{field: object()}))


def test_legacy_catalog_fills_only_missing_current_snapshot_values() -> None:
    item, logger = _project(
        _row(
            render_color_catalog_name="Current",
            render_color_catalog='{"id": "legacy-id", "name": "Legacy", "sub": "legacy-sub"}',
        )
    )

    assert logger.calls == []
    assert item["render_color_catalog_id"] == "legacy-id"
    assert item["render_color_catalog_name"] == "Current"
    assert item["render_color_catalog_sub"] == "legacy-sub"


def test_history_projection_preserves_raw_seed_wild_and_falsy_hash_branches() -> None:
    item, logger = _project(
        _row(
            render_hash="",
            render_seed="not-an-integer",
            composition_seed="also-not-an-integer",
            render_wild="true",
        )
    )

    assert logger.calls == []
    assert item["render_hash_short"] is None
    assert item["render_seed"] == "not-an-integer"
    assert item["composition_seed"] == "also-not-an-integer"
    assert item["render_wild"] is False
    assert history.render_hash_short(None) is None
    assert history.render_hash_short("") is None
