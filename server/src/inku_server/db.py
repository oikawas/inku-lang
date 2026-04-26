"""DB layer — SQLite (default) or PostgreSQL via INKU_DB_URL.

  SQLite:     INKU_DB_URL=sqlite:///~/.local/share/inku/inku.db  (default)
  PostgreSQL: INKU_DB_URL=postgresql://user:pass@localhost/inku
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import BigInteger, Column, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DEFAULT_DB = "sqlite:///" + str(Path.home() / ".local" / "share" / "inku" / "inku.db")
_DB_URL = os.getenv("INKU_DB_URL", _DEFAULT_DB)

_connect_args = {"check_same_thread": False} if _DB_URL.startswith("sqlite") else {}
engine = create_engine(_DB_URL, echo=False, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class HistoryRow(Base):
    __tablename__ = "history"

    id           = Column(String,     primary_key=True)
    at           = Column(BigInteger, nullable=False, index=True)
    input        = Column(Text,       nullable=False, default="")
    ddl          = Column(Text,       nullable=True)
    score        = Column(Text,       nullable=False, default="{}")
    svg          = Column(Text,       nullable=False, default="")
    output_path  = Column(Text,       nullable=True)
    elapsed_ms   = Column(Integer,    nullable=False, default=0)
    stage1_model = Column(String,     nullable=True)
    stage2_model = Column(String,     nullable=True)
    tokens_in    = Column(Integer,    nullable=True)
    tokens_out   = Column(Integer,    nullable=True)


def init_db() -> None:
    if _DB_URL.startswith("sqlite:///"):
        db_path = Path(_DB_URL[len("sqlite:///"):]).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


def _row_to_dict(row: HistoryRow) -> dict:
    return {
        "id":           row.id,
        "at":           row.at,
        "input":        row.input,
        "ddl":          row.ddl,
        "score":        json.loads(row.score) if row.score else {},
        "svg":          row.svg,
        "output_path":  row.output_path,
        "elapsed_ms":   row.elapsed_ms,
        "stage1_model": row.stage1_model,
        "stage2_model": row.stage2_model,
        "tokens_in":    row.tokens_in,
        "tokens_out":   row.tokens_out,
    }


def add_item(item: dict) -> dict:
    row = HistoryRow(
        id=item["id"],
        at=item["at"],
        input=item.get("input", ""),
        ddl=item.get("ddl"),
        score=json.dumps(item.get("score", {})),
        svg=item.get("svg", ""),
        output_path=item.get("output_path"),
        elapsed_ms=item.get("elapsed_ms", 0),
        stage1_model=item.get("stage1_model"),
        stage2_model=item.get("stage2_model"),
        tokens_in=item.get("tokens_in"),
        tokens_out=item.get("tokens_out"),
    )
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return _row_to_dict(row)


def list_items(offset: int = 0, limit: int = 10) -> tuple[list[dict], int]:
    with SessionLocal() as session:
        total: int = session.query(func.count(HistoryRow.id)).scalar() or 0
        rows = (
            session.query(HistoryRow)
            .order_by(HistoryRow.at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_row_to_dict(r) for r in rows], total


def delete_all() -> None:
    with SessionLocal() as session:
        session.query(HistoryRow).delete()
        session.commit()
