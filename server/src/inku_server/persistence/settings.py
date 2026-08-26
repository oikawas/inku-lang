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
# How many past batch prompts a member keeps. Cut on the way in and on the way
# out, so lowering it later drops the tail of what is already stored. The web
# client holds the same number (BATCH_PROMPT_HISTORY_LIMIT in +page.svelte);
# raising one without the other changes nothing, because the shorter of the two
# is what reaches the picker.
BATCH_PROMPT_HISTORY_LIMIT = 50
BATCH_PROMPT_HISTORY_MAX_TEXT = 20_000
DEMO_DEFAULT_SETTINGS = {
    "save_db": False,
    "save_files": False,
    # v2.9.1: the provider is kept beside the model, as every stage does. The
    # picker used to hand over a provider that was thrown away here.
    "prompt_provider": "nvidia",
    "prompt_model": "google/gemma-4-31b-it",
    "seed_phrase": "日本の四季を感じさせる文章を40語以内で生成",
    "interval_seconds": 30,
    "timeout_seconds": 3600,
}


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


def normalize_batch_prompt_history(items: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise ValueError("batch prompt history must contain strings")
        prompt = item.strip().replace("\r\n", "\n").replace("\r", "\n")
        if not prompt or prompt in seen:
            continue
        if len(prompt) > BATCH_PROMPT_HISTORY_MAX_TEXT:
            raise ValueError("batch prompt history item is too long")
        normalized.append(prompt)
        seen.add(prompt)
        if len(normalized) >= BATCH_PROMPT_HISTORY_LIMIT:
            break
    return normalized


@dataclass(frozen=True)
class UserBatchPromptHistoryStore:
    """Read and write one user's normalized batch prompt history."""

    session_factory: Callable[[], Session]

    def get(self, user_id: str) -> list[str]:
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return []
            try:
                parsed = json.loads(row.batch_prompt_history or "[]")
            except json.JSONDecodeError:
                return []
            if not isinstance(parsed, list):
                return []
            try:
                return normalize_batch_prompt_history(parsed)
            except ValueError:
                return []

    def update(self, user_id: str, items: list[str]) -> list[str] | None:
        prompts = normalize_batch_prompt_history(items)
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return None
            row.batch_prompt_history = json.dumps(prompts, ensure_ascii=False)
            session.commit()
            return prompts


def normalize_demo_settings(settings: dict) -> dict:
    if not isinstance(settings, dict):
        raise ValueError("demo settings must be an object")
    clean = dict(DEMO_DEFAULT_SETTINGS)
    if "save_db" in settings:
        clean["save_db"] = bool(settings["save_db"])
    if "save_files" in settings:
        clean["save_files"] = bool(settings["save_files"])
    if "prompt_provider" in settings:
        provider = settings["prompt_provider"]
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("demo prompt provider is required")
        clean["prompt_provider"] = provider.strip()
    if "prompt_model" in settings:
        model = settings["prompt_model"]
        if not isinstance(model, str) or not model.strip():
            raise ValueError("demo prompt model is required")
        clean["prompt_model"] = model.strip()
    # Values stored before prompt_provider existed carry the provider inside
    # prompt_model. Read both shapes, write the pair.
    from ..model_settings import split_model_ref

    prompt_prefix, prompt_bare = split_model_ref(str(clean["prompt_model"]), None)
    if prompt_prefix:
        clean["prompt_provider"] = prompt_prefix
        clean["prompt_model"] = prompt_bare
    if "seed_phrase" in settings:
        phrase = settings["seed_phrase"]
        if not isinstance(phrase, str):
            raise ValueError("demo seed phrase must be a string")
        phrase = phrase.strip()
        if not phrase:
            raise ValueError("demo seed phrase is required")
        if len(phrase) > 1000:
            raise ValueError("demo seed phrase is too long")
        clean["seed_phrase"] = phrase
    if "interval_seconds" in settings:
        try:
            interval = int(settings["interval_seconds"])
        except (TypeError, ValueError) as exc:
            raise ValueError("demo interval must be an integer") from exc
        if interval < 1 or interval > 3600:
            raise ValueError("demo interval must be between 1 and 3600 seconds")
        clean["interval_seconds"] = interval
    if "timeout_seconds" in settings:
        try:
            timeout = int(settings["timeout_seconds"])
        except (TypeError, ValueError) as exc:
            raise ValueError("demo timeout must be an integer") from exc
        if timeout < 60 or timeout > 86400:
            raise ValueError("demo timeout must be between 60 and 86400 seconds")
        clean["timeout_seconds"] = timeout
    return clean


@dataclass(frozen=True)
class UserDemoSettingsStore:
    """Read and write one user's normalized demo settings."""

    session_factory: Callable[[], Session]

    def get(self, user_id: str) -> dict:
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return dict(DEMO_DEFAULT_SETTINGS)
            try:
                parsed = json.loads(row.demo_settings or "{}")
            except json.JSONDecodeError:
                return dict(DEMO_DEFAULT_SETTINGS)
            if not isinstance(parsed, dict):
                return dict(DEMO_DEFAULT_SETTINGS)
            try:
                return normalize_demo_settings(parsed)
            except ValueError:
                return dict(DEMO_DEFAULT_SETTINGS)

    def update(self, user_id: str, settings: dict) -> dict | None:
        clean = normalize_demo_settings(settings)
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return None
            row.demo_settings = json.dumps(clean, ensure_ascii=False)
            session.commit()
            return clean


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
