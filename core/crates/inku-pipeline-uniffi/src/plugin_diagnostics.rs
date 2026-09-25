//! Explain why a plugin sentence in visible DDL was not drawn.
//!
//! The compiler withholds an unresolved plugin invocation with an internal
//! resolution reason. Hosts know more than the compiler: which plugins are
//! enabled, which are installed but disabled, and which came with an imported
//! DDL export. This shared projection turns the compiler's reason and the
//! host's lists into one author-facing reason per sentence, so every host
//! shows the same explanation.

use std::collections::BTreeSet;
use std::panic::{AssertUnwindSafe, catch_unwind};

use serde::{Deserialize, Serialize};
use serde_json::Value;

const SCHEMA: &str = "inku.plugin-diagnostics.v1";
const MAX_INPUT_BYTES: usize = 4 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    source: String,
    upstream_diagnostics: Vec<Value>,
    #[serde(default)]
    enabled: Vec<String>,
    #[serde(default)]
    disabled: Vec<String>,
}

/// One author-facing explanation for a withheld plugin sentence.
#[derive(Debug, Eq, PartialEq, Serialize)]
pub(crate) struct PluginDiagnostic {
    pub name: String,
    pub reason: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub suggestion: Option<String>,
    pub start_byte: usize,
    pub end_byte: usize,
}

#[derive(Serialize)]
struct Output {
    schema: &'static str,
    plugins: Vec<PluginDiagnostic>,
}

const PARTICLES: [char; 9] = ['を', 'に', 'の', 'で', 'と', 'へ', 'が', 'は', 'も'];

/// The `Namespace.Heading` written in one sentence. A known name at the same
/// position wins so a heading containing a particle is still read whole.
fn written_name(text: &str, known: &BTreeSet<&str>) -> Option<String> {
    let bytes = text.as_bytes();
    for (start, character) in text.char_indices() {
        if !character.is_ascii_alphabetic()
            || (start > 0 && (bytes[start - 1].is_ascii_alphanumeric() || bytes[start - 1] == b'_'))
        {
            continue;
        }
        let rest = &text[start..];
        let namespace_end = rest
            .find(|c: char| !(c.is_ascii_alphanumeric() || c == '_' || c == '-'))
            .unwrap_or(rest.len());
        if !rest[namespace_end..].starts_with('.') {
            continue;
        }
        if let Some(name) = known
            .iter()
            .filter(|name| rest.starts_with(**name))
            .max_by_key(|name| name.len())
        {
            return Some((*name).to_owned());
        }
        let heading = &rest[namespace_end + 1..];
        let heading_end = heading
            .find(|c: char| c.is_whitespace() || PARTICLES.contains(&c) || "。．.、,，".contains(c))
            .unwrap_or(heading.len());
        if heading_end > 0 {
            return Some(rest[..namespace_end + 1 + heading_end].to_owned());
        }
    }
    None
}

fn edit_distance(left: &str, right: &str) -> usize {
    let right: Vec<char> = right.chars().collect();
    let mut previous: Vec<usize> = (0..=right.len()).collect();
    for (i, a) in left.chars().enumerate() {
        let mut current = vec![i + 1];
        for (j, b) in right.iter().enumerate() {
            current.push(
                (previous[j] + usize::from(a != *b))
                    .min(previous[j + 1] + 1)
                    .min(current[j] + 1),
            );
        }
        previous = current;
    }
    previous[right.len()]
}

/// An enabled name the author probably meant: the same heading under another
/// namespace, a case-only difference, or at most two edits away.
fn suggestion(name: &str, enabled: &[String]) -> Option<String> {
    let heading = name.split_once('.').map_or(name, |(_, heading)| heading);
    enabled
        .iter()
        .filter(|candidate| candidate.as_str() != name)
        .map(|candidate| {
            let same_heading = candidate
                .split_once('.')
                .is_some_and(|(_, other)| other == heading);
            let score = if candidate.eq_ignore_ascii_case(name) || same_heading {
                0
            } else {
                edit_distance(name, candidate)
            };
            (score, candidate)
        })
        .filter(|(score, _)| *score <= 2)
        .min()
        .map(|(_, candidate)| candidate.clone())
}

