"""FastAPI endpoints for inku-server.

POST /api/compose : 正規化DDL (or 生入力) → JSON Score + SVG
GET  /health      : liveness
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .color_catalogs import render_color_map_for_catalog
from .render_engines import current_render_engine
from .security import ConcurrencyLimitMiddleware, RequestBodyLimitMiddleware
from . import db as _db
from .api_core.common import _APP_VERSION, _build_number, _env_flag
from .api_core.deps import _logger
from .api_core.state import _render_slots
from .api_core.routers import public, auth, me, plugins, settings, users, history, lineage, render, feedback


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


_DEFAULT_OUTPUT_DIR = Path.home() / ".local" / "share" / "inku" / "outputs"


_OUTPUT_DIR = Path(os.getenv("INKU_OUTPUT_DIR", str(_DEFAULT_OUTPUT_DIR)))


_OUTPUT_PNG_SIZE = int(os.getenv("INKU_OUTPUT_PNG_SIZE", "2160"))


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


_MAX_REQUEST_BODY_BYTES = max(1024, int(os.getenv("INKU_MAX_REQUEST_BODY_BYTES", str(16 * 1024 * 1024))))


_MAX_CONCURRENT_REQUESTS = max(1, int(os.getenv("INKU_MAX_CONCURRENT_REQUESTS", "64")))


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


app.include_router(public.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(plugins.router)
app.include_router(settings.router)
app.include_router(users.router)
app.include_router(history.router)
app.include_router(lineage.router)
app.include_router(render.router)
app.include_router(feedback.router)


class InterpretResponse(BaseModel):
    ddl: str
    plugin_provenance: list[dict[str, str]] = Field(default_factory=list)
    plugin_warnings: list[str] = Field(default_factory=list)
    thinking: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


def _bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    return authorization.removeprefix("Bearer ").strip()


def _can_manage_user(actor: dict, target: dict) -> bool:
    if actor["role"] == "admin":
        return True
    return (
        actor["role"] == "group_lead"
        and actor.get("group_id")
        and target.get("group_id") == actor.get("group_id")
        and target.get("role") == "user"
    )


def _strip_anthropic_prefix(model: str) -> str:
    return model.removeprefix("anthropic:")


def main() -> None:
    import uvicorn

    host = os.getenv("INKU_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("INKU_SERVER_PORT", "8100"))
    reload = _env_flag("INKU_SERVER_RELOAD", default=False)
    uvicorn.run("inku_server.api:app", host=host, port=port, reload=reload)
