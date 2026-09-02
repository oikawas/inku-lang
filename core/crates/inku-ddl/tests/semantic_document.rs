use std::collections::{HashMap, HashSet};

use inku_ddl::{
    ClauseAtom, ClauseStream, CoreRoleKind, MacroDefinition, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, SEMANTIC_DOCUMENT_SCHEMA_ID,
    SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID, SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID,
    SemanticContinuationIssueKind, SemanticDocumentResult, SemanticHead,
    SemanticInstructionAssociationResult, SemanticIssueCausalProvenance,
    SemanticUpstreamCausalRelation, SourceOccurrence, associate_semantic_document,
    associate_semantic_document_with_macro_binding, bind_macro_parameters,
    project_macro_semantic_ref, saijiki_asset,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/semantic-document-v11.json");

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
    ground: Option<String>,
    instruction_count: usize,
    document_issue_kinds: Vec<String>,
    association_issue_kinds: Vec<String>,
    instruction_issue_kinds: Vec<String>,
    canonical: Option<String>,
    instruction_canonical: Option<String>,
    ground_occurrence_count: usize,
    #[serde(default)]
    instruction_proportion_aspects: Vec<Option<String>>,
    #[serde(default)]
    instruction_proportion_width_extents: Vec<Option<String>>,
    #[serde(default)]
    instruction_proportion_arc_forms: Vec<Option<String>>,
    #[serde(default)]
    instruction_thinnesses: Vec<Option<String>>,
}

#[test]
fn fixture_associates_document_global_ground_without_reparsing_instruction_ownership() {
    let fixture = load_fixture();
    let mut canonical_by_case = HashMap::new();

    for case in &fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source.clone(),
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap_or_else(|error| panic!("{}: unexpected document diagnostic: {error}", case.id));
        let result = associate_semantic_document(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected clause-stream error: {error}", case.id));

        assert_eq!(result.schema_id, SEMANTIC_DOCUMENT_SCHEMA_ID, "{}", case.id);
        assert_eq!(
            result.instruction_association.schema_id, SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID,
            "{}: accepted instruction schema remains unchanged",
            case.id
        );
        assert_eq!(
            result.instruction_association.association.schema_id,
            SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
            "{}: accepted entity schema remains unchanged",
            case.id
        );
        assert_eq!(
            result
                .ast
                .ground
                .as_ref()
                .map(|term| term.identity.id.as_str()),
            case.ground.as_deref(),
            "{}",
            case.id
        );
        assert_eq!(
            result.ast.instructions.len(),
            case.instruction_count,
            "{}",
            case.id
        );
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
                "{}: document nested core Thinness",
                case.id
            );
        }
        assert_eq!(
            result.ast.instructions, result.instruction_association.ast.instructions,
            "{}: accepted instruction AST is retained unchanged",
            case.id
        );
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
                "{}: document retains Proportion aspect",
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
                "{}: document retains Proportion width extent",
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
                "{}: document retains Proportion arc form",
                case.id
            );
        }
        assert_eq!(
            result
                .issues
                .iter()
                .map(|issue| issue.kind.as_str())
                .collect::<Vec<_>>(),
            case.document_issue_kinds
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}",
            case.id
        );
        assert_eq!(
            result
                .instruction_association
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
            instruction_issue_kinds(&result.instruction_association),
            case.instruction_issue_kinds,
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
            result.instruction_association.canonical_bytes.as_deref(),
            case.instruction_canonical.as_ref().map(String::as_bytes),
            "{}: accepted instruction canonical bytes remain unchanged",
            case.id
        );
        assert_eq!(
            result.ast.complete,
            result.instruction_association.ast.complete && result.issues.is_empty(),
            "{}: only instruction-complete, document-issue-free AST is complete",
            case.id
        );
        assert_eq!(
            result.owned_ground_occurrence_count, case.ground_occurrence_count,
            "{}",
            case.id
        );
        assert_eq!(
            result.delivered_ground_occurrence_count, result.owned_ground_occurrence_count,
            "{}: every Ground occurrence is delivered exactly once",
            case.id
        );
        assert_ground_provenance(case, &result);
        assert_ground_occurrence_join(case, &result);

        if let Some(canonical) = &case.canonical {
            canonical_by_case.insert(case.id.as_str(), canonical.as_str());
        }
    }

    let equivalent = [
        "ja-paper-leading",
        "en-paper-trailing",
        "paper-soft-line-break",
    ]
    .map(|id| canonical_by_case[id]);
    assert!(equivalent.windows(2).all(|pair| pair[0] == pair[1]));
    assert_ne!(
        canonical_by_case["ground-only-washi"],
        canonical_by_case["ground-only-canvas"]
    );
}

