//! Source-preserving relation/reference candidate evidence over accepted attachment evidence.

use crate::{
    AttachmentEvidenceResult, AttachmentMarkerKind, ClauseAtom, ClauseSegment, ClauseStreamError,
    EnglishAttachmentMarkerKind, JapaneseAttachmentMarkerKind, NeutralDiagnosticKind,
    NormalizedDdlDocument, SourceSpan, collect_attachment_evidence,
};

/// Stable identity for the runtime-disconnected relation/reference evidence envelope.
pub const RELATION_REFERENCE_EVIDENCE_SCHEMA_ID: &str = "inku.relation-reference-evidence.v1";

/// Closed candidate availability without a target-selection policy.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RelationReferenceEvidenceAvailability {
    Zero,
    ExactOne,
    Multiple,
}

/// One explicit source occurrence that can carry same-clause candidate evidence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RelationReferenceOccurrenceKind {
    SaijikiRelation {
        asset_id: String,
        relation_type: String,
    },
    AttachmentMarker {
        attachment_evidence_index: usize,
        marker: AttachmentMarkerKind,
    },
}

/// Source identity shared by successful envelopes and stable diagnostics.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RelationReferenceOccurrence {
    pub kind: RelationReferenceOccurrenceKind,
    pub surface: String,
    pub span: SourceSpan,
}

/// One valid occurrence and all of its source-ordered same-clause candidates.
///
/// Candidate indexes point into `attachment_evidence.noun_phrase.clause_stream`.
/// They retain typed Saijiki role atoms and opaque unknown atoms (including visible
/// qualified terms) without choosing a target, role, side, adjacency, or fallback.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RelationReferenceCandidateEnvelope {
    pub occurrence: RelationReferenceOccurrence,
    pub clause_index: usize,
    pub clause_span: SourceSpan,
    pub occurrence_atom_index: usize,
    pub left_context_span: Option<SourceSpan>,
    pub right_context_span: Option<SourceSpan>,
    pub left_context_atom_indices: Vec<usize>,
    pub right_context_atom_indices: Vec<usize>,
    pub candidate_atom_indices: Vec<usize>,
    pub availability: RelationReferenceEvidenceAvailability,
}

/// Stable integrity failures that never produce a partial semantic relation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RelationReferenceEvidenceDiagnosticKind {
    MissingContext {
        missing_left: bool,
        missing_right: bool,
    },
    SourceContainment,
    OrphanOccurrence,
    DuplicateOccurrence,
    ClauseMembershipMismatch,
    CandidateMembershipMismatch,
}

/// One occurrence withheld from the valid envelope set.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RelationReferenceEvidenceDiagnostic {
    pub kind: RelationReferenceEvidenceDiagnosticKind,
    pub occurrence: RelationReferenceOccurrence,
    pub declared_clause_index: Option<usize>,
    pub occurrence_atom_index: Option<usize>,
}

/// The accepted I-569 result plus meaning-neutral relation/reference evidence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RelationReferenceEvidenceResult {
    pub attachment_evidence: AttachmentEvidenceResult,
    pub evidence: Vec<RelationReferenceCandidateEnvelope>,
    pub diagnostics: Vec<RelationReferenceEvidenceDiagnostic>,
}

/// Collect relation/reference evidence from one source-preserving document.
///
/// The accepted I-569 collector is invoked exactly once. Its complete result,
/// including the accepted clause stream, is owned unchanged by the return value.
pub fn collect_relation_reference_evidence(
    document: &NormalizedDdlDocument,
) -> Result<RelationReferenceEvidenceResult, ClauseStreamError> {
    let attachment_evidence = collect_attachment_evidence(document)?;
    Ok(build_evidence(document.source(), attachment_evidence))
}

#[derive(Clone)]
struct PendingOccurrence {
    occurrence: RelationReferenceOccurrence,
    declared_clause_index: Option<usize>,
    occurrence_atom_index: Option<usize>,
    attachment_evidence_index: Option<usize>,
}

