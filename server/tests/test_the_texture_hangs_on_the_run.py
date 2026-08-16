"""The texture filter hangs on the run of marks, not on every mark (T-129..T-138).

One work in production held 24,446 filter references: 24,445 of them were the
crayon's texture, written on every element, and one was the performance touch,
hung once on the content group. The touch already had the shape this change
gives the texture -- one filter over the stretch it covers.

**Where the fold happens is the whole design.** A reference-count threshold that
pays at both production widths was measured first and does not exist: at 2160px
folding lost at every count from 34 to 26,675 and got worse as the count rose,
because a run's box is the union of the boxes it replaces. What decides is the
width being rasterized, so the fold sits at bake time and the stored drawing
never moves. The measurements are in `inku_analysis.texture_fold`'s docstring.

The tests read, in order: what must not move (the order of the marks, then the
stored drawing), what the fold does (the three boundaries it keeps), what
decides that it runs at all (the width), and that nothing rasterizes around it.
"""

from __future__ import annotations

import pathlib
import re
import statistics
import time
from xml.etree import ElementTree

import pytest

from inku_analysis import rasterizer, texture_fold
from inku_analysis.rasterizer import svg_to_png
from inku_analysis.texture_fold import (
    TEXTURE_FOLD_MAX_WIDTH,
    TEXTURE_REF_RE,
    fold_texture_runs,
    should_fold,
)
from inku_server.renderer import TEXTURE_FILTER_WEIGHTS, render
from inku_server.schema import Score

ROOT = pathlib.Path(__file__).resolve().parents[2]
# An element-level reference: the same string, on a tag that is not a group.
ELEMENT_REF = re.compile(r'<(?!g[ >/])[a-z]+[^>]*filter="url\(#texture-[a-z_]+\)"')
GROUP_REF = re.compile(r'<g filter="url\(#(texture-[a-z_]+)\)">')


def _scatter(weight: str, count: int, radius: float = 0.06) -> dict:
    return {
        "primitive": "circle",
        "center": [0.5, 0.5],
        "radius": radius,
        "weight": weight,
        "arrangement": {
            "count": count, "layout": "scatter", "jitter": 0.12, "margin": 0.1,
        },
    }


def _drawing(*instructions: dict, profile: str = "display") -> str:
    return render(
        Score.model_validate({"instructions": list(instructions)}),
        svg_profile=profile,
        render_seed=12345,
    )


def _element_sequence(svg: str) -> list[str]:
    """Every drawing element in document order, with its geometry.

    The filter attribute is deliberately not read: this is the claim that the
    marks did not move, and the fold is allowed to move the attribute.
    """
    root = ElementTree.fromstring(svg)
    out = []
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag in ("svg", "g", "defs", "clipPath", "title", "desc", "filter"):
            continue
        if tag.startswith("fe"):
            continue
        keys = sorted(
            (name, value) for name, value in element.attrib.items()
            if name in ("d", "points", "cx", "cy", "r", "x", "y", "width", "height")
        )
        out.append(f"{tag}:{keys}")
    return out


def _synthetic(*refs: str | None) -> str:
    """A minimal document whose marks carry exactly the references given.

    `None` is a mark with no texture. The wrapper group is there so the fold has
    a boundary to respect at both ends.
    """
    body = "".join(
        f'<path d="M0 {index} L1 {index}"'
        + (f' filter="url(#{ref})"' if ref else "")
        + "/>"
        for index, ref in enumerate(refs)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg"><defs/>'
        f'<g id="content">{body}</g></svg>'
    )


# --- T-129 ------------------------------------------------------------------


def test_the_marks_keep_their_order_through_the_fold():
    """T-129: the marks come out in the order they went in, and there are as many.

    Read from the parsed document rather than from the string, so a fold that
    produced text which merely looks like SVG cannot pass. The nesting is
    checked by the parse itself: a run wrapped across a group boundary does not
    parse.
    """
    svg = _drawing(_scatter("crayon", 6))
    before = _element_sequence(svg)
    assert len(before) > 50, len(before)
    assert len(ELEMENT_REF.findall(svg)) > 50

    folded = fold_texture_runs(svg)
    assert _element_sequence(folded) == before


