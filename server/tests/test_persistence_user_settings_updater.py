"""Direct authority and transaction coverage for persisted user UI settings."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
import json
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import settings


def _updater_or_skip():
    updater = getattr(settings, "UserSettingsUpdater", None)
    if updater is None:
        pytest.skip("user settings updater is intentionally absent during fail-first")
    return updater


def test_settings_owns_user_updater_and_db_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    updater = getattr(settings, "UserSettingsUpdater", None)
    assert updater is not None, "persistence.settings must own user UI/settings updates"
    assert is_dataclass(updater) and updater.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        updater(None, None).session_factory = None

    for name in (
        "normalize_history_strip_fields",
        "_user_settings_updater",
        "update_user_theme",
        "update_user_settings",
    ):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    assert db._SETTINGS_TABS is settings.SETTINGS_TABS
    assert db._UI_MODES is settings.UI_MODES
    assert db._UI_CUSTOM_KEYS is settings.UI_CUSTOM_KEYS
    assert db._HISTORY_STRIP_FIELDS is settings.HISTORY_STRIP_FIELDS
    assert db._HISTORY_STRIP_FIELD_LIMIT == settings.HISTORY_STRIP_FIELD_LIMIT

    calls: list[tuple[str, tuple[object, ...], tuple[object, ...], dict[str, object]]] = []

    class RecordingUpdater:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def update_user_theme(self, *args: object, **kwargs: object) -> str:
            calls.append(("theme", self.dependencies, args, kwargs))
            return "theme-sentinel"

        def update_user_settings(self, *args: object, **kwargs: object) -> str:
            calls.append(("settings", self.dependencies, args, kwargs))
            return "settings-sentinel"

    dependencies = (object(), object())
    monkeypatch.setattr(db._settings, "UserSettingsUpdater", RecordingUpdater)
    monkeypatch.setattr(db, "SessionLocal", dependencies[0])
    monkeypatch.setattr(db, "_user_to_dict", dependencies[1])

    assert db.update_user_theme("u", "light") == "theme-sentinel"
    assert db.update_user_settings("u", ui_mode="full") == "settings-sentinel"
    assert calls[0] == ("theme", dependencies, ("u", "light"), {})
    assert calls[1][0:3] == ("settings", dependencies, ("u",))
    assert calls[1][3]["ui_mode"] == "full"
    assert calls[1][3]["history_strip_fields"] is None


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
        if getattr(row_type, "__tablename__", "") == "user_accounts":
            return self.row
        return SimpleNamespace(name="Group")

    def commit(self) -> None:
        self.events.append("commit")

    def refresh(self, row: object) -> None:
        self.events.append(("refresh", row))


def _build(session: _Session):
    updater_type = _updater_or_skip()

    def project(row: object, group_name: str | None = None) -> dict:
        session.events.append(("project", row, group_name))
        return {"id": row.id, "group_name": group_name}

    return updater_type(lambda: session, project)


def test_user_settings_preserves_normalizer_theme_and_missing_results() -> None:
    _updater_or_skip()
    assert settings.normalize_history_strip_fields(None) == ["generation", "model"]
    assert settings.normalize_history_strip_fields([]) == []
    assert settings.normalize_history_strip_fields(["bytes", "generation", "bytes", "nope"]) == [
        "generation",
        "bytes",
    ]

    missing = _Session(None)
    assert _build(missing).update_user_theme("missing", "dark") is None
    assert "commit" not in missing.events

    row = SimpleNamespace(id="u", group_id="g", ui_theme="dark")
    invalid = _Session(row)
    with pytest.raises(ValueError, match="invalid ui theme"):
        _build(invalid).update_user_theme("u", "sepia")
    assert not invalid.events

    session = _Session(row)
    assert _build(session).update_user_theme("u", "light") == {"id": "u", "group_name": "Group"}
    assert row.ui_theme == "light"
    assert session.events == [
        ("get", "user_accounts", "u"),
        "commit",
        ("refresh", row),
        ("get", "user_groups", "g"),
        ("project", row, "Group"),
    ]


def test_user_settings_preserves_validation_before_write() -> None:
    row = SimpleNamespace(id="u", group_id=None)
    cases = (
        ({"ui_theme": "sepia"}, "invalid ui theme"),
        ({"ui_mode": "expert"}, "invalid ui mode"),
        ({"ui_custom": {"unknown": True}}, "invalid custom ui settings"),
        ({"ui_custom": {"history": "yes"}}, "invalid custom ui settings"),
        ({"tooltips_enabled": 1}, "invalid tooltips enabled setting"),
        ({"download_folder_enabled": 1}, "invalid download folder setting"),
        ({"download_folder_name": "x" * 241}, "download folder name is too long"),
        ({"settings_tab": "unknown"}, "invalid settings tab"),
        ({"history_strip_fields": "bytes"}, "invalid history strip fields"),
        ({"history_strip_fields": ["bytes", "bytes"]}, "invalid history strip fields"),
        ({"history_strip_fields": ["generation", "model", "bytes"]}, "invalid history strip fields"),
    )
    for kwargs, message in cases:
        session = _Session(row)
        with pytest.raises(ValueError, match=message):
            _build(session).update_user_settings("u", **kwargs)
        assert not session.events


def test_user_settings_preserves_json_merge_transaction_and_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _updater_or_skip()
    row = SimpleNamespace(
        id="u",
        group_id="g",
        ui_theme="dark",
        ui_mode="simple",
        ui_custom="{}",
        history_strip_fields='["generation", "model"]',
        tooltips_enabled=True,
        download_folder_enabled=False,
        download_folder_name="old",
        settings_tab="db",
        model_settings="broken-json",
    )
    monkeypatch.setattr(
        settings,
        "update_user_model_settings",
        lambda current, patch: {"current": current, "patch": patch},
    )
    session = _Session(row)
    result = _build(session).update_user_settings(
        "u",
        ui_theme="light",
        ui_mode="custom",
        ui_custom={"history": False},
        tooltips_enabled=False,
        download_folder_enabled=True,
        download_folder_name=" ",
        settings_tab="models",
        model_settings={"stage1_model": "example:model"},
        history_strip_fields=["bytes", "generation"],
    )
    assert result == {"id": "u", "group_name": "Group"}
    assert (row.ui_theme, row.ui_mode, row.tooltips_enabled, row.download_folder_enabled) == (
        "light", "custom", False, True
    )
    assert row.download_folder_name is None
    assert row.settings_tab == "models"
    assert json.loads(row.ui_custom) == {"history": False}
    assert json.loads(row.history_strip_fields) == ["generation", "bytes"]
    assert json.loads(row.model_settings) == {
        "current": {}, "patch": {"stage1_model": "example:model"}
    }
    assert session.events == [
        ("get", "user_accounts", "u"),
        "commit",
        ("refresh", row),
        ("get", "user_groups", "g"),
        ("project", row, "Group"),
    ]

    class BrokenSession(_Session):
        def get(self, _row_type: object, _key: object) -> object:
            raise RuntimeError("get failed")

    with pytest.raises(RuntimeError, match="get failed"):
        _build(BrokenSession(None)).update_user_settings("u")
