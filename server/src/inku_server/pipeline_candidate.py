"""Serialized host execution for the shared Rust authoring pipeline.

Configuration, bundle location and owner identity come from the trusted server.
Clients cannot submit snapshots,
authority sidecars, effect results or resource policies through this module.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import platform
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from .persistence.variation_authority import VariationAuthoringContext, VariationAuthorityStore


class CandidateHostError(ValueError):
    """A stable host error; provider exception text is not part of the protocol."""


def _bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


class PipelineBinding:
    """Use the shipped native wheel or an explicit short-lived fixture bundle."""

    def __init__(self, bundle: Path | None = None):
        if bundle is None:
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
            if self.versions != {"binding_version": "1.0.0", "protocol_version": "1.0.0"}:
                raise CandidateHostError("binding_protocol_mismatch")
            return

        bundle = bundle.resolve()
        manifest = json.loads((bundle / "manifest.json").read_bytes())
        library = {"Darwin": "libinku_pipeline_uniffi.dylib", "Linux": "libinku_pipeline_uniffi.so"}.get(platform.system())
        if (
            manifest.get("schema") != "inku.pipeline-python-bundle.v1"
            or manifest.get("platform") != platform.system()
            or manifest.get("machine") != platform.machine()
            or set(manifest.get("files", {})) != {library, "inku_pipeline_uniffi.py"}
        ):
            raise CandidateHostError("binding_bundle_mismatch")
        for name, digest in manifest["files"].items():
            if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != digest:
                raise CandidateHostError("binding_bundle_mismatch")
        spec = importlib.util.spec_from_file_location(
            "inku_pipeline_candidate_" + uuid.uuid4().hex, bundle / "inku_pipeline_uniffi.py"
        )
        if spec is None or spec.loader is None:
            raise CandidateHostError("binding_unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.versions = json.loads(module.version_report())
        if self.versions != {"binding_version": "1.0.0", "protocol_version": "1.0.0"}:
            raise CandidateHostError("binding_protocol_mismatch")
        self.step = module.step
        # Older Step12 bundles remain useful for their existing byte fixtures.
        self.canvas_registry = json.loads(module.canvas_registry()) if hasattr(module, "canvas_registry") else None
        self.resolve_palette = getattr(module, "resolve_palette", None)
        self.render_saved = getattr(module, "render_saved", None)
        self.resolve_macro_catalog = getattr(module, "resolve_macro_catalog", None)


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
                self.context = {**self.context, "description": payload.get("description", "")}
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
                    generated = action["payload"]["reason"] == "stage1_generated"
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
                           "catalog_diagnostics": self.context.get("macro_catalog", {}).get("diagnostics", []),
                           "rendered": self._rendered,
                           "result": self.context.get("result")})
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
        if self.save_snapshot is not None:
            self.save_snapshot(state, next_snapshot, self.context, rendered)
        self._snapshot = next_snapshot
        self._rendered = rendered
        self.last_output = output
        return output
