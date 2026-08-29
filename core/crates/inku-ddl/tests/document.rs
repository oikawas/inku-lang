use std::collections::HashSet;

use inku_ddl::{
    DdlDocumentBodyNode, DdlDocumentParseOutcome, NORMALIZED_DDL_DOCUMENT_SCHEMA_ID,
    ResolvedInstructionLanguage, parse_normalized_ddl_document, wrap_legacy_prose,
};
use serde::Deserialize;
use serde_json::{Value, json};

const FIXTURE: &str = include_str!("fixtures/normalized-ddl-document-v1.json");

#[derive(Deserialize)]
struct Fixture {
    schema: String,
    version: u32,
    valid_cases: Vec<ValidCase>,
    legacy_cases: Vec<LegacyCase>,
    invalid_cases: Vec<InvalidCase>,
}

#[derive(Deserialize)]
struct ValidCase {
    id: String,
    input: String,
    expected: ExpectedDocument,
}

#[derive(Deserialize)]
struct ExpectedDocument {
    language: String,
    canvas_id: String,
    locks: Vec<Value>,
    body: Vec<Value>,
    canonical: String,
}

#[derive(Deserialize)]
struct LegacyCase {
    id: String,
    input: String,
    language: String,
    canvas_id: String,
    expected_prose: String,
    expected_canonical: String,
}

#[derive(Deserialize)]
struct InvalidCase {
    id: String,
    input: String,
    expected_code: String,
    line: usize,
    column: usize,
}

#[test]
fn fixture_known_answers_match_parser_serializer_and_reparse() {
    let fixture = load_fixture();
    for case in fixture.valid_cases {
        let DdlDocumentParseOutcome::Document(document) =
            parse_normalized_ddl_document(&case.input)
                .unwrap_or_else(|error| panic!("{}: unexpected diagnostic {error}", case.id))
        else {
            panic!("{}: v1 input was classified as legacy prose", case.id);
        };

        assert_eq!(
            document.language().as_str(),
            case.expected.language,
            "{}",
            case.id
        );
        assert_eq!(document.canvas_id(), case.expected.canvas_id, "{}", case.id);
        assert_eq!(project_locks(&document), case.expected.locks, "{}", case.id);
        assert_eq!(project_body(&document), case.expected.body, "{}", case.id);
        assert_eq!(
            document.canonical_string(),
            case.expected.canonical,
            "{}",
            case.id
        );
        assert!(!document.canonical_string().ends_with('\n'), "{}", case.id);
        assert!(!document.canonical_string().contains('\r'), "{}", case.id);

        let DdlDocumentParseOutcome::Document(reparsed) =
            parse_normalized_ddl_document(&case.expected.canonical).unwrap()
        else {
            panic!(
                "{}: canonical output was classified as legacy prose",
                case.id
            );
        };
        assert_eq!(reparsed, document, "{}", case.id);
        assert_eq!(
            reparsed.canonical_string(),
            case.expected.canonical,
            "{}",
            case.id
        );
    }
}

#[test]
fn fixture_legacy_cases_require_explicit_language_and_canvas_wrapping() {
    let fixture = load_fixture();
    for case in fixture.legacy_cases {
        let DdlDocumentParseOutcome::LegacyProse(legacy) =
            parse_normalized_ddl_document(&case.input)
                .unwrap_or_else(|error| panic!("{}: unexpected diagnostic {error}", case.id))
        else {
            panic!("{}: headerless input silently became v1", case.id);
        };
        assert_eq!(legacy.prose(), case.expected_prose, "{}", case.id);

        let language = match case.language.as_str() {
            "ja" => ResolvedInstructionLanguage::Ja,
            "en" => ResolvedInstructionLanguage::En,
            _ => panic!("{}: invalid fixture language", case.id),
        };
        let wrapped = wrap_legacy_prose(&case.input, language, &case.canvas_id)
            .unwrap_or_else(|error| panic!("{}: wrap failed: {error}", case.id));
        assert_eq!(
            wrapped.canonical_string(),
            case.expected_canonical,
            "{}",
            case.id
        );

        let DdlDocumentParseOutcome::Document(reparsed) =
            parse_normalized_ddl_document(&case.expected_canonical).unwrap()
        else {
            panic!("{}: wrapped canonical output became legacy", case.id);
        };
        assert_eq!(reparsed, wrapped, "{}", case.id);
    }
}

