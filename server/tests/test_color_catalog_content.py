"""Contract tests for the engine-18 color catalog content.

Engine 18 moves data and nothing else: thirteen catalogs, each with exactly
three achromatic and seven chromatic colors, a nine-key map drawn from the
palette, and a swatch strip derived from that map. These tests pin the shape of
that data by value, because a catalog table is the kind of thing a later edit
can quietly unbalance -- one hex nudged past the chroma floor empties a band.
"""

from __future__ import annotations

import pytest

from inku_server.color_catalogs import (
    COLOR_CATALOGS,
    COLOR_KEYS,
    SWATCH_KEY_ORDER,
    color_catalog_ids,
    get_color_catalog,
    render_color_map_for_catalog,
)
from inku_server.renderer import (
    _OKLCH_CHROMA_FLOOR,
    _oklch_from_hex,
    _resolve_color,
    _work_color_assignment,
    COLOR_MAP,
)


ACHROMATIC_KEYS = ("black", "gray", "white")
CHROMATIC_KEYS = ("red", "orange", "yellow", "green", "blue", "purple")

EXPECTED_CATALOG_IDS = (
    "default",
    "ink_season",
    "fresco_study",
    "open_air_light",
    "ink_porcelain",
    "cool_material",
    "dye_earth",
    "vivid_material",
    "weathered_heritage",
    "sea_stone",
    "moss_bark",
    "neon_plate",
    "lantern_dew",
)

RETIRED_CATALOG_IDS = (
    "desert_mineral",
    "japanese",
    "mexican",
    "indian",
    "british",
    "egyptian",
    "greek",
    "impressionism",
    "nordic",
    "renaissance",
)


def _is_chromatic(hex_value: str) -> bool:
    oklch = _oklch_from_hex(hex_value)
    assert oklch is not None, hex_value
    return oklch[1] >= _OKLCH_CHROMA_FLOOR


def test_color_keys_are_the_nine_abstract_colors() -> None:
    assert len(COLOR_KEYS) == 9
    assert COLOR_KEYS == (
        "white", "black", "gray", "red", "orange", "yellow", "green", "blue", "purple",
    )


def test_catalog_ids_and_order() -> None:
    assert color_catalog_ids() == EXPECTED_CATALOG_IDS


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda item: item["id"])
def test_every_catalog_holds_three_achromatic_and_seven_chromatic_colors(
    catalog: dict,
) -> None:
    palette = catalog["palette"]
    codes = [str(color["code"]) for color in palette]

    assert len(palette) == 10
    assert len(set(codes)) == 10, f"duplicate hex in {catalog['id']}"

    chromatic = [code for code in codes if _is_chromatic(code)]
    achromatic = [code for code in codes if not _is_chromatic(code)]
    assert len(achromatic) == 3, f"{catalog['id']} achromatic: {achromatic}"
    assert len(chromatic) == 7, f"{catalog['id']} chromatic: {chromatic}"


def test_no_hex_is_reused_across_catalogs() -> None:
    codes = [
        str(color["code"])
        for catalog in COLOR_CATALOGS
        for color in catalog["palette"]
    ]

    assert len(codes) == 130
    assert len(set(codes)) == 130


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda item: item["id"])
def test_every_map_key_names_a_color_from_the_same_palette(catalog: dict) -> None:
    codes = {str(color["code"]) for color in catalog["palette"]}

    assert set(catalog["map"]) == set(COLOR_KEYS)
    for key in COLOR_KEYS:
        assert catalog["map"][key] in codes, (catalog["id"], key)


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda item: item["id"])
def test_the_first_four_swatches_are_chromatic(catalog: dict) -> None:
    # Android draws `swatches.take(4)` in one screen, so the leading four slots
    # decide whether that strip shows a catalog's colors or its grays. Asserted
    # against the chroma floor rather than against SWATCH_KEY_ORDER, which would
    # only restate how the list was built.
    swatches = catalog["swatches"]

    assert len(swatches) == 9
    assert [_is_chromatic(hex_value) for hex_value in swatches[:4]] == [True] * 4
    assert [_is_chromatic(hex_value) for hex_value in swatches[:8]].count(False) == 2


def test_swatch_key_order_leads_with_the_six_bands() -> None:
    assert SWATCH_KEY_ORDER[:6] == CHROMATIC_KEYS
    assert SWATCH_KEY_ORDER[6:] == ACHROMATIC_KEYS


@pytest.mark.parametrize("catalog_id", EXPECTED_CATALOG_IDS)
def test_every_catalog_map_carries_ten_palette_entries(catalog_id: str) -> None:
    color_map = render_color_map_for_catalog(catalog_id)

    assert color_map is not None
    assert sum(1 for key in color_map if key.startswith("palette:")) == 10


def test_sea_stone_purple_stands_in_with_night_sea() -> None:
    # sea_stone is the one catalog left without a color in the purple band, by
    # the author's ruling. The renderer's nearest-band stand-in must answer with
    # Night Sea, which is also its blue -- that collision is the ruling, not a
    # defect.
    color_map = render_color_map_for_catalog("sea_stone")
    assert color_map is not None
    cmap = {**COLOR_MAP, **color_map}

    assignment = _work_color_assignment(cmap, 12345, "sea_stone")

    assert assignment["purple"] == "#191970"
    assert assignment["blue"] == "#191970"


# The ground is painted with whatever the score's background word resolves to
# through the same work assignment (renderer.py: `bg = work_assignment.get(
# score.background, ...)`), so a role within this much lightness of the
# catalog's own white is drawn on paper as bright as itself.
PAPER_DISSOLVE_LIMIT = 0.15
ROLES_THAT_DISSOLVE = {
    ("open_air_light", "yellow"): "#ffce00",
    ("vivid_material", "yellow"): "#fff200",
}
ASSIGNMENT_SEEDS = (0, 1, 7, 99, 555, 4242, 12345, 31337)


def test_only_the_two_bright_yellows_dissolve_into_the_paper() -> None:
    # I-062: engine 17 handed cool_material's black `#e5e8e8`, 0.062 in
    # lightness from its own paper, and every test stayed green because they all
    # compared hexes. The expected-assignment table cannot stand in for this --
    # a later catalog edit regenerates that table and takes the property with
    # it. A bright yellow band is thin by nature, so those two are named here by
    # value instead of being silently tolerated.
    found: dict[tuple[str, str], str] = {}
    for catalog in COLOR_CATALOGS:
        catalog_id = str(catalog["id"])
        cmap = {**COLOR_MAP, **(render_color_map_for_catalog(catalog_id) or {})}
        for seed in ASSIGNMENT_SEEDS:
            assignment = _work_color_assignment(cmap, seed, catalog_id)
            resolved = {
                key: _resolve_color(key, None, cmap, work_assignment=assignment)
                for key in COLOR_KEYS
            }
            paper = _oklch_from_hex(resolved["white"])[0]
            for key, value in resolved.items():
                if key == "white":
                    continue
                if abs(_oklch_from_hex(value)[0] - paper) < PAPER_DISSOLVE_LIMIT:
                    found[(catalog_id, key)] = value

    assert found == ROLES_THAT_DISSOLVE


@pytest.mark.parametrize("catalog_id", RETIRED_CATALOG_IDS)
def test_retired_catalog_ids_resolve_to_nothing(catalog_id: str) -> None:
    assert get_color_catalog(catalog_id) is None
    assert render_color_map_for_catalog(catalog_id) is None
