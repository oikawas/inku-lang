use std::collections::HashSet;

use inku_ddl::{
    CLAUSE_STREAM_SCHEMA_ID, ClauseAtom, ClauseSeparatorKind, ClauseStream, CoreRoleKind,
    NeutralDiagnosticKind, NormalizedDdlDocument, RemainingRoleKind, ResolvedInstructionLanguage,
    SourceSpan, parse_clause_stream,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/clause-stream-v1.json");

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
    expected_clauses: Vec<ExpectedClause>,
    expected_separators: Vec<ExpectedSeparator>,
    delivery_conservation_count: usize,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedClause {
    start_byte: usize,
    end_byte: usize,
    atoms: Vec<ExpectedAtom>,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedAtom {
    kind: String,
    surface: String,
    start_byte: usize,
    end_byte: usize,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedSeparator {
    kind: String,
    surface: String,
    start_byte: usize,
    end_byte: usize,
}

#[test]
fn fixture_preserves_source_order_clauses_separators_and_all_atom_kinds() {
    let fixture = load_fixture();
    let mut observed_atom_classes = HashSet::new();

    for case in fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source.clone(),
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap_or_else(|error| panic!("{}: unexpected document diagnostic: {error}", case.id));
        let stream = parse_clause_stream(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected clause-stream error: {error}", case.id));

        let projected_clauses = stream
            .clauses
            .iter()
            .map(|clause| {
                assert_span(&case.id, &case.source, clause.span);
                let atoms = clause
                    .atoms
                    .iter()
                    .map(|atom| {
                        let projected = project_atom(atom, &case.source);
                        observed_atom_classes
                            .insert(projected.kind.split(':').next().unwrap().to_owned());
                        assert!(
                            clause.span.start_byte <= projected.start_byte
                                && projected.end_byte <= clause.span.end_byte,
                            "{}: atom must have unique containing clause",
                            case.id
                        );
                        projected
                    })
                    .collect::<Vec<_>>();
                for pair in atoms.windows(2) {
                    assert!(
                        pair[0].end_byte <= pair[1].start_byte,
                        "{}: atoms overlap or are not in source order",
                        case.id
                    );
                }
                ExpectedClause {
                    start_byte: clause.span.start_byte,
                    end_byte: clause.span.end_byte,
                    atoms,
                }
            })
            .collect::<Vec<_>>();
        assert_eq!(projected_clauses, case.expected_clauses, "{}", case.id);

        let projected_separators = stream
            .separators
            .iter()
            .map(|separator| {
                assert_span(&case.id, &case.source, separator.span);
                ExpectedSeparator {
                    kind: match separator.kind {
                        ClauseSeparatorKind::LineBreak => "line_break",
                        ClauseSeparatorKind::SentenceEnd => "sentence_end",
                    }
                    .to_owned(),
                    surface: case.source[separator.span.start_byte..separator.span.end_byte]
                        .to_owned(),
                    start_byte: separator.span.start_byte,
                    end_byte: separator.span.end_byte,
                }
            })
            .collect::<Vec<_>>();
        assert_eq!(
            projected_separators, case.expected_separators,
            "{}",
            case.id
        );
        assert_eq!(
            stream.delivery_conservation_count, case.delivery_conservation_count,
            "{}",
            case.id
        );
        assert_eq!(
            stream
                .clauses
                .iter()
                .flat_map(|clause| &clause.atoms)
                .filter(|atom| contributes_to_delivery_count(atom))
                .count(),
            stream.delivery_conservation_count,
            "{}: every semantic delivery must occur exactly once",
            case.id
        );
    }

    assert_eq!(
        observed_atom_classes,
        [
            "core",
            "remaining",
            "exact_number",
            "function_word",
            "relation",
            "diagnostic",
        ]
        .into_iter()
        .map(str::to_owned)
        .collect()
    );
}

#[test]
fn atom_owned_punctuation_is_not_also_a_qualified_macro_separator() {
    let source = "namespace.heading!";
    let document =
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new()).unwrap();
    let Ok(stream) = parse_clause_stream(&document) else {
        panic!("qualified macro punctuation should be atom-owned");
    };

    assert_eq!(stream.clauses.len(), 1);
    assert_eq!(stream.clauses[0].atoms.len(), 1);
    assert!(matches!(
        &stream.clauses[0].atoms[0],
        ClauseAtom::UnresolvedDiagnostic(diagnostic)
            if diagnostic.kind == NeutralDiagnosticKind::Unknown && !diagnostic.recognized
    ));
    assert_eq!(stream.separators.len(), 1);
    assert_eq!(stream.separators[0].kind, ClauseSeparatorKind::SentenceEnd);
    assert_eq!(stream.delivery_conservation_count, 0);
    assert_stream_integrity(source, &stream);
}

#[test]
fn atom_owned_punctuation_is_not_also_an_unsupported_decimal_separator() {
    let source = "1.5.";
    let document =
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new()).unwrap();
    let Ok(stream) = parse_clause_stream(&document) else {
        panic!("unsupported decimal punctuation should be atom-owned");
    };

    assert_eq!(stream.clauses.len(), 1);
    assert_eq!(stream.clauses[0].atoms.len(), 1);
    assert!(matches!(
        &stream.clauses[0].atoms[0],
        ClauseAtom::UnresolvedDiagnostic(diagnostic)
            if diagnostic.kind == NeutralDiagnosticKind::Hole && diagnostic.recognized
    ));
    assert_eq!(stream.separators.len(), 1);
    assert_eq!(stream.separators[0].kind, ClauseSeparatorKind::SentenceEnd);
    assert_eq!(stream.delivery_conservation_count, 1);
    assert_stream_integrity(source, &stream);
}

#[test]
fn sentence_ends_and_lf_crlf_outside_atoms_remain_separators() {
    let source = "8。\n12!\r\n";
    let document =
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new()).unwrap();
    let Ok(stream) = parse_clause_stream(&document) else {
        panic!("ordinary sentence and line separators should remain valid");
    };

    assert_eq!(stream.clauses.len(), 2);
    assert_eq!(stream.separators.len(), 4);
    assert_eq!(
        stream
            .separators
            .iter()
            .filter(|separator| separator.kind == ClauseSeparatorKind::SentenceEnd)
            .count(),
        2
    );
    assert_eq!(
        stream
            .separators
            .iter()
            .filter(|separator| separator.kind == ClauseSeparatorKind::LineBreak)
            .count(),
        2
    );
    assert_eq!(stream.delivery_conservation_count, 2);
    assert_stream_integrity(source, &stream);
}