#[test]
fn marked_subject_predicate_continues_the_unique_prior_entity() {
    let mut canonical = Vec::new();
    for (language, source) in [
        (
            ResolvedInstructionLanguage::Ja,
            "中心に鉛筆の細い線をひとつ置く。線は細かく揺れる。",
        ),
        (
            ResolvedInstructionLanguage::En,
            "place one thin pencil line at the center. the line swaying fine.",
        ),
    ] {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        let result = associate_semantic_document(&document).unwrap();

        assert_eq!(
            result.ast.instructions.len(),
            1,
            "marked subject predicate must continue one prior entity: {source}"
        );
        assert_eq!(result.ast.continuations.len(), 1, "{source}");
        assert!(result.continuation_issues.is_empty(), "{source}");
        assert_eq!(result.owned_continuation_occurrence_count, 2, "{source}");
        assert_eq!(
            result.delivered_continuation_occurrence_count,
            result.owned_continuation_occurrence_count,
            "{source}"
        );
        assert_eq!(
            result.ast.instructions[0]
                .entity
                .fluctuation
                .amplitude
                .as_ref()
                .map(|term| term.identity.id.as_str()),
            Some("fine"),
            "{source}"
        );
        assert_eq!(
            result.ast.instructions[0]
                .entity
                .fluctuation
                .quality
                .as_ref()
                .map(|term| term.identity.id.as_str()),
            Some("swaying"),
            "{source}"
        );
        assert!(result.ast.complete, "{source}");
        canonical.push(result.canonical_bytes.unwrap());
    }
    assert_eq!(canonical[0], canonical[1]);
}

#[test]
fn continuation_target_cardinality_and_boundary_fail_closed_without_order_fallback() {
    for (source, expected) in [
        (
            "circle. the line swaying fine.",
            SemanticContinuationIssueKind::MissingTarget,
        ),
        (
            "line. line. the line swaying fine.",
            SemanticContinuationIssueKind::AmbiguousTarget,
        ),
        (
            "line. mystery. the line swaying fine.",
            SemanticContinuationIssueKind::BlockedBoundary,
        ),
        (
            "line. mystery. orchard. the line swaying fine.",
            SemanticContinuationIssueKind::BlockedBoundary,
        ),
        (
            "fine line. the line large swaying.",
            SemanticContinuationIssueKind::ConflictingPredicate,
        ),
    ] {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .unwrap();
        let result = associate_semantic_document(&document).unwrap();

        assert_eq!(result.continuation_issues.len(), 1, "{source}");
        assert_eq!(result.continuation_issues[0].kind, expected, "{source}");
        match expected {
            SemanticContinuationIssueKind::BlockedBoundary => {
                let SemanticIssueCausalProvenance::UpstreamDiagnostics(causes) =
                    &result.continuation_issues[0].causal_provenance
                else {
                    panic!("blocked continuation retains its diagnostic boundary: {source}");
                };
                let expected_count = if source.contains("orchard") { 2 } else { 1 };
                assert_eq!(causes.len(), expected_count, "{source}");
                assert!(causes.iter().all(|cause| {
                    cause.relation == SemanticUpstreamCausalRelation::ContinuationBoundary
                }));
                assert!(
                    causes
                        .windows(2)
                        .all(|pair| pair[0].span.start_byte < pair[1].span.start_byte),
                    "{source}"
                );
            }
            _ => assert_eq!(
                result.continuation_issues[0].causal_provenance,
                SemanticIssueCausalProvenance::Unattributed,
                "independent continuation issue stays explicitly unattributed: {source}"
            ),
        }
        assert!(!result.ast.complete, "{source}");
        assert!(result.canonical_bytes.is_none(), "{source}");
        assert_eq!(result.owned_continuation_occurrence_count, 2, "{source}");
        assert_eq!(
            result.delivered_continuation_occurrence_count,
            result.owned_continuation_occurrence_count,
            "{source}"
        );
    }
}

