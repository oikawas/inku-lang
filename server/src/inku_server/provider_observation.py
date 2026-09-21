"""Durable developer-only provider transcripts, deliberately outside history."""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.engine import Engine

from .persistence.schema import ProviderObservationRow


class ProviderObservationError(RuntimeError):
    """An observation write failed, so the provider attempt cannot be trusted."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _bounded_text(value: bytes, limit: int) -> tuple[str, bool]:
    clipped = len(value) > limit
    return value[:limit].decode("utf-8", errors="replace"), clipped


def _usage(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    source = value.get("usageMetadata") if isinstance(value.get("usageMetadata"), dict) else value.get("usage")
    if not isinstance(source, dict):
        return None
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens", "promptTokenCount"),
        "output_tokens": ("output_tokens", "completion_tokens", "candidatesTokenCount"),
        "total_tokens": ("total_tokens", "totalTokenCount"),
    }
    result = {
        name: int(source[key])
        for name, keys in aliases.items()
        for key in keys
        if isinstance(source.get(key), int)
    }
    return result or None


class ProviderObservationStore:
    """Write before send; later failures remain explicitly incomplete."""

    def __init__(self, engine: Engine, *, limit: int):
        if limit <= 0:
            raise ValueError("positive observation limit required")
        self.engine, self.limit = engine, limit

    def request(self, owner_id: str, execution_id: str, action: dict, stage: str, provider_id: str, model: str, body: bytes) -> bool:
        identity = action["identity"]
        request_body, request_truncated = _bounded_text(body, self.limit)
        now = int(time.time() * 1000)
        try:
            with self.engine.begin() as connection:
                connection.execute(ProviderObservationRow.__table__.insert().values(
                    owner_id=owner_id, execution_id=execution_id,
                    action_id=str(identity["action_id"]), request_digest=str(identity.get("request_digest", "")),
                    action_tag=str(action["tag"]), stage=stage,
                    provider_id=provider_id, model=model,
                    attempt=int(identity["attempt"]), timeout_ms=int(action["timeout_ms"]),
                    request_body=request_body, request_truncated=request_truncated,
                    outcome="request_saved", created_at=now, updated_at=now,
                ))
        except Exception as error:
            raise ProviderObservationError("request_save_failed") from error
        return request_truncated

    def response(self, owner_id: str, execution_id: str, action: dict, *, status: int, raw: bytes, truncated: bool = False) -> None:
        response_body, response_truncated = _bounded_text(raw, self.limit)
        response_truncated = response_truncated or truncated
        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = None
        values = {
            "response_body": response_body, "response_truncated": response_truncated,
            "http_status": status, "usage_json": None if _usage(decoded) is None else _json(_usage(decoded)),
            "outcome": "response_saved", "updated_at": int(time.time() * 1000),
        }
        try:
            with self.engine.begin() as connection:
                changed = connection.execute(update(ProviderObservationRow.__table__).where(and_(
                    ProviderObservationRow.owner_id == owner_id,
                    ProviderObservationRow.execution_id == execution_id,
                    ProviderObservationRow.action_id == str(action["identity"]["action_id"]),
                )).values(**values))
                if changed.rowcount != 1:
                    raise ProviderObservationError("response_without_request")
        except ProviderObservationError:
            raise
        except Exception as error:
            raise ProviderObservationError("response_save_failed") from error

    def outcome(self, owner_id: str, execution_id: str, action: dict, *, failure: str | None, elapsed_ms: int, capture_complete: bool) -> None:
        try:
            with self.engine.begin() as connection:
                changed = connection.execute(update(ProviderObservationRow.__table__).where(and_(
                    ProviderObservationRow.owner_id == owner_id,
                    ProviderObservationRow.execution_id == execution_id,
                    ProviderObservationRow.action_id == str(action["identity"]["action_id"]),
                )).values(
                    outcome="completed", capture_complete=capture_complete,
                    failure=failure, elapsed_ms=elapsed_ms, updated_at=int(time.time() * 1000),
                ))
                if changed.rowcount != 1:
                    raise ProviderObservationError("outcome_without_request")
        except ProviderObservationError:
            raise
        except Exception as error:
            raise ProviderObservationError("outcome_save_failed") from error

    def read_execution(self, owner_id: str, execution_id: str) -> list[dict]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(ProviderObservationRow.__table__).where(and_(
                ProviderObservationRow.owner_id == owner_id,
                ProviderObservationRow.execution_id == execution_id,
            )).order_by(ProviderObservationRow.created_at, ProviderObservationRow.action_id)).mappings()
            return [{key: value for key, value in row.items() if key != "owner_id"} for row in rows]
