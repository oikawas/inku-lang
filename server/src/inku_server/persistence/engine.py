"""Build SQLite engines with the Server's connection-time integrity settings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine as _sqlalchemy_create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .config import validate_sqlite_url


@dataclass(frozen=True)
class SQLitePragmas:
    """Connection PRAGMAs owned by one SQLite store."""

    foreign_keys: bool = False
    busy_timeout_ms: int | None = None
    wal: bool = False


CANONICAL_SQLITE_PRAGMAS = SQLitePragmas(
    foreign_keys=True,
    busy_timeout_ms=10_000,
    wal=True,
)
# Thumbnail rebuilds write from a worker pool while listings read. WAL lets
# those overlap instead of serializing every reader behind the writer.
THUMBNAIL_SQLITE_PRAGMAS = SQLitePragmas(wal=True)


def create_sqlite_engine(
    url: str,
    *,
    setting: str,
    pragmas: SQLitePragmas,
) -> Engine:
    """Validate first, then build an engine that configures every connection."""
    validated_url = validate_sqlite_url(url, setting=setting)
    engine = _sqlalchemy_create_engine(
        validated_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            if pragmas.foreign_keys:
                cursor.execute("PRAGMA foreign_keys=ON")
            if pragmas.busy_timeout_ms is not None:
                cursor.execute(f"PRAGMA busy_timeout={pragmas.busy_timeout_ms}")
            if pragmas.wal:
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

    return engine
