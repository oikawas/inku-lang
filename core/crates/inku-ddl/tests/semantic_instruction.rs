use std::collections::{HashMap, HashSet};

use inku_ddl::{
    ClauseAtom, ClauseSeparatorKind, ClauseStream, MacroLock, NormalizedDdlDocument,
    RemainingRoleKind, ResolvedInstructionLanguage, SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
    SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID, SemanticInstructionAssociationResult,
    SourceOccurrence, associate_semantic_instructions,
    semantic_instruction::SemanticInstructionOccurrenceRole,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/semantic-instruction-v4.json");

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
    #[serde(default)]
    macro_locks: Vec<FixtureMacroLock>,
    instruction_actions: Vec<Option<String>>,
    instruction_positions: Vec<Option<String>>,
    #[serde(default)]
    instruction_touches: Vec<Option<String>>,
    #[serde(default)]
    instruction_continuities: Vec<Option<String>>,
    #[serde(default)]
    instruction_angles: Vec<Option<String>>,
    #[serde(default)]
    instruction_surface_qualities: Vec<Option<String>>,
    #[serde(default)]
    instruction_surface_intensities: Vec<Option<String>>,
    association_issue_kinds: Vec<String>,
    instruction_issues: Vec<String>,
    canonical: Option<String>,
    owned_instruction_occurrence_count: usize,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct FixtureMacroLock {
    qualified_name: String,
    version: String,
    digest: String,
}

#[test]
fn fixture_associates_explicit_actions_and_positions_without_surface_order_rules() {
    let fixture = load_fixture();
    let mut canonical_by_case = HashMap::new();

    for case in &fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source.clone(),
            parse_language(&case.language, &case.id),
            case.macro_locks
                .iter()
                .map(|lock| {
                    MacroLock::new(&lock.qualified_name, &lock.version, &lock.digest)
                        .unwrap_or_else(|error| panic!("{}: invalid macro lock: {error}", case.id))
                })
                .collect(),
        )
        .unwrap_or_else(|error| panic!("{}: unexpected document diagnostic: {error}", case.id));
        let result = associate_semantic_instructions(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected clause-stream error: {error}", case.id));

        assert_eq!(
            result.schema_id, SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID,
            "{}",
            case.id
        );
        assert_eq!(
            result.association.schema_id, SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
            "{}: accepted I-584 result is retained",
            case.id
        );
        assert_eq!(
            result
                .ast
                .instructions
                .iter()
                .map(|instruction| {
                    instruction
                        .action
                        .as_ref()
                        .map(|action| action.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.instruction_actions
                .iter()
                .map(|action| action.as_deref())
                .collect::<Vec<_>>(),
            "{}",
            case.id
        );
        if !case.instruction_touches.is_empty() {
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .entity
                            .touch
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_touches
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Touch",
                case.id
            );
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .entity
                            .continuity
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_continuities
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Continuity",
                case.id
            );
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .entity
                            .angle
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_angles
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Angle",
                case.id
            );
        }
        if !case.instruction_surface_qualities.is_empty() {
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .entity
                            .surface
                            .quality
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_surface_qualities
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Surface quality",
                case.id
            );
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .entity
                            .surface
                            .intensity
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_surface_intensities
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Surface intensity",
                case.id
            );
        }
        assert_eq!(
            result
                .ast
                .instructions
                .iter()
                .map(|instruction| {
                    instruction
                        .position
                        .as_ref()
                        .map(|position| position.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.instruction_positions
                .iter()
                .map(|position| position.as_deref())
                .collect::<Vec<_>>(),
            "{}",
            case.id
        );
        assert_eq!(
            result
                .association
                .issues
                .iter()
                .map(|issue| issue.kind.as_str())
                .collect::<Vec<_>>(),
            case.association_issue_kinds
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}",
            case.id
        );
        assert_eq!(
            result
                .issues
                .iter()
                .map(|issue| {
                    let role = issue
                        .occurrences
                        .first()
                        .map(|occurrence| occurrence.role.as_str())
                        .expect("instruction issue owns at least one occurrence");
                    format!("{role}:{}", issue.kind.as_str())
                })
                .collect::<Vec<_>>(),
            case.instruction_issues,
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
            result.association.ast.complete && result.issues.is_empty(),
            "{}: only upstream-complete, instruction-issue-free AST is complete",
            case.id
        );
        assert_eq!(
            result.owned_instruction_occurrence_count, case.owned_instruction_occurrence_count,
            "{}",
            case.id
        );
        assert_eq!(
            result.delivered_instruction_occurrence_count,
            result.owned_instruction_occurrence_count,
            "{}: every Action / Position occurrence must be delivered exactly once",
            case.id
        );
        assert_source_provenance(case, &result);
        assert_instruction_occurrence_join(case, &result);

        if let Some(canonical) = &case.canonical {
            canonical_by_case.insert(case.id.as_str(), canonical.as_str());
        }
    }

    let equivalent = [
        "ja-position-order-one",
        "ja-position-order-two",
        "en-position-order-one",
        "en-position-order-two",
        "soft-line-break",
    ]
    .map(|id| canonical_by_case[id]);
    assert!(equivalent.windows(2).all(|pair| pair[0] == pair[1]));
    assert_ne!(
        canonical_by_case["en-position-order-one"],
        canonical_by_case["position-left-edge"]
    );
    assert_ne!(
        canonical_by_case["action-line-up-position-unspecified"],
        canonical_by_case["action-scatter-position-unspecified"]
    );
}

