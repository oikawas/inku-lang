"""The query planner has statistics once the server has started."""

from sqlalchemy import text

from inku_server import db


def test_a_start_leaves_the_planner_statistics():
    db.init_db()
    with db.engine.connect() as connection:
        tables = connection.execute(text("SELECT count(*) FROM sqlite_master WHERE name = 'sqlite_stat1'")).scalar()
    assert tables == 1
