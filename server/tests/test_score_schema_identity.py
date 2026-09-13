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


def test_score11_keeps_explicit_path_contact_and_rejects_older_editions() -> None:
    from copy import deepcopy

    data = {
        "version": "0.11.0",
        "instructions": [
            {"primitive": "line"}, {"primitive": "point"},
            {"primitive": "arc", "relation": {
                "type": "connected", "target_instruction_index": 0,
                "target_path_position": 0.375, "position_authority": "named_movable",
            }},
        ],
    }
    score = Score.model_validate(data)
    assert score.resource_policy is None
    assert score.model_dump()["instructions"][2]["relation"]["target_path_position"] == 0.375
    with pytest.raises(ValueError, match="target_path_position requires Score version 0.11.0"):
        Score.model_validate({**data, "version": "0.10.0"})
    invalid = deepcopy(data)
    invalid["instructions"][2]["relation"]["type"] = "along"
    with pytest.raises(ValueError, match="requires Connected"):
        Score.model_validate(invalid)


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
    assert {"version", "canvas", "background", "presence", "instructions", "anchors", "transform_groups", "placement_groups", "repetition_groups", "fill_groups", "resource_policy"} <= properties.keys()

    assert properties["version"]["default"] == "0.9.0"
    assert properties["version"]["enum"] == ["0.11.0", "0.10.0", "0.9.0", "0.8.0", "0.7.0", "0.6.0", "0.5.0", "0.4.0", "0.3.0", "0.2.0", "0.1.0"]
    transform_group = schema["$defs"]["TransformGroup"]["properties"]
    assert {"start", "end", "rotation_degrees", "scale_x", "scale_y", "translate_x", "translate_y", "fixed_position_indices", "anchor_indices"} <= transform_group.keys()
    placement_group = schema["$defs"]["PlacementGroup"]["properties"]
    assert {"start", "end", "layout", "at", "members", "resolved"} == placement_group.keys()
    assert placement_group["layout"]["enum"] == [
        "overlap", "horizontal_source_order", "scatter", "tile"
    ]
    placement_member = schema["$defs"]["PlacementMember"]["properties"]
    assert {"start", "end", "anchor_indices", "transform_group_indices", "symbolic"} == placement_member.keys()
    instruction = schema["$defs"]["Instruction"]["properties"]
    assert "point" in instruction["primitive"]["enum"]
    assert "oil_paint" in instruction["weight"]["enum"]
    assert "semantic anchor" in instruction["position"]["description"]
    relation = schema["$defs"]["Relation"]["properties"]
    assert "connected" in relation["type"]["enum"]
    assert "target_instruction_index" in relation
    assert "target_anchor_index" in relation
    assert "position_authority" in relation
    assert "target_path_position" in relation
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
    assert Score.model_validate({**scatter, "version": "0.8.0"}).placement_groups


def test_score09_placement_members_are_atomic_and_edition_gated() -> None:
    data = {
        "version": "0.9.0",
        "instructions": [{"primitive": "circle"}, {"primitive": "square"}],
        "anchors": [{"position": [0.5, 0.5]}],
        "transform_groups": [{"start": 1, "end": 2, "rotation_degrees": 10.0}],
        "placement_groups": [{
            "start": 0, "end": 2, "layout": "overlap",
            "at": {"region": [0.4, 0.4, 0.6, 0.6]},
            "members": [
                {"start": 0, "end": 1},
                {"start": 1, "end": 2, "anchor_indices": [0], "transform_group_indices": [0]},
            ],
        }],
    }
    assert Score.model_validate(data).placement_groups[0].members
    with pytest.raises(ValueError, match="require Score version 0.9.0"):
        Score.model_validate({**data, "version": "0.8.0"})


def test_score010_compact_recipe_reads_without_changing_the_default_edition() -> None:
    maximum = {
        "logical_objects": 400,
        "primitive_marks": 400,
        "object_templates": 64,
        "maximum_per_template_primitive_marks": 240,
        "maximum_resolved_count": 2000,
        "template_nodes": 400,
        "anchor_instances": 400,
        "transform_instances": 400,
        "placement_instances": 400,
        "fill_instances": 400,
    }
    score = Score.model_validate({
        "version": "0.10.0",
        "instructions": [{
            "primitive": "point",
            "arrangement": {
                "count": 1,
                "resolved": {
                    "owner": {"kind": "source_instruction", "instruction_index": 0},
                    "first_instance_ordinal": 0,
                    "count_origin": {"kind": "explicit"},
                    "domain": [1.0, 1.0],
                    "anchor": {"kind": "numeric", "point": [0.5, 0.5]},
                    "recipe": {"kind": "place"},
                    "ordinal_scheme": "source_member_then_instance_v1",
                },
            },
        }],
        "resource_policy": {
            "accounting_id": "inku.resource-accounting.v1",
            "hard_policy": {"identity": "shipping-v1", "budget": {"maximum": maximum}},
            "operational_budget": {"maximum": maximum},
        },
    })

    assert score.version == "0.10.0"
    assert score.instructions[0].arrangement.resolved.recipe.kind == "place"
    assert Score.model_fields["version"].default == "0.9.0"
