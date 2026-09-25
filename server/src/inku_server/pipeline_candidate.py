"""Serialized host execution for the shared Rust authoring pipeline.

Configuration, native binding and owner identity come from the trusted server.
Clients cannot submit snapshots,
authority sidecars, effect results or resource policies through this module.
"""

from __future__ import annotations

import importlib
import json
import logging
import threading
import time
import uuid
from typing import Callable

from .persistence.variation_authority import VariationAuthoringContext, VariationAuthorityStore


_logger = logging.getLogger(__name__)
_PIPELINE_FAILURES = {
    "transport_unavailable",
    "transport_timeout",
    "rate_limited",
    "provider_rejected",
    "malformed_payload",
    "schema_violation",
    "semantic_violation",
}
_PIPELINE_FAILURE_DETAILS = {"credentials_unavailable"}
_HOLE_COMPLETION_STATUSES = {"validated", "rejected", "unresolved"}
_ACTION_STAGES = {
    "generate_sketch": "sketch",
    "select_description_catalog": "catalog",
    "generate_normalized_ddl": "stage1",
    "complete_visible_ddl_holes": "stage2",
}


class CandidateHostError(ValueError):
    """A stable host error; provider exception text is not part of the protocol."""


def _bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _nonnegative_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_compiler_failure_detail(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    return value if all(character.isascii() and (character.islower() or character.isdigit() or character == "_") for character in value) else None


def _safe_hole_id(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or len(value) != 69
        or not value.startswith("hole:")
    ):
        return None
    suffix = value.removeprefix("hole:")
    return value if all(character in "0123456789abcdef" for character in suffix) else None


def _safe_hole_completion_check(value: object) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("results"), list):
        return None
    results = []
    for row in value["results"]:
        if not isinstance(row, dict):
            continue
        hole_id = _safe_hole_id(row.get("hole_id"))
        status = row.get("status")
        reason = _safe_compiler_failure_detail(row.get("reason"))
        if hole_id is None or status not in _HOLE_COMPLETION_STATUSES:
            continue
        results.append({"hole_id": hole_id, "status": status, "reason": reason})
    return {"results": results} if results else None


def _hole_completion_checks(result: dict) -> list[dict]:
    """Project the core's safe per-hole event without retaining provider text."""
    projected = []
    for event in result.get("events") or []:
        if not isinstance(event, dict) or event.get("tag") != "hole_completion_checked":
            continue
        check = _safe_hole_completion_check(event.get("payload"))
        if check is not None:
            projected.append(check)
    return projected


def _sync_hole_completion_check(context: dict, snapshot: dict) -> dict | None:
    check = _safe_hole_completion_check(snapshot.get("hole_completion_check"))
    if check is None:
        context.pop("hole_completion_check", None)
        return None
    context["hole_completion_check"] = check
    return check


def _pipeline_failures(state: dict | None, envelope: dict, result: dict) -> list[tuple[str, dict]]:
    """Project only stable failure values from a fresh core transition."""
    if state is None or envelope["payload"].get("tag") != "effect_result":
        return []
    action = state.get("action") or {}
    action_identity = action.get("identity") or {}
    effect_result = envelope["payload"].get("result") or {}
    elapsed_ms = _nonnegative_int(effect_result.get("elapsed_ms"))
    attempt = _nonnegative_int(action_identity.get("attempt"))
    stage = _ACTION_STAGES.get(str(action.get("tag") or ""))
    projected: list[tuple[str, dict]] = []
    for event in result.get("events") or []:
        transition = event.get("tag")
        if transition not in {"retry_scheduled", "failed"}:
            continue
        payload = event.get("payload") or {}
        failure = payload.get("failure") if transition == "retry_scheduled" else payload.get("reason")
        if failure not in _PIPELINE_FAILURES or stage is None:
            continue
        diagnostic: dict[str, object] = {"failure": failure, "stage": stage}
        detail = _safe_compiler_failure_detail(payload.get("detail"))
        if failure == "semantic_violation" and detail is not None:
            diagnostic["detail"] = detail
        if attempt is not None:
            diagnostic["attempt"] = attempt
        if elapsed_ms is not None:
            diagnostic["elapsed_ms"] = elapsed_ms
        projected.append((transition, diagnostic))
    return projected


class PipelineBinding:
    """Use the shared authoring boundary packaged in the shipped native wheel."""

    def __init__(self):
        try:
            module = importlib.import_module("inku_render")
            version_report = module.pipeline_version_report
            self.step = module.pipeline_step
            self.canvas_registry = json.loads(module.pipeline_canvas_registry())
            self.resolve_palette = module.pipeline_resolve_palette
            self.render_saved = module.pipeline_render_saved
            self.resolve_macro_catalog = module.pipeline_resolve_macro_catalog
        except (AttributeError, ImportError) as error:
            raise CandidateHostError("binding_unavailable") from error
        self.versions = json.loads(version_report())
        if self.versions != {"binding_version": "1.1.0", "protocol_version": "1.0.0"}:
            raise CandidateHostError("binding_protocol_mismatch")


