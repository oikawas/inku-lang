"""Resolve the Server's canonical and derived SQLite store locations."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

CANONICAL_DB_ENV = "INKU_DB_URL"
THUMBNAIL_DB_ENV = "INKU_THUMBS_DB_URL"
_SQLITE_FILE_PREFIX = "sqlite:///"
_DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "inku"
DEFAULT_CANONICAL_DB_URL = _SQLITE_FILE_PREFIX + str(_DEFAULT_DATA_DIR / "inku.db")
DEFAULT_THUMBNAIL_DB_URL = _SQLITE_FILE_PREFIX + str(_DEFAULT_DATA_DIR / "thumbs.db")


class PersistenceConfigurationError(ValueError):
    """A configured database URL is invalid for the SQLite-only Server."""


@dataclass(frozen=True)
class PersistenceConfig:
    """The two SQLite URLs selected once during process startup."""

    canonical_url: str
    thumbnail_url: str

    @property
    def canonical_is_default(self) -> bool:
        return self.canonical_url == DEFAULT_CANONICAL_DB_URL


def validate_sqlite_url(value: str, *, setting: str) -> str:
    """Return a valid SQLite URL without exposing its value in an error."""
    if not isinstance(value, str) or not value.strip():
        raise PersistenceConfigurationError(f"{setting} must be a non-empty SQLite URL")
    try:
        parsed = make_url(value)
    except ArgumentError as exc:
        raise PersistenceConfigurationError(f"{setting} must be a valid SQLite URL") from exc
    if parsed.get_backend_name() != "sqlite":
        raise PersistenceConfigurationError(
            f"{setting} must use SQLite; got backend {parsed.get_backend_name()!r}"
        )
    return value


def derive_thumbnail_url(canonical_url: str) -> str:
    """Derive the existing beside-canonical thumbnail location."""
    validate_sqlite_url(canonical_url, setting=CANONICAL_DB_ENV)
    if canonical_url.startswith(_SQLITE_FILE_PREFIX):
        canonical_path = Path(canonical_url[len(_SQLITE_FILE_PREFIX) :]).expanduser()
        return _SQLITE_FILE_PREFIX + str(canonical_path.with_name("thumbs.db"))
    return DEFAULT_THUMBNAIL_DB_URL


def sqlite_database_path(url: str, *, setting: str) -> Path | None:
    """Return the local SQLite path, or None for an in-memory database."""
    validate_sqlite_url(url, setting=setting)
    database = make_url(url).database
    if not database or database == ":memory:":
        return None
    return Path(database).expanduser()


def resolve_persistence_config(
    environ: Mapping[str, str] | None = None,
) -> PersistenceConfig:
    """Resolve and validate both stores before either engine is created."""
    values = os.environ if environ is None else environ
    canonical_url = validate_sqlite_url(
        values.get(CANONICAL_DB_ENV, DEFAULT_CANONICAL_DB_URL),
        setting=CANONICAL_DB_ENV,
    )
    thumbnail_url = validate_sqlite_url(
        values.get(THUMBNAIL_DB_ENV) or derive_thumbnail_url(canonical_url),
        setting=THUMBNAIL_DB_ENV,
    )
    return PersistenceConfig(
        canonical_url=canonical_url,
        thumbnail_url=thumbnail_url,
    )


# Both consumers share this startup snapshot. Reading the environment separately
# would let import order select two configurations for one process.
PERSISTENCE_CONFIG = resolve_persistence_config()
