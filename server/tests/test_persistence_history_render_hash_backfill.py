"""Direct ownership coverage for the legacy render-hash backfill."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import history


SELECT_SQL = """
SELECT id, input, ddl, score, svg, catalog_id, render_build_number,
       render_engine_id, render_engine_version,
       render_color_catalog_id, render_color_catalog_name,
       render_color_catalog_sub, render_color_map, render_canvas_aspect,
       render_canvas_aspect_id, render_canvas_aspect_ratio, render_seed,
       composition_seed
FROM history
WHERE render_hash IS NULL OR render_hash = ''
"""
UPDATE_SQL = "UPDATE history SET render_hash = :render_hash WHERE id = :id"


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


class _Result:
    def __init__(self, rows):
        self.rows = rows
        self.mappings_called = False

    def mappings(self):
        self.mappings_called = True
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.result = _Result(rows)
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((statement, params))
        if len(self.calls) == 1:
            return self.result
        return None


class _Text:
    def __init__(self):
        self.sources = []

    def __call__(self, source):
        self.sources.append(source)
        return source


class _Logger:
    def __init__(self):
        self.errors = []

    def error(self, *args):
        self.errors.append(args)


def _engine(dialect_name: str):
    return SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))


def _row(**overrides):
    row = {
        "id": "history-id",
        "input": "input",
        "ddl": "ddl",
        "score": "",
        "svg": "<svg/>",
        "catalog_id": "catalog",
        "render_build_number": "123",
        "render_engine_id": "default",
        "render_engine_version": "41",
        "render_color_catalog_id": "color-id",
        "render_color_catalog_name": "Color Name",
        "render_color_catalog_sub": "Color Sub",
        "render_color_map": "{invalid",
        "render_canvas_aspect": "square",
        "render_canvas_aspect_id": "square",
        "render_canvas_aspect_ratio": 1.0,
        "render_seed": "42",
        "composition_seed": "84",
    }
    row.update(overrides)
    return row


def _backfill_or_fail():
    backfill_type = getattr(history, "HistoryRenderHashBackfill", None)
    assert backfill_type is not None
    return backfill_type


def test_history_owns_frozen_backfill_and_non_sqlite_is_a_noop() -> None:
    backfill_type = _backfill_or_fail()
    assert is_dataclass(backfill_type) and backfill_type.__dataclass_params__.frozen
    text_fn = _Text()
    logger = _Logger()
    conn = _Connection([])
    backfill = backfill_type(
        _engine("postgresql"),
        text_fn,
        logger,
        lambda _item: pytest.fail("non-SQLite backfill must not hash"),
    )
    with pytest.raises(FrozenInstanceError):
        backfill.engine = None
    assert backfill.backfill(conn) is None
    assert text_fn.sources == []
    assert conn.calls == []


def test_backfill_preserves_projection_invalid_color_map_and_one_update() -> None:
    text_fn = _Text()
    logger = _Logger()
    conn = _Connection([_row()])
    projected = []

    def render_hash(item):
        projected.append(item)
        return "rh3:new"

    backfill = _backfill_or_fail()(_engine("sqlite"), text_fn, logger, render_hash)
    assert backfill.backfill(conn) is None

    assert conn.result.mappings_called
    assert [_normalized_sql(source) for source in text_fn.sources] == [
        _normalized_sql(SELECT_SQL),
        UPDATE_SQL,
    ]
    assert projected == [{
        "input": "input",
        "ddl": "ddl",
        "score": {},
        "svg": "<svg/>",
        "catalog_id": "catalog",
        "render_build_number": "123",
        "render_engine_id": "default",
        "render_engine_version": "41",
        "render_canvas_aspect": "square",
        "render_canvas_aspect_id": "square",
        "render_canvas_aspect_ratio": 1.0,
        "render_color_catalog_id": "color-id",
        "render_color_catalog_name": "Color Name",
        "render_color_catalog_sub": "Color Sub",
        "render_seed": "42",
        "composition_seed": "84",
        "render_color_map": None,
    }]
    assert conn.calls[1] == (UPDATE_SQL, {"id": "history-id", "render_hash": "rh3:new"})
    assert logger.errors == []


def test_backfill_skips_corrupt_and_non_object_scores_with_exact_logs() -> None:
    text_fn = _Text()
    logger = _Logger()
    conn = _Connection([
        _row(id="corrupt", score="{"),
        _row(id="non-object", score="[]"),
    ])
    backfill = _backfill_or_fail()(
        _engine("sqlite"),
        text_fn,
        logger,
        lambda _item: pytest.fail("skipped rows must not hash"),
    )

    assert backfill.backfill(conn) is None
    assert len(conn.calls) == 1
    assert logger.errors == [
        ("skipping render-hash backfill for corrupt score JSON: history_id=%s", "corrupt"),
        ("skipping render-hash backfill for non-object score JSON: history_id=%s", "non-object"),
    ]


def test_db_backfill_facade_constructs_and_delegates_at_call_time(monkeypatch) -> None:
    created = []
    calls = []
    engine = object()
    text_fn = object()
    logger = object()
    render_hash = object()
    conn = object()
    result = object()

    class Recording:
        def __init__(self, *args):
            created.append(args)

        def backfill(self, received):
            calls.append(received)
            return result

    monkeypatch.setattr(history, "HistoryRenderHashBackfill", Recording, raising=False)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "text", text_fn)
    monkeypatch.setattr(db, "_logger", logger)
    monkeypatch.setattr(db, "render_hash_for_item", render_hash)

    assert db._backfill_render_hashes(conn) is result
    assert created == [(engine, text_fn, logger, render_hash)]
    assert calls == [conn]
