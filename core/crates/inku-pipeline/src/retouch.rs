//! Another touch written into a work's visible instructions (the author, 2026-10-14).
//!
//! The touches (てざわり) are the drawing tools of the saijiki: silverpoint,
//! pencil, pen and the others. A work's sentences are read back; a sentence whose
//! head is a shape names its tool, or is drawn with the default one. The host asks
//! for a tool per sentence, and the answer is the source with only those words
//! changed: a written tool word is replaced, and a sentence without one gets the
//! new word just before its shape (`チョークの円`, `chalk circles`). The new source
//! is compiled again and read back; an answer is given only when every asked
//! sentence reads the asked tool and every other sentence reads as before.
//!
//! The host draws the saved Score with the new tools and keeps this source as the
//! child's instructions, so the drawing changes only where the tools changed.

use std::collections::BTreeMap;
use std::ops::Range;

use inku_ddl::{
    MacroDefinition, MacroExpansionLimits, ResolvedInstructionLanguage, SemanticHead,
    SemanticInstruction, saijiki_asset,
};
use serde::{Deserialize, Serialize};

use crate::laws_record::{LawsLayerRecord, applying};
use crate::recompose::canonical;

pub const RETOUCH_SCHEMA_ID: &str = "inku.touch-change.v1";

const TOUCH_CATEGORY: &str = "tezawari";

/// A tool by its Score value with its words in both languages, in the saijiki's order.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Tool {
    pub value: String,
    pub ja: String,
    pub en: String,
}

