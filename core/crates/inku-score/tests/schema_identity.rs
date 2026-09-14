use inku_score::{SCORE_SCHEMA_DIGEST_DOMAIN, score_schema_bytes, score_schema_digest};
use serde_json::Value;
use sha2::{Digest, Sha256};

const EXPECTED_SCHEMA_DIGEST: &str =
    "9c536bfe51507f5ce13e3cec4670e9a25a86e5a53e82f0d1ff275f45abf69d72";

#[test]
fn canonical_score_schema_identity_is_stable() {
    let artifact = include_bytes!("../schema/score.schema.json");
    assert_eq!(score_schema_bytes(), artifact, "public schema bytes");

    let schema: Value = serde_json::from_slice(artifact).expect("schema JSON must parse");
    let properties = schema
        .as_object()
        .and_then(|root| root.get("properties"))
        .and_then(Value::as_object)
        .expect("schema root properties must be an object");
    for required in [
        "version",
        "canvas",
        "background",
        "presence",
        "instructions",
        "transform_groups",
        "placement_groups",
        "repetition_groups",
        "fill_groups",
        "resource_policy",
    ] {
        assert!(
            properties.contains_key(required),
            "missing {required} property"
        );
    }

    let placement_group = schema["$defs"]["PlacementGroup"]["properties"]
        .as_object()
        .expect("PlacementGroup properties must be an object");
    for required in ["start", "end", "layout", "at", "members", "resolved"] {
        assert!(
            placement_group.contains_key(required),
            "missing PlacementGroup property {required}"
        );
    }
    assert_eq!(
        placement_group["layout"]["enum"],
        serde_json::json!(["overlap", "horizontal_source_order", "scatter", "tile"])
    );
    let placement_member = schema["$defs"]["PlacementMember"]["properties"]
        .as_object()
        .expect("PlacementMember properties must be an object");
    for required in [
        "start",
        "end",
        "anchor_indices",
        "transform_group_indices",
        "symbolic",
    ] {
        assert!(
            placement_member.contains_key(required),
            "missing PlacementMember property {required}"
        );
    }
    let fill_group = schema["$defs"]["FillGroup"]["properties"]
        .as_object()
        .expect("FillGroup properties must be an object");
    for required in [
        "start",
        "end",
        "owner",
        "logical_count",
        "recipe",
        "target",
        "boundary",
        "ordinal_scheme",
        "members",
    ] {
        assert!(
            fill_group.contains_key(required),
            "missing FillGroup property {required}"
        );
    }
    let resource_policy = schema["$defs"]["ScoreResourcePolicy"]["properties"]
        .as_object()
        .expect("ScoreResourcePolicy properties must be an object");
    assert!(resource_policy.contains_key("accounting_id"));
    assert!(resource_policy.contains_key("hard_policy"));
    assert!(resource_policy.contains_key("operational_budget"));

    let instruction = schema["$defs"]["Instruction"]["properties"]
        .as_object()
        .expect("Instruction properties must be an object");
    assert!(
        instruction["primitive"]["enum"]
            .as_array()
            .expect("primitive enum")
            .iter()
            .any(|value| value == "point")
    );
    assert!(
        instruction["position"]["description"]
            .as_str()
            .expect("position description")
            .contains("semantic anchor")
    );
    assert_eq!(instruction["arc_form"]["default"], Value::Null);
    assert_eq!(instruction["arc_form"]["anyOf"][0]["const"], "crescent");
    assert_eq!(instruction["ink_spread"]["default"], Value::Null);
    assert_eq!(instruction["ink_spread"]["anyOf"][0]["const"], "bleed");
    let relation = schema["$defs"]["Relation"]["properties"]
        .as_object()
        .expect("Relation properties must be an object");
    assert!(
        relation["type"]["enum"]
            .as_array()
            .expect("relation enum")
            .iter()
            .any(|value| value == "connected")
    );
    assert!(relation.contains_key("target_instruction_index"));
    assert!(relation.contains_key("position_authority"));
    assert_eq!(relation["target_endpoint"]["default"], Value::Null);
    assert_eq!(
        relation["target_endpoint"]["anyOf"][0]["enum"],
        serde_json::json!(["start", "end"])
    );

    let transform_group = schema["$defs"]["TransformGroup"]["properties"]
        .as_object()
        .expect("TransformGroup properties must be an object");
    for required in [
        "start",
        "end",
        "rotation_degrees",
        "scale_x",
        "scale_y",
        "translate_x",
        "translate_y",
        "fixed_position_indices",
    ] {
        assert!(
            transform_group.contains_key(required),
            "missing TransformGroup property {required}"
        );
    }

    assert_eq!(SCORE_SCHEMA_DIGEST_DOMAIN, "inku.score.schema.v1");
    let mut hasher = Sha256::new();
    hasher.update(SCORE_SCHEMA_DIGEST_DOMAIN.as_bytes());
    hasher.update([0]);
    hasher.update((artifact.len() as u64).to_be_bytes());
    hasher.update(artifact);
    let digest = hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    assert_eq!(digest, EXPECTED_SCHEMA_DIGEST);
    assert_eq!(score_schema_digest(), EXPECTED_SCHEMA_DIGEST);
}
