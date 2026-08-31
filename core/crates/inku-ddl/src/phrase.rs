//! Source-preserving general evidence for English determiner phrases.

use std::ops::Range;

use crate::{
    ClauseAtom, ClauseStreamError, EnglishNounPhraseCandidateEvidence,
    EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult, NeutralDiagnosticKind,
    NormalizedDdlDocument, NounPhraseEvidenceDiagnostic, NounPhraseEvidenceDiagnosticKind,
    SourceSpan, collect_english_unresolved_determiner_phrase_topology_evidence,
};

/// Stable identity for the runtime-disconnected general determiner-phrase evidence envelope.
pub const DETERMINER_PHRASE_EVIDENCE_SCHEMA_ID: &str = "inku.english-determiner-phrase-evidence.v1";

/// Canonical candidate availability for one accepted English determiner region.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DeterminerPhraseEvidenceAvailability {
    Missing,
    ExactOne,
    Multiple,
}

/// One source-contiguous run of opaque candidate atoms in a determiner region.
///
/// The range is half-open over the owned clause's atom indexes. It references existing atoms
/// without copying their surfaces and does not select a semantic head or role.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeterminerPhraseOpaqueCandidateRun {
    pub clause_atom_range: Range<usize>,
    pub candidate_count: usize,
}

/// One lossless, meaning-neutral evidence node for an accepted English determiner region.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EnglishDeterminerPhraseEvidence {
    pub clause_index: usize,
    pub determiner_span: SourceSpan,
    pub candidate_region_span: SourceSpan,
    pub candidate_region_atom_indices: Vec<usize>,
    pub canonical_candidate_spans: Vec<SourceSpan>,
    pub opaque_candidate_runs: Vec<DeterminerPhraseOpaqueCandidateRun>,
    pub availability: DeterminerPhraseEvidenceAvailability,
}

/// The accepted I-576 result plus one general non-delivery node per owned I-568 region.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EnglishDeterminerPhraseEvidenceResult {
    pub unresolved_phrase_topology_result: EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult,
    pub evidence: Vec<EnglishDeterminerPhraseEvidence>,
}

/// Collect general English determiner-phrase evidence without semantic selection.
///
/// The accepted I-576 collector runs exactly once. Its complete result is owned unchanged; the
/// general nodes only reference source spans and atom indexes already present in that result and
/// never contribute semantic deliveries.
pub fn collect_english_determiner_phrase_evidence(
    document: &NormalizedDdlDocument,
) -> Result<EnglishDeterminerPhraseEvidenceResult, ClauseStreamError> {
    let unresolved_phrase_topology_result =
        collect_english_unresolved_determiner_phrase_topology_evidence(document)?;
    let evidence = collect_general_evidence(&unresolved_phrase_topology_result);

    Ok(EnglishDeterminerPhraseEvidenceResult {
        unresolved_phrase_topology_result,
        evidence,
    })
}

fn collect_general_evidence(
    result: &EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult,
) -> Vec<EnglishDeterminerPhraseEvidence> {
    let noun_phrase_result = &result.opaque_head_candidate_result.noun_phrase_result;
    let mut missing_topology = result.topology.iter();

    noun_phrase_result
        .evidence
        .iter()
        .map(|region| {
            let (availability, canonical_candidate_spans) =
                classify_availability(region, &noun_phrase_result.diagnostics);
            let (candidate_region_atom_indices, opaque_candidate_runs) =
                if availability == DeterminerPhraseEvidenceAvailability::Missing {
                    let topology = missing_topology
                        .next()
                        .expect("accepted I-576 topology covers every missing I-568 region");
                    debug_assert_eq!(topology.clause_index, region.clause_index);
                    debug_assert_eq!(topology.determiner_span, region.determiner.span);
                    debug_assert_eq!(topology.candidate_region_span, region.candidate_region_span);
                    (
                        topology.candidate_region_atom_indices.clone(),
                        topology
                            .opaque_candidate_runs
                            .iter()
                            .map(|run| DeterminerPhraseOpaqueCandidateRun {
                                clause_atom_range: run.clause_atom_range.clone(),
                                candidate_count: run.candidate_count,
                            })
                            .collect(),
                    )
                } else {
                    let clause = &noun_phrase_result.clause_stream.clauses[region.clause_index];
                    let atom_indices = clause
                        .atoms
                        .iter()
                        .enumerate()
                        .filter(|(_, atom)| atom_belongs_to_candidate_region(atom, region))
                        .map(|(atom_index, _)| atom_index)
                        .collect::<Vec<_>>();
                    let opaque_runs = collect_opaque_candidate_runs(&clause.atoms, &atom_indices);
                    (atom_indices, opaque_runs)
                };

            EnglishDeterminerPhraseEvidence {
                clause_index: region.clause_index,
                determiner_span: region.determiner.span,
                candidate_region_span: region.candidate_region_span,
                candidate_region_atom_indices,
                canonical_candidate_spans,
                opaque_candidate_runs,
                availability,
            }
        })
        .collect()
}