#[test]
fn leading_marked_predicate_is_missing_target_but_head_only_remains_independent() {
    for (language, source) in [
        (ResolvedInstructionLanguage::Ja, "線は細かく揺れる。"),
        (ResolvedInstructionLanguage::En, "the line swaying fine."),
    ] {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        let result = associate_semantic_document(&document).unwrap();

        assert!(result.ast.instructions.is_empty(), "{source}");
        assert!(result.ast.continuations.is_empty(), "{source}");
        assert_eq!(result.continuation_issues.len(), 1, "{source}");
        assert_eq!(
            result.continuation_issues[0].kind,
            SemanticContinuationIssueKind::MissingTarget,
            "{source}"
        );
        assert!(!result.ast.complete, "{source}");
        assert!(result.canonical_bytes.is_none(), "{source}");
        assert_eq!(result.owned_continuation_occurrence_count, 2, "{source}");
        assert_eq!(
            result.delivered_continuation_occurrence_count,
            result.owned_continuation_occurrence_count,
            "{source}"
        );
    }

    for (language, source) in [
        (ResolvedInstructionLanguage::Ja, "線は。"),
        (ResolvedInstructionLanguage::En, "the line."),
    ] {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        let result = associate_semantic_document(&document).unwrap();

        assert_eq!(result.ast.instructions.len(), 1, "{source}");
        assert!(result.ast.continuations.is_empty(), "{source}");
        assert!(result.continuation_issues.is_empty(), "{source}");
        assert_eq!(result.owned_continuation_occurrence_count, 0, "{source}");
    }
}

#[test]
fn continuation_preserves_original_fields_and_accepts_reordered_predicate_atoms() {
    let sources = [
        "place one thin pencil line at center. the line swaying fine.",
        "place one thin pencil line at center. the line fine swaying.",
    ];
    let results = sources.map(|source| {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .unwrap();
        associate_semantic_document(&document).unwrap()
    });
    for result in &results {
        assert!(result.ast.complete);
        assert_eq!(result.ast.instructions.len(), 1);
        let instruction = &result.ast.instructions[0];
        assert_eq!(
            instruction
                .entity
                .quantity
                .as_ref()
                .map(|value| value.value),
            Some(1)
        );
        assert_eq!(
            instruction
                .entity
                .thinness
                .as_ref()
                .map(|value| value.value.as_str()),
            Some("fine")
        );
        assert_eq!(
            instruction
                .entity
                .touch
                .as_ref()
                .map(|term| term.identity.id.as_str()),
            Some("pencil")
        );
        assert_eq!(
            instruction
                .action
                .as_ref()
                .map(|term| term.identity.id.as_str()),
            Some("place")
        );
        assert_eq!(
            instruction
                .position
                .as_ref()
                .map(|term| term.identity.id.as_str()),
            Some("center")
        );
    }
    assert_eq!(results[0].canonical_bytes, results[1].canonical_bytes);
}

