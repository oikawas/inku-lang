use std::collections::HashSet;

use inku_ddl::{
    CANONICAL_SEMANTIC_DDL_SCHEMA_ID, CompilerLockState, MacroDefinition, MacroExpansionLimits,
    MacroLock, NormalizedDdlDocument, ResolvedInstructionLanguage, TYPED_DDL_COMPILATION_SCHEMA_ID,
    TYPED_DDL_COMPILER_LOCK_SCHEMA_ID, bind_macro_parameters, compile_typed_ddl,
    expanded_meaning_canonical_bytes,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const FIXTURE: &str = include_str!("fixtures/compiler-lock-visible-patch-v1.json");
const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1_000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixture {
    schema: String,
    version: u32,
    definition: Value,
    known_answers: KnownAnswers,
    delivery_case_ids: Vec<String>,
    patch_case_ids: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct KnownAnswers {
    canonical_bytes: String,
    canonical_sha256: String,
    seed_digest: String,
    expanded_meaning_sha256: String,
    full_lock_digest: String,
}

#[test]
fn canonical_known_answers_bind_seed_expand_and_lock_exactly() {
    let fixture = fixture();
    let definition = fixture_definition(&fixture);
    let document = locked_document("Canon.Empty", ResolvedInstructionLanguage::En, &definition);
    let accepted = bind_macro_parameters(&document, &[definition.clone()]).unwrap();
    let result = compile_typed_ddl(document, &[definition], Some(7), LIMITS);

    assert_eq!(result.schema_id, TYPED_DDL_COMPILATION_SCHEMA_ID);
    assert_eq!(result.accepted_parameter_binding(), Some(&accepted));
    assert!(result.parameter_binding.is_none());
    let expansion = result.macro_expansion.as_ref().unwrap();
    assert_eq!(&expansion.parameter_binding, &accepted);
    assert!(expansion.diagnostics.is_empty());
    assert_eq!(result.derived_seeds.len(), 1);

    let canonical = result.canonical_semantic_bytes.as_ref().unwrap();
    let lock = result.compiler_lock.as_ref().unwrap();
    assert_eq!(lock.schema_id, TYPED_DDL_COMPILER_LOCK_SCHEMA_ID);
    assert_eq!(lock.state, CompilerLockState::CanonicalReady);

    let actual = KnownAnswers {
        canonical_bytes: String::from_utf8(canonical.clone()).unwrap(),
        canonical_sha256: sha256(canonical),
        seed_digest: result.derived_seeds[0].full_digest_hex().to_owned(),
        expanded_meaning_sha256: sha256(&expanded_meaning_canonical_bytes(expansion)),
        full_lock_digest: lock.full_digest.clone(),
    };
    if fixture.known_answers.canonical_bytes == "__UPDATE__" {
        panic!(
            "known answers: canonical_bytes={:?} canonical_sha256={} seed_digest={} expanded_meaning_sha256={} full_lock_digest={}",
            actual.canonical_bytes,
            actual.canonical_sha256,
            actual.seed_digest,
            actual.expanded_meaning_sha256,
            actual.full_lock_digest
        );
    }
    assert_eq!(
        actual.canonical_bytes,
        fixture.known_answers.canonical_bytes
    );
    assert_eq!(
        actual.canonical_sha256,
        fixture.known_answers.canonical_sha256
    );
    assert_eq!(actual.seed_digest, fixture.known_answers.seed_digest);
    assert_eq!(
        actual.expanded_meaning_sha256,
        fixture.known_answers.expanded_meaning_sha256
    );
    assert_eq!(
        actual.full_lock_digest,
        fixture.known_answers.full_lock_digest
    );
    assert_eq!(
        lock.canonical_pre_expansion_digest,
        Some(actual.canonical_sha256)
    );
    assert_eq!(
        lock.expanded_meaning_digest,
        Some(actual.expanded_meaning_sha256)
    );
    assert_eq!(lock.macro_seeds[0].full_digest, actual.seed_digest);
}

#[test]
fn language_format_and_approved_order_project_to_same_semantics_but_not_source_lock() {
    let ja = compile(
        "八つ  白 円",
        ResolvedInstructionLanguage::Ja,
        &[],
        None,
        LIMITS,
    );
    let en = compile(
        "circle white eight",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let en_format = compile(
        "  eight   white circle.  ",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    for result in [&ja, &en, &en_format] {
        assert_eq!(
            result.compiler_lock.as_ref().unwrap().state,
            CompilerLockState::CanonicalReady
        );
        assert_eq!(
            result.compiler_lock.as_ref().unwrap().composition_seed,
            Some(0)
        );
        assert_eq!(result.delivery_summary.recognized_but_ignored, 0);
    }
    assert_eq!(ja.canonical_semantic_bytes, en.canonical_semantic_bytes);
    assert_eq!(
        en.canonical_semantic_bytes,
        en_format.canonical_semantic_bytes
    );
    assert_eq!(
        ja.compiler_lock
            .as_ref()
            .unwrap()
            .canonical_pre_expansion_digest,
        en.compiler_lock
            .as_ref()
            .unwrap()
            .canonical_pre_expansion_digest
    );
    assert_ne!(
        ja.compiler_lock.as_ref().unwrap().visible_source_digest,
        en.compiler_lock.as_ref().unwrap().visible_source_digest
    );
    assert_ne!(
        ja.compiler_lock.as_ref().unwrap().full_digest,
        en.compiler_lock.as_ref().unwrap().full_digest
    );

    let different_number = compile(
        "circle white twelve",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    assert_ne!(
        en.canonical_semantic_bytes,
        different_number.canonical_semantic_bytes
    );
    let different_multiplicity = compile(
        "circle circle white eight",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    assert_ne!(
        en.canonical_semantic_bytes,
        different_multiplicity.canonical_semantic_bytes
    );
}

#[test]
fn definition_identity_is_not_seed_input_and_expanded_meaning_excludes_definition_provenance() {
    let plain = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Meaning","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"}}}]}"#,
    );
    let unused_component = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Meaning","version":"1.0.0","parameters":{},"components":{"unused":{"parameters":{},"body":[]}},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"}}}]}"#,
    );
    assert_ne!(
        plain.identity().unwrap().full_digest_hex(),
        unused_component.identity().unwrap().full_digest_hex()
    );

    let left = compile_locked(
        "Canon.Meaning",
        ResolvedInstructionLanguage::En,
        &[plain.clone()],
        Some(17),
        LIMITS,
    );
    let right = compile_locked(
        "Canon.Meaning",
        ResolvedInstructionLanguage::En,
        &[unused_component],
        Some(17),
        LIMITS,
    );
    assert_eq!(
        left.canonical_semantic_bytes,
        right.canonical_semantic_bytes
    );
    assert_eq!(
        left.derived_seeds[0].full_digest_hex(),
        right.derived_seeds[0].full_digest_hex()
    );
    assert_eq!(
        left.compiler_lock.as_ref().unwrap().expanded_meaning_digest,
        right
            .compiler_lock
            .as_ref()
            .unwrap()
            .expanded_meaning_digest
    );
    assert_ne!(
        left.compiler_lock.as_ref().unwrap().definition_identities,
        right.compiler_lock.as_ref().unwrap().definition_identities
    );
    assert_ne!(
        left.compiler_lock.as_ref().unwrap().full_digest,
        right.compiler_lock.as_ref().unwrap().full_digest
    );

    let different_composition_seed = compile_locked(
        "Canon.Meaning",
        ResolvedInstructionLanguage::En,
        &[plain],
        Some(18),
        LIMITS,
    );
    assert_eq!(
        left.canonical_semantic_bytes,
        different_composition_seed.canonical_semantic_bytes
    );
    assert_ne!(
        left.derived_seeds[0].full_digest_hex(),
        different_composition_seed.derived_seeds[0].full_digest_hex()
    );
    assert_eq!(
        left.compiler_lock.as_ref().unwrap().expanded_meaning_digest,
        different_composition_seed
            .compiler_lock
            .as_ref()
            .unwrap()
            .expanded_meaning_digest
    );
    assert_ne!(
        left.compiler_lock.as_ref().unwrap().full_digest,
        different_composition_seed
            .compiler_lock
            .as_ref()
            .unwrap()
            .full_digest
    );
}

