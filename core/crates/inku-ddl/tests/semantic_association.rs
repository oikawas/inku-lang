use std::collections::{HashMap, HashSet};

use inku_ddl::{
    ClauseAtom, ClauseSeparatorKind, ClauseStream, CoreRoleKind, NormalizedDdlDocument,
    OwnedSemanticOccurrence, RemainingRoleKind, ResolvedInstructionLanguage,
    SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID, SemanticAssociationResult, SourceOccurrence,
    associate_semantic_entities,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/semantic-association-v2.json");

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixture {
    schema: String,
    version: u32,
    cases: Vec<Case>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    id: String,
    language: String,
    source: String,
    entity_count: usize,
    issue_kinds: Vec<String>,
    canonical: Option<String>,
    owned_occurrence_count: usize,
    #[serde(default)]
    explicit_touches: Vec<String>,
    #[serde(default)]
    explicit_continuities: Vec<String>,
    #[serde(default)]
    explicit_angles: Vec<String>,
}

#[test]
fn fixture_associates_single_head_entities_without_surface_order_rules() {
    let fixture = load_fixture();
    let mut canonical_by_case = HashMap::new();

    for case in &fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source.clone(),
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap_or_else(|error| panic!("{}: unexpected document diagnostic: {error}", case.id));
        let result = associate_semantic_entities(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected clause-stream error: {error}", case.id));

        assert_eq!(
            result.schema_id, SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
            "{}",
            case.id
        );
        assert_eq!(result.ast.entities.len(), case.entity_count, "{}", case.id);
        assert_eq!(
            result
                .issues
                .iter()
                .map(|issue| issue.kind.as_str())
                .collect::<Vec<_>>(),
            case.issue_kinds
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}",
            case.id
        );
        assert_eq!(
            result.canonical_bytes.as_deref(),
            case.canonical.as_ref().map(String::as_bytes),
            "{}",
            case.id
        );
        assert_eq!(
            result.ast.complete,
            result.issues.is_empty(),
            "{}: only issue-free AST is complete",
            case.id
        );
        assert_eq!(
            result.owned_occurrence_count, case.owned_occurrence_count,
            "{}",
            case.id
        );
        assert_eq!(
            result.delivered_occurrence_count, result.owned_occurrence_count,
            "{}: every slice-owned occurrence must be delivered exactly once",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| entity.touch.as_ref().map(|term| term.identity.id.as_str()))
                .collect::<Vec<_>>(),
            case.explicit_touches
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Touch fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| entity
                    .continuity
                    .as_ref()
                    .map(|term| term.identity.id.as_str()))
                .collect::<Vec<_>>(),
            case.explicit_continuities
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Continuity fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| entity.angle.as_ref().map(|term| term.identity.id.as_str()))
                .collect::<Vec<_>>(),
            case.explicit_angles
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Angle fields",
            case.id
        );
        assert_source_provenance(case, &result);
        assert_owned_occurrence_join(case, &result);

        if let Some(canonical) = &case.canonical {
            canonical_by_case.insert(case.id.as_str(), canonical.as_str());
        }
    }

    let equivalent = [
        "ja-canonical-order-one",
        "ja-canonical-order-two",
        "en-canonical-order-one",
        "en-canonical-order-two",
        "en-case-comma-space-soft-line-break",
    ]
    .map(|id| canonical_by_case[id]);
    assert!(equivalent.windows(2).all(|pair| pair[0] == pair[1]));
    assert_ne!(
        canonical_by_case["ownership-a"],
        canonical_by_case["ownership-b"]
    );
    let styled_equivalent = [
        "ja-style-order-one",
        "ja-style-order-two",
        "en-style-order-one",
        "en-style-order-two",
        "style-soft-line-break",
    ]
    .map(|id| canonical_by_case[id]);
    assert!(styled_equivalent.windows(2).all(|pair| pair[0] == pair[1]));
    assert_ne!(
        canonical_by_case["en-style-order-one"],
        canonical_by_case["style-touch-contrast"]
    );
    assert_ne!(
        canonical_by_case["en-style-order-one"],
        canonical_by_case["style-continuity-contrast"]
    );
    assert_ne!(
        canonical_by_case["en-style-order-one"],
        canonical_by_case["style-angle-contrast"]
    );
}

#[test]
fn fixture_schema_and_required_semantic_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(
        SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
        "inku.semantic-entity-association.v2"
    );
    assert_eq!(
        fixture.schema,
        "inku.semantic-entity-association-fixture.v2"
    );
    assert_eq!(fixture.version, 2);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "ja-canonical-order-one",
        "ja-canonical-order-two",
        "en-canonical-order-one",
        "en-canonical-order-two",
        "en-case-comma-space-soft-line-break",
        "ownership-a",
        "ownership-b",
        "multi-head-ambiguity",
        "orphan-color",
        "orphan-quantity",
        "conflicting-colors",
        "conflicting-quantities",
        "upstream-hole-retained",
        "upstream-unknown-retained",
        "negative-quantity-remains-hole",
        "unobserved-order-and-vocabulary",
        "ja-style-order-one",
        "ja-style-order-two",
        "en-style-order-one",
        "en-style-order-two",
        "style-touch-only",
        "style-touch-contrast",
        "style-continuity-contrast",
        "style-angle-contrast",
        "conflicting-touches",
        "conflicting-continuities",
        "conflicting-angles",
        "orphan-style-terms",
        "multi-head-style-ambiguity",
        "regional-style-ownership",
        "style-soft-line-break",
        "style-upstream-issue-retained",
        "unobserved-primitive-style-combination",
    ] {
        assert!(
            ids.contains(required),
            "missing required fixture case: {required}"
        );
    }
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