#[test]
fn continuation_delivers_each_bounded_predicate_dimension_and_action_once() {
    let document = NormalizedDdlDocument::new(
        "line. the flat dense tall thin small line place.",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_document(&document).unwrap();

    assert!(
        result.ast.complete,
        "association={:?} instruction={:?} continuation={:?}",
        result
            .instruction_association
            .association
            .issues
            .iter()
            .map(|issue| issue.kind.as_str())
            .collect::<Vec<_>>(),
        result
            .instruction_association
            .issues
            .iter()
            .map(|issue| issue.kind.as_str())
            .collect::<Vec<_>>(),
        result
            .continuation_issues
            .iter()
            .map(|issue| issue.kind.as_str())
            .collect::<Vec<_>>()
    );
    assert_eq!(result.ast.instructions.len(), 1);
    assert_eq!(result.ast.continuations.len(), 1);
    let instruction = &result.ast.instructions[0];
    assert_eq!(
        instruction
            .entity
            .surface
            .quality
            .as_ref()
            .map(|term| term.identity.id.as_str()),
        Some("solid")
    );
    assert_eq!(
        instruction
            .entity
            .surface
            .intensity
            .as_ref()
            .map(|term| term.identity.id.as_str()),
        Some("dense")
    );
    assert_eq!(
        instruction
            .entity
            .proportion
            .aspect
            .as_ref()
            .map(|term| term.identity.id.as_str()),
        Some("tall")
    );
    assert_eq!(
        instruction
            .entity
            .thinness
            .as_ref()
            .map(|value| value.value.as_str()),
        Some("fine")
    );
    assert_eq!(
        instruction
            .entity
            .relative_scale
            .as_ref()
            .map(|value| value.value.as_str()),
        Some("small")
    );
    assert_eq!(
        instruction
            .action
            .as_ref()
            .map(|term| term.identity.id.as_str()),
        Some("place")
    );
    assert_eq!(result.owned_continuation_occurrence_count, 2);
    assert_eq!(
        result.delivered_continuation_occurrence_count,
        result.owned_continuation_occurrence_count
    );
}

#[test]
fn schema_fixture_and_required_document_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(SEMANTIC_DOCUMENT_SCHEMA_ID, "inku.semantic-document.v11");
    assert_eq!(
        SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
        "inku.semantic-entity-association.v13"
    );
    assert_eq!(
        SEMANTIC_INSTRUCTION_ASSOCIATION_SCHEMA_ID,
        "inku.semantic-instruction-association.v14"
    );
    assert_eq!(fixture.schema, "inku.semantic-document-fixture.v11");
    assert_eq!(fixture.version, 11);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "no-ground-unspecified",
        "en-core-thinness",
        "ja-paper-leading",
        "en-paper-trailing",
        "paper-soft-line-break",
        "ground-with-multiple-instructions",
        "ground-only-washi",
        "ground-only-canvas",
        "conflicting-grounds",
        "surface-and-ground-coexist",
        "ground-preserves-i590-instruction",
        "ground-with-upstream-issue",
        "ground-with-instruction-issue",
    ] {
        assert!(
            ids.contains(required),
            "missing required fixture case: {required}"
        );
    }
}

#[test]
fn head_only_multi_head_document_preserves_order_and_is_canonical_ready() {
    let mut canonical = Vec::new();
    for source in ["paper circle line", "paper line circle"] {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .unwrap();
        let result = associate_semantic_document(&document).unwrap();
        assert!(result.issues.is_empty());
        assert!(result.instruction_association.issues.is_empty());
        assert!(result.instruction_association.relation_issues.is_empty());
        assert!(result.ast.complete);
        assert_eq!(
            result
                .ast
                .ground
                .as_ref()
                .map(|term| term.identity.id.as_str()),
            Some("paper")
        );
        assert_eq!(result.ast.instructions.len(), 2);
        assert_eq!(
            result
                .ast
                .instructions
                .iter()
                .map(|instruction| match &instruction.entity.head {
                    SemanticHead::Primitive(term) => term.identity.id.as_str(),
                    SemanticHead::MacroInvocation(_) => "macro",
                })
                .collect::<Vec<_>>(),
            source.split_whitespace().skip(1).collect::<Vec<_>>()
        );
        canonical.push(result.canonical_bytes.unwrap());
    }
    assert_ne!(canonical[0], canonical[1]);
}

