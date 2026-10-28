"""Persistent provider-wide admission of generation requests, without retries."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Callable

import inku_render

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .persistence.schema import AppSettingRow

WINDOW_SECONDS = 62.0


class RateLimitUnavailable(Exception):
    """Admission cannot fit this attempt or this provider's input/day budget."""


class RateAccountingUnavailable(Exception):
    """No provider send is authorized when its usage cannot be saved."""


def retry_after_seconds(headers, raw: bytes, *, now: float) -> float:
    return _core("retry", now=now, retry_after=headers.get("retry-after"),
                 raw=raw.decode("utf-8", errors="replace"))["seconds"]


def _core(action, **fields):
    try:
        request = json.dumps({"action": action, **fields}, allow_nan=False, separators=(",", ":")).encode()
        response = json.loads(inku_render.pipeline_provider_admission(request))
        if "error" in response:
            raise ValueError(response["error"])
        return response
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise RateAccountingUnavailable from error


def _replace_state(state, result):
    # Preserve the insertion order used by the existing compact DB encoding.
    old_events = {event["id"]: event for event in state["events"]}
    new = result["state"]
    events = []
    for event in new["events"]:
        old = old_events.get(event["id"], {})
        ordered = {key: event[key] for key in old if key in event}
        ordered.update(event)
        if not old:
            ordered = {key: event[key] for key in ("id", "at", "tokens")}
        events.append(ordered)
    new["events"] = events
    for key in state:
        state[key] = new[key]
    for key in new:
        if key not in state:
            state[key] = new[key]


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
        preflight = _core("preflight", limits=limits, input_tokens=input_tokens)
        if preflight["decision"] == "reject":
            raise RateLimitUnavailable(preflight["reason"])
        while True:
            now = self.clock()

            def admit(state):
                result = _core("admit", state=state, now=now, kind=kind, limits=limits,
                               input_tokens=input_tokens, id=token)
                if result["decision"] == "reject":
                    raise RateLimitUnavailable(result["reason"])
                _replace_state(state, result)
                return result.get("seconds", 0.0)

            delay = self._change(provider, admit)
            if not delay:
                return token
            await self.sleep(delay)

    def settle(self, provider: str, token: str, input_tokens: int | None):
        def reconcile(state):
            result = _core("settle", state=state, now=self.clock() if input_tokens is None else 0,
                           id=token, input_tokens=input_tokens)
            _replace_state(state, result)
        self._change(provider, reconcile)

    def cool_down(self, provider: str, seconds: float):
        def pause(state):
            result = _core("pause", state=state, now=self.clock(), seconds=seconds)
            _replace_state(state, result)
        self._change(provider, pause)
