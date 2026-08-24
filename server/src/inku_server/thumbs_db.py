"""Thumbnail store — a derived SQLite database beside the canonical one.

A thumbnail is a rasterization of a work's saved SVG. Nothing here is a source
of truth: every row can be baked again from the canonical database, so deleting
this file costs rebuild time and nothing else. That is the point of keeping it
out of `inku.db` — the canonical database does not grow, and "clear every
thumbnail" is `rm thumbs.db`.

  default:  beside INKU_DB_URL's file, named thumbs.db
  override: INKU_THUMBS_DB_URL=sqlite:////var/lib/inku/thumbs.db

The default is derived rather than required, so a deployment that sets only the
canonical URL keeps working without learning a second variable.
"""
from __future__ import annotations

import time

from sqlalchemy import BigInteger, Column, Integer, LargeBinary, String, func, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .persistence.config import PERSISTENCE_CONFIG, THUMBNAIL_DB_ENV, sqlite_database_path
from .persistence.engine import THUMBNAIL_SQLITE_PRAGMAS, create_sqlite_engine

engine = create_sqlite_engine(
    PERSISTENCE_CONFIG.thumbnail_url,
    setting=THUMBNAIL_DB_ENV,
    pragmas=THUMBNAIL_SQLITE_PRAGMAS,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


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
    db_path = sqlite_database_path(
        PERSISTENCE_CONFIG.thumbnail_url,
        setting=THUMBNAIL_DB_ENV,
    )
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


def thumbs_db_path() -> str | None:
    """The file backing the store, when it is a file. For reporting its size."""
    path = sqlite_database_path(
        PERSISTENCE_CONFIG.thumbnail_url,
        setting=THUMBNAIL_DB_ENV,
    )
    return str(path) if path is not None else None


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