#[test]
fn fixture_invalid_cases_have_stable_source_diagnostics() {
    let fixture = load_fixture();
    for case in fixture.invalid_cases {
        let error = parse_normalized_ddl_document(&case.input)
            .expect_err(&format!("{}: invalid input was accepted", case.id));
        assert_eq!(error.code(), case.expected_code, "{}", case.id);
        assert_eq!(error.line(), case.line, "{}", case.id);
        assert_eq!(error.column(), case.column, "{}", case.id);
    }
}

#[test]
fn fixture_shape_ids_and_checked_in_canonical_answers_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(fixture.schema, "inku.normalized-ddl-document-v1-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(
        NORMALIZED_DDL_DOCUMENT_SCHEMA_ID,
        "inku.normalized-ddl-document.v1"
    );
    assert_eq!(fixture.valid_cases.len(), 3);
    assert_eq!(fixture.legacy_cases.len(), 2);
    assert_eq!(fixture.invalid_cases.len(), 23);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let mut ids = HashSet::new();
    for id in fixture
        .valid_cases
        .iter()
        .map(|case| case.id.as_str())
        .chain(fixture.legacy_cases.iter().map(|case| case.id.as_str()))
        .chain(fixture.invalid_cases.iter().map(|case| case.id.as_str()))
    {
        assert!(ids.insert(id), "duplicate fixture case ID: {id}");
    }
    for required in [
        "ja-sd-monitor-no-macro",
        "en-hd-monitor-crlf-no-macro",
        "unicode-space-dot-lock-sort-repeat-invoke-arguments",
        "legacy-ja-explicit-wrap",
        "legacy-en-explicit-wrap",
        "language-auto",
        "language-unknown",
        "canvas-unknown",
        "document-version-unknown",
        "semantic-version-invalid",
        "digest-short",
        "lock-identical-duplicate",
        "lock-conflicting-duplicate",
        "lock-unused",
        "lock-missing",
        "unknown-body-directive",
        "lock-qualified-name-malformed",
        "arguments-malformed-json",
        "arguments-nested-object",
        "arguments-null",
        "body-blank",
        "body-separator-missing",
        "bare-carriage-return",
    ] {
        assert!(
            ids.contains(required),
            "missing required fixture case: {required}"
        );
    }

    for expected in fixture
        .valid_cases
        .iter()
        .map(|case| &case.expected.canonical)
        .chain(
            fixture
                .legacy_cases
                .iter()
                .map(|case| &case.expected_canonical),
        )
    {
        assert!(expected.starts_with("@inku-ddl v1\n@language "));
        assert!(expected.contains("\n@canvas "));
        assert!(expected.contains("\n\n"));
        assert!(!expected.contains('\r'));
        assert!(!expected.ends_with('\n'));
    }
}

fn load_fixture() -> Fixture {
    serde_json::from_str(FIXTURE).expect("fixture must be valid JSON")
}

fn project_locks(document: &inku_ddl::NormalizedDdlDocument) -> Vec<Value> {
    document
        .macro_locks()
        .iter()
        .map(|macro_lock| {
            json!({
                "qualified_name": macro_lock.qualified_name(),
                "version": macro_lock.version(),
                "digest": macro_lock.digest(),
            })
        })
        .collect()
}

fn project_body(document: &inku_ddl::NormalizedDdlDocument) -> Vec<Value> {
    document
        .body()
        .iter()
        .map(|node| match node {
            DdlDocumentBodyNode::Text(text) => json!({"kind": "text", "text": text}),
            DdlDocumentBodyNode::Invocation(invocation) => json!({
                "kind": "invoke",
                "qualified_name": invocation.invocation().qualified_name(),
                "ordinal": invocation.invocation().ordinal(),
                "arguments": invocation.arguments(),
            }),
        })
        .collect()
}
