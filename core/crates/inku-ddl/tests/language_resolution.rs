use std::collections::HashSet;

use inku_ddl::{
    DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE, INSTRUCTION_LANGUAGE_REGISTRY_ID,
    InstructionLanguageError, REQUESTABLE_INSTRUCTION_LANGUAGE_CODES, ResolvedInstructionLanguage,
    SUPPORTED_INSTRUCTION_LANGUAGE_CODES, normalize_instruction_language,
    resolve_instruction_language, resolve_instruction_language_for_ui,
};
use serde::Deserialize;
use serde_json::Value;

const FIXTURE: &str = include_str!("fixtures/instruction-language-resolution-v1.json");

#[derive(Deserialize)]
struct Fixture {
    schema: String,
    version: u32,
    cases: Vec<FixtureCase>,
}

#[derive(Deserialize)]
struct FixtureCase {
    id: String,
    operation: String,
    input: Value,
    expected: Expected,
}

#[derive(Deserialize)]
struct Expected {
    result: Option<String>,
    error_kind: Option<String>,
}

#[test]
fn instruction_language_fixture_matches_registry_api() {
    let fixture: Fixture = serde_json::from_str(FIXTURE).expect("fixture must be valid JSON");
    assert_eq!(
        fixture.schema,
        "inku.instruction-language-resolution-fixture.v1"
    );
    assert_eq!(fixture.version, 1);

    let mut ids = HashSet::new();
    for case in fixture.cases {
        assert!(
            ids.insert(case.id.clone()),
            "duplicate fixture case ID: {}",
            case.id
        );
        assert_eq!(
            case.expected.result.is_some(),
            case.expected.error_kind.is_none(),
            "fixture case must have exactly one expected result or error: {}",
            case.id
        );

        let actual = match case.operation.as_str() {
            "normalize" => normalize_instruction_language(
                optional_string(&case.input, "value"),
                required_string(&case.input, "default"),
            )
            .map(|language| language.as_str()),
            "resolve" => resolve_instruction_language(
                required_string(&case.input, "text"),
                optional_string(&case.input, "requested"),
                required_string(&case.input, "fallback"),
            )
            .map(ResolvedInstructionLanguage::as_str),
            "ui_fallback" => resolve_instruction_language_for_ui(
                required_string(&case.input, "text"),
                optional_string(&case.input, "requested"),
                optional_string(&case.input, "ui_lang"),
            )
            .map(ResolvedInstructionLanguage::as_str),
            operation => panic!("unknown fixture operation {operation:?}: {}", case.id),
        };
        assert_expected(actual, &case.expected, &case.id);
    }
}

#[test]
fn registry_identity_order_and_resolved_boundary_are_stable() {
    assert_eq!(
        INSTRUCTION_LANGUAGE_REGISTRY_ID,
        "inku.instruction-language-registry.v1"
    );
    assert_eq!(SUPPORTED_INSTRUCTION_LANGUAGE_CODES, ["ja", "en"]);
    assert_eq!(REQUESTABLE_INSTRUCTION_LANGUAGE_CODES, ["auto", "ja", "en"]);
    assert_eq!(DEFAULT_RESOLVED_INSTRUCTION_LANGUAGE.as_str(), "ja");

    for language in [
        ResolvedInstructionLanguage::Ja,
        ResolvedInstructionLanguage::En,
    ] {
        match language {
            ResolvedInstructionLanguage::Ja => assert_eq!(language.as_str(), "ja"),
            ResolvedInstructionLanguage::En => assert_eq!(language.as_str(), "en"),
        }
    }
}

fn required_string<'a>(input: &'a Value, field: &str) -> &'a str {
    input
        .get(field)
        .and_then(Value::as_str)
        .unwrap_or_else(|| panic!("fixture field {field:?} must be a string"))
}

fn optional_string<'a>(input: &'a Value, field: &str) -> Option<&'a str> {
    match input.get(field) {
        Some(Value::Null) => None,
        Some(Value::String(value)) => Some(value),
        _ => panic!("fixture field {field:?} must be a string or null"),
    }
}

fn assert_expected(
    actual: Result<&str, InstructionLanguageError>,
    expected: &Expected,
    case_id: &str,
) {
    match (
        actual,
        expected.result.as_deref(),
        expected.error_kind.as_deref(),
    ) {
        (Ok(result), Some(expected_result), None) => {
            assert_eq!(result, expected_result, "{case_id}")
        }
        (Err(error), None, Some(expected_kind)) => {
            assert_eq!(error.kind(), expected_kind, "{case_id}")
        }
        _ => panic!("invalid expected result or error for {case_id}"),
    }
}
