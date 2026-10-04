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


def test_score12_independent_spread_and_selected_endpoint_preserve_legacy_meaning() -> None:
    relation = {
        "type": "connected", "target_instruction_index": 0,
        "target_endpoint": "start", "position_authority": "named_movable",
    }
    data = {
        "version": "0.12.0", "instructions": [
            {"primitive": "arc"},
            {"primitive": "line", "ink_spread": "bleed", "relation": relation,
             "variation": {"quality": "wave"}, "surface": {"texture": "stipple"}},
        ],
    }
    result = Score.model_validate(data).model_dump()
    mark = result["instructions"][1]
    assert mark["ink_spread"] == "bleed"
    assert mark["variation"]["quality"] == "wave"
    assert mark["surface"]["texture"] == "stipple"
    assert mark["relation"]["target_endpoint"] == "start"
    # A flat Score has no policy, and the dump omits it as the Rust Score does.
    assert "resource_policy" not in result
    with pytest.raises(ValueError, match="require Score version 0.12.0"):
        Score.model_validate({**data, "version": "0.11.0"})
    with pytest.raises(ValueError, match="are exclusive"):
        Score.model_validate({**data, "instructions": [data["instructions"][0], {
            **data["instructions"][1],
            "relation": {**relation, "target_path_position": 0.0},
        }]})
    legacy = Score.model_validate({
        "version": "0.9.0", "instructions": [{"primitive": "circle",
            "variation": {"quality": "pink"}, "surface": {"texture": "bleed"}}],
    }).model_dump()["instructions"][0]
    assert "ink_spread" not in legacy
    assert legacy["variation"]["quality"] == "pink"
    assert legacy["surface"]["texture"] == "bleed"


