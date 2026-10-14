"""Changing the support swaps the saved Score's ground and the instructions' ground sentence only."""

from inku_server.ground_variants import GROUND_MATERIALS, ddl_with_ground, score_with_ground, unused_materials


def test_a_work_is_offered_every_named_support_it_is_not_on():
    assert GROUND_MATERIALS == ("paper", "washi", "ink_wash", "charcoal_ground", "canvas", "drawing_paper", "mezzotint")
    assert unused_materials({"canvas": "square"}) == list(GROUND_MATERIALS)
    on_washi = {"canvas": {"aspect": "wide", "ground": {"material": "washi"}}}
    assert unused_materials(on_washi) == [m for m in GROUND_MATERIALS if m != "washi"]


def test_only_the_ground_material_changes_in_the_score():
    instructions = [{"primitive": "circle", "count": 1}]
    bare = {"version": "0.13.0", "canvas": "wide", "background": "white", "instructions": instructions}
    changed = score_with_ground(bare, "canvas")
    assert changed == {**bare, "canvas": {"aspect": "wide", "ground": {"material": "canvas"}}}
    assert bare["canvas"] == "wide"
    grounded = {**bare, "canvas": {"aspect": "wide", "ground": {"material": "washi", "tone": "white", "seed": None}}}
    assert score_with_ground(grounded, "mezzotint")["canvas"] == {
        "aspect": "wide", "ground": {"material": "mezzotint", "tone": "white", "seed": None}}


def test_the_instructions_name_the_new_ground():
    assert ddl_with_ground("画用紙。\n背景を白で埋める。", "mezzotint", "ja") == "メゾチント。\n背景を白で埋める。"
    assert ddl_with_ground("Drawing paper.\nFill the background with white.", "ink_wash", "en") == (
        "Ink wash ground.\nFill the background with white.")
    # Without a ground sentence, one is placed first in the instructions' language.
    assert ddl_with_ground("背景を黒で埋める。", "washi", None) == "和紙。\n背景を黒で埋める。"
    assert ddl_with_ground("Fill the background with blue.", "charcoal_ground", "en") == (
        "Charcoal ground.\nFill the background with blue.")
