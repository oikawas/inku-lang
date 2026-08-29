use std::collections::{BTreeMap, HashSet};

use inku_ddl::{
    LEGACY_PLUGIN_FORMAT_WARNING, LegacyImportOutcome, MACRO_DEFINITION_DIGEST_DOMAIN,
    MACRO_DEFINITION_SCHEMA_ID, MacroDefinition,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const FIXTURE: &str = include_str!("fixtures/macro-definition-v1.json");

#[derive(Deserialize)]
struct Fixture {
    schema: String,
    version: u32,
    definitions: BTreeMap<String, Value>,
    valid_cases: Vec<ValidCase>,
    invalid_cases: Vec<InvalidCase>,
}

#[derive(Deserialize)]
struct ValidCase {
    id: String,
    definition: String,
    alternate_input_json: Option<String>,
    expected_canonical_json: String,
    expected_digest: String,
    expected_qualified_name: String,
    expected_version: String,
    expected_upper_bound: u64,
}

#[derive(Deserialize)]
struct InvalidCase {
    id: String,
    input_json: String,
    expected_code: String,
}

#[test]
fn shared_known_answers_match_typed_canonical_identity_and_resource_bounds() {
    let fixture: Fixture = serde_json::from_str(FIXTURE).expect("fixture must be valid JSON");
    assert_eq!(fixture.schema, "inku.macro-definition-v1-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));
    assert_eq!(MACRO_DEFINITION_SCHEMA_ID, "inku.macro-definition.v1");
    assert_eq!(MACRO_DEFINITION_DIGEST_DOMAIN, b"inku.macro-definition.v1");

    let mut ids = HashSet::new();
    let mut digests = BTreeMap::new();
    for case in &fixture.valid_cases {
        assert!(
            ids.insert(case.id.clone()),
            "duplicate case ID: {}",
            case.id
        );
        assert_lowercase_digest(&case.expected_digest, &case.id);
        let source = serde_json::to_string(
            fixture
                .definitions
                .get(&case.definition)
                .expect("known definition reference"),
        )
        .unwrap();
        assert_valid_case(case, &source);
        if let Some(alternate) = &case.alternate_input_json {
            assert_valid_case(case, alternate);
        }
        digests.insert(case.id.as_str(), case.expected_digest.as_str());
    }
    assert_ne!(
        digests["all-operators-ja-component-reuse-bounded-vary-touch-surface"],
        digests["digest-sensitivity-version"]
    );
}

#[test]
fn invalid_fixture_cases_are_rejected_with_stable_codes() {
    let fixture: Fixture = serde_json::from_str(FIXTURE).expect("fixture must be valid JSON");
    let mut ids = HashSet::new();
    for case in &fixture.invalid_cases {
        assert!(
            ids.insert(case.id.clone()),
            "duplicate case ID: {}",
            case.id
        );
        match MacroDefinition::from_json(&case.input_json) {
            Err(error) => assert_eq!(error.code(), case.expected_code, "{}", case.id),
            Ok(definition) => {
                let validation = definition.validate();
                assert!(
                    validation.has_code(&case.expected_code),
                    "{}: expected {}, got {:?}",
                    case.id,
                    case.expected_code,
                    validation
                        .diagnostics()
                        .iter()
                        .map(|diagnostic| (diagnostic.code(), diagnostic.path()))
                        .collect::<Vec<_>>()
                );
                assert!(definition.canonical_json_bytes().is_err(), "{}", case.id);
            }
        }
    }
    assert_required_invalid_coverage(&ids);
}

#[test]
fn legacy_import_and_omission_are_nonfatal_per_macro_warning_outcomes() {
    let fixture: Fixture = serde_json::from_str(FIXTURE).unwrap();
    let source = serde_json::to_string(&fixture.definitions["key-order-whitespace"]).unwrap();
    let definition = MacroDefinition::from_json(&source).unwrap();
    let imported = LegacyImportOutcome::imported(definition).unwrap();
    let omitted = LegacyImportOutcome::omitted("legacy.unconvertible", "unsupported_entry");

    for outcome in [&imported, &omitted] {
        assert_eq!(outcome.warnings().len(), 1);
        assert_eq!(outcome.warnings()[0].code(), LEGACY_PLUGIN_FORMAT_WARNING);
    }
    assert!(matches!(imported, LegacyImportOutcome::Imported { .. }));
    assert!(matches!(omitted, LegacyImportOutcome::Omitted { .. }));
}

fn assert_valid_case(case: &ValidCase, source: &str) {
    let definition = MacroDefinition::from_json(source).unwrap_or_else(|error| {
        panic!("{} parse failed: {error}", case.id);
    });
    let validation = definition.validate();
    assert!(
        validation.is_valid(),
        "{}: {:?}",
        case.id,
        validation
            .diagnostics()
            .iter()
            .map(|diagnostic| (diagnostic.code(), diagnostic.path()))
            .collect::<Vec<_>>()
    );
    assert_eq!(
        validation.symbolic_upper_bound(),
        Some(case.expected_upper_bound),
        "{}",
        case.id
    );

    let identity = definition.identity().unwrap();
    assert_eq!(
        identity.canonical_json_bytes(),
        case.expected_canonical_json.as_bytes(),
        "{}",
        case.id
    );
    assert!(!identity.canonical_json_bytes().ends_with(b"\n"));
    assert_eq!(identity.qualified_name(), case.expected_qualified_name);
    assert_eq!(identity.version(), case.expected_version);
    assert_eq!(identity.full_digest_hex(), case.expected_digest);
    let expected_digest: [u8; 32] = Sha256::digest(
        [
            MACRO_DEFINITION_DIGEST_DOMAIN,
            &(identity.canonical_json_bytes().len() as u64).to_be_bytes(),
            identity.canonical_json_bytes(),
        ]
        .concat(),
    )
    .into();
    assert_eq!(identity.full_digest_bytes(), &expected_digest);
}

fn assert_lowercase_digest(value: &str, case_id: &str) {
    assert!(
        value.len() == 64
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f')),
        "invalid digest in {case_id}: {value}"
    );
}

fn assert_required_invalid_coverage(ids: &HashSet<String>) {
    for required in [
        "domain-specific-operator",
        "unknown-semantic-id",
        "filled-authoring-field",
        "wild-host-option",
        "wild-semantic-reference",
        "raw-score",
        "raw-svg",
        "renderer-instruction",
        "external-use",
        "component-cycle",
        "undefined-anchor",
        "undefined-parameter",
        "unbounded-repeat",
        "empty-vary",
        "non-finite-number",
        "duplicate-anchor",
    ] {
        assert!(
            ids.contains(required),
            "missing invalid coverage: {required}"
        );
    }
}
