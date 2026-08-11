"""Thumbnail store — a derived SQLite database beside the canonical one.

A thumbnail is a rasterization of a work's saved SVG. Nothing here is a source
of truth: every row can be baked again from the canonical database, so deleting
this file costs rebuild time and nothing else. That is the point of keeping it
out of `inku.db` — the canonical database does not grow, and "clear every
thumbnail" is `rm thumbs.db`.

  default:  beside INKU_DB_URL's file, named thumbs.db
  override: INKU_THUMBS_DB_URL=sqlite:////var/lib/inku/thumbs.db

The default is derived rather than required, so a deployment that has only ever
set INKU_DB_URL keeps working without learning a second variable.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from sqlalchemy import BigInteger, Column, Integer, LargeBinary, String, create_engine, event, func, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# The canonical URL rather than os.getenv: the default that produced it lives in
# db.py, and reading the environment again here would be a second copy of it.
from .db import _DB_URL as _CANONICAL_DB_URL

_logger = logging.getLogger("inku.thumbs")

_SQLITE_PREFIX = "sqlite:///"


def _derived_thumbs_url(canonical_url: str) -> str:
    """Where thumbnails go when nothing was configured for them."""
    if canonical_url.startswith(_SQLITE_PREFIX):
        canonical_path = Path(canonical_url[len(_SQLITE_PREFIX):]).expanduser()
        return _SQLITE_PREFIX + str(canonical_path.with_name("thumbs.db"))
    # A canonical database on another server says nothing about where a derived
    # file belongs, so fall back to the directory the default canonical one uses.
    return _SQLITE_PREFIX + str(Path.home() / ".local" / "share" / "inku" / "thumbs.db")


_THUMBS_DB_URL = os.getenv("INKU_THUMBS_DB_URL") or _derived_thumbs_url(_CANONICAL_DB_URL)

_connect_args = {"check_same_thread": False} if _THUMBS_DB_URL.startswith("sqlite") else {}
engine = create_engine(_THUMBS_DB_URL, echo=False, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


if _THUMBS_DB_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_wal(dbapi_connection, _connection_record) -> None:
        # Rebuilds write from a pool of threads while the listing reads. WAL lets
        # those overlap instead of serializing behind a writer.
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


class Base(DeclarativeBase):
    pass


class ThumbRow(Base):
    __tablename__ = "thumbs"

    history_id = Column(String, primary_key=True)
    # One row holds one scale. Two sizes in one row would make deleting the
    # HiDPI set a rewrite of every row instead of a delete.
    scale = Column(Integer, primary_key=True)
    png = Column(LargeBinary, nullable=False)
    # The render hash of the SVG this was baked from. A thumbnail whose source
    # has moved is stale, and comparing two short strings says so without
    # reading either picture.
    source_render_hash = Column(String, nullable=True, index=True)
    built_at = Column(BigInteger, nullable=False)


#: The scales a thumbnail may be stored at. 1 is always kept; 2 is the HiDPI
#: option and is the only one a settings change may delete.
SCALES = (1, 2)
BASE_WIDTH = 256


def width_for_scale(scale: int) -> int:
    """The pixel width a thumbnail of this scale is rasterized at.

    Only the width is ever given to the rasterizer, which scales the other side
    to preserve the aspect ratio; a thumbnail is the work's own shape, smaller.
    """
    if scale not in SCALES:
        raise ValueError(f"unsupported thumbnail scale: {scale}")
    return BASE_WIDTH * scale


def init_thumbs_db() -> None:
    if _THUMBS_DB_URL.startswith(_SQLITE_PREFIX):
        db_path = Path(_THUMBS_DB_URL[len(_SQLITE_PREFIX):]).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


def thumbs_db_path() -> str | None:
    """The file backing the store, when it is a file. For reporting its size."""
    if not _THUMBS_DB_URL.startswith(_SQLITE_PREFIX):
        return None
    return str(Path(_THUMBS_DB_URL[len(_SQLITE_PREFIX):]).expanduser())


def get_thumb(history_id: str, scale: int) -> dict | None:
    with SessionLocal() as session:
        row = session.get(ThumbRow, (history_id, scale))
        if row is None:
            return None
        return {
            "history_id": row.history_id,
            "scale": row.scale,
            "png": row.png,
            "source_render_hash": row.source_render_hash,
            "built_at": row.built_at,
        }


def put_thumb(history_id: str, scale: int, png: bytes, source_render_hash: str | None) -> None:
    """Write a thumbnail, replacing any earlier one for the same id and scale.

    Replacing rather than deleting-then-inserting is what lets a rebuild serve
    the old picture until the new one is ready: there is no moment at which the
    row is absent.
    """
    now = int(time.time() * 1000)
    with SessionLocal() as session:
        row = session.get(ThumbRow, (history_id, scale))
        if row is None:
            session.add(ThumbRow(
                history_id=history_id,
                scale=scale,
                png=png,
                source_render_hash=source_render_hash,
                built_at=now,
            ))
        else:
            row.png = png
            row.source_render_hash = source_render_hash
            row.built_at = now
        session.commit()


def stored_hashes(scale: int) -> dict[str, str | None]:
    """Every id at this scale, with the render hash it was baked from."""
    with SessionLocal() as session:
        rows = session.execute(
            select(ThumbRow.history_id, ThumbRow.source_render_hash).where(ThumbRow.scale == scale)
        ).all()
    return {history_id: source_hash for history_id, source_hash in rows}


def delete_scale(scale: int) -> int:
    """Drop every thumbnail at one scale. Used when HiDPI is turned off."""
    with SessionLocal() as session:
        rows = session.query(ThumbRow).filter(ThumbRow.scale == scale).delete()
        session.commit()
    return int(rows)


def delete_for_history(history_ids: list[str]) -> int:
    if not history_ids:
        return 0
    with SessionLocal() as session:
        rows = session.query(ThumbRow).filter(ThumbRow.history_id.in_(history_ids)).delete(
            synchronize_session=False
        )
        session.commit()
    return int(rows)


def counts_by_scale() -> dict[int, int]:
    with SessionLocal() as session:
        rows = session.execute(
            select(ThumbRow.scale, func.count()).group_by(ThumbRow.scale)
        ).all()
    return {int(scale): int(count) for scale, count in rows}


def stored_bytes() -> int:
    """Total size of the stored PNGs. Not the file size, which includes WAL."""
    with SessionLocal() as session:
        total = session.execute(select(func.sum(func.length(ThumbRow.png)))).scalar()
    return int(total or 0)