class CandidateExecution:
    """One serialized, host-owned execution, isolated from legacy history.

    The provider callback performs exactly one transport attempt and returns an
    EffectResult. Only Rust selects retries, completion and fallback. The caller
    owns saving the returned bytes through save_snapshot.
    """

    def __init__(
        self, binding: PipelineBinding, store: VariationAuthorityStore, *,
        owner_id: str, config: dict, provider: Callable[[dict], dict],
        allow_render: bool = False,
        context: dict | None = None,
        save_snapshot: Callable[[dict | None, dict, dict, dict | None], None] | None = None,
    ):
        self.binding, self.store, self.owner_id = binding, store, owner_id
        self.config = json.loads(_bytes(config))
        self.provider = provider
        self.allow_render = allow_render
        self.context = json.loads(_bytes(context or {}))
        self.save_snapshot = save_snapshot
        self._rendered: dict | None = None
        self._snapshot: dict | None = None
        self._lock = threading.RLock()
        self._fresh = False
        self._provider_in_flight = False
        self.transcript: list[dict] = []
        self.last_output: dict | None = None

    def start_new(self, authoring: dict) -> dict:
        """A fresh host-minted identity; absence in history never implies newness."""
        with self._lock:
            if self._snapshot is not None or authoring.get("tag") not in {"direct_ddl", "description"}:
                raise CandidateHostError("invalid_start")
            direct = authoring["tag"] == "direct_ddl"
            self._fresh = True
            return self._advance({
                "tag": "start", "variation_id": uuid.uuid4().hex,
                "authoring_nonce": uuid.uuid4().hex, "config": self.config,
                "authority": {
                    "protocol_version": "inku.variation-authority.v1", "revision": "0",
                    "origin": "user_authored_ddl" if direct else "stage1_generated",
                    "authority": "ddl_authoritative" if direct else "description_authoritative",
                },
                "authoring": authoring,
            })

    def command(self, payload: dict, *, context_updates: dict | None = None) -> dict:
        """Forward only author actions; expected revisions remain Rust inputs."""
        allowed = {"commit_user_ddl", "generate_from_description", "complete_holes",
                   "approve_patch", "decline_patch", "cancel"}
        if self.allow_render:
            allowed.add("render")
        if payload.get("tag") not in allowed:
            raise CandidateHostError("unsupported_author_action")
        with self._lock:
            if self._snapshot is None:
                raise CandidateHostError("execution_not_started")
            previous_context = self.context
            if context_updates:
                self.context = {**self.context, **json.loads(_bytes(context_updates))}
            if payload["tag"] == "generate_from_description":
                # The core reads the drawn text; the work keeps what the author
                # wrote, which the host may pass alongside as the context value.
                written = (context_updates or {}).get("description", payload.get("description", ""))
                self.context = {**self.context, "description": written}
            try:
                return self._advance(payload)
            except Exception:
                self.context = previous_context
                raise

    def restore(self, snapshot: dict, *, rendered: dict | None = None) -> None:
        """Restore only trusted host persistence; never accept client snapshots."""
        with self._lock:
            if self._snapshot is not None:
                raise CandidateHostError("execution_already_started")
            self._snapshot = json.loads(_bytes(snapshot))
            self._rendered = rendered
            self._fresh = snapshot["authority"]["revision"] == "0"

    def run_effect(self) -> dict | None:
        """Execute the current effect once. No effect means author input is next."""
        with self._lock:
            if self._snapshot is None or self._snapshot["action"] is None:
                return None
            if self._provider_in_flight:
                raise CandidateHostError("provider_effect_in_flight")
            action = json.loads(_bytes(self._snapshot["action"]))
            if action["tag"] == "commit_visible_normalized_ddl":
                context = None
                if self.context:
                    generated = action["payload"]["reason"] in {
                        "stage1_generated", "stage1_residual_execution",
                    }
                    description = self.context.get("description", "") if generated else self.context.get("committed_description", self.context.get("description", ""))
                    context = VariationAuthoringContext(
                        description=description,
                        derivation_kind=self.context.get("derivation_kind", "new"),
                        parent_legacy_history_id=self.context.get("parent_legacy_history_id"),
                        parent_variation_id=self.context.get("parent_variation_id"),
                    )
                result = self.store.commit_effect(
                    self.owner_id, action, create_if_missing=self._fresh,
                    authoring_context=context,
                )
                if result["tag"] == "visible_normalized_ddl_committed":
                    self._fresh = False
                    if context is not None:
                        self.context["committed_description"] = context.description
                        if action["payload"]["authority"]["next_state"]["authority"] == "ddl_authoritative":
                            self.context["description"] = context.description
                return self._advance({"tag": "effect_result", "result": result})
            self._provider_in_flight = True
        try:
            # Cancellation can invalidate the action during bounded provider I/O.
            time.sleep(int(action["delay_ms"]) / 1000)
            with self._lock:
                if self._snapshot["action"] != action:
                    return None
            result = self.provider(action)
            with self._lock:
                if self._snapshot["action"] != action:
                    return None
                return self._advance({"tag": "effect_result", "result": result})
        finally:
            with self._lock:
                self._provider_in_flight = False

    def view(self) -> dict:
        """Visible source/diagnostics and exact authority; not a resumable token."""
        with self._lock:
            if self._snapshot is None:
                raise CandidateHostError("execution_not_started")
            state = self._snapshot
            result = {key: state[key] for key in (
                "execution_id", "variation_id", "sequence", "authority", "document", "phase", "delivery"
            )}
            result.update({"description": self.context.get("description", ""),
                           "parent": self.context.get("parent"),
                           "busy": state["action"] is not None,
                           "sketch": state.get("sketch"),
                           "catalog_diagnostics": self.context.get("macro_catalog", {}).get("diagnostics", []),
                           "rendered": self._rendered,
                           "result": self.context.get("result")})
            if self.context.get("provider_failure") is not None:
                result["provider_failure"] = self.context["provider_failure"]
            if self.context.get("hole_completion_check") is not None:
                result["hole_completion_check"] = self.context["hole_completion_check"]
            if self.context.get("host_options", {}).get("developer_capture_provider_io") is True:
                result["provider_capture_requested"] = True
            return json.loads(_bytes(result))

    def snapshot(self) -> dict:
        """Internal harness/export API, not exposed on the HTTP author surface."""
        with self._lock:
            if self._snapshot is None:
                raise CandidateHostError("execution_not_started")
            return json.loads(_bytes(self._snapshot))

    def _advance(self, payload: dict) -> dict:
        limits = self.config["envelope_limits"]
        state = self._snapshot
        envelope = {
            "protocol": "inku.pipeline", "version": "1.0.0", "kind": "input",
            "execution_id": state["execution_id"] if state else "new",
            "sequence": str(int(state["sequence"]) + 1) if state else "0",
            "message_id": uuid.uuid4().hex, "payload": {**payload, "version": 1},
        }
        snapshot_bytes, input_bytes = (_bytes(state) if state else b""), _bytes(envelope)
        if len(snapshot_bytes) > limits["max_snapshot_bytes"] or len(input_bytes) > limits["max_input_bytes"]:
            raise CandidateHostError("transport_size_limit")
        output_bytes = self.binding.step(snapshot_bytes, input_bytes)
        if len(output_bytes) > limits["max_output_bytes"]:
            raise CandidateHostError("transport_size_limit")
        output = json.loads(output_bytes)
        self.transcript.append({"input": envelope, "output": output})
        if output["kind"] == "error":
            raise CandidateHostError(output["payload"]["code"])
        result = output["payload"]["result"]
        next_snapshot = result["snapshot"]
        rendered = result["rendered"]
        # A committed edit invalidates the previous performance. Keep it only
        # when the same acknowledged source and Score remain active.
        if rendered is None and state and next_snapshot["document"] == state["document"] and next_snapshot["delivery"] is not None:
            rendered = self._rendered
        for transition, diagnostic in _pipeline_failures(state, envelope, result):
            existing = self.context.get("provider_failure")
            if (
                diagnostic.get("failure") == "provider_rejected"
                and isinstance(existing, dict)
                and all(existing.get(key) == diagnostic.get(key) for key in ("failure", "stage", "attempt"))
                and existing.get("detail") in _PIPELINE_FAILURE_DETAILS
            ):
                diagnostic["detail"] = existing["detail"]
            self.context["provider_failure"] = diagnostic
            _logger.warning(
                "pipeline_failure %s",
                json.dumps(
                    {
                        "execution_id": next_snapshot["execution_id"],
                        "variation_id": next_snapshot["variation_id"],
                        "transition": transition,
                        **diagnostic,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        check = _sync_hole_completion_check(self.context, next_snapshot)
        if _hole_completion_checks(result):
            if check is None:
                raise CandidateHostError("pipeline_schema_violation")
            _logger.info(
                "hole_completion_checked %s",
                json.dumps(
                    {
                        "execution_id": next_snapshot["execution_id"],
                        "variation_id": next_snapshot["variation_id"],
                        **check,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        # The host may need this server-generated identity before its first
        # provider effect. Put it into the same context snapshot that is about
        # to be durably saved, rather than only the caller's pre-copy dict.
        self.context["execution_id"] = next_snapshot["execution_id"]
        if self.save_snapshot is not None:
            self.save_snapshot(state, next_snapshot, self.context, rendered)
        self._snapshot = next_snapshot
        self._rendered = rendered
        self.last_output = output
        return output
