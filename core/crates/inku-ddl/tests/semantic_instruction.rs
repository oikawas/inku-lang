use std::collections::{HashMap, HashSet};

use inku_ddl::{
    ClauseAtom, ClauseSeparatorKind, ClauseStream, MacroLock, NormalizedDdlDocument,
    RemainingRoleKind, ResolvedInstructionLanguage, SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
    SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID, SemanticInstructionAssociationResult,
    SourceOccurrence, associate_semantic_instructions, saijiki_asset,
    semantic_instruction::SemanticInstructionOccurrenceRole,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/semantic-instruction-v7.json");

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
    #[serde(default)]
    instruction_fluctuation_amplitudes: Vec<Option<String>>,
    #[serde(default)]
    instruction_fluctuation_frequencies: Vec<Option<String>>,
    #[serde(default)]
    instruction_fluctuation_qualities: Vec<Option<String>>,
    #[serde(default)]
    instruction_proportion_aspects: Vec<Option<String>>,
    #[serde(default)]
    instruction_proportion_width_extents: Vec<Option<String>>,
    #[serde(default)]
    instruction_proportion_arc_forms: Vec<Option<String>>,
    #[serde(default)]
    instruction_relations: Vec<Option<String>>,
    #[serde(default)]
    instruction_relation_references: Vec<Option<String>>,
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
        if !case.instruction_fluctuation_amplitudes.is_empty() {
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .entity
                            .fluctuation
                            .amplitude
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_fluctuation_amplitudes
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Fluctuation amplitude",
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
                            .fluctuation
                            .frequency
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_fluctuation_frequencies
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Fluctuation frequency",
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
                            .fluctuation
                            .quality
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_fluctuation_qualities
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Fluctuation quality",
                case.id
            );
        }
        if !case.instruction_proportion_aspects.is_empty() {
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .entity
                            .proportion
                            .aspect
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_proportion_aspects
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Proportion aspect",
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
                            .proportion
                            .width_extent
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_proportion_width_extents
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Proportion width extent",
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
                            .proportion
                            .arc_form
                            .as_ref()
                            .map(|term| term.identity.id.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_proportion_arc_forms
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity Proportion arc form",
                case.id
            );
        }
        if !case.instruction_relations.is_empty() {
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .relation
                            .as_ref()
                            .map(|relation| relation.kind.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_relations
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: explicit relation kind",
                case.id
            );
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .relation
                            .as_ref()
                            .map(|relation| relation.reference.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_relation_references
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: explicit previous reference",
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
            result.association.ast.complete
                && result.issues.is_empty()
                && result.relation_issues.is_empty(),
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
        "inku.semantic-instruction-association.v7"
    );
    assert_eq!(
        fixture.schema,
        "inku.semantic-instruction-association-fixture.v7"
    );
    assert_eq!(fixture.version, 7);
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
        "fluctuation-fields-preserve-i589-and-action-position",
        "fluctuation-conflict-preserves-action-position",
    ] {
        assert!(
            ids.contains(required),
            "missing required fixture case: {required}"
        );
    }
}

