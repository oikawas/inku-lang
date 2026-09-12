import json

import pytest
from pathlib import Path

from inku_server.schema import Score


_ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "core"
    / "crates"
    / "inku-score"
    / "schema"
    / "score.schema.json"
)


def _canonical_score_schema_bytes() -> bytes:
    return json.dumps(
        Score.model_json_schema(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def test_checked_in_score_schema_matches_the_live_pydantic_model() -> None:
    artifact = _ARTIFACT_PATH.read_bytes()
    assert artifact == _canonical_score_schema_bytes()

    schema = json.loads(artifact)
    assert isinstance(schema, dict)
    properties = schema.get("properties")
    assert isinstance(properties, dict)
    assert {"version", "canvas", "background", "presence", "instructions", "anchors", "transform_groups", "placement_groups"} <= properties.keys()

    assert properties["version"]["default"] == "0.8.0"
    assert properties["version"]["enum"] == ["0.8.0", "0.7.0", "0.6.0", "0.5.0", "0.4.0", "0.3.0", "0.2.0", "0.1.0"]
    transform_group = schema["$defs"]["TransformGroup"]["properties"]
    assert {"start", "end", "rotation_degrees", "scale_x", "scale_y", "translate_x", "translate_y", "fixed_position_indices", "anchor_indices"} <= transform_group.keys()
    placement_group = schema["$defs"]["PlacementGroup"]["properties"]
    assert {"start", "end", "layout", "at"} == placement_group.keys()
    assert placement_group["layout"]["enum"] == [
        "overlap", "horizontal_source_order", "scatter", "tile"
    ]
    instruction = schema["$defs"]["Instruction"]["properties"]
    assert "point" in instruction["primitive"]["enum"]
    assert "oil_paint" in instruction["weight"]["enum"]
    assert "semantic anchor" in instruction["position"]["description"]
    relation = schema["$defs"]["Relation"]["properties"]
    assert "connected" in relation["type"]["enum"]
    assert "target_instruction_index" in relation
    assert "target_anchor_index" in relation
    assert "position_authority" in relation
    assert "touching_constraints" in relation
    assert set(schema["$defs"]["TouchingConstraints"]["required"]) == {
        "dimensions_fixed", "direction_fixed"
    }


def test_anchor_only_containment_uses_membership_and_rejects_crossing() -> None:
    data = {
        "version": "0.6.0", "instructions": [{"primitive": "line"}, {"primitive": "line"}],
        "anchors": [{"position": [0.5, 0.5]} for _ in range(3)],
        "transform_groups": [
            {"start": 0, "end": 0, "rotation_degrees": 0, "anchor_indices": [0]},
            {"start": 0, "end": 0, "rotation_degrees": 0, "anchor_indices": [1]},
            {"start": 1, "end": 2, "rotation_degrees": 0, "anchor_indices": [0, 1]},
        ],
    }
    assert len(Score.model_validate(data).transform_groups) == 3
    data["transform_groups"].reverse()
    with pytest.raises(ValueError, match="inner-before-outer"):
        Score.model_validate(data)
    data["transform_groups"] = [
        {"start": 0, "end": 0, "rotation_degrees": 0, "anchor_indices": [0, 1]},
        {"start": 0, "end": 0, "rotation_degrees": 0, "anchor_indices": [1, 2]},
    ]
    with pytest.raises(ValueError, match="cannot cross"):
        Score.model_validate(data)


def test_score08_gates_scatter_and_tile_placement_groups() -> None:
    base = {
        "instructions": [{"primitive": "circle"}, {"primitive": "square"}],
        "placement_groups": [{
            "start": 0,
            "end": 2,
            "layout": "horizontal_source_order",
            "at": {"region": [0.4, 0.4, 0.6, 0.6]},
        }],
    }
    assert Score.model_validate({"version": "0.7.0", **base}).placement_groups
    scatter = {"version": "0.7.0", **base}
    scatter["placement_groups"] = [{**base["placement_groups"][0], "layout": "scatter"}]
    with pytest.raises(ValueError, match="require Score version 0.8.0"):
        Score.model_validate(scatter)
    assert Score.model_validate({"version": "0.8.0", **scatter}).placement_groups