def test_a_group_boundary_ends_the_run():
    """T-129: a run stops at a group, and never reaches over one.

    Stated separately because the sequence check above cannot see this. Wrapping
    two textured marks that sit either side of a nested group produces a
    document that still parses and whose marks are still in order -- what it
    changes is that the group's own children end up under a filter nobody asked
    to put on them. Order and well-formedness are both green while the picture
    has moved, which is exactly the kind of miss the acceptance is here to
    refuse.
    """
    document = (
        '<svg xmlns="http://www.w3.org/2000/svg"><defs/><g id="content">'
        '<path d="M0 0 L1 0" filter="url(#texture-crayon)"/>'
        '<g class="inner"><path d="M0 1 L1 1"/></g>'
        '<path d="M0 2 L1 2" filter="url(#texture-crayon)"/>'
        "</g></svg>"
    )
    folded = fold_texture_runs(document)
    assert GROUP_REF.findall(folded) == ["texture-crayon", "texture-crayon"]
    inner = ElementTree.fromstring(folded).find(".//*[@class='inner']")
    assert inner is not None
    # Nothing between the inner group and the root names a texture filter.
    root = ElementTree.fromstring(folded)
    parents = {child: parent for parent in root.iter() for child in parent}
    node = inner
    while node in parents:
        node = parents[node]
        assert "texture-" not in node.get("filter", "")


def test_a_filtered_group_is_not_swept_into_a_run():
    """T-129: a group that carries a texture filter is a boundary, not a member.

    The renderer writes one (`renderer.py:5876`, the pencil material outline
    layer), so this is not a hypothetical tag. Treating it as a run member
    swallows its opening tag without its closing one.
    """
    document = (
        '<svg xmlns="http://www.w3.org/2000/svg"><defs/><g id="content">'
        '<path d="M0 0 L1 0" filter="url(#texture-pencil)"/>'
        '<g class="layer" filter="url(#texture-pencil)">'
        '<path d="M0 1 L1 1" filter="url(#texture-pencil)"/></g>'
        "</g></svg>"
    )
    folded = fold_texture_runs(document)
    ElementTree.fromstring(folded)  # it still parses
    layer = ElementTree.fromstring(folded).find(".//*[@class='layer']")
    assert layer is not None
    assert layer.get("filter") == "url(#texture-pencil)"


# --- T-130 ------------------------------------------------------------------


def test_a_run_of_one_tool_becomes_one_group():
    """T-130: N marks of one tool in a row leave 0 element references and 1 group."""
    folded = fold_texture_runs(_synthetic(*["texture-crayon"] * 8))
    assert ELEMENT_REF.findall(folded) == []
    assert GROUP_REF.findall(folded) == ["texture-crayon"]
    assert folded.count("<path") == 8


def test_a_run_of_one_tool_becomes_one_group_in_a_real_drawing():
    """T-130, on the renderer's own output rather than on a hand-built document."""
    folded = fold_texture_runs(_drawing(_scatter("crayon", 4)))
    assert ELEMENT_REF.findall(folded) == []
    groups = GROUP_REF.findall(folded)
    assert groups and set(groups) == {"texture-crayon"}


# --- T-131 ------------------------------------------------------------------


def test_a_mark_without_texture_cuts_the_run():
    """T-131: textured, bare, textured is two groups -- never one over the bare mark."""
    folded = fold_texture_runs(
        _synthetic("texture-crayon", "texture-crayon", None, "texture-crayon")
    )
    assert GROUP_REF.findall(folded) == ["texture-crayon", "texture-crayon"]
    assert ELEMENT_REF.findall(folded) == []
    # The bare mark kept its place and nothing put a filter over it.
    content = ElementTree.fromstring(folded).find(".//*[@id='content']")
    assert content is not None
    assert [child.tag.split("}")[-1] for child in content] == ["g", "path", "g"]


# --- T-132 ------------------------------------------------------------------


def test_another_tool_cuts_the_run():
    """T-132: tool A then tool B is one group each, each naming its own filter."""
    folded = fold_texture_runs(
        _synthetic(
            "texture-crayon", "texture-crayon", "texture-pencil", "texture-pencil"
        )
    )
    assert GROUP_REF.findall(folded) == ["texture-crayon", "texture-pencil"]
    assert ELEMENT_REF.findall(folded) == []


def test_another_tool_cuts_the_run_in_a_real_drawing():
    """T-132, on the renderer's own output: two tools keep two sets of groups."""
    folded = fold_texture_runs(
        _drawing(_scatter("crayon", 3), _scatter("pencil", 3, radius=0.08))
    )
    assert ELEMENT_REF.findall(folded) == []
    assert set(GROUP_REF.findall(folded)) == {"texture-crayon", "texture-pencil"}


# --- T-133 ------------------------------------------------------------------