#[test]
fn document_preserves_ground_and_source_ordered_pre_head_modifier_ownership() {
    let document = NormalizedDdlDocument::new(
        "paper red circle blue line",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_document(&document).unwrap();

    assert!(result.issues.is_empty());
    assert!(result.instruction_association.issues.is_empty());
    assert!(result.instruction_association.relation_issues.is_empty());
    assert!(result.ast.complete);
    assert_eq!(result.ast.ground.as_ref().unwrap().identity.id, "paper");
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
    assert!(result.canonical_bytes.is_some());
}

#[test]
fn every_accepted_ground_row_projects_to_one_document_global_identity() {
    let category = saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == "ji")
        .expect("accepted asset has the Ground category");
    assert_eq!(category.words.len(), 7);

    let mut ids = HashSet::new();
    for word in &category.words {
        let projection = project_macro_semantic_ref(&category.key, &word.surface_ja)
            .expect("accepted Ground row has canonical identity");
        let source = format!(
            "{}.",
            word.surface_en
                .as_deref()
                .expect("accepted Ground row has English source surface")
        );
        let document = NormalizedDdlDocument::new(
            source,
            inku_ddl::ResolvedInstructionLanguage::En,
            Vec::new(),
        )
        .expect("accepted Ground row forms a normalized document");
        let result = associate_semantic_document(&document)
            .expect("accepted Ground row forms a semantic document");
        assert!(result.issues.is_empty(), "{}", projection.canonical_id);
        assert!(
            result.ast.instructions.is_empty(),
            "{}",
            projection.canonical_id
        );
        let ground = result.ast.ground.as_ref().expect("one explicit Ground");
        assert_eq!(ground.identity.category, "ground");
        assert_eq!(ground.identity.id, projection.canonical_id);
        assert!(ids.insert(ground.identity.id.clone()));
        assert_eq!(result.owned_ground_occurrence_count, 1);
        assert_eq!(result.delivered_ground_occurrence_count, 1);
    }

    assert_eq!(
        ids,
        [
            "paper",
            "washi",
            "ink_wash",
            "charcoal_ground",
            "canvas",
            "drawing_paper",
            "mezzotint",
        ]
        .map(str::to_owned)
        .into_iter()
        .collect()
    );
}

