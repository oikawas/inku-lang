use std::collections::HashSet;

use inku_ddl::{
    ATTACHMENT_EVIDENCE_SCHEMA_ID, AttachmentEvidenceDiagnosticKind, AttachmentMarkerKind,
    ClauseAtom, CoordinationMarkerKind, EnglishAttachmentMarkerKind, JapaneseAttachmentMarkerKind,
    NormalizedDdlDocument, ResolvedInstructionLanguage, SourceSpan, collect_attachment_evidence,
    collect_english_noun_phrase_evidence,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/attachment-evidence-v2.json");

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
    expected_markers: Vec<ExpectedMarker>,
    expected_missing: Vec<ExpectedMissing>,
    expected_links: Vec<ExpectedLinks>,
    expected_details: Vec<ExpectedDetail>,
    noun_phrase_evidence_count: usize,
    noun_phrase_diagnostic_count: usize,
    delivery_conservation_count: usize,
    #[serde(default)]
    coordination_evidence_count: Option<usize>,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedMarker {
    kind: String,
    surface: String,
    span: ExpectedSpan,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedMissing {
    evidence_index: usize,
    kinds: Vec<String>,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedLinks {
    evidence_index: usize,
    left_evidence: Vec<usize>,
    right_evidence: Vec<usize>,
    left_diagnostics: Vec<usize>,
    right_diagnostics: Vec<usize>,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedDetail {
    evidence_index: usize,
    clause_index: usize,
    clause_span: ExpectedSpan,
    left_context: Option<ExpectedSlice>,
    right_context: Option<ExpectedSlice>,
    left_atom_spans: Vec<ExpectedSpan>,
    right_atom_spans: Vec<ExpectedSpan>,
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
fn fixture_preserves_exact_markers_full_context_and_owned_i568_result() {
    for case in load_fixture().cases {
        let language = parse_language(&case.language, &case.id);
        let document = NormalizedDdlDocument::new(case.source.clone(), language, Vec::new())
            .unwrap_or_else(|error| panic!("{}: invalid document: {error}", case.id));
        let before = document.source().as_bytes().to_vec();
        let accepted = collect_english_noun_phrase_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: I-568 failed: {error}", case.id));

        let result = collect_attachment_evidence(&document)
            .unwrap_or_else(|error| panic!("{}: attachment evidence failed: {error}", case.id));

        assert_eq!(document.source().as_bytes(), before, "{}", case.id);
        assert_eq!(result.noun_phrase, accepted, "{}", case.id);
        assert_eq!(
            result.noun_phrase.clause_stream.delivery_conservation_count,
            case.delivery_conservation_count,
            "{}",
            case.id
        );
        assert_eq!(
            result.noun_phrase.evidence.len(),
            case.noun_phrase_evidence_count,
            "{}",
            case.id
        );
        assert_eq!(
            result.noun_phrase.diagnostics.len(),
            case.noun_phrase_diagnostic_count,
            "{}",
            case.id
        );
        if let Some(expected) = case.coordination_evidence_count {
            assert_eq!(result.coordination_evidence.len(), expected, "{}", case.id);
        }

        let markers = result
            .evidence
            .iter()
            .map(|evidence| ExpectedMarker {
                kind: marker_name(evidence.marker).to_owned(),
                surface: evidence.surface.clone(),
                span: project_span(evidence.span),
            })
            .collect::<Vec<_>>();
        assert_eq!(markers, case.expected_markers, "{}", case.id);

        let missing = result
            .evidence
            .iter()
            .enumerate()
            .filter_map(|(evidence_index, _)| {
                let kinds = result
                    .diagnostics
                    .iter()
                    .filter(|diagnostic| diagnostic.evidence_index == evidence_index)
                    .map(|diagnostic| diagnostic_name(diagnostic.kind).to_owned())
                    .collect::<Vec<_>>();
                (!kinds.is_empty()).then_some(ExpectedMissing {
                    evidence_index,
                    kinds,
                })
            })
            .collect::<Vec<_>>();
        assert_eq!(missing, case.expected_missing, "{}", case.id);

        let links = result
            .evidence
            .iter()
            .enumerate()
            .filter_map(|(evidence_index, evidence)| {
                let projected = ExpectedLinks {
                    evidence_index,
                    left_evidence: evidence.left_noun_phrase_evidence_indices.clone(),
                    right_evidence: evidence.right_noun_phrase_evidence_indices.clone(),
                    left_diagnostics: evidence.left_noun_phrase_diagnostic_indices.clone(),
                    right_diagnostics: evidence.right_noun_phrase_diagnostic_indices.clone(),
                };
                (language == ResolvedInstructionLanguage::En
                    && (!projected.left_evidence.is_empty()
                        || !projected.right_evidence.is_empty()
                        || !projected.left_diagnostics.is_empty()
                        || !projected.right_diagnostics.is_empty()))
                .then_some(projected)
            })
            .collect::<Vec<_>>();
        assert_eq!(links, case.expected_links, "{}", case.id);

        for expected in case.expected_details {
            let evidence = &result.evidence[expected.evidence_index];
            assert_eq!(evidence.clause_index, expected.clause_index, "{}", case.id);
            assert_eq!(
                project_span(evidence.clause_span),
                expected.clause_span,
                "{}",
                case.id
            );
            assert_eq!(
                evidence
                    .left_context_span
                    .map(|span| project_slice(&case.source, span)),
                expected.left_context,
                "{}",
                case.id
            );
            assert_eq!(
                evidence
                    .right_context_span
                    .map(|span| project_slice(&case.source, span)),
                expected.right_context,
                "{}",
                case.id
            );
            assert_eq!(
                evidence
                    .left_atom_spans
                    .iter()
                    .copied()
                    .map(project_span)
                    .collect::<Vec<_>>(),
                expected.left_atom_spans,
                "{}",
                case.id
            );
            assert_eq!(
                evidence
                    .right_atom_spans
                    .iter()
                    .copied()
                    .map(project_span)
                    .collect::<Vec<_>>(),
                expected.right_atom_spans,
                "{}",
                case.id
            );
        }
    }
}

#[test]
fn ja_en_coordination_function_words_project_one_typed_identity() {
    for (language, source, expected_surface) in [
        (ResolvedInstructionLanguage::Ja, "円と線", "と"),
        (ResolvedInstructionLanguage::En, "circle AND line", "AND"),
    ] {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        let result = collect_attachment_evidence(&document).unwrap();
        let [marker] = result.coordination_evidence.as_slice() else {
            panic!("{source}: expected exactly one coordination marker");
        };
        assert_eq!(marker.kind, CoordinationMarkerKind::HeadConjunction);
        assert_eq!(
            &source[marker.source.start_byte..marker.source.end_byte],
            expected_surface
        );
        assert_eq!(marker.clause_index, 0);
        assert!(!marker.left_atom_spans.is_empty());
        assert!(!marker.right_atom_spans.is_empty());
        let left = marker.left_atom_spans.last().copied().unwrap();
        let right = marker.right_atom_spans.first().copied().unwrap();
        assert_eq!(
            &source[left.start_byte..left.end_byte],
            if language == ResolvedInstructionLanguage::Ja {
                "円"
            } else {
                "circle"
            }
        );
        assert_eq!(
            &source[right.start_byte..right.end_byte],
            if language == ResolvedInstructionLanguage::Ja {
                "線"
            } else {
                "line"
            }
        );
    }
    for (language, source) in [
        (ResolvedInstructionLanguage::Ja, "円を線"),
        (ResolvedInstructionLanguage::En, "circle with line"),
    ] {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        assert!(
            collect_attachment_evidence(&document)
                .unwrap()
                .coordination_evidence
                .is_empty(),
            "{source}"
        );
    }
}

#[test]
fn every_marker_is_exactly_once_and_atoms_remain_a_source_ordered_partition() {
    for case in load_fixture().cases {
        let language = parse_language(&case.language, &case.id);
        let document =
            NormalizedDdlDocument::new(case.source.clone(), language, Vec::new()).unwrap();
        let result = collect_attachment_evidence(&document).unwrap();
        let source = case.source.as_str();
        let accepted_markers = result
            .noun_phrase
            .clause_stream
            .clauses
            .iter()
            .enumerate()
            .flat_map(|(clause_index, clause)| {
                clause.atoms.iter().filter_map(move |atom| {
                    accepted_marker(language, atom, source)
                        .map(|span| (clause_index, span.start_byte, span.end_byte))
                })
            })
            .collect::<Vec<_>>();
        let observed_markers = result
            .evidence
            .iter()
            .map(|evidence| {
                (
                    evidence.clause_index,
                    evidence.span.start_byte,
                    evidence.span.end_byte,
                )
            })
            .collect::<Vec<_>>();
        assert_eq!(observed_markers, accepted_markers, "{}", case.id);
        assert_eq!(
            observed_markers
                .iter()
                .copied()
                .collect::<HashSet<_>>()
                .len(),
            observed_markers.len(),
            "{}",
            case.id
        );

        for (evidence_index, evidence) in result.evidence.iter().enumerate() {
            let clause = &result.noun_phrase.clause_stream.clauses[evidence.clause_index];
            assert_eq!(evidence.language, language, "{}", case.id);
            assert_eq!(evidence.clause_span, clause.span, "{}", case.id);
            assert_span(&case.id, &case.source, evidence.span);
            assert_eq!(
                &case.source[evidence.span.start_byte..evidence.span.end_byte],
                evidence.surface,
                "{}",
                case.id
            );
            assert_eq!(
                evidence.left_context_span,
                (clause.span.start_byte < evidence.span.start_byte).then_some(SourceSpan {
                    start_byte: clause.span.start_byte,
                    end_byte: evidence.span.start_byte,
                }),
                "{}",
                case.id
            );
            assert_eq!(
                evidence.right_context_span,
                (evidence.span.end_byte < clause.span.end_byte).then_some(SourceSpan {
                    start_byte: evidence.span.end_byte,
                    end_byte: clause.span.end_byte,
                }),
                "{}",
                case.id
            );

            let expected_left = clause
                .atoms
                .iter()
                .filter(|atom| atom.span().end_byte <= evidence.span.start_byte)
                .map(ClauseAtom::span)
                .collect::<Vec<_>>();
            let expected_right = clause
                .atoms
                .iter()
                .filter(|atom| evidence.span.end_byte <= atom.span().start_byte)
                .map(ClauseAtom::span)
                .collect::<Vec<_>>();
            assert_eq!(evidence.left_atom_spans, expected_left, "{}", case.id);
            assert_eq!(evidence.right_atom_spans, expected_right, "{}", case.id);
            assert!(
                evidence
                    .left_atom_spans
                    .windows(2)
                    .all(|pair| pair[0].end_byte <= pair[1].start_byte)
            );
            assert!(
                evidence
                    .right_atom_spans
                    .windows(2)
                    .all(|pair| pair[0].end_byte <= pair[1].start_byte)
            );

            let missing_left = result.diagnostics.iter().any(|diagnostic| {
                diagnostic.evidence_index == evidence_index
                    && diagnostic.kind == AttachmentEvidenceDiagnosticKind::MissingLeftContext
            });
            let missing_right = result.diagnostics.iter().any(|diagnostic| {
                diagnostic.evidence_index == evidence_index
                    && diagnostic.kind == AttachmentEvidenceDiagnosticKind::MissingRightContext
            });
            assert_eq!(
                missing_left,
                evidence.left_atom_spans.is_empty(),
                "{}",
                case.id
            );
            assert_eq!(
                missing_right,
                evidence.right_atom_spans.is_empty(),
                "{}",
                case.id
            );

            if language == ResolvedInstructionLanguage::Ja {
                assert!(evidence.left_noun_phrase_evidence_indices.is_empty());
                assert!(evidence.right_noun_phrase_evidence_indices.is_empty());
                assert!(evidence.left_noun_phrase_diagnostic_indices.is_empty());
                assert!(evidence.right_noun_phrase_diagnostic_indices.is_empty());
            }
        }
    }
}

#[test]
fn fixture_schema_and_required_neutral_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(ATTACHMENT_EVIDENCE_SCHEMA_ID, "inku.attachment-evidence.v2");
    assert_eq!(fixture.schema, "inku.attachment-evidence-fixture.v2");
    assert_eq!(fixture.version, 2);
    assert_eq!(fixture.cases.len(), 8);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "ja-exact-eight",
        "en-exact-six-case-variants",
        "determiners-and-unclassified-and",
        "mixed-atoms-and-noun-phrase",
        "noun-phrase-diagnostic",
        "multiple-markers-and-determiners",
        "marker-boundaries-and-separators",
        "cross-clause-noun-phrase-exclusion",
    ] {
        assert!(ids.contains(required), "missing fixture case: {required}");
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

fn accepted_marker(
    language: ResolvedInstructionLanguage,
    atom: &ClauseAtom,
    source: &str,
) -> Option<SourceSpan> {
    let ClauseAtom::FunctionWord { span, .. } = atom else {
        return None;
    };
    let surface = &source[span.start_byte..span.end_byte];
    let recognized = match language {
        ResolvedInstructionLanguage::Ja => {
            ["を", "に", "で", "の", "は", "が", "へ", "と"].contains(&surface)
        }
        ResolvedInstructionLanguage::En => ["with", "in", "at", "on", "to", "of"]
            .iter()
            .any(|candidate| surface.eq_ignore_ascii_case(candidate)),
    };
    recognized.then_some(*span)
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

const fn diagnostic_name(kind: AttachmentEvidenceDiagnosticKind) -> &'static str {
    match kind {
        AttachmentEvidenceDiagnosticKind::MissingLeftContext => "missing_left_context",
        AttachmentEvidenceDiagnosticKind::MissingRightContext => "missing_right_context",
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
    assert!(span.start_byte < span.end_byte, "{case_id}: empty span");
    assert!(
        span.end_byte <= source.len(),
        "{case_id}: span outside source"
    );
    assert!(
        source.is_char_boundary(span.start_byte),
        "{case_id}: invalid start"
    );
    assert!(
        source.is_char_boundary(span.end_byte),
        "{case_id}: invalid end"
    );
}
