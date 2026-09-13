use std::collections::HashSet;

use inku_score::{
    Primitive, Score, canonical_json_bytes, canonical_score_digest, read_saved_score_json,
};
use serde::Deserialize;
use serde_json::Value;

#[derive(Debug, Deserialize)]
struct FixtureFile {
    cases: Vec<SuccessCase>,
    invalid_cases: Vec<InvalidCase>,
}

#[derive(Debug, Deserialize)]
struct SuccessCase {
    id: String,
    input: Value,
    canonical_json: String,
    digest: String,
}

#[derive(Debug, Deserialize)]
struct InvalidCase {
    id: String,
    input: Value,
}

fn fixtures() -> FixtureFile {
    serde_json::from_str(include_str!("fixtures/saved-score-compatibility.json"))
        .expect("compatibility fixture JSON must parse")
}

#[test]
fn saved_score_compatibility_fixtures_preserve_canonical_identity() {
    let fixtures = fixtures();
    let ids = fixtures
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .chain(fixtures.invalid_cases.iter().map(|case| case.id.as_str()))
        .collect::<HashSet<_>>();
    assert_eq!(
        ids.len(),
        fixtures.cases.len() + fixtures.invalid_cases.len(),
        "fixture IDs must be unique"
    );

    for case in fixtures.cases {
        let input = serde_json::to_vec(&case.input).expect("fixture input must serialize");
        let score = read_saved_score_json(&input).expect("saved fixture must parse");
        let canonical = canonical_json_bytes(&score).expect("Score must canonicalize");

        assert_eq!(
            canonical,
            case.canonical_json.as_bytes(),
            "{} bytes",
            case.id
        );
        assert_eq!(
            canonical_score_digest(&score).expect("Score must digest"),
            case.digest,
            "{} digest",
            case.id
        );

        let reread = read_saved_score_json(&canonical).expect("canonical Score must reread");
        assert_eq!(reread, score, "{} reread semantics", case.id);
        assert_eq!(
            canonical_json_bytes(&reread).expect("reread Score must canonicalize"),
            canonical,
            "{} reread bytes",
            case.id
        );

        if case.id == "current-valid" {
            let direct: Score = serde_json::from_slice(&input).expect("current Score must parse");
            assert_eq!(score, direct, "current Score must remain unchanged");
        }
    }
}

#[test]
fn saved_score_compatibility_rejects_invalid_artifacts() {
    for case in fixtures().invalid_cases {
        let input = serde_json::to_vec(&case.input).expect("fixture input must serialize");
        assert!(
            read_saved_score_json(&input).is_err(),
            "{} must be rejected",
            case.id
        );
    }
    assert!(
        read_saved_score_json(b"{").is_err(),
        "malformed JSON must be rejected"
    );
}

#[test]
fn crescent_is_rejected_when_mislabeled_as_score_0_1() {
    let source = br#"{"version":"0.1.0","instructions":[{
        "primitive":"arc","arc_form":"crescent","center":[0.5,0.5],
        "size":[0.2,0.2572564393705176],"filled":true
    }]}"#;
    assert!(read_saved_score_json(source).is_err());

    let direct: Score = serde_json::from_slice(source).expect("typed Score can inspect input");
    assert!(canonical_json_bytes(&direct).is_err());
}

#[test]
fn canonical_score_rejects_crescent_open_arc_geometry() {
    let source = br#"{"version":"0.2.0","instructions":[{
        "primitive":"arc","arc_form":"crescent","center":[0.5,0.5],
        "size":[0.2,0.2572564393705176],"radius":0.1,"filled":true
    }]}"#;
    let direct: Score = serde_json::from_slice(source).expect("typed Score can inspect input");
    assert!(canonical_json_bytes(&direct).is_err());
    assert!(read_saved_score_json(source).is_err());
}

#[test]
fn point_roundtrips_while_an_old_arc_keeps_the_absent_semantic_anchor() {
    let source = br#"{"instructions":[
        {"primitive":"point","center":[0.25,0.4],"radius":0.006,"filled":true},
        {"primitive":"arc","center":[0.5,0.59],"radius":0.15,
         "angle_start":143.13010235415598,"angle_end":36.86989764584402}
    ]}"#;
    let score = read_saved_score_json(source).expect("endpoint-family Score must parse");
    assert_eq!(score.instructions[0].primitive, Primitive::Point);
    assert!(score.instructions[0].filled);
    assert_eq!(score.instructions[1].primitive, Primitive::Arc);
    assert_eq!(score.instructions[1].position, None);

    let canonical = canonical_json_bytes(&score).expect("endpoint-family Score must serialize");
    let reread = read_saved_score_json(&canonical).expect("serialized Score must reread");
    assert_eq!(reread, score);
    assert_eq!(reread.instructions[1].position, None);
}

