"""Focused integrity checks for the active shared-Rust DDL corpus."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from inku_server.layer_versions import DDL_ENGINE_VERSION, DDL_VERSION


SERVER_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_ddl_reference.py"


def _latest_frozen_manifest() -> Path:
    """The newest shared-Rust DDL record; SPEC §2.1 freezes one only at a checkpoint."""
    frozen = [
        (int(path.parent.name.rsplit("-", 1)[-1]), path)
        for path in (SERVER_ROOT / "reference").glob("ddl-engine-*/manifest.json")
        if path.parent.name.rsplit("-", 1)[-1].isdigit()
        and json.loads(path.read_text(encoding="utf-8")).get("baseline_kind")
        == "shared-rust-pipeline"
    ]
    return max(frozen)[1]


MANIFEST_PATH = _latest_frozen_manifest()


def _generator():
    spec = importlib.util.spec_from_file_location("gen_ddl_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _output(manifest: dict, case_id: str) -> dict:
    path = MANIFEST_PATH.parent / manifest["cases"][case_id]["output_path"]
    return json.loads(path.read_text(encoding="utf-8"))


def test_active_inputs_are_the_three_accepted_meaning_boundaries() -> None:
    cases = _generator().CASE_SPECS
    assert set(cases) == {
        "accepted-macro-mirror",
        "accepted-ordinary-group-cycle",
        "accepted-local-resource-recovery",
    }
    assert cases["accepted-macro-mirror"]["source"] == (
        "Nature.若葉. Place a small diagonal red arc at top. "
        "Place a blue arc at bottom, mirrored with the previous shape."
    )
    assert cases["accepted-ordinary-group-cycle"]["source"] == (
        "赤い円と青い線の組を、灰の弧と交互に5つ並べる。"
    )
    assert cases["accepted-local-resource-recovery"]["source"] == (
        "fill red point. fill a circle diameter 0.5 at horizontal 0.5 "
        "vertical 0.5 with 3 red points. place one blue line at center "
        "connected to the previous shape."
    )
    assert cases["accepted-macro-mirror"]["composition_seed"] == "17"
    assert cases["accepted-ordinary-group-cycle"]["composition_seed"] == "37"
    assert cases["accepted-local-resource-recovery"]["budget"]["maximum"][
        "logical_objects"
    ] == 400


def test_current_manifest_and_outputs_record_the_three_actual_scores() -> None:
    manifest = _manifest()
    assert manifest["corpus_format_version"] == "2"
    assert manifest["baseline_kind"] == "shared-rust-pipeline"
    # The record names its own frozen versions; later engines may move on
    # without a new directory until the next checkpoint.
    assert MANIFEST_PATH.parent.name == f"ddl-engine-{manifest['engine_version']}"
    assert int(manifest["engine_version"]) <= int(DDL_ENGINE_VERSION)
    assert int(manifest["ddl_version"]) <= int(DDL_VERSION)
    assert manifest["binding_version"] == "1.1.0"
    assert manifest["protocol_version"] == "1.0.0"
    assert set(manifest["cases"]) == set(_generator().CASE_SPECS)

    for case in manifest["cases"].values():
        data = (MANIFEST_PATH.parent / case["output_path"]).read_bytes()
        assert len(data) == case["bytes"]
        assert hashlib.sha256(data).hexdigest()[:32] == case["digest"]
        output = json.loads(data)
        assert set(output) == {"document", "delivery"}
        assert set(output["document"]) == {"source", "language", "macro_locks"}
        assert set(output["delivery"]) == {
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
        }

    macro = _output(manifest, "accepted-macro-mirror")
    assert manifest["cases"]["accepted-macro-mirror"]["score_version"] == "0.15.0"
    assert macro["document"]["macro_locks"]
    assert len(macro["delivery"]["score"]["mirror_relations"]) == 1
    assert macro["delivery"]["resource_omissions"] == []
    assert macro["delivery"]["relation_omissions"] == []

    group = _output(manifest, "accepted-ordinary-group-cycle")
    assert manifest["cases"]["accepted-ordinary-group-cycle"]["score_version"] == "0.14.0"
    cycle = group["delivery"]["score"]["placement_groups"][0]["cycle_members"]
    assert cycle["occurrence_count"] == 5
    assert group["delivery"]["resource_omissions"] == []

    recovery = _output(manifest, "accepted-local-resource-recovery")
    assert manifest["cases"]["accepted-local-resource-recovery"]["score_version"] == "0.10.0"
    assert len(recovery["delivery"]["resource_omissions"]) == 1
    assert recovery["delivery"]["resource_omissions"][0]["cause"]["reason"][
        "value"
    ] == {
        "authority": "hard_policy",
        "dimension": "logical_objects",
        "maximum": 400,
        "required": 6945,
    }
    assert len(recovery["delivery"]["score"]["instructions"]) == 2
    assert recovery["delivery"]["score"]["fill_groups"][0]["logical_count"] == 3
    assert recovery["delivery"]["score"]["instructions"][1]["relation"][
        "target_instruction_index"
    ] == 0


def _minimal_manifest(case_digest: str = "digest") -> dict:
    generator = _generator()
    return {
        "corpus_format_version": generator.CORPUS_FORMAT_VERSION,
        "engine_version": "45",
        "ddl_version": "11",
        "binding_version": generator.EXPECTED_BINDING_VERSION,
        "protocol_version": generator.EXPECTED_PROTOCOL_VERSION,
        "cases": {
            "case": {
                "output_path": "pipeline/case.json",
                "digest": case_digest,
            }
        },
    }


def test_same_identity_drift_is_rejected() -> None:
    generator = _generator()
    existing = _minimal_manifest("before")
    candidate = _minimal_manifest("after")
    with pytest.raises(SystemExit, match="without an identity-field change"):
        generator._refuse_same_identity_drift(existing, candidate)
    candidate["engine_version"] = "46"
    generator._refuse_same_identity_drift(existing, candidate)


def test_atomic_publisher_replaces_one_complete_directory(tmp_path: Path) -> None:
    generator = _generator()
    output_dir = tmp_path / "ddl-engine-test"
    first = _minimal_manifest("first")
    first["cases"]["case"].update(bytes=6)
    generator._publish_output_directory(
        first, {"pipeline/case.json": "first\n"}, output_dir=output_dir
    )
    second = _minimal_manifest("second")
    second["cases"]["case"].update(bytes=7)
    generator._publish_output_directory(
        second, {"pipeline/case.json": "second\n"}, output_dir=output_dir
    )
    assert (output_dir / "pipeline/case.json").read_text(encoding="utf-8") == "second\n"
    assert not (tmp_path / ".ddl-engine-test.previous").exists()
    assert not list(tmp_path.glob(".ddl-engine-test.staging-*"))
