"""Focused boundary checks for the opt-in variation-authority sidecar."""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import create_engine

from inku_server.persistence.variation_authority import (
    AUTHORITY_PROTOCOL,
    ActionIdentityConflict,
    VariationAuthorityAdapterError,
    VariationAuthorityStore,
)


def _core_digest(
    value: object,
    *,
    domain: str = AUTHORITY_PROTOCOL,
    sort_keys: bool = False,
) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=sort_keys,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(domain.encode("utf-8"))
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    return digest.hexdigest()


def _action(
    *,
    action_digit: str,
    source: str,
    expected_revision: str,
    next_revision: str,
    origin: str = "stage1_generated",
    authority: str = "description_authoritative",
    attempt: int = 1,
) -> dict:
    state = {
        "protocol_version": AUTHORITY_PROTOCOL,
        "revision": next_revision,
        "origin": origin,
        "authority": authority,
    }
    document = {"source": source, "language": "ja", "macro_locks": []}
    payload = {
        "variation_id": "variation-1",
        "document": document,
        "ddl_digest": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "authority": {
            "expected_revision": expected_revision,
            "next_state": state,
        },
        "authority_digest": _core_digest(state),
        "reason": "focused_test",
    }
    return {
        "tag": "commit_visible_normalized_ddl",
        "version": 1,
        "identity": {
            "action_id": action_digit * 64,
            "attempt": attempt,
            "request_digest": _core_digest(
                payload,
                domain="inku.pipeline-request.v1",
                sort_keys=True,
            ),
        },
        "timeout_ms": "0",
        "delay_ms": "0",
        "payload": payload,
    }


def test_atomic_authority_commit_replays_ack_and_rejects_stale_tab(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'authority.db'}"
    first_engine = create_engine(database_url, future=True)
    second_engine = create_engine(database_url, future=True)
    first_tab = VariationAuthorityStore(
        first_engine, now_ms=lambda: 1_777_777_777
    )
    second_tab = VariationAuthorityStore(
        second_engine, now_ms=lambda: 1_777_777_778
    )
    first_tab.install_schema()

    initial = _action(
        action_digit="1",
        source="赤い円を描く。",
        expected_revision="0",
        next_revision="1",
    )
    first = first_tab.commit_effect(
        "author-1", initial, create_if_missing=True
    )
    retried = json.loads(json.dumps(initial))
    retried["identity"]["attempt"] = 2

    assert first_tab.commit_effect("author-1", retried) == {
        **first,
        "identity": {**first["identity"], "attempt": 2},
    }
    assert first_tab.inventory().action_acknowledgments == 1

    stale_description = _action(
        action_digit="2",
        source="青い円を描く。",
        expected_revision="1",
        next_revision="2",
    )
    locking_edit = _action(
        action_digit="3",
        source="大きな赤い円を描く。",
        expected_revision="1",
        next_revision="2",
        authority="ddl_authoritative",
    )
    assert second_tab.commit_effect("author-1", locking_edit)["tag"] == (
        "visible_normalized_ddl_committed"
    )

    assert first_tab.commit_effect("author-1", stale_description) == {
        "tag": "host_commit_failed",
        "identity": stale_description["identity"],
        "actual_revision": "2",
    }
    saved = first_tab.read("author-1", "variation-1")
    assert saved is not None
    assert saved["document"]["source"] == "大きな赤い円を描く。"
    assert saved["authority"] == {
        "protocol_version": AUTHORITY_PROTOCOL,
        "revision": "2",
        "origin": "stage1_generated",
        "authority": "ddl_authoritative",
    }
    first_engine.dispose()
    second_engine.dispose()


def test_origin_and_description_lock_are_immutable(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'authority.db'}", future=True)
    store = VariationAuthorityStore(engine)
    store.install_schema()
    store.commit_effect(
        "author-1",
        _action(
            action_digit="1",
            source="円。",
            expected_revision="0",
            next_revision="1",
            authority="ddl_authoritative",
        ),
        create_if_missing=True,
    )

    unlock = _action(
        action_digit="2",
        source="円と線。",
        expected_revision="1",
        next_revision="2",
        authority="description_authoritative",
    )
    with pytest.raises(VariationAuthorityAdapterError, match="cannot be unlocked"):
        store.commit_effect("author-1", unlock)

    changed_origin = _action(
        action_digit="3",
        source="円と線。",
        expected_revision="1",
        next_revision="2",
        origin="user_authored_ddl",
        authority="ddl_authoritative",
    )
    with pytest.raises(VariationAuthorityAdapterError, match="origin is immutable"):
        store.commit_effect("author-1", changed_origin)

    reused_identity = json.loads(json.dumps(unlock))
    reused_identity["identity"]["action_id"] = "1" * 64
    with pytest.raises(ActionIdentityConflict):
        store.commit_effect("author-1", reused_identity)
    engine.dispose()


def test_inventory_keeps_history_explicitly_legacy_unknown_without_reading_text(
    tmp_path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'inventory.db'}", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE history "
            "(id TEXT PRIMARY KEY, input TEXT NOT NULL, ddl TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO history(id, input, ddl) VALUES "
            "('old-description', 'do not classify me', NULL), "
            "('old-ddl', '', '円を描く。')"
        )
    store = VariationAuthorityStore(engine)

    before = store.inventory()
    assert before.history_rows == 2
    assert before.legacy_unknown_history_rows == 2
    assert before.history_authority_columns_present is False
    assert before.candidate_tables_present is False

    store.install_schema()
    after = store.inventory()
    assert after.history_rows == 2
    assert after.legacy_unknown_history_rows == 2
    assert after.candidate_tables_present is True
    assert after.candidate_variations == 0
    assert after.action_acknowledgments == 0
    engine.dispose()
