//! The author's labels, cut before a description reaches any layer.
//!
//! The rule is Server's `description_labels.py`: a leading number orders lines
//! in a batch and a bracketed comment names a source. Both stay in the saved
//! work and neither is drawn. Hosts that do not pass through Server (Android,
//! the description meter) call this one copy.

use regex::Regex;

fn regex(pattern: &str) -> Regex {
    Regex::new(pattern).expect("static description label pattern")
}

/// The description with its labels removed, as every layer reads it.
pub fn pipeline_description(text: &str) -> String {
    let number = regex(r"^[ \t]*[0-9０-９]+[.．、)）:：　][ \t　]*");
    let comment = regex(r"\[[^\[\]\n]*\]|［[^［］\n]*］");
    let mut spans = Vec::new();
    let mut offset = 0;
    for line in text.split_inclusive('\n') {
        if let Some(found) = number.find(line) {
            spans.push((offset + found.start(), offset + found.end()));
        }
        spans.extend(
            comment
                .find_iter(line)
                .map(|m| (offset + m.start(), offset + m.end())),
        );
        offset += line.len();
    }
    if spans.is_empty() {
        return text.to_owned();
    }
    spans.sort_unstable();
    let mut kept = String::new();
    let mut at = 0;
    for (start, end) in spans {
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
    use super::pipeline_description;

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
        }
        eprintln!("compared {} shared label cases", cases.len());
    }
}
