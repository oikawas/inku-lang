//! The color stage on a composed read-and-draw work (2026-10-26): the work's
//! DDL read as the color stage reads a printed plan, the stage's request with
//! the thing each layer draws, and the chosen colors written back into the
//! DDL.
//!
//! The prototype is arm B of read-draw-laws-20261026 (the colors chosen after
//! the review, on the drawing the review left; the author found it better than
//! the drawing without them in 8 of 10 works with each model). Each sentence is
//! one layer, read without its numbers and given them as the color stage
//! prints them. A sentence whose color alone changes has its color word
//! rewritten where the parser read it, so the drawer's words stay; a sentence
//! otherwise changed (a cycle, a shift, a fade, a kasane, a size) is printed
//! again with its numbers; a chosen ground prints the background sentence. A
//! sentence the colors keep is not touched, nor is a sentence the compile left
//! out (it draws nothing and takes no colors; the layers are those drawn).

use inku_ddl::work_plan::{
    NumericPlace, NumericSize, NumericWriting, WorkPlan, WorkPlanLayer, WorkPlanSlot,
    print_work_plan_with_numbers,
};
use inku_ddl::{
    MacroDefinition, NormalizedDdlDocument, ParameterSchema, ResolvedInstructionLanguage,
    SemanticExplicitGeometry, SemanticGeometryValue, SemanticHead, SemanticInstruction,
    SemanticMacroParameterValue, compile_typed_ddl,
};
use std::collections::{BTreeMap, BTreeSet};

use inku_score::{Color, Score, ScoreSourceOwner};
use serde::{Deserialize, Serialize};

use crate::colors::{ColorsChosen, PrintedPlan};
use crate::description_laws::{LIMITS, fraction, layer_without_numbers, locked_document};
use crate::image_ddl::color_word;
use crate::prompts::{LlmPrompt, PromptError, PromptLimits};

/// A composed work's DDL as the color stage reads it: one plan layer for
/// each instruction, in the order the source writes them.
#[derive(Clone, Debug, PartialEq)]
pub struct DescribedPlan {
    pub printed: PrintedPlan,
    /// The line of the source each layer's sentence is written on.
    pub lines: Vec<usize>,
    /// Whether a layer's color word may be rewritten in place: its sentence
    /// reads as a layer and draws no color cycle.
    rewritable: Vec<bool>,
}

impl DescribedPlan {
    /// The plan of the sentences the compile drew (`drawn`, the source
    /// instructions its Score draws), in their order. A sentence the compile
    /// left out keeps its words and takes no colors. `None` when the compile
    /// drew none, or drew an instruction the plan does not read.
    #[must_use]
    pub fn drawn(self, drawn: &BTreeSet<usize>) -> Option<Self> {
        if drawn.is_empty() || drawn.iter().any(|index| *index >= self.lines.len()) {
            return None;
        }
        let printed = self.printed;
        Some(Self {
            printed: PrintedPlan {
                plan: WorkPlan {
                    layers: kept(printed.plan.layers, drawn),
                    ..printed.plan
                },
                ranges: kept(printed.ranges, drawn),
                joints: kept(printed.joints, drawn),
                numeric: kept(printed.numeric, drawn),
            },
            lines: kept(self.lines, drawn),
            rewritable: kept(self.rewritable, drawn),
        })
    }
}

fn kept<T>(items: Vec<T>, drawn: &BTreeSet<usize>) -> Vec<T> {
    items
        .into_iter()
        .enumerate()
        .filter(|(at, _)| drawn.contains(at))
        .map(|(_, item)| item)
        .collect()
}

