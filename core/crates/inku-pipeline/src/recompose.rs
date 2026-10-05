//! Another composition read from the visible instructions alone (draw-system05,
//! the author's decisions of 2026-10-04).
//!
//! A work's composition is written into its instructions as numeric ranges
//! (`右下（横2/3〜1、縦2/3〜1）に`). Another composition moves every numeric range,
//! whoever wrote it, as "change the layout" asks for the places to change (the
//! author's decision of 2026-10-05): a place the description states is written as a
//! place word and stays, and a corner keeps its corner, since the instructions
//! cannot tell a corner the description names from one the composition chose.
//! Works printed from Build 1155 to Build 1163 carry the mark `［構図］` before a
//! range; it is read as part of the range's words and goes when the range moves.
//!
//! Each sentence is read back as the work-plan layer it was printed from, and the
//! layers are solved with what the instructions alone tell (roles from how each
//! layer is drawn, no relations, the author's defaults), as the author chose over
//! saving the composition reading. Two modes:
//!
//! - principled: an answer other than the current one, among the near-best, else
//!   the best other one by score (the author's decision Q5);
//! - chance (automatism): each moving layer takes one of the ranges its kind
//!   allows, by a hash of the seed, the work and the layer.
//!
//! Only the text of the moving ranges changes; every other byte stays. A work the
//! instructions cannot recompose (no range to move, a sentence a plan does not
//! write) is left as it is, with the reason.

use inku_ddl::work_plan::{
    COMPOSITION_MARK_EN, COMPOSITION_MARK_JA, WorkPlanLayer, WorkPlanSlot, composition_background,
    composition_layer,
};
use inku_ddl::{
    CompilerLockState, MacroDefinition, MacroExpansionLimits, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, SemanticHead, compile_typed_ddl,
};
use serde::{Deserialize, Serialize};

use crate::composition::{
    self, OtherAnswer, chance_answer, corner_place, default_reading, fixed_region,
    is_composition_range, other_answer, region_key, region_of_bounds, written_range,
};

pub const RECOMPOSITION_SCHEMA_ID: &str = "inku.composition-recompose.v1";

/// How another composition chooses the moving ranges.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RecomposeMode {
    /// Follow the composition's principles: an answer other than the current one.
    Principled,
    /// Leave the ranges to chance (automatism).
    Chance,
}

/// One range that moved, in the order of the sentences.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct RangeMove {
    /// The moving sentence's place among the composed layers (0 is the first).
    pub layer: usize,
    /// The range the sentence had: its key when it is one of the composition's
    /// ranges, else `None`.
    pub from_key: Option<String>,
    /// The range the sentence had, as written (without an old mark).
    pub from: String,
    pub to_key: String,
    /// The range the sentence has now, as written.
    pub to: String,
}

/// The result: a recomposed source, or the reason the work is left as it is.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "outcome", rename_all = "snake_case")]
pub enum Recomposition {
    Recomposed {
        source: String,
        moves: Vec<RangeMove>,
        /// `near`, `next` or `chance`.
        answer: &'static str,
    },
    Unchanged {
        reason: &'static str,
    },
}

/// A sentence read back as a layer, with what its range allows.
struct ReadLayer {
    layer: WorkPlanLayer,
    /// The source bytes of the range, from its words to its end, when it moves.
    moving: Option<std::ops::Range<usize>>,
    /// The range it has now, when the instructions name one of the solver's.
    current: Option<usize>,
}

fn document(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> Option<NormalizedDdlDocument> {
    let mut locks = Vec::new();
    for definition in definitions {
        let identity = definition.identity().ok()?;
        locks.push(
            MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .and_then(|lock| lock.with_aliases(definition.alias_qualified_names()))
            .ok()?,
        );
    }
    NormalizedDdlDocument::new(source, language, locks).ok()
}

fn canonical(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    limits: MacroExpansionLimits,
) -> Option<inku_ddl::TypedDdlCompilation> {
    let compilation = compile_typed_ddl(
        document(source, language, definitions)?,
        definitions,
        None,
        limits,
    );
    compilation
        .compiler_lock
        .as_ref()
        .is_some_and(|lock| lock.state == CompilerLockState::CanonicalReady)
        .then_some(compilation)
}

const fn mark(language: ResolvedInstructionLanguage) -> &'static str {
    match language {
        ResolvedInstructionLanguage::Ja => COMPOSITION_MARK_JA,
        ResolvedInstructionLanguage::En => COMPOSITION_MARK_EN,
    }
}

