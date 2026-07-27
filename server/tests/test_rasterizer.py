import builtins
import re
import tomllib
from pathlib import Path

import pytest

from inku_analysis.rasterizer import (
    BACKEND_RESVG,
    RasterizerUnavailable,
    rasterizer_backend,
    rasterizer_info,
    svg_to_png,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
REPO = Path(__file__).resolve().parents[2]

PLAIN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">'
    '<circle cx="100" cy="100" r="60" fill="black"/>'
    "</svg>"
)

# The same circle behind the material filter the renderer emits for pencil / crayon /
# chalk / brush_thick.
FILTERED_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">'
    "<defs><filter id=\"grain\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\">"
    '<feTurbulence type="fractalNoise" baseFrequency="0.18" numOctaves="2" seed="7" result="noise"/>'
    '<feDisplacementMap in="SourceGraphic" in2="noise" scale="8"/>'
    "</filter></defs>"
    '<circle cx="100" cy="100" r="60" fill="black" filter="url(#grain)"/>'
    "</svg>"
)


def _block_imports(monkeypatch, *names):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in names:
            raise ImportError(f"missing {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_resvg_is_the_backend():
    assert rasterizer_backend() == BACKEND_RESVG


def test_raises_when_resvg_is_absent(monkeypatch):
    """There is no second backend. Without resvg, rasterizing fails loudly.

    It used to fall through to cairosvg, which drops the material filters and
    returns a PNG that looks cleaner than the work is.
    """
    _block_imports(monkeypatch, "resvg_py")
    assert rasterizer_backend() is None
    with pytest.raises(RasterizerUnavailable):
        svg_to_png(PLAIN_SVG, width=64)


def test_installing_cairosvg_does_not_bring_a_fallback_back(monkeypatch):
    """cairosvg being importable in some environment must not make it reachable."""
    pytest.importorskip("cairosvg")
    _block_imports(monkeypatch, "resvg_py")
    with pytest.raises(RasterizerUnavailable):
        svg_to_png(PLAIN_SVG, width=64)


@pytest.mark.parametrize(
    "pyproject",
    ["shared/pyproject.toml", "server/pyproject.toml", "cli/pyproject.toml"],
)
def test_cairosvg_is_not_a_declared_dependency(pyproject):
    data = tomllib.loads((REPO / pyproject).read_text(encoding="utf-8"))
    declared = " ".join(data.get("project", {}).get("dependencies", []))
    assert "cairosvg" not in declared, f"{pyproject} still declares cairosvg"


# Directories that hold no source the repository ships: virtualenvs, dependency
# trees, build output, caches, CLI run artifacts, and `no-git-sync`, the untracked
# working area where past measurement scripts are kept as a record of what was run.
_UNSCANNED_DIRS = frozenset(
    {
        ".git",
        ".gradle",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "bench",
        "build",
        "dist",
        "no-git-sync",
        "node_modules",
        "out",
        "out2",
        "site-packages",
    }
)


def _repo_python_files():
    """Every .py we own, found by exclusion rather than by a list of roots.

    The first version of this named its four roots, which is why `android/scripts`
    kept an `import cairosvg` through v2.7.10: a named list cannot fail to be
    incomplete, it can only fail to say so.
    """
    for path in REPO.rglob("*.py"):
        if _UNSCANNED_DIRS.isdisjoint(path.relative_to(REPO).parts):
            yield path


def test_no_source_file_imports_cairosvg():
    """Prose may name it -- the module docstring explains why it is gone. Code may not."""
    pattern = re.compile(r"^\s*(import\s+cairosvg|from\s+cairosvg\b)", re.M)
    hits = [
        path.relative_to(REPO)
        for path in _repo_python_files()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not hits, f"cairosvg is imported by {hits}"


def test_the_scan_reaches_outside_the_python_packages():
    """The guard above is only worth what it covers.

    `android/scripts/` is the directory the named-roots version missed, so it is
    named here -- not as the scope, but as proof the scope is wider than it was.
    """
    scanned = {path.relative_to(REPO).parts[0] for path in _repo_python_files()}
    assert {"android", "cli", "server", "shared"} <= scanned, scanned


@pytest.mark.parametrize(
    "kwargs, expected_prefix",
    [
        ({}, b"\x00\x00\x01\x90\x00\x00\x00\xc8"),  # intrinsic 400x200
        ({"width": 768}, b"\x00\x00\x03\x00\x00\x00\x01\x80"),  # 768x384, aspect kept
        ({"height": 768}, b"\x00\x00\x06\x00\x00\x00\x03\x00"),  # 1536x768, aspect kept
        ({"width": 768, "height": 384}, b"\x00\x00\x03\x00\x00\x00\x01\x80"),
    ],
)
def test_output_size(kwargs, expected_prefix):
    """PNG IHDR carries width and height as big-endian uint32 at byte offset 16."""
    png = svg_to_png(PLAIN_SVG, **kwargs)
    assert png.startswith(PNG_MAGIC)
    assert png[16:24] == expected_prefix


def test_rasterizer_info_identifies_backend_and_version():
    info = rasterizer_info()
    assert info["backend"] == BACKEND_RESVG
    assert info["version"]


def test_rasterizer_info_is_empty_without_resvg(monkeypatch):
    _block_imports(monkeypatch, "resvg_py")
    assert rasterizer_info() == {}


def test_resvg_renders_the_material_filters():
    """The reason this module exists. A rasterizer that drops feTurbulence /
    feDisplacementMap returns the filtered and unfiltered circles as one image."""
    assert svg_to_png(FILTERED_SVG, width=256) != svg_to_png(PLAIN_SVG, width=256)
