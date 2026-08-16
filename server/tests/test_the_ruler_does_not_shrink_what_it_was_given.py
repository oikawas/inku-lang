"""The counting rule measures what it was handed, at the size it was handed.

Burning a picture chooses a width; counting one does not. The tool the
evaluation track names every round halved the image before counting, which
costs thin marks and keeps thick ones -- so a change that thins the marks reads
as no change. These gates hold the new rule to exact numbers on fixed materials
built here, because shrinking has no single direction: on the 255 full-size
rasters of run 851 it moves strong ink by x0.735, and on the twenty-line
material below it moves it the other way, 0.10 to 0.20. An inequality would go
green for the wrong reason whichever way it was written.
"""

import re
import tomllib
from pathlib import Path

import pytest
from PIL import Image

from inku_analysis.raster_metrics import measure_dir, measure_png

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "shared" / "src" / "inku_analysis"

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREY = (128, 128, 128)


def _columns(size: tuple[int, int], ground, mark, xs) -> Image.Image:
    """A ground with one-pixel-wide full-height columns at the given x."""
    img = Image.new("RGB", size, ground)
    for x in xs:
        for y in range(size[1]):
            img.putpixel((x, y), mark)
    return img


def _written(tmp_path: Path, name: str, img: Image.Image) -> Path:
    path = tmp_path / name
    img.save(path)
    return path


# ---------------------------------------------------------------- T-109

def test_the_pixel_count_is_the_size_of_the_file(tmp_path):
    """T-109. The number of pixels counted is the number the file holds.

    Deliberately not square: a rule that returned width squared, or height
    squared, would agree with a square material and disagree with a picture.
    """
    path = _written(tmp_path, "oblong.png", _columns((37, 23), WHITE, BLACK, [3, 11, 29]))
    with Image.open(path) as opened:
        on_disk = opened.width * opened.height
    assert on_disk == 37 * 23
    assert measure_png(path)["pixels"] == on_disk


# ---------------------------------------------------------------- T-110

def test_twenty_black_lines_on_white(tmp_path):
    """T-110. 200x200 white, twenty one-pixel black lines ten pixels apart.

    Exact values, not bounds. Halving this material raises strong ink to 0.20
    (the resampling widens each line to two columns at half the scale, and the
    neighbours are far enough away not to blend), so a `>=` would have passed
    the very defect these gates exist for.
    """
    path = _written(tmp_path, "lines.png", _columns((200, 200), WHITE, BLACK, range(5, 200, 10)))
    metrics = measure_png(path)
    assert metrics["pixels"] == 40000
    assert metrics["strong"] == 0.10000
    assert metrics["faint"] == 0.10000
    assert metrics["mean_distance"] == 25.5


# ---------------------------------------------------------------- T-111

def test_ten_pure_red_columns_on_white(tmp_path):
    """T-111. Pure red is fully saturated, and all of it is coloured ink."""
    path = _written(tmp_path, "red.png", _columns((100, 100), WHITE, RED, range(5, 100, 10)))
    metrics = measure_png(path)
    assert metrics["sat_marks"] == 1.0
    assert metrics["colored_share"] == 1.0
    assert metrics["strong"] == 0.1


# ---------------------------------------------------------------- T-112

def test_ten_grey_columns_on_white(tmp_path):
    """T-112. Mid grey is ink with no colour in it: saturation zero, not absent."""
    path = _written(tmp_path, "grey.png", _columns((100, 100), WHITE, GREY, range(5, 100, 10)))
    metrics = measure_png(path)
    assert metrics["colored_share"] == 0.0
    assert metrics["sat_marks"] == 0.0
    assert metrics["strong"] == 0.1
    assert metrics["mean_distance"] == 12.7


# ---------------------------------------------------------------- T-113

def test_forty_white_columns_on_black(tmp_path):
    """T-113. The ground is the modal colour.

    Not the first pixel -- the top-left of this material is one of the white
    columns -- and not the lightest colour. A work on black paper has white ink,
    and reading the ground off either of those turns its ink into its paper.
    """
    path = _written(tmp_path, "black.png", _columns((100, 100), BLACK, WHITE, range(40)))
    metrics = measure_png(path)
    assert tuple(metrics["ground"]) == (0, 0, 0)
    assert metrics["ground"] == [0, 0, 0]
    assert metrics["ground_light"] == 0.0
    assert metrics["strong"] == 0.4
    assert metrics["mean_distance"] == 102.0


