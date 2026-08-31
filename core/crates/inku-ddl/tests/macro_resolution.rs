use std::collections::{HashMap, HashSet};

use inku_ddl::{
    MACRO_INVOCATION_LOCK_RESOLUTION_SCHEMA_ID, MacroDefinition,
    MacroInvocationResolutionDiagnosticKind, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, collect_relation_reference_evidence, resolve_macro_invocations,
};
use serde::Deserialize;
use serde_json::Value;

const FIXTURE: &str = include_str!("fixtures/macro-resolution-v1.json");

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixture {
    schema: String,
    version: u32,
    definitions: HashMap<String, Value>,
    valid_cases: Vec<ValidCase>,
    diagnostic_cases: Vec<DiagnosticCase>,
    invalid_document_cases: Vec<InvalidDocumentCase>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ValidCase {
    id: String,
    source: String,
    language: String,
    locks: Vec<LockCase>,
    definition_inputs: Vec<String>,
    expected: Vec<ExpectedResolved>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DiagnosticCase {
    id: String,
    source: String,
    language: String,
    locks: Vec<LockCase>,
    definition_inputs: Vec<String>,
    expected_kind: String,
    expected_surface: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LockCase {
    definition: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ExpectedResolved {
    surface: String,
    ordinal: u64,
    clause_index: usize,
    atom_index: usize,
    definition: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InvalidDocumentCase {
    id: String,
    qualified_name: String,
    version: String,
    digest: String,
    expected_code: String,
}

#[test]
fn locked_visible_macros_resolve_in_source_order_without_changing_i579() {
    let fixture = load_fixture();
    for case in &fixture.valid_cases {
        let definitions = definitions(&fixture, &case.definition_inputs);
        let document = document(
            &fixture,
            &case.source,
            &case.language,
            &case.locks,
            &case.id,
        );
        let accepted = collect_relation_reference_evidence(&document).unwrap();
        let result = resolve_macro_invocations(&document, &definitions).unwrap();

        assert_eq!(result.relation_reference_evidence, accepted, "{}", case.id);
        assert_eq!(
            result.recognized_occurrence_count,
            case.expected.len(),
            "{}",
            case.id
        );
        assert!(
            result.diagnostics.is_empty(),
            "{}: {:?}",
            case.id,
            result.diagnostics
        );
        assert_eq!(result.resolved.len(), case.expected.len(), "{}", case.id);

        let mut search_start = 0;
        for (actual, expected) in result.resolved.iter().zip(&case.expected) {
            let relative = case.source[search_start..]
                .find(&expected.surface)
                .unwrap_or_else(|| panic!("{}: missing expected surface", case.id));
            let start_byte = search_start + relative;
            let end_byte = start_byte + expected.surface.len();
            search_start = end_byte;
            let expected_identity = definition(&fixture, &expected.definition)
                .identity()
                .unwrap();

            assert_eq!(
                actual.invocation.qualified_name(),
                expected.surface,
                "{}",
                case.id
            );
            assert_eq!(actual.invocation.ordinal(), expected.ordinal, "{}", case.id);
            assert_eq!(
                (actual.span.start_byte, actual.span.end_byte),
                (start_byte, end_byte),
                "{}",
                case.id
            );
            assert_eq!(
                (actual.clause_index, actual.atom_index),
                (expected.clause_index, expected.atom_index),
                "{}",
                case.id
            );
            assert_eq!(actual.lock.qualified_name, expected.surface, "{}", case.id);
            assert_eq!(
                actual.lock.version,
                expected_identity.version(),
                "{}",
                case.id
            );
            assert_eq!(
                actual.lock.digest,
                format!("sha256:{}", expected_identity.full_digest_hex()),
                "{}",
                case.id
            );
            assert_eq!(actual.definition_identity, expected_identity, "{}", case.id);
            assert_eq!(
                &case.source[actual.span.start_byte..actual.span.end_byte],
                expected.surface,
                "{}",
                case.id
            );
        }
        if case.id == "ja-no-whitespace-suffix" {
            let clause = &result
                .relation_reference_evidence
                .attachment_evidence
                .noun_phrase
                .clause_stream
                .clauses[0];
            assert_eq!(
                (clause.span.start_byte, clause.span.end_byte),
                (0, case.source.len())
            );
            assert_eq!(
                &case.source[result.resolved[0].span.end_byte..],
                "を右下にひとつ置く"
            );
        }
        if case.id == "ja-typed-suffix-evidence" {
            let atoms = &result
                .relation_reference_evidence
                .attachment_evidence
                .noun_phrase
                .clause_stream
                .clauses[0]
                .atoms;
            let surfaces = atoms
                .iter()
                .map(|atom| {
                    let span = atom.span();
                    &case.source[span.start_byte..span.end_byte]
                })
                .collect::<Vec<_>>();
            assert_eq!(surfaces, ["Nature.若葉", "を", "上", "に", "八つ", "置く"]);
        }
    }
}

#[test]
fn every_unresolved_occurrence_has_one_stable_typed_diagnostic() {
    let fixture = load_fixture();
    for case in &fixture.diagnostic_cases {
        let definitions = definitions(&fixture, &case.definition_inputs);
        let document = document(
            &fixture,
            &case.source,
            &case.language,
            &case.locks,
            &case.id,
        );
        let accepted = collect_relation_reference_evidence(&document).unwrap();
        let result = resolve_macro_invocations(&document, &definitions).unwrap();

        assert_eq!(result.relation_reference_evidence, accepted, "{}", case.id);
        assert_eq!(result.recognized_occurrence_count, 1, "{}", case.id);
        assert!(result.resolved.is_empty(), "{}", case.id);
        assert_eq!(result.diagnostics.len(), 1, "{}", case.id);
        assert_eq!(
            result.diagnostics[0].kind,
            diagnostic_kind(&case.expected_kind),
            "{}",
            case.id
        );
        assert_eq!(
            result.diagnostics[0].surface, case.expected_surface,
            "{}",
            case.id
        );
        assert_eq!(result.diagnostics[0].ordinal, 0, "{}", case.id);
    }
}

#[test]
fn document_boundary_rejects_noncanonical_lock_digests_before_resolution() {
    let fixture = load_fixture();
    for case in &fixture.invalid_document_cases {
        let error = MacroLock::new(&case.qualified_name, &case.version, &case.digest)
            .expect_err(&format!("{}: invalid lock accepted", case.id));
        assert_eq!(error.code(), case.expected_code, "{}", case.id);
    }
}

#[test]
fn fixture_shape_and_required_boundary_coverage_are_stable() {
    let fixture = load_fixture();
    assert_eq!(
        fixture.schema,
        "inku.macro-invocation-lock-resolution-v1-fixture.v1"
    );
    assert_eq!(fixture.version, 1);
    assert_eq!(
        MACRO_INVOCATION_LOCK_RESOLUTION_SCHEMA_ID,
        "inku.macro-invocation-lock-resolution.v1"
    );
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let mut ids = HashSet::new();
    for id in fixture
        .valid_cases
        .iter()
        .map(|case| case.id.as_str())
        .chain(fixture.diagnostic_cases.iter().map(|case| case.id.as_str()))
        .chain(
            fixture
                .invalid_document_cases
                .iter()
                .map(|case| case.id.as_str()),
        )
    {
        assert!(ids.insert(id), "duplicate fixture case ID: {id}");
    }
    for required in [
        "ja-no-whitespace-suffix",
        "en-whitespace-suffix",
        "ja-typed-suffix-evidence",
        "same-macro-repeated-ordinal",
        "multiple-macro-source-order",
        "unicode-heading-internal-dot",
        "punctuation-and-line-break",
        "missing-lock",
        "ambiguous-lock-prefix",
        "missing-definition",
        "duplicate-matching-definition",
        "invalid-definition",
        "qualified-name-mismatch",
        "version-mismatch",
        "digest-mismatch",
        "case-fold-is-not-a-match",
        "substring-is-not-a-match",
        "uppercase-digest",
        "short-digest",
    ] {
        assert!(ids.contains(required), "missing required case: {required}");
    }
    assert!(!FIXTURE.contains("fires_on"));
    assert!(!FIXTURE.contains("@invoke"));
}

fn load_fixture() -> Fixture {
    serde_json::from_str(FIXTURE).expect("fixture must be valid JSON")
}

fn definition(fixture: &Fixture, id: &str) -> MacroDefinition {
    MacroDefinition::from_json(
        &serde_json::to_string(
            fixture
                .definitions
                .get(id)
                .unwrap_or_else(|| panic!("unknown definition: {id}")),
        )
        .unwrap(),
    )
    .unwrap_or_else(|error| panic!("{id}: invalid typed definition input: {error}"))
}

fn definitions(fixture: &Fixture, ids: &[String]) -> Vec<MacroDefinition> {
    ids.iter().map(|id| definition(fixture, id)).collect()
}

fn document(
    fixture: &Fixture,
    source: &str,
    language: &str,
    locks: &[LockCase],
    id: &str,
) -> NormalizedDdlDocument {
    let locks = locks
        .iter()
        .map(|lock| {
            let identity = definition(fixture, &lock.definition).identity().unwrap();
            MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .unwrap()
        })
        .collect();
    NormalizedDdlDocument::new(source, parse_language(language, id), locks).unwrap()
}

fn parse_language(language: &str, id: &str) -> ResolvedInstructionLanguage {
    match language {
        "ja" => ResolvedInstructionLanguage::Ja,
        "en" => ResolvedInstructionLanguage::En,
        _ => panic!("{id}: invalid language"),
    }
}

fn diagnostic_kind(value: &str) -> MacroInvocationResolutionDiagnosticKind {
    match value {
        "missing_lock" => MacroInvocationResolutionDiagnosticKind::MissingLock,
        "ambiguous_lock_prefix" => MacroInvocationResolutionDiagnosticKind::AmbiguousLockPrefix,
        "missing_definition" => MacroInvocationResolutionDiagnosticKind::MissingDefinition,
        "duplicate_matching_definition" => {
            MacroInvocationResolutionDiagnosticKind::DuplicateMatchingDefinition
        }
        "invalid_definition" => MacroInvocationResolutionDiagnosticKind::InvalidDefinition,
        "qualified_name_mismatch" => MacroInvocationResolutionDiagnosticKind::QualifiedNameMismatch,
        "version_mismatch" => MacroInvocationResolutionDiagnosticKind::VersionMismatch,
        "digest_mismatch" => MacroInvocationResolutionDiagnosticKind::DigestMismatch,
        _ => panic!("unknown expected diagnostic kind: {value}"),
    }
}
