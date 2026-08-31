use std::collections::HashSet;

use inku_ddl::{
    NeutralDiagnosticKind, NeutralTokenKind, NormalizedDdlDocument, ResolvedInstructionLanguage,
    parse_neutral_lexemes, project_macro_semantic_ref, saijiki_asset,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/neutral-parser-v1.json");

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
    expected_tokens: Vec<ExpectedToken>,
    expected_diagnostics: Vec<ExpectedDiagnostic>,
    recognized_delivery_count: usize,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedToken {
    kind: String,
    surface: String,
    start_byte: usize,
    end_byte: usize,
    #[serde(default)]
    asset_id: Option<String>,
    #[serde(default)]
    category_key: Option<String>,
    #[serde(default)]
    canonical_surface_ja: Option<String>,
    #[serde(default)]
    relation_type: Option<String>,
    #[serde(default)]
    value: Option<u64>,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedDiagnostic {
    kind: String,
    surface: String,
    start_byte: usize,
    end_byte: usize,
    recognized: bool,
}

#[test]
fn fixture_known_answers_are_source_preserving_and_meaning_neutral() {
    let fixture = load_fixture();
    for case in fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source.clone(),
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap_or_else(|error| panic!("{}: unexpected document diagnostic: {error}", case.id));
        let before = document.source().as_bytes().to_vec();

        let result = parse_neutral_lexemes(&document);

        assert_eq!(document.source().as_bytes(), before, "{}", case.id);
        assert_eq!(
            result.tokens.iter().map(project_token).collect::<Vec<_>>(),
            case.expected_tokens,
            "{}",
            case.id
        );
        assert_eq!(
            result
                .diagnostics
                .iter()
                .map(project_diagnostic)
                .collect::<Vec<_>>(),
            case.expected_diagnostics,
            "{}",
            case.id
        );
        assert_eq!(
            result.recognized_delivery_count, case.recognized_delivery_count,
            "{}",
            case.id
        );
    }
}

#[test]
fn every_delivery_has_an_exact_non_overlapping_utf8_source_span() {
    let fixture = load_fixture();
    for case in fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source,
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap();
        let result = parse_neutral_lexemes(&document);
        let source = document.source();
        let mut deliveries = result
            .tokens
            .iter()
            .map(|token| {
                (
                    token.span.start_byte,
                    token.span.end_byte,
                    token.surface.as_str(),
                )
            })
            .chain(result.diagnostics.iter().map(|diagnostic| {
                (
                    diagnostic.span.start_byte,
                    diagnostic.span.end_byte,
                    diagnostic.surface.as_str(),
                )
            }))
            .collect::<Vec<_>>();
        deliveries.sort_by_key(|(start, end, _)| (*start, *end));

        for (start, end, surface) in &deliveries {
            assert!(source.is_char_boundary(*start), "{}", case.id);
            assert!(source.is_char_boundary(*end), "{}", case.id);
            assert_eq!(&source[*start..*end], *surface, "{}", case.id);
        }
        assert!(
            deliveries.windows(2).all(|pair| pair[0].1 <= pair[1].0),
            "{}",
            case.id
        );
        assert!(
            result
                .tokens
                .windows(2)
                .all(|pair| pair[0].span.end_byte <= pair[1].span.start_byte),
            "{}",
            case.id
        );
        assert!(
            result
                .diagnostics
                .windows(2)
                .all(|pair| pair[0].span.end_byte <= pair[1].span.start_byte),
            "{}",
            case.id
        );
    }
}

#[test]
fn bilingual_surfaces_share_the_same_canonical_asset_row() {
    let fixture = load_fixture();
    let canonical_row = |case_id: &str, surface: &str| {
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
        parse_neutral_lexemes(&document)
            .tokens
            .into_iter()
            .find_map(|token| match token.kind {
                NeutralTokenKind::SaijikiWord {
                    asset_id,
                    category_key,
                    canonical_surface_ja,
                } if token.surface == surface => {
                    Some((asset_id, category_key, canonical_surface_ja))
                }
                _ => None,
            })
            .unwrap()
    };

    assert_eq!(
        canonical_row("ja-longest-source-and-hole", "画用紙"),
        canonical_row("en-case-longest-source-and-hole", "Drawing Paper")
    );
}

#[test]
fn asset_flags_drive_candidate_eligibility_without_losing_semantic_identity() {
    let asset = saijiki_asset();
    let mut active = 0;
    let mut marker_only = 0;
    let mut disabled = 0;

    for category in &asset.categories {
        for word in &category.words {
            let enabled = word.prompt || word.display || word.marker == Some(true);
            if enabled {
                active += 1;
                assert!(
                    project_macro_semantic_ref(&category.key, &word.surface_ja).is_some(),
                    "eligible asset row must have one canonical semantic identity"
                );
                if !word.prompt && !word.display {
                    marker_only += 1;
                }
            } else {
                disabled += 1;
            }
        }
    }

    assert_eq!((active, marker_only, disabled), (87, 1, 1));
}

