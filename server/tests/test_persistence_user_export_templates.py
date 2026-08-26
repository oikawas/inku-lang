"""Direct authority and transaction coverage for persisted export templates."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
import json
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import settings


def _store_or_skip():
    store = getattr(settings, "UserExportTemplateStore", None)
    if store is None:
        pytest.skip("export template store is intentionally absent during fail-first")
    return store


def test_settings_owns_export_templates_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = getattr(settings, "UserExportTemplateStore", None)
    assert store is not None, "persistence.settings must own user export templates"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None).session_factory = None

    for name in (
        "_normalize_export_templates",
        "_user_export_template_store",
        "get_user_export_templates",
        "update_user_export_templates",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    assert db._EXPORT_TEMPLATE_LIMIT == settings.EXPORT_TEMPLATE_LIMIT
    assert db._EXPORT_TEMPLATE_DEFAULTS is settings.EXPORT_TEMPLATE_DEFAULTS

    calls: list[tuple[str, object, tuple[object, ...]]] = []

    class RecordingStore:
        def __init__(self, dependency: object) -> None:
            self.dependency = dependency

        def get(self, *args: object) -> str:
            calls.append(("get", self.dependency, args))
            return "get-sentinel"

        def update(self, *args: object) -> str:
            calls.append(("update", self.dependency, args))
            return "update-sentinel"

    dependency = object()
    monkeypatch.setattr(db._settings, "UserExportTemplateStore", RecordingStore)
    monkeypatch.setattr(db, "SessionLocal", dependency)
    assert db.get_user_export_templates("u") == "get-sentinel"
    assert db.update_user_export_templates("u", [{"id": "x"}]) == "update-sentinel"
    assert calls == [
        ("get", dependency, ("u",)),
        ("update", dependency, ("u", [{"id": "x"}])),
    ]


def test_export_templates_preserves_defaults_legacy_dedup_and_limits() -> None:
    _store_or_skip()
    assert settings.normalize_export_templates([]) == settings.EXPORT_TEMPLATE_DEFAULTS
    legacy = settings.normalize_export_templates(
        [
            {"id": "png-1024", "name": "old", "description": "", "y_px": 1024},
            {"id": "png-2048", "name": "old", "description": "", "y_px": 2048},
        ]
    )
    assert legacy == settings.EXPORT_TEMPLATE_DEFAULTS

    items = [
        {
            "id": " same ",
            "name": " N " * 50,
            "description": " D " * 100,
            "y_px": "3000",
        },
        {"id": "same", "name": "ignored", "description": "", "y_px": 4000},
    ] + [
        {"id": f"id-{index}", "name": str(index), "description": "", "y_px": 64}
        for index in range(30)
    ]
    clean = settings.normalize_export_templates(items)
    assert len(clean) == 20
    assert clean[0]["id"] == "same"
    assert len(clean[0]["name"]) == 80
    assert len(clean[0]["description"]) == 240
    assert clean[0]["y_px"] == 3000
    assert sum(item["id"] == "same" for item in clean) == 1


def test_export_templates_preserves_validation_and_ranges() -> None:
    _store_or_skip()
    cases = (
        ({}, "must be a list"),
        (["bad"], "must be an object"),
        ([{"id": "", "name": "n", "y_px": 100}], "id is required"),
        ([{"id": "id", "name": "", "y_px": 100}], "name is required"),
        ([{"id": "id", "name": "n", "description": 1, "y_px": 100}], "description must be a string"),
        ([{"id": "id", "name": "n", "y_px": "bad"}], "y_px must be an integer"),
        ([{"id": "id", "name": "n", "y_px": 63}], "y_px must be between"),
        ([{"id": "id", "name": "n", "y_px": 12001}], "y_px must be between"),
    )
    for value, message in cases:
        with pytest.raises(ValueError, match=message):
            settings.normalize_export_templates(value)


class _Session:
    def __init__(self, row: object | None) -> None:
        self.row = row
        self.events: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, row_type: object, key: object) -> object | None:
        self.events.append(("get", getattr(row_type, "__tablename__", "unknown"), key))
        return self.row

    def commit(self) -> None:
        self.events.append("commit")


def _build(session: _Session):
    return _store_or_skip()(lambda: session)


def test_export_templates_preserves_read_write_fallbacks_and_exceptions() -> None:
    _store_or_skip()
    defaults = settings.EXPORT_TEMPLATE_DEFAULTS
    for row in (
        None,
        SimpleNamespace(export_templates="broken"),
        SimpleNamespace(export_templates="{}"),
        SimpleNamespace(export_templates="[]"),
    ):
        session = _Session(row)
        result = _build(session).get("u")
        assert result == defaults
        assert result is not defaults

    missing = _Session(None)
    assert _build(missing).update("missing", []) is None
    assert "commit" not in missing.events

    row = SimpleNamespace(export_templates="[]")
    session = _Session(row)
    item = {"id": "custom", "name": "Poster", "description": "Tall", "y_px": 3000}
    assert _build(session).update("u", [item]) == [item]
    assert json.loads(row.export_templates) == [item]
    assert session.events == [("get", "user_accounts", "u"), "commit"]

    class BrokenSession(_Session):
        def get(self, _row_type: object, _key: object) -> object:
            raise RuntimeError("get failed")

    with pytest.raises(RuntimeError, match="get failed"):
        _build(BrokenSession(None)).get("u")
