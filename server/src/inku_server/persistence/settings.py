"""Persistence-owned storage for generic application settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..model_settings import update_user_model_settings
from .schema import AppSettingRow, UserAccountRow, UserGroupRow


SETTINGS_TABS = {
    "models",
    "db",
    "plugins",
    "users",
    "export",
    "misc",
    "server_misc",
    "logs",
    "limits",
}
UI_MODES = {"simple", "full", "custom"}
UI_CUSTOM_KEYS = {
    "input_modes",
    "drawing_settings",
    "ddl_tools",
    "detail_status",
    "work_tools",
    "history",
    "auxiliary",
}
# What the history strip prints under each thumbnail. The order is the order the
# strip reads them in, so it is a list here rather than a set; at most
# HISTORY_STRIP_FIELD_LIMIT of them, and an empty list is a choice, not an
# absence. The web half of this pair is web/src/lib/historyStripFields.ts.
HISTORY_STRIP_FIELDS = ("generation", "model", "engine_version", "bytes")
HISTORY_STRIP_FIELD_LIMIT = 2
HISTORY_STRIP_FIELDS_DEFAULT = ["generation", "model"]


def normalize_history_strip_fields(value) -> list[str]:
    """Which facts the strip prints, as a list this API can hand to the page.

    Anything that is not a list is an absence and takes the default. A list is
    taken at its word -- unknown names drop, repeats collapse, the declared
    order is restored, and at most two survive -- so an empty list comes back
    empty, which is how "print nothing under the picture" is stored at all.
    """
    if not isinstance(value, list):
        return list(HISTORY_STRIP_FIELDS_DEFAULT)
    chosen = {item for item in value if item in HISTORY_STRIP_FIELDS}
    ordered = [field for field in HISTORY_STRIP_FIELDS if field in chosen]
    return ordered[:HISTORY_STRIP_FIELD_LIMIT]


@dataclass(frozen=True)
class AppSettingsStore:
    """Read and write JSON object settings through explicit runtime dependencies."""

    session_factory: Callable[[], Session]
    now_ms: Callable[[], int]

    def read(self, key: str) -> dict | None:
        with self.session_factory() as session:
            row = session.get(AppSettingRow, key)
            if not row:
                return None
            try:
                value = json.loads(row.value or "{}")
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None

    def write(self, key: str, value: dict) -> dict:
        with self.session_factory() as session:
            row = session.get(AppSettingRow, key)
            if row:
                row.value = json.dumps(value, ensure_ascii=False)
                row.at = self.now_ms()
            else:
                row = AppSettingRow(
                    key=key,
                    value=json.dumps(value, ensure_ascii=False),
                    at=self.now_ms(),
                )
                session.add(row)
            session.commit()
            return value


@dataclass(frozen=True)
class UserSettingsUpdater:
    session_factory: Callable[[], Any]
    user_to_dict_fn: Callable[[UserAccountRow, str | None], dict]

    def update_user_theme(self, user_id: str, ui_theme: str) -> dict | None:
        if ui_theme not in {"light", "dark"}:
            raise ValueError("invalid ui theme")
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return None
            row.ui_theme = ui_theme
            session.commit()
            session.refresh(row)
            group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
            return self.user_to_dict_fn(row, group_name)

    def update_user_settings(
        self,
        user_id: str,
        ui_theme: str | None = None,
        ui_mode: str | None = None,
        ui_custom: dict | None = None,
        tooltips_enabled: bool | None = None,
        download_folder_enabled: bool | None = None,
        download_folder_name: str | None = None,
        settings_tab: str | None = None,
        model_settings: dict | None = None,
        history_strip_fields: list | None = None,
    ) -> dict | None:
        if ui_theme is not None and ui_theme not in {"light", "dark"}:
            raise ValueError("invalid ui theme")
        if ui_mode is not None and ui_mode not in UI_MODES:
            raise ValueError("invalid ui mode")
        if ui_custom is not None and (
            not isinstance(ui_custom, dict)
            or any(
                key not in UI_CUSTOM_KEYS or not isinstance(value, bool)
                for key, value in ui_custom.items()
            )
        ):
            raise ValueError("invalid custom ui settings")
        if tooltips_enabled is not None and not isinstance(tooltips_enabled, bool):
            raise ValueError("invalid tooltips enabled setting")
        if download_folder_enabled is not None and not isinstance(download_folder_enabled, bool):
            raise ValueError("invalid download folder setting")
        if download_folder_name is not None and len(download_folder_name) > 240:
            raise ValueError("download folder name is too long")
        if settings_tab is not None and settings_tab not in SETTINGS_TABS:
            raise ValueError("invalid settings tab")
        # Refused rather than quietly trimmed: a caller asking for a fifth field or
        # for three at once has misread the control, and silently storing two of the
        # three would put a choice on screen that nobody made.
        if history_strip_fields is not None and (
            not isinstance(history_strip_fields, list)
            or any(field not in HISTORY_STRIP_FIELDS for field in history_strip_fields)
            or len(set(history_strip_fields)) != len(history_strip_fields)
            or len(history_strip_fields) > HISTORY_STRIP_FIELD_LIMIT
        ):
            raise ValueError("invalid history strip fields")
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return None
            if ui_theme is not None:
                row.ui_theme = ui_theme
            if ui_mode is not None:
                row.ui_mode = ui_mode
            if ui_custom is not None:
                row.ui_custom = json.dumps(ui_custom, ensure_ascii=False, sort_keys=True)
            if history_strip_fields is not None:
                # Stored in the declared order, not the order they were ticked, so
                # the strip reads the same however the reader got there.
                row.history_strip_fields = json.dumps(
                    normalize_history_strip_fields(history_strip_fields), ensure_ascii=False
                )
            if tooltips_enabled is not None:
                row.tooltips_enabled = tooltips_enabled
            if download_folder_enabled is not None:
                row.download_folder_enabled = download_folder_enabled
            if download_folder_name is not None:
                # An empty name clears it: the user dropped the folder.
                row.download_folder_name = download_folder_name.strip() or None
            if settings_tab is not None:
                row.settings_tab = settings_tab
            if model_settings is not None:
                try:
                    current_model_settings = json.loads(row.model_settings or "{}")
                except json.JSONDecodeError:
                    current_model_settings = {}
                row.model_settings = json.dumps(
                    update_user_model_settings(current_model_settings, model_settings),
                    ensure_ascii=False,
                )
            session.commit()
            session.refresh(row)
            group_name = session.get(UserGroupRow, row.group_id).name if row.group_id else None
            return self.user_to_dict_fn(row, group_name)