#[test]
fn exhaustive_delivery_mapping_has_no_default_or_ignored_bucket() {
    let fixture = fixture();
    let definition = fixture_definition(&fixture);
    let color = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Color","version":"1.0.0","parameters":{"value":{"type":"semantic_ref","category":"color"}},"components":{},"body":[]}"#,
    );
    let emits_two = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Two","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{}},{"op":"emit","binding":null,"fields":{}}]}"#,
    );

    let cases = [
        (
            "explicit-and-syntax",
            compile(
                "the circle",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::CanonicalReady,
        ),
        (
            "relation-zero-hole",
            compile(
                "eight along twelve",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::IncompleteKnownHole,
        ),
        (
            "relation-exact-one",
            compile(
                "eight along circle",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::CanonicalReady,
        ),
        (
            "relation-multiple-conflict",
            compile(
                "circle with line of square",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::BlockedConflict,
        ),
        (
            "parser-hole",
            compile("many", ResolvedInstructionLanguage::En, &[], None, LIMITS),
            CompilerLockState::IncompleteKnownHole,
        ),
        (
            "unknown-blocking",
            compile(
                "mystery",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::BlockedDiagnostic,
        ),
        (
            "macro-missing-hole",
            compile(
                "Canon.Empty",
                ResolvedInstructionLanguage::En,
                &[definition.clone()],
                None,
                LIMITS,
            ),
            CompilerLockState::IncompleteKnownHole,
        ),
        (
            "macro-ambiguous-conflict",
            compile_locked(
                "Canon.Color white black",
                ResolvedInstructionLanguage::En,
                &[color.clone()],
                None,
                LIMITS,
            ),
            CompilerLockState::BlockedConflict,
        ),
        (
            "expansion-diagnostic-hole",
            compile_locked(
                "Canon.Two",
                ResolvedInstructionLanguage::En,
                &[emits_two],
                None,
                MacroExpansionLimits {
                    max_nodes_per_invocation: 1,
                    ..LIMITS
                },
            ),
            CompilerLockState::IncompleteKnownHole,
        ),
    ];
    let actual_ids = cases.iter().map(|(id, _, _)| *id).collect::<HashSet<_>>();
    assert_eq!(
        actual_ids,
        fixture
            .delivery_case_ids
            .iter()
            .map(String::as_str)
            .collect()
    );
    for (id, result, expected_state) in cases {
        assert_eq!(
            result.compiler_lock.as_ref().unwrap().state,
            expected_state,
            "{id}"
        );
        assert_eq!(
            result.canonical_semantic_bytes.is_some(),
            matches!(
                expected_state,
                CompilerLockState::CanonicalReady | CompilerLockState::IncompleteKnownHole
            ),
            "{id}"
        );
        assert_eq!(result.delivery_summary.unspecified, 0, "{id}");
        assert_eq!(result.delivery_summary.defaulted, 0, "{id}");
        assert_eq!(result.delivery_summary.recognized_but_ignored, 0, "{id}");
        assert_eq!(
            result.deliveries.len(),
            result.delivery_summary.explicit
                + result.delivery_summary.holes
                + result.delivery_summary.conflicts
                + result.delivery_summary.blocking_diagnostics
                + result.delivery_summary.syntax_only,
            "{id}"
        );
    }

    let invalid = compile(
        "circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        MacroExpansionLimits {
            max_invocations: 0,
            ..LIMITS
        },
    );
    assert!(invalid.compiler_lock.is_none());
    assert_eq!(invalid.delivery_summary.blocking_diagnostics, 1);
}

#[test]
fn successful_expanded_nodes_are_explicit_deliveries_without_entering_pre_expansion_bytes() {
    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"One","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"}}}]}"#,
    );
    let result = compile_locked(
        "Canon.One",
        ResolvedInstructionLanguage::En,
        &[definition],
        Some(3),
        LIMITS,
    );
    assert_eq!(
        result.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
    assert_eq!(result.macro_expansion.as_ref().unwrap().expanded.len(), 1);
    assert!(
        result.deliveries.iter().any(
            |item| item.id.starts_with("expanded:") && item.descriptor.contains("semantic_ref")
        )
    );
    assert!(
        !String::from_utf8(result.canonical_semantic_bytes.unwrap())
            .unwrap()
            .contains("semantic_ref")
    );
}

