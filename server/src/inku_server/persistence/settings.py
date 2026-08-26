"""Persistence-owned storage for generic application settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
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
EXPORT_TEMPLATE_LIMIT = 20
EXPORT_TEMPLATE_DEFAULTS = [
    {
        "id": "png-1080",
        "name": "PNG 1080px",
        "description": "PNG / Y軸 1080px",
        "y_px": 1080,
    },
    {
        "id": "png-2160",
        "name": "PNG 2160px",
        "description": "PNG / Y軸 2160px",
        "y_px": 2160,
    },
    {
        "id": "png-4320",
        "name": "PNG 4320px",
        "description": "PNG / Y軸 4320px",
        "y_px": 4320,
    },
]
PLUGIN_STORAGE_MAX_BYTES = 20_000
OUTPUT_SAVE_SETTINGS_KEY = "output_save_settings"
OUTPUT_SAVE_DEFAULT_SETTINGS = {
    "enabled": True,
    "output_dir": str(
        Path(
            os.getenv(
                "INKU_OUTPUT_DIR",
                str(Path.home() / ".local" / "share" / "inku" / "outputs"),
            )
        )
    ),
    "png_size": int(os.getenv("INKU_OUTPUT_PNG_SIZE", "2160")),
}
RENDER_CONCURRENCY_SETTINGS_KEY = "render_concurrency_settings"
# INKU_RENDER_CONCURRENCY / INKU_CLIENT_FANOUT_LIMIT seed the first value only;
# once stored, the DB row is the source of truth (admin settings screen).
RENDER_CONCURRENCY_DEFAULT_SETTINGS = {
    "server_limit": int(os.getenv("INKU_RENDER_CONCURRENCY", "2")),
    "client_limit": int(os.getenv("INKU_CLIENT_FANOUT_LIMIT", "4")),
}
RENDER_CONCURRENCY_MIN = 1
RENDER_CONCURRENCY_MAX = 16
RENDER_LIMIT_SETTINGS_KEY = "render_limit_settings"
THUMBNAIL_SETTINGS_KEY = "thumbnail_settings"
# Off by default: the second size doubles the rebuild and roughly quadruples the
# stored bytes, and is worth neither until someone is looking at the listing on
# a HiDPI screen.
# The parallelism is the administrator's to enter: nothing here reads the core
# count, and in a container the host's count is the wrong answer anyway.
THUMBNAIL_DEFAULT_SETTINGS = {
    "hidpi": False,
    "workers": 4,
}
THUMBNAIL_WORKERS_MIN = 1
THUMBNAIL_WORKERS_MAX = 16
LOG_RETENTION_SETTINGS_KEY = "log_retention_settings"
LOG_RETENTION_DEFAULT_SETTINGS = {
    "enabled": True,
    "retention_days": int(os.getenv("INKU_LOG_RETENTION_DAYS", "90")),
    "rotate": os.getenv("INKU_LOG_ROTATE", "daily"),
    "compress": True,
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


def normalize_export_templates(items: list[dict]) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("export templates must be a list")
    if (
        len(items) == 2
        and items[0].get("id") == "png-1024"
        and items[0].get("y_px") == 1024
        and items[1].get("id") == "png-2048"
        and items[1].get("y_px") == 2048
    ):
        return [dict(item) for item in EXPORT_TEMPLATE_DEFAULTS]
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("export template must be an object")
        template_id = item.get("id")
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError("export template id is required")
        template_id = template_id.strip()[:80]
        if template_id in seen:
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("export template name is required")
        description = item.get("description", "")
        if not isinstance(description, str):
            raise ValueError("export template description must be a string")
        try:
            y_px = int(item.get("y_px"))
        except (TypeError, ValueError) as exc:
            raise ValueError("export template y_px must be an integer") from exc
        if y_px < 64 or y_px > 12000:
            raise ValueError("export template y_px must be between 64 and 12000")
        normalized.append(
            {
                "id": template_id,
                "name": name.strip()[:80],
                "description": description.strip()[:240],
                "y_px": y_px,
            }
        )
        seen.add(template_id)
        if len(normalized) >= EXPORT_TEMPLATE_LIMIT:
            break
    return normalized or [dict(item) for item in EXPORT_TEMPLATE_DEFAULTS]


@dataclass(frozen=True)
class UserExportTemplateStore:
    """Read and write one user's normalized export templates."""

    session_factory: Callable[[], Session]

    def get(self, user_id: str) -> list[dict]:
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return [dict(item) for item in EXPORT_TEMPLATE_DEFAULTS]
            try:
                parsed = json.loads(row.export_templates or "[]")
            except json.JSONDecodeError:
                return [dict(item) for item in EXPORT_TEMPLATE_DEFAULTS]
            if not isinstance(parsed, list) or not parsed:
                return [dict(item) for item in EXPORT_TEMPLATE_DEFAULTS]
            try:
                return normalize_export_templates(parsed)
            except ValueError:
                return [dict(item) for item in EXPORT_TEMPLATE_DEFAULTS]

    def update(self, user_id: str, items: list[dict]) -> list[dict] | None:
        clean = normalize_export_templates(items)
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return None
            row.export_templates = json.dumps(clean, ensure_ascii=False)
            session.commit()
            return clean


