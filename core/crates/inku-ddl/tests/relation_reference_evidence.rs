use std::collections::{HashMap, HashSet};

use inku_ddl::{
    AttachmentMarkerKind, ClauseAtom, EnglishAttachmentMarkerKind, JapaneseAttachmentMarkerKind,
    NeutralDiagnosticKind, NormalizedDdlDocument, RELATION_REFERENCE_EVIDENCE_SCHEMA_ID,
    RelationReferenceCandidateEnvelope, RelationReferenceEvidenceAvailability,
    RelationReferenceEvidenceDiagnosticKind, RelationReferenceEvidenceResult,
    RelationReferenceOccurrenceKind, ResolvedInstructionLanguage, SourceSpan,
    collect_attachment_evidence, collect_relation_reference_evidence,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/relation-reference-evidence-v1.json");

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
    expected_nodes: Vec<ExpectedNode>,
    expected_missing_context: Vec<ExpectedMissingContext>,
    delivery_conservation_count: usize,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedNode {
    kind: String,
    clause_index: usize,
    occurrence_atom_index: usize,
    left_context_atom_indices: Vec<usize>,
    right_context_atom_indices: Vec<usize>,
    candidate_atom_indices: Vec<usize>,
    availability: String,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedMissingContext {
    kind: String,
    missing_left: bool,
    missing_right: bool,
}

#[test]
fn fixture_builds_source_ordered_candidate_envelopes_and_owns_i569_unchanged() {
    for case in load_fixture().cases {
        let document = document_for(&case);
        let source_before = document.source().as_bytes().to_vec();
        let accepted = collect_attachment_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected I-569 error: {error}", case.id));
        let result = collect_relation_reference_evidence(&document).unwrap_or_else(|error| {
            panic!("{}: unexpected relation/reference error: {error}", case.id)
        });

        assert_eq!(document.source().as_bytes(), source_before, "{}", case.id);
        assert_eq!(
            result.attachment_evidence, accepted,
            "{}: accepted I-569 result must be owned unchanged",
            case.id
        );
        assert_eq!(
            result
                .attachment_evidence
                .noun_phrase
                .clause_stream
                .delivery_conservation_count,
            case.delivery_conservation_count,
            "{}",
            case.id
        );
        assert_eq!(project_nodes(&result), case.expected_nodes, "{}", case.id);
        assert_eq!(
            project_missing_context(&result),
            case.expected_missing_context,
            "{}",
            case.id
        );
        assert_lossless_envelope(&case, &result);
    }
}

#[test]
fn fixture_schema_and_required_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(
        RELATION_REFERENCE_EVIDENCE_SCHEMA_ID,
        "inku.relation-reference-evidence.v1"
    );
    assert_eq!(
        fixture.schema,
        "inku.relation-reference-evidence-fixture.v1"
    );
    assert_eq!(fixture.version, 1);
    assert_eq!(fixture.cases.len(), 10);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "ja-relation-exact-one",
        "ja-marker-and-relation-multiple",
        "en-relation-zero",
        "en-marker-exact-one",
        "en-multiple-markers",
        "sentence-boundary-no-cross-clause-fallback",
        "line-break-no-cross-clause-fallback",
        "ja-qualified-term-candidate",
        "en-marker-missing-both-contexts",
        "en-marker-zero-candidates",
    ] {
        assert!(ids.contains(required), "missing fixture case: {required}");
    }
}

fn load_fixture() -> Fixture {
    serde_json::from_str(FIXTURE).expect("fixture must be valid JSON")
}

fn document_for(case: &Case) -> NormalizedDdlDocument {
    NormalizedDdlDocument::new(
        case.source.clone(),
        match case.language.as_str() {
            "ja" => ResolvedInstructionLanguage::Ja,
            "en" => ResolvedInstructionLanguage::En,
            _ => panic!("{}: invalid language", case.id),
        },
        Vec::new(),
    )
    .unwrap_or_else(|error| panic!("{}: invalid document: {error}", case.id))
}

fn project_nodes(result: &RelationReferenceEvidenceResult) -> Vec<ExpectedNode> {
    result
        .evidence
        .iter()
        .map(|node| ExpectedNode {
            kind: occurrence_name(&node.occurrence.kind),
            clause_index: node.clause_index,
            occurrence_atom_index: node.occurrence_atom_index,
            left_context_atom_indices: node.left_context_atom_indices.clone(),
            right_context_atom_indices: node.right_context_atom_indices.clone(),
            candidate_atom_indices: node.candidate_atom_indices.clone(),
            availability: availability_name(node.availability).to_owned(),
        })
        .collect()
}

fn project_missing_context(
    result: &RelationReferenceEvidenceResult,
) -> Vec<ExpectedMissingContext> {
    result
        .diagnostics
        .iter()
        .filter_map(|diagnostic| {
            let RelationReferenceEvidenceDiagnosticKind::MissingContext {
                missing_left,
                missing_right,
            } = diagnostic.kind
            else {
                return None;
            };
            Some(ExpectedMissingContext {
                kind: occurrence_name(&diagnostic.occurrence.kind),
                missing_left,
                missing_right,
            })
        })
        .collect()
}

