use inku_score::{SCORE_SCHEMA_DIGEST_DOMAIN, score_schema_bytes, score_schema_digest};
use serde_json::Value;
use sha2::{Digest, Sha256};

const EXPECTED_SCHEMA_DIGEST: &str =
    "b89cb89d4fc23b325f8d790a77392bcd48ba439160d60516742972d7df24c0a7";

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
    ] {
        assert!(
            properties.contains_key(required),
            "missing {required} property"
        );
    }

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
