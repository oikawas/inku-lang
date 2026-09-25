"""Persistence adapter for shared variation-authority commit effects.

The ordinary Server pipeline service (`pipeline_runtime.py`) keeps variation
authority, action acknowledgments, execution snapshots, and history links here.
History rows themselves stay in the existing history store; a link ties one
immutable performance to the authoring revision that produced it.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    and_,
    func,
    inspect,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .schema import (
    Base,
    HistoryRow,
    PipelineCandidateExecutionRow,
    PipelineHistoryLinkRow,
    VariationAuthorityActionRow,
    VariationAuthorityRow,
)


AUTHORITY_PROTOCOL = "inku.variation-authority.v1"
COMMIT_ACTION_TAG = "commit_visible_normalized_ddl"
_LEGACY_HISTORY_FORK_CONTEXT_PROTOCOL = "inku.pipeline-history-fork-context.v1"
HISTORY_FORK_CONTEXT_PROTOCOL = "inku.pipeline-history-fork-context.v2"
_PIPELINE_DIAGNOSTIC_KEYS = frozenset(
    {
        "upstream_diagnostics",
        "downstream_diagnostics",
        "resource_omissions",
        "relation_omissions",
        "render_diagnostics",
        "resource_execution",
    }
)
_U64_MAX = (1 << 64) - 1
_ORIGINS = frozenset({"stage1_generated", "user_authored_ddl"})
_AUTHORITIES = frozenset(
    {"description_authoritative", "ddl_authoritative", "legacy_unknown"}
)
_INITIAL_PAIRS = frozenset(
    {
        ("stage1_generated", "description_authoritative"),
        ("stage1_generated", "ddl_authoritative"),
        ("user_authored_ddl", "ddl_authoritative"),
    }
)
_DERIVATION_KINDS = frozenset(
    {
        "new",
        "legacy_ddl_fork",
        "legacy_description_fork",
        "description_fork",
        "variation_ddl_fork",
    }
)

candidate_metadata = Base.metadata
variation_authority = VariationAuthorityRow.__table__
variation_authority_actions = VariationAuthorityActionRow.__table__
pipeline_candidate_executions = PipelineCandidateExecutionRow.__table__
pipeline_history_links = PipelineHistoryLinkRow.__table__


class VariationAuthorityAdapterError(ValueError):
    """A core commit action does not satisfy the candidate host contract."""


class ActionIdentityConflict(VariationAuthorityAdapterError):
    """A reused action identity carries different logical action bytes."""


class ExecutionSnapshotConflict(VariationAuthorityAdapterError):
    """An execution snapshot CAS observed another tab's revision."""

    def __init__(self, actual_sequence: str | None) -> None:
        super().__init__("execution snapshot sequence conflict")
        self.actual_sequence = actual_sequence


@dataclass(frozen=True)
class VariationAuthoringContext:
    """Host-owned authoring provenance stored beside the core authority."""

    description: str = ""
    derivation_kind: str = "new"
    parent_legacy_history_id: str | None = None
    parent_variation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.description, str):
            raise VariationAuthorityAdapterError("description must be text")
        if self.derivation_kind not in _DERIVATION_KINDS:
            raise VariationAuthorityAdapterError("unknown derivation kind")
        legacy_parent = bool(self.parent_legacy_history_id)
        variation_parent = bool(self.parent_variation_id)
        valid = (
            self.derivation_kind == "new"
            and not legacy_parent
            and not variation_parent
        ) or (
            self.derivation_kind
            in {"legacy_ddl_fork", "legacy_description_fork"}
            and legacy_parent
            and not variation_parent
        ) or (
            self.derivation_kind in {"description_fork", "variation_ddl_fork"}
            and not legacy_parent
            and variation_parent
        )
        if not valid:
            raise VariationAuthorityAdapterError(
                "derivation kind does not match its parent"
            )


@dataclass(frozen=True)
class LegacyHistoryRecord:
    """Exact owner-scoped legacy inputs projected without authority inference."""

    history_id: str
    description: str
    source: str | None
    expanded_source: str | None
    score_json: str
    svg: str
    authority: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class PipelineExecutionRecord:
    """Opaque host wrapper bytes and their adapter-local CAS identity."""

    execution_id: str
    variation_id: str
    sequence: str
    state_bytes: bytes
    state_digest: str
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class LinkedHistoryForkRecord:
    """Exact immutable history and trusted context for a managed fork."""

    history: LegacyHistoryRecord
    variation_id: str
    revision: str
    ddl_digest: str
    saved_config: dict[str, object]
    host_options: dict[str, object]
    macro_catalog: dict[str, object]
    pipeline_diagnostics: dict[str, object] | None


@dataclass(frozen=True)
class VariationAuthorityInventory:
    """Aggregate-only evidence; no source, description, or DDL bytes are read."""

    history_table_present: bool
    history_rows: int
    history_authority_columns_present: bool
    legacy_unknown_history_rows: int
    candidate_tables_present: bool
    candidate_variations: int
    description_authoritative: int
    ddl_authoritative: int
    explicit_legacy_unknown: int
    action_acknowledgments: int
    candidate_executions: int


@dataclass(frozen=True)
class _Commit:
    owner_id: str
    variation_id: str
    action_id: str
    attempt: int
    request_digest: str
    expected_revision: str
    next_revision: str
    origin: str
    authority: str
    source: str
    document_json: str
    ddl_digest: str
    authority_digest: str
    action_fingerprint: str
    reason: str


