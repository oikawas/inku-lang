"""The historical Android fixtures must match their declared owners.

Stage 6 retires the Engine 40 generator with the Python renderer. The Android
engine continues to consume its declared historical corpus until shared Rust
integration replaces that path, so manifests remain the byte authority and a
newer Server must not silently rebake these files.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

# `android/` is permanently excluded from every pentala sync path (standing rule
# 2026-07-30), so on the deployed server the tree is absent. Key the skip to the
# DIRECTORY: wherever `android/` exists these assertions still run, and a moved
# or renamed fixture is a failure rather than a skip.
ANDROID_TREE = ROOT / "android"
FIXTURES = ANDROID_TREE / "app/src/test/resources/server_reference"
ANDROID_COMPATIBILITY = (
    ANDROID_TREE
    / "app/src/main/java/app/inku/mobile/data/model/CompatibilityConstants.kt"
)
ANDROID_REFERENCE_CORPUS = (
    ANDROID_TREE / "app/src/test/java/app/inku/mobile/ReferenceCorpus.kt"
)
ANDROID_RENDERER = (
    ANDROID_TREE / "app/src/main/java/app/inku/mobile/render/DefaultSvgRenderer.kt"
)

android_only = pytest.mark.skipif(
    not ANDROID_TREE.is_dir(), reason="android/ is absent (pentala)"
)

VERSION_DIRECTORY = re.compile(r"^(render-engine|ddl-engine)-(\d+)$")
# The primitives `planning._anchor` answers with a stored coordinate. The rest
# derive theirs by a sum, which carries no quantum. See F-2 (ledger I-165).
QUANTISED_ANCHOR_PRIMITIVES = frozenset(
    {"circle", "ellipse", "arc", "polygon", "cloudform"}
)


def _kotlin_string_constant(path: pathlib.Path, name: str) -> str:
    """Read a version from the Android declaration that owns fixture routing."""
    source = path.read_text(encoding="utf-8")
    match = re.search(rf"\bconst val {re.escape(name)}\s*=\s*\"([^\"]+)\"", source)
    assert match is not None, f"{name} is not declared in {path}"
    return match.group(1)


def _android_render_engine_dir() -> pathlib.Path:
    version = _kotlin_string_constant(ANDROID_COMPATIBILITY, "renderEngineVersion")
    return FIXTURES / f"render-engine-{version}"


def _android_ddl_engine_dir() -> pathlib.Path:
    version = _kotlin_string_constant(ANDROID_REFERENCE_CORPUS, "ddlEngineVersion")
    return FIXTURES / f"ddl-engine-{version}"


def _android_arrangement_quantum() -> int:
    """Derive decimal precision from the Android renderer's quantizer."""
    source = ANDROID_RENDERER.read_text(encoding="utf-8")
    match = re.search(
        r"round\(value \* (1(?:_000)+)\.0\) / \1\.0",
        source,
    )
    assert match is not None, "the Android arrangement quantizer is not recognizable"
    return len(match.group(1).replace("_", "")) - 1


def _fixture_path(name: str) -> pathlib.Path:
    """Resolve a renderer fixture through Android's declared compatibility version."""
    return _android_render_engine_dir() / name


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
    quantum = _android_arrangement_quantum()
    assert fixture["arrangement_quantum"] == quantum

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
    assert decimals <= quantum
    assert decimals == quantum


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
    names = {path.name for path in directories}
    # Android's declared versions must be present; server may be newer by design.
    assert _android_render_engine_dir().name in names
    assert _android_ddl_engine_dir().name in names
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
