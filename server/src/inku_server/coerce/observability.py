"""Internal, versioned coerce observations."""

from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from .observation_registry import SITE_REGISTRY

TRACE_VERSION = 1
INTERNAL_HISTORY_COLUMNS = (
    "score_pre_coerce",
    "coerce_trace_version",
    "coerce_catalog_digest",
    "coerce_trace",
)


class MarkerToken(str):
    """An input marker with the declaration that made it observable."""

    __slots__ = ("system", "language")

    def __new__(cls, value: str, *, system: str, language: str) -> "MarkerToken":
        token = super().__new__(cls, value)
        token.system = system
        token.language = language
        return token


_REGISTERED_TOKENS: list[MarkerToken] = []


def marker_token(value: str, *, system: str, language: str) -> MarkerToken:
    token = MarkerToken(value, system=system, language=language)
    _REGISTERED_TOKENS.append(token)
    return token


def marker_tokens() -> tuple[MarkerToken, ...]:
    """Return declaration-order runtime input tokens only."""
    return tuple(_REGISTERED_TOKENS)


def catalog_snapshot() -> dict[str, Any]:
    # Importing compose initializes the declarations without reading any DDL.
    from . import COERCE_BRANCH_ORDER, compose  # noqa: F401

    tokens_by_system: dict[str, list[MarkerToken]] = {}
    for token in marker_tokens():
        tokens_by_system.setdefault(token.system, []).append(token)
    markers: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for site in SITE_REGISTRY:
        if site["source_kind"] not in {
            "language_support.COERCE_MARKERS",
            "compose_direct_input",
        }:
            continue
        for system in site["systems"]:
            for token in tokens_by_system.get(system, []):
                event = {
                    "system": token.system,
                    "marker": str(token),
                    "language": token.language,
                    "decision_site": site["decision_site"],
                    "match_mode": site["match_mode"],
                }
                key = (
                    event["decision_site"],
                    event["system"],
                    event["language"],
                    event["marker"],
                    event["match_mode"],
                )
                if key not in seen:
                    seen.add(key)
                    markers.append(event)
    return {
        "trace_version": TRACE_VERSION,
        "markers": markers,
        "branches": list(COERCE_BRANCH_ORDER),
    }

def catalog_digest(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


_ACTIVE_TRACE: ContextVar[TraceContext | None] = ContextVar(
    "inku_coerce_trace", default=None
)


def record_marker_match(
    token: object, matched: bool, *, match_mode: str, decision_site: str | None = None
) -> bool:
    """Record only a true comparison against a registered input token."""
    active = _ACTIVE_TRACE.get()
    if matched and active is not None and isinstance(token, MarkerToken):
        active.record_marker(token, match_mode, decision_site=decision_site)
    return matched


_MISSING = object()


def _pointer_part(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _diff(before: Any, after: Any, path: str = "") -> list[dict[str, str]]:
    if isinstance(before, dict) and isinstance(after, dict):
        return [
            event
            for key in sorted(set(before) | set(after))
            for event in _diff(
                before.get(key, _MISSING), after.get(key, _MISSING),
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


class _TraceActivation:
    def __init__(self, trace: "TraceContext") -> None:
        self.trace = trace
        self.token = None

    def __enter__(self) -> None:
        self.token = _ACTIVE_TRACE.set(self.trace)

    def __exit__(self, *_: object) -> None:
        assert self.token is not None
        _ACTIVE_TRACE.reset(self.token)


@dataclass
class TraceContext:
    pre_score: dict[str, Any]
    ddl: str
    lang: str
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

    def activate(self) -> _TraceActivation:
        return _TraceActivation(self)

    def record_marker(
        self, token: MarkerToken, match_mode: str, *, decision_site: str | None
    ) -> None:
        for event in self.snapshot["markers"]:
            if (
                event["language"] == token.language
                and event["system"] == token.system
                and event["marker"] == str(token)
                and event["decision_site"] == decision_site
                and event not in self.trace["marker_events"]
            ):
                self.trace["marker_events"].append(event)

    def record_branch(
        self, branch: str, before: Any, after: Any, *, change_count: int, path: str
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


def record_branch_effect(
    branch: str,
    before: Any,
    after: Any,
    *,
    change_count: int,
    path: str,
) -> None:
    active = _ACTIVE_TRACE.get()
    if active is not None:
        active.record_branch(
            branch, before, after, change_count=change_count, path=path
        )


def capture_context(score: Any, *, ddl: str | None, lang: str | None) -> TraceContext:
    return TraceContext(
        score.model_dump(mode="json", by_alias=True), ddl or "", lang or "ja"
    )


def verify_decision_site_registry() -> list[str]:
    from .observation_registry import DIRECT_INPUT_SEMANTIC_LEAVES

    snapshot = catalog_snapshot()
    input_sites = [
        site
        for site in SITE_REGISTRY
        if site["source_kind"]
        in {"language_support.COERCE_MARKERS", "compose_direct_input"}
    ]
    catalog_sites = {event["decision_site"] for event in snapshot["markers"]}
    errors = [
        f"missing catalog site: {site['decision_site']}"
        for site in input_sites
        if site["decision_site"] not in catalog_sites
    ]
    direct_sites = [
        site for site in input_sites if site["source_kind"] == "compose_direct_input"
    ]
    direct_systems = {site["systems"][0] for site in direct_sites}
    direct_token_systems = {
        token.system for token in marker_tokens() if token.system.startswith("direct.")
    }
    errors.extend(
        f"missing direct token system: {system}"
        for system in sorted(direct_systems - direct_token_systems)
    )
    errors.extend(
        f"unused direct token system: {system}"
        for system in sorted(direct_token_systems - direct_systems)
    )
    semantic_leaves = {
        leaf for site in direct_sites for leaf in site["semantic_leaves"]
    }
    if semantic_leaves != set(DIRECT_INPUT_SEMANTIC_LEAVES):
        errors.append("direct semantic leaves do not match the registry definition")
    return errors
