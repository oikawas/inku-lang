use std::collections::{HashMap, HashSet};

use inku_ddl::{
    BoundMacroParameterValue, ClauseAtom, MACRO_PARAMETER_BINDING_SCHEMA_ID, MacroDefinition,
    MacroLock, MacroParameterBindingDiagnosticKind, NormalizedDdlDocument, ParameterSchema,
    ResolvedInstructionLanguage, bind_macro_parameters, resolve_macro_invocations,
};
use serde::Deserialize;
use serde_json::Value;

const FIXTURE: &str = include_str!("fixtures/macro-parameter-binding-v1.json");

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixture {
    schema: String,
    version: u32,
    definitions: HashMap<String, Value>,
    valid_cases: Vec<ValidCase>,
    diagnostic_cases: Vec<DiagnosticCase>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ValidCase {
    id: String,
    source: String,
    language: String,
    locks: Vec<LockCase>,
    definition_inputs: Vec<String>,
    expected_complete: usize,
    expected_parameters: Vec<ExpectedParameter>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DiagnosticCase {
    id: String,
    source: String,
    language: String,
    locks: Vec<LockCase>,
    definition_inputs: Vec<String>,
    expected_kind: Option<String>,
    expected_binding_diagnostics: usize,
    expected_resolution_diagnostics: usize,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LockCase {
    definition: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ExpectedParameter {
    invocation_ordinal: u64,
    name: String,
    value_kind: String,
    value: String,
}

#[test]
fn unique_complete_assignments_bind_typed_same_clause_facts_without_changing_i580() {
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
        let accepted = resolve_macro_invocations(&document, &definitions).unwrap();
        let result = bind_macro_parameters(&document, &definitions).unwrap();

        assert_eq!(result.macro_resolution, accepted, "{}", case.id);
        assert!(result.diagnostics.is_empty(), "{}", case.id);
        assert_eq!(result.complete.len(), case.expected_complete, "{}", case.id);
        assert_eq!(
            result
                .complete
                .iter()
                .map(|binding| binding.invocation_index)
                .collect::<Vec<_>>(),
            (0..case.expected_complete).collect::<Vec<_>>(),
            "{}",
            case.id
        );

        let parameters = result
            .complete
            .iter()
            .flat_map(|binding| &binding.parameters)
            .collect::<Vec<_>>();
        assert_eq!(
            parameters.len(),
            case.expected_parameters.len(),
            "{}",
            case.id
        );
        for (actual, expected) in parameters.iter().zip(&case.expected_parameters) {
            assert_eq!(
                actual.invocation_ordinal, expected.invocation_ordinal,
                "{}",
                case.id
            );
            assert_eq!(actual.parameter_name, expected.name, "{}", case.id);
            assert_eq!(
                value_kind(&actual.value),
                expected.value_kind,
                "{}",
                case.id
            );
            assert_eq!(
                schema_kind(&actual.parameter_schema),
                expected.value_kind,
                "{}",
                case.id
            );
            assert_eq!(value_text(&actual.value), expected.value, "{}", case.id);
            assert_eq!(
                actual.source_span,
                actual.value.source_span(),
                "{}",
                case.id
            );
            assert_eq!(
                &case.source[actual.source_span.start_byte..actual.source_span.end_byte],
                actual.source_surface,
                "{}",
                case.id
            );
            let clause = &result
                .macro_resolution
                .relation_reference_evidence
                .attachment_evidence
                .noun_phrase
                .clause_stream
                .clauses[actual.source_fact_clause_index];
            assert_eq!(
                clause.atoms[actual.source_fact_atom_index].span(),
                actual.source_span,
                "{}",
                case.id
            );
            if let BoundMacroParameterValue::SemanticRef {
                source_asset_id,
                canonical_surface_ja,
                ..
            } = &actual.value
            {
                assert_eq!(source_asset_id, "inku.saijiki.v1", "{}", case.id);
                assert!(!canonical_surface_ja.is_empty(), "{}", case.id);
            }
        }
        if case.id == "unrelated-fact-preserved" {
            let bound_spans = parameters
                .iter()
                .map(|parameter| parameter.source_span)
                .collect::<Vec<_>>();
            let candidate_spans = result
                .macro_resolution
                .relation_reference_evidence
                .attachment_evidence
                .noun_phrase
                .clause_stream
                .clauses
                .iter()
                .flat_map(|clause| &clause.atoms)
                .filter_map(|atom| match atom {
                    ClauseAtom::CoreRole(_)
                    | ClauseAtom::RemainingRole(_)
                    | ClauseAtom::UnattachedExactNumber(_) => Some(atom.span()),
                    _ => None,
                })
                .collect::<Vec<_>>();
            assert_eq!(candidate_spans.len(), 2);
            assert_eq!(bound_spans.len(), 1);
            assert_eq!(
                candidate_spans
                    .iter()
                    .filter(|span| !bound_spans.contains(span))
                    .count(),
                1
            );
        }
    }
}

#[test]
fn incomplete_or_nonunique_clause_assignments_return_only_stable_diagnostics() {
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
        let accepted = resolve_macro_invocations(&document, &definitions).unwrap();
        let result = bind_macro_parameters(&document, &definitions).unwrap();

        assert_eq!(result.macro_resolution, accepted, "{}", case.id);
        assert!(result.complete.is_empty(), "{}", case.id);
        assert_eq!(
            result.diagnostics.len(),
            case.expected_binding_diagnostics,
            "{}",
            case.id
        );
        assert_eq!(
            result.macro_resolution.diagnostics.len(),
            case.expected_resolution_diagnostics,
            "{}",
            case.id
        );
        if let Some(expected) = &case.expected_kind {
            assert!(
                result
                    .diagnostics
                    .iter()
                    .all(|diagnostic| diagnostic_kind_name(diagnostic.kind) == expected),
                "{}: {:?}",
                case.id,
                result.diagnostics
            );
        }
    }
}

#[test]
fn core_thinness_is_not_promoted_to_a_macro_semantic_fact() {
    let definition = MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Bind","heading":"ThinParam","version":"1.0.0","parameters":{"value":{"type":"semantic_ref","category":"variation"}},"components":{},"body":[]}"#,
    )
    .unwrap();
    let identity = definition.identity().unwrap();
    let lock = MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap();
    let document = NormalizedDdlDocument::new(
        "Bind.ThinParam thin",
        ResolvedInstructionLanguage::En,
        vec![lock],
    )
    .unwrap();
    let result = bind_macro_parameters(&document, std::slice::from_ref(&definition)).unwrap();

    assert!(result.complete.is_empty());
    assert_eq!(result.diagnostics.len(), 1);
    assert_eq!(
        result.diagnostics[0].kind,
        MacroParameterBindingDiagnosticKind::MissingCompatibleFact
    );
    assert!(
        result
            .macro_resolution
            .relation_reference_evidence
            .attachment_evidence
            .noun_phrase
            .clause_stream
            .clauses
            .iter()
            .flat_map(|clause| &clause.atoms)
            .any(|atom| matches!(atom, ClauseAtom::CoreModifier(_)))
    );
}

#[test]
fn lexical_place_facts_bind_as_one_canonical_value_without_losing_source() {
    let definition = MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Bind","heading":"Place","version":"1.0.0","parameters":{"where":{"type":"semantic_ref","category":"place"}},"components":{},"body":[]}"#,
    )
    .unwrap();

    for source_surface in ["center", "middle"] {
        let identity = definition.identity().unwrap();
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap();
        let source = format!("Bind.Place {source_surface}");
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, vec![lock])
                .unwrap();
        let result = bind_macro_parameters(&document, std::slice::from_ref(&definition)).unwrap();

        assert!(result.diagnostics.is_empty(), "{source_surface}");
        let parameter = &result.complete[0].parameters[0];
        assert_eq!(parameter.source_surface, source_surface);
        let BoundMacroParameterValue::SemanticRef {
            category,
            canonical_id,
            ..
        } = &parameter.value
        else {
            panic!("{source_surface}: expected semantic Place binding");
        };
        assert_eq!(category, "place");
        assert_eq!(canonical_id, "center");
    }
}

