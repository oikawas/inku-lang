"""History and lineage use the same readable primary-parent generations."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from inku_server.persistence import ancestry, history, lineage
from inku_server.persistence.schema import Base, HistoryRow, LineageEdgeRow, LineageNodeRow


def test_cross_owner_generation_and_depth_independent_queries():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    actor = {"id": "viewer", "permission_groups": ["admins"], "group_id": None}
    with Session(engine) as session:
        for i in range(24):
            owner = "second" if i == 23 else "first"
            session.add(HistoryRow(id=f"h{i}", user_id=owner, at=i, input="", lineage_node_id=f"n{i}"))
            session.add(LineageNodeRow(id=f"n{i}", user_id=owner, history_id=f"h{i}", state="active", at=i,
                                       root_node_id="n0"))
            if i:
                session.add(LineageEdgeRow(id=f"e{i}", user_id=owner, parent_node_id=f"n{i-1}",
                                           child_node_id=f"n{i}", derivation_kind="touch_change", at=i))
        session.commit()
        statements = []
        @event.listens_for(engine, "before_cursor_execute")
        def count(_conn, _cursor, statement, *_args):
            statements.append(statement)
        row = session.get(HistoryRow, "h23")
        projector = history.HistoryListProjector(lambda row: {"id": row.id}, lambda edge: {"metadata": {}})
        listed = projector.rows_to_dicts_with_lineage(session, [row], actor)[0]
        assert sum("FROM pipeline_history_links" in sql for sql in statements) == 1
        store = lineage.LineageStore(None, None, None)
        assert listed["lineage_generation"] == store._lineage_generations(session, actor, ["n23"])["n23"] == 24
        statements.clear()
        ancestry.ancestors(session, ["n23"], actor)
        deep_count = len(statements)
        assert deep_count == 1
        statements.clear()
        ancestry.ancestors(session, ["n0"], actor)
        assert len(statements) == deep_count
    engine.dispose()