#[test]
fn disabled_row_is_unknown_while_active_rows_remain_source_preserving() {
    let asset = saijiki_asset();
    let disabled = asset
        .categories
        .iter()
        .flat_map(|category| {
            category
                .words
                .iter()
                .map(move |word| (category.key.as_str(), word))
        })
        .find(|(_, word)| !word.prompt && !word.display && word.marker != Some(true))
        .expect("accepted asset has one disabled tombstone");
    let marker_only = asset
        .categories
        .iter()
        .flat_map(|category| {
            category
                .words
                .iter()
                .map(move |word| (category.key.as_str(), word))
        })
        .find(|(_, word)| !word.prompt && !word.display && word.marker == Some(true))
        .expect("accepted asset has one marker-only active row");
    let normal = asset
        .categories
        .iter()
        .flat_map(|category| {
            category
                .words
                .iter()
                .map(move |word| (category.key.as_str(), word))
        })
        .find(|(_, word)| (word.prompt || word.display) && word.surface_en.is_some())
        .expect("accepted asset has a bilingual normal active row");

    let disabled_document = NormalizedDdlDocument::new(
        disabled.1.surface_ja.clone(),
        ResolvedInstructionLanguage::Ja,
        Vec::new(),
    )
    .unwrap();
    let disabled_result = parse_neutral_lexemes(&disabled_document);
    assert!(disabled_result.tokens.is_empty());
    assert_eq!(disabled_result.diagnostics.len(), 1);
    assert_eq!(
        disabled_result.diagnostics[0].kind,
        NeutralDiagnosticKind::Unknown
    );
    assert_eq!(
        disabled_result.diagnostics[0].surface,
        disabled.1.surface_ja
    );
    assert!(!disabled_result.diagnostics[0].recognized);

    for (category_key, word) in [marker_only, normal] {
        for (language, surface) in [
            (
                ResolvedInstructionLanguage::Ja,
                Some(word.surface_ja.as_str()),
            ),
            (ResolvedInstructionLanguage::En, word.surface_en.as_deref()),
        ] {
            let Some(surface) = surface else {
                continue;
            };
            let document = NormalizedDdlDocument::new(surface, language, Vec::new()).unwrap();
            let result = parse_neutral_lexemes(&document);
            assert!(result.diagnostics.is_empty(), "{category_key}/{surface}");
            assert!(result.tokens.iter().any(|token| {
                token.span.start_byte == 0
                    && token.span.end_byte == surface.len()
                    && matches!(
                        &token.kind,
                        NeutralTokenKind::SaijikiWord {
                            category_key: actual_category,
                            canonical_surface_ja,
                            ..
                        } if actual_category == category_key
                            && canonical_surface_ja == &word.surface_ja
                    )
            }));
        }
    }

    let source = format!("{} {}", disabled.1.surface_ja, normal.1.surface_ja);
    let document =
        NormalizedDdlDocument::new(source.clone(), ResolvedInstructionLanguage::Ja, Vec::new())
            .unwrap();
    let result = parse_neutral_lexemes(&document);
    assert!(result.tokens.iter().any(|token| {
        token.surface == normal.1.surface_ja
            && matches!(
                &token.kind,
                NeutralTokenKind::SaijikiWord { category_key, .. }
                    if category_key == normal.0
            )
    }));
    assert!(result.diagnostics.iter().any(|diagnostic| {
        diagnostic.kind == NeutralDiagnosticKind::Unknown
            && diagnostic.surface == disabled.1.surface_ja
            && &source[diagnostic.span.start_byte..diagnostic.span.end_byte] == diagnostic.surface
    }));
    for token in &result.tokens {
        assert_eq!(
            &source[token.span.start_byte..token.span.end_byte],
            token.surface
        );
    }
    let mut spans = result
        .tokens
        .iter()
        .map(|token| token.span)
        .chain(result.diagnostics.iter().map(|diagnostic| diagnostic.span))
        .collect::<Vec<_>>();
    spans.sort_by_key(|span| (span.start_byte, span.end_byte));
    assert!(
        spans
            .windows(2)
            .all(|pair| pair[0].end_byte <= pair[1].start_byte)
    );
}

#[test]
fn false_positive_and_macro_cases_never_emit_saijiki_tokens() {
    let fixture = load_fixture();
    for case_id in [
        "en-substring-false-positives",
        "ja-substring-and-qualified-macro-unknown",
    ] {
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
        let result = parse_neutral_lexemes(&document);
        assert!(result.tokens.iter().all(|token| !matches!(
            token.kind,
            NeutralTokenKind::SaijikiWord { .. } | NeutralTokenKind::SaijikiRelation { .. }
        )));
    }
}

