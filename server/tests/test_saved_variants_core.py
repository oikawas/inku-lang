"""Changing the touches, the support or the color arrangement is the shared core's rule.

The rows in data/saved-variant-cases.json were written by the Python rules
Server used to hold (tool_variants.py, ground_variants.py, color_arrangements.py),
with the 2026-10-17 ruling on an added ground sentence's language. Android and
Swift read the same file. The properties below are the ones the removed Python
unit tests guarded, now asked of the core.
"""

from __future__ import annotations

import itertools
import json
import pathlib

import pytest

from inku_server.saved_variants import SavedVariantRefused, ask

CASES = json.loads((pathlib.Path(__file__).parent / "data" / "saved-variant-cases.json").read_text(encoding="utf-8"))


def _owner(index: int, weight: str | None = None) -> dict:
    instruction = {"primitive": "line", "arrangement": {"resolved": {"owner": {"kind": "source_instruction", "instruction_index": index}}}}
    if weight:
        instruction["weight"] = weight
    return instruction


@pytest.mark.parametrize("row", CASES["grounds"], ids=[r["why"] for r in CASES["grounds"]])
def test_every_shared_ground_case_is_planned_as_server_planned_it(row):
    plan = ask("ground_plan", score=row["score"])
    assert plan["current"] == row["current"]
    assert [entry["material"] for entry in plan["entries"]] == row["entries"]


@pytest.mark.parametrize("row", CASES["ground_sentences"], ids=[r["why"] for r in CASES["ground_sentences"]])
def test_every_shared_ground_sentence_is_written_as_ruled(row):
    score = {"canvas": {"aspect": "square", "ground": {"material": "washi"}}, "instructions": []}
    for material, expected in row["results"].items():
        drawn = ask("ground_render", score=score, source=row["ddl"], material=material, language=row["language"])
        assert drawn["ddl"] == expected


@pytest.mark.parametrize("row", CASES["colors"], ids=[r["why"] for r in CASES["colors"]])
def test_every_shared_color_case_pages_and_recolors_as_server_did(row):
    base = {"svg": row["svg"], "color_map": row["color_map"], "work_id": row["work_id"]}
    for cursor, expected in row["pages"].items():
        page = ask("color_plan", **base, cursor=int(cursor))
        assert {key: page[key] for key in ("entries", "next_cursor", "total")} == expected
    for index, expected in row["color_maps"].items():
        drawn = ask("color_render", **base, index=int(index), catalog_id="ink_season")
        assert drawn["color_map"] == expected
        assert drawn["derivation_metadata"] == {"color_arrangement_index": int(index), "catalog_id": "ink_season"}


@pytest.mark.parametrize("row", CASES["color_refusals"], ids=[r["why"] for r in CASES["color_refusals"]])
def test_every_shared_color_refusal_says_what_server_said(row):
    with pytest.raises(SavedVariantRefused, match=row["detail"]):
        ask("color_render", svg=row["svg"], color_map=row["color_map"], work_id=row["work_id"], index=row["index"], catalog_id="x")


def test_pages_exhaust_distinct_assignments_without_the_work_s_own():
    colors = {"palette:a": "#111111", "palette:alias": "#111", "palette:b": "#ABCDEF", "palette:c": "#222222", "palette:d": "#333333"}
    base = {"svg": '<svg><path fill="#111111" stroke="#abcdef"/></svg>', "color_map": colors, "work_id": ""}
    pages = [ask("color_plan", **base, cursor=cursor) for cursor in (0, 8, 11, 100)]
    assert [len(page["entries"]) for page in pages] == [8, 3, 0, 0]
    assert [page["next_cursor"] for page in pages] == [8, None, None, None]
    assert pages[0]["total"] == 11
    used = ("#111111", "#abcdef")
    palette = ("#111111", "#222222", "#333333", "#abcdef")
    assignments = []
    for index in range(11):
        recolored = ask("color_render", **base, index=index, catalog_id="x")["color_map"]
        assignments.append(tuple(recolored.get(f"recolor:{color}", color) for color in used))
    assert len(set(assignments)) == 11
    assert set(assignments) == set(itertools.permutations(palette, len(used))) - {used}
    with pytest.raises(SavedVariantRefused, match="exhausted"):
        ask("color_render", **base, index=11, catalog_id="x")


