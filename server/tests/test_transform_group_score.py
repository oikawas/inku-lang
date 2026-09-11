import json

import pytest
from pydantic import ValidationError

from inku_server.schema import Score


def test_old_and_transform_group_scores_roundtrip_without_dropping_metadata() -> None:
    old = Score.model_validate({"version": "0.3.0", "instructions": [{"primitive": "line"}]})
    assert old.model_dump(mode="json", exclude_none=True)["version"] == "0.3.0"

    score = Score.model_validate(
        {
            "version": "0.4.0",
            "instructions": [{"primitive": "line"}, {"primitive": "line"}],
            "transform_groups": [
                {
                    "start": 0,
                    "end": 2,
                    "rotation_degrees": 90.0,
                    "fixed_position_indices": [1],
                }
            ],
        }
    )
    payload = json.loads(score.model_dump_json(exclude_none=True))
    assert payload["transform_groups"] == [
        {"start": 0, "end": 2, "rotation_degrees": 90.0, "fixed_position_indices": [1]}
    ]


@pytest.mark.parametrize(
    "groups",
    [
        [{"start": 0, "end": 0, "rotation_degrees": 0.0}],
        [
            {"start": 0, "end": 2, "rotation_degrees": 0.0},
            {"start": 1, "end": 3, "rotation_degrees": 0.0},
        ],
        [
            {"start": 0, "end": 2, "rotation_degrees": 0.0, "fixed_position_indices": [1]},
            {"start": 0, "end": 2, "rotation_degrees": 0.0},
        ],
    ],
)
def test_transform_groups_reject_malformed_ranges_and_fixed_metadata(groups: list[dict]) -> None:
    with pytest.raises(ValidationError):
        Score.model_validate(
            {
                "version": "0.4.0",
                "instructions": [{"primitive": "line"}] * 3,
                "transform_groups": groups,
            }
        )
