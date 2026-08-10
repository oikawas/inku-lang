from __future__ import annotations

import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from inku_server import db
from inku_server.api import app


client = TestClient(app)


def _user(prefix: str) -> tuple[dict, dict[str, str], str, str]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"{prefix}-group-{suffix}")
    user = db.add_user(
        f"{prefix}-{suffix}",
        f"{prefix}-{suffix}@example.test",
        "password-123",
        ["users"],
        group["id"],
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token, group["id"]


def _item(user_id: str, label: str, at: int) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "at": at,
        "input": label,
        "source_text": label,
        "ddl": "背景を白で塗る。",
        "score": {"canvas": "square", "instructions": []},
        "svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
    }


def _cleanup(user: dict, token: str, group_id: str) -> None:
    db.delete_all(user["id"])
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group_id)


def test_sqlite_connections_enforce_foreign_keys() -> None:
    if db.engine.dialect.name != "sqlite":
        return
    with db.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_permanent_delete_requires_trash_and_keeps_tombstone() -> None:
    user, headers, token, group_id = _user("safe-delete")
    try:
        item = db.add_item(_item(user["id"], "active", int(time.time() * 1000)))

        active_delete = client.post(
            "/api/history/permanent-delete",
            headers=headers,
            json={"ids": [item["id"]]},
        )
        assert active_delete.status_code == 200
        assert active_delete.json()["count"] == 0
        assert db.get_items(user["id"], [item["id"]])

        assert client.post("/api/history/trash", headers=headers, json={"ids": [item["id"]]}).json()["count"] == 1
        deleted = client.post(
            "/api/history/permanent-delete",
            headers=headers,
            json={"ids": [item["id"]]},
        )
        assert deleted.status_code == 200
        assert deleted.json()["count"] == 1
        graph = db.get_lineage(user["id"], item["lineage_node_id"])
        assert graph is not None
        assert graph["nodes"][0]["state"] == "tombstone"
    finally:
        _cleanup(user, token, group_id)


def test_delete_all_trash_requires_confirmation_header() -> None:
    user, headers, token, group_id = _user("purge-trash")
    try:
        item = db.add_item(_item(user["id"], "trashed", int(time.time() * 1000)))
        db.trash_items(user["id"], [item["id"]])

        rejected = client.delete("/api/history", headers=headers)
        assert rejected.status_code == 409
        # `get_items` skips the trash (I-094), so ask the listing that owns it.
        assert db.list_items(user["id"], trashed=True)[1] == 1

        confirmed = client.delete(
            "/api/history",
            headers={**headers, "X-Inku-Confirm": "permanent-delete-trash"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["count"] == 1
    finally:
        _cleanup(user, token, group_id)


def test_deleting_user_removes_sessions_and_unread_words() -> None:
    user, _headers, token, group_id = _user("delete-user")
    db.record_unread_words(user["id"], ["曖昧語"], "context", at=int(time.time() * 1000))

    assert db.delete_user(user["id"])
    assert db.get_session_user(token) is None
    with db.SessionLocal() as session:
        assert session.query(db.UnreadWordRow).filter_by(user_id=user["id"]).count() == 0
        assert session.query(db.UserSessionRow).filter_by(user_id=user["id"]).count() == 0
    db.delete_user_group(group_id)


def test_history_idempotency_key_prevents_duplicate_lineage_nodes() -> None:
    user, _headers, token, group_id = _user("idempotency")
    try:
        first_payload = {**_item(user["id"], "first", int(time.time() * 1000)), "idempotency_key": "request-1"}
        first = db.add_item(first_payload)
        replay = db.add_item({
            **_item(user["id"], "retry", int(time.time() * 1000) + 1),
            "idempotency_key": "request-1",
        })
        assert replay["id"] == first["id"]
        assert replay["_idempotent_replay"] is True
        with db.SessionLocal() as session:
            assert session.query(db.HistoryRow).filter_by(user_id=user["id"]).count() == 1
            assert session.query(db.LineageNodeRow).filter_by(user_id=user["id"]).count() == 1
    finally:
        _cleanup(user, token, group_id)


def test_group_lead_scope_is_enforced_inside_update_and_delete_transactions() -> None:
    lead, _headers, lead_token, lead_group = _user("lead")
    target, _target_headers, target_token, target_group = _user("outside")
    try:
        with db.SessionLocal() as session:
            row = session.get(db.UserAccountRow, lead["id"])
            db._set_permission_groups(session, row, ["leaders"])
            session.commit()
        actor = {**lead, "permission_groups": ["leaders"], "group_id": lead_group}
        assert db.update_user(target["id"], actor=actor, email="stolen@example.test") is None
        assert db.delete_user(target["id"], actor=actor) is False
        assert db.get_user(target["id"])["email"] == target["email"]
    finally:
        _cleanup(target, target_token, target_group)
        _cleanup(lead, lead_token, lead_group)


def test_external_identity_subject_is_unique_and_resolves_existing_user() -> None:
    user, _headers, token, group_id = _user("external-id")
    try:
        linked = db.link_external_identity(
            user["id"],
            provider="google",
            subject="google-subject-1",
            email=user["email"],
        )
        assert linked["provider"] == "google"
        assert db.get_user_by_external_identity("GOOGLE", "google-subject-1")["id"] == user["id"]
    finally:
        _cleanup(user, token, group_id)


def test_corrupt_score_json_does_not_hide_the_rest_of_history() -> None:
    user, _headers, token, group_id = _user("corrupt-json")
    try:
        damaged = db.add_item(_item(user["id"], "damaged", 100))
        healthy = db.add_item(_item(user["id"], "healthy", 101))
        with db.SessionLocal() as session:
            session.get(db.HistoryRow, damaged["id"]).score = "{broken"
            session.commit()
        items, total = db.list_items(user["id"], limit=10)
        assert total == 2
        by_id = {item["id"]: item for item in items}
        assert by_id[healthy["id"]]["score"] == {"canvas": "square", "instructions": []}
        assert by_id[damaged["id"]]["score"] == {}
        assert by_id[damaged["id"]]["data_warnings"] == ["score_json_invalid"]
    finally:
        _cleanup(user, token, group_id)
