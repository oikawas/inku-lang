//! Source-preserving topology for unresolved English determiner phrases.

use std::ops::Range;

use crate::{
    ClauseAtom, ClauseStreamError, EnglishOpaqueHeadCandidateEvidenceResult, NeutralDiagnosticKind,
    NormalizedDdlDocument, NounPhraseEvidenceDiagnosticKind, SourceSpan,
    collect_english_opaque_head_candidate_evidence,
};

/// Stable identity for the runtime-disconnected unresolved determiner-phrase topology overlay.
pub const UNRESOLVED_DETERMINER_PHRASE_TOPOLOGY_EVIDENCE_SCHEMA_ID: &str =
    "inku.english-unresolved-determiner-phrase-topology-evidence.v1";

/// One source-contiguous run of opaque candidate atoms in an accepted candidate region.
///
/// The range is half-open over the owned clause's atom indexes. It references the source-bearing
/// atoms without copying their surfaces and does not select a semantic head or role.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnresolvedDeterminerPhraseOpaqueCandidateRun {
    pub clause_atom_range: Range<usize>,
    pub candidate_count: usize,
}

/// One lossless, meaning-neutral topology node for an I-572 missing-canonical region.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnresolvedDeterminerPhraseTopologyEvidence {
    pub clause_index: usize,
    pub determiner_span: SourceSpan,
    pub candidate_region_span: SourceSpan,
    pub candidate_region_atom_indices: Vec<usize>,
    pub opaque_candidate_runs: Vec<UnresolvedDeterminerPhraseOpaqueCandidateRun>,
}

/// The accepted I-572 result plus a non-delivery unresolved phrase-topology overlay.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult {
    pub opaque_head_candidate_result: EnglishOpaqueHeadCandidateEvidenceResult,
    pub topology: Vec<UnresolvedDeterminerPhraseTopologyEvidence>,
}

/// Collect source-preserving topology for missing canonical English determiner-phrase heads.
///
/// The accepted I-572 collector runs exactly once. Its complete result is owned unchanged; this
/// overlay only records indexes and ranges into that result and contributes no semantic delivery.
pub fn collect_english_unresolved_determiner_phrase_topology_evidence(
    document: &NormalizedDdlDocument,
) -> Result<EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult, ClauseStreamError> {
    let opaque_head_candidate_result = collect_english_opaque_head_candidate_evidence(document)?;
    let topology = collect_topology(&opaque_head_candidate_result);

    Ok(EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult {
        opaque_head_candidate_result,
        topology,
    })
}

fn collect_topology(
    result: &EnglishOpaqueHeadCandidateEvidenceResult,
) -> Vec<UnresolvedDeterminerPhraseTopologyEvidence> {
    result
        .noun_phrase_result
        .diagnostics
        .iter()
        .filter(|diagnostic| {
            diagnostic.kind == NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate
        })
        .map(|missing| {
            let clause = &result.noun_phrase_result.clause_stream.clauses[missing.clause_index];
            let candidate_region_atom_indices = clause
                .atoms
                .iter()
                .enumerate()
                .filter(|(_, atom)| atom_belongs_to_candidate_region(atom, missing))
                .map(|(atom_index, _)| atom_index)
                .collect::<Vec<_>>();
            let opaque_candidate_runs =
                collect_opaque_candidate_runs(&clause.atoms, &candidate_region_atom_indices);

            UnresolvedDeterminerPhraseTopologyEvidence {
                clause_index: missing.clause_index,
                determiner_span: missing.determiner_span,
                candidate_region_span: missing.candidate_region_span,
                candidate_region_atom_indices,
                opaque_candidate_runs,
            }
        })
        .collect()
}

fn atom_belongs_to_candidate_region(
    atom: &ClauseAtom,
    missing: &crate::NounPhraseEvidenceDiagnostic,
) -> bool {
    let span = atom.span();
    span.start_byte >= missing.determiner_span.end_byte
        && span.end_byte <= missing.candidate_region_span.end_byte
}

fn collect_opaque_candidate_runs(
    atoms: &[ClauseAtom],
    candidate_region_atom_indices: &[usize],
) -> Vec<UnresolvedDeterminerPhraseOpaqueCandidateRun> {
    let mut runs: Vec<UnresolvedDeterminerPhraseOpaqueCandidateRun> = Vec::new();

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
            runs.push(UnresolvedDeterminerPhraseOpaqueCandidateRun {
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{NeutralDiagnostic, NeutralDiagnosticKind};

    #[test]
    fn only_consecutive_unrecognized_unknown_atoms_share_a_run() {
        let diagnostic = |kind, recognized, start_byte, end_byte| {
            ClauseAtom::UnresolvedDiagnostic(NeutralDiagnostic {
                span: SourceSpan {
                    start_byte,
                    end_byte,
                },
                surface: "synthetic".to_owned(),
                kind,
                recognized,
            })
        };
        let atoms = vec![
            diagnostic(NeutralDiagnosticKind::Unknown, false, 0, 1),
            diagnostic(NeutralDiagnosticKind::Unknown, false, 2, 3),
            diagnostic(NeutralDiagnosticKind::Hole, true, 4, 5),
            diagnostic(NeutralDiagnosticKind::Unknown, true, 6, 7),
            diagnostic(NeutralDiagnosticKind::Unknown, false, 8, 9),
        ];

        assert_eq!(
            collect_opaque_candidate_runs(&atoms, &[0, 1, 2, 3, 4]),
            vec![
                UnresolvedDeterminerPhraseOpaqueCandidateRun {
                    clause_atom_range: 0..2,
                    candidate_count: 2,
                },
                UnresolvedDeterminerPhraseOpaqueCandidateRun {
                    clause_atom_range: 4..5,
                    candidate_count: 1,
                },
            ]
        );
    }
}
