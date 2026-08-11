"""Acceptance for the shareable card: the bundled font, and what gets typeset.

The font tests rasterize for real rather than stubbing the rasterizer. A stub
would keep passing if the bundled face went missing, which is the one failure
the card cannot survive: the headnote is Japanese, and a machine with no font
draws it as nothing at all rather than as a substitute.
"""

from io import BytesIO
from xml.etree import ElementTree

import pytest
from PIL import Image

from inku_analysis.rasterizer import svg_to_png
from inku_server import card_export
from inku_server.card_export import (
    FONT_FAMILY,
    FONT_PATH,
    HEADNOTE_LINE_HEIGHT,
    LAYOUT_SIZES,
    build_card,
    compose_card_svg,
)

SVG_NS = "{http://www.w3.org/2000/svg}"

WORK = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" '
    'viewBox="0 0 1000 1000">'
    '<rect id="the_work_ground" width="1000" height="1000" fill="#ffffff"/>'
    '<circle id="the_work_mark" cx="500" cy="500" r="120" fill="#23201b"/>'
    "</svg>"
)

HEADNOTE = "夕立のあと、濡れた石の匂いだけが残っている"


def _elements(document: str) -> dict[str, ElementTree.Element]:
    root = ElementTree.fromstring(document)
    found = {}
    for node in root.iter():
        ident = node.get("id")
        if ident:
            found[ident] = node
    return found


def _headnote_band(layout: str, line_count: int) -> tuple[int, int]:
    """Rows the headnote occupies, derived from the module's own layout constants."""
    _, height = LAYOUT_SIZES[layout]
    footer_baseline = height - card_export.MARGIN
    block = line_count * HEADNOTE_LINE_HEIGHT
    top = footer_baseline - card_export.FOOTER_SIZE - card_export.GAP - block
    return top, top + block


def _band_ink(png: bytes, band: tuple[int, int]) -> tuple[int, int]:
    """Pixels darker than the card ground inside ``band``, and their drawn width."""
    image = Image.open(BytesIO(png)).convert("L")
    crop = image.crop((0, band[0], image.width, band[1]))
    mask = crop.point(lambda value: 255 if value < 160 else 0)
    box = mask.getbbox()
    count = mask.histogram()[255]
    return count, (box[2] - box[0]) if box else 0


# --- T-1: the bundled font is doing the drawing ------------------------------


def test_t1_bundled_font_puts_ink_in_the_headnote_band():
    document = compose_card_svg(WORK, headnote=HEADNOTE, seed=4821)
    width, height = LAYOUT_SIZES["square"]
    png = svg_to_png(
        document,
        width=width,
        height=height,
        font_files=[str(FONT_PATH)],
        skip_system_fonts=True,
    )
    ink, _ = _band_ink(png, _headnote_band("square", 1))
    assert ink > 0


def test_t1_control_without_the_font_the_same_band_is_empty():
    """The control for the test above. It has no discriminating power alone."""
    document = compose_card_svg(WORK, headnote=HEADNOTE, seed=4821)
    width, height = LAYOUT_SIZES["square"]
    png = svg_to_png(document, width=width, height=height, skip_system_fonts=True)
    ink, _ = _band_ink(png, _headnote_band("square", 1))
    assert ink == 0


def test_t1_a_longer_headnote_is_drawn_wider():
    """Rules out an implementation that draws a constant regardless of the text."""
    width, height = LAYOUT_SIZES["square"]
    widths = []
    for text in ("石", "石の匂いだけが残っている"):
        png = svg_to_png(
            compose_card_svg(WORK, headnote=text, seed=4821),
            width=width,
            height=height,
            font_files=[str(FONT_PATH)],
            skip_system_fonts=True,
        )
        _, drawn = _band_ink(png, _headnote_band("square", 1))
        widths.append(drawn)
    assert widths[0] > 0
    assert widths[1] > widths[0] * 2


# --- T-2: four things are typeset, each matched against its source -----------


def test_t2_the_picture_is_the_work_itself():
    found = _elements(compose_card_svg(WORK, headnote=HEADNOTE, seed=4821))
    assert "inku_card_work" in found
    nested = found["inku_card_work"]
    assert nested.tag == f"{SVG_NS}svg"
    inner_ids = {node.get("id") for node in nested.iter()}
    assert {"the_work_ground", "the_work_mark"} <= inner_ids


def test_t2_the_headnote_is_the_source_text():
    found = _elements(compose_card_svg(WORK, headnote=HEADNOTE, seed=4821))
    lines = found["inku_card_headnote"].findall(f"{SVG_NS}text")
    assert "".join(line.text or "" for line in lines) == HEADNOTE


def test_t2_the_seed_is_the_last_four_digits_of_the_works_seed():
    found = _elements(compose_card_svg(WORK, headnote=HEADNOTE, seed=917364821))
    assert found["inku_card_seed"].text == "seed 4821"


def test_t2_the_seal_reads_inku():
    found = _elements(compose_card_svg(WORK, headnote=HEADNOTE, seed=4821))
    assert found["inku_card_seal"].text == "inku"


# --- T-3: the seal comes off -------------------------------------------------


def test_t3_seal_on_puts_exactly_one_seal_in():
    found = _elements(compose_card_svg(WORK, headnote=HEADNOTE, seed=4821, seal=True))
    assert sum(1 for key in found if key == "inku_card_seal") == 1


def test_t3_seal_off_puts_none_in():
    document = compose_card_svg(WORK, headnote=HEADNOTE, seed=4821, seal=False)
    assert "inku_card_seal" not in _elements(document)
    assert ">inku<" not in document


# --- T-4: two page shapes ----------------------------------------------------


@pytest.mark.parametrize(
    ("layout", "ratio"),
    [("square", 1080 / 1080), ("portrait", 1080 / 1350)],
)
def test_t4_the_output_carries_the_layouts_aspect_ratio(layout, ratio):
    png = build_card(WORK, headnote=HEADNOTE, seed=4821, layout=layout)
    image = Image.open(BytesIO(png))
    assert image.size == LAYOUT_SIZES[layout]
    assert image.width / image.height == pytest.approx(ratio)


# --- T-5: the seed belongs to the work --------------------------------------


def test_t5_a_different_work_shows_a_different_seed_tail():
    first = _elements(compose_card_svg(WORK, headnote=HEADNOTE, seed=917364821))
    second = _elements(compose_card_svg(WORK, headnote=HEADNOTE, seed=917360137))
    assert first["inku_card_seed"].text == "seed 4821"
    assert second["inku_card_seed"].text == "seed 0137"
    assert first["inku_card_seed"].text != second["inku_card_seed"].text


# --- T-9: a work with no headnote -------------------------------------------


def test_t9_a_work_without_a_headnote_still_produces_a_card():
    document = compose_card_svg(WORK, headnote="", seed=4821)
    found = _elements(document)
    assert "inku_card_headnote" not in found
    assert "inku_card_work" in found
    png = build_card(WORK, headnote="", seed=4821)
    image = Image.open(BytesIO(png))
    assert image.size == LAYOUT_SIZES["square"]


def test_the_family_written_into_the_svg_is_the_one_the_bundled_file_answers_to():
    """resvg matches on the typographic family name; a mismatch draws nothing."""
    assert FONT_PATH.exists()
    assert f'font-family="{FONT_FAMILY}"' in compose_card_svg(
        WORK, headnote=HEADNOTE, seed=4821
    )