/// The source instructions a Score draws, and the Score with their layers
/// numbered in order (0, 1, …) as the color stage numbers a printed plan's
/// layers. The renumbered Score serves the colors' estimate and checks only;
/// the work is drawn from its own compile, so a sentence left out moves
/// nothing.
#[must_use]
pub fn drawn_layers(score: &Score) -> (Score, BTreeSet<usize>) {
    let index_of = |owner: &ScoreSourceOwner| match owner {
        ScoreSourceOwner::SourceInstruction { instruction_index } => Some(*instruction_index),
        ScoreSourceOwner::MacroEmit {
            source_instruction_index,
            ..
        } => Some(*source_instruction_index),
        ScoreSourceOwner::OrdinaryGroup { .. } => None,
    };
    let drawn: BTreeSet<usize> = score
        .instructions
        .iter()
        .filter_map(|instruction| instruction.arrangement.as_ref()?.resolved.as_ref())
        .filter_map(|resolved| index_of(&resolved.owner))
        .collect();
    let rank: BTreeMap<usize, usize> = drawn
        .iter()
        .enumerate()
        .map(|(rank, index)| (*index, rank))
        .collect();
    let mut renumbered = score.clone();
    for resolved in renumbered
        .instructions
        .iter_mut()
        .filter_map(|instruction| instruction.arrangement.as_mut()?.resolved.as_mut())
    {
        match &mut resolved.owner {
            ScoreSourceOwner::SourceInstruction { instruction_index } => {
                *instruction_index = rank[&*instruction_index];
            }
            ScoreSourceOwner::MacroEmit {
                source_instruction_index,
                ..
            } => *source_instruction_index = rank[&*source_instruction_index],
            ScoreSourceOwner::OrdinaryGroup { .. } => {}
        }
    }
    (renumbered, drawn)
}

/// What one layer of a composed work draws: the thing its sentence draws (0
/// for a sentence of no thing) and the thing's name.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LayerThing {
    pub thing: u64,
    pub what: String,
}

/// How the colors wrote a line of the DDL.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ColorsChangeHow {
    /// The color word rewritten where the parser read it.
    ColorWord,
    /// The layer printed again with its numbers, a kasane's lower colors first.
    Printed,
    /// The background sentence printed with the chosen ground.
    Ground,
    /// A background sentence added after the ratio sentence.
    GroundAdded,
}

/// A line the colors wrote: the line of the DDL before them (none for an
/// added background), how, and the text before and after.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ColorsChange {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub line: Option<usize>,
    pub how: ColorsChangeHow,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub before: String,
    pub after: Vec<String>,
}

