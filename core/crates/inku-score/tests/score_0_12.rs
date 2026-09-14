use inku_score::{
    Endpoint, InkSpread, Instruction, Score, TargetPathPosition, read_saved_score_json,
};

#[test]
fn new_optional_fields_are_omitted_and_gated_by_score_0_12() {
    let legacy: Instruction = serde_json::from_str(r#"{"primitive":"line"}"#).unwrap();
    let legacy_json = serde_json::to_value(legacy).unwrap();
    assert!(legacy_json.get("ink_spread").is_none());

    let mut score: Score = serde_json::from_str(
        r#"{"version":"0.12.0","instructions":[
          {"primitive":"arc","center":[0.5,0.5],"radius":0.2,
           "angle_start":0,"angle_end":180},
          {"primitive":"line","from":[0.2,0.2],"to":[0.3,0.3],
           "ink_spread":"bleed",
           "relation":{"type":"connected","target_instruction_index":0,
                       "target_endpoint":"start"}}
        ]}"#,
    )
    .unwrap();
    assert_eq!(score.instructions[1].ink_spread, Some(InkSpread::Bleed));
    assert_eq!(
        score.instructions[1]
            .relation
            .as_ref()
            .unwrap()
            .target_endpoint,
        Some(Endpoint::Start)
    );
    assert_eq!(score.validate_schema_edition(), Ok(()));
    assert!(
        read_saved_score_json(&serde_json::to_vec(&score).unwrap()).is_ok(),
        "saved Score 0.12 must remain replayable"
    );

    score.instructions[1]
        .relation
        .as_mut()
        .unwrap()
        .target_path_position = Some(TargetPathPosition::Exact(0.5));
    assert_eq!(
        score.validate_schema_edition(),
        Err("relation target path position and endpoint are exclusive")
    );

    score.instructions[1]
        .relation
        .as_mut()
        .unwrap()
        .target_path_position = None;
    score.version = "0.11.0".to_owned();
    assert_eq!(
        score.validate_schema_edition(),
        Err("relation target_endpoint requires Score version 0.12.0")
    );
    score.instructions[1].relation = None;
    assert_eq!(
        score.validate_schema_edition(),
        Err("ink_spread requires Score version 0.12.0")
    );
}
