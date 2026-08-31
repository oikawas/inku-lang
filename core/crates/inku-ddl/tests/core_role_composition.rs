use std::collections::HashSet;

use inku_ddl::{
    CORE_ROLE_COMPOSITION_SCHEMA_ID, CoreRoleKind, NeutralDiagnostic, NeutralDiagnosticKind,
    NeutralParseResult, NeutralTokenKind, NormalizedDdlDocument, ResolvedInstructionLanguage,
    SourceSpan, compose_core_roles, parse_neutral_lexemes,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/core-role-composition-v1.json");

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
    expected_roles: Vec<ExpectedRole>,
    expected_deferred: Vec<ExpectedDeferred>,
    expected_diagnostics: Vec<ExpectedDiagnostic>,
    recognized_delivery_count: usize,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedRole {
    role: String,
    asset_id: String,
    category_key: String,
    canonical_surface_ja: String,
    start_byte: usize,
    end_byte: usize,
}

#[derive(Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct ExpectedDeferred {
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
fn fixture_composes_exact_five_and_defers_every_other_delivery() {
    let fixture = load_fixture();
    for case in fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source,
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap_or_else(|error| panic!("{}: unexpected document diagnostic: {error}", case.id));
        let neutral = parse_neutral_lexemes(&document);
        let input_token_count = neutral.tokens.len();
        let input_recognized_delivery_count = neutral.recognized_delivery_count;

        let composition = compose_core_roles(neutral);

        assert_eq!(
            composition
                .typed_roles
                .iter()
                .map(project_role)
                .collect::<Vec<_>>(),
            case.expected_roles,
            "{}",
            case.id
        );
        assert_eq!(
            composition
                .deferred_tokens
                .iter()
                .map(project_deferred)
                .collect::<Vec<_>>(),
            case.expected_deferred,
            "{}",
            case.id
        );
        assert_eq!(
            composition
                .diagnostics
                .iter()
                .map(project_diagnostic)
                .collect::<Vec<_>>(),
            case.expected_diagnostics,
            "{}",
            case.id
        );
        assert_eq!(
            input_token_count,
            composition.typed_roles.len() + composition.deferred_tokens.len(),
            "{}",
            case.id
        );
        assert_eq!(
            composition.delivery_conservation_count, input_recognized_delivery_count,
            "{}",
            case.id
        );
        assert_eq!(
            composition.delivery_conservation_count,
            composition.typed_roles.len()
                + composition.deferred_tokens.len()
                + composition
                    .diagnostics
                    .iter()
                    .filter(|diagnostic| diagnostic.recognized)
                    .count(),
            "{}",
            case.id
        );
        assert_eq!(
            composition.delivery_conservation_count, case.recognized_delivery_count,
            "{}",
            case.id
        );
    }
}

#[test]
fn bilingual_surfaces_share_role_and_canonical_row_identity() {
    let fixture = load_fixture();
    let identity = |case_id: &str| {
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
        compose_core_roles(parse_neutral_lexemes(&document))
            .typed_roles
            .into_iter()
            .find(|term| term.canonical_surface_ja == "紙")
            .map(|term| {
                (
                    term.role,
                    term.asset_id,
                    term.category_key,
                    term.canonical_surface_ja,
                )
            })
            .unwrap()
    };

    assert_eq!(identity("ja-exact-five"), identity("en-exact-five"));
}

#[test]
fn diagnostics_are_forwarded_without_reclassification() {
    let diagnostics = vec![
        NeutralDiagnostic {
            span: SourceSpan {
                start_byte: 1,
                end_byte: 5,
            },
            surface: "hole".to_owned(),
            kind: NeutralDiagnosticKind::Hole,
            recognized: true,
        },
        NeutralDiagnostic {
            span: SourceSpan {
                start_byte: 8,
                end_byte: 16,
            },
            surface: "conflict".to_owned(),
            kind: NeutralDiagnosticKind::Conflict,
            recognized: true,
        },
        NeutralDiagnostic {
            span: SourceSpan {
                start_byte: 20,
                end_byte: 27,
            },
            surface: "unknown".to_owned(),
            kind: NeutralDiagnosticKind::Unknown,
            recognized: false,
        },
    ];
    let before = diagnostics.clone();
    let composition = compose_core_roles(NeutralParseResult {
        tokens: Vec::new(),
        diagnostics,
        recognized_delivery_count: 2,
    });

    assert!(composition.typed_roles.is_empty());
    assert!(composition.deferred_tokens.is_empty());
    assert_eq!(composition.diagnostics, before);
    assert_eq!(composition.delivery_conservation_count, 2);
}

#[test]
fn fixture_schema_ids_and_required_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(
        CORE_ROLE_COMPOSITION_SCHEMA_ID,
        "inku.core-role-composition.v1"
    );
    assert_eq!(fixture.schema, "inku.core-role-composition-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(fixture.cases.len(), 6);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "ja-exact-five",
        "en-exact-five",
        "en-same-role-multiple",
        "en-all-deferred-kinds",
        "en-partial-hole-and-unknowns",
        "en-unknown-sentence-and-qualified-macro",
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

fn project_role(term: &inku_ddl::CoreRoleTerm) -> ExpectedRole {
    ExpectedRole {
        role: match term.role {
            CoreRoleKind::Primitive => "primitive",
            CoreRoleKind::Touch => "touch",
            CoreRoleKind::Color => "color",
            CoreRoleKind::Surface => "surface",
            CoreRoleKind::Ground => "ground",
        }
        .to_owned(),
        asset_id: term.asset_id.clone(),
        category_key: term.category_key.clone(),
        canonical_surface_ja: term.canonical_surface_ja.clone(),
        start_byte: term.span.start_byte,
        end_byte: term.span.end_byte,
    }
}

fn project_deferred(token: &inku_ddl::NeutralToken) -> ExpectedDeferred {
    let mut projected = ExpectedDeferred {
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
            canonical_identity,
        } => {
            assert_eq!(
                canonical_identity.kind.as_str(),
                relation_type,
                "deferred relation canonical kind"
            );
            assert_eq!(
                canonical_identity.form,
                inku_ddl::CanonicalRelationForm::Short,
                "fixture relation is the accepted short form"
            );
            assert_eq!(canonical_identity.previous_reference, None);
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
