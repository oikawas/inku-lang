"""Library anchors use the visible filtered order, including tied timestamps."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from inku_server import db
from inku_server.api_core.routers import history, lineage
from inku_server.persistence.schema import Base, HistoryRow, LineageNodeRow


def test_library_positions_respect_search_marks_access_and_selected_singleton(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(db, "SessionLocal", sessions)
    monkeypatch.setattr(db, "_HISTORY_FTS_ENABLED", False)
    db._ensure_permission_groups()
    owner = db.add_user("library-owner", "library-owner@example.test", "password-123", ["users"], None)
    other = db.add_user("library-other", "library-other@example.test", "password-123", ["users"], None)
    with sessions() as session:
        for item_id, root, at, label, starred, user_id in [
            ("a", "root-a", 30, "keep blue", 1, owner["id"]),
            ("b", "root-b", 20, "keep blue", 1, owner["id"]),
            ("c", "root-c", 20, "keep blue", 1, owner["id"]),
            ("d", "root-d", 10, "keep red", 0, owner["id"]),
            ("private", "root-private", 40, "keep blue", 1, other["id"]),
        ]:
            session.add(HistoryRow(id=item_id, user_id=user_id, at=at, input=label, score='{"instructions":[]}', lineage_node_id=root, history_visibility="normal", starred=starred))
            session.add(LineageNodeRow(id=root, user_id=user_id, history_id=item_id, at=at, root_node_id=root))
        session.commit()
    def listing(**kwargs):
        return history.api_history_get(**{
            "offset": 0, "limit": 1, "trashed": False, "starred": False,
            "for_revision": False, "for_share": False, "q": "", "canvas_search": False,
            "anchor_id": "c", "include_svg": False, "actor": owner, **kwargs,
        })

    def grouped(**kwargs):
        return lineage.api_history_lineage_groups(**{
            "offset": 0, "limit": 8, "trashed": False, "starred": True,
            "for_revision": False, "for_share": False, "q": "blue", "min_items": 1,
            "anchor_id": "c", "include_id": None, "include_svg": False, "actor": owner, **kwargs,
        })

    page = listing(q="blue", starred=True)
    assert page.offset == 2
    assert [item.id for item in page.items] == ["c"]
    excluded = listing(offset=1, q="red")
    assert excluded.offset == 1, "an excluded anchor must not move the retained page"
    assert db.item_position(owner["id"], "private", query_text="blue") is None
    groups = grouped(min_items=2)
    assert groups.offset == 0
    assert groups.total == 1
    assert [group.root_node_id for group in groups.groups] == ["root-c"]
    all_groups = grouped()
    assert all_groups.offset == 2
    assert [group.root_node_id for group in all_groups.groups] == ["root-c"]
    assert db.lineage_group_position(owner["id"], "c", query_text="red") is None
    assert db.lineage_group_position(owner["id"], "private") is None
    with sessions() as session:
        session.execute(text("CREATE VIRTUAL TABLE history_fts USING fts5(input, ddl, stage1_model, stage2_model, catalog_id, tokenize='trigram')"))
        session.execute(text("INSERT INTO history_fts(rowid,input,ddl,stage1_model,stage2_model,catalog_id) SELECT rowid,input,ddl,stage1_model,stage2_model,catalog_id FROM history"))
        session.commit()
    monkeypatch.setattr(db, "_HISTORY_FTS_ENABLED", True)
    fts_page = listing(q="keep blue", starred=True)
    assert fts_page.offset == 2
    assert [item.id for item in fts_page.items] == ["c"]
    assert db.item_position(owner["id"], "c", query_text="keep blu%") is None
