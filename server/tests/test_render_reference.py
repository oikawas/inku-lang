"""Structural checks for the frozen render-engine reference corpus."""

from __future__ import annotations

import importlib.util
import json
import pathlib

from inku_server.schema import CanvasGroundSpec, Instruction, Score, SurfaceSpec

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"
MANIFEST_PATH = SERVER_ROOT / "reference" / "render-engine-10" / "manifest.json"


def _generator():
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_render_reference_case_counts() -> None:
    cases = _manifest()["cases"]
    assert len(cases) == 220
    assert {
        prefix: sum(case_id.startswith(f"{prefix}-") for case_id in cases)
        for prefix in ("A", "B", "C", "D")
    } == {"A": 80, "B": 72, "C": 40, "D": 28}


def test_render_reference_inputs_are_fully_explicit() -> None:
    generator = _generator()
    instruction_fields = set(generator.BASE_INSTRUCTION)
    score_fields = set(generator.BASE_SCORE)
    assert instruction_fields == {
        field.alias or name for name, field in Instruction.model_fields.items()
    }
    assert score_fields == set(Score.model_fields)
    assert set(generator.BASE_SURFACE) == set(SurfaceSpec.model_fields)
    assert set(generator.BASE_GROUND) == set(CanvasGroundSpec.model_fields)
    for case in generator.build_inputs().values():
        score = case["score"]
        assert set(score) == score_fields
        assert set(score["instructions"][0]) == instruction_fields
        assert set(case["color_map"]) == set(generator.DEFAULT_COLOR_MAP)
        assert case["svg_profile"] == "editable"
        assert isinstance(case["render_seed"], int)


def test_render_reference_discriminator_cases() -> None:
    cases = _manifest()["cases"]
    square = cases["D-canvas-square-arc-brush-thick"]
    pillar = cases["D-canvas-pillar-arc-brush-thick"]
    assert square["digest"] != pillar["digest"]

    ordinary = cases["D-seed-12345"]
    for seed in (2**63 + 1, 2**64 - 1):
        high = cases[f"D-unsigned-seed-{seed}"]
        assert high["input"]["render_seed"] > 2**63
        assert high["digest"] != ordinary["digest"]

    tiny = cases["D-size-tiny-filled-circle"]
    assert not any("fill-stroke-v1" in name for name in tiny["classes"])


def test_render_reference_svg_files_match_manifest() -> None:
    manifest = _manifest()
    output_dir = MANIFEST_PATH.parent
    generator = _generator()
    for case_id, case in manifest["cases"].items():
        svg = (output_dir / f"{case_id}.svg").read_text(encoding="utf-8")
        assert len(svg.encode("utf-8")) == case["bytes"]
        assert generator._normalized_digest(svg) == case["digest"]
