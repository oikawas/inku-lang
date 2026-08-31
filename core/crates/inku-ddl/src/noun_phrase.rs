//! Source-preserving English determiner and noun-phrase candidate evidence.

use crate::{
    ClauseAtom, ClauseSegment, ClauseStream, ClauseStreamError, CoreRoleKind,
    NormalizedDdlDocument, ResolvedInstructionLanguage, SourceSpan, parse_clause_stream,
};

/// Stable identity for the runtime-disconnected English noun-phrase evidence foundation.
pub const NOUN_PHRASE_EVIDENCE_SCHEMA_ID: &str = "inku.english-noun-phrase-evidence.v1";

/// Canonical identity of an accepted English determiner function word.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EnglishDeterminerKind {
    A,
    An,
    The,
}

impl EnglishDeterminerKind {
    fn from_ascii_case_insensitive_surface(surface: &str) -> Option<Self> {
        if surface.eq_ignore_ascii_case("a") {
            Some(Self::A)
        } else if surface.eq_ignore_ascii_case("an") {
            Some(Self::An)
        } else if surface.eq_ignore_ascii_case("the") {
            Some(Self::The)
        } else {
            None
        }
    }
}

/// One accepted determiner with exact source bytes and a half-open UTF-8 span.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EnglishDeterminerEvidence {
    pub kind: EnglishDeterminerKind,
    pub surface: String,
    pub span: SourceSpan,
}

/// One canonical primitive delivery that is mechanically eligible as a head.
///
/// This is evidence only and does not assign subject, literal, drawable, reference,
/// or attachment semantics.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CanonicalHeadCandidate {
    pub asset_id: String,
    pub category_key: String,
    pub canonical_surface_ja: String,
    pub span: SourceSpan,
}

/// One determiner-bounded mechanical candidate region in an accepted clause.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EnglishNounPhraseCandidateEvidence {
    pub clause_index: usize,
    pub clause_span: SourceSpan,
    pub determiner: EnglishDeterminerEvidence,
    pub candidate_region_span: SourceSpan,
    pub head_candidate: Option<CanonicalHeadCandidate>,
    pub opaque_pre_head_span: Option<SourceSpan>,
}

/// Stable evidence-availability diagnostics without a semantic fallback.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum NounPhraseEvidenceDiagnosticKind {
    MissingCanonicalHeadCandidate,
    AmbiguousCanonicalHeadCandidates,
}

/// One unresolved candidate region, retaining every eligible primitive in source order.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NounPhraseEvidenceDiagnostic {
    pub kind: NounPhraseEvidenceDiagnosticKind,
    pub clause_index: usize,
    pub determiner_span: SourceSpan,
    pub candidate_region_span: SourceSpan,
    pub candidates: Vec<CanonicalHeadCandidate>,
}

/// The accepted clause stream plus a non-delivery evidence overlay.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EnglishNounPhraseEvidenceResult {
    pub clause_stream: ClauseStream,
    pub evidence: Vec<EnglishNounPhraseCandidateEvidence>,
    pub diagnostics: Vec<NounPhraseEvidenceDiagnostic>,
}

/// Collect English noun-phrase candidate evidence from one normalized document.
///
/// The accepted clause parser runs exactly once. The resulting stream is owned by
/// the return value unchanged; evidence and diagnostics are read-only overlays and
/// never contribute semantic deliveries.
pub fn collect_english_noun_phrase_evidence(
    document: &NormalizedDdlDocument,
) -> Result<EnglishNounPhraseEvidenceResult, ClauseStreamError> {
    let clause_stream = parse_clause_stream(document)?;
    let mut evidence = Vec::new();
    let mut diagnostics = Vec::new();

    if document.language() == ResolvedInstructionLanguage::En {
        for (clause_index, clause) in clause_stream.clauses.iter().enumerate() {
            collect_clause_evidence(
                document.source(),
                clause_index,
                clause,
                &mut evidence,
                &mut diagnostics,
            );
        }
    }

    Ok(EnglishNounPhraseEvidenceResult {
        clause_stream,
        evidence,
        diagnostics,
    })
}

