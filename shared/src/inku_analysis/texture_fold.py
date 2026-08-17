"""Hang a texture filter on the run of marks it covers, before rasterizing small.

One work in production held 24,446 filter references: 24,445 of them were the
crayon's texture, written on every element, and one was the performance touch,
hung once on the content group. Rasterizing it took 16 seconds at thumbnail size
and 460 at export size, and the per-element references were most of that.

A run is a maximal stretch of consecutive sibling elements naming the same
`texture-<tool>` filter. Replacing a run with one group that names the filter
once draws the same marks in the same order -- nothing is reordered, nothing is
added or removed -- and asks the rasterizer for one filter instead of N.

**This is a bake-time transform and never touches the stored drawing.** The
saved SVG is the renderer's, byte for byte; only the bytes handed to the
rasterizer change, and only when the target is small.

Why only when it is small. Folding trades two costs against each other: the
number of times a filter is applied falls by roughly twelve, and the total area
those applications cover rises by 1.35 to 1.41, because a run's box is the union
of the boxes it replaces. At thumbnail sizes the count is what costs and folding
wins; past about 576px the area is what costs and it loses. Measured on
2026-08-16 across four subjects (105 / 378 / 4,616 / 12,292 references), pairs
taken inside one round:

    width   105     378     4,616   12,292
    256px   2.62x   1.27x   1.89x   1.95x
    512px   1.11x   1.02x   1.09x   1.37x
    576px   1.03x   0.89x   1.12x   1.11x
    768px   0.94x   0.91x   0.98x   1.00x
    2160px    --    0.85x   0.82x   0.86x

512px is the last width at which all four win, and it is exactly the HiDPI
thumbnail. Production bakes thumbnails at 256 and 512 (`thumbs_db.BASE_WIDTH`
times the scale) and exports PNG at 2160 (`db.png_size`), so the rule as stated
folds for every thumbnail and for nothing else.

The ceiling is a ruling as well as a measurement: I-264 puts the PNG export
default of 2160px and the browser's display width outside it, and leaves the
stored SVG the renderer's byte for byte. Folding does change the pixels -- at
1:1 the mean difference (/255) is 0.058 / 0.184 / 2.010 / 3.685 at 256px and
0.039 / 0.115 / 1.383 / 2.575 at 512px, for subjects of 127 / 378 / 4,616 /
12,292 references -- and the author judged those two widths and no others, so
the difference at any other width has been neither measured nor seen.

A reference-count threshold was measured first and does not exist: at 2160px
folding lost at every count from 34 to 26,675, and got worse as the count rose.
"""

from __future__ import annotations

import re

#: The largest raster width at which folding is worth it. Above this the union
#: box the fold creates costs more than the applications it saves.
TEXTURE_FOLD_MAX_WIDTH = 512

_TAG = re.compile(r"<[^>]*>")
#: The id shape the renderer writes. `inku_server.renderer` builds it from
#: `TEXTURE_SPECS`, and a server-side test reads THIS pattern against a real
#: render, because a rename on either side would make this file silently do
#: nothing rather than fail. Public for that test to read.
TEXTURE_REF_RE = re.compile(r' filter="url\(#(texture-[a-z_]+)\)"')
_REF = TEXTURE_REF_RE


def should_fold(width: int | None, height: int | None) -> bool:
    """Whether a raster of this size is small enough to be worth folding.

    Only one of the two is usually given -- the rasterizer scales the other side
    to keep the aspect -- so the size signal is whichever was stated. With
    neither, the drawing is rasterized at its intrinsic size, which is the
    canvas's own 1000-plus pixels and well past the boundary.
    """
    stated = [value for value in (width, height) if value is not None]
    if not stated:
        return False
    return max(stated) <= TEXTURE_FOLD_MAX_WIDTH


def _is_edge(tag: str) -> bool:
    """Whether this tag is a boundary a run must not reach across.

    Any closing tag, the prologue and comments, and any `<g>`. The last one is
    not covered by "carries no texture": the renderer writes one group that does
    carry a texture filter (`renderer.py:5876`, the pencil material outline), and
    treating that as a run member swallows its opening tag without its close.
    """
    if tag.startswith(("</", "<?", "<!")):
        return True
    return tag.startswith("<g") and not tag[2:3].isalnum()


def fold_texture_runs(svg: str) -> str:
    """Replace each run of same-texture siblings with one group naming it once.

    Three things end a run, and all three are boundaries the picture already has:

    * a `<g>` or `</g>`, because wrapping across it would cross tags and move a
      mark out of the group it was drawn in;
    * a mark with no texture reference, which would otherwise be drawn through a
      filter nothing asked to put on it;
    * a different tool, whose filter is a different filter.

    Runs of one are wrapped too. It draws the same -- a filter over a group of
    one is that one element's filter -- and it means a folded document carries
    no element-level texture reference at all, which is a claim a test can read
    without knowing how the marks happened to fall.
    """
    runs: list[tuple[int, int, str]] = []
    start = end = -1
    weight = ""
    for match in _TAG.finditer(svg):
        tag = match.group(0)
        ref: str | None = None
        if _is_edge(tag):
            # An edge ends the run rather than being skipped over. Skipping
            # would let a run reach across a nested group, which parses and
            # keeps the order -- and puts that group's own marks under a filter
            # nobody asked to put on them.
            ref = None
        else:
            found = _REF.search(tag)
            if found is not None:
                ref = found.group(1)
        if ref is not None and ref == weight:
            end = match.end()
            continue
        if start >= 0:
            runs.append((start, end, weight))
            start = end = -1
            weight = ""
        if ref is not None:
            start, end, weight = match.start(), match.end(), ref
    if start >= 0:
        runs.append((start, end, weight))
    if not runs:
        return svg

    out: list[str] = []
    last = 0
    for begin, stop, name in runs:
        out.append(svg[last:begin])
        out.append(f'<g filter="url(#{name})">')
        out.append(_REF.sub("", svg[begin:stop]))
        out.append("</g>")
        last = stop
    out.append(svg[last:])
    return "".join(out)
