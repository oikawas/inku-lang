"""Durable, owner-scoped batch leases using the existing application settings table."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.engine import Engine

from .schema import AppSettingRow

LEASE_MS = 90_000


def batch_prefix(owner: str) -> str:
    return "batch-run:" + hashlib.sha256(owner.encode()).hexdigest() + ":"


def _key(owner: str, run_id: str) -> str:
    return batch_prefix(owner) + hashlib.sha256(run_id.encode()).hexdigest()


@dataclass
class BatchRuns:
    engine: Engine

    def require(self, owner: str, run_id: str, lease: str) -> None:
        with self.engine.connect() as connection:
            row = connection.execute(select(AppSettingRow.value).where(AppSettingRow.key == _key(owner, run_id))).scalar_one_or_none()
        record = json.loads(row) if row else None
        if not record or record["lease"] != lease or record["state"] != "running" or record["updated_at"] + LEASE_MS <= int(time.time() * 1000):
            raise HTTPException(409, "batch_lease_lost")

    def start(self, owner: str, body: dict, active_ids: set[str]) -> dict:
        now = int(time.time() * 1000)
        key = _key(owner, body["run_id"])
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            row = connection.execute(select(AppSettingRow.value).where(AppSettingRow.key == key)).scalar_one_or_none()
            previous = json.loads(row) if row else None
            if previous:
                if previous["state"] == "completed":
                    raise HTTPException(409, "batch_already_completed")
                if body["run_id"] in active_ids or (previous["state"] == "running" and previous["updated_at"] + LEASE_MS > now):
                    raise HTTPException(409, "batch_still_active")
                if any(previous.get(field) != body.get(field) for field in ("total", "kind", "prompt", "conditions")):
                    raise HTTPException(409, "batch_plan_changed")
            lease = uuid.uuid4().hex
            record = {**body, "state": "running", "lease": lease, "updated_at": now,
                      "completed": previous.get("completed", 0) if previous else 0}
            if previous:
                connection.execute(AppSettingRow.__table__.update().where(AppSettingRow.key == key).values(value=json.dumps(record, ensure_ascii=False), at=now))
            else:
                connection.execute(AppSettingRow.__table__.insert().values(key=key, value=json.dumps(record, ensure_ascii=False), at=now))
            connection.commit()
        return {"lease": lease, "lease_ms": LEASE_MS}

    def update(self, owner: str, run_id: str, lease: str, completed: int, state: str) -> None:
        now = int(time.time() * 1000)
        key = _key(owner, run_id)
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            row = connection.execute(select(AppSettingRow.value).where(AppSettingRow.key == key)).scalar_one_or_none()
            record = json.loads(row) if row else None
            if not record or record["lease"] != lease or record["state"] != "running":
                raise HTTPException(409, "batch_lease_lost")
            if completed > record["total"]:
                raise HTTPException(422, "batch_completed_exceeds_total")
            if state == "completed" and max(record["completed"], completed) != record["total"]:
                raise HTTPException(422, "batch_not_complete")
            if state == "finished_with_failures" and max(record["completed"], completed) == record["total"]:
                raise HTTPException(422, "batch_has_no_failures")
            record.update(completed=max(record["completed"], completed), state=state, updated_at=now)
            connection.execute(AppSettingRow.__table__.update().where(AppSettingRow.key == key).values(value=json.dumps(record, ensure_ascii=False), at=now))
            connection.commit()

    def list(self, owner: str | None, active_ids: set[str]) -> list[dict]:
        with self.engine.connect() as connection:
            query = select(AppSettingRow.key, AppSettingRow.value, AppSettingRow.at).where(
                AppSettingRow.key.startswith(batch_prefix(owner) if owner is not None else "batch-run:"))
            rows = connection.execute(query.order_by(AppSettingRow.at.desc()).limit(100)).all()
        now = int(time.time() * 1000)
        result = []
        for _key_value, value, _at in rows:
            item = json.loads(value)
            item.pop("lease", None)
            if item["state"] != "completed" and item["run_id"] in active_ids and (
                item["state"] != "running" or item["updated_at"] + LEASE_MS <= now
            ):
                item["state"] = "uncertain"
            elif item["state"] == "running" and item["updated_at"] + LEASE_MS <= now:
                item["state"] = "lease_expired"
            result.append(item)
        return result