/// The tools a sentence can be drawn with.
#[must_use]
pub fn tools() -> Vec<Tool> {
    saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == TOUCH_CATEGORY)
        .map(|category| {
            category
                .words
                .iter()
                .filter_map(|word| {
                    Some(Tool {
                        value: word.score_value.clone()?,
                        ja: word.surface_ja.clone(),
                        en: word.surface_en.clone()?,
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

/// One sentence whose tool can change: its instruction index (the Score's
/// `owner.instruction_index`) and the tool it names, if it names one.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct TouchSentence {
    pub index: usize,
    pub tool: Option<String>,
}

/// The answer: the sentences read back, and the rewritten source when tools were asked.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "outcome", rename_all = "snake_case")]
pub enum Retouch {
    Read {
        sentences: Vec<TouchSentence>,
    },
    Retouched {
        sentences: Vec<TouchSentence>,
        source: String,
    },
    Unchanged {
        reason: &'static str,
    },
}

/// A sentence a tool can be written into: a shape drawn by itself, whose tool is
/// not set by a sequence of its own.
fn changeable(instruction: &SemanticInstruction) -> bool {
    matches!(instruction.entity.head, SemanticHead::Primitive(_))
        && (instruction.entity.touch.is_some() || instruction.sequence.is_none())
}

fn read(instructions: &[SemanticInstruction]) -> Vec<TouchSentence> {
    instructions
        .iter()
        .enumerate()
        .filter(|(_, instruction)| changeable(instruction))
        .map(|(index, instruction)| TouchSentence {
            index,
            tool: instruction
                .entity
                .touch
                .as_ref()
                .map(|term| term.identity.id.clone()),
        })
        .collect()
}

fn touches(instructions: &[SemanticInstruction]) -> Vec<(String, Option<String>)> {
    instructions
        .iter()
        .map(|instruction| {
            (
                instruction.entity.head.source().surface.clone(),
                instruction
                    .entity
                    .touch
                    .as_ref()
                    .map(|term| term.identity.id.clone()),
            )
        })
        .collect()
}

/// Read a work's sentences back and, when `asked` names a tool for some of them,
/// write those tools into the source.
#[must_use]
pub fn retouch(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    limits: MacroExpansionLimits,
    asked: &BTreeMap<usize, String>,
) -> Retouch {
    retouch_with_edits(source, language, definitions, limits, asked).0
}

/// [`retouch`], with the record of the layers a work's laws placed written for
/// the retouched source (2026-10-20). The record names its layers by their
/// sentences, so a tool word changed in a recorded sentence is changed in the
/// record too; otherwise the child's record no longer meets its own source, and
/// "change the layout" moves the laws' layers or refuses. A layer the source
/// does not hold, and every layer when nothing was retouched, stays as it was.
#[must_use]
pub fn retouch_with_record(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    limits: MacroExpansionLimits,
    asked: &BTreeMap<usize, String>,
    record: &LawsLayerRecord,
) -> (Retouch, LawsLayerRecord) {
    let (answer, edits) = retouch_with_edits(source, language, definitions, limits, asked);
    let record = match &answer {
        Retouch::Retouched {
            source: changed, ..
        } => rewritten(record, source, changed, &edits),
        _ => record.clone(),
    };
    (answer, record)
}

/// One rewrite of the source: the bytes `start..end` replaced by the text.
type Edit = (usize, usize, String);

/// Each recorded sentence the source holds, read again where the edits moved it.
fn rewritten(
    record: &LawsLayerRecord,
    before: &str,
    after: &str,
    edits: &[Edit],
) -> LawsLayerRecord {
    let mut layers = record.layers.clone();
    for (index, ranges) in applying(record, before) {
        let sentences: Option<Vec<String>> = ranges
            .iter()
            .map(|range| {
                moved(range, edits)
                    .and_then(|range| after.get(range))
                    .map(str::to_owned)
            })
            .collect();
        if let Some(sentences) = sentences {
            layers[index].sentences = sentences;
        }
    }
    LawsLayerRecord { layers }
}

/// Where a sentence's bytes are after the edits: an edit before it shifts it,
/// and one inside it (a tool word, or one written before its shape) changes its
/// length. An edit across its edge has no answer.
fn moved(range: &Range<usize>, edits: &[Edit]) -> Option<Range<usize>> {
    let (mut shift, mut grow) = (0_isize, 0_isize);
    for (start, end, text) in edits {
        let delta = isize::try_from(text.len()).ok()? - isize::try_from(end - start).ok()?;
        if *end <= range.start && *start < range.start {
            shift += delta;
        } else if *start >= range.start && *start < range.end && *end <= range.end {
            grow += delta;
        } else if *start < range.end {
            return None;
        }
    }
    let start = range.start.checked_add_signed(shift)?;
    let end = range.end.checked_add_signed(shift + grow)?;
    Some(start..end)
}

fn retouch_with_edits(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    limits: MacroExpansionLimits,
    asked: &BTreeMap<usize, String>,
) -> (Retouch, Vec<Edit>) {
    let unchanged = |reason| (Retouch::Unchanged { reason }, Vec::new());
    let Some(compilation) = canonical(source, language, definitions, limits) else {
        return unchanged("not_canonical");
    };
    let Some(semantic) = compilation.semantic_document.as_ref() else {
        return unchanged("not_canonical");
    };
    let instructions = &semantic.ast.instructions;
    let sentences = read(instructions);
    if asked.is_empty() {
        return (Retouch::Read { sentences }, Vec::new());
    }
    let tools = tools();
    let mut edits = Vec::new();
    for (&index, value) in asked {
        let Some(tool) = tools.iter().find(|tool| tool.value == *value) else {
            return unchanged("unknown_tool");
        };
        let Some(instruction) = instructions
            .get(index)
            .filter(|instruction| changeable(instruction))
        else {
            return unchanged("unchangeable_sentence");
        };
        let word = match language {
            ResolvedInstructionLanguage::Ja => tool.ja.as_str(),
            ResolvedInstructionLanguage::En => tool.en.as_str(),
        };
        edits.push(match &instruction.entity.touch {
            Some(term) => {
                let span = term.provenance.source.span;
                (span.start_byte, span.end_byte, word.to_owned())
            }
            None => {
                let start = instruction.entity.head.source().span.start_byte;
                let written = match language {
                    ResolvedInstructionLanguage::Ja => format!("{word}の"),
                    ResolvedInstructionLanguage::En => format!("{word} "),
                };
                (start, start, written)
            }
        });
    }
    edits.sort_by_key(|(start, _, _)| std::cmp::Reverse(*start));
    let mut changed = source.to_owned();
    for (start, end, text) in &edits {
        if !changed.is_char_boundary(*start) || !changed.is_char_boundary(*end) {
            return unchanged("unverified");
        }
        changed.replace_range(*start..*end, text);
    }
    // Read the new source back: each asked sentence names its tool, and every
    // other sentence keeps its shape and its tool.
    let Some(after) = canonical(&changed, language, definitions, limits) else {
        return unchanged("unverified");
    };
    let Some(after) = after.semantic_document.as_ref() else {
        return unchanged("unverified");
    };
    let before = touches(instructions);
    let now = touches(&after.ast.instructions);
    let expected: Vec<_> = before
        .iter()
        .enumerate()
        .map(|(index, (head, tool))| {
            (
                head.clone(),
                asked.get(&index).cloned().or_else(|| tool.clone()),
            )
        })
        .collect();
    if now != expected {
        return unchanged("unverified");
    }
    (
        Retouch::Retouched {
            sentences,
            source: changed,
        },
        edits,
    )
}

/// The host request: the pipeline configuration the host draws the work with, the
/// visible source, and the tool asked for each sentence by its instruction index
/// (none to read the sentences only).
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RetouchRequest {
    pub config: crate::machine::PipelineConfig,
    pub source: String,
    #[serde(default)]
    pub tools: BTreeMap<usize, String>,
}

#[derive(Serialize)]
struct RetouchResponse<'a> {
    schema: &'static str,
    #[serde(flatten)]
    result: &'a Retouch,
    tools: Vec<Tool>,
}

/// JSON in, JSON out, for the hosts' bindings. A request that cannot be read
/// answers `{"error": "invalid_request"}`.
#[must_use]
pub fn retouch_json(input: &[u8]) -> Vec<u8> {
    let Ok(request) = serde_json::from_slice::<RetouchRequest>(input) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let Ok(limits) = request.config.compiler.macro_limits() else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let result = retouch(
        &request.source,
        request.config.language,
        &request.config.definitions,
        limits,
        &request.tools,
    );
    serde_json::to_vec(&RetouchResponse {
        schema: RETOUCH_SCHEMA_ID,
        result: &result,
        tools: tools(),
    })
    .unwrap_or_else(|_| br#"{"error":"internal"}"#.to_vec())
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::{RETOUCH_SCHEMA_ID, retouch_json};

    fn answer(source: &str, language: &str, tools: Value) -> Value {
        let mut config = crate::focused_flow::config();
        config.language = serde_json::from_value(json!(language)).expect("a language");
        let request =
            serde_json::to_vec(&json!({"config": config, "source": source, "tools": tools}))
                .expect("a request");
        serde_json::from_slice(&retouch_json(&request)).expect("JSON")
    }

    #[test]
    fn the_saijiki_names_twelve_tools() {
        let read = answer("背景を白で埋める。", "ja", json!({}));
        assert_eq!(read["schema"], RETOUCH_SCHEMA_ID);
        let tools = read["tools"].as_array().expect("tools");
        assert_eq!(tools.len(), 12);
        assert_eq!(
            tools[0],
            json!({"value": "silverpoint", "ja": "銀筆", "en": "silverpoint"})
        );
    }

    #[test]
    fn a_written_tool_is_replaced_and_a_missing_one_is_written_before_the_shape() {
        let source = "背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。";
        let read = answer(source, "ja", json!({}));
        assert_eq!(read["outcome"], "read", "{read}");
        assert_eq!(
            read["sentences"],
            json!([{"index": 0, "tool": "brush_thin"}, {"index": 1, "tool": null}])
        );
        let changed = answer(source, "ja", json!({"0": "chalk", "1": "chalk"}));
        assert_eq!(changed["outcome"], "retouched", "{changed}");
        assert_eq!(
            changed["source"],
            "背景を白で埋める。\n青のチョークの線を3個引く。\n赤の大きなチョークの円を1個置く。"
        );
        let one = answer(source, "ja", json!({"1": "oil_paint"}));
        assert_eq!(
            one["source"],
            "背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな油彩の円を1個置く。"
        );
    }

    #[test]
    fn english_sentences_take_the_english_words() {
        let source = "Fill the background with black.\nScatter 9 green thin fine-brush small lines.\nPlace one gray large cloudform.";
        let changed = answer(source, "en", json!({"0": "drypoint", "1": "oil_paint"}));
        assert_eq!(changed["outcome"], "retouched", "{changed}");
        assert_eq!(
            changed["source"],
            "Fill the background with black.\nScatter 9 green thin drypoint small lines.\nPlace one gray large oil paint cloudform."
        );
    }

    #[test]
    fn a_request_outside_the_sentences_or_the_tools_is_not_written() {
        let source = "青の線を1個引く。";
        assert_eq!(
            answer(source, "ja", json!({"5": "chalk"}))["reason"],
            "unchangeable_sentence"
        );
        assert_eq!(
            answer(source, "ja", json!({"0": "crayons"}))["reason"],
            "unknown_tool"
        );
        assert_eq!(retouch_json(b"{}"), br#"{"error":"invalid_request"}"#);
    }
}
