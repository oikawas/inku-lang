"""Short-lived acceptance host for the shared Rust authoring pipeline.

Never imported by the ordinary API/router. Configuration, bundle location and
owner identity come from a trusted harness. Clients cannot submit snapshots,
authority sidecars, effect results or resource policies through this module.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from .persistence.variation_authority import VariationAuthorityStore


class CandidateHostError(ValueError):
    """A stable host error; provider exception text is not part of the protocol."""


def _bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


class PipelineBinding:
    """Load one explicitly selected, platform-specific generated binding bundle."""

    def __init__(self, bundle: Path):
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


class CandidateExecution:
    """One serialized, host-owned execution, isolated from legacy history.

    The provider callback performs exactly one transport attempt and returns an
    EffectResult. Only Rust selects retries, completion and fallback. The caller
    owns saving the returned bytes/transcript for a comparison run; this class is
    not a persistent product session service.
    """

    def __init__(
        self, binding: PipelineBinding, store: VariationAuthorityStore, *,
        owner_id: str, config: dict, provider: Callable[[dict], dict],
        allow_render: bool = False,
    ):
        self.binding, self.store, self.owner_id = binding, store, owner_id
        self.config = json.loads(_bytes(config))
        self.provider = provider
        self.allow_render = allow_render
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

    def command(self, payload: dict) -> dict:
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
            return self._advance(payload)

    def run_effect(self) -> dict | None:
        """Execute the current effect once. No effect means author input is next."""
        with self._lock:
            if self._snapshot is None or self._snapshot["action"] is None:
                return None
            if self._provider_in_flight:
                raise CandidateHostError("provider_effect_in_flight")
            action = json.loads(_bytes(self._snapshot["action"]))
            if action["tag"] == "commit_visible_normalized_ddl":
                result = self.store.commit_effect(
                    self.owner_id, action, create_if_missing=self._fresh
                )
                if result["tag"] == "visible_normalized_ddl_committed":
                    self._fresh = False
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
            return json.loads(_bytes({key: state[key] for key in (
                "execution_id", "variation_id", "sequence", "authority", "document", "phase", "delivery"
            )}))

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
        self._snapshot = output["payload"]["result"]["snapshot"]
        self.last_output = output
        return output
