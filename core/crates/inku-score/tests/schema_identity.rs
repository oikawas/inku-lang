use inku_score::{SCORE_SCHEMA_DIGEST_DOMAIN, score_schema_bytes, score_schema_digest};
use serde_json::Value;
use sha2::{Digest, Sha256};

const EXPECTED_SCHEMA_DIGEST: &str =
    "15d467bdc3adf1523040e827c3721cbdb47e785af12aed55d8000dbfe3436ad8";

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

    assert_eq!(SCORE_SCHEMA_DIGEST_DOMAIN, "inku.score.schema.v1");
    let mut hasher = Sha256::new();
    hasher.update(SCORE_SCHEMA_DIGEST_DOMAIN.as_bytes());
    hasher.update([0]);
    hasher.update((artifact.len() as u64).to_be_bytes());
    hasher.update(artifact);
    assert_eq!(format!("{:x}", hasher.finalize()), EXPECTED_SCHEMA_DIGEST);
    assert_eq!(score_schema_digest(), EXPECTED_SCHEMA_DIGEST);
}
