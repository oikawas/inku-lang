"""FastAPI endpoints for inku-server.

POST /api/compose : 正規化DDL (or 生入力) → JSON Score + SVG
GET  /health      : liveness
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Literal

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .animation_export import build_animation
from .autonomous_refine import ALLOWED_KINDS as AUTONOMOUS_REFINE_KINDS, vision_refine_advice
from .feature_analysis import composition_distance
from .okugaki import DEFAULT_MODEL as DEFAULT_OKUGAKI_MODEL, generate_okugaki
from .color_catalogs import color_catalog_ids, color_catalogs, get_color_catalog, render_color_map_for_catalog
from .coerce import coerce_score, count_hint_from_ddl, ensure_renderable_score
from .composer import _finalize_score, compose
from .ddl_expander import FOCUS_IDS, VARIATION_AMPLITUDES
from .interpreter import _sanitize_placement_words, interpret_detail
from .layer_versions import DDL_ENGINE_VERSION, DDL_VERSION
from .languages import (
    SUPPORTED_INSTRUCTION_LANGS,
    expand_intermediate_for_lang,
    normalize_instruction_lang,
    resolve_instruction_lang,
    stage_prompts_for_lang,
)
from .plugins import (
    DOCUMENT_PLUGIN_MANAGER,
    PluginFormatError,
    canvas_aspect_ids,
    canvas_aspect_ratio_for_aspect,
    normalize_canvas_aspect_id,
    plugin_status_items,
    validate_plugin_document,
)
from .reference import build_reference, render_markdown
from .saijiki import display_categories
from .renderer import SVG_PROFILES, new_render_seed
from .carriage import carriage_warnings as _carriage_warnings
from .render_engines import current_render_engine
from .security import ConcurrencyLimitMiddleware, RequestBodyLimitMiddleware, SlidingWindowRateLimiter
from .schema import CanvasSpec, Score
from .model_settings import (
    MODEL_METADATA_KEYS,
    connection_for,
    model_provider_catalog,
    normalize_model_settings,
    provider_for_model,
    public_model_settings,
    split_model_ref,
    update_model_settings,
)
from . import db as _db

def _app_version() -> str:
    """Report the installed distribution version so pyproject.toml stays the single source."""
    try:
        return importlib.metadata.version("inku-server")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"


_APP_VERSION = _app_version()

# The automatic DB backup used to run only inside GET /api/settings/status, so
# it fired whenever an admin happened to open the settings — never at a stated
# time. The loop below is what lets the configured hour and minute mean what
# they say. Set INKU_DB_BACKUP_SCHEDULER=0 to keep it out of a process (tests
# that drive the app without its lifespan never start it in the first place).
_DB_BACKUP_SCHEDULER_TICK_SECONDS = 60


async def _db_backup_scheduler_loop() -> None:
    """Ask once a minute whether the backup is due; the due check decides.

    A coarse tick is deliberate: a missed or late wake-up delays a copy, it
    never skips one, because the schedule is derived from the last backup's
    timestamp rather than from this loop's own cadence.
    """
    while True:
        try:
            result = await asyncio.to_thread(_db.ensure_scheduled_db_backup)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("scheduled DB backup failed; will retry on the next tick")
        else:
            if result is not None:
                _logger.info("scheduled DB backup written to %s", result["path"])
        await asyncio.sleep(_DB_BACKUP_SCHEDULER_TICK_SECONDS)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    task: asyncio.Task | None = None
    if os.getenv("INKU_DB_BACKUP_SCHEDULER", "1") != "0":
        task = asyncio.create_task(_db_backup_scheduler_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="inku-server", version=_APP_VERSION, lifespan=_lifespan)

_db.init_db()

# ── 出力ファイル保存 ────────────────────────────────────────────────────────────
# DB の履歴レコードを正本とし、ここで作る SVG/JSON/PNG 等は再生成可能な副産物として扱う。
_DEFAULT_OUTPUT_DIR = Path.home() / ".local" / "share" / "inku" / "outputs"
_OUTPUT_DIR = Path(os.getenv("INKU_OUTPUT_DIR", str(_DEFAULT_OUTPUT_DIR)))
_OUTPUT_PNG_SIZE = int(os.getenv("INKU_OUTPUT_PNG_SIZE", "2160"))
_SAVE_WORKERS = max(1, int(os.getenv("INKU_OUTPUT_SAVE_WORKERS", "2")))
_SAVE_QUEUE_LIMIT = max(_SAVE_WORKERS, int(os.getenv("INKU_OUTPUT_SAVE_QUEUE_LIMIT", "32")))
_save_executor = ThreadPoolExecutor(max_workers=_SAVE_WORKERS, thread_name_prefix="inku-save")
_save_slots = BoundedSemaphore(_SAVE_QUEUE_LIMIT)
_save_stats_lock = Lock()
_save_stats = {
    "submitted": 0,
    "completed": 0,
    "failed": 0,
    "skipped": 0,
}
_STAGE_WORKERS = max(1, int(os.getenv("INKU_STAGE_WORKERS", "4")))
_STAGE_QUEUE_LIMIT = max(_STAGE_WORKERS, int(os.getenv("INKU_STAGE_QUEUE_LIMIT", str(_STAGE_WORKERS * 2))))
_stage_executor = ThreadPoolExecutor(max_workers=_STAGE_WORKERS, thread_name_prefix="inku-stage")
_stage_slots = BoundedSemaphore(_STAGE_QUEUE_LIMIT)
_stage_stats_lock = Lock()
_stage_stats = {
    "submitted": 0,
    "completed": 0,
    "failed": 0,
    "timed_out": 0,
    "rejected": 0,
}
class _RenderCapacity:
    """描画スロット。上限は管理者設定で実行中に変更できるため、固定長の
    BoundedSemaphore ではなく上限と使用数を明示的に持つ。acquire は待たない
    (満杯なら即 False) 従来どおりの挙動。"""

    def __init__(self, limit: int) -> None:
        self._lock = Lock()
        self._limit = max(1, limit)
        self._active = 0

    @property
    def limit(self) -> int:
        with self._lock:
            return self._limit

    def set_limit(self, limit: int) -> None:
        with self._lock:
            self._limit = max(1, limit)

    def acquire(self) -> bool:
        with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)


_render_slots = _RenderCapacity(max(1, int(os.getenv("INKU_RENDER_CONCURRENCY", "2"))))
_logger = logging.getLogger(__name__)


def _apply_stored_render_concurrency() -> None:
    """起動時に DB の設定を反映する。env は DB 未設定時の初期値でしかない。"""
    try:
        settings = _db.get_render_concurrency_settings()
    except Exception:
        _logger.warning("render concurrency settings unavailable; keeping environment default")
        return
    _render_slots.set_limit(int(settings["server_limit"]))


_apply_stored_render_concurrency()


def _log_rasterizer_backend() -> None:
    """Announce the PNG backend at boot.

    resvg is the only one; there is no fallback to notice having taken. Logged once
    per process rather than per rasterization.
    """
    from inku_analysis.rasterizer import rasterizer_info

    info = rasterizer_info()
    if not info:
        _logger.warning("resvg is not installed; PNG output is disabled")
    else:
        _logger.info("PNG rasterizer: %s %s", info["backend"], info.get("version", "?"))


_log_rasterizer_backend()

_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
_SESSION_COOKIE_NAME = "inku_session"
_SESSION_COOKIE_MAX_AGE = int(os.getenv("INKU_SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))
_SESSION_COOKIE_SECURE = os.getenv("INKU_SESSION_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes"}
_MAX_REQUEST_BODY_BYTES = max(1024, int(os.getenv("INKU_MAX_REQUEST_BODY_BYTES", str(16 * 1024 * 1024))))
_MAX_CONCURRENT_REQUESTS = max(1, int(os.getenv("INKU_MAX_CONCURRENT_REQUESTS", "64")))
_LOGIN_RATE_ATTEMPTS = max(1, int(os.getenv("INKU_LOGIN_RATE_ATTEMPTS", "10")))
_LOGIN_RATE_WINDOW_SECONDS = max(1, int(os.getenv("INKU_LOGIN_RATE_WINDOW_SECONDS", "60")))
_login_rate_limiter = SlidingWindowRateLimiter(
    attempts=_LOGIN_RATE_ATTEMPTS,
    window_seconds=_LOGIN_RATE_WINDOW_SECONDS,
)
_SRGB_COLOR_PROFILE = {
    "id": "srgb",
    "name": "sRGB IEC61966-2.1",
    "standard": "IEC 61966-2-1:1999",
}


def _provider_failure_detail(operation: str, exc: BaseException | None) -> dict | None:
    """LLM プロバイダ由来の失敗を種別に分けて返す (v1.98)。

    種別が分かるものだけを構造化する。判別できない失敗は None を返し、
    従来どおり `<operation> failed` として扱う。原文メッセージは常に添える。
    """
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        status = getattr(exc, "status_code", None)
        if status is None:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
        if isinstance(status, int):
            if status == 410:
                code = "model_gone"
            elif status in (401, 403):
                code = "provider_auth"
            elif status == 429:
                code = "provider_rate_limit"
            else:
                code = "provider_error"
            return {
                "code": code,
                "stage": operation,
                "provider_status": status,
                "message": str(exc),
            }
        exc = exc.__cause__ or exc.__context__
    return None


def _stage_http_error(operation: str, status_code: int) -> HTTPException:
    """種別が分かるプロバイダ失敗は構造化し、それ以外は従来の扱いに落とす。"""
    _, exc_value, _ = sys.exc_info()
    detail = _provider_failure_detail(operation, exc_value)
    if detail is not None:
        _logger.warning("%s failed: %s %s", operation, detail["provider_status"], detail["message"])
        return HTTPException(status_code=status_code, detail=detail)
    return _unexpected_http_error(operation, status_code)


def _unexpected_http_error(operation: str, status_code: int) -> HTTPException:
    _logger.exception("%s failed", operation)
    detail = f"{operation} failed"
    if os.getenv("INKU_ENV") == "development":
        import sys
        import traceback
        exc_type, exc_value, _ = sys.exc_info()
        if exc_value:
            detail = f"{operation} failed: {exc_type.__name__}: {exc_value}\n{traceback.format_exc()}"
    return HTTPException(status_code=status_code, detail=detail)


@contextmanager
def _render_capacity():
    if not _render_slots.acquire():
        raise HTTPException(status_code=503, detail="render capacity is full", headers={"Retry-After": "1"})
    try:
        yield
    finally:
        _render_slots.release()


def _normalize_instruction_lang(value: str | None, *, default: str = "ja") -> str:
    try:
        return normalize_instruction_lang(value, default=default)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unsupported instruction language: {value}")


def _resolve_instruction_lang(text: str, requested: str, *, ui_lang: str | None = None) -> str:
    fallback = ui_lang if ui_lang in SUPPORTED_INSTRUCTION_LANGS else "ja"
    return resolve_instruction_lang(text, requested, fallback=fallback)


def _normalize_ui_lang(value: str | None) -> str | None:
    lang = (value or "").strip().lower()
    if not lang:
        return None
    return lang[:32]


def _build_number() -> str | None:
    path = Path(__file__).resolve().parents[3] / "web" / "BUILD_NUMBER"
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _build_date() -> str | None:
    path = Path(__file__).resolve().parents[3] / "web" / "BUILD_NUMBER"
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def _startup_banner(*, service_name: str, service_kind: str, emoji: str) -> str:
    build_number = _build_number() or "unknown"
    build_date = _build_date() or "unknown"
    host = os.getenv("INKU_LISTEN_HOST", "0.0.0.0")
    port = os.getenv("INKU_LISTEN_PORT", os.getenv("INKU_SERVER_PORT", "8100"))
    engine = current_render_engine()
    border = "=" * 60
    return "\n".join(
        [
            border,
            f"{emoji} {service_name} starting",
            f"service: {service_kind}",
            f"mode: {os.getenv('INKU_ENV', os.getenv('ENVIRONMENT', 'development'))}",
            f"listen: {host}:{port}",
            f"runtime: Python {platform.python_version()} / {platform.system()} {platform.machine()}",
            f"render engine: {engine.id} v{engine.version}",
            "log: journal + /var/log/inku/inku-api.log",
            f"version: {_APP_VERSION}",
            f"build: {build_number} ({build_date})",
            border,
        ]
    )


def _log_startup_banner() -> None:
    banner = _startup_banner(service_name="inku-api", service_kind="FastAPI rendering API", emoji="🧠 ⚙️ 🔌 🖌️ 🚀")
    print(banner, flush=True)
    _logger.info(banner)


_log_startup_banner()


def _is_qualified_model_id(model: str) -> bool:
    provider, _ = split_model_ref(model, _db.get_model_settings())
    return provider is not None


def _resolved_stage_model(model: str | None, actor: dict | None, *, stage: str) -> str:
    settings = (actor or {}).get("model_settings") or {}
    provider_key = "stage1_provider" if stage == "stage1" else "stage2_provider"
    model_key = "stage1_model" if stage == "stage1" else "stage2_model"
    default_model = "google/gemma-4-31b-it"
    provider = str(settings.get(provider_key, "nvidia") or "nvidia")
    model_id = str(settings.get(model_key, default_model) or default_model)
    if model:
        requested = str(model).strip()
        if _is_qualified_model_id(requested):
            return requested
        if requested == model_id:
            return f"{provider}:{requested}"
        return requested
    return model_id if _is_qualified_model_id(model_id) else f"{provider}:{model_id}"


def _resolved_vision_model(model: str | None, actor: dict | None = None) -> str:
    settings = (actor or {}).get("model_settings") or {}
    provider = str(settings.get("vision_provider", "nvidia") or "nvidia")
    model_id = str(settings.get("vision_model", DEFAULT_OKUGAKI_MODEL) or DEFAULT_OKUGAKI_MODEL)
    if model:
        requested = str(model).strip()
        if _is_qualified_model_id(requested):
            return requested
        if requested == model_id:
            return f"{provider}:{requested}"
        return requested
    return model_id if _is_qualified_model_id(model_id) else f"{provider}:{model_id}"


def _resolved_stage1_model(model: str | None, actor: dict | None = None) -> str:
    return _resolved_stage_model(model, actor, stage="stage1")


def _resolved_stage2_model(model: str | None, actor: dict | None = None) -> str:
    return _resolved_stage_model(model, actor, stage="stage2")


def _model_metadata(*, stage1_model: str | None = None, stage2_model: str | None = None) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if stage1_model:
        metadata["stage1_model"] = stage1_model
    if stage2_model:
        metadata["stage2_model"] = stage2_model
    return metadata


def _output_save_settings() -> dict:
    return _db.get_output_save_settings()


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


def _current_output_dir() -> Path:
    return Path(_output_save_settings()["output_dir"])


def _output_prefix(user_id: str, item_id: str, at_ms: int) -> Path:
    dt = datetime.fromtimestamp(at_ms / 1000, tz=timezone.utc).astimezone()
    date_dir = _current_output_dir() / user_id / dt.strftime("%Y-%m-%d")
    return date_dir / (dt.strftime("%Y%m%d_%H%M%S") + "_" + item_id[:8])


def _save_output_files(
    prefix: Path,
    input_text: str,
    ddl: str | None,
    score: dict,
    svg: str,
    render_metadata: dict | None = None,
    model_metadata: dict | None = None,
) -> None:
    try:
        prefix.parent.mkdir(parents=True, exist_ok=True)
        if input_text:
            Path(f"{prefix}_instruction.txt").write_text(input_text, encoding="utf-8")
        if ddl:
            Path(f"{prefix}_normalized.ddl").write_text(ddl, encoding="utf-8")
        score_payload = {"score": score, **(model_metadata or {}), **(render_metadata or {})}
        Path(f"{prefix}_score.json").write_text(json.dumps(score_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        svg_bytes = svg.encode("utf-8")
        Path(f"{prefix}_output.svg").write_bytes(svg_bytes)
    except Exception:
        _logger.exception("failed to save output files: prefix=%s", prefix)
        return

    from inku_analysis.rasterizer import RasterizerUnavailable, svg_to_png

    try:
        png_bytes = svg_to_png(svg, width=int(_output_save_settings()["png_size"]))
        Path(f"{prefix}_output.png").write_bytes(png_bytes)
    except RasterizerUnavailable:
        _logger.warning("no SVG rasterizer is installed; skipped PNG output: prefix=%s", prefix)
    except Exception:
        _logger.exception("failed to save PNG output: prefix=%s", prefix)


def _render_hash_metadata(
    *,
    input_text: str,
    ddl: str | None,
    score: Score | dict,
    svg: str,
    catalog_id: str | None,
    render_metadata: dict | None,
) -> dict[str, str]:
    score_payload = score.model_dump(by_alias=True) if isinstance(score, Score) else score
    item = {
        "input": input_text,
        "ddl": _sanitize_placement_words(ddl) if ddl else ddl,
        "score": score_payload,
        "svg": svg,
        "catalog_id": catalog_id,
        **(render_metadata or {}),
    }
    render_hash = _db.render_hash_for_item(item)
    return {
        "render_hash": render_hash,
        "render_hash_short": _db.render_hash_short(render_hash) or "",
    }


def _resolved_tenkei(requested: str | None, actor: dict, lineage_parent_node_id: str | None) -> str:
    """添景水準の解決 (v1.97): 明示値 > 派生元作品からの継承 > auto。

    継承をサーバー側で解決することで、AI 自律推敲・CLI・全クライアントの派生生成が
    系統の水準を無指定のまま維持する（作者裁定 2026-07-19: 親作品から継承）。
    """
    if requested:
        return requested
    if lineage_parent_node_id:
        inherited = _db.tenkei_for_node(actor["id"], lineage_parent_node_id)
        if inherited in {"none", "sparse", "auto"}:
            return inherited
    return "auto"


def _validated_variation_amplitude(value: str | None) -> str | None:
    """変奏 (v2.0): 未指定・未知の強度は None にして変奏なしへ戻す。

    変奏は系譜継承しない（作者裁定 2026-07-20）。明示された作品だけが
    (強度, seed) を持ち、未指定の派生は変奏前と同じ展開になる。
    """
    if value in VARIATION_AMPLITUDES:
        return value
    return None


def _coerce_context(ddl: str, original_description: str | None = None) -> str:
    original = (original_description or "").strip()
    normalized = ddl.strip()
    if original and original != normalized:
        return f"{original}\n{normalized}"
    return normalized


def _validated_svg_profile(svg_profile: str | None) -> str:
    profile = (svg_profile or "display").strip().lower()
    if profile not in SVG_PROFILES:
        raise HTTPException(status_code=422, detail=f"unsupported svg profile: {svg_profile}")
    return profile


def _score_with_plugin_instructions(score: Score, instructions: list[dict]) -> Score:
    """展開層の決定的転写 instruction を coerce 後の Score へ合流させる (v1.94 輪1)。

    機械生成の instruction は構築時に確定済みのため coerce の対象にしない。
    自由文由来の instruction 群の後ろへ、展開順のまま連結する。
    """
    if not instructions:
        return score
    data = score.model_dump(by_alias=True)
    data["instructions"] = list(data["instructions"]) + [dict(i) for i in instructions]
    return Score.model_validate(data)


def _render_score_svg(
    score_payload: dict,
    *,
    catalog_id: str | None,
    canvas_aspect: str | None = None,
    svg_profile: str | None = None,
    render_seed: int | None = None,
    wild: bool = False,
) -> str:
    score = coerce_score(Score.model_validate(score_payload))
    canvas = _validated_canvas_aspect_override(canvas_aspect)
    if canvas is not None:
        score = _score_with_canvas(score, canvas)
    render_metadata = _render_metadata(_resolved_catalog_id(catalog_id))
    with _render_capacity():
        return current_render_engine().render(
            score,
            color_map=render_metadata["render_color_map"],
            catalog_id=render_metadata.get("render_color_catalog_id"),
            svg_profile=_validated_svg_profile(svg_profile),
            render_seed=render_seed,
            wild=wild,
        ).svg


def _history_output_prefix(item: dict) -> Path:
    output_path = item.get("output_path")
    if output_path:
        return Path(output_path)
    return _output_prefix(item["user_id"], item["id"], item["at"])


def _history_render_metadata(item: dict) -> dict | None:
    if isinstance(item.get("render_metadata"), dict):
        metadata = dict(item["render_metadata"])
        if metadata.get("render_canvas_aspect_id") is None and metadata.get("render_canvas_aspect") is not None:
            canvas_aspect_id = normalize_canvas_aspect_id(metadata.get("render_canvas_aspect"))
            metadata["render_canvas_aspect_id"] = canvas_aspect_id
            metadata.setdefault("render_canvas_aspect", canvas_aspect_id)
            metadata.setdefault("render_canvas_aspect_ratio", canvas_aspect_ratio_for_aspect(canvas_aspect_id))
        if item.get("render_hash") is not None:
            metadata["render_hash"] = item["render_hash"]
            metadata["render_hash_short"] = item.get("render_hash_short") or _db.render_hash_short(item.get("render_hash"))
        return metadata
    keys = (
        "stage1_prompt_digest",
        "stage1_prompt_base_digest",
        "stage2_prompt_digest",
        "ddl_version",
        "ddl_engine_version",
        "render_build_number",
        "render_color_profile",
        "render_engine_id",
        "render_engine_version",
        "render_canvas_aspect",
        "render_canvas_aspect_id",
        "render_canvas_aspect_ratio",
        "render_hash",
        "render_hash_short",
        "render_color_catalog_id",
        "render_color_catalog_name",
        "render_color_catalog_sub",
        "render_color_map",
    )
    metadata = {key: item[key] for key in keys if item.get(key) is not None}
    return metadata or None


def _history_model_metadata(item: dict) -> dict | None:
    metadata = _model_metadata(
        stage1_model=item.get("stage1_model"),
        stage2_model=item.get("stage2_model"),
    )
    return metadata or None


def _save_history_artifacts(item: dict) -> None:
    _save_output_files(
        _history_output_prefix(item),
        item.get("input", ""),
        item.get("ddl"),
        item.get("score", {}),
        item.get("svg", ""),
        _history_render_metadata(item),
        _history_model_metadata(item),
    )


def _increment_save_stat(name: str) -> None:
    with _save_stats_lock:
        _save_stats[name] = _save_stats.get(name, 0) + 1


def _artifact_save_stats() -> dict[str, int]:
    with _save_stats_lock:
        return dict(_save_stats)


def _increment_stage_stat(name: str) -> None:
    with _stage_stats_lock:
        _stage_stats[name] = _stage_stats.get(name, 0) + 1


def _stage_execution_stats() -> dict[str, int]:
    with _stage_stats_lock:
        return dict(_stage_stats)


def _run_history_artifact_save(item: dict) -> None:
    try:
        _save_history_artifacts(item)
        _increment_save_stat("completed")
    except Exception:
        _increment_save_stat("failed")
        _logger.exception("unexpected artifact save failure: history_id=%s", item.get("id"))
    finally:
        _save_slots.release()


def _submit_history_artifact_save(item: dict) -> bool:
    if not _output_save_settings()["enabled"]:
        _increment_save_stat("skipped")
        return False
    if not _save_slots.acquire(blocking=False):
        _increment_save_stat("skipped")
        _logger.warning(
            "artifact save queue is full; skipped background save: history_id=%s queue_limit=%s",
            item.get("id"),
            _SAVE_QUEUE_LIMIT,
        )
        return False
    _increment_save_stat("submitted")
    try:
        _save_executor.submit(_run_history_artifact_save, item)
    except Exception:
        _increment_save_stat("failed")
        _save_slots.release()
        _logger.exception("failed to submit artifact save job: history_id=%s", item.get("id"))
        return False
    return True


def _validated_color_map(color_map: dict[str, str] | None) -> dict[str, str] | None:
    if color_map is None:
        return None
    clean: dict[str, str] = {}
    for key, value in color_map.items():
        if not isinstance(key, str) or not isinstance(value, str) or not _HEX_COLOR_RE.fullmatch(value):
            raise HTTPException(status_code=422, detail="color_map values must be #RRGGBB hex colors")
        clean[key] = value
    return clean


def _catalog_render_color_map(catalog_id: str | None) -> dict[str, str]:
    color_map = render_color_map_for_catalog(catalog_id)
    if color_map is None:
        raise HTTPException(status_code=422, detail=f"unsupported color catalog: {catalog_id}")
    return color_map



def _score_canvas_aspect_value(score: Score) -> str:
    if isinstance(score.canvas, CanvasSpec):
        return score.canvas.aspect
    return str(score.canvas or "square")

def _render_metadata(catalog_id: str | None, *, canvas_aspect: str | None = None) -> dict:
    catalog = get_color_catalog(catalog_id)
    color_map = render_color_map_for_catalog(catalog_id)
    if catalog is None or color_map is None:
        raise HTTPException(status_code=422, detail=f"unsupported color catalog: {catalog_id}")
    metadata = {
        "ddl_version": DDL_VERSION,
        "ddl_engine_version": DDL_ENGINE_VERSION,
        "render_build_number": _build_number(),
        "render_color_profile": dict(_SRGB_COLOR_PROFILE),
    }
    if canvas_aspect is not None:
        canvas_aspect_id = normalize_canvas_aspect_id(canvas_aspect)
        metadata["render_canvas_aspect"] = canvas_aspect_id
        metadata["render_canvas_aspect_id"] = canvas_aspect_id
        metadata["render_canvas_aspect_ratio"] = canvas_aspect_ratio_for_aspect(canvas_aspect_id)
    metadata.update({
        "render_color_catalog_id": str(catalog["id"]),
        "render_color_catalog_name": str(catalog["name"]),
        "render_color_catalog_sub": str(catalog["sub"]),
    })
    metadata["render_color_map"] = color_map
    return metadata


def _render_with_metadata(score: Score, render_metadata: dict, *, svg_profile: str | None = None) -> tuple[str, dict]:
    effective_seed = int(render_metadata.get("render_seed") or new_render_seed())
    wild = bool(render_metadata.get("render_wild"))
    render_metadata = {**render_metadata, "render_seed": effective_seed, "render_wild": wild}
    with _render_capacity():
        result = current_render_engine().render(
            score,
            color_map=render_metadata["render_color_map"],
            catalog_id=render_metadata.get("render_color_catalog_id"),
            svg_profile=_validated_svg_profile(svg_profile),
            render_seed=effective_seed,
            wild=wild,
        )
    return result.svg, {**render_metadata, **result.metadata}


def _resolved_catalog_id(catalog_id: str | None) -> str:
    catalog = get_color_catalog(catalog_id)
    if catalog is None:
        raise HTTPException(status_code=422, detail=f"unsupported color catalog: {catalog_id}")
    return str(catalog["id"])


def _resolved_paint_catalog_id(catalog_id: str | None, *, random_catalog: bool) -> str:
    resolved = _resolved_catalog_id(catalog_id)
    if not random_catalog:
        return resolved
    candidates = [candidate for candidate in color_catalog_ids() if candidate != resolved]
    return secrets.choice(candidates) if candidates else resolved


def _validated_canvas_aspect(value: str | None) -> str:
    if value is None:
        return normalize_canvas_aspect_id(None)
    if value not in canvas_aspect_ids():
        raise HTTPException(status_code=422, detail=f"unsupported canvas aspect: {value}")
    return value


def _render_seed_from_text(seed_text: str | None, render_seed: int | None) -> tuple[int | None, str | None]:
    normalized = (seed_text or "").strip()
    if not normalized:
        return render_seed, None
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False), normalized


def _validated_canvas_aspect_override(value: str | None) -> str | None:
    if value is None:
        return None
    return _validated_canvas_aspect(value)


def _score_with_canvas(score: Score, canvas_aspect: str) -> Score:
    data = score.model_dump(by_alias=True)
    existing = data.get("canvas")
    if isinstance(existing, dict) and existing.get("ground") is not None:
        existing["aspect"] = canvas_aspect
    else:
        data["canvas"] = canvas_aspect
    return Score.model_validate(data)


def _score_relation_count(score: Score | None) -> int:
    if score is None:
        return 0
    return sum(1 for instruction in score.instructions if instruction.relation is not None)


def _coerce_relation_report(before: Score | None, after: Score | None) -> dict[str, object]:
    input_count = _score_relation_count(before)
    output_count = _score_relation_count(after)
    dropped_count = max(0, input_count - output_count)
    warnings = ["relation dropped during coerce validation"] if dropped_count else []
    return {
        "coerce_relation_input_count": input_count,
        "coerce_relation_output_count": output_count,
        "coerce_relation_dropped_count": dropped_count,
        "coerce_relation_drop_rate": round(dropped_count / input_count, 6) if input_count else None,
        "coerce_warnings": warnings,
    }


_cors_origins = [
    origin.strip()
    for origin in os.getenv("INKU_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=_MAX_REQUEST_BODY_BYTES)
app.add_middleware(ConcurrencyLimitMiddleware, max_requests=_MAX_CONCURRENT_REQUESTS)


class ComposeRequest(BaseModel):
    ddl: str = Field(..., min_length=1, max_length=100_000, description="正規化DDL テキスト")
    model: str | None = Field(
        default=None, description="Stage 2 モデル名 (未指定時は利用者の Stage 2 既定)"
    )
    description: str | None = Field(default=None, max_length=100_000, description="作者が書いた記述 (省略可)")
    instruction_lang: str = Field(default="auto", description="指示文言語 (auto / ja / en)")
    ui_lang: str | None = Field(default=None, description="UI表示言語")
    color_map: dict[str, str] | None = Field(default=None, description="Deprecated: ignored; catalog_id is resolved server-side")
    catalog_id: str | None = Field(default=None, description="使用するサーバー側色カタログID")
    canvas_aspect: str | None = Field(default=None, description="Canvas aspect plugin selection")
    auto_repair: bool = Field(default=True, description="Stage 2 Score の自動補正を適用するか")
    tenkei: str | None = Field(default=None, pattern="^(none|sparse|auto)$", description="添景水準 (v1.97): none / sparse / auto。省略時は lineage_parent_node_id の作品から継承、無ければ auto")
    variation_amplitude: str | None = Field(default=None, description="変奏 (v2.0): 展開層をずらす強度 small / medium / large。variation_seed と揃って初めて有効")
    variation_seed: int | None = Field(default=None, description="変奏 (v2.0): どの軸がどう動くかを決める seed。variation_amplitude と揃って初めて有効")
    lineage_parent_node_id: str | None = Field(default=None, description="添景水準の継承元 lineage ノード (v1.97)。保存には関与しない")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    composition_seed: int | None = Field(default=None, description="Stage 1.5 composition variation seed")
    interpretation_seed: str | None = Field(default=None, description="Opaque identifier for an explicit Stage 1 re-interpretation")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")
    include_trace: bool = Field(default=False, description="各層の RAW 中間生成物を trace として返すか (観測のみ)")


class ComposeResponse(BaseModel):
    ddl: str
    # 入力側 DDL (展開前)。ddl は Stage 2 に渡った展開後。
    source_ddl: str | None = None
    plugin_provenance: list[dict[str, str]] = Field(default_factory=list)
    plugin_warnings: list[str] = Field(default_factory=list)
    carriage_warnings: list[str] | None = None  # v1.94 B: 搬送契約の鏡（検査のみ）
    score: Score
    svg: str
    stage2_model: str | None = None
    stage2_prompt_digest: str | None = None
    ddl_version: str | None = None
    ddl_engine_version: str | None = None
    render_build_number: str | None = None
    render_color_profile: dict[str, str] | None = None
    render_engine_id: str | None = None
    render_engine_version: str | None = None
    render_hash: str | None = None
    render_hash_short: str | None = None
    render_color_catalog_id: str | None = None
    render_color_catalog_name: str | None = None
    render_color_catalog_sub: str | None = None
    render_color_map: dict[str, str] | None = None
    render_canvas_aspect: str | None = None
    render_canvas_aspect_id: str | None = None
    render_canvas_aspect_ratio: float | None = None
    render_seed: int | None = None
    render_wild: bool | None = None
    composition_seed: int | None = None
    tenkei: str | None = None
    focus: str | None = None
    variation_amplitude: str | None = None
    variation_seed: int | None = None
    variation_moved_axes: list[dict[str, str]] = Field(default_factory=list)
    interpretation_seed: str | None = None
    seed_text: str | None = None
    instruction_lang_requested: str | None = None
    instruction_lang_resolved: str | None = None
    ui_lang: str | None = None
    elapsed_ms: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    retry_count: int = 0
    retry_reasons: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    coerce_relation_input_count: int = 0
    coerce_relation_output_count: int = 0
    coerce_relation_dropped_count: int = 0
    coerce_relation_drop_rate: float | None = None
    coerce_warnings: list[str] = Field(default_factory=list)
    coerce_branch_counts: dict[str, int] = Field(default_factory=dict)
    trace: dict | None = None


class InterpretRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=100_000, description="作者が書いた記述")
    stage1_input: str | None = Field(default=None, max_length=100_000, description="Stage 1 が実際に読む文字列 (記述に文脈を注入したもの)。省略時は description")
    model: str | None = Field(
        default=None, description="Stage 1 モデル名 (未指定時は利用者の Stage 1 既定)"
    )
    include_thinking: bool = Field(
        default=False, description="qwen3 の <think> 内容を別フィールドで返すか"
    )
    instruction_lang: str = Field(default="auto", description="指示文言語 (auto / ja / en)")
    ui_lang: str | None = Field(default=None, description="UI表示言語")
    expand_intermediate: bool = Field(default=False, description="Stage 1.5 の中間DDL拡張を適用するか")
    tenkei: str | None = Field(default=None, pattern="^(none|sparse|auto)$", description="添景水準 (v1.97): none / sparse / auto。省略時 auto")


class InterpretResponse(BaseModel):
    ddl: str
    plugin_provenance: list[dict[str, str]] = Field(default_factory=list)
    plugin_warnings: list[str] = Field(default_factory=list)
    thinking: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class PaintRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=100_000, description="作者が書いた記述")
    stage1_input: str | None = Field(default=None, max_length=100_000, description="Stage 1 が実際に読む文字列 (記述に文脈を注入したもの)。省略時は description")
    stage1_model: str | None = Field(default=None, description="Stage 1 モデル名")
    stage2_model: str | None = Field(default=None, description="Stage 2 モデル名")
    include_thinking: bool = Field(default=False, description="Stage 1 の思考を返すか")
    instruction_lang: str = Field(default="auto", description="指示文言語 (auto / ja / en)")
    ui_lang: str | None = Field(default=None, description="UI表示言語")
    color_map: dict[str, str] | None = Field(default=None, description="Deprecated: ignored; catalog_id is resolved server-side")
    canvas_aspect: str | None = Field(default=None, description="Canvas aspect plugin selection")
    save_history: bool = Field(default=False, description="描画結果を履歴に保存するか")
    save_artifacts: bool | None = Field(default=None, description="SVG/JSON/PNG などの副産物ファイルを保存するか")
    count_generation: bool = Field(default=True, description="完了した描画をユーザーの累積生成数に加算するか")
    history_input: str | None = Field(default=None, description="履歴に表示するユーザー記述")
    history_at: int | None = Field(default=None, description="履歴保存時刻")
    history_source_text: str | None = Field(default=None, description="作者が書いたラベルなしの履歴本文")
    history_display_label: str | None = Field(default=None, description="バッチ番号やdemoなどの表示ラベル")
    batch_line_number: int | None = None
    batch_run_id: str | None = None
    history_visibility: str = "normal"
    lineage_parent_node_id: str | None = None
    derivation_kind: str | None = None
    derivation_metadata: dict[str, object] = Field(default_factory=dict)
    catalog_id: str | None = Field(default=None, description="使用する色カタログID。ランダム選択時は直前IDとして除外する")
    random_color_catalog: bool = Field(default=False, description="現在のcatalog_idを除外してサーバー側で色カタログを選ぶか")
    auto_repair: bool = Field(default=True, description="Stage 2 Score の自動補正を適用するか")
    tenkei: str | None = Field(default=None, pattern="^(none|sparse|auto)$", description="添景水準 (v1.97): none / sparse / auto。省略時は lineage_parent_node_id の作品から継承、無ければ auto")
    variation_amplitude: str | None = Field(default=None, description="変奏 (v2.0): 展開層をずらす強度 small / medium / large。variation_seed と揃って初めて有効")
    variation_seed: int | None = Field(default=None, description="変奏 (v2.0): どの軸がどう動くかを決める seed。variation_amplitude と揃って初めて有効")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    composition_seed: int | None = Field(default=None, description="Stage 1.5 composition variation seed")
    interpretation_seed: str | None = Field(default=None, description="Opaque identifier for an explicit Stage 1 re-interpretation")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")
    include_trace: bool = Field(default=False, description="各層の RAW 中間生成物を trace として返すか (観測のみ)")


class PaintResponse(BaseModel):
    description: str
    ddl: str
    # 入力側 DDL (展開前)。ddl は Stage 2 に渡った展開後。
    source_ddl: str | None = None
    plugin_provenance: list[dict[str, str]] = Field(default_factory=list)
    plugin_warnings: list[str] = Field(default_factory=list)
    carriage_warnings: list[str] | None = None  # v1.94 B: 搬送契約の鏡（検査のみ）
    thinking: str | None = None
    score: Score
    svg: str
    stage1_model: str | None = None
    stage2_model: str | None = None
    stage1_prompt_digest: str | None = None
    stage1_prompt_base_digest: str | None = None
    stage2_prompt_digest: str | None = None
    ddl_version: str | None = None
    ddl_engine_version: str | None = None
    render_build_number: str | None = None
    render_color_profile: dict[str, str] | None = None
    render_engine_id: str | None = None
    render_engine_version: str | None = None
    render_color_catalog_id: str | None = None
    render_color_catalog_name: str | None = None
    render_color_catalog_sub: str | None = None
    render_color_map: dict[str, str] | None = None
    render_canvas_aspect: str | None = None
    render_canvas_aspect_id: str | None = None
    render_canvas_aspect_ratio: float | None = None
    render_seed: int | None = None
    render_wild: bool | None = None
    composition_seed: int | None = None
    tenkei: str | None = None
    focus: str | None = None
    variation_amplitude: str | None = None
    variation_seed: int | None = None
    variation_moved_axes: list[dict[str, str]] = Field(default_factory=list)
    interpretation_seed: str | None = None
    seed_text: str | None = None
    instruction_lang_requested: str | None = None
    instruction_lang_resolved: str | None = None
    ui_lang: str | None = None
    render_hash: str | None = None
    render_hash_short: str | None = None
    history_id: str | None = None
    history_at: int | None = None
    description_hash: str | None = None
    lineage_node_id: str | None = None
    lineage_parent_node_id: str | None = None
    derivation_kind: str | None = None
    elapsed_stage1_ms: int = 0
    elapsed_stage2_ms: int = 0
    elapsed_total_ms: int = 0
    tokens_in_stage1: int | None = None
    tokens_out_stage1: int | None = None
    tokens_in_stage2: int | None = None
    tokens_out_stage2: int | None = None
    interpret_fallback_used: bool = False
    interpret_fallback_reasons: list[str] = Field(default_factory=list)
    compose_retry_count: int = 0
    compose_retry_reasons: list[str] = Field(default_factory=list)
    compose_fallback_used: bool = False
    user_generation_count: int | None = None
    catalog_id: str | None = None
    coerce_relation_input_count: int = 0
    coerce_relation_output_count: int = 0
    coerce_relation_dropped_count: int = 0
    coerce_relation_drop_rate: float | None = None
    coerce_warnings: list[str] = Field(default_factory=list)
    coerce_branch_counts: dict[str, int] = Field(default_factory=dict)
    trace: dict | None = None


class UnreadWordsBody(BaseModel):
    words: list[str] = Field(default_factory=list, max_length=100)
    context: str = Field(default="", max_length=1000)


class RenderSvgRequest(BaseModel):
    score: dict
    catalog_id: str | None = None
    canvas_aspect: str | None = None
    svg_profile: str = Field(default="display", description="SVG output profile: display / editable / compat")
    render_seed: int | None = Field(default=None, description="Renderer performance seed for reproducible replay")
    wild: bool = Field(default=False, description="Unleash the stroke performance (removes the amplitude ceiling); recorded and replayed like the seed")
    seed_text: str | None = Field(default=None, description="Explicit text used only to derive the Renderer performance seed")


class RenderScoreRequest(BaseModel):
    score: dict
    input: str = ""
    ddl: str | None = None
    catalog_id: str | None = None
    canvas_aspect: str | None = None
    render_seed: int | None = None
    wild: bool = False
    composition_seed: int | None = None
    interpretation_seed: str | None = None
    seed_text: str | None = None


class RenderScoreResponse(BaseModel):
    score: Score
    svg: str
    catalog_id: str
    ddl_version: str
    ddl_engine_version: str
    render_build_number: str
    render_color_profile: dict[str, str]
    render_engine_id: str
    render_engine_version: str
    render_color_catalog_id: str
    render_color_catalog_name: str
    render_color_catalog_sub: str
    render_color_map: dict[str, str]
    render_canvas_aspect: str
    render_canvas_aspect_id: str
    render_canvas_aspect_ratio: float
    render_seed: int
    composition_seed: int | None = None
    interpretation_seed: str | None = None
    seed_text: str | None = None
    render_hash: str
    render_hash_short: str


@dataclass
class InterpretDetail:
    ddl: str
    thinking: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    fallback_used: bool = False
    fallback_reasons: list[str] = field(default_factory=list)
    raw: str | None = None  # trace: サニタイズ前の Stage 1 生 DDL (include_trace 時のみ)
    stage1_prompt_digest: str | None = None
    stage1_prompt_base_digest: str | None = None


@dataclass
class ComposeDetail:
    score: Score
    # ddl は Stage 2 に渡った展開後 DDL。source_ddl は展開前の入力側 (Stage 1 出力
    # またはユーザーが書いた DDL)。v1.98 で trace 限定から常時保持へ昇格。
    ddl: str
    source_ddl: str = ""
    plugin_provenance: list[dict[str, str]] = field(default_factory=list)
    plugin_warnings: list[str] = field(default_factory=list)
    # v1.94 輪1: 展開層が決定的に転写した instruction（coerce を迂回して後段合流）
    plugin_instructions: list[dict] = field(default_factory=list)
    tokens_in: int | None = None
    tokens_out: int | None = None
    retry_count: int = 0
    retry_reasons: list[str] = field(default_factory=list)
    fallback_used: bool = False
    # trace (include_trace 時のみ; ddl は stage15 と同一)
    stage1_ddl_in: str | None = None
    plugin_expanded_ddl: str | None = None
    stage15_ddl: str | None = None
    stage2_raw_attempts: list[dict] | None = None
    # 変奏 (v2.0): 展開層が実際に振った結果。resolved_focus は history.focus の供給源。
    variation_moved_axes: list[dict[str, str]] = field(default_factory=list)
    resolved_focus: str | None = None
    stage2_prompt_digest: str | None = None


class PromptsResponse(BaseModel):
    stage1_system: str
    stage2_system: str


class AppInfoResponse(BaseModel):
    name: str
    version: str
    build_number: str | None = None
    developer_mode: bool = False
    render_engine_id: str
    render_engine_version: str
    ddl_version: str
    ddl_engine_version: str


class ColorCatalogsResponse(BaseModel):
    default_catalog_id: str
    catalogs: list[dict]


class HistoryPostBody(BaseModel):
    input: str
    ddl: str | None = None
    expanded_ddl: str | None = None
    focus: str | None = None
    variation_amplitude: str | None = None
    variation_seed: int | None = None
    interpret_fallback: str | None = None
    score: dict
    svg: str = ""
    at: int
    elapsed_ms: int = 0
    stage1_model: str | None = None
    stage2_model: str | None = None
    stage1_prompt_digest: str | None = None
    stage1_prompt_base_digest: str | None = None
    stage2_prompt_digest: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    catalog_id: str | None = None
    ddl_version: str | None = None
    ddl_engine_version: str | None = None
    render_build_number: str | None = None
    render_color_profile: dict[str, str] | None = None
    render_engine_id: str | None = None
    render_engine_version: str | None = None
    render_color_catalog_id: str | None = None
    render_color_catalog_name: str | None = None
    render_color_catalog_sub: str | None = None
    render_color_map: dict[str, str] | None = None
    render_canvas_aspect: str | None = None
    render_canvas_aspect_id: str | None = None
    render_canvas_aspect_ratio: float | None = None
    render_seed: int | None = None
    render_wild: bool | None = None
    composition_seed: int | None = None
    tenkei: str | None = Field(default=None, pattern="^(none|sparse|auto)$")
    interpretation_seed: str | None = None
    seed_text: str | None = None
    source_text: str | None = None
    display_label: str | None = None
    batch_line_number: int | None = None
    batch_run_id: str | None = None
    history_visibility: str = "normal"
    lineage_parent_node_id: str | None = None
    derivation_kind: str | None = None
    derivation_metadata: dict[str, object] = Field(default_factory=dict)
    instruction_lang_requested: str | None = None
    instruction_lang_resolved: str | None = None
    ui_lang: str | None = None
    save_artifacts: bool = True
    count_generation: bool = Field(default=False, exclude=True)
    color_map: dict[str, str] | None = Field(default=None, exclude=True, description="Deprecated: ignored; catalog_id is resolved server-side")
    canvas_aspect: str | None = Field(default=None, exclude=True)


class HistoryItem(HistoryPostBody):
    id: str
    output_path: str | None = None
    render_hash: str | None = None
    render_hash_short: str | None = None
    trashed: bool = False
    starred: bool = False
    note: str | None = None
    description_hash: str | None = None
    lineage_node_id: str | None = None
    lineage_root_node_id: str | None = None
    lineage_generation: int | None = Field(default=None, ge=1)
    lineage_state: Literal["active", "lineage_only", "tombstone"] | None = None
    data_warnings: list[str] = Field(default_factory=list)


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int
    offset: int
    limit: int


class HistoryLineageGroup(BaseModel):
    root_node_id: str
    representative: HistoryItem
    item_count: int
    starred_count: int
    latest_at: int


class HistoryLineageGroupListResponse(BaseModel):
    groups: list[HistoryLineageGroup]
    total: int
    offset: int
    limit: int


class VisionRefineAdviceBody(BaseModel):
    history_id: str = Field(..., min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    instruction: str = Field(..., min_length=1, max_length=100_000)
    direction: str = Field(default="", max_length=2000)
    enabled_kinds: list[str] = Field(..., min_length=1, max_length=5)
    language: str = Field(default="ja", pattern="^(ja|en)$")


class VisionRefineAdviceResponse(BaseModel):
    observation: str
    next_direction: str
    suggested_kind: str
    model: str


class OkugakiGenerateBody(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=200)
    language: str = Field(default="ja", pattern="^(ja|en)$")
    save: bool = True


class OkugakiItem(BaseModel):
    id: str | None = None
    target_node_id: str
    branch_snapshot: list[str]
    model: str
    at: int
    language: str
    body: str
    warnings: list[str] = Field(default_factory=list)
    fact_sheet: dict = Field(default_factory=dict)


class HistoryIdsBody(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=1000)


class AnimationExportBody(BaseModel):
    ids: list[str] = Field(..., min_length=2, max_length=100)
    format: Literal["apng", "gif"] = "apng"
    pattern: Literal["cut", "crossfade", "fade_white", "slide"] = "cut"
    hold_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    resolution: Literal["1k", "4k", "8k"] = "1k"
    height_px: int | None = Field(default=None, ge=64, le=12000)


class HistoryStarBody(BaseModel):
    starred: bool = False
    note: str | None = None


class UserGroupItem(BaseModel):
    id: str
    name: str
    at: int


class UserGroupCreateBody(BaseModel):
    name: str = Field(..., min_length=1, description="ユーザーグループ名")


class UserGroupUpdateBody(BaseModel):
    name: str = Field(..., min_length=1, description="ユーザーグループ名")


class UserAccountItem(BaseModel):
    id: str
    username: str
    email: str
    role: str
    role_label: str
    group_id: str | None = None
    group_name: str | None = None
    ui_theme: str = "dark"
    ui_mode: str = "simple"
    ui_custom: dict[str, bool] = Field(default_factory=dict)
    tooltips_enabled: bool = True
    settings_tab: str = "db"
    model_settings: dict = Field(default_factory=dict)
    image_generation_count: int = 0
    at: int


class UserAccountCreateBody(BaseModel):
    username: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)
    role: str = Field(default="user")
    group_id: str | None = None


class UserAccountUpdateBody(BaseModel):
    username: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=8)
    role: str | None = None
    group_id: str | None = None


class UserProfileUpdateBody(BaseModel):
    email: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=8)
    current_password: str | None = Field(default=None, min_length=1)


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    user: UserAccountItem


class UserSettingsBody(BaseModel):
    ui_theme: str | None = None
    ui_mode: str | None = None
    ui_custom: dict[str, bool] | None = None
    tooltips_enabled: bool | None = None
    settings_tab: str | None = None
    model_settings: dict | None = None


class BatchPromptHistoryBody(BaseModel):
    items: list[str] = Field(default_factory=list)


class BatchPromptHistoryResponse(BaseModel):
    items: list[str] = Field(default_factory=list)


class ExportTemplateItem(BaseModel):
    id: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    y_px: int = Field(..., ge=64, le=12000)


class ExportTemplatesBody(BaseModel):
    templates: list[ExportTemplateItem] = Field(default_factory=list)


class PluginStorageBody(BaseModel):
    storage: dict = Field(default_factory=dict)


class PluginValueBody(BaseModel):
    value: dict = Field(default_factory=dict)


class DemoSettingsBody(BaseModel):
    save_db: bool = False
    save_files: bool = False
    prompt_provider: str = Field(default="nvidia", min_length=1)
    prompt_model: str = Field(default="google/gemma-4-31b-it", min_length=1)
    seed_phrase: str = Field(default="日本の四季を感じさせる文章を40語以内で生成", min_length=1, max_length=1000)
    interval_seconds: int = Field(default=30, ge=1, le=3600)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    random_color_catalog: bool = False


class DemoInstructionBody(BaseModel):
    seed_phrase: str = Field(..., min_length=1, max_length=1000)
    model: str | None = Field(default=None)
    instruction_lang: str = Field(default="auto")
    ui_lang: str | None = None


class DemoInstructionResponse(BaseModel):
    instruction: str


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


class PluginValidateBody(BaseModel):
    document: str = Field(..., min_length=1, max_length=500_000)


class PluginCreateBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=500_000)
    filename: str | None = Field(default=None, max_length=200)


class PluginUpdateBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=500_000)


class PluginEnabledBody(BaseModel):
    enabled: bool


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


class ModelSettingsResponse(BaseModel):
    catalog: list[dict] = Field(default_factory=list)
    llm_catalog: list[dict] = Field(default_factory=list)
    vision_catalog: list[dict] = Field(default_factory=list)
    settings: dict = Field(default_factory=dict)


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


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        _SESSION_COOKIE_NAME,
        token,
        max_age=_SESSION_COOKIE_MAX_AGE,
        httponly=True,
        secure=_SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(_SESSION_COOKIE_NAME, path="/", samesite="lax")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _session_token(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=_SESSION_COOKIE_NAME),
) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    if session_cookie:
        return session_cookie
    raise HTTPException(status_code=401, detail="authentication required")


def _bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    return authorization.removeprefix("Bearer ").strip()


def _current_user(token: str = Depends(_session_token)) -> dict:
    user = _db.get_session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _user_manager(actor: dict = Depends(_current_user)) -> dict:
    if actor["role"] not in {"admin", "group_lead"}:
        raise HTTPException(status_code=403, detail="user management is not permitted")
    return actor


def _admin_user(actor: dict = Depends(_current_user)) -> dict:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="administrator permission is required")
    return actor


def _can_manage_user(actor: dict, target: dict) -> bool:
    if actor["role"] == "admin":
        return True
    return (
        actor["role"] == "group_lead"
        and actor.get("group_id")
        and target.get("group_id") == actor.get("group_id")
        and target.get("role") == "user"
    )


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/info", response_model=AppInfoResponse)
def api_info() -> AppInfoResponse:
    engine = current_render_engine()
    return AppInfoResponse(
        name="inku-server",
        version=_APP_VERSION,
        build_number=_build_number(),
        developer_mode=_env_flag("INKU_DEVELOPER_MODE"),
        render_engine_id=engine.id,
        render_engine_version=engine.version,
        ddl_version=DDL_VERSION,
        ddl_engine_version=DDL_ENGINE_VERSION,
    )


@app.get("/api/color-catalogs", response_model=ColorCatalogsResponse)
def api_color_catalogs() -> ColorCatalogsResponse:
    return ColorCatalogsResponse(default_catalog_id="default", catalogs=color_catalogs())


@app.get("/api/auth/config")
def api_auth_config() -> dict:
    return _db.get_auth_settings()


class AuthSettingsBody(BaseModel):
    google_enabled: bool
    local_enabled: bool


@app.put("/api/auth/config")
def api_auth_config_update(body: AuthSettingsBody, actor: dict = Depends(_user_manager)) -> dict:
    return _db.update_auth_settings(body.google_enabled, body.local_enabled)


@app.post("/api/auth/login", response_model=LoginResponse)
def api_auth_login(body: LoginBody, response: Response, request: Request) -> LoginResponse:
    auth_config = _db.get_auth_settings()
    if not auth_config.get("local_enabled", True):
        raise HTTPException(status_code=403, detail="Local authentication is disabled")
    client_host = request.client.host if request.client else "unknown"
    rate_key = f"{client_host}:{body.username.strip().casefold()}"
    rate_result = _login_rate_limiter.check(rate_key)
    if not rate_result.allowed:
        raise HTTPException(
            status_code=429,
            detail="too many login attempts",
            headers={"Retry-After": str(rate_result.retry_after)},
        )
    user = _db.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid username or password")
    _login_rate_limiter.reset(rate_key)
    token = _db.create_session(user["id"])
    _set_session_cookie(response, token)
    return LoginResponse(user=UserAccountItem(**user))


@app.get("/api/auth/me", response_model=UserAccountItem)
def api_auth_me(actor: dict = Depends(_current_user)) -> UserAccountItem:
    return UserAccountItem(**actor)


@app.patch("/api/auth/me/settings", response_model=UserAccountItem)
def api_auth_me_settings(body: UserSettingsBody, actor: dict = Depends(_current_user)) -> UserAccountItem:
    try:
        user = _db.update_user_settings(
            actor["id"],
            ui_theme=body.ui_theme,
            ui_mode=body.ui_mode,
            ui_custom=body.ui_custom,
            tooltips_enabled=body.tooltips_enabled,
            settings_tab=body.settings_tab,
            model_settings=body.model_settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@app.get("/api/models", response_model=ModelSettingsResponse)
def api_models(actor: dict = Depends(_current_user)) -> ModelSettingsResponse:
    settings = _db.get_model_settings()
    developer_mode = _env_flag("INKU_DEVELOPER_MODE")
    return ModelSettingsResponse(
        catalog=model_provider_catalog(
            settings, include_disabled=False, include_developer=developer_mode, purpose="llm"
        ),
        llm_catalog=model_provider_catalog(
            settings, include_disabled=False, include_developer=developer_mode, purpose="llm"
        ),
        vision_catalog=model_provider_catalog(
            settings, include_disabled=False, include_developer=developer_mode, purpose="vision"
        ),
        settings={"model_settings": actor.get("model_settings") or {}},
    )


@app.patch("/api/auth/me/profile", response_model=UserAccountItem)
def api_auth_me_profile(body: UserProfileUpdateBody, actor: dict = Depends(_current_user)) -> UserAccountItem:
    try:
        user = _db.update_current_user_profile(
            actor["id"],
            email=body.email,
            password=body.password,
            current_password=body.current_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("profile update", 409) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@app.get("/api/auth/me/batch-prompt-history", response_model=BatchPromptHistoryResponse)
def api_auth_me_batch_prompt_history(actor: dict = Depends(_current_user)) -> BatchPromptHistoryResponse:
    return BatchPromptHistoryResponse(items=_db.get_user_batch_prompt_history(actor["id"]))


@app.put("/api/auth/me/batch-prompt-history", response_model=BatchPromptHistoryResponse)
def api_auth_me_update_batch_prompt_history(
    body: BatchPromptHistoryBody,
    actor: dict = Depends(_current_user),
) -> BatchPromptHistoryResponse:
    try:
        items = _db.update_user_batch_prompt_history(actor["id"], body.items)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if items is None:
        raise HTTPException(status_code=404, detail="user not found")
    return BatchPromptHistoryResponse(items=items)


@app.get("/api/auth/me/export-templates", response_model=ExportTemplatesBody)
def api_auth_me_export_templates(actor: dict = Depends(_current_user)) -> ExportTemplatesBody:
    return ExportTemplatesBody(templates=_db.get_user_export_templates(actor["id"]))


@app.put("/api/auth/me/export-templates", response_model=ExportTemplatesBody)
def api_auth_me_update_export_templates(
    body: ExportTemplatesBody,
    actor: dict = Depends(_current_user),
) -> ExportTemplatesBody:
    try:
        templates = _db.update_user_export_templates(
            actor["id"],
            [item.model_dump() for item in body.templates],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if templates is None:
        raise HTTPException(status_code=404, detail="user not found")
    return ExportTemplatesBody(templates=templates)


@app.get("/api/auth/me/plugin-storage", response_model=PluginStorageBody)
def api_auth_me_plugin_storage(actor: dict = Depends(_current_user)) -> PluginStorageBody:
    return PluginStorageBody(storage=_db.get_user_plugin_storage(actor["id"]))


@app.put("/api/auth/me/plugin-storage", response_model=PluginStorageBody)
def api_auth_me_update_plugin_storage(
    body: PluginStorageBody,
    actor: dict = Depends(_admin_user),
) -> PluginStorageBody:
    try:
        storage = _db.update_user_plugin_storage(actor["id"], body.storage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if storage is None:
        raise HTTPException(status_code=404, detail="user not found")
    return PluginStorageBody(storage=storage)


@app.put("/api/auth/me/plugin-storage/{plugin_id}", response_model=PluginStorageBody)
def api_auth_me_update_plugin_value(
    plugin_id: str,
    body: PluginValueBody,
    actor: dict = Depends(_admin_user),
) -> PluginStorageBody:
    try:
        storage = _db.update_user_plugin_value(actor["id"], plugin_id, body.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if storage is None:
        raise HTTPException(status_code=404, detail="user not found")
    return PluginStorageBody(storage=storage)


@app.get("/api/auth/me/demo-settings", response_model=DemoSettingsBody)
def api_auth_me_demo_settings(actor: dict = Depends(_current_user)) -> DemoSettingsBody:
    return DemoSettingsBody(**_db.get_user_demo_settings(actor["id"]))


@app.put("/api/auth/me/demo-settings", response_model=DemoSettingsBody)
def api_auth_me_update_demo_settings(
    body: DemoSettingsBody,
    actor: dict = Depends(_current_user),
) -> DemoSettingsBody:
    try:
        settings = _db.update_user_demo_settings(actor["id"], body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if settings is None:
        raise HTTPException(status_code=404, detail="user not found")
    return DemoSettingsBody(**settings)


@app.get("/api/plugins")
def api_plugins(actor: dict = Depends(_current_user)) -> dict[str, object]:
    return {"items": [item.as_dict() for item in DOCUMENT_PLUGIN_MANAGER.items()]}


@app.post("/api/plugins/validate")
def api_plugins_validate(
    body: PluginValidateBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    try:
        document = validate_plugin_document(body.document)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    return {
        "valid": True,
        "namespace": document.manifest.namespace,
        "name": document.manifest.name,
        "version": document.manifest.version,
        "entries": len(document.entries),
    }


@app.post("/api/plugins/reload")
def api_plugins_reload(actor: dict = Depends(_admin_user)) -> dict[str, object]:
    items = DOCUMENT_PLUGIN_MANAGER.reload(force=True)
    return {"items": [item.as_dict() for item in items]}


@app.get("/api/plugins/{plugin_id}/content")
def api_plugin_content(plugin_id: str, actor: dict = Depends(_admin_user)) -> dict[str, object]:
    try:
        content = DOCUMENT_PLUGIN_MANAGER.content(plugin_id)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return {"id": plugin_id, "path": plugin_id, "content": content, "editable": True}


@app.post("/api/plugins", status_code=201)
def api_plugin_create(
    body: PluginCreateBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    try:
        item = DOCUMENT_PLUGIN_MANAGER.create(body.content, filename=body.filename)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"plugin file already exists: {exc}") from None
    return item.as_dict()


@app.put("/api/plugins/{plugin_id}")
def api_plugin_update(
    plugin_id: str,
    body: PluginUpdateBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    try:
        item = DOCUMENT_PLUGIN_MANAGER.update(plugin_id, body.content)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return item.as_dict()


@app.delete("/api/plugins/{plugin_id}")
def api_plugin_delete(plugin_id: str, actor: dict = Depends(_admin_user)) -> dict[str, object]:
    try:
        DOCUMENT_PLUGIN_MANAGER.delete(plugin_id)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return {"ok": True}


@app.put("/api/plugins/{plugin_id}/enabled")
def api_plugin_set_enabled(
    plugin_id: str,
    body: PluginEnabledBody,
    actor: dict = Depends(_admin_user),
) -> dict[str, object]:
    try:
        item = DOCUMENT_PLUGIN_MANAGER.set_enabled(plugin_id, body.enabled)
    except PluginFormatError as exc:
        raise HTTPException(status_code=422, detail=list(exc.reasons)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plugin not found") from None
    return item.as_dict()


def _enabled_plugin_entries() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for item in DOCUMENT_PLUGIN_MANAGER.items():
        if item.status != "enabled":
            continue
        entries.extend(dict(entry) for entry in item.entries)
    return entries


@app.get("/api/saijiki")
def api_saijiki(
    lang: str = Query(default="ja", pattern="^(ja|en)$"),
    actor: dict = Depends(_current_user),
) -> dict[str, object]:
    """Saijiki vocabulary for display: core categories (from the saijiki table)
    plus loaded declarative plugin words. Single delivery for web hydration."""
    return {
        "categories": display_categories(lang),
        "plugins": _enabled_plugin_entries(),
    }


@app.get("/api/reference")
def api_reference(
    format: str = Query(default="json", pattern="^(json|md)$"),
    actor: dict = Depends(_current_user),
) -> Response:
    """Machine-generated mirror of implementation tables (read-only)."""
    reference = build_reference()
    if format == "md":
        return Response(content=render_markdown(reference), media_type="text/markdown")
    return JSONResponse(content=reference)


@app.get("/api/settings/status", response_model=SettingsStatusResponse)
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


@app.get("/api/settings/models", response_model=ModelSettingsResponse)
def api_settings_models(actor: dict = Depends(_admin_user)) -> ModelSettingsResponse:
    settings = _db.get_model_settings()
    developer_mode = _env_flag("INKU_DEVELOPER_MODE")
    return ModelSettingsResponse(
        catalog=model_provider_catalog(
            settings, include_disabled=True, include_developer=developer_mode
        ),
        settings=public_model_settings(settings, include_developer=developer_mode),
    )


@app.put("/api/settings/models", response_model=ModelSettingsResponse)
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


@app.post("/api/settings/models/{provider_id}/fetch-models", response_model=ModelSettingsResponse)
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


@app.put("/api/settings/db-backup", response_model=DbBackupStatus)
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


@app.put("/api/settings/output-save", response_model=OutputSaveStatus)
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


@app.put("/api/settings/render-concurrency", response_model=RenderConcurrencyStatus)
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


@app.get("/api/client-config")
def api_client_config(actor: dict = Depends(_current_user)) -> dict[str, object]:
    """Server-owned values every client needs. Editable by admins only."""
    return {"render_fanout_limit": int(_db.get_render_concurrency_settings()["client_limit"])}


@app.put("/api/settings/log-retention", response_model=LogRetentionStatus)
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


@app.post("/api/settings/db-backup/run", response_model=DbBackupResult)
def api_settings_run_db_backup(actor: dict = Depends(_admin_user)) -> DbBackupResult:
    try:
        result = _db.create_db_backup(manual=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return DbBackupResult(**result)


@app.post("/api/auth/logout")
def api_auth_logout(response: Response, token: str = Depends(_session_token)) -> dict[str, bool]:
    _db.delete_session(token)
    _clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/prompts", response_model=PromptsResponse)
def api_prompts(lang: str = Query(default="ja")) -> PromptsResponse:
    try:
        requested_lang = _normalize_instruction_lang(lang)
        s1, s2 = stage_prompts_for_lang("ja" if requested_lang == "auto" else requested_lang)
    except (HTTPException, ValueError):
        s1, s2 = stage_prompts_for_lang("ja")
    return PromptsResponse(stage1_system=s1, stage2_system=s2)


def _fallback_score_from_ddl(ddl: str, *, lang: str) -> Score:
    """Build a visible deterministic score when Stage 2 returns empty twice."""
    lower = ddl.lower()

    if ("背景を黒" in ddl) or ("fill background with black" in lower):
        background = "black"
        color = "white"
    elif ("背景を赤" in ddl) or ("fill background with red" in lower):
        background = "red"
        color = "black"
    elif ("背景を青" in ddl) or ("fill background with blue" in lower):
        background = "blue"
        color = "white"
    elif ("背景を緑" in ddl) or ("fill background with green" in lower):
        background = "green"
        color = "black"
    else:
        background = "white"
        color = "black"

    if (("白" in ddl) or ("white" in lower)) and background != "white":
        color = "white"
    elif (("青" in ddl) or ("blue" in lower)) and background != "blue":
        color = "blue"
    elif (("赤" in ddl) or ("red" in lower)) and background != "red":
        color = "red"
    elif (("緑" in ddl) or ("green" in lower)) and background != "green":
        color = "green"
    elif (("灰" in ddl) or ("gray" in lower) or ("grey" in lower)) and background != "gray":
        color = "gray"

    if color == background:
        color = "white" if background in {"black", "blue"} else "black"

    weight = "pen"
    if ("ビュラン" in ddl) or ("burin" in lower):
        weight = "burin"
    elif ("ドライポイント" in ddl) or ("drypoint" in lower):
        weight = "drypoint"
    elif ("コンピュータ" in ddl) or ("computer" in lower):
        weight = "computer"
    elif ("ロットリング" in ddl) or ("rotring" in lower):
        weight = "rotring"
    elif ("鉛筆" in ddl) or ("pencil" in lower):
        weight = "pencil"
    elif ("クレヨン" in ddl) or ("crayon" in lower):
        weight = "crayon"
    elif ("チョーク" in ddl) or ("chalk" in lower):
        weight = "chalk"
    elif ("太筆" in ddl) or ("thick-brush" in lower) or ("thick brush" in lower) or ("厚塗り" in ddl):
        weight = "brush_thick"
    elif ("細筆" in ddl) or ("水墨" in ddl) or ("墨" in ddl) or ("fine-brush" in lower) or ("ink" in lower):
        weight = "brush_thin"

    if any(marker in ddl for marker in ("色とりどり", "多色", "赤・青", "赤、青")) or any(
        marker in lower for marker in ("colorful", "multi-color", "multicolor", "red, blue")
    ):
        color_cycle = ["red", "blue", "green", "gray"]
    elif any(marker in ddl for marker in ("春", "花", "蕾", "桜", "温", "陽光")) or any(
        marker in lower for marker in ("spring", "flower", "bud", "warm", "sunlight")
    ):
        color_cycle = ["red", "green", "white"]
        if color == "black":
            color = "red"
    elif any(marker in ddl for marker in ("夜", "月", "水", "雨", "霧", "冷")) or any(
        marker in lower for marker in ("night", "moon", "water", "rain", "mist", "cold")
    ):
        color_cycle = ["blue", "white", "gray"]
        if color == "black":
            color = "blue"
    else:
        color_cycle = []

    if ("雲形" in ddl) or ("cloudform" in lower):
        instruction = {
            "primitive": "cloudform",
            "center": [0.62, 0.36],
            "size": [0.34, 0.22],
            "color": color,
            "weight": weight,
            "note": "fallback from explicit DDL cloudform",
        }
    elif ("三角" in ddl) or ("triangle" in lower) or ("山" in ddl) or ("mountain" in lower):
        instruction = {
            "primitive": "triangle",
            "position": [0.54, 0.22],
            "size": [0.20, 0.18],
            "rotation": -8,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    elif ("弧" in ddl) or ("arc" in lower) or ("crescent" in lower):
        instruction = {
            "primitive": "arc",
            "center": [0.72, 0.32],
            "radius": 0.16,
            "angle_start": 210,
            "angle_end": 330,
            "color": color,
            "weight": weight,
            "note": "fallback from DDL",
        }
    elif ("四角" in ddl) or ("square" in lower) or ("rectangle" in lower) or ("紙片" in ddl) or ("patch" in lower):
        instruction = {
            "primitive": "square",
            "position": [0.62, 0.28],
            "size": [0.18, 0.12],
            "rotation": -12,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    elif ("多角形" in ddl) or ("五角" in ddl) or ("六角" in ddl) or ("polygon" in lower):
        instruction = {
            "primitive": "polygon",
            "center": [0.62, 0.30],
            "radius": 0.13,
            "sides": 6 if ("六角" in ddl or "hexagon" in lower) else 5,
            "rotation": -12,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    elif ("楕円" in ddl) or ("oval" in lower) or ("ellipse" in lower) or ("蕾" in ddl) or ("花びら" in ddl) or ("petal" in lower) or ("bud" in lower):
        instruction = {
            "primitive": "ellipse",
            "center": [0.72, 0.32],
            "size": [0.18, 0.11],
            "rotation": -18,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    elif ("円" in ddl) or ("circle" in lower) or ("moon" in lower) or ("月" in ddl):
        instruction = {
            "primitive": "circle",
            "center": [0.72, 0.32],
            "radius": 0.09,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "note": "fallback from DDL",
        }
    else:
        instruction = {
            "primitive": "line",
            "from": [0.16, 0.78],
            "to": [0.84, 0.28],
            "rotation": -8,
            "color": color,
            "weight": weight,
            "note": "fallback from DDL",
        }

    arrangement: dict[str, object] | None = None
    explicit_count = count_hint_from_ddl(ddl)
    if ("散らす" in ddl) or ("点々" in ddl) or ("scatter" in lower) or ("dotted" in lower):
        arrangement = {"count": explicit_count or 11, "layout": "scatter", "margin": 0.18}
    elif ("並べる" in ddl) or ("line up" in lower):
        arrangement = {"count": explicit_count or 3, "layout": "horizontal", "margin": 0.1}
    elif explicit_count and explicit_count > 1:
        arrangement = {"count": explicit_count, "layout": "scatter", "margin": 0.18}

    ma_fallback = _fallback_needs_negative_space_support(ddl)
    if arrangement is not None:
        if ("波打つ軌跡" in ddl) or ("undulating trace" in lower):
            arrangement["path"] = "wave"
        elif ("斜めの帯" in ddl) or ("diagonal band" in lower):
            arrangement["path"] = "diagonal"
        elif ("右半分" in ddl) or ("right half" in lower):
            arrangement["path"] = "right_half"
        elif ("上から下" in ddl) or ("top to bottom" in lower):
            arrangement["layout"] = "vertical"
            arrangement["path"] = "top_to_bottom"
        elif ("左から右" in ddl) or ("left to right" in lower):
            arrangement["layout"] = "horizontal"
            arrangement["path"] = "left_to_right"
        count = int(arrangement.get("count") or 1)
        if count > 120:
            arrangement["count"] = min(count, 120)
            arrangement["density"] = "high" if count >= 300 else "medium"
            arrangement["cluster_count"] = 9 if count >= 300 else 5
            arrangement["fade"] = "directional" if arrangement.get("path") not in (None, "none") else "outward"
            arrangement["preserve_space"] = True
        elif count >= 40:
            arrangement["density"] = "medium"
            arrangement["cluster_count"] = 4
            arrangement["fade"] = "directional" if arrangement.get("path") not in (None, "none") else "outward"
            arrangement["preserve_space"] = True
        if color_cycle:
            arrangement["color_cycle"] = color_cycle
        instruction["arrangement"] = arrangement
    elif ma_fallback:
        instruction["arrangement"] = {
            "count": 3,
            "layout": "scatter",
            "margin": 0.26,
            "density": "low",
            "fade": "outward",
            "preserve_space": True,
        }
    elif color_cycle:
        instruction["note"] = f"{instruction['note']}; palette {'/'.join(color_cycle)}"

    instructions = [instruction]
    if ma_fallback:
        support_color = _fallback_support_color(background, color)
        instructions.append(
            {
                "primitive": "arc",
                "center": [0.28, 0.72],
                "radius": 0.075,
                "angle_start": 25,
                "angle_end": 205,
                "rotation": -18,
                "color": support_color,
                "weight": "silverpoint",
                "note": "fallback negative space support",
                "arrangement": {
                    "count": 3,
                    "layout": "radial",
                    "margin": 0.26,
                    "density": "low",
                    "fade": "outward",
                    "preserve_space": True,
                },
            }
        )

    return _finalize_score(
        Score.model_validate({"background": background, "instructions": instructions}),
        ddl,
    )


def _fallback_needs_negative_space_support(ddl: str) -> bool:
    lower = ddl.lower()
    return any(
        marker in ddl or marker in lower
        for marker in (
            "余白",
            "間",
            "気配",
            "記憶",
            "忘れ",
            "手紙",
            "新聞紙",
            "紙片",
            "窓",
            "鏡",
            "膜",
            "透明",
            "消え",
            "迷う",
            "漂う",
            "薄い",
            "negative space",
            "presence",
            "memory",
            "forgotten",
            "letter",
            "newspaper",
            "paper",
            "window",
            "mirror",
            "membrane",
            "transparent",
            "fade",
            "fading",
            "wander",
            "drift",
            "thin",
        )
    )


def _fallback_support_color(background: str, main_color: str) -> str:
    for color in ("gray", "blue", "red", "black", "white"):
        if color != background and color != main_color:
            return color
    return "white" if background in {"black", "blue"} else "black"


def _compose_retry_reason(score: Score, *, tokens_out: int | None, elapsed_ms: int) -> str:
    if not score.instructions:
        return "empty_instructions"
    return "none"


def _should_retry_compose_result(score: Score, *, tokens_out: int | None, elapsed_ms: int) -> bool:
    return _compose_retry_reason(score, tokens_out=tokens_out, elapsed_ms=elapsed_ms) != "none"


def _compose_retry_prompt(*, reason: str, lang: str) -> str:
    if lang == "en":
        return (
            "# Compact Stage 2 retry\n"
            f"The previous Stage 2 result was invalid or inefficient: {reason}.\n"
            "Submit a valid Score through the submit_score tool.\n"
            "Required: instructions must contain 1-5 drawable items.\n"
            "Allowed primitives: line, circle, ellipse, triangle, square, polygon, arc, cloudform.\n"
            "Allowed colors: white, black, blue, red, green, gray.\n"
            "For repeated marks in the same placement, use one instruction with arrangement instead of many instructions. Groups with different counts or placements may use separate instructions.\n"
            "Do not draw humans, faces, or animals as objects; convert them to abstract presence, weight, spacing, symmetry, or gaze pressure.\n"
            "Do not add unspecified helper lines or helper shapes. Apply adjectives and motion words to the requested primitive.\n"
            "Keep the result compact and do not restate the DDL."
        )
    return (
        "# 空描画リトライ / コンパクト描画リトライ\n"
        f"直前の Stage 2 出力は無効または非効率: {reason}。\n"
        "submit_score tool で有効な Score を提出する。\n"
        "必須: instructions には描画可能な命令を1〜5個入れる。空配列は禁止。\n"
        "使用できる primitive: line, circle, ellipse, triangle, square, polygon, arc, cloudform。\n"
        "使用できる color: white, black, blue, red, green, gray。\n"
        "同一配置の繰り返し図形は複数 instruction にせず、1 instruction + arrangement で表す。個数や配置が異なる群は別 instruction でよい。\n"
        "人・顔・動物を対象物として描かず、存在感、重心、余白、対称性、視線圧として抽象化する。\n"
        "未指定の補助線・補助図形を追加しない。形容・動作語は指定された primitive へ適用する。\n"
        "DDLを説明し直さず、JSONを短く保つ。"
    )


def _call_compose_detail(
    ddl: str,
    *,
    model: str | None = None,
    original_description: str | None = None,
    system_prompt: str | None = None,
    lang: str = "ja",
    composition_seed: int | None = None,
    include_trace: bool = False,
    tenkei: str = "auto",
    focus: str | None = None,
    variation_amplitude: str | None = None,
    variation_seed: int | None = None,
) -> ComposeDetail:
    stage1_ddl_in = ddl  # trace: Stage 1 output before plugin expansion
    plugin_expansion = DOCUMENT_PLUGIN_MANAGER.expand(
        ddl,
        source_text=original_description,
        lang=lang,
        seed_text=original_description or ddl,
    )
    plugin_expanded_ddl = plugin_expansion.ddl  # trace: after plugin expansion
    variation_report: dict = {}
    ddl = expand_intermediate_for_lang(
        plugin_expansion.ddl,
        lang=lang,
        context_text=original_description,
        composition_seed=composition_seed,
        plugin_instructions_present=bool(plugin_expansion.instructions),
        tenkei=tenkei,
        focus=focus,
        variation_amplitude=variation_amplitude,
        variation_seed=variation_seed,
        variation_report=variation_report,
    )
    stage15_ddl = ddl  # trace: Stage 1.5 output = Stage 2 input (== ComposeDetail.ddl)
    plugin_provenance = list(plugin_expansion.provenance)
    plugin_warnings = list(plugin_expansion.warnings)
    plugin_instructions = list(plugin_expansion.instructions)
    retry_count = 0
    retry_reasons: list[str] = []
    fallback_used = False
    attempts: list[dict] = [] if include_trace else []
    prompt_metadata: dict[str, str] = {}

    def _detail_fields() -> dict:
        fields: dict = {
            "source_ddl": stage1_ddl_in,
            "variation_moved_axes": list(variation_report.get("moved_axes") or []),
            "resolved_focus": variation_report.get("resolved_focus"),
            "stage2_prompt_digest": prompt_metadata.get("stage2_prompt_digest"),
        }
        if include_trace:
            fields.update(
                {
                    "plugin_expanded_ddl": plugin_expanded_ddl,
                    "stage15_ddl": stage15_ddl,
                    "stage2_raw_attempts": attempts,
                    "stage1_ddl_in": stage1_ddl_in,
                }
            )
        return fields

    def _record_fallback_attempt() -> None:
        if include_trace:
            attempts.append(
                {"attempt": len(attempts) + 1, "raw_text": None, "parse_ok": None, "fallback": True}
            )

    def invoke(prompt: str | None) -> tuple[Score, int | None, int | None, int]:
        started = time.perf_counter()
        sink: list[dict] | None = [] if include_trace else None

        def run_compose():
            kwargs: dict = {
                "model": model,
                "original_description": original_description,
                "system_prompt": prompt,
                "lang": lang,
                "prompt_metadata": prompt_metadata,
            }
            if sink is not None:  # only when tracing: keep the no-trace call byte-identical
                kwargs["trace_sink"] = sink
            try:
                return compose(ddl, **kwargs)
            except TypeError as e:
                if "unexpected keyword argument" not in str(e):
                    raise
                kwargs.pop("prompt_metadata", None)
                try:
                    return compose(ddl, **kwargs)
                except TypeError as retry_error:
                    if "unexpected keyword argument" not in str(retry_error):
                        raise
                return compose(ddl, model=model)

        value = _run_with_hard_timeout(
            "stage2",
            _hard_timeout_seconds("INKU_STAGE2_HARD_TIMEOUT_SECONDS"),
            run_compose,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if include_trace:
            raw = sink[-1] if sink else {"raw_text": None, "parse_ok": None}
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "raw_text": raw.get("raw_text"),
                    "parse_ok": raw.get("parse_ok"),
                    "fallback": False,
                }
            )
        if isinstance(value, tuple):
            return value[0], value[1], value[2], elapsed_ms
        return value, None, None, elapsed_ms

    try:
        score, tokens_in, tokens_out, elapsed_ms = invoke(system_prompt)
    except StageHardTimeoutError:
        _record_fallback_attempt()
        return ComposeDetail(
            score=_fallback_score_from_ddl(ddl, lang=lang),
            ddl=ddl,
            retry_reasons=["stage2_hard_timeout"],
            fallback_used=True,
            plugin_provenance=plugin_provenance,
            plugin_instructions=plugin_instructions,
            plugin_warnings=plugin_warnings,
            **_detail_fields(),
        )
    if score.instructions and not _should_retry_compose_result(score, tokens_out=tokens_out, elapsed_ms=elapsed_ms):
        return ComposeDetail(
            score=score,
            ddl=ddl,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            plugin_provenance=plugin_provenance,
            plugin_instructions=plugin_instructions,
            plugin_warnings=plugin_warnings,
            **_detail_fields(),
        )

    reason = _compose_retry_reason(score, tokens_out=tokens_out, elapsed_ms=elapsed_ms)
    retry_count += 1
    retry_reasons.append(reason)
    try:
        retry_score, retry_tokens_in, retry_tokens_out, _retry_elapsed_ms = invoke(
            _compose_retry_prompt(reason=reason, lang=lang)
        )
    except StageHardTimeoutError:
        fallback_used = True
        retry_reasons.append("stage2_retry_hard_timeout")
        retry_score = _fallback_score_from_ddl(ddl, lang=lang)
        retry_tokens_in = None
        retry_tokens_out = None
        _record_fallback_attempt()
    if retry_tokens_in is not None:
        tokens_in = (tokens_in or 0) + retry_tokens_in
    if retry_tokens_out is not None:
        tokens_out = (tokens_out or 0) + retry_tokens_out
    if not retry_score.instructions:
        fallback_used = True
        retry_reasons.append("fallback_after_empty_retry")
        retry_score = _fallback_score_from_ddl(ddl, lang=lang)
        if include_trace and attempts:
            attempts[-1]["fallback"] = True
    return ComposeDetail(
        score=retry_score,
        ddl=ddl,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        retry_count=retry_count,
        retry_reasons=retry_reasons,
        fallback_used=fallback_used,
        plugin_provenance=plugin_provenance,
            plugin_instructions=plugin_instructions,
        plugin_warnings=plugin_warnings,
        **_detail_fields(),
    )


def _call_interpret_detail(
    text: str,
    *,
    model: str | None = None,
    include_thinking: bool = False,
    system_prompt_prefix: str | None = None,
    lang: str = "ja",
    include_trace: bool = False,
    tenkei: str = "auto",
) -> InterpretDetail:
    trace_sink: list[str] | None = [] if include_trace else None
    prompt_metadata: dict[str, str] = {}

    def run_interpret():
        kwargs: dict = {
            "model": model,
            "include_thinking": include_thinking,
            "system_prompt_prefix": system_prompt_prefix,
            "lang": lang,
            "tenkei": tenkei,
            "prompt_metadata": prompt_metadata,
        }
        if trace_sink is not None:  # only when tracing: keep the no-trace call byte-identical
            kwargs["trace_sink"] = trace_sink
        try:
            return interpret_detail(text, **kwargs)
        except TypeError as e:
            if "unexpected keyword argument" not in str(e):
                raise
            kwargs.pop("prompt_metadata", None)
            try:
                return interpret_detail(text, **kwargs)
            except TypeError as retry_error:
                if "unexpected keyword argument" not in str(retry_error):
                    raise
            return interpret_detail(text, model=model, include_thinking=include_thinking)

    try:
        value = _run_with_hard_timeout(
            "stage1",
            _hard_timeout_seconds("INKU_STAGE1_HARD_TIMEOUT_SECONDS"),
            run_interpret,
        )
    except StageHardTimeoutError:
        return InterpretDetail(
            ddl=_fallback_ddl_from_text(text, lang=lang),
            fallback_used=True,
            fallback_reasons=["stage1_hard_timeout"],
        )
    raw = trace_sink[-1] if trace_sink else None
    if len(value) == 4:
        ddl, thinking, tokens_in, tokens_out = value
    else:
        ddl, thinking = value
        tokens_in = None
        tokens_out = None
    if not (ddl or "").strip():
        # v1.98: 空の Stage 1 出力はハードタイムアウトと同じ失敗として扱う。
        # 素通しすると展開層が空を返し、記述を持たない作品が描かれて保存される
        # （2026-05-05 以降 11 件確認）。
        return InterpretDetail(
            ddl=_fallback_ddl_from_text(text, lang=lang),
            thinking=thinking,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            fallback_used=True,
            fallback_reasons=["stage1_empty_output"],
            raw=raw,
            stage1_prompt_digest=prompt_metadata.get("stage1_prompt_digest"),
            stage1_prompt_base_digest=prompt_metadata.get("stage1_prompt_base_digest"),
        )
    return InterpretDetail(
        ddl=_sanitize_placement_words(ddl),
        thinking=thinking,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        raw=raw,
        stage1_prompt_digest=prompt_metadata.get("stage1_prompt_digest"),
        stage1_prompt_base_digest=prompt_metadata.get("stage1_prompt_base_digest"),
    )


def _assemble_trace(
    include_trace: bool,
    *,
    interpret_result: InterpretDetail | None = None,
    compose_detail: ComposeDetail,
    score_pre_coerce_dump: dict | None,
    coerce_report: dict,
) -> dict | None:
    """Assemble the RAW trace bundle (observation only). Never fails generation:
    a collection error is reported as a warning inside the trace instead."""
    if not include_trace:
        return None
    try:
        trace: dict = {}
        if interpret_result is not None:
            trace["stage1_raw"] = interpret_result.raw
            trace["stage1_thinking"] = interpret_result.thinking
            trace["stage1_ddl"] = interpret_result.ddl
        trace.update(
            {
                "plugin_expanded_ddl": compose_detail.plugin_expanded_ddl,
                "stage15_ddl": compose_detail.stage15_ddl,
                "stage2_raw_attempts": compose_detail.stage2_raw_attempts,
                "score_pre_coerce": score_pre_coerce_dump,
                "coerce_branch_counts": coerce_report.get("coerce_branch_counts", {}),
                "coerce_relation_input_count": coerce_report.get("coerce_relation_input_count", 0),
                "coerce_relation_output_count": coerce_report.get("coerce_relation_output_count", 0),
                "coerce_relation_dropped_count": coerce_report.get("coerce_relation_dropped_count", 0),
                "plugin_provenance": compose_detail.plugin_provenance,
                "plugin_warnings": compose_detail.plugin_warnings,
            }
        )
        return trace
    except Exception as exc:  # noqa: BLE001 — trace must never break generation
        return {"warning": f"trace collection failed: {exc}"}


class VariationSeedsRequest(BaseModel):
    amplitude: str = Field(..., description="変奏の強度 small / medium / large")
    count: int = Field(default=4, ge=1, le=8, description="採番する候補数")


class VariationSeedsResponse(BaseModel):
    amplitude: str
    seeds: list[int]


@app.post("/api/variation/seeds", response_model=VariationSeedsResponse)
def api_variation_seeds(
    req: VariationSeedsRequest, actor: dict = Depends(_current_user)
) -> VariationSeedsResponse:
    """変奏候補の seed を採番する。

    採番をサーバー側に置くのは、seed 空間の管理と重複回避を UI に持ち込まない
    ため（契約 §3.4）。展開は決定的なので、返した seed をそのまま /api/compose
    へ渡せば候補が再現できる。
    """
    amplitude = _validated_variation_amplitude(req.amplitude)
    if amplitude is None:
        raise HTTPException(status_code=422, detail="unknown variation amplitude")
    seeds: list[int] = []
    while len(seeds) < req.count:
        candidate = secrets.randbelow(2**31 - 1) + 1
        if candidate not in seeds:
            seeds.append(candidate)
    return VariationSeedsResponse(amplitude=amplitude, seeds=seeds)


@app.post("/api/compose", response_model=ComposeResponse, response_model_exclude_none=True)
def api_compose(req: ComposeRequest, actor: dict = Depends(_current_user)) -> ComposeResponse:
    render_seed, seed_text = _render_seed_from_text(req.seed_text, req.render_seed)
    t0 = time.perf_counter()
    instruction_lang_requested = _normalize_instruction_lang(req.instruction_lang)
    ui_lang = _normalize_ui_lang(req.ui_lang)
    instruction_lang_resolved = _resolve_instruction_lang(
        req.description or req.ddl,
        instruction_lang_requested,
        ui_lang=ui_lang,
    )
    resolved_stage2_model = _resolved_stage2_model(req.model, actor)
    resolved_tenkei = _resolved_tenkei(req.tenkei, actor, req.lineage_parent_node_id)
    resolved_variation_amplitude = _validated_variation_amplitude(req.variation_amplitude)
    resolved_variation_seed = (
        req.variation_seed if resolved_variation_amplitude is not None else None
    )
    try:
        compose_detail = _call_compose_detail(
            req.ddl,
            model=resolved_stage2_model,
            original_description=req.description,
            system_prompt=None,
            lang=instruction_lang_resolved,
            composition_seed=req.composition_seed,
            include_trace=req.include_trace,
            tenkei=resolved_tenkei,
            variation_amplitude=resolved_variation_amplitude,
            variation_seed=resolved_variation_seed,
        )
    except Exception as e:  # noqa: BLE001
        raise _stage_http_error("compose", 502) from e

    score_pre_coerce_dump = (
        compose_detail.score.model_dump(mode="json", by_alias=True)
        if req.include_trace
        else None
    )
    coerce_report: dict[str, object] = _coerce_relation_report(None, None)
    try:
        score = compose_detail.score
        ensure_renderable_score(score)
        if req.auto_repair:
            before_coerce = score
            branch_counts: dict[str, int] = {}
            score = coerce_score(
                score,
                branch_report=branch_counts,
                ddl=_coerce_context(compose_detail.ddl, req.description),
                tenkei=resolved_tenkei,
                plugin_instructions_present=bool(compose_detail.plugin_instructions),
            )
            coerce_report = {**_coerce_relation_report(before_coerce, score), "coerce_branch_counts": branch_counts}
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("compose", 502) from e

    score = _score_with_plugin_instructions(score, compose_detail.plugin_instructions)

    normalized_compose_ddl = compose_detail.ddl.lower()
    if "雲形" in compose_detail.ddl or "cloudform" in normalized_compose_ddl:
        score = _finalize_score(score, compose_detail.ddl)
        coerce_report["coerce_relation_output_count"] = _score_relation_count(score)

    canvas_aspect = _validated_canvas_aspect(req.canvas_aspect)
    score = _score_with_canvas(score, canvas_aspect)
    render_metadata = {
        **_render_metadata(req.catalog_id, canvas_aspect=_score_canvas_aspect_value(score)),
        "stage2_prompt_digest": compose_detail.stage2_prompt_digest,
        "instruction_lang_requested": instruction_lang_requested,
        "instruction_lang_resolved": instruction_lang_resolved,
        "ui_lang": ui_lang,
        "render_seed": render_seed,
        "render_wild": req.wild,
        "composition_seed": req.composition_seed,
        "tenkei": resolved_tenkei,
        "focus": compose_detail.resolved_focus,
        "variation_amplitude": resolved_variation_amplitude,
        "variation_seed": resolved_variation_seed,
        "seed_text": seed_text,
        "interpretation_seed": req.interpretation_seed,
    }
    try:
        svg, render_metadata = _render_with_metadata(score, render_metadata)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("render", 500) from e
    render_metadata = {
        **render_metadata,
        **_render_hash_metadata(
            input_text=req.description or req.ddl,
            ddl=compose_detail.ddl,
            score=score,
            svg=svg,
            catalog_id=req.catalog_id,
            render_metadata=render_metadata,
        ),
    }

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    _carriage = _carriage_warnings(compose_detail.ddl, score) or None
    return ComposeResponse(
        ddl=compose_detail.ddl,
        source_ddl=compose_detail.source_ddl or None,
        plugin_provenance=compose_detail.plugin_provenance,
        plugin_warnings=compose_detail.plugin_warnings,
        carriage_warnings=_carriage,
        score=score,
        svg=svg,
        stage2_model=resolved_stage2_model,
        variation_moved_axes=compose_detail.variation_moved_axes,
        **render_metadata,
        elapsed_ms=elapsed_ms,
        tokens_in=compose_detail.tokens_in,
        tokens_out=compose_detail.tokens_out,
        retry_count=compose_detail.retry_count,
        retry_reasons=compose_detail.retry_reasons,
        fallback_used=compose_detail.fallback_used,
        **coerce_report,
        trace=_assemble_trace(
            req.include_trace,
            compose_detail=compose_detail,
            score_pre_coerce_dump=score_pre_coerce_dump,
            coerce_report=coerce_report,
        ),
    )


@app.post("/api/interpret")
def api_interpret(req: InterpretRequest, actor: dict = Depends(_current_user)) -> dict:
    instruction_lang_requested = _normalize_instruction_lang(req.instruction_lang)
    source_text = req.description
    # Stage 1 が読むのは、記述に文脈を注入したあとの文字列。注入しない client は
    # stage1_input を送ってこないので、そのときは記述そのものを読む。
    stage1_text = req.stage1_input or req.description
    ui_lang = _normalize_ui_lang(req.ui_lang)
    instruction_lang_resolved = _resolve_instruction_lang(
        source_text, instruction_lang_requested, ui_lang=ui_lang
    )
    resolved_tenkei = req.tenkei or "auto"
    try:
        if resolved_tenkei == "none" and DOCUMENT_PLUGIN_MANAGER.is_pure_invocation(stage1_text):
            # v1.96 純明示バイパス: プラグイン語だけの入力は Stage 1 を経ず転記する
            detail = InterpretDetail(ddl=stage1_text.strip(), thinking=None, raw=None)
        else:
            detail = _call_interpret_detail(
                stage1_text,
                model=_resolved_stage1_model(req.model, actor),
                include_thinking=req.include_thinking,
                system_prompt_prefix=None,
                lang=instruction_lang_resolved,
                tenkei=resolved_tenkei,
            )
    except Exception as e:  # noqa: BLE001
        raise _stage_http_error("interpret", 502) from e
    plugin_provenance: list[dict[str, str]] = []
    plugin_warnings: list[str] = []
    if req.expand_intermediate:
        plugin_expansion = DOCUMENT_PLUGIN_MANAGER.expand(
            detail.ddl,
            source_text=source_text,
            lang=instruction_lang_resolved,
            seed_text=source_text,
        )
        detail.ddl = expand_intermediate_for_lang(
            plugin_expansion.ddl,
            lang=instruction_lang_resolved,
            context_text=source_text,
            plugin_instructions_present=bool(plugin_expansion.instructions),
            tenkei=resolved_tenkei,
        )
        plugin_provenance = list(plugin_expansion.provenance)
        plugin_warnings = list(plugin_expansion.warnings)
    data: dict = {
        "ddl": detail.ddl,
        "thinking": detail.thinking,
        "instruction_lang_requested": instruction_lang_requested,
        "instruction_lang_resolved": instruction_lang_resolved,
        "ui_lang": ui_lang,
    }
    if detail.stage1_prompt_digest is not None:
        data["stage1_prompt_digest"] = detail.stage1_prompt_digest
    if detail.stage1_prompt_base_digest is not None:
        data["stage1_prompt_base_digest"] = detail.stage1_prompt_base_digest
    if plugin_provenance:
        data["plugin_provenance"] = plugin_provenance
    if plugin_warnings:
        data["plugin_warnings"] = plugin_warnings
    if detail.tokens_in is not None:
        data["tokens_in"] = detail.tokens_in
    if detail.tokens_out is not None:
        data["tokens_out"] = detail.tokens_out
    if detail.fallback_used:
        data["fallback_used"] = detail.fallback_used
        data["fallback_reasons"] = detail.fallback_reasons
    return data


def _strip_anthropic_prefix(model: str) -> str:
    return model.removeprefix("anthropic:")


class StageHardTimeoutError(TimeoutError):
    pass


def _hard_timeout_seconds(env_name: str, default: str = "120") -> float:
    return max(0.1, float(os.getenv(env_name, default)))


def _run_with_hard_timeout(label: str, timeout_seconds: float, operation):
    stage_slots = _stage_slots
    if not stage_slots.acquire(timeout=timeout_seconds):
        _increment_stage_stat("rejected")
        raise StageHardTimeoutError(f"{label} could not start within {timeout_seconds:g}s stage capacity timeout")
    try:
        future = _stage_executor.submit(operation)
    except Exception:
        stage_slots.release()
        raise
    _increment_stage_stat("submitted")
    future.add_done_callback(lambda _future, slots=stage_slots: slots.release())
    try:
        result = future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        _increment_stage_stat("timed_out")
        future.cancel()
        raise StageHardTimeoutError(f"{label} exceeded {timeout_seconds:g}s hard timeout") from exc
    except Exception:
        _increment_stage_stat("failed")
        raise
    _increment_stage_stat("completed")
    return result


def _fallback_background_from_text(text: str, *, lang: str) -> tuple[str, str]:
    lower = text.lower()
    if lang == "en":
        has_dawn = "dawn" in lower or "daybreak" in lower or "sunrise" in lower
        is_dark = not has_dawn and any(marker in lower for marker in ("night", "dark", "black"))
        background = "black" if is_dark else "white"
        foreground = "white" if background == "black" else "black"
        return background, foreground
    has_dawn = any(marker in text for marker in ("夜明け", "明け方", "朝焼け"))
    is_dark = not has_dawn and any(marker in text for marker in ("夜", "黒", "暗"))
    background = "黒" if is_dark else "白"
    foreground = "白" if background == "黒" else "黒"
    return background, foreground


def _fallback_ddl_from_text(text: str, *, lang: str) -> str:
    if lang == "en":
        background, foreground = _fallback_background_from_text(text, lang=lang)
        return (
            f"Fill background with {background}. "
            f"Draw three thin {foreground} diagonal lines. "
            "Scatter twelve small gray dots across the whole canvas."
        )
    background, foreground = _fallback_background_from_text(text, lang=lang)
    accent = "青" if foreground == "黒" and ("白" in text or "雪" in text) else "灰色"
    return (
        f"背景を{background}で埋める。"
        f"{foreground}い細い斜めの線を三本並べる。"
        f"{accent}の小さな点を十二個、画面全体に点々と散らす。"
    )


def _demo_instruction_system(lang: str) -> str:
    if lang == "en":
        return (
            "Generate one short, concrete visual prompt for inku. "
            "Return only the prompt text. Keep it under 40 words. "
            "Use sensory detail and a clear scene, but do not explain."
        )
    return (
        "inkuのデモ描画に使う短い指示文を1つ生成してください。"
        "返答は指示文のみ。40語以内。"
        "情景、質感、動きが感じられる具体的な文章にし、説明は不要です。"
    )


def _generate_demo_instruction(seed_phrase: str, *, model: str | None, lang: str) -> str:
    # No env fallback and no literal: both named ovms models, so an unconfigured
    # demo asked a withdrawn provider for its instruction. provider_for_model
    # reads the Stage 1 default when the model is None, which is the same answer
    # every other caller gets.
    settings = _db.get_model_settings()
    provider, model_id = provider_for_model(model or None, stage="stage1", settings=settings)
    if provider == "anthropic":
        import anthropic

        connection = connection_for("anthropic", settings)
        kwargs = {"api_key": connection["api_key"]} if connection.get("api_key") else {}
        if connection.get("base_url"):
            kwargs["base_url"] = connection["base_url"]
        client = anthropic.Anthropic(**kwargs)
        resp = client.messages.create(
            model=model_id,
            max_tokens=180,
            temperature=0.9,
            system=_demo_instruction_system(lang),
            messages=[{"role": "user", "content": seed_phrase}],
        )
        parts = [getattr(block, "text", "") for block in resp.content if getattr(block, "type", "") == "text"]
        text = "\n".join(parts).strip()
    elif provider == "gemini":
        connection = connection_for("gemini", settings)
        api_key = connection.get("api_key") or ""
        if not api_key:
            raise RuntimeError("Gemini API key is not configured")
        base_url = str(connection.get("base_url") or "https://generativelanguage.googleapis.com").rstrip("/")
        url = f"{base_url}/v1beta/models/{model_id}:generateContent?key={api_key}"
        body = {
            "systemInstruction": {"parts": [{"text": _demo_instruction_system(lang)}]},
            "contents": [{"role": "user", "parts": [{"text": seed_phrase}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 180},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "120"))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "\n".join(str(part.get("text", "")) for part in parts).strip()
    else:
        from openai import OpenAI

        connection = connection_for(provider, settings)
        client = OpenAI(base_url=connection["base_url"], api_key=connection.get("api_key") or "none")
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": _demo_instruction_system(lang)},
                {"role": "user", "content": seed_phrase},
            ],
            temperature=0.9,
            max_tokens=180,
        )
        text = (resp.choices[0].message.content or "").strip()
    text = text.strip().strip("\"'“”‘’")
    if not text:
        raise ValueError("empty demo instruction")
    return text


@app.post("/api/demo/instruction", response_model=DemoInstructionResponse)
def api_demo_instruction(req: DemoInstructionBody, _actor: dict = Depends(_current_user)) -> DemoInstructionResponse:
    instruction_lang = _resolve_instruction_lang(
        req.seed_phrase,
        _normalize_instruction_lang(req.instruction_lang),
        ui_lang=_normalize_ui_lang(req.ui_lang),
    )
    try:
        instruction = _generate_demo_instruction(req.seed_phrase, model=req.model, lang=instruction_lang)
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("demo instruction", 502) from e
    return DemoInstructionResponse(instruction=instruction)


@app.post("/api/render-score", response_model=RenderScoreResponse, response_model_exclude_none=True)
def api_render_score(req: RenderScoreRequest, _actor: dict = Depends(_current_user)) -> RenderScoreResponse:
    render_seed, seed_text = _render_seed_from_text(req.seed_text, req.render_seed)
    try:
        score = coerce_score(Score.model_validate(req.score))
        canvas_aspect = _validated_canvas_aspect_override(req.canvas_aspect)
        if canvas_aspect is not None:
            score = _score_with_canvas(score, canvas_aspect)
        catalog_id = _resolved_catalog_id(req.catalog_id)
        render_metadata = {
            **_render_metadata(catalog_id, canvas_aspect=_score_canvas_aspect_value(score)),
            "render_seed": render_seed,
            "render_wild": req.wild,
            "composition_seed": req.composition_seed,
            "interpretation_seed": req.interpretation_seed,
            "seed_text": seed_text,
        }
        svg, render_metadata = _render_with_metadata(score, render_metadata)
        render_metadata = {
            **render_metadata,
            **_render_hash_metadata(
                input_text=req.input,
                ddl=req.ddl,
                score=score,
                svg=svg,
                catalog_id=catalog_id,
                render_metadata=render_metadata,
            ),
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("score render", 422) from e
    return RenderScoreResponse(score=score, svg=svg, catalog_id=catalog_id, **render_metadata)


@app.post("/api/render-svg")
def api_render_svg(req: RenderSvgRequest, _actor: dict = Depends(_current_user)) -> Response:
    render_seed, _ = _render_seed_from_text(req.seed_text, req.render_seed)
    try:
        svg = _render_score_svg(
            req.score,
            catalog_id=req.catalog_id,
            canvas_aspect=req.canvas_aspect,
            svg_profile=req.svg_profile,
            render_seed=render_seed,
            wild=req.wild,
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("svg render", 422) from e
    return Response(content=svg, media_type="image/svg+xml; charset=utf-8")


def _add_history_item(
    *,
    actor: dict,
    input_text: str,
    ddl: str | None,
    score: Score,
    svg: str,
    at: int,
    expanded_ddl: str | None = None,
    interpret_fallback: str | None = None,
    elapsed_ms: int = 0,
    stage1_model: str | None = None,
    stage2_model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    catalog_id: str | None = None,
    save_artifacts: bool = True,
    render_metadata: dict | None = None,
    source_text: str | None = None,
    display_label: str | None = None,
    batch_line_number: int | None = None,
    batch_run_id: str | None = None,
    history_visibility: str = "normal",
    lineage_parent_node_id: str | None = None,
    derivation_kind: str | None = None,
    derivation_metadata: dict[str, object] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    item_id = str(uuid.uuid4())
    score_dict = score.model_dump(by_alias=True)
    prefix = _output_prefix(actor["id"], item_id, at)
    metadata = dict(render_metadata or {})
    metadata.setdefault("ddl_version", DDL_VERSION)
    metadata.setdefault("ddl_engine_version", DDL_ENGINE_VERSION)
    if not metadata.get("render_hash"):
        metadata.update(
            _render_hash_metadata(
                input_text=input_text,
                ddl=ddl,
                score=score_dict,
                svg=svg,
                catalog_id=catalog_id,
                render_metadata=metadata,
            )
        )
    try:
        item_dict = _db.add_item({
        "id": item_id,
        "user_id": actor["id"],
        "output_path": str(prefix),
        "input": input_text,
        "ddl": _sanitize_placement_words(ddl) if ddl else ddl,
        "expanded_ddl": _sanitize_placement_words(expanded_ddl) if expanded_ddl else expanded_ddl,
        "interpret_fallback": interpret_fallback,
        "score": score_dict,
        "svg": svg,
        "at": at,
        "elapsed_ms": elapsed_ms,
        "stage1_model": stage1_model,
        "stage2_model": stage2_model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
"catalog_id": catalog_id,
"source_text": source_text if source_text is not None else input_text,
"display_label": display_label,
"batch_line_number": batch_line_number,
"batch_run_id": batch_run_id,
"history_visibility": history_visibility,
"lineage_parent_node_id": lineage_parent_node_id,
"derivation_kind": derivation_kind,
"derivation_metadata": derivation_metadata or {},
"idempotency_key": idempotency_key,
**metadata,
    })
    except ValueError as exc:
        status_code = 404 if str(exc) == "lineage parent not found" else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if save_artifacts:
        item_dict.update(metadata)
        item_dict["render_metadata"] = metadata
        _submit_history_artifact_save(item_dict)
    else:
        item_dict.update(metadata)
    return item_dict


def _paint_events(
    req: PaintRequest,
    idempotency_key: str | None,
    actor: dict,
) -> Iterator[dict[str, object]]:
    """Run a paint and yield its stage boundaries.

    Both /api/paint and /api/paint/stream consume this generator, so the two
    endpoints cannot drift apart. Events are ``stage1`` (interpretation is
    finished, its DDL and token counts are known) followed by ``done`` (the
    complete PaintResponse).
    """
    t0 = time.perf_counter()
    source_text = req.description
    # Stage 1 が読むのは、記述に文脈を注入したあとの文字列 (api_interpret と同じ規約)。
    stage1_text = req.stage1_input or req.description
    instruction_lang_requested = _normalize_instruction_lang(req.instruction_lang)
    ui_lang = _normalize_ui_lang(req.ui_lang)
    instruction_lang_resolved = _resolve_instruction_lang(
        source_text, instruction_lang_requested, ui_lang=ui_lang
    )
    catalog_id = _resolved_paint_catalog_id(req.catalog_id, random_catalog=req.random_color_catalog)
    resolved_stage1_model = _resolved_stage1_model(req.stage1_model, actor)
    resolved_stage2_model = _resolved_stage2_model(req.stage2_model, actor)
    render_seed, seed_text = _render_seed_from_text(req.seed_text, req.render_seed)
    resolved_tenkei = _resolved_tenkei(req.tenkei, actor, req.lineage_parent_node_id)
    resolved_variation_amplitude = _validated_variation_amplitude(req.variation_amplitude)
    resolved_variation_seed = (
        req.variation_seed if resolved_variation_amplitude is not None else None
    )
    try:
        if resolved_tenkei == "none" and DOCUMENT_PLUGIN_MANAGER.is_pure_invocation(stage1_text):
            # v1.96 純明示バイパス: プラグイン語だけの入力は Stage 1 を経ず転記する
            interpret_detail_result = InterpretDetail(
                ddl=stage1_text.strip(), raw=stage1_text.strip() if req.include_trace else None
            )
        else:
            interpret_detail_result = _call_interpret_detail(
                stage1_text,
                model=resolved_stage1_model,
                include_thinking=req.include_thinking,
                lang=instruction_lang_resolved,
                include_trace=req.include_trace,
                tenkei=resolved_tenkei,
            )
    except Exception as e:  # noqa: BLE001
        raise _stage_http_error("interpret", 502) from e
    ddl = interpret_detail_result.ddl
    t1 = time.perf_counter()
    stage1_event = {
        "event": "stage1",
        # 入力側 DDL (展開前)。done イベントの ddl は展開後なので別物。
        "ddl": ddl,
        "thinking": interpret_detail_result.thinking,
        "stage1_model": resolved_stage1_model,
        "stage2_model": resolved_stage2_model,
        "tokens_in": interpret_detail_result.tokens_in,
        "tokens_out": interpret_detail_result.tokens_out,
        "elapsed_ms": int((t1 - t0) * 1000),
        "interpret_fallback_used": interpret_detail_result.fallback_used,
    }
    if interpret_detail_result.stage1_prompt_digest is not None:
        stage1_event["stage1_prompt_digest"] = interpret_detail_result.stage1_prompt_digest
    if interpret_detail_result.stage1_prompt_base_digest is not None:
        stage1_event["stage1_prompt_base_digest"] = (
            interpret_detail_result.stage1_prompt_base_digest
        )
    yield stage1_event
    try:
        compose_detail = _call_compose_detail(
            ddl,
            model=resolved_stage2_model,
            original_description=source_text,
            lang=instruction_lang_resolved,
            include_trace=req.include_trace,
            tenkei=resolved_tenkei,
            variation_amplitude=resolved_variation_amplitude,
            variation_seed=resolved_variation_seed,
        )
    except Exception as e:  # noqa: BLE001
        raise _stage_http_error("compose", 502) from e

    ddl = compose_detail.ddl
    # trace: capture the pre-coerce Score before any coerce/ensure mutation.
    score_pre_coerce_dump = (
        compose_detail.score.model_dump(mode="json", by_alias=True)
        if req.include_trace
        else None
    )
    coerce_report: dict[str, object] = _coerce_relation_report(None, None)
    try:
        score = compose_detail.score
        ensure_renderable_score(score)
        if req.auto_repair:
            before_coerce = score
            branch_counts: dict[str, int] = {}
            score = coerce_score(
                score,
                branch_report=branch_counts,
                ddl=_coerce_context(ddl, source_text),
                tenkei=resolved_tenkei,
                plugin_instructions_present=bool(compose_detail.plugin_instructions),
            )
            coerce_report = {**_coerce_relation_report(before_coerce, score), "coerce_branch_counts": branch_counts}
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("compose", 502) from e

    score = _score_with_plugin_instructions(score, compose_detail.plugin_instructions)

    normalized_compose_ddl = compose_detail.ddl.lower()
    if "雲形" in compose_detail.ddl or "cloudform" in normalized_compose_ddl:
        score = _finalize_score(score, compose_detail.ddl)
        coerce_report["coerce_relation_output_count"] = _score_relation_count(score)

    canvas_aspect = _validated_canvas_aspect(req.canvas_aspect)
    score = _score_with_canvas(score, canvas_aspect)
    render_metadata = {
        **_render_metadata(catalog_id, canvas_aspect=_score_canvas_aspect_value(score)),
        "stage1_prompt_digest": interpret_detail_result.stage1_prompt_digest,
        "stage1_prompt_base_digest": interpret_detail_result.stage1_prompt_base_digest,
        "stage2_prompt_digest": compose_detail.stage2_prompt_digest,
        "instruction_lang_requested": instruction_lang_requested,
        "instruction_lang_resolved": instruction_lang_resolved,
        "ui_lang": ui_lang,
        "render_seed": render_seed,
        "render_wild": req.wild,
        "composition_seed": req.composition_seed,
        "tenkei": resolved_tenkei,
        "focus": compose_detail.resolved_focus,
        "variation_amplitude": resolved_variation_amplitude,
        "variation_seed": resolved_variation_seed,
        "seed_text": seed_text,
        "interpretation_seed": req.interpretation_seed,
    }
    if compose_detail.plugin_provenance:
        render_metadata["plugin_provenance"] = compose_detail.plugin_provenance
    if compose_detail.plugin_warnings:
        render_metadata["plugin_warnings"] = compose_detail.plugin_warnings
    t2 = time.perf_counter()
    try:
        svg, render_metadata = _render_with_metadata(score, render_metadata)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("render", 500) from e
    artifact_input = req.history_input or source_text
    artifact_catalog_id = None if catalog_id == "default" else catalog_id
    render_metadata = {
        **render_metadata,
        **_render_hash_metadata(
            input_text=artifact_input,
            ddl=ddl,
            score=score,
            svg=svg,
            catalog_id=artifact_catalog_id,
            render_metadata=render_metadata,
        ),
    }
    elapsed_stage1_ms = int((t1 - t0) * 1000)
    elapsed_stage2_ms = int((t2 - t1) * 1000)
    elapsed_total_ms = int((time.perf_counter() - t0) * 1000)
    history_id = None
    history_at = None
    saved_identity: dict[str, object] = {}
    idempotent_replay = False
    save_artifacts = req.save_artifacts if req.save_artifacts is not None else req.save_history
    if req.save_history:
        history_at = req.history_at or int(time.time() * 1000)
        item = _add_history_item(
            actor=actor,
            input_text=req.history_input or source_text,
            ddl=compose_detail.source_ddl or ddl,
            expanded_ddl=ddl,
            interpret_fallback=(
                (interpret_detail_result.fallback_reasons or ["stage1_fallback"])[0]
                if interpret_detail_result.fallback_used
                else None
            ),
            score=score,
            svg=svg,
            at=history_at,
            elapsed_ms=elapsed_total_ms,
            stage1_model=resolved_stage1_model,
            stage2_model=resolved_stage2_model,
            tokens_in=(interpret_detail_result.tokens_in or 0) + (compose_detail.tokens_in or 0) or None,
            tokens_out=(interpret_detail_result.tokens_out or 0) + (compose_detail.tokens_out or 0) or None,
            catalog_id=artifact_catalog_id,
            save_artifacts=save_artifacts,
            render_metadata=render_metadata,
            source_text=req.history_source_text or source_text,
            display_label=req.history_display_label,
            batch_line_number=req.batch_line_number,
            batch_run_id=req.batch_run_id,
            history_visibility=req.history_visibility,
            lineage_parent_node_id=req.lineage_parent_node_id,
            derivation_kind=req.derivation_kind,
            derivation_metadata={
                **req.derivation_metadata,
                "plugin_provenance": compose_detail.plugin_provenance,
                "plugin_warnings": compose_detail.plugin_warnings,
            },
            idempotency_key=idempotency_key,
        )
        history_id = item["id"]
        idempotent_replay = bool(item.get("_idempotent_replay"))
        saved_identity = {
            "description_hash": item.get("description_hash"),
            "lineage_node_id": item.get("lineage_node_id"),
            "lineage_parent_node_id": item.get("lineage_parent_node_id"),
            "derivation_kind": item.get("derivation_kind"),
        }
    elif save_artifacts:
        history_at = req.history_at or int(time.time() * 1000)
        item_id = str(uuid.uuid4())
        score_dict = score.model_dump(by_alias=True)
        _submit_history_artifact_save({
            "id": item_id,
            "user_id": actor["id"],
            "output_path": str(_output_prefix(actor["id"], item_id, history_at)),
            "input": req.history_input or source_text,
            "ddl": _sanitize_placement_words(ddl) if ddl else ddl,
            "score": score_dict,
            "svg": svg,
            "at": history_at,
            "stage1_model": resolved_stage1_model,
            "stage2_model": resolved_stage2_model,
            "render_metadata": render_metadata,
        })
    user_generation_count = None
    if req.count_generation and not idempotent_replay:
        user_generation_count = _db.increment_user_generation_count(actor["id"])
        if user_generation_count is None:
            raise HTTPException(status_code=404, detail="user not found")
    paint_trace = _assemble_trace(
        req.include_trace,
        interpret_result=interpret_detail_result,
        compose_detail=compose_detail,
        score_pre_coerce_dump=score_pre_coerce_dump,
        coerce_report=coerce_report,
    )
    _carriage = _carriage_warnings(compose_detail.ddl, score) or None
    response = PaintResponse(
        description=source_text,
        ddl=ddl,
        source_ddl=compose_detail.source_ddl or None,
        thinking=interpret_detail_result.thinking,
        carriage_warnings=_carriage,
        score=score,
        svg=svg,
        stage1_model=resolved_stage1_model,
        stage2_model=resolved_stage2_model,
        variation_moved_axes=compose_detail.variation_moved_axes,
        **render_metadata,
        history_id=history_id,
        history_at=history_at,
        **saved_identity,
        elapsed_stage1_ms=elapsed_stage1_ms,
        elapsed_stage2_ms=elapsed_stage2_ms,
        elapsed_total_ms=elapsed_total_ms,
        tokens_in_stage1=interpret_detail_result.tokens_in,
        tokens_out_stage1=interpret_detail_result.tokens_out,
        tokens_in_stage2=compose_detail.tokens_in,
        tokens_out_stage2=compose_detail.tokens_out,
        interpret_fallback_used=interpret_detail_result.fallback_used,
        interpret_fallback_reasons=interpret_detail_result.fallback_reasons,
        compose_retry_count=compose_detail.retry_count,
        compose_retry_reasons=compose_detail.retry_reasons,
        compose_fallback_used=compose_detail.fallback_used,
        user_generation_count=user_generation_count,
        catalog_id=catalog_id,
        **coerce_report,
        trace=paint_trace,
    )
    yield {"event": "done", "response": response}


@app.post("/api/paint", response_model=PaintResponse, response_model_exclude_none=True)
def api_paint(
    req: PaintRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> PaintResponse:
    for event in _paint_events(req, idempotency_key, actor):
        if event["event"] == "done":
            return event["response"]  # type: ignore[return-value]
    raise _unexpected_http_error("paint", 500)


@app.post("/api/paint/stream")
def api_paint_stream(
    req: PaintRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> StreamingResponse:
    """Newline-delimited JSON variant of /api/paint.

    The response is already committed once the first event is written, so a
    failure after that point is reported as an in-band ``error`` event instead
    of an HTTP status.
    """

    def lines() -> Iterator[str]:
        try:
            for event in _paint_events(req, idempotency_key, actor):
                if event["event"] == "done":
                    response = event["response"]
                    payload = {
                        "event": "done",
                        **response.model_dump(mode="json", by_alias=True, exclude_none=True),
                    }
                else:
                    payload = event
                yield json.dumps(payload, ensure_ascii=False) + "\n"
        except HTTPException as e:
            yield json.dumps(
                {"event": "error", "status": e.status_code, "detail": e.detail},
                ensure_ascii=False,
            ) + "\n"
        except Exception as e:  # noqa: BLE001
            _logger.exception("paint stream failed: %s", e)
            yield json.dumps(
                {"event": "error", "status": 500, "detail": "unexpected error"},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/user-groups", response_model=list[UserGroupItem])
def api_user_groups_list(actor: dict = Depends(_user_manager)) -> list[UserGroupItem]:
    groups = _db.list_user_groups()
    if actor["role"] == "group_lead":
        groups = [group for group in groups if group["id"] == actor.get("group_id")]
    return [UserGroupItem(**group) for group in groups]


@app.post("/api/user-groups", response_model=UserGroupItem)
def api_user_groups_create(body: UserGroupCreateBody, actor: dict = Depends(_user_manager)) -> UserGroupItem:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="only administrators can create groups")
    try:
        return UserGroupItem(**_db.add_user_group(body.name))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("group create", 409) from e


@app.patch("/api/user-groups/{group_id}", response_model=UserGroupItem)
def api_user_groups_update(
    group_id: str,
    body: UserGroupUpdateBody,
    actor: dict = Depends(_user_manager),
) -> UserGroupItem:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="only administrators can update groups")
    try:
        group = _db.update_user_group(group_id, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("group update", 409) from e
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    return UserGroupItem(**group)


@app.delete("/api/user-groups/{group_id}")
def api_user_groups_delete(group_id: str, actor: dict = Depends(_user_manager)) -> dict[str, bool]:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="only administrators can delete groups")
    try:
        found = _db.delete_user_group(group_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail="group not found")
    return {"ok": True}


@app.get("/api/users", response_model=list[UserAccountItem])
def api_users_list(actor: dict = Depends(_user_manager)) -> list[UserAccountItem]:
    return [UserAccountItem(**user) for user in _db.list_users_for_actor(actor)]


@app.post("/api/users", response_model=UserAccountItem)
def api_users_create(body: UserAccountCreateBody, actor: dict = Depends(_user_manager)) -> UserAccountItem:
    if actor["role"] == "group_lead":
        if body.role != "user" or body.group_id != actor.get("group_id"):
            raise HTTPException(status_code=403, detail="group leads can create users only in their own group")
    try:
        user = _db.add_user(
            username=body.username,
            email=body.email,
            password=body.password,
            role=body.role,
            group_id=body.group_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("user create", 409) from e
    return UserAccountItem(**user)


@app.patch("/api/users/{user_id}", response_model=UserAccountItem)
def api_users_update(
    user_id: str,
    body: UserAccountUpdateBody,
    actor: dict = Depends(_user_manager),
) -> UserAccountItem:
    if actor["role"] == "group_lead":
        if body.role and body.role != "user":
            raise HTTPException(status_code=403, detail="group leads cannot change user roles")
        if body.group_id is not None and body.group_id != actor.get("group_id"):
            raise HTTPException(status_code=403, detail="group leads cannot move users outside their group")
    try:
        user = _db.update_user(user_id, actor=actor, **body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("user update", 409) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@app.delete("/api/users/{user_id}")
def api_users_delete(
    user_id: str,
    cascade: bool = Query(default=False),
    actor: dict = Depends(_user_manager),
) -> dict[str, bool]:
    try:
        found = _db.delete_user(user_id, cascade=cascade, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True}


@app.get("/api/history/lineage-groups", response_model=HistoryLineageGroupListResponse, response_model_exclude_none=True)
def api_history_lineage_groups(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=100),
    trashed: bool = Query(default=False),
    starred: bool = Query(default=False),
    q: str = Query(default="", max_length=200),
    actor: dict = Depends(_current_user),
) -> HistoryLineageGroupListResponse:
    groups, total = _db.list_lineage_groups(
        actor["id"], offset=offset, limit=limit, trashed=trashed, query_text=q, starred=starred
    )
    return HistoryLineageGroupListResponse(groups=groups, total=total, offset=offset, limit=limit)


@app.get("/api/history/lineage-groups/{root_node_id}/items", response_model=HistoryListResponse, response_model_exclude_none=True)
def api_history_lineage_group_items(
    root_node_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=10_000),
    trashed: bool = Query(default=False),
    starred: bool = Query(default=False),
    q: str = Query(default="", max_length=200),
    actor: dict = Depends(_current_user),
) -> HistoryListResponse:
    items, total = _db.list_lineage_group_items(
        actor["id"], root_node_id, offset=offset, limit=limit, trashed=trashed, query_text=q, starred=starred
    )
    if total == 0:
        root = _db.get_lineage(actor["id"], root_node_id, descendant_depth=0, node_limit=1)
        if root is None:
            raise HTTPException(status_code=404, detail="lineage not found")
    return HistoryListResponse(items=items, total=total, offset=offset, limit=limit)


@app.get("/api/history", response_model=HistoryListResponse, response_model_exclude_none=True)
def api_history_get(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    trashed: bool = Query(default=False),
    starred: bool = Query(default=False),
    q: str = Query(default="", max_length=200),
    anchor_id: str | None = Query(default=None, max_length=100),
    actor: dict = Depends(_current_user),
) -> HistoryListResponse:
    if anchor_id:
        position = _db.item_position(actor["id"], anchor_id, trashed=trashed, starred=starred)
        if position is not None:
            offset = (position // limit) * limit
    items, total = _db.list_items(
        actor["id"],
        offset=offset,
        limit=limit,
        trashed=trashed,
        query_text=q,
        starred=starred,
    )
    return HistoryListResponse(items=items, total=total, offset=offset, limit=limit)



@app.post("/api/history/export-animation")
def api_history_export_animation(
    body: AnimationExportBody,
    actor: dict = Depends(_current_user),
) -> Response:
    ids = list(dict.fromkeys(body.ids))
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="at least two distinct works are required")
    items = _db.get_items(actor["id"], ids)
    if len(items) != len(ids):
        raise HTTPException(status_code=404, detail="one or more history items were not found")
    svgs = [str(item.get("svg") or "") for item in items]
    if any(not svg for svg in svgs):
        raise HTTPException(status_code=409, detail="one or more works have no saved SVG")
    try:
        payload = build_animation(
            svgs,
            output_format=body.format,
            pattern=body.pattern,
            hold_seconds=body.hold_seconds,
            resolution=body.resolution,
            height_px=body.height_px,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    extension = "png" if body.format == "apng" else "gif"
    media_type = "image/apng" if body.format == "apng" else "image/gif"
    filename = f"inku-animation-{timestamp}.{extension}"
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": "attachment; filename=\"" + filename + "\"",
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/history/{item_id}/neighbors", response_model=list[HistoryItem], response_model_exclude_none=True)
def api_history_neighbors(item_id: str, actor: dict = Depends(_current_user)) -> list[HistoryItem]:
    focus = _db.get_items(actor["id"], [item_id])
    if not focus:
        raise HTTPException(status_code=404, detail="history item not found")
    candidates = _db.list_neighbor_candidates(actor["id"], item_id)
    ranked = sorted(
        candidates,
        key=lambda item: (composition_distance(focus[0].get("score") or {}, item.get("score") or {}), -int(item.get("at") or 0)),
    )[:3]
    return [HistoryItem(**item) for item in _db.get_items(actor["id"], [item["id"] for item in ranked])]


@app.post("/api/feedback/unread-words")
def api_record_unread_words(body: UnreadWordsBody, actor: dict = Depends(_current_user)) -> dict:
    _db.record_unread_words(actor["id"], body.words, body.context, at=int(time.time() * 1000))
    return {"ok": True}


@app.get("/api/feedback/unread-words")
def api_my_unread_words(limit: int = Query(default=100, ge=1, le=500), actor: dict = Depends(_current_user)) -> list[dict]:
    return _db.list_unread_words(actor["id"], limit=limit)


@app.get("/api/admin/unread-words")
def api_admin_unread_words(limit: int = Query(default=500, ge=1, le=2000), actor: dict = Depends(_current_user)) -> list[dict]:
    if actor.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return _db.list_unread_words(None, limit=limit)


@app.get("/api/history/{item_id}/lineage")
def api_history_lineage(
    item_id: str,
    descendant_depth: int = Query(default=2, ge=0, le=200),
    node_limit: int = Query(default=200, ge=1, le=200),
    actor: dict = Depends(_current_user),
) -> dict:
    items = _db.get_items(actor["id"], [item_id])
    if not items or not items[0].get("lineage_node_id"):
        raise HTTPException(status_code=404, detail="history item not found")
    lineage = _db.get_lineage(
        actor["id"],
        items[0]["lineage_node_id"],
        descendant_depth=descendant_depth,
        node_limit=node_limit,
    )
    if lineage is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    return lineage


@app.get("/api/lineage/{node_id}")
def api_lineage(
    node_id: str,
    descendant_depth: int = Query(default=2, ge=0, le=200),
    node_limit: int = Query(default=200, ge=1, le=200),
    actor: dict = Depends(_current_user),
) -> dict:
    lineage = _db.get_lineage(actor["id"], node_id, descendant_depth=descendant_depth, node_limit=node_limit)
    if lineage is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    return lineage


@app.post("/api/lineage/{node_id}/promote", response_model=HistoryItem, response_model_exclude_none=True)
def api_lineage_promote(node_id: str, actor: dict = Depends(_current_user)) -> HistoryItem:
    item = _db.promote_lineage_node(actor["id"], node_id)
    if item is None:
        raise HTTPException(status_code=404, detail="lineage item not found")
    return HistoryItem(**item)


@app.post("/api/refine/vision-advice", response_model=VisionRefineAdviceResponse)
def api_vision_refine_advice(
    body: VisionRefineAdviceBody,
    actor: dict = Depends(_current_user),
) -> VisionRefineAdviceResponse:
    invalid_kinds = [kind for kind in body.enabled_kinds if kind not in AUTONOMOUS_REFINE_KINDS]
    if invalid_kinds:
        raise HTTPException(status_code=422, detail=f"unsupported refinement kind: {invalid_kinds[0]}")
    items = _db.get_items(actor["id"], [body.history_id])
    if not items:
        raise HTTPException(status_code=404, detail="refinement source not found")
    svg = str(items[0].get("svg") or "")
    if not svg:
        raise HTTPException(status_code=422, detail="refinement source has no image")
    try:
        advice = vision_refine_advice(
            svg=svg,
            instruction=body.instruction,
            direction=body.direction,
            enabled_kinds=body.enabled_kinds,
            model=_resolved_vision_model(body.model, actor),
            language=body.language,
            settings=_db.get_model_settings(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise _unexpected_http_error("Vision refinement advice", 502) from exc
    return VisionRefineAdviceResponse(**advice)


@app.get("/api/lineage/{node_id}/colophon", response_model=list[OkugakiItem], response_model_exclude_none=True)
def api_okugaki_list(node_id: str, actor: dict = Depends(_current_user)) -> list[OkugakiItem]:
    branch = _db.get_lineage_branch(actor["id"], node_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    return [OkugakiItem(**item) for item in _db.list_okugaki(actor["id"], node_id)]


@app.post("/api/lineage/{node_id}/colophon", response_model=OkugakiItem, response_model_exclude_none=True)
def api_okugaki_generate(
    node_id: str,
    body: OkugakiGenerateBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> OkugakiItem:
    if body.save and idempotency_key:
        existing = _db.get_okugaki_by_idempotency(actor["id"], idempotency_key)
        if existing is not None:
            return OkugakiItem(**existing)
    branch = _db.get_lineage_branch(actor["id"], node_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="lineage not found")
    at = int(time.time() * 1000)
    try:
        item = generate_okugaki(
            branch,
            model=_resolved_vision_model(body.model, actor),
            language=body.language,
            settings=_db.get_model_settings(),
            at=at,
        )
        if body.save:
            item = _db.add_okugaki(actor["id"], item, idempotency_key=idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError as exc:
        detail = (
            "Visionモデルがタイムアウトしました。完了済みの世代所見は一時保存されています。再度追記してください。"
            if body.language == "ja"
            else "The Vision model timed out. Completed generation readings are cached temporarily; retry the append."
        )
        raise HTTPException(status_code=504, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        raise _unexpected_http_error("okugaki generation", 502) from exc
    return OkugakiItem(**item)


@app.delete("/api/colophon/{colophon_id}")
def api_okugaki_delete(colophon_id: str, actor: dict = Depends(_current_user)) -> dict[str, bool]:
    if not _db.delete_okugaki(actor["id"], colophon_id):
        raise HTTPException(status_code=404, detail="colophon not found")
    return {"ok": True}


@app.get("/api/history/{item_id}/svg")
def api_history_svg(
    item_id: str,
    profile: str = Query(default="display", description="SVG output profile: display / editable / compat"),
    actor: dict = Depends(_current_user),
) -> Response:
    svg_profile = _validated_svg_profile(profile)
    items = _db.get_items(actor["id"], [item_id])
    if not items:
        raise HTTPException(status_code=404, detail="history item not found")
    item = items[0]
    if svg_profile == "display":
        svg = item.get("svg", "")
    else:
        try:
            svg = _render_score_svg(
                item.get("score", {}),
                catalog_id=item.get("catalog_id") or item.get("render_color_catalog_id"),
                svg_profile=svg_profile,
                wild=bool(item.get("render_wild")),
            )
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _unexpected_http_error("history svg render", 422) from e
    return Response(content=svg, media_type="image/svg+xml; charset=utf-8")


@app.post("/api/history", response_model=HistoryItem, response_model_exclude_none=True)
def api_history_post(
    body: HistoryPostBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    actor: dict = Depends(_current_user),
) -> HistoryItem:
    metadata_seed_text = body.derivation_metadata.get("seed_text")
    requested_seed_text = body.seed_text
    if requested_seed_text is None and isinstance(metadata_seed_text, str):
        requested_seed_text = metadata_seed_text
    render_seed, seed_text = _render_seed_from_text(requested_seed_text, body.render_seed)
    try:
        score = coerce_score(Score.model_validate(body.score))
        catalog_id = _resolved_catalog_id(body.catalog_id)
        canvas_aspect = _validated_canvas_aspect_override(body.canvas_aspect)
        if canvas_aspect is not None:
            score = _score_with_canvas(score, canvas_aspect)
        render_metadata = {
            **_render_metadata(catalog_id, canvas_aspect=_score_canvas_aspect_value(score)),
            "stage1_prompt_digest": body.stage1_prompt_digest,
            "stage1_prompt_base_digest": body.stage1_prompt_base_digest,
            "stage2_prompt_digest": body.stage2_prompt_digest,
            "instruction_lang_requested": body.instruction_lang_requested,
            "instruction_lang_resolved": body.instruction_lang_resolved,
            "ui_lang": body.ui_lang,
            "render_seed": render_seed,
            "composition_seed": body.composition_seed,
            # v1.97: 保存時に水準を確定する（renderer 専用派生でも系統の水準が途切れない）
            "tenkei": _resolved_tenkei(body.tenkei, actor, body.lineage_parent_node_id),
            "focus": body.focus if body.focus in FOCUS_IDS else None,
            "variation_amplitude": _validated_variation_amplitude(body.variation_amplitude),
            "variation_seed": body.variation_seed,
            "seed_text": seed_text,
            "interpretation_seed": body.interpretation_seed,
        }
        svg, render_metadata = _render_with_metadata(score, render_metadata)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("history score render", 422) from e
    item_dict = _add_history_item(
        actor=actor,
        input_text=body.input,
        ddl=body.ddl,
        expanded_ddl=body.expanded_ddl,
        interpret_fallback=body.interpret_fallback,
        score=score,
        svg=svg,
        at=body.at,
        elapsed_ms=body.elapsed_ms,
        stage1_model=body.stage1_model,
        stage2_model=body.stage2_model,
        tokens_in=body.tokens_in,
        tokens_out=body.tokens_out,
        catalog_id=None if catalog_id == "default" else catalog_id,
        save_artifacts=body.save_artifacts,
        render_metadata=render_metadata,
        source_text=body.source_text,
        display_label=body.display_label,
        batch_line_number=body.batch_line_number,
        batch_run_id=body.batch_run_id,
        history_visibility=body.history_visibility,
        lineage_parent_node_id=body.lineage_parent_node_id,
        derivation_kind=body.derivation_kind,
        derivation_metadata=body.derivation_metadata,
        idempotency_key=idempotency_key,
    )
    if body.count_generation and not item_dict.get("_idempotent_replay"):
        if _db.increment_user_generation_count(actor["id"]) is None:
            raise HTTPException(status_code=404, detail="user not found")
    return HistoryItem(**item_dict)


@app.delete("/api/history")
def api_history_delete(
    x_inku_confirm: str | None = Header(default=None, alias="X-Inku-Confirm"),
    actor: dict = Depends(_current_user),
) -> dict[str, int | bool]:
    if x_inku_confirm != "permanent-delete-trash":
        raise HTTPException(
            status_code=409,
            detail="X-Inku-Confirm: permanent-delete-trash is required",
        )
    count = _db.delete_all_trashed_items(actor["id"])
    return {"ok": True, "count": count}


@app.post("/api/history/trash")
def api_history_trash(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.trash_items(actor["id"], body.ids)
    return {"ok": True, "count": count}


@app.post("/api/history/restore")
def api_history_restore(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.restore_items(actor["id"], body.ids)
    return {"ok": True, "count": count}


@app.patch("/api/history/{item_id}/star", response_model=HistoryItem, response_model_exclude_none=True)
def api_history_star(item_id: str, body: HistoryStarBody, actor: dict = Depends(_current_user)) -> HistoryItem:
    item = _db.set_item_starred(actor["id"], item_id, body.starred, body.note)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    return HistoryItem(**item)


@app.post("/api/history/rebuild-output-files")
def api_history_rebuild_output_files(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    items = _db.get_items(actor["id"], body.ids)
    for item in items:
        _save_history_artifacts(item)
    return {"ok": True, "count": len(items)}


@app.post("/api/history/permanent-delete")
def api_history_permanent_delete(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.delete_items(actor["id"], body.ids, require_trashed=True)
    return {"ok": True, "count": count}



def main() -> None:
    import uvicorn

    host = os.getenv("INKU_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("INKU_SERVER_PORT", "8100"))
    reload = _env_flag("INKU_SERVER_RELOAD", default=False)
    uvicorn.run("inku_server.api:app", host=host, port=port, reload=reload)
