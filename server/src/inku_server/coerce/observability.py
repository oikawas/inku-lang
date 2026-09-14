"""Persisted observation envelope for versionless saved Score normalization."""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any


TRACE_VERSION = 1
INTERNAL_HISTORY_COLUMNS = (
    "score_pre_coerce",
    "coerce_trace_version",
    "coerce_catalog_digest",
    "coerce_trace",
)


def catalog_snapshot() -> dict[str, Any]:
    from ..saved_score_compat import SAVED_SCORE_BRANCH_ORDER

    return {
        "trace_version": TRACE_VERSION,
        "markers": [],
        "branches": list(SAVED_SCORE_BRANCH_ORDER),
    }


def catalog_digest(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


_MISSING = object()


def _pointer_part(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _diff(before: Any, after: Any, path: str = "") -> list[dict[str, str]]:
    if isinstance(before, dict) and isinstance(after, dict):
        return [
            event
            for key in sorted(set(before) | set(after))
            for event in _diff(
                before.get(key, _MISSING),
                after.get(key, _MISSING),
                f"{path}/{_pointer_part(key)}",
            )
        ]
    if isinstance(before, list) and isinstance(after, list):
        return [
            event
            for index in range(max(len(before), len(after)))
            for event in _diff(
                before[index] if index < len(before) else _MISSING,
                after[index] if index < len(after) else _MISSING,
                f"{path}/{index}",
            )
        ]
    if before is _MISSING:
        return [{"path": path or "/", "effect": "add"}]
    if after is _MISSING:
        return [{"path": path or "/", "effect": "remove"}]
    if before == after:
        return []
    return [{"path": path or "/", "effect": "replace"}]


@dataclass
class TraceContext:
    pre_score: dict[str, Any]
    snapshot: dict[str, Any] = field(default_factory=catalog_snapshot)
    trace: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.trace = {
            "complete": False,
            "executed": False,
            "disabled": False,
            "marker_events": [],
            "branch_events": [],
            "changed_fields": [],
        }

    def activate(self):
        return nullcontext()

    def record_branch(
        self,
        branch: str,
        before: Any,
        after: Any,
        *,
        change_count: int,
        path: str,
    ) -> None:
        changed_fields = _diff(before, after, path)
        if changed_fields:
            self.trace["branch_events"].append(
                {
                    "branch": branch,
                    "change_count": change_count,
                    "changed_fields": changed_fields,
                }
            )

    def mark_not_executed(self, reason_class: str) -> None:
        self.trace.update({"failure_stage": "coerce", "reason_class": reason_class})

    def finish(
        self, post: dict[str, Any], branches: dict[str, int], *, disabled: bool
    ) -> None:
        del branches
        self.trace.update(
            {
                "complete": True,
                "executed": True,
                "disabled": disabled,
                "changed_fields": _diff(self.pre_score, post),
            }
        )

    def persistable(self) -> dict[str, Any]:
        trace = dict(self.trace)
        if not trace["complete"]:
            trace.setdefault("failure_stage", "coerce")
            trace.setdefault("reason_class", "not_executed")
        return {
            **trace,
            "trace_version": TRACE_VERSION,
            "catalog_digest": catalog_digest(self.snapshot),
            "catalog_snapshot": self.snapshot,
            "score_pre_coerce": self.pre_score,
        }


def capture_context(score: Any, *, ddl: str | None, lang: str | None) -> TraceContext:
    del ddl, lang
    return TraceContext(score.model_dump(mode="json", by_alias=True))