#[test]
fn source_independent_known_hole_still_seeds_every_complete_binding_and_runs_i582() {
    let fixture = fixture();
    let definition = fixture_definition(&fixture);
    let result = compile_locked(
        "Canon.Empty many",
        ResolvedInstructionLanguage::En,
        &[definition],
        Some(5),
        LIMITS,
    );
    assert_eq!(
        result.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::IncompleteKnownHole
    );
    assert!(result.canonical_semantic_bytes.is_some());
    assert_eq!(result.holes.len(), 1);
    assert_eq!(result.derived_seeds.len(), 1);
    assert!(result.parameter_binding.is_none());
    let expansion = result.macro_expansion.as_ref().unwrap();
    assert_eq!(expansion.parameter_binding.complete.len(), 1);
    assert_eq!(expansion.expanded.len(), 1);
    assert!(expansion.diagnostics.is_empty());
    let lock = result.compiler_lock.as_ref().unwrap();
    assert!(lock.canonical_pre_expansion_digest.is_none());
    assert!(lock.macro_seeds.is_empty());
    assert!(lock.expanded_meaning_digest.is_none());
}

#[test]
fn fixture_schema_and_closed_ids_are_stable() {
    let fixture = fixture();
    assert_eq!(
        fixture.schema,
        "inku.compiler-lock-visible-patch-v1-fixture.v1"
    );
    assert_eq!(fixture.version, 1);
    assert_eq!(
        CANONICAL_SEMANTIC_DDL_SCHEMA_ID,
        "inku.canonical-semantic-ddl.v1"
    );
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));
    assert_eq!(
        fixture
            .delivery_case_ids
            .iter()
            .collect::<HashSet<_>>()
            .len(),
        9
    );
    assert_eq!(
        fixture.patch_case_ids.iter().collect::<HashSet<_>>().len(),
        19
    );
}

