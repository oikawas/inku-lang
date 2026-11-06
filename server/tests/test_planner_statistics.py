"""Startup lets SQLite decide whether planner statistics need updating."""

from sqlalchemy import event

from inku_server import db


def test_a_start_leaves_the_planner_statistics():
    statements = []
    def record(_connection, _cursor, statement, *_):
        statements.append(statement)
    event.listen(db.engine, "before_cursor_execute", record)
    try:
        db.init_db()
    finally:
        event.remove(db.engine, "before_cursor_execute", record)
    assert any(statement.strip().upper() == "PRAGMA OPTIMIZE" for statement in statements)