/// A range as the moves show it: its text without the English article or an old
/// mark (`右下（横2/3〜1、縦2/3〜1）`, `bottom right (horizontal 2/3 to 1, ...)`).
fn shown(text: &str, language: ResolvedInstructionLanguage) -> String {
    let text = text.trim();
    let text = match language {
        ResolvedInstructionLanguage::Ja => text,
        ResolvedInstructionLanguage::En => text.strip_prefix("the ").unwrap_or(text),
    };
    text.strip_prefix(mark(language))
        .unwrap_or(text)
        .trim_start()
        .to_owned()
}

/// Read every sentence back as a layer, or say why the work cannot be recomposed.
fn read_layers(
    source: &str,
    language: ResolvedInstructionLanguage,
    ast: &inku_ddl::SemanticDocumentAst,
) -> Result<Vec<ReadLayer>, &'static str> {
    if !ast.coordinated_head_groups.is_empty()
        || !ast.group_predicates.is_empty()
        || !ast.continuations.is_empty()
    {
        return Err("unsupported_sentence");
    }
    let mut read = Vec::new();
    for instruction in &ast.instructions {
        let range = instruction.entity.numeric_range.as_ref();
        if matches!(instruction.entity.head, SemanticHead::MacroInvocation(_)) {
            // A plugin word is not a plan layer and the composition never places it.
            if range.is_some() || instruction.position.is_some() {
                return Err("unsupported_sentence");
            }
            continue;
        }
        let mut layer = composition_layer(instruction).ok_or("unsupported_sentence")?;
        let Some(range) = range else {
            if layer.attributes.contains_key(&WorkPlanSlot::Position) {
                read.push(ReadLayer {
                    layer,
                    moving: None,
                    current: None,
                });
                continue;
            }
            return Err("unplaced_sentence");
        };
        let span = range.source().span;
        source
            .get(span.start_byte..span.end_byte)
            .ok_or("unsupported_sentence")?;
        let bounds = range
            .bounds
            .map(|value| (value.numerator(), value.denominator()));
        let region = region_of_bounds(bounds);
        if let Some(place) = region.and_then(corner_place) {
            // A corner keeps its corner: the description may have named it (I-712).
            layer
                .attributes
                .insert(WorkPlanSlot::Position, place.to_owned());
            read.push(ReadLayer {
                layer,
                moving: None,
                current: region,
            });
            continue;
        }
        read.push(ReadLayer {
            layer,
            moving: Some(span.start_byte..span.end_byte),
            current: region.filter(|index| is_composition_range(*index)),
        });
    }
    Ok(read)
}

/// The layers and the background a composition reads from the visible
/// instructions: one layer per sentence a plan writes, with the place the
/// instructions keep (a stated place, or a corner as a named corner); moving
/// ranges have no place. `Err` names why the work cannot be recomposed.
pub fn composition_layers(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    limits: MacroExpansionLimits,
) -> Result<(Vec<WorkPlanLayer>, String), &'static str> {
    let compilation = canonical(source, language, definitions, limits).ok_or("not_canonical")?;
    let semantic = compilation
        .semantic_document
        .as_ref()
        .ok_or("not_canonical")?;
    let read = read_layers(source, language, &semantic.ast)?;
    let background = semantic
        .ast
        .background
        .as_ref()
        .and_then(composition_background)
        .unwrap_or_else(|| "white".to_owned());
    Ok((
        read.into_iter().map(|layer| layer.layer).collect(),
        background,
    ))
}

