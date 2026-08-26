"""Direct ownership coverage for user-account response projection."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
import json
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _projector_or_skip():
    projector = getattr(accounts, "UserAccountProjector", None)
    if projector is None:
        pytest.skip("account projector is intentionally absent during fail-first")
    return projector


def test_accounts_owns_projection_and_db_delegates() -> None:
    projector = getattr(accounts, "UserAccountProjector", None)
    assert projector is not None
    assert is_dataclass(projector) and projector.__dataclass_params__.frozen
    instance = projector(*([None] * 8))
    with pytest.raises(FrozenInstanceError):
        instance.object_session_fn = None
    for name in ("_loads_or_none", "_user_to_dict"):
        function = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(function.body[-1], ast.Return)


def test_projection_factory_receives_runtime_dependencies(monkeypatch) -> None:
    _projector_or_skip()
    import sqlalchemy.orm
    from inku_server import model_settings

    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    markers = [object() for _ in range(4)]
    monkeypatch.setattr(db._accounts, "UserAccountProjector", Recording)
    monkeypatch.setattr(sqlalchemy.orm, "object_session", markers[0])
    monkeypatch.setattr(db, "_permission_groups_of", markers[1])
    monkeypatch.setattr(db, "normalize_history_strip_fields", markers[2])
    monkeypatch.setattr(model_settings, "normalize_user_model_settings", markers[3])

    db._user_account_projector()

    assert received == [(
        markers[0],
        markers[1],
        db.PERMISSION_GROUP_LABELS,
        db._UI_MODES,
        db._UI_CUSTOM_KEYS,
        db._SETTINGS_TABS,
        markers[2],
        markers[3],
    )]


def test_projector_preserves_response_defaults_filtering_and_labels() -> None:
    projector_type = _projector_or_skip()
    session = object()
    history_values = []
    model_values = []
    projector = projector_type(
        lambda row: session,
        lambda active_session, user_id: ["users", "admins"],
        {"users": "User", "admins": "Admin"},
        {"simple", "custom"},
        {"show_stage1", "show_language"},
        {"db", "account"},
        lambda value: history_values.append(value) or ["description"],
        lambda value: model_values.append(value) or {"normalized": True},
    )
    row = SimpleNamespace(
        id="u1",
        username="name",
        email="mail@example.test",
        group_id="g1",
        ui_theme="unknown",
        ui_mode="unknown",
        ui_custom=json.dumps({"show_stage1": True, "show_language": 1, "unknown": False}),
        history_strip_fields=json.dumps(["description"]),
        tooltips_enabled=None,
        download_folder_enabled=True,
        download_folder_name="Art",
        settings_tab="unknown",
        model_settings=json.dumps({"stage1": {"model": "m"}}),
        image_generation_count=None,
        at=123,
    )

    result = projector.project(row, "Group")

    assert result == {
        "id": "u1",
        "username": "name",
        "email": "mail@example.test",
        "permission_groups": ["users", "admins"],
        "permission_group_labels": ["User", "Admin"],
        "group_id": "g1",
        "group_name": "Group",
        "ui_theme": "light",
        "ui_mode": "simple",
        "ui_custom": {"show_stage1": True},
        "history_strip_fields": ["description"],
        "tooltips_enabled": True,
        "download_folder_enabled": True,
        "download_folder_name": "Art",
        "settings_tab": "db",
        "model_settings": {"normalized": True},
        "image_generation_count": 0,
        "at": 123,
    }
    assert history_values == [["description"]]
    assert model_values == [{"stage1": {"model": "m"}}]


def test_projection_preserves_json_fallback_and_attached_row_failure() -> None:
    projector_type = _projector_or_skip()
    assert accounts.loads_or_none(None) is None
    assert accounts.loads_or_none("not-json") is None
    assert accounts.loads_or_none("[]") == []
    assert db._loads_or_none("[]") == []
    corrupt_row = SimpleNamespace(
        id="u1",
        username="name",
        email="mail@example.test",
        group_id=None,
        ui_theme="light",
        ui_mode="simple",
        ui_custom="not-json",
        history_strip_fields="not-json",
        tooltips_enabled=False,
        download_folder_enabled=False,
        download_folder_name=None,
        settings_tab="db",
        model_settings="not-json",
        image_generation_count=2,
        at=123,
    )
    attached = projector_type(
        lambda value: object(),
        lambda *_args: [],
        {},
        {"simple"},
        set(),
        {"db"},
        lambda value: [] if value is None else pytest.fail("expected unreadable history"),
        lambda value: {"fallback": True}
        if value == {}
        else pytest.fail("expected empty model settings"),
    )
    result = attached.project(corrupt_row)
    assert result["ui_custom"] == {}
    assert result["history_strip_fields"] == []
    assert result["model_settings"] == {"fallback": True}

    row = SimpleNamespace(id="u1")
    projector = projector_type(
        lambda value: None,
        lambda *_args: pytest.fail("membership lookup must not run for a detached row"),
        {},
        set(),
        set(),
        set(),
        lambda value: value,
        lambda value: value,
    )
    with pytest.raises(
        RuntimeError,
        match="^_user_to_dict needs an attached row to read permission groups$",
    ):
        projector.project(row)