#[test]
fn connected_fields_roundtrip_while_legacy_relations_keep_them_absent() {
    let source = br#"{"instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.4,0.5]},
        {"primitive":"line","from":[0.4,0.5],"to":[0.7,0.5],
         "relation":{"type":"connected","target_instruction_index":0,
         "position_authority":"numeric_fixed"}},
        {"primitive":"circle","center":[0.8,0.8],"radius":0.05,
         "relation":{"type":"not_touching"}}
    ]}"#;
    let score = read_saved_score_json(source).expect("Connected Score must parse");
    let connected = score.instructions[1].relation.as_ref().unwrap();
    assert_eq!(connected.target_instruction_index, Some(0));
    assert!(connected.position_authority.is_some());
    let legacy = score.instructions[2].relation.as_ref().unwrap();
    assert_eq!(legacy.target_instruction_index, None);
    assert_eq!(legacy.position_authority, None);
    let canonical = canonical_json_bytes(&score).expect("Connected Score serializes");
    let reread = read_saved_score_json(&canonical).expect("Connected Score rereads");
    assert_eq!(reread, score);
}

#[test]
fn old_and_transform_group_scores_roundtrip_through_saved_compatibility() {
    for source in [
        br#"{"version":"0.3.0","instructions":[{"primitive":"line"}]}"#.as_slice(),
        br#"{"version":"0.4.0","instructions":[
            {"primitive":"line"},{"primitive":"line"},{"primitive":"circle"}],
            "transform_groups":[
                {"start":0,"end":2,"rotation_degrees":30.0,"fixed_position_indices":[1]},
                {"start":0,"end":3,"rotation_degrees":90.0,"fixed_position_indices":[1]}
            ]}"#
        .as_slice(),
        br#"{"version":"0.5.0","instructions":[{"primitive":"line"},{"primitive":"line"}],
            "transform_groups":[{"start":0,"end":2,"rotation_degrees":0.0,
            "scale_x":-1.0,"scale_y":0.0,"translate_x":0.2,"translate_y":-0.1}]}"#
            .as_slice(),
    ] {
        let score = read_saved_score_json(source).expect("saved Score must parse");
        let canonical = canonical_json_bytes(&score).expect("saved Score must canonicalize");
        assert_eq!(
            read_saved_score_json(&canonical).expect("canonical Score must reread"),
            score
        );
    }
}

#[test]
fn compact_fill_score_roundtrips_without_sampled_positions_or_stored_demand() {
    let source = br#"{
        "version":"0.10.0","instructions":[{
            "primitive":"point","center":[0.5,0.5],"radius":0.006,"filled":true,
            "arrangement":{"count":1,"resolved":{
                "owner":{"kind":"source_instruction","instruction_index":0},
                "first_instance_ordinal":0,"count_origin":{"kind":"omitted_default"},
                "domain":[1.0,1.0],"anchor":{"kind":"numeric","point":[0.5,0.5]},
                "recipe":{"kind":"place"},
                "ordinal_scheme":"source_member_then_instance_v1"
            }}
        }],
        "fill_groups":[{
            "start":0,"end":1,
            "owner":{"kind":"instruction","source_instruction_index":0},
            "logical_count":2,"recipe":"uniform_in_region",
            "target":{"owner":{"kind":"omitted_canvas"},
                "geometry":{"kind":"rectangle","bounds":[0.0,0.0,1.0,1.0]},
                "reference_area":1.0},
            "boundary":"clip_to_target",
            "ordinal_scheme":"source_member_then_instance_v1",
            "members":[{"start":0,"end":1,"symbolic":{
                "owner":{"kind":"source_instruction","instruction_index":0},
                "kind":"primitive","member_ordinal":0,"first_instance_ordinal":0,
                "instance_count":2,"count_origin":{"kind":"explicit"}
            }}]
        }],
        "resource_policy":{
            "accounting_id":"inku.resource-accounting.v1",
            "hard_policy":{"identity":"shipping-v1","budget":{"maximum":{
                "logical_objects":400,"primitive_marks":400,"object_templates":64,
                "maximum_per_template_primitive_marks":240,"maximum_resolved_count":2000,
                "template_nodes":400,"anchor_instances":400,"transform_instances":400,
                "placement_instances":400,"fill_instances":400
            }}},
            "operational_budget":{"maximum":{
                "logical_objects":400,"primitive_marks":400,"object_templates":64,
                "maximum_per_template_primitive_marks":240,"maximum_resolved_count":2000,
                "template_nodes":400,"anchor_instances":400,"transform_instances":400,
                "placement_instances":400,"fill_instances":400
            }}
        }
    }"#;

    let score = read_saved_score_json(source).expect("compact Score must parse");
    assert_eq!(score.fill_groups[0].logical_count, 2);
    let canonical = canonical_json_bytes(&score).expect("compact Score must canonicalize");
    let text = std::str::from_utf8(&canonical).unwrap();
    assert!(!text.contains("sampled"));
    assert!(!text.contains("demand"));
    assert_eq!(
        read_saved_score_json(&canonical).expect("compact Score must reread"),
        score
    );

    let mut old_edition: Value = serde_json::from_slice(source).unwrap();
    old_edition["version"] = Value::String("0.9.0".to_owned());
    assert!(read_saved_score_json(&serde_json::to_vec(&old_edition).unwrap()).is_err());
}