def _canonical_json(value: object, *, sort_keys: bool = False) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=sort_keys,
        separators=(",", ":"),
    )


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _decimal_u64(value: object, field: str) -> tuple[str, int]:
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not value.isdecimal()
        or (len(value) > 1 and value.startswith("0"))
    ):
        raise VariationAuthorityAdapterError(
            f"{field} must be a canonical unsigned decimal string"
        )
    parsed = int(value)
    if parsed > _U64_MAX:
        raise VariationAuthorityAdapterError(f"{field} exceeds u64")
    return value, parsed


def _mapping(
    value: object,
    field: str,
    *,
    keys: frozenset[str],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != keys:
        raise VariationAuthorityAdapterError(f"{field} has an unexpected shape")
    return value


def _core_value_digest(
    domain: str, value: object, *, sort_keys: bool = False
) -> str:
    encoded = _canonical_json(value, sort_keys=sort_keys).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(domain.encode("utf-8"))
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    return digest.hexdigest()


def _parse_commit(owner_id: str, action: Mapping[str, Any]) -> _Commit:
    if not owner_id:
        raise VariationAuthorityAdapterError("owner_id must not be empty")
    action = _mapping(
        action,
        "action",
        keys=frozenset(
            {"tag", "version", "identity", "timeout_ms", "delay_ms", "payload"}
        ),
    )
    if action["tag"] != COMMIT_ACTION_TAG or action["version"] != 1:
        raise VariationAuthorityAdapterError("expected commit action version 1")

    identity = _mapping(
        action["identity"],
        "identity",
        keys=frozenset({"action_id", "attempt", "request_digest"}),
    )
    action_id = identity["action_id"]
    request_digest = identity["request_digest"]
    attempt = identity["attempt"]
    if not _is_digest(action_id) or not _is_digest(request_digest):
        raise VariationAuthorityAdapterError(
            "action identity digests must be lowercase sha256"
        )
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise VariationAuthorityAdapterError(
            "action attempt must be a positive integer"
        )

    payload = _mapping(
        action["payload"],
        "payload",
        keys=frozenset(
            {
                "variation_id",
                "document",
                "ddl_digest",
                "authority",
                "authority_digest",
                "reason",
            }
        ),
    )
    variation_id = payload["variation_id"]
    if not isinstance(variation_id, str) or not variation_id:
        raise VariationAuthorityAdapterError("variation_id must not be empty")
    if not isinstance(payload["reason"], str) or not payload["reason"]:
        raise VariationAuthorityAdapterError("commit reason must not be empty")
    reason = payload["reason"]
    if (
        _core_value_digest(
            "inku.pipeline-request.v1", payload, sort_keys=True
        )
        != request_digest
    ):
        raise VariationAuthorityAdapterError(
            "request_digest does not identify the commit payload"
        )

    document = _mapping(
        payload["document"],
        "document",
        keys=frozenset({"source", "language", "macro_locks"}),
    )
    source = document["source"]
    if not isinstance(source, str):
        raise VariationAuthorityAdapterError("document source must be UTF-8 text")
    if not isinstance(document["language"], str) or not isinstance(
        document["macro_locks"], list
    ):
        raise VariationAuthorityAdapterError(
            "document metadata has an unexpected shape"
        )
    document_json = _canonical_json(document, sort_keys=True)

    ddl_digest = payload["ddl_digest"]
    if (
        not _is_digest(ddl_digest)
        or hashlib.sha256(source.encode("utf-8")).hexdigest() != ddl_digest
    ):
        raise VariationAuthorityAdapterError(
            "ddl_digest does not identify exact source bytes"
        )

    proposal = _mapping(
        payload["authority"],
        "authority proposal",
        keys=frozenset({"expected_revision", "next_state"}),
    )
    expected_revision, expected = _decimal_u64(
        proposal["expected_revision"], "expected_revision"
    )
    next_state = _mapping(
        proposal["next_state"],
        "next authority state",
        keys=frozenset({"protocol_version", "revision", "origin", "authority"}),
    )
    if next_state["protocol_version"] != AUTHORITY_PROTOCOL:
        raise VariationAuthorityAdapterError("authority protocol mismatch")
    next_revision, following = _decimal_u64(
        next_state["revision"], "next revision"
    )
    if expected == _U64_MAX or following != expected + 1:
        raise VariationAuthorityAdapterError(
            "next revision must increment expected revision"
        )
    origin = next_state["origin"]
    authority = next_state["authority"]
    if origin not in _ORIGINS or authority not in _AUTHORITIES:
        raise VariationAuthorityAdapterError("unknown origin or authority")

    authority_digest = payload["authority_digest"]
    if not _is_digest(authority_digest):
        raise VariationAuthorityAdapterError(
            "authority_digest must be lowercase sha256"
        )
    ordered_state = {
        "protocol_version": AUTHORITY_PROTOCOL,
        "revision": next_revision,
        "origin": origin,
        "authority": authority,
    }
    if _core_value_digest(AUTHORITY_PROTOCOL, ordered_state) != authority_digest:
        raise VariationAuthorityAdapterError(
            "authority_digest does not identify the proposed next state"
        )

    logical_action = {
        "tag": action["tag"],
        "version": action["version"],
        "action_id": action_id,
        "request_digest": request_digest,
        "payload": payload,
    }
    action_fingerprint = hashlib.sha256(
        _canonical_json(logical_action, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return _Commit(
        owner_id=owner_id,
        variation_id=variation_id,
        action_id=action_id,
        attempt=attempt,
        request_digest=request_digest,
        expected_revision=expected_revision,
        next_revision=next_revision,
        origin=origin,
        authority=authority,
        source=source,
        document_json=document_json,
        ddl_digest=ddl_digest,
        authority_digest=authority_digest,
        action_fingerprint=action_fingerprint,
        reason=reason,
    )


def _context_payload(context: VariationAuthoringContext) -> dict[str, object]:
    return {
        "description": context.description,
        "derivation_kind": context.derivation_kind,
        "parent_legacy_history_id": context.parent_legacy_history_id,
        "parent_variation_id": context.parent_variation_id,
    }


def _context_fingerprint(context: VariationAuthoringContext) -> str:
    return hashlib.sha256(
        _canonical_json(_context_payload(context), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _context_from_row(row: Mapping[str, Any]) -> VariationAuthoringContext:
    return VariationAuthoringContext(
        description=str(row["description"]),
        derivation_kind=str(row["derivation_kind"]),
        parent_legacy_history_id=row["parent_legacy_history_id"],
        parent_variation_id=row["parent_variation_id"],
    )


def _resolved_context(
    current: Mapping[str, Any],
    commit: _Commit,
    proposed: VariationAuthoringContext | None,
) -> VariationAuthoringContext:
    stored = _context_from_row(current)
    if proposed is None:
        return stored
    if (
        proposed.derivation_kind != stored.derivation_kind
        or proposed.parent_legacy_history_id
        != stored.parent_legacy_history_id
        or proposed.parent_variation_id != stored.parent_variation_id
    ):
        raise VariationAuthorityAdapterError(
            "variation derivation and parent are immutable"
        )
    if proposed.description == stored.description:
        return stored
    if (
        commit.reason in {"stage1_generated", "stage1_residual_execution"}
        and current["authority"] == "description_authoritative"
        and commit.authority == "description_authoritative"
    ):
        return proposed
    raise VariationAuthorityAdapterError(
        "description can change only during an authoritative Stage 1 commit"
    )


def _validate_initial_context(
    connection,
    commit: _Commit,
    context: VariationAuthoringContext,
) -> None:
    required_pair = {
        "legacy_ddl_fork": ("user_authored_ddl", "ddl_authoritative"),
        "legacy_description_fork": (
            "stage1_generated",
            "description_authoritative",
        ),
        "description_fork": ("stage1_generated", "description_authoritative"),
    }.get(context.derivation_kind)
    if required_pair is not None and required_pair != (
        commit.origin,
        commit.authority,
    ):
        raise VariationAuthorityAdapterError(
            "fork kind does not match its initial origin and authority"
        )
    if context.parent_legacy_history_id is not None:
        parent = connection.execute(
            select(HistoryRow.id).where(
                and_(
                    HistoryRow.user_id == commit.owner_id,
                    HistoryRow.id == context.parent_legacy_history_id,
                    HistoryRow.trashed == 0,
                )
            )
        ).scalar_one_or_none()
        if parent is None:
            raise VariationAuthorityAdapterError(
                "owned legacy parent was not found"
            )
    if context.parent_variation_id is not None:
        parent = connection.execute(
            select(variation_authority.c.variation_id).where(
                and_(
                    variation_authority.c.owner_id == commit.owner_id,
                    variation_authority.c.variation_id
                    == context.parent_variation_id,
                )
            )
        ).scalar_one_or_none()
        if parent is None:
            raise VariationAuthorityAdapterError(
                "owned candidate parent was not found"
            )


def _transition_allowed(current: Mapping[str, Any], commit: _Commit) -> None:
    if current["protocol_version"] != AUTHORITY_PROTOCOL:
        raise VariationAuthorityAdapterError("stored authority protocol mismatch")
    if current["origin"] != commit.origin:
        raise VariationAuthorityAdapterError("variation origin is immutable")
    before = current["authority"]
    after = commit.authority
    if before == "description_authoritative" and after in {
        "description_authoritative",
        "ddl_authoritative",
    }:
        return
    if before == "ddl_authoritative":
        if after != "ddl_authoritative":
            raise VariationAuthorityAdapterError("DDL authority cannot be unlocked")
        return
    if before == "legacy_unknown":
        raise VariationAuthorityAdapterError(
            "legacy_unknown requires an author-approved compatibility decision"
        )
    raise VariationAuthorityAdapterError("stored authority is unknown")


def _committed_result(commit: _Commit) -> dict[str, object]:
    return {
        "tag": "visible_normalized_ddl_committed",
        "identity": {
            "action_id": commit.action_id,
            "attempt": commit.attempt,
            "request_digest": commit.request_digest,
        },
        "ddl_digest": commit.ddl_digest,
        "revision": commit.next_revision,
        "authority_digest": commit.authority_digest,
    }


def _failed_result(commit: _Commit, actual_revision: str | None) -> dict[str, object]:
    return {
        "tag": "host_commit_failed",
        "identity": {
            "action_id": commit.action_id,
            "attempt": commit.attempt,
            "request_digest": commit.request_digest,
        },
        "actual_revision": actual_revision,
    }


def _validated_state_bytes(value: bytes) -> tuple[bytes, str]:
    if not isinstance(value, bytes):
        raise VariationAuthorityAdapterError(
            "execution state must be owned bytes"
        )
    try:
        wrapper = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VariationAuthorityAdapterError(
            "execution state must be a UTF-8 JSON wrapper"
        ) from exc
    if not isinstance(wrapper, dict) or set(wrapper) != {
        "snapshot",
        "context",
        "rendered",
    }:
        raise VariationAuthorityAdapterError(
            "execution state wrapper must contain snapshot, context, and rendered"
        )
    return value, hashlib.sha256(value).hexdigest()


def _history_fork_context_bytes(
    snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    variation_id: str,
    revision: str,
    ddl_digest: str,
    pipeline_diagnostics: Mapping[str, Any],
) -> tuple[bytes, str]:
    """Freeze trusted fork inputs and the raw diagnostics of this performance."""
    authority = snapshot.get("authority")
    document = snapshot.get("document")
    delivery = snapshot.get("delivery")
    config = snapshot.get("config")
    host_options = context.get("host_options")
    macro_catalog = context.get("macro_catalog")
    if not all(
        isinstance(value, Mapping)
        for value in (
            authority,
            document,
            delivery,
            config,
            host_options,
            macro_catalog,
        )
    ):
        raise VariationAuthorityAdapterError(
            "history fork context requires config, document, delivery, and host metadata"
        )
    source = document.get("source")
    if (
        snapshot.get("variation_id") != variation_id
        or authority.get("revision") != revision
        or delivery.get("source_digest") != ddl_digest
        or not isinstance(source, str)
        or hashlib.sha256(source.encode("utf-8")).hexdigest() != ddl_digest
    ):
        raise VariationAuthorityAdapterError(
            "history fork context does not match the committed revision"
        )
    payload = {
        "protocol_version": HISTORY_FORK_CONTEXT_PROTOCOL,
        "variation_id": variation_id,
        "revision": revision,
        "ddl_digest": ddl_digest,
        "config": config,
        "host_options": host_options,
        "macro_catalog": macro_catalog,
        "pipeline_diagnostics": _validate_pipeline_diagnostics(
            pipeline_diagnostics
        ),
    }
    encoded = _canonical_json(payload, sort_keys=True).encode("utf-8")
    return encoded, hashlib.sha256(encoded).hexdigest()


def _validate_pipeline_diagnostics(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) not in (
        _PIPELINE_DIAGNOSTIC_KEYS,
        _PIPELINE_DIAGNOSTIC_KEYS | {"plugin_diagnostics"},
    ):
        raise VariationAuthorityAdapterError(
            "pipeline diagnostics have an unexpected shape"
        )
    for key in (
        "upstream_diagnostics",
        "downstream_diagnostics",
        "resource_omissions",
        "relation_omissions",
    ):
        if not isinstance(value[key], list):
            raise VariationAuthorityAdapterError(
                "pipeline diagnostic channels must be arrays"
            )
    if "plugin_diagnostics" in value and not isinstance(value["plugin_diagnostics"], list):
        raise VariationAuthorityAdapterError(
            "pipeline diagnostic channels must be arrays"
        )
    for key in ("render_diagnostics", "resource_execution"):
        if value[key] is not None and not isinstance(value[key], Mapping):
            raise VariationAuthorityAdapterError(
                "render diagnostic records must be objects or null"
            )
    return dict(value)


def _decode_history_fork_context_payload(
    row: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, object] | None]:
    encoded = bytes(row["fork_context_bytes"])
    digest = hashlib.sha256(encoded).hexdigest()
    if digest != row["fork_context_digest"]:
        raise VariationAuthorityAdapterError(
            "stored history fork context failed integrity validation"
        )
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VariationAuthorityAdapterError(
            "stored history fork context is not UTF-8 JSON"
        ) from exc
    legacy_keys = {
        "protocol_version",
        "variation_id",
        "revision",
        "ddl_digest",
        "config",
        "host_options",
        "macro_catalog",
    }
    if not isinstance(payload, dict):
        raise VariationAuthorityAdapterError(
            "stored history fork context has an unexpected shape"
        )
    protocol = payload.get("protocol_version")
    if protocol == _LEGACY_HISTORY_FORK_CONTEXT_PROTOCOL:
        expected_keys = legacy_keys
        pipeline_diagnostics = None
    elif protocol == HISTORY_FORK_CONTEXT_PROTOCOL:
        expected_keys = legacy_keys | {"pipeline_diagnostics"}
        pipeline_diagnostics = _validate_pipeline_diagnostics(
            payload.get("pipeline_diagnostics")
        )
    else:
        raise VariationAuthorityAdapterError(
            "stored history fork context does not match its history link"
        )
    if set(payload) != expected_keys:
        raise VariationAuthorityAdapterError(
            "stored history fork context has an unexpected shape"
        )
    if (
        payload["variation_id"] != row["variation_id"]
        or payload["revision"] != row["revision"]
        or payload["ddl_digest"] != row["ddl_digest"]
        or not isinstance(payload["config"], dict)
        or not isinstance(payload["host_options"], dict)
        or not isinstance(payload["macro_catalog"], dict)
    ):
        raise VariationAuthorityAdapterError(
            "stored history fork context does not match its history link"
        )
    return payload, pipeline_diagnostics


def history_pipeline_diagnostics(
    row: Mapping[str, Any],
) -> dict[str, object] | None:
    """Read only diagnostics frozen on this exact immutable history link."""
    _, pipeline_diagnostics = _decode_history_fork_context_payload(row)
    return pipeline_diagnostics


def _decode_history_fork_context(
    row: Mapping[str, Any], history: LegacyHistoryRecord
) -> LinkedHistoryForkRecord:
    payload, pipeline_diagnostics = _decode_history_fork_context_payload(row)
    if (
        history.source is None
        or hashlib.sha256(history.source.encode("utf-8")).hexdigest()
        != row["ddl_digest"]
    ):
        raise VariationAuthorityAdapterError(
            "history source does not match its committed revision"
        )
    return LinkedHistoryForkRecord(
        history=history,
        variation_id=str(row["variation_id"]),
        revision=str(row["revision"]),
        ddl_digest=str(row["ddl_digest"]),
        saved_config=payload["config"],
        host_options=payload["host_options"],
        macro_catalog=payload["macro_catalog"],
        pipeline_diagnostics=pipeline_diagnostics,
    )


def _execution_record(row: Mapping[str, Any]) -> PipelineExecutionRecord:
    state_bytes = bytes(row["state_bytes"])
    state_digest = hashlib.sha256(state_bytes).hexdigest()
    if state_digest != row["state_digest"]:
        raise VariationAuthorityAdapterError(
            "stored execution state bytes failed integrity validation"
        )
    return PipelineExecutionRecord(
        execution_id=str(row["execution_id"]),
        variation_id=str(row["variation_id"]),
        sequence=str(row["sequence"]),
        state_bytes=state_bytes,
        state_digest=state_digest,
        created_at=int(row["created_at"]),
        updated_at=int(row["updated_at"]),
    )


@dataclass(frozen=True)
class VariationAuthorityStore:
    """Atomic owner-scoped storage for shared-core commit effects."""

    engine: Engine
    now_ms: Callable[[], int] = lambda: int(time.time() * 1000)

    def install_schema(self) -> None:
        """Install only the candidate tables, primarily for isolated harnesses."""
        candidate_metadata.create_all(
            self.engine,
            tables=[
                variation_authority,
                variation_authority_actions,
                pipeline_candidate_executions,
                pipeline_history_links,
            ],
        )

    def read(self, owner_id: str, variation_id: str) -> dict[str, object] | None:
        """Read one candidate sidecar without touching legacy history."""
        with self.engine.connect() as connection:
            row = connection.execute(
                select(variation_authority).where(
                    and_(
                        variation_authority.c.owner_id == owner_id,
                        variation_authority.c.variation_id == variation_id,
                    )
                )
            ).mappings().one_or_none()
        if row is None:
            return None
        return {
            "variation_id": row["variation_id"],
            "document": json.loads(row["document_json"]),
            "ddl_digest": row["ddl_digest"],
            "authority": {
                "protocol_version": row["protocol_version"],
                "revision": row["revision"],
                "origin": row["origin"],
                "authority": row["authority"],
            },
            "authority_digest": row["authority_digest"],
            "context": _context_payload(_context_from_row(row)),
        }

    def read_legacy_history(
        self, owner_id: str, history_id: str
    ) -> LegacyHistoryRecord | None:
        """Read an owned, non-trashed legacy work without classifying its origin."""
        with self.engine.connect() as connection:
            row = connection.execute(
                select(HistoryRow.__table__).where(
                    and_(
                        HistoryRow.user_id == owner_id,
                        HistoryRow.id == history_id,
                        HistoryRow.trashed == 0,
                    )
                )
            ).mappings().one_or_none()
        if row is None:
            return None
        metadata_fields = (
            "at",
            "catalog_id",
            "catalog_mode",
            "ddl_version",
            "ddl_engine_version",
            "stage1_model",
            "stage2_model",
            "stage1_prompt_digest",
            "stage1_prompt_base_digest",
            "stage2_prompt_digest",
            "render_build_number",
            "render_engine_id",
            "render_engine_version",
            "render_color_profile",
            "render_color_catalog_id",
            "render_color_catalog_name",
            "render_color_catalog_sub",
            "render_color_catalog",
            "render_color_map",
            "render_canvas_aspect",
            "render_canvas_aspect_id",
            "render_canvas_aspect_ratio",
            "instruction_lang_requested",
            "instruction_lang_resolved",
            "ui_lang",
            "render_seed",
            "render_wild",
            "composition_seed",
            "variation_amplitude",
            "variation_seed",
            "interpretation_seed",
            "seed_text",
            "render_limits",
            "lineage_node_id",
        )
        # A historical schema can lack a later optional column. The read remains
        # faithful by omitting that key rather than manufacturing a default.
        metadata = {
            field: row[field]
            for field in metadata_fields
            if field in row and row[field] is not None
        }
        return LegacyHistoryRecord(
            history_id=str(row["id"]),
            description=str(row["input"] or ""),
            source=row["ddl"],
            expanded_source=row["expanded_ddl"],
            score_json=str(row["score"] or "{}"),
            svg=str(row["svg"] or ""),
            authority="legacy_unknown",
            metadata=metadata,
        )

    def inventory(self) -> VariationAuthorityInventory:
        """Count compatible state without reading any authored text."""
        inspector = inspect(self.engine)
        history_present = inspector.has_table("history")
        candidate_present = inspector.has_table(
            variation_authority.name
        ) and inspector.has_table(
            variation_authority_actions.name
        ) and inspector.has_table(pipeline_candidate_executions.name)
        history_rows = 0
        history_has_authority = False
        candidate_counts = {
            "candidate_variations": 0,
            "description_authoritative": 0,
            "ddl_authoritative": 0,
            "explicit_legacy_unknown": 0,
            "action_acknowledgments": 0,
            "candidate_executions": 0,
        }
        with self.engine.connect() as connection:
            if history_present:
                history_columns = {
                    column["name"] for column in inspector.get_columns("history")
                }
                history_has_authority = {
                    "variation_id",
                    "variation_origin",
                    "authoring_authority",
                    "authoring_revision",
                }.issubset(history_columns)
                history_rows = int(
                    connection.exec_driver_sql(
                        "SELECT count(*) FROM history"
                    ).scalar_one()
                )
            if candidate_present:
                candidate_counts["candidate_variations"] = int(
                    connection.execute(
                        select(func.count()).select_from(variation_authority)
                    ).scalar_one()
                )
                for authority in _AUTHORITIES:
                    key = (
                        "explicit_legacy_unknown"
                        if authority == "legacy_unknown"
                        else authority
                    )
                    candidate_counts[key] = int(
                        connection.execute(
                            select(func.count())
                            .select_from(variation_authority)
                            .where(variation_authority.c.authority == authority)
                        ).scalar_one()
                    )
                candidate_counts["action_acknowledgments"] = int(
                    connection.execute(
                        select(func.count()).select_from(
                            variation_authority_actions
                        )
                    ).scalar_one()
                )
                candidate_counts["candidate_executions"] = int(
                    connection.execute(
                        select(func.count()).select_from(
                            pipeline_candidate_executions
                        )
                    ).scalar_one()
                )
        return VariationAuthorityInventory(
            history_table_present=history_present,
            history_rows=history_rows,
            history_authority_columns_present=history_has_authority,
            # Current history has none of the four authority fields. Every such
            # row stays explicitly unclassified; no input/DDL resemblance is read.
            legacy_unknown_history_rows=(
                history_rows if not history_has_authority else 0
            ),
            candidate_tables_present=candidate_present,
            **candidate_counts,
        )

    def link_history(
        self,
        owner_id: str,
        history_id: str,
        variation_id: str,
        revision: str,
        ddl_digest: str,
        *,
        snapshot: Mapping[str, Any],
        context: Mapping[str, Any],
        pipeline_diagnostics: Mapping[str, Any],
    ) -> None:
        revision, _ = _decimal_u64(revision, "history revision")
        context_bytes, context_digest = _history_fork_context_bytes(
            snapshot,
            context,
            variation_id=variation_id,
            revision=revision,
            ddl_digest=ddl_digest,
            pipeline_diagnostics=pipeline_diagnostics,
        )
        values = dict(owner_id=owner_id, history_id=history_id, variation_id=variation_id,
                      revision=revision, ddl_digest=ddl_digest,
                      fork_context_bytes=context_bytes,
                      fork_context_digest=context_digest)
        with self.engine.begin() as connection:
            owned_source = connection.execute(select(HistoryRow.ddl).where(
                HistoryRow.id == history_id, HistoryRow.user_id == owner_id,
            )).scalar_one_or_none()
            acknowledged = connection.execute(select(variation_authority_actions.c.action_id).where(
                variation_authority_actions.c.owner_id == owner_id,
                variation_authority_actions.c.variation_id == variation_id,
                variation_authority_actions.c.revision == revision,
                variation_authority_actions.c.ddl_digest == ddl_digest,
            ).limit(1)).scalar_one_or_none()
            if (
                owned_source is None
                or hashlib.sha256(owned_source.encode("utf-8")).hexdigest()
                != ddl_digest
                or acknowledged is None
            ):
                raise VariationAuthorityAdapterError("history link requires owned history and committed source")
            existing = connection.execute(select(pipeline_history_links).where(
                pipeline_history_links.c.owner_id == owner_id,
                pipeline_history_links.c.history_id == history_id,
            )).mappings().one_or_none()
            if existing is not None:
                if dict(existing) != values:
                    raise VariationAuthorityAdapterError("history link identity conflict")
                return
            connection.execute(pipeline_history_links.insert().values(**values))

    def history_link(self, owner_id: str, history_id: str) -> dict | None:
        with self.engine.connect() as connection:
            row = connection.execute(select(pipeline_history_links).where(
                pipeline_history_links.c.owner_id == owner_id,
                pipeline_history_links.c.history_id == history_id,
            )).mappings().one_or_none()
        if row is None:
            return None
        return {
            key: row[key]
            for key in ("owner_id", "history_id", "variation_id", "revision", "ddl_digest")
        }

    def read_linked_history(
        self, owner_id: str, history_id: str
    ) -> LinkedHistoryForkRecord | None:
        """Read one exact managed-history fork without consulting latest state."""
        history = self.read_legacy_history(owner_id, history_id)
        if history is None:
            return None
        with self.engine.connect() as connection:
            row = connection.execute(
                select(pipeline_history_links).where(
                    pipeline_history_links.c.owner_id == owner_id,
                    pipeline_history_links.c.history_id == history_id,
                )
            ).mappings().one_or_none()
        if row is None:
            return None
        return _decode_history_fork_context(row, history)

    def create_execution(
        self,
        owner_id: str,
        execution_id: str,
        variation_id: str,
        sequence: str,
        state_bytes: bytes,
    ) -> PipelineExecutionRecord:
        """Persist the first complete host wrapper for a minted execution."""
        if not owner_id or not execution_id or not variation_id:
            raise VariationAuthorityAdapterError(
                "execution owner and identities must not be empty"
            )
        sequence, _ = _decimal_u64(sequence, "execution sequence")
        state_bytes, state_digest = _validated_state_bytes(state_bytes)
        now = self.now_ms()
        try:
            with self.engine.begin() as connection:
                existing = connection.execute(
                    select(pipeline_candidate_executions).where(
                        and_(
                            pipeline_candidate_executions.c.owner_id
                            == owner_id,
                            pipeline_candidate_executions.c.execution_id
                            == execution_id,
                        )
                    )
                ).mappings().one_or_none()
                if existing is not None:
                    record = _execution_record(existing)
                    if (
                        record.variation_id == variation_id
                        and record.sequence == sequence
                        and record.state_digest == state_digest
                    ):
                        return record
                    raise ExecutionSnapshotConflict(record.sequence)
                connection.execute(
                    pipeline_candidate_executions.insert().values(
                        owner_id=owner_id,
                        execution_id=execution_id,
                        variation_id=variation_id,
                        sequence=sequence,
                        state_bytes=state_bytes,
                        state_digest=state_digest,
                        created_at=now,
                        updated_at=now,
                    )
                )
        except IntegrityError as exc:
            existing = self.read_execution(owner_id, execution_id)
            if (
                existing is not None
                and existing.variation_id == variation_id
                and existing.sequence == sequence
                and existing.state_digest == state_digest
            ):
                return existing
            raise ExecutionSnapshotConflict(
                None if existing is None else existing.sequence
            ) from exc
        record = self.read_execution(owner_id, execution_id)
        if record is None:
            raise VariationAuthorityAdapterError(
                "execution insert was not durable"
            )
        return record

    def read_execution(
        self,
        owner_id: str,
        execution_id: str | None = None,
        *,
        variation_id: str | None = None,
    ) -> PipelineExecutionRecord | None:
        """Read by execution id, or route a variation id to its latest save."""
        if (execution_id is None) == (variation_id is None):
            raise VariationAuthorityAdapterError(
                "exactly one execution or variation identity is required"
            )
        if variation_id is not None:
            return self.read_latest_execution_for_variation(
                owner_id, variation_id
            )
        with self.engine.connect() as connection:
            row = connection.execute(
                select(pipeline_candidate_executions).where(
                    and_(
                        pipeline_candidate_executions.c.owner_id == owner_id,
                        pipeline_candidate_executions.c.execution_id
                        == execution_id,
                    )
                )
            ).mappings().one_or_none()
        return None if row is None else _execution_record(row)

    def read_latest_execution_for_variation(
        self, owner_id: str, variation_id: str
    ) -> PipelineExecutionRecord | None:
        """Read the most recently persisted execution for one owned variation."""
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(pipeline_candidate_executions)
                    .where(
                        and_(
                            pipeline_candidate_executions.c.owner_id
                            == owner_id,
                            pipeline_candidate_executions.c.variation_id
                            == variation_id,
                        )
                    )
                    .order_by(
                        pipeline_candidate_executions.c.updated_at.desc(),
                        pipeline_candidate_executions.c.execution_id.desc(),
                    )
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _execution_record(row)

    def compare_and_set_execution(
        self,
        owner_id: str,
        execution_id: str,
        *,
        expected_sequence: str,
        next_sequence: str,
        state_bytes: bytes,
    ) -> PipelineExecutionRecord:
        """Advance one opaque host wrapper exactly once across shared tabs."""
        expected_sequence, expected = _decimal_u64(
            expected_sequence, "expected execution sequence"
        )
        next_sequence, following = _decimal_u64(
            next_sequence, "next execution sequence"
        )
        if expected == _U64_MAX or following != expected + 1:
            raise VariationAuthorityAdapterError(
                "next execution sequence must increment expected sequence"
            )
        state_bytes, state_digest = _validated_state_bytes(state_bytes)
        now = self.now_ms()
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(pipeline_candidate_executions)
                .where(
                    and_(
                        pipeline_candidate_executions.c.owner_id == owner_id,
                        pipeline_candidate_executions.c.execution_id
                        == execution_id,
                        pipeline_candidate_executions.c.sequence
                        == expected_sequence,
                    )
                )
                .values(
                    sequence=next_sequence,
                    state_bytes=state_bytes,
                    state_digest=state_digest,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                actual = connection.execute(
                    select(pipeline_candidate_executions.c.sequence).where(
                        and_(
                            pipeline_candidate_executions.c.owner_id
                            == owner_id,
                            pipeline_candidate_executions.c.execution_id
                            == execution_id,
                        )
                    )
                ).scalar_one_or_none()
                raise ExecutionSnapshotConflict(
                    None if actual is None else str(actual)
                )
        record = self.read_execution(owner_id, execution_id)
        if record is None:
            raise VariationAuthorityAdapterError(
                "execution update was not durable"
            )
        return record

    def commit_effect(
        self,
        owner_id: str,
        action: Mapping[str, Any],
        *,
        create_if_missing: bool = False,
        authoring_context: VariationAuthoringContext | None = None,
    ) -> dict[str, object]:
        """Apply one core commit action and return its typed effect result.

        create_if_missing is an explicit candidate-host assertion that this is a
        new variation. It must never be enabled merely because no sidecar exists:
        an absent legacy sidecar is not evidence of a new variation.
        """
        commit = _parse_commit(owner_id, action)
        try:
            return self._commit_once(
                commit,
                create_if_missing=create_if_missing,
                authoring_context=authoring_context,
            )
        except IntegrityError:
            # A concurrent transaction may have installed the same action ack or
            # won the initial insert. Re-read durable state instead of retrying
            # the mutation under a fresh interpretation.
            return self._recover_after_integrity_conflict(
                commit, authoring_context
            )

    def _commit_once(
        self,
        commit: _Commit,
        *,
        create_if_missing: bool,
        authoring_context: VariationAuthoringContext | None,
    ) -> dict[str, object]:
        now = self.now_ms()
        with self.engine.begin() as connection:
            acknowledged = connection.execute(
                select(variation_authority_actions).where(
                    and_(
                        variation_authority_actions.c.owner_id == commit.owner_id,
                        variation_authority_actions.c.action_id == commit.action_id,
                    )
                )
            ).mappings().one_or_none()
            if acknowledged is not None:
                return self._replay_ack(
                    commit, acknowledged, authoring_context
                )

            current = connection.execute(
                select(variation_authority).where(
                    and_(
                        variation_authority.c.owner_id == commit.owner_id,
                        variation_authority.c.variation_id == commit.variation_id,
                    )
                )
            ).mappings().one_or_none()
            if current is None:
                if not create_if_missing:
                    return _failed_result(commit, None)
                if commit.expected_revision != "0" or (
                    commit.origin,
                    commit.authority,
                ) not in _INITIAL_PAIRS:
                    raise VariationAuthorityAdapterError(
                        "new candidate variation has an invalid initial transition"
                    )
                resolved_context = (
                    authoring_context or VariationAuthoringContext()
                )
                _validate_initial_context(
                    connection, commit, resolved_context
                )
                connection.execute(
                    variation_authority.insert().values(
                        owner_id=commit.owner_id,
                        variation_id=commit.variation_id,
                        protocol_version=AUTHORITY_PROTOCOL,
                        revision=commit.next_revision,
                        origin=commit.origin,
                        authority=commit.authority,
                        source=commit.source,
                        document_json=commit.document_json,
                        ddl_digest=commit.ddl_digest,
                        authority_digest=commit.authority_digest,
                        description=resolved_context.description,
                        derivation_kind=resolved_context.derivation_kind,
                        parent_legacy_history_id=(
                            resolved_context.parent_legacy_history_id
                        ),
                        parent_variation_id=(
                            resolved_context.parent_variation_id
                        ),
                        updated_at=now,
                    )
                )
            else:
                if current["revision"] != commit.expected_revision:
                    return _failed_result(commit, str(current["revision"]))
                _transition_allowed(current, commit)
                resolved_context = _resolved_context(
                    current, commit, authoring_context
                )
                changed = connection.execute(
                    update(variation_authority)
                    .where(
                        and_(
                            variation_authority.c.owner_id == commit.owner_id,
                            variation_authority.c.variation_id == commit.variation_id,
                            variation_authority.c.revision
                            == commit.expected_revision,
                        )
                    )
                    .values(
                        revision=commit.next_revision,
                        authority=commit.authority,
                        source=commit.source,
                        document_json=commit.document_json,
                        ddl_digest=commit.ddl_digest,
                        authority_digest=commit.authority_digest,
                        description=resolved_context.description,
                        updated_at=now,
                    )
                )
                if changed.rowcount != 1:
                    actual = connection.execute(
                        select(variation_authority.c.revision).where(
                            and_(
                                variation_authority.c.owner_id == commit.owner_id,
                                variation_authority.c.variation_id
                                == commit.variation_id,
                            )
                        )
                    ).scalar_one_or_none()
                    return _failed_result(
                        commit, None if actual is None else str(actual)
                    )

            connection.execute(
                variation_authority_actions.insert().values(
                    owner_id=commit.owner_id,
                    action_id=commit.action_id,
                    variation_id=commit.variation_id,
                    request_digest=commit.request_digest,
                    action_fingerprint=commit.action_fingerprint,
                    context_fingerprint=_context_fingerprint(
                        resolved_context
                    ),
                    ddl_digest=commit.ddl_digest,
                    revision=commit.next_revision,
                    authority_digest=commit.authority_digest,
                    committed_at=now,
                )
            )
        return _committed_result(commit)

    def _recover_after_integrity_conflict(
        self,
        commit: _Commit,
        authoring_context: VariationAuthoringContext | None,
    ) -> dict[str, object]:
        with self.engine.connect() as connection:
            acknowledged = connection.execute(
                select(variation_authority_actions).where(
                    and_(
                        variation_authority_actions.c.owner_id == commit.owner_id,
                        variation_authority_actions.c.action_id == commit.action_id,
                    )
                )
            ).mappings().one_or_none()
            if acknowledged is not None:
                return self._replay_ack(
                    commit, acknowledged, authoring_context
                )
            actual = connection.execute(
                select(variation_authority.c.revision).where(
                    and_(
                        variation_authority.c.owner_id == commit.owner_id,
                        variation_authority.c.variation_id == commit.variation_id,
                    )
                )
            ).scalar_one_or_none()
        return _failed_result(commit, None if actual is None else str(actual))

    @staticmethod
    def _replay_ack(
        commit: _Commit,
        acknowledged: Mapping[str, Any],
        authoring_context: VariationAuthoringContext | None,
    ) -> dict[str, object]:
        if (
            acknowledged["variation_id"] != commit.variation_id
            or acknowledged["request_digest"] != commit.request_digest
            or acknowledged["action_fingerprint"] != commit.action_fingerprint
            or acknowledged["ddl_digest"] != commit.ddl_digest
            or acknowledged["revision"] != commit.next_revision
            or acknowledged["authority_digest"] != commit.authority_digest
            or (
                authoring_context is not None
                and acknowledged["context_fingerprint"]
                != _context_fingerprint(authoring_context)
            )
        ):
            raise ActionIdentityConflict(
                "action_id was already acknowledged for different commit bytes"
            )
        return _committed_result(commit)
