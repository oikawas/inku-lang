"""Candidate persistence adapter for shared variation-authority commit effects.

The ordinary Server runtime does not import or install these tables. A managed
candidate host must explicitly call VariationAuthorityStore.install_schema
before it can apply a shared-core commit effect. This keeps the legacy history
path unchanged until the later runtime cutover.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    MetaData,
    String,
    Table,
    Text,
    and_,
    func,
    inspect,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


AUTHORITY_PROTOCOL = "inku.variation-authority.v1"
COMMIT_ACTION_TAG = "commit_visible_normalized_ddl"
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

candidate_metadata = MetaData()

variation_authority = Table(
    "variation_authority",
    candidate_metadata,
    Column("owner_id", String, primary_key=True),
    Column("variation_id", String, primary_key=True),
    Column("protocol_version", String, nullable=False),
    # Revisions remain canonical decimal strings across the Rust/Python/SQLite
    # boundary, so no binding or database integer can truncate a u64.
    Column("revision", String, nullable=False),
    Column("origin", String, nullable=False),
    Column("authority", String, nullable=False),
    Column("source", Text, nullable=False),
    Column("document_json", Text, nullable=False),
    Column("ddl_digest", String, nullable=False),
    Column("authority_digest", String, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    CheckConstraint(
        "origin IN ('stage1_generated', 'user_authored_ddl')",
        name="ck_variation_authority_origin",
    ),
    CheckConstraint(
        "authority IN "
        "('description_authoritative', 'ddl_authoritative', 'legacy_unknown')",
        name="ck_variation_authority_value",
    ),
)

variation_authority_actions = Table(
    "variation_authority_actions",
    candidate_metadata,
    Column("owner_id", String, primary_key=True),
    Column("action_id", String, primary_key=True),
    Column("variation_id", String, nullable=False),
    Column("request_digest", String, nullable=False),
    # This adapter-local equality fingerprint is never returned as a shared-core
    # digest and never becomes semantic authority.
    Column("action_fingerprint", String, nullable=False),
    Column("ddl_digest", String, nullable=False),
    Column("revision", String, nullable=False),
    Column("authority_digest", String, nullable=False),
    Column("committed_at", BigInteger, nullable=False),
)


class VariationAuthorityAdapterError(ValueError):
    """A core commit action does not satisfy the candidate host contract."""


class ActionIdentityConflict(VariationAuthorityAdapterError):
    """A reused action identity carries different logical action bytes."""


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


@dataclass(frozen=True)
class VariationAuthorityStore:
    """Atomic owner-scoped storage for shared-core commit effects."""

    engine: Engine
    now_ms: Callable[[], int] = lambda: int(time.time() * 1000)

    def install_schema(self) -> None:
        """Install only the opt-in candidate sidecar tables."""
        candidate_metadata.create_all(self.engine)

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
        }

    def inventory(self) -> VariationAuthorityInventory:
        """Count compatible state without reading any authored text."""
        inspector = inspect(self.engine)
        history_present = inspector.has_table("history")
        candidate_present = inspector.has_table(
            variation_authority.name
        ) and inspector.has_table(variation_authority_actions.name)
        history_rows = 0
        history_has_authority = False
        candidate_counts = {
            "candidate_variations": 0,
            "description_authoritative": 0,
            "ddl_authoritative": 0,
            "explicit_legacy_unknown": 0,
            "action_acknowledgments": 0,
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

    def commit_effect(
        self,
        owner_id: str,
        action: Mapping[str, Any],
        *,
        create_if_missing: bool = False,
    ) -> dict[str, object]:
        """Apply one core commit action and return its typed effect result.

        create_if_missing is an explicit candidate-host assertion that this is a
        new variation. It must never be enabled merely because no sidecar exists:
        an absent legacy sidecar is not evidence of a new variation.
        """
        commit = _parse_commit(owner_id, action)
        try:
            return self._commit_once(commit, create_if_missing=create_if_missing)
        except IntegrityError:
            # A concurrent transaction may have installed the same action ack or
            # won the initial insert. Re-read durable state instead of retrying
            # the mutation under a fresh interpretation.
            return self._recover_after_integrity_conflict(commit)

    def _commit_once(
        self,
        commit: _Commit,
        *,
        create_if_missing: bool,
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
                return self._replay_ack(commit, acknowledged)

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
                        updated_at=now,
                    )
                )
            else:
                if current["revision"] != commit.expected_revision:
                    return _failed_result(commit, str(current["revision"]))
                _transition_allowed(current, commit)
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
                    ddl_digest=commit.ddl_digest,
                    revision=commit.next_revision,
                    authority_digest=commit.authority_digest,
                    committed_at=now,
                )
            )
        return _committed_result(commit)

    def _recover_after_integrity_conflict(
        self, commit: _Commit
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
                return self._replay_ack(commit, acknowledged)
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
    ) -> dict[str, object]:
        if (
            acknowledged["variation_id"] != commit.variation_id
            or acknowledged["request_digest"] != commit.request_digest
            or acknowledged["action_fingerprint"] != commit.action_fingerprint
            or acknowledged["ddl_digest"] != commit.ddl_digest
            or acknowledged["revision"] != commit.next_revision
            or acknowledged["authority_digest"] != commit.authority_digest
        ):
            raise ActionIdentityConflict(
                "action_id was already acknowledged for different commit bytes"
            )
        return _committed_result(commit)