#[test]
fn fixture_schema_case_count_ids_and_required_cases_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(fixture.schema, "inku.neutral-lexeme-parser-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(fixture.cases.len(), 13);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "ja-longest-source-and-hole",
        "en-case-longest-source-and-hole",
        "ja-relation-longest",
        "en-relation-longest",
        "ja-exact-number-equivalence",
        "en-exact-number-equivalence",
        "ja-qualitative-quantities-remain-holes",
        "en-qualitative-quantities-remain-holes",
        "en-substring-false-positives",
        "ja-substring-and-qualified-macro-unknown",
        "separator-only-source",
        "ja-full-relation-literal",
        "en-full-relation-literal-case",
    ] {
        assert!(
            ids.contains(required),
            "missing required fixture case: {required}"
        );
    }
}

#[test]
fn accepted_full_relation_literals_are_single_source_preserving_lexemes() {
    for relation in &saijiki_asset().relations {
        for (language, literals) in [
            (ResolvedInstructionLanguage::Ja, &relation.literals_ja),
            (ResolvedInstructionLanguage::En, &relation.literals_en),
        ] {
            for literal in literals {
                let source = format!("{literal}.");
                let document = NormalizedDdlDocument::new(source.clone(), language, Vec::new())
                    .expect("accepted relation literal forms a document");
                let result = parse_neutral_lexemes(&document);
                assert!(result.diagnostics.is_empty(), "{literal}");
                assert_eq!(result.tokens.len(), 1, "{literal}");
                let token = &result.tokens[0];
                assert_eq!(token.surface, *literal, "{literal}");
                assert_eq!(token.span.start_byte, 0, "{literal}");
                assert_eq!(token.span.end_byte, literal.len(), "{literal}");
                assert!(matches!(
                    &token.kind,
                    NeutralTokenKind::SaijikiRelation { relation_type, .. }
                        if relation_type == &relation.relation_type
                ));
            }
        }

        for literal in &relation.literals_en {
            let upper = literal.to_ascii_uppercase();
            let source = format!("{upper}.");
            let document =
                NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                    .expect("ASCII case variant forms a document");
            let result = parse_neutral_lexemes(&document);
            assert!(result.diagnostics.is_empty(), "{upper}");
            assert_eq!(result.tokens.len(), 1, "{upper}");
            assert_eq!(result.tokens[0].surface, upper);

            let embedded = format!("x{literal}y");
            let document =
                NormalizedDdlDocument::new(embedded, ResolvedInstructionLanguage::En, Vec::new())
                    .expect("embedded ASCII surface forms a document");
            assert!(
                parse_neutral_lexemes(&document)
                    .tokens
                    .iter()
                    .all(|token| !token.surface.eq_ignore_ascii_case(literal)),
                "{literal}: ASCII word boundary"
            );
        }
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

fn project_token(token: &inku_ddl::NeutralToken) -> ExpectedToken {
    let mut projected = ExpectedToken {
        kind: String::new(),
        surface: token.surface.clone(),
        start_byte: token.span.start_byte,
        end_byte: token.span.end_byte,
        asset_id: None,
        category_key: None,
        canonical_surface_ja: None,
        relation_type: None,
        value: None,
    };
    match &token.kind {
        NeutralTokenKind::SaijikiWord {
            asset_id,
            category_key,
            canonical_surface_ja,
        } => {
            projected.kind = "saijiki_word".to_owned();
            projected.asset_id = Some(asset_id.clone());
            projected.category_key = Some(category_key.clone());
            projected.canonical_surface_ja = Some(canonical_surface_ja.clone());
        }
        NeutralTokenKind::SaijikiRelation {
            asset_id,
            relation_type,
        } => {
            projected.kind = "saijiki_relation".to_owned();
            projected.asset_id = Some(asset_id.clone());
            projected.relation_type = Some(relation_type.clone());
        }
        NeutralTokenKind::FunctionWord => projected.kind = "function_word".to_owned(),
        NeutralTokenKind::ExactNumber { value } => {
            projected.kind = "exact_number".to_owned();
            projected.value = Some(*value);
        }
    }
    projected
}

fn project_diagnostic(diagnostic: &inku_ddl::NeutralDiagnostic) -> ExpectedDiagnostic {
    ExpectedDiagnostic {
        kind: match diagnostic.kind {
            NeutralDiagnosticKind::Hole => "hole",
            NeutralDiagnosticKind::Conflict => "conflict",
            NeutralDiagnosticKind::Unknown => "unknown",
        }
        .to_owned(),
        surface: diagnostic.surface.clone(),
        start_byte: diagnostic.span.start_byte,
        end_byte: diagnostic.span.end_byte,
        recognized: diagnostic.recognized,
    }
}