fn assert_lossless_envelope(case: &Case, result: &RelationReferenceEvidenceResult) {
    let stream = &result.attachment_evidence.noun_phrase.clause_stream;
    let mut expected_occurrences = HashMap::new();
    for (clause_index, clause) in stream.clauses.iter().enumerate() {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            if matches!(atom, ClauseAtom::SaijikiRelation { .. }) {
                expected_occurrences.insert((clause_index, atom_index), 1usize);
            }
        }
    }
    for marker in &result.attachment_evidence.evidence {
        let clause = &stream.clauses[marker.clause_index];
        let atom_index = clause
            .atoms
            .iter()
            .position(|atom| atom.span() == marker.span)
            .expect("accepted marker must own a clause atom");
        *expected_occurrences
            .entry((marker.clause_index, atom_index))
            .or_default() += 1;
    }
    assert!(
        expected_occurrences.values().all(|count| *count == 1),
        "{}",
        case.id
    );

    let mut delivered_occurrences = HashSet::new();
    for node in &result.evidence {
        assert_node(case, result, node);
        assert!(
            delivered_occurrences.insert((node.clause_index, node.occurrence_atom_index)),
            "{}: duplicate envelope",
            case.id
        );
    }
    for diagnostic in &result.diagnostics {
        let key = (
            diagnostic
                .declared_clause_index
                .expect("fixture diagnostics retain clause membership"),
            diagnostic
                .occurrence_atom_index
                .expect("fixture diagnostics retain atom membership"),
        );
        assert!(
            delivered_occurrences.insert(key),
            "{}: occurrence reached both envelope and diagnostic",
            case.id
        );
    }
    assert_eq!(
        delivered_occurrences.len(),
        expected_occurrences.len(),
        "{}",
        case.id
    );
    assert_eq!(
        result
            .evidence
            .iter()
            .map(|node| node.occurrence.span.start_byte)
            .chain(
                result
                    .diagnostics
                    .iter()
                    .map(|diagnostic| diagnostic.occurrence.span.start_byte),
            )
            .collect::<Vec<_>>()
            .len(),
        expected_occurrences.len(),
        "{}",
        case.id
    );
}

fn assert_node(
    case: &Case,
    result: &RelationReferenceEvidenceResult,
    node: &RelationReferenceCandidateEnvelope,
) {
    let stream = &result.attachment_evidence.noun_phrase.clause_stream;
    let clause = &stream.clauses[node.clause_index];
    assert_eq!(node.clause_span, clause.span, "{}", case.id);
    assert_eq!(
        clause.atoms[node.occurrence_atom_index].span(),
        node.occurrence.span,
        "{}",
        case.id
    );
    assert_eq!(
        node.left_context_span,
        (clause.span.start_byte < node.occurrence.span.start_byte).then_some(SourceSpan {
            start_byte: clause.span.start_byte,
            end_byte: node.occurrence.span.start_byte,
        }),
        "{}",
        case.id
    );
    assert_eq!(
        node.right_context_span,
        (node.occurrence.span.end_byte < clause.span.end_byte).then_some(SourceSpan {
            start_byte: node.occurrence.span.end_byte,
            end_byte: clause.span.end_byte,
        }),
        "{}",
        case.id
    );
    assert!(
        node.candidate_atom_indices
            .windows(2)
            .all(|pair| pair[0] < pair[1]),
        "{}: candidates must remain in source order",
        case.id
    );
    for &candidate_index in &node.candidate_atom_indices {
        assert!(candidate_index < clause.atoms.len(), "{}", case.id);
        assert!(
            is_reference_candidate(&clause.atoms[candidate_index]),
            "{}",
            case.id
        );
    }
    assert_eq!(
        node.availability,
        match node.candidate_atom_indices.len() {
            0 => RelationReferenceEvidenceAvailability::Zero,
            1 => RelationReferenceEvidenceAvailability::ExactOne,
            _ => RelationReferenceEvidenceAvailability::Multiple,
        },
        "{}",
        case.id
    );
}

fn is_reference_candidate(atom: &ClauseAtom) -> bool {
    matches!(atom, ClauseAtom::CoreRole(_) | ClauseAtom::RemainingRole(_))
        || matches!(
            atom,
            ClauseAtom::UnresolvedDiagnostic(diagnostic)
                if diagnostic.kind == NeutralDiagnosticKind::Unknown && !diagnostic.recognized
        )
}

fn occurrence_name(kind: &RelationReferenceOccurrenceKind) -> String {
    match kind {
        RelationReferenceOccurrenceKind::SaijikiRelation { relation_type, .. } => {
            format!("relation:{relation_type}")
        }
        RelationReferenceOccurrenceKind::AttachmentMarker { marker, .. } => {
            format!("marker:{}", marker_name(*marker))
        }
    }
}

const fn marker_name(marker: AttachmentMarkerKind) -> &'static str {
    match marker {
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wo) => "ja:wo",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Ni) => "ja:ni",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::De) => "ja:de",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::No) => "ja:no",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wa) => "ja:wa",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Ga) => "ja:ga",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::He) => "ja:he",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::To) => "ja:to",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::With) => "en:with",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::In) => "en:in",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::At) => "en:at",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::On) => "en:on",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::To) => "en:to",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::Of) => "en:of",
    }
}

const fn availability_name(availability: RelationReferenceEvidenceAvailability) -> &'static str {
    match availability {
        RelationReferenceEvidenceAvailability::Zero => "zero",
        RelationReferenceEvidenceAvailability::ExactOne => "exact_one",
        RelationReferenceEvidenceAvailability::Multiple => "multiple",
    }
}