fn build_evidence(
    source: &str,
    attachment_evidence: AttachmentEvidenceResult,
) -> RelationReferenceEvidenceResult {
    let stream = &attachment_evidence.noun_phrase.clause_stream;
    let mut pending = Vec::new();

    for (clause_index, clause) in stream.clauses.iter().enumerate() {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            let ClauseAtom::SaijikiRelation {
                asset_id,
                relation_type,
                surface,
                span,
            } = atom
            else {
                continue;
            };
            pending.push(PendingOccurrence {
                occurrence: RelationReferenceOccurrence {
                    kind: RelationReferenceOccurrenceKind::SaijikiRelation {
                        asset_id: asset_id.clone(),
                        relation_type: relation_type.clone(),
                    },
                    surface: surface.clone(),
                    span: *span,
                },
                declared_clause_index: Some(clause_index),
                occurrence_atom_index: Some(atom_index),
                attachment_evidence_index: None,
            });
        }
    }

    for (attachment_evidence_index, marker) in attachment_evidence.evidence.iter().enumerate() {
        let occurrence_atom_index = stream.clauses.get(marker.clause_index).and_then(|clause| {
            clause
                .atoms
                .iter()
                .position(|atom| atom.span() == marker.span)
        });
        pending.push(PendingOccurrence {
            occurrence: RelationReferenceOccurrence {
                kind: RelationReferenceOccurrenceKind::AttachmentMarker {
                    attachment_evidence_index,
                    marker: marker.marker,
                },
                surface: marker.surface.clone(),
                span: marker.span,
            },
            declared_clause_index: Some(marker.clause_index),
            occurrence_atom_index,
            attachment_evidence_index: Some(attachment_evidence_index),
        });
    }

    pending.sort_by_key(|item| {
        (
            item.occurrence.span.start_byte,
            item.occurrence.span.end_byte,
        )
    });

    let mut evidence = Vec::new();
    let mut diagnostics = Vec::new();
    for item in &pending {
        let duplicate = pending
            .iter()
            .filter(|candidate| candidate.occurrence.span == item.occurrence.span)
            .count()
            > 1;
        match build_envelope(source, &attachment_evidence, item, duplicate) {
            Ok(envelope) => evidence.push(envelope),
            Err(diagnostic) => diagnostics.push(diagnostic),
        }
    }

    RelationReferenceEvidenceResult {
        attachment_evidence,
        evidence,
        diagnostics,
    }
}

fn build_envelope(
    source: &str,
    attachment_evidence: &AttachmentEvidenceResult,
    pending: &PendingOccurrence,
    duplicate: bool,
) -> Result<RelationReferenceCandidateEnvelope, RelationReferenceEvidenceDiagnostic> {
    if duplicate {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::DuplicateOccurrence,
        ));
    }

    let span = pending.occurrence.span;
    if !valid_source_span(source, span) {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::SourceContainment,
        ));
    }

    let Some(clause_index) = pending.declared_clause_index else {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::ClauseMembershipMismatch,
        ));
    };
    let Some(clause) = attachment_evidence
        .noun_phrase
        .clause_stream
        .clauses
        .get(clause_index)
    else {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::ClauseMembershipMismatch,
        ));
    };
    if !contains(clause.span, span) {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::SourceContainment,
        ));
    }

    let Some(occurrence_atom_index) = pending.occurrence_atom_index else {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::OrphanOccurrence,
        ));
    };
    let Some(occurrence_atom) = clause.atoms.get(occurrence_atom_index) else {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::ClauseMembershipMismatch,
        ));
    };
    if occurrence_atom.span() != span
        || !occurrence_matches_atom(&pending.occurrence, occurrence_atom, source)
    {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::OrphanOccurrence,
        ));
    }

    let left_context_span = (clause.span.start_byte < span.start_byte).then_some(SourceSpan {
        start_byte: clause.span.start_byte,
        end_byte: span.start_byte,
    });
    let right_context_span = (span.end_byte < clause.span.end_byte).then_some(SourceSpan {
        start_byte: span.end_byte,
        end_byte: clause.span.end_byte,
    });
    let left_context_atom_indices = clause
        .atoms
        .iter()
        .enumerate()
        .filter(|(_, atom)| atom.span().end_byte <= span.start_byte)
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    let right_context_atom_indices = clause
        .atoms
        .iter()
        .enumerate()
        .filter(|(_, atom)| span.end_byte <= atom.span().start_byte)
        .map(|(index, _)| index)
        .collect::<Vec<_>>();

    if let Some(attachment_evidence_index) = pending.attachment_evidence_index {
        let Some(marker) = attachment_evidence.evidence.get(attachment_evidence_index) else {
            return Err(diagnostic(
                pending,
                RelationReferenceEvidenceDiagnosticKind::OrphanOccurrence,
            ));
        };
        let left_atom_spans = project_atom_spans(clause, &left_context_atom_indices);
        let right_atom_spans = project_atom_spans(clause, &right_context_atom_indices);
        if marker.clause_index != clause_index
            || marker.clause_span != clause.span
            || marker.left_context_span != left_context_span
            || marker.right_context_span != right_context_span
            || marker.left_atom_spans != left_atom_spans
            || marker.right_atom_spans != right_atom_spans
        {
            return Err(diagnostic(
                pending,
                RelationReferenceEvidenceDiagnosticKind::CandidateMembershipMismatch,
            ));
        }
    }

    let missing_left = left_context_atom_indices.is_empty();
    let missing_right = right_context_atom_indices.is_empty();
    if missing_left || missing_right {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::MissingContext {
                missing_left,
                missing_right,
            },
        ));
    }

    let candidate_atom_indices = clause
        .atoms
        .iter()
        .enumerate()
        .filter(|(_, atom)| is_reference_candidate(atom))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    if !valid_candidate_membership(
        clause,
        occurrence_atom_index,
        &left_context_atom_indices,
        &right_context_atom_indices,
        &candidate_atom_indices,
    ) {
        return Err(diagnostic(
            pending,
            RelationReferenceEvidenceDiagnosticKind::CandidateMembershipMismatch,
        ));
    }

    Ok(RelationReferenceCandidateEnvelope {
        occurrence: pending.occurrence.clone(),
        clause_index,
        clause_span: clause.span,
        occurrence_atom_index,
        left_context_span,
        right_context_span,
        left_context_atom_indices,
        right_context_atom_indices,
        availability: availability(candidate_atom_indices.len()),
        candidate_atom_indices,
    })
}

