"""`hair` -> `silverpoint`: the name moved, the tool did not.

`hair` named a material nobody draws with, and the physics filed under it —
hard, no width response, almost no sway — is a silverpoint. The rename is a
replacement, not a second entry, and it must not carry any change of value with
it: if a number moves under cover of the rename, these tests are where it shows.

Saved Scores hold the old name (445 works / 583 instructions on 2026-07-27), so
`Instruction` replaces it on the way in. Replacing is not the same as dropping:
dropping would take the tool away and silently fall back to `pen`.
"""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from inku_server.renderer import WEIGHT_STYLE, WEIGHT_TO_STROKE_WIDTH
from inku_server.schema import Score, Weight
from inku_server.stroke_engine import GRAMMARS


def _score(weight: str) -> Score:
    return Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5], "weight": weight}
            ]
        }
    )


# --- the enum holds one name, not two ---------------------------------------


def test_the_weight_enum_replaced_the_name_rather_than_adding_one() -> None:
    weights = get_args(Weight)
    assert "silverpoint" in weights
    assert "hair" not in weights
    assert len(weights) == 11


def test_every_table_the_tool_lives_in_moved_with_it() -> None:
    for table in (WEIGHT_TO_STROKE_WIDTH, WEIGHT_STYLE, GRAMMARS):
        assert "silverpoint" in table
        assert "hair" not in table


# --- saved Scores keep the tool, under the new name -------------------------


def test_saved_scores_written_as_hair_replay_as_silverpoint() -> None:
    assert _score("hair").instructions[0].weight == "silverpoint"


def test_the_old_name_is_replaced_and_not_dropped() -> None:
    """A drop would validate too — and quietly hand the line to `pen` instead."""
    assert _score("hair").instructions[0].weight != Score.model_validate(
        {"instructions": [{"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5]}]}
    ).instructions[0].weight


def test_the_replacement_is_the_only_spelling_accepted() -> None:
    """Nothing else slips through the `before` validator into the enum."""
    for spelling in ("Hair", "hairs", "silver-point", "silver point", "metalpoint"):
        with pytest.raises(ValidationError):
            _score(spelling)


# --- the physics is unchanged (契約 A-4) ------------------------------------


def test_the_stroke_width_did_not_move() -> None:
    assert WEIGHT_TO_STROKE_WIDTH["silverpoint"] == 0.5


def test_the_stroke_attributes_did_not_move() -> None:
    assert WEIGHT_STYLE["silverpoint"] == {"stroke_opacity": 0.72, "stroke_linecap": "butt"}


def test_the_eight_grammar_values_did_not_move() -> None:
    grammar = GRAMMARS["silverpoint"]
    assert (
        grammar.stiffness,
        grammar.damping,
        grammar.energy_width,
        grammar.energy_lateral,
        grammar.event_rate,
        grammar.taper,
        grammar.bulge,
        grammar.gesture,
    ) == (0.93, 0.90, 0.08, 0.05, 0.04, 0.05, 0.02, 0.012)
    # The machine-pole extras belong to `computer`; the silverpoint never had them.
    assert grammar.periodic is False
    assert grammar.quantize == 0.0
    assert grammar.width_steps == 0


def test_it_still_sits_just_inside_the_machine_pole() -> None:
    """Harder and steadier than every hand tool, and short of `rotring`'s zero.

    This is the reading that made the rename: the tool is not a brush at all.
    """
    hand_tools = {
        name: g for name, g in GRAMMARS.items() if name not in ("rotring", "computer")
    }
    silverpoint = GRAMMARS["silverpoint"]
    assert silverpoint.gesture == min(g.gesture for g in hand_tools.values())
    assert silverpoint.gesture > GRAMMARS["rotring"].gesture
    assert silverpoint.energy_width == min(g.energy_width for g in hand_tools.values())
    assert WEIGHT_TO_STROKE_WIDTH["silverpoint"] < WEIGHT_TO_STROKE_WIDTH["rotring"]
