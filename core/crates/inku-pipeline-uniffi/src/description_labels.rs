//! The author's labels, cut before a description reaches any layer.
//!
//! The rule is Server's `description_labels.py`: a leading number orders lines
//! in a batch and a bracketed comment names a source. Both stay in the saved
//! work and neither is drawn. Hosts that do not pass through Server (Android,
//! the description meter) call this one copy.

use regex::Regex;
use std::sync::LazyLock;

fn regex(pattern: &str) -> Regex {
    Regex::new(pattern).expect("static description label pattern")
}

/// The labels' byte ranges in `text`, each with its kind, in order.
fn byte_spans(text: &str) -> Vec<(usize, usize, &'static str)> {
    static NUMBER: LazyLock<Regex> =
        LazyLock::new(|| regex(r"^[ \t]*[0-9０-９]+[.．、)）:：　][ \t　]*"));
    static COMMENT: LazyLock<Regex> = LazyLock::new(|| regex(r"\[[^\[\]\n]*\]|［[^［］\n]*］"));
    let mut spans = Vec::new();
    let mut offset = 0;
    for line in text.split_inclusive('\n') {
        if let Some(found) = NUMBER.find(line) {
            spans.push((offset + found.start(), offset + found.end(), "number"));
        }
        spans.extend(
            COMMENT
                .find_iter(line)
                .map(|m| (offset + m.start(), offset + m.end(), "comment")),
        );
        offset += line.len();
    }
    spans.sort_unstable();
    spans
}

/// Every range the drawing does not read, as `[[start, end, kind], ...]` JSON.
///
/// Offsets count Unicode scalar values, as Server's `excluded_spans` counts
/// Python characters, so an editor can paint exactly what is dropped.
pub fn description_label_spans(text: &str) -> String {
    let mut byte_cursor = 0;
    let mut scalar_cursor = 0;
    let spans: Vec<serde_json::Value> = byte_spans(text)
        .into_iter()
        .map(|(start, end, kind)| {
            scalar_cursor += text[byte_cursor..start].chars().count();
            let scalar_start = scalar_cursor;
            scalar_cursor += text[start..end].chars().count();
            byte_cursor = end;
            serde_json::json!([scalar_start, scalar_cursor, kind])
        })
        .collect();
    serde_json::Value::Array(spans).to_string()
}

/// Comment contents, with Python-compatible whitespace removed.
pub fn description_source_labels(text: &str) -> String {
    let labels: Vec<&str> = byte_spans(text)
        .into_iter()
        .filter(|(_, _, kind)| *kind == "comment")
        .filter_map(|(start, end, _)| {
            let comment = &text[start..end];
            let inner = &comment[comment.chars().next()?.len_utf8()
                ..comment.len() - comment.chars().next_back()?.len_utf8()];
            let label = inku_pipeline::identity::python_strip(inner);
            (!label.is_empty()).then_some(label)
        })
        .collect();
    serde_json::to_string(&labels).expect("string array serializes")
}

/// Whether the words read by the pipeline differ, ignoring labels and spacing.
pub fn description_rewords(text: &str, description: &str) -> bool {
    fn words(value: &str) -> String {
        pipeline_description(value)
            .split(inku_pipeline::identity::is_python_space)
            .filter(|word| !word.is_empty())
            .collect::<Vec<_>>()
            .join(" ")
    }
    words(text) != words(description)
}

/// The description with its labels removed, as every layer reads it.
pub fn pipeline_description(text: &str) -> String {
    let spans = byte_spans(text);
    if spans.is_empty() {
        return text.to_owned();
    }
    let mut kept = String::new();
    let mut at = 0;
    for (start, end, _kind) in spans {
        kept.push_str(&text[at..start]);
        at = end;
    }
    kept.push_str(&text[at..]);
    let spaces = regex(r"[ \t　]{2,}");
    kept.split('\n')
        .map(|line| {
            spaces
                .replace_all(line, " ")
                .trim_matches([' ', '\t', '　'])
                .to_owned()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[cfg(test)]
mod tests {
    use super::{
        description_label_spans, description_rewords, description_source_labels,
        pipeline_description,
    };

    #[test]
    fn every_shared_case_cuts_what_server_cuts() {
        let table: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../server/tests/data/description-label-cases.json"
        ))
        .expect("shared label cases");
        let cases = table["cases"].as_array().expect("cases");
        assert!(!cases.is_empty());
        for case in cases {
            let text = case["text"].as_str().expect("text");
            let expected = case["pipeline"].as_str().expect("pipeline");
            assert_eq!(
                pipeline_description(text),
                expected,
                "{}",
                case["why"].as_str().unwrap_or(text)
            );
            let spans: serde_json::Value =
                serde_json::from_str(&description_label_spans(text)).expect("spans json");
            assert_eq!(
                spans,
                case["spans"],
                "{}",
                case["why"].as_str().unwrap_or(text)
            );
            let labels: serde_json::Value =
                serde_json::from_str(&description_source_labels(text)).unwrap();
            assert_eq!(labels, case["source_labels"], "{}", case["why"]);
        }
        for case in table["rewords_cases"].as_array().expect("rewords cases") {
            assert_eq!(
                description_rewords(
                    case["text"].as_str().unwrap(),
                    case["description"].as_str().unwrap()
                ),
                case["rewords"].as_bool().unwrap(),
                "{case}"
            );
        }
        eprintln!("compared {} shared label cases", cases.len());
    }

    #[test]
    fn long_multilingual_labels_match_the_previous_algorithm() {
        use std::time::Instant;

        fn previous(text: &str) -> String {
            let number = regex::Regex::new(r"^[ \t]*[0-9０-９]+[.．、)）:：　][ \t　]*").unwrap();
            let comment = regex::Regex::new(r"\[[^\[\]\n]*\]|［[^［］\n]*］").unwrap();
            let mut spans = Vec::new();
            let mut offset = 0;
            for line in text.split_inclusive('\n') {
                if let Some(m) = number.find(line) {
                    spans.push((offset + m.start(), offset + m.end(), "number"));
                }
                spans.extend(
                    comment
                        .find_iter(line)
                        .map(|m| (offset + m.start(), offset + m.end(), "comment")),
                );
                offset += line.len();
            }
            spans.sort_unstable();
            let offset = |byte| text[..byte].chars().count();
            serde_json::Value::Array(
                spans
                    .into_iter()
                    .map(|(start, end, kind)| serde_json::json!([offset(start), offset(end), kind]))
                    .collect(),
            )
            .to_string()
        }
        let text = (1..=1000)
            .map(|line| format!("{line}． 青い絵🎨 ［注釈{line}］ and [note {line}]\n"))
            .collect::<String>();
        let started = Instant::now();
        let expected = previous(&text);
        let before = started.elapsed();
        let started = Instant::now();
        let actual = description_label_spans(&text);
        let after = started.elapsed();
        assert_eq!(actual, expected);
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(&actual)
                .unwrap()
                .as_array()
                .unwrap()
                .len(),
            3000
        );
        eprintln!("description-labels-1000-lines previous={before:?} optimized={after:?}");
    }
}