fn occurrence_matches_atom(
    occurrence: &RelationReferenceOccurrence,
    atom: &ClauseAtom,
    source: &str,
) -> bool {
    if source[occurrence.span.start_byte..occurrence.span.end_byte] != occurrence.surface {
        return false;
    }
    match (&occurrence.kind, atom) {
        (
            RelationReferenceOccurrenceKind::SaijikiRelation {
                asset_id,
                relation_type,
            },
            ClauseAtom::SaijikiRelation {
                asset_id: atom_asset_id,
                relation_type: atom_relation_type,
                surface,
                ..
            },
        ) => {
            asset_id == atom_asset_id
                && relation_type == atom_relation_type
                && occurrence.surface == *surface
        }
        (
            RelationReferenceOccurrenceKind::AttachmentMarker { marker, .. },
            ClauseAtom::FunctionWord { surface, .. },
        ) => occurrence.surface == *surface && marker_matches_surface(*marker, surface),
        _ => false,
    }
}

fn marker_matches_surface(marker: AttachmentMarkerKind, surface: &str) -> bool {
    match marker {
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wo) => surface == "を",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Ni) => surface == "に",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::De) => surface == "で",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::No) => surface == "の",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Wa) => surface == "は",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::Ga) => surface == "が",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::He) => surface == "へ",
        AttachmentMarkerKind::Japanese(JapaneseAttachmentMarkerKind::To) => surface == "と",
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::With) => {
            surface.eq_ignore_ascii_case("with")
        }
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::In) => {
            surface.eq_ignore_ascii_case("in")
        }
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::At) => {
            surface.eq_ignore_ascii_case("at")
        }
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::On) => {
            surface.eq_ignore_ascii_case("on")
        }
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::To) => {
            surface.eq_ignore_ascii_case("to")
        }
        AttachmentMarkerKind::English(EnglishAttachmentMarkerKind::Of) => {
            surface.eq_ignore_ascii_case("of")
        }
    }
}

fn is_reference_candidate(atom: &ClauseAtom) -> bool {
    matches!(atom, ClauseAtom::CoreRole(_) | ClauseAtom::RemainingRole(_))
        || matches!(
            atom,
            ClauseAtom::UnresolvedDiagnostic(diagnostic)
                if diagnostic.kind == NeutralDiagnosticKind::Unknown && !diagnostic.recognized
        )
}

