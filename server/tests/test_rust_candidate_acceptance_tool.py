"""Focused offline checks for the temporary Engine 41 acceptance tool."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SERVER_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = SERVER_ROOT / "scripts" / "run_rust_candidate_acceptance.py"


def _tool():
    spec = importlib.util.spec_from_file_location("rust_candidate_acceptance", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_signature_normalizes_serializer_number_spelling() -> None:
    tool = _tool()
    left = '<svg width="1000.0" height="1000" viewBox="0 0 1000 1000"><path d="M 1.0 2.000 L 3 4"/></svg>'
    right = '<svg width="1000" height="1000.000000" viewBox="0.0 0 1000.0 1000"><path d="M 1 2 L 3.000000 4"/></svg>'

    assert tool._signature(left) == tool._signature(right)


def test_signature_does_not_read_hex_colours_as_exponents() -> None:
    tool = _tool()
    svg = '<svg width="1000" height="1000"><path d="M 0 0" fill="#4e8372"/></svg>'

    visual, _structure = tool._signature(svg)

    assert visual["drawing_families"] == {"path": 1}


def test_internal_reference_check_reports_only_missing_targets() -> None:
    tool = _tool()
    root = tool._parse_svg(
        '<svg><defs><filter id="present"/></defs><path filter="url(#present)"/>'
        '<path filter="url(#missing)"/></svg>'
    )

    assert tool._internal_reference_errors(root) == ["missing"]


def test_metadata_meaning_normalizes_absent_optional_values() -> None:
    tool = _tool()
    sparse = {
        "render_engine_id": "default",
        "render_engine_version": "40",
        "render_texture_version": "1",
        "render_texture_profile": "display",
        "texture_degraded": False,
    }
    explicit = {
        **sparse,
        "render_engine_version": "41",
        "render_canvas_ground": {"material": "paper", "seed": None},
        "render_surface_textures": [],
    }

    expected = tool._metadata_meaning(sparse)
    expected["render_canvas_ground"] = {"material": "paper"}
    assert expected == tool._metadata_meaning(explicit)


def test_non_finite_svg_is_rejected() -> None:
    tool = _tool()

    with pytest.raises(tool.CandidateValidationError, match="NaN or Inf"):
        tool._parse_svg('<svg><path d="M NaN 0"/></svg>')