def test_no_recolorable_paints_exhausts_and_an_empty_palette_refuses():
    page = ask("color_plan", svg='<svg><path fill="none" stroke="#999999"/></svg>', color_map={"palette:a": "#111111"}, work_id="", cursor=0)
    assert {key: page[key] for key in ("entries", "next_cursor", "total")} == {"entries": [], "next_cursor": None, "total": 0}
    with pytest.raises(SavedVariantRefused, match="no usable palette"):
        ask("color_plan", svg="<svg/>", color_map={"black": "#111111"}, work_id="", cursor=0)


def test_a_page_spreads_over_the_assignments_and_is_the_work_s_own():
    palette = {f"palette:{index}": f"#{index:02x}0000" for index in range(1, 10)}
    svg = "<svg>" + "".join(f'<path fill="#{index:02x}0000"/>' for index in range(1, 5)) + "</svg>"
    used = [f"#{index:02x}0000" for index in range(1, 5)]

    def first_page(work_id):
        return [tuple(ask("color_render", svg=svg, color_map=palette, work_id=work_id, index=index, catalog_id="x")["color_map"]
                      .get(f"recolor:{color}", color) for color in used) for index in range(8)]

    page = first_page("work-a")
    for position in range(len(used)):
        assert len({assignment[position] for assignment in page}) >= 5
    assert first_page("work-a") == page
    assert first_page("work-b") != page


def test_the_ground_changes_the_material_and_keeps_the_rest():
    bare = {"version": "0.13.0", "canvas": "wide", "background": "white", "instructions": [{"primitive": "circle", "count": 1}]}
    drawn = ask("ground_render", score=bare, source="", material="canvas", language="ja")
    assert drawn["score"] == {**bare, "canvas": {"aspect": "wide", "ground": {"material": "canvas"}}}
    assert drawn["derivation_metadata"] == {"ground_material": "canvas", "parent_ground_material": "plain"}
    grounded = {**bare, "canvas": {"aspect": "wide", "ground": {"material": "washi", "tone": "white", "seed": None}}}
    assert ask("ground_render", score=grounded, source="", material="mezzotint", language="ja")["score"]["canvas"] == {
        "aspect": "wide", "ground": {"material": "mezzotint", "tone": "white", "seed": None}}
    with pytest.raises(SavedVariantRefused, match="not on"):
        ask("ground_render", score=grounded, source="", material="washi", language="ja")


def test_the_instructions_name_the_new_ground():
    score = {"canvas": "square", "instructions": []}

    def ddl(source, material, language):
        return ask("ground_render", score=score, source=source, material=material, language=language)["ddl"]

    assert ddl("画用紙。\n背景を白で埋める。", "mezzotint", "ja") == "メゾチント。\n背景を白で埋める。"
    assert ddl("Drawing paper.\nFill the background with white.", "ink_wash", "en") == "Ink wash ground.\nFill the background with white."
    assert ddl("背景を黒で埋める。", "washi", None) == "和紙。\n背景を黒で埋める。"
    assert ddl("Fill the background with blue.", "charcoal_ground", "en") == "Charcoal ground.\nFill the background with blue."


def test_the_saijiki_names_twelve_tools_with_the_pen_as_default():
    assert CASES["conditions"]["tools"] == ["silverpoint", "pencil", "pen", "rotring", "crayon", "chalk", "brush_thin",
                                            "brush_thick", "oil_paint", "burin", "drypoint", "computer"]
    assert CASES["conditions"]["default_tool"] == "pen"