fn valid_candidate_membership(
    clause: &ClauseSegment,
    occurrence_atom_index: usize,
    left_context_atom_indices: &[usize],
    right_context_atom_indices: &[usize],
    candidate_atom_indices: &[usize],
) -> bool {
    let context_count = left_context_atom_indices.len() + right_context_atom_indices.len();
    if context_count + 1 != clause.atoms.len()
        || left_context_atom_indices
            .iter()
            .chain(right_context_atom_indices)
            .any(|&index| index == occurrence_atom_index || index >= clause.atoms.len())
        || !strictly_increasing(left_context_atom_indices)
        || !strictly_increasing(right_context_atom_indices)
        || !strictly_increasing(candidate_atom_indices)
    {
        return false;
    }

    let expected_candidates = clause
        .atoms
        .iter()
        .enumerate()
        .filter(|(_, atom)| is_reference_candidate(atom))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    candidate_atom_indices == expected_candidates
        && candidate_atom_indices.iter().all(|index| {
            left_context_atom_indices.contains(index) || right_context_atom_indices.contains(index)
        })
}

fn project_atom_spans(clause: &ClauseSegment, indices: &[usize]) -> Vec<SourceSpan> {
    indices
        .iter()
        .filter_map(|&index| clause.atoms.get(index).map(ClauseAtom::span))
        .collect()
}

const fn availability(candidate_count: usize) -> RelationReferenceEvidenceAvailability {
    match candidate_count {
        0 => RelationReferenceEvidenceAvailability::Zero,
        1 => RelationReferenceEvidenceAvailability::ExactOne,
        _ => RelationReferenceEvidenceAvailability::Multiple,
    }
}

fn diagnostic(
    pending: &PendingOccurrence,
    kind: RelationReferenceEvidenceDiagnosticKind,
) -> RelationReferenceEvidenceDiagnostic {
    RelationReferenceEvidenceDiagnostic {
        kind,
        occurrence: pending.occurrence.clone(),
        declared_clause_index: pending.declared_clause_index,
        occurrence_atom_index: pending.occurrence_atom_index,
    }
}

fn valid_source_span(source: &str, span: SourceSpan) -> bool {
    span.start_byte < span.end_byte
        && span.end_byte <= source.len()
        && source.is_char_boundary(span.start_byte)
        && source.is_char_boundary(span.end_byte)
}

fn strictly_increasing(indices: &[usize]) -> bool {
    indices.windows(2).all(|pair| pair[0] < pair[1])
}

const fn contains(container: SourceSpan, contained: SourceSpan) -> bool {
    container.start_byte <= contained.start_byte && contained.end_byte <= container.end_byte
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ResolvedInstructionLanguage;

    fn attachment(source: &str) -> AttachmentEvidenceResult {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .unwrap();
        collect_attachment_evidence(&document).unwrap()
    }

    #[test]
    fn corrupted_attachment_overlay_yields_stable_diagnostics_without_partial_envelopes() {
        let source = "circle with line";

        let mut duplicate = attachment(source);
        duplicate.evidence.push(duplicate.evidence[0].clone());
        let result = build_evidence(source, duplicate);
        assert!(result.evidence.is_empty());
        assert_eq!(result.diagnostics.len(), 2);
        assert!(result.diagnostics.iter().all(|item| {
            item.kind == RelationReferenceEvidenceDiagnosticKind::DuplicateOccurrence
        }));

        let mut orphan = attachment(source);
        orphan.evidence[0].surface = "other".to_owned();
        let result = build_evidence(source, orphan);
        assert!(result.evidence.is_empty());
        assert_eq!(
            result.diagnostics[0].kind,
            RelationReferenceEvidenceDiagnosticKind::OrphanOccurrence
        );

        let mut containment = attachment(source);
        containment.evidence[0].span.end_byte = source.len() + 1;
        let result = build_evidence(source, containment);
        assert!(result.evidence.is_empty());
        assert_eq!(
            result.diagnostics[0].kind,
            RelationReferenceEvidenceDiagnosticKind::SourceContainment
        );

        let mut membership = attachment(source);
        membership.evidence[0].clause_index = 7;
        let result = build_evidence(source, membership);
        assert!(result.evidence.is_empty());
        assert_eq!(
            result.diagnostics[0].kind,
            RelationReferenceEvidenceDiagnosticKind::ClauseMembershipMismatch
        );

        let mut candidate_membership = attachment(source);
        candidate_membership.evidence[0].left_atom_spans.clear();
        let result = build_evidence(source, candidate_membership);
        assert!(result.evidence.is_empty());
        assert_eq!(
            result.diagnostics[0].kind,
            RelationReferenceEvidenceDiagnosticKind::CandidateMembershipMismatch
        );
    }
}
