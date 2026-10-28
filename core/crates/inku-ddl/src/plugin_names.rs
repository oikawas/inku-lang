//! Visible plugin names shared by the parser, validation, and migration.

use crate::{
    ResolvedInstructionLanguage,
    parser::core_modifier_surface_forms,
    saijiki::{SaijikiEdition, parser_candidate_surfaces},
};
use unicode_normalization::UnicodeNormalization;

/// Normalize the user-visible name for lookup; the written source remains unchanged.
pub fn normalize_plugin_name(name: &str) -> String {
    let folded: String = name.nfkc().flat_map(char::to_lowercase).collect();
    folded.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Generate the v1 names used by both the transitional spelling and migration.
pub fn v1_plugin_names(heading: &str, aliases: &[String]) -> (Vec<String>, Vec<String>) {
    let ja = if aliases.is_empty() {
        vec![heading.to_owned()]
    } else {
        aliases.to_vec()
    };
    let mut english = String::new();
    let mut previous: Option<char> = None;
    for ch in heading.chars() {
        if ch == '_' || ch == '-' {
            if !english.is_empty() && !english.ends_with(' ') {
                english.push(' ');
            }
        } else {
            if ch.is_ascii_uppercase()
                && previous.is_some_and(|p| p.is_ascii_lowercase() || p.is_ascii_digit())
                && !english.ends_with(' ')
            {
                english.push(' ');
            }
            english.extend(ch.to_lowercase());
        }
        previous = Some(ch);
    }
    (ja, vec![english.trim().to_owned()])
}

/// A v2 name must be visible as one noun and must contain a letter.
pub fn valid_plugin_name(name: &str, language: ResolvedInstructionLanguage) -> bool {
    if name.is_empty() || name.trim() != name || !name.chars().any(char::is_alphabetic) {
        return false;
    }
    let mut space = false;
    for ch in name.chars() {
        if ch == ' ' && language == ResolvedInstructionLanguage::En {
            if space {
                return false;
            }
            space = true;
        } else if ch.is_alphabetic() || ch.is_numeric() || matches!(ch, 'ー' | '・' | '-') {
            space = false;
        } else {
            return false;
        }
    }
    true
}

/// Compare against the same asset surfaces and parser-owned modifier forms.
pub fn plugin_name_is_core_word(name: &str) -> bool {
    let wanted = normalize_plugin_name(name);
    let asset = SaijikiEdition::CURRENT.asset();
    let asset_match = asset
        .categories
        .iter()
        .flat_map(|category| &category.words)
        .any(|word| {
            [
                ResolvedInstructionLanguage::Ja,
                ResolvedInstructionLanguage::En,
            ]
            .into_iter()
            .flat_map(|language| parser_candidate_surfaces(word, language))
            .any(|surface| normalize_plugin_name(&surface) == wanted)
        });
    asset_match
        || [
            ResolvedInstructionLanguage::Ja,
            ResolvedInstructionLanguage::En,
        ]
        .into_iter()
        .any(|language| {
            let forms = core_modifier_surface_forms(language);
            std::iter::once(forms.regular)
                .chain(forms.thinness.iter().map(|(s, _)| *s))
                .chain(forms.relative_scale.iter().map(|(s, _)| *s))
                .any(|surface| normalize_plugin_name(surface) == wanted)
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_fold_compatibility_and_convert_v1_headings_without_changing_the_source() {
        assert_eq!(
            normalize_plugin_name(" ＹＯＵＮＧ　 𝐋𝐞𝐚𝐯𝐞𝐬 "),
            "young leaves"
        );
        assert_eq!(
            v1_plugin_names("YoungLeaves", &["若葉".to_owned()]),
            (vec!["若葉".to_owned()], vec!["young leaves".to_owned()])
        );
        assert_eq!(
            v1_plugin_names("Withered-Grass2Green", &[]).1,
            vec!["withered grass2 green"]
        );
        assert!(valid_plugin_name(
            "young leaves",
            ResolvedInstructionLanguage::En
        ));
        assert!(!valid_plugin_name(
            "young  leaves",
            ResolvedInstructionLanguage::En
        ));
        assert!(!valid_plugin_name("123", ResolvedInstructionLanguage::Ja));
        assert!(plugin_name_is_core_word("ＣＩＲＣＬＥ"));
        assert!(plugin_name_is_core_word("大きい"));
    }
}
