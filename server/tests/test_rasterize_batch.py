"""Gates for `inku_analysis.rasterize_batch`, the one place a folder gets burned.

It lives here rather than beside the module because `shared/` carries no tests of
its own; `test_rasterizer.py`, which guards the single-file rasterizer under it,
is here for the same reason.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from inku_analysis import rasterize_batch
from inku_analysis.rasterize_batch import rasterize_dir

MODULE = Path(rasterize_batch.__file__)

# Three SVGs, and no two of them share a width: rendering at the width each SVG
# declares and rendering at one width for all of them look the same on a corpus
# that happens to be uniform.
INTRINSIC = {"wide": (400, 200), "narrow": (120, 120), "tall": (200, 500)}

# resvg parses recursively. At this depth the child dies of a stack overflow --
# measured as SIGSEGV on macOS and on the development server alike -- which is
# the panic class [I-075] is about: in-process it takes the interpreter with it.
CRASHING_DEPTH = 60_000


def _svg(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><circle cx="{width // 2}" cy="{height // 2}" '
        f'r="{min(width, height) // 4}" fill="black"/></svg>'
    )


def _corpus(root: Path) -> Path:
    src = root / "svg"
    src.mkdir()
    for name, (width, height) in INTRINSIC.items():
        (src / f"{name}.svg").write_text(_svg(width, height), encoding="utf-8")
    return src


def _png_size(path: Path) -> tuple[int, int]:
    """PNG IHDR carries width and height as big-endian uint32 at byte offset 16."""
    raw = path.read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n"), path
    return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")


def _names(directory: Path) -> list[str]:
    """Everything in the directory, not only what looks like output."""
    return sorted(path.name for path in directory.iterdir())


# T-1
@pytest.mark.parametrize("width", [None, 256], ids=["intrinsic", "at-256"])
def test_every_svg_becomes_a_png_at_the_asked_for_width(tmp_path, width):
    dst = tmp_path / "png"
    report = rasterize_dir(_corpus(tmp_path), dst, width=width)

    assert (report.succeeded, report.failures) == (3, 0), report.failed
    assert _names(dst) == ["narrow.png", "tall.png", "wide.png"]
    for name, (intrinsic_width, intrinsic_height) in INTRINSIC.items():
        expected = (
            (intrinsic_width, intrinsic_height)
            if width is None
            else (width, intrinsic_height * width // intrinsic_width)
        )
        assert _png_size(dst / f"{name}.png") == expected, name


# T-2
def test_a_file_that_cannot_be_burned_leaves_nothing_behind(tmp_path):
    """Not a short PNG, not a 0-byte one, not a half-written temporary file.

    "A failure is absent, not zero" is a rule about how numbers are read, and a
    file on disk breaks it before anybody gets to the reading: an empty PNG is
    counted, sheeted and looked at like any other.
    """
    src = _corpus(tmp_path)
    (src / "broken.svg").write_text("this is not an svg at all", encoding="utf-8")
    dst = tmp_path / "png"

    rasterize_dir(src, dst)

    assert _names(dst) == ["narrow.png", "tall.png", "wide.png"]
    assert all(path.stat().st_size > 0 for path in dst.iterdir())


# T-3
def test_the_failure_is_reported_with_a_reason_and_the_rest_still_burn(tmp_path):
    src = _corpus(tmp_path)
    (src / "broken.svg").write_text("this is not an svg at all", encoding="utf-8")

    report = rasterize_dir(src, tmp_path / "png")

    assert report.attempted == 4
    assert report.succeeded == 3
    assert [failure.source.name for failure in report.failed] == ["broken.svg"]
    # A count without a reason cannot be acted on, and "it failed" is a count.
    assert report.failed[0].reason.strip()


# T-4
def test_a_child_that_dies_hard_costs_one_picture_and_not_the_run(tmp_path):
    """**This test crashes a Python process on purpose, twice, and that is the point.**

    macOS files a crash report for each; nothing is wrong with the machine or with
    pytest. A merely invalid SVG raises and would leave this green on an
    in-process implementation, which is the shape [I-075] says loses a worker and
    everything it was holding to the first bad file.
    """
    src = _corpus(tmp_path)
    crashing = src / "crash.svg"
    crashing.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        + "<g>" * CRASHING_DEPTH
        + '<circle cx="1" cy="1" r="1"/>'
        + "</g>" * CRASHING_DEPTH
        + "</svg>",
        encoding="utf-8",
    )

    # The premise, measured rather than assumed: this input does not raise, it
    # kills the interpreter. Were it only an exception, the gate below would pass
    # on an in-process implementation too and prove nothing about isolation.
    premise = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "from inku_analysis.rasterizer import svg_to_png\n"
            "svg_to_png(open(sys.argv[1], encoding='utf-8').read())\n",
            str(crashing),
        ],
        capture_output=True,
    )
    assert premise.returncode < 0, (
        f"{CRASHING_DEPTH} nested groups no longer kill the interpreter "
        f"(returncode {premise.returncode}); this gate is measuring nothing"
    )

    report = rasterize_dir(src, tmp_path / "png")

    assert report.succeeded == 3
    assert [failure.source.name for failure in report.failed] == ["crash.svg"]
    assert "signal" in report.failed[0].reason, report.failed[0].reason


# T-5
def test_the_batch_module_imports_neither_the_cli_nor_the_server():
    """The container runs this as `python -m` and `cli/` is not in the image.

    Read the import statements, not the file: the module docstring names
    `inku_cli` on purpose, and a check over the whole text would be satisfied by
    that sentence -- green for a reason that has nothing to do with imports.
    """
    imported: set[str] = set()
    for node in ast.walk(ast.parse(MODULE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])

    assert {"inku_cli", "inku_server"}.isdisjoint(imported), sorted(imported)


# T-6
def test_more_workers_do_not_change_the_bytes(tmp_path):
    """Workers buy wall-clock. Anything else they bought would make the eight-fold
    speed-up of burning on the development server a change to the picture."""
    src = _corpus(tmp_path)
    alone = rasterize_dir(src, tmp_path / "one", width=256, workers=1)
    together = rasterize_dir(src, tmp_path / "many", width=256, workers=4)

    assert [path.name for path in alone.written] == [path.name for path in together.written]
    assert alone.failures == together.failures == 0
    for path in alone.written:
        assert path.read_bytes() == (tmp_path / "many" / path.name).read_bytes(), path.name
