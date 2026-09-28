"""Which works are held by their DDL, so that none is redrawn from its description."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from inku_server.persistence.description_lock import locked_history_ids, node_is_locked
from inku_server.persistence.schema import (
    HistoryRow,
    LineageEdgeRow,
    LineageNodeRow,
    PipelineHistoryLinkRow,
    VariationAuthorityRow,
)


def _session() -> Session:
    engine = create_engine("sqlite://")
    for table in (HistoryRow, LineageNodeRow, LineageEdgeRow, PipelineHistoryLinkRow, VariationAuthorityRow):
        table.__table__.create(engine)
    return Session(engine)


def _work(session: Session, history_id: str, parent: str | None = None, kind: str | None = None,
          authority: str | None = None, ddl: str | None = None) -> None:
    if ddl is not None:
        session.add(HistoryRow(id=history_id, at=0, input="", ddl=ddl))
    session.add(LineageNodeRow(id=f"n-{history_id}", user_id="u", history_id=history_id, state="active", at=0))
    if parent is not None:
        session.add(LineageEdgeRow(id=f"e-{history_id}", user_id="u", parent_node_id=f"n-{parent}",
                                   child_node_id=f"n-{history_id}", derivation_kind=kind, metadata_json="{}", at=0))
    if authority is not None:
        session.add(PipelineHistoryLinkRow(owner_id="u", history_id=history_id, variation_id=f"v-{history_id}",
                                           revision="1", ddl_digest="d", fork_context_bytes=b"", fork_context_digest="d"))
        session.add(VariationAuthorityRow(
            owner_id="u", variation_id=f"v-{history_id}", protocol_version="p", revision="1",
            origin="user_authored_ddl" if authority == "ddl_authoritative" else "stage1_generated",
            authority=authority, source="", document_json="{}", ddl_digest="d", authority_digest="d",
            derivation_kind="new", updated_at=0,
        ))


def test_a_ddl_edit_and_what_keeps_its_ddl_are_locked_and_a_new_reading_is_not():
    session = _session()
    _work(session, "root", authority="description_authoritative")
    _work(session, "edited", "root", "ddl_edit")            # a DDL edit saved before the authority existed
    _work(session, "touched", "edited", "touch_change")    # keeps the edited DDL
    _work(session, "recolored", "touched", "catalog_change")
    _work(session, "reread", "recolored", "reinterpretation")  # back to the words
    _work(session, "reread-touched", "reread", "touch_change")
    _work(session, "authored", authority="ddl_authoritative")  # a DDL-authoritative variation
    _work(session, "sibling", "root", "layout_change")
    session.commit()

    everything = ["root", "edited", "touched", "recolored", "reread", "reread-touched", "authored", "sibling", "unknown"]
    assert locked_history_ids(session, everything) == {"edited", "touched", "recolored", "authored"}
    assert node_is_locked(session, "n-recolored") is True
    assert node_is_locked(session, "n-reread-touched") is False
    assert locked_history_ids(session, []) == set()


def test_a_replay_is_held_by_its_ddl_not_by_its_kind():
    session = _session()
    _work(session, "edited", authority="ddl_authoritative", ddl="Scene:\n  Moon")
    # The Describe tab saved an unchanged description drawn again as a replay:
    # Stage 1 wrote a new DDL, so it went back to the words.
    _work(session, "reread", "edited", "replay", authority="description_authoritative", ddl="Scene:\n  Sun")
    # The same DDL drawn again from the DDL panel: a DDL-authoritative variation
    # with no edit, held because its parent is.
    _work(session, "redrawn", "edited", "replay", authority="ddl_authoritative", ddl="Scene:  Moon")
    _work(session, "plain", authority="description_authoritative", ddl="Scene: Sun")
    _work(session, "plain-redrawn", "plain", "replay", authority="ddl_authoritative", ddl="Scene: Sun")
    _work(session, "plain-redrawn-touched", "plain-redrawn", "touch_change", ddl="Scene: Sun, soft")
    _work(session, "unknown-ddl", "edited", "replay")  # nothing to compare: as before
    session.commit()

    everything = ["edited", "reread", "redrawn", "plain", "plain-redrawn", "plain-redrawn-touched", "unknown-ddl"]
    assert locked_history_ids(session, everything) == {"edited", "redrawn", "unknown-ddl"}
    assert node_is_locked(session, "n-plain-redrawn") is False