def normalize_plugin_storage(storage: dict) -> dict:
    if not isinstance(storage, dict):
        raise ValueError("plugin storage must be an object")
    normalized: dict[str, dict] = {}
    for plugin_id, value in storage.items():
        if not isinstance(plugin_id, str) or not plugin_id:
            raise ValueError("plugin id must be a non-empty string")
        if len(plugin_id) > 80 or not all(ch.isalnum() or ch in "-_." for ch in plugin_id):
            raise ValueError("plugin id contains unsupported characters")
        if not isinstance(value, dict):
            raise ValueError("plugin storage values must be objects")
        normalized[plugin_id] = value
    raw = json.dumps(normalized, ensure_ascii=False)
    if len(raw.encode("utf-8")) > PLUGIN_STORAGE_MAX_BYTES:
        raise ValueError("plugin storage is too large")
    return normalized


def normalize_output_save_settings(settings: dict | None) -> dict:
    clean = dict(OUTPUT_SAVE_DEFAULT_SETTINGS)
    if not isinstance(settings, dict):
        return clean
    if "enabled" in settings:
        clean["enabled"] = bool(settings["enabled"])
    if "output_dir" in settings:
        raw_path = str(settings["output_dir"] or "").strip()
        if not raw_path:
            raise ValueError("output directory must not be empty")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise ValueError("output directory must be an absolute path")
        clean["output_dir"] = str(path)
    if "png_size" in settings:
        try:
            png_size = int(settings["png_size"])
        except (TypeError, ValueError) as exc:
            raise ValueError("PNG size must be 1080 or 2160") from exc
        if png_size not in {1080, 2160}:
            raise ValueError("PNG size must be 1080 or 2160")
        clean["png_size"] = png_size
    return clean


def clamped_concurrency(value: object, key: str) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if number < RENDER_CONCURRENCY_MIN or number > RENDER_CONCURRENCY_MAX:
        raise ValueError(
            f"{key} must be between {RENDER_CONCURRENCY_MIN} and "
            f"{RENDER_CONCURRENCY_MAX}"
        )
    return number


def normalize_render_concurrency_settings(settings: dict | None) -> dict:
    clean = dict(RENDER_CONCURRENCY_DEFAULT_SETTINGS)
    for key in ("server_limit", "client_limit"):
        clean[key] = clamped_concurrency(clean[key], key)
    if not isinstance(settings, dict):
        return clean
    for key in ("server_limit", "client_limit"):
        if key in settings:
            clean[key] = clamped_concurrency(settings[key], key)
    return clean


def normalize_thumbnail_settings(settings: dict | None) -> dict:
    clean = dict(THUMBNAIL_DEFAULT_SETTINGS)
    if not isinstance(settings, dict):
        return clean
    if "hidpi" in settings:
        clean["hidpi"] = bool(settings["hidpi"])
    if "workers" in settings:
        try:
            workers = int(settings["workers"])
        except (TypeError, ValueError):
            workers = clean["workers"]
        clean["workers"] = max(
            THUMBNAIL_WORKERS_MIN, min(THUMBNAIL_WORKERS_MAX, workers)
        )
    return clean


def normalize_log_retention_settings(settings: dict | None) -> dict:
    clean = dict(LOG_RETENTION_DEFAULT_SETTINGS)
    if clean["rotate"] not in {"daily", "weekly", "monthly"}:
        clean["rotate"] = "daily"
    if clean["retention_days"] < 1:
        clean["retention_days"] = 90
    if not isinstance(settings, dict):
        return clean
    if "enabled" in settings:
        clean["enabled"] = bool(settings["enabled"])
    if "retention_days" in settings:
        try:
            retention_days = int(settings["retention_days"])
        except (TypeError, ValueError) as exc:
            raise ValueError("log retention days must be an integer") from exc
        if retention_days < 1 or retention_days > 3650:
            raise ValueError("log retention days must be between 1 and 3650")
        clean["retention_days"] = retention_days
    if "rotate" in settings:
        rotate = str(settings["rotate"] or "").strip().lower()
        if rotate not in {"daily", "weekly", "monthly"}:
            raise ValueError("log rotate must be daily, weekly, or monthly")
        clean["rotate"] = rotate
    if "compress" in settings:
        clean["compress"] = bool(settings["compress"])
    return clean


