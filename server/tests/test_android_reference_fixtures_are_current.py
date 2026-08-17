"""The Android reference fixtures must be what today's tree bakes (F-1..F-4).

The corpus is filed by the engine version that governs it, so "today's tree"
means the current version directory plus the five fixtures no engine governs.
Older versions are not rebaked -- an engine 22 tree cannot produce engine 21's
expectations -- so F-4 holds them by manifest instead. Rebaking them is exactly
the failure this layout exists to prevent: it rewrites expectations the port
still holds, and turned 7 of 159 JVM tests red when engine 22 merged.

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
regenerate. Watching one file is not watching the corpus: F-1 rebakes the whole
current version of it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import sys

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

# F-1 rebakes and compares bytes, so it can only be asked on the platform the
# fixture was baked on. `renderer_variation_primitives.json` stores raw doubles
# -- wave phases and hash01 values that reach sin/cos -- and macOS libm and glibc
# disagree there by one ULP: six values, the last digit, e.g.
# -1.7282983464997077 on darwin against -1.7282983464997073 on glibc 2.41
# (measured 2026-08-17 in the pentala test container). The port compares those
# fields with a 1e-9 tolerance, so the difference reaches nothing it asserts;
# only a byte comparison sees it.
#
# The release runs linux (the GHCR images), so linux is where the fixture is
# baked and where this record is kept. On darwin the rebake is not a fair
# comparison and this test says so instead of failing. The cost is stated
# plainly: a fixture staled on a Mac is caught by the container run, not by the
# Mac. See `no-git-sync/scripts/testbox.sh --corpora`.
FROZEN_BAKE_PLATFORM = "linux"

baked_here_only = pytest.mark.skipif(
    sys.platform != FROZEN_BAKE_PLATFORM,
    reason=(
        f"the fixture is baked on {FROZEN_BAKE_PLATFORM} (the platform the release"
        f" runs on) and this is {sys.platform}; rebake and check it with"
        " no-git-sync/scripts/testbox.sh --sync --corpora"
    ),
)


VERSION_DIRECTORY = re.compile(r"^(render-engine|ddl-engine)-(\d+)$")
# The primitives `renderer._anchor` answers with a stored coordinate. The rest
# derive theirs by a sum, which carries no quantum. See F-2 (ledger I-165).
QUANTISED_ANCHOR_PRIMITIVES = frozenset(
    {"circle", "ellipse", "arc", "polygon", "cloudform"}
)


def _load_generator(out_dir: pathlib.Path):
    """Import the generator as a module and point its output at `out_dir`."""
    spec = importlib.util.spec_from_file_location("gen_android_reference", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = out_dir
    return module


def _fixture_path(name: str) -> pathlib.Path:
    """Resolve a fixture the way the generator files it, rather than guessing."""
    return _load_generator(FIXTURES).out_path(name)


def _files_under(root: pathlib.Path, subdirectories: set[str]) -> set[str]:
    """Paths the generator writes: the flat fixtures plus the given directories."""
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and (path.parent == root or path.parent.name in subdirectories)
    }


@android_only
@baked_here_only
def test_every_android_fixture_matches_a_fresh_bake(tmp_path) -> None:
    """F-1 currency: rebaking the current version reproduces every checked-in byte.

    This is a record, not a property -- it says the files on disk are what the
    current tree produces. That is the failure it exists for: a change moves the
    drawing, the fixtures are not rebaked, and the port stays green against an
    expectation the server no longer holds.

    It reaches only what the generator writes. Older version directories are held
    by F-4, because this tree cannot bake them at all.
    """
    module = _load_generator(tmp_path)
    module.main()

    current = {module.render_engine_dir().name, module.ddl_engine_dir().name}
    baked = _files_under(tmp_path, current)
    committed = _files_under(FIXTURES, current)
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

    Asked of the primitives whose anchor IS a stored coordinate. `_anchor`
    returns the saved `center` for those, and for `square`/`triangle` it returns
    `position + size/2` and for `line` the midpoint of the ends -- sums, which
    the quantum does not survive even though every term carries it. Sixteen
    decimals there is the rule working, not a port skipping it, and the values
    themselves are still held: the fixture says "compare exactly, no tolerance"
    and the port does. Until the corpus grew a group that was not a circle the
    claim happened to be true of all of it. Ledger I-165, author ruling A,
    2026-08-09.
    """
    fixture = json.loads(_fixture_path("renderer_arrangement.json").read_text())
    assert fixture["arrangement_quantum"] == renderer.ARRANGEMENT_QUANTUM

    stored = [
        case
        for case in fixture["cases"]
        if case["instruction"]["primitive"] in QUANTISED_ANCHOR_PRIMITIVES
    ]
    # A narrowed population is a gate only while something is left in it: a
    # rename on either side would empty this and turn the claim vacuous.
    assert stored, "no case carries a stored anchor; the quantum is unmeasured"

    decimals = max(
        len(str(value).partition(".")[2])
        for case in stored
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
    fixture = json.loads(_fixture_path("renderer_arrangement.json").read_text())
    cases = {case["case_id"]: case for case in fixture["cases"]}

    x0, y0, x1, y1 = cases["G-grid-region-edge"]["instruction"]["at"]["region"]
    for x, y in cases["G-grid-region-edge"]["anchors"]:
        assert x0 <= x <= x1 and y0 <= y <= y1

    free = cases["G-grid-edge"]["anchors"]
    assert max(x for x, _ in free) > x1


@android_only
def test_every_version_directory_matches_its_manifest() -> None:
    """F-4 holding: an older version is guarded by its manifest, not by a rebake.

    F-1 cannot see these directories -- an engine 22 tree has no way to produce
    engine 21's SVGs, which is the whole reason they are kept rather than baked.
    Without this, the corpus the port actually reads would be the one file set in
    the repository nothing checks at all.
    """
    directories = sorted(
        path
        for path in FIXTURES.iterdir()
        if path.is_dir() and VERSION_DIRECTORY.match(path.name)
    )
    module = _load_generator(FIXTURES)
    names = {path.name for path in directories}
    # The current versions must be among them; the older ones are why this exists.
    assert module.render_engine_dir().name in names
    assert module.ddl_engine_dir().name in names
    assert len(names) > 2, f"only the current versions are filed: {sorted(names)}"

    for directory in directories:
        layer, version = VERSION_DIRECTORY.match(directory.name).groups()
        manifest = json.loads((directory / "manifest.json").read_text())
        assert manifest["layer"] == layer
        assert manifest["version"] == version

        on_disk = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.iterdir())
            if path.is_file() and path.name != "manifest.json"
        }
        assert on_disk == manifest["files"], f"{directory.name} drifted from its manifest"