/// Recompose a work from its visible instructions alone.
#[must_use]
pub fn recompose(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    limits: MacroExpansionLimits,
    mode: RecomposeMode,
    seed: u64,
    work_id: &str,
) -> Recomposition {
    let unchanged = |reason| Recomposition::Unchanged { reason };
    let Some(compilation) = canonical(source, language, definitions, limits) else {
        return unchanged("not_canonical");
    };
    let Some(semantic) = compilation.semantic_document.as_ref() else {
        return unchanged("not_canonical");
    };
    let read = match read_layers(source, language, &semantic.ast) {
        Ok(read) => read,
        Err(reason) => return unchanged(reason),
    };
    if !read.iter().any(|layer| layer.moving.is_some()) {
        return unchanged("nothing_to_move");
    }
    let layers: Vec<WorkPlanLayer> = read.iter().map(|layer| layer.layer.clone()).collect();
    let background = semantic
        .ast
        .background
        .as_ref()
        .and_then(composition_background)
        .unwrap_or_else(|| "white".to_owned());
    let reading = default_reading(&layers);
    let (answer, kind) = match mode {
        RecomposeMode::Principled => {
            let Ok(searched) = composition::search(&layers, &reading, &background) else {
                return unchanged("unsolved");
            };
            // The current answer, when every range is one the solver knows.
            let current: Option<Vec<usize>> = read
                .iter()
                .enumerate()
                .map(|(index, layer)| {
                    if layer.moving.is_some() {
                        layer.current
                    } else {
                        reading
                            .fixed
                            .get(&index)
                            .and_then(|place| fixed_region(place))
                    }
                })
                .collect();
            match other_answer(
                &layers,
                &reading,
                &background,
                &searched,
                current.as_deref(),
                seed,
                work_id,
            ) {
                Ok((_, OtherAnswer::None)) => return unchanged("no_other_answer"),
                Ok((answer, OtherAnswer::Near)) => (answer, "near"),
                Ok((answer, OtherAnswer::Next)) => (answer, "next"),
                Err(_) => return unchanged("unsolved"),
            }
        }
        RecomposeMode::Chance => match chance_answer(&layers, &reading.fixed, seed, work_id) {
            Ok(answer) => (answer, "chance"),
            Err(_) => return unchanged("unsolved"),
        },
    };
    let mut rewritten = source.to_owned();
    let mut moves = Vec::new();
    for (index, layer) in read.iter().enumerate().rev() {
        let Some(span) = &layer.moving else {
            continue;
        };
        if layer.current == Some(answer[index]) {
            continue;
        }
        let Some(range) = written_range(answer[index]) else {
            return unchanged("unsolved");
        };
        let to = range.written(language);
        let replacement = match language {
            ResolvedInstructionLanguage::Ja => to.clone(),
            // The range's words follow the place preposition: `at the top left (...)`.
            ResolvedInstructionLanguage::En => format!("the {to}"),
        };
        let from = shown(&source[span.clone()], language);
        rewritten.replace_range(span.clone(), &replacement);
        moves.push(RangeMove {
            layer: index,
            from_key: layer.current.map(|current| region_key(current).to_owned()),
            from,
            to_key: region_key(answer[index]).to_owned(),
            to,
        });
    }
    if moves.is_empty() {
        return unchanged("same_ranges");
    }
    moves.reverse();
    if canonical(&rewritten, language, definitions, limits).is_none() {
        return unchanged("not_canonical_after");
    }
    Recomposition::Recomposed {
        source: rewritten,
        moves,
        answer: kind,
    }
}

/// The host request: the pipeline configuration the host draws the work with,
/// the visible source, the mode, the seed and the work's identity.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RecomposeRequest {
    pub config: crate::machine::PipelineConfig,
    pub source: String,
    pub mode: RecomposeMode,
    pub seed: crate::protocol::DecimalU64,
    pub work_id: String,
}

#[derive(Serialize)]
struct RecomposeResponse<'a> {
    schema: &'static str,
    #[serde(flatten)]
    result: &'a Recomposition,
}

/// JSON in, JSON out, for the hosts' bindings. A request that cannot be read
/// answers `{"error": "invalid_request"}`.
#[must_use]
pub fn recompose_json(input: &[u8]) -> Vec<u8> {
    let Ok(request) = serde_json::from_slice::<RecomposeRequest>(input) else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let Ok(limits) = request.config.compiler.macro_limits() else {
        return br#"{"error":"invalid_request"}"#.to_vec();
    };
    let result = recompose(
        &request.source,
        request.config.language,
        &request.config.definitions,
        limits,
        request.mode,
        request.seed.get(),
        &request.work_id,
    );
    serde_json::to_vec(&RecomposeResponse {
        schema: RECOMPOSITION_SCHEMA_ID,
        result: &result,
    })
    .unwrap_or_else(|_| br#"{"error":"internal"}"#.to_vec())
}

pub const COMPOSITION_RANGES_SCHEMA_ID: &str = "inku.composition-ranges.v1";

#[derive(Serialize)]
struct RangeWords<'a> {
    ja: &'a str,
    en: &'a str,
}

#[derive(Serialize)]
struct RangeEntry<'a> {
    key: &'a str,
    words: RangeWords<'a>,
    bounds: [(u32, u32); 4],
    corner: bool,
}

#[derive(Serialize)]
struct RangesResponse<'a> {
    schema: &'static str,
    ranges: Vec<RangeEntry<'a>>,
}

