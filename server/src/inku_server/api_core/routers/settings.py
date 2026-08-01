"""Endpoints for the settings group, moved out of api.py unchanged."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ...plugins import plugin_status_items
from ...model_settings import MODEL_METADATA_KEYS, connection_for, model_provider_catalog, normalize_model_settings, public_model_settings, update_model_settings
from ... import db as _db
from ..common import _env_flag
from ..deps import _admin_user
from ..models import ModelSettingsResponse
from ..rendering import _output_save_settings
from ..state import _SAVE_QUEUE_LIMIT, _SAVE_WORKERS, _STAGE_QUEUE_LIMIT, _STAGE_WORKERS, _artifact_save_stats, _render_slots, _stage_execution_stats


router = APIRouter(dependencies=[Depends(_admin_user)])


_LOG_SERVICE_FILES = {
    "inku-server": "/var/log/inku/inku-server.log",
    "inku-api": "/var/log/inku/inku-api.log",
}


_LOG_DIR = "/var/log/inku"


def _log_retention_settings() -> dict:
    return _db.get_log_retention_settings()


def _log_systemd_dropins(settings: dict) -> dict[str, str]:
    if not settings["enabled"]:
        return {}
    return {
        service: "\n".join(
            [
                "[Service]",
                "LogsDirectory=inku",
                f"StandardOutput=journal+append:{path}",
                f"StandardError=journal+append:{path}",
                "",
            ]
        )
        for service, path in _LOG_SERVICE_FILES.items()
    }


def _logrotate_config(settings: dict) -> str:
    if not settings["enabled"]:
        return "# Log retention is disabled.\n"
    paths = " ".join(_LOG_SERVICE_FILES.values())
    lines = [
        f"{paths} {{",
        f"    {settings['rotate']}",
        f"    rotate {settings['retention_days']}",
        f"    maxage {settings['retention_days']}",
        "    missingok",
        "    notifempty",
    ]
    if settings["compress"]:
        lines.extend(["    compress", "    delaycompress"])
    lines.extend(
        [
            "    copytruncate",
            "    dateext",
            "    dateformat -%Y%m%d",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


class DatabaseSettingsStatus(BaseModel):
    backend: str
    driver: str
    url: str
    database: str | None = None
    is_default: bool
    file_size_bytes: int | None = None
    file_path: str | None = None
    runtime_editable: bool = False
    note: str


class DbBackupEntry(BaseModel):
    kind: Literal["auto", "manual"]
    name: str
    at: int
    size_bytes: int
    generation: int | None = None


class DbBackupStatus(BaseModel):
    supported: bool
    interval_days: int
    max_generations: int
    backup_hour: int = 3
    backup_minute: int = 0
    last_auto_backup_at: int = 0
    next_auto_backup_at: int = 0
    backup_dir: str
    auto_count: int = 0
    manual_count: int = 0
    backups: list[DbBackupEntry] = Field(default_factory=list)
    backups_total_count: int = 0
    backups_total_size_bytes: int = 0


class DbBackupSettingsBody(BaseModel):
    interval_days: int = Field(default=7, ge=1, le=365)
    max_generations: int = Field(default=4, ge=1, le=100)
    backup_hour: int = Field(default=3, ge=0, le=23)
    backup_minute: int = Field(default=0, ge=0, le=59)


class OutputSaveSettingsBody(BaseModel):
    enabled: bool = True
    output_dir: str
    png_size: int = Field(default=2160)


class LogRetentionSettingsBody(BaseModel):
    enabled: bool = True
    retention_days: int = Field(default=90, ge=1, le=3650)
    rotate: str = Field(default="daily", pattern="^(daily|weekly|monthly)$")
    compress: bool = True


class DbBackupResult(BaseModel):
    path: str
    at: int
    manual: bool
    size_bytes: int | None = None


class PluginSettingsStatus(BaseModel):
    enabled: bool = False
    loaded: list[dict[str, object]] = Field(default_factory=list)
    runtime_editable: bool = False
    note: str


class OutputSaveStatus(BaseModel):
    enabled: bool
    output_dir: str
    png_size: int
    workers: int
    queue_limit: int
    submitted: int
    completed: int
    failed: int
    skipped: int
    note: str


class LogRetentionStatus(BaseModel):
    enabled: bool
    retention_days: int
    rotate: str
    compress: bool
    log_dir: str
    services: list[str]
    systemd_dropins: dict[str, str]
    logrotate_config: str
    note: str


class StageExecutionStatus(BaseModel):
    workers: int
    queue_limit: int
    submitted: int
    completed: int
    failed: int
    timed_out: int
    rejected: int
    note: str


class ModelProviderPatch(BaseModel):
    label: str | None = None
    kind: str | None = None
    api_key_env: str | None = None
    base_url_env: str | None = None
    default_base_url: str | None = None
    requires_api_key: bool | None = None
    memo: str | None = None
    models: list[dict] = Field(default_factory=list)
    active: bool | None = None
    delete: bool = False
    base_url: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    enabled_models: dict[str, bool] = Field(default_factory=dict)


class ModelSettingsPatch(BaseModel):
    stage1_provider: str | None = None
    stage1_model: str | None = None
    stage2_provider: str | None = None
    stage2_model: str | None = None
    providers: dict[str, ModelProviderPatch] = Field(default_factory=dict)


class RenderConcurrencyStatus(BaseModel):
    server_limit: int
    client_limit: int
    min_limit: int
    max_limit: int
    note: str


class SettingsStatusResponse(BaseModel):
    database: DatabaseSettingsStatus
    db_backup: DbBackupStatus
    plugins: PluginSettingsStatus
    output_save: OutputSaveStatus
    log_retention: LogRetentionStatus
    stage_execution: StageExecutionStatus
    render_concurrency: RenderConcurrencyStatus


@router.get("/api/settings/status", response_model=SettingsStatusResponse)
def api_settings_status(actor: dict = Depends(_admin_user)) -> SettingsStatusResponse:
    # Reading the panel must not write a backup. This used to call
    # ensure_scheduled_db_backup() because it was the only trigger there was;
    # the resident scheduler asks the same question every minute now.
    db_info = _db.database_info()
    output_settings = _output_save_settings()
    log_settings = _log_retention_settings()
    return SettingsStatusResponse(
        database=DatabaseSettingsStatus(
            **db_info,
            note="DB connection is selected at server startup by INKU_DB_URL. Restart the server after changing it.",
        ),
        db_backup=DbBackupStatus(**_db.db_backup_status()),
        plugins=PluginSettingsStatus(
            enabled=True,
            loaded=plugin_status_items(),
            runtime_editable=True,
            note="Declarative DDL plugin documents are reloaded without restarting; rejected documents include reasons.",
        ),
        output_save=OutputSaveStatus(
            enabled=bool(output_settings["enabled"]),
            output_dir=str(output_settings["output_dir"]),
            png_size=int(output_settings["png_size"]),
            workers=_SAVE_WORKERS,
            queue_limit=_SAVE_QUEUE_LIMIT,
            **_artifact_save_stats(),
            note="History DB is the source of truth. Output files are background artifacts and may be rebuilt from DB.",
        ),
        log_retention=LogRetentionStatus(
            enabled=bool(log_settings["enabled"]),
            retention_days=int(log_settings["retention_days"]),
            rotate=str(log_settings["rotate"]),
            compress=bool(log_settings["compress"]),
            log_dir=_LOG_DIR,
            services=list(_LOG_SERVICE_FILES),
            systemd_dropins=_log_systemd_dropins(log_settings),
            logrotate_config=_logrotate_config(log_settings),
            note="Log retention policy is stored in the application DB. Applying systemd and logrotate files requires server OS privileges.",
        ),
        render_concurrency=_render_concurrency_status(),
        stage_execution=StageExecutionStatus(
            workers=_STAGE_WORKERS,
            queue_limit=_STAGE_QUEUE_LIMIT,
            **_stage_execution_stats(),
            note="Stage 1/2 LLM calls share a bounded executor. Timed-out calls keep capacity until the underlying call finishes.",
        ),
    )


@router.get("/api/settings/models", response_model=ModelSettingsResponse)
def api_settings_models(actor: dict = Depends(_admin_user)) -> ModelSettingsResponse:
    settings = _db.get_model_settings()
    developer_mode = _env_flag("INKU_DEVELOPER_MODE")
    return ModelSettingsResponse(
        catalog=model_provider_catalog(
            settings, include_disabled=True, include_developer=developer_mode
        ),
        settings=public_model_settings(settings, include_developer=developer_mode),
    )


@router.put("/api/settings/models", response_model=ModelSettingsResponse)
def api_settings_update_models(
    body: ModelSettingsPatch,
    actor: dict = Depends(_admin_user),
) -> ModelSettingsResponse:
    current = _db.get_model_settings()
    provider_patch = {
        key: value.model_dump(exclude_unset=True)
        for key, value in body.providers.items()
    }
    next_settings = update_model_settings(current, {
        **body.model_dump(exclude={"providers"}, exclude_unset=True),
        "providers": provider_patch,
    })
    saved = _db.update_model_settings(next_settings)
    developer_mode = _env_flag("INKU_DEVELOPER_MODE")
    return ModelSettingsResponse(
        catalog=model_provider_catalog(
            saved, include_disabled=True, include_developer=developer_mode
        ),
        settings=public_model_settings(saved, include_developer=developer_mode),
    )


def _fetch_provider_model_list(provider_id: str, settings: dict) -> list[dict[str, str]]:
    catalog = {
        str(provider["id"]): provider
        for provider in model_provider_catalog(
            settings, include_disabled=True, include_developer=_env_flag("INKU_DEVELOPER_MODE")
        )
    }
    provider = catalog.get(provider_id)
    if not provider:
        raise ValueError("unknown provider")
    conn = connection_for(provider_id, settings)
    base_url = str(conn["base_url"]).rstrip("/")
    headers: dict[str, str] = {"Accept": "application/json"}
    if conn.get("kind") == "anthropic":
        url = f"{base_url}/v1/models"
        if conn.get("api_key"):
            headers["x-api-key"] = str(conn["api_key"])
        headers["anthropic-version"] = "2023-06-01"
    elif conn.get("kind") == "gemini":
        query = f"?key={urllib.parse.quote(str(conn.get('api_key') or ''))}" if conn.get("api_key") else ""
        url = f"{base_url}/v1beta/models{query}"
    else:
        url = f"{base_url}/models"
        if conn.get("api_key"):
            headers["Authorization"] = f"Bearer {conn['api_key']}"
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ValueError(f"model list fetch failed: {exc}") from exc

    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if raw_models is None and isinstance(payload, dict):
        raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        raise ValueError("model list response did not contain models")
    models: list[dict[str, str]] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("name") or "").strip()
        if model_id.startswith("models/"):
            model_id = model_id.removeprefix("models/")
        if not model_id:
            continue
        label = str(item.get("display_name") or item.get("displayName") or model_id).strip()
        models.append({"id": model_id, "label": label or model_id})
    if not models:
        raise ValueError("model list response was empty")
    return models


@router.post("/api/settings/models/{provider_id}/fetch-models", response_model=ModelSettingsResponse)
def api_settings_fetch_provider_models(
    provider_id: str,
    actor: dict = Depends(_admin_user),
) -> ModelSettingsResponse:
    current = _db.get_model_settings()
    try:
        models = _fetch_provider_model_list(provider_id, current)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    clean = normalize_model_settings(current)
    previous_provider = clean.get("providers", {}).get(provider_id, {})
    previous_models = {
        str(model.get("id")): model
        for model in previous_provider.get("models", [])
    }
    carried = (
        *MODEL_METADATA_KEYS,
        "eol", "eol_date",
        # 有料プラン限定の印は提供元の一覧に現れない (一覧には載るが叩くと 403 が
        # 返る)。取得のたびに消えては困るので、EOL と違って再提供で外さない。
        "requires_subscription",
    )
    for model in models:
        previous = previous_models.get(str(model["id"]))
        if not previous:
            continue
        for key in carried:
            if key in previous:
                model[key] = previous[key]
        # NVIDIA NIM のようにプロバイダが display_name を返さない場合、取得のたびに
        # ラベルが ID へ戻ってしまう。提供元が実質ラベルを持たないときだけ、
        # 既存の整えたラベルを残す (提供元が名前を返すならそちらを優先)。
        previous_label = str(previous.get("label") or "").strip()
        if (
            previous_label
            and previous_label != str(previous.get("id"))
            and str(model.get("label") or "") == str(model["id"])
        ):
            model["label"] = previous_label
        # 一度 EOL にしたモデルが再び提供された場合は印を外す。
        model.pop("eol", None)
        model.pop("eol_date", None)

    # 提供元から消えたモデルは削除せず EOL として末尾に残す。過去の作品が記録して
    # いるモデル名の表示・評価情報を失わないため (v1.98)。
    live_ids = {str(model["id"]) for model in models}
    retired_on = datetime.now(timezone.utc).date().isoformat()
    retired = []
    for model_id, previous in previous_models.items():
        if model_id in live_ids:
            continue
        kept = dict(previous)
        kept["eol"] = True
        kept.setdefault("eol_date", retired_on)
        retired.append(kept)
    models = models + sorted(retired, key=lambda item: str(item.get("id")))

    previous_enabled_models = previous_provider.get("enabled_models") or {}
    enabled_models = {
        model["id"]: (
            not model.get("eol")
            and not model.get("requires_subscription")
            and str(model["id"]) in previous_models
            and bool(previous_enabled_models.get(model["id"], False))
        )
        for model in models
    }
    saved = _db.update_model_settings(update_model_settings(current, {
        "providers": {
            provider_id: {
                "models": models,
                "enabled_models": enabled_models,
            }
        }
    }))
    developer_mode = _env_flag("INKU_DEVELOPER_MODE")
    return ModelSettingsResponse(
        catalog=model_provider_catalog(
            saved, include_disabled=True, include_developer=developer_mode
        ),
        settings=public_model_settings(saved, include_developer=developer_mode),
    )


@router.put("/api/settings/db-backup", response_model=DbBackupStatus)
def api_settings_update_db_backup(
    body: DbBackupSettingsBody,
    actor: dict = Depends(_admin_user),
) -> DbBackupStatus:
    try:
        _db.update_db_backup_settings(
            body.interval_days,
            body.max_generations,
            body.backup_hour,
            body.backup_minute,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return DbBackupStatus(**_db.db_backup_status())


@router.put("/api/settings/output-save", response_model=OutputSaveStatus)
def api_settings_update_output_save(
    body: OutputSaveSettingsBody,
    actor: dict = Depends(_admin_user),
) -> OutputSaveStatus:
    try:
        output_settings = _db.update_output_save_settings(body.enabled, body.output_dir, body.png_size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return OutputSaveStatus(
        enabled=bool(output_settings["enabled"]),
        output_dir=str(output_settings["output_dir"]),
        png_size=int(output_settings["png_size"]),
        workers=_SAVE_WORKERS,
        queue_limit=_SAVE_QUEUE_LIMIT,
        **_artifact_save_stats(),
        note="History DB is the source of truth. Output files are background artifacts and may be rebuilt from DB.",
    )


def _render_concurrency_status() -> RenderConcurrencyStatus:
    settings = _db.get_render_concurrency_settings()
    return RenderConcurrencyStatus(
        server_limit=_render_slots.limit,
        client_limit=int(settings["client_limit"]),
        min_limit=_db.RENDER_CONCURRENCY_MIN,
        max_limit=_db.RENDER_CONCURRENCY_MAX,
        note=(
            "Server limit caps concurrent renders in this process; requests beyond it are refused with 503. "
            "Client limit is advisory and bounds the browser's candidate fan-out. "
            "INKU_RENDER_CONCURRENCY / INKU_CLIENT_FANOUT_LIMIT only seed the first value."
        ),
    )


class RenderConcurrencyBody(BaseModel):
    server_limit: int
    client_limit: int


@router.put("/api/settings/render-concurrency", response_model=RenderConcurrencyStatus)
def api_settings_update_render_concurrency(
    body: RenderConcurrencyBody,
    actor: dict = Depends(_admin_user),
) -> RenderConcurrencyStatus:
    try:
        settings = _db.update_render_concurrency_settings(body.server_limit, body.client_limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # New limit applies to renders acquired from here on; running renders finish.
    _render_slots.set_limit(int(settings["server_limit"]))
    return _render_concurrency_status()


@router.put("/api/settings/log-retention", response_model=LogRetentionStatus)
def api_settings_update_log_retention(
    body: LogRetentionSettingsBody,
    actor: dict = Depends(_admin_user),
) -> LogRetentionStatus:
    try:
        log_settings = _db.update_log_retention_settings(
            body.enabled,
            body.retention_days,
            body.rotate,
            body.compress,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return LogRetentionStatus(
        enabled=bool(log_settings["enabled"]),
        retention_days=int(log_settings["retention_days"]),
        rotate=str(log_settings["rotate"]),
        compress=bool(log_settings["compress"]),
        log_dir=_LOG_DIR,
        services=list(_LOG_SERVICE_FILES),
        systemd_dropins=_log_systemd_dropins(log_settings),
        logrotate_config=_logrotate_config(log_settings),
        note="Log retention policy is stored in the application DB. Applying systemd and logrotate files requires server OS privileges.",
    )


@router.post("/api/settings/db-backup/run", response_model=DbBackupResult)
def api_settings_run_db_backup(actor: dict = Depends(_admin_user)) -> DbBackupResult:
    try:
        result = _db.create_db_backup(manual=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return DbBackupResult(**result)
