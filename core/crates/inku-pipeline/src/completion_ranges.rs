//! The states of a work's completion ranges, for the hosts' instruction editors
//! (A3, the author's choice of 2026-10-11: a short tag after each range the
//! record knows, and one line under the editor while a range's words were
//! changed).
//!
//! The answer comes from the same matching the pipeline uses when the
//! instructions are drawn, so what an editor shows is what drawing does.

use inku_ddl::completion_record::fraction_text;
use inku_ddl::{
    CompletionRangeRecord, ExactFraction, compile_typed_ddl, match_completion_ranges,
    written_ranges,
};
use serde::{Deserialize, Serialize};

pub const COMPLETION_RANGE_STATES_SCHEMA_ID: &str = "inku.completion-range-states.v1";

/// The host request: the pipeline configuration the host draws the work with,
/// the visible source as it is in the editor, and the work's record.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CompletionRangeStatesRequest {
    pub config: crate::machine::PipelineConfig,
    pub source: String,
    pub completion_ranges: CompletionRangeRecord,
}

#[derive(Serialize)]
struct Recorded {
    words: String,
    horizontal: [String; 2],
    vertical: [String; 2],
}

/// One range the record knows. `start` and `end` are UTF-8 byte offsets and
/// `utf16_start` and `utf16_end` UTF-16 offsets, from the range's words to its
/// closing parenthesis.
#[derive(Serialize)]
struct RangeState {
    start: usize,
    end: usize,
    utf16_start: usize,
    utf16_end: usize,
    words: String,
    horizontal: [String; 2],
    vertical: [String; 2],
    state: &'static str,
    recorded: Recorded,
}

#[derive(Serialize)]
struct StatesResponse {
    schema: &'static str,
    ranges: Vec<RangeState>,
}

fn axis(bounds: [ExactFraction; 2]) -> [String; 2] {
    bounds.map(fraction_text)
}

/// JSON in, JSON out, for the hosts' bindings: the ranges the record knows, in
/// source order, each with its state (`completed`, `numbers_changed` or
/// `words_changed`). A range the record does not know is left out. A request
/// that cannot be read answers `{"error": "invalid_request"}`.
#[must_use]
pub fn completion_range_states_json(input: &[u8]) -> Vec<u8> {
    let Ok(request) = serde_json::from_slice::<CompletionRangeStatesRequest>(input) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let Ok(limits) = request.config.compiler.macro_limits() else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let Some(document) = crate::recompose::document(
        &request.source,
        request.config.language,
        &request.config.definitions,
    ) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let compilation = compile_typed_ddl(document, &request.config.definitions, None, limits);
    let source = compilation.document.source();
    let utf16 = |byte: usize| source[..byte].encode_utf16().count();
    let ranges = match_completion_ranges(&written_ranges(&compilation), &request.completion_ranges)
        .into_iter()
        .map(|found| {
            let recorded = &request.completion_ranges.ranges[found.recorded];
            RangeState {
                start: found.range.span.start_byte,
                end: found.range.span.end_byte,
                utf16_start: utf16(found.range.span.start_byte),
                utf16_end: utf16(found.range.span.end_byte),
                words: found.range.words,
                horizontal: axis(found.range.horizontal),
                vertical: axis(found.range.vertical),
                state: found.state.as_str(),
                recorded: Recorded {
                    words: recorded.words.clone(),
                    horizontal: axis(recorded.horizontal),
                    vertical: axis(recorded.vertical),
                },
            }
        })
        .collect();
    serde_json::to_vec(&StatesResponse {
        schema: COMPLETION_RANGE_STATES_SCHEMA_ID,
        ranges,
    })
    .unwrap_or_else(|_| br#"{"error":"internal"}"#.to_vec())
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::{COMPLETION_RANGE_STATES_SCHEMA_ID, completion_range_states_json};

    /// The hosts send the configuration they draw with, the editor's text and
    /// the work's record; the answer names each recorded range's state with its
    /// place in UTF-8 bytes and in UTF-16, after text with characters of both
    /// widths (T6).
    #[test]
    fn the_json_entry_names_each_recorded_range_and_its_place() {
        let source = "黒い背景に、白い四角を中心に置く。左上（横2/3〜1、縦2/3〜1）に、赤い小さな円を置く。上の方（横0〜1、縦0〜2/5）に、青い線を引く。";
        let record = json!({
            "schema": "inku.completion-ranges.v1",
            "ranges": [
                {"words": "右下", "horizontal": ["2/3", "1"], "vertical": ["2/3", "1"],
                 "sentence": "￼に、赤い小さな円を置く"},
                {"words": "上の方", "horizontal": ["0", "1"], "vertical": ["0", "1/3"],
                 "sentence": "￼に、青い線を引く"},
            ],
        });
        let mut config = crate::focused_flow::config();
        config.language = inku_ddl::ResolvedInstructionLanguage::Ja;
        let request = |source: Value, record: Value| {
            serde_json::to_vec(&json!({
                "config": config,
                "source": source,
                "completion_ranges": record,
            }))
            .expect("a request")
        };
        let answer: Value = serde_json::from_slice(&completion_range_states_json(&request(
            json!(source),
            record.clone(),
        )))
        .expect("JSON");
        assert_eq!(answer["schema"], COMPLETION_RANGE_STATES_SCHEMA_ID);
        let ranges = answer["ranges"].as_array().expect("ranges");
        assert_eq!(ranges.len(), 2, "{answer}");
        for (range, words, state) in [
            (&ranges[0], "左上", "words_changed"),
            (&ranges[1], "上の方", "numbers_changed"),
        ] {
            let start = range["start"].as_u64().unwrap() as usize;
            let end = range["end"].as_u64().unwrap() as usize;
            assert!(source[start..end].starts_with(words), "{range}");
            assert!(source[start..end].ends_with('）'), "{range}");
            let utf16 = |byte: usize| source[..byte].encode_utf16().count() as u64;
            assert_eq!(range["utf16_start"], utf16(start));
            assert_eq!(range["utf16_end"], utf16(end));
            assert_eq!(range["state"], state);
        }
        assert_eq!(ranges[0]["recorded"]["words"], "右下");
        assert_eq!(ranges[1]["vertical"], json!(["0", "2/5"]));
        assert_eq!(
            completion_range_states_json(&request(json!(source), json!({"ranges": []}))),
            br#"{"error":"invalid_request"}"#
        );
    }
}
