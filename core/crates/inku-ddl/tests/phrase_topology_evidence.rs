use std::collections::HashSet;

use inku_ddl::{
    ClauseAtom, EnglishOpaqueHeadCandidateEvidenceResult,
    EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult, NeutralDiagnosticKind,
    NormalizedDdlDocument, ResolvedInstructionLanguage, SourceSpan,
    UNRESOLVED_DETERMINER_PHRASE_TOPOLOGY_EVIDENCE_SCHEMA_ID,
    collect_english_opaque_head_candidate_evidence,
    collect_english_unresolved_determiner_phrase_topology_evidence,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/phrase-topology-evidence-v1.json");

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
    delivery_conservation_count: usize,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedNode {
    clause_index: usize,
    determiner_span: ExpectedSpan,
    candidate_region_span: ExpectedSpan,
    candidate_region_atom_indices: Vec<usize>,
    opaque_candidate_runs: Vec<ExpectedRun>,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedRun {
    start_atom_index: usize,
    end_atom_index: usize,
    candidate_count: usize,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedSpan {
    start_byte: usize,
    end_byte: usize,
}

#[test]
fn fixture_preserves_every_missing_region_atom_and_opaque_run() {
    for case in load_fixture().cases {
        let document = document_for(&case);
        let source_before = document.source().as_bytes().to_vec();
        let accepted = collect_english_opaque_head_candidate_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected I-572 error: {error}", case.id));
        let result = collect_english_unresolved_determiner_phrase_topology_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected topology error: {error}", case.id));

        assert_eq!(document.source().as_bytes(), source_before, "{}", case.id);
        assert_eq!(
            result.opaque_head_candidate_result, accepted,
            "{}: the accepted I-572 result must be owned unchanged",
            case.id
        );
        assert_eq!(
            result
                .opaque_head_candidate_result
                .noun_phrase_result
                .clause_stream
                .delivery_conservation_count,
            case.delivery_conservation_count,
            "{}",
            case.id
        );
        assert_eq!(project_nodes(&result), case.expected_nodes, "{}", case.id);
        assert_lossless_topology(&case.id, &result);
    }
}

#[test]
fn schema_fixture_and_required_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(
        UNRESOLVED_DETERMINER_PHRASE_TOPOLOGY_EVIDENCE_SCHEMA_ID,
        "inku.english-unresolved-determiner-phrase-topology-evidence.v1"
    );
    assert_eq!(
        fixture.schema,
        "inku.english-unresolved-determiner-phrase-topology-evidence-fixture.v1"
    );
    assert_eq!(fixture.version, 1);
    assert_eq!(fixture.cases.len(), 12);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "zero-empty-region",
        "zero-known-only-region",
        "exact-one-left-edge",
        "exact-one-right-edge",
        "exact-one-internal",
        "exact-one-both-edges",
        "multiple-one-run",
        "multiple-two-runs",
        "multiple-three-runs",
        "next-determiner-boundary",
        "utf8-source",
        "ja-non-output",
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

fn document_for(case: &Case) -> NormalizedDdlDocument {
    NormalizedDdlDocument::new(
        case.source.clone(),
        match case.language.as_str() {
            "ja" => ResolvedInstructionLanguage::Ja,
            "en" => ResolvedInstructionLanguage::En,
            _ => panic!("{}: invalid fixture language", case.id),
        },
        Vec::new(),
    )
    .unwrap_or_else(|error| panic!("{}: unexpected document diagnostic: {error}", case.id))
}

fn project_nodes(
    result: &EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult,
) -> Vec<ExpectedNode> {
    result
        .topology
        .iter()
        .map(|node| ExpectedNode {
            clause_index: node.clause_index,
            determiner_span: project_span(node.determiner_span),
            candidate_region_span: project_span(node.candidate_region_span),
            candidate_region_atom_indices: node.candidate_region_atom_indices.clone(),
            opaque_candidate_runs: node
                .opaque_candidate_runs
                .iter()
                .map(|run| ExpectedRun {
                    start_atom_index: run.clause_atom_range.start,
                    end_atom_index: run.clause_atom_range.end,
                    candidate_count: run.candidate_count,
                })
                .collect(),
        })
        .collect()
}

const fn project_span(span: SourceSpan) -> ExpectedSpan {
    ExpectedSpan {
        start_byte: span.start_byte,
        end_byte: span.end_byte,
    }
}

fn assert_lossless_topology(
    case_id: &str,
    result: &EnglishUnresolvedDeterminerPhraseTopologyEvidenceResult,
) {
    let accepted = &result.opaque_head_candidate_result;
    let missing = accepted
        .noun_phrase_result
        .diagnostics
        .iter()
        .filter(|diagnostic| {
            diagnostic.kind
                == inku_ddl::NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate
        })
        .collect::<Vec<_>>();
    assert_eq!(result.topology.len(), missing.len(), "{case_id}");

    let mut node_identities = HashSet::new();
    for (node, diagnostic) in result.topology.iter().zip(missing) {
        assert_eq!(node.clause_index, diagnostic.clause_index, "{case_id}");
        assert_eq!(
            node.determiner_span, diagnostic.determiner_span,
            "{case_id}"
        );
        assert_eq!(
            node.candidate_region_span, diagnostic.candidate_region_span,
            "{case_id}"
        );
        assert!(
            node_identities.insert((
                node.clause_index,
                node.determiner_span.start_byte,
                node.determiner_span.end_byte,
            )),
            "{case_id}: duplicate topology node"
        );

        let clause = &accepted.noun_phrase_result.clause_stream.clauses[node.clause_index];
        let expected_membership = clause
            .atoms
            .iter()
            .enumerate()
            .filter(|(_, atom)| {
                let span = atom.span();
                span.start_byte >= node.determiner_span.end_byte
                    && span.end_byte <= node.candidate_region_span.end_byte
            })
            .map(|(atom_index, _)| atom_index)
            .collect::<Vec<_>>();
        assert_eq!(
            node.candidate_region_atom_indices, expected_membership,
            "{case_id}: region membership must be complete and source ordered"
        );
        assert!(
            node.candidate_region_atom_indices
                .windows(2)
                .all(|pair| pair[0] < pair[1]),
            "{case_id}: duplicate or reordered atom membership"
        );

        let expected_candidates = opaque_candidate_indices(accepted, node);
        let mut run_candidates = Vec::new();
        let mut previous_end = None;
        for run in &node.opaque_candidate_runs {
            assert!(
                run.clause_atom_range.start < run.clause_atom_range.end,
                "{case_id}: empty candidate run"
            );
            assert_eq!(
                run.candidate_count,
                run.clause_atom_range.end - run.clause_atom_range.start,
                "{case_id}: candidate count/range mismatch"
            );
            if let Some(end) = previous_end {
                assert!(end < run.clause_atom_range.start, "{case_id}: run overlap");
            }
            for atom_index in run.clause_atom_range.clone() {
                assert!(
                    node.candidate_region_atom_indices.contains(&atom_index),
                    "{case_id}: candidate run outside region"
                );
                assert!(
                    is_opaque_candidate(&clause.atoms[atom_index]),
                    "{case_id}: non-candidate inside run"
                );
                run_candidates.push(atom_index);
            }
            previous_end = Some(run.clause_atom_range.end);
        }
        assert_eq!(
            run_candidates, expected_candidates,
            "{case_id}: candidates must appear exactly once in source-ordered runs"
        );
        assert_eq!(
            accepted_candidate_count(accepted, node),
            run_candidates.len(),
            "{case_id}: topology candidates must match the owned I-572 outcome"
        );
        match run_candidates.len() {
            0 => assert!(node.opaque_candidate_runs.is_empty(), "{case_id}"),
            1 => assert_eq!(node.opaque_candidate_runs.len(), 1, "{case_id}"),
            _ => assert!(!node.opaque_candidate_runs.is_empty(), "{case_id}"),
        }
    }
}

fn accepted_candidate_count(
    accepted: &EnglishOpaqueHeadCandidateEvidenceResult,
    node: &inku_ddl::UnresolvedDeterminerPhraseTopologyEvidence,
) -> usize {
    accepted
        .evidence
        .iter()
        .find(|candidate| {
            candidate.clause_index == node.clause_index
                && candidate.determiner_span == node.determiner_span
        })
        .map(|_| 1)
        .or_else(|| {
            accepted
                .diagnostics
                .iter()
                .find(|diagnostic| {
                    diagnostic.clause_index == node.clause_index
                        && diagnostic.determiner_span == node.determiner_span
                })
                .map(|diagnostic| diagnostic.candidates.len())
        })
        .expect("every topology node must retain one I-572 outcome")
}

fn opaque_candidate_indices(
    accepted: &EnglishOpaqueHeadCandidateEvidenceResult,
    node: &inku_ddl::UnresolvedDeterminerPhraseTopologyEvidence,
) -> Vec<usize> {
    let clause = &accepted.noun_phrase_result.clause_stream.clauses[node.clause_index];
    node.candidate_region_atom_indices
        .iter()
        .copied()
        .filter(|atom_index| is_opaque_candidate(&clause.atoms[*atom_index]))
        .collect()
}

fn is_opaque_candidate(atom: &ClauseAtom) -> bool {
    matches!(
        atom,
        ClauseAtom::UnresolvedDiagnostic(diagnostic)
            if diagnostic.kind == NeutralDiagnosticKind::Unknown && !diagnostic.recognized
    )
}