#[test]
fn document_retains_ground_and_owned_relation_edge_without_reparse() {
    let asset = saijiki_asset();
    let shapes = asset
        .categories
        .iter()
        .find(|category| category.key == "katachi")
        .expect("accepted asset has Primitive rows");
    let english_shape = |name: &str| {
        shapes
            .words
            .iter()
            .find(|word| word.surface_en.as_deref() == Some(name))
            .and_then(|word| word.surface_en.as_deref())
            .expect("accepted English Primitive surface")
    };
    let ground = asset
        .categories
        .iter()
        .find(|category| category.key == "ji")
        .and_then(|category| category.words.first())
        .and_then(|word| word.surface_en.as_deref())
        .expect("accepted Ground English surface");
    let relation = asset
        .relations
        .iter()
        .find(|relation| relation.relation_type == "along")
        .expect("accepted along relation");
    let literal = relation
        .literals_en
        .first()
        .expect("accepted along EN literal");
    let source = format!(
        "{ground}. {}. {} {literal}.",
        english_shape("line"),
        english_shape("circle")
    );
    let document = NormalizedDdlDocument::new(
        source,
        inku_ddl::ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .expect("Ground and relation source forms a document");
    let result = associate_semantic_document(&document)
        .expect("Ground and relation source forms a semantic document");

    assert!(result.issues.is_empty());
    assert!(result.instruction_association.relation_issues.is_empty());
    assert_eq!(
        result.ast.instructions,
        result.instruction_association.ast.instructions
    );
    assert!(result.ast.ground.is_some());
    assert_eq!(result.ast.instructions.len(), 2);
    let relation = result.ast.instructions[1]
        .relation
        .as_ref()
        .expect("current instruction retains relation");
    assert_eq!(relation.kind.as_str(), "along");
    assert_eq!(relation.reference.as_str(), "previous_one");
    assert_eq!(relation.provenance.surface, *literal);

    let canonical: serde_json::Value = serde_json::from_slice(
        result
            .canonical_bytes
            .as_deref()
            .expect("issue-free document canonical"),
    )
    .expect("document canonical JSON");
    assert_eq!(canonical["schema"], "inku.semantic-document.v11");
    assert_eq!(canonical["instructions"][1]["relation"]["kind"], "along");
    assert_eq!(
        canonical["instructions"][1]["relation"]["reference"],
        "previous_one"
    );
    assert_eq!(
        canonical["instructions"][1]["relation"]
            .as_object()
            .map(|object| object.len()),
        Some(2)
    );
}

fn load_fixture() -> Fixture {
    serde_json::from_str(FIXTURE).expect("fixture must be valid JSON")
}

fn parse_language(value: &str, case_id: &str) -> inku_ddl::ResolvedInstructionLanguage {
    match value {
        "ja" => inku_ddl::ResolvedInstructionLanguage::Ja,
        "en" => inku_ddl::ResolvedInstructionLanguage::En,
        _ => panic!("{case_id}: invalid fixture language"),
    }
}

fn instruction_issue_kinds(result: &SemanticInstructionAssociationResult) -> Vec<String> {
    result
        .issues
        .iter()
        .map(|issue| {
            let role = issue
                .occurrences
                .first()
                .expect("instruction issue owns occurrences")
                .role
                .as_str();
            format!("{role}:{}", issue.kind.as_str())
        })
        .collect()
}

fn assert_ground_provenance(case: &Case, result: &SemanticDocumentResult) {
    if let Some(ground) = &result.ast.ground {
        assert_source_occurrence(
            case,
            &ground.provenance.source,
            &result.instruction_association.association.clause_stream,
        );
    }
    for issue in &result.issues {
        for occurrence in &issue.occurrences {
            assert_source_occurrence(
                case,
                &occurrence.provenance.source,
                &result.instruction_association.association.clause_stream,
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
    let atom = stream
        .clauses
        .get(occurrence.clause_index)
        .and_then(|clause| clause.atoms.get(occurrence.atom_index))
        .unwrap_or_else(|| panic!("{}: invalid clause / atom provenance", case.id));
    assert_eq!(atom.span(), occurrence.span, "{}: atom provenance", case.id);
}

fn assert_ground_occurrence_join(case: &Case, result: &SemanticDocumentResult) {
    let input = result
        .instruction_association
        .association
        .clause_stream
        .clauses
        .iter()
        .flat_map(|clause| &clause.atoms)
        .filter_map(|atom| match atom {
            ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Ground => Some(term.span),
            _ => None,
        })
        .collect::<Vec<_>>();
    let mut output = result
        .ast
        .ground
        .iter()
        .map(|ground| ground.provenance.source.span)
        .chain(result.issues.iter().flat_map(|issue| {
            issue
                .occurrences
                .iter()
                .map(|term| term.provenance.source.span)
        }))
        .collect::<Vec<_>>();
    output.sort_by_key(|span| span.start_byte);
    assert_eq!(output, input, "{}: Ground occurrence join", case.id);
}

#[test]
fn core_thinness_reaches_the_document_root_without_reparse_or_default() {
    let document = NormalizedDdlDocument::new(
        "thin circle paper",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_document(&document).unwrap();

    assert!(result.issues.is_empty());
    assert_eq!(result.ast.instructions.len(), 1);
    assert_eq!(result.ast.ground.as_ref().unwrap().identity.id, "paper");
    let thinness = result.ast.instructions[0]
        .entity
        .thinness
        .as_ref()
        .expect("document retains nested explicit thinness");
    assert_eq!(thinness.value.as_str(), "fine");
    assert_eq!(thinness.provenance.surface, "thin");
    let canonical = std::str::from_utf8(result.canonical_bytes.as_deref().unwrap()).unwrap();
    assert!(canonical.contains("\"thinness\":\"fine\""));
}

#[test]
fn core_relative_scale_reaches_the_document_root_without_reparse_or_default() {
    let document = NormalizedDdlDocument::new(
        "small circle paper",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_document(&document).unwrap();
    assert!(result.issues.is_empty());
    let relative_scale = result.ast.instructions[0]
        .entity
        .relative_scale
        .as_ref()
        .expect("document retains nested explicit relative scale");
    assert_eq!(relative_scale.value.as_str(), "small");
    assert_eq!(relative_scale.provenance.surface, "small");
    assert!(result.ast.instructions[0].entity.thinness.is_none());
    let canonical = std::str::from_utf8(result.canonical_bytes.as_deref().unwrap()).unwrap();
    assert!(canonical.contains("\"relative_scale\":\"small\""));
}

#[test]
fn macro_parameter_ground_is_not_redelivered_but_unbound_ground_reaches_document_owner() {
    let ground_surface = saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == "ji")
        .and_then(|category| category.words.first())
        .and_then(|word| word.surface_en.as_deref())
        .expect("accepted Ground has English surface");
    let bound_definition = document_macro_definition(
        "Bound",
        serde_json::json!({
            "ground": {"type": "semantic_ref", "category": "ground"}
        }),
    );
    let bound_source = format!("Nature.Bound {ground_surface}");
    let bound_document =
        document_macro_document(&bound_source, std::slice::from_ref(&bound_definition));
    let bound_binding =
        bind_macro_parameters(&bound_document, std::slice::from_ref(&bound_definition)).unwrap();
    let bound = associate_semantic_document_with_macro_binding(&bound_document, bound_binding);

    assert!(bound.issues.is_empty());
    assert!(bound.ast.ground.is_none());
    assert_eq!(bound.owned_ground_occurrence_count, 0);
    assert_eq!(bound.delivered_ground_occurrence_count, 0);
    assert_eq!(bound.ast.instructions.len(), 1);
    let SemanticHead::MacroInvocation(head) = &bound.ast.instructions[0].entity.head else {
        panic!("expected MacroInvocation head");
    };
    assert_eq!(head.parameters.len(), 1);
    assert_eq!(head.parameters[0].name, "ground");
    assert!(
        bound
            .instruction_association
            .association
            .macro_parameter_binding
            .is_some()
    );
    let bound_canonical: serde_json::Value = serde_json::from_slice(
        bound
            .canonical_bytes
            .as_deref()
            .expect("complete canonical"),
    )
    .unwrap();
    assert_eq!(bound_canonical["schema"], "inku.semantic-document.v11");
    assert!(bound_canonical["ground"].is_null());

    let outer_definition = document_macro_definition("Outer", serde_json::json!({}));
    let outer_source = format!("Nature.Outer {ground_surface}");
    let outer_document =
        document_macro_document(&outer_source, std::slice::from_ref(&outer_definition));
    let outer_binding =
        bind_macro_parameters(&outer_document, std::slice::from_ref(&outer_definition)).unwrap();
    let outer = associate_semantic_document_with_macro_binding(&outer_document, outer_binding);
    assert_eq!(
        outer
            .ast
            .ground
            .as_ref()
            .map(|term| term.identity.category.as_str()),
        Some("ground")
    );
    assert_eq!(outer.owned_ground_occurrence_count, 1);
    assert_eq!(outer.delivered_ground_occurrence_count, 1);
}

fn document_macro_definition(heading: &str, parameters: serde_json::Value) -> MacroDefinition {
    MacroDefinition::from_json(
        &serde_json::json!({
            "schema": "inku.macro-definition.v1",
            "namespace": "Nature",
            "heading": heading,
            "version": "1.0.0",
            "parameters": parameters,
            "components": {},
            "body": []
        })
        .to_string(),
    )
    .expect("synthetic document macro definition parses")
}

fn document_macro_document(source: &str, definitions: &[MacroDefinition]) -> NormalizedDdlDocument {
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
    NormalizedDdlDocument::new(source, inku_ddl::ResolvedInstructionLanguage::En, locks)
        .expect("synthetic document macro input is valid")
}
