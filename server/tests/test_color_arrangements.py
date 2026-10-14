"""A repeated or identity candidate must not occupy an arrangement page."""

import itertools

import pytest

from inku_server.color_arrangements import ColorArrangements


def test_pages_exhaust_distinct_injections_without_identity_or_aliases():
    colors = {"palette:a": "#111111", "palette:alias": "#111", "palette:b": "#ABCDEF", "palette:c": "#222222", "palette:d": "#333333"}
    plan = ColorArrangements.from_saved('<svg><path fill="#111111" stroke="#abcdef"/></svg>', colors)
    pages = [plan.page(cursor) for cursor in (0, 8, 11, 100)]
    assert [len(page["entries"]) for page in pages] == [8, 3, 0, 0]
    assert [page["next_cursor"] for page in pages] == [8, None, None, None]
    assert plan.total == 11
    assignments = [tuple(plan.substitution(index).values()) for index in range(plan.total)]
    expected = set(itertools.permutations(plan.palette, len(plan.used))) - {plan.used}
    assert len(assignments) == len(set(assignments))
    assert set(assignments) == expected
    assert {entry["index"] for entry in pages[0]["entries"]}.isdisjoint(entry["index"] for entry in pages[1]["entries"])
    with pytest.raises(ValueError, match="exhausted"):
        plan.substitution(plan.total)


def test_child_mapping_composes_visible_colors_once():
    colors = {"palette:a": "#111111", "palette:b": "#222222", "palette:c": "#333333", "black": "#111111",
              "recolor:#111111": "#222222", "recolor:#222222": "#111111"}
    plan = ColorArrangements.from_saved('<svg><path fill="#222222" stroke="#111111"/></svg>', colors)
    substitution = plan.substitution(0)
    child = plan.color_map(colors, 0)
    assert {key: value for key, value in child.items() if not key.startswith("recolor:")} == {
        key: value for key, value in colors.items() if not key.startswith("recolor:")
    }
    for original in plan.palette:
        current = colors.get(f"recolor:{original}", original)
        assert child.get(f"recolor:{original}", original) == substitution.get(current, current)


def test_no_recolorable_paints_exhausts_and_empty_palette_refuses():
    plan = ColorArrangements.from_saved('<svg><path fill="none" stroke="#999999"/></svg>', {"palette:a": "#111111"})
    assert plan.page() == {"entries": [], "next_cursor": None, "total": 0}
    with pytest.raises(ValueError, match="no usable palette"):
        ColorArrangements.from_saved("<svg/>", {"black": "#111111"})
