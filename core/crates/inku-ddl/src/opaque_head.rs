//! Meaning-neutral opaque head-candidate evidence for missing canonical English heads.

use crate::{
    ClauseAtom, ClauseStreamError, EnglishNounPhraseEvidenceResult, NeutralDiagnosticKind,
    NormalizedDdlDocument, NounPhraseEvidenceDiagnostic, NounPhraseEvidenceDiagnosticKind,
    SourceSpan, collect_english_noun_phrase_evidence,
};

/// Stable identity for the runtime-disconnected opaque head-candidate evidence overlay.
pub const OPAQUE_HEAD_CANDIDATE_EVIDENCE_SCHEMA_ID: &str =
    "inku.english-opaque-head-candidate-evidence.v1";

/// One unrecognized source surface mechanically available inside an accepted candidate region.
///
/// This is syntactic availability evidence only. It does not classify the surface as a noun,
/// head, subject, drawable, literal, reference, or attachment target.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct OpaqueHeadCandidateEvidence {
    pub surface: String,
    pub span: SourceSpan,
    pub clause_index: usize,
    pub determiner_span: SourceSpan,
    pub candidate_region_span: SourceSpan,
}

/// Stable evidence-availability diagnostics without a semantic fallback or silent selection.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum OpaqueHeadCandidateEvidenceDiagnosticKind {
    MissingOpaqueHeadCandidate,
    AmbiguousOpaqueHeadCandidates,
}

/// One missing or ambiguous opaque candidate outcome for an I-568 missing-canonical region.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct OpaqueHeadCandidateEvidenceDiagnostic {
    pub kind: OpaqueHeadCandidateEvidenceDiagnosticKind,
    pub clause_index: usize,
    pub determiner_span: SourceSpan,
    pub candidate_region_span: SourceSpan,
    pub candidates: Vec<OpaqueHeadCandidateEvidence>,
}

/// The accepted I-568 result plus a non-delivery opaque candidate overlay.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EnglishOpaqueHeadCandidateEvidenceResult {
    pub noun_phrase_result: EnglishNounPhraseEvidenceResult,
    pub evidence: Vec<OpaqueHeadCandidateEvidence>,
    pub diagnostics: Vec<OpaqueHeadCandidateEvidenceDiagnostic>,
}

/// Collect opaque candidate availability for missing canonical English heads.
///
/// The accepted noun-phrase collector runs exactly once. Its complete result is owned unchanged;
/// this overlay only reads unrecognized `Unknown` diagnostics already present in that result and
/// does not contribute semantic deliveries.
pub fn collect_english_opaque_head_candidate_evidence(
    document: &NormalizedDdlDocument,
) -> Result<EnglishOpaqueHeadCandidateEvidenceResult, ClauseStreamError> {
    let noun_phrase_result = collect_english_noun_phrase_evidence(document)?;
    let (evidence, diagnostics) = collect_overlay(&noun_phrase_result);

    Ok(EnglishOpaqueHeadCandidateEvidenceResult {
        noun_phrase_result,
        evidence,
        diagnostics,
    })
}

fn collect_overlay(
    noun_phrase_result: &EnglishNounPhraseEvidenceResult,
) -> (
    Vec<OpaqueHeadCandidateEvidence>,
    Vec<OpaqueHeadCandidateEvidenceDiagnostic>,
) {
    let mut evidence = Vec::new();
    let mut diagnostics = Vec::new();

    for missing in noun_phrase_result.diagnostics.iter().filter(|diagnostic| {
        diagnostic.kind == NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate
    }) {
        let clause = &noun_phrase_result.clause_stream.clauses[missing.clause_index];
        let candidates = clause
            .atoms
            .iter()
            .filter_map(|atom| candidate_in_region(atom, missing))
            .collect::<Vec<_>>();

        match candidates.as_slice() {
            [candidate] => evidence.push(candidate.clone()),
            _ => diagnostics.push(OpaqueHeadCandidateEvidenceDiagnostic {
                kind: if candidates.is_empty() {
                    OpaqueHeadCandidateEvidenceDiagnosticKind::MissingOpaqueHeadCandidate
                } else {
                    OpaqueHeadCandidateEvidenceDiagnosticKind::AmbiguousOpaqueHeadCandidates
                },
                clause_index: missing.clause_index,
                determiner_span: missing.determiner_span,
                candidate_region_span: missing.candidate_region_span,
                candidates,
            }),
        }
    }

    (evidence, diagnostics)
}

fn candidate_in_region(
    atom: &ClauseAtom,
    missing: &NounPhraseEvidenceDiagnostic,
) -> Option<OpaqueHeadCandidateEvidence> {
    let ClauseAtom::UnresolvedDiagnostic(diagnostic) = atom else {
        return None;
    };
    if diagnostic.kind != NeutralDiagnosticKind::Unknown
        || diagnostic.recognized
        || diagnostic.span.start_byte < missing.determiner_span.end_byte
        || diagnostic.span.end_byte > missing.candidate_region_span.end_byte
    {
        return None;
    }

    Some(OpaqueHeadCandidateEvidence {
        surface: diagnostic.surface.clone(),
        span: diagnostic.span,
        clause_index: missing.clause_index,
        determiner_span: missing.determiner_span,
        candidate_region_span: missing.candidate_region_span,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{NeutralDiagnostic, NeutralDiagnosticKind};

    #[test]
    fn holes_conflicts_and_recognized_unknowns_are_not_candidates() {
        let missing = NounPhraseEvidenceDiagnostic {
            kind: NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate,
            clause_index: 0,
            determiner_span: SourceSpan {
                start_byte: 0,
                end_byte: 1,
            },
            candidate_region_span: SourceSpan {
                start_byte: 0,
                end_byte: 32,
            },
            candidates: Vec::new(),
        };
        let diagnostic_atom = |kind, recognized, surface: &str, start_byte, end_byte| {
            ClauseAtom::UnresolvedDiagnostic(NeutralDiagnostic {
                span: SourceSpan {
                    start_byte,
                    end_byte,
                },
                surface: surface.to_owned(),
                kind,
                recognized,
            })
        };

        for atom in [
            diagnostic_atom(NeutralDiagnosticKind::Hole, true, "many", 2, 6),
            diagnostic_atom(NeutralDiagnosticKind::Conflict, true, "conflict", 7, 15),
            diagnostic_atom(NeutralDiagnosticKind::Unknown, true, "known", 16, 21),
        ] {
            assert!(candidate_in_region(&atom, &missing).is_none());
        }

        let opaque = diagnostic_atom(NeutralDiagnosticKind::Unknown, false, "opaque", 22, 28);
        assert_eq!(
            candidate_in_region(&opaque, &missing),
            Some(OpaqueHeadCandidateEvidence {
                surface: "opaque".to_owned(),
                span: SourceSpan {
                    start_byte: 22,
                    end_byte: 28,
                },
                clause_index: 0,
                determiner_span: missing.determiner_span,
                candidate_region_span: missing.candidate_region_span,
            })
        );
    }
}
