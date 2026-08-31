use std::collections::HashSet;

use inku_ddl::{
    ClauseAtom, EnglishDeterminerKind, EnglishNounPhraseCandidateEvidence,
    NOUN_PHRASE_EVIDENCE_SCHEMA_ID, NormalizedDdlDocument, NounPhraseEvidenceDiagnosticKind,
    ResolvedInstructionLanguage, SourceSpan, collect_english_noun_phrase_evidence,
    parse_clause_stream,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/noun-phrase-evidence-v1.json");

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
    expected_evidence: Vec<ExpectedEvidence>,
    delivery_conservation_count: usize,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedEvidence {
    clause_index: usize,
    clause_span: ExpectedSpan,
    determiner: ExpectedDeterminer,
    candidate_region: ExpectedSlice,
    head_candidate: Option<ExpectedHeadCandidate>,
    opaque_pre_head: Option<ExpectedSlice>,
    diagnostic: Option<ExpectedDiagnostic>,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedDeterminer {
    kind: String,
    surface: String,
    span: ExpectedSpan,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedHeadCandidate {
    surface: String,
    asset_id: String,
    category_key: String,
    canonical_surface_ja: String,
    span: ExpectedSpan,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedDiagnostic {
    kind: String,
    candidate_spans: Vec<ExpectedSpan>,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedSlice {
    surface: String,
    start_byte: usize,
    end_byte: usize,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedSpan {
    start_byte: usize,
    end_byte: usize,
}

#[test]
fn fixture_preserves_owned_clause_stream_regions_candidates_and_source_slices() {
    let fixture = load_fixture();
    for case in fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source.clone(),
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap_or_else(|error| panic!("{}: unexpected document diagnostic: {error}", case.id));
        let before = document.source().as_bytes().to_vec();
        let accepted_stream = parse_clause_stream(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected clause-stream error: {error}", case.id));

        let result = collect_english_noun_phrase_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected noun-phrase error: {error}", case.id));

        assert_eq!(document.source().as_bytes(), before, "{}", case.id);
        assert_eq!(
            result.clause_stream, accepted_stream,
            "{}: result must own the unchanged accepted ClauseStream",
            case.id
        );
        assert_eq!(
            result.clause_stream.delivery_conservation_count, case.delivery_conservation_count,
            "{}",
            case.id
        );
        assert_eq!(
            result
                .evidence
                .iter()
                .map(|evidence| project_evidence(evidence, &result.diagnostics, &case.source))
                .collect::<Vec<_>>(),
            case.expected_evidence,
            "{}",
            case.id
        );
    }
}

#[test]
fn each_accepted_ascii_case_insensitive_determiner_has_one_evidence_overlay() {
    let fixture = load_fixture();
    for case in fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source,
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap();
        let result = collect_english_noun_phrase_evidence(&document).unwrap();
        let expected_determiners = result
            .clause_stream
            .clauses
            .iter()
            .flat_map(|clause| clause.atoms.iter())
            .filter(|atom| accepted_english_determiner(atom, &document))
            .count();

        assert_eq!(result.evidence.len(), expected_determiners, "{}", case.id);
        let identities = result
            .evidence
            .iter()
            .map(|evidence| {
                (
                    evidence.clause_index,
                    evidence.determiner.span.start_byte,
                    evidence.determiner.span.end_byte,
                )
            })
            .collect::<HashSet<_>>();
        assert_eq!(identities.len(), result.evidence.len(), "{}", case.id);
        assert_eq!(
            result.diagnostics.len(),
            result
                .evidence
                .iter()
                .filter(|evidence| evidence.head_candidate.is_none())
                .count(),
            "{}",
            case.id
        );
    }
}

#[test]
fn candidate_regions_are_clause_contained_ordered_and_non_overlapping() {
    let fixture = load_fixture();
    for case in fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source,
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap();
        let result = collect_english_noun_phrase_evidence(&document).unwrap();

        for evidence in &result.evidence {
            assert_span(&case.id, document.source(), evidence.clause_span);
            assert_span(&case.id, document.source(), evidence.candidate_region_span);
            assert!(
                evidence.clause_span.start_byte <= evidence.candidate_region_span.start_byte
                    && evidence.candidate_region_span.end_byte <= evidence.clause_span.end_byte,
                "{}",
                case.id
            );
            assert_eq!(
                result.clause_stream.clauses[evidence.clause_index].span, evidence.clause_span,
                "{}: clause identity must name the owning accepted clause",
                case.id
            );
            assert_eq!(
                evidence.candidate_region_span.start_byte, evidence.determiner.span.start_byte,
                "{}",
                case.id
            );
            if let Some(head) = &evidence.head_candidate {
                assert!(
                    evidence.determiner.span.end_byte <= head.span.start_byte
                        && head.span.end_byte <= evidence.candidate_region_span.end_byte,
                    "{}",
                    case.id
                );
                match evidence.opaque_pre_head_span {
                    Some(span) => {
                        assert_eq!(span.start_byte, evidence.determiner.span.end_byte);
                        assert_eq!(span.end_byte, head.span.start_byte);
                        assert!(span.start_byte < span.end_byte);
                    }
                    None => assert_eq!(evidence.determiner.span.end_byte, head.span.start_byte),
                }
            } else {
                assert!(evidence.opaque_pre_head_span.is_none());
            }
        }
        for clause_index in 0..result.clause_stream.clauses.len() {
            let regions = result
                .evidence
                .iter()
                .filter(|evidence| evidence.clause_index == clause_index)
                .map(|evidence| evidence.candidate_region_span)
                .collect::<Vec<_>>();
            assert!(
                regions
                    .windows(2)
                    .all(|pair| pair[0].end_byte <= pair[1].start_byte),
                "{}",
                case.id
            );
        }
    }
}

#[test]
fn zero_and_multiple_primitives_never_select_a_head() {
    let fixture = load_fixture();
    for case_id in ["zero-candidate-clause-boundary", "multiple-candidates"] {
        let case = fixture
            .cases
            .iter()
            .find(|case| case.id == case_id)
            .unwrap();
        let document = NormalizedDdlDocument::new(
            case.source.clone(),
            parse_language(&case.language, case_id),
            Vec::new(),
        )
        .unwrap();
        let result = collect_english_noun_phrase_evidence(&document).unwrap();

        assert_eq!(result.evidence.len(), 1, "{case_id}");
        assert!(result.evidence[0].head_candidate.is_none(), "{case_id}");
        assert!(
            result.evidence[0].opaque_pre_head_span.is_none(),
            "{case_id}"
        );
        assert_eq!(result.diagnostics.len(), 1, "{case_id}");
        match case_id {
            "zero-candidate-clause-boundary" => {
                assert_eq!(
                    result.diagnostics[0].kind,
                    NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate
                );
                assert!(result.diagnostics[0].candidates.is_empty());
            }
            "multiple-candidates" => {
                assert_eq!(
                    result.diagnostics[0].kind,
                    NounPhraseEvidenceDiagnosticKind::AmbiguousCanonicalHeadCandidates
                );
                assert_eq!(result.diagnostics[0].candidates.len(), 2);
            }
            _ => unreachable!(),
        }
    }
}

#[test]
fn fixture_schema_and_required_cases_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(
        NOUN_PHRASE_EVIDENCE_SCHEMA_ID,
        "inku.english-noun-phrase-evidence.v1"
    );
    assert_eq!(
        fixture.schema,
        "inku.english-noun-phrase-evidence-fixture.v1"
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
        "case-variants-opaque-utf8",
        "multiple-determiners",
        "zero-candidate-clause-boundary",
        "multiple-candidates",
        "typed-opaque-atoms",
        "multiple-clauses-line-endings",
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

fn parse_language(value: &str, case_id: &str) -> ResolvedInstructionLanguage {
    match value {
        "ja" => ResolvedInstructionLanguage::Ja,
        "en" => ResolvedInstructionLanguage::En,
        _ => panic!("{case_id}: invalid fixture language"),
    }
}

fn accepted_english_determiner(atom: &ClauseAtom, document: &NormalizedDdlDocument) -> bool {
    let ClauseAtom::FunctionWord { span, .. } = atom else {
        return false;
    };
    if document.language() != ResolvedInstructionLanguage::En {
        return false;
    }
    let surface = &document.source()[span.start_byte..span.end_byte];
    ["a", "an", "the"]
        .iter()
        .any(|candidate| surface.eq_ignore_ascii_case(candidate))
}

fn project_evidence(
    evidence: &EnglishNounPhraseCandidateEvidence,
    diagnostics: &[inku_ddl::NounPhraseEvidenceDiagnostic],
    source: &str,
) -> ExpectedEvidence {
    let determiner_surface =
        &source[evidence.determiner.span.start_byte..evidence.determiner.span.end_byte];
    assert_eq!(evidence.determiner.surface, determiner_surface);
    let diagnostic = diagnostics.iter().find(|diagnostic| {
        diagnostic.clause_index == evidence.clause_index
            && diagnostic.determiner_span == evidence.determiner.span
    });
    ExpectedEvidence {
        clause_index: evidence.clause_index,
        clause_span: project_span(evidence.clause_span),
        determiner: ExpectedDeterminer {
            kind: match evidence.determiner.kind {
                EnglishDeterminerKind::A => "a",
                EnglishDeterminerKind::An => "an",
                EnglishDeterminerKind::The => "the",
            }
            .to_owned(),
            surface: evidence.determiner.surface.clone(),
            span: project_span(evidence.determiner.span),
        },
        candidate_region: project_slice(source, evidence.candidate_region_span),
        head_candidate: evidence
            .head_candidate
            .as_ref()
            .map(|candidate| ExpectedHeadCandidate {
                surface: source[candidate.span.start_byte..candidate.span.end_byte].to_owned(),
                asset_id: candidate.asset_id.clone(),
                category_key: candidate.category_key.clone(),
                canonical_surface_ja: candidate.canonical_surface_ja.clone(),
                span: project_span(candidate.span),
            }),
        opaque_pre_head: evidence
            .opaque_pre_head_span
            .map(|span| project_slice(source, span)),
        diagnostic: diagnostic.map(|diagnostic| ExpectedDiagnostic {
            kind: match diagnostic.kind {
                NounPhraseEvidenceDiagnosticKind::MissingCanonicalHeadCandidate => {
                    "missing_canonical_head_candidate"
                }
                NounPhraseEvidenceDiagnosticKind::AmbiguousCanonicalHeadCandidates => {
                    "ambiguous_canonical_head_candidates"
                }
            }
            .to_owned(),
            candidate_spans: diagnostic
                .candidates
                .iter()
                .map(|candidate| project_span(candidate.span))
                .collect(),
        }),
    }
}

fn project_slice(source: &str, span: SourceSpan) -> ExpectedSlice {
    ExpectedSlice {
        surface: source[span.start_byte..span.end_byte].to_owned(),
        start_byte: span.start_byte,
        end_byte: span.end_byte,
    }
}

const fn project_span(span: SourceSpan) -> ExpectedSpan {
    ExpectedSpan {
        start_byte: span.start_byte,
        end_byte: span.end_byte,
    }
}

fn assert_span(case_id: &str, source: &str, span: SourceSpan) {
    assert!(span.start_byte <= span.end_byte, "{case_id}: reversed span");
    assert!(
        span.end_byte <= source.len(),
        "{case_id}: span outside source"
    );
    assert!(
        source.is_char_boundary(span.start_byte) && source.is_char_boundary(span.end_byte),
        "{case_id}: span is not on UTF-8 boundaries"
    );
}
