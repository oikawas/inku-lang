"""Persistence owner for Okugaki projection and storage."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from . import access
from .schema import LineageNodeRow, OkugakiRow


def okugaki_to_dict(row: OkugakiRow) -> dict:
    def load(value: str, fallback):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    return {
        "id": row.id,
        "target_node_id": row.target_node_id,
        "branch_snapshot": load(row.branch_snapshot_json, []),
        "model": row.model,
        "at": row.at,
        "language": row.language,
        "body": row.body,
        "warnings": load(row.warnings_json, []),
        "fact_sheet": load(row.fact_sheet_json, {}),
    }


@dataclass(frozen=True)
class OkugakiStore:
    """Store colophons without widening their distinct read/write/owner scopes."""

    session_factory: Callable[[], object]
    actor_of_fn: Callable[[str], dict]
    owner_actor_fn: Callable[[str], dict]
    canonical_json_fn: Callable[[object], str]

    def add_okugaki(
        self,
        user_id: str,
        item: dict,
        *,
        idempotency_key: str | None = None,
    ) -> dict:
        actor = self.actor_of_fn(user_id)
        with self.session_factory() as session:
            if idempotency_key:
                existing = session.query(OkugakiRow).filter(
                    access._owned_by(actor, OkugakiRow.user_id),
                    OkugakiRow.idempotency_key == idempotency_key,
                ).first()
                if existing is not None:
                    result = okugaki_to_dict(existing)
                    result["_idempotent_replay"] = True
                    return result
            target = session.query(LineageNodeRow).filter(
                access._readable_node(actor),
                LineageNodeRow.id == item["target_node_id"],
            ).first()
            if target is None:
                raise ValueError("lineage target not found")
            row = OkugakiRow(
                id=item.get("id") or str(uuid.uuid4()),
                user_id=user_id,
                target_node_id=item["target_node_id"],
                branch_snapshot_json=self.canonical_json_fn(item["branch_snapshot"]),
                model=item["model"],
                at=item["at"],
                language=item["language"],
                body=item["body"],
                warnings_json=self.canonical_json_fn(item.get("warnings") or []),
                fact_sheet_json=self.canonical_json_fn(item.get("fact_sheet") or {}),
                idempotency_key=idempotency_key,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                if not idempotency_key:
                    raise
                existing = session.query(OkugakiRow).filter(
                    access._owned_by(actor, OkugakiRow.user_id),
                    OkugakiRow.idempotency_key == idempotency_key,
                ).first()
                if existing is None:
                    raise
                result = okugaki_to_dict(existing)
                result["_idempotent_replay"] = True
                return result
            session.refresh(row)
            return okugaki_to_dict(row)

    def list_okugaki(self, user_id: str, target_node_id: str) -> list[dict]:
        actor = self.actor_of_fn(user_id)
        with self.session_factory() as session:
            rows = session.query(OkugakiRow).filter(
                access._readable_by(actor, OkugakiRow.user_id),
                OkugakiRow.target_node_id == target_node_id,
            ).order_by(OkugakiRow.at.asc(), OkugakiRow.id.asc()).all()
            return [okugaki_to_dict(row) for row in rows]

    def get_okugaki_by_idempotency(
        self,
        user_id: str,
        idempotency_key: str,
    ) -> dict | None:
        owner = self.owner_actor_fn(user_id)
        with self.session_factory() as session:
            row = session.query(OkugakiRow).filter(
                access._owned_by(owner, OkugakiRow.user_id),
                OkugakiRow.idempotency_key == idempotency_key,
            ).first()
            return okugaki_to_dict(row) if row is not None else None

    def delete_okugaki(self, user_id: str, okugaki_id: str) -> bool:
        actor = self.actor_of_fn(user_id)
        with self.session_factory() as session:
            row = session.query(OkugakiRow).filter(
                OkugakiRow.id == okugaki_id,
                access._writable_by(actor, OkugakiRow.user_id),
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