def test_score13_keeps_interior_symbolic_and_preserves_numeric_positions() -> None:
    relation = {
        "type": "connected", "target_instruction_index": 0,
        "target_path_position": "interior", "position_authority": "named_movable",
    }
    data = {"version": "0.13.0", "instructions": [
        {"primitive": "arc"}, {"primitive": "line", "relation": relation},
    ]}
    result = Score.model_validate(data).model_dump()
    assert result["instructions"][1]["relation"]["target_path_position"] == "interior"
    # A flat Score has no policy, and the dump omits it as the Rust Score does.
    assert "resource_policy" not in result
    with pytest.raises(ValueError, match="requires Score version 0.13.0"):
        Score.model_validate({**data, "version": "0.12.0"})
    with pytest.raises(ValueError, match="are exclusive"):
        Score.model_validate({**data, "instructions": [data["instructions"][0], {
            "primitive": "line", "relation": {**relation, "target_endpoint": "end"},
        }]})
    from inku_server.schema import Relation

    assert Relation.model_validate({**relation, "target_path_position": 0.375}).model_dump()["target_path_position"] == 0.375
    with pytest.raises(ValueError):
        Relation.model_validate({**relation, "target_path_position": "center"})


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
    assert {"version", "canvas", "background", "presence", "instructions", "anchors", "transform_groups", "placement_groups", "repetition_groups", "fill_groups", "mirror_relations", "resource_policy"} <= properties.keys()

    assert properties["version"]["default"] == "0.9.0"
    assert properties["version"]["enum"] == ["0.19.0", "0.18.0", "0.17.0", "0.16.0", "0.15.0", "0.14.0", "0.13.0", "0.12.0", "0.11.0", "0.10.0", "0.9.0", "0.8.0", "0.7.0", "0.6.0", "0.5.0", "0.4.0", "0.3.0", "0.2.0", "0.1.0"]
    transform_group = schema["$defs"]["TransformGroup"]["properties"]
    assert {"start", "end", "rotation_degrees", "scale_x", "scale_y", "translate_x", "translate_y", "fixed_position_indices", "anchor_indices"} <= transform_group.keys()
    placement_group = schema["$defs"]["PlacementGroup"]["properties"]
    assert {"start", "end", "layout", "at", "members", "resolved", "cycle_members"} == placement_group.keys()
    assert placement_group["layout"]["enum"] == [
        "overlap", "horizontal_source_order", "scatter", "tile", "cells"
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


def test_score16_gates_the_thick_side_of_thinness() -> None:
    for thinness in ("thick", "extra_thick"):
        data = {"version": "0.16.0", "instructions": [{"primitive": "line", "thinness": thinness}]}
        assert Score.model_validate(data).instructions[0].thinness == thinness
        with pytest.raises(ValueError, match="thick thinness requires Score version 0.16.0"):
            Score.model_validate({**data, "version": "0.15.0"})


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


# Compiled by core from 「下（横0〜1、縦2/3〜1）に、赤い円を三つ埋める。」.
_NUMERIC_FILL_RANGE_SCORE = json.loads(
    '{"background":"white","canvas":"square","fill_groups":[{"boundary":"clip_to_target","end":1,"logical_count":3,"members":[{"end":1,"start":0,"symbolic":{"count_origin":{"kind":"explicit"},"first_instance_ordinal":0,"instance_count":3,"kind":"primitive","member_ordinal":0,"owner":{"instruction_index":0,"kind":"source_instruction"}}}],"ordinal_scheme":"source_member_then_instance_v1","owner":{"kind":"instruction","source_instruction_index":0},"recipe":"uniform_in_region","start":0,"target":{"geometry":{"bounds":[0.0,0.6666666666666666,1.0,1.0],"kind":"rectangle"},"owner":{"kind":"numeric_range","source":{"clause_index":0,"region_index":0}},"reference_area":0.3333333333333333}}],"instructions":[{"angle_end":null,"angle_start":null,"arrangement":{"center":null,"cluster_count":null,"color_cycle":[],"cols":null,"count":1,"density":"none","fade":"none","group_size":1,"jitter":0.0,"layout":"horizontal","margin":0.0,"path":"none","preserve_space":false,"radius":null,"resolved":{"anchor":{"kind":"enclosing_group"},"count_origin":{"kind":"template_single"},"domain":[1.0,1.0],"first_instance_ordinal":0,"ordinal_scheme":"source_member_then_instance_v1","owner":{"instruction_index":0,"kind":"source_instruction"},"recipe":{"kind":"place"}},"rhythm_spacing":"none","rows":null},"at":{"region":[0.5,0.5,0.5,0.5]},"carve_depth":null,"center":null,"color":"red","color_hint":null,"filled":true,"from":null,"mode":"additive","note":null,"position":null,"primitive":"circle","radius":0.12,"relation":null,"rotation":null,"sides":null,"size":null,"style":"solid","surface":null,"thinness":null,"to":null,"variation":null,"weight":"pen"}],"presence":null,"resource_policy":{"accounting_id":"inku.resource-accounting.v1","hard_policy":{"budget":{"maximum":{"anchor_instances":400,"fill_instances":400,"logical_objects":400,"maximum_per_template_primitive_marks":240,"maximum_resolved_count":2000,"object_templates":64,"placement_instances":400,"primitive_marks":400,"template_nodes":400,"transform_instances":400}},"identity":"shipping-v1"},"operational_budget":{"maximum":{"anchor_instances":400,"fill_instances":400,"logical_objects":400,"maximum_per_template_primitive_marks":240,"maximum_resolved_count":2000,"object_templates":64,"placement_instances":400,"primitive_marks":400,"template_nodes":400,"transform_instances":400}}},"version":"0.18.0"}'
)


def test_score18_records_a_fill_range_written_in_numbers() -> None:
    score = Score.model_validate(_NUMERIC_FILL_RANGE_SCORE)
    assert score.version == "0.18.0"
    assert score.fill_groups[0].target.owner.kind == "numeric_range"
    with pytest.raises(ValueError, match="fill target numeric_range requires Score version 0.18.0"):
        Score.model_validate({**_NUMERIC_FILL_RANGE_SCORE, "version": "0.17.0"})


# Compiled by core (DDL engine 57) from 「Nature.紅葉を3枚置く。」: the three
# copies of the maple leaf are one member of a cells placement group (I-708).
_CELLS_SCORE = json.loads(
    (Path(__file__).parent / "data" / "score-0.19-maple-leaves-in-cells.json").read_text(encoding="utf-8")
)


def test_score19_places_the_copies_of_a_word_in_cells() -> None:
    from copy import deepcopy

    score = Score.model_validate(_CELLS_SCORE)
    assert score.version == "0.19.0"
    group = score.placement_groups[0]
    assert group.layout == "cells"
    assert group.resolved.recipe.kind == "cells"
    assert group.members[0].symbolic.instance_count == 3
    with pytest.raises(ValueError, match="cells placement_groups require Score version 0.19.0"):
        Score.model_validate({**_CELLS_SCORE, "version": "0.18.0"})
    unpaired = deepcopy(_CELLS_SCORE)
    unpaired["placement_groups"][0]["resolved"]["recipe"] = {
        "kind": "scatter_uniform_with_centroid_translation"
    }
    with pytest.raises(ValueError, match="cells placement_groups require the resolved cells recipe"):
        Score.model_validate(unpaired)
    template = deepcopy(_CELLS_SCORE)
    template["instructions"][0]["arrangement"]["resolved"]["recipe"] = {"kind": "cells"}
    with pytest.raises(ValueError, match="cells recipes belong to cells placement_groups"):
        Score.model_validate(template)


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
