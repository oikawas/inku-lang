//! Saijiki v4 words (2026-11-17, V1 core): the shared メゾチント surface is read by place,
//! and the thinness and size words are the asset's ふとさ・おおきさ.

use inku_ddl::{
    CoreModifierValue, NeutralTokenKind, NormalizedDdlDocument, ResolvedInstructionLanguage,
    parse_neutral_lexemes,
};

fn modifiers_of(source: &str, language: ResolvedInstructionLanguage) -> Vec<CoreModifierValue> {
    let document = NormalizedDdlDocument::new(source, language, vec![]).unwrap();
    parse_neutral_lexemes(&document)
        .tokens
        .into_iter()
        .filter_map(|token| match token.kind {
            NeutralTokenKind::CoreModifier(identity) => Some(identity.value),
            _ => None,
        })
        .collect()
}

// Concrete failure: the forms still come from the fixed v3 tables, so the v4 words are
// unknown and the retired words still read.
#[test]
fn thinness_and_size_read_the_v4_words_only() {
    use CoreModifierValue::{ExtraFine, ExtraThick, Large, Normal, Small, VeryLarge, VerySmall};
    use ResolvedInstructionLanguage::{En, Ja};
    for (source, language, expected) in [
        ("ごく小さな円を置く。", Ja, vec![VerySmall]),
        ("ごく大きい円を置く。", Ja, vec![VeryLarge]),
        (
            "小さい円と大きな円と普通の大きさの円を置く。",
            Ja,
            vec![Small, Large, Normal],
        ),
        (
            "ごく細い線とごく太い線を引く。",
            Ja,
            vec![ExtraFine, ExtraThick],
        ),
        (
            "place a very small circle and a very large circle.",
            En,
            vec![VerySmall, VeryLarge],
        ),
        (
            "draw a very thin line and a very thick line.",
            En,
            vec![ExtraFine, ExtraThick],
        ),
        ("とても小さな円と小さめの円と巨大な円を置く。", Ja, vec![]),
        ("draw an extra-fine line and a huge circle.", En, vec![]),
    ] {
        assert_eq!(modifiers_of(source, language), expected, "{source}");
    }
}

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
