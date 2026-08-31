use std::collections::HashSet;

use inku_ddl::{
    ClauseAtom, DETERMINER_PHRASE_EVIDENCE_SCHEMA_ID, DeterminerPhraseEvidenceAvailability,
    EnglishDeterminerPhraseEvidenceResult, NeutralDiagnosticKind, NormalizedDdlDocument,
    NounPhraseEvidenceDiagnosticKind, ResolvedInstructionLanguage, SourceSpan,
    collect_english_determiner_phrase_evidence,
    collect_english_unresolved_determiner_phrase_topology_evidence,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/determiner-phrase-evidence-v1.json");

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
    canonical_candidate_spans: Vec<ExpectedSpan>,
    opaque_candidate_runs: Vec<ExpectedRun>,
    availability: String,
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
fn fixture_builds_one_lossless_general_node_per_owned_region() {
    for case in load_fixture().cases {
        let document = document_for(&case);
        let source_before = document.source().as_bytes().to_vec();
        let accepted = collect_english_unresolved_determiner_phrase_topology_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected I-576 error: {error}", case.id));
        let result = collect_english_determiner_phrase_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected phrase error: {error}", case.id));

        assert_eq!(document.source().as_bytes(), source_before, "{}", case.id);
        assert_eq!(
            result.unresolved_phrase_topology_result, accepted,
            "{}: the accepted I-576 result must be owned unchanged",
            case.id
        );
        assert_eq!(
            result
                .unresolved_phrase_topology_result
                .opaque_head_candidate_result
                .noun_phrase_result
                .clause_stream
                .delivery_conservation_count,
            case.delivery_conservation_count,
            "{}",
            case.id
        );
        assert_eq!(project_nodes(&result), case.expected_nodes, "{}", case.id);
        assert_lossless_envelope(&case.id, &result);
    }
}

#[test]
fn schema_fixture_and_required_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(
        DETERMINER_PHRASE_EVIDENCE_SCHEMA_ID,
        "inku.english-determiner-phrase-evidence.v1"
    );
    assert_eq!(
        fixture.schema,
        "inku.english-determiner-phrase-evidence-fixture.v1"
    );
    assert_eq!(fixture.version, 1);
    assert_eq!(fixture.cases.len(), 9);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "missing-zero-opaque-run",
        "missing-one-opaque-run",
        "missing-multiple-opaque-runs",
        "canonical-exact-one-opaque-before-after",
        "synthetic-canonical-multiple",
        "known-atom-interleaving",
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

fn project_nodes(result: &EnglishDeterminerPhraseEvidenceResult) -> Vec<ExpectedNode> {
    result
        .evidence
        .iter()
        .map(|node| ExpectedNode {
            clause_index: node.clause_index,
            determiner_span: project_span(node.determiner_span),
            candidate_region_span: project_span(node.candidate_region_span),
            candidate_region_atom_indices: node.candidate_region_atom_indices.clone(),
            canonical_candidate_spans: node
                .canonical_candidate_spans
                .iter()
                .copied()
                .map(project_span)
                .collect(),
            opaque_candidate_runs: node
                .opaque_candidate_runs
                .iter()
                .map(|run| ExpectedRun {
                    start_atom_index: run.clause_atom_range.start,
                    end_atom_index: run.clause_atom_range.end,
                    candidate_count: run.candidate_count,
                })
                .collect(),
            availability: match node.availability {
                DeterminerPhraseEvidenceAvailability::Missing => "missing",
                DeterminerPhraseEvidenceAvailability::ExactOne => "exact_one",
                DeterminerPhraseEvidenceAvailability::Multiple => "multiple",
            }
            .to_owned(),
        })
        .collect()
}

const fn project_span(span: SourceSpan) -> ExpectedSpan {
    ExpectedSpan {
        start_byte: span.start_byte,
        end_byte: span.end_byte,
    }
}

fn assert_lossless_envelope(case_id: &str, result: &EnglishDeterminerPhraseEvidenceResult) {
    let accepted = &result.unresolved_phrase_topology_result;
    let noun_phrase_result = &accepted.opaque_head_candidate_result.noun_phrase_result;
    assert_eq!(
        result.evidence.len(),
        noun_phrase_result.evidence.len(),
        "{case_id}"
    );

    let mut node_identities = HashSet::new();
    let mut region_atom_memberships = HashSet::new();
    let mut matched_diagnostics = HashSet::new();
    let mut missing_topology = accepted.topology.iter();

    for (node, region) in result.evidence.iter().zip(&noun_phrase_result.evidence) {
        assert_eq!(node.clause_index, region.clause_index, "{case_id}");
        assert_eq!(node.determiner_span, region.determiner.span, "{case_id}");
        assert_eq!(
            node.candidate_region_span, region.candidate_region_span,
            "{case_id}"
        );
        assert!(
            node_identities.insert((
                node.clause_index,
                node.determiner_span.start_byte,
                node.determiner_span.end_byte,
            )),
            "{case_id}: duplicate general node"
        );

        let clause = &noun_phrase_result.clause_stream.clauses[node.clause_index];
        let expected_membership = clause
            .atoms
            .iter()
            .enumerate()
            .filter(|(_, atom)| atom_in_region(atom, node))
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
        for &atom_index in &node.candidate_region_atom_indices {
            assert!(
                region_atom_memberships.insert((node.clause_index, atom_index)),
                "{case_id}: overlapping region membership"
            );
        }

        let matching_diagnostics = noun_phrase_result
            .diagnostics
            .iter()
            .enumerate()
            .filter(|(_, diagnostic)| {
                diagnostic.clause_index == node.clause_index
                    && diagnostic.determiner_span == node.determiner_span
                    && diagnostic.candidate_region_span == node.candidate_region_span
            })
            .collect::<Vec<_>>();
        let (expected_availability, expected_candidate_spans) =
            if let Some(candidate) = &region.head_candidate {
                assert!(matching_diagnostics.is_empty(), "{case_id}");
                (
                    DeterminerPhraseEvidenceAvailability::ExactOne,
                    vec![candidate.span],
                )
            } else {
                assert_eq!(matching_diagnostics.len(), 1, "{case_id}");
                let (diagnostic_index, diagnostic) = matching_diagnostics[0];
                assert!(matched_diagnostics.insert(diagnostic_index), "{case_id}");
                (
                    match diagnostic.kind {
                        NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate => {
                            DeterminerPhraseEvidenceAvailability::Missing
                        }
                        NounPhraseEvidenceDiagnosticKind::AmbiguousCanonicalHeadCandidates => {
                            DeterminerPhraseEvidenceAvailability::Multiple
                        }
                    },
                    diagnostic
                        .candidates
                        .iter()
                        .map(|candidate| candidate.span)
                        .collect(),
                )
            };
        assert_eq!(node.availability, expected_availability, "{case_id}");
        assert_eq!(
            node.canonical_candidate_spans, expected_candidate_spans,
            "{case_id}"
        );
        assert!(
            node.canonical_candidate_spans
                .windows(2)
                .all(|pair| pair[0].end_byte <= pair[1].start_byte),
            "{case_id}: canonical candidates must be source ordered and non-overlapping"
        );

        let expected_opaque_indices = node
            .candidate_region_atom_indices
            .iter()
            .copied()
            .filter(|atom_index| is_opaque_candidate(&clause.atoms[*atom_index]))
            .collect::<Vec<_>>();
        let mut run_indices = Vec::new();
        let mut previous_end = None;
        for run in &node.opaque_candidate_runs {
            assert!(
                run.clause_atom_range.start < run.clause_atom_range.end,
                "{case_id}: empty opaque run"
            );
            assert_eq!(
                run.candidate_count,
                run.clause_atom_range.end - run.clause_atom_range.start,
                "{case_id}: opaque run count mismatch"
            );
            if let Some(end) = previous_end {
                assert!(end < run.clause_atom_range.start, "{case_id}: run overlap");
            }
            run_indices.extend(run.clause_atom_range.clone());
            previous_end = Some(run.clause_atom_range.end);
        }
        assert_eq!(run_indices, expected_opaque_indices, "{case_id}");

        if node.availability == DeterminerPhraseEvidenceAvailability::Missing {
            let topology = missing_topology.next().expect("missing topology parity");
            assert_eq!(node.clause_index, topology.clause_index, "{case_id}");
            assert_eq!(node.determiner_span, topology.determiner_span, "{case_id}");
            assert_eq!(
                node.candidate_region_span, topology.candidate_region_span,
                "{case_id}"
            );
            assert_eq!(
                node.candidate_region_atom_indices, topology.candidate_region_atom_indices,
                "{case_id}"
            );
            assert_eq!(
                project_runs(&node.opaque_candidate_runs),
                project_runs(&topology.opaque_candidate_runs),
                "{case_id}"
            );
        }
    }

    assert_eq!(
        matched_diagnostics.len(),
        noun_phrase_result.diagnostics.len(),
        "{case_id}: orphan diagnostic"
    );
    assert!(missing_topology.next().is_none(), "{case_id}");
}

fn atom_in_region(atom: &ClauseAtom, node: &inku_ddl::EnglishDeterminerPhraseEvidence) -> bool {
    let span = atom.span();
    span.start_byte >= node.determiner_span.end_byte
        && span.end_byte <= node.candidate_region_span.end_byte
}

fn is_opaque_candidate(atom: &ClauseAtom) -> bool {
    matches!(
        atom,
        ClauseAtom::UnresolvedDiagnostic(diagnostic)
            if diagnostic.kind == NeutralDiagnosticKind::Unknown && !diagnostic.recognized
    )
}

fn project_runs<T>(runs: &[T]) -> Vec<(usize, usize, usize)>
where
    T: RunProjection,
{
    runs.iter().map(RunProjection::project).collect()
}

trait RunProjection {
    fn project(&self) -> (usize, usize, usize);
}

impl RunProjection for inku_ddl::DeterminerPhraseOpaqueCandidateRun {
    fn project(&self) -> (usize, usize, usize) {
        (
            self.clause_atom_range.start,
            self.clause_atom_range.end,
            self.candidate_count,
        )
    }
}

impl RunProjection for inku_ddl::UnresolvedDeterminerPhraseOpaqueCandidateRun {
    fn project(&self) -> (usize, usize, usize) {
        (
            self.clause_atom_range.start,
            self.clause_atom_range.end,
            self.candidate_count,
        )
    }
}