fn fixture() -> Fixture {
    serde_json::from_str(FIXTURE).unwrap()
}

fn fixture_definition(fixture: &Fixture) -> MacroDefinition {
    definition_from(&serde_json::to_string(&fixture.definition).unwrap())
}

fn definition_from(value: &str) -> MacroDefinition {
    MacroDefinition::from_json(value).unwrap()
}

fn compile(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    seed: Option<u64>,
    limits: MacroExpansionLimits,
) -> inku_ddl::TypedDdlCompilation {
    compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        definitions,
        seed,
        limits,
    )
}

fn compile_locked(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    seed: Option<u64>,
    limits: MacroExpansionLimits,
) -> inku_ddl::TypedDdlCompilation {
    let locks = definitions.iter().map(lock_for).collect::<Vec<_>>();
    compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, locks).unwrap(),
        definitions,
        seed,
        limits,
    )
}

fn locked_document(
    source: &str,
    language: ResolvedInstructionLanguage,
    definition: &MacroDefinition,
) -> NormalizedDdlDocument {
    NormalizedDdlDocument::new(source, language, vec![lock_for(definition)]).unwrap()
}

fn lock_for(definition: &MacroDefinition) -> MacroLock {
    let identity = definition.identity().unwrap();
    MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap()
}

fn sha256(value: &[u8]) -> String {
    Sha256::digest(value)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
