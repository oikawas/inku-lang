//! Selection of the installed plugin words relevant to a particular request.

use inku_ddl::{
    MacroDefinition, ParameterSchema, ResolvedInstructionLanguage, bracketed_plugin_at,
    plugin_names::{normalize_plugin_name, v1_plugin_names},
};
use serde::{Deserialize, Serialize};

use crate::prompts::MacroPromptEntry;
use crate::prompts::{LlmPrompt, PromptError, PromptLimits, hash_prompt, project_macro_catalog};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OfferReason {
    Brace,
    Ddl,
    Name,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct OfferItem {
    pub qualified_name: String,
    pub reason: OfferReason,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub written_ja: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub written_en: String,
}

#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
pub struct PluginOffer {
    pub offered: Vec<OfferItem>,
    pub omitted: Vec<OfferItem>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct OfferRecord {
    pub stage: crate::prompts::LlmStage,
    pub offer: PluginOffer,
}

pub const PLUGIN_RULE_JA: &str = "\n\n# プラグインの語\nplugins の語だけを使う。記述の物そのものなら使い、合成語の前の語が景を言う時も含む（川舟の川）。色名・たとえ・時など別の意味なら使わない。物の語は形の語（円・四角など）の代わりに書き、その語の行に挙がった語だけを添える。情景の語は数以外を添えず、数は記述にある時だけ（例：｛若葉｝。）。描く物を他の形で重ねない。";
pub const PLUGIN_RULE_EN: &str = "\n\n# Plugin words\nUse only the words in plugins. Use a word when the description means its thing itself, including a compound's first word when it names the scene (river in river-boat); do not use it for another meaning (a color, simile, or time). An object word replaces a shape word (circle, square, ...) and takes only the words its line lists. A scene word takes only a count, and only when stated (e.g. {young leaves}.). Do not draw its subject again with other shapes.";

pub fn rule(language: ResolvedInstructionLanguage) -> &'static str {
    match language {
        ResolvedInstructionLanguage::Ja => PLUGIN_RULE_JA,
        ResolvedInstructionLanguage::En => PLUGIN_RULE_EN,
    }
}

pub fn primary_name(definition: &MacroDefinition, language: ResolvedInstructionLanguage) -> String {
    let (ja, en) = visible_names(definition);
    match language {
        ResolvedInstructionLanguage::Ja => {
            format!("｛{}｝", ja.first().unwrap_or(&definition.heading))
        }
        ResolvedInstructionLanguage::En => {
            format!("{{{}}}", en.first().unwrap_or(&definition.heading))
        }
    }
}

/// A short presentation, derived from the definition and the first sentence
/// of the host's localized summary, without exposing the definition body.
pub fn offer_line(entry: &MacroPromptEntry<'_>, language: ResolvedInstructionLanguage) -> String {
    let definition = entry.definition;
    let summary = entry.localized_summary.trim();
    let end = match language {
        ResolvedInstructionLanguage::Ja => summary.find('。').map(|i| i + '。'.len_utf8()),
        ResolvedInstructionLanguage::En => summary.find(". ").map(|i| i + 1),
    }
    .unwrap_or(summary.len());
    let sentence = &summary[..end];
    let summary = if let Some((cut, next)) = sentence.char_indices().nth(99)
        && sentence.chars().count() > 100
    {
        let prefix = &sentence[..cut];
        let prefix = match language {
            ResolvedInstructionLanguage::Ja => prefix,
            ResolvedInstructionLanguage::En if next.is_whitespace() => prefix.trim_end(),
            ResolvedInstructionLanguage::En => prefix
                .rfind(char::is_whitespace)
                .map_or("", |boundary| prefix[..boundary].trim_end()),
        };
        format!("{prefix}…")
    } else {
        sentence.to_owned()
    };
    let object = definition
        .plugin_v2
        .as_ref()
        .is_some_and(|v2| v2.kind == "object");
    let count = definition
        .parameters
        .iter()
        .find_map(|(_, schema)| schema.count_parameter());
    let counter = definition
        .plugin_v2
        .as_ref()
        .and_then(|v2| v2.counter.as_deref())
        .unwrap_or("general");
    let counter = match counter {
        "flat" => "枚",
        "long" => "本",
        _ => "個",
    };
    let colorable = object && (definition.primary_literal_color().is_some() || definition.parameters.iter().any(|(_, schema)| matches!(schema, ParameterSchema::SemanticRef { category, .. } if category == "color")));
    let category = match (language, object, count) {
        (ResolvedInstructionLanguage::Ja, true, _) => format!(
            "物の語（{}数は「{counter}」・位置・動き・大きさ・傾き。数の寸法は一辺、または幅と高さ）",
            if colorable { "色・" } else { "" }
        ),
        (ResolvedInstructionLanguage::En, true, _) => format!(
            "object word ({}count, place, action, size, angle; numeric dimensions: side or width and height)",
            if colorable { "color, " } else { "" }
        ),
        (ResolvedInstructionLanguage::Ja, false, Some(count)) => format!(
            "情景の語（数は「{}」で {}〜{}）",
            count.counter.japanese(),
            count.minimum,
            count.maximum
        ),
        (ResolvedInstructionLanguage::En, false, Some(count)) => {
            format!("scene word (count {}–{})", count.minimum, count.maximum)
        }
        (ResolvedInstructionLanguage::Ja, false, None) => {
            "情景の語（数を書くと区画に並べる）".to_owned()
        }
        (ResolvedInstructionLanguage::En, false, None) => {
            "scene word (a count lays copies in cells)".to_owned()
        }
    };
    let appearance: Vec<_> = definition
        .parameters
        .iter()
        .filter_map(|(_, schema)| match schema {
            ParameterSchema::SemanticRef { category, .. }
                if matches!(
                    category.as_str(),
                    "color"
                        | "touch"
                        | "surface"
                        | "continuity"
                        | "handling"
                        | "fineness"
                        | "variation"
                ) =>
            {
                Some(category.as_str())
            }
            _ => None,
        })
        .collect();
    let extra = if appearance.is_empty() {
        String::new()
    } else {
        format!(" [{}]", appearance.join(", "))
    };
    let separator = match language {
        ResolvedInstructionLanguage::Ja => "",
        ResolvedInstructionLanguage::En => " ",
    };
    format!(
        "{} {}{}{}{}",
        primary_name(definition, language),
        summary,
        separator,
        category,
        extra
    )
}

/// Both language lists are used for selection, independent of output language.
pub fn visible_names(definition: &MacroDefinition) -> (Vec<String>, Vec<String>) {
    definition.plugin_v2.as_ref().map_or_else(
        || v1_plugin_names(&definition.heading, &definition.aliases),
        |v2| (v2.names.ja.clone(), v2.names.en.clone()),
    )
}

fn cjk(ch: char) -> bool {
    matches!(ch as u32, 0x3040..=0x30ff | 0x3400..=0x9fff | 0xac00..=0xd7af | 0xf900..=0xfaff | 0x20000..=0x3134f)
}

fn occurrence(text: &str, name: &str) -> Option<usize> {
    let name = normalize_plugin_name(name);
    if name.is_empty() {
        return None;
    }
    if name.chars().any(cjk) {
        return text
            .match_indices(&name)
            .find_map(|(at, _)| (!follows_namespace_dot(text, at)).then_some(at));
    }
    let words = |value: &str| {
        let mut result = Vec::new();
        let mut start = None;
        for (at, ch) in value.char_indices() {
            if ch.is_alphanumeric() {
                start.get_or_insert(at);
            } else if let Some(begin) = start.take() {
                result.push((begin, value[begin..at].to_owned()));
            }
        }
        if let Some(begin) = start {
            result.push((begin, value[begin..].to_owned()));
        }
        result
    };
    let wanted: Vec<_> = words(&name).into_iter().map(|(_, word)| word).collect();
    if wanted.is_empty() {
        return None;
    }
    let actual = words(text);
    actual.windows(wanted.len()).find_map(|window| {
        (window.iter().map(|(_, word)| word).eq(wanted.iter())
            && !follows_namespace_dot(text, window[0].0))
        .then_some(window[0].0)
    })
}

fn follows_namespace_dot(text: &str, at: usize) -> bool {
    let Some(before) = text[..at].strip_suffix('.') else {
        return false;
    };
    let namespace = before
        .rsplit(|ch: char| !ch.is_ascii_alphanumeric() && ch != '_' && ch != '-')
        .next()
        .unwrap_or("");
    namespace
        .chars()
        .next()
        .is_some_and(|ch| ch.is_ascii_alphabetic())
}

fn braced(text: &str, names: &[String]) -> Option<usize> {
    text.char_indices().find_map(|(at, ch)| {
        if !matches!(ch, '{' | '｛') {
            return None;
        }
        let (_, written) = bracketed_plugin_at(text, at)?;
        let inner = normalize_plugin_name(written);
        names
            .iter()
            .any(|name| normalize_plugin_name(name) == inner)
            .then_some(at)
    })
}

/// Prioritize explicit braces, then names already in the DDL, then ordinary
/// mentions. Preserve occurrence order within each category and catalog order
/// for ties; count omissions separately for the run record.
pub fn offer_plugins(
    description: &str,
    current_ddl: Option<&str>,
    catalog: &[MacroPromptEntry<'_>],
    limit: usize,
) -> PluginOffer {
    let text = normalize_plugin_name(description);
    let ddl = current_ddl.map(normalize_plugin_name);
    let mut matches = Vec::new();
    for (index, entry) in catalog.iter().enumerate() {
        let definition = entry.definition;
        let Some(qualified_name) = definition.qualified_name() else {
            continue;
        };
        let (ja, en) = visible_names(definition);
        let names: Vec<_> = ja.into_iter().chain(en).collect();
        let brace = braced(&text, &names);
        let ddl_at = ddl.as_deref().and_then(|ddl| braced(ddl, &names));
        let named = names
            .iter()
            .filter_map(|name| occurrence(&text, name))
            .min();
        let selected = brace
            .map(|at| (0, at, OfferReason::Brace))
            .or_else(|| ddl_at.map(|at| (1, at, OfferReason::Ddl)))
            .or_else(|| named.map(|at| (2, at, OfferReason::Name)));
        if let Some((priority, at, reason)) = selected {
            matches.push((
                priority,
                at,
                index,
                OfferItem {
                    qualified_name,
                    reason,
                    written_ja: primary_name(definition, ResolvedInstructionLanguage::Ja),
                    written_en: primary_name(definition, ResolvedInstructionLanguage::En),
                },
            ));
        }
    }
    matches.sort_by_key(|(priority, at, index, _)| (*priority, *at, *index));
    let mut all: Vec<_> = matches.into_iter().map(|(_, _, _, item)| item).collect();
    let omitted = all.split_off(limit.min(all.len()));
    PluginOffer {
        offered: all,
        omitted,
    }
}

/// Add an offer after the complete writing/review system, so the shared prefix
/// remains cacheable. An empty offer leaves the request exactly as it was.
pub fn with_plugin_offer(
    mut prompt: LlmPrompt,
    description: &str,
    current_ddl: Option<&str>,
    catalog: &[MacroPromptEntry<'_>],
    limits: PromptLimits,
) -> Result<(LlmPrompt, PluginOffer), PromptError> {
    let offer = offer_plugins(
        description,
        current_ddl,
        catalog,
        limits.max_offered_plugins,
    );
    if offer.offered.is_empty() {
        return Ok((prompt, offer));
    }
    let entries: Vec<_> = offer
        .offered
        .iter()
        .filter_map(|item| {
            catalog
                .iter()
                .find(|entry| {
                    entry.definition.qualified_name().as_deref()
                        == Some(item.qualified_name.as_str())
                })
                .copied()
        })
        .collect();
    let mut message: serde_json::Value =
        serde_json::from_str(&prompt.message).map_err(|_| PromptError::Serialization)?;
    message["plugins"] = serde_json::json!(
        entries
            .iter()
            .map(|entry| offer_line(entry, prompt.instruction_language))
            .collect::<Vec<_>>()
    );
    prompt.message = serde_json::to_string(&message).map_err(|_| PromptError::Serialization)?;
    prompt.system.push_str(rule(prompt.instruction_language));
    prompt.macro_catalog_digest = Some(project_macro_catalog(&entries, limits)?.1);
    let schema =
        serde_json::to_string(&prompt.response_schema).map_err(|_| PromptError::Serialization)?;
    Ok((hash_prompt(prompt, &schema), offer))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    #[test]
    fn plugin_rules_include_compound_scene_words_in_both_languages() {
        assert_eq!(
            PLUGIN_RULE_JA,
            "\n\n# プラグインの語\nplugins の語だけを使う。記述の物そのものなら使い、合成語の前の語が景を言う時も含む（川舟の川）。色名・たとえ・時など別の意味なら使わない。物の語は形の語（円・四角など）の代わりに書き、その語の行に挙がった語だけを添える。情景の語は数以外を添えず、数は記述にある時だけ（例：｛若葉｝。）。描く物を他の形で重ねない。"
        );
        assert_eq!(
            PLUGIN_RULE_EN,
            "\n\n# Plugin words\nUse only the words in plugins. Use a word when the description means its thing itself, including a compound's first word when it names the scene (river in river-boat); do not use it for another meaning (a color, simile, or time). An object word replaces a shape word (circle, square, ...) and takes only the words its line lists. A scene word takes only a count, and only when stated (e.g. {young leaves}.). Do not draw its subject again with other shapes."
        );
    }

    #[test]
    fn braced_offer_uses_the_parser_boundaries() {
        let names = vec!["young leaves".to_owned()];
        assert_eq!(braced("｛young leaves｝", &names), Some(0));
        assert_eq!(braced("{young leaves.}", &names), None);
        assert_eq!(braced("{\"young leaves\":1}", &names), None);
        assert_eq!(braced("{young leaves", &names), None);
    }

    #[test]
    fn summary_lines_separate_english_and_mark_truncated_sentences() {
        let asset: Value = serde_json::from_str(include_str!(
            "../../inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json"
        ))
        .unwrap();
        let definition =
            MacroDefinition::from_json(&asset["entries"][0]["definition"].to_string()).unwrap();
        let summary = "Scatter fallen leaves widely and unevenly to both sides of a drift from upper left to lower right, gently gathering near the edge.";
        let entry = MacroPromptEntry {
            definition: &definition,
            localized_summary: summary,
        };
        let line = offer_line(&entry, ResolvedInstructionLanguage::En);
        let text = line
            .strip_prefix("{young leaves} ")
            .unwrap()
            .split_once(" scene word")
            .unwrap()
            .0;
        assert!(text.ends_with('…'));
        let complete = text.strip_suffix('…').unwrap();
        assert!(summary.starts_with(complete));
        assert!(summary[complete.len()..].starts_with(char::is_whitespace));
        assert!(text.chars().count() <= 100);

        let japanese = "若".repeat(101);
        let entry = MacroPromptEntry {
            definition: &definition,
            localized_summary: &japanese,
        };
        let line = offer_line(&entry, ResolvedInstructionLanguage::Ja);
        let text = line
            .strip_prefix("｛若葉｝ ")
            .unwrap()
            .split_once("情景の語")
            .unwrap()
            .0;
        assert!(text.ends_with('…'));
        assert_eq!(text.chars().count(), 100);

        let entry = MacroPromptEntry {
            definition: &definition,
            localized_summary: "A short sentence. Another sentence.",
        };
        let line = offer_line(&entry, ResolvedInstructionLanguage::En);
        assert!(line.contains("A short sentence. scene word"));
        assert!(!line.contains("Another sentence"));
    }

    #[test]
    fn selection_prioritizes_braces_then_ddl_then_mentions_and_respects_word_boundaries() {
        let asset: Value = serde_json::from_str(include_str!(
            "../../inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json"
        ))
        .unwrap();
        let leaves =
            MacroDefinition::from_json(&asset["entries"][0]["definition"].to_string()).unwrap();
        let mut rain = leaves.clone();
        rain.heading = "Rain".into();
        rain.aliases = vec!["雨".into()];
        let mut moon = leaves.clone();
        moon.heading = "FullMoon".into();
        moon.aliases = vec!["満月".into()];
        let catalog = [&leaves, &rain, &moon].map(|definition| MacroPromptEntry {
            definition,
            localized_summary: "",
        });
        let result = offer_plugins(
            "terrain に若葉、｛満月｝と雨",
            Some("｛若葉｝。"),
            &catalog,
            2,
        );
        assert_eq!(
            result
                .offered
                .iter()
                .map(|item| item.reason)
                .collect::<Vec<_>>(),
            [OfferReason::Brace, OfferReason::Ddl]
        );
        assert_eq!(result.offered[0].qualified_name, "Nature.FullMoon");
        assert_eq!(
            result.offered[1].qualified_name,
            leaves.qualified_name().unwrap()
        );
        assert_eq!(result.omitted[0].qualified_name, "Nature.Rain");
        assert!(
            offer_plugins("terrain", None, &catalog, 8)
                .offered
                .is_empty()
        );
        let english = offer_plugins("FULL MOON and rain", None, &catalog, 8);
        assert_eq!(
            english
                .offered
                .iter()
                .map(|item| item.qualified_name.as_str())
                .collect::<Vec<_>>(),
            ["Nature.FullMoon", "Nature.Rain"]
        );
        let braced = offer_plugins("｛ＹＯＵＮＧ　ＬＥＡＶＥＳ｝", None, &catalog, 8);
        assert_eq!(braced.offered[0].reason, OfferReason::Brace);
        assert!(
            offer_plugins("景色", Some("Nature.若葉。"), &catalog, 8)
                .offered
                .is_empty()
        );
        assert!(
            offer_plugins("Nature.若葉", None, &catalog, 8)
                .offered
                .is_empty()
        );
        assert_eq!(
            offer_plugins("Nature.若葉と若葉", None, &catalog, 8).offered[0].reason,
            OfferReason::Name
        );
    }

    #[test]
    fn no_offer_keeps_the_prompt_bytes_and_review_offers_the_locked_word() {
        let asset: Value = serde_json::from_str(include_str!(
            "../../inku-ddl/tests/fixtures/nature-leaves-2.1-v1.json"
        ))
        .unwrap();
        let definition =
            MacroDefinition::from_json(&asset["entries"][0]["definition"].to_string()).unwrap();
        let catalog = [MacroPromptEntry {
            definition: &definition,
            localized_summary: "若葉を描く。二文目。",
        }];
        let limits = crate::focused_flow::config().prompt_limits;
        let base =
            crate::prompts::build_sketch_prompt("海", ResolvedInstructionLanguage::Ja, limits)
                .unwrap();
        let (empty, record) =
            with_plugin_offer(base.clone(), "海", None, &catalog, limits).unwrap();
        assert!(record.offered.is_empty());
        assert_eq!(
            serde_json::to_vec(&base).unwrap(),
            serde_json::to_vec(&empty).unwrap()
        );
        let (prompt, record) =
            with_plugin_offer(base, "海", Some("｛若葉｝。"), &catalog, limits).unwrap();
        assert_eq!(record.offered[0].reason, OfferReason::Ddl);
        assert!(prompt.system.ends_with(PLUGIN_RULE_JA));
        let message: Value = serde_json::from_str(&prompt.message).unwrap();
        assert!(
            message["plugins"][0]
                .as_str()
                .unwrap()
                .contains("若葉を描く。")
        );
        assert!(!message["plugins"][0].as_str().unwrap().contains("二文目"));
        assert!(prompt.macro_catalog_digest.is_some());
    }
}