# ---------------------------------------------------------------- T-114

def test_an_unreadable_input_is_named_and_is_not_a_zero(tmp_path):
    """T-114. A file that cannot be read is an absent measurement.

    A zero row gets counted, averaged and plotted; a named failure gets looked
    at. This is what `rasterize_dir` does with a picture it could not burn.
    """
    _written(tmp_path, "good.png", _columns((20, 20), WHITE, BLACK, [4]))
    (tmp_path / "broken.png").write_bytes(b"this is not a PNG")

    report = measure_dir(tmp_path)

    assert set(report["works"]) == {"good"}, "the unreadable file must not become a row"
    assert report["measured"] == 1
    assert [entry["source"] for entry in report["unresolved"]] == [str(tmp_path / "broken.png")]
    assert report["unresolved"][0]["reason"].strip(), "an unresolved entry without a reason is a zero with a name"


# ---------------------------------------------------------------- T-115

def test_pillow_is_a_declared_dependency_of_shared():
    """T-115. The package that opens the PNGs says so in its own manifest.

    It imported cleanly before this line existed, because the server and the CLI
    each declare pillow and this package is installed editable beside them. That
    is the layout being convenient, not a dependency being declared.
    """
    if not (REPO / "shared").is_dir():
        # The development server carries only what the two services need, so a
        # partial checkout is a skip on the directory, not on the manifest: a
        # renamed manifest must stay a red.
        pytest.skip("shared/ is absent from this checkout")
    data = tomllib.loads((REPO / "shared" / "pyproject.toml").read_text(encoding="utf-8"))
    declared = " ".join(data.get("project", {}).get("dependencies", []))
    assert "pillow" in declared, "shared/pyproject.toml does not declare pillow"


# ---------------------------------------------------------------- the scan

def _package_modules() -> list[Path]:
    """Every .py of the analysis package, read off the directory.

    Derived rather than written down. A hand-written list cannot fail to be
    incomplete, it can only fail to say so -- which is how the counting rule
    grew eight copies while every guard stayed green.
    """
    return sorted(path for path in PACKAGE.rglob("*.py") if "__pycache__" not in path.parts)


# ---------------------------------------------------------------- T-116

def test_nothing_in_the_analysis_package_shrinks_an_image():
    """T-116. No module here may resize, thumbnail or reduce.

    Prose may say the word -- the module docstring explains why shrinking is
    wrong. A call may not appear.
    """
    pattern = re.compile(r"\.(resize|thumbnail|reduce)\s*\(")
    hits = [path.relative_to(REPO) for path in _package_modules() if pattern.search(path.read_text(encoding="utf-8"))]
    assert not hits, f"an image is shrunk in {hits}"


# ---------------------------------------------------------------- T-117

def test_nothing_in_the_analysis_package_calls_getdata():
    """T-117. `getdata()` is deprecated in Pillow 12.3 and removed in Pillow 14."""
    pattern = re.compile(r"\.getdata\s*\(")
    hits = [path.relative_to(REPO) for path in _package_modules() if pattern.search(path.read_text(encoding="utf-8"))]
    assert not hits, f"getdata is called in {hits}"


# ---------------------------------------------------------------- T-120

def test_the_scan_reaches_every_module_the_package_holds():
    """T-120. The two guards above are worth exactly what they cover.

    Compared against the directory listing rather than against a written list,
    so a return to named modules shows up as a module the scan no longer reaches
    -- on whichever checkout it is run, and for a module added after this test
    was written.
    """
    scanned = {path.resolve() for path in _package_modules()}
    # Read a second way, so the check is not the scan agreeing with itself.
    holding = {entry.resolve() for entry in PACKAGE.iterdir() if entry.suffix == ".py"}
    assert holding, "the package holds no .py at all -- the path is wrong, not the scan"
    assert holding <= scanned, holding - scanned
