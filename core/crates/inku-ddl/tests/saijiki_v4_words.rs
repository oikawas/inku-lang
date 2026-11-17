//! Saijiki v4 words (2026-11-17, V1 core): the shared メゾチント surface is read by place.

use inku_ddl::{
    NeutralTokenKind, NormalizedDdlDocument, ResolvedInstructionLanguage, parse_neutral_lexemes,
};

fn categories_of(
    source: &str,
    language: ResolvedInstructionLanguage,
    surface: &str,
) -> Vec<String> {
    let document = NormalizedDdlDocument::new(source, language, vec![]).unwrap();
    parse_neutral_lexemes(&document)
        .tokens
        .into_iter()
        .filter(|token| token.surface.eq_ignore_ascii_case(surface))
        .filter_map(|token| match token.kind {
            NeutralTokenKind::SaijikiWord { category_key, .. } => Some(category_key),
            _ => None,
        })
        .collect()
}

// Concrete failure: the shared surface is read as one category everywhere, so either the
// ground sentence or the surface of a circle loses its meaning.
#[test]
fn mezzotint_is_the_ground_alone_in_its_sentence_and_the_surface_elsewhere() {
    use ResolvedInstructionLanguage::{En, Ja};
    for (source, language, surface, expected) in [
        ("メゾチント。", Ja, "メゾチント", vec!["ji"]),
        (
            "メゾチント。メゾチントの円を置く。",
            Ja,
            "メゾチント",
            vec!["ji", "omote"],
        ),
        (
            "白いメゾチントの円を置く。メゾチント。",
            Ja,
            "メゾチント",
            vec!["omote", "ji"],
        ),
        ("Mezzotint.", En, "mezzotint", vec!["ji"]),
        (
            "Place a white mezzotint circle. Mezzotint.",
            En,
            "mezzotint",
            vec!["omote", "ji"],
        ),
    ] {
        assert_eq!(
            categories_of(source, language, surface),
            expected,
            "{source}"
        );
    }
}