fn classify_availability(
    region: &EnglishNounPhraseCandidateEvidence,
    diagnostics: &[NounPhraseEvidenceDiagnostic],
) -> (DeterminerPhraseEvidenceAvailability, Vec<SourceSpan>) {
    if let Some(candidate) = &region.head_candidate {
        return (
            DeterminerPhraseEvidenceAvailability::ExactOne,
            vec![candidate.span],
        );
    }

    let diagnostic = diagnostics
        .iter()
        .find(|diagnostic| diagnostic_matches_region(diagnostic, region))
        .expect("accepted I-568 evidence has one diagnostic for every unresolved region");
    let availability = match diagnostic.kind {
        NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate => {
            debug_assert!(diagnostic.candidates.is_empty());
            DeterminerPhraseEvidenceAvailability::Missing
        }
        NounPhraseEvidenceDiagnosticKind::AmbiguousCanonicalHeadCandidates => {
            debug_assert!(diagnostic.candidates.len() > 1);
            DeterminerPhraseEvidenceAvailability::Multiple
        }
    };
    (
        availability,
        diagnostic
            .candidates
            .iter()
            .map(|candidate| candidate.span)
            .collect(),
    )
}

fn diagnostic_matches_region(
    diagnostic: &NounPhraseEvidenceDiagnostic,
    region: &EnglishNounPhraseCandidateEvidence,
) -> bool {
    diagnostic.clause_index == region.clause_index
        && diagnostic.determiner_span == region.determiner.span
        && diagnostic.candidate_region_span == region.candidate_region_span
}

fn atom_belongs_to_candidate_region(
    atom: &ClauseAtom,
    region: &EnglishNounPhraseCandidateEvidence,
) -> bool {
    let span = atom.span();
    span.start_byte >= region.determiner.span.end_byte
        && span.end_byte <= region.candidate_region_span.end_byte
}

fn collect_opaque_candidate_runs(
    atoms: &[ClauseAtom],
    candidate_region_atom_indices: &[usize],
) -> Vec<DeterminerPhraseOpaqueCandidateRun> {
    let mut runs: Vec<DeterminerPhraseOpaqueCandidateRun> = Vec::new();

    for &atom_index in candidate_region_atom_indices {
        if !is_opaque_candidate(&atoms[atom_index]) {
            continue;
        }

        if let Some(run) = runs
            .last_mut()
            .filter(|run| run.clause_atom_range.end == atom_index)
        {
            run.clause_atom_range.end += 1;
            run.candidate_count += 1;
        } else {
            runs.push(DeterminerPhraseOpaqueCandidateRun {
                clause_atom_range: atom_index..atom_index + 1,
                candidate_count: 1,
            });
        }
    }

    runs
}

fn is_opaque_candidate(atom: &ClauseAtom) -> bool {
    matches!(
        atom,
        ClauseAtom::UnresolvedDiagnostic(diagnostic)
            if diagnostic.kind == NeutralDiagnosticKind::Unknown && !diagnostic.recognized
    )
}