@dataclass(frozen=True)
class UserPluginStorageStore:
    """Read and write one user's validated plugin storage."""

    session_factory: Callable[[], Session]

    def get(self, user_id: str) -> dict:
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return {}
            try:
                parsed = json.loads(row.plugin_storage or "{}")
            except json.JSONDecodeError:
                return {}
            if not isinstance(parsed, dict):
                return {}
            try:
                return normalize_plugin_storage(parsed)
            except ValueError:
                return {}

    def update(self, user_id: str, storage: dict) -> dict | None:
        clean = normalize_plugin_storage(storage)
        with self.session_factory() as session:
            row = session.get(UserAccountRow, user_id)
            if not row:
                return None
            row.plugin_storage = json.dumps(clean, ensure_ascii=False)
            session.commit()
            return clean

    def update_value(self, user_id: str, plugin_id: str, value: dict) -> dict | None:
        current = self.get(user_id)
        current[plugin_id] = value
        return self.update(user_id, current)


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
class OutputSaveSettingsStore:
    """Read and write normalized output-save settings."""

    app_settings: AppSettingsStore

    def get(self) -> dict:
        return normalize_output_save_settings(
            self.app_settings.read(OUTPUT_SAVE_SETTINGS_KEY)
        )

    def update(self, enabled: bool, output_dir: str, png_size: int) -> dict:
        clean = normalize_output_save_settings(
            {
                "enabled": enabled,
                "output_dir": output_dir,
                "png_size": png_size,
            }
        )
        return self.app_settings.write(OUTPUT_SAVE_SETTINGS_KEY, clean)


@dataclass(frozen=True)
class RenderConcurrencySettingsStore:
    """Read and write normalized render-concurrency settings."""

    app_settings: AppSettingsStore

    def get(self) -> dict:
        return normalize_render_concurrency_settings(
            self.app_settings.read(RENDER_CONCURRENCY_SETTINGS_KEY)
        )

    def update(self, server_limit: int, client_limit: int) -> dict:
        clean = normalize_render_concurrency_settings(
            {"server_limit": server_limit, "client_limit": client_limit}
        )
        return self.app_settings.write(RENDER_CONCURRENCY_SETTINGS_KEY, clean)


@dataclass(frozen=True)
class RenderLimitSettingsStore:
    """Read and merge-write normalized render-limit settings."""

    app_settings: AppSettingsStore
    normalize: Callable[[object], dict[str, int]]

    def get(self) -> dict[str, int]:
        return self.normalize(self.app_settings.read(RENDER_LIMIT_SETTINGS_KEY))

    def update(self, settings: dict) -> dict:
        """Merge a partial update over what is stored and normalize the result.

        Rounding happens before the write, so what comes back is what took effect --
        a caller that sent a self-contradicting set gets the corrected one, not its
        own input echoed.
        """
        current = self.get()
        if isinstance(settings, dict):
            current.update(
                {key: value for key, value in settings.items() if key in current}
            )
        clean = self.normalize(current)
        return self.app_settings.write(RENDER_LIMIT_SETTINGS_KEY, clean)


@dataclass(frozen=True)
class ThumbnailSettingsStore:
    """Read and write normalized thumbnail settings."""

    app_settings: AppSettingsStore

    def get(self) -> dict:
        return normalize_thumbnail_settings(
            self.app_settings.read(THUMBNAIL_SETTINGS_KEY)
        )

    def update(self, hidpi: bool, workers: int) -> dict:
        clean = normalize_thumbnail_settings({"hidpi": hidpi, "workers": workers})
        return self.app_settings.write(THUMBNAIL_SETTINGS_KEY, clean)


@dataclass(frozen=True)
class LogRetentionSettingsStore:
    """Read and write normalized log-retention settings."""

    app_settings: AppSettingsStore

    def get(self) -> dict:
        return normalize_log_retention_settings(
            self.app_settings.read(LOG_RETENTION_SETTINGS_KEY)
        )

    def update(
        self,
        enabled: bool,
        retention_days: int,
        rotate: str,
        compress: bool,
    ) -> dict:
        clean = normalize_log_retention_settings(
            {
                "enabled": enabled,
                "retention_days": retention_days,
                "rotate": rotate,
                "compress": compress,
            }
        )
        return self.app_settings.write(LOG_RETENTION_SETTINGS_KEY, clean)


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
