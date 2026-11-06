"""Startup lets SQLite decide whether planner statistics need updating."""

from sqlalchemy import create_engine, event, text

from inku_server import db


def test_a_start_leaves_the_planner_statistics():
    db.init_db()
    with db.engine.connect() as connection:
        tables = connection.execute(text("SELECT count(*) FROM sqlite_master WHERE name = 'sqlite_stat1'")).scalar()
    assert tables == 1


def test_existing_statistics_use_optimize_without_analyze(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'planner.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE work (id INTEGER PRIMARY KEY, value TEXT)")
        connection.exec_driver_sql("CREATE INDEX work_value ON work(value)")
        connection.exec_driver_sql("INSERT INTO work VALUES (1, 'one')")
        connection.exec_driver_sql("ANALYZE")
    monkeypatch.setattr(db, "engine", engine)
    statements = []
    def record(_connection, _cursor, statement, *_):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", record)
    try:
        db._refresh_planner_statistics()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert any(statement.strip().upper() == "PRAGMA OPTIMIZE" for statement in statements)
    assert not any(statement.strip().upper() == "ANALYZE" for statement in statements)
    engine.dispose()
