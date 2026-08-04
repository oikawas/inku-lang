"""The Android reference fixtures must be what today's tree bakes (F-1..F-3).

`gen_android_reference.py` is run by hand, and nothing watched its output. On
2026-08-04 five of the 53 files had been stale since `4eef595c` (the commit that
moved `thinness` in front of `surface`): that commit regenerated
`score_schema_contract.json` and left `06_surface_hatch.svg`,
`21_hatch_computer.svg`, `renderer_cloudform_and_relations.json`,
`renderer_seed_range.json` and `svg_index.json` behind. The port kept matching
the old expectations, so the divergence it hid -- the Kotlin copy of the dump
order inside `surfaceSeed` still ended `surface, thinness` -- stayed green for
two days.

`test_thinness_declaration_position.py` P-7 already watched the two order tables
in `score_schema_contract.json`, which is exactly the file that commit did
regenerate. Watching one file is not watching the corpus: F-1 rebakes all of it.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from inku_server import renderer

ROOT = pathlib.Path(__file__).resolve().parents[2]

# `android/` is permanently excluded from every pentala sync path (standing rule
# 2026-07-30), so on the deployed server the tree is absent. Key the skip to the
# DIRECTORY: wherever `android/` exists these assertions still run, and a moved
# or renamed fixture is a failure rather than a skip.
ANDROID_TREE = ROOT / "android"
FIXTURES = ANDROID_TREE / "app/src/test/resources/server_reference"
GENERATOR = ROOT / "server/scripts/gen_android_reference.py"

android_only = pytest.mark.skipif(
    not ANDROID_TREE.is_dir(), reason="android/ is absent (pentala)"
)


def _load_generator(out_dir: pathlib.Path):
    """Import the generator as a module and point its output at `out_dir`."""
    spec = importlib.util.spec_from_file_location("gen_android_reference", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = out_dir
    return module


@android_only
def test_every_android_fixture_matches_a_fresh_bake(tmp_path) -> None:
    """F-1 currency: rebaking the whole corpus reproduces every checked-in byte.

    This is a record, not a property -- it says the files on disk are what the
    current tree produces. That is the failure it exists for: a change moves the
    drawing, the fixtures are not rebaked, and the port stays green against an
    expectation the server no longer holds.
    """
    module = _load_generator(tmp_path)
    module.main()

    baked = {path.name for path in tmp_path.iterdir()}
    committed = {path.name for path in FIXTURES.iterdir()}
    assert baked == committed

    stale = sorted(
        name
        for name in sorted(committed)
        if (tmp_path / name).read_bytes() != (FIXTURES / name).read_bytes()
    )
    assert stale == [], (
        f"stale: {stale}"
        " -- rebake with: uv run python scripts/gen_android_reference.py"
    )


@android_only
def test_arrangement_anchors_carry_the_quantum_the_renderer_uses() -> None:
    """F-2 quantum: the fixture is quantised, and says by how much.

    Engine 21 moves two of the 33 cases by 4.9e-10 and nothing else, so a port
    that skips the quantisation is only visible if the expected values really
    carry nine decimals and the comparison is exact.
    """
    fixture = json.loads((FIXTURES / "renderer_arrangement.json").read_text())
    assert fixture["arrangement_quantum"] == renderer.ARRANGEMENT_QUANTUM

    decimals = max(
        len(str(value).partition(".")[2])
        for case in fixture["cases"]
        for anchor in case["anchors"]
        for value in anchor
    )
    assert decimals <= renderer.ARRANGEMENT_QUANTUM
    assert decimals == renderer.ARRANGEMENT_QUANTUM


@android_only
def test_grid_that_states_a_region_is_not_pulled_onto_its_anchor() -> None:
    """F-3 carve-out: engine 20's one exception survives a rebake.

    A grid tiling a stated region keeps `at`, so the second stage would replace
    the region the description gave with the shape's own centre. The sibling
    case without `at` is the contrast: it does move onto the 0.85 anchor.
    """
    fixture = json.loads((FIXTURES / "renderer_arrangement.json").read_text())
    cases = {case["case_id"]: case for case in fixture["cases"]}

    x0, y0, x1, y1 = cases["G-grid-region-edge"]["instruction"]["at"]["region"]
    for x, y in cases["G-grid-region-edge"]["anchors"]:
        assert x0 <= x <= x1 and y0 <= y <= y1

    free = cases["G-grid-edge"]["anchors"]
    assert max(x for x, _ in free) > x1