def test_the_stored_drawing_does_not_move():
    """T-133: the fold is a bake-time transform; `render` still writes per element.

    Stated as the pair, not as one half. That the renderer's output still holds
    element-level references says the fold did not run inside it; that folding
    that output *would* change it says the first half is not merely a drawing
    too small to fold.
    """
    for profile in ("display", "editable", "compat"):
        svg = _drawing(_scatter("crayon", 4), _scatter("pencil", 4, radius=0.08),
                       profile=profile)
        assert GROUP_REF.findall(svg) == [], profile
        if profile == "display":
            assert ELEMENT_REF.findall(svg), profile
            assert fold_texture_runs(svg) != svg, profile
        else:
            # The structured profiles carry no texture filter at all, so there
            # is nothing here for the fold to hang and it cannot move a byte.
            assert TEXTURE_REF_RE.findall(svg) == [], profile
            assert fold_texture_runs(svg) == svg, profile


# --- T-134 ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("width", "folds"),
    [(256, True), (512, True), (513, False), (576, False), (2160, False)],
)
def test_the_width_decides_whether_it_folds(monkeypatch, width, folds):
    """T-134: what reaches the rasterizer is folded at thumbnail sizes and not above.

    The bytes are caught at the backend rather than inferred from a timing, so
    the claim is about what was handed over and not about how fast it went.
    """
    handed: list[str] = []

    def _capture(svg, w, h, fonts, skip):
        handed.append(svg)
        return b""

    monkeypatch.setattr(rasterizer, "_resvg_renderer", lambda: _capture)
    drawing = _drawing(_scatter("crayon", 3))
    svg_to_png(drawing, width=width)

    assert len(handed) == 1
    if folds:
        assert ELEMENT_REF.findall(handed[0]) == []
        assert GROUP_REF.findall(handed[0])
    else:
        assert handed[0] == drawing


def test_the_width_boundary_is_the_hidpi_thumbnail():
    """T-134: the two production thumbnail widths are inside and export is outside.

    `thumbs_db.BASE_WIDTH` times the scales is 256 and 512; `db.png_size`
    defaults to 2160. Read the boundary rather than restating the numbers.
    """
    from inku_server import thumbs_db

    assert [thumbs_db.width_for_scale(scale) for scale in thumbs_db.SCALES] == [256, 512]
    assert all(
        should_fold(thumbs_db.width_for_scale(scale), None)
        for scale in thumbs_db.SCALES
    )
    assert not should_fold(2160, None)
    assert not should_fold(None, None)
    assert should_fold(None, TEXTURE_FOLD_MAX_WIDTH)


# --- T-135 ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "bar"), [(4, 0.5), (32, 3.0)]
)
def test_the_thumbnail_is_the_same_picture(count, bar):
    """T-135: the folded thumbnail is the drawing, not a different drawing.

    The mean per-pixel difference, not a byte comparison: the fold changes how a
    filter is applied, so some pixels do move, and the claim is that they move
    by less than the eye reads as a different picture.

    **The bar is per subject because the difference grows as the drawing gets
    denser and the thumbnail stays the same size.** Measured on 2026-08-16 at
    256px: 0.058 at 127 references, 0.184 at 378, 2.010 at 4,616, 3.685 at
    12,292. One bar for all of them would be slack on the light end, which is
    where a fold that started reordering marks would first show. The issuer's
    sheets -- the ones the author judged -- were baked at 1618px, where the same
    six tools measured 0.036 to 1.333; a thumbnail is not that measurement.

    The control is the point of the second half: a comparison that would pass on
    two unrelated pictures says nothing.
    """
    pytest.importorskip("resvg_py")
    from io import BytesIO

    from PIL import Image

    drawing = _drawing(_scatter("crayon", count))
    folded = fold_texture_runs(drawing)
    plain = Image.open(BytesIO(_raw_png(drawing, 256))).convert("RGB")
    hung = Image.open(BytesIO(_raw_png(folded, 256))).convert("RGB")
    assert plain.size == hung.size

    difference = _mean_difference(plain, hung)
    assert difference < bar, difference

    other = Image.open(
        BytesIO(_raw_png(_drawing(_scatter("chalk", count, radius=0.2)), 256))
    ).convert("RGB")
    assert _mean_difference(plain, other) > difference * 4


def _raw_png(svg: str, width: int) -> bytes:
    """Rasterize without the fold, whatever the width says.

    `svg_to_png` folds by itself below the boundary, which is the whole point of
    it; this test needs to hand over exactly the bytes it names.
    """
    render_fn = rasterizer._resvg_renderer()
    assert render_fn is not None
    return render_fn(svg, width, None, None, False)


