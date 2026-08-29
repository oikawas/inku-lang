use std::collections::HashSet;

use inku_ddl::{
    MacroLock, NORMALIZED_DDL_DOCUMENT_SCHEMA_ID, NormalizedDdlDocument,
    ResolvedInstructionLanguage,
};
use serde::Deserialize;
use serde_json::Value;

const FIXTURE: &str = include_str!("fixtures/normalized-ddl-document-v1.json");

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixture {
    schema: String,
    version: u32,
    valid_cases: Vec<ValidCase>,
    invalid_macro_lock_cases: Vec<InvalidMacroLockCase>,
    duplicate_lock_cases: Vec<DuplicateLockCase>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ValidCase {
    id: String,
    source: String,
    language: String,
    locks: Vec<LockFixture>,
    expected: ExpectedDocument,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ExpectedDocument {
    source: String,
    language: String,
    locks: Vec<LockFixture>,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct LockFixture {
    qualified_name: String,
    version: String,
    digest: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InvalidMacroLockCase {
    id: String,
    lock: LockFixture,
    expected_code: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DuplicateLockCase {
    id: String,
    source: String,
    language: String,
    locks: Vec<LockFixture>,
    expected_code: String,
}

#[test]
fn fixture_known_answers_preserve_source_and_canonicalize_sidecar_locks() {
    let fixture = load_fixture();
    for case in fixture.valid_cases {
        let document = NormalizedDdlDocument::new(
            case.source.clone(),
            parse_language(&case.language, &case.id),
            make_locks(&case.locks, &case.id),
        )
        .unwrap_or_else(|error| panic!("{}: unexpected diagnostic {error}", case.id));

        assert_eq!(
            document.source().as_bytes(),
            case.expected.source.as_bytes(),
            "{}",
            case.id
        );
        assert_eq!(
            document.language().as_str(),
            case.expected.language,
            "{}",
            case.id
        );
        assert_eq!(
            project_locks(&document),
            project_lock_fixtures(&case.expected.locks),
            "{}",
            case.id
        );
        assert!(!document.source().contains("@inku-ddl"), "{}", case.id);
        assert!(!document.source().contains("@language"), "{}", case.id);
        assert!(!document.source().contains("@canvas"), "{}", case.id);
        assert!(!document.source().contains("@macro-lock"), "{}", case.id);
        assert!(!document.source().contains("@invoke"), "{}", case.id);
    }
}

#[test]
fn fixture_invalid_macro_locks_have_stable_metadata_diagnostics() {
    let fixture = load_fixture();
    for case in fixture.invalid_macro_lock_cases {
        let error = MacroLock::new(
            case.lock.qualified_name,
            case.lock.version,
            case.lock.digest,
        )
        .expect_err(&format!("{}: invalid macro lock was accepted", case.id));
        assert_eq!(error.code(), case.expected_code, "{}", case.id);
    }
}

#[test]
fn fixture_duplicate_locks_are_rejected_after_byte_order_canonicalization() {
    let fixture = load_fixture();
    for case in fixture.duplicate_lock_cases {
        let error = NormalizedDdlDocument::new(
            case.source,
            parse_language(&case.language, &case.id),
            make_locks(&case.locks, &case.id),
        )
        .expect_err(&format!("{}: duplicate macro locks were accepted", case.id));
        assert_eq!(error.code(), case.expected_code, "{}", case.id);
    }
}

#[test]
fn fixture_shape_ids_and_source_only_boundary_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(fixture.schema, "inku.normalized-ddl-document-v1-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(
        NORMALIZED_DDL_DOCUMENT_SCHEMA_ID,
        "inku.normalized-ddl-document.v1"
    );
    assert_eq!(fixture.valid_cases.len(), 3);
    assert_eq!(fixture.invalid_macro_lock_cases.len(), 5);
    assert_eq!(fixture.duplicate_lock_cases.len(), 2);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let mut ids = HashSet::new();
    for id in fixture
        .valid_cases
        .iter()
        .map(|case| case.id.as_str())
        .chain(
            fixture
                .invalid_macro_lock_cases
                .iter()
                .map(|case| case.id.as_str()),
        )
        .chain(
            fixture
                .duplicate_lock_cases
                .iter()
                .map(|case| case.id.as_str()),
        )
    {
        assert!(ids.insert(id), "duplicate fixture case ID: {id}");
    }
    for required in [
        "ja-source-preserves-crlf-and-macro-term",
        "en-source-preserves-whitespace-and-macro-term",
        "blank-source-is-semantic-parser-work",
        "lock-qualified-name-malformed",
        "semantic-version-invalid",
        "digest-short",
        "digest-uppercase",
        "lock-qualified-name-leading-space",
        "lock-identical-duplicate",
        "lock-conflicting-duplicate",
    ] {
        assert!(
            ids.contains(required),
            "missing required fixture case: {required}"
        );
    }
    assert!(!include_str!("../src/document.rs").contains("canvas"));
}

fn load_fixture() -> Fixture {
    serde_json::from_str(FIXTURE).expect("fixture must be valid JSON")
}

fn parse_language(value: &str, case_id: &str) -> ResolvedInstructionLanguage {
    match value {
        "ja" => ResolvedInstructionLanguage::Ja,
        "en" => ResolvedInstructionLanguage::En,
        _ => panic!("{case_id}: invalid fixture language"),
    }
}

fn make_locks(locks: &[LockFixture], case_id: &str) -> Vec<MacroLock> {
    locks
        .iter()
        .cloned()
        .map(|lock| {
            MacroLock::new(lock.qualified_name, lock.version, lock.digest)
                .unwrap_or_else(|error| panic!("{case_id}: invalid fixture lock: {error}"))
        })
        .collect()
}

fn project_locks(document: &NormalizedDdlDocument) -> Vec<Value> {
    document
        .macro_locks()
        .iter()
        .map(|macro_lock| {
            serde_json::json!({
                "qualified_name": macro_lock.qualified_name(),
                "version": macro_lock.version(),
                "digest": macro_lock.digest(),
            })
        })
        .collect()
}

fn project_lock_fixtures(locks: &[LockFixture]) -> Vec<Value> {
    locks
        .iter()
        .map(|lock| {
            serde_json::json!({
                "qualified_name": lock.qualified_name,
                "version": lock.version,
                "digest": lock.digest,
            })
        })
        .collect()
}
