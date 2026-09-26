"""A permanent deletion takes the drafts its works were the last trace of.

The author's decision (2026-09-26): deleting a work for good used to leave the
draft it was saved from -- the description and DDL -- until the account was
deleted. A draft is shared, though, and may still be in use, so it goes only
when nothing else reaches or needs it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence.schema import (
    Base,
    PipelineCandidateExecutionRow,
    PipelineHistoryLinkRow,
    ProviderObservationRow,
    VariationAuthorityActionRow,
    VariationAuthorityRow,
)


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'drafts.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine, autocommit=False, autoflush=False))
    db._ensure_permission_groups()


def _work(owner: str, at: int) -> str:
    return db.add_item({
        "id": str(uuid.uuid4()), "user_id": owner, "at": at, "input": "松", "source_text": "松",
        "ddl": "背景を白で塗る。", "score": {"canvas": "square", "instructions": []},
        "svg": "<svg xmlns='http://www.w3.org/2000/svg'/>", "history_visibility": "normal",
    })["id"]


def _draft(session, owner: str, variation: str, revision: str, parent: str | None = None) -> None:
    session.add(VariationAuthorityRow(
        owner_id=owner, variation_id=variation, protocol_version="inku.variation-authority.v1",
        revision=revision, origin="stage1_generated", authority="description_authoritative",
        source="背景を白で塗る。", document_json="{}", ddl_digest="d", authority_digest="a",
        description="松", derivation_kind="description_fork" if parent else "new",
        parent_variation_id=parent, updated_at=1,
    ))


def _saved(session, owner: str, work: str, variation: str, revision: str) -> None:
    session.add(PipelineHistoryLinkRow(
        owner_id=owner, history_id=work, variation_id=variation, revision=revision,
        ddl_digest="d", fork_context_bytes=b"{}", fork_context_digest="f",
    ))


def test_a_draft_goes_only_when_nothing_else_reaches_it(fresh_db) -> None:
    owner = db.add_user("drafts", "drafts@example.test", "password-1", ["admins"], None)["id"]
    alone, moved_on, shared, shared_twin, forked = (_work(owner, at) for at in range(1, 6))
    with db.SessionLocal() as session:
        _draft(session, owner, "alone", "2")
        _saved(session, owner, alone, "alone", "2")
        session.add(PipelineCandidateExecutionRow(
            owner_id=owner, execution_id="run", variation_id="alone", sequence="1",
            state_bytes=b"x", state_digest="s", created_at=1, updated_at=1,
        ))
        session.add(ProviderObservationRow(
            owner_id=owner, execution_id="run", action_id="act", request_digest="r", action_tag="t",
            stage="stage1", provider_id="p", model="m", attempt=1, timeout_ms=1, request_body="{}",
            created_at=1, updated_at=1,
        ))
        session.add(VariationAuthorityActionRow(
            owner_id=owner, action_id="act", variation_id="alone", request_digest="r",
            action_fingerprint="f", context_fingerprint="c", ddl_digest="d", revision="2",
            authority_digest="a", committed_at=1,
        ))
        # Written on after the save: the page may still be authoring it.
        _draft(session, owner, "moved-on", "3")
        _saved(session, owner, moved_on, "moved-on", "1")
        # Two works drawn from one draft; one of them stays.
        _draft(session, owner, "shared", "1")
        _saved(session, owner, shared, "shared", "1")
        _saved(session, owner, shared_twin, "shared", "1")
        # Another draft was forked from this one and names it as its parent.
        _draft(session, owner, "forked", "1")
        _saved(session, owner, forked, "forked", "1")
        _draft(session, owner, "child", "1", parent="forked")
        session.commit()

    assert db.delete_items(owner, [alone, moved_on, shared, forked]) == 4

    with db.SessionLocal() as session:
        left = {row.variation_id for row in session.query(VariationAuthorityRow).filter_by(owner_id=owner)}
        assert left == {"moved-on", "shared", "forked", "child"}
        assert session.query(PipelineCandidateExecutionRow).filter_by(owner_id=owner).count() == 0
        assert session.query(ProviderObservationRow).filter_by(owner_id=owner).count() == 0
        assert session.query(VariationAuthorityActionRow).filter_by(owner_id=owner).count() == 0
        assert [row.history_id for row in session.query(PipelineHistoryLinkRow)] == [shared_twin]