def _mean_difference(left, right) -> float:
    pixels_left = left.tobytes()
    pixels_right = right.tobytes()
    assert len(pixels_left) == len(pixels_right)
    total = sum(abs(a - b) for a, b in zip(pixels_left, pixels_right))
    return total / len(pixels_left)


# --- T-136 ------------------------------------------------------------------


def test_no_road_rasterizes_around_the_fold():
    """T-136: every road to resvg goes through `svg_to_png`, which decides.

    The decision is not a flag each caller passes, because a flag any caller
    could forget is one some caller would. That only holds while `svg_to_png` is
    the single door, so the door is counted here: nothing outside the rasterizer
    module imports the backend.

    The search is for the import and not for the word `resvg`, which appears in
    six places as prose and log text -- a census that counts those counts
    documentation and goes red on a comment.
    """
    backend_import = re.compile(r"^\s*(?:import resvg_py|from resvg_py\b)", re.M)
    offenders = []
    counted = 0
    for tree in ("server/src", "cli/src", "shared/src"):
        for path in sorted((ROOT / tree).rglob("*.py")):
            counted += 1
            if path == ROOT / "shared/src/inku_analysis/rasterizer.py":
                continue
            if backend_import.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
    # Say how many were read: an empty answer from a walk that found no files
    # would look exactly the same.
    assert counted > 50, counted
    assert backend_import.search(
        (ROOT / "shared/src/inku_analysis/rasterizer.py").read_text(encoding="utf-8")
    )

    # And the door itself still opens onto the fold.
    source = (ROOT / "shared/src/inku_analysis/rasterizer.py").read_text(
        encoding="utf-8"
    )
    assert "should_fold(width, height)" in source
    assert "fold_texture_runs(svg)" in source


# --- T-137 ------------------------------------------------------------------


def test_folding_pays_for_itself_at_the_thumbnail_width():
    """T-137: at 256px the fold costs less than it saves, fold time included.

    The pair is taken inside one round -- the same bytes baked in two different
    rounds moved by 40 percent in the issuer's own table, so only a ratio read
    within a round means anything -- and the fold's own time is charged to the
    folded side.

    **Only 256px is timed, and that is a measurement and not an omission.**
    Across four subjects the fold measured 1.27x to 2.62x at 256px and 0.96x to
    1.37x at 512px. The second band straddles 1.0 by less than the noise, so an
    assertion there would pass or fail on which other process was running, not
    on the code. That 512px folds at all is decided by
    `test_the_width_decides_whether_it_folds`, which reads bytes and not a
    clock; the ratios are recorded in `texture_fold`'s docstring.
    """
    pytest.importorskip("resvg_py")
    drawing = _drawing(_scatter("crayon", 6))
    assert len(ELEMENT_REF.findall(drawing)) > 100

    plain, hung = [], []
    for _ in range(3):
        start = time.perf_counter()
        _raw_png(drawing, 256)
        plain.append(time.perf_counter() - start)

        start = time.perf_counter()
        _raw_png(fold_texture_runs(drawing), 256)
        hung.append(time.perf_counter() - start)

    assert statistics.median(hung) < statistics.median(plain), (
        statistics.median(plain), statistics.median(hung)
    )


# --- T-138 ------------------------------------------------------------------


def test_the_renderer_still_writes_the_id_the_fold_keys_on():
    """T-138: the shape the fold matches is the shape the renderer writes.

    The fold lives in `shared/` and keys on a string the server builds. Nothing
    holds those two together on its own: renaming the id would leave this file
    matching nothing, and a fold that matches nothing is not an error, it is a
    fold that quietly stops happening. So the pattern is read against a real
    render of every tool that carries a texture.

    `drypoint` reaches its filter only through the burr on an outline, which is
    why it is drawn as a line here and the rest as circles.
    """
    assert TEXTURE_FILTER_WEIGHTS, "the renderer names no textured tool at all"
    seen = set()
    for weight in sorted(TEXTURE_FILTER_WEIGHTS):
        if weight == "drypoint":
            instruction = {
                "primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5],
                "weight": weight,
            }
        else:
            instruction = _scatter(weight, 2)
        svg = _drawing(instruction)
        found = TEXTURE_REF_RE.findall(svg)
        assert found, weight
        assert set(found) == {f"texture-{weight}"}, (weight, set(found))
        seen.add(weight)
    assert seen == set(TEXTURE_FILTER_WEIGHTS)
    assert texture_fold.TEXTURE_REF_RE is TEXTURE_REF_RE
