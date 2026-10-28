use inku_score::Score;
use serde_json::{Value, json};

#[test]
fn templates_require_the_new_edition_and_a_unique_square_owner() {
    let body = json!({"version":"0.9.0", "instructions":[]});
    let wire = json!({"version":"0.23.0", "instructions":[{"primitive":"square"}],
        "object_templates":[{"instruction_index":0,"aspect":[2,1],"body":body}]});
    let score: Score = serde_json::from_value(wire.clone()).unwrap();
    assert!(score.validate_schema_edition().is_ok());
    let round_trip: Value = serde_json::to_value(&score).unwrap();
    assert_eq!(round_trip["object_templates"][0]["aspect"], json!([2, 1]));
    let mut old = wire.clone();
    old["version"] = json!("0.22.0");
    let old: Score = serde_json::from_value(old).unwrap();
    assert!(old.validate_schema_edition().is_err());
    let mut duplicate = wire.clone();
    duplicate["object_templates"] =
        json!([wire["object_templates"][0], wire["object_templates"][0]]);
    let duplicate: Score = serde_json::from_value(duplicate).unwrap();
    assert!(duplicate.validate_schema_edition().is_err());
    let mut wrong = wire;
    wrong["instructions"][0]["primitive"] = json!("circle");
    let wrong: Score = serde_json::from_value(wrong).unwrap();
    assert!(wrong.validate_schema_edition().is_err());
    let legacy: Score =
        serde_json::from_value(json!({"version":"0.22.0", "instructions":[]})).unwrap();
    assert!(legacy.validate_schema_edition().is_ok());
    assert!(
        serde_json::to_value(legacy)
            .unwrap()
            .get("object_templates")
            .is_none()
    );
}
