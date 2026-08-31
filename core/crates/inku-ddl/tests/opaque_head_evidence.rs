use std::collections::HashSet;

use inku_ddl::{
    ClauseAtom, EnglishOpaqueHeadCandidateEvidenceResult, NOUN_PHRASE_EVIDENCE_SCHEMA_ID,
    NeutralDiagnosticKind, NormalizedDdlDocument, OPAQUE_HEAD_CANDIDATE_EVIDENCE_SCHEMA_ID,
    OpaqueHeadCandidateEvidence, OpaqueHeadCandidateEvidenceDiagnosticKind,
    ResolvedInstructionLanguage, SourceSpan, collect_english_noun_phrase_evidence,
    collect_english_opaque_head_candidate_evidence,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/opaque-head-evidence-v1.json");

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
    expected_outcomes: Vec<ExpectedOutcome>,
    noun_phrase_evidence_count: usize,
    noun_phrase_diagnostic_count: usize,
    separator_count: usize,
    delivery_conservation_count: usize,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedOutcome {
    kind: String,
    clause_index: usize,
    determiner_span: ExpectedSpan,
    candidate_region_span: ExpectedSpan,
    candidates: Vec<ExpectedCandidate>,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedCandidate {
    surface: String,
    span: ExpectedSpan,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedSpan {
    start_byte: usize,
    end_byte: usize,
}

#[test]
fn fixture_classifies_each_missing_canonical_region_exactly_once() {
    let fixture = load_fixture();
    for case in fixture.cases {
        let document = document_for(&case);
        let source_before = document.source().as_bytes().to_vec();
        let accepted = collect_english_noun_phrase_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected noun-phrase error: {error}", case.id));

        let result = collect_english_opaque_head_candidate_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected opaque-head error: {error}", case.id));

        assert_eq!(document.source().as_bytes(), source_before, "{}", case.id);
        assert_eq!(
            result.noun_phrase_result, accepted,
            "{}: the accepted I-568 result must be owned unchanged",
            case.id
        );
        assert_eq!(
            result.noun_phrase_result.evidence.len(),
            case.noun_phrase_evidence_count,
            "{}",
            case.id
        );
        assert_eq!(
            result.noun_phrase_result.diagnostics.len(),
            case.noun_phrase_diagnostic_count,
            "{}",
            case.id
        );
        assert_eq!(
            result.noun_phrase_result.clause_stream.separators.len(),
            case.separator_count,
            "{}",
            case.id
        );
        assert_eq!(
            result
                .noun_phrase_result
                .clause_stream
                .delivery_conservation_count,
            case.delivery_conservation_count,
            "{}",
            case.id
        );
        assert_eq!(
            project_outcomes(&result),
            case.expected_outcomes,
            "{}",
            case.id
        );

        let missing_count = result
            .noun_phrase_result
            .diagnostics
            .iter()
            .filter(|diagnostic| {
                diagnostic.kind
                    == inku_ddl::NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate
            })
            .count();
        assert_eq!(
            result.evidence.len() + result.diagnostics.len(),
            missing_count,
            "{}: every missing-canonical region must have exactly one outcome",
            case.id
        );
        assert_candidates_are_source_diagnostics(&case.id, &case.source, &result);
    }
}

#[test]
fn typed_deliveries_holes_numbers_and_function_words_are_not_candidates() {
    let fixture = load_fixture();
    let case = fixture
        .cases
        .iter()
        .find(|case| case.id == "typed-and-recognized-exclusions")
        .unwrap();
    let result = collect_english_opaque_head_candidate_evidence(&document_for(case)).unwrap();
    let atoms = &result.noun_phrase_result.clause_stream.clauses[0].atoms;

    assert!(result.evidence.is_empty());
    assert_eq!(result.diagnostics.len(), 1);
    assert!(result.diagnostics[0].candidates.is_empty());
    assert!(
        atoms
            .iter()
            .any(|atom| matches!(atom, ClauseAtom::CoreRole(_)))
    );
    assert!(
        atoms
            .iter()
            .any(|atom| matches!(atom, ClauseAtom::RemainingRole(_)))
    );
    assert!(
        atoms
            .iter()
            .any(|atom| matches!(atom, ClauseAtom::UnattachedExactNumber(_)))
    );
    assert!(atoms.iter().any(|atom| matches!(
        atom,
        ClauseAtom::FunctionWord { surface, .. } if surface == "with"
    )));
    assert!(atoms.iter().any(|atom| matches!(
        atom,
        ClauseAtom::SaijikiRelation { surface, .. } if surface == "not touching"
    )));
    assert!(atoms.iter().any(|atom| matches!(
        atom,
        ClauseAtom::UnresolvedDiagnostic(diagnostic)
            if diagnostic.kind == NeutralDiagnosticKind::Hole && diagnostic.recognized
    )));
}

#[test]
fn canonical_and_ambiguous_canonical_heads_never_receive_an_opaque_overlay() {
    let fixture = load_fixture();
    for case_id in ["canonical-exact-one", "canonical-ambiguous"] {
        let case = fixture
            .cases
            .iter()
            .find(|case| case.id == case_id)
            .unwrap();
        let result = collect_english_opaque_head_candidate_evidence(&document_for(case)).unwrap();

        assert!(result.evidence.is_empty(), "{case_id}");
        assert!(result.diagnostics.is_empty(), "{case_id}");
    }
}

#[test]
fn schema_fixture_and_required_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(
        OPAQUE_HEAD_CANDIDATE_EVIDENCE_SCHEMA_ID,
        "inku.english-opaque-head-candidate-evidence.v1"
    );
    assert_eq!(
        NOUN_PHRASE_EVIDENCE_SCHEMA_ID,
        "inku.english-noun-phrase-evidence.v1"
    );
    assert_eq!(
        fixture.schema,
        "inku.english-opaque-head-candidate-evidence-fixture.v1"
    );
    assert_eq!(fixture.version, 1);
    assert_eq!(fixture.cases.len(), 8);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "typed-and-recognized-exclusions",
        "exact-one-utf8",
        "multiple-opaque",
        "canonical-exact-one",
        "canonical-ambiguous",
        "multiple-determiners-clauses-and-separators",
        "ja-input",
        "en-no-determiner",
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

fn project_outcomes(result: &EnglishOpaqueHeadCandidateEvidenceResult) -> Vec<ExpectedOutcome> {
    let mut outcomes = result
        .evidence
        .iter()
        .map(|candidate| ExpectedOutcome {
            kind: "exact_one".to_owned(),
            clause_index: candidate.clause_index,
            determiner_span: project_span(candidate.determiner_span),
            candidate_region_span: project_span(candidate.candidate_region_span),
            candidates: vec![project_candidate(candidate)],
        })
        .chain(result.diagnostics.iter().map(|diagnostic| {
            ExpectedOutcome {
                kind: match diagnostic.kind {
                    OpaqueHeadCandidateEvidenceDiagnosticKind::MissingOpaqueHeadCandidate => {
                        "missing"
                    }
                    OpaqueHeadCandidateEvidenceDiagnosticKind::AmbiguousOpaqueHeadCandidates => {
                        "ambiguous"
                    }
                }
                .to_owned(),
                clause_index: diagnostic.clause_index,
                determiner_span: project_span(diagnostic.determiner_span),
                candidate_region_span: project_span(diagnostic.candidate_region_span),
                candidates: diagnostic
                    .candidates
                    .iter()
                    .map(project_candidate)
                    .collect(),
            }
        }))
        .collect::<Vec<_>>();
    outcomes.sort_by_key(|outcome| {
        (
            outcome.clause_index,
            outcome.determiner_span.start_byte,
            outcome.determiner_span.end_byte,
        )
    });
    outcomes
}

fn project_candidate(candidate: &OpaqueHeadCandidateEvidence) -> ExpectedCandidate {
    ExpectedCandidate {
        surface: candidate.surface.clone(),
        span: project_span(candidate.span),
    }
}

const fn project_span(span: SourceSpan) -> ExpectedSpan {
    ExpectedSpan {
        start_byte: span.start_byte,
        end_byte: span.end_byte,
    }
}

fn assert_candidates_are_source_diagnostics(
    case_id: &str,
    source: &str,
    result: &EnglishOpaqueHeadCandidateEvidenceResult,
) {
    let candidates = result.evidence.iter().chain(
        result
            .diagnostics
            .iter()
            .flat_map(|diagnostic| diagnostic.candidates.iter()),
    );
    let mut identities = HashSet::new();
    for candidate in candidates {
        assert!(
            source.is_char_boundary(candidate.span.start_byte),
            "{case_id}"
        );
        assert!(
            source.is_char_boundary(candidate.span.end_byte),
            "{case_id}"
        );
        assert_eq!(
            &source[candidate.span.start_byte..candidate.span.end_byte],
            candidate.surface,
            "{case_id}"
        );
        assert!(
            candidate.determiner_span.end_byte <= candidate.span.start_byte
                && candidate.span.end_byte <= candidate.candidate_region_span.end_byte,
            "{case_id}"
        );
        assert!(
            identities.insert((
                candidate.clause_index,
                candidate.span.start_byte,
                candidate.span.end_byte,
            )),
            "{case_id}"
        );
        assert!(
            result.noun_phrase_result.clause_stream.clauses[candidate.clause_index]
                .atoms
                .iter()
                .any(|atom| matches!(
                    atom,
                    ClauseAtom::UnresolvedDiagnostic(diagnostic)
                        if diagnostic.kind == NeutralDiagnosticKind::Unknown
                            && !diagnostic.recognized
                            && diagnostic.span == candidate.span
                            && diagnostic.surface == candidate.surface
                )),
            "{case_id}"
        );
    }
}
