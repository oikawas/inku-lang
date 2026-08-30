"""Direct non-image coverage for the derived thumbnail SQLite store."""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from inku_server import thumbs_db


def test_put_thumb_uses_one_atomic_upsert_for_insert_and_replace(
    tmp_path,
    monkeypatch,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'thumbs.db'}", future=True)
    thumbs_db.Base.metadata.create_all(engine)
    monkeypatch.setattr(
        thumbs_db,
        "SessionLocal",
        sessionmaker(bind=engine, autocommit=False, autoflush=False),
    )
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_statement(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        statements.append(" ".join(statement.split()))

    try:
        thumbs_db.put_thumb("history-1", 1, b"first", "rh3:first")
        assert len(statements) == 1
        assert statements[0].startswith("INSERT INTO thumbs")
        assert "ON CONFLICT" in statements[0]

        statements.clear()
        thumbs_db.put_thumb("history-1", 1, b"second", "rh3:second")
        assert len(statements) == 1
        assert "ON CONFLICT" in statements[0]

        stored = thumbs_db.get_thumb("history-1", 1)
        assert stored is not None
        assert stored["png"] == b"second"
        assert stored["source_render_hash"] == "rh3:second"
    finally:
        engine.dispose()
