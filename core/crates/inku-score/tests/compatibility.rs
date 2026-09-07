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
