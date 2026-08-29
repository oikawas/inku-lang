use std::collections::HashSet;

use inku_score::{Score, canonical_json_bytes, canonical_score_digest};
use serde::Deserialize;
use serde_json::Value;

#[derive(Debug, Deserialize)]
struct FixtureFile {
    cases: Vec<FixtureCase>,
}

#[derive(Debug, Deserialize)]
struct FixtureCase {
    id: String,
    input: Value,
    canonical_json: String,
    digest: String,
}

#[test]
fn canonical_score_fixtures_are_stable() {
    let fixtures: FixtureFile =
        serde_json::from_str(include_str!("fixtures/canonical-score-cases.json"))
            .expect("fixture JSON must parse");

    assert!(
        fixtures.cases.len() >= 2,
        "fixtures need at least two cases"
    );
    let unique_ids = fixtures
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(
        unique_ids.len(),
        fixtures.cases.len(),
        "fixture IDs must be unique"
    );

    for fixture in fixtures.cases {
        assert!(
            serde_json::from_str::<Value>(&fixture.canonical_json).is_ok(),
            "{} canonical JSON must parse",
            fixture.id
        );
        assert!(
            fixture.digest.len() == 64
                && fixture
                    .digest
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)),
            "{} digest must be lowercase hexadecimal",
            fixture.id
        );

        let score: Score = serde_json::from_value(fixture.input).expect("fixture Score must parse");
        let canonical_json = canonical_json_bytes(&score).expect("Score must serialize");
        assert_eq!(
            canonical_json,
            fixture.canonical_json.as_bytes(),
            "{} canonical JSON",
            fixture.id
        );
        assert_eq!(
            canonical_score_digest(&score).expect("Score must digest"),
            fixture.digest,
            "{} canonical digest",
            fixture.id
        );

        let reparsed: Score =
            serde_json::from_slice(&canonical_json).expect("canonical Score must parse");
        assert_eq!(reparsed, score, "{} canonical Score reparse", fixture.id);
        assert_eq!(
            canonical_json_bytes(&score).expect("Score must serialize"),
            canonical_json,
            "{} repeated canonical bytes",
            fixture.id
        );
        assert_eq!(
            canonical_score_digest(&score).expect("Score must digest"),
            canonical_score_digest(&score).expect("Score must digest"),
            "{} repeated canonical digest",
            fixture.id
        );
    }
}
