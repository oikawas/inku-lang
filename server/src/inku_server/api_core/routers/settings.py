"""Endpoints for the settings group, moved out of api.py unchanged."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from ...limits import (
    BYTES_PER_MARK,
    LIMIT_ABSOLUTE_MAX,
    LIMIT_GROUPS,
    SVG_LIMIT_FIELD,
    SVG_LIMIT_MIN_MIB,
    SVG_LIMIT_MAX_MIB,
    normalize_render_limit_settings,
)
from ...persistence.backup import BackupNotFoundError, BackupSchemaMismatchError, SQLiteSnapshotError
from ...plugins import plugin_status_items
from ...model_catalog import catalog_models
from ...model_settings import MODEL_METADATA_KEYS, connection_for, model_provider_catalog, normalize_model_settings, public_model_settings, update_model_settings
from ... import db as _db
from ... import logging_setup as _logging_setup
from ... import thumbs_db as _thumbs_db
from .. import thumbnails as _thumbnails
from ..common import _env_flag
from ..deps import _admin_user, _logger
from ..models import ModelSettingsResponse
from ..rendering import _output_save_settings
from ..state import _SAVE_QUEUE_LIMIT, _SAVE_WORKERS, _artifact_save_stats, _render_slots, _stage_execution_stats, _thumbnail_stats


router = APIRouter(dependencies=[Depends(_admin_user)])


def _log_retention_settings() -> dict:
    return _db.get_log_retention_settings()


def _log_retention_status(settings: dict) -> "LogRetentionStatus":
    """One builder for both the GET and the PUT, so the two cannot drift."""
    return LogRetentionStatus(
        enabled=bool(settings["enabled"]),
        retention_days=int(settings["retention_days"]),
        rotate=str(settings["rotate"]),
        compress=bool(settings["compress"]),
        log_dir=str(_logging_setup.log_dir()),
        files=_logging_setup.current_log_files(),
        note=(
            "The log retention policy is stored in the application DB and the application "
            "executes it: it writes, rotates and prunes the files itself. Lines keep going "
            "to stdout as well, so journalctl and docker logs are unchanged."
        ),
    )


class DatabaseSettingsStatus(BaseModel):
    backend: str = Field(description="Database backend name from the connection URL, such as sqlite or postgresql")
    driver: str = Field(description="SQLAlchemy driver name from the connection URL")
    url: str = Field(description="Connection URL with any password hidden")
    database: str | None = Field(
        default=None,
        description="Database name from the connection URL; for SQLite, the file path given there",
    )
    is_default: bool = Field(description="Whether the store is the default one rather than a configured URL")
    file_size_bytes: int | None = Field(
        default=None,
        description="Size in bytes of the SQLite file plus its write-ahead log; None when the database is not a file",
    )
    file_path: str | None = Field(
        default=None,
        description="Path of the SQLite file; None when the database is not a file",
    )
    runtime_editable: bool = Field(
        default=False,
        description="Whether the connection can be changed while the server runs; always false, because it is chosen at startup",
    )
    note: str = Field(description="Explanation of how the database connection is chosen")


class DbBackupEntry(BaseModel):
    kind: Literal["auto", "manual"] = Field(
        description="auto for a scheduled copy, which is pruned by generation; manual for a copy requested by an administrator, which is never pruned",
    )
    name: str = Field(description="File name of the copy inside its auto or manual folder")
    at: int = Field(description="When the copy was written, in milliseconds since the Unix epoch, from the file's modification time")
    size_bytes: int = Field(description="Size of the copy in bytes")
    generation: int | None = Field(
        default=None,
        description="Position among automatic copies, where 1 is the newest; None for manual copies, which are not numbered",
    )


class DbBackupStatus(BaseModel):
    supported: bool = Field(description="Whether backups can be made; true only for a SQLite file database")
    interval_days: int = Field(description="Days between automatic backups")
    max_generations: int = Field(description="Number of automatic copies kept; older automatic copies are deleted after each new one")
    backup_hour: int = Field(
        default=3,
        description="Hour of the day, from 0 to 23 in the server's local time, at which an automatic backup is due",
    )
    backup_minute: int = Field(
        default=0,
        description="Minute of the hour, from 0 to 59, at which an automatic backup is due",
    )
    last_auto_backup_at: int = Field(
        default=0,
        description="When the last automatic backup was made, in milliseconds since the Unix epoch; 0 when none has run",
    )
    next_auto_backup_at: int = Field(
        default=0,
        description="When the next automatic backup is due, in milliseconds since the Unix epoch; 0 when none has run yet, which means it is due at once",
    )
    backup_dir: str = Field(description="Folder that holds the automatic and manual backup subfolders")
    auto_count: int = Field(default=0, description="Number of automatic copies on disk")
    manual_count: int = Field(default=0, description="Number of manual copies on disk")
    backups: list[DbBackupEntry] = Field(
        default_factory=list,
        description="Retained copies, newest first, limited to 50 entries",
    )
    backups_total_count: int = Field(
        default=0,
        description="Number of copies on disk, including any beyond the list limit",
    )
    backups_total_size_bytes: int = Field(
        default=0,
        description="Total size in bytes of every copy on disk, including any beyond the list limit",
    )


class DbBackupSettingsBody(BaseModel):
    interval_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Days between automatic backups, from 1 to 365",
    )
    max_generations: int = Field(
        default=4,
        ge=1,
        le=100,
        description="Number of automatic copies to keep, from 1 to 100",
    )
    backup_hour: int = Field(
        default=3,
        ge=0,
        le=23,
        description="Hour of the day, from 0 to 23 in the server's local time, at which an automatic backup is due",
    )
    backup_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        description="Minute of the hour, from 0 to 59, at which an automatic backup is due",
    )


class OutputSaveSettingsBody(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Whether each finished work is written to output_dir in the background",
    )
    output_dir: str = Field(description="Absolute folder that receives the saved output files; must not be empty")
    png_size: int = Field(
        default=2160,
        description="Size of the saved PNG in pixels, either 1080 or 2160; any other value is refused with 400",
    )


class ThumbnailSettingsBody(BaseModel):
    hidpi: bool = Field(
        default=False,
        description="Whether a second, double-size thumbnail set (scale 2) is also made, for high-density screens",
    )
    # Rasterizing is CPU-bound, so the useful range is the machine's cores --
    # and the machine is not asked, because in a container the host's count is
    # the wrong answer. The administrator enters it, once, and the rebuild reads
    # it: one place decides the parallelism.
    workers: int = Field(
        default=4,
        ge=_db.THUMBNAIL_WORKERS_MIN,
        le=_db.THUMBNAIL_WORKERS_MAX,
        description="Number of thumbnails baked at once, within the accepted range; every rebuild uses this number",
    )


class LogRetentionSettingsBody(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Whether the server writes its own log files and applies this policy; lines also still go to stdout",
    )
    retention_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Number of rotated log files kept before pruning: one file per day, week or month according to rotate, from 1 to 3650",
    )
    rotate: str = Field(
        default="daily",
        pattern="^(daily|weekly|monthly)$",
        description="How often the log file rotates: daily, weekly or monthly",
    )
    compress: bool = Field(default=True, description="Whether rotated log files are gzip-compressed")


class DbBackupResult(BaseModel):
    path: str = Field(description="Path of the new copy")
    at: int = Field(description="When the copy was made, in milliseconds since the Unix epoch")
    manual: bool = Field(description="Whether the copy was requested by an administrator; true for this endpoint")
    size_bytes: int | None = Field(
        default=None,
        description="Size of the copy in bytes; None when the file is not present after it was written",
    )


class PluginSettingsStatus(BaseModel):
    enabled: bool = Field(default=False, description="Whether declarative DDL plugin documents are in use")
    loaded: list[dict[str, object]] = Field(
        default_factory=list,
        description="Status of each plugin document, as the plugin loader reports it, including the reason a document was rejected",
    )
    runtime_editable: bool = Field(
        default=False,
        description="Whether plugin documents can be changed while the server runs, without a restart",
    )
    note: str = Field(description="Explanation of how plugin documents are reloaded")


class ThumbnailRebuildStatus(BaseModel):
    running: bool = Field(description="Whether a rebuild is in progress")
    total: int = Field(description="Number of thumbnails the current or last rebuild set out to bake")
    done: int = Field(description="Number of thumbnails the rebuild has finished so far")
    remaining: int = Field(description="Number of thumbnails the rebuild still has to bake")
    built: int = Field(description="Number of thumbnails the rebuild has written in this run")
    failed: int = Field(description="Number of thumbnails the rebuild could not bake in this run")
    #: A run that stopped with work left. Without it, an abandoned run and a
    #: complete one both read as `running: False` with nothing else to separate
    #: them once a later run has replaced the counts.
    ended_short: bool = Field(
        default=False,
        description="True when the last run stopped before all of its work was done",
    )
    started_at: int | None = Field(
        default=None,
        description="When the current or last run started, in milliseconds since the Unix epoch; None when no run has started",
    )
    finished_at: int | None = Field(
        default=None,
        description="When the last run finished, in milliseconds since the Unix epoch; None while a run is in progress or before any run",
    )
    workers: int = Field(description="Number of thumbnails baked at once in this run")


class ThumbnailStatus(BaseModel):
    hidpi: bool = Field(description="Whether the second, double-size thumbnail set is made")
    #: How many bakes run at once, as the administrator entered it.
    workers: int = Field(default=4, description="Number of thumbnails baked at once, as set by the administrator")
    store_path: str | None = Field(description="Path of the separate file that holds the thumbnails; None when there is none")
    stored_bytes: int = Field(description="Total size in bytes of the stored thumbnail images")
    count_scale_1: int = Field(description="Number of stored thumbnails at scale 1")
    count_scale_2: int = Field(description="Number of stored thumbnails at scale 2")
    rebuild: ThumbnailRebuildStatus = Field(description="Progress of the current or last rebuild")
    submitted: int = Field(description="Thumbnail bakes submitted since this server process started")
    completed: int = Field(description="Thumbnail bakes completed since this server process started")
    failed: int = Field(description="Thumbnail bakes that failed since this server process started")
    skipped: int = Field(description="Thumbnail bakes skipped since this server process started")
    unavailable: int = Field(description="Thumbnail results that were unavailable since this server process started")
    note: str = Field(description="Explanation of how thumbnails are made and stored")


class OutputSaveStatus(BaseModel):
    enabled: bool = Field(description="Whether finished works are written to output_dir in the background")
    output_dir: str = Field(description="Folder that receives the saved output files")
    png_size: int = Field(description="Size of the saved PNG in pixels, either 1080 or 2160")
    workers: int = Field(description="Number of background threads that write output files; set at startup, not here")
    queue_limit: int = Field(description="Maximum number of saves waiting at once; a save that finds the queue full is skipped")
    submitted: int = Field(description="Saves submitted since this server process started")
    completed: int = Field(description="Saves completed since this server process started")
    failed: int = Field(description="Saves that failed since this server process started")
    skipped: int = Field(description="Saves skipped since this server process started, including those refused by a full queue")
    note: str = Field(description="Explanation of how the saved files relate to the database")


class LogRetentionStatus(BaseModel):
    enabled: bool = Field(description="Whether the server writes its own log files and applies this policy")
    retention_days: int = Field(description="Number of rotated log files kept before pruning: one file per day, week or month according to rotate")
    rotate: str = Field(description="How often the log file rotates: daily, weekly or monthly")
    compress: bool = Field(description="Whether rotated log files are gzip-compressed")
    # Where the application writes, and what is there now. These replace the
    # systemd drop-in and logrotate snippets the screen used to hand out: the
    # container distribution has neither, so the policy is executed in process
    # instead of being copied into the host OS (ledger I-167).
    log_dir: str = Field(description="Folder where the server writes its log files")
    files: list[str] = Field(description="Names of the log files currently in log_dir")
    note: str = Field(description="Explanation of how the log policy is applied")


class StageExecutionStatus(BaseModel):
    workers: int = Field(description="Number of model effects the shared pipeline runs at once")
    queue_limit: int = Field(
        description="Number of executions the pipeline keeps resident; a new start beyond it while all are busy is refused",
    )
    submitted: int = Field(description="Model effects submitted since this server process started")
    completed: int = Field(description="Model effects completed since this server process started")
    failed: int = Field(description="Model effects that failed since this server process started")
    timed_out: int = Field(description="Model effects that timed out since this server process started")
    rejected: int = Field(description="Starts refused because the pool was full, since this server process started")
    note: str = Field(description="Explanation of which pipeline steps run in this pool")


def _stage_execution_status() -> StageExecutionStatus:
    # Model effects run in the shared pipeline's worker pool. `queue_limit` is
    # the number of executions it keeps resident; a new start beyond it while
    # all are busy is refused and counted as rejected.
    from ...pipeline_runtime import host_limits

    limits = host_limits()
    return StageExecutionStatus(
        workers=limits["max_workers"],
        queue_limit=limits["max_retained_runs"],
        **_stage_execution_stats(),
        note="Model effects of the shared pipeline (catalog selection, sketch, Stage 1, hole completion) run in its worker pool. Each effect is sent once; the shared core decides any retry.",
    )


class ProviderRateLimitsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rpm: int = Field(
        default=0,
        ge=0,
        le=1_000_000_000,
        strict=True,
        description="Requests allowed per minute to this provider; 0 means no limit",
    )
    tpm: int = Field(
        default=0,
        ge=0,
        le=1_000_000_000,
        strict=True,
        description="Input tokens allowed per minute to this provider; 0 means no limit",
    )
    rpd: int = Field(
        default=0,
        ge=0,
        le=1_000_000_000,
        strict=True,
        description="Requests allowed per day to this provider; 0 means no limit",
    )


class ModelProviderPatch(BaseModel):
    label: str | None = Field(
        default=None,
        description="Display name of the provider; omit to leave it unchanged",
    )
    kind: str | None = Field(
        default=None,
        description="Wire protocol the provider speaks, such as openai_compatible, anthropic, gemini or mlx; any other value is stored as openai_compatible",
    )
    api_key_env: str | None = Field(
        default=None,
        description="Name of the environment variable that may supply the API key when none is stored",
    )
    base_url_env: str | None = Field(
        default=None,
        description="Name of the environment variable that seeds a built-in provider's default base URL; custom providers do not read it",
    )
    default_base_url: str | None = Field(
        default=None,
        description="Base URL used when the provider has no base URL of its own",
    )
    requires_api_key: bool | None = Field(
        default=None,
        description="Whether calls to this provider need an API key",
    )
    memo: str | None = Field(default=None, description="Free-text note the administrator keeps on the provider")
    rate_limits: ProviderRateLimitsPatch | None = Field(
        default=None,
        description="Request and token limits for this provider; only the keys sent are changed",
    )
    models: list[dict] = Field(
        default_factory=list,
        description="Models offered by the provider, each an object with an id and optionally a label and other metadata; replaces the stored list when sent",
    )
    active: bool | None = Field(
        default=None,
        description="Whether the provider is in use; set to false to hide it without deleting it",
    )
    delete: bool = Field(
        default=False,
        description="True removes a custom provider; a built-in provider is deactivated instead of removed",
    )
    base_url: str | None = Field(
        default=None,
        description="Base URL to call for this provider; when it is set and non-empty it overrides the default",
    )
    api_key: str | None = Field(
        default=None,
        description="API key to store for this provider; an empty value is ignored. The key is stored encrypted and shown only in masked form",
    )
    clear_api_key: bool = Field(
        default=False,
        description="True removes the stored API key; takes precedence over api_key in the same request",
    )
    enabled_models: dict[str, bool] = Field(
        default_factory=dict,
        description="Map of model id to whether users may use that model; a retired model or one that needs a subscription stays disabled whatever is sent",
    )


class ModelSettingsPatch(BaseModel):
    stage1_provider: str | None = Field(
        default=None,
        description="Provider used for Stage 1, the interpretation of the description",
    )
    stage1_model: str | None = Field(default=None, description="Model used for Stage 1, given as a model id")
    stage2_provider: str | None = Field(
        default=None,
        description="Provider used for Stage 2, which composes the score",
    )
    stage2_model: str | None = Field(default=None, description="Model used for Stage 2, given as a model id")
    providers: dict[str, ModelProviderPatch] = Field(
        default_factory=dict,
        description="Changes to model providers, keyed by provider id; only the providers sent are changed",
    )
    # Shared assessments of ChatGPT plan models, by model id; each entry replaces
    # that model's stored assessment. Publication stays personal (/api/me/chatgpt).
    chatgpt_models: list[dict] | None = Field(
        default=None,
        description="Shared assessments of ChatGPT plan models, by model id; each entry replaces that model's stored assessment, and null leaves them unchanged",
    )


class RenderConcurrencyStatus(BaseModel):
    server_limit: int = Field(
        description="Number of renders allowed at once in this process; requests beyond it are refused with 503",
    )
    client_limit: int = Field(
        description="Advisory limit on how many candidate renders the browser runs at once",
    )
    min_limit: int = Field(description="Smallest value accepted for either limit")
    max_limit: int = Field(description="Largest value accepted for either limit")
    note: str = Field(description="Explanation of how the two limits apply")


class RenderLimitsStatus(BaseModel):
    limits: dict[str, int] = Field(
        description="Limits in effect now, by name: the mark limits and max_generated_svg_mib, the SVG output ceiling in MiB",
    )
    defaults: dict[str, int] = Field(description="Default value of each limit, by name")
    groups: dict[str, list[str]] = Field(
        description="Names of the limits in each family: capability, legibility, safety and svg_output",
    )
    absolute_max: int = Field(description="Largest value any mark limit can be set to")
    field_bounds: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Minimum, maximum and step for each limit that has its own bounds, by name",
    )
    # Bytes of SVG one mark costs, by drawing tool. The panel turns the count on
    # the stepper into the weight a reader will actually open.
    bytes_per_mark: dict[str, int] = Field(
        description="Approximate SVG bytes one mark costs, by drawing tool: pen and brush_thick",
    )
    note: str = Field(description="Explanation of how the limits are recorded and rounded")


class DescriptionMeterStatus(BaseModel):
    japanese: bool = Field(description="日本語の記述の詩型を音数で判定する")
    english: bool = Field(description="英語の記述の形式を行数と音節で判定する")


class DbWriteLockStatus(BaseModel):
    locked: bool = Field(description="DB への書き込みを伴う要求をすべて断る（管理者の切り替えだけは通す）")


class JuxtapositionSettingsStatus(BaseModel):
    candidate_limit: int = Field(description="取り合わせで AI に渡す一文の上限。超えるときは要求ごとに無作為に選ぶ")
    min_limit: int = Field(description="Smallest value accepted for candidate_limit")
    max_limit: int = Field(description="Largest value accepted for candidate_limit")


class SettingsStatusResponse(BaseModel):
    database: DatabaseSettingsStatus = Field(description="Database connection and file information")
    db_backup: DbBackupStatus = Field(description="Automatic and manual database backups")
    plugins: PluginSettingsStatus = Field(description="Declarative DDL plugin documents")
    output_save: OutputSaveStatus = Field(description="Saving of output files")
    log_retention: LogRetentionStatus = Field(description="Log file retention policy and current log files")
    stage_execution: StageExecutionStatus = Field(description="Worker pool that runs the pipeline's model effects")
    render_concurrency: RenderConcurrencyStatus = Field(description="How many renders may run at once")
    render_limits: RenderLimitsStatus = Field(description="Limits on how many marks and how much SVG a work may draw")
    description_meter: DescriptionMeterStatus = Field(description="Which description languages the meter judges")
    db_write_lock: DbWriteLockStatus = Field(description="Whether writes to the database are locked")
    juxtaposition: JuxtapositionSettingsStatus = Field(description="How many sentences Juxtaposition offers the model")


@router.get("/api/settings/status", response_model=SettingsStatusResponse, summary="Read all settings status")
def api_settings_status() -> SettingsStatusResponse:
    """Return the database, backup, output, log, render and other settings in one response.

    Reading the settings does not write a backup. Only an administrator may call it.
    """
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
        log_retention=_log_retention_status(log_settings),
        render_concurrency=_render_concurrency_status(),
        render_limits=_render_limits_status(),
        stage_execution=_stage_execution_status(),
        description_meter=DescriptionMeterStatus(**_db.get_description_meter_settings()),
        db_write_lock=DbWriteLockStatus(**_db.get_db_write_lock()),
        juxtaposition=_juxtaposition_status(),
    )


@router.get("/api/settings/models", response_model=ModelSettingsResponse, summary="Read model settings")
def api_settings_models() -> ModelSettingsResponse:
    """Return the model provider catalog and the public model settings.

    Developer providers are included only while developer mode is on. Only an administrator may call it.
    """
    settings = _db.get_model_settings()
    developer_mode = _env_flag("INKU_DEVELOPER_MODE")
    return ModelSettingsResponse(
        catalog=model_provider_catalog(
            settings, include_disabled=True, include_developer=developer_mode
        ),
        settings=public_model_settings(settings, include_developer=developer_mode),
    )


@router.put("/api/settings/models", response_model=ModelSettingsResponse, summary="Update model settings")
def api_settings_update_models(
    body: ModelSettingsPatch,
) -> ModelSettingsResponse:
    """Apply a partial change to the model settings and return the saved catalog and settings.

    Only the providers and fields that are sent are changed. Only an administrator may call it.
    """
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


# Anthropic and Gemini hand their model lists out a page at a time (20 and 50
# by default). A model past the first page would read as withdrawn below, and a
# withdrawn model is marked EOL and switched off, so every page is read -- the
# largest page each API allows, so one request is the usual case. The page cap
# only stops a provider that never says it is done; a list cut short there
# would retire real models, so it is an error rather than a partial answer.
_MODEL_LIST_PAGE_SIZE = 1000
_MODEL_LIST_PAGE_LIMIT = 20


def _get_model_list_page(url: str, headers: dict[str, str]) -> object:
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ValueError(f"model list fetch failed: {exc}") from exc


def _fetch_paged_model_list(
    base: str,
    headers: dict[str, str],
    *,
    items_key: str,
    first_query: dict[str, str],
    next_query,
) -> dict:
    """Read every page of a paginated model list into one `{items_key: [...]}`.

    `next_query(page)` answers the query for the page after `page`, or None when
    `page` was the last one.
    """
    collected: list = []
    query = first_query
    for _ in range(_MODEL_LIST_PAGE_LIMIT):
        page = _get_model_list_page(f"{base}?{urllib.parse.urlencode(query)}", headers)
        if not isinstance(page, dict) or not isinstance(page.get(items_key), list):
            raise ValueError("model list response did not contain models")
        collected.extend(page[items_key])
        following = next_query(page)
        if following is None:
            return {items_key: collected}
        query = {**first_query, **following}
    raise ValueError("model list response did not end")


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
        if conn.get("api_key"):
            headers["x-api-key"] = str(conn["api_key"])
        headers["anthropic-version"] = "2023-06-01"
        payload = _fetch_paged_model_list(
            f"{base_url}/v1/models",
            headers,
            items_key="data",
            first_query={"limit": str(_MODEL_LIST_PAGE_SIZE)},
            next_query=lambda page: (
                {"after_id": str(page["last_id"])}
                if page.get("has_more") and page.get("last_id")
                else None
            ),
        )
    elif conn.get("kind") == "gemini":
        # The key rides in the header the pipeline transport already uses. In
        # the query string it would be written into every proxy and access log
        # the URL passes through.
        if conn.get("api_key"):
            headers["x-goog-api-key"] = str(conn["api_key"])
        payload = _fetch_paged_model_list(
            f"{base_url}/v1beta/models",
            headers,
            items_key="models",
            first_query={"pageSize": str(_MODEL_LIST_PAGE_SIZE)},
            next_query=lambda page: (
                {"pageToken": str(page["nextPageToken"])} if page.get("nextPageToken") else None
            ),
        )
    else:
        if conn.get("api_key"):
            headers["Authorization"] = f"Bearer {conn['api_key']}"
        payload = _get_model_list_page(f"{base_url}/models", headers)

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


# Ollama Cloud hands its model list, and each model's details, to anyone: both
# answer without a key, so neither says which models this account may call.
# What does say it is the service's answer to a call: 403 for a model the
# account's plan does not reach (measured 2026-07-29), and 410 from /api/show
# for a retired one (qwen3.5:397b, 2026-09-28). Each model is therefore asked,
# once per fetch, with the smallest call there is. Anything else -- a busy
# service, a timeout, a key the service refuses -- settles nothing, and the
# mark the model already carries stays.
_ACCESS_PROBE_PROVIDERS = frozenset({"ollama-cloud"})
_ACCESS_PROBE_TIMEOUT_SECONDS = 20
# The service refuses by concurrency, and two is its limit (model_settings).
_ACCESS_PROBE_WORKERS = 2
_RETIRED_AT = re.compile(r"retired at (\d{4}-\d{2}-\d{2})")


def _post_for_status(url: str, headers: dict[str, str], body: dict) -> tuple[int | None, str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_ACCESS_PROBE_TIMEOUT_SECONDS) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read(2048).decode("utf-8", "replace")
        except OSError:
            text = ""
        return exc.code, text
    except (OSError, urllib.error.URLError):
        return None, ""


def _probe_model_access(base_url: str, api_key: str, model_id: str) -> dict:
    """What one model is to this key: {"retired": date}, {"subscription": bool}, or {} when unsettled."""
    origin = base_url.rstrip("/").removesuffix("/v1")
    status, text = _post_for_status(f"{origin}/api/show", {}, {"model": model_id})
    if status == 410:
        found = _RETIRED_AT.search(text)
        return {"retired": found.group(1) if found else datetime.now(timezone.utc).date().isoformat()}
    if not api_key:
        return {}
    status, _ = _post_for_status(
        f"{base_url.rstrip('/')}/chat/completions",
        {"Authorization": f"Bearer {api_key}"},
        {"model": model_id, "messages": [{"role": "user", "content": "."}], "max_tokens": 1},
    )
    # A model outside the Free plan answers 402 (2026-10-13), one the account
    # cannot reach yet 403; neither can be called on this key.
    if status in (402, 403):
        return {"subscription": True}
    if status == 200:
        return {"subscription": False}
    return {}


def _apply_model_access(provider_id: str, settings: dict, models: list[dict]) -> None:
    """Mark the models this key cannot call, in place, for a provider that must be asked."""
    if provider_id not in _ACCESS_PROBE_PROVIDERS:
        return
    conn = connection_for(provider_id, settings)
    base_url = str(conn["base_url"])
    api_key = str(conn.get("api_key") or "")
    asked = [model for model in models if not model.get("eol")]
    with ThreadPoolExecutor(max_workers=_ACCESS_PROBE_WORKERS) as pool:
        answers = list(pool.map(lambda model: _probe_model_access(base_url, api_key, str(model["id"])), asked))
    for model, answer in zip(asked, answers):
        if "retired" in answer:
            model["eol"] = True
            model["eol_date"] = answer["retired"]
        elif answer.get("subscription") is True:
            model["requires_subscription"] = True
        elif answer.get("subscription") is False:
            # The account reaches it now, whatever the builtin catalog assumed.
            model.pop("requires_subscription", None)


@router.post(
    "/api/settings/models/{provider_id}/fetch-models",
    response_model=ModelSettingsResponse,
    summary="Fetch a provider's model list",
)
def api_settings_fetch_provider_models(
    provider_id: str = Path(description="Id of the model provider whose model list is fetched"),
) -> ModelSettingsResponse:
    """Fetch the model list of one provider and save it.

    A model the provider no longer lists is kept as retired (EOL) rather than deleted.
    Returns 502 when the provider is unknown, its list cannot be read, or the list is empty. Only an administrator may call it.
    """
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
        # 有料プラン限定の印は提供元の一覧に現れない (一覧には載るが叩くと 402 か
        # 403 が返る)。取得のたびに消えては困るので、EOL と違って再提供で外さない。
        "requires_subscription",
    )
    catalog = catalog_models(provider_id)
    for model in models:
        previous = previous_models.get(str(model["id"]))
        if not previous:
            # A model this installation meets for the first time takes what the catalog
            # (model_catalog.json) knows about it. The provider names it, and listing it
            # means it is offered, so the catalog's end-of-life mark is not taken.
            known = catalog.get(str(model["id"]))
            if known:
                model.update({key: value for key, value in known.items() if key not in ("id", "label", "eol", "eol_date")})
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
    _apply_model_access(provider_id, current, models)

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


@router.put("/api/settings/db-backup", response_model=DbBackupStatus, summary="Update database backup schedule")
def api_settings_update_db_backup(
    body: DbBackupSettingsBody,
) -> DbBackupStatus:
    """Save the automatic backup interval, generation count and time of day, and return the backup status.

    Out-of-range values are refused with 422 by request validation. Only an administrator may call it.
    """
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


@router.put("/api/settings/output-save", response_model=OutputSaveStatus, summary="Update output save settings")
def api_settings_update_output_save(
    body: OutputSaveSettingsBody,
) -> OutputSaveStatus:
    """Save whether output files are written, their folder and PNG size, and return the output save status.

    Returns 400 for an empty or relative folder or an unsupported PNG size. Only an administrator may call it.
    """
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


def _thumbnail_status() -> "ThumbnailStatus":
    """One builder for every route that reports thumbnails, so none can drift."""
    settings = _db.get_thumbnail_settings()
    counts = _thumbs_db.counts_by_scale()
    return ThumbnailStatus(
        hidpi=bool(settings["hidpi"]),
        workers=int(settings["workers"]),
        store_path=_thumbs_db.thumbs_db_path(),
        stored_bytes=_thumbs_db.stored_bytes(),
        count_scale_1=counts.get(1, 0),
        count_scale_2=counts.get(2, 0),
        rebuild=ThumbnailRebuildStatus(**_thumbnails.rebuild_progress()),
        **_thumbnail_stats(),
        note=(
            "Thumbnails are rasterized from each work's stored SVG; the engine is not run "
            "and the picture does not change. The store is a separate file and may be "
            "deleted at any time -- the listing falls back to the SVG until it is rebuilt."
        ),
    )


@router.get("/api/settings/thumbnails", response_model=ThumbnailStatus, summary="Read thumbnail settings")
def api_settings_thumbnails() -> "ThumbnailStatus":
    """Return the thumbnail settings, the size of the thumbnail store and the rebuild progress.

    Only an administrator may call it.
    """
    return _thumbnail_status()


@router.put("/api/settings/thumbnails", response_model=ThumbnailStatus, summary="Update thumbnail settings")
def api_settings_update_thumbnails(
    body: ThumbnailSettingsBody,
) -> "ThumbnailStatus":
    """Save the second-size switch and the number of thumbnails baked at once.

    Turning it off deletes the scale-2 rows and nothing else: scale 1 is what
    the listing draws from, and losing it would blank every thumbnail. The
    confirmation for the deletion belongs to the client, which is where the
    person is.
    """
    was_hidpi = bool(_db.get_thumbnail_settings()["hidpi"])
    settings = _db.update_thumbnail_settings(body.hidpi, body.workers)
    if was_hidpi and not settings["hidpi"]:
        removed = _thumbnails.drop_hidpi()
        _logger.info("HiDPI thumbnails turned off; removed %d scale-2 thumbnails", removed)
    return _thumbnail_status()


@router.get("/api/settings/thumbnails/rebuild", response_model=ThumbnailStatus, summary="Read thumbnail rebuild progress")
def api_settings_thumbnail_rebuild_status() -> "ThumbnailStatus":
    """Return the thumbnail status, including the progress of the current or last rebuild.

    Only an administrator may call it.
    """
    return _thumbnail_status()


@router.post("/api/settings/thumbnails/rebuild", response_model=ThumbnailStatus, summary="Start a thumbnail rebuild")
def api_settings_thumbnail_rebuild() -> "ThumbnailStatus":
    """Bake what is missing or stale, in the background, while serving.

    Works that already have a thumbnail keep serving the one they have until
    their new one is written, so running this does not blank the listing.
    """
    _thumbnails.start_rebuild()
    return _thumbnail_status()


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


def _render_limits_status() -> RenderLimitsStatus:
    return RenderLimitsStatus(
        limits=_db.get_render_limit_settings(),
        defaults=normalize_render_limit_settings(None),
        groups={**{name: list(fields) for name, fields in LIMIT_GROUPS},
                "svg_output": [SVG_LIMIT_FIELD]},
        absolute_max=LIMIT_ABSOLUTE_MAX,
        field_bounds={SVG_LIMIT_FIELD: {"min": SVG_LIMIT_MIN_MIB, "max": SVG_LIMIT_MAX_MIB, "step": 1}},
        bytes_per_mark=dict(BYTES_PER_MARK),
        note=(
            "Mark limits are recorded on each work (history.render_limits). The SVG output "
            "ceiling is separate installation safety policy applied to fresh renders, not "
            "stored-display retrieval or the work's identity. "
            "Values that contradict each other are rounded down, not rejected; the stored set "
            "is what comes back."
        ),
    )


class RenderLimitsBody(BaseModel):
    # Every field optional: the panel sends what it changed, and the stored set
    # is merged and re-normalized, so a partial update cannot drop the rest.
    model_config = ConfigDict(extra="forbid")

    max_expanded_primitives: int | None = Field(
        default=None,
        description="Largest number of marks one work may draw in total",
    )
    max_expanded_per_instruction: int | None = Field(
        default=None,
        description="Largest number of marks one instruction may draw; capped at max_expanded_primitives",
    )
    max_instructions: int | None = Field(
        default=None,
        description="Largest number of instructions one work may contain",
    )
    literal_count_threshold: int | None = Field(
        default=None,
        description="Largest stated count that is drawn mark by mark; above it the group is shown as a band",
    )
    represented_count_min: int | None = Field(
        default=None,
        description="Lower bound on the number of marks drawn for a count shown as a band; cannot exceed represented_count_max",
    )
    represented_count_max: int | None = Field(
        default=None,
        description="Upper bound on the number of marks drawn for a count shown as a band; capped at literal_count_threshold",
    )
    ddl_count_max: int | None = Field(
        default=None,
        description="Ceiling applied to a count written in the description's text",
    )
    ddl_count_max_grid: int | None = Field(
        default=None,
        description="Ceiling applied to a count the description asks for as a literal grid",
    )
    schema_count_max: int | None = Field(
        default=None,
        description="Ceiling on the count the model may declare in its own output",
    )
    max_generated_svg_mib: StrictInt | None = Field(
        default=None,
        description="Largest SVG output a fresh render may produce, in MiB, from 1 to 32; a value outside that range is clamped to the nearest end; it does not change stored works",
    )
    reset_to_defaults: bool = Field(
        default=False,
        description="True restores every limit to its default and ignores the other fields in the same request",
    )


@router.put("/api/settings/limits", response_model=RenderLimitsStatus, summary="Update render limits")
def api_settings_update_limits(
    body: RenderLimitsBody,
) -> RenderLimitsStatus:
    """Apply a partial change to the render limits, or reset them to their defaults, and return the effective limits.

    Values that contradict each other are rounded rather than refused. Only an administrator may call it.
    """
    if body.reset_to_defaults:
        requested = normalize_render_limit_settings(None)
    else:
        requested = {
            key: value
            for key, value in body.model_dump(exclude={"reset_to_defaults"}).items()
            if value is not None
        }
    _db.update_render_limit_settings(requested)
    return _render_limits_status()


class RenderConcurrencyBody(BaseModel):
    server_limit: int = Field(
        description="Number of renders allowed at once in this process, from 1 to 16",
    )
    client_limit: int = Field(
        description="Advisory limit on how many candidate renders the browser runs at once, from 1 to 16",
    )


@router.put("/api/settings/render-concurrency", response_model=RenderConcurrencyStatus, summary="Update render concurrency")
def api_settings_update_render_concurrency(
    body: RenderConcurrencyBody,
) -> RenderConcurrencyStatus:
    """Save the server and client render limits and apply the server limit to renders that start from now on.

    Returns 400 when a limit is outside its range. Only an administrator may call it.
    """
    try:
        settings = _db.update_render_concurrency_settings(body.server_limit, body.client_limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # New limit applies to renders acquired from here on; running renders finish.
    _render_slots.set_limit(int(settings["server_limit"]))
    return _render_concurrency_status()


class DescriptionMeterBody(BaseModel):
    japanese: bool = Field(description="Whether the meter counts the sounds of a Japanese description")
    english: bool = Field(description="Whether the meter checks the line and syllable form of an English description")


@router.put("/api/settings/description-meter", response_model=DescriptionMeterStatus, summary="Update description meter switches")
def api_settings_update_description_meter(body: DescriptionMeterBody) -> DescriptionMeterStatus:
    """Save which description languages the meter judges and return the saved switches.

    Only an administrator may call it.
    """
    return DescriptionMeterStatus(**_db.update_description_meter_settings(body.japanese, body.english))


def _juxtaposition_status() -> JuxtapositionSettingsStatus:
    return JuxtapositionSettingsStatus(
        **_db.get_juxtaposition_settings(),
        min_limit=_db.JUXTAPOSITION_CANDIDATE_MIN,
        max_limit=_db.JUXTAPOSITION_CANDIDATE_MAX,
    )


class JuxtapositionSettingsBody(BaseModel):
    candidate_limit: StrictInt = Field(
        description="Number of sentences from other works offered to the model per request, within the accepted range; a random subset is taken when there are more",
    )


@router.put("/api/settings/juxtaposition", response_model=JuxtapositionSettingsStatus, summary="Update juxtaposition candidate limit")
def api_settings_update_juxtaposition(body: JuxtapositionSettingsBody) -> JuxtapositionSettingsStatus:
    """Save how many sentences from other works a juxtaposition offers the model, and return the status.

    Returns 400 when the value is outside the accepted range. Only an administrator may call it.
    """
    try:
        _db.update_juxtaposition_settings(body.candidate_limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _juxtaposition_status()


class DbWriteLockBody(BaseModel):
    locked: bool = Field(
        description="True refuses every POST, PUT, PATCH and DELETE request with 503, whether or not it writes; this switch, sign-in and sign-out still pass",
    )


@router.put("/api/settings/db-write-lock", response_model=DbWriteLockStatus, summary="Turn the database write lock on or off")
def api_settings_update_db_write_lock(body: DbWriteLockBody) -> DbWriteLockStatus:
    """Lock or unlock writes to the database and return the new state.

    While locked, every POST, PUT, PATCH and DELETE request is refused with 503, whether or not it writes; this switch, sign-in and sign-out still pass.
    Only an administrator may call it.
    """
    return DbWriteLockStatus(**_db.update_db_write_lock(body.locked))


@router.put("/api/settings/log-retention", response_model=LogRetentionStatus, summary="Update log retention policy")
def api_settings_update_log_retention(
    body: LogRetentionSettingsBody,
) -> LogRetentionStatus:
    """Save the log retention policy, apply it to the running server at once, and return the log status.

    Returns 400 for an out-of-range value or an unsupported rotation. Only an administrator may call it.
    """
    try:
        log_settings = _db.update_log_retention_settings(
            body.enabled,
            body.retention_days,
            body.rotate,
            body.compress,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Apply it now. The screen used to end here with a file for the operator to
    # copy, which meant the stored policy and the running one could disagree
    # forever -- and on pentala they did, for months.
    _logging_setup.configure_logging(log_settings)
    return _log_retention_status(log_settings)


@router.post("/api/settings/db-backup/run", response_model=DbBackupResult, summary="Make a manual database backup")
def api_settings_run_db_backup() -> DbBackupResult:
    """Copy the SQLite database to a new manual backup and return the details of the copy.

    Returns 400 when a copy cannot be made for this database, and 409 when the copy cannot be
    written or verified, for example because a copy with the same name already exists.
    Only an administrator may call it.
    """
    try:
        result = _db.create_db_backup(manual=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SQLiteSnapshotError as e:
        # A copy is named to the second, so a second press within it finds its
        # name taken; the copy can also fail to be made or verified. Each says
        # which in its message. Unhandled, both came back as a bare 500.
        _logger.warning("manual DB backup was not written: %s", e)
        raise HTTPException(status_code=409, detail=str(e)) from e
    return DbBackupResult(**result)


class DbBackupRestoreResult(BaseModel):
    restored: str = Field(description="File name of the copy written into the database")
    kind: Literal["auto", "manual"] = Field(description="Folder of the restored copy, auto or manual")
    safety_backup: str = Field(
        description="File name of the manual backup of the contents the restore replaced, made just before it",
    )


_BackupKind = Annotated[Literal["auto", "manual"], Path(description="Folder of the copy, auto or manual")]
_BackupName = Annotated[str, Path(max_length=64, description="File name of the copy, as the backup list gives it")]


@router.delete("/api/settings/db-backup/{kind}/{name}", response_model=DbBackupStatus, summary="Delete a database backup")
def api_settings_delete_db_backup(kind: _BackupKind, name: _BackupName) -> DbBackupStatus:
    """Delete one retained backup and return the backup status.

    Returns 404 when the name is not a retained copy in that folder. Only an administrator may call it.
    """
    try:
        _db.delete_db_backup(kind, name)
    except BackupNotFoundError as e:
        raise HTTPException(status_code=404, detail="DB backup not found") from e
    return DbBackupStatus(**_db.db_backup_status())


@router.post("/api/settings/db-backup/{kind}/{name}/restore", response_model=DbBackupRestoreResult,
             summary="Restore the database from a backup")
def api_settings_restore_db_backup(kind: _BackupKind, name: _BackupName) -> DbBackupRestoreResult:
    """Replace the whole database with one retained backup.

    The current contents are first saved as a new manual backup, and the restore does not start
    without it. Works, settings and sign-ins saved after the backup was made are replaced; a
    sign-in the backup does not hold ends. Other writes are refused with 503 while it runs.
    Returns 404 when the name is not a retained copy, 409 when the copy fails its integrity check,
    its tables or migration registry differ from the running database, or the safety backup
    cannot be written, and 400 when this database cannot be restored or another restore is
    running. Only an administrator may call it.
    """
    try:
        result = _db.restore_db_backup(kind, name)
    except BackupNotFoundError as e:
        raise HTTPException(status_code=404, detail="DB backup not found") from e
    except BackupSchemaMismatchError as e:
        raise HTTPException(status_code=409, detail="DB backup schema differs from the running database") from e
    except SQLiteSnapshotError as e:
        _logger.warning("DB restore did not run: %s", e)
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _logger.warning("DB restored from %s/%s; previous contents saved as %s", kind, name, result["safety_backup"])
    return DbBackupRestoreResult(**result)


class SingleUserCandidate(BaseModel):
    id: str = Field(description="Id of the account")
    username: str = Field(description="Name of the account")


class SingleUserStatus(BaseModel):
    enabled: bool = Field(description="Whether single-user mode is on; the pinned account is read only while it is on")
    user_id: str | None = Field(
        default=None,
        description="Id of the account the server opens as automatically; None when no account is pinned",
    )
    username: str | None = Field(default=None, description="Name of the pinned account; None when no account is pinned")
    eligible: list[SingleUserCandidate] = Field(
        default_factory=list,
        description="Accounts that may be chosen, which are the accounts that hold the admins permission group",
    )


class SingleUserBody(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Id of the account to hand the server to; it must hold the admins permission group",
    )


@router.get("/api/settings/single-user", response_model=SingleUserStatus, summary="Read single-user setting")
def api_settings_single_user() -> SingleUserStatus:
    """Return whether single-user mode is on, which account the server opens as, and the accounts that may be chosen.

    Only an administrator may call it.
    """
    return SingleUserStatus(**_db.single_user_pin_status())


@router.put("/api/settings/single-user", response_model=SingleUserStatus, summary="Hand the server to another account")
def api_settings_set_single_user(
    body: SingleUserBody
) -> SingleUserStatus:
    """Hand the server to a different account, from the next automatic login on.

    Returns 400 when single-user mode is off, the account does not exist, or it
    does not hold the admins permission group.
    """
    try:
        return SingleUserStatus(**_db.set_single_user_pin(body.user_id))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