fn instructions_of_with_definitions(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> Vec<SemanticInstruction> {
    let Some(document) = locked_document(source, language, definitions) else {
        return Vec::new();
    };
    compile_typed_ddl(document, definitions, None, LIMITS)
        .semantic_document
        .map(|semantic| semantic.ast.instructions)
        .unwrap_or_default()
}

/// The line the background sentence is written on.
fn background_line_of(source: &str, language: ResolvedInstructionLanguage) -> Option<usize> {
    let document = NormalizedDdlDocument::new(source, language, Vec::new()).ok()?;
    let compilation = compile_typed_ddl(document, &[], None, LIMITS);
    let background = compilation.semantic_document?.ast.background?;
    Some(line_at(source, background.head.span.start_byte))
}

/// The line the byte `at` of the source is on.
fn line_at(source: &str, at: usize) -> usize {
    source.as_bytes()[..at.min(source.len())]
        .iter()
        .filter(|byte| **byte == b'\n')
        .count()
}

/// A sentence's numbers as the color stage prints them: its place (a point,
/// a range or two points), its first size, its turn and its fade.
fn numeric_of(instruction: &SemanticInstruction) -> NumericWriting {
    let entity = &instruction.entity;
    let mut numeric = NumericWriting::default();
    if let Some(segment) = &entity.numeric_segment {
        let ends = segment.ends.map(fraction);
        numeric.place = Some(NumericPlace::Segment {
            from: [ends[0], ends[1]],
            to: [ends[2], ends[3]],
        });
    } else if let Some(range) = &entity.numeric_range {
        numeric.place = Some(NumericPlace::Range {
            bounds: range.bounds.map(fraction),
        });
    } else if let Some(position) = &entity.numeric_position
        && let (Ok(x), Ok(y)) = (
            position.x.decimal.value.to_f64(),
            position.y.decimal.value.to_f64(),
        )
    {
        numeric.place = Some(NumericPlace::Point { at: [x, y] });
    }
    let value = |value: &SemanticGeometryValue| value.decimal.value.to_f64().ok();
    if let Some(geometry) = entity
        .explicit_geometry
        .iter()
        .chain(&entity.additional_explicit_geometries)
        .next()
    {
        numeric.size = match geometry {
            SemanticExplicitGeometry::Radius(radius) => {
                value(radius).map(|radius| NumericSize::Radius { radius })
            }
            SemanticExplicitGeometry::Diameter(diameter) => {
                value(diameter).map(|diameter| NumericSize::Radius {
                    radius: diameter / 2.0,
                })
            }
            SemanticExplicitGeometry::Length(length) => {
                value(length).map(|length| NumericSize::Length { length })
            }
            SemanticExplicitGeometry::Side(side) => {
                value(side).map(|side| NumericSize::Side { side })
            }
            SemanticExplicitGeometry::WidthHeight { width, height } => {
                match (value(width), value(height)) {
                    (Some(width), Some(height)) => Some(NumericSize::WidthHeight { width, height }),
                    _ => None,
                }
            }
            SemanticExplicitGeometry::ChordSagitta { chord, sagitta } => {
                match (value(chord), value(sagitta)) {
                    (Some(chord), Some(sagitta)) => {
                        Some(NumericSize::ChordSagitta { chord, sagitta })
                    }
                    _ => None,
                }
            }
        };
    }
    numeric.turn = entity
        .numeric_angle
        .as_ref()
        .map(|angle| fraction(angle.degrees));
    numeric.fade = entity.fade.as_ref().map(|fade| fade.direction);
    numeric
}

/// A sentence read as a plan layer without its numbers: the laws' reading
/// (`layer_without_numbers`) without its range and its fade too, which the
/// color stage prints from the numbers.
fn layer_of(instruction: &SemanticInstruction) -> Option<WorkPlanLayer> {
    let mut cleared = instruction.clone();
    cleared.entity.numeric_range = None;
    cleared.entity.fade = None;
    layer_without_numbers(&cleared)
}

/// The DDL read as the color stage reads a printed plan: one layer for each
/// instruction, with its numbers. A layer that does not read takes another's
/// words (the colors print only the layers they change). `None` when no
/// sentence reads as a layer, or an instruction is not on a line.
#[must_use]
pub fn plan_of(source: &str, language: ResolvedInstructionLanguage) -> Option<DescribedPlan> {
    plan_of_with_definitions(source, language, &[])
}

pub fn plan_of_with_definitions(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> Option<DescribedPlan> {
    let instructions = instructions_of_with_definitions(source, language, definitions);
    let mut lines = Vec::new();
    let mut layers = Vec::new();
    let mut numeric = Vec::new();
    let mut rewritable = Vec::new();
    for instruction in &instructions {
        let at = instruction.entity.head.source().span.start_byte;
        if at > source.len() {
            return None;
        }
        lines.push(line_at(source, at));
        let layer = layer_of(instruction);
        rewritable.push(layer.is_some() && instruction.sequence.is_none());
        layers.push(layer);
        numeric.push(Some(numeric_of(instruction)));
    }
    let any = layers.iter().flatten().next()?.clone();
    let layers: Vec<WorkPlanLayer> = layers
        .into_iter()
        .map(|layer| layer.unwrap_or_else(|| any.clone()))
        .collect();
    let count = layers.len();
    Some(DescribedPlan {
        printed: PrintedPlan {
            plan: WorkPlan {
                ground: None,
                background: None,
                plugins: Vec::new(),
                layers,
            },
            ranges: vec![None; count],
            joints: vec![None; count],
            numeric,
        },
        lines,
        rewritable,
    })
}

/// The color request with the thing each layer draws after its message, as
/// the prototype sent it: one thing may be drawn in several layers.
pub fn with_layer_things(
    mut prompt: LlmPrompt,
    things: &[LayerThing],
    limits: PromptLimits,
) -> Result<LlmPrompt, PromptError> {
    let language = prompt.instruction_language;
    prompt.message.push_str(match language {
        ResolvedInstructionLanguage::Ja => {
            "\n\n## 層の物（読んで描くの構図と法則）\n層の表の番号の層が、どの物を描くか。一つの物が何層にも分かれることがある。\n"
        }
        ResolvedInstructionLanguage::En => {
            "\n\n## The things of the layers (read and draw's composition and laws)\nWhich thing each layer of the layer table draws. One thing may be drawn in several layers.\n"
        }
    });
    for (layer, item) in things.iter().enumerate() {
        prompt.message.push_str(&match language {
            ResolvedInstructionLanguage::Ja => {
                format!("- layer {layer}: 物 {}（{}）\n", item.thing, item.what)
            }
            ResolvedInstructionLanguage::En => {
                format!("- layer {layer}: thing {} ({})\n", item.thing, item.what)
            }
        });
    }
    crate::prompts::require_within(
        "message",
        prompt.message.len(),
        limits.max_source_bytes.saturating_mul(4),
    )?;
    prompt.prompt_digest = String::new();
    crate::prompts::finish_prompt(prompt)
}

/// The line with its color word rewritten to `color` where the parser read
/// it, when the line then reads that color; `None` otherwise. A Japanese
/// adjective (赤い, 黄色い) becomes the noun with の; an English word keeps
/// its capital.
#[cfg(test)]
fn recolored_line(
    line: &str,
    color: Color,
    language: ResolvedInstructionLanguage,
) -> Option<String> {
    recolored_line_with_definitions(line, color, language, &[])
}

fn recolored_line_with_definitions(
    line: &str,
    color: Color,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> Option<String> {
    let [instruction] = instructions_of_with_definitions(line, language, definitions)
        .try_into()
        .ok()?;
    let span = match &instruction.entity.head {
        SemanticHead::MacroInvocation(head) if head.object_aspect.is_some() => {
            &head
                .parameters
                .iter()
                .find(|parameter| {
                    matches!(&parameter.schema,
                ParameterSchema::SemanticRef { category, .. } if category == "color")
                })?
                .provenance
                .span
        }
        _ => &instruction.entity.color.as_ref()?.provenance.source.span,
    };
    let word = line.get(span.start_byte..span.end_byte)?;
    let mut replacement = color_word(color, language);
    match language {
        ResolvedInstructionLanguage::Ja => {
            if word.ends_with('い') {
                replacement.push('の');
            }
        }
        ResolvedInstructionLanguage::En => {
            if word.chars().next().is_some_and(char::is_uppercase) {
                let mut chars = replacement.chars();
                replacement = chars
                    .next()
                    .map(|first| first.to_uppercase().collect::<String>() + chars.as_str())
                    .unwrap_or_default();
            }
        }
    }
    let text = format!(
        "{}{replacement}{}",
        &line[..span.start_byte],
        &line[span.end_byte..]
    );
    let [again] = instructions_of_with_definitions(&text, language, definitions)
        .try_into()
        .ok()?;
    let reads = match &again.entity.head {
        SemanticHead::MacroInvocation(head) if head.object_aspect.is_some() => {
            head.parameters.iter().any(|parameter| {
                matches!(&parameter.value, SemanticMacroParameterValue::SemanticRef(identity)
                if identity.category == "color" && identity.id == color.as_str())
            })
        }
        _ => again.entity.color.as_ref().is_some_and(|term| {
            term.provenance.canonical_surface_ja
                == color_word(color, ResolvedInstructionLanguage::Ja)
        }),
    };
    reads.then_some(text)
}

/// One printed layer as its own sentence.
fn printed_line(
    printed: &PrintedPlan,
    at: usize,
    language: ResolvedInstructionLanguage,
    plugins: &[inku_ddl::work_plan::WorkPlanPlugin],
) -> String {
    print_work_plan_with_numbers(
        &WorkPlan {
            ground: None,
            background: None,
            plugins: Vec::new(),
            layers: vec![printed.plan.layers[at].clone()],
        },
        language,
        plugins,
        &[printed.ranges[at].clone()],
        &[printed.joints[at].as_deref()],
        &[printed.numeric[at].clone()],
    )
    .trim()
    .to_owned()
}

fn background_sentence(color: Color, language: ResolvedInstructionLanguage) -> String {
    print_work_plan_with_numbers(
        &WorkPlan {
            ground: None,
            background: Some(color.as_str().to_owned()),
            plugins: Vec::new(),
            layers: Vec::new(),
        },
        language,
        &[],
        &[],
        &[],
        &[],
    )
    .trim()
    .to_owned()
}

/// Write the chosen colors into the DDL the plan was read from: each changed
/// layer's color word, or the layer printed again, and the ground's
/// background sentence. The other lines stay as they are.
#[must_use]
pub fn apply_colors(
    source: &str,
    plan: &DescribedPlan,
    chosen: &ColorsChosen,
    language: ResolvedInstructionLanguage,
) -> (String, Vec<ColorsChange>) {
    apply_colors_with_definitions(source, plan, chosen, language, &[])
}

pub fn apply_colors_with_definitions(
    source: &str,
    plan: &DescribedPlan,
    chosen: &ColorsChosen,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> (String, Vec<ColorsChange>) {
    let plugins = crate::prompts::work_plan_plugins(definitions.iter());
    let print = &chosen.print;
    let background = background_line_of(source, language);
    let mut out = Vec::new();
    let mut changes = Vec::new();
    for (number, line) in source.lines().enumerate() {
        if let Some(ground) = chosen.ground
            && background == Some(number)
        {
            let after = background_sentence(ground, language);
            changes.push(ColorsChange {
                line: Some(number),
                how: ColorsChangeHow::Ground,
                before: line.to_owned(),
                after: vec![after.clone()],
            });
            out.push(after);
            continue;
        }
        let Some(layer) = plan.lines.iter().position(|at| *at == number) else {
            out.push(line.to_owned());
            continue;
        };
        let at: Vec<usize> = (0..print.from.len())
            .filter(|at| print.from[*at] == layer)
            .collect();
        let Some(&main) = at
            .last()
            .filter(|_| at.iter().any(|at| print.changed.contains(at)))
        else {
            out.push(line.to_owned());
            continue;
        };
        let kasane = at.iter().any(|at| print.under.contains(at));
        let before = &plan.printed.plan.layers[layer];
        let after = &print.printed.plan.layers[main];
        let mut before_rest = before.clone();
        let mut after_rest = after.clone();
        before_rest.attributes.remove(&WorkPlanSlot::Color);
        after_rest.attributes.remove(&WorkPlanSlot::Color);
        let color_only = !kasane
            && before_rest == after_rest
            && plan.printed.numeric[layer] == print.printed.numeric[main]
            && plan.rewritable[layer];
        let recolored = after
            .attributes
            .get(&WorkPlanSlot::Color)
            .and_then(|name| {
                Color::ALL
                    .iter()
                    .copied()
                    .find(|color| color.as_str() == name)
            })
            .filter(|_| color_only)
            .and_then(|color| recolored_line_with_definitions(line, color, language, definitions));
        let (how, lines) = match recolored {
            Some(text) => (ColorsChangeHow::ColorWord, vec![text]),
            None => (
                ColorsChangeHow::Printed,
                at.iter()
                    .map(|at| printed_line(&print.printed, *at, language, &plugins))
                    .collect(),
            ),
        };
        changes.push(ColorsChange {
            line: Some(number),
            how,
            before: line.to_owned(),
            after: lines.clone(),
        });
        out.extend(lines);
    }
    if let Some(ground) = chosen.ground
        && background.is_none()
    {
        // The ratio sentence stays first.
        let after = background_sentence(ground, language);
        changes.push(ColorsChange {
            line: None,
            how: ColorsChangeHow::GroundAdded,
            before: String::new(),
            after: vec![after.clone()],
        });
        out.insert(1.min(out.len()), after);
    }
    (out.join("\n"), changes)
}

#[cfg(test)]
mod tests {
    use inku_ddl::MacroDefinition;
    use inku_ddl::ResolvedInstructionLanguage::{En, Ja};
    use inku_ddl::work_plan::{NumericPlace, NumericSize};
    use inku_score::Color;

    use super::{
        background_line_of, background_sentence, plan_of, plan_of_with_definitions, recolored_line,
        recolored_line_with_definitions,
    };

    #[test]
    fn a_numeric_object_is_a_described_color_layer() {
        let definition = MacroDefinition::from_json(
            &serde_json::json!({
                "schema":"inku.macro-definition.v2", "namespace":"TestObject", "id":"Boat",
                "names":{"ja":["舟"],"en":["boat"]}, "kind":"object", "aspect":"2:1",
                "counter":"general", "version":"1.0.0", "parameters":{}, "components":{},
                "body":[{"op":"emit","binding":"hull","fields":{
                    "shape":{"expr":"semantic_ref","category":"shape","id":"arc"},
                    "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
                    "color":{"expr":"semantic_ref","category":"color","id":"green"},
                    "position_x":{"expr":"exact_decimal","value":"0.5"},
                    "position_y":{"expr":"exact_decimal","value":"0.5"},
                    "chord":{"expr":"exact_decimal","value":"0.6"},
                    "sagitta":{"expr":"exact_decimal","value":"0.2"}
                }}]
            })
            .to_string(),
        )
        .unwrap();
        let source = "画面の横0.3、縦0.7の位置に、一辺0.2の｛舟｝を置く。";
        let plan =
            plan_of_with_definitions(source, Ja, &[definition.clone()]).expect("object color plan");
        assert_eq!(plan.printed.plan.layers[0].shape, "TestObject.Boat");
        assert_eq!(plan.lines, [0]);
        let mut raw = serde_json::to_value(definition).unwrap();
        raw["parameters"]["hue"] = serde_json::json!({"type":"semantic_ref","category":"color"});
        raw["body"][0]["fields"]["color"] = serde_json::json!({"expr":"parameter","name":"hue"});
        let colored = MacroDefinition::from_json(&raw.to_string()).unwrap();
        assert!(
            colored.validate().is_valid(),
            "{:?}",
            colored.validate().diagnostics()
        );
        let parsed =
            super::instructions_of_with_definitions("赤い｛舟｝を置く。", Ja, &[colored.clone()]);
        assert_eq!(parsed.len(), 1);
        assert!(matches!(
            parsed[0].entity.head,
            inku_ddl::SemanticHead::MacroInvocation(_)
        ));
        assert_eq!(
            recolored_line_with_definitions("赤い｛舟｝を置く。", Color::Blue, Ja, &[colored])
                .as_deref(),
            Some("青の｛舟｝を置く。")
        );
    }

    const CYCLE: &str = "画面の横0.06、縦0.58から横0.94、縦0.58まで、青と緑を交互にして、幅0.05、高さ0.3の回転0度の塗りの四角を18個並べる。";

    #[test]
    fn each_sentence_is_a_layer_on_its_line_with_its_numbers() {
        let source = format!(
            "画面比1:1。\n背景を白で埋める。\n画面の横0.5、縦0.4の位置に、直径0.3の赤い円を1個置く。\n{CYCLE}"
        );
        let plan = plan_of(&source, Ja).unwrap();
        assert_eq!(plan.lines, [2, 3]);
        let numeric = plan.printed.numeric[0].as_ref().unwrap();
        assert_eq!(numeric.place, Some(NumericPlace::Point { at: [0.5, 0.4] }));
        assert_eq!(numeric.size, Some(NumericSize::Radius { radius: 0.15 }));
        // A sentence of a color cycle is printed again, never rewritten.
        assert_eq!(plan.rewritable, [true, false]);
        assert_eq!(background_line_of(&source, Ja), Some(1));
    }

    #[test]
    fn a_color_word_is_rewritten_where_the_parser_read_it() {
        assert_eq!(
            recolored_line(
                "画面の横0.5、縦0.4の位置に、直径0.3の赤い円を1個置く。",
                Color::Blue,
                Ja
            )
            .as_deref(),
            Some("画面の横0.5、縦0.4の位置に、直径0.3の青の円を1個置く。")
        );
        assert_eq!(
            recolored_line(
                "place one red flat circle diameter 0.3 at horizontal 0.5, vertical 0.4.",
                Color::Gray,
                En
            )
            .as_deref(),
            Some("place one gray flat circle diameter 0.3 at horizontal 0.5, vertical 0.4.")
        );
        assert_eq!(recolored_line("背景を白で埋める。", Color::Blue, Ja), None);
    }

    #[test]
    fn a_ground_prints_the_background_sentence() {
        assert_eq!(background_sentence(Color::Black, Ja), "背景を黒で埋める。");
        assert_eq!(
            background_sentence(Color::Black, En),
            "Fill the background with black."
        );
    }
}