#[test]
fn fixture_schema_and_required_instruction_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(
        SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID,
        "inku.semantic-instruction-association.v4"
    );
    assert_eq!(
        fixture.schema,
        "inku.semantic-instruction-association-fixture.v4"
    );
    assert_eq!(fixture.version, 4);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "ja-position-order-one",
        "ja-position-order-two",
        "en-position-order-one",
        "en-position-order-two",
        "position-left-edge",
        "position-unspecified-action",
        "action-unspecified-position",
        "action-and-position-unspecified",
        "conflicting-positions",
        "orphan-position",
        "conflicting-actions-position-retained",
        "multi-head-action-position",
        "regional-instruction-ownership",
        "soft-line-break",
        "upstream-conflict-retained",
        "unobserved-primitive-action-position-combination",
        "style-fields-preserve-action-position",
        "style-conflict-preserves-action-position",
        "surface-fields-preserve-i588-and-action-position",
        "surface-conflict-preserves-action-position",
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

fn assert_source_provenance(case: &Case, result: &SemanticInstructionAssociationResult) {
    for instruction in &result.ast.instructions {
        if let Some(action) = &instruction.action {
            assert_eq!(action.identity.category, "movement", "{}", case.id);
            assert_source_occurrence(
                case,
                &action.provenance.source,
                &result.association.clause_stream,
            );
            assert_eq!(
                instruction.entity.head.provenance.source.region_index,
                action.provenance.source.region_index,
                "{}: entity and Action must share one sentence region",
                case.id
            );
        }
        if let Some(position) = &instruction.position {
            assert_eq!(position.identity.category, "place", "{}", case.id);
            assert_source_occurrence(
                case,
                &position.provenance.source,
                &result.association.clause_stream,
            );
            assert_eq!(
                instruction.entity.head.provenance.source.region_index,
                position.provenance.source.region_index,
                "{}: entity and Position must share one sentence region",
                case.id
            );
        }
    }
    for issue in &result.issues {
        for occurrence in &issue.occurrences {
            let expected_category = match occurrence.role {
                SemanticInstructionOccurrenceRole::Action => "movement",
                SemanticInstructionOccurrenceRole::Position => "place",
            };
            assert_eq!(
                occurrence.term.identity.category, expected_category,
                "{}",
                case.id
            );
            assert_eq!(
                occurrence.term.provenance.source.region_index, issue.region_index,
                "{}",
                case.id
            );
            assert_source_occurrence(
                case,
                &occurrence.term.provenance.source,
                &result.association.clause_stream,
            );
        }
    }
}

fn assert_source_occurrence(case: &Case, occurrence: &SourceOccurrence, stream: &ClauseStream) {
    let span = occurrence.span;
    assert!(
        span.start_byte < span.end_byte && span.end_byte <= case.source.len(),
        "{}: invalid occurrence span",
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

fn assert_instruction_occurrence_join(case: &Case, result: &SemanticInstructionAssociationResult) {
    let mut input = result
        .association
        .clause_stream
        .clauses
        .iter()
        .flat_map(|clause| &clause.atoms)
        .filter_map(|atom| match atom {
            ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Motion => {
                Some(("action", term.span))
            }
            ClauseAtom::RemainingRole(term) if term.role == RemainingRoleKind::Place => {
                Some(("position", term.span))
            }
            _ => None,
        })
        .collect::<Vec<_>>();
    input.sort_by_key(|(role, span)| (*role, span.start_byte));

    let mut output = result
        .ast
        .instructions
        .iter()
        .flat_map(|instruction| {
            instruction
                .action
                .iter()
                .map(|term| ("action", term.provenance.source.span))
                .chain(
                    instruction
                        .position
                        .iter()
                        .map(|term| ("position", term.provenance.source.span)),
                )
        })
        .chain(result.issues.iter().flat_map(|issue| {
            issue.occurrences.iter().map(|occurrence| {
                (
                    occurrence.role.as_str(),
                    occurrence.term.provenance.source.span,
                )
            })
        }))
        .collect::<Vec<_>>();
    output.sort_by_key(|(role, span)| (*role, span.start_byte));

    assert_eq!(output, input, "{}: instruction occurrence join", case.id);
}