pub(crate) fn explain(
    source: &str,
    diagnostics: &[Value],
    enabled: &[String],
    disabled: &[String],
) -> Vec<PluginDiagnostic> {
    let known: BTreeSet<&str> = enabled.iter().chain(disabled).map(String::as_str).collect();
    let mut out = Vec::new();
    for diagnostic in diagnostics {
        let Some(reason) = diagnostic.get("reason").and_then(Value::as_str) else {
            continue;
        };
        let version = matches!(
            reason,
            "macro_resolution_version_mismatch" | "macro_resolution_digest_mismatch"
        );
        if !version
            && !matches!(
                reason,
                "macro_resolution_missing_lock" | "macro_resolution_missing_definition"
            )
        {
            continue;
        }
        let span = diagnostic.get("span");
        let (Some(start), Some(end)) = (
            span.and_then(|span| span.get("start_byte"))
                .and_then(Value::as_u64),
            span.and_then(|span| span.get("end_byte"))
                .and_then(Value::as_u64),
        ) else {
            continue;
        };
        let (Ok(start), Ok(end)) = (usize::try_from(start), usize::try_from(end)) else {
            continue;
        };
        let Some(text) = source.get(start..end) else {
            continue;
        };
        let Some(name) = written_name(text, &known) else {
            continue;
        };
        let (reason, suggestion) = if version {
            ("plugin_version_mismatch", None)
        } else if disabled.contains(&name) && !enabled.contains(&name) {
            ("plugin_disabled", None)
        } else if enabled.contains(&name) {
            // A stale host list must not turn an unresolved name into a guess.
            ("plugin_not_installed", None)
        } else if let Some(candidate) = suggestion(&name, enabled) {
            ("plugin_name_mismatch", Some(candidate))
        } else {
            ("plugin_not_installed", None)
        };
        out.push(PluginDiagnostic {
            name,
            reason,
            suggestion,
            start_byte: start,
            end_byte: end,
        });
    }
    out
}

fn run(input_bytes: &[u8]) -> Result<Output, ()> {
    if input_bytes.len() > MAX_INPUT_BYTES {
        return Err(());
    }
    let input: Input = serde_json::from_slice(input_bytes).map_err(|_| ())?;
    Ok(Output {
        schema: SCHEMA,
        plugins: explain(
            &input.source,
            &input.upstream_diagnostics,
            &input.enabled,
            &input.disabled,
        ),
    })
}

/// Explain withheld plugin sentences from a delivery's upstream diagnostics.
#[uniffi::export]
pub fn explain_plugin_diagnostics(input_bytes: Vec<u8>) -> Vec<u8> {
    catch_unwind(AssertUnwindSafe(|| run(&input_bytes)))
        .ok()
        .and_then(Result::ok)
        .and_then(|output| serde_json::to_vec(&output).ok())
        .unwrap_or_else(|| {
            br#"{"schema":"inku.plugin-diagnostics.v1","error":"invalid_plugin_diagnostics_input"}"#
                .to_vec()
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn missing(source: &str, sentence: &str, reason: &str) -> Value {
        let start = source.find(sentence).unwrap();
        json!({"reason": reason, "span": {"start_byte": start, "end_byte": start + sentence.len()}})
    }

    #[test]
    fn each_withheld_plugin_sentence_gets_one_author_facing_reason() {
        let source = "背景を白で埋める。\nGarden.薔薇。\nNature.若葉を置く。\nnature.若葉。\nStudio.若葉。\nNature.若菜。\nOld.Mark。\nNature.紅葉。";
        let diagnostics = [
            missing(source, "Garden.薔薇", "macro_resolution_missing_lock"),
            missing(source, "Nature.若葉を置く", "macro_resolution_missing_lock"),
            missing(source, "nature.若葉", "macro_resolution_missing_lock"),
            missing(source, "Studio.若葉", "macro_resolution_missing_lock"),
            missing(source, "Nature.若菜", "macro_resolution_missing_lock"),
            missing(source, "Old.Mark", "macro_resolution_missing_lock"),
            missing(source, "Nature.紅葉", "macro_resolution_digest_mismatch"),
            json!({"reason": "unresolved_clause", "span": {"start_byte": 0, "end_byte": 3}}),
        ];
        let enabled = ["Nature.紅葉".to_owned(), "Nature.若葉".to_owned()];
        let disabled = ["Old.Mark".to_owned()];
        let explained = explain(source, &diagnostics, &enabled, &disabled);
        let summary: Vec<_> = explained
            .iter()
            .map(|item| (item.name.as_str(), item.reason, item.suggestion.as_deref()))
            .collect();
        assert_eq!(
            summary,
            [
                ("Garden.薔薇", "plugin_not_installed", None),
                // An enabled name that still failed is reported, not hidden.
                ("Nature.若葉", "plugin_not_installed", None),
                ("nature.若葉", "plugin_name_mismatch", Some("Nature.若葉")),
                ("Studio.若葉", "plugin_name_mismatch", Some("Nature.若葉")),
                ("Nature.若菜", "plugin_name_mismatch", Some("Nature.若葉")),
                ("Old.Mark", "plugin_disabled", None),
                ("Nature.紅葉", "plugin_version_mismatch", None),
            ]
        );
        let bytes = explain_plugin_diagnostics(
            serde_json::to_vec(&json!({"source": source, "upstream_diagnostics": diagnostics}))
                .unwrap(),
        );
        let output: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(output["schema"], SCHEMA);
        assert_eq!(output["plugins"].as_array().unwrap().len(), 7);
        assert!(
            String::from_utf8(explain_plugin_diagnostics(b"{}".to_vec()))
                .unwrap()
                .contains("invalid_plugin_diagnostics_input")
        );
    }
}
