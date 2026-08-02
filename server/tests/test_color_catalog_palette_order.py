"""The palette of every catalog follows the order the `default` catalog sets.

`palette` feeds two readers at once: the swatch grid in ColorCatalogModal and
the one-line card `build_catalog_card()` hands to the Stage 1 model. Both read
the list in source order, so a catalog whose palette is shuffled looks unlike
its neighbours in the grid and describes its colors in a different sequence in
the prompt.

The order is checked as a property, not as a table of expected names: the
reference sequence is derived from `default` at test time. Writing the nine
abstract keys as a constant here would turn this file into a record that a
later edit to `default` merely re-bakes -- it would stop failing when the thing
it guards actually breaks.
"""

from __future__ import annotations

import pytest

from inku_server.color_catalogs import (
    COLOR_CATALOGS,
    DEFAULT_COLOR_CATALOG_ID,
    get_color_catalog,
)


def _partition(catalog: dict) -> tuple[list[str], list[str]]:
    """Split a palette into (abstract keys of map-matched entries, leftover names).

    An entry belongs to the map when its hex equals one of the nine map values.
    The remaining entries are the catalog's own extra colors.
    """
    color_map = catalog["map"]
    matched: list[str] = []
    leftover: list[str] = []
    for entry in catalog["palette"]:
        keys = [k for k, v in color_map.items() if v.lower() == entry["code"].lower()]
        assert len(keys) <= 1, f"{catalog['id']}: {entry['code']} matches {keys}"
        if keys:
            matched.append(keys[0])
        else:
            leftover.append(entry["name"])
    return matched, leftover


@pytest.fixture(scope="module")
def reference_order() -> list[str]:
    """The abstract key sequence taken from `default`, the catalog that sets the order."""
    matched, leftover = _partition(get_color_catalog(DEFAULT_COLOR_CATALOG_ID))
    assert len(matched) == 9, matched
    assert len(leftover) == 1, leftover
    return matched


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda c: c["id"])
def test_palette_has_ten_entries(catalog: dict) -> None:
    assert len(catalog["palette"]) == 10


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda c: c["id"])
def test_palette_splits_into_nine_map_colors_and_one_extra(catalog: dict) -> None:
    matched, leftover = _partition(catalog)
    assert len(matched) == 9, f"{catalog['id']}: map-matched entries {matched}"
    assert len(leftover) == 1, f"{catalog['id']}: extra entries {leftover}"


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda c: c["id"])
def test_map_colors_follow_the_default_catalog_order(
    catalog: dict, reference_order: list[str]
) -> None:
    matched, _ = _partition(catalog)
    assert matched == reference_order, (
        f"{catalog['id']} orders its map colors {matched}, "
        f"but {DEFAULT_COLOR_CATALOG_ID} orders them {reference_order}"
    )


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda c: c["id"])
def test_the_extra_color_comes_last(catalog: dict) -> None:
    color_map = catalog["map"]
    hexes = {v.lower() for v in color_map.values()}
    positions = [
        index
        for index, entry in enumerate(catalog["palette"])
        if entry["code"].lower() not in hexes
    ]
    assert positions == [len(catalog["palette"]) - 1], (
        f"{catalog['id']}: the extra color sits at {positions}, not at the end"
    )