/// The named ranges as JSON, for the hosts' display of the instructions: the 28
/// composition ranges and the four corners, each with its key, its words in both
/// languages, its bounds (left, top, right, bottom as `[numerator, denominator]`)
/// and whether it is a corner another composition keeps.
#[must_use]
pub fn composition_ranges_json() -> String {
    let ranges = composition::named_ranges();
    serde_json::to_string(&RangesResponse {
        schema: COMPOSITION_RANGES_SCHEMA_ID,
        ranges: ranges
            .iter()
            .map(|range| RangeEntry {
                key: range.key,
                words: RangeWords {
                    ja: &range.words_ja,
                    en: &range.words_en,
                },
                bounds: range.bounds,
                corner: range.corner,
            })
            .collect(),
    })
    .expect("the named ranges serialize")
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::{
        COMPOSITION_RANGES_SCHEMA_ID, RECOMPOSITION_SCHEMA_ID, composition_ranges_json,
        recompose_json,
    };

    /// The hosts call the JSON entry with the configuration they run the work
    /// with, the saved source, the mode, the candidate's seed as a decimal and
    /// the work's identity (Server and Android, 2026-10-05); their own tests
    /// answer for the core. en-01 by principle gives the fixture's answer.
    #[test]
    fn the_json_entry_reads_the_request_a_host_sends() {
        let fixture: Value = serde_json::from_str(include_str!("../tests/data/recompose-v1.json"))
            .expect("the fixture is JSON");
        let case = fixture["cases"]
            .as_array()
            .expect("cases")
            .iter()
            .find(|case| case["id"] == "en-01")
            .expect("en-01");
        let request = |seed: Value| {
            serde_json::to_vec(&json!({
                "config": crate::focused_flow::config(),
                "source": case["source"],
                "mode": "principled",
                "seed": seed,
                "work_id": "en-01",
            }))
            .expect("a request")
        };
        let answer: Value =
            serde_json::from_slice(&recompose_json(&request(json!("1")))).expect("JSON");
        assert_eq!(answer["schema"], RECOMPOSITION_SCHEMA_ID);
        assert_eq!(answer["outcome"], "recomposed");
        assert_eq!(answer["source"], case["principled"]["source"]);
        assert_eq!(answer["answer"], "near");
        // The seed is the candidate's, as a decimal: a request without one is not read.
        assert_eq!(
            recompose_json(&request(Value::Null)),
            br#"{"error":"invalid_request"}"#
        );
    }

    /// The hosts read the named ranges as JSON (Server and Android display): the
    /// 28 composition ranges and the four corners, each written as the printer
    /// writes it, so a printed range is found in the table by its words and numbers.
    #[test]
    fn the_named_ranges_are_the_ones_the_printer_writes() {
        let table: Value = serde_json::from_str(&composition_ranges_json()).expect("JSON");
        assert_eq!(table["schema"], COMPOSITION_RANGES_SCHEMA_ID);
        let ranges = table["ranges"].as_array().expect("ranges");
        assert_eq!(ranges.len(), 32);
        assert_eq!(
            ranges
                .iter()
                .filter(|range| range["corner"] == true)
                .count(),
            4
        );
        let bottom_right = ranges
            .iter()
            .find(|range| range["key"] == "cell-22")
            .expect("cell-22");
        assert_eq!(
            bottom_right["words"],
            json!({"ja": "右下", "en": "bottom right"})
        );
        assert_eq!(
            bottom_right["bounds"],
            json!([[2, 3], [2, 3], [1, 1], [1, 1]])
        );
        let corner = ranges
            .iter()
            .find(|range| range["key"] == "corner-tr")
            .expect("corner-tr");
        assert_eq!(corner["words"]["ja"], "右上の隅");
        assert_eq!(corner["bounds"], json!([[4, 5], [0, 1], [1, 1], [1, 5]]));
        for (index, range) in ranges.iter().enumerate() {
            let written = crate::composition::written_range(
                crate::composition::region_of_bounds(
                    range["bounds"]
                        .as_array()
                        .expect("bounds")
                        .iter()
                        .map(|bound| (bound[0].as_u64().expect("n"), bound[1].as_u64().expect("d")))
                        .collect::<Vec<_>>()
                        .try_into()
                        .expect("four bounds"),
                )
                .expect("a named range is found by its bounds"),
            )
            .expect("written");
            assert_eq!(range["words"]["ja"], written.words_ja.as_str(), "{index}");
            assert_eq!(range["words"]["en"], written.words_en.as_str(), "{index}");
        }
    }
}