fn collect_clause_evidence(
    source: &str,
    clause_index: usize,
    clause: &ClauseSegment,
    evidence: &mut Vec<EnglishNounPhraseCandidateEvidence>,
    diagnostics: &mut Vec<NounPhraseEvidenceDiagnostic>,
) {
    let determiners = clause
        .atoms
        .iter()
        .filter_map(|atom| determiner_from_atom(atom, source))
        .collect::<Vec<_>>();

    for (index, determiner) in determiners.iter().enumerate() {
        let region_end = determiners
            .get(index + 1)
            .map_or(clause.span.end_byte, |next| next.span.start_byte);
        let candidate_region_span = SourceSpan {
            start_byte: determiner.span.start_byte,
            end_byte: region_end,
        };
        let candidates = clause
            .atoms
            .iter()
            .filter_map(|atom| candidate_in_region(atom, determiner.span.end_byte, region_end))
            .collect::<Vec<_>>();

        let (head_candidate, opaque_pre_head_span) = match candidates.as_slice() {
            [candidate] => (
                Some(candidate.clone()),
                (determiner.span.end_byte < candidate.span.start_byte).then_some(SourceSpan {
                    start_byte: determiner.span.end_byte,
                    end_byte: candidate.span.start_byte,
                }),
            ),
            _ => (None, None),
        };
        if head_candidate.is_none() {
            diagnostics.push(NounPhraseEvidenceDiagnostic {
                kind: if candidates.is_empty() {
                    NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate
                } else {
                    NounPhraseEvidenceDiagnosticKind::AmbiguousCanonicalHeadCandidates
                },
                clause_index,
                determiner_span: determiner.span,
                candidate_region_span,
                candidates,
            });
        }

        evidence.push(EnglishNounPhraseCandidateEvidence {
            clause_index,
            clause_span: clause.span,
            determiner: determiner.clone(),
            candidate_region_span,
            head_candidate,
            opaque_pre_head_span,
        });
    }
}

fn determiner_from_atom(atom: &ClauseAtom, source: &str) -> Option<EnglishDeterminerEvidence> {
    let ClauseAtom::FunctionWord { span, .. } = atom else {
        return None;
    };
    let surface = &source[span.start_byte..span.end_byte];
    Some(EnglishDeterminerEvidence {
        kind: EnglishDeterminerKind::from_ascii_case_insensitive_surface(surface)?,
        surface: surface.to_owned(),
        span: *span,
    })
}

fn candidate_in_region(
    atom: &ClauseAtom,
    region_content_start: usize,
    region_end: usize,
) -> Option<CanonicalHeadCandidate> {
    let ClauseAtom::CoreRole(term) = atom else {
        return None;
    };
    if term.role != CoreRoleKind::Primitive
        || term.span.start_byte < region_content_start
        || term.span.end_byte > region_end
    {
        return None;
    }
    Some(CanonicalHeadCandidate {
        asset_id: term.asset_id.clone(),
        category_key: term.category_key.clone(),
        canonical_surface_ja: term.canonical_surface_ja.clone(),
        span: term.span,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::CoreRoleTerm;

    #[test]
    fn adjacent_synthetic_head_uses_none_for_the_empty_opaque_span() {
        let clause = ClauseSegment {
            span: SourceSpan {
                start_byte: 0,
                end_byte: 7,
            },
            atoms: vec![
                ClauseAtom::FunctionWord {
                    surface: "a".to_owned(),
                    span: SourceSpan {
                        start_byte: 0,
                        end_byte: 1,
                    },
                },
                ClauseAtom::CoreRole(CoreRoleTerm {
                    role: CoreRoleKind::Primitive,
                    asset_id: "inku.saijiki.v1".to_owned(),
                    category_key: "katachi".to_owned(),
                    canonical_surface_ja: "円".to_owned(),
                    span: SourceSpan {
                        start_byte: 1,
                        end_byte: 7,
                    },
                }),
            ],
        };
        let mut evidence = Vec::new();
        let mut diagnostics = Vec::new();

        collect_clause_evidence("acircle", 0, &clause, &mut evidence, &mut diagnostics);

        assert_eq!(evidence.len(), 1);
        assert_eq!(
            evidence[0].head_candidate.as_ref().unwrap().span.start_byte,
            1
        );
        assert!(evidence[0].opaque_pre_head_span.is_none());
        assert!(diagnostics.is_empty());
    }
}
