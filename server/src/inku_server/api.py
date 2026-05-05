"""FastAPI endpoints for inku-server.

POST /api/compose : 正規化DDL (or 生入力) → JSON Score + SVG
GET  /health      : liveness
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore, Lock

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .color_catalogs import color_catalogs, get_color_catalog, render_color_map_for_catalog
from .coerce import coerce_score, count_hint_from_ddl, ensure_renderable_score
from .composer import compose
from .composer import SYSTEM_PROMPT as STAGE2_PROMPT
from .composer import SYSTEM_PROMPT_EN as STAGE2_PROMPT_EN
from .ddl_expander import expand_intermediate_ddl
from .interpreter import _sanitize_placement_words, interpret_detail
from .interpreter import SYSTEM_PROMPT as STAGE1_PROMPT
from .interpreter import SYSTEM_PROMPT_EN as STAGE1_PROMPT_EN
from .plugins import (
    canvas_aspect_ids,
    normalize_canvas_aspect_id,
    plugin_status_items,
)
from .renderer import SVG_PROFILES
from .render_engines import current_render_engine
from .schema import Score
from .model_settings import (
    connection_for,
    model_provider_catalog,
    normalize_model_settings,
    provider_for_model,
    public_model_settings,
    update_model_settings,
)
from . import db as _db

_APP_VERSION = "0.1.0"
app = FastAPI(title="inku-server", version=_APP_VERSION)

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
_logger = logging.getLogger(__name__)
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
_SESSION_COOKIE_NAME = "inku_session"
_SESSION_COOKIE_MAX_AGE = int(os.getenv("INKU_SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))
_SESSION_COOKIE_SECURE = os.getenv("INKU_SESSION_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes"}
_SRGB_COLOR_PROFILE = {
    "id": "srgb",
    "name": "sRGB IEC61966-2.1",
    "standard": "IEC 61966-2-1:1999",
}


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
    if ":" not in model:
        return False
    prefix = model.split(":", 1)[0]
    return prefix in normalize_model_settings(_db.get_model_settings())["providers"]


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

    try:
        import cairosvg  # lazy import — optional dependency
    except ImportError:
        _logger.warning("cairosvg is not installed; skipped PNG output: prefix=%s", prefix)
        return

    try:
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=int(_output_save_settings()["png_size"]))
        Path(f"{prefix}_output.png").write_bytes(png_bytes)
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


def _coerce_context(ddl: str, original_text: str | None = None) -> str:
    original = (original_text or "").strip()
    normalized = ddl.strip()
    if original and original != normalized:
        return f"{original}\n{normalized}"
    return normalized


def _validated_svg_profile(svg_profile: str | None) -> str:
    profile = (svg_profile or "display").strip().lower()
    if profile not in SVG_PROFILES:
        raise HTTPException(status_code=422, detail=f"unsupported svg profile: {svg_profile}")
    return profile


def _render_score_svg(
    score_payload: dict,
    *,
    catalog_id: str | None,
    canvas_aspect: str | None = None,
    svg_profile: str | None = None,
) -> str:
    score = coerce_score(Score.model_validate(score_payload))
    canvas = _validated_canvas_aspect_override(canvas_aspect)
    if canvas is not None:
        score = _score_with_canvas(score, canvas)
    render_metadata = _render_metadata(_resolved_catalog_id(catalog_id))
    return current_render_engine().render(
        score,
        color_map=render_metadata["render_color_map"],
        svg_profile=_validated_svg_profile(svg_profile),
    ).svg


def _history_output_prefix(item: dict) -> Path:
    output_path = item.get("output_path")
    if output_path:
        return Path(output_path)
    return _output_prefix(item["user_id"], item["id"], item["at"])


def _history_render_metadata(item: dict) -> dict | None:
    if isinstance(item.get("render_metadata"), dict):
        metadata = dict(item["render_metadata"])
        if item.get("render_hash") is not None:
            metadata["render_hash"] = item["render_hash"]
            metadata["render_hash_short"] = item.get("render_hash_short") or _db.render_hash_short(item.get("render_hash"))
        return metadata
    keys = (
        "render_build_number",
        "render_color_profile",
        "render_engine_id",
        "render_engine_version",
        "render_canvas_aspect",
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


def _render_metadata(catalog_id: str | None, *, canvas_aspect: str | None = None) -> dict:
    catalog = get_color_catalog(catalog_id)
    color_map = render_color_map_for_catalog(catalog_id)
    if catalog is None or color_map is None:
        raise HTTPException(status_code=422, detail=f"unsupported color catalog: {catalog_id}")
    metadata = {
        "render_build_number": _build_number(),
        "render_color_profile": dict(_SRGB_COLOR_PROFILE),
    }
    if canvas_aspect is not None:
        metadata["render_canvas_aspect"] = canvas_aspect
    metadata.update({
        "render_color_catalog_id": str(catalog["id"]),
        "render_color_catalog_name": str(catalog["name"]),
        "render_color_catalog_sub": str(catalog["sub"]),
    })
    metadata["render_color_map"] = color_map
    return metadata


def _render_with_metadata(score: Score, render_metadata: dict, *, svg_profile: str | None = None) -> tuple[str, dict]:
    result = current_render_engine().render(
        score,
        color_map=render_metadata["render_color_map"],
        svg_profile=_validated_svg_profile(svg_profile),
    )
    return result.svg, {**render_metadata, **result.metadata}


def _resolved_catalog_id(catalog_id: str | None) -> str:
    catalog = get_color_catalog(catalog_id)
    if catalog is None:
        raise HTTPException(status_code=422, detail=f"unsupported color catalog: {catalog_id}")
    return str(catalog["id"])


def _validated_canvas_aspect(value: str | None) -> str:
    if value is None:
        return normalize_canvas_aspect_id(None)
    if value not in canvas_aspect_ids():
        raise HTTPException(status_code=422, detail=f"unsupported canvas aspect: {value}")
    return value


def _validated_canvas_aspect_override(value: str | None) -> str | None:
    if value is None:
        return None
    return _validated_canvas_aspect(value)


def _score_with_canvas(score: Score, canvas_aspect: str) -> Score:
    data = score.model_dump(by_alias=True)
    data["canvas"] = canvas_aspect
    return Score.model_validate(data)


app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ComposeRequest(BaseModel):
    ddl: str = Field(..., min_length=1, description="正規化DDL テキスト")
    model: str | None = Field(
        default=None, description="Stage 2 モデル名 (未指定時は OPENAI_MODEL 既定)"
    )
    original_text: str | None = Field(default=None, description="元のユーザー記述 (省略可)")
    lang: str = Field(default="ja", description="言語コード (ja / en)")
    color_map: dict[str, str] | None = Field(default=None, description="Deprecated: ignored; catalog_id is resolved server-side")
    catalog_id: str | None = Field(default=None, description="使用するサーバー側色カタログID")
    canvas_aspect: str | None = Field(default=None, description="Canvas aspect plugin selection")


class ComposeResponse(BaseModel):
    score: Score
    svg: str
    stage2_model: str | None = None
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
    elapsed_ms: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    retry_count: int = 0
    retry_reasons: list[str] = Field(default_factory=list)
    fallback_used: bool = False


class InterpretRequest(BaseModel):
    text: str = Field(..., min_length=1, description="自由な自然言語の記述")
    original_text: str | None = Field(default=None, description="元のユーザー記述")
    model: str | None = Field(
        default=None, description="Stage 1 モデル名 (未指定時は OPENAI_MODEL_STAGE1 既定)"
    )
    include_thinking: bool = Field(
        default=False, description="qwen3 の <think> 内容を別フィールドで返すか"
    )
    lang: str = Field(default="ja", description="言語コード (ja / en)")
    expand_intermediate: bool = Field(default=False, description="Stage 1.5 の中間DDL拡張を適用するか")


class InterpretResponse(BaseModel):
    ddl: str
    thinking: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class PaintRequest(BaseModel):
    text: str = Field(..., min_length=1, description="自由な自然言語の記述")
    original_text: str | None = Field(default=None, description="元のユーザー記述")
    stage1_model: str | None = Field(default=None, description="Stage 1 モデル名")
    stage2_model: str | None = Field(default=None, description="Stage 2 モデル名")
    include_thinking: bool = Field(default=False, description="Stage 1 の思考を返すか")
    lang: str = Field(default="ja", description="言語コード (ja / en)")
    color_map: dict[str, str] | None = Field(default=None, description="Deprecated: ignored; catalog_id is resolved server-side")
    canvas_aspect: str | None = Field(default=None, description="Canvas aspect plugin selection")
    save_history: bool = Field(default=False, description="描画結果を履歴に保存するか")
    save_artifacts: bool | None = Field(default=None, description="SVG/JSON/PNG などの副産物ファイルを保存するか")
    count_generation: bool = Field(default=True, description="完了した描画をユーザーの累積生成数に加算するか")
    history_input: str | None = Field(default=None, description="履歴に表示するユーザー記述")
    history_at: int | None = Field(default=None, description="履歴保存時刻")
    catalog_id: str | None = Field(default=None, description="使用した色カタログID")


class PaintResponse(BaseModel):
    text: str
    ddl: str
    thinking: str | None = None
    score: Score
    svg: str
    stage1_model: str | None = None
    stage2_model: str | None = None
    render_build_number: str | None = None
    render_color_profile: dict[str, str] | None = None
    render_engine_id: str | None = None
    render_engine_version: str | None = None
    render_color_catalog_id: str | None = None
    render_color_catalog_name: str | None = None
    render_color_catalog_sub: str | None = None
    render_color_map: dict[str, str] | None = None
    render_canvas_aspect: str | None = None
    render_hash: str | None = None
    render_hash_short: str | None = None
    history_id: str | None = None
    history_at: int | None = None
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


class RenderSvgRequest(BaseModel):
    score: dict
    catalog_id: str | None = None
    canvas_aspect: str | None = None
    svg_profile: str = Field(default="display", description="SVG output profile: display / editable / compat")


@dataclass
class InterpretDetail:
    ddl: str
    thinking: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    fallback_used: bool = False
    fallback_reasons: list[str] = field(default_factory=list)


@dataclass
class ComposeDetail:
    score: Score
    tokens_in: int | None = None
    tokens_out: int | None = None
    retry_count: int = 0
    retry_reasons: list[str] = field(default_factory=list)
    fallback_used: bool = False


class PromptsResponse(BaseModel):
    stage1_system: str
    stage2_system: str


class AppInfoResponse(BaseModel):
    name: str
    version: str
    build_number: str | None = None


class ColorCatalogsResponse(BaseModel):
    default_catalog_id: str
    catalogs: list[dict]


class HistoryPostBody(BaseModel):
    input: str
    ddl: str | None = None
    score: dict
    svg: str = ""
    at: int
    elapsed_ms: int = 0
    stage1_model: str | None = None
    stage2_model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    catalog_id: str | None = None
    render_build_number: str | None = None
    render_color_profile: dict[str, str] | None = None
    render_engine_id: str | None = None
    render_engine_version: str | None = None
    render_color_catalog_id: str | None = None
    render_color_catalog_name: str | None = None
    render_color_catalog_sub: str | None = None
    render_color_map: dict[str, str] | None = None
    render_canvas_aspect: str | None = None
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


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int
    offset: int
    limit: int


class HistoryIdsBody(BaseModel):
    ids: list[str] = Field(default_factory=list)


class HistoryStarBody(BaseModel):
    starred: bool = False


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
    ui_theme: str = "light"
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
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    user: UserAccountItem


class UserSettingsBody(BaseModel):
    ui_theme: str | None = None
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
    prompt_model: str = Field(default="google/gemma-4-31b-it", min_length=1)
    seed_phrase: str = Field(default="日本の四季を感じさせる文章を40語以内で生成", min_length=1, max_length=1000)
    interval_seconds: int = Field(default=30, ge=1, le=3600)
    random_color_catalog: bool = False


class DemoInstructionBody(BaseModel):
    seed_phrase: str = Field(..., min_length=1, max_length=1000)
    model: str | None = Field(default=None)
    lang: str = Field(default="ja")


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


class DbBackupStatus(BaseModel):
    supported: bool
    interval_days: int
    max_generations: int
    last_auto_backup_at: int = 0
    backup_dir: str
    auto_count: int = 0
    manual_count: int = 0


class DbBackupSettingsBody(BaseModel):
    interval_days: int = Field(default=7, ge=1, le=365)
    max_generations: int = Field(default=4, ge=1, le=100)


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
    loaded: list[dict[str, str]] = Field(default_factory=list)
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


class ModelSettingsResponse(BaseModel):
    catalog: list[dict] = Field(default_factory=list)
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


class SettingsStatusResponse(BaseModel):
    database: DatabaseSettingsStatus
    db_backup: DbBackupStatus
    plugins: PluginSettingsStatus
    output_save: OutputSaveStatus
    log_retention: LogRetentionStatus
    stage_execution: StageExecutionStatus


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
    return AppInfoResponse(name="inku-server", version=_APP_VERSION, build_number=_build_number())


@app.get("/api/color-catalogs", response_model=ColorCatalogsResponse)
def api_color_catalogs() -> ColorCatalogsResponse:
    return ColorCatalogsResponse(default_catalog_id="default", catalogs=color_catalogs())


@app.post("/api/auth/login", response_model=LoginResponse)
def api_auth_login(body: LoginBody, response: Response) -> LoginResponse:
    user = _db.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid username or password")
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
    return ModelSettingsResponse(
        catalog=model_provider_catalog(settings, include_disabled=False),
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
        raise HTTPException(status_code=409, detail=f"profile update failed: {e}") from e
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


@app.get("/api/settings/status", response_model=SettingsStatusResponse)
def api_settings_status(actor: dict = Depends(_admin_user)) -> SettingsStatusResponse:
    _db.ensure_scheduled_db_backup()
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
            note="Reference plugin hook is enabled for canvas aspect selection. Third-party plugin loading is not implemented yet.",
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
    return ModelSettingsResponse(
        catalog=model_provider_catalog(settings, include_disabled=True),
        settings=public_model_settings(settings),
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
    return ModelSettingsResponse(
        catalog=model_provider_catalog(saved, include_disabled=True),
        settings=public_model_settings(saved),
    )


def _fetch_provider_model_list(provider_id: str, settings: dict) -> list[dict[str, str]]:
    catalog = {str(provider["id"]): provider for provider in model_provider_catalog(settings, include_disabled=True)}
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
    previous_model_ids = {str(model.get("id")) for model in previous_provider.get("models", [])}
    previous_enabled_models = previous_provider.get("enabled_models") or {}
    enabled_models = {
        model["id"]: model["id"] in previous_model_ids and bool(previous_enabled_models.get(model["id"], False))
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
    return ModelSettingsResponse(
        catalog=model_provider_catalog(saved, include_disabled=True),
        settings=public_model_settings(saved),
    )


@app.put("/api/settings/db-backup", response_model=DbBackupStatus)
def api_settings_update_db_backup(
    body: DbBackupSettingsBody,
    actor: dict = Depends(_admin_user),
) -> DbBackupStatus:
    try:
        _db.update_db_backup_settings(body.interval_days, body.max_generations)
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
    s1 = STAGE1_PROMPT_EN if lang == "en" else STAGE1_PROMPT
    s2 = STAGE2_PROMPT_EN if lang == "en" else STAGE2_PROMPT
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
    if ("ロットリング" in ddl) or ("rotring" in lower):
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
    elif ("縄" in ddl) or ("rope" in lower):
        weight = "rope"

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

    if ("三角" in ddl) or ("triangle" in lower) or ("山" in ddl) or ("mountain" in lower):
        instruction = {
            "primitive": "triangle",
            "position": [0.54, 0.22],
            "size": [0.20, 0.18],
            "rotation": -8,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "color_hint": "fallback from DDL",
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
            "color_hint": "fallback from DDL",
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
            "color_hint": "fallback from DDL",
        }
    elif (
        ("円" in ddl)
        or ("circle" in lower)
        or ("moon" in lower)
        or ("月" in ddl)
        or ("蕾" in ddl)
        or ("花びら" in ddl)
        or ("petal" in lower)
        or ("bud" in lower)
    ):
        instruction = {
            "primitive": "ellipse",
            "center": [0.72, 0.32],
            "size": [0.18, 0.11],
            "rotation": -18,
            "color": color,
            "weight": weight,
            "filled": "塗" in ddl or "fill" in lower,
            "color_hint": "fallback from DDL",
        }
    else:
        instruction = {
            "primitive": "line",
            "from": [0.16, 0.78],
            "to": [0.84, 0.28],
            "rotation": -8,
            "color": color,
            "weight": weight,
            "color_hint": "fallback from DDL",
        }

    arrangement: dict[str, object] | None = None
    explicit_count = count_hint_from_ddl(ddl)
    if ("散らす" in ddl) or ("点々" in ddl) or ("scatter" in lower) or ("dotted" in lower):
        arrangement = {"count": explicit_count or 11, "layout": "scatter", "margin": 0.18}
    elif ("並べる" in ddl) or ("line up" in lower):
        arrangement = {"count": explicit_count or 3, "layout": "horizontal", "margin": 0.1}

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
    elif color_cycle:
        instruction["color_hint"] = f"{instruction['color_hint']}; palette {'/'.join(color_cycle)}"

    return Score.model_validate({"background": background, "instructions": [instruction]})


def _compose_retry_reason(score: Score, *, tokens_out: int | None, elapsed_ms: int) -> str:
    token_limit = int(os.getenv("INKU_STAGE2_RETRY_TOKENS_OUT", "3800"))
    elapsed_limit = int(os.getenv("INKU_STAGE2_RETRY_ELAPSED_MS", "120000"))
    if not score.instructions:
        return "empty_instructions"
    if tokens_out is not None and tokens_out >= token_limit:
        return "excessive_tokens_out"
    if elapsed_ms >= elapsed_limit and len(score.instructions) <= 1:
        return "slow_single_instruction"
    return "none"


def _should_retry_compose_result(score: Score, *, tokens_out: int | None, elapsed_ms: int) -> bool:
    return _compose_retry_reason(score, tokens_out=tokens_out, elapsed_ms=elapsed_ms) != "none"


def _call_compose_detail(
    ddl: str,
    *,
    model: str | None = None,
    original_text: str | None = None,
    system_prompt: str | None = None,
    lang: str = "ja",
) -> ComposeDetail:
    ddl = expand_intermediate_ddl(ddl, lang=lang, context_text=original_text)
    retry_count = 0
    retry_reasons: list[str] = []
    fallback_used = False

    def invoke(prompt: str | None) -> tuple[Score, int | None, int | None, int]:
        started = time.perf_counter()

        def run_compose():
            try:
                return compose(
                    ddl,
                    model=model,
                    original_text=original_text,
                    system_prompt=prompt,
                    lang=lang,
                )
            except TypeError as e:
                if "unexpected keyword argument" not in str(e):
                    raise
                return compose(ddl, model=model)

        value = _run_with_hard_timeout(
            "stage2",
            _hard_timeout_seconds("INKU_STAGE2_HARD_TIMEOUT_SECONDS"),
            run_compose,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if isinstance(value, tuple):
            return value[0], value[1], value[2], elapsed_ms
        return value, None, None, elapsed_ms

    try:
        score, tokens_in, tokens_out, elapsed_ms = invoke(system_prompt)
    except StageHardTimeoutError:
        return ComposeDetail(
            score=_fallback_score_from_ddl(ddl, lang=lang),
            retry_reasons=["stage2_hard_timeout"],
            fallback_used=True,
        )
    if score.instructions and not _should_retry_compose_result(score, tokens_out=tokens_out, elapsed_ms=elapsed_ms):
        return ComposeDetail(score=score, tokens_in=tokens_in, tokens_out=tokens_out)

    base_prompt = system_prompt or (STAGE2_PROMPT_EN if lang == "en" else STAGE2_PROMPT)
    reason = _compose_retry_reason(score, tokens_out=tokens_out, elapsed_ms=elapsed_ms)
    retry_count += 1
    retry_reasons.append(reason)
    rescue_note = (
        "\n\n# Compact result retry\n"
        f"The previous Stage 2 result was invalid or inefficient: {reason}. "
        "Return 2-5 concise drawable instructions. "
        "Do not return an empty instructions array. "
        "Use one instruction plus arrangement for repeated shapes. "
        "Keep the response compact and avoid restating the DDL."
        if lang == "en"
        else "\n\n# 空描画リトライ / コンパクト描画リトライ\n"
        f"直前の Stage 2 出力は無効または非効率: {reason}。"
        "2〜5個の簡潔な描画命令を返す。"
        "instructions を空配列にしてはいけない。"
        "繰り返し図形は複数 instruction にせず、1 instruction + arrangement で表す。"
        "DDLを説明し直さず、JSONを短く保つ。"
    )
    try:
        retry_score, retry_tokens_in, retry_tokens_out, _retry_elapsed_ms = invoke(base_prompt + rescue_note)
    except StageHardTimeoutError:
        fallback_used = True
        retry_reasons.append("stage2_retry_hard_timeout")
        retry_score = _fallback_score_from_ddl(ddl, lang=lang)
        retry_tokens_in = None
        retry_tokens_out = None
    if retry_tokens_in is not None:
        tokens_in = (tokens_in or 0) + retry_tokens_in
    if retry_tokens_out is not None:
        tokens_out = (tokens_out or 0) + retry_tokens_out
    if not retry_score.instructions:
        fallback_used = True
        retry_reasons.append("fallback_after_empty_retry")
        retry_score = _fallback_score_from_ddl(ddl, lang=lang)
    return ComposeDetail(
        score=retry_score,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        retry_count=retry_count,
        retry_reasons=retry_reasons,
        fallback_used=fallback_used,
    )


def _call_interpret_detail(
    text: str,
    *,
    model: str | None = None,
    include_thinking: bool = False,
    system_prompt_prefix: str | None = None,
    lang: str = "ja",
) -> InterpretDetail:
    def run_interpret():
        try:
            return interpret_detail(
                text,
                model=model,
                include_thinking=include_thinking,
                system_prompt_prefix=system_prompt_prefix,
                lang=lang,
            )
        except TypeError as e:
            if "unexpected keyword argument" not in str(e):
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
    if len(value) == 4:
        ddl, thinking, tokens_in, tokens_out = value
        return InterpretDetail(
            ddl=_sanitize_placement_words(ddl),
            thinking=thinking,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
    ddl, thinking = value
    return InterpretDetail(ddl=_sanitize_placement_words(ddl), thinking=thinking)


@app.post("/api/compose", response_model=ComposeResponse, response_model_exclude_none=True)
def api_compose(req: ComposeRequest, actor: dict = Depends(_current_user)) -> ComposeResponse:
    t0 = time.perf_counter()
    resolved_stage2_model = _resolved_stage2_model(req.model, actor)
    try:
        compose_detail = _call_compose_detail(
            req.ddl,
            model=resolved_stage2_model,
            original_text=req.original_text,
            system_prompt=None,
            lang=req.lang,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    try:
        score = compose_detail.score
        ensure_renderable_score(score)
        score = coerce_score(score, ddl=_coerce_context(req.ddl, req.original_text))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    canvas_aspect = _validated_canvas_aspect(req.canvas_aspect)
    score = _score_with_canvas(score, canvas_aspect)
    render_metadata = _render_metadata(req.catalog_id, canvas_aspect=score.canvas)
    try:
        svg, render_metadata = _render_with_metadata(score, render_metadata)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e
    render_metadata = {
        **render_metadata,
        **_render_hash_metadata(
            input_text=req.original_text or req.ddl,
            ddl=req.ddl,
            score=score,
            svg=svg,
            catalog_id=req.catalog_id,
            render_metadata=render_metadata,
        ),
    }

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return ComposeResponse(
        score=score,
        svg=svg,
        stage2_model=resolved_stage2_model,
        **render_metadata,
        elapsed_ms=elapsed_ms,
        tokens_in=compose_detail.tokens_in,
        tokens_out=compose_detail.tokens_out,
        retry_count=compose_detail.retry_count,
        retry_reasons=compose_detail.retry_reasons,
        fallback_used=compose_detail.fallback_used,
    )


@app.post("/api/interpret")
def api_interpret(req: InterpretRequest, actor: dict = Depends(_current_user)) -> dict:
    try:
        detail = _call_interpret_detail(
            req.text,
            model=_resolved_stage1_model(req.model, actor),
            include_thinking=req.include_thinking,
            system_prompt_prefix=None,
            lang=req.lang,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    if req.expand_intermediate:
        source_text = req.original_text or req.text
        detail.ddl = expand_intermediate_ddl(detail.ddl, lang=req.lang, context_text=source_text)
    data: dict = {"ddl": detail.ddl, "thinking": detail.thinking}
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


def _fallback_ddl_from_text(text: str, *, lang: str) -> str:
    lower = text.lower()
    if lang == "en":
        background = "black" if "night" in lower or "dark" in lower or "black" in lower else "white"
        foreground = "white" if background == "black" else "black"
        return (
            f"Fill background with {background}. "
            f"Draw three thin {foreground} diagonal lines. "
            "Scatter twelve small gray dots across the whole canvas."
        )
    background = "黒" if ("夜" in text or "黒" in text or "暗" in text) else "白"
    foreground = "白" if background == "黒" else "黒"
    accent = "青" if foreground == "黒" and ("白" in text or "雪" in text) else "灰色"
    return (
        f"背景を{background}で塗りつぶす。"
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
    model_name = model or os.getenv("OPENAI_MODEL_STAGE1") or os.getenv("OPENAI_MODEL") or "qwen-api"
    settings = _db.get_model_settings()
    provider, model_id = provider_for_model(model_name, stage="stage1", settings=settings)
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
    try:
        instruction = _generate_demo_instruction(req.seed_phrase, model=req.model, lang=req.lang)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"demo instruction failed: {e}") from e
    return DemoInstructionResponse(instruction=instruction)


@app.post("/api/render-svg")
def api_render_svg(req: RenderSvgRequest, _actor: dict = Depends(_current_user)) -> Response:
    try:
        svg = _render_score_svg(
            req.score,
            catalog_id=req.catalog_id,
            canvas_aspect=req.canvas_aspect,
            svg_profile=req.svg_profile,
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"svg render failed: {e}") from e
    return Response(content=svg, media_type="image/svg+xml; charset=utf-8")


def _add_history_item(
    *,
    actor: dict,
    input_text: str,
    ddl: str | None,
    score: Score,
    svg: str,
    at: int,
    elapsed_ms: int = 0,
    stage1_model: str | None = None,
    stage2_model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    catalog_id: str | None = None,
    save_artifacts: bool = True,
    render_metadata: dict | None = None,
) -> dict:
    item_id = str(uuid.uuid4())
    score_dict = score.model_dump(by_alias=True)
    prefix = _output_prefix(actor["id"], item_id, at)
    metadata = dict(render_metadata or {})
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
    item_dict = _db.add_item({
        "id": item_id,
        "user_id": actor["id"],
        "output_path": str(prefix),
        "input": input_text,
        "ddl": _sanitize_placement_words(ddl) if ddl else ddl,
        "score": score_dict,
        "svg": svg,
        "at": at,
        "elapsed_ms": elapsed_ms,
        "stage1_model": stage1_model,
        "stage2_model": stage2_model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "catalog_id": catalog_id,
        **metadata,
    })
    if save_artifacts:
        item_dict.update(metadata)
        item_dict["render_metadata"] = metadata
        _submit_history_artifact_save(item_dict)
    else:
        item_dict.update(metadata)
    return item_dict


@app.post("/api/paint", response_model=PaintResponse, response_model_exclude_none=True)
def api_paint(req: PaintRequest, actor: dict = Depends(_current_user)) -> PaintResponse:
    t0 = time.perf_counter()
    source_text = req.original_text or req.text
    catalog_id = _resolved_catalog_id(req.catalog_id)
    resolved_stage1_model = _resolved_stage1_model(req.stage1_model, actor)
    resolved_stage2_model = _resolved_stage2_model(req.stage2_model, actor)
    try:
        interpret_detail_result = _call_interpret_detail(
            req.text, model=resolved_stage1_model, include_thinking=req.include_thinking, lang=req.lang
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    ddl = interpret_detail_result.ddl
    ddl = expand_intermediate_ddl(ddl, lang=req.lang, context_text=source_text)
    t1 = time.perf_counter()
    try:
        compose_detail = _call_compose_detail(
            ddl, model=resolved_stage2_model, original_text=source_text, lang=req.lang
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    try:
        score = compose_detail.score
        ensure_renderable_score(score)
        score = coerce_score(score, ddl=_coerce_context(ddl, source_text))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    canvas_aspect = _validated_canvas_aspect(req.canvas_aspect)
    score = _score_with_canvas(score, canvas_aspect)
    render_metadata = _render_metadata(catalog_id, canvas_aspect=score.canvas)
    t2 = time.perf_counter()
    try:
        svg, render_metadata = _render_with_metadata(score, render_metadata)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e
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
    save_artifacts = req.save_artifacts if req.save_artifacts is not None else req.save_history
    if req.save_history:
        history_at = req.history_at or int(time.time() * 1000)
        item = _add_history_item(
            actor=actor,
            input_text=req.history_input or source_text,
            ddl=ddl,
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
        )
        history_id = item["id"]
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
    if req.count_generation:
        user_generation_count = _db.increment_user_generation_count(actor["id"])
        if user_generation_count is None:
            raise HTTPException(status_code=404, detail="user not found")
    return PaintResponse(
        text=source_text,
        ddl=ddl,
        thinking=interpret_detail_result.thinking,
        score=score,
        svg=svg,
        stage1_model=resolved_stage1_model,
        stage2_model=resolved_stage2_model,
        **render_metadata,
        history_id=history_id,
        history_at=history_at,
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
        raise HTTPException(status_code=409, detail=f"group create failed: {e}") from e


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
        raise HTTPException(status_code=409, detail=f"group update failed: {e}") from e
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
        raise HTTPException(status_code=409, detail=f"user create failed: {e}") from e
    return UserAccountItem(**user)


@app.patch("/api/users/{user_id}", response_model=UserAccountItem)
def api_users_update(
    user_id: str,
    body: UserAccountUpdateBody,
    actor: dict = Depends(_user_manager),
) -> UserAccountItem:
    target = _db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    if not _can_manage_user(actor, target):
        raise HTTPException(status_code=403, detail="user update is not permitted")
    if actor["role"] == "group_lead":
        if body.role and body.role != "user":
            raise HTTPException(status_code=403, detail="group leads cannot change user roles")
        if body.group_id is not None and body.group_id != actor.get("group_id"):
            raise HTTPException(status_code=403, detail="group leads cannot move users outside their group")
    try:
        user = _db.update_user(user_id, **body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=409, detail=f"user update failed: {e}") from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@app.delete("/api/users/{user_id}")
def api_users_delete(user_id: str, actor: dict = Depends(_user_manager)) -> dict[str, bool]:
    target = _db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    if not _can_manage_user(actor, target):
        raise HTTPException(status_code=403, detail="user delete is not permitted")
    try:
        found = _db.delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True}


@app.get("/api/history", response_model=HistoryListResponse, response_model_exclude_none=True)
def api_history_get(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    trashed: bool = Query(default=False),
    starred: bool = Query(default=False),
    q: str = Query(default="", max_length=200),
    actor: dict = Depends(_current_user),
) -> HistoryListResponse:
    items, total = _db.list_items(
        actor["id"],
        offset=offset,
        limit=limit,
        trashed=trashed,
        query_text=q,
        starred=starred,
    )
    return HistoryListResponse(items=items, total=total, offset=offset, limit=limit)


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
            )
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"history svg render failed: {e}") from e
    return Response(content=svg, media_type="image/svg+xml; charset=utf-8")


@app.post("/api/history", response_model=HistoryItem, response_model_exclude_none=True)
def api_history_post(body: HistoryPostBody, actor: dict = Depends(_current_user)) -> HistoryItem:
    try:
        score = coerce_score(Score.model_validate(body.score))
        catalog_id = _resolved_catalog_id(body.catalog_id)
        canvas_aspect = _validated_canvas_aspect_override(body.canvas_aspect)
        if canvas_aspect is not None:
            score = _score_with_canvas(score, canvas_aspect)
        render_metadata = _render_metadata(catalog_id, canvas_aspect=score.canvas)
        svg, render_metadata = _render_with_metadata(score, render_metadata)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"history score render failed: {e}") from e
    item_dict = _add_history_item(
        actor=actor,
        input_text=body.input,
        ddl=body.ddl,
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
    )
    if body.count_generation:
        if _db.increment_user_generation_count(actor["id"]) is None:
            raise HTTPException(status_code=404, detail="user not found")
    return HistoryItem(**item_dict)


@app.delete("/api/history")
def api_history_delete(actor: dict = Depends(_current_user)) -> dict[str, bool]:
    _db.delete_all(actor["id"])
    return {"ok": True}


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
    item = _db.set_item_starred(actor["id"], item_id, body.starred)
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
    count = _db.delete_items(actor["id"], body.ids)
    return {"ok": True, "count": count}



def main() -> None:
    import uvicorn

    host = os.getenv("INKU_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("INKU_SERVER_PORT", "8100"))
    reload = _env_flag("INKU_SERVER_RELOAD", default=False)
    uvicorn.run("inku_server.api:app", host=host, port=port, reload=reload)
