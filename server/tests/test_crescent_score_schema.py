import json

import pytest
from pydantic import ValidationError

from inku_server.limits import DEFAULT_LIMITS
from inku_server.saved_score_compat import coerce_saved_score
from inku_server.schema import Instruction, Score


def test_crescent_descriptor_survives_the_active_score_dto() -> None:
    score = Score.model_validate(
        {
            "version": "0.2.0",
            "instructions": [
                {
                    "primitive": "arc",
                    "arc_form": "crescent",
                    "center": [0.5, 0.5],
                    "size": [0.2, 0.257256],
                    "rotation": 30,
                    "filled": True,
                }
            ],
        }
    )
    payload = score.model_dump(mode="json", by_alias=True)
    assert payload["version"] == "0.2.0"
    assert payload["instructions"][0]["arc_form"] == "crescent"

    legacy = Score.model_validate({"version": "0.1.0", "instructions": [{"primitive": "line"}]})
    legacy_payload = json.loads(legacy.model_dump_json(by_alias=True))
    assert legacy_payload["version"] == "0.1.0"
    assert "arc_form" not in legacy_payload["instructions"][0]


@pytest.mark.parametrize(
    "instruction",
    [
        {"primitive": "circle", "arc_form": "crescent", "center": [0.5, 0.5], "size": [0.2, 0.25], "filled": True},
        {"primitive": "arc", "arc_form": "crescent", "center": [0.5, 0.5], "size": [0.2, 0.25], "filled": False},
        {"primitive": "arc", "arc_form": "crescent", "center": [0.5, 0.5], "size": [0.2, 0.25], "filled": True, "radius": 0.1},
        {"primitive": "arc", "arc_form": "crescent", "center": [0.5, 0.5], "size": [0.0, 0.25], "filled": True},
    ],
)
def test_crescent_rejects_incompatible_open_arc_geometry(instruction: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Score.model_validate({"version": "0.2.0", "instructions": [instruction]})


def test_crescent_requires_the_score_edition_that_introduced_it() -> None:
    with pytest.raises(ValidationError, match="arc_form requires Score version 0.2.0"):
        Score.model_validate(
            {
                "version": "0.1.0",
                "instructions": [
                    {
                        "primitive": "arc",
                        "arc_form": "crescent",
                        "center": [0.5, 0.5],
                        "size": [0.2, 0.2572564393705176],
                        "filled": True,
                    }
                ],
            }
        )


def test_crescent_coercion_preserves_its_physical_box() -> None:
    crescent = Instruction.model_validate(
        {
            "primitive": "arc",
            "arc_form": "crescent",
            "center": [0.5, 0.5],
            "size": [0.2, 0.2572564393705176],
            "filled": True,
        }
    )

    coerced = coerce_saved_score(
        Score(version="0.2.0", instructions=[crescent]), limits=DEFAULT_LIMITS
    ).instructions[0]

    assert coerced.arc_form == "crescent"
    assert coerced.center == (0.5, 0.5)
    assert coerced.size == (0.2, 0.2572564393705176)
    assert coerced.radius is None
    assert coerced.angle_start is None
    assert coerced.angle_end is None
