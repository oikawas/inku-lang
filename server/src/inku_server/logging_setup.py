"""File logging the application performs itself.

The retention policy (enabled / days / rotation / compression) lives in the app
DB beside the database-backup policy, and this module executes it in process.

Nothing here is delegated to systemd or logrotate. The container distribution
has neither, so a policy the platform executes cannot be the same policy on
both deployments -- which is how `StandardOutput=journal+append:` came to be
handed to operators for months without anyone writing a byte to a file
(ledger I-167). The database backup already worked this way: the app decides
when to copy and how many generations to keep. Logs now match it.

The stream handler stays attached, so `journalctl -u inku-api` on bare metal and
`docker logs` in a container keep showing the same lines they always did.
"""
from __future__ import annotations

import gzip
import logging
import os
import shutil
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "inku-api.log"

_DEFAULT_LOG_DIR = Path.home() / ".local" / "share" / "inku" / "logs"

# (when, interval) for TimedRotatingFileHandler. The three choices must stay
# distinct in the pair, not just in `when`: a gate that only reads `when` cannot
# tell "daily" from "monthly".
_ROTATE_SCHEDULE = {
    "daily": ("midnight", 1),
    "weekly": ("W0", 1),
    "monthly": ("midnight", 30),
}

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

_installed: TimedRotatingFileHandler | None = None


def log_dir() -> Path:
    """Where the app writes its own log files.

    The container image points this at the data volume (`/data/logs`) so the
    files survive a restart the same way `INKU_DB_BACKUP_DIR` does.
    """
    return Path(os.getenv("INKU_LOG_DIR", str(_DEFAULT_LOG_DIR))).expanduser()


def rotation_schedule(rotate: str) -> tuple[str, int]:
    return _ROTATE_SCHEDULE.get(rotate, _ROTATE_SCHEDULE["daily"])


def _gzip_rotator(source: str, dest: str) -> None:
    with open(source, "rb") as raw, gzip.open(f"{dest}.gz", "wb") as packed:
        shutil.copyfileobj(raw, packed)
    os.remove(source)


def _plain_rotator(source: str, dest: str) -> None:
    os.replace(source, dest)


def build_file_handler(settings: dict) -> TimedRotatingFileHandler | None:
    """The file handler the stored policy asks for, or None when disabled."""
    if not settings.get("enabled"):
        return None
    directory = log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    when, interval = rotation_schedule(str(settings.get("rotate", "daily")))
    handler = TimedRotatingFileHandler(
        directory / LOG_FILE_NAME,
        when=when,
        interval=interval,
        # One kept file per retained day: this is the number the settings screen
        # calls "retention days", and it has to arrive here to mean anything.
        backupCount=int(settings.get("retention_days", 90)),
        encoding="utf-8",
        utc=False,
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.rotator = _gzip_rotator if settings.get("compress") else _plain_rotator
    return handler


def configure_logging(settings: dict | None = None) -> TimedRotatingFileHandler | None:
    """Attach the file handler described by the stored policy.

    Safe to call again after the policy changes: the previous file handler is
    detached first, so an operator who lowers the retention does not keep the
    old handler alive until the next restart.
    """
    global _installed

    if settings is None:
        from . import db

        settings = db.get_log_retention_settings()

    root = logging.getLogger()
    if root.level == logging.NOTSET:
        root.setLevel(logging.INFO)

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(stream)

    if _installed is not None:
        root.removeHandler(_installed)
        _installed.close()
        _installed = None

    handler = build_file_handler(settings)
    if handler is not None:
        root.addHandler(handler)
        _installed = handler
    return handler


def installed_file_handler() -> TimedRotatingFileHandler | None:
    return _installed


def current_log_files() -> list[str]:
    directory = log_dir()
    if not directory.exists():
        return []
    return sorted(p.name for p in directory.glob(f"{LOG_FILE_NAME}*"))
