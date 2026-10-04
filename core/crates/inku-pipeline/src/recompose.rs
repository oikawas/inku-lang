//! Another composition read from the visible instructions alone (draw-system05,
//! the author's decisions of 2026-10-04).
//!
//! A work's composition is written into its instructions as ranges behind the
//! composition mark (`［構図］右下（横2/3〜1、縦2/3〜1）に`). Another composition
//! moves only those ranges: a place the description states is written without the
//! mark and stays, and a corner keeps its corner, since the instructions cannot
//! tell a corner the description names from one the composition chose.
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
//! instructions cannot recompose (no mark, a sentence a plan does not write, a
//! range the author wrote) is left as it is, with the reason.

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
    /// The words the sentence had after the mark, as written.
    pub from: String,
    pub to_key: String,
    /// The words the sentence has after the mark, as written.
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
    /// The source bytes of the range from the mark to its end, when it moves.
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
        let text = source
            .get(span.start_byte..span.end_byte)
            .ok_or("unsupported_sentence")?;
        let Some(offset) = text.find(mark(language)) else {
            return Err("author_range");
        };
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
            moving: Some(span.start_byte + offset..span.end_byte),
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
        let from = source[span.clone()].to_owned();
        rewritten.replace_range(span.clone(), &to);
        moves.push(RangeMove {
            layer: index,
            from_key: layer.current.map(|current| region_key(current).to_owned()),
            from: from[mark(language).len()..].trim_start().to_owned(),
            to_key: region_key(answer[index]).to_owned(),
            to: to[mark(language).len()..].trim_start().to_owned(),
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
