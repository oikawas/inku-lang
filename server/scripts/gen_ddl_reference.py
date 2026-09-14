"""Generate the shared-Rust DDL reference corpus.

The three fixed sources are accepted product boundaries, not a coverage matrix.
Each starts as visible DDL and reaches a Score through the shipped
``inku_render.pipeline_step`` byte protocol. Historical expander, coerce, and
document-plugin corpora remain in their existing engine directories.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from typing import Any

from inku_server.layer_versions import DDL_ENGINE_VERSION, DDL_VERSION


REFERENCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "reference"
OUTPUT_DIR = REFERENCE_ROOT / f"ddl-engine-{DDL_ENGINE_VERSION}"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

CORPUS_FORMAT_VERSION = "2"
EXPECTED_BINDING_VERSION = "1.1.0"
EXPECTED_PROTOCOL_VERSION = "1.0.0"
FROZEN_AT = "2026-09-14"
REASON = (
    "DDL engine 45 makes the shared Rust authoring pipeline the active compiler "
    "for visible DDL. Three accepted inputs freeze the bundled Nature Macro and "
    "mirroring, an ordinary finite member cycle, and local resource recovery. "
    "DDL engines 1 through 26 remain unchanged historical records of the retired "
    "expander, coerce, and document-plugin layers."
)

IDENTITY_FIELDS = (
    "corpus_format_version",
    "engine_version",
    "ddl_version",
    "binding_version",
    "protocol_version",
)

CANVAS_REGISTRY_ID = "inku.canvas-format-registry.v1"
CANVAS_REGISTRY_DIGEST = (
    "16fde66009a901ec65887303389a0253235467cb0437ab38084ff15ea4f8ae18"
)

DEFAULT_COLOR_MAP = {
    "white": "#ffffff",
    "black": "#111111",
    "blue": "#2c3e91",
    "red": "#a2342a",
    "green": "#2f6b3a",
    "gray": "#888888",
    "yellow": "#b8901f",
    "orange": "#b9671e",
    "purple": "#6a4d94",
}

SHIPPING_BUDGET = {
    "maximum": {
        "logical_objects": 4096,
        "primitive_marks": 400,
        "object_templates": 64,
        "maximum_per_template_primitive_marks": 240,
        "maximum_resolved_count": 2000,
        "template_nodes": 128,
        "anchor_instances": 4096,
        "transform_instances": 4096,
        "placement_instances": 64,
        "fill_instances": 64,
    }
}

RECOVERY_BUDGET = {
    "maximum": {
        "logical_objects": 400,
        "primitive_marks": 400,
        "object_templates": 64,
        "maximum_per_template_primitive_marks": 240,
        "maximum_resolved_count": 2000,
        "template_nodes": 512,
        "anchor_instances": 400,
        "transform_instances": 400,
        "placement_instances": 400,
        "fill_instances": 400,
    }
}

NATURE_NAMES = (
    "Nature.若葉",
    "Nature.下草",
    "Nature.青葉",
    "Nature.紅葉",
    "Nature.落葉",
    "Nature.枯草",
    "Nature.枯葉",
)

CASE_SPECS: dict[str, dict[str, Any]] = {
    "accepted-macro-mirror": {
        "source": (
            "Nature.若葉. Place a small diagonal red arc at top. "
            "Place a blue arc at bottom, mirrored with the previous shape."
        ),
        "language": "en",
        "canvas_format_id": "square",
        "composition_seed": "17",
        "render_seed": "77",
        "budget": SHIPPING_BUDGET,
        "policy_identity": "host-settings",
        "macro_limits": (64, 16, 8192, 128, 128),
        "prompt_limits": (64, 8192, 1_048_576, 400_000, 1_048_576),
        "retry": (4, "120000", "120000", "2000"),
        "envelope_limits": (16 * 1024 * 1024, 32 * 1024 * 1024, 64 * 1024 * 1024),
        "nature": True,
    },
    "accepted-ordinary-group-cycle": {
        "source": "赤い円と青い線の組を、灰の弧と交互に5つ並べる。",
        "language": "ja",
        "canvas_format_id": "wide",
        "composition_seed": "37",
        "render_seed": "77",
        "budget": SHIPPING_BUDGET,
        "policy_identity": "installation-default.v1",
        "macro_limits": (64, 16, 8192, 128, 128),
        "prompt_limits": (64, 8192, 1_048_576, 400_000, 1_048_576),
        "retry": (4, "120000", "120000", "2000"),
        "envelope_limits": (16 * 1024 * 1024, 32 * 1024 * 1024, 64 * 1024 * 1024),
        "nature": False,
    },
    "accepted-local-resource-recovery": {
        "source": (
            "fill red point. fill a circle diameter 0.5 at horizontal 0.5 "
            "vertical 0.5 with 3 red points. place one blue line at center "
            "connected to the previous shape."
        ),
        "language": "en",
        "canvas_format_id": "square",
        "composition_seed": "17",
        "render_seed": "666010",
        "budget": RECOVERY_BUDGET,
        "policy_identity": "host-settings",
        "macro_limits": (16, 16, 1000, 100, 500),
        "prompt_limits": (16, 1024, 32768, 8192, 16384),
        "retry": (2, "1000", "3000", "10"),
        "envelope_limits": (1_000_000, 1_000_000, 2_000_000),
        "nature": False,
    },
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_output(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2
    ) + "\n"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _native_binding() -> tuple[Any, dict[str, str]]:
    native = importlib.import_module("inku_render")
    try:
        versions = json.loads(native.pipeline_version_report())
        required = (
            native.pipeline_step,
            native.pipeline_resolve_palette,
            native.pipeline_resolve_macro_catalog,
        )
    except (AttributeError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("shared pipeline binding is unavailable") from error
    if required and versions != {
        "binding_version": EXPECTED_BINDING_VERSION,
        "protocol_version": EXPECTED_PROTOCOL_VERSION,
    }:
        raise RuntimeError(f"unexpected shared pipeline binding identity: {versions}")
    return native, versions


def _palette(native: Any, render_seed: str) -> dict[str, Any]:
    payload = {
        "color_map": DEFAULT_COLOR_MAP,
        "catalog_id": "default",
        "render_seed": render_seed,
        "background": "white",
    }
    result = json.loads(native.pipeline_resolve_palette(_canonical_bytes(payload)))
    if not isinstance(result, dict) or "error" in result:
        raise RuntimeError(f"native palette resolution failed: {result}")
    return result


def _nature_catalog(native: Any, language: str) -> tuple[list[dict], list[str]]:
    payload = {
        "maximum_entries": 64,
        "canonical": [],
        "legacy": [
            {"source_id": "bundled:Nature.leaves", "qualified_name": name}
            for name in NATURE_NAMES
        ],
        "bundled_packages": ["Nature.leaves"],
        "language": language,
    }
    result = json.loads(native.pipeline_resolve_macro_catalog(_canonical_bytes(payload)))
    if (
        not isinstance(result, dict)
        or result.get("schema") != "inku.macro-catalog-resolution.v1"
        or result.get("diagnostics") != []
        or len(result.get("entries", [])) != len(NATURE_NAMES)
    ):
        raise RuntimeError(f"bundled Nature catalog did not resolve exactly: {result}")
    return (
        [entry["definition"] for entry in result["entries"]],
        [entry["summary"] for entry in result["entries"]],
    )


def _host_policy_identity(budget: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_bytes(budget)).hexdigest()
    return f"host-settings:{digest}"


def _config(native: Any, spec: dict[str, Any]) -> dict[str, Any]:
    budget = copy.deepcopy(spec["budget"])
    identity = spec["policy_identity"]
    if identity == "host-settings":
        identity = _host_policy_identity(budget)
    max_invocations, max_depth, max_steps, max_nodes, max_total = spec[
        "macro_limits"
    ]
    max_entries, max_summary, max_catalog, max_source, max_response = spec[
        "prompt_limits"
    ]
    attempts, attempt_timeout, total_timeout, delay = spec["retry"]
    max_input, max_snapshot, max_output = spec["envelope_limits"]
    retry = {
        "max_attempts": attempts,
        "attempt_timeout_ms": attempt_timeout,
        "total_timeout_ms": total_timeout,
        "retry_delay_ms": delay,
    }
    definitions: list[dict] = []
    summaries: list[str] = []
    if spec["nature"]:
        definitions, summaries = _nature_catalog(native, spec["language"])
    return {
        "envelope_limits": {
            "max_input_bytes": max_input,
            "max_snapshot_bytes": max_snapshot,
            "max_output_bytes": max_output,
        },
        "language": spec["language"],
        "compiler": {
            "host": {
                "canvas_format_id": spec["canvas_format_id"],
                "canvas_format_registry_id": CANVAS_REGISTRY_ID,
                "canvas_format_registry_digest": CANVAS_REGISTRY_DIGEST,
                "resolved_catalog_id": "default",
                "catalog_mode": "default",
                "background": "white",
                "palette": _palette(native, spec["render_seed"]),
            },
            "composition_seed": spec["composition_seed"],
            "macro_expansion_limits": {
                "max_invocations": str(max_invocations),
                "max_depth": str(max_depth),
                "max_evaluation_steps": str(max_steps),
                "max_nodes_per_invocation": str(max_nodes),
                "max_total_nodes": str(max_total),
            },
            "stage15_variation": None,
            "error_policy": "omit_and_continue",
            "hard_resource_policy": {"identity": identity, "budget": budget},
            "operational_resource_budget": copy.deepcopy(budget),
        },
        "definitions": definitions,
        "macro_summaries": summaries,
        "catalogs": [],
        "prompt_limits": {
            "max_catalog_entries": max_entries,
            "max_summary_bytes": max_summary,
            "max_catalog_serialized_bytes": max_catalog,
            "max_source_bytes": max_source,
            "max_response_bytes": max_response,
        },
        "catalog_retry": copy.deepcopy(retry),
        "stage1_retry": copy.deepcopy(retry),
        "hole_retry": copy.deepcopy(retry),
    }


def build_inputs(native: Any) -> dict[str, dict[str, Any]]:
    return {
        case_id: {
            "source": spec["source"],
            "config": _config(native, spec),
        }
        for case_id, spec in CASE_SPECS.items()
    }


def _step(
    native: Any,
    snapshot: dict[str, Any] | None,
    payload: dict[str, Any],
    *,
    message_id: str,
) -> dict[str, Any]:
    sequence = "0" if snapshot is None else str(int(snapshot["sequence"]) + 1)
    envelope = {
        "protocol": "inku.pipeline",
        "version": EXPECTED_PROTOCOL_VERSION,
        "kind": "input",
        "execution_id": "new" if snapshot is None else snapshot["execution_id"],
        "sequence": sequence,
        "message_id": message_id,
        "payload": {**payload, "version": 1},
    }
    snapshot_bytes = b"" if snapshot is None else _canonical_bytes(snapshot)
    output = json.loads(native.pipeline_step(snapshot_bytes, _canonical_bytes(envelope)))
    if output.get("kind") != "output":
        raise RuntimeError(f"shared pipeline step failed: {output}")
    return output["payload"]["result"]["snapshot"]


def _compile_visible_ddl(
    native: Any, case_id: str, input_data: dict[str, Any]
) -> dict[str, Any]:
    identity = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
    snapshot = _step(
        native,
        None,
        {
            "tag": "start",
            "variation_id": identity[:32],
            "authoring_nonce": identity[32:],
            "config": input_data["config"],
            "authority": {
                "protocol_version": "inku.variation-authority.v1",
                "revision": "0",
                "origin": "user_authored_ddl",
                "authority": "ddl_authoritative",
            },
            "authoring": {"tag": "direct_ddl", "source": input_data["source"]},
        },
        message_id=identity,
    )
    action = snapshot.get("action")
    if not isinstance(action, dict) or action.get("tag") != "commit_visible_normalized_ddl":
        raise RuntimeError(
            f"visible DDL did not request a host commit: {snapshot.get('phase')}"
        )
    payload = action["payload"]
    snapshot = _step(
        native,
        snapshot,
        {
            "tag": "effect_result",
            "result": {
                "tag": "visible_normalized_ddl_committed",
                "identity": action["identity"],
                "ddl_digest": payload["ddl_digest"],
                "revision": payload["authority"]["next_state"]["revision"],
                "authority_digest": payload["authority_digest"],
            },
        },
        message_id=identity[::-1],
    )
    if snapshot.get("phase", {}).get("tag") != "score_ready":
        raise RuntimeError(f"visible DDL did not reach Score: {snapshot.get('phase')}")
    delivery = snapshot["delivery"]
    return {
        "document": {
            "source": snapshot["document"]["source"],
            "language": snapshot["document"]["language"],
            "macro_locks": snapshot["document"]["macro_locks"],
        },
        "delivery": {
            key: delivery[key]
            for key in (
                "schema_id",
                "outcome",
                "compiler_lock",
                "compiler_lock_digest",
                "score",
                "score_digest",
                "upstream_diagnostics",
                "downstream_diagnostics",
                "resource_omissions",
                "relation_omissions",
            )
        },
    }


def _render_cases(
    native: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    manifest_cases: dict[str, dict[str, Any]] = {}
    outputs: dict[str, str] = {}
    for case_id, input_data in sorted(build_inputs(native).items()):
        result = _compile_visible_ddl(native, case_id, input_data)
        text = _canonical_output(result)
        path = f"pipeline/{case_id}.json"
        outputs[path] = text
        delivery = result["delivery"]
        manifest_cases[case_id] = {
            "part": "pipeline",
            "input": input_data,
            "output_path": path,
            "digest": _digest(text),
            "bytes": len(text.encode("utf-8")),
            "score_version": delivery["score"]["version"],
            "outcome": delivery["outcome"],
            "upstream_diagnostic_count": len(delivery["upstream_diagnostics"]),
            "downstream_diagnostic_count": len(delivery["downstream_diagnostics"]),
            "resource_omission_count": len(delivery["resource_omissions"]),
            "relation_omission_count": len(delivery["relation_omissions"]),
        }
    return manifest_cases, outputs


def _source_commit() -> str:
    archive_commit = os.environ.get("INKU_SOURCE_COMMIT")
    if archive_commit is not None:
        if len(archive_commit) != 40 or any(
            character not in "0123456789abcdef" for character in archive_commit
        ):
            raise ValueError("INKU_SOURCE_COMMIT must be a full lowercase Git commit SHA")
        return archive_commit
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REFERENCE_ROOT.parent.parent,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _previous_manifest() -> dict[str, Any] | None:
    current = int(DDL_ENGINE_VERSION)
    candidates: list[tuple[int, pathlib.Path]] = []
    for path in REFERENCE_ROOT.glob("ddl-engine-*/manifest.json"):
        suffix = path.parent.name.rsplit("-", 1)[-1]
        if suffix.isdigit() and int(suffix) < current:
            candidates.append((int(suffix), path))
    if not candidates:
        return None
    return json.loads(max(candidates)[1].read_text(encoding="utf-8"))


_REQUIRED_PARTS = ("pipeline",)


def _manifest_output_paths(manifest: dict[str, Any]) -> set[str]:
    return {str(case["output_path"]) for case in manifest["cases"].values()}


def _is_complete_output_directory(output_dir: pathlib.Path) -> bool:
    manifest_path = output_dir / "manifest.json"
    if not output_dir.is_dir() or not manifest_path.is_file():
        return False
    if any(not (output_dir / part).is_dir() for part in _REQUIRED_PARTS):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        paths = _manifest_output_paths(manifest)
    except (KeyError, TypeError, json.JSONDecodeError, OSError):
        return False
    return all((output_dir / path).is_file() for path in paths)


def _write_output_directory(
    output_dir: pathlib.Path,
    manifest: dict[str, Any],
    outputs: dict[str, str],
) -> None:
    expected = _manifest_output_paths(manifest)
    if set(outputs) != expected:
        raise ValueError("DDL manifest output paths do not match generated outputs")
    output_dir.mkdir()
    for part in _REQUIRED_PARTS:
        (output_dir / part).mkdir()
    for path, body in outputs.items():
        (output_dir / path).write_text(body, encoding="utf-8")
    (output_dir / "manifest.json").write_text(
        _canonical_output(manifest), encoding="utf-8"
    )


def _publish_output_directory(
    manifest: dict[str, Any],
    outputs: dict[str, str],
    *,
    output_dir: pathlib.Path,
) -> None:
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    backup = parent / f".{output_dir.name}.previous"
    if backup.exists():
        if output_dir.exists():
            if not _is_complete_output_directory(output_dir) or not backup.is_dir():
                raise SystemExit(
                    "cannot reconcile incomplete DDL corpus and fixed backup"
                )
            shutil.rmtree(backup)
        else:
            if not _is_complete_output_directory(backup):
                raise SystemExit("cannot restore incomplete DDL corpus backup")
            backup.rename(output_dir)
    if output_dir.exists() and not _is_complete_output_directory(output_dir):
        raise SystemExit("refusing to replace an incomplete DDL corpus")
    staging = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=parent)
    )
    try:
        staging.rmdir()
        _write_output_directory(staging, manifest, outputs)
        if not output_dir.exists():
            staging.rename(output_dir)
            return
        output_dir.rename(backup)
        try:
            staging.rename(output_dir)
        except BaseException:
            backup.rename(output_dir)
            raise
        shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def generate() -> None:
    native, versions = _native_binding()
    existing = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if MANIFEST_PATH.exists()
        else None
    )
    cases, outputs = _render_cases(native)
    identity = {
        "corpus_format_version": CORPUS_FORMAT_VERSION,
        "layer": "ddl-engine",
        "baseline_kind": "shared-rust-pipeline",
        "engine_version": DDL_ENGINE_VERSION,
        "ddl_version": DDL_VERSION,
        "binding_version": versions["binding_version"],
        "protocol_version": versions["protocol_version"],
    }
    if existing is None:
        previous = _previous_manifest()
        before = {} if previous is None else previous.get("cases", {})
        changed = sorted(
            case_id
            for case_id, case in cases.items()
            if case_id not in before or before[case_id].get("digest") != case["digest"]
        )
        frozen = {
            "frozen_at": FROZEN_AT,
            "commit": _source_commit(),
            "reason": REASON,
            "changed_from_previous": changed,
        }
    else:
        frozen = {
            key: existing[key]
            for key in ("frozen_at", "commit", "reason", "changed_from_previous")
        }
    manifest = {**identity, **frozen, "cases": cases}
    _refuse_same_identity_drift(existing, manifest)
    _publish_output_directory(manifest, outputs, output_dir=OUTPUT_DIR)


def _refuse_same_identity_drift(
    existing: dict[str, Any] | None, manifest: dict[str, Any]
) -> None:
    if existing is None or existing.get("cases") == manifest["cases"]:
        return
    before_identity = tuple(existing.get(field) for field in IDENTITY_FIELDS)
    after_identity = tuple(manifest.get(field) for field in IDENTITY_FIELDS)
    if before_identity == after_identity:
        raise SystemExit(
            "DDL corpus changed without an identity-field change; bump the "
            "appropriate version instead of rewriting a frozen corpus"
        )


if __name__ == "__main__":
    generate()