#[test]
fn accepted_full_literals_form_closed_previous_edges_and_canonical_identity() {
    let asset = saijiki_asset();
    let shapes = asset
        .categories
        .iter()
        .find(|category| category.key == "katachi")
        .expect("accepted asset has Primitive rows");
    let shape = |english: &str| {
        shapes
            .words
            .iter()
            .find(|word| word.surface_en.as_deref() == Some(english))
            .unwrap_or_else(|| panic!("accepted asset has {english}"))
    };
    let line = shape("line");
    let square = shape("square");
    let circle = shape("circle");
    let mut canonical_by_relation = HashMap::<String, Vec<u8>>::new();

    for relation in &asset.relations {
        for (language, literals, line_surface, square_surface, circle_surface, ending) in [
            (
                ResolvedInstructionLanguage::Ja,
                &relation.literals_ja,
                line.surface_ja.as_str(),
                square.surface_ja.as_str(),
                circle.surface_ja.as_str(),
                "。",
            ),
            (
                ResolvedInstructionLanguage::En,
                &relation.literals_en,
                line.surface_en.as_deref().expect("line has EN surface"),
                square.surface_en.as_deref().expect("square has EN surface"),
                circle.surface_en.as_deref().expect("circle has EN surface"),
                ".",
            ),
        ] {
            for literal in literals {
                let (source, expected_reference, expected_instruction_count) = if relation
                    .relation_type
                    == "between"
                {
                    (
                        format!(
                            "{line_surface}{ending} {square_surface}{ending} {circle_surface} {literal}{ending}"
                        ),
                        "previous_two",
                        3,
                    )
                } else {
                    (
                        format!("{line_surface}{ending} {circle_surface} {literal}{ending}"),
                        "previous_one",
                        2,
                    )
                };
                let document = NormalizedDdlDocument::new(source.clone(), language, Vec::new())
                    .expect("accepted relation source forms a document");
                let result = associate_semantic_instructions(&document)
                    .expect("accepted relation source forms an instruction association");
                assert!(result.association.issues.is_empty(), "{literal}");
                assert!(result.issues.is_empty(), "{literal}");
                assert!(result.relation_issues.is_empty(), "{literal}");
                assert_eq!(
                    result.ast.instructions.len(),
                    expected_instruction_count,
                    "{literal}"
                );
                let edge = result
                    .ast
                    .instructions
                    .last()
                    .and_then(|instruction| instruction.relation.as_ref())
                    .expect("current instruction has one relation");
                assert_eq!(edge.kind.as_str(), relation.relation_type, "{literal}");
                assert_eq!(edge.reference.as_str(), expected_reference, "{literal}");
                assert_eq!(edge.provenance.surface, *literal, "{literal}");
                assert_eq!(result.owned_relation_occurrence_count, 1, "{literal}");
                assert_eq!(result.delivered_relation_occurrence_count, 1, "{literal}");

                let canonical = result.canonical_bytes.expect("issue-free canonical bytes");
                if let Some(expected) = canonical_by_relation.get(&relation.relation_type) {
                    assert_eq!(&canonical, expected, "{literal}: bilingual canonical");
                } else {
                    canonical_by_relation.insert(relation.relation_type.clone(), canonical.clone());
                }
                let canonical_json: serde_json::Value =
                    serde_json::from_slice(&canonical).expect("canonical JSON");
                let relation_value = canonical_json["instructions"]
                    .as_array()
                    .and_then(|instructions| instructions.last())
                    .and_then(|instruction| instruction.get("relation"))
                    .expect("canonical relation value");
                assert_eq!(
                    relation_value.as_object().map(|object| object.len()),
                    Some(2)
                );
                assert_eq!(relation_value["kind"], relation.relation_type);
                assert_eq!(relation_value["reference"], expected_reference);
            }
        }
    }
}

#[test]
fn relation_issues_and_short_surface_boundary_are_closed_without_fallback() {
    let asset = saijiki_asset();
    let relation = |kind: &str| {
        asset
            .relations
            .iter()
            .find(|relation| relation.relation_type == kind)
            .unwrap_or_else(|| panic!("accepted relation {kind}"))
    };
    let along = relation("along");
    let between = relation("between");
    let touching = relation("touching");
    let along_literal = along.literals_en.first().expect("along EN literal");
    let between_literal = between.literals_en.first().expect("between EN literal");
    let touching_literal = touching.literals_en.first().expect("touching EN literal");

    for (source, expected_issue, expected_owned) in [
        (
            format!("circle {along_literal}."),
            "missing_previous_one",
            1,
        ),
        (
            format!("line. circle {between_literal}."),
            "missing_previous_two",
            1,
        ),
        (
            format!("line. {along_literal}."),
            "missing_current_instruction",
            1,
        ),
        (
            format!("line. circle {along_literal} {touching_literal}."),
            "conflicting_relations",
            2,
        ),
    ] {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .expect("relation issue source forms a document");
        let result = associate_semantic_instructions(&document)
            .expect("relation issue source forms an association");
        assert_eq!(result.relation_issues.len(), 1, "{expected_issue}");
        assert_eq!(result.relation_issues[0].kind.as_str(), expected_issue);
        assert_eq!(
            result.relation_issues[0].occurrences.len(),
            expected_owned,
            "{expected_issue}"
        );
        assert_eq!(result.owned_relation_occurrence_count, expected_owned);
        assert_eq!(result.delivered_relation_occurrence_count, expected_owned);
        assert!(result.canonical_bytes.is_none(), "{expected_issue}");
    }

    let source = format!("line. circle {}.", along.surface_en);
    let document = NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
        .expect("short relation surface forms a document");
    let result = associate_semantic_instructions(&document)
        .expect("short relation surface forms an association");
    assert!(result.relation_issues.is_empty());
    assert_eq!(result.owned_relation_occurrence_count, 0);
    assert!(
        result
            .ast
            .instructions
            .iter()
            .all(|instruction| instruction.relation.is_none())
    );
    assert!(result.canonical_bytes.is_some());
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