fn assert_source_provenance(case: &Case, result: &SemanticAssociationResult) {
    for entity in &result.ast.entities {
        assert_source_occurrence(case, &entity.head.provenance.source, &result.clause_stream);
        if let Some(color) = &entity.color {
            assert_source_occurrence(case, &color.provenance.source, &result.clause_stream);
        }
        if let Some(quantity) = &entity.quantity {
            assert_source_occurrence(case, &quantity.provenance, &result.clause_stream);
        }
        for term in [&entity.touch, &entity.continuity, &entity.angle]
            .into_iter()
            .flatten()
        {
            assert_source_occurrence(case, &term.provenance.source, &result.clause_stream);
            assert_eq!(
                entity.head.provenance.source.region_index, term.provenance.source.region_index,
                "{}: entity attribute must remain in its sentence region",
                case.id
            );
        }
    }
    for issue in &result.issues {
        for occurrence in &issue.occurrences {
            assert_eq!(
                occurrence.source().region_index,
                issue.region_index,
                "{}",
                case.id
            );
            assert_source_occurrence(case, occurrence.source(), &result.clause_stream);
        }
        if let Some(diagnostic) = &issue.upstream_diagnostic {
            assert_eq!(
                diagnostic.surface,
                case.source[diagnostic.span.start_byte..diagnostic.span.end_byte],
                "{}: upstream diagnostic source slice",
                case.id
            );
            assert_eq!(
                issue.region_index,
                expected_region_index(&result.clause_stream, diagnostic.span),
                "{}: upstream diagnostic region provenance",
                case.id
            );
        }
    }
}

fn assert_source_occurrence(case: &Case, occurrence: &SourceOccurrence, stream: &ClauseStream) {
    let span = occurrence.span;
    assert!(
        span.start_byte < span.end_byte,
        "{}: empty occurrence",
        case.id
    );
    assert!(
        span.end_byte <= case.source.len(),
        "{}: span outside source",
        case.id
    );
    assert!(
        case.source.is_char_boundary(span.start_byte)
            && case.source.is_char_boundary(span.end_byte),
        "{}: non-UTF-8-boundary span",
        case.id
    );
    assert_eq!(
        occurrence.surface,
        case.source[span.start_byte..span.end_byte],
        "{}: source slice mismatch",
        case.id
    );
    assert_eq!(
        occurrence.language,
        parse_language(&case.language, &case.id),
        "{}: language provenance",
        case.id
    );
    let atom = stream
        .clauses
        .get(occurrence.clause_index)
        .and_then(|clause| clause.atoms.get(occurrence.atom_index))
        .unwrap_or_else(|| panic!("{}: invalid clause / atom provenance", case.id));
    assert_eq!(atom.span(), occurrence.span, "{}: atom provenance", case.id);
    assert_eq!(
        occurrence.region_index,
        expected_region_index(stream, occurrence.span),
        "{}: region provenance",
        case.id
    );
}

fn expected_region_index(stream: &ClauseStream, span: inku_ddl::SourceSpan) -> usize {
    stream
        .separators
        .iter()
        .filter(|separator| {
            separator.kind == ClauseSeparatorKind::SentenceEnd
                && separator.span.end_byte <= span.start_byte
        })
        .count()
}

fn assert_owned_occurrence_join(case: &Case, result: &inku_ddl::SemanticAssociationResult) {
    let input_spans = result
        .clause_stream
        .clauses
        .iter()
        .flat_map(|clause| &clause.atoms)
        .filter_map(|atom| match atom {
            ClauseAtom::CoreRole(term)
                if matches!(
                    term.role,
                    CoreRoleKind::Primitive | CoreRoleKind::Color | CoreRoleKind::Touch
                ) =>
            {
                Some(term.span)
            }
            ClauseAtom::RemainingRole(term)
                if matches!(
                    term.role,
                    RemainingRoleKind::Continuity | RemainingRoleKind::Angle
                ) =>
            {
                Some(term.span)
            }
            ClauseAtom::UnattachedExactNumber(number) => Some(number.span),
            _ => None,
        })
        .collect::<Vec<_>>();

    let mut output_spans = Vec::new();
    for entity in &result.ast.entities {
        output_spans.push(entity.head.provenance.source.span);
        if let Some(color) = &entity.color {
            output_spans.push(color.provenance.source.span);
        }
        if let Some(quantity) = &entity.quantity {
            output_spans.push(quantity.provenance.span);
        }
        for term in [&entity.touch, &entity.continuity, &entity.angle]
            .into_iter()
            .flatten()
        {
            output_spans.push(term.provenance.source.span);
        }
    }
    for occurrence in result.issues.iter().flat_map(|issue| &issue.occurrences) {
        output_spans.push(match occurrence {
            OwnedSemanticOccurrence::Head(term) | OwnedSemanticOccurrence::Color(term) => {
                term.provenance.source.span
            }
            OwnedSemanticOccurrence::Quantity(quantity) => quantity.provenance.span,
            OwnedSemanticOccurrence::Touch(term)
            | OwnedSemanticOccurrence::Continuity(term)
            | OwnedSemanticOccurrence::Angle(term) => term.provenance.source.span,
        });
    }

    assert_eq!(output_spans.len(), input_spans.len(), "{}", case.id);
    for span in input_spans {
        assert_eq!(
            output_spans
                .iter()
                .filter(|candidate| **candidate == span)
                .count(),
            1,
            "{}: owned span {span:?} must join exactly once",
            case.id
        );
    }
}