#[test]
fn sentence_end_without_atoms_remains_a_separator() {
    let source = ".";
    let document =
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new()).unwrap();
    let Ok(stream) = parse_clause_stream(&document) else {
        panic!("a standalone sentence end should remain valid");
    };

    assert!(stream.clauses.is_empty());
    assert_eq!(stream.separators.len(), 1);
    assert_eq!(stream.separators[0].kind, ClauseSeparatorKind::SentenceEnd);
    assert_eq!(stream.delivery_conservation_count, 0);
    assert_stream_integrity(source, &stream);
}

#[test]
fn fixture_schema_and_required_boundary_cases_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(CLAUSE_STREAM_SCHEMA_ID, "inku.clause-stream.v1");
    assert_eq!(fixture.schema, "inku.clause-stream-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(fixture.cases.len(), 5);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "ja-all-atom-kinds",
        "en-leading-trailing-mixed-line-endings",
        "en-all-sentence-endings",
        "en-punctuation-does-not-split",
        "separator-only",
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

fn project_atom(atom: &ClauseAtom, source: &str) -> ExpectedAtom {
    let span = atom.span();
    let kind = match atom {
        ClauseAtom::CoreRole(term) => format!(
            "core:{}",
            match term.role {
                CoreRoleKind::Primitive => "primitive",
                CoreRoleKind::Touch => "touch",
                CoreRoleKind::Color => "color",
                CoreRoleKind::Surface => "surface",
                CoreRoleKind::Ground => "ground",
            }
        ),
        ClauseAtom::RemainingRole(term) => format!(
            "remaining:{}",
            match term.role {
                RemainingRoleKind::Angle => "angle",
                RemainingRoleKind::Continuity => "continuity",
                RemainingRoleKind::Fluctuation => "fluctuation",
                RemainingRoleKind::Place => "place",
                RemainingRoleKind::Motion => "motion",
                RemainingRoleKind::Proportion => "proportion",
            }
        ),
        ClauseAtom::UnattachedExactNumber(number) => format!("exact_number:{}", number.value),
        ClauseAtom::FunctionWord { surface, .. } => {
            assert_eq!(surface, &source[span.start_byte..span.end_byte]);
            "function_word".to_owned()
        }
        ClauseAtom::SaijikiRelation {
            asset_id,
            surface,
            relation_type,
            ..
        } => {
            assert_eq!(asset_id, "inku.saijiki.v1");
            assert_eq!(surface, &source[span.start_byte..span.end_byte]);
            format!("relation:{relation_type}")
        }
        ClauseAtom::UnresolvedDiagnostic(diagnostic) => {
            assert_eq!(
                diagnostic.surface,
                source[diagnostic.span.start_byte..diagnostic.span.end_byte]
            );
            format!(
                "diagnostic:{}:{}",
                match diagnostic.kind {
                    NeutralDiagnosticKind::Hole => "hole",
                    NeutralDiagnosticKind::Conflict => "conflict",
                    NeutralDiagnosticKind::Unknown => "unknown",
                },
                diagnostic.recognized
            )
        }
    };
    ExpectedAtom {
        kind,
        surface: source[span.start_byte..span.end_byte].to_owned(),
        start_byte: span.start_byte,
        end_byte: span.end_byte,
    }
}

fn contributes_to_delivery_count(atom: &ClauseAtom) -> bool {
    !matches!(
        atom,
        ClauseAtom::UnresolvedDiagnostic(diagnostic) if !diagnostic.recognized
    )
}

fn assert_stream_integrity(source: &str, stream: &ClauseStream) {
    let atoms = stream
        .clauses
        .iter()
        .flat_map(|clause| clause.atoms.iter())
        .collect::<Vec<_>>();

    for atom in &atoms {
        assert_span("focused ownership case", source, atom.span());
    }
    for separator in &stream.separators {
        assert_span("focused ownership case", source, separator.span);
    }
    for atom in &atoms {
        for separator in &stream.separators {
            assert!(
                atom.span().end_byte <= separator.span.start_byte
                    || separator.span.end_byte <= atom.span().start_byte
            );
        }
    }
    assert_eq!(
        atoms
            .iter()
            .filter(|atom| contributes_to_delivery_count(atom))
            .count(),
        stream.delivery_conservation_count
    );
}

fn assert_span(case_id: &str, source: &str, span: SourceSpan) {
    assert!(span.start_byte <= span.end_byte, "{case_id}: reversed span");
    assert!(
        span.end_byte <= source.len(),
        "{case_id}: span out of source"
    );
    assert!(
        source.is_char_boundary(span.start_byte) && source.is_char_boundary(span.end_byte),
        "{case_id}: span is not on UTF-8 character boundaries"
    );
}