#[test]
fn schema_fixture_and_required_boundary_coverage_are_stable() {
    let fixture = load_fixture();
    assert_eq!(fixture.schema, "inku.macro-parameter-binding-v1-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(
        MACRO_PARAMETER_BINDING_SCHEMA_ID,
        "inku.macro-parameter-binding.v1"
    );
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .valid_cases
        .iter()
        .map(|case| case.id.as_str())
        .chain(fixture.diagnostic_cases.iter().map(|case| case.id.as_str()))
        .collect::<HashSet<_>>();
    assert_eq!(
        ids.len(),
        fixture.valid_cases.len() + fixture.diagnostic_cases.len()
    );
    for required in [
        "zero-parameter",
        "ja-no-whitespace",
        "en-whitespace",
        "integer",
        "integer-to-number",
        "all-eleven-semantic-categories",
        "unique-multiple-parameters",
        "two-invocations-disjoint-facts",
        "unrelated-fact-preserved",
        "missing",
        "same-category-duplicate",
        "same-type-permutation",
        "shared-fact",
        "integer-overflow",
        "number-precision-loss",
        "boolean-unsupported",
        "list-unsupported",
        "i580-unresolved",
        "cross-clause-fallback-excluded",
        "nonfact-atoms-excluded",
    ] {
        assert!(
            ids.contains(required),
            "missing required fixture case: {required}"
        );
    }
    assert!(!FIXTURE.contains("@invoke"));
    assert!(!FIXTURE.contains("fires_on"));
}

