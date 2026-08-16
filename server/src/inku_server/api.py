"""FastAPI endpoints for inku-server.

POST /api/compose : 正規化DDL (or 生入力) → JSON Score + SVG
GET  /health      : liveness
"""

from __future__ import annotations

import asyncio
import os
import platform
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import gzip as _gzip
from .color_catalogs import render_color_map_for_catalog
from .compression import FlushingGZipMiddleware
from .render_engines import current_render_engine
from .security import ConcurrencyLimitMiddleware, RequestBodyLimitMiddleware
from . import db as _db
from . import thumbs_db as _thumbs_db
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
# The derived thumbnail store. Separate from the canonical schema on purpose:
# deleting its file is the supported way to clear every thumbnail, and the next
# start makes an empty one again.
_thumbs_db.init_thumbs_db()


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


_MAX_REQUEST_BODY_BYTES = max(1024, int(os.getenv("INKU_MAX_REQUEST_BODY_BYTES", str(16 * 1024 * 1024))))


_MAX_CONCURRENT_REQUESTS = max(1, int(os.getenv("INKU_MAX_CONCURRENT_REQUESTS", "64")))


def _build_date() -> str | None:
    path = Path(__file__).resolve().parents[3] / "web" / "BUILD_NUMBER"
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def _log_destination() -> str:
    """What the banner may honestly claim about where the lines go.

    It used to print `/var/log/inku/inku-api.log` unconditionally, while systemd
    had silently dropped the drop-in that was supposed to fill that file and the
    file sat at 0 bytes for months (ledger I-167). Ask the policy instead.
    """
    from . import db
    from .logging_setup import log_dir

    try:
        enabled = bool(db.get_log_retention_settings()["enabled"])
    except Exception:
        return "no file (policy unreadable)"
    return str(log_dir()) if enabled else "no file (retention disabled)"


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
            f"log: stdout + {_log_destination()}",
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


# Starlette's own exclusion list holds one entry, text/event-stream. Everything
# added here is already compressed, so gzipping it spends the work and returns
# the same bytes: a thumbnail of 115,167 bytes came back 115,026 after 2.87 ms,
# measured 2026-08-16, and a listing page draws up to thirty-five of them.
#
# ⚠ Named one format at a time, not as `image/`. A drawing leaves here as
# image/svg+xml, which is text and compresses to 26% -- the very thing this
# middleware was added for. A family prefix would have excluded it.
#
# The check is `startswith` against this tuple, so a bare type covers the
# `; charset=` forms as well.
_gzip.DEFAULT_EXCLUDED_CONTENT_TYPES = _gzip.DEFAULT_EXCLUDED_CONTENT_TYPES + (
    "image/png",
    "image/apng",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/avif",
    "video/",
    "audio/",
    "application/zip",
    "application/gzip",
)

# Added last, so it is the outermost layer and sees the finished response.
#
# What it is for: a work's SVG goes out uncompressed today. The largest one in
# production on 2026-08-16 was 11,068,576 bytes; at level 6 it is 2,917,551
# (26.4%). Level 9, the library default, spends 572 ms of server time to reach
# 2,890,540 -- 0.9% smaller for 204 ms more, on every such request. Level 6
# takes 368 ms and is what this codebase already picked for the animation
# export, so the two agree.
#
# ⚠ Not Starlette's own class. /api/paint/stream writes an event per stage while
# it works and the page reads them to say which stage is running; the stock
# responder holds those events inside zlib until the response ends, so they all
# arrived at once, when the drawing was already there. FlushingGZipMiddleware is
# the same layer with a flush after each chunk. See compression.py.
app.add_middleware(FlushingGZipMiddleware, minimum_size=500, compresslevel=6)


app.include_router(public.router)
app.include_router(public.authenticated_router)
app.include_router(auth.router)
app.include_router(auth.authenticated_router)
app.include_router(auth.manager_router)
app.include_router(me.router)
app.include_router(plugins.router)
app.include_router(settings.router)
app.include_router(users.router)
app.include_router(history.router)
app.include_router(lineage.router)
app.include_router(render.router)
app.include_router(feedback.router)


def main() -> None:
    import uvicorn

    from .logging_setup import configure_logging

    # The stored policy is executed here, not copied into systemd by an operator.
    configure_logging()

    host = os.getenv("INKU_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("INKU_SERVER_PORT", "8100"))
    reload = _env_flag("INKU_SERVER_RELOAD", default=False)
    uvicorn.run("inku_server.api:app", host=host, port=port, reload=reload)
