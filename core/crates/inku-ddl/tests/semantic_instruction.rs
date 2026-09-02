use std::collections::{HashMap, HashSet};

use inku_ddl::{
    ClauseAtom, ClauseSeparatorKind, ClauseStream, MacroDefinition, MacroLock,
    NormalizedDdlDocument, RemainingRoleKind, ResolvedInstructionLanguage,
    SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID, SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID,
    SemanticHead, SemanticInstructionAssociationResult, SemanticIssueCausalProvenance,
    SemanticUpstreamCausalRelation, SourceOccurrence, associate_semantic_instructions,
    associate_semantic_instructions_with_macro_binding, bind_macro_parameters, saijiki_asset,
    semantic_instruction::SemanticInstructionOccurrenceRole,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/semantic-instruction-v15.json");

#[test]
fn action_and_position_issues_retain_only_diagnostics_on_their_ownership_paths() {
    for (source, expected_kind) in [
        ("place mystery circle.", "ambiguous_action_ownership"),
        ("circle mystery at center.", "ambiguous_position_ownership"),
    ] {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .unwrap();
        let result = associate_semantic_instructions(&document).unwrap();
        let issue = result
            .issues
            .iter()
            .find(|issue| issue.kind.as_str() == expected_kind)
            .unwrap_or_else(|| panic!("expected {expected_kind}: {source}"));
        assert_eq!(issue.occurrences.len(), 1, "{source}");
        let SemanticIssueCausalProvenance::UpstreamDiagnostics(causes) = &issue.causal_provenance
        else {
            panic!("instruction issue must retain the diagnostic on its head path: {source}");
        };
        assert_eq!(causes.len(), 1, "{source}");
        assert_eq!(
            causes[0].relation,
            SemanticUpstreamCausalRelation::InstructionOwnershipPath,
            "{source}"
        );
        assert_eq!(
            &source[causes[0].span.start_byte..causes[0].span.end_byte],
            "mystery",
            "{source}"
        );
        assert!(
            result
                .association
                .issues
                .iter()
                .any(|upstream| upstream.upstream_diagnostic.is_some()),
            "the dedicated upstream issue remains separately delivered: {source}"
        );
        assert_eq!(
            result.delivered_instruction_occurrence_count,
            result.owned_instruction_occurrence_count,
            "{source}"
        );
    }
}

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
    head_group_members: Vec<Vec<usize>>,
    #[serde(default)]
    group_actions: Vec<Option<String>>,
    #[serde(default)]
    group_positions: Vec<Option<String>>,
    #[serde(default)]
    coordination_issues: Vec<String>,
    #[serde(default)]
    instruction_touches: Vec<Option<String>>,
    #[serde(default)]
    instruction_thinnesses: Vec<Option<String>>,
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
fn fixture_associates_uniform_clause_local_actions_and_positions() {
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
        if !case.head_group_members.is_empty() {
            assert_eq!(
                result
                    .ast
                    .coordinated_head_groups
                    .iter()
                    .map(|group| group.member_instruction_indices.clone())
                    .collect::<Vec<_>>(),
                case.head_group_members,
                "{}: source-ordered coordinated members",
                case.id
            );
            assert_eq!(
                result
                    .ast
                    .group_predicates
                    .iter()
                    .map(|edge| edge.action.as_ref().map(|term| term.identity.id.clone()))
                    .collect::<Vec<_>>(),
                case.group_actions,
                "{}: group Action owners",
                case.id
            );
            assert_eq!(
                result
                    .ast
                    .group_predicates
                    .iter()
                    .map(|edge| edge.position.as_ref().map(|term| term.identity.id.clone()))
                    .collect::<Vec<_>>(),
                case.group_positions,
                "{}: group Position owners",
                case.id
            );
        }
        assert_eq!(
            result
                .coordination_issues
                .iter()
                .map(|issue| issue.kind.as_str())
                .collect::<Vec<_>>(),
            case.coordination_issues,
            "{}: typed coordination issues",
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
        if !case.instruction_thinnesses.is_empty() {
            assert_eq!(
                result
                    .ast
                    .instructions
                    .iter()
                    .map(|instruction| {
                        instruction
                            .entity
                            .thinness
                            .as_ref()
                            .map(|thinness| thinness.value.as_str())
                    })
                    .collect::<Vec<_>>(),
                case.instruction_thinnesses
                    .iter()
                    .map(|value| value.as_deref())
                    .collect::<Vec<_>>(),
                "{}: nested entity core Thinness",
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
        "inku.semantic-instruction-association.v15"
    );
    assert_eq!(
        fixture.schema,
        "inku.semantic-instruction-association-fixture.v15"
    );
    assert_eq!(fixture.version, 15);
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
        "en-core-thinness",
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
        "ja-coordinated-action-position",
        "en-coordinated-action-position",
    ] {
        assert!(
            ids.contains(required),
            "missing required fixture case: {required}"
        );
    }
}

#[test]
fn multi_head_instruction_and_relation_owners_remain_ambiguous_exactly_once() {
    let document = NormalizedDdlDocument::new(
        "place center circle line",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_instructions(&document).unwrap();
    assert_eq!(result.ast.instructions.len(), 2);
    assert!(result.ast.instructions.iter().all(|instruction| {
        instruction.action.is_none()
            && instruction.position.is_none()
            && instruction.relation.is_none()
    }));
    assert_eq!(
        result
            .issues
            .iter()
            .map(|issue| issue.kind.as_str())
            .collect::<Vec<_>>(),
        ["ambiguous_action_ownership", "ambiguous_position_ownership"]
    );
    assert_eq!(
        result
            .issues
            .iter()
            .map(|issue| issue.occurrences.len())
            .sum::<usize>(),
        2
    );
    assert_eq!(result.owned_instruction_occurrence_count, 2);
    assert_eq!(result.delivered_instruction_occurrence_count, 2);

    let document = NormalizedDdlDocument::new(
        "center place circle line",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let reversed = associate_semantic_instructions(&document).unwrap();
    assert_eq!(
        reversed
            .issues
            .iter()
            .map(|issue| issue.kind.as_str())
            .collect::<Vec<_>>(),
        ["ambiguous_position_ownership"]
    );
    assert_eq!(
        reversed.ast.instructions[0]
            .action
            .as_ref()
            .map(|term| term.identity.id.as_str()),
        Some("place"),
        "typed Motion owns the first bounded following entity phrase"
    );

    let document = NormalizedDdlDocument::new(
        "place circle line at center",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let next_head_boundary = associate_semantic_instructions(&document).unwrap();
    assert_eq!(
        next_head_boundary
            .ast
            .instructions
            .iter()
            .map(|instruction| instruction
                .action
                .as_ref()
                .map(|term| term.identity.id.as_str()))
            .collect::<Vec<_>>(),
        [Some("place"), None]
    );
    assert!(
        next_head_boundary
            .ast
            .instructions
            .iter()
            .all(|instruction| instruction.position.is_none()),
        "Position after another head must not attach to the first instruction"
    );
    assert_eq!(
        next_head_boundary.issues[0].kind.as_str(),
        "ambiguous_position_ownership"
    );

    let relation = saijiki_asset()
        .relations
        .iter()
        .find(|relation| relation.relation_type == "touching")
        .and_then(|relation| relation.literals_en.first())
        .expect("accepted touching relation has one EN full literal");
    let source = format!("circle line {relation}");
    let document =
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new()).unwrap();
    let result = associate_semantic_instructions(&document).unwrap();
    assert_eq!(result.ast.instructions.len(), 2);
    assert!(
        result
            .ast
            .instructions
            .iter()
            .all(|instruction| instruction.relation.is_none())
    );
    assert_eq!(result.relation_issues.len(), 1);
    assert_eq!(
        result.relation_issues[0].kind.as_str(),
        "ambiguous_current_relation_ownership"
    );
    assert_eq!(result.relation_issues[0].occurrences.len(), 1);
    assert_eq!(result.owned_relation_occurrence_count, 1);
    assert_eq!(result.delivered_relation_occurrence_count, 1);
}

#[test]
fn pre_head_modifier_ownership_reaches_each_instruction_without_target_guessing() {
    let document = NormalizedDdlDocument::new(
        "place center red circle blue line",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_instructions(&document).unwrap();

    assert!(result.association.issues.is_empty());
    assert_eq!(result.ast.instructions.len(), 2);
    assert_eq!(
        result
            .ast
            .instructions
            .iter()
            .map(|instruction| {
                instruction
                    .entity
                    .color
                    .as_ref()
                    .unwrap()
                    .identity
                    .id
                    .as_str()
            })
            .collect::<Vec<_>>(),
        ["red", "blue"]
    );
    assert!(result.ast.instructions.iter().all(|instruction| {
        instruction.action.is_none()
            && instruction.position.is_none()
            && instruction.relation.is_none()
    }));
    assert_eq!(
        result
            .issues
            .iter()
            .map(|issue| issue.kind.as_str())
            .collect::<Vec<_>>(),
        ["ambiguous_action_ownership", "ambiguous_position_ownership"]
    );
}

#[test]
fn core_thinness_is_owned_unchanged_by_the_nested_instruction_entity() {
    let document = NormalizedDdlDocument::new(
        "place one thin pencil line at center.",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_instructions(&document).unwrap();

    assert!(result.issues.is_empty());
    assert!(result.association.issues.is_empty());
    assert_eq!(result.ast.instructions.len(), 1);
    let instruction = &result.ast.instructions[0];
    let thinness = instruction
        .entity
        .thinness
        .as_ref()
        .expect("nested entity owns explicit thinness");
    assert_eq!(thinness.value.as_str(), "fine");
    assert_eq!(thinness.provenance.surface, "thin");
    assert_eq!(instruction.entity.quantity.as_ref().unwrap().value, 1);
    assert_eq!(instruction.action.as_ref().unwrap().identity.id, "place");
    assert_eq!(instruction.position.as_ref().unwrap().identity.id, "center");
}

#[test]
fn core_relative_scale_is_owned_unchanged_by_the_nested_instruction_entity() {
    let document = NormalizedDdlDocument::new(
        "place one small circle at center.",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_instructions(&document).unwrap();
    assert!(result.issues.is_empty());
    assert!(result.association.issues.is_empty());
    let instruction = &result.ast.instructions[0];
    let relative_scale = instruction
        .entity
        .relative_scale
        .as_ref()
        .expect("nested entity owns explicit relative scale");
    assert_eq!(relative_scale.value.as_str(), "small");
    assert_eq!(relative_scale.provenance.surface, "small");
    assert!(instruction.entity.thinness.is_none());
}

#[test]
fn spec_ja_and_en_use_one_clause_local_instruction_meaning() {
    let cases = [
        (
            "中心に、鉛筆の細い線をひとつ置く。",
            ResolvedInstructionLanguage::Ja,
            ["線", "鉛筆", "細い", "ひとつ", "置く", "中心"],
        ),
        (
            "place one thin pencil line at the center",
            ResolvedInstructionLanguage::En,
            ["line", "pencil", "thin", "one", "place", "center"],
        ),
    ];
    let mut canonical = Vec::new();

    for (source, language, surfaces) in cases {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        let result = associate_semantic_instructions(&document).unwrap();

        assert!(result.association.issues.is_empty(), "{source}");
        assert!(result.issues.is_empty(), "{source}");
        assert_eq!(result.ast.instructions.len(), 1, "{source}");
        let instruction = &result.ast.instructions[0];
        let SemanticHead::Primitive(head) = &instruction.entity.head else {
            panic!("{source}: expected Primitive head");
        };
        assert_eq!(head.identity.id, "line", "{source}");
        assert_eq!(
            instruction.entity.head.source().surface,
            surfaces[0],
            "{source}"
        );
        assert_eq!(
            instruction.entity.touch.as_ref().unwrap().identity.id,
            "pencil",
            "{source}"
        );
        assert_eq!(
            instruction
                .entity
                .touch
                .as_ref()
                .unwrap()
                .provenance
                .source
                .surface,
            surfaces[1],
            "{source}"
        );
        assert_eq!(
            instruction.entity.thinness.as_ref().unwrap().value.as_str(),
            "fine",
            "{source}"
        );
        assert_eq!(
            instruction
                .entity
                .thinness
                .as_ref()
                .unwrap()
                .provenance
                .surface,
            surfaces[2],
            "{source}"
        );
        assert_eq!(
            instruction.entity.quantity.as_ref().unwrap().value,
            1,
            "{source}"
        );
        assert_eq!(
            instruction
                .entity
                .quantity
                .as_ref()
                .unwrap()
                .provenance
                .surface,
            surfaces[3],
            "{source}"
        );
        assert_eq!(
            instruction.action.as_ref().unwrap().identity.id,
            "place",
            "{source}"
        );
        assert_eq!(
            instruction
                .action
                .as_ref()
                .unwrap()
                .provenance
                .source
                .surface,
            surfaces[4],
            "{source}"
        );
        assert_eq!(
            instruction.position.as_ref().unwrap().identity.id,
            "center",
            "{source}"
        );
        assert_eq!(
            instruction
                .position
                .as_ref()
                .unwrap()
                .provenance
                .source
                .surface,
            surfaces[5],
            "{source}"
        );
        assert_eq!(
            result.owned_instruction_occurrence_count,
            result.delivered_instruction_occurrence_count,
            "{source}"
        );
        canonical.push(result.canonical_bytes.unwrap());
    }

    assert_eq!(canonical[0], canonical[1]);
}

#[test]
fn ja_and_en_multi_instruction_pairs_keep_source_order_and_shared_meaning() {
    let cases = [
        (
            "中央に円をひとつ置く。左端に線を二つ並べる。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "place one circle at center. line-up two line at left-edge.",
            ResolvedInstructionLanguage::En,
        ),
    ];
    let mut canonical = Vec::new();

    for (source, language) in cases {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        let result = associate_semantic_instructions(&document).unwrap();

        assert!(result.association.issues.is_empty(), "{source}");
        assert!(result.issues.is_empty(), "{source}");
        assert_eq!(result.ast.instructions.len(), 2, "{source}");
        assert_eq!(
            result
                .ast
                .instructions
                .iter()
                .map(|instruction| match &instruction.entity.head {
                    SemanticHead::Primitive(head) => head.identity.id.as_str(),
                    SemanticHead::MacroInvocation(_) => panic!("{source}: unexpected macro head"),
                })
                .collect::<Vec<_>>(),
            ["circle", "line"],
            "{source}"
        );
        assert_eq!(
            result
                .ast
                .instructions
                .iter()
                .map(|instruction| instruction.entity.quantity.as_ref().unwrap().value)
                .collect::<Vec<_>>(),
            [1, 2],
            "{source}"
        );
        assert_eq!(
            result
                .ast
                .instructions
                .iter()
                .map(|instruction| instruction.action.as_ref().unwrap().identity.id.as_str())
                .collect::<Vec<_>>(),
            ["place", "line_up"],
            "{source}"
        );
        assert_eq!(
            result
                .ast
                .instructions
                .iter()
                .map(|instruction| instruction.position.as_ref().unwrap().identity.id.as_str())
                .collect::<Vec<_>>(),
            ["center", "left_edge"],
            "{source}"
        );
        assert_eq!(
            result.owned_instruction_occurrence_count,
            result.delivered_instruction_occurrence_count,
            "{source}"
        );
        canonical.push(result.canonical_bytes.unwrap());
    }

    assert_eq!(canonical[0], canonical[1]);
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

#[test]
fn coordinated_heads_have_one_shared_predicate_owner() {
    let mut canonical = Vec::new();
    for (language, source) in [
        (ResolvedInstructionLanguage::Ja, "円と線を中心に置く。"),
        (
            ResolvedInstructionLanguage::En,
            "place a circle and a line at the center.",
        ),
    ] {
        let document = NormalizedDdlDocument::new(source, language, Vec::new())
            .unwrap_or_else(|error| panic!("{source}: invalid document: {error}"));
        let result = associate_semantic_instructions(&document)
            .unwrap_or_else(|error| panic!("{source}: association failed: {error}"));

        assert!(
            result.issues.is_empty(),
            "{source}: explicit coordination must own its predicate instead of remaining ambiguous: {:?}",
            result
                .issues
                .iter()
                .map(|issue| issue.kind.as_str())
                .collect::<Vec<_>>()
        );
        assert!(result.coordination_issues.is_empty(), "{source}");
        assert_eq!(result.ast.instructions.len(), 2, "{source}");
        assert!(
            result.ast.instructions.iter().all(|instruction| {
                instruction.action.is_none() && instruction.position.is_none()
            })
        );
        assert_eq!(result.ast.coordinated_head_groups.len(), 1, "{source}");
        let group = &result.ast.coordinated_head_groups[0];
        assert_eq!(group.member_instruction_indices, [0, 1], "{source}");
        assert_eq!(group.markers.len(), 1, "{source}");
        assert_eq!(
            group.markers[0].surface.to_ascii_lowercase(),
            if language == ResolvedInstructionLanguage::Ja {
                "と"
            } else {
                "and"
            },
            "{source}"
        );
        assert_eq!(result.ast.group_predicates.len(), 1, "{source}");
        let edge = &result.ast.group_predicates[0];
        assert_eq!(edge.group_index, 0, "{source}");
        assert_eq!(
            edge.action.as_ref().map(|term| term.identity.id.as_str()),
            Some("place"),
            "{source}"
        );
        assert_eq!(
            edge.position.as_ref().map(|term| term.identity.id.as_str()),
            Some("center"),
            "{source}"
        );
        assert_eq!(result.owned_instruction_occurrence_count, 2, "{source}");
        assert_eq!(result.delivered_instruction_occurrence_count, 2, "{source}");
        assert_eq!(result.owned_coordination_marker_count, 1, "{source}");
        assert_eq!(result.delivered_coordination_marker_count, 1, "{source}");
        canonical.push(result.canonical_bytes.expect("group result is complete"));
    }
    assert_eq!(canonical[0], canonical[1]);
}

#[test]
fn coordinated_group_preserves_member_order_modifiers_and_fail_closed_boundaries() {
    let associate = |source: &str| {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .unwrap();
        associate_semantic_instructions(&document).unwrap()
    };
    let ordered = associate("place a red circle and a thin line at the center.");
    assert!(ordered.ast.complete);
    assert_eq!(
        ordered.ast.coordinated_head_groups[0].member_instruction_indices,
        [0, 1]
    );
    assert_eq!(
        ordered.ast.instructions[0]
            .entity
            .color
            .as_ref()
            .map(|term| term.identity.id.as_str()),
        Some("red")
    );
    assert_eq!(
        ordered.ast.instructions[1]
            .entity
            .thinness
            .as_ref()
            .map(|thinness| thinness.value.as_str()),
        Some("fine")
    );

    let reversed = associate("place a thin line and a red circle at the center.");
    assert!(reversed.ast.complete);
    assert_ne!(ordered.canonical_bytes, reversed.canonical_bytes);

    let blocked = associate("place a circle and mystery line at the center.");
    assert!(blocked.ast.coordinated_head_groups.is_empty());
    assert!(blocked.ast.group_predicates.is_empty());
    let [issue] = blocked.coordination_issues.as_slice() else {
        panic!("blocked coordination boundary has one typed issue");
    };
    assert_eq!(issue.kind.as_str(), "ambiguous_coordination_boundary");
    assert_eq!(issue.member_instruction_indices, [0, 1]);
    assert_eq!(issue.markers.len(), 1);
    assert_eq!(issue.predicates.len(), 2);
    assert_eq!(blocked.owned_instruction_occurrence_count, 2);
    assert_eq!(blocked.delivered_instruction_occurrence_count, 2);
    assert!(!blocked.ast.complete);
    assert!(blocked.canonical_bytes.is_none());
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
                instruction.entity.head.source().region_index,
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
                instruction.entity.head.source().region_index,
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
        .chain(result.ast.group_predicates.iter().flat_map(|edge| {
            edge.action
                .iter()
                .map(|term| ("action", term.provenance.source.span))
                .chain(
                    edge.position
                        .iter()
                        .map(|term| ("position", term.provenance.source.span)),
                )
        }))
        .chain(result.issues.iter().flat_map(|issue| {
            issue.occurrences.iter().map(|occurrence| {
                (
                    occurrence.role.as_str(),
                    occurrence.term.provenance.source.span,
                )
            })
        }))
        .chain(result.coordination_issues.iter().flat_map(|issue| {
            issue.predicates.iter().map(|occurrence| {
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

#[test]
fn macro_head_retains_unbound_action_position_and_mixed_relation_order() {
    let definition = instruction_macro_definition("Nature", "Leaf", serde_json::json!({}));
    let motion = english_role_surface("ugoki");
    let place = english_role_surface("basho");
    let along = saijiki_asset()
        .relations
        .iter()
        .find(|relation| relation.relation_type == "along")
        .and_then(|relation| relation.literals_en.first())
        .expect("accepted along literal");
    let source = format!("circle! {motion} Nature.Leaf at {place} {along}! square {along}!");
    let document = instruction_macro_document(&source, std::slice::from_ref(&definition));
    let binding = bind_macro_parameters(&document, std::slice::from_ref(&definition)).unwrap();
    let result = associate_semantic_instructions_with_macro_binding(&document, binding);

    assert!(result.issues.is_empty());
    assert!(result.relation_issues.is_empty());
    assert_eq!(result.ast.instructions.len(), 3);
    assert!(matches!(
        result.ast.instructions[1].entity.head,
        SemanticHead::MacroInvocation(_)
    ));
    assert_eq!(
        result.ast.instructions[1]
            .action
            .as_ref()
            .map(|term| term.identity.category.as_str()),
        Some("movement")
    );
    assert_eq!(
        result.ast.instructions[1]
            .position
            .as_ref()
            .map(|term| term.identity.category.as_str()),
        Some("place")
    );
    let relation = result.ast.instructions[1]
        .relation
        .as_ref()
        .expect("MacroInvocation current instruction retains its unbound relation");
    assert_eq!(relation.kind.as_str(), "along");
    assert_eq!(relation.reference.as_str(), "previous_one");
    assert_eq!(
        result.ast.instructions[2]
            .relation
            .as_ref()
            .map(|relation| relation.reference.as_str()),
        Some("previous_one"),
        "Primitive current instruction counts the previous MacroInvocation"
    );
    assert_eq!(result.owned_instruction_occurrence_count, 2);
    assert_eq!(result.delivered_instruction_occurrence_count, 2);

    let canonical: serde_json::Value = serde_json::from_slice(
        result
            .canonical_bytes
            .as_deref()
            .expect("complete canonical"),
    )
    .unwrap();
    assert_eq!(
        canonical["schema"],
        "inku.semantic-instruction-association.v15"
    );
    assert_eq!(
        canonical["instructions"][1]["entity"]["head"]["kind"],
        "macro_invocation"
    );
    assert_eq!(
        canonical["instructions"][1]["relation"]["reference"],
        "previous_one"
    );

    let between = saijiki_asset()
        .relations
        .iter()
        .find(|relation| relation.relation_type == "between")
        .and_then(|relation| relation.literals_en.first())
        .expect("accepted between literal");
    let previous_two_source = format!("circle! Nature.Leaf! square {between}!");
    let previous_two_document =
        instruction_macro_document(&previous_two_source, std::slice::from_ref(&definition));
    let previous_two_binding =
        bind_macro_parameters(&previous_two_document, std::slice::from_ref(&definition)).unwrap();
    let previous_two = associate_semantic_instructions_with_macro_binding(
        &previous_two_document,
        previous_two_binding,
    );
    assert!(previous_two.relation_issues.is_empty());
    assert_eq!(previous_two.ast.instructions.len(), 3);
    assert!(matches!(
        previous_two.ast.instructions[1].entity.head,
        SemanticHead::MacroInvocation(_)
    ));
    assert_eq!(
        previous_two.ast.instructions[2]
            .relation
            .as_ref()
            .map(|relation| relation.reference.as_str()),
        Some("previous_two")
    );
}

#[test]
fn bound_action_and_position_are_not_redelivered_to_outer_instruction_fields() {
    let definition = instruction_macro_definition(
        "Nature",
        "Bound",
        serde_json::json!({
            "action": {"type": "semantic_ref", "category": "movement"},
            "position": {"type": "semantic_ref", "category": "place"}
        }),
    );
    let source = format!(
        "Nature.Bound {} {}",
        english_role_surface("ugoki"),
        english_role_surface("basho")
    );
    let document = instruction_macro_document(&source, std::slice::from_ref(&definition));
    let binding = bind_macro_parameters(&document, std::slice::from_ref(&definition)).unwrap();
    let result = associate_semantic_instructions_with_macro_binding(&document, binding);

    assert!(result.issues.is_empty());
    assert_eq!(result.ast.instructions.len(), 1);
    assert!(result.ast.instructions[0].action.is_none());
    assert!(result.ast.instructions[0].position.is_none());
    assert_eq!(result.owned_instruction_occurrence_count, 0);
    assert_eq!(result.delivered_instruction_occurrence_count, 0);
    let SemanticHead::MacroInvocation(head) = &result.ast.instructions[0].entity.head else {
        panic!("expected MacroInvocation head");
    };
    assert_eq!(head.parameters.len(), 2);
}

fn instruction_macro_definition(
    namespace: &str,
    heading: &str,
    parameters: serde_json::Value,
) -> MacroDefinition {
    MacroDefinition::from_json(
        &serde_json::json!({
            "schema": "inku.macro-definition.v1",
            "namespace": namespace,
            "heading": heading,
            "version": "1.0.0",
            "parameters": parameters,
            "components": {},
            "body": []
        })
        .to_string(),
    )
    .expect("synthetic instruction macro definition parses")
}

fn instruction_macro_document(
    source: &str,
    definitions: &[MacroDefinition],
) -> NormalizedDdlDocument {
    let locks = definitions
        .iter()
        .map(|definition| {
            let identity = definition
                .identity()
                .expect("synthetic definition is valid");
            MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .expect("synthetic lock is valid")
        })
        .collect();
    NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, locks)
        .expect("synthetic instruction macro document is valid")
}

fn english_role_surface(category_key: &str) -> &str {
    saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == category_key)
        .and_then(|category| category.words.first())
        .and_then(|word| word.surface_en.as_deref())
        .expect("accepted role has an English surface")
}