fn load_fixture() -> Fixture {
    serde_json::from_str(FIXTURE).expect("fixture must be valid JSON")
}

fn definition(fixture: &Fixture, id: &str) -> MacroDefinition {
    MacroDefinition::from_json(&serde_json::to_string(&fixture.definitions[id]).unwrap())
        .unwrap_or_else(|error| panic!("{id}: invalid definition: {error}"))
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

fn parse_language(value: &str, id: &str) -> ResolvedInstructionLanguage {
    match value {
        "ja" => ResolvedInstructionLanguage::Ja,
        "en" => ResolvedInstructionLanguage::En,
        _ => panic!("{id}: invalid language"),
    }
}

fn value_kind(value: &BoundMacroParameterValue) -> String {
    match value {
        BoundMacroParameterValue::Integer { .. } => "integer",
        BoundMacroParameterValue::Number { .. } => "number",
        BoundMacroParameterValue::SemanticRef { .. } => "semantic_ref",
    }
    .to_owned()
}

fn value_text(value: &BoundMacroParameterValue) -> String {
    match value {
        BoundMacroParameterValue::Integer { value, .. } => value.to_string(),
        BoundMacroParameterValue::Number { value, .. } => value.to_string(),
        BoundMacroParameterValue::SemanticRef {
            category,
            canonical_id,
            ..
        } => format!("{category}:{canonical_id}"),
    }
}

fn schema_kind(schema: &ParameterSchema) -> String {
    match schema {
        ParameterSchema::Integer => "integer",
        ParameterSchema::Number => "number",
        ParameterSchema::SemanticRef { .. } => "semantic_ref",
        ParameterSchema::Boolean => "boolean",
        ParameterSchema::List { .. } => "list",
    }
    .to_owned()
}

fn diagnostic_kind_name(kind: MacroParameterBindingDiagnosticKind) -> &'static str {
    match kind {
        MacroParameterBindingDiagnosticKind::MissingCompatibleFact => "missing_compatible_fact",
        MacroParameterBindingDiagnosticKind::AmbiguousCompleteAssignment => {
            "ambiguous_complete_assignment"
        }
        MacroParameterBindingDiagnosticKind::SharedFact => "shared_fact",
        MacroParameterBindingDiagnosticKind::UnsupportedSchema => "unsupported_schema",
        MacroParameterBindingDiagnosticKind::NumericRange => "numeric_range",
        MacroParameterBindingDiagnosticKind::NumericPrecision => "numeric_precision",
        MacroParameterBindingDiagnosticKind::DefinitionIdentityOwnershipMismatch => {
            "definition_identity_ownership_mismatch"
        }
        MacroParameterBindingDiagnosticKind::SourceClauseAtomOwnershipMismatch => {
            "source_clause_atom_ownership_mismatch"
        }
    }
}
