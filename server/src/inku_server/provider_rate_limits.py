"""Persistent provider-wide admission of generation requests, without retries."""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .persistence.schema import AppSettingRow

WINDOW_SECONDS = 62.0


class RateLimitUnavailable(Exception):
    """Admission cannot fit this attempt or this provider's input/day budget."""


class RateAccountingUnavailable(Exception):
    """No provider send is authorized when its usage cannot be saved."""


def retry_after_seconds(headers, raw: bytes, *, now: float) -> float:
    values = [WINDOW_SECONDS]
    value = headers.get("retry-after")
    if value:
        try:
            values.append(float(value))
        except ValueError:
            try:
                values.append(parsedate_to_datetime(value).timestamp() - now)
            except (TypeError, ValueError, OverflowError):
                pass
    try:
        details = json.loads(raw).get("error", {}).get("details", [])
        for detail in details:
            if isinstance(detail, dict) and detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                delay = detail.get("retryDelay")
                if isinstance(delay, str) and delay.endswith("s"):
                    values.append(float(delay[:-1]))
    except (ValueError, TypeError, AttributeError):
        pass
    return max(value for value in values if math.isfinite(value))


class ProviderRateBudget:
    def __init__(self, engine, *, clock: Callable = time.time, sleep: Callable = asyncio.sleep):
        self.engine, self.clock, self.sleep = engine, clock, sleep

    def _change(self, provider: str, modify: Callable):
        # Compare-and-set also serializes independent processes using this DB.
        key = "provider_rate_usage:" + provider
        for _ in range(16):
            try:
                with self.engine.begin() as connection:
                    if self.engine.dialect.name == "sqlite":
                        connection.exec_driver_sql("BEGIN IMMEDIATE")
                    raw = connection.execute(select(AppSettingRow.value).where(AppSettingRow.key == key)).scalar_one_or_none()
                    state = json.loads(raw) if raw is not None else {"events": [], "day": "", "daily": 0, "not_before": 0}
                    result = modify(state)
                    value = json.dumps(state, separators=(",", ":"), allow_nan=False)
                    if raw is None:
                        connection.execute(insert(AppSettingRow).values(key=key, value=value, at=int(self.clock() * 1000)))
                    else:
                        changed = connection.execute(update(AppSettingRow).where(
                            AppSettingRow.key == key, AppSettingRow.value == raw,
                        ).values(value=value, at=int(self.clock() * 1000)))
                        if changed.rowcount != 1:
                            continue
                    return result
            except IntegrityError:
                continue
            except SQLAlchemyError as error:
                raise RateAccountingUnavailable from error
        raise RateAccountingUnavailable

    async def reserve(self, provider: str, kind: str, limits: dict, input_tokens: int) -> str:
        token = uuid.uuid4().hex
        rpm = max(1, limits["rpm"] * 9 // 10) if limits["rpm"] else 0
        tpm = max(1, limits["tpm"] * 9 // 10) if limits["tpm"] else 0
        if tpm and input_tokens > tpm:
            raise RateLimitUnavailable("request exceeds the configured input-token budget")
        while True:
            now = self.clock()
            zone = ZoneInfo("America/Los_Angeles") if kind == "gemini" else timezone.utc
            day = datetime.fromtimestamp(now, zone).date()

            def admit(state):
                state["events"] = [event for event in state["events"] if event["at"] + WINDOW_SECONDS > now]
                if state["day"] != day.isoformat():
                    state["day"], state["daily"] = day.isoformat(), 0
                if limits["rpd"] and state["daily"] >= limits["rpd"]:
                    raise RateLimitUnavailable("provider daily request budget exhausted")
                delay = max(0.0, state["not_before"] - now)
                if ((rpm and len(state["events"]) >= rpm)
                        or (tpm and sum(event["tokens"] for event in state["events"]) + input_tokens > tpm)):
                    delay = max(delay, min(event["at"] for event in state["events"]) + WINDOW_SECONDS - now)
                if delay > 0:
                    return delay
                state["events"].append({"id": token, "at": now, "tokens": input_tokens})
                state["daily"] += 1
                return 0.0

            delay = self._change(provider, admit)
            if not delay:
                return token
            await self.sleep(delay)

    def settle(self, provider: str, token: str, input_tokens: int | None):
        def reconcile(state):
            for event in state["events"]:
                if event["id"] == token and input_tokens is not None:
                    event["tokens"] = input_tokens
            if input_tokens is None:
                state["not_before"] = max(state["not_before"], self.clock() + WINDOW_SECONDS)
        self._change(provider, reconcile)

    def cool_down(self, provider: str, seconds: float):
        def pause(state):
            state["not_before"] = max(state["not_before"], self.clock() + seconds)
        self._change(provider, pause)
